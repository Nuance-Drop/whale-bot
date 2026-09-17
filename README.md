# Autonomous Multi-Bot Trading System

A production-grade, serverless trading system built entirely on GitHub Actions 
+ free-tier APIs. Designed for reliability, observability, and zero-cost operation.

## Architecture
- 4 parallel bots with independent strategies (v3, v3_fixed, v10, shadow)
- Centralized API wrapper with exponential backoff and retry logic
- Airtable as the persistent state layer (runs, trades, exits, fills, peak equity)
- Telegram notifications for real-time alerts
- Auto-halt after 3 consecutive errors
- Persistent drawdown kill switch (Airtable-backed)
- 5 unit tests with CI/CD on every push
- Streamlit dashboard for live monitoring

## What This Demonstrates
- Serverless system design (GitHub Actions as compute)
- Multi-service API integration (Alpaca, Airtable, Telegram, yfinance, Kalshi)
- Fault tolerance (backoff, halt, kill switch, state persistence)
- Production observability (structured logging, per-run audit trail)
- Test-driven development
