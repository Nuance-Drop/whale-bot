"""
Shared utilities for all Whale Bots.
Centralized API calls, Airtable-backed drawdown, failure tracking,
GLOBAL exposure cap, regulatory fees, correlation checks.
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

GLOBAL_EXPOSURE_CAP_PCT = float(os.environ.get("GLOBAL_EXPOSURE_CAP_PCT", "0.30"))

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
# SAFE REQUEST
# ============================================================
def safe_request(fn, *args, max_retries=3, **kwargs):
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
# AIRTABLE — Runs
# ============================================================
def log_run(bot_name, status, equity=None, positions=0, threshold=None,
            top_candidate=None, top_score=None, action="", error=""):
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
# AIRTABLE — Peak
# ============================================================
def _find_numeric_field(fields, preferred=("Value", "value", "Peak", "peak", "Equity", "equity")):
    for k in preferred:
        if k in fields:
            try:
                return k, float(fields[k])
            except (ValueError, TypeError):
                continue
    for k, v in fields.items():
        if isinstance(v, (int, float)):
            return k, float(v)
    return None, None

def get_peak_equity():
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID]):
            return None
        from pyairtable import Api
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID)
        rows = table.all()
        if not rows: return None
        _, val = _find_numeric_field(rows[0]['fields'])
        return val
    except Exception:
        return None

def set_peak_equity(value):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID]):
            return
        from pyairtable import Api
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_PEAK_TABLE_ID)
        rows = table.all()
        if rows:
            field_name, _ = _find_numeric_field(rows[0]['fields'])
            if not field_name:
                field_name = "Value"
            table.update(rows[0]['id'], {field_name: round(float(value), 4)})
        else:
            table.create({"Value": round(float(value), 4)})
    except Exception:
        pass

# ============================================================
# FAILURE CHECK
# ============================================================
def consecutive_failures(bot_name, lookback=3):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_RUNS_TABLE_ID]):
            return 0
        from pyairtable import Api
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_RUNS_TABLE_ID)
        rows = table.all(formula=f"{{Bot}}='{bot_name}'", sort=["-Timestamp"])[:lookback]
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
    n = consecutive_failures(bot_name, lookback=3)
    if n >= 3:
        send_telegram(f"🛑 *{bot_name} HALTED* — {n} consecutive errors.")
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
# GLOBAL EXPOSURE CAP
# ============================================================
def total_exposure(client):
    try:
        positions = client.get_all_positions()
        return sum(float(p.market_value) for p in positions)
    except Exception:
        return 0.0

def would_exceed_global_cap(client, new_position_value, log_fn=None):
    try:
        a = client.get_account()
        equity = float(a.equity)
        exposure = total_exposure(client)
        cap = equity * GLOBAL_EXPOSURE_CAP_PCT
        new_total = exposure + float(new_position_value)
        ok = new_total <= cap
        if log_fn:
            log_fn(f"  🌐 global cap: ${exposure:.2f} + ${new_position_value:.2f} = "
                   f"${new_total:.2f} / ${cap:.2f} ({GLOBAL_EXPOSURE_CAP_PCT:.0%}) "
                   f"→ {'OK' if ok else 'BLOCKED'}")
        return ok, exposure, cap, equity
    except Exception as e:
        if log_fn:
            log_fn(f"  ⚠️ global cap check failed: {e}")
        return True, 0.0, 0.0, 0.0

# ============================================================
# CORRELATION CHECK
# ============================================================
def positions_correlation_risk(candidate_symbol, existing_symbols, threshold=0.7, log_fn=None):
    """
    Check if candidate_symbol is highly correlated with any existing position.
    Returns (ok_to_trade, highest_corr, correlated_with).
    """
    if not existing_symbols:
        return True, 0.0, None
    try:
        all_syms = [candidate_symbol] + list(existing_symbols)
        data = yf.download(all_syms, period="2mo", interval="1d",
                           auto_adjust=True, progress=False)['Close']
        if data.empty or candidate_symbol not in data.columns:
            return True, 0.0, None
        returns = data.pct_change().dropna()
        if len(returns) < 10:
            return True, 0.0, None

        candidate_ret = returns[candidate_symbol]
        worst = 0.0
        worst_sym = None
        for s in existing_symbols:
            if s not in returns.columns:
                continue
            corr = candidate_ret.corr(returns[s])
            if corr is None:
                continue
            corr = float(corr)
            if abs(corr) > abs(worst):
                worst = corr
                worst_sym = s

        ok = abs(worst) <= threshold
        if log_fn:
            log_fn(f"  🔗 correlation: {candidate_symbol} vs existing = {worst:+.2f} "
                   f"(worst: {worst_sym}) → {'OK' if ok else 'BLOCKED'}")
        return ok, worst, worst_sym
    except Exception as e:
        if log_fn:
            log_fn(f"  ⚠️ correlation check failed: {e}")
        return True, 0.0, None

# ============================================================
# REGULATORY FEES
# ============================================================
def estimate_regulatory_fees(exit_price, qty):
    """
    Estimate US equity regulatory fees on a SELL order.
    - SEC fee: $27.80 per $1,000,000 of proceeds
    - FINRA TAF: $0.000166 per share
    - CAT fee: $0.000114 per trade
    Returns total fees in dollars.
    """
    proceeds = exit_price * qty
    sec_fee = proceeds * 0.0000278
    finra_fee = max(qty * 0.000166, 0.01)
    cat_fee = max(0.000114, 0.01)
    return round(sec_fee + finra_fee + cat_fee, 4)

# ============================================================
# PURE FUNCTIONS (unit-testable)
# ============================================================
def score_mult(score, threshold):
    gap = score - threshold
    if gap <= 0: return 0.5
    if gap <= 1: return 0.75
    if gap <= 2: return 1.0
    if gap <= 3: return 1.25
    return 1.5

def calc_dynamic_threshold_base(regime_strength, vix, num_positions):
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
