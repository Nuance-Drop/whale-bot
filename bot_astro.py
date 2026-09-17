"""
Whale Bot Astro - Logs astrology signals to Airtable. Does NOT trade.
Uses OpenEphemeris (free tier) + Vedaksha for Vedic calculations.
"""

import os, json, time, logging, requests
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd
from pyairtable import Api

from common import (
    get_logger, safe_request, send_telegram, log_run,
    is_market_open, http_get, http_post, clean_for_json
)

# ============================================================
# CONFIG
# ============================================================
OPENEPHEMERIS_API_KEY = os.environ.get("OPENEPHEMERIS_API_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_ASTRO_TABLE_ID = os.environ.get("AIRTABLE_ASTRO_TABLE_ID")
AIRTABLE_RUNS_TABLE_ID = os.environ.get("AIRTABLE_RUNS_TABLE_ID")

# Reference locations
NYSE_LAT = 40.7069
NYSE_LON = -74.0113
LOCAL_LAT = float(os.environ.get("LOCAL_LAT", "0"))
LOCAL_LON = float(os.environ.get("LOCAL_LON", "0"))

OE_BASE = "https://api.openephemeris.com"

log = get_logger("astro", "astro_bot.log")
def L(m): print(m); log.info(m)

client = None  # Astro bot does not trade

# ============================================================
# HIERARCHY SCORING
# ============================================================
# Based on published research on planetary effects on markets.
# Tier 1 (3 points): Saturn, Jupiter, Moon
# Tier 2 (2 points): Mars, Venus, Mercury
# Tier 3 (1 point): Sun, outer planets
TIER_1 = ["saturn", "jupiter", "moon"]
TIER_2 = ["mars", "venus", "mercury"]
TIER_3 = ["sun", "uranus", "neptune", "pluto"]

def get_planet_weight(planet_name):
    p = planet_name.lower()
    if p in TIER_1: return 3.0
    if p in TIER_2: return 2.0
    if p in TIER_3: return 1.0
    return 0.5

def aspect_score(aspect_type):
    """Score aspects by type. Conjunctions and oppositions are strongest."""
    a = aspect_type.lower()
    if "conjunction" in a: return 1.0
    if "opposition" in a: return 0.9
    if "square" in a: return 0.7
    if "trine" in a: return 0.5
    if "sextile" in a: return 0.4
    return 0.2

# ============================================================
# OPENEPHEMERIS API CALLS
# ============================================================
def fetch_positions(dt_utc, lat, lon):
    """Fetch all planetary positions for a given datetime and location."""
    try:
        # Vedic chart includes Western positions too
        r = http_post(
            f"{OE_BASE}/vedic/chart",
            headers={"Authorization": f"Bearer {OPENEPHEMERIS_API_KEY}"},
            json={
                "datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%S"),
                "latitude": lat,
                "longitude": lon,
            }
        )
        if r is None or r.status_code != 200:
            L(f"⚠️ OpenEphemeris returned {r.status_code if r else 'None'}")
            return None
        return r.json()
    except Exception as e:
        L(f"⚠️ OE fetch error: {e}")
        return None

def fetch_aspects(dt_utc):
    """Fetch aspects between planets."""
    try:
        r = http_post(
            f"{OE_BASE}/ephemeris/aspects",
            headers={"Authorization": f"Bearer {OPENEPHEMERIS_API_KEY}"},
            json={"datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%S")}
        )
        if r is None or r.status_code != 200:
            return []
        return r.json().get("aspects", [])
    except Exception as e:
        L(f"⚠️ OE aspects error: {e}")
        return []

def fetch_moon_phase(dt_utc):
    try:
        r = http_get(
            f"{OE_BASE}/lunar/phase",
            headers={"Authorization": f"Bearer {OPENEPHEMERIS_API_KEY}"},
            params={"datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%S")}
        )
        if r is None or r.status_code != 200:
            return {}
        return r.json()
    except Exception as e:
        L(f"⚠️ OE moon error: {e}")
        return {}

# ============================================================
# VEDAKSHA (self-hosted, optional)
# ============================================================
def get_vedaksha_data(dt_utc, lat, lon):
    """Vedic calculations via Vedaksha. Returns {} if not installed."""
    try:
        import vedaksha
        # Vedaksha API: chart(datetime, lat, lon) returns kundali data
        chart = vedaksha.chart(
            dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            lat, lon
        )
        return {
            "nakshatra": chart.get("moon_nakshatra", ""),
            "dasha": chart.get("current_dasha", ""),
            "houses": chart.get("houses", {}),
        }
    except ImportError:
        L("ℹ️ Vedaksha not installed. Skipping Vedic calculations.")
        return {}
    except Exception as e:
        L(f"⚠️ Vedaksha error: {e}")
        return {}

# ============================================================
# SCORING
# ============================================================
def compute_astro_score(positions, aspects, moon_phase):
    """Compute composite astrology score using hierarchy."""
    score = 0.0
    breakdown = {}

    # Moon phase (Tier 1)
    illumination = moon_phase.get("illumination", 0)
    if illumination > 50:
        score += 1.5
        breakdown["moon_full"] = 1.5
    elif illumination < 10:
        score -= 1.0
        breakdown["moon_new"] = -1.0

    # Aspects (Tier 1-3)
    for asp in aspects:
        p1 = asp.get("planet1", "").lower()
        p2 = asp.get("planet2", "").lower()
        atype = asp.get("aspect", "")
        w1 = get_planet_weight(p1)
        w2 = get_planet_weight(p2)
        a_score = aspect_score(atype)
        contribution = (w1 + w2) * a_score * 0.5
        # Determine sign: trine/sextile positive, square/opposition negative
        if "trine" in atype.lower() or "sextile" in atype.lower():
            score += contribution
        elif "square" in atype.lower() or "opposition" in atype.lower():
            score -= contribution
        else:
            score += contribution * 0.3
        breakdown[f"{p1}_{p2}_{atype}"] = round(contribution, 2)

    # Retrograde flags
    for planet in ["mercury", "venus", "mars", "jupiter", "saturn"]:
        retro = False
        for pos in positions.get("planets", []):
            if pos.get("name", "").lower() == planet:
                retro = pos.get("is_retrograde", False)
                break
        if retro:
            # Research: Mercury retrograde = -3.22% annual market returns
            penalty = -1.5 if planet == "mercury" else -0.5
            score += penalty
            breakdown[f"{planet}_retrograde"] = penalty

    # Normalize to [-10, +10]
    score = max(-10, min(10, score))
    return round(score, 2), breakdown

# ============================================================
# AIRTABLE LOGGING
# ============================================================
def log_astro(reference, positions, aspects, moon_phase, vedic, score, breakdown):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_ASTRO_TABLE_ID]):
            return
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_ASTRO_TABLE_ID)

        # Extract key values from positions
        planets = {p.get("name", "").lower(): p for p in positions.get("planets", [])}
        sun = planets.get("sun", {})
        moon = planets.get("moon", {})
        jup = planets.get("jupiter", {})
        sat = planets.get("saturn", {})
        merc = planets.get("mercury", {})
        ven = planets.get("venus", {})
        mars = planets.get("mars", {})

        houses = vedic.get("houses", {})

        payload = {
            "Timestamp": datetime.now().isoformat(),
            "Reference": reference,
            "Sun_Sign": sun.get("sign_name", ""),
            "Sun_Degree": round(sun.get("sign_longitude", 0), 2),
            "Moon_Sign": moon.get("sign_name", ""),
            "Moon_Phase": moon_phase.get("phase", ""),
            "Moon_Illumination": round(moon_phase.get("illumination", 0), 2),
            "Mercury_Retrograde": merc.get("is_retrograde", False),
            "Venus_Retrograde": ven.get("is_retrograde", False),
            "Mars_Retrograde": mars.get("is_retrograde", False),
            "Jupiter_Sign": jup.get("sign_name", ""),
            "Jupiter_Degree": round(jup.get("sign_longitude", 0), 2),
            "Saturn_Sign": sat.get("sign_name", ""),
            "Saturn_Degree": round(sat.get("sign_longitude", 0), 2),
            "Nakshatra": vedic.get("nakshatra", ""),
            "Current_Dasha": vedic.get("dasha", ""),
            "Astro_Score": score,
            "Astro_Hierarchy": json.dumps(breakdown),
            "Vedic_House_2": str(houses.get("2", "")),
            "Vedic_House_5": str(houses.get("5", "")),
            "Vedic_House_8": str(houses.get("8", "")),
            "Vedic_House_11": str(houses.get("11", "")),
        }
        table.create(payload)
        L(f"✅ Astro logged [{reference}]: score={score}")
    except Exception as e:
        L(f"⚠️ Astro log failed: {e}")

# ============================================================
# MAIN
# ============================================================
def run():
    L("=" * 60)
    L(f"astro start {datetime.now().isoformat()}")

    if not is_market_open():
        L("market closed")
        log_run("astro", "market_closed")
        return

    dt = datetime.now(timezone.utc)

    # Fetch data for both reference points
    for ref, lat, lon in [("NYSE", NYSE_LAT, NYSE_LON), ("Local", LOCAL_LAT, LOCAL_LON)]:
        L(f"--- {ref} ---")
        positions = fetch_positions(dt, lat, lon)
        if not positions:
            continue
        aspects = fetch_aspects(dt)
        moon_phase = fetch_moon_phase(dt)
        vedic = get_vedaksha_data(dt, lat, lon) if ref == "NYSE" else {}

        score, breakdown = compute_astro_score(positions, aspects, moon_phase)
        log_astro(ref, positions, aspects, moon_phase, vedic, score, breakdown)

    log_run("astro", "ok", action="astro signals logged")
    L("=" * 60)

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        L(f"❌ FATAL: {e}")
        send_telegram(f"❌ astro fatal: {e}")
