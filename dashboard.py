"""
Whale Bot Dashboard — Frutiger Aero Edition
Bright sky, glossy glass, Windows 7 / Vista era aesthetic.
"""

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Whale Bot",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# FRUTIGER AERO CSS
# ============================================================
AERO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Segoe UI', 'Lucida Grande', 'Trebuchet MS', Tahoma, sans-serif !important;
    color: #0e3a4a !important;
}

/* ---------- BACKGROUND: SKY + CLOUDS + GREEN HILL ---------- */
.stApp {
    background:
        radial-gradient(ellipse 60% 18% at 15% 12%, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0) 60%),
        radial-gradient(ellipse 45% 12% at 80% 8%, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0) 60%),
        radial-gradient(ellipse 55% 15% at 50% 20%, rgba(255,255,255,0.75) 0%, rgba(255,255,255,0) 65%),
        radial-gradient(ellipse 40% 10% at 25% 28%, rgba(255,255,255,0.6) 0%, rgba(255,255,255,0) 60%),
        radial-gradient(ellipse 100% 30% at 50% 100%, #7ac470 0%, #5fb454 40%, rgba(95,180,84,0) 80%),
        linear-gradient(180deg, #4fc3ee 0%, #6dd0f0 25%, #98e2ef 55%, #b8e8d8 80%, #a8dd9a 100%) !important;
    background-attachment: fixed !important;
    min-height: 100vh;
}

/* Floating glossy bubbles overlay */
.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image:
        radial-gradient(circle at 12% 22%, rgba(255,255,255,0.5) 0px, rgba(255,255,255,0.15) 8px, transparent 12px),
        radial-gradient(circle at 88% 45%, rgba(255,255,255,0.45) 0px, rgba(255,255,255,0.12) 10px, transparent 15px),
        radial-gradient(circle at 30% 78%, rgba(255,255,255,0.4) 0px, rgba(255,255,255,0.1) 6px, transparent 10px),
        radial-gradient(circle at 65% 15%, rgba(255,255,255,0.55) 0px, rgba(255,255,255,0.15) 5px, transparent 9px),
        radial-gradient(circle at 45% 55%, rgba(255,255,255,0.3) 0px, rgba(255,255,255,0.08) 7px, transparent 11px);
    background-size: 700px 700px, 800px 800px, 600px 600px, 500px 500px, 550px 550px;
    pointer-events: none;
    z-index: 0;
    animation: bubblesFloat 60s linear infinite;
}

@keyframes bubblesFloat {
    0%   { background-position: 0 0, 0 0, 0 0, 0 0, 0 0; }
    100% { background-position: 100px -700px, -120px -800px, 80px -600px, -60px -500px, 40px -550px; }
}

#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1200px;
    position: relative;
    z-index: 1;
}

/* ---------- WINDOWS-STYLE TITLE BAR ---------- */
h1 {
    background: linear-gradient(180deg, #d8eef8 0%, #a4d4ea 48%, #7bb8d8 52%, #5a9ac0 100%) !important;
    color: #103a52 !important;
    padding: 14px 22px !important;
    border-radius: 8px !important;
    border: 1px solid #4d8aa8 !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.95),
        inset 0 -1px 0 rgba(0,50,80,0.15),
        0 2px 8px rgba(0,50,80,0.35) !important;
    font-size: 1.8rem !important;
    font-weight: 400 !important;
    letter-spacing: 0.5px !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9) !important;
    margin-bottom: 0.5rem !important;
}

h2 {
    background: linear-gradient(180deg, rgba(255,255,255,0.85) 0%, rgba(200,235,245,0.7) 100%) !important;
    color: #0e4a68 !important;
    padding: 10px 18px !important;
    border-radius: 8px !important;
    border: 1px solid rgba(255,255,255,0.95) !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 3px 8px rgba(0,50,80,0.2) !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.95) !important;
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    margin-top: 1.8rem !important;
    margin-bottom: 1rem !important;
}

h3, h4 {
    color: #0e4a68 !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9), 0 2px 4px rgba(0,50,80,0.15) !important;
}

/* ---------- GLASS PANELS ---------- */
[data-testid="stMetric"],
[data-testid="stDataFrame"],
[data-testid="stExpander"],
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(180deg,
        rgba(255,255,255,0.85) 0%,
        rgba(235,248,255,0.72) 45%,
        rgba(180,220,240,0.65) 100%) !important;
    backdrop-filter: blur(18px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(18px) saturate(180%) !important;
    border: 1px solid rgba(255,255,255,0.95) !important;
    border-radius: 10px !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        inset 0 -1px 0 rgba(80,140,180,0.2),
        inset 0 0 30px rgba(255,255,255,0.4),
        0 6px 16px rgba(0,80,120,0.28),
        0 2px 4px rgba(0,80,120,0.15) !important;
    padding: 1.1rem 1.3rem !important;
    margin-bottom: 1rem !important;
    position: relative;
}

[data-testid="stMetric"]::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%;
    height: 38%;
    background: linear-gradient(180deg, rgba(255,255,255,0.75) 0%, rgba(255,255,255,0) 100%);
    border-radius: 10px 10px 40% 40%;
    pointer-events: none;
}

/* ---------- METRIC VALUES ---------- */
[data-testid="stMetricValue"] {
    color: #0d5a7a !important;
    font-weight: 700 !important;
    font-size: 2.4rem !important;
    text-shadow:
        0 1px 0 rgba(255,255,255,0.95),
        0 2px 6px rgba(0,80,120,0.2) !important;
}

[data-testid="stMetricLabel"] {
    color: #2a7090 !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-size: 0.7rem !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.8) !important;
}

/* ---------- AERO BUTTONS ---------- */
.stButton > button, .stDownloadButton > button {
    background:
        linear-gradient(180deg,
            #ffffff 0%,
            #e8f6ff 15%,
            #b8e0f0 48%,
            #7bb8d8 52%,
            #4d94b8 100%) !important;
    color: #0d3a52 !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    border: 1px solid #4d8aa8 !important;
    border-radius: 6px !important;
    padding: 0.55rem 1.4rem !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9) !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        inset 0 -1px 0 rgba(0,50,80,0.2),
        0 2px 6px rgba(0,50,80,0.25) !important;
    transition: all 0.12s ease !important;
}

.stButton > button:hover {
    background:
        linear-gradient(180deg,
            #ffffff 0%,
            #f0faff 15%,
            #c8ecff 48%,
            #8cc8e4 52%,
            #5aa8c8 100%) !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        inset 0 -1px 0 rgba(0,50,80,0.15),
        0 0 12px rgba(120,200,240,0.7),
        0 3px 8px rgba(0,50,80,0.3) !important;
}

.stButton > button:active {
    background: linear-gradient(180deg, #7bb8d8 0%, #4d94b8 100%) !important;
    box-shadow: inset 0 2px 6px rgba(0,50,80,0.4) !important;
}

/* ---------- TABS ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: transparent !important;
    border: none !important;
}
.stTabs [data-baseweb="tab"] {
    background: linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(200,235,255,0.55) 100%) !important;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.9) !important;
    border-bottom: none !important;
    border-radius: 8px 8px 0 0 !important;
    color: #0e4a68 !important;
    font-weight: 600 !important;
    padding: 8px 18px !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,1) !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, #ffffff 0%, #e0f2ff 50%, #c8e8fa 100%) !important;
    color: #054a6a !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 -1px 8px rgba(100,180,220,0.4) !important;
}

/* ---------- DATAFRAMES ---------- */
[data-testid="stDataFrame"],
[data-testid="stDataFrameResizable"],
[data-testid="stDataFrame"] > div,
[data-testid="stDataFrame"] iframe {
    background: rgba(255,255,255,0.55) !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255,255,255,0.95) !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 3px 10px rgba(0,80,120,0.2) !important;
    overflow: hidden !important;
}
[data-testid="stDataFrame"] [role="columnheader"],
[data-testid="stDataFrame"] [role="gridcell"] {
    background: transparent !important;
    color: #0d3a52 !important;
    font-family: 'Segoe UI', sans-serif !important;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    background: linear-gradient(180deg, #e8f6ff 0%, #b8dff0 100%) !important;
    color: #0a4a6a !important;
    font-weight: 700 !important;
    border-bottom: 1px solid #7bb8d8 !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9) !important;
}
[data-testid="stDataFrame"] [role="gridcell"] {
    border-bottom: 1px solid rgba(200,230,245,0.5) !important;
}
[data-testid="stDataFrame"] canvas {
    border-radius: 10px !important;
}

/* ---------- ALERT BOXES ---------- */
.stAlert {
    background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(215,240,255,0.75) 100%) !important;
    backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,0.95) !important;
    border-left: 4px solid #4fc3ee !important;
    border-radius: 8px !important;
    color: #0a4a6a !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 3px 10px rgba(0,80,120,0.22) !important;
    font-weight: 500 !important;
}

/* ---------- DIVIDERS ---------- */
hr {
    border: none !important;
    height: 2px !important;
    background: linear-gradient(90deg,
        rgba(255,255,255,0) 0%,
        rgba(255,255,255,0.85) 50%,
        rgba(255,255,255,0) 100%) !important;
    margin: 1.8rem 0 !important;
    box-shadow: 0 1px 2px rgba(0,80,120,0.15) !important;
}

/* ---------- SIDEBAR ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(255,255,255,0.8) 0%, rgba(200,235,255,0.7) 100%) !important;
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255,255,255,0.95) !important;
}

/* ---------- CHARTS ---------- */
[data-testid="stArrowVegaLiteChart"],
[data-testid="stVegaLiteChart"] {
    background: rgba(255,255,255,0.5) !important;
    border-radius: 10px !important;
    padding: 0.6rem !important;
    border: 1px solid rgba(255,255,255,0.9) !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 3px 8px rgba(0,80,120,0.18) !important;
}

/* ---------- FLOAT ANIMATION ---------- */
@keyframes aeroFloat {
    0%, 100% { transform: translateY(0px); }
    50%      { transform: translateY(-2px); }
}
[data-testid="stMetric"] {
    animation: aeroFloat 8s ease-in-out infinite;
}
[data-testid="stMetric"]:nth-of-type(1) { animation-delay: 0s; }
[data-testid="stMetric"]:nth-of-type(2) { animation-delay: 1s; }
[data-testid="stMetric"]:nth-of-type(3) { animation-delay: 2s; }
[data-testid="stMetric"]:nth-of-type(4) { animation-delay: 3s; }

/* ---------- TEXT ---------- */
p, span, div, label {
    color: #0d3a52 !important;
}
.stMarkdown p {
    text-shadow: 0 1px 0 rgba(255,255,255,0.7) !important;
}
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
    "<p style='color: #0a4a6a; font-size: 1rem; font-weight: 500; "
    "text-shadow: 0 1px 0 rgba(255,255,255,0.8); margin-top: -0.5rem;'>"
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
    if cols:
        st.dataframe(trades_df[cols].tail(20), use_container_width=True)
    else:
        st.info("Trades table has no matching columns yet.")
else:
    st.info("🌊 No trades logged yet. The bot will write its first entry when a signal fires.")

st.markdown("## 📋 Recent Exits")
if not exits_df.empty:
    show = ["Exit Timestamp", "Symbol", "Exit Reason", "PnL Dollars", "PnL Percent"]
    cols = [c for c in show if c in exits_df.columns]
    if cols:
        st.dataframe(exits_df[cols].tail(20), use_container_width=True)
    else:
        st.info("Exits table has no matching columns yet.")
else:
    st.info("🌊 No exits yet. This fills in when a trade hits its target or stop-loss.")

st.markdown("---")

# ============================================================
# FOOTER
# ============================================================
st.markdown(
    "<p style='text-align: center; color: #0a4a6a; font-weight: 500; "
    "font-size: 0.85rem; text-shadow: 0 1px 0 rgba(255,255,255,0.8); "
    "padding-top: 2rem;'>"
    "🐋 Whale Bot · Frutiger Aero Edition · Refreshes every 60s"
    "</p>",
    unsafe_allow_html=True,
   )
