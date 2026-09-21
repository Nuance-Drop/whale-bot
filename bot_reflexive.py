"""
Reflexive Loop Detector. Supabase storage backend.
"""

import os, json, logging
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd

from common import (
    get_logger, send_telegram, log_run,
    _sb, SUPABASE_URL, SUPABASE_KEY
)

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN"]

log = get_logger("reflexive", "reflexive_bot.log")
def L(m): print(m); log.info(m)

def _safe_float(v, default=0.0):
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except (ValueError, TypeError):
        return default

def get_vix_term_structure():
    try:
        vix = yf.Ticker("^VIX").history(period="5d")
        vix9d = yf.Ticker("^VIX9D").history(period="5d")
        vix3m = yf.Ticker("^VIX3M").history(period="5d")
        if vix.empty or vix9d.empty or vix3m.empty:
            L("⚠️ VIX data missing — skipping term structure")
            return {}
        vix_val = _safe_float(vix['Close'].iloc[-1], 0)
        vix9d_val = _safe_float(vix9d['Close'].iloc[-1], vix_val)
        vix3m_val = _safe_float(vix3m['Close'].iloc[-1], vix_val)
        structure = "Backwardation" if vix9d_val > vix_val > vix3m_val else "Contango"
        return {"vix": vix_val, "vix9d": vix9d_val, "vix3m": vix3m_val, "structure": structure}
    except Exception as e:
        L(f"⚠️ VIX term error: {e}")
        return {}

def get_cross_correlation():
    try:
        data = yf.download(WATCHLIST, period="1mo", interval="1d",
                           auto_adjust=True, progress=False)['Close']
        if data.empty or len(data) < 5: return 0.0
        returns = data.pct_change().dropna()
        if returns.empty: return 0.0
        corr = returns.corr()
        n = len(corr)
        if n < 2: return 0.0
        total = corr.values.sum() - n
        return _safe_float(total / (n * (n - 1)), 0.0)
    except Exception as e:
        L(f"⚠️ correlation error: {e}")
        return 0.0

def get_spy_vix_correlation():
    try:
        spy = yf.Ticker("SPY").history(period="3mo")['Close'].pct_change().dropna()
        vix = yf.Ticker("^VIX").history(period="3mo")['Close'].pct_change().dropna()
        if spy.empty or vix.empty: return 0.0
        df = pd.concat([spy, vix], axis=1, join="inner")
        if len(df) < 5: return 0.0
        df.columns = ["spy", "vix"]
        return _safe_float(df.tail(20).corr().iloc[0, 1], 0.0)
    except Exception as e:
        L(f"⚠️ SPY/VIX corr error: {e}")
        return 0.0

def get_volume_z_score():
    try:
        spy = yf.Ticker("SPY").history(period="2mo")
        vol = spy['Volume']
        if len(vol) < 21: return 0.0
        mean = vol.iloc[-20:].mean(); std = vol.iloc[-20:].std()
        if std == 0 or std != std: return 0.0
        return _safe_float((vol.iloc[-1] - mean) / std, 0.0)
    except Exception as e:
        L(f"⚠️ volume Z error: {e}")
        return 0.0

def compute_reflexive_intensity(vix_struct, cross_corr, spy_vix_corr, vol_z):
    intensity = 0.0; notes = []
    if vix_struct.get("structure") == "Backwardation":
        intensity += 2.5; notes.append("VIX backwardation (stress)")
    if cross_corr > 0.7: intensity += 2.5; notes.append(f"cross-corr {cross_corr:.2f}")
    elif cross_corr > 0.5: intensity += 1.5; notes.append(f"cross-corr {cross_corr:.2f}")
    elif cross_corr < 0.2: notes.append("cross-corr low (diversified)")
    if spy_vix_corr > 0: intensity += 1.5; notes.append("SPY/VIX positive (unusual)")
    elif spy_vix_corr < -0.8: intensity += 1.0; notes.append("SPY/VIX strongly coupled")
    if abs(vol_z) > 2.0: intensity += 2.0; notes.append(f"volume Z={vol_z:.1f}")
    elif abs(vol_z) > 1.5: intensity += 1.0; notes.append(f"volume Z={vol_z:.1f}")
    return round(min(10.0, intensity), 2), notes

def log_reflexive(vix_struct, cross_corr, spy_vix_corr, vol_z, intensity, notes):
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            L("⚠️ Supabase credentials missing")
            return
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vix_spot": round(_safe_float(vix_struct.get("vix", 0)), 2),
            "vix_9d": round(_safe_float(vix_struct.get("vix9d", 0)), 2),
            "vix_1m": round(_safe_float(vix_struct.get("vix3m", 0)), 2),
            "vix_term_structure": vix_struct.get("structure", "") or "",
            "spy_vix_correlation": round(_safe_float(spy_vix_corr), 4),
            "cross_ticker_correlation": round(_safe_float(cross_corr), 4),
            "volume_z_score": round(_safe_float(vol_z), 2),
            "reflexive_intensity": _safe_float(intensity),
            "herding_flag": bool(intensity >= 7.0),
            "notes": " | ".join(notes) if notes else "",
        }
        _sb().table("reflexive").insert(payload).execute()
        L(f"✅ Reflexive logged: intensity={intensity}")
        if intensity >= 7.0:
            send_telegram(f"⚠️ *Reflexive intensity {intensity}/10*\n" + "\n".join(notes))
    except Exception as e:
        L(f"⚠️ Reflexive log failed: {e}")

def run():
    L("=" * 60); L(f"reflexive start {datetime.now().isoformat()}")
    vix_struct = get_vix_term_structure()
    cross_corr = get_cross_correlation()
    spy_vix_corr = get_spy_vix_correlation()
    vol_z = get_volume_z_score()
    L(f"  VIX: {vix_struct.get('vix', 0)} ({vix_struct.get('structure', 'unknown')})")
    L(f"  Cross-corr: {cross_corr:.4f}")
    L(f"  SPY/VIX corr: {spy_vix_corr:.4f}")
    L(f"  Volume Z: {vol_z:+.2f}")
    intensity, notes = compute_reflexive_intensity(vix_struct, cross_corr, spy_vix_corr, vol_z)
    L(f"Intensity: {intensity}/10")
    for n in notes: L(f"  → {n}")
    log_reflexive(vix_struct, cross_corr, spy_vix_corr, vol_z, intensity, notes)
    log_run("reflexive", "ok", action=f"intensity={intensity}")
    L("=" * 60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}"); send_telegram(f"❌ reflexive fatal: {e}")
