"""
Whale Bot Dashboard v7 — Live Trading + Research Lab tabs.
Research tab styled with early-2000s magical aesthetic.
"""

import streamlit as st
import streamlit.components.v1 as components
import requests, pandas as pd, numpy as np, json, math
from datetime import datetime

st.set_page_config(
    page_title="Whale Bot",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# PARENT PAGE CSS
# ============================================================
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding: 0 !important; max-width: 100vw !important; }
iframe { width: 100% !important; max-width: 100vw !important; display: block !important; border: none !important; }
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    gap: 8px !important;
    padding: 8px 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: linear-gradient(180deg, #eafcff 0%, #c8ecf8 48%, #9ce0f0 52%, #7ad0e8 100%) !important;
    border: 1px solid #5ab8d8 !important;
    border-radius: 8px 8px 0 0 !important;
    color: #063a52 !important;
    font-weight: 600 !important;
    padding: 8px 20px !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, #ffffff 0%, #d8f0ff 100%) !important;
    box-shadow: 0 -2px 10px rgba(100,180,220,0.5) !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# SECRETS
# ============================================================
AIRTABLE_API_KEY = st.secrets["AIRTABLE_API_KEY"]
BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
TRADES_ID = st.secrets["AIRTABLE_TABLE_ID"]
EXITS_ID = st.secrets["AIRTABLE_EXITS_TABLE_ID"]
FILLS_ID = st.secrets["AIRTABLE_FILLS_TABLE_ID"]
RUNS_ID = st.secrets.get("AIRTABLE_RUNS_TABLE_ID", "")
SIGNALS_ID = st.secrets.get("AIRTABLE_SIGNALS_TABLE_ID", "")
ASTRO_ID = st.secrets.get("AIRTABLE_ASTRO_TABLE_ID", "")
REFLEXIVE_ID = st.secrets.get("AIRTABLE_REFLEXIVE_TABLE_ID", "")
MAB_ID = st.secrets.get("AIRTABLE_MAB_TABLE_ID", "")

BASE = f"https://api.airtable.com/v0/{BASE_ID}"
H = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

@st.cache_data(ttl=60)
def fetch(table_id):
    if not table_id: return []
    out, params = [], {}
    while True:
        r = requests.get(f"{BASE}/{table_id}", headers=H, params=params, timeout=30)
        d = r.json()
        out.extend(d.get("records", []))
        if not d.get("offset"): break
        params["offset"] = d["offset"]
    return [rec["fields"] for rec in out]

def clean_for_json(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj): return 0
        return obj
    if isinstance(obj, dict): return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list): return [clean_for_json(x) for x in obj]
    return obj

# ============================================================
# TABS
# ============================================================
tab_live, tab_research = st.tabs(["📊 Live Trading", "✨ Research Lab"])

# ============================================================
# TAB 1: LIVE TRADING (existing aesthetic)
# ============================================================
with tab_live:
    try:
        trades = fetch(TRADES_ID)
        exits = fetch(EXITS_ID)
        fills = fetch(FILLS_ID)
        runs = fetch(RUNS_ID) if RUNS_ID else []
        signals = fetch(SIGNALS_ID) if SIGNALS_ID else []
    except Exception as e:
        st.error(f"Airtable: {e}"); st.stop()

    for f in fills:
        if "Slippage (%)" not in f and "Slippage ($)" in f and "Expected Price" in f:
            ep = f.get("Expected Price", 0)
            if ep: f["Slippage (%)"] = round((f["Slippage ($)"]/ep)*100, 4)

    total_pnl = sum(e.get("PnL Dollars", 0) for e in exits)
    wins = sum(1 for e in exits if e.get("PnL Dollars", 0) > 0)
    win_rate = (wins/len(exits)*100) if exits else 0
    open_trades = max(len(trades) - len(exits), 0)

    exits_sorted = sorted(exits, key=lambda x: x.get("Exit Timestamp", ""))
    cum = 0; equity_points = []
    for e in exits_sorted:
        cum += e.get("PnL Dollars", 0)
        equity_points.append({"t": e.get("Exit Timestamp", ""), "v": round(cum, 2)})

    by_symbol = {}
    for e in exits:
        s = e.get("Symbol", "?"); by_symbol[s] = by_symbol.get(s, 0) + e.get("PnL Dollars", 0)

    sample_size = len(exits)
    sample_pct = min(sample_size/90*100, 100)

    signal_fires = {"regime":0,"rsi":0,"sma":0,"sentiment":0,"congress":0,"insider":0,"pead":0,"flow":0}
    for s in signals:
        for k in signal_fires:
            if s.get(k.capitalize()) or s.get(k): signal_fires[k] += 1

    def rolling_win_rate(seq, window=10):
        if len(seq) < 2: return []
        out = []
        for i in range(len(seq)):
            start = max(0, i - window + 1)
            sub = seq[start:i+1]
            w = sum(1 for x in sub if x.get("PnL Dollars", 0) > 0)
            out.append({"t": sub[-1].get("Exit Timestamp",""), "v": round(w/len(sub)*100, 1)})
        return out

    rwr = rolling_win_rate(exits_sorted)

    live_payload = clean_for_json({
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "open_trades": open_trades,
        "fills_count": len(fills),
        "trades": trades[-30:],
        "exits": exits[-30:],
        "fills": fills[-20:],
        "runs": runs[-50:],
        "equity": equity_points,
        "by_symbol": by_symbol,
        "refreshed": datetime.now().strftime("%I:%M %p"),
        "n_trades": len(trades),
        "n_exits": len(exits),
        "n_fills": len(fills),
        "sample_size": sample_size,
        "sample_pct": round(sample_pct, 1),
        "signal_fires": signal_fires,
        "rolling_wr": rwr[-30:],
    })

    LIVE_HTML = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ font-family:'Segoe UI',Tahoma,sans-serif; color:#063a52; overflow-x:hidden; width:100%; max-width:100vw; }}
body {{ background:
    radial-gradient(ellipse 90% 12% at 50% 0%, rgba(255,255,255,0.85), transparent 70%),
    radial-gradient(circle 200px at 15% 22%, rgba(220,255,255,0.6), transparent 65%),
    radial-gradient(circle 260px at 82% 35%, rgba(200,250,255,0.5), transparent 70%),
    radial-gradient(circle 380px at 100% 0%, rgba(255,252,220,0.55), transparent 60%),
    linear-gradient(180deg,#b8ecf5 0%,#8fd8ee 18%,#62c0e0 38%,#3aa8d0 58%,#1e8cbc 78%,#0d6e9c 100%);
    background-attachment:fixed; min-height:100vh; padding:10px 10px 68px 10px; }}
.aero-window {{ position:relative; width:100%; max-width:1300px; margin:0 auto; border-radius:8px 8px 4px 4px; overflow:hidden;
    background:rgba(200,240,255,0.55);
    box-shadow:0 0 0 1px rgba(0,60,90,0.35),0 12px 36px rgba(0,60,90,0.35),0 4px 10px rgba(0,60,90,0.25);
    backdrop-filter:blur(22px) saturate(180%); -webkit-backdrop-filter:blur(22px) saturate(180%); }}
.window-titlebar {{ background:linear-gradient(180deg,#eafcff 0%,#c8ecf8 8%,#9ce0f0 45%,#7ad0e8 47%,#5ab8d8 52%,#4aa8c8 92%,#6ac0d8 100%);
    padding:7px 10px; display:flex; align-items:center; justify-content:space-between;
    border-bottom:1px solid rgba(0,60,90,0.25);
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.95),inset 0 -1px 0 rgba(0,60,90,0.15);
    font-size:12px; font-weight:600; color:#063a52; text-shadow:0 1px 0 rgba(255,255,255,0.9); }}
.window-body {{ background:linear-gradient(180deg,rgba(220,245,255,0.72) 0%,rgba(190,230,250,0.6) 100%); padding:14px; }}
.gadget-row {{ display:grid; grid-template-columns:2fr 1fr 1fr 1fr; gap:10px; margin-bottom:14px; }}
.gadget {{ position:relative; background:linear-gradient(180deg,rgba(255,255,255,0.94) 0%,rgba(235,252,255,0.85) 45%,rgba(180,235,250,0.78) 100%);
    border:1px solid rgba(255,255,255,0.98); border-radius:10px; padding:12px 12px 10px 12px; overflow:hidden;
    box-shadow:inset 0 1px 0 rgba(255,255,255,1),inset 0 -20px 40px rgba(140,220,240,0.18),inset 0 -1px 0 rgba(60,140,180,0.2),0 6px 14px rgba(0,80,120,0.22),0 14px 32px rgba(0,80,120,0.12); }}
.gadget::before {{ content:''; position:absolute; top:0; left:0; right:0; height:48%;
    background:linear-gradient(180deg,rgba(255,255,255,0.88) 0%,rgba(255,255,255,0.35) 60%,rgba(255,255,255,0) 100%);
    border-radius:10px 10px 50% 50%; pointer-events:none; }}
.gadget-label {{ position:relative; z-index:1; font-size:9.5px; font-weight:600; text-transform:uppercase; letter-spacing:1.4px; color:#1a6a8a; margin-bottom:4px; }}
.gadget-value {{ position:relative; z-index:1; font-family:Georgia,serif; font-weight:700; font-size:26px; color:#063e5a;
    text-shadow:0 1px 0 rgba(255,255,255,1),0 2px 6px rgba(0,80,120,0.18); line-height:1; }}
.section {{ font-size:11.5px; font-weight:600; text-transform:uppercase; letter-spacing:1.3px; color:#063a52;
    padding-bottom:5px; margin:16px 0 10px 0; border-bottom:1px solid rgba(255,255,255,0.9); }}
.chart-panel {{ background:linear-gradient(180deg,rgba(255,255,255,0.75) 0%,rgba(220,245,255,0.55) 100%);
    border:1px solid rgba(255,255,255,0.95); border-radius:10px; padding:12px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,1),0 4px 10px rgba(0,80,120,0.15); margin-bottom:12px; }}
.chart-svg {{ width:100%; height:160px; display:block; }}
.progress-wrap {{ background:linear-gradient(180deg,rgba(220,240,250,0.8),rgba(200,225,240,0.6)); border-radius:10px; height:22px; overflow:hidden; position:relative; }}
.progress-fill {{ height:100%; background:linear-gradient(180deg,#7ee4c0 0%,#4ac0a0 50%,#2a9c80 100%); border-radius:10px; }}
.progress-label {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:600; color:#063e5a; }}
.bar-row {{ display:flex; align-items:center; gap:8px; padding:4px 0; font-size:12px; }}
.bar-label {{ width:52px; font-weight:600; color:#063a52; font-size:11px; }}
.bar-track {{ flex:1; height:14px; background:linear-gradient(180deg,rgba(220,240,250,0.8),rgba(200,225,240,0.6)); border-radius:4px; overflow:hidden; }}
.bar-fill {{ height:100%; background:linear-gradient(180deg,#7ee4c0 0%,#4ac0a0 50%,#2a9c80 100%); border-radius:4px; }}
.bar-fill.negative {{ background:linear-gradient(180deg,#ff9090 0%,#e86060 50%,#c84040 100%); }}
.bar-fill.signal {{ background:linear-gradient(180deg,#a4e4ff 0%,#5ac0e8 50%,#2a90c0 100%); }}
.bar-value {{ width:68px; text-align:right; font-family:Georgia,serif; font-weight:700; color:#063a52; font-size:11.5px; }}
.table-wrap {{ overflow-x:auto; border-radius:8px; }}
.glass-table {{ width:100%; border-collapse:collapse; background:rgba(255,255,255,0.55); border-radius:8px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,1),0 3px 10px rgba(0,80,120,0.15); font-size:11.5px; min-width:440px; }}
.glass-table thead th {{ background:linear-gradient(180deg,#eafcff 0%,#c8ecf8 48%,#9ce0f0 52%,#7ad0e8 100%);
    color:#063a52; text-align:left; padding:7px 9px; font-weight:600; text-transform:uppercase; letter-spacing:0.7px; font-size:9.5px;
    border-bottom:1px solid #5ab8d8; }}
.glass-table tbody td {{ padding:6px 9px; border-bottom:1px solid rgba(180,225,240,0.35); color:#063a52; white-space:nowrap; }}
.glass-table tbody tr:nth-child(even) td {{ background:rgba(235,250,255,0.4); }}
.empty-state {{ padding:14px; text-align:center; background:linear-gradient(180deg,rgba(255,255,255,0.9) 0%,rgba(215,245,255,0.7) 100%);
    border:1px solid rgba(255,255,255,0.95); border-radius:12px; color:#1a6a8a; font-size:12px; }}
@media (max-width:900px) {{
    body {{ padding:6px 6px 62px 6px; }}
    .window-body {{ padding:10px; }}
    .gadget-row {{ grid-template-columns:1fr 1fr; gap:8px; }}
    .gadget-value {{ font-size:22px; }}
    .glass-table {{ font-size:10.5px; min-width:380px; }}
}}
</style></head>
<body>
<div class="aero-window">
  <div class="window-titlebar">
    <span>🐋 Whale Bot Dashboard</span>
    <span>Refreshed {live_payload["refreshed"]}</span>
  </div>
  <div class="window-body">
    <div class="gadget-row">
      <div class="gadget">
        <div class="gadget-label">Total P/L</div>
        <div class="gadget-value">${live_payload["total_pnl"]:,.2f}</div>
      </div>
      <div class="gadget">
        <div class="gadget-label">Win Rate</div>
        <div class="gadget-value">{live_payload["win_rate"]:.0f}%</div>
      </div>
      <div class="gadget">
        <div class="gadget-label">Open</div>
        <div class="gadget-value">{live_payload["open_trades"]}</div>
      </div>
      <div class="gadget">
        <div class="gadget-label">Fills</div>
        <div class="gadget-value">{live_payload["fills_count"]}</div>
      </div>
    </div>

    <div class="section">📈 Sample Size Progress</div>
    <div class="chart-panel">
      <div class="progress-wrap">
        <div class="progress-fill" style="width:{live_payload["sample_pct"]}%"></div>
        <div class="progress-label">{live_payload["sample_size"]} / 90 trades</div>
      </div>
    </div>

    <div class="section">💹 Equity Curve</div>
    <div class="chart-panel" id="equity-panel"></div>

    <div class="section">📋 Recent Trades</div>
    <div class="table-wrap" id="trades-panel"></div>

    <div class="section">📕 Recent Exits</div>
    <div class="table-wrap" id="exits-panel"></div>
  </div>
</div>
<script>
const DATA = {json.dumps(live_payload, default=str)};
function lineChart(elId, pts, color) {{
    const panel = document.getElementById(elId);
    if (!pts || pts.length < 2) {{ panel.innerHTML = '<div class="empty-state">Not enough data yet.</div>'; return; }}
    const W = Math.max(panel.clientWidth - 20, 260), H = 160, pad = 24;
    const vals = pts.map(p => p.v); const minV = Math.min(...vals), maxV = Math.max(...vals);
    const range = maxV - minV || 1;
    const dx = (W - pad*2) / Math.max(pts.length-1, 1);
    const points = pts.map((p, i) => [pad + i*dx, H - pad - ((p.v - minV)/range)*(H - pad*2)]);
    const pathD = points.map((p, i) => (i===0 ? `M${{p[0]}},${{p[1]}}` : `L${{p[0]}},${{p[1]}}`)).join(' ');
    const areaD = pathD + ` L${{points[points.length-1][0]}},${{H-pad}} L${{points[0][0]}},${{H-pad}} Z`;
    panel.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none">
        <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${{color}}" stop-opacity="0.6"/><stop offset="100%" stop-color="${{color}}" stop-opacity="0.05"/></linearGradient></defs>
        <path d="${{areaD}}" fill="url(#g)"/><path d="${{pathD}}" fill="none" stroke="${{color}}" stroke-width="2.5"/>
        ${{points.map(p => `<circle cx="${{p[0]}}" cy="${{p[1]}}" r="3" fill="#fff" stroke="${{color}}" stroke-width="2"/>`).join('')}}
    </svg>`;
}}
lineChart('equity-panel', DATA.equity, '#1c90c8');
function renderTable(id, rows, fields, headers, emptyMsg) {{
    const panel = document.getElementById(id);
    if (!rows || rows.length === 0) {{ panel.innerHTML = `<div class="empty-state">${{emptyMsg}}</div>`; return; }}
    let html = '<table class="glass-table"><thead><tr>';
    headers.forEach(h => html += `<th>${{h}}</th>`); html += '</tr></thead><tbody>';
    rows.slice().reverse().forEach(r => {{
        html += '<tr>';
        fields.forEach(f => {{ let v = r[f]; if (v === undefined || v === null) v = '—'; if (typeof v === 'number' && v.toFixed) v = v.toFixed(2); html += `<td>${{v}}</td>`; }});
        html += '</tr>';
    }});
    html += '</tbody></table>'; panel.innerHTML = html;
}}
renderTable('trades-panel', DATA.trades,
    ['Timestamp','Symbol','Qty','Price','Score','Threshold'],
    ['Time','Symbol','Qty','Price','Score','Thr'], '🌊 No trades yet.');
renderTable('exits-panel', DATA.exits,
    ['Exit Timestamp','Symbol','Exit Reason','PnL Dollars','Source'],
    ['Time','Symbol','Reason','P/L $','Source'], '🌊 No exits yet.');
</script>
</body></html>"""
    components.html(LIVE_HTML, height=1600, scrolling=True)


# ============================================================
# TAB 2: RESEARCH LAB (magical early 2000s)
# ============================================================
with tab_research:
    try:
        astro_rows = fetch(ASTRO_ID) if ASTRO_ID else []
        reflexive_rows = fetch(REFLEXIVE_ID) if REFLEXIVE_ID else []
        mab_rows = fetch(MAB_ID) if MAB_ID else []
    except Exception as e:
        st.error(f"Research data fetch failed: {e}")
        astro_rows, reflexive_rows, mab_rows = [], [], []

    current_astro = {}
    if astro_rows:
        nyse = sorted([a for a in astro_rows if a.get('Reference') == 'NYSE'], key=lambda x: x.get('Timestamp',''))
        if nyse: current_astro = nyse[-1]

    current_reflexive = {}
    if reflexive_rows:
        srtd = sorted(reflexive_rows, key=lambda x: x.get('Timestamp',''))
        current_reflexive = srtd[-1]

    mab_latest = {}
    if mab_rows:
        for r in sorted(mab_rows, key=lambda x: x.get('Timestamp','')):
            mab_latest[r.get('Signal')] = float(r.get('Weight', 0))

    astro_payload = clean_for_json({
        "sun_sign": current_astro.get('Sun_Sign', '—'),
        "sun_degree": current_astro.get('Sun_Degree', 0),
        "moon_sign": current_astro.get('Moon_Sign', '—'),
        "moon_phase": current_astro.get('Moon_Phase', '—'),
        "moon_illum": current_astro.get('Moon_Illumination', 0),
        "mercury_rx": current_astro.get('Mercury_Retrograde', False),
        "venus_rx": current_astro.get('Venus_Retrograde', False),
        "mars_rx": current_astro.get('Mars_Retrograde', False),
        "jupiter_sign": current_astro.get('Jupiter_Sign', '—'),
        "jupiter_deg": current_astro.get('Jupiter_Degree', 0),
        "saturn_sign": current_astro.get('Saturn_Sign', '—'),
        "saturn_deg": current_astro.get('Saturn_Degree', 0),
        "nakshatra": current_astro.get('Nakshatra', '—'),
        "dasha": current_astro.get('Current_Dasha', '—'),
        "astro_score": current_astro.get('Astro_Score', 0),
        "house_2": current_astro.get('Vedic_House_2', '—'),
        "house_5": current_astro.get('Vedic_House_5', '—'),
        "house_8": current_astro.get('Vedic_House_8', '—'),
        "house_11": current_astro.get('Vedic_House_11', '—'),
    })

    reflex_payload = clean_for_json({
        "intensity": current_reflexive.get('Reflexive_Intensity', 0),
        "herding": current_reflexive.get('Herding_Flag', False),
        "vix_spot": current_reflexive.get('VIX_Spot', 0),
        "vix_structure": current_reflexive.get('VIX_Term_Structure', '—'),
        "cross_corr": current_reflexive.get('Cross_Ticker_Correlation', 0),
        "spy_vix_corr": current_reflexive.get('SPY_VIX_Correlation', 0),
        "volume_z": current_reflexive.get('Volume_Z_Score', 0),
        "notes": current_reflexive.get('Notes', ''),
    })

    # Astro score bar (0-100 = map -10..+10 to 0..100)
    astro_display = float(astro_payload["astro_score"])
    astro_pct = max(0, min(100, (astro_display + 10) * 5))

    research_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
@import url('https://fonts.googleapis.com/css2?family=Trebuchet+MS&display=swap');
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ font-family: 'Trebuchet MS', sans-serif; overflow-x: hidden; }}

body.research-body {{
    cursor: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="none" stroke="%23a8e4ff" stroke-width="2" opacity="0.9"/><circle cx="16" cy="16" r="6" fill="%23ffffff" opacity="0.7"/><circle cx="13" cy="13" r="2" fill="%23ffffff" opacity="0.9"/></svg>') 16 16, auto;
    background:
        radial-gradient(circle at 20% 30%, rgba(168,228,255,0.6), transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(140,200,255,0.5), transparent 45%),
        radial-gradient(circle at 50% 50%, rgba(200,240,255,0.3), transparent 60%),
        linear-gradient(135deg, #0a1e3a 0%, #1a3a5c 25%, #2a5a8a 50%, #1a4a7a 75%, #0a2a4a 100%);
    background-attachment: fixed;
    min-height: 100vh;
    padding: 20px;
    position: relative;
}}

body.research-body::before {{
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        radial-gradient(circle at 10% 20%, rgba(255,255,255,0.9) 1px, transparent 2px),
        radial-gradient(circle at 30% 60%, rgba(200,240,255,0.8) 1.5px, transparent 3px),
        radial-gradient(circle at 60% 15%, rgba(255,255,255,0.7) 1px, transparent 2px),
        radial-gradient(circle at 85% 45%, rgba(180,230,255,0.9) 2px, transparent 3px),
        radial-gradient(circle at 45% 85%, rgba(255,255,255,0.6) 1px, transparent 2px),
        radial-gradient(circle at 95% 90%, rgba(200,240,255,0.8) 1.5px, transparent 3px);
    background-size: 400px 400px, 500px 500px, 350px 350px, 450px 450px, 380px 380px, 520px 520px;
    animation: sparkleFloat 20s linear infinite;
    pointer-events: none;
    z-index: 0;
}}
@keyframes sparkleFloat {{
    0%   {{ background-position: 0 0, 0 0, 0 0, 0 0, 0 0, 0 0; }}
    100% {{ background-position: 0 -400px, 0 -500px, 0 -350px, 0 -450px, 0 -380px, 0 -520px; }}
}}

.research-title {{
    font-size: 2.4rem;
    font-weight: bold;
    color: #ffffff;
    text-align: center;
    text-shadow: 0 0 10px #a8e4ff, 0 0 20px #6cc8ff, 0 0 30px #4ab8f0, 0 2px 0 #0a2a4a;
    letter-spacing: 2px;
    padding: 20px;
    animation: titleGlow 3s ease-in-out infinite;
    position: relative;
    z-index: 1;
}}
@keyframes titleGlow {{
    0%, 100% {{ text-shadow: 0 0 10px #a8e4ff, 0 0 20px #6cc8ff, 0 0 30px #4ab8f0, 0 2px 0 #0a2a4a; }}
    50%      {{ text-shadow: 0 0 20px #d0f0ff, 0 0 40px #a8e4ff, 0 0 60px #6cc8ff, 0 2px 0 #0a2a4a; }}
}}

.research-panel {{
    background: linear-gradient(180deg, rgba(255,255,255,0.15) 0%, rgba(200,230,255,0.08) 50%, rgba(150,200,255,0.12) 100%);
    backdrop-filter: blur(12px) saturate(180%);
    border: 1px solid rgba(200,230,255,0.4);
    border-radius: 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.4), inset 0 -1px 0 rgba(100,180,255,0.2), 0 8px 24px rgba(0,20,60,0.5), 0 0 40px rgba(100,180,255,0.3);
    padding: 18px 20px;
    margin-bottom: 16px;
    position: relative;
    z-index: 1;
    color: #e8f4ff;
}}
.research-panel h3 {{
    color: #a8e4ff;
    font-size: 1.1rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    text-shadow: 0 0 8px #4ab8f0;
    border-bottom: 1px solid rgba(168,228,255,0.3);
    padding-bottom: 8px;
    margin-bottom: 14px;
}}
.astro-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; font-size: 0.88rem; }}
.astro-grid div {{ padding: 4px 0; }}
.astro-grid strong {{ color: #a8e4ff; }}
.astro-orb {{
    display: inline-block;
    background: radial-gradient(circle at 50% 30%, rgba(168,228,255,0.5), rgba(60,120,180,0.35));
    border: 2px solid rgba(200,240,255,0.7);
    border-radius: 50%;
    width: 130px; height: 130px;
    line-height: 130px;
    text-align: center;
    font-size: 2rem;
    font-weight: bold;
    color: #ffffff;
    text-shadow: 0 0 15px #a8e4ff;
    box-shadow: inset 0 2px 12px rgba(255,255,255,0.4), 0 0 30px rgba(168,228,255,0.7);
    animation: orbPulse 4s ease-in-out infinite;
    margin: 12px auto;
}}
@keyframes orbPulse {{
    0%, 100% {{ transform: scale(1); box-shadow: inset 0 2px 12px rgba(255,255,255,0.4), 0 0 30px rgba(168,228,255,0.7); }}
    50%      {{ transform: scale(1.06); box-shadow: inset 0 2px 12px rgba(255,255,255,0.6), 0 0 50px rgba(168,228,255,1); }}
}}
.bar-container {{ margin: 10px 0; }}
.bar-label-row {{ display: flex; justify-content: space-between; font-size: 0.9rem; margin-bottom: 4px; }}
.bar-track {{ height: 22px; background: rgba(20,50,90,0.5); border-radius: 11px; overflow: hidden; position: relative; box-shadow: inset 0 2px 4px rgba(0,0,0,0.3); }}
.bar-fill {{
    height: 100%;
    background: linear-gradient(90deg, #a8e4ff 0%, #6cc8ff 50%, #4ab8f0 100%);
    border-radius: 11px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6), 0 0 14px rgba(168,228,255,0.7);
    position: relative;
    overflow: hidden;
}}
.bar-fill::after {{
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.6) 50%, transparent 100%);
    animation: shimmer 3s linear infinite;
}}
@keyframes shimmer {{ 0% {{ transform: translateX(-100%); }} 100% {{ transform: translateX(100%); }} }}
.reflexive-number {{
    font-size: 3rem;
    text-align: center;
    color: #a8e4ff;
    text-shadow: 0 0 20px #4ab8f0, 0 0 40px #2a88d0;
    animation: titleGlow 2s ease-in-out infinite;
}}
.screensaver {{
    text-align: center;
    padding: 20px;
    position: relative;
    height: 200px;
}}
.ring {{
    display: inline-block;
    width: 100px; height: 100px;
    border: 3px dashed rgba(168,228,255,0.5);
    border-radius: 50%;
    animation: rotate 20s linear infinite;
    position: absolute;
    top: 50%; left: 50%;
    margin-left: -50px; margin-top: -50px;
}}
.ring:nth-child(2) {{ animation-delay: -7s; width: 130px; height: 130px; margin-left: -65px; margin-top: -65px; }}
.ring:nth-child(3) {{ animation-delay: -14s; width: 160px; height: 160px; margin-left: -80px; margin-top: -80px; }}
@keyframes rotate {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
</style></head>
<body class="research-body">
<div class="research-title">✨ Astrological Research Lab ✨</div>

<div class="research-panel">
    <h3>🌙 Current Planetary State</h3>
    <div class="astro-grid">
        <div><strong>Sun:</strong> {astro_payload["sun_sign"]} {astro_payload["sun_degree"]:.1f}°</div>
        <div><strong>Moon:</strong> {astro_payload["moon_sign"]}</div>
        <div><strong>Moon Phase:</strong> {astro_payload["moon_phase"]}</div>
        <div><strong>Illumination:</strong> {astro_payload["moon_illum"]:.1f}%</div>
        <div><strong>Mercury:</strong> {'☿ Retrograde' if astro_payload["mercury_rx"] else '☿ Direct'}</div>
        <div><strong>Venus:</strong> {'♀ Retrograde' if astro_payload["venus_rx"] else '♀ Direct'}</div>
        <div><strong>Mars:</strong> {'♂ Retrograde' if astro_payload["mars_rx"] else '♂ Direct'}</div>
        <div><strong>Jupiter:</strong> {astro_payload["jupiter_sign"]} {astro_payload["jupiter_deg"]:.1f}°</div>
        <div><strong>Saturn:</strong> {astro_payload["saturn_sign"]} {astro_payload["saturn_deg"]:.1f}°</div>
        <div><strong>Nakshatra:</strong> {astro_payload["nakshatra"]}</div>
        <div><strong>Dasha:</strong> {astro_payload["dasha"]}</div>
    </div>
</div>

<div class="research-panel">
    <h3>🔮 Composite Astro Score</h3>
    <div style="text-align:center;">
        <div class="astro-orb">{astro_payload["astro_score"]:+.1f}</div>
        <div style="opacity:0.8; font-size:0.85rem; margin-top:8px;">-10 (bearish) → +10 (bullish)</div>
    </div>
</div>

<div class="research-panel">
    <h3>🏛️ Vedic Money Houses</h3>
    <div class="astro-grid">
        <div><strong>2nd (Wealth):</strong> {astro_payload["house_2"]}</div>
        <div><strong>5th (Speculation):</strong> {astro_payload["house_5"]}</div>
        <div><strong>8th (Leverage):</strong> {astro_payload["house_8"]}</div>
        <div><strong>11th (Gains):</strong> {astro_payload["house_11"]}</div>
    </div>
</div>

<div class="research-panel">
    <h3>🌀 Reflexive Intensity</h3>
    <div class="reflexive-number">{reflex_payload["intensity"]:.1f} / 10</div>
    <div style="text-align:center; margin: 12px 0; font-size: 0.95rem;">
        {'⚠️ HERDING DETECTED' if reflex_payload["herding"] else '✅ Markets operating normally'}
    </div>
    <div class="astro-grid" style="margin-top:12px;">
        <div><strong>VIX:</strong> {reflex_payload["vix_spot"]:.2f} ({reflex_payload["vix_structure"]})</div>
        <div><strong>Cross-ticker corr:</strong> {reflex_payload["cross_corr"]:.3f}</div>
        <div><strong>SPY/VIX corr:</strong> {reflex_payload["spy_vix_corr"]:.3f}</div>
        <div><strong>Volume Z:</strong> {reflex_payload["volume_z"]:+.2f}</div>
    </div>
    <div style="font-size:0.8rem; opacity:0.75; margin-top:10px; font-style:italic;">{reflex_payload["notes"]}</div>
</div>

<div class="research-panel">
    <h3>⚖️ Adaptive Signal Weights (Thompson Sampling)</h3>
    {''.join([f'''
    <div class="bar-container">
        <div class="bar-label-row"><span><strong>{sig}</strong></span><span>{(w*100):.1f}%</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:{(w*100):.1f}%"></div></div>
    </div>
    ''' for sig, w in sorted(mab_latest.items(), key=lambda x: -x[1])]) if mab_latest else '<div style="opacity:0.7;">MAB weights will appear after first trade closes.</div>'}
</div>

<div class="research-panel">
    <h3>🌌 Screensaver</h3>
    <div class="screensaver">
        <div class="ring"></div>
        <div class="ring"></div>
        <div class="ring"></div>
    </div>
</div>

</body></html>"""

    components.html(research_html, height=2000, scrolling=True)
