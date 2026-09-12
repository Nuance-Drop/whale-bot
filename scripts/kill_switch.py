"""Runs hourly. Triggers emergency close if equity drawdown exceeds threshold."""
import os, sys
from alpaca.trading.client import TradingClient
from datetime import datetime

API_KEY = os.environ["ALPACA_API_KEY"]
SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DRAWDOWN_LIMIT = 0.05

def tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    import requests
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                  json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)

def main():
    client = TradingClient(API_KEY, SECRET_KEY, paper=True)
    account = client.get_account()
    equity = float(account.equity)
    try:
        peak = float(open("peak_equity.txt").read().strip())
    except Exception:
        peak = equity
        with open("peak_equity.txt", "w") as f:
            f.write(str(peak))
    if equity > peak:
        peak = equity
        with open("peak_equity.txt", "w") as f:
            f.write(str(peak))
    dd = (peak - equity) / peak
    print(f"Equity: ${equity:.2f} | Peak: ${peak:.2f} | Drawdown: {dd:.2%}")
    if dd >= DRAWDOWN_LIMIT:
        print("🛑 KILL SWITCH TRIGGERED")
        client.close_all_positions(cancel_orders=True)
        tg(f"🛑 *KILL SWITCH*\nDrawdown {dd:.2%}\nAll positions closed.")
        sys.exit(0)
    print("✅ Kill switch OK")

if __name__ == "__main__":
    main()
