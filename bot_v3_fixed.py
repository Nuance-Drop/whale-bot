"""
Whale Bot v3_fixed - V3 entries with FIXED bracket exits.
Isolates entry quality from exit quality.
"""

import os, time, logging
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
import yfinance as yf
from pyairtable import Api

from common import (
    get_logger, send_telegram, log_run, is_market_open, is_market_bullish,
    drawdown_check, get_rsi_sma, run_is_dry, should_halt, http_get, http_post
)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID")
AIRTABLE_EXITS_TABLE_ID = os.environ.get("AIRTABLE_EXITS_TABLE_ID")

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]
STOP_LOSS_PCT = 0.025
TAKE_PROFIT_PCT = 0.05
RISK_PER_TRADE = 0.02
MAX_POSITIONS = 2
TACTICAL_LIMIT_PCT = 0.10

log = get_logger("v3_fixed", "v3_fixed_bot.log")
def L(m): print(m); log.info(m)

client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

def log_entry(sym, qty, price, stop, target):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID]): return
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID).create({
            "Timestamp": datetime.now().isoformat(), "Symbol": sym, "Side": "BUY",
            "Qty": qty, "Price": price, "Stop": stop, "Target": target,
            "Score": 3, "Threshold": 3,
            "Signal Breakdown": "{'source':'v3_fixed','regime':True,'rsi':True,'sma':True}"
        })
    except Exception as e: L(f"⚠️ entry log: {e}")

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
            ep = None
            for x in closed:
                if x.symbol == o.symbol and x.side == OrderSide.BUY and x.filled_at and x.filled_avg_price:
                    ep = float(x.filled_avg_price); break
            if ep is None: continue
            xp = float(o.filled_avg_price); q = int(o.filled_qty)
            pd_ = (xp - ep) * q; pp_ = (xp - ep) / ep * 100
            reason = "OTHER"
            try:
                if o.order_type.value == "stop": reason = "STOP_LOSS"
                elif o.order_type.value == "limit": reason = "TAKE_PROFIT"
            except Exception: pass
            table.create({
                "Exit Timestamp": ts, "Symbol": o.symbol,
                "Entry Price": round(ep, 2), "Exit Price": round(xp, 2),
                "Qty": q, "Exit Reason": reason,
                "PnL Dollars": round(pd_, 2), "PnL Percent": round(pp_, 2),
                "Signals That Fired": "v3_fixed", "Signal Score": 3, "Signal Threshold": 3,
                "Source": "v3_fixed"
            })
            L(f"📕 v3_fixed exit {o.symbol}: ${pd_:.2f}")
            send_telegram(f"📕 *v3_fixed exit*: {o.symbol} | ${pd_:.2f}")
    except Exception as e: L(f"⚠️ log exits: {e}")

def try_entry():
    if not is_market_bullish():
        L("regime below 200MA"); return "no_signal"
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
            stop = round(close * (1 - STOP_LOSS_PCT), 2)
            target = round(close * (1 + TAKE_PROFIT_PCT), 2)
            remaining = cap - total
            risk = eq * RISK_PER_TRADE
            rps = close * STOP_LOSS_PCT
            qty = min(int(risk/rps), int(remaining/close))
            if qty < 1: continue
            L(f"🎯 v3_fixed {sym} qty {qty} @ ${close:.2f} SL ${stop} TP ${target}")
            if run_is_dry():
                send_telegram(f"🟡 *v3_fixed DRY*: {sym} {qty} @ ${close:.2f}")
                return "traded"
            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=sym, qty=qty, side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY, order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=target),
                    stop_loss=StopLossRequest(stop_price=stop)))
                L(f"  ✅ {sym} submitted")
                log_entry(sym, qty, close, stop, target)
                send_telegram(f"🚨 *v3_fixed*: {sym} {qty} @ ${close:.2f}\nSL ${stop} TP ${target}")
                return "traded"
            except Exception as e:
                L(f"  ❌ {sym}: {e}")
                send_telegram(f"❌ v3_fixed failed {sym}: {e}")
                return "error"
    return "no_signal"

def run():
    L("="*60); L(f"v3_fixed start {datetime.now().isoformat()}")
    if not is_market_open():
        L("market closed"); log_run("v3_fixed", "market_closed"); return

    if should_halt("v3_fixed"):
        L("🛑 halted due to consecutive failures")
        log_run("v3_fixed", "error", error="halted due to consecutive failures")
        return

    if drawdown_check(client, 0.05, L):
        log_run("v3_fixed", "error", error="drawdown halt"); return

    try: log_exits_from_broker()
    except Exception as e: L(f"exits: {e}")

    status = "error"
    try:
        status = try_entry()
        a = client.get_account()
        log_run("v3_fixed", status, equity=float(a.equity),
                positions=len(client.get_all_positions()))
    except Exception as e:
        L(f"entry: {e}"); log_run("v3_fixed", "error", error=str(e))
    L("="*60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}"); send_telegram(f"❌ v3_fixed fatal: {e}")
