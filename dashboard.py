"""
Whale Bot Dashboard v5 — Frutiger Aqua (mobile-first + working nav)
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import numpy as np
import json
import math
from datetime import datetime

st.set_page_config(
    page_title="Whale Bot",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# PARENT-PAGE CSS — force iframe to viewport width on mobile
# ============================================================
st.markdown(
    """
    <style>
    #MainMenu, footer, header { visibility: hidden !important; }
    [data-testid="stAppViewContainer"] {
        padding: 0 !important;
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stVerticalBlock"],
    [data-testid="stVerticalBlockBorderWrapper"],
    .block-container {
        padding: 0 !important;
        max-width: 100vw !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
    }
    iframe[title="streamlit_component"],
    iframe[title="st.components.v1.html"],
    iframe {
        width: 100% !important;
        max-width: 100vw !important;
        min-width: 0 !important;
        display: block !important;
        border: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# SECRETS + FETCH
# ============================================================
AIRTABLE_API_KEY = st.secrets["AIRTABLE_API_KEY"]
BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
TRADES_ID = st.secrets["AIRTABLE_TABLE_ID"]
EXITS_ID = st.secrets["AIRTABLE_EXITS_TABLE_ID"]
FILLS_ID = st.secrets["AIRTABLE_FILLS_TABLE_ID"]

BASE = f"https://api.airtable.com/v0/{BASE_ID}"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

@st.cache_data(ttl=60)
def fetch(table_id):
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
for f in fills:
    if "Slippage (%)" not in f and "Slippage ($)" in f and "Expected Price" in f:
        ep = f.get("Expected Price", 0)
        if ep:
            f["Slippage (%)"] = round((f["Slippage ($)"] / ep) * 100, 4)

total_pnl = sum(e.get("PnL Dollars", 0) for e in exits)
wins = sum(1 for e in exits if e.get("PnL Dollars", 0) > 0)
win_rate = (wins / len(exits) * 100) if exits else 0
open_trades = max(len(trades) - len(exits), 0)

exits_sorted = sorted(exits, key=lambda x: x.get("Exit Timestamp", ""))
cum = 0
equity_points = []
for e in exits_sorted:
    cum += e.get("PnL Dollars", 0)
    equity_points.append({"t": e.get("Exit Timestamp", ""), "v": round(cum, 2)})

by_symbol = {}
for e in exits:
    s = e.get("Symbol", "?")
    by_symbol[s] = by_symbol.get(s, 0) + e.get("PnL Dollars", 0)

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

def clean_for_json(obj):
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
# HTML
# ============================================================
HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<style>
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body {{
    font-family: 'Segoe UI', Tahoma, sans-serif;
    color: #063a52;
    overflow-x: hidden;
    -webkit-text-size-adjust: 100%;
    width: 100%;
    max-width: 100vw;
}}

body {{
    background:
        radial-gradient(ellipse 90% 12% at 50% 0%, rgba(255,255,255,0.85), transparent 70%),
        radial-gradient(circle 200px at 15% 22%, rgba(220,255,255,0.6), transparent 65%),
        radial-gradient(circle 260px at 82% 35%, rgba(200,250,255,0.5), transparent 70%),
        radial-gradient(circle 180px at 35% 55%, rgba(210,255,255,0.4), transparent 70%),
        radial-gradient(circle 240px at 68% 75%, rgba(190,245,255,0.45), transparent 70%),
        radial-gradient(circle 160px at 8% 78%, rgba(200,250,255,0.4), transparent 70%),
        radial-gradient(circle 380px at 100% 0%, rgba(255,252,220,0.55), transparent 60%),
        linear-gradient(180deg,
            #b8ecf5 0%, #8fd8ee 18%, #62c0e0 38%,
            #3aa8d0 58%, #1e8cbc 78%, #0d6e9c 100%);
    background-attachment: fixed;
    min-height: 100vh;
    padding: 10px 10px 68px 10px;
}}

body::before {{
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        radial-gradient(circle at 8% 92%, rgba(255,255,255,0.7) 0px, rgba(255,255,255,0.2) 6px, transparent 10px),
        radial-gradient(circle at 22% 88%, rgba(255,255,255,0.6) 0px, rgba(255,255,255,0.15) 4px, transparent 8px),
        radial-gradient(circle at 38% 94%, rgba(255,255,255,0.75) 0px, rgba(255,255,255,0.2) 8px, transparent 12px),
        radial-gradient(circle at 55% 90%, rgba(255,255,255,0.55) 0px, rgba(255,255,255,0.15) 5px, transparent 9px),
        radial-gradient(circle at 72% 96%, rgba(255,255,255,0.7) 0px, rgba(255,255,255,0.2) 7px, transparent 11px),
        radial-gradient(circle at 88% 92%, rgba(255,255,255,0.65) 0px, rgba(255,255,255,0.15) 5px, transparent 9px);
    background-size: 600px 700px, 500px 600px, 700px 800px, 550px 650px, 620px 720px, 580px 680px;
    pointer-events: none;
    z-index: 0;
    animation: rise 30s linear infinite;
}}
@keyframes rise {{
    from {{ background-position: 0 0, 0 0, 0 0, 0 0, 0 0, 0 0; }}
    to   {{ background-position: 40px -700px, -30px -600px, 50px -800px, -40px -650px, 30px -720px, -25px -680px; }}
}}

/* ---------- WINDOW ---------- */
.aero-window {{
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 1300px;
    margin: 0 auto;
    border-radius: 8px 8px 4px 4px;
    box-shadow:
        0 0 0 1px rgba(0,60,90,0.35),
        0 12px 36px rgba(0,60,90,0.35),
        0 4px 10px rgba(0,60,90,0.25);
    overflow: hidden;
    background: rgba(200, 240, 255, 0.55);
    backdrop-filter: blur(22px) saturate(180%);
    -webkit-backdrop-filter: blur(22px) saturate(180%);
}}

.window-titlebar {{
    background: linear-gradient(180deg,
        #eafcff 0%, #c8ecf8 8%, #9ce0f0 45%, #7ad0e8 47%,
        #5ab8d8 52%, #4aa8c8 92%, #6ac0d8 100%);
    padding: 7px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(0,60,90,0.25);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.95), inset 0 -1px 0 rgba(0,60,90,0.15);
    font-size: 12px;
    font-weight: 600;
    color: #063a52;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9);
    gap: 8px;
}}
.window-titlebar .title {{
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    overflow: hidden;
}}
.window-titlebar .title span:last-child {{
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.window-controls {{ display: flex; gap: 2px; flex-shrink: 0; }}
.win-btn {{
    width: 26px; height: 18px;
    border-radius: 3px;
    border: 1px solid rgba(255,255,255,0.5);
    background: linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.15) 48%, rgba(0,0,0,0.05) 52%, rgba(255,255,255,0.15) 100%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6), inset 0 -1px 0 rgba(0,60,90,0.15);
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 700; color: #063a52;
    padding: 0;
}}
.win-btn.close {{
    background: linear-gradient(180deg, #ff9b7a 0%, #e8603a 45%, #c84028 55%, #a02818 100%);
    color: white; border-color: #8a2828;
}}

.window-body {{
    background: linear-gradient(180deg, rgba(220, 245, 255, 0.72) 0%, rgba(190, 230, 250, 0.6) 100%);
    padding: 14px 14px;
}}

/* ---------- LAYOUT ---------- */
.workspace {{
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 14px;
}}

/* ---------- EXPLORER ---------- */
.explorer {{
    background: linear-gradient(180deg, rgba(255,255,255,0.85) 0%, rgba(230,248,255,0.7) 100%);
    border: 1px solid rgba(120,200,230,0.6);
    border-radius: 6px;
    padding: 8px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,1), 0 3px 8px rgba(0,80,120,0.15);
    height: fit-content;
}}
.explorer-header {{
    font-size: 10px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
    color: #1a6a8a;
    padding: 2px 6px 6px 6px;
    border-bottom: 1px solid rgba(120,200,230,0.4);
    margin-bottom: 6px;
}}
.tree-node {{
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 12.5px;
    color: #063a52;
    cursor: pointer;
    margin-bottom: 2px;
    transition: background 0.15s, outline 0.15s;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
}}
.tree-node:hover {{
    background: linear-gradient(180deg, #e5fbff 0%, #cff2ff 100%);
    outline: 1px solid #99e1ff;
}}
.tree-node.active {{
    background: linear-gradient(180deg, #d5f7ff 0%, #b8ecff 100%);
    outline: 1px solid #6cd0ec;
    font-weight: 600;
}}
.node-icon {{ font-size: 13px; }}

/* ---------- MAIN ---------- */
.main {{ min-width: 0; overflow: hidden; }}
.page-title {{
    font-size: 22px; font-weight: 300;
    color: #063a52;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9), 0 2px 4px rgba(0,80,120,0.15);
    margin-bottom: 3px;
}}
.page-sub {{
    font-size: 12px; color: #1a6a8a;
    text-shadow: 0 1px 0 rgba(255,255,255,0.8);
    margin-bottom: 14px;
}}

/* ---------- GADGETS ---------- */
.gadget-row {{
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 16px;
}}
.gadget {{
    position: relative;
    background: linear-gradient(180deg,
        rgba(255,255,255,0.94) 0%,
        rgba(235,252,255,0.85) 45%,
        rgba(180,235,250,0.78) 100%);
    border: 1px solid rgba(255,255,255,0.98);
    border-radius: 10px;
    padding: 12px 12px 10px 12px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        inset 0 -20px 40px rgba(140,220,240,0.18),
        inset 0 -1px 0 rgba(60,140,180,0.2),
        0 6px 14px rgba(0,80,120,0.22),
        0 14px 32px rgba(0,80,120,0.12);
    overflow: hidden;
}}
.gadget::before {{
    content: '';
    position: absolute; top: 0; left: 0; right: 0;
    height: 48%;
    background: linear-gradient(180deg,
        rgba(255,255,255,0.88) 0%,
        rgba(255,255,255,0.35) 60%,
        rgba(255,255,255,0) 100%);
    border-radius: 10px 10px 50% 50%;
    pointer-events: none;
}}
.gadget-label {{
    position: relative; z-index: 1;
    font-size: 9.5px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1.4px;
    color: #1a6a8a;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9);
    margin-bottom: 4px;
}}
.gadget-value {{
    position: relative; z-index: 1;
    font-family: Georgia, serif;
    font-weight: 700;
    font-size: 26px;
    color: #063e5a;
    text-shadow: 0 1px 0 rgba(255,255,255,1), 0 2px 6px rgba(0,80,120,0.18);
    line-height: 1;
}}
.gadget-sub {{
    position: relative; z-index: 1;
    font-size: 10px; color: #1a6a8a;
    margin-top: 4px;
}}

/* ---------- SECTIONS ---------- */
.section {{
    font-size: 11.5px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1.3px;
    color: #063a52;
    padding-bottom: 5px;
    margin: 16px 0 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.9);
    position: relative;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9);
    scroll-margin-top: 12px;
}}
.section::after {{
    content: '';
    position: absolute;
    bottom: -1px; left: 0;
    width: 50px; height: 2px;
    background: linear-gradient(90deg, #2aa8d0, transparent);
}}

/* ---------- PANELS ---------- */
.chart-panel {{
    background: linear-gradient(180deg, rgba(255,255,255,0.75) 0%, rgba(220,245,255,0.55) 100%);
    border: 1px solid rgba(255,255,255,0.95);
    border-radius: 10px;
    padding: 12px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,1), 0 4px 10px rgba(0,80,120,0.15);
    margin-bottom: 12px;
}}
.chart-svg {{ width: 100%; height: 160px; display: block; }}
.signal-grid {{
    display: grid;
    grid-template-columns: 1fr 2fr;
    gap: 10px;
}}

/* ---------- BAR CHART ---------- */
.bar-row {{
    display: flex; align-items: center;
    gap: 8px; padding: 4px 0; font-size: 12px;
}}
.bar-label {{ width: 52px; font-weight: 600; color: #063a52; font-size: 11px; }}
.bar-track {{
    flex: 1; height: 14px;
    background: linear-gradient(180deg, rgba(220,240,250,0.8), rgba(200,225,240,0.6));
    border-radius: 4px; overflow: hidden;
    box-shadow: inset 0 1px 3px rgba(0,60,90,0.15);
}}
.bar-fill {{
    height: 100%;
    background: linear-gradient(180deg, #7ee4c0 0%, #4ac0a0 50%, #2a9c80 100%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
    border-radius: 4px;
}}
.bar-fill.negative {{
    background: linear-gradient(180deg, #ff9090 0%, #e86060 50%, #c84040 100%);
}}
.bar-value {{
    width: 68px; text-align: right;
    font-family: Georgia, serif; font-weight: 700;
    color: #063a52; font-size: 11.5px;
}}

/* ---------- TABLE ---------- */
.table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; }}
.glass-table {{
    width: 100%; border-collapse: collapse;
    background: rgba(255,255,255,0.55);
    border-radius: 8px; overflow: hidden;
    box-shadow: inset 0 1px 0 rgba(255,255,255,1), 0 3px 10px rgba(0,80,120,0.15);
    font-size: 11.5px;
    min-width: 480px;
}}
.glass-table thead th {{
    background: linear-gradient(180deg, #eafcff 0%, #c8ecf8 48%, #9ce0f0 52%, #7ad0e8 100%);
    color: #063a52; text-align: left;
    padding: 7px 9px;
    font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.7px; font-size: 9.5px;
    text-shadow: 0 1px 0 rgba(255,255,255,0.95);
    border-bottom: 1px solid #5ab8d8;
    white-space: nowrap;
}}
.glass-table tbody td {{
    padding: 6px 9px;
    border-bottom: 1px solid rgba(180,225,240,0.35);
    color: #063a52;
    white-space: nowrap;
}}
.glass-table tbody tr:nth-child(even) td {{ background: rgba(235,250,255,0.4); }}

/* ---------- EMPTY ---------- */
.empty-state {{
    padding: 14px; text-align: center;
    background: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(215,245,255,0.7) 100%);
    border: 1px solid rgba(255,255,255,0.95);
    border-radius: 12px;
    color: #1a6a8a; font-size: 12px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,1), 0 4px 12px rgba(0,80,120,0.15);
}}

/* ---------- TASKBAR ---------- */
.taskbar {{
    position: fixed;
    left: 0; right: 0; bottom: 0;
    height: 40px;
    background: linear-gradient(180deg,
        rgba(20,80,130,0.6) 0%, rgba(10,55,95,0.75) 48%,
        rgba(5,35,70,0.85) 52%, rgba(15,65,105,0.8) 100%);
    backdrop-filter: blur(22px) saturate(180%);
    -webkit-backdrop-filter: blur(22px) saturate(180%);
    border-top: 1px solid rgba(255,255,255,0.35);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.4), 0 -3px 14px rgba(0,30,60,0.4);
    display: flex; align-items: center;
    padding: 0 8px; gap: 6px;
    z-index: 9999;
    font-size: 11px; color: rgba(255,255,255,0.95);
}}
.start-orb-wrapper {{ position: relative; width: 44px; height: 40px; flex-shrink: 0; }}
.start-orb {{
    position: absolute; top: -6px; left: 4px;
    width: 38px; height: 38px;
    border-radius: 50%;
    background: radial-gradient(circle at 50% 22%, #b4f0ff 0%, #4ec8f0 25%, #1c90c8 65%, #0a5088 100%);
    box-shadow:
        inset 0 2px 4px rgba(255,255,255,0.9),
        inset 0 -4px 8px rgba(0,40,80,0.5),
        0 2px 6px rgba(0,0,0,0.4),
        0 0 20px rgba(120,220,255,0.7);
    border: 1px solid rgba(255,255,255,0.5);
}}
.start-orb::before {{
    content: '';
    position: absolute;
    top: 8%; left: 20%; right: 20%; height: 30%;
    background: linear-gradient(180deg, rgba(255,255,255,0.85), rgba(255,255,255,0));
    border-radius: 50%;
}}
.taskbar-tab {{
    padding: 5px 10px; border-radius: 4px;
    background: linear-gradient(180deg,
        rgba(255,255,255,0.4) 0%, rgba(180,230,250,0.3) 48%,
        rgba(120,190,225,0.4) 52%, rgba(90,160,210,0.45) 100%);
    border: 1px solid rgba(255,255,255,0.5);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6), 0 1px 3px rgba(0,0,0,0.3);
    color: #ffffff; font-weight: 600;
    text-shadow: 0 1px 2px rgba(0,30,60,0.6);
    display: flex; align-items: center; gap: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 55vw;
}}
.taskbar-clock {{
    margin-left: auto;
    padding: 3px 8px;
    background: linear-gradient(180deg, rgba(255,255,255,0.25), rgba(180,225,245,0.15));
    border: 1px solid rgba(255,255,255,0.35);
    border-radius: 4px;
    font-size: 10px; color: #ffffff;
    text-shadow: 0 1px 2px rgba(0,30,60,0.6);
    text-align: center; line-height: 1.2;
    white-space: nowrap;
}}

/* ============================================================
   MOBILE — collapse everything into a single column
   ============================================================ */
@media (max-width: 900px) {{
    body {{ padding: 6px 6px 62px 6px; }}
    .window-body {{ padding: 10px 10px; }}
    .window-titlebar {{ font-size: 11px; padding: 6px 8px; }}
    .window-titlebar .title span:last-child {{ font-size: 10.5px; }}
    .win-btn {{ width: 22px; height: 16px; font-size: 9px; }}

    .workspace {{ grid-template-columns: 1fr; gap: 10px; }}

    /* Explorer becomes horizontal tab strip */
    .explorer {{
        display: flex;
        gap: 4px;
        overflow-x: auto;
        padding: 6px;
        border-radius: 8px;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
    }}
    .explorer::-webkit-scrollbar {{ display: none; }}
    .explorer-header {{ display: none; }}
    .tree-node {{
        white-space: nowrap;
        padding: 6px 10px;
        font-size: 11.5px;
        margin-bottom: 0;
        flex-shrink: 0;
    }}

    .page-title {{ font-size: 18px; }}
    .page-sub {{ font-size: 10.5px; margin-bottom: 12px; }}

    .gadget-row {{
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-bottom: 14px;
    }}
    .gadget {{ padding: 10px 10px 8px 10px; }}
    .gadget-value {{ font-size: 22px; }}
    .gadget-label {{ font-size: 8.5px; letter-spacing: 1.2px; }}
    .gadget-sub {{ font-size: 9.5px; }}

    .section {{ font-size: 10.5px; letter-spacing: 1.1px; margin: 14px 0 8px 0; }}

    .signal-grid {{ grid-template-columns: 1fr; gap: 8px; }}
    .chart-svg {{ height: 130px; }}
    .chart-panel {{ padding: 10px; margin-bottom: 10px; }}

    .glass-table {{ font-size: 10.5px; min-width: 420px; }}
    .glass-table thead th {{ padding: 6px 8px; font-size: 9px; }}
    .glass-table tbody td {{ padding: 5px 8px; }}

    .bar-label {{ font-size: 10.5px; width: 48px; }}
    .bar-value {{ font-size: 10.5px; width: 62px; }}
    .bar-track {{ height: 12px; }}
}}

/* Very narrow phones */
@media (max-width: 400px) {{
    .gadget-value {{ font-size: 19px; }}
    .gadget-label {{ font-size: 8px; letter-spacing: 1px; }}
    .page-title {{ font-size: 16px; }}
    .taskbar-tab {{ font-size: 10.5px; padding: 4px 8px; }}
    .taskbar-clock {{ font-size: 9.5px; padding: 3px 6px; }}
    .start-orb {{ width: 32px; height: 32px; }}
    .start-orb-wrapper {{ width: 38px; }}
}}

html {{ scroll-behavior: smooth; }}
</style>
</head>
<body>

<div class="aero-window">
    <div class="window-titlebar">
        <div class="title">
            <span style="font-size:14px">🐋</span>
            <span>Whale Bot Dashboard</span>
        </div>
        <div class="window-controls">
            <button class="win-btn">—</button>
            <button class="win-btn">□</button>
            <button class="win-btn close">✕</button>
        </div>
    </div>

    <div class="window-body">
        <div class="workspace">
            <div class="explorer" id="nav">
                <div class="explorer-header">📁 Navigation</div>
                <div class="tree-node active" data-target="top"><span class="node-icon">📊</span> Dashboard</div>
                <div class="tree-node" data-target="section-equity"><span class="node-icon">📈</span> Equity</div>
                <div class="tree-node" data-target="section-signals"><span class="node-icon">📡</span> Signals</div>
                <div class="tree-node" data-target="section-trades"><span class="node-icon">📋</span> Trades</div>
                <div class="tree-node" data-target="section-exits"><span class="node-icon">📕</span> Exits</div>
            </div>

            <div class="main">
                <div id="top"></div>
                <div class="page-title">Whale Bot Dashboard</div>
                <div class="page-sub">Automated multi-signal trading · Refreshed {payload["refreshed"]}</div>

                <div class="gadget-row">
                    <div class="gadget">
                        <div class="gadget-label">Total P/L</div>
                        <div class="gadget-value">${payload["total_pnl"]:,.2f}</div>
                        <div class="gadget-sub">{payload["n_exits"]} closed</div>
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

                <div class="section" id="section-equity">📈 Equity Curve</div>
                <div class="chart-panel" id="equity-panel"></div>

                <div class="section" id="section-signals">📡 Signal Performance</div>
                <div class="signal-grid">
                    <div class="chart-panel">
                        <div style="font-size:10px;font-weight:600;letter-spacing:1px;color:#1a6a8a;margin-bottom:6px;text-transform:uppercase;">Slippage</div>
                        <div id="slippage-panel"></div>
                    </div>
                    <div class="chart-panel">
                        <div style="font-size:10px;font-weight:600;letter-spacing:1px;color:#1a6a8a;margin-bottom:6px;text-transform:uppercase;">P/L by Symbol</div>
                        <div id="symbol-panel"></div>
                    </div>
                </div>

                <div class="section" id="section-trades">📋 Recent Trades</div>
                <div class="table-wrap" id="trades-panel"></div>

                <div class="section" id="section-exits">📕 Recent Exits</div>
                <div class="table-wrap" id="exits-panel"></div>
            </div>
        </div>
    </div>
</div>

<div class="taskbar">
    <div class="start-orb-wrapper"><div class="start-orb"></div></div>
    <div class="taskbar-tab"><span>🐋</span> <span>Whale Bot</span></div>
    <div class="taskbar-clock">
        {payload["refreshed"]}<br>
        <span style="font-size:9px;opacity:0.8;">● Running</span>
    </div>
</div>

<script>
const DATA = {json.dumps(payload, default=str)};

/* ---------- NAVIGATION ---------- */
document.querySelectorAll('.tree-node').forEach(node => {{
    node.addEventListener('click', () => {{
        const targetId = node.getAttribute('data-target');
        const target = document.getElementById(targetId);
        if (!target) return;

        // Scroll to section
        target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});

        // Update active state
        document.querySelectorAll('.tree-node').forEach(n => n.classList.remove('active'));
        node.classList.add('active');
    }});
}});

/* ---------- EQUITY ---------- */
function renderEquity() {{
    const panel = document.getElementById('equity-panel');
    const pts = DATA.equity;
    if (!pts || pts.length < 2) {{
        panel.innerHTML = '<div class="empty-state">🌊 No closed trades yet. First data point appears after a trade hits its target or stop.</div>';
        return;
    }}
    const W = Math.max(panel.clientWidth - 20, 260);
    const H = 160;
    const pad = 24;
    const vals = pts.map(p => p.v);
    const minV = Math.min(...vals), maxV = Math.max(...vals);
    const range = maxV - minV || 1;
    const dx = (W - pad * 2) / Math.max(pts.length - 1, 1);
    const points = pts.map((p, i) => [
        pad + i * dx,
        H - pad - ((p.v - minV) / range) * (H - pad * 2)
    ]);
    const pathD = points.map((p, i) => (i === 0 ? `M${{p[0]}},${{p[1]}}` : `L${{p[0]}},${{p[1]}}`)).join(' ');
    const areaD = pathD + ` L${{points[points.length-1][0]}},${{H-pad}} L${{points[0][0]}},${{H-pad}} Z`;
    panel.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none">
        <defs>
            <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#4ed8f0" stop-opacity="0.6"/>
                <stop offset="100%" stop-color="#4ed8f0" stop-opacity="0.05"/>
            </linearGradient>
        </defs>
        <path d="${{areaD}}" fill="url(#lg)"/>
        <path d="${{pathD}}" fill="none" stroke="#1c90c8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        ${{points.map(p => `<circle cx="${{p[0]}}" cy="${{p[1]}}" r="3" fill="#fff" stroke="#1c90c8" stroke-width="2"/>`).join('')}}
    </svg>`;
}}

/* ---------- SLIPPAGE ---------- */
function renderSlippage() {{
    const panel = document.getElementById('slippage-panel');
    if (!DATA.fills || DATA.fills.length === 0) {{
        panel.innerHTML = '<div class="empty-state" style="padding:10px;font-size:11px;">No fills yet.</div>';
        return;
    }}
    const groups = {{}};
    DATA.fills.forEach(f => {{
        const t = f['Order Type'] || 'Other';
        const s = f['Slippage (%)'] || 0;
        if (!groups[t]) groups[t] = {{ sum: 0, count: 0 }};
        groups[t].sum += s; groups[t].count += 1;
    }});
    let html = '';
    Object.entries(groups).forEach(([type, g]) => {{
        const avg = (g.sum / g.count).toFixed(4);
        html += `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(180,225,240,0.4);font-size:11px;">
            <span style="font-weight:600;color:#063a52;">${{type}}</span>
            <span style="font-family:Georgia,serif;color:#063e5a;">${{avg}}% <span style="color:#1a6a8a;font-size:9.5px;">(${{g.count}})</span></span>
        </div>`;
    }});
    panel.innerHTML = html;
}}

/* ---------- SYMBOL P/L ---------- */
function renderSymbolPnl() {{
    const panel = document.getElementById('symbol-panel');
    const entries = Object.entries(DATA.by_symbol || {{}});
    if (entries.length === 0) {{
        panel.innerHTML = '<div class="empty-state" style="padding:10px;font-size:11px;">No closed trades yet.</div>';
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

renderEquity();
renderSlippage();
renderSymbolPnl();
renderTable('trades-panel', DATA.trades,
    ['Timestamp', 'Symbol', 'Qty', 'Price', 'Score', 'Threshold'],
    ['Time', 'Symbol', 'Qty', 'Price', 'Score', 'Thr'],
    '🌊 No trades logged yet.');
renderTable('exits-panel', DATA.exits,
    ['Exit Timestamp', 'Symbol', 'Exit Reason', 'PnL Dollars', 'PnL Percent'],
    ['Time', 'Symbol', 'Reason', 'P/L $', 'P/L %'],
    '🌊 No exits yet.');

window.addEventListener('resize', renderEquity);
</script>

</body>
</html>
"""

components.html(HTML, height=1400, scrolling=True)
