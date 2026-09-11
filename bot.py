"""
Whale Bot v5 - Multi-Signal Confluence Engine with Dynamic Threshold + Telegram Alerts
Combines: Congressional Trades + Insider Trades + PEAD + Options Flow + RSI/SMA + Sentiment
"""

import os
import csv
import logging
import requests
from datetime import datetime, time, timezone, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
)
from alpaca.trading.enums import (
    OrderSide, TimeInForce, OrderClass, QueryOrderStatus
)
import yfinance as yf
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ============================================================
# API KEYS
# ============================================================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
APIFY_API_KEY = os.environ.get("APIFY_API_KEY")
FORM4API_KEY = os.environ.get("FORM4API_KEY")
BARGO_API_KEY = os.environ.get("BARGO_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ============================================================
# CONFIGURATION
# ============================================================
WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN"]
RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.025
TRAIL_PCT = 0.015
MAX_POSITIONS = 3
TACTICAL_LIMIT_PCT = 0.20
MIN_SIGNAL_SCORE = 4

LOG_FILE = "trade_log.csv"
BOT_LOG = "bot.log"

logging.basicConfig(filename=BOT_LOG, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def log(msg):
    print(msg)
    logging.info(msg)

# ============================================================
# TELEGRAM NOTIFICATIONS
# ============================================================
def send_telegram(message):
    """Send a Telegram message. Never crashes the bot if it fails."""
    try:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        log(f"⚠️ Telegram failed: {e}")

# ============================================================
# MARKET REGIME
# ============================================================
def is_market_bullish():
    spy = yf.download("SPY", period="1y", interval="1d",
                      auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy['SMA200'] = spy['Close'].rolling(200).mean()
    return spy['Close'].iloc[-1] > spy['SMA200'].iloc[-1]

# ============================================================
# SIGNAL 1: CONGRESSIONAL TRADES (Bargo Congress - Free)
# ============================================================
def congressional_signal(symbol):
    try:
        if not BARGO_API_KEY:
            return False
        url = "https://www.bargo.ai/free-apis/congress/v1/trades"
        headers = {"X-Api-Key": BARGO_API_KEY}
        params = {
            "ticker": symbol,
            "type": "buy",
            "fromDate": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "limit": 5
        }
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return False
        data = r.json()
        return len(data.get("trades", [])) > 0
    except Exception as e:
        log(f"⚠️ Congressional signal error: {e}")
        return False

# ============================================================
# SIGNAL 2: INSIDER TRADES (Form4API - Free)
# ============================================================
def insider_signal(symbol):
    try:
        if not FORM4API_KEY:
            return False
        url = f"https://api.form4api.com/v1/insider/trades/{symbol}"
        headers = {"Authorization": f"Bearer {FORM4API_KEY}"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return False
        data = r.json()
        cutoff = datetime.now() - timedelta(days=30)
        for trade in data.get("trades", []):
            trade_date = pd.to_datetime(trade.get("filingDate", "2000-01-01"))
            if trade_date > cutoff and trade.get("transactionCode") in ["P", "A"]:
                return True
        return False
    except Exception as e:
        log(f"⚠️ Insider signal error: {e}")
        return False

# ============================================================
# SIGNAL 3: PEAD
# ============================================================
def pead_signal(symbol):
    try:
        ticker = yf.Ticker(symbol)
        earnings = ticker.earnings_dates
        if earnings is None or earnings.empty:
            return False
        for idx, row in earnings.iterrows():
            ed = pd.Timestamp(idx).tz_localize(None)
            if pd.Timestamp.now() - ed > pd.Timedelta(days=30):
                continue
            try:
                reported = float(row.get('Reported EPS', 0))
                estimate = float(row.get('EPS Estimate', 0))
                if reported > estimate:
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        log(f"⚠️ PEAD error: {e}")
        return False

# ============================================================
# SIGNAL 4: OPTIONS FLOW
# ============================================================
def options_flow_signal(symbol):
    try:
        url = "https://mcp.gammarips.com/mcp"
        r = requests.post(url, json={"method": "get_daily_report"}, timeout=10)
        if r.status_code != 200:
            return False
        data = r.json()
        for item in data.get('bullish_pool', []):
            if item.get('symbol') == symbol:
                return True
        return False
    except Exception as e:
        log(f"⚠️ Options flow error: {e}")
        return False

# ============================================================
# SIGNAL 5: TECHNICAL
# ============================================================
def technical_signal(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50:
            return (False, False)
        df['SMA50'] = df['Close'].rolling(50).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))
        last = df.iloc[-1]
        rsi_ok = 35 < last['RSI'] < 55
        sma_ok = last['Close'] > last['SMA50']
        log(f"  {symbol}: RSI={last['RSI']:.1f}, Close={last['Close']:.2f}, SMA50={last['SMA50']:.2f}")
        return (rsi_ok, sma_ok)
    except Exception as e:
        log(f"⚠️ Technical error: {e}")
        return (False, False)

# ============================================================
# SIGNAL 6: SENTIMENT
# ============================================================
analyzer = SentimentIntensityAnalyzer()

def sentiment_signal(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news:
            return False
        scores = []
        for item in news[:5]:
            title = item.get('title') or item.get('content', {}).get('title', '')
            if title:
                scores.append(analyzer.polarity_scores(title)['compound'])
        return (sum(scores) / len(scores)) > 0.1 if scores else False
    except Exception:
        return False

# ============================================================
# COMPOSITE SCORING
# ============================================================
def calculate_score(symbol):
    score = 0
    signals = {}
    if not is_market_bullish():
        return 0, {"regime": False}
    score += 1
    signals['regime'] = True
    rsi_ok, sma_ok = technical_signal(symbol)
    if rsi_ok: score += 1; signals['rsi'] = True
    if sma_ok: score += 1; signals['sma'] = True
    if sentiment_signal(symbol):
        score += 1; signals['sentiment'] = True
    if congressional_signal(symbol):
        score += 2; signals['congress'] = True
    if insider_signal(symbol):
        score += 2; signals['insider'] = True
    if pead_signal(symbol):
        score += 1; signals['pead'] = True
    if options_flow_signal(symbol):
        score += 2; signals['flow'] = True
    log(f"  {symbol} SCORE: {score}/10 | Signals: {signals}")
    return score, signals

# ============================================================
# DYNAMIC THRESHOLD
# ============================================================
def get_vix_level():
    try:
        vix = yf.download("^VIX", period="5d", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        return float(vix['Close'].iloc[-1])
    except Exception:
        return 20.0

def get_spy_regime_strength():
    try:
        spy = yf.download("SPY", period="1y", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        spy['SMA200'] = spy['Close'].rolling(200).mean()
        last = spy.iloc[-1]
        return (last['Close'] - last['SMA200']) / last['SMA200'] * 100
    except Exception:
        return 0.0

def is_earnings_season():
    return datetime.now().month in [1, 4, 7, 10]

def is_macro_event_week():
    now = datetime.now()
    if now.weekday() == 4 and now.day <= 7:
        return True
    return False

def calculate_dynamic_threshold(equity, num_positions, log):
    threshold = 4
    reasons = []
    regime_strength = get_spy_regime_strength()
    if regime_strength < 0:
        log(f"  🚫 SPY below 200MA ({regime_strength:.1f}%) — BLOCK ALL TRADES")
        return 999, ["regime_block"]
    elif regime_strength < 2:
        threshold += 1
        reasons.append(f"Fragile regime (+1, SPY only +{regime_strength:.1f}%)")
    elif regime_strength > 5:
        threshold -= 1
        reasons.append(f"Strong bull (-1, SPY +{regime_strength:.1f}%)")
    vix = get_vix_level()
    if vix > 30:
        threshold += 2
        reasons.append(f"VIX {vix:.1f} > 30 (+2)")
    elif vix > 20:
        threshold += 1
        reasons.append(f"VIX {vix:.1f} elevated (+1)")
    elif vix < 15:
        threshold -= 1
        reasons.append(f"VIX {vix:.1f} < 15 (-1)")
    if is_earnings_season():
        threshold += 1
        reasons.append("Earnings season (+1)")
    if is_macro_event_week():
        threshold += 1
        reasons.append("Macro event week (+1)")
    if num_positions >= 2:
        threshold += 1
        reasons.append(f"Holding {num_positions} positions (+1)")
    now = datetime.now(timezone.utc)
    if now.weekday() == 0 and now.hour < 16:
        threshold += 1
        reasons.append("Monday morning (+1)")
    if now.weekday() == 4 and now.hour >= 19:
        threshold += 1
        reasons.append("Friday afternoon (+1)")
    threshold = max(3, min(threshold, 10))
    return threshold, reasons

# ============================================================
# POSITION SIZING
# ============================================================
def calculate_position_multiplier(score, threshold):
    if score <= threshold:
        return 0.5
    elif score == threshold + 1:
        return 0.75
    elif score == threshold + 2:
        return 1.0
    elif score == threshold + 3:
        return 1.25
    else:
        return 1.5

# ============================================================
# BROKER
# ============================================================
client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

def log_trade(symbol, side, qty, price, stop, target):
    try:
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "side", "qty", "price", "stop", "target"])
            writer.writerow([datetime.now().isoformat(), symbol, side, qty, price, stop, target])
    except Exception as e:
        log(f"⚠️ Log error: {e}")

def place_bracket_order(symbol, side, qty, entry_price, score, threshold):
    try:
        stop_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)
        target_price = round(entry_price * (1 + 0.05), 2)
        order_data = MarketOrderRequest(
            symbol=symbol, qty=qty, side=side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=target_price),
            stop_loss=StopLossRequest(stop_price=stop_price)
        )
        order = client.submit_order(order_data)
        log(f"✅ {side} {qty} {symbol} @ ${entry_price:.2f} | SL: ${stop_price} | TP: ${target_price}")
        log_trade(symbol, str(side), qty, entry_price, stop_price, target_price)

        # Telegram alert for the trade
        alert = (
            f"🚨 *TRADE PLACED*\n\n"
            f"*Symbol:* {symbol}\n"
            f"*Side:* BUY\n"
            f"*Quantity:* {qty} shares\n"
            f"*Entry:* ${entry_price:.2f}\n"
            f"*Stop-Loss:* ${stop_price}\n"
            f"*Target:* ${target_price}\n"
            f"*Score:* {score}/{threshold}\n"
            f"*Cost:* ${qty * entry_price:.2f}\n\n"
            f"Equity: ${float(client.get_account().equity):.2f}"
        )
        send_telegram(alert)
        return order
    except Exception as e:
        log(f"❌ Order failed: {e}")
        send_telegram(f"❌ *Order failed* for {symbol}: {e}")
        return None

# ============================================================
# MAIN BOT
# ============================================================
def run_bot():
    log("=" * 60)
    log(f"Bot v5 started at {datetime.now().isoformat()}")

    now = datetime.now(timezone.utc)
    if now.weekday() >= 5 or now.hour < 14 or now.hour >= 21:
        log("Market closed. Exiting.")
        return

    try:
        account = client.get_account()
        equity = float(account.equity)
        open_positions = client.get_all_positions()
        position_symbols = [p.symbol for p in open_positions]
        orders_request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        open_orders = client.get_orders(filter=orders_request)
        order_symbols = [o.symbol for o in open_orders]
        already_held = set(position_symbols + order_symbols)
        total_position_value = sum([float(p.market_value) for p in open_positions])
        tactical_limit = equity * TACTICAL_LIMIT_PCT

        log(f"Equity: ${equity:.2f} | Exposure: ${total_position_value:.2f} | Limit: ${tactical_limit:.2f}")

        threshold, reasons = calculate_dynamic_threshold(equity, len(already_held), log)
        log(f"📊 DYNAMIC THRESHOLD: {threshold} (base was 4)")
        for reason in reasons:
            log(f"   → {reason}")

        if threshold > 10:
            log("🚫 Threshold exceeds max score. No trades today.")
            return
        if total_position_value >= tactical_limit:
            log("⚠️ Tactical limit reached.")
            return
        if len(already_held) >= MAX_POSITIONS:
            log(f"⚠️ Max positions ({MAX_POSITIONS}) reached.")
            return

        candidates = []
        for symbol in WATCHLIST:
            if symbol in already_held:
                log(f"⏸️ {symbol}: Already held.")
                continue
            score, signals = calculate_score(symbol)
            if score >= threshold:
                candidates.append((symbol, score))
            else:
                log(f"  ❌ {symbol}: Score {score} below threshold {threshold}")

        if not candidates:
            log("No tickers met the dynamic threshold.")
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        symbol, score = candidates[0]
        multiplier = calculate_position_multiplier(score, threshold)
        log(f"🎯 TRADING {symbol} (Score: {score}/{threshold}) | Size multiplier: {multiplier}x")

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", auto_adjust=True)
        price = float(hist['Close'].iloc[-1])

        remaining_tactical = tactical_limit - total_position_value
        risk_amount = equity * RISK_PER_TRADE * multiplier
        risk_per_share = price * STOP_LOSS_PCT
        qty = min(int(risk_amount / risk_per_share), int(remaining_tactical / price))

        if qty < 1:
            log(f"⚠️ Not enough room for 1 share of {symbol}.")
            return

        place_bracket_order(symbol, OrderSide.BUY, qty, price, score, threshold)

    except Exception as e:
        log(f"❌ Bot error: {e}")
        send_telegram(f"❌ *Bot error:* {e}")

    log("Bot cycle complete.")
    log("=" * 60)

if __name__ == "__main__":
    run_bot()
