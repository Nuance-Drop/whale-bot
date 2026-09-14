"""
Whale Bot V3 - Backtested strategy. Trades SPY, QQQ, AAPL, MSFT. Trailing stops.
"""

import os, time, logging, traceback
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, StopOrderRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
import requests
import yfinance as yf
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pyairtable import Api

from common import (
    get_logger, send_telegram, log_run, is_market_open, is_market_bullish,
    drawdown_check, get_rsi_sma, get_peak_since, run_is_dry
)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID")
AIRTABLE_EXITS_TABLE_ID = os.environ.get("AIRTABLE_EXITS_TABLE_ID")

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]
INITIAL_STOP_PCT = 0.025
TRAIL_PCT = 0.015
RISK_PER_TRADE = 0.02
MAX_POSITIONS = 2
TACTICAL_LIMIT_PCT = 0.10

log = get_logger("v3", "v3_bot.log")
def L(m): print(m); log.info(m)
def phase(n): L(f"\n===== V3: {n} =====")

client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

def entry_info(sym):
    req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100)
    for o in client.get_orders(filter=req):
        if o.symbol == sym and o.side == OrderSide.BUY and o.filled_at:
            return float(o.filled_avg_price), o.filled_at
    return None, None

def open_stop(sym):
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
    for o in client.get_orders(filter=req):
        if o.symbol == sym and o.side == OrderSide.SELL and o.order_type.value == "stop":
            return o
    return None

def log_entry(sym, qty, price, stop, score):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID]): return
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID).create({
            "Timestamp": datetime.now().isoformat(), "Symbol": sym, "Side": "BUY",
            "Qty": qty, "Price": price, "Stop": stop,
            "Target": round(price*1.10, 2), "Score": score, "Threshold": 3,
            "Signal Breakdown": "{'source':'v3','regime':True,'rsi':True,'sma':True}"
        })
    except Exception as e: L(f"⚠️ entry log: {e}")

def log_exit(sym, entry, exit_price, qty, peak=None):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID]): return
        pd_ = (exit_price - entry) * qty
        pp_ = (exit_price - entry) / entry * 100
        payload = {
            "Exit Timestamp": datetime.now().isoformat(), "Symbol": sym,
            "Entry Price": round(entry, 2), "Exit Price": round(exit_price, 2),
            "Qty": qty, "Exit Reason": "STOP_LOSS",
            "PnL Dollars": round(pd_, 2), "PnL Percent": round(pp_, 2),
            "Signals That Fired": "v3", "Signal Score": 3, "Signal Threshold": 3
        }
        if peak: payload["Peak Price"] = round(peak, 4)
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID).create(payload)
        L(f"📕 v3 exit {sym}: ${pd_:.2f} peak ${peak}")
        send_telegram(f"📕 *v3 exit*: {sym} | ${pd_:.2f} | peak ${peak}")
    except Exception as e: L(f"⚠️ exit log: {e}")

def log_exits_from_broker():
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID]): return
        closed = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100))
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID)
        existing = table.all(fields=["Exit Timestamp", "Symbol"])
        seen = {f"{r['fields'].get('Symbol')}_{r['fields'].get('Exit Timestamp')}" for r in existing}
        for o in closed:
            if o.side != OrderSide.SELL or not o.filled_at or not o.filled_avg_price: continue
            ts = o.filled_at.isoformat()
            if f"{o.symbol}_{ts}" in seen: continue
            ep, et = entry_info(o.symbol)
            if ep is None: continue
            xp = float(o.filled_avg_price); q = int(o.filled_qty)
            peak = get_peak_since(o.symbol, et) if et else None
            log_exit(o.symbol, ep, xp, q, peak)
    except Exception as e: L(f"⚠️ log exits: {e}")

def update_trails():
    for p in client.get_all_positions():
        sym = p.symbol
        if sym not in WATCHLIST: continue
        q = int(float(p.qty))
        ep, et = entry_info(sym)
        if ep is None or et is None: continue
        peak = get_peak_since(sym, et) or ep
        init = ep * (1 - INITIAL_STOP_PCT)
        trail = peak * (1 - TRAIL_PCT)
        target = round(max(init, trail), 2)
        cur = open_stop(sym)
        cs = float(cur.stop_price) if cur and cur.stop_price else None
        L(f"  {sym}: entry ${ep:.2f} peak ${peak:.2f} target ${target:.2f} cur ${cs}")
        if cs is not None and cs >= target: continue
        if run_is_dry():
            L(f"  {sym}: DRY would update stop ${cs} → ${target}")
            continue
        if cur:
            try: client.cancel_order_by_id(cur.id)
            except Exception as e: L(f"  cancel: {e}")
        try:
            client.submit_order(StopOrderRequest(symbol=sym, qty=q, side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC, stop_price=target))
            L(f"  {sym}: new stop ${target}")
        except Exception as e: L(f"  stop: {e}")

def try_entry():
    if not is_market_bullish():
        L("regime: below 200MA"); return "no_signal"
    a = client.get_account(); eq = float(a.equity)
    pos = client.get_all_positions()
    held = [p.symbol for p in pos]
    if len(pos) >= MAX_POSITIONS: return "skipped"
    total = sum(float(p.market_value) for p in pos)
    cap = eq * TACTICAL_LIMIT_PCT
    if total >= cap: return "skipped"
    for sym in WATCHLIST:
        if sym in held: continue
        rsi, close, sma = get_rsi_sma(sym)
        if rsi is None: continue
        L(f"  {sym}: RSI {rsi:.1f} Close ${close:.2f} SMA50 ${sma:.2f}")
        if 35 < rsi < 55 and close > sma:
            stop = round(close * (1 - INITIAL_STOP_PCT), 2)
            remaining = cap - total
            risk = eq * RISK_PER_TRADE
            rps = close * INITIAL_STOP_PCT
            qty = min(int(risk/rps), int(remaining/close))
            if qty < 1: continue
            L(f"🎯 V3 entry {sym} qty {qty} @ ${close:.2f}")
            if run_is_dry():
                L(f"🟡 DRY would buy {sym}")
                send_telegram(f"🟡 *v3 DRY*: {sym} {qty} @ ${close:.2f}")
                return "traded"
            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
                actual = close
                for _ in range(15):
                    time.sleep(2)
                    f = client.get_order_by_id(order.id)
                    if f.status.value == "filled":
                        actual = float(f.filled_avg_price or close); break
                real_stop = round(actual * (1 - INITIAL_STOP_PCT), 2)
                client.submit_order(StopOrderRequest(symbol=sym, qty=qty, side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC, stop_price=real_stop))
                L(f"  ✅ filled ${actual:.2f} stop ${real_stop}")
                log_entry(sym, qty, actual, real_stop, 3)
                send_telegram(f"🚨 *v3*: {sym} {qty} @ ${actual:.2f}\nStop ${real_stop}")
                return "traded"
            except Exception as e:
                L(f"  ❌ {sym}: {e}")
                send_telegram(f"❌ v3 failed {sym}: {e}")
                return "error"
    L("no V3 signals")
    return "no_signal"

def run():
    L("="*60); L(f"v3 start {datetime.now().isoformat()}")
    if not is_market_open():
        L("market closed"); log_run("v3", "market_closed"); return
    L("--- drawdown ---")
    if drawdown_check(client, 0.05, L):
        log_run("v3", "error", error="drawdown halt"); return
    L("--- trails ---")
    try: update_trails()
    except Exception as e: L(f"trails: {e}")
    L("--- exits ---")
    try: log_exits_from_broker()
    except Exception as e: L(f"exits: {e}")
    L("--- entry ---")
    try:
        status = try_entry()
        try:
            a = client.get_account()
            log_run("v3", status, equity=float(a.equity), positions=len(client.get_all_positions()))
        except Exception: log_run("v3", status)
    except Exception as e:
        L(f"entry: {e}"); log_run("v3", "error", error=str(e))
    L("="*60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}"); send_telegram(f"❌ v3 fatal: {e}")
