"""
Shared utilities for all Whale Bots. Imported, not run directly.
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

def get_logger(name, logfile):
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    if not log.handlers:
        fh = logging.FileHandler(logfile)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        log.addHandler(fh)
    return log

def safe_request(fn, *args, max_retries=3, **kwargs):
    for i in range(max_retries):
        try:
            r = fn(*args, **kwargs)
            if hasattr(r, 'status_code') and r.status_code in [429,500,502,503,504]:
                time.sleep((2**i) + random.uniform(0, 1)); continue
            return r
        except (requests.exceptions.RequestException, ConnectionError):
            if i == max_retries-1: raise
            time.sleep((2**i) + random.uniform(0, 1))
    return None

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        safe_request(requests.post,
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10)
    except Exception: pass

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

def is_market_open():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5: return False
    return 14 <= now.hour < 21

def is_market_bullish():
    spy = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy['SMA200'] = spy['Close'].rolling(200).mean()
    return bool(spy['Close'].iloc[-1] > spy['SMA200'].iloc[-1])

def drawdown_check(client, threshold=0.05, log_fn=None):
    """Return True if we should halt (drawdown too big). Never raises."""
    try:
        a = client.get_account()
        equity = float(a.equity)
        peak_file = "peak_equity.txt"
        peak = float(open(peak_file).read().strip()) if os.path.isfile(peak_file) else equity
        if equity > peak:
            peak = equity
            with open(peak_file, "w") as f: f.write(str(peak))
        dd = (peak - equity) / peak
        if log_fn: log_fn(f"drawdown {dd:.2%} (peak ${peak:.2f}, equity ${equity:.2f})")
        if dd >= threshold:
            if log_fn: log_fn(f"🛑 DRAWDOWN LIMIT ({dd:.2%})")
            send_telegram(f"🛑 *DRAWDOWN HALT*: {dd:.2%}")
            client.close_all_positions(cancel_orders=True)
            return True
        return False
    except Exception as e:
        if log_fn: log_fn(f"⚠️ drawdown check failed: {e}")
        return False

def get_vix():
    try:
        v = yf.download("^VIX", period="5d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(v.columns, pd.MultiIndex):
            v.columns = v.columns.get_level_values(0)
        return float(v['Close'].iloc[-1])
    except Exception: return 20.0

def spy_strength_pct():
    try:
        s = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(s.columns, pd.MultiIndex):
            s.columns = s.columns.get_level_values(0)
        s['SMA200'] = s['Close'].rolling(200).mean()
        return (s['Close'].iloc[-1] - s['SMA200'].iloc[-1]) / s['SMA200'].iloc[-1] * 100
    except Exception: return 0.0

def get_rsi_sma(symbol):
    """Returns (rsi, close, sma50) or (None, None, None)."""
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50: return None, None, None
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
        if df.empty: return None
        if df.index.tz is None: df.index = df.index.tz_localize("UTC")
        et = since_time
        if et.tzinfo is None: et = et.replace(tzinfo=timezone.utc)
        df = df[df.index >= et]
        return float(df['High'].max()) if not df.empty else None
    except Exception:
        return None

def run_is_dry():
    return os.environ.get("DRY_RUN", "0") == "1"
