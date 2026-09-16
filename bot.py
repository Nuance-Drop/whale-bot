"""
Whale Bot v10 - Full 8-signal trading.
Trades NVDA, GOOGL, META, AMZN. Max 2 positions, 10% tactical cap.
"""

import os, csv, time, json, logging, traceback
from datetime import datetime, timezone, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus

import yfinance as yf
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pyairtable import Api

from common import (
    get_logger, safe_request, send_telegram, log_run, is_market_open,
    is_market_bullish, drawdown_check, get_vix, spy_strength_pct,
    get_rsi_sma, run_is_dry, should_halt, http_get, http_post
)

# ---- config ----
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BARGO_API_KEY = os.environ.get("BARGO_API_KEY")
FORM4API_KEY = os.environ.get("FORM4API_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID")
AIRTABLE_EXITS_TABLE_ID = os.environ.get("AIRTABLE_EXITS_TABLE_ID")
AIRTABLE_FILLS_TABLE_ID = os.environ.get("AIRTABLE_FILLS_TABLE_ID")
KALSHI_API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID")
KALSHI_PRIVATE_KEY = os.environ.get("KALSHI_PRIVATE_KEY")

WATCHLIST = ["NVDA", "GOOGL", "META", "AMZN"]
RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.025
MAX_POSITIONS = 2
TACTICAL_LIMIT_PCT = 0.10
WEIGHTS_FILE = "signal_weights.json"

log = get_logger("v10", "bot.log")
def L(m): print(m); log.info(m)
def phase(n): L(f"\n===== V10: {n} =====")

DEFAULT_WEIGHTS = {"regime":1.0,"rsi":1.0,"sma":1.0,"sentiment":1.0,
                   "congress":2.0,"insider":2.0,"pead":1.0,"flow":2.0}
def load_weights():
    try:
        if os.path.isfile(WEIGHTS_FILE):
            with open(WEIGHTS_FILE) as f: return json.load(f)
    except Exception: pass
    return DEFAULT_WEIGHTS
W = load_weights()

analyzer = SentimentIntensityAnalyzer()
client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

# ---- kalshi ----
KALSHI_URL = "https://external-api.kalshi.com/trade-api/v2"
def kalshi_macro():
    try:
        if not KALSHI_API_KEY_ID: return 0
        r = http_get(f"{KALSHI_URL}/markets", params={"limit":20,"status":"open"})
        if r is None or r.status_code != 200: return 0
        for m in r.json().get("markets", []):
            t = (m.get("title") or "").lower()
            y = float(m.get("yes_bid", 0))/100 if m.get("yes_bid") else 0.5
            if any(k in t for k in ["recession","rate hike","crash","default"]) and y > 0.60:
                return -1
            if any(k in t for k in ["rate cut","soft landing","growth"]) and y > 0.60:
                return 1
        return 0
    except Exception: return 0

# ---- signals ----
def congress_sig(sym):
    try:
        if not BARGO_API_KEY: return False
        r = http_get("https://www.bargo.ai/free-apis/congress/v1/trades",
            headers={"X-Api-Key": BARGO_API_KEY},
            params={"ticker":sym,"type":"buy",
                    "fromDate":(datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d")})
        return r is not None and r.status_code == 200 and len(r.json().get("trades", [])) > 0
    except Exception: return False

def insider_sig(sym):
    try:
        if not FORM4API_KEY: return False
        r = http_get(f"https://api.form4api.com/v1/insider/trades/{sym}",
            headers={"Authorization": f"Bearer {FORM4API_KEY}"})
        if r is None or r.status_code != 200: return False
        cutoff = datetime.now() - timedelta(days=30)
        for t in r.json().get("trades", []):
            if pd.to_datetime(t.get("filingDate","2000-01-01")) > cutoff and t.get("transactionCode") in ["P","A"]:
                return True
        return False
    except Exception: return False

def pead_sig(sym):
    try:
        e = yf.Ticker(sym).earnings_dates
        if e is None or e.empty: return False
        for idx, row in e.iterrows():
            ed = pd.Timestamp(idx).tz_localize(None)
            if pd.Timestamp.now() - ed > pd.Timedelta(days=30): continue
            try:
                if float(row.get('Reported EPS', 0)) > float(row.get('EPS Estimate', 0)): return True
            except Exception: pass
        return False
    except Exception: return False

def flow_sig(sym):
    try:
        r = http_post("https://mcp.gammarips.com/mcp",
                      json={"method":"get_daily_report"})
        if r is None or r.status_code != 200: return False
        return any(i.get('symbol') == sym for i in r.json().get('bullish_pool', []))
    except Exception: return False

def senti_sig(sym):
    try:
        n = yf.Ticker(sym).news
        if not n: return False
        s = [analyzer.polarity_scores(i.get('title') or i.get('content',{}).get('title',''))['compound']
             for i in n[:5] if i.get('title') or i.get('content',{}).get('title')]
        return (sum(s)/len(s)) > 0.1 if s else False
    except Exception: return False

def calc_score(sym):
    score = 0; sigs = {}
    if not is_market_bullish(): return 0, {"regime": False}
    score += W.get("regime",1.0); sigs['regime'] = True
    k = kalshi_macro()
    if k: score += k; sigs['kalshi'] = k
    rsi, close, sma = get_rsi_sma(sym)
    if rsi is not None:
        if 35 < rsi < 55: score += W.get("rsi",1.0); sigs['rsi'] = True
        if close > sma: score += W.get("sma",1.0); sigs['sma'] = True
        L(f"  {sym}: RSI {rsi:.1f} Close ${close:.2f} SMA50 ${sma:.2f}")
    if senti_sig(sym): score += W.get("sentiment",1.0); sigs['sentiment'] = True
    if congress_sig(sym): score += W.get("congress",2.0); sigs['congress'] = True
    if insider_sig(sym): score += W.get("insider",2.0); sigs['insider'] = True
    if pead_sig(sym): score += W.get("pead",1.0); sigs['pead'] = True
    if flow_sig(sym): score += W.get("flow",2.0); sigs['flow'] = True
    L(f"  {sym} SCORE {score:.2f} | {sigs}")
    return score, sigs

def dyn_threshold(n):
    t = 4.0; reasons = []
    rs = spy_strength_pct()
    if rs < 0: return 999, ["regime_block"]
    elif rs < 2: t += 1; reasons.append("fragile(+1)")
    elif rs > 5: t -= 1; reasons.append("strong bull(-1)")
    v = get_vix()
    if v > 30: t += 2; reasons.append(f"VIX {v:.1f}(+2)")
    elif v > 20: t += 1; reasons.append(f"VIX {v:.1f}(+1)")
    elif v < 15: t -= 1; reasons.append(f"VIX {v:.1f}(-1)")
    if datetime.now().month in [1,4,7,10]: t += 1; reasons.append("earnings(+1)")
    if n >= 2: t += 1; reasons.append(f"holding {n}(+1)")
    now = datetime.now(timezone.utc)
    if now.weekday() == 0 and now.hour < 16: t += 1; reasons.append("Mon AM(+1)")
    return max(3.0, min(t, 15.0)), reasons

def score_mult_fn(s, t):
    g = s - t
    if g <= 0: return 0.5
    if g <= 1: return 0.75
    if g <= 2: return 1.0
    if g <= 3: return 1.25
    return 1.5

def atr_mult(sym, lb=20):
    try:
        df = yf.Ticker(sym).history(period="3mo", interval="1d", auto_adjust=True)
        if len(df) < lb + 5: return 1.0
        h, l, c = df['High'], df['Low'], df['Close']
        tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        a = tr.iloc[-lb:].mean(); m = tr.iloc[-60:].median()
        if m == 0 or a == 0: return 1.0
        return max(0.5, min(m/a, 1.5))
    except Exception: return 1.0

# ---- airtable ----
def log_entry(sym, qty, price, stop, target, score, th, sigs):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID]): return
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID).create({
            "Timestamp": datetime.now().isoformat(), "Symbol": sym, "Side": "BUY",
            "Qty": qty, "Price": price, "Stop": stop, "Target": target,
            "Score": score, "Threshold": th, "Signal Breakdown": json.dumps(sigs)
        })
    except Exception as e: L(f"⚠️ entry log: {e}")

def log_exit(sym, entry, exit_price, qty, reason, peak=None):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID]): return
        pnl_d = (exit_price - entry) * qty
        pnl_p = (exit_price - entry) / entry * 100
        payload = {
            "Exit Timestamp": datetime.now().isoformat(), "Symbol": sym,
            "Entry Price": round(entry, 2), "Exit Price": round(exit_price, 2),
            "Qty": qty, "Exit Reason": reason,
            "PnL Dollars": round(pnl_d, 2), "PnL Percent": round(pnl_p, 2),
            "Signals That Fired": "v10", "Signal Score": 0, "Signal Threshold": 0,
            "Source": "v10"
        }
        if peak: payload["Peak Price"] = round(peak, 4)
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID).create(payload)
        L(f"📕 exit {sym}: ${pnl_d:.2f}")
        send_telegram(f"📕 *v10 exit*: {sym} | ${pnl_d:.2f}")
    except Exception as e: L(f"⚠️ exit log: {e}")

def log_fill(sym, otype, exp, actual, oid=None):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_FILLS_TABLE_ID]): return
        sd = actual - exp; sp = (sd / exp) * 100
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_FILLS_TABLE_ID).create({
            "Timestamp": datetime.now().isoformat(), "Symbol": sym, "Order Type": otype,
            "Expected Price": round(exp, 4), "Actual Fill Price": round(actual, 4),
            "Slippage ($)": round(sd, 4), "Slippage (%)": round(sp, 4),
            "Order ID": str(oid or "")
        })
    except Exception as e: L(f"⚠️ fill log: {e}")

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
            reason = "OTHER"
            try:
                if o.order_type.value == "stop": reason = "STOP_LOSS"
                elif o.order_type.value == "limit": reason = "TAKE_PROFIT"
            except Exception: pass
            log_exit(o.symbol, ep, xp, q, reason)
    except Exception as e: L(f"⚠️ log_exits: {e}")

def place_bracket(sym, qty, entry, score, th, sigs, mult):
    stop = round(entry*(1-STOP_LOSS_PCT), 2)
    target = round(entry*1.05, 2)
    if run_is_dry():
        L(f"🟡 DRY: would place BUY {qty} {sym} @ ${entry:.2f} SL ${stop} TP ${target}")
        send_telegram(f"🟡 *DRY*: {sym} {qty} @ ${entry:.2f}")
        log_run("v10", "skipped", top_candidate=sym, top_score=score,
                action=f"DRY would buy {qty} @ ${entry:.2f}")
        return None
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=sym, qty=qty, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=target),
            stop_loss=StopLossRequest(stop_price=stop)))
        time.sleep(2)
        try:
            f = client.get_order_by_id(order.id)
            actual = float(f.filled_avg_price or entry)
        except Exception: actual = entry
        log_fill(sym, "Entry", entry, actual, order.id)
        L(f"✅ {sym} {qty} @ ${actual:.2f}")
        send_telegram(f"🚨 *v10*: {sym} {qty} @ ${actual:.2f}\nSL ${stop} TP ${target}\nScore {score:.2f}/{th:.2f}")
        log_entry(sym, qty, actual, stop, target, score, th, sigs)
        log_run("v10", "traded", top_candidate=sym, top_score=score,
                action=f"BUY {qty} @ ${actual:.2f}")
    except Exception as e:
        L(f"❌ order: {e}")
        log_run("v10", "error", top_candidate=sym, error=str(e))

def run():
    L("="*60); L(f"v10 start {datetime.now().isoformat()}")
    if not is_market_open():
        L("market closed"); log_run("v10", "market_closed"); return

    if should_halt("v10"):
        L("🛑 halted due to consecutive failures")
        log_run("v10", "error", error="halted due to consecutive failures")
        return

    L("--- drawdown ---")
    if drawdown_check(client, 0.05, L):
        log_run("v10", "error", error="drawdown halt"); return

    L("--- exits ---")
    log_exits_from_broker()

    try:
        a = client.get_account(); eq = float(a.equity)
    except Exception as e:
        L(f"❌ account: {e}"); log_run("v10", "error", error=str(e)); return

    L("--- positions ---")
    pos = client.get_all_positions()
    held = {p.symbol for p in pos}
    for o in client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)):
        held.add(o.symbol)
    total = sum(float(p.market_value) for p in pos)
    cap = eq * TACTICAL_LIMIT_PCT
    L(f"Equity ${eq:.2f} | Exposure ${total:.2f} | Cap ${cap:.2f} | Held {held}")

    th, rs = dyn_threshold(len(held))
    L(f"📊 Threshold {th:.2f}")
    for r in rs: L(f"   → {r}")

    if th > 15:
        log_run("v10", "skipped", equity=eq, positions=len(held), threshold=th, error="threshold too high"); return
    if total >= cap:
        log_run("v10", "skipped", equity=eq, positions=len(held), threshold=th, error="tactical cap"); return
    if len(held) >= MAX_POSITIONS:
        log_run("v10", "skipped", equity=eq, positions=len(held), threshold=th, error="max positions"); return

    L("--- scoring ---")
    cands = []
    for s in WATCHLIST:
        if s in held: continue
        try:
            sc, sig = calc_score(s)
            if sc >= th: cands.append((s, sc, sig))
            else: L(f"  ❌ {s}: {sc:.2f} < {th:.2f}")
        except Exception as e: L(f"  ❌ {s}: {e}")

    if not cands:
        log_run("v10", "no_signal", equity=eq, positions=len(held), threshold=th); return

    cands.sort(key=lambda x: x[1], reverse=True)
    s, sc, sig = cands[0]
    mult = score_mult_fn(sc, th) * atr_mult(s)
    L(f"🎯 {s} | {sc:.2f}/{th:.2f} | {mult:.2f}x")

    try:
        h = yf.Ticker(s).history(period="1d", auto_adjust=True)
        price = float(h['Close'].iloc[-1])
        remaining = cap - total
        risk = eq * RISK_PER_TRADE * mult
        rps = price * STOP_LOSS_PCT
        qty = min(int(risk/rps), int(remaining/price))
        if qty < 1:
            log_run("v10", "skipped", equity=eq, positions=len(held), threshold=th, error="qty < 1"); return
        place_bracket(s, qty, price, sc, th, sig, mult)
    except Exception as e:
        L(f"❌ exec: {e}"); log_run("v10", "error", error=str(e))

    L("="*60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}"); send_telegram(f"❌ v10 fatal: {e}")
