"""
Reflexive Loop Detector - Measures algorithmic herding and feedback loops.
Logs to Airtable. Does NOT trade.
"""

import os, json, logging
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd
from pyairtable import Api

from common import (
    get_logger, send_telegram, log_run, is_market_open,
    http_get, http_post
)

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_REFLEXIVE_TABLE_ID = os.environ.get("AIRTABLE_REFLEXIVE_TABLE_ID")

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN"]

log = get_logger("reflexive", "reflexive_bot.log")
def L(m): print(m); log.info(m)

def get_vix_term_structure():
    """Fetch VIX, VIX9D, VIX3M and determine contango/backwardation."""
    try:
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        vix9d = yf.Ticker("^VIX9D").history(period="5d")['Close'].iloc[-1]
        vix3m = yf.Ticker("^VIX3M").history(period="5d")['Close'].iloc[-1]
        if vix9d > vix > vix3m:
            structure = "Backwardation"
        else:
            structure = "Contango"
        return {
            "vix": float(vix),
            "vix9d": float(vix9d),
            "vix3m": float(vix3m),
            "structure": structure,
        }
    except Exception as e:
        L(f"⚠️ VIX term error: {e}")
        return {}

def get_cross_correlation():
    """Average pairwise correlation of watchlist over last 20 days."""
    try:
        data = yf.download(WATCHLIST, period="1mo", interval="1d",
                           auto_adjust=True, progress=False)['Close']
        returns = data.pct_change().dropna()
        corr = returns.corr()
        # Average off-diagonal
        n = len(corr)
        total = corr.values.sum() - n  # subtract diagonal
        avg = total / (n * (n - 1))
        return float(avg)
    except Exception as e:
        L(f"⚠️ correlation error: {e}")
        return 0.0

def get_spy_vix_correlation():
    """Rolling 20-day correlation between SPY returns and VIX changes."""
    try:
        spy = yf.Ticker("SPY").history(period="3mo")['Close'].pct_change().dropna()
        vix = yf.Ticker("^VIX").history(period="3mo")['Close'].pct_change().dropna()
        df = pd.concat([spy, vix], axis=1, join="inner")
        df.columns = ["spy", "vix"]
        corr = df.tail(20).corr().iloc[0, 1]
        return float(corr)
    except Exception as e:
        L(f"⚠️ SPY/VIX corr error: {e}")
        return 0.0

def get_volume_z_score():
    """Z-score of today's SPY volume vs 20-day average."""
    try:
        spy = yf.Ticker("SPY").history(period="2mo")
        vol = spy['Volume']
        z = (vol.iloc[-1] - vol.iloc[-20:].mean()) / vol.iloc[-20:].std()
        return float(z)
    except Exception as e:
        L(f"⚠️ volume Z error: {e}")
        return 0.0

def compute_reflexive_intensity(vix_struct, cross_corr, spy_vix_corr, vol_z):
    """
    Score 0-10 for how reflexive the market is right now.
    High scores = algorithmic herding likely.
    """
    intensity = 0.0
    notes = []

    # VIX backwardation → stress → herding
    if vix_struct.get("structure") == "Backwardation":
        intensity += 2.5
        notes.append("VIX backwardation (stress)")

    # High cross-ticker correlation → everyone trading the same
    if cross_corr > 0.7:
        intensity += 2.5
        notes.append(f"cross-corr {cross_corr:.2f}")
    elif cross_corr > 0.5:
        intensity += 1.5
        notes.append(f"cross-corr {cross_corr:.2f}")
    elif cross_corr < 0.2:
        notes.append("cross-corr low (diversified)")

    # Strong negative SPY/VIX correlation → normal. Positive = unusual
    if spy_vix_corr > 0:
        intensity += 1.5
        notes.append("SPY/VIX positive (unusual)")
    elif spy_vix_corr < -0.8:
        intensity += 1.0
        notes.append("SPY/VIX strongly coupled")

    # Volume spike → algorithmic activity
    if abs(vol_z) > 2.0:
        intensity += 2.0
        notes.append(f"volume Z={vol_z:.1f}")
    elif abs(vol_z) > 1.5:
        intensity += 1.0
        notes.append(f"volume Z={vol_z:.1f}")

    intensity = min(10.0, intensity)
    return round(intensity, 2), notes

def log_reflexive(vix_struct, cross_corr, spy_vix_corr, vol_z, intensity, notes):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_REFLEXIVE_TABLE_ID]):
            return
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_REFLEXIVE_TABLE_ID)
        table.create({
            "Timestamp": datetime.now().isoformat(),
            "VIX_Spot": round(vix_struct.get("vix", 0), 2),
            "VIX_9D": round(vix_struct.get("vix9d", 0), 2),
            "VIX_1M": round(vix_struct.get("vix3m", 0), 2),
            "VIX_Term_Structure": vix_struct.get("structure", ""),
            "SPY_VIX_Correlation": round(spy_vix_corr, 4),
            "Cross_Ticker_Correlation": round(cross_corr, 4),
            "Volume_Z_Score": round(vol_z, 2),
            "Reflexive_Intensity": intensity,
            "Herding_Flag": intensity >= 7.0,
            "Notes": " | ".join(notes),
        })
        L(f"✅ Reflexive logged: intensity={intensity}")
        if intensity >= 7.0:
            send_telegram(f"⚠️ *Reflexive intensity {intensity}/10*\n" + "\n".join(notes))
    except Exception as e:
        L(f"⚠️ Reflexive log failed: {e}")

def run():
    L("="*60)
    L(f"reflexive start {datetime.now().isoformat()}")
    # Reflexive data is valid 24/7 — no market hours gate
pass

    vix_struct = get_vix_term_structure()
    cross_corr = get_cross_correlation()
    spy_vix_corr = get_spy_vix_correlation()
    vol_z = get_volume_z_score()

    intensity, notes = compute_reflexive_intensity(vix_struct, cross_corr, spy_vix_corr, vol_z)
    L(f"Intensity: {intensity}/10")
    for n in notes: L(f"  → {n}")

    log_reflexive(vix_struct, cross_corr, spy_vix_corr, vol_z, intensity, notes)
    log_run("reflexive", "ok", action=f"intensity={intensity}")
    L("="*60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}")
        send_telegram(f"❌ reflexive fatal: {e}")
