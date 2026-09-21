"""
Whale Bot Dashboard v9 — Live Trading + Research Lab.
Fixed attribution via Source column. Net P/L after fees.
Supabase storage backend.
"""

import streamlit as st
import streamlit.components.v1 as components
import requests, pandas as pd, numpy as np, json, math
from datetime import datetime

st.set_page_config(page_title="Whale Bot", page_icon="🐋", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding: 0 !important; max-width: 100vw !important; }
iframe { width: 100% !important; max-width: 100vw !important; display: block !important; border: none !important; }
.stTabs [data-baseweb="tab-list"] { background: transparent !important; gap: 8px !important; padding: 8px 0 !important; }
.stTabs [data-baseweb="tab"] {
    background: linear-gradient(180deg, #eafcff 0%, #c8ecf8 48%, #9ce0f0 52%, #7ad0e8 100%) !important;
    border: 1px solid #5ab8d8 !important; border-radius: 8px 8px 0 0 !important;
    color: #063a52 !important; font-weight: 600 !important; padding: 8px 20px !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, #ffffff 0%, #d8f0ff 100%) !important;
    box-shadow: 0 -2px 10px rgba(100,180,220,0.5) !important;
}
</style>
""", unsafe_allow_html=True)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_data(ttl=300)
def fetch_sb(table_name, limit=500):
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        r = sb.table(table_name).select("*").order("created_at", desc=True).limit(limit).execute()
        return r.data or []
    except Exception as e:
        st.error(f"Supabase fetch failed for {table_name}: {e}")
        return []

def clean_for_json(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj): return 0
        return obj
    if isinstance(obj, dict): return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list): return [clean_for_json(x) for x in obj]
    return obj

tab_live, tab_research = st.tabs(["📊 Live Trading", "✨ Research Lab"])

with tab_live:
    trades = fetch_sb("trades")
    exits = fetch_sb("exits")
    fills = fetch_sb("fills")
    runs = fetch_sb("runs")
    signals = fetch_sb("signals")

    for f in fills:
        if "slippage_percent" not in f and "slippage_dollars" in f and "expected_price" in f:
            ep = f.get("expected_price", 0)
            if ep: f["slippage_percent"] = round((f["slippage_dollars"]/ep)*100, 4)

    total_pnl = sum(e.get("pnl_dollars", 0) for e in exits)
    total_fees = sum(e.get("fees", 0) for e in exits)
    net_pnl = total_pnl - total_fees

    wins = sum(1 for e in exits if e.get("pnl_dollars", 0) > 0)
    win_rate = (wins/len(exits)*100) if exits else 0
    open_trades = max(len(trades) - len(exits), 0)

    exits_sorted = sorted(exits, key=lambda x: x.get("exit_timestamp", ""))
    cum = 0; equity_points = []
    for e in exits_sorted:
        cum += e.get("pnl_dollars", 0) - e.get("fees", 0)
        equity_points.append({"t": e.get("exit_timestamp", ""), "v": round(cum, 2)})

    by_symbol = {}
    for e in exits:
        s = e.get("symbol", "?"); by_symbol[s] = by_symbol.get(s, 0) + e.get("pnl_dollars", 0)

    sample_size = len(exits)
    sample_pct = min(sample_size/90*100, 100)

    signal_fires = {"regime":0,"rsi":0,"sma":0,"sentiment":0,"congress":0,"insider":0,"pead":0,"flow":0}
    for s in signals:
        for k in signal_fires:
            if s.get(k): signal_fires[k] += 1

    def detect_source(record):
        src = record.get("source", "")
        if src: return str(src).lower()
        sb = record.get("signal_breakdown", "") or ""
        if "v3_chandelier" in sb: return "v3_chandelier"
        if "v3_fixed" in sb: return "v3_fixed"
        if "v3" in sb: return "v3"
        if "v10" in sb: return "v10"
        return "unknown"

    source_counts = {"v3": 0, "v10": 0, "v3_fixed": 0, "v3_chandelier": 0, "unknown": 0}
    for e in exits:
        src = detect_source(e)
        source_counts[src] = source_counts.get(src, 0) + 1

    live_payload = clean_for_json({
        "total_pnl": round(net_pnl, 2),
        "gross_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 4),
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
        "v3_count": source_counts.get("v3", 0),
        "v10_count": source_counts.get("v10", 0),
        "v3f_count": source_counts.get("v3_fixed", 0),
        "v3ch_count": source_counts.get("v3_chandelier", 0),
    })

    LIVE_HTML = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ font-family:'Segoe UI',Tahoma,sans-serif; color:#063a52; overflow-x:hidden; width:100%; max-width:100vw; }}
body {{ background: radial-gradient(ellipse 90% 12% at 50% 0%, rgba(255,255,255,0.85), transparent 70%), linear-gradient(180deg,#b8ecf5 0%,#8fd8ee 18%,#62c0e0 38%,#3aa8d0 58%,#1e8cbc 78%,#0d6e9c 100%); background-attachment:fixed; min-height:100vh; padding:10px 10px 68px 10px; }}
.aero-window {{ position:relative; width:100%; max-width:1300px; margin:0 auto; border-radius:8px 8px 4px 4px; overflow:hidden; background:rgba(200,240,255,0.55); box-shadow:0 0 0 1px rgba(0,60,90,0.35),0 12px 36px rgba(0,60,90,0.35); backdrop-filter:blur(22px) saturate(180%); -webkit-backdrop-filter:blur(22px) saturate(180%); }}
.window-titlebar {{ background:linear-gradient(180deg,#eafcff 0%,#c8ecf8 8%,#9ce0f0 45%,#7ad0e8 47%,#5ab8d8 52%,#4aa8c8 92%,#6ac0d8 100%); padding:7px 10px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid rgba(0,60,90,0.25); font-size:12px; font-weight:600; color:#063a52; }}
.window-body {{ background:linear-gradient(180deg,rgba(220,245,255,0.72) 0%,rgba(190,230,250,0.6) 100%); padding:14px; }}
.gadget-row {{ display:grid; grid-template-columns:2fr 1fr 1fr 1fr; gap:10px; margin-bottom:14px; }}
.gadget {{ position:relative; background:linear-gradient(180deg,rgba(255,255,255,0.94) 0%,rgba(235,252,255,0.85) 45%,rgba(180,235,250,0.78) 100%); border:1px solid rgba(255,255,255,0.98); border-radius:10px; padding:12px 12px 10px 12px; overflow:hidden; box-shadow:inset 0 1px 0 rgba(255,255,255,1),0 6px 14px rgba(0,80,120,0.22); }}
.gadget::before {{ content:''; position:absolute; top:0; left:0; right:0; height:48%; background:linear-gradient(180deg,rgba(255,255,255,0.88) 0%,rgba(255,255,255,0.35) 60%,rgba(255,255,255,0) 100%); border-radius:10px 10px 50% 50%; pointer-events:none; }}
.gadget-label {{ position:relative; z-index:1; font-size:9.5px; font-weight:600; text-transform:uppercase; letter-spacing:1.4px; color:#1a6a8a; margin-bottom:4px; }}
.gadget-value {{ position:relative; z-index:1; font-family:Georgia,serif; font-weight:700; font-size:26px; color:#063e5a; line-height:1; }}
.gadget-sub {{ position:relative; z-index:1; font-size:10px; color:#1a6a8a; margin-top:4px; }}
.section {{ font-size:11.5px; font-weight:600; text-transform:uppercase; letter-spacing:1.3px; color:#063a52; padding-bottom:5px; margin:16px 0 10px 0; border-bottom:1px solid rgba(255,255,255,0.9); }}
.chart-panel {{ background:linear-gradient(180deg,rgba(255,255,255,0.75) 0%,rgba(220,245,255,0.55) 100%); border:1px solid rgba(255,255,255,0.95); border-radius:10px; padding:12px; box-shadow:inset 0 1px 0 rgba(255,255,255,1),0 4px 10px rgba(0,80,120,0.15); margin-bottom:12px; }}
.chart-svg {{ width:100%; height:160px; display:block; }}
.progress-wrap {{ background:linear-gradient(180deg,rgba(220,240,250,0.8),rgba(200,225,240,0.6)); border-radius:10px; height:22px; overflow:hidden; position:relative; }}
.progress-fill {{ height:100%; background:linear-gradient(180deg,#7ee4c0 0%,#4ac0a0 50%,#2a9c80 100%); border-radius:10px; }}
.progress-label {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:600; color:#063e5a; }}
.glass-table {{ width:100%; border-collapse:collapse; background:rgba(255,255,255,0.55); border-radius:8px; box-shadow:inset 0 1px 0 rgba(255,255,255,1),0 3px 10px rgba(0,80,120,0.15); font-size:11.5px; min-width:440px; }}
.glass-table thead th {{ background:linear-gradient(180deg,#eafcff 0%,#c8ecf8 48%,#9ce0f0 52%,#7ad0e8 100%); color:#063a52; text-align:left; padding:7px 9px; font-weight:600; text-transform:uppercase; font-size:9.5px; border-bottom:1px solid #5ab8d8; }}
.glass-table tbody td {{ padding:6px 9px; border-bottom:1px solid rgba(180,225,240,0.35); color:#063a52; white-space:nowrap; }}
.empty-state {{ padding:14px; text-align:center; background:linear-gradient(180deg,rgba(255,255,255,0.9) 0%,rgba(215,245,255,0.7) 100%); border:1px solid rgba(255,255,255,0.95); border-radius:12px; color:#1a6a8a; font-size:12px; }}
@media (max-width:900px) {{ body {{ padding:6px 6px 62px 6px; }} .window-body {{ padding:10px; }} .gadget-row {{ grid-template-columns:1fr 1fr; gap:8px; }} .gadget-value {{ font-size:22px; }} .glass-table {{ font-size:10.5px; min-width:380px; }} }}
</style></head>
<body>
<div class="aero-window">
  <div class="window-titlebar"><span>🐋 Whale Bot Dashboard</span><span>Refreshed {live_payload["refreshed"]}</span></div>
  <div class="window-body">
    <div class="gadget-row">
      <div class="gadget"><div class="gadget-label">Net P/L</div><div class="gadget-value">${live_payload["total_pnl"]:,.2f}</div><div class="gadget-sub">fees ${live_payload["total_fees"]:.4f}</div></div>
      <div class="gadget"><div class="gadget-label">Win Rate</div><div class="gadget-value">{live_payload["win_rate"]:.0f}%</div></div>
      <div class="gadget"><div class="gadget-label">Open</div><div class="gadget-value">{live_payload["open_trades"]}</div></div>
      <div class="gadget"><div class="gadget-label">Fills</div><div class="gadget-value">{live_payload["fills_count"]}</div></div>
    </div>
    <div class="section">📈 Sample Size Progress</div>
    <div class="chart-panel">
      <div class="progress-wrap"><div class="progress-fill" style="width:{live_payload["sample_pct"]}%"></div><div class="progress-label">{live_payload["sample_size"]} / 90 trades</div></div>
      <div style="display:flex;justify-content:space-between;margin-top:10px;font-size:10.5px;color:#1a6a8a;">
        <span>v3: {live_payload["v3_count"]}</span>
        <span>v10: {live_payload["v10_count"]}</span>
        <span>v3_fixed: {live_payload["v3f_count"]}</span>
        <span>v3_chandelier: {live_payload["v3ch_count"]}</span>
      </div>
    </div>
    <div class="section">💹 Equity Curve (net)</div><div class="chart-panel" id="equity-panel"></div>
    <div class="section">📋 Recent Trades</div><div id="trades-panel"></div>
    <div class="section">📕 Recent Exits</div><div id="exits-panel"></div>
  </div>
</div>
<script>
const DATA = {json.dumps(live_payload, default=str)};
function lineChart(elId, pts, color) {{
    const panel = document.getElementById(elId);
    if (!pts || pts.length < 2) {{ panel.innerHTML = '<div class="empty-state">Not enough data yet.</div>'; return; }}
    const W = Math.max(panel.clientWidth - 20, 260), H = 160, pad = 24;
    const vals = pts.map(p => p.v); const minV = Math.min(...vals), maxV = Math.max(...vals); const range = maxV - minV || 1;
    const dx = (W - pad*2) / Math.max(pts.length-1, 1);
    const points = pts.map((p, i) => [pad + i*dx, H - pad - ((p.v - minV)/range)*(H - pad*2)]);
    const pathD = points.map((p, i) => (i===0 ? `M${{p[0]}},${{p[1]}}` : `L${{p[0]}},${{p[1]}}`)).join(' ');
    const areaD = pathD + ` L${{points[points.length-1][0]}},${{H-pad}} L${{points[0][0]}},${{H-pad}} Z`;
    panel.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${{W}} ${{H}}" preserveAspectRatio="none"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${{color}}" stop-opacity="0.6"/><stop offset="100%" stop-color="${{color}}" stop-opacity="0.05"/></linearGradient></defs><path d="${{areaD}}" fill="url(#g)"/><path d="${{pathD}}" fill="none" stroke="${{color}}" stroke-width="2.5"/>${{points.map(p => `<circle cx="${{p[0]}}" cy="${{p[1]}}" r="3" fill="#fff" stroke="${{color}}" stroke-width="2"/>`).join('')}}</svg>`;
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
renderTable('trades-panel', DATA.trades, ['timestamp','symbol','qty','price','score','threshold'], ['Time','Symbol','Qty','Price','Score','Thr'], '🌊 No trades yet.');
renderTable('exits-panel', DATA.exits, ['exit_timestamp','symbol','exit_reason','pnl_dollars','source','fees'], ['Time','Symbol','Reason','P/L $','Source','Fees'], '🌊 No exits yet.');
</script>
</body></html>"""
    components.html(LIVE_HTML, height=1700, scrolling=True)

with tab_research:
    astro_rows = fetch_sb("astro")
    reflexive_rows = fetch_sb("reflexive")
    mab_rows = fetch_sb("mab_weights")
    signals_rows = fetch_sb("signals")
    exits_for_viz = fetch_sb("exits")

    current_astro = {}
    if astro_rows:
        nyse = sorted([a for a in astro_rows if a.get('reference') == 'NYSE'], key=lambda x: x.get('timestamp',''))
        if nyse: current_astro = nyse[-1]

    current_reflexive = {}
    if reflexive_rows:
        srtd = sorted(reflexive_rows, key=lambda x: x.get('timestamp',''))
        current_reflexive = srtd[-1]

    mab_latest = {}
    if mab_rows:
        for r in sorted(mab_rows, key=lambda x: x.get('timestamp','')):
            mab_latest[r.get('signal')] = float(r.get('weight', 0))

    try:
        from visualizer import narrate_state, build_state_space_figure, build_signal_heatmap
        narrative = narrate_state(current_astro, current_reflexive, mab_latest, exits_for_viz)
        fig_state = build_state_space_figure(astro_rows, reflexive_rows, exits_for_viz)
        fig_heatmap = build_signal_heatmap(signals_rows)
    except Exception as e:
        narrative = f"Visualizer error: {e}"
        fig_state = None
        fig_heatmap = None

    RESEARCH_CSS = """
    <style>
    .research-header {
        font-family: 'Trebuchet MS', 'Comic Sans MS', sans-serif;
        font-size: 2.4rem; font-weight: bold; color: #ffffff;
        text-align: center;
        text-shadow: 0 0 10px #a8e4ff, 0 0 20px #6cc8ff, 0 0 30px #4ab8f0, 0 2px 0 #0a2a4a;
        letter-spacing: 2px; padding: 20px;
        animation: titleGlow 3s ease-in-out infinite;
    }
    @keyframes titleGlow {
        0%, 100% { text-shadow: 0 0 10px #a8e4ff, 0 0 20px #6cc8ff, 0 0 30px #4ab8f0, 0 2px 0 #0a2a4a; }
        50% { text-shadow: 0 0 20px #d0f0ff, 0 0 40px #a8e4ff, 0 0 60px #6cc8ff, 0 2px 0 #0a2a4a; }
    }
    .narrative-box {
        background: linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(200,230,255,0.1) 100%);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(200,230,255,0.5);
        border-radius: 14px;
        padding: 20px 24px;
        margin: 16px 0;
        color: #e8f4ff;
        font-size: 1.05rem;
        line-height: 1.6;
        box-shadow: 0 8px 24px rgba(0,20,60,0.4), 0 0 30px rgba(100,180,255,0.3);
    }
    .narrative-box h3 {
        color: #a8e4ff; font-size: 0.9rem; text-transform: uppercase;
        letter-spacing: 2px; margin-bottom: 10px;
        text-shadow: 0 0 8px #4ab8f0;
    }
    </style>
    """
    st.markdown(RESEARCH_CSS, unsafe_allow_html=True)

    st.markdown('<div class="research-header">✨ Astrological Research Lab ✨</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="narrative-box"><h3>🧠 AI Interpretation</h3>{narrative}</div>',
        unsafe_allow_html=True
    )

    if fig_state:
        st.markdown("### 🌌 State Space Animation")
        st.plotly_chart(fig_state, use_container_width=True)
    else:
        st.info("State space visualizer will appear after a few days of data.")

    if fig_heatmap:
        st.markdown("### 🔥 Signal Fire Heatmap")
        st.plotly_chart(fig_heatmap, use_container_width=True)

    astro_display = float(current_astro.get('astro_score', 0))
    astro_pct = max(0, min(100, (astro_display + 10) * 5))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🌙 Planetary State")
        st.markdown(f"""
        - **Sun:** {current_astro.get('sun_sign','—')} {current_astro.get('sun_degree',0)}°
        - **Moon:** {current_astro.get('moon_sign','—')} | {current_astro.get('moon_phase','—')} ({current_astro.get('moon_illumination',0)}%)
        - **Mercury Rx:** {'☿ Yes' if current_astro.get('mercury_retrograde') else 'Direct'}
        - **Jupiter:** {current_astro.get('jupiter_sign','—')}
        - **Saturn:** {current_astro.get('saturn_sign','—')}
        - **Nakshatra:** {current_astro.get('nakshatra','—')}
        """)
        st.progress(astro_pct / 100, text=f"Astro Score: {astro_display:+.1f}")

    with col2:
        st.markdown("#### 🌀 Reflexive Intensity")
        intensity = float(current_reflexive.get('reflexive_intensity', 0))
        st.metric("Intensity", f"{intensity:.1f}/10")
        st.markdown(f"""
        - **VIX:** {current_reflexive.get('vix_spot',0)} ({current_reflexive.get('vix_term_structure','—')})
        - **Cross-corr:** {current_reflexive.get('cross_ticker_correlation',0):.3f}
        - **SPY/VIX:** {current_reflexive.get('spy_vix_correlation',0):.3f}
        - **Volume Z:** {current_reflexive.get('volume_z_score',0):+.2f}
        """)

    st.markdown("#### ⚖️ Adaptive Signal Weights")
    if mab_latest:
        for sig, w in sorted(mab_latest.items(), key=lambda x: -x[1]):
            st.progress(w, text=f"{sig}: {w*100:.1f}%")
    else:
        st.info("MAB weights will appear after first trade closes.")
