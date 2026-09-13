AERO_CSS = """
<style>
/* ============================================================
   FRUTIGER AERO THEME — Windows 7 / Vista era
   Bright sky, glossy glass, skeuomorphic depth
   ============================================================ */

@import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Segoe UI', 'Lucida Grande', 'Trebuchet MS', Tahoma, sans-serif !important;
    color: #0e3a4a !important;
}

/* ============================================================
   BACKGROUND: BRIGHT SKY + CLOUDS + GREEN HILL
   ============================================================ */
.stApp {
    background:
        /* White clouds */
        radial-gradient(ellipse 60% 18% at 15% 12%, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0) 60%),
        radial-gradient(ellipse 45% 12% at 80% 8%, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0) 60%),
        radial-gradient(ellipse 55% 15% at 50% 20%, rgba(255,255,255,0.75) 0%, rgba(255,255,255,0) 65%),
        radial-gradient(ellipse 40% 10% at 25% 28%, rgba(255,255,255,0.6) 0%, rgba(255,255,255,0) 60%),
        /* Green grass bloom at bottom */
        radial-gradient(ellipse 100% 30% at 50% 100%, #7ac470 0%, #5fb454 40%, rgba(95,180,84,0) 80%),
        /* Bright sky gradient */
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

/* Streamlit chrome hide */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 3rem !important;
    max-width: 1200px;
    position: relative;
    z-index: 1;
}

/* ============================================================
   WINDOWS-STYLE TITLE BAR for headings
   ============================================================ */
h1 {
    background: linear-gradient(180deg, #d8eef8 0%, #a4d4ea 48%, #7bb8d8 52%, #5a9ac0 100%) !important;
    color: #103a52 !important;
    padding: 14px 22px !important;
    border-radius: 8px 8px 0 0 !important;
    border: 1px solid #4d8aa8 !important;
    border-bottom: none !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.95),
        inset 0 -1px 0 rgba(0,50,80,0.15),
        0 2px 8px rgba(0,50,80,0.35) !important;
    font-size: 1.8rem !important;
    font-weight: 400 !important;
    letter-spacing: 0.5px !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.9) !important;
    margin-bottom: 0 !important;
    position: relative;
}

/* Small text under the h1 becomes the window body */
.stApp > div > div > div > div > div > div > div:first-child p {
    /* handled by markdown below */
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

/* ============================================================
   GLASS PANELS — Windows 7 Aero glass
   ============================================================ */
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

/* Gloss highlight on top of each panel */
[data-testid="stMetric"]::before {
    content: '';
    position: absolute;
    top: 0; left: 8%; right: 8%;
    height: 38%;
    background: linear-gradient(180deg, rgba(255,255,255,0.75) 0%, rgba(255,255,255,0) 100%);
    border-radius: 10px 10px 40% 40%;
    pointer-events: none;
}

/* ============================================================
   METRIC VALUES — bold Windows sidebar gadget style
   ============================================================ */
[data-testid="stMetricValue"] {
    color: #0d5a7a !important;
    font-weight: 700 !important;
    font-size: 2.4rem !important;
    text-shadow:
        0 1px 0 rgba(255,255,255,0.95),
        0 2px 6px rgba(0,80,120,0.2) !important;
    font-family: 'Segoe UI', sans-serif !important;
}

[data-testid="stMetricLabel"] {
    color: #2a7090 !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-size: 0.7rem !important;
    text-shadow: 0 1px 0 rgba(255,255,255,0.8) !important;
}

/* ============================================================
   AERO GLASS BUTTONS — skeuomorphic Windows 7 style
   ============================================================ */
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
    background:
        linear-gradient(180deg,
            #7bb8d8 0%,
            #4d94b8 100%) !important;
    box-shadow:
        inset 0 2px 6px rgba(0,50,80,0.4) !important;
    padding-top: 0.65rem !important;
    padding-bottom: 0.45rem !important;
}

/* ============================================================
   TABS — Aero tab style
   ============================================================ */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: transparent !important;
    border: none !important;
}
.stTabs [data-baseweb="tab"] {
    background: linear-gradient(180deg,
        rgba(255,255,255,0.7) 0%,
        rgba(200,235,255,0.55) 100%) !important;
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
    background: linear-gradient(180deg,
        #ffffff 0%,
        #e0f2ff 50%,
        #c8e8fa 100%) !important;
    color: #054a6a !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,1),
        0 -1px 8px rgba(100,180,220,0.4) !important;
}

/* ============================================================
   DATAFRAMES — light glass with aqua header
   ============================================================ */
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

/* ============================================================
   INFO / ALERT BOXES — glossy Aero panels
   ============================================================ */
.stAlert {
    background: linear-gradient(180deg,
        rgba(255,255,255,0.9) 0%,
        rgba(215,240,255,0.75) 100%) !important;
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

/* ============================================================
   DIVIDERS — glossy white line
   ============================================================ */
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

/* ============================================================
   SIDEBAR — glass panel
   ============================================================ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,
        rgba(255,255,255,0.8) 0%,
        rgba(200,235,255,0.7) 100%) !important;
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255,255,255,0.95) !important;
    box-shadow: inset -1px 0 0 rgba(120,180,220,0.3) !important;
}

/* ============================================================
   CHARTS — glass panels
   ============================================================ */
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

/* ============================================================
   SUBTLE FLOAT ANIMATION on metric gadgets
   ============================================================ */
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

/* ============================================================
   MARKDOWN TEXT
   ============================================================ */
p, span, div, label {
    color: #0d3a52 !important;
}
.stMarkdown p {
    text-shadow: 0 1px 0 rgba(255,255,255,0.7) !important;
}
</style>
"""
