"""
Signal Shadow Bot - Logs every signal independently.
Supabase storage backend.
"""

import os, json
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from common import (
    get_logger, safe_request, log_run, is_market_open, is_market_bullish,
    get_rsi_sma, _sb, SUPABASE_URL, SUPABASE_KEY
)

BARGO_API_KEY = os.environ.get("BARGO_API_KEY")
FORM4API_KEY = os.environ.get("FORM4API_KEY")

WATCHLIST = ["SPY","QQQ","AAPL","MSFT","NVDA","GOOGL","META","AMZN"]
log = get_logger("shadow", "shadow_bot.log")
def L(m): print(m); log.info(m)

import requests
analyzer = SentimentIntensityAnalyzer()

def s_sent(sym):
    try:
        n = yf.Ticker(sym).news
        if not n: return False, 0.0
        s = [analyzer.polarity_scores(i.get('title') or i.get('content',{}).get('title',''))['compound']
             for i in n[:5] if i.get('title') or i.get('content',{}).get('title')]
        avg = sum(s)/len(s) if s else 0.0
        return avg > 0.1, round(avg, 4)
    except Exception: return False, 0.0

def s_congress(sym):
    try:
        if not BARGO_API_KEY: return False
        r = safe_request(requests.get, "https://www.bargo.ai/free-apis/congress/v1/trades",
            headers={"X-Api-Key": BARGO_API_KEY},
            params={"ticker":sym,"type":"buy",
                    "fromDate":(datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d")}, timeout=15)
        return r is not None and r.status_code == 200 and len(r.json().get("trades", [])) > 0
    except Exception: return False

def s_insider(sym):
    try:
        if not FORM4API_KEY: return False
        r = safe_request(requests.get, f"https://api.form4api.com/v1/insider/trades/{sym}",
            headers={"Authorization": f"Bearer {FORM4API_KEY}"}, timeout=15)
        if r is None or r.status_code != 200: return False
        cutoff = datetime.now() - timedelta(days=30)
        for t in r.json().get("trades", []):
            if pd.to_datetime(t.get("filingDate","2000-01-01")) > cutoff and t.get("transactionCode") in ["P","A"]:
                return True
        return False
    except Exception: return False

def s_pead(sym):
    try:
        e = yf.Ticker(sym).earnings_dates
        if e is None or e.empty: return False
        for idx, row in e.iterrows():
            ed = pd.Timestamp(idx).tz_localize(None)
            if pd.Timestamp.now() - ed > pd.Timedelta(days=30): continue
            try:
                if float(row.get('Reported EPS', 0)) > float(row.get('EPS Estimate', 0)): return True
            except Exception: pass
        return False
    except Exception: return False

def s_flow(sym):
    try:
        r = safe_request(requests.post, "https://mcp.gammarips.com/mcp",
                         json={"method":"get_daily_report"}, timeout=10)
        if r is None or r.status_code != 200: return False
        return any(i.get('symbol') == sym for i in r.json().get('bullish_pool', []))
    except Exception: return False

def run():
    L("="*60); L(f"shadow {datetime.now().isoformat()}")
    if not is_market_open():
        L("market closed"); log_run("shadow", "market_closed"); return
    regime = is_market_bullish()
    rows = []
    for sym in WATCHLIST:
        rsi, close, sma = get_rsi_sma(sym)
        rsi_ok = rsi is not None and 35 < rsi < 55
        sma_ok = rsi is not None and close > sma
        sent, sent_val = s_sent(sym)
        con = s_congress(sym); ins = s_insider(sym)
        pead = s_pead(sym); flow = s_flow(sym)
        rows.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": sym,
            "regime": regime, "rsi": rsi_ok, "sma": sma_ok,
            "sentiment": sent, "sentiment_score": sent_val,
            "congress": con, "insider": ins, "pead": pead, "flow": flow,
            "source": "shadow"
        })
        L(f"  {sym}: regime={regime} rsi={rsi_ok} sma={sma_ok} sent={sent} "
          f"congress={con} insider={ins} pead={pead} flow={flow}")
    try:
        if SUPABASE_URL and SUPABASE_KEY:
            _sb().table("signals").insert(rows).execute()
            L(f"✅ logged {len(rows)} shadow rows")
    except Exception as e:
        L(f"⚠️ shadow log: {e}")
    log_run("shadow", "ok", action=f"logged {len(rows)} signal rows")
    L("="*60)

if __name__ == "__main__":
    try: run()
    except Exception as e:
        L(f"❌ FATAL: {e}")
