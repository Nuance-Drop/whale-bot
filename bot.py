"""
Whale Bot - Automated Trading System
Layer 3: Tactical Engine (Flow + Sentiment + Trend)
Runs on PythonAnywhere via scheduled task.
"""

import os
import csv
import logging
from datetime import datetime, time, timezone

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
# тЪая╕П REPLACE THESE WITH YOUR ACTUAL ALPACA KEYS
# ============================================================
API_KEY = os.environ.get("PKCJJGQWRGCJB24ZPEWVO6WICB")
SECRET_KEY = os.environ.get("BpD5Tjc4R8mcVTR6hDL8i6AP21y9gFox6m9AYtr5xysB")
# ============================================================
# CONFIGURATION
# ============================================================
WATCHLIST = ["SPY", "QQQ", "AAPL", "NVDA", "MSFT"]
RISK_PER_TRADE = 0.02       # 2% of equity per trade
STOP_LOSS_PCT = 0.015       # 1.5%
TAKE_PROFIT_PCT = 0.03      # 3%
MAX_POSITIONS = 3
TACTICAL_LIMIT_PCT = 0.20   # 20% of equity for tactical trades

LOG_FILE = "trade_log.csv"
BOT_LOG = "bot.log"

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    filename=BOT_LOG,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log(msg):
    print(msg)
    logging.info(msg)

# ============================================================
# MARKET HOURS CHECK
# ============================================================
def is_market_open():
    """Returns True if US market is open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
    now = datetime.now(timezone.utc) # UTC time
    # US market: 14:30 - 21:00 UTC (adjusts for DST)
    if now.weekday() >= 5:  # Weekend
        return False
    market_open = time(13, 30)   # 9:30 AM ET (approx, includes DST buffer)
    market_close = time(20, 0)   # 4:00 PM ET
    return market_open <= now.time() <= market_close

# ============================================================
# BROKER CONNECTION
# ============================================================
client = TradingClient(API_KEY, SECRET_KEY, paper=True)
analyzer = SentimentIntensityAnalyzer()

# ============================================================
# SENTIMENT
# ============================================================
def get_sentiment_score(symbol):
    try:
        ticker = yf.Ticker(symbol)
        news_list = ticker.news
        if not news_list:
            return 0.0
        scores = []
        for item in news_list[:5]:
            title = item.get('title') or item.get('content', {}).get('title', '')
            if title:
                scores.append(analyzer.polarity_scores(title)['compound'])
        return sum(scores) / len(scores) if scores else 0.0
    except Exception as e:
        log(f"тЪая╕П Sentiment error for {symbol}: {e}")
        return 0.0

# ============================================================
# SIGNAL FUNCTION
# ============================================================
def get_signal(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 50 or 'Close' not in df.columns:
            return None

        df['SMA50'] = df['Close'].rolling(50).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]
        sentiment = get_sentiment_score(symbol)

        log(f"{symbol}: RSI={last['RSI']:.1f}, Close={last['Close']:.2f}, "
            f"SMA50={last['SMA50']:.2f}, Sentiment={sentiment:.2f}")

        if (last['Close'] > last['SMA50'] and 30 < last['RSI'] < 60
                and sentiment > 0.1):
            return 'BUY'
        if last['RSI'] > 70:
            return 'SELL'
        return None
    except Exception as e:
        log(f"тЪая╕П Signal error for {symbol}: {e}")
        return None

# ============================================================
# LOGGING + BROKER
# ============================================================
def log_trade(symbol, side, qty, price, stop, target):
    try:
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "side", "qty", "price",
                                 "stop_loss", "take_profit"])
            writer.writerow([datetime.now().isoformat(), symbol, side, qty,
                             price, stop, target])
        log(f"ЁЯУЭ Logged trade: {symbol} {side} {qty} @ ${price:.2f}")
    except Exception as e:
        log(f"тЪая╕П Logging failed: {e}")

def place_bracket_order(symbol, side, qty, entry_price):
    try:
        if side == OrderSide.BUY:
            stop_price = round(entry_price * (1 - STOP_LOSS_PCT), 2)
            target_price = round(entry_price * (1 + TAKE_PROFIT_PCT), 2)
        else:
            stop_price = round(entry_price * (1 + STOP_LOSS_PCT), 2)
            target_price = round(entry_price * (1 - TAKE_PROFIT_PCT), 2)

        order_data = MarketOrderRequest(
            symbol=symbol, qty=qty, side=side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=target_price),
            stop_loss=StopLossRequest(stop_price=stop_price)
        )
        order = client.submit_order(order_data)
        log(f"тЬЕ {side} {qty} {symbol} @ market. SL: ${stop_price}, TP: ${target_price}")
        log_trade(symbol, str(side), qty, entry_price, stop_price, target_price)
        return order
    except Exception as e:
        log(f"тЭМ Trade execution failed for {symbol}: {e}")
        return None

# ============================================================
# MAIN BOT LOGIC
# ============================================================
def run_bot():
    log("=" * 60)
    log(f"Bot started at {datetime.now().isoformat()}")

    if not is_market_open():
        log("Market is closed. Exiting.")
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
        log(f"Holding: {already_held}")

        if total_position_value >= tactical_limit:
            log("тЪая╕П Tactical limit reached. Skipping.")
            return
        if len(already_held) >= MAX_POSITIONS:
            log(f"тЪая╕П Max positions ({MAX_POSITIONS}) reached. Skipping.")
            return

        for symbol in WATCHLIST:
            signal = get_signal(symbol)

            if signal == 'BUY':
                if symbol in already_held:
                    log(f"тП╕я╕П {symbol}: Already held. Skipping.")
                    continue

                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1d", auto_adjust=True)
                price = float(hist['Close'].iloc[-1])

                remaining_tactical = tactical_limit - total_position_value
                risk_amount = equity * RISK_PER_TRADE
                risk_per_share = price * STOP_LOSS_PCT

                qty_risk = int(risk_amount / risk_per_share)
                qty_cap = int(remaining_tactical / price)
                qty = min(qty_risk, qty_cap)

                if qty < 1:
                    log(f"тЪая╕П {symbol}: Not enough room for 1 share.")
                    continue

                log(f"Calculated qty: {qty}")
                place_bracket_order(symbol, OrderSide.BUY, qty, price)
                break
            else:
                log(f"тП╕я╕П {symbol}: No signal.")

    except Exception as e:
        log(f"тЭМ Bot error: {e}")

    log("Bot cycle complete.")
    log("=" * 60)

# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    run_bot()
