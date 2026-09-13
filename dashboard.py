"""Streamlit dashboard. Deploy to Streamlit Cloud, connect to this repo."""
import streamlit as st
import requests, pandas as pd
from datetime import datetime
from collections import defaultdict

st.set_page_config(page_title="Whale Bot", page_icon="🐋", layout="wide")

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
        if not d.get("offset"): break
        params["offset"] = d["offset"]
    return [r["fields"] for r in out]

st.title("🐋 Whale Bot Dashboard")

try:
    exits = pd.DataFrame(fetch(EXITS_ID))
    trades = pd.DataFrame(fetch(TRADES_ID))
    fills = pd.DataFrame(fetch(FILLS_ID))
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# ---- HEADER METRICS ----
c1, c2, c3, c4 = st.columns(4)
if not exits.empty and "PnL Dollars" in exits:
    total_pnl = exits["PnL Dollars"].sum()
    wins = (exits["PnL Dollars"] > 0).sum()
    win_rate = wins / len(exits) if len(exits) else 0
    c1.metric("Total P/L", f"${total_pnl:,.2f}")
    c2.metric("Win Rate", f"{win_rate:.1%}")
c3.metric("Open Trades", len(trades) - len(exits) if not trades.empty else 0)
c4.metric("Fills Logged", len(fills))

st.divider()

# ---- EQUITY CURVE ----
st.subheader("Equity Curve")
if not exits.empty and "PnL Dollars" in exits:
    exits_sorted = exits.sort_values("Exit Timestamp")
    exits_sorted["Cumulative"] = exits_sorted["PnL Dollars"].cumsum()
    st.line_chart(exits_sorted.set_index("Exit Timestamp")["Cumulative"])
else:
    st.info("No closed trades yet.")

# ---- SIGNAL PERFORMANCE ----
st.subheader("Signal Performance (IC)")
col1, col2 = st.columns(2)

with col1:
    st.markdown("**Slippage by Order Type**")
    if not fills.empty and "Slippage (%)" in fills:
        slip = fills.groupby("Order Type")["Slippage (%)"].agg(["mean", "count"])
        st.dataframe(slip, use_container_width=True)
    else:
        st.info("No fills logged yet.")

with col2:
    st.markdown("**P/L by Symbol**")
    if not exits.empty and "PnL Dollars" in exits:
        by_sym = exits.groupby("Symbol")["PnL Dollars"].sum().sort_values()
        st.bar_chart(by_sym)
    else:
        st.info("No closed trades yet.")

# ---- RECENT TABLES ----
st.subheader("Recent Trades")
if not trades.empty:
    show = ["Timestamp", "Symbol", "Qty", "Price", "Score", "Threshold"]
    cols = [c for c in show if c in trades.columns]
    st.dataframe(trades[cols].tail(20), use_container_width=True)

st.subheader("Recent Exits")
if not exits.empty:
    show = ["Exit Timestamp", "Symbol", "Exit Reason", "PnL Dollars", "PnL Percent"]
    cols = [c for c in show if c in exits.columns]
    st.dataframe(exits[cols].tail(20), use_container_width=True)
