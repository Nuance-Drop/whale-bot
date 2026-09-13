"""
Whale Bot Dashboard — Frutiger Aero Edition
Glassy, aqua, early-2000s Windows Vista aesthetic.
"""

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

st.set_page_config(
    page_title="Whale Bot",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# FRUTIGER AERO THEME — Custom CSS
# ============================================================
AERO_CSS = """
<style>
/* ---------- FONTS ---------- */
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700&family=Lucida+Grande&display=swap');

html, body, [class*="css"] {
    font-family: 'Segoe UI', 'Lucida Grande', 'Trebuchet MS', sans-serif !important;
}

/* ---------- BACKGROUND: SKY + WATER GRADIENT ---------- */
.stApp {
    background: 
        radial-gradient(ellipse at 20% 0%, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0) 45%),
        radial-gradient(ellipse at 80% 100%, rgba(154,239,242,0.7) 0%, rgba(154,239,242,0) 50%),
        linear-gradient(180deg, #6dd6ec 0%, #33bcde 30%, #129aca 65%, #0a7ba8 100%) !important;
    background-attachment: fixed !important;
    min-height: 100vh;
}

/* Subtle floating bubbles background */
.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: 
        radial-gradient(circle at 10% 20%, rgba(255,255,255,0.15) 3px, transparent 3px),
        radial-gradient(circle at 80% 60%, rgba(255,255,255,0.12) 5px, transparent 5px),
        radial-gradient(circle at 45% 85%, rgba(255,255,255,0.10) 4px, transparent 4px),
        radial-gradient(circle at 92% 25%, rgba(255,255,255,0.14) 2px, transparent 2px);
    background-size: 400px 400px, 500px 500px, 600px 600px, 350px 350px;
    pointer-events: none;
    z-index: 0;
    animation: floatUp 40s linear infinite;
}

@keyframes floatUp {
    0%   { background-position: 0 0, 0 0, 0 0, 0 0; }
    100% { background-position: 0 -400px, 0 -500px, 0 -600px, 0 -350px; }
}

/* ---------- HIDE STREAMLIT DEFAULT CHROME ---------- */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem !important; padding-bottom: 3rem !important; max-width: 1300px; }

/* ---------- HEADINGS: GLOSSY WHITE ---------- */
h1, h2, h3, h4 {
    color: #ffffff !important;
    text-shadow: 
        0 1px 0 rgba(255,255,255,0.4),
        0 2px 4px rgba(0,50,80,0.3),
        0 4px 12px rgba(0,50,80,0.2) !important;
    letter-spacing: 0.3px;
    font-weight: 700 !important;
}
h1 { font-size: 2.6rem !important; }
h2 { font-size: 1.5rem !important; margin-top: 1.5rem !important; }
h3 { font-size: 1.15rem !important; }

/* ---------- GLASS PANELS (containers, metrics, dataframes) ---------- */
[data-testid="stMetric"],
[data-testid="stDataFrame"],
[data-testid="stExpander"],
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(180deg, rgba(255,255,255,0.72) 0%, rgba(230,243,255,0.58) 100%) !important;
    backdrop-filter: blur(16px) saturate(160%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(160%) !important;
    border: 1px solid rgba(255,255,255,0.9) !important;
    border-radius: 14px !important;
    box-shadow:
        0 1px 0 rgba(255,255,255,1) inset,
        0 -1px 0 rgba(0,80,120,0.15) inset,
        0 6px 18px rgba(0,80,120,0.25),
        0 2px 6px rgba(0,80,120,0.15) !important;
    padding: 1rem 1.2rem !important;
    margin-bottom: 1rem !important;
}

/* ---------- METRIC VALUES ---------- */
[data-testid="stMetricValue"] {
    color: #0a5a7a !important;
    font-weight: 700 !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.8) !important;
    font-size: 2.2rem !important;
}
[data-testid="stMetricLabel"] {
    color: #2c7c96 !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 0.75rem !important;
}

/* ---------- BUTTONS: GLOSSY AERO ---------- */
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(180deg, #e8f6ff 0%, #a8e4f4 45%, #55c0e0 50%, #1e97c4 100%) !important;
    color: #053a52 !important;
    font-weight: 700 !important;
    border: 1px solid rgba(255,255,255,0.95) !important;
    border-radius: 20px !important;
    padding: 0.55rem 1.4rem !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.7) !important;
    box-shadow:
        0 1px 0 rgba(255,255,255,1) inset,
        0 -8px 12px rgba(0,80,120,0.2) inset,
        0 4px 10px rgba(0,80,120,0.3) !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(180deg, #ffffff 0%, #c5ecf8 45%, #6ccce8 50%, #2aa5d0 100%) !important;
    transform: translateY(-1px);
    box-shadow:
        0 1px 0 rgba(255,255,255,1) inset,
        0 -8px 12px rgba(0,80,120,0.15) inset,
        0 6px 14px rgba(0,80,120,0.35) !important;
}
.stButton > button:active {
    transform: translateY(1px);
    box-shadow:
        0 2px 6px rgba(0,80,120,0.4) inset !important;
}

/* ---------- INPUTS ---------- */
.stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
    background: rgba(255,255,255,0.85) !important;
    border: 1px solid rgba(255,255,255,0.95) !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 6px rgba(0,80,120,0.15) inset !important;
    color: #0a3a52 !important;
}

/* ---------- TABS ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: transparent !important;
    border: none !important;
}
.stTabs [data-baseweb="tab"] {
    background: linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(200,235,255,0.4) 100%) !important;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.8) !important;
    border-radius: 14px 14px 0 0 !important;
    color: #0a5a7a !important;
    font-weight: 600 !important;
    padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, #ffffff 0%, #d8f0ff 100%) !important;
    color: #054a6a !important;
    box-shadow: 0 -2px 8px rgba(0,80,120,0.25) !important;
}

/* ---------- DATAFRAME TEXT ---------- */
[data-testid="stDataFrame"] * {
    color: #053a52 !important;
}
[data-testid="stDataFrame"] thead tr th {
    background: linear-gradient(180deg, #e8f6ff 0%, #b8e0f0 100%) !important;
    color: #054a6a !important;
    font-weight: 700 !important;
    border-bottom: 1px solid rgba(255,255,255,0.9) !important;
}

/* ---------- ALERTS / INFO BOXES ---------- */
.stAlert {
    background: linear-gradient(180deg, rgba(255,255,255,0.75) 0%, rgba(220,245,255,0.6) 100%) !important;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.9) !important;
    border-radius: 12px !important;
    color: #0a5a7a !important;
    box-shadow: 0 4px 12px rgba(0,80,120,0.2) !important;
}

/* ---------- DIVIDERS ---------- */
hr {
    border: none !important;
    height: 2px !important;
    background: linear-gradient(90deg, 
        rgba(255,255,255,0) 0%, 
        rgba(255,255,255,0.7) 50%, 
        rgba(255,255,255,0) 100%) !important;
    margin: 1.5rem 0 !important;
}

/* ---------- SIDEBAR ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(255,255,255,0.85) 0%, rgba(200,235,255,0.75) 100%) !important;
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255,255,255,0.9) !important;
}

/* ---------- CHARTS ---------- */
[data-testid="stArrowVegaLiteChart"] {
    background: rgba(255,255,255,0.4) !important;
    border-radius: 12px !important;
    padding: 0.5rem !important;
}

/* ---------- ANIMATION: everything floats gently ---------- */
@keyframes aeroFloat {
    0%, 100% { transform: translateY(0px); }
    50%      { transform: translateY(-3px); }
}
[data-testid="stMetric"] {
    animation: aeroFloat 6s ease-in-out infinite;
}
[data-testid="stMetric"]:nth-child(2) { animation-delay: 0.5s; }
[data-testid="stMetric"]:nth-child(3) { animation-delay: 1s; }
[data-testid="stMetric"]:nth-child(4) { animation-delay: 1.5s; }
</style>
"""
st.markdown(AERO_CSS, unsafe_allow_html=True)

# ============================================================
# SECRETS
# ============================================================
AIRTABLE_API_KEY = st.secrets["AIRTABLE_API_KEY"]
BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
TRADES_ID = st.secrets["AIRTABLE_TABLE_ID"]
EXITS_ID = st.secrets["AIRTABLE_EXITS_TABLE_ID"]
FILLS_ID = st.secrets["AIRTABLE_FILLS_TABLE_ID"]

BASE = f"https://api.airtable.com/v0/{BASE_ID}"
H = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

@st.cache_data(ttl=60)
def fetch(table_id):
    out, params = [], {}
    while True:
        r = requests.get(f"{BASE}/{table_id}", headers=H, params=params, timeout=30)
        d = r.json()
        out.extend(d.get("records", []))
        if not d.get("offset"):
            break
        params["offset"] = d["offset"]
    return [rec["fields"] for rec in out]

# ============================================================
# HEADER
# ============================================================
st.markdown("# 🐋 Whale Bot Dashboard")
st.markdown(
    "<p style='color: rgba(255,255,255,0.9); font-size: 1rem; "
    "text-shadow: 0 1px 3px rgba(0,50,80,0.5); margin-top: -1rem;'>"
    "Automated multi-signal trading · Live from Airtable</p>",
    unsafe_allow_html=True,
)

# ============================================================
# LOAD DATA
# ============================================================
try:
    exits_df = pd.DataFrame(fetch(EXITS_ID))
    trades_df = pd.DataFrame(fetch(TRADES_ID))
    fills_df = pd.DataFrame(fetch(FILLS_ID))
except Exception as e:
    st.error(f"Failed to load Airtable data: {e}")
    st.stop()

# ============================================================
# COMPUTE DERIVED COLUMNS
# ============================================================
# Fix: Compute Slippage (%) from Slippage ($) and Expected Price if missing
if not fills_df.empty and "Slippage (%)" not in fills_df.columns:
    if "Slippage ($)" in fills_df.columns and "Expected Price" in fills_df.columns:
        fills_df["Slippage (%)"] = (
            fills_df["Slippage ($)"] /
            fills_df["Expected Price"].replace(0, np.nan)
        ) * 100

# ============================================================
# TOP METRICS
# ============================================================
c1, c2, c3, c4 = st.columns(4)

if not exits_df.empty and "PnL Dollars" in exits_df.columns:
    total_pnl = exits_df["PnL Dollars"].sum()
    wins = (exits_df["PnL Dollars"] > 0).sum()
    win_rate = wins / len(exits_df) if len(exits_df) else 0
    c1.metric("Total P/L", f"${total_pnl:,.2f}")
    c2.metric("Win Rate", f"{win_rate:.0%}")
else:
    c1.metric("Total P/L", "$0.00")
    c2.metric("Win Rate", "—")

open_trades = len(trades_df) - len(exits_df) if not trades_df.empty else 0
c3.metric("Open Trades", max(open_trades, 0))
c4.metric("Fills Logged", len(fills_df))

st.markdown("---")

# ============================================================
# EQUITY CURVE
# ============================================================
st.markdown("## 💹 Equity Curve")
if not exits_df.empty and "PnL Dollars" in exits_df.columns:
    sorted_exits = exits_df.sort_values("Exit Timestamp").copy()
    sorted_exits["Cumulative"] = sorted_exits["PnL Dollars"].cumsum()
    st.line_chart(
        sorted_exits.set_index("Exit Timestamp")["Cumulative"],
        height=260,
    )
else:
    st.info("No closed trades yet. The first data point appears after a trade hits its target or stop.")

st.markdown("---")

# ============================================================
# SIGNAL PERFORMANCE
# ============================================================
st.markdown("## 📡 Signal Performance")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### Execution Slippage")
    if not fills_df.empty and "Slippage (%)" in fills_df.columns:
        slip = fills_df.groupby("Order Type")["Slippage (%)"].agg(["mean", "count"])
        slip.columns = ["Avg Slippage (%)", "Count"]
        st.dataframe(slip, use_container_width=True)
    else:
        st.info("No fills logged yet.")

with col2:
    st.markdown("### P/L by Symbol")
    if not exits_df.empty and "PnL Dollars" in exits_df.columns:
        by_sym = exits_df.groupby("Symbol")["PnL Dollars"].sum().sort_values()
        st.bar_chart(by_sym, height=260)
    else:
        st.info("No closed trades yet.")

st.markdown("---")

# ============================================================
# RECENT TABLES
# ============================================================
st.markdown("## 📋 Recent Trades")
if not trades_df.empty:
    show = ["Timestamp", "Symbol", "Qty", "Price", "Score", "Threshold"]
    cols = [c for c in show if c in trades_df.columns]
    st.dataframe(trades_df[cols].tail(20), use_container_width=True)
else:
    st.info("No trades logged yet.")

st.markdown("## 📋 Recent Exits")
if not exits_df.empty:
    show = ["Exit Timestamp", "Symbol", "Exit Reason", "PnL Dollars", "PnL Percent"]
    cols = [c for c in show if c in exits_df.columns]
    st.dataframe(exits_df[cols].tail(20), use_container_width=True)
else:
    st.info("No exits yet.")

st.markdown("---")

# ============================================================
# FOOTER
# ============================================================
st.markdown(
    "<p style='text-align: center; color: rgba(255,255,255,0.7); "
    "font-size: 0.8rem; text-shadow: 0 1px 3px rgba(0,50,80,0.5); "
    "padding-top: 2rem;'>"
    "🐋 Whale Bot · Frutiger Aero Edition · Data refreshes every 60s"
    "</p>",
    unsafe_allow_html=True,
)
