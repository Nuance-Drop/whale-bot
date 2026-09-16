"""
Shared utilities for all Whale Bots.
Centralized API calls, Airtable-backed drawdown, failure tracking.
"""

import os, time, json, random, logging, requests
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_RUNS_TABLE_ID = os.environ.get("AIRTABLE_RUNS_TABLE_ID")
AIRTABLE_PEAK_TABLE_ID = os.environ.get("AIRTABLE_PEAK_TABLE_ID")

# ============================================================
# LOGGER
# ============================================================
def get_logger(name, logfile):
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    if not log.handlers:
        fh = logging.FileHandler(logfile)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log.addHandler(fh)
    return log

# ============================================================
# SAFE REQUEST — every external call goes through here
# ============================================================
def safe_request(fn, *args, max_retries=3, **kwargs):
    """Exponential backoff wrapper. Retries on 429/5xx and network errors."""
    for i in range(max_retries):
        try:
            r = fn(*args, **kwargs)
            if hasattr(r, 'status_code') and r.status_code in [429, 500, 502, 503, 504]:
                time.sleep((2**i) + random.uniform(0, 1))
                continue
            return r
        except (requests.exceptions.RequestException, ConnectionError, TimeoutError):
            if i == max_retries - 1:
                raise
            time.sleep((2**i) + random.uniform(0, 1))
    return None

def http_get(url, **kwargs):
    return safe_request(requests.get, url, timeout=15, **kwargs)

def http_post(url, **kwargs):
    return safe_request(requests.post, url, timeout=15, **kwargs)

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        safe_request(requests.post,
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10)
    except Exception:
        pass

# ============================================================
# AIRTABLE — Runs table logging
# ============================================================
def log_run(bot_name, status, equity=None, positions=0, threshold=None,
            top_candidate=None, top_score=None, action="", error=""):
    """Write one row to the Runs table. Never raises."""
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_RUNS_TABLE_ID]):
            return
        from pyairtable import Api
        payload = {
            "Timestamp": datetime.now().isoformat(),
            "Bot": bot_name,
            "Status": status,
        }
        if equity is not None: payload["Equity"] = round(float(equity), 2)
        payload["Positions Held"] = int(positions)
        if threshold is not None: payload["Threshold"] = round(float(threshold), 2)
        if top_candidate: payload["Top Candidate"] = top_candidate
        if top_score is not None: payload["Top Score"] = round(float(top_score), 2)
        if action: payload["Action Taken"] = action[:500]
        if error: payload["Error"] = str(error)[:500]
        Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_RUNS_TABLE_ID).create(payload)
    except Exception:
        pass

# ============================================================
# AIRTABLE — Peak equity (persistent across runs)
# ============================================================
def get_peak_equity():
    """Read peak equity from Airtable. Returns None if not set."""
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID]):
            return None
        from pyairtable import Api
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID)
        rows = table.all(formula="{Key}='peak_equity'")
        if not rows:
            return None
        return float(rows[0]['fields'].get('Value', 0))
    except Exception:
        return None

def set_peak_equity(value):
    """Update peak equity in Airtable."""
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID]):
            return
        from pyairtable import Api
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID)
        rows = table.all(formula="{Key}='peak_equity'")
        if rows:
            table.update(rows[0]['id'], {"Value": round(float(value), 4)})
        else:
            table.create({"Key": "peak_equity", "Value": round(float(value), 4)})
    except Exception:
        pass

# ============================================================
# AIRTABLE — Failure check (auto-halt after N consecutive errors)
# ============================================================
def consecutive_failures(bot_name, lookback=3):
    """Return number of consecutive 'error' statuses for this bot, most recent first."""
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_RUNS_TABLE_ID]):
            return 0
        from pyairtable import Api
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_RUNS_TABLE_ID)
        rows = table.all(
            formula=f"{{Bot}}='{bot_name}'",
            sort=["-Timestamp"]
        )[:lookback]
        count = 0
        for r in rows:
            if r['fields'].get('Status') == 'error':
                count += 1
            else:
                break
        return count
    except Exception:
        return 0

def should_halt(bot_name):
    """If last N runs all errored, halt this bot."""
    n = consecutive_failures(bot_name, lookback=3)
    if n >= 3:
        send_telegram(f"🛑 *{bot_name} HALTED* — {n} consecutive errors. Check Airtable Runs.")
        return True
    return False

# ============================================================
# MARKET UTILITIES
# ============================================================
def is_market_open():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    return 14 <= now.hour < 21

def is_market_bullish():
    spy = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy['SMA200'] = spy['Close'].rolling(200).mean()
    return bool(spy['Close'].iloc[-1] > spy['SMA200'].iloc[-1])

def drawdown_check(client, threshold=0.05, log_fn=None):
    """Return True if we should halt (drawdown too big). Uses Airtable peak."""
    try:
        a = client.get_account()
        equity = float(a.equity)
        peak = get_peak_equity()
        if peak is None or equity > peak:
            peak = equity
            set_peak_equity(peak)
        dd = (peak - equity) / peak if peak else 0
        if log_fn:
            log_fn(f"drawdown {dd:.2%} (peak ${peak:.2f}, equity ${equity:.2f})")
        if dd >= threshold:
            if log_fn:
                log_fn(f"🛑 DRAWDOWN LIMIT ({dd:.2%})")
            send_telegram(f"🛑 *DRAWDOWN HALT*: {dd:.2%}")
            client.close_all_positions(cancel_orders=True)
            return True
        return False
    except Exception as e:
        if log_fn:
            log_fn(f"⚠️ drawdown check failed: {e}")
        return False

def get_vix():
    try:
        v = yf.download("^VIX", period="5d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(v.columns, pd.MultiIndex):
            v.columns = v.columns.get_level_values(0)
        return float(v['Close'].iloc[-1])
    except Exception:
        return 20.0

def spy_strength_pct():
    try:
        s = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(s.columns, pd.MultiIndex):
            s.columns = s.columns.get_level_values(0)
        s['SMA200'] = s['Close'].rolling(200).mean()
        return (s['Close'].iloc[-1] - s['SMA200'].iloc[-1]) / s['SMA200'].iloc[-1] * 100
    except Exception:
        return 0.0

def get_rsi_sma(symbol):
    """Returns (rsi, close, sma50) or (None, None, None)."""
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50:
            return None, None, None
        df['SMA50'] = df['Close'].rolling(50).mean()
        d = df['Close'].diff()
        g = (d.where(d > 0, 0)).rolling(14).mean()
        l = (-d.where(d < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + g/l))
        last = df.iloc[-1]
        return float(last['RSI']), float(last['Close']), float(last['SMA50'])
    except Exception:
        return None, None, None

def get_peak_since(symbol, since_time):
    """Highest intraday high since since_time (uses 5m bars, last 5 days)."""
    try:
        df = yf.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=True)
        if df.empty:
            return None
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        et = since_time
        if et.tzinfo is None:
            et = et.replace(tzinfo=timezone.utc)
        df = df[df.index >= et]
        return float(df['High'].max()) if not df.empty else None
    except Exception:
        return None

def run_is_dry():
    return os.environ.get("DRY_RUN", "0") == "1"

def clean_for_json(obj):
    """Recursively replace NaN/Inf with 0. Used by dashboard."""
    import math
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0
        return obj
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_for_json(x) for x in obj]
    return obj

# ============================================================
# PURE FUNCTIONS (unit-testable)
# ============================================================
def score_mult(score, threshold):
    """Position size multiplier based on gap over threshold."""
    gap = score - threshold
    if gap <= 0:
        return 0.5
    if gap <= 1:
        return 0.75
    if gap <= 2:
        return 1.0
    if gap <= 3:
        return 1.25
    return 1.5

def calc_dynamic_threshold_base(regime_strength, vix, num_positions):
    """
    Pure version of the dynamic threshold logic.
    Returns (threshold, reason_list).
    regime_strength: percent above/below 200MA
    vix: current VIX level
    num_positions: currently held
    """
    t = 4.0
    reasons = []
    if regime_strength < 0:
        return 999, ["regime_block"]
    elif regime_strength < 2:
        t += 1; reasons.append("fragile")
    elif regime_strength > 5:
        t -= 1; reasons.append("strong bull")
    if vix > 30:
        t += 2; reasons.append("vix>30")
    elif vix > 20:
        t += 1; reasons.append("vix>20")
    elif vix < 15:
        t -= 1; reasons.append("vix<15")
    if num_positions >= 2:
        t += 1; reasons.append("holding 2+")
    return max(3.0, min(t, 15.0)), reasons

def atr_multiplier_from_series(high, low, close, lookback=20):
    """
    Pure ATR multiplier. Inputs are pandas Series.
    Returns multiplier in [0.5, 1.5].
    """
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    a = tr.iloc[-lookback:].mean()
    m = tr.iloc[-60:].median()
    if m == 0 or a == 0:
        return 1.0
    return max(0.5, min(m/a, 1.5))
