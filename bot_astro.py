"""
Whale Bot Astro - Self-hosted Swiss Ephemeris calculations.
No API key. No 404s. Runs offline.
"""

import os, json, math, logging
from datetime import datetime, timezone, timedelta

import swisseph as swe
from pyairtable import Api

from common import (
    get_logger, send_telegram, log_run, clean_for_json
)

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_ASTRO_TABLE_ID = os.environ.get("AIRTABLE_ASTRO_TABLE_ID")
AIRTABLE_RUNS_TABLE_ID = os.environ.get("AIRTABLE_RUNS_TABLE_ID")

NYSE_LAT = 40.7069
NYSE_LON = -74.0113
LOCAL_LAT = float(os.environ.get("LOCAL_LAT", "0"))
LOCAL_LON = float(os.environ.get("LOCAL_LON", "0"))

log = get_logger("astro", "astro_bot.log")
def L(m): print(m); log.info(m)

# ============================================================
# PLANET IDS (Swiss Ephemeris)
# ============================================================
PLANETS = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
    "rahu": swe.MEAN_NODE,  # North Node = Rahu in Vedic
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

def sign_of(lon):
    return SIGNS[int(lon // 30) % 12]

def degree_in_sign(lon):
    return round(lon % 30, 2)

def nakshatra_of(lon):
    # 27 nakshatras, each 13°20'
    idx = int(lon // (360 / 27)) % 27
    return NAKSHATRAS[idx]

# ============================================================
# JULIAN DAY
# ============================================================
def to_julian(dt):
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0)

# ============================================================
# FETCH PLANET POSITIONS
# ============================================================
def get_positions(jd, sidereal=False):
    """Return dict of planet -> {lon, sign, degree, retrograde}."""
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    if sidereal:
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        flags |= swe.FLG_SIDEREAL

    out = {}
    for name, pid in PLANETS.items():
        try:
            pos, _ = swe.calc_ut(jd, pid, flags)
            lon = pos[0]
            speed = pos[3]  # degrees/day; negative = retrograde
            out[name] = {
                "lon": round(lon, 4),
                "sign": sign_of(lon),
                "degree": degree_in_sign(lon),
                "retrograde": speed < 0,
            }
        except Exception as e:
            L(f"⚠️ {name} calc failed: {e}")
    return out

# ============================================================
# MOON PHASE
# ============================================================
def get_moon_phase(jd):
    try:
        sun_pos, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
        moon_pos, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        elongation = (moon_pos[0] - sun_pos[0]) % 360

        if elongation < 45: phase = "New"
        elif elongation < 90: phase = "Waxing Crescent"
        elif elongation < 135: phase = "First Quarter"
        elif elongation < 180: phase = "Waxing Gibbous"
        elif elongation < 225: phase = "Full"
        elif elongation < 270: phase = "Waning Gibbous"
        elif elongation < 315: phase = "Last Quarter"
        else: phase = "Waning Crescent"

        # Illumination: 0.5 * (1 - cos(elongation))
        illum = round(50 * (1 - math.cos(math.radians(elongation))), 2)
        return {"phase": phase, "illumination": illum, "elongation": round(elongation, 2)}
    except Exception as e:
        L(f"⚠️ Moon phase error: {e}")
        return {"phase": "Unknown", "illumination": 0, "elongation": 0}

# ============================================================
# ASPECTS (between planets)
# ============================================================
ASPECT_ANGLES = {
    "Conjunction": 0,
    "Sextile": 60,
    "Square": 90,
    "Trine": 120,
    "Opposition": 180,
}
ORB = 6.0  # degrees of tolerance

def compute_aspects(positions):
    out = []
    keys = list(positions.keys())
    for i in range(len(keys)):
        for j in range(i+1, len(keys)):
            p1, p2 = keys[i], keys[j]
            d = abs((positions[p1]["lon"] - positions[p2]["lon"]) % 360)
            if d > 180:
                d = 360 - d
            for asp_name, asp_angle in ASPECT_ANGLES.items():
                if abs(d - asp_angle) <= ORB:
                    out.append({
                        "planet1": p1,
                        "planet2": p2,
                        "aspect": asp_name,
                        "exact_angle": round(d, 2),
                    })
                    break
    return out

# ============================================================
# SCORING
# ============================================================
TIER_1 = ["saturn", "jupiter", "moon"]
TIER_2 = ["mars", "venus", "mercury"]
TIER_3 = ["sun", "uranus", "neptune", "pluto"]

def planet_weight(name):
    p = name.lower()
    if p in TIER_1: return 3.0
    if p in TIER_2: return 2.0
    if p in TIER_3: return 1.0
    return 0.5

def aspect_score(atype):
    a = atype.lower()
    if "conjunction" in a: return 1.0
    if "opposition" in a: return 0.9
    if "square" in a: return 0.7
    if "trine" in a: return 0.5
    if "sextile" in a: return 0.4
    return 0.2

def compute_astro_score(positions, aspects, moon_phase):
    score = 0.0
    breakdown = {}

    illum = moon_phase.get("illumination", 0)
    if illum > 50:
        score += 1.5
        breakdown["moon_full"] = 1.5
    elif illum < 10:
        score -= 1.0
        breakdown["moon_new"] = -1.0

    for asp in aspects:
        p1, p2 = asp["planet1"], asp["planet2"]
        atype = asp["aspect"]
        contribution = (planet_weight(p1) + planet_weight(p2)) * aspect_score(atype) * 0.5
        if atype.lower() in ("trine", "sextile"):
            score += contribution
        elif atype.lower() in ("square", "opposition"):
            score -= contribution
        else:
            score += contribution * 0.3
        breakdown[f"{p1}_{p2}_{atype}"] = round(contribution, 2)

    for planet in ["mercury", "venus", "mars", "jupiter", "saturn"]:
        if positions.get(planet, {}).get("retrograde"):
            penalty = -1.5 if planet == "mercury" else -0.5
            score += penalty
            breakdown[f"{planet}_retrograde"] = penalty

    score = max(-10, min(10, score))
    return round(score, 2), breakdown

# ============================================================
# AIRTABLE LOGGING
# ============================================================
def log_astro(reference, positions, moon_phase, score, breakdown):
    try:
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_ASTRO_TABLE_ID]):
            return
        table = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_ASTRO_TABLE_ID)

        sun = positions.get("sun", {})
        moon = positions.get("moon", {})
        jup = positions.get("jupiter", {})
        sat = positions.get("saturn", {})
        merc = positions.get("mercury", {})
        ven = positions.get("venus", {})
        mars = positions.get("mars", {})
        rahu = positions.get("rahu", {})

        payload = {
            "Timestamp": datetime.now().isoformat(),
            "Reference": reference,
            "Sun_Sign": sun.get("sign", ""),
            "Sun_Degree": sun.get("degree", 0),
            "Moon_Sign": moon.get("sign", ""),
            "Moon_Phase": moon_phase.get("phase", ""),
            "Moon_Illumination": moon_phase.get("illumination", 0),
            "Mercury_Retrograde": bool(merc.get("retrograde", False)),
            "Venus_Retrograde": bool(ven.get("retrograde", False)),
            "Mars_Retrograde": bool(mars.get("retrograde", False)),
            "Jupiter_Sign": jup.get("sign", ""),
            "Jupiter_Degree": jup.get("degree", 0),
            "Saturn_Sign": sat.get("sign", ""),
            "Saturn_Degree": sat.get("degree", 0),
            "Nakshatra": nakshatra_of(moon.get("lon", 0)),
            "Current_Dasha": "",
            "Astro_Score": score,
            "Astro_Hierarchy": json.dumps(breakdown),
            "Vedic_House_2": rahu.get("sign", ""),
            "Vedic_House_5": "",
            "Vedic_House_8": "",
            "Vedic_House_11": "",
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

    dt = datetime.now(timezone.utc)
    jd = to_julian(dt)
    L(f"Julian day: {jd}")

    for ref, lat, lon in [("NYSE", NYSE_LAT, NYSE_LON), ("Local", LOCAL_LAT, LOCAL_LON)]:
        L(f"--- {ref} ---")
        positions = get_positions(jd, sidereal=False)
        aspects = compute_aspects(positions)
        moon_phase = get_moon_phase(jd)

        L(f"  Sun: {positions.get('sun',{}).get('sign','?')} {positions.get('sun',{}).get('degree','?')}°")
        L(f"  Moon: {positions.get('moon',{}).get('sign','?')} | Phase: {moon_phase['phase']} ({moon_phase['illumination']}%)")
        L(f"  Mercury Rx: {positions.get('mercury',{}).get('retrograde', False)}")
        L(f"  Aspects: {len(aspects)}")

        score, breakdown = compute_astro_score(positions, aspects, moon_phase)
        log_astro(ref, positions, moon_phase, score, breakdown)

    log_run("astro", "ok", action="astro signals logged")
    L("=" * 60)

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        L(f"❌ FATAL: {e}")
        send_telegram(f"❌ astro fatal: {e}")
