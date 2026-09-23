"""
Whale Bot V3 - Trailing-stop bot. Trades SPY, QQQ, AAPL, MSFT.
Supabase storage backend.
"""

import os, time, logging
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, StopOrderRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
import yfinance as yf
import pandas as pd

from common import (
    get_logger, send_telegram, log_run, is_market_open, is_market_bullish,
    drawdown_check, get_rsi_sma, get_peak_since, run_is_dry, should_halt,
    http_get, http_post, would_exceed_global_cap, positions_correlation_risk,
    estimate_regulatory_fees, _sb, SUPABASE_URL, SUPABASE_KEY
)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT"]
INITIAL_STOP_PCT = 0.025
TRAIL_PCT = 0.015
RISK_PER_TRADE = 0.02
MAX_POSITIONS = 2
TACTICAL_LIMIT_PCT = 0.10

BOT_NAME = "v3"
log = get_logger("v3", "v3_bot.log")
def L(m): print(m); log.info(m)

client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

def entry_info(sym):
    req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100)
    latest = None
    for o in client.get_orders(filter=req):
        if o.symbol == sym and o.side == OrderSide.BUY and o.filled_at:
            cid = (getattr(o, "client_order_id", "") or "")
            if cid and not cid.startswith(BOT_NAME + "_"):
                continue
            if latest is None or o.filled_at > latest.filled_at:
                latest = o
    if latest is None:
        return None, None
    return float(latest.filled_avg_price), latest.filled_at

def all_open_stops(sym):
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
    stops = []
    for o in client.get_orders(filter=req):
        if o.symbol == sym and o.side == OrderSide.SELL and o.order_type.value == "stop":
            stops.append(o)
    return stops

def log_entry(sym, qty, price, stop, score):
    try:
        if not SUPABASE_URL or not SUPABASE_KEY: return
        _sb().table("trades").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": sym, "side": "BUY",
            "qty": qty, "price": price, "stop": stop,
            "target": round(price*1.10, 2), "score": score, "threshold": 3,
            "signal_breakdown": "{'source':'v3','regime':True,'rsi':True,'sma':True}"
        }).execute()
    except Exception as e: L(f"⚠️ entry log: {e}")

def log_exit(sym, entry, exit_price, qty, peak=None, exit_timestamp=None):
    try:
        if not SUPABASE_URL or not SUPABASE_KEY: return
        pd_ = (exit_price - entry) * qty
        pp_ = (exit_price - entry) / entry * 100
        fees = estimate_regulatory_fees(exit_price, qty)
        payload = {
            "exit_timestamp": exit_timestamp or datetime.now(timezone.utc).isoformat(), "symbol": sym,
            "entry_price": round(entry, 2), "exit_price": round(exit_price, 2),
            "qty": qty, "exit_reason": "STOP_LOSS",
            "pnl_dollars": round(pd_, 2), "pnl_percent": round(pp_, 2),
            "signals_that_fired": "v3", "signal_score": 3, "signal_threshold": 3,
            "source": "v3", "fees": fees
        }
        if peak: payload["peak_price"] = round(peak, 4)
        _sb().table("exits").insert(payload).execute()
        L(f"📕 v3 exit {sym}: ${pd_:.2f} peak ${peak}")
        send_telegram(f"📕 *v3 exit*: {sym} | ${pd_:.2f} | peak ${peak}")
    except Exception as e: L(f"⚠️ exit log: {e}")

def log_exits_from_broker():
    try:
        if not SUPABASE_URL or not SUPABASE_KEY: return
        closed = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=100))
        existing = _sb().table("exits").select("symbol, exit_timestamp").execute()
        seen = {f"{r['symbol']}_{r['exit_timestamp']}" for r in (existing.data or [])}
        for o in closed:
            if o.side != OrderSide.SELL or not o.filled_at or not o.filled_avg_price: continue
            ts = o.filled_at.isoformat()
            if f"{o.symbol}_{ts}" in seen: continue
            ep, et = entry_info(o.symbol)
            if ep is None: continue
            xp = float(o.filled_avg_price); q = int(o.filled_qty)
            peak = get_peak_since(o.symbol, et) if et else None
            log_exit(o.symbol, ep, xp, q, peak, exit_timestamp=ts)
    except Exception as e: L(f"⚠️ log exits: {e}")

def update_trails():
    positions = client.get_all_positions()
    if not positions:
        L("No open positions.")
        return

    for p in positions:
        sym = p.symbol
        if sym not in WATCHLIST: continue
        q = int(float(p.qty))
        ep, et = entry_info(sym)
        if ep is None or et is None:
            L(f"  {sym}: no entry info, skipping")
            continue

        peak = get_peak_since(sym, et) or ep
        init = ep * (1 - INITIAL_STOP_PCT)
        trail = peak * (1 - TRAIL_PCT)
        target = round(max(init, trail), 2)

        stops = all_open_stops(sym)
        stop_prices = [float(s.stop_price) for s in stops if s.stop_price]
        tightest = max(stop_prices) if stop_prices else None

        L(f"  {sym}: entry ${ep:.2f} peak ${peak:.2f} target ${target:.2f} stops={stop_prices}")

        if len(stops) > 1:
            L(f"  🚨 {sym}: found {len(stops)} stops, cancelling extras")
            for s in stops:
                try: client.cancel_order_by_id(s.id)
                except Exception as e: L(f"  {sym}: cancel failed: {e}")
            time.sleep(2)
            stops = []
            tightest = None

        if tightest is not None and tightest >= target:
            L(f"  {sym}: existing stop ${tightest} already tight enough")
            continue

        if stops:
            for s in stops:
                try: client.cancel_order_by_id(s.id)
                except Exception as e: L(f"  {sym}: cancel failed: {e}")
            time.sleep(2)

        if run_is_dry():
            L(f"  {sym}: DRY would place stop ${target}")
            continue

        try:
            client.submit_order(StopOrderRequest(
                symbol=sym, qty=q, side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC, stop_price=target
            ))
            L(f"  {sym}: new stop placed @ ${target}")
        except Exception as e:
            L(f"  ❌ {sym}: stop placement failed: {e}")

def try_entry():
    if not is_market_bullish():
        L("regime: below 200MA")
        return "no_signal"

    a = client.get_account()
    eq = float(a.equity)
    pos = client.get_all_positions()
    held = [p.symbol for p in pos]
    if len(pos) >= MAX_POSITIONS:
        L(f"max positions ({len(pos)})")
        return "skipped"
    total = sum(float(p.market_value) for p in pos)
    cap = eq * TACTICAL_LIMIT_PCT
    if total >= cap:
        L(f"tactical cap (${total:.2f} / ${cap:.2f})")
        return "skipped"

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

            new_position_value = qty * close
            ok, exposure, gcap, _ = would_exceed_global_cap(client, new_position_value, L)
            if not ok:
                L(f"  ⛔ global cap — skipping {sym}")
                continue

            existing_syms = [p.symbol for p in pos if p.symbol != sym]
            corr_ok, worst_corr, corr_sym = positions_correlation_risk(sym, existing_syms, threshold=0.7, log_fn=L)
            if not corr_ok:
                L(f"  ⛔ correlated with {corr_sym} ({worst_corr:+.2f}) — skipping {sym}")
                continue

            L(f"🎯 V3 ENTRY {sym} qty {qty} @ ${close:.2f} stop ${stop}")
            if run_is_dry():
                send_telegram(f"🟡 *v3 DRY*: {sym} {qty} @ ${close:.2f}")
                return "traded"
            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=sym, qty=qty, side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                ))
                actual = close
                for _ in range(15):
                    time.sleep(2)
                    f = client.get_order_by_id(order.id)
                    if f.status.value == "filled":
                        actual = float(f.filled_avg_price or close)
                        break
                real_stop = round(actual * (1 - INITIAL_STOP_PCT), 2)
                client.submit_order(StopOrderRequest(
                    symbol=sym, qty=qty, side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC, stop_price=real_stop
                ))
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

    if should_halt("v3"):
        L("🛑 halted")
        log_run("v3", "error", error="halted due to consecutive failures")
        return

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
            log_run("v3", status, equity=float(a.equity),
                    positions=len(client.get_all_positions()))
        except Exception:
            log_run("v3", status)
    except Exception as e:
        L(f"entry: {e}"); log_run("v3", "error", error=str(e))

    L("="*60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}"); send_telegram(f"❌ v3 fatal: {e}")
