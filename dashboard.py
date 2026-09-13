"""
Whale Bot Dashboard v3 — Authentic Frutiger Aero
Streamlit as data proxy + full HTML/CSS window metaphor.

Flow:
  1. Fetch Airtable data server-side (secrets stay on the server)
  2. Build a JSON payload
  3. Sanitize payload (NaN/Inf → 0) so JS can parse it
  4. Inject payload into a fully custom HTML/CSS/JS page
  5. Render via st.components.v1.html()
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import numpy as np
import json
import math
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

# Strip Streamlit chrome — the iframe is the entire page
st.markdown(
    """
    <style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    [data-testid="stAppViewContainer"] > .main { padding: 0 !important; }
    iframe { display: block; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# SECRETS
# ============================================================
AIRTABLE_API_KEY = st.secrets["AIRTABLE_API_KEY"]
BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
TRADES_ID = st.secrets["AIRTABLE_TABLE_ID"]
EXITS_ID = st.secrets["AIRTABLE_EXITS_TABLE_ID"]
FILLS_ID = st.secrets["AIRTABLE_FILLS_TABLE_ID"]

BASE = f"https://api.airtable.com/v0/{BASE_ID}"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

# ============================================================
# FETCH
# ============================================================
@st.cache_data(ttl=60)
def fetch(table_id):
    """Fetch every record from an Airtable table (handles pagination)."""
    out, params = [], {}
    while True:
        r = requests.get(f"{BASE}/{table_id}", headers=HEADERS, params=params, timeout=30)
        d = r.json()
        out.extend(d.get("records", []))
        if not d.get("offset"):
            break
        params["offset"] = d["offset"]
    return [rec["fields"] for rec in out]

try:
    trades = fetch(TRADES_ID)
    exits = fetch(EXITS_ID)
    fills = fetch(FILLS_ID)
except Exception as e:
    st.error(f"Airtable fetch failed: {e}")
    st.stop()

# ============================================================
# DERIVED FIELDS
# ============================================================
# Backfill Slippage (%) if the Airtable column is missing
for f in fills:
    if "Slippage (%)" not in f and "Slippage ($)" in f and "Expected Price" in f:
        ep = f.get("Expected Price", 0)
        if ep:
            f["Slippage (%)"] = round((f["Slippage ($)"] / ep) * 100, 4)

# Top-level metrics
total_pnl = sum(e.get("PnL Dollars", 0) for e in exits)
wins = sum(1 for e in exits if e.get("PnL Dollars", 0) > 0)
win_rate = (wins / len(exits) * 100) if exits else 0
open_trades = max(len(trades) - len(exits), 0)

# Cumulative equity curve
exits_sorted = sorted(exits, key=lambda x: x.get("Exit Timestamp", ""))
cum = 0
equity_points = []
for e in exits_sorted:
    cum += e.get("PnL Dollars", 0)
    equity_points.append({"t": e.get("Exit Timestamp", ""), "v": round(cum, 2)})

# P/L by symbol
by_symbol = {}
for e in exits:
    s = e.get("Symbol", "?")
    by_symbol[s] = by_symbol.get(s, 0) + e.get("PnL Dollars", 0)

# ============================================================
# PAYLOAD
# ============================================================
payload = {
    "total_pnl": round(total_pnl, 2),
    "win_rate": round(win_rate, 1),
    "open_trades": open_trades,
    "fills_count": len(fills),
    "trades": trades[-20:],
    "exits": exits[-20:],
    "fills": fills[-20:],
    "equity": equity_points,
    "by_symbol": by_symbol,
    "refreshed": datetime.now().strftime("%I:%M %p"),
    "n_trades": len(trades),
    "n_exits": len(exits),
    "n_fills": len(fills),
}

# ============================================================
# SANITIZE PAYLOAD FOR JSON
# ============================================================
def clean_for_json(obj):
    """Recursively replace NaN/Inf with 0 so json.dumps produces valid JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0
        return obj
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_for_json(x) for x in obj]
    return obj

payload = clean_for_json(payload)

# ============================================================
# HTML TEMPLATE
# ============================================================
HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body {{
    font-family: 'Segoe UI', Tahoma, sans-serif;
    min-height: 100vh;
    color: #0a3a52;
    overflow-x: hidden;
}}

/* ---------- DESKTOP BACKGROUND ---------- */
body {{
    background:
        radial-gradient(ellipse 320px 100px at 8% 10%, rgba(255,255,255,0.98), transparent 70%),
        radial-gradient(ellipse 240px 70px at 24% 14%, rgba(255,255,255,0.9), transparent 72%),
        radial-gradient(ellipse 380px 120px at 78% 6%, rgba(255,255,255,0.95), transparent 70%),
        radial-gradient(ellipse 280px 85px at 56% 18%, rgba(255,255,255,0.85), transparent 72%),
        radial-gradient(ellipse 340px 95px at 92% 22%, rgba(255,255,255,0.8), transparent 72%),
        radial-gradient(circle 500px at 0% 0%, rgba(255,250,220,0.5), transparent 55%),
        radial-gradient(ellipse 150% 22% at 50% 106%, #7bc86d 0%, #5db04d 30%, #4a9c3e 55%, transparent 85%),
        linear-gradient(180deg, #58bce8 0%, #6cc8ec 20%, #8cd8ec 45%, #b0e4e0 70%, #c8ecb0 92%, #a8dd9a 100%);
    background-attachment: fixed;
    padding: 40px 40px 90px 40px;
}}

body::before {{
    content: '';
    position: fixed;
    top: 0; left: -200px; right: -200px; bottom: 0;
    background-image:
        radial-gradient(ellipse 200px 55px at 15% 15%, rgba(255,255,255,0.85), transparent 70%),
        radial-gradient(ellipse 240px 60px at 65% 25%, rgba(255,255,255,0.65), transparent 70%),
        radial-gradient(ellipse 180px 50px at 88% 8%, rgba(255,255,255,0.75), transparent 70%);
    background-size: 900px 600px, 1000px 700px, 800px 500px;
    pointer-events: none;
    z-index: 0;
    animation: drift 140s linear infinite;
}}

@keyframes drift {{
    from {{ background-position: 0 0, 0 0, 0 0; }}
    to   {{ background-position: 400px 0, 300px 0, 350px 0; }}
}}

/* ---------- AERO WINDOW ---------- */
.aero-window {{
    position: relative;
    z-index: 1;
    max-width: 1400px;
    margin: 0 auto;
    border-radius: 8px 8px 4px 4px;
    box-shadow:
        0 0 0 1px rgba(0,50,80,0.35),
        0 14px 40px rgba(0,50,80,0.35),
        0 4px 10px rgba(0,50,80,0.25);
    overflow: hidden;
    background: rgba(220, 240, 255, 0.65);
    backdrop-filter: blur(20px) saturate(170%);
    -webkit-backdrop-filter: blur(20px) saturate(170%);
}}

.window-titlebar {{
    background: linear-gradient(180deg,
        #eaf6fc 0%,
        #c8e4f0 8%,
        #9ccde4 45%,
        #7ab8d4 47%,
        #5a9cc0 52%,
        #4a8cb0 92%,
        #6aa8c8 100%);
    padding: 7px 8px 7px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(0,50,80,0.25);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.95),
        inset 0 -1px 0 rgba(0,50,80,0.15);
    font-size: 13px;
    font-weight: 600;
    color: #0a3a52;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9);
    letter-spacing: 0.3px;
}}

.window-titlebar .title {{
    display: flex;
    align-items: center;
    gap: 8px;
}}

.window-controls {{ display: flex; gap: 2px; }}

.win-btn {{
    width: 30px;
    height: 20px;
    border-radius: 3px;
    border: 1px solid rgba(255,255,255,0.5);
    background: linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.15) 48%, rgba(0,0,0,0.05) 52%, rgba(255,255,255,0.15) 100%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6), inset 0 -1px 0 rgba(0,50,80,0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    color: #0a3a52;
    cursor: pointer;
    transition: filter 0.15s;
}}
.win-btn:hover {{ filter: brightness(1.15); }}
.win-btn.close {{
    background: linear-gradient(180deg, #ff9b7a 0%, #e8603a 45%, #c84028 55%, #a02818 100%);
    color: white;
    border-color: #8a2828;
}}

.window-body {{
    background: linear-gradient(180deg, rgba(235, 248, 255, 0.75) 0%, rgba(210, 235, 250, 0.65) 100%);
    padding: 22px 26px;
}}

/* ---------- LAYOUT ---------- */
.workspace {{
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 20px;
}}

/* ---------- EXPLORER SIDEBAR ---------- */
.explorer {{
    background: linear-gradient(180deg, rgba(255,255,255,0.8) 0%, rgba(240,248,255,0.7) 100%);
    border: 1px solid rgba(120,180,220,0.6);
    border-radius: 6px;
    padding: 10px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 3px 8px rgba(0,80,120,0.15);
    height: fit-content;
}}

.explorer-header {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #2a6a8a;
    padding: 4px 6px 8px 6px;
    border-bottom: 1px solid rgba(120,180,220,0.4);
    margin-bottom: 8px;
}}

.tree-node {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 13px;
    color: #153a52;
    cursor: pointer;
    transition: background 0.12s;
    margin-bottom: 2px;
}}
.tree-node:hover {{
    background: linear-gradient(180deg, #e5f3ff 0%, #cfe8ff 100%);
    outline: 1px solid #99d1ff;
}}
.tree-node.active {{
    background: linear-gradient(180deg, #d5ecff 0%, #b8dfff 100%);
    outline: 1px solid #6cb8ec;
    font-weight: 600;
}}

.node-icon {{ font-size: 14px; }}

/* ---------- MAIN ---------- */
.main {{ min-width: 0; }}

.page-title {{
    font-size: 26px;
    font-weight: 300;
    color: #0a3a52;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9), 0 2px 4px rgba(0,80,120,0.15);
    margin-bottom: 4px;
}}
.page-sub {{
    font-size: 13px;
    color: #2a6a8a;
    text-shadow: 0 1px 0 rgba(255,255,255,0.8);
    margin-bottom: 22px;
}}

/* ---------- GADGET GRID (asymmetric 2:1:1:1) ---------- */
.gadget-row {{
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr;
    gap: 14px;
    margin-bottom: 22px;
}}

.gadget {{
    position: relative;
    background: linear-gradient(180deg,
        rgba(255,255,255,0.92) 0%,
        rgba(240,250,255,0.85) 45%,
        rgba(200,230,245,0.78) 100%);
    border: 1px solid rgba(255,255,255,0.98);
    border-radius: 10px;
    padding: 16px 16px 14px 16px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        inset 0 -20px 40px rgba(150,200,230,0.15),
        inset 0 -1px 0 rgba(80,140,180,0.2),
        0 6px 14px rgba(0,80,120,0.22),
        0 14px 32px rgba(0,80,120,0.12);
    overflow: hidden;
}}
.gadget::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 48%;
    background: linear-gradient(180deg,
        rgba(255,255,255,0.85) 0%,
        rgba(255,255,255,0.35) 60%,
        rgba(255,255,255,0) 100%);
    border-radius: 10px 10px 50% 50%;
    pointer-events: none;
}}
.gadget::after {{
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 18%;
    background: linear-gradient(0deg, rgba(180,220,240,0.35), transparent);
    pointer-events: none;
}}

.gadget-label {{
    position: relative;
    z-index: 1;
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.6px;
    color: #2a6a8a;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9);
    margin-bottom: 6px;
}}
.gadget-value {{
    position: relative;
    z-index: 1;
    font-family: Georgia, 'Times New Roman', serif;
    font-weight: 700;
    font-size: 34px;
    color: #0a4a6a;
    text-shadow:
        0 1px 0 rgba(255,255,255,1),
        0 2px 6px rgba(0,80,120,0.18);
    line-height: 1;
}}
.gadget-sub {{
    position: relative;
    z-index: 1;
    font-size: 11px;
    color: #2a6a8a;
    margin-top: 6px;
}}

/* ---------- SECTIONS ---------- */
.section {{
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #0a3a52;
    padding-bottom: 6px;
    margin: 22px 0 12px 0;
    border-bottom: 1px solid rgba(255,255,255,0.9);
    position: relative;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9);
}}
.section::after {{
    content: '';
    position: absolute;
    bottom: -1px; left: 0;
    width: 60px; height: 2px;
    background: linear-gradient(90deg, #4a9cc0, transparent);
}}

/* ---------- CHART PANELS ---------- */
.chart-panel {{
    background: linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(235,248,255,0.55) 100%);
    border: 1px solid rgba(255,255,255,0.95);
    border-radius: 10px;
    padding: 14px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 4px 10px rgba(0,80,120,0.15);
    margin-bottom: 16px;
}}

.chart-svg {{ width: 100%; height: 200px; display: block; }}

/* ---------- BAR CHART ---------- */
.bar-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 0;
    font-size: 12px;
}}
.bar-label {{
    width: 60px;
    font-weight: 600;
    color: #153a52;
}}
.bar-track {{
    flex: 1;
    height: 18px;
    background: linear-gradient(180deg, rgba(220,235,245,0.8), rgba(200,220,235,0.6));
    border-radius: 4px;
    position: relative;
    overflow: hidden;
    box-shadow: inset 0 1px 3px rgba(0,50,80,0.15);
}}
.bar-fill {{
    height: 100%;
    background: linear-gradient(180deg, #7ee49c 0%, #4ac070 50%, #2a9c50 100%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
    border-radius: 4px;
}}
.bar-fill.negative {{
    background: linear-gradient(180deg, #ff9090 0%, #e86060 50%, #c84040 100%);
}}
.bar-value {{
    width: 80px;
    text-align: right;
    font-family: Georgia, serif;
    font-weight: 700;
    color: #153a52;
}}

/* ---------- GLASS TABLE ---------- */
.glass-table {{
    width: 100%;
    border-collapse: collapse;
    background: rgba(255,255,255,0.5);
    border-radius: 8px;
    overflow: hidden;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 3px 10px rgba(0,80,120,0.15);
    font-size: 12px;
}}
.glass-table thead th {{
    background: linear-gradient(180deg, #eaf6fc 0%, #c8e4f0 48%, #9ccde4 52%, #7ab8d4 100%);
    color: #0a3a52;
    text-align: left;
    padding: 8px 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-size: 10.5px;
    text-shadow: 0 1px 0 rgba(255,255,255,0.95);
    border-bottom: 1px solid #5a9cc0;
}}
.glass-table tbody td {{
    padding: 7px 12px;
    border-bottom: 1px solid rgba(180,220,240,0.35);
    color: #153a52;
}}
.glass-table tbody tr:nth-child(even) td {{
    background: rgba(235,248,255,0.4);
}}
.glass-table tbody tr:hover td {{
    background: rgba(210,240,255,0.6);
}}

/* ---------- EMPTY STATE ---------- */
.empty-state {{
    padding: 22px;
    text-align: center;
    background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(220,240,255,0.7) 100%);
    border: 1px solid rgba(255,255,255,0.95);
    border-radius: 12px;
    color: #2a6a8a;
    font-size: 13px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        inset 0 -20px 40px rgba(150,200,230,0.1),
        0 4px 12px rgba(0,80,120,0.15);
}}

/* ---------- TASKBAR ---------- */
.taskbar {{
    position: fixed;
    left: 0; right: 0; bottom: 0;
    height: 44px;
    background: linear-gradient(180deg,
        rgba(30,90,140,0.55) 0%,
        rgba(15,60,100,0.7) 48%,
        rgba(8,40,75,0.8) 52%,
        rgba(20,70,110,0.75) 100%);
    backdrop-filter: blur(22px) saturate(180%);
    -webkit-backdrop-filter: blur(22px) saturate(180%);
    border-top: 1px solid rgba(255,255,255,0.35);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.4),
        inset 0 -1px 0 rgba(0,0,0,0.3),
        0 -3px 14px rgba(0,30,60,0.4);
    display: flex;
    align-items: center;
    padding: 0 10px;
    gap: 8px;
    z-index: 9999;
    font-size: 12px;
    color: rgba(255,255,255,0.9);
}}

.start-orb-wrapper {{
    position: relative;
    width: 52px;
    height: 44px;
    flex-shrink: 0;
}}
.start-orb {{
    position: absolute;
    top: -6px; left: 4px;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background:
        radial-gradient(circle at 50% 22%, #b4ecff 0%, #4ec0f0 25%, #1c82c0 65%, #0a4a80 100%);
    box-shadow:
        inset 0 2px 4px rgba(255,255,255,0.9),
        inset 0 -4px 8px rgba(0,40,80,0.5),
        0 2px 6px rgba(0,0,0,0.4),
        0 0 20px rgba(120,200,240,0.7);
    border: 1px solid rgba(255,255,255,0.5);
    cursor: pointer;
    transition: filter 0.2s;
}}
.start-orb:hover {{
    filter: brightness(1.15) drop-shadow(0 0 10px rgba(120,220,255,0.9));
}}
.start-orb::before {{
    content: '';
    position: absolute;
    top: 8%; left: 20%; right: 20%;
    height: 30%;
    background: linear-gradient(180deg, rgba(255,255,255,0.85), rgba(255,255,255,0));
    border-radius: 50%;
}}

.taskbar-tab {{
    padding: 6px 14px;
    border-radius: 4px;
    background: linear-gradient(180deg,
        rgba(255,255,255,0.35) 0%,
        rgba(180,220,245,0.25) 48%,
        rgba(120,180,220,0.35) 52%,
        rgba(90,150,200,0.4) 100%);
    border: 1px solid rgba(255,255,255,0.5);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.6),
        0 1px 3px rgba(0,0,0,0.3);
    color: #ffffff;
    font-weight: 600;
    text-shadow: 0 1px 2px rgba(0,30,60,0.6);
    display: flex;
    align-items: center;
    gap: 6px;
}}
.taskbar-tab.active {{
    background: linear-gradient(180deg,
        rgba(255,255,255,0.55) 0%,
        rgba(200,235,255,0.5) 48%,
        rgba(140,200,240,0.55) 52%,
        rgba(100,170,220,0.6) 100%);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.9),
        inset 0 -1px 0 rgba(0,40,80,0.3),
        0 0 14px rgba(120,200,255,0.6),
        0 1px 3px rgba(0,0,0,0.4);
}}

.taskbar-clock {{
    margin-left: auto;
    padding: 4px 12px;
    background: linear-gradient(180deg, rgba(255,255,255,0.25), rgba(180,220,245,0.15));
    border: 1px solid rgba(255,255,255,0.35);
    border-radius: 4px;
    font-size: 11px;
    color: #ffffff;
    text-shadow: 0 1px 2px rgba(0,30,60,0.6);
    text-align: center;
    line-height: 1.2;
}}
</style>
</head>
<body>

<!-- AERO WINDOW -->
<div class="aero-window">
    <div class="window-titlebar">
        <div class="title">
            <span style="font-size:15px">🐋</span>
            <span>Whale Bot Dashboard — Windows Internet Explorer</span>
        </div>
        <div class="window-controls">
            <button class="win-btn min">—</button>
            <button class="win-btn max">□</button>
            <button class="win-btn close">✕</button>
        </div>
    </div>

    <div class="window-body">
        <div class="workspace">

            <!-- EXPLORER SIDEBAR -->
            <div class="explorer">
                <div class="explorer-header">📁 Navigation</div>
                <div class="tree-node active"><span class="node-icon">📊</span> Dashboard</div>
                <div class="tree-node"><span class="node-icon">📋</span> Trades</div>
                <div class="tree-node"><span class="node-icon">📕</span> Exits</div>
                <div class="tree-node"><span class="node-icon">💾</span> Fills</div>
                <div class="tree-node"><span class="node-icon">📡</span> Signals</div>
                <div class="tree-node"><span class="node-icon">⚙️</span> Settings</div>
            </div>

            <!-- MAIN CONTENT -->
            <div class="main">
                <div class="page-title">Whale Bot Dashboard</div>
                <div class="page-sub">Automated multi-signal trading · Live from Airtable · Refreshed {payload["refreshed"]}</div>

                <div class="gadget-row">
                    <div class="gadget">
                        <div class="gadget-label">Total P/L</div>
                        <div class="gadget-value">${payload["total_pnl"]:,.2f}</div>
                        <div class="gadget-sub">{payload["n_exits"]} closed trades</div>
                    </div>
                    <div class="gadget">
                        <div class="gadget-label">Win Rate</div>
                        <div class="gadget-value">{payload["win_rate"]:.0f}%</div>
                    </div>
                    <div class="gadget">
                        <div class="gadget-label">Open</div>
                        <div class="gadget-value">{payload["open_trades"]}</div>
                    </div>
                    <div class="gadget">
                        <div class="gadget-label">Fills</div>
                        <div class="gadget-value">{payload["fills_count"]}</div>
                    </div>
                </div>

                <div class="section">📈 Equity Curve</div>
                <div class="chart-panel" id="equity-panel"></div>

                <div class="section">📡 Signal Performance</div>
                <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 14px;">
                    <div class="chart-panel">
                        <div style="font-size:11px;font-weight:600;letter-spacing:1px;color:#2a6a8a;margin-bottom:8px;text-transform:uppercase;">Slippage by Type</div>
                        <div id="slippage-panel"></div>
                    </div>
                    <div class="chart-panel">
                        <div style="font-size:11px;font-weight:600;letter-spacing:1px;color:#2a6a8a;margin-bottom:8px;text-transform:uppercase;">P/L by Symbol</div>
                        <div id="symbol-panel"></div>
                    </div>
                </div>

                <div class="section">📋 Recent Trades</div>
                <div id="trades-panel"></div>

                <div class="section">📕 Recent Exits</div>
                <div id="exits-panel"></div>
            </div>
        </div>
    </div>
</div>

<!-- TASKBAR -->
<div class="taskbar">
    <div class="start-orb-wrapper"><div class="start-orb"></div></div>
    <div class="taskbar-tab active"><span>🐋</span> <span>Whale Bot Dashboard</span></div>
    <div class="taskbar-clock">
        {payload["refreshed"]}<br>
        <span style="font-size:10px;opacity:0.8;">● Bot running</span>
    </div>
</div>

<script>
const DATA = {json.dumps(payload, default=str)};

/* ---------- EQUITY CURVE ---------- */
function renderEquity() {{
    const panel = document.getElementById('equity-panel');
    const pts = DATA.equity;
    if (!pts || pts.length < 2) {{
        panel.innerHTML = '<div class="empty-state">🌊 No closed trades yet. The first data point appears after a trade hits its target or stop.</div>';
        return;
    }}
    const W = Math.max(panel.clientWidth - 28, 300);
    const H = 200;
    const pad = 30;
    const vals = pts.map(p => p.v);
    const minV = Math.min(...vals);
    const maxV = Math.max(...vals);
    const range = maxV - minV || 1;
    const dx = (W - pad * 2) / Math.max(pts.length - 1, 1);
    const points = pts.map((p, i) => {{
        const x = pad + i * dx;
        const y = H - pad - ((p.v - minV) / range) * (H - pad * 2);
        return [x, y];
    }});
    const pathD = points.map((p, i) => (i === 0 ? `M${{p[0]}},${{p[1]}}` : `L${{p[0]}},${{p[1]}}`)).join(' ');
    const areaD = pathD + ` L${{points[points.length-1][0]}},${{H-pad}} L${{points[0][0]}},${{H-pad}} Z`;
    const svg = `
    <svg class="chart-svg" viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none">
        <defs>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#4ec0f0" stop-opacity="0.6"/>
                <stop offset="100%" stop-color="#4ec0f0" stop-opacity="0.05"/>
            </linearGradient>
        </defs>
        <path d="${{areaD}}" fill="url(#lineGrad)"/>
        <path d="${{pathD}}" fill="none" stroke="#1c82c0" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        ${{points.map(p => `<circle cx="${{p[0]}}" cy="${{p[1]}}" r="3.5" fill="#ffffff" stroke="#1c82c0" stroke-width="2"/>`).join('')}}
    </svg>`;
    panel.innerHTML = svg;
}}

/* ---------- SLIPPAGE ---------- */
function renderSlippage() {{
    const panel = document.getElementById('slippage-panel');
    if (!DATA.fills || DATA.fills.length === 0) {{
        panel.innerHTML = '<div class="empty-state" style="padding:14px;font-size:12px;">No fills logged yet.</div>';
        return;
    }}
    const groups = {{}};
    DATA.fills.forEach(f => {{
        const t = f['Order Type'] || 'Other';
        const s = f['Slippage (%)'] || 0;
        if (!groups[t]) groups[t] = {{ sum: 0, count: 0 }};
        groups[t].sum += s;
        groups[t].count += 1;
    }});
    let html = '';
    Object.entries(groups).forEach(([type, g]) => {{
        const avg = (g.sum / g.count).toFixed(4);
        html += `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(180,220,240,0.4);font-size:12px;">
            <span style="font-weight:600;color:#153a52;">${{type}}</span>
            <span style="font-family:Georgia,serif;color:#0a4a6a;">${{avg}}% <span style="color:#2a6a8a;font-size:10px;">(${{g.count}})</span></span>
        </div>`;
    }});
    panel.innerHTML = html;
}}

/* ---------- P/L BY SYMBOL ---------- */
function renderSymbolPnl() {{
    const panel = document.getElementById('symbol-panel');
    const entries = Object.entries(DATA.by_symbol || {{}});
    if (entries.length === 0) {{
        panel.innerHTML = '<div class="empty-state" style="padding:14px;font-size:12px;">No closed trades yet.</div>';
        return;
    }}
    const maxAbs = Math.max(...entries.map(([_, v]) => Math.abs(v)), 1);
    let html = '';
    entries.sort((a, b) => b[1] - a[1]).forEach(([sym, val]) => {{
        const pct = Math.abs(val) / maxAbs * 100;
        const cls = val >= 0 ? '' : 'negative';
        html += `<div class="bar-row">
            <div class="bar-label">${{sym}}</div>
            <div class="bar-track"><div class="bar-fill ${{cls}}" style="width:${{pct}}%"></div></div>
            <div class="bar-value">$${{val.toFixed(2)}}</div>
        </div>`;
    }});
    panel.innerHTML = html;
}}

/* ---------- TABLES ---------- */
function renderTable(containerId, rows, fields, headers, emptyMsg) {{
    const panel = document.getElementById(containerId);
    if (!rows || rows.length === 0) {{
        panel.innerHTML = `<div class="empty-state">${{emptyMsg}}</div>`;
        return;
    }}
    let html = '<table class="glass-table"><thead><tr>';
    headers.forEach(h => html += `<th>${{h}}</th>`);
    html += '</tr></thead><tbody>';
    rows.slice().reverse().forEach(r => {{
        html += '<tr>';
        fields.forEach(f => {{
            let v = r[f];
            if (v === undefined || v === null) v = '—';
            if (typeof v === 'number' && v.toFixed) v = v.toFixed(2);
            html += `<td>${{v}}</td>`;
        }});
        html += '</tr>';
    }});
    html += '</tbody></table>';
    panel.innerHTML = html;
}}

/* ---------- RENDER ---------- */
renderEquity();
renderSlippage();
renderSymbolPnl();
renderTable('trades-panel', DATA.trades,
    ['Timestamp', 'Symbol', 'Qty', 'Price', 'Score', 'Threshold'],
    ['Time', 'Symbol', 'Qty', 'Price', 'Score', 'Threshold'],
    '🌊 No trades logged yet. The bot writes its first entry when a signal fires.');
renderTable('exits-panel', DATA.exits,
    ['Exit Timestamp', 'Symbol', 'Exit Reason', 'PnL Dollars', 'PnL Percent'],
    ['Time', 'Symbol', 'Reason', 'P/L $', 'P/L %'],
    '🌊 No exits yet. This fills in when a trade hits its target or stop-loss.');

window.addEventListener('resize', renderEquity);
</script>

</body>
</html>
"""

# ============================================================
# RENDER
# ============================================================
components.html(HTML, height=2400, scrolling=True)
