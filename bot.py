"""
Whale Bot v10 - Full Learning Loop Runtime
- Multi-signal confluence with dynamic weights (loaded from signal_weights.json)
- Volatility-targeted position sizing (ATR-based)
- Kill switch check at startup
- Full Airtable logging: entries, exits, fills
- Exponential backoff on all API calls
- Clear phase markers in logs for debugging
"""

import os, csv, time, json, random, logging, requests, traceback
from datetime import datetime, time, timezone, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
)
from alpaca.trading.enums import (
    OrderSide, TimeInForce, OrderClass, QueryOrderStatus
)
import yfinance as yf
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pyairtable import Api

# ============================================================
# API KEYS & CONFIG
# ============================================================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
APIFY_API_KEY = os.environ.get("APIFY_API_KEY")
FORM4API_KEY = os.environ.get("FORM4API_KEY")
BARGO_API_KEY = os.environ.get("BARGO_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID")
AIRTABLE_EXITS_TABLE_ID = os.environ.get("AIRTABLE_EXITS_TABLE_ID")
AIRTABLE_FILLS_TABLE_ID = os.environ.get("AIRTABLE_FILLS_TABLE_ID")
KALSHI_API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID")
KALSHI_PRIVATE_KEY = os.environ.get("KALSHI_PRIVATE_KEY")

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN"]
RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.025
MAX_POSITIONS = 3
TACTICAL_LIMIT_PCT = 0.20
KILL_SWITCH_DRAWDOWN = 0.05   # Close all if equity drops 5% from peak

WEIGHTS_FILE = "signal_weights.json"
PEAK_FILE = "peak_equity.txt"
LOG_FILE = "trade_log.csv"
BOT_LOG = "bot.log"

logging.basicConfig(filename=BOT_LOG, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
def log(msg):
    print(msg)
    logging.info(msg)

def phase(name):
    log(f"\n{'='*20} PHASE: {name} {'='*20}")

# ============================================================
# LOAD SIGNAL WEIGHTS
# ============================================================
DEFAULT_WEIGHTS = {
    "regime": 1.0, "rsi": 1.0, "sma": 1.0, "sentiment": 1.0,
    "congress": 2.0, "insider": 2.0, "pead": 1.0, "flow": 2.0
}

def load_signal_weights():
    try:
        if os.path.isfile(WEIGHTS_FILE):
            with open(WEIGHTS_FILE) as f:
                weights = json.load(f)
            log(f"✅ Loaded weights from {WEIGHTS_FILE}: {weights}")
            return weights
        log(f"⚠️ {WEIGHTS_FILE} not found, using defaults")
        return DEFAULT_WEIGHTS
    except Exception as e:
        log(f"⚠️ Failed to load weights ({e}), using defaults")
        return DEFAULT_WEIGHTS

SIGNAL_WEIGHTS = load_signal_weights()

# ============================================================
# EXPONENTIAL BACKOFF
# ============================================================
def safe_request(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if hasattr(result, 'status_code') and result.status_code in [429, 500, 502, 503, 504]:
                wait = (2 ** attempt) + random.uniform(0, 1)
                log(f"⚠️ API {result.status_code}, retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            return result
        except (requests.exceptions.RequestException, ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            log(f"⚠️ {e}, retrying in {wait:.1f}s")
            time.sleep(wait)
    return None

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(message):
    try:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        safe_request(requests.post, url, json={
            "chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        log(f"⚠️ Telegram failed: {e}")

# ============================================================
# KALSHI MACRO
# ============================================================
KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

def kalshi_macro_signal():
    try:
        if not KALSHI_API_KEY_ID:
            return 0
        r = safe_request(requests.get, f"{KALSHI_BASE_URL}/markets",
                         params={"limit": 20, "status": "open"}, timeout=15)
        if r is None or r.status_code != 200:
            return 0
        for m in r.json().get("markets", []):
            title = (m.get("title") or "").lower()
            yes = float(m.get("yes_bid", 0)) / 100 if m.get("yes_bid") else 0.5
            if any(kw in title for kw in ["recession", "rate hike", "crash", "default"]):
                if yes > 0.60:
                    log(f"  📉 Kalshi macro: {title} @ {yes:.0%} — risk-off")
                    return -1
            elif any(kw in title for kw in ["rate cut", "soft landing", "growth"]):
                if yes > 0.60:
                    log(f"  📈 Kalshi macro: {title} @ {yes:.0%} — risk-on")
                    return +1
        return 0
    except Exception as e:
        log(f"⚠️ Kalshi macro error: {e}")
        return 0

# ============================================================
# AIRTABLE LOGGING
# ============================================================
def log_entry(symbol, side, qty, price, stop, target, score, threshold, signals_dict):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID]):
            log("⚠️ Airtable entry credentials missing")
            return
        api = Api(AIRTABLE_API_KEY)
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        table.create({
            "Timestamp": datetime.now().isoformat(),
            "Symbol": symbol, "Side": str(side), "Qty": qty,
            "Price": price, "Stop": stop, "Target": target,
            "Score": score, "Threshold": threshold,
            "Signal Breakdown": json.dumps(signals_dict)
        })
        log(f"✅ Entry logged: {symbol}")
    except Exception as e:
        log(f"⚠️ Entry log failed: {e}")

def log_exits():
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID]):
            return
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50)
        closed = client.get_orders(filter=req)
        api = Api(AIRTABLE_API_KEY)
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_EXITS_TABLE_ID)
        existing = table.all(fields=["Exit Timestamp", "Symbol"])
        seen = {f"{r['fields'].get('Symbol')}_{r['fields'].get('Exit Timestamp')}" for r in existing}
        count = 0
        for order in closed:
            if order.side != OrderSide.SELL or order.filled_at is None or order.filled_avg_price is None:
                continue
            ts = order.filled_at.isoformat()
            if f"{order.symbol}_{ts}" in seen:
                continue
            reason = "OTHER"
            try:
                if order.order_type.value == "stop": reason = "STOP_LOSS"
                elif order.order_type.value == "limit": reason = "TAKE_PROFIT"
                elif order.order_type.value == "market": reason = "MANUAL"
            except Exception: pass
            entry_price = None
            for o in closed:
                if (o.symbol == order.symbol and o.side == OrderSide.BUY
                        and o.filled_at and o.filled_avg_price):
                    entry_price = float(o.filled_avg_price)
                    break
            if entry_price is None: continue
            exit_price = float(order.filled_avg_price)
            qty = int(order.filled_qty)
            pnl_d = (exit_price - entry_price) * qty
            pnl_p = (exit_price - entry_price) / entry_price * 100
            table.create({
                "Exit Timestamp": ts, "Symbol": order.symbol,
                "Entry Price": round(entry_price, 2), "Exit Price": round(exit_price, 2),
                "Qty": qty, "Exit Reason": reason,
                "PnL Dollars": round(pnl_d, 2), "PnL Percent": round(pnl_p, 2),
                "Signals That Fired": "", "Signal Score": 0, "Signal Threshold": 0
            })
            log(f"📕 Exit logged: {order.symbol} PnL ${pnl_d:.2f}")
            count += 1
        if count > 0:
            send_telegram(f"📕 {count} trade(s) exited since last check")
    except Exception as e:
        log(f"⚠️ Exit log failed: {e}")

def log_fill(symbol, order_type, expected, actual, order_id=None):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_FILLS_TABLE_ID]):
            return
        slip_d = actual - expected
        slip_p = (slip_d / expected) * 100
        api = Api(AIRTABLE_API_KEY)
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_FILLS_TABLE_ID)
        table.create({
            "Timestamp": datetime.now().isoformat(),
            "Symbol": symbol, "Order Type": order_type,
            "Expected Price": round(expected, 4), "Actual Fill Price": round(actual, 4),
            "Slippage ($)": round(slip_d, 4), "Slippage (%)": round(slip_p, 4),
            "Order ID": str(order_id or "")
        })
        log(f"📝 Fill logged: {symbol} {order_type} slip {slip_p:+.4f}%")
    except Exception as e:
        log(f"⚠️ Fill log failed: {e}")

# ============================================================
# KILL SWITCH
# ============================================================
def check_kill_switch(equity):
    try:
        peak = float(open(PEAK_FILE).read().strip()) if os.path.isfile(PEAK_FILE) else equity
        if equity > peak:
            peak = equity
            with open(PEAK_FILE, "w") as f:
                f.write(str(peak))
        drawdown = (peak - equity) / peak
        if drawdown >= KILL_SWITCH_DRAWDOWN:
            log(f"🛑 KILL SWITCH: Drawdown {drawdown:.2%} >= {KILL_SWITCH_DRAWDOWN:.0%}")
            send_telegram(f"🛑 *KILL SWITCH TRIGGERED*\nDrawdown: {drawdown:.2%}\nClosing all positions.")
            client.close_all_positions(cancel_orders=True)
            return True
        return False
    except Exception as e:
        log(f"⚠️ Kill switch check failed: {e}")
        return False

# ============================================================
# MARKET REGIME
# ============================================================
def is_market_bullish():
    spy = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex): spy.columns = spy.columns.get_level_values(0)
    spy['SMA200'] = spy['Close'].rolling(200).mean()
    return spy['Close'].iloc[-1] > spy['SMA200'].iloc[-1]

# ============================================================
# SIGNALS
# ============================================================
def congressional_signal(symbol):
    try:
        if not BARGO_API_KEY: return False
        r = safe_request(requests.get, "https://www.bargo.ai/free-apis/congress/v1/trades",
                         headers={"X-Api-Key": BARGO_API_KEY},
                         params={"ticker": symbol, "type": "buy",
                                 "fromDate": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")},
                         timeout=15)
        return r is not None and r.status_code == 200 and len(r.json().get("trades", [])) > 0
    except Exception: return False

def insider_signal(symbol):
    try:
        if not FORM4API_KEY: return False
        r = safe_request(requests.get, f"https://api.form4api.com/v1/insider/trades/{symbol}",
                         headers={"Authorization": f"Bearer {FORM4API_KEY}"}, timeout=15)
        if r is None or r.status_code != 200: return False
        cutoff = datetime.now() - timedelta(days=30)
        for t in r.json().get("trades", []):
            if pd.to_datetime(t.get("filingDate", "2000-01-01")) > cutoff and t.get("transactionCode") in ["P", "A"]:
                return True
        return False
    except Exception: return False

def pead_signal(symbol):
    try:
        earnings = yf.Ticker(symbol).earnings_dates
        if earnings is None or earnings.empty: return False
        for idx, row in earnings.iterrows():
            ed = pd.Timestamp(idx).tz_localize(None)
            if pd.Timestamp.now() - ed > pd.Timedelta(days=30): continue
            try:
                if float(row.get('Reported EPS', 0)) > float(row.get('EPS Estimate', 0)): return True
            except Exception: continue
        return False
    except Exception: return False

def options_flow_signal(symbol):
    try:
        r = safe_request(requests.post, "https://mcp.gammarips.com/mcp",
                         json={"method": "get_daily_report"}, timeout=10)
        if r is None or r.status_code != 200: return False
        return any(item.get('symbol') == symbol for item in r.json().get('bullish_pool', []))
    except Exception: return False

def technical_signal(symbol):
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50: return (False, False)
        df['SMA50'] = df['Close'].rolling(50).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))
        last = df.iloc[-1]
        log(f"  {symbol}: RSI={last['RSI']:.1f} Close={last['Close']:.2f} SMA50={last['SMA50']:.2f}")
        return (35 < last['RSI'] < 55, last['Close'] > last['SMA50'])
    except Exception as e:
        log(f"⚠️ Technical error on {symbol}: {e}")
        return (False, False)

analyzer = SentimentIntensityAnalyzer()
def sentiment_signal(symbol):
    try:
        news = yf.Ticker(symbol).news
        if not news: return False
        scores = [analyzer.polarity_scores(item.get('title') or item.get('content', {}).get('title', ''))['compound']
                  for item in news[:5] if item.get('title') or item.get('content', {}).get('title')]
        return (sum(scores) / len(scores)) > 0.1 if scores else False
    except Exception: return False

# ============================================================
# SCORING
# ============================================================
def calculate_score(symbol):
    score = 0; signals = {}
    if not is_market_bullish(): return 0, {"regime": False}
    score += SIGNAL_WEIGHTS.get("regime", 1.0); signals['regime'] = True
    kalshi_adj = kalshi_macro_signal()
    if kalshi_adj != 0:
        score += kalshi_adj; signals['kalshi_macro'] = kalshi_adj
    rsi_ok, sma_ok = technical_signal(symbol)
    if rsi_ok: score += SIGNAL_WEIGHTS.get("rsi", 1.0); signals['rsi'] = True
    if sma_ok: score += SIGNAL_WEIGHTS.get("sma", 1.0); signals['sma'] = True
    if sentiment_signal(symbol): score += SIGNAL_WEIGHTS.get("sentiment", 1.0); signals['sentiment'] = True
    if congressional_signal(symbol): score += SIGNAL_WEIGHTS.get("congress", 2.0); signals['congress'] = True
    if insider_signal(symbol): score += SIGNAL_WEIGHTS.get("insider", 2.0); signals['insider'] = True
    if pead_signal(symbol): score += SIGNAL_WEIGHTS.get("pead", 1.0); signals['pead'] = True
    if options_flow_signal(symbol): score += SIGNAL_WEIGHTS.get("flow", 2.0); signals['flow'] = True
    log(f"  {symbol} SCORE: {score:.2f} | Signals: {signals}")
    return score, signals

# ============================================================
# DYNAMIC THRESHOLD
# ============================================================
def get_vix_level():
    try:
        vix = yf.download("^VIX", period="5d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex): vix.columns = vix.columns.get_level_values(0)
        return float(vix['Close'].iloc[-1])
    except Exception: return 20.0

def get_spy_regime_strength():
    try:
        spy = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(spy.columns, pd.MultiIndex): spy.columns = spy.columns.get_level_values(0)
        spy['SMA200'] = spy['Close'].rolling(200).mean()
        return (spy['Close'].iloc[-1] - spy['SMA200'].iloc[-1]) / spy['SMA200'].iloc[-1] * 100
    except Exception: return 0.0

def calculate_dynamic_threshold(num_positions):
    threshold = 4.0; reasons = []
    rs = get_spy_regime_strength()
    if rs < 0:
        log(f"  🚫 SPY below 200MA ({rs:.1f}%)")
        return 999, ["regime_block"]
    elif rs < 2: threshold += 1; reasons.append(f"Fragile regime (+1)")
    elif rs > 5: threshold -= 1; reasons.append(f"Strong bull (-1)")
    vix = get_vix_level()
    if vix > 30: threshold += 2; reasons.append(f"VIX {vix:.1f} (+2)")
    elif vix > 20: threshold += 1; reasons.append(f"VIX {vix:.1f} (+1)")
    elif vix < 15: threshold -= 1; reasons.append(f"VIX {vix:.1f} (-1)")
    if datetime.now().month in [1,4,7,10]: threshold += 1; reasons.append("Earnings season (+1)")
    if num_positions >= 2: threshold += 1; reasons.append(f"Holding {num_positions} (+1)")
    now = datetime.now(timezone.utc)
    if now.weekday() == 0 and now.hour < 16: threshold += 1; reasons.append("Monday AM (+1)")
    return max(3.0, min(threshold, 15.0)), reasons

def calculate_position_multiplier(score, threshold):
    gap = score - threshold
    if gap <= 0: return 0.5
    elif gap <= 1: return 0.75
    elif gap <= 2: return 1.0
    elif gap <= 3: return 1.25
    else: return 1.5

# ============================================================
# VOLATILITY TARGETING
# ============================================================
def get_atr_multiplier(symbol, lookback=20):
    """Scale position size inversely to recent volatility.
    Higher ATR = smaller position; lower ATR = larger position.
    Capped [0.5, 1.5]."""
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=True)
        if len(df) < lookback + 5: return 1.0
        high, low, close = df['High'], df['Low'], df['Close']
        tr = pd.concat([high - low,
                        (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        atr_now = tr.iloc[-lookback:].mean()
        atr_median = tr.iloc[-60:].median()
        if atr_median == 0 or atr_now == 0: return 1.0
        ratio = atr_median / atr_now
        return max(0.5, min(ratio, 1.5))
    except Exception as e:
        log(f"⚠️ ATR error on {symbol}: {e}")
        return 1.0

# ============================================================
# BROKER
# ============================================================
client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

def place_bracket_order(symbol, side, qty, entry_price, score, threshold, signals, mult):
    try:
        stop_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)
        target_price = round(entry_price * 1.05, 2)
        order_data = MarketOrderRequest(
            symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=target_price),
            stop_loss=StopLossRequest(stop_price=stop_price)
        )
        order = client.submit_order(order_data)
        log(f"✅ {side} {qty} {symbol} @ ${entry_price:.2f} | SL ${stop_price} | TP ${target_price}")
        time.sleep(2)  # Allow fill
        try:
            filled = client.get_order_by_id(order.id)
            actual = float(filled.filled_avg_price or entry_price)
        except Exception:
            actual = entry_price
        log_fill(symbol, "Entry", entry_price, actual, order.id)
        alert = (f"🚨 *TRADE PLACED*\n\n*Symbol:* {symbol}\n*Qty:* {qty}\n"
                 f"*Entry:* ${entry_price:.2f}\n*SL:* ${stop_price}\n*TP:* ${target_price}\n"
                 f"*Score:* {score:.2f}/{threshold:.2f}\n*Vol Mult:* {mult:.2f}x\n"
                 f"*Cost:* ${qty*entry_price:.2f}\n\n"
                 f"Equity: ${float(client.get_account().equity):.2f}")
        send_telegram(alert)
        log_entry(symbol, str(side), qty, entry_price, stop_price, target_price, score, threshold, signals)
        return order
    except Exception as e:
        log(f"❌ Order failed: {e}")
        send_telegram(f"❌ Order failed {symbol}: {e}")
        return None

# ============================================================
# MAIN
# ============================================================
def run_bot():
    log("=" * 60)
    log(f"Bot v10 started at {datetime.now().isoformat()}")

    phase("1. Market Hours Check")
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5 or now.hour < 14 or now.hour >= 21:
        log("Market closed. Exiting.")
        return

    phase("2. Kill Switch Check")
    try:
        account = client.get_account()
        equity = float(account.equity)
        if check_kill_switch(equity):
            return
    except Exception as e:
        log(f"❌ Account fetch failed: {e}")
        return

    phase("3. Exit Logging")
    log_exits()

    phase("4. Position Analysis")
    try:
        open_positions = client.get_all_positions()
        position_symbols = [p.symbol for p in open_positions]
        orders_req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        open_orders = client.get_orders(filter=orders_req)
        order_symbols = [o.symbol for o in open_orders]
        already_held = set(position_symbols + order_symbols)
        total_value = sum(float(p.market_value) for p in open_positions)
        tactical_limit = equity * TACTICAL_LIMIT_PCT
        log(f"Equity: ${equity:.2f} | Exposure: ${total_value:.2f} | Limit: ${tactical_limit:.2f}")
        log(f"Holding: {already_held}")
    except Exception as e:
        log(f"❌ Position analysis failed: {e}")
        return

    phase("5. Threshold Calculation")
    threshold, reasons = calculate_dynamic_threshold(len(already_held))
    log(f"📊 Threshold: {threshold:.2f}")
    for r in reasons: log(f"   → {r}")

    phase("6. Pre-Flight Checks")
    if threshold > 15:
        log("🚫 Threshold too high, skipping."); return
    if total_value >= tactical_limit:
        log("⚠️ Tactical limit reached."); return
    if len(already_held) >= MAX_POSITIONS:
        log(f"⚠️ Max positions reached."); return

    phase("7. Signal Scoring")
    candidates = []
    for symbol in WATCHLIST:
        if symbol in already_held:
            log(f"⏸️ {symbol}: Already held")
            continue
        try:
            score, signals = calculate_score(symbol)
            if score >= threshold:
                candidates.append((symbol, score, signals))
            else:
                log(f"  ❌ {symbol}: {score:.2f} < {threshold:.2f}")
        except Exception as e:
            log(f"  ❌ {symbol} scoring failed: {e}")

    phase("8. Trade Execution")
    if not candidates:
        log("No candidates passed threshold."); return
    candidates.sort(key=lambda x: x[1], reverse=True)
    symbol, score, signals = candidates[0]
    score_mult = calculate_position_multiplier(score, threshold)
    vol_mult = get_atr_multiplier(symbol)
    mult = score_mult * vol_mult
    log(f"🎯 {symbol} | Score {score:.2f}/{threshold:.2f} | Score mult {score_mult}x | Vol mult {vol_mult:.2f}x | Total {mult:.2f}x")

    try:
        hist = yf.Ticker(symbol).history(period="1d", auto_adjust=True)
        price = float(hist['Close'].iloc[-1])
        remaining = tactical_limit - total_value
        risk_amount = equity * RISK_PER_TRADE * mult
        risk_per_share = price * STOP_LOSS_PCT
        qty = min(int(risk_amount / risk_per_share), int(remaining / price))
        if qty < 1:
            log(f"⚠️ Not enough room for 1 share."); return
        place_bracket_order(symbol, OrderSide.BUY, qty, price, score, threshold, signals, mult)
    except Exception as e:
        log(f"❌ Execution failed: {e}")
        log(traceback.format_exc())

    log("\nBot cycle complete.")
    log("=" * 60)

if __name__ == "__main__":
    try:
        run_bot()
    except Exception as e:
        log(f"❌ FATAL: {e}")
        log(traceback.format_exc())
        send_telegram(f"❌ *Bot FATAL:* {e}")
