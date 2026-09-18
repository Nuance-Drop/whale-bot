# Whale Bot

An autonomous, multi-bot trading research system built entirely on free-tier infrastructure. Runs 24/5 on GitHub Actions, trades a paper Alpaca account, logs everything to Airtable, and serves a live dashboard via Streamlit Cloud.

**Status:** Active research project. Not a profitable strategy. Not financial advice.

---

## What This Is

Seven independent bots run on staggered schedules, each testing a different hypothesis about how markets move. All data flows into a shared Airtable base for analysis. A Streamlit dashboard renders both live trading state and a research lab with astrological signals, reflexive herding detection, and adaptive signal weights.

**The goal** is not to make money on $100. It's to build infrastructure that can answer one question after 90 days of data: *does any of these bots beat buy-and-hold SPY?*

---

## The Bots

| Bot | Role | Watchlist | Exit Style | Schedule |
|-----|------|-----------|------------|----------|
| `bot.py` (v10) | 8-signal confluence trader | NVDA, GOOGL, META, AMZN | Fixed bracket (-2.5% / +5%) | :00, :30 |
| `bot_v3.py` | Backtested 3-rule strategy | SPY, QQQ, AAPL, MSFT | Trailing stop (1.5%) | :05, :35 |
| `bot_v3_fixed.py` | Same entries as v3 | SPY, QQQ, AAPL, MSFT | Fixed bracket (-2.5% / +5%) | :10, :40 |
| `bot_v3_chandelier.py` | Same entries as v3 | SPY, QQQ, AAPL, MSFT | Chandelier ATR trail | :15, :45 |
| `bot_shadow.py` | Signal logger only | All 8 tickers | Never trades | :20, :50 |
| `bot_astro.py` | Planetary data logger | NYSE + local | Never trades | Daily 14:00 UTC |
| `bot_reflexive.py` | Herding/volatility detector | N/A | Never trades | :25, :55 |

The three v3 variants use **identical entry logic** but different exits. This isolates exit quality from entry quality. Whichever exit produces better P&L on the same signals wins.

---

## Signals

The v10 bot scores each ticker across eight weighted signals:

| Signal | Weight | Source | Condition |
|--------|--------|--------|-----------|
| Regime | 1.0 | yfinance SPY | SPY > 200-day MA |
| RSI | 1.0 | yfinance | 35 < RSI < 55 |
| SMA50 | 1.0 | yfinance | Price > 50-day MA |
| Sentiment | 1.0 | yfinance news + VADER | Mean compound > 0.1 |
| Congressional | 2.0 | Bargo (free tier) | Buy in last 30 days |
| Insider | 2.0 | Form4API (free tier) | Form 4 purchase in 30 days |
| PEAD | 1.0 | yfinance earnings | Earnings beat in 30 days |
| Options Flow | 2.0 | GammaRips MCP (free) | In bullish pool |

A dynamic threshold (base 4.0) adjusts upward on high VIX, earnings season, existing holdings, and Monday mornings. Scores above threshold trigger a trade.

**Thompson Sampling** (in `adaptive_allocator.py`) continuously reweights signals based on realized outcomes. The blend starts 50/50 static/adaptive and shifts to 30/70 once enough trades accumulate.

---

## Risk Controls

| Control | Default | Where |
|---------|---------|-------|
| Per-trade risk | 2% of equity | All bots |
| Stop-loss | -2.5% | Bracket orders |
| Max concurrent positions (per bot) | 2 | All bots |
| Tactical cap (per bot) | 10% of equity | All bots |
| Global exposure cap | 30% of equity | `would_exceed_global_cap()` |
| Correlation filter | 0.70 threshold | `positions_correlation_risk()` |
| Drawdown kill switch | -5% from peak | `drawdown_check()` |
| Auto-halt | 3 consecutive errors | `should_halt()` |

The global cap and correlation filter prevent the bots from stacking the same risk. If you hold QQQ and the bot wants SPY (correlation ~0.95), the trade is blocked.

---

## Infrastructure

- **Compute:** GitHub Actions (free tier, 2,000 min/month)
- **Scheduler:** cron-job.org (external — GitHub's native cron is unreliable)
- **Broker:** Alpaca paper trading
- **Database:** Airtable (free tier, 1,000 records/base)
- **Dashboard:** Streamlit Community Cloud (free tier)
- **Alerts:** Telegram bot
- **Astro data:** pyswisseph (self-hosted, no API key)
- **Vedic data:** Vedaksha (optional, graceful fallback)

**Total monthly cost: $0.**

---

## Repository Structure

```

.
├── .github/workflows/          # 9 GitHub Actions workflows
├── .streamlit/                 # Streamlit Cloud secrets template
├── scripts/
│   └── weekly_ic_update.py     # Computes IC per signal weekly
├── tests/
│   └── test_scoring.py         # Pure-function unit tests
├── adaptive_allocator.py       # Thompson Sampling weight engine
├── bot.py                      # v10 trading bot
├── bot_astro.py                # Astrology signal logger
├── bot_reflexive.py            # Herding detector
├── bot_shadow.py               # Signal-only logger
├── bot_v3.py                   # Trailing-stop bot
├── bot_v3_chandelier.py        # ATR-trail bot
├── bot_v3_fixed.py             # Fixed-bracket bot
├── common.py                   # Shared utilities
├── dashboard.py                # Streamlit app
├── requirements.txt
├── signal_weights.json         # Static signal weights
└── visualizer.py               # Plotly animations + LLM narrator

```

---

## Setup

### 1. Airtable Tables

Create a base with these tables. Column names must match exactly.

**Trades**
| Column | Type |
|--------|------|
| Timestamp | DateTime (ISO) |
| Symbol | Text |
| Side | Single select (BUY / SELL) |
| Qty | Number |
| Price | Number (2 dec) |
| Stop | Number (2 dec) |
| Target | Number (2 dec) |
| Score | Number (2 dec) |
| Threshold | Number (2 dec) |
| Signal Breakdown | Long text |

**Exits**
| Column | Type |
|--------|------|
| Exit Timestamp | DateTime |
| Symbol | Text |
| Entry Price | Number |
| Exit Price | Number |
| Qty | Number |
| Exit Reason | Single select (STOP_LOSS / TAKE_PROFIT / MANUAL / OTHER) |
| PnL Dollars | Number (allow negative) |
| PnL Percent | Number (allow negative) |
| Peak Price | Number (4 dec) |
| Signals That Fired | Long text |
| Signal Score | Number |
| Signal Threshold | Number |
| Source | Single select (v3 / v10 / v3_fixed / v3_chandelier / manual) |
| Fees | Number (4 dec) |

**Fills**
| Column | Type |
|--------|------|
| Timestamp | DateTime |
| Symbol | Text |
| Order Type | Single select (Entry / Stop / Target / Manual) |
| Expected Price | Number (4 dec) |
| Actual Fill Price | Number (4 dec) |
| Slippage ($) | Number (4 dec, allow negative) |
| Slippage (%) | Number (4 dec, allow negative) |
| Order ID | Text |

**Runs**
| Column | Type |
|--------|------|
| Timestamp | DateTime |
| Bot | Single select (v3 / v10 / v3_fixed / v3_chandelier / shadow / astro / reflexive) |
| Status | Single select (ok / market_closed / error / no_signal / traded / skipped) |
| Equity | Number |
| Positions Held | Number |
| Threshold | Number |
| Top Candidate | Text |
| Top Score | Number |
| Action Taken | Long text |
| Error | Long text |

**Signals**
| Column | Type |
|--------|------|
| Timestamp | DateTime |
| Symbol | Text |
| Regime | Checkbox |
| RSI | Checkbox |
| SMA | Checkbox |
| Sentiment | Checkbox |
| Sentiment Score | Number (4 dec) |
| Congress | Checkbox |
| Insider | Checkbox |
| PEAD | Checkbox |
| Flow | Checkbox |
| Source | Text |

**Astro**
| Column | Type |
|--------|------|
| Timestamp | DateTime |
| Reference | Single select (NYSE / Local) |
| Sun_Sign | Text |
| Sun_Degree | Number |
| Moon_Sign | Text |
| Moon_Phase | Text |
| Moon_Illumination | Number |
| Mercury_Retrograde | Checkbox |
| Venus_Retrograde | Checkbox |
| Mars_Retrograde | Checkbox |
| Jupiter_Sign | Text |
| Jupiter_Degree | Number |
| Saturn_Sign | Text |
| Saturn_Degree | Number |
| Nakshatra | Text |
| Current_Dasha | Text |
| Astro_Score | Number (allow negative) |
| Astro_Hierarchy | Long text |
| Vedic_House_2 | Text |
| Vedic_House_5 | Text |
| Vedic_House_8 | Text |
| Vedic_House_11 | Text |

**Reflexive**
| Column | Type |
|--------|------|
| Timestamp | DateTime |
| VIX_Spot | Number |
| VIX_9D | Number |
| VIX_1M | Number |
| VIX_Term_Structure | Single select (Contango / Backwardation) |
| SPY_VIX_Correlation | Number (4 dec) |
| Cross_Ticker_Correlation | Number (4 dec) |
| Volume_Z_Score | Number (2 dec) |
| Reflexive_Intensity | Number (2 dec) |
| Herding_Flag | Checkbox |
| Notes | Long text |

**MAB_Weights**
| Column | Type |
|--------|------|
| Timestamp | DateTime |
| Bot | Text |
| Signal | Text |
| Alpha | Number (4 dec) |
| Beta | Number (4 dec) |
| Weight | Number (4 dec) |

**Peak**
| Column | Type |
|--------|------|
| Key | Text |
| Value | Number (4 dec) |

Seed with one row: `peak_equity` / `100000`.

### 2. GitHub Secrets

Add at `Settings → Secrets and variables → Actions`:

```

ALPACA_API_KEY
ALPACA_SECRET_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
AIRTABLE_API_KEY
AIRTABLE_BASE_ID
AIRTABLE_TABLE_ID
AIRTABLE_EXITS_TABLE_ID
AIRTABLE_FILLS_TABLE_ID
AIRTABLE_RUNS_TABLE_ID
AIRTABLE_SIGNALS_TABLE_ID
AIRTABLE_ASTRO_TABLE_ID
AIRTABLE_REFLEXIVE_TABLE_ID
AIRTABLE_MAB_TABLE_ID
AIRTABLE_PEAK_TABLE_ID
BARGO_API_KEY
FORM4API_KEY
KALSHI_API_KEY_ID
KALSHI_PRIVATE_KEY
LOCAL_LAT
LOCAL_LON

```

Optional:
```

GLOBAL_EXPOSURE_CAP_PCT     # default 0.30
ANTHROPIC_API_KEY           # for LLM dashboard narration

```

### 3. Streamlit Cloud

Add the same Airtable secrets to Streamlit's secrets panel (Settings → Secrets). Only Airtable tables are needed there — no Alpaca or trading credentials.

### 4. External Scheduler

GitHub's built-in cron is unreliable. Create jobs at cron-job.org that POST to:

```

https://api.github.com/repos/YOUR_USERNAME/whale-bot/actions/workflows/WORKFLOW_FILE.yml/dispatches

```

With headers:
```

Authorization: Bearer <github_pat>
Accept: application/vnd.github+json
Content-Type: application/json

```

Body: `{"ref":"main"}`

Schedule each workflow per the table in "The Bots" section.

### 5. Local Development

```bash
pip install -r requirements.txt
pytest tests/ -v          # Verify scoring logic
python bot.py             # Test a single run
```

---

Development Principles

1. Multi-bot isolation. Never modify one bot to fix another. Each tests an independent hypothesis.
2. Every exit is logged with a Source. So attribution is never ambiguous.
3. Fees are estimated on every exit. Real paper P&L is net of regulatory costs.
4. Global risk controls outrank per-bot logic. No amount of edge justifies concentrated exposure.
5. Signal weights come from data, not intuition. Thompson Sampling replaces manual weight-setting.
6. No new features without 30+ trades of supporting data.

---

Testing

```bash
python -m pytest tests/ -v
```

Covers:

· Score multiplier bounds
· Dynamic threshold regime blocks
· ATR multiplier clamping
· NaN/Inf cleaning for JSON

---

Limitations

· No proven edge. Backtests showed +0.107% per trade across regimes; real slippage may erase it.
· $100 paper account. Cannot trade whole shares of any watchlist ticker with real money.
· Free-tier limits. Airtable caps at 1,000 records/base; Airtable will need upgrading at ~100 trades.
· No live-money testing. Paper fills are optimistic. Real results will be worse.
· Unvalidated alternative data. Congressional, insider, and flow signals carry 2x weight but zero live-trade validation.

---

Not Financial Advice

This is a personal research project. The code is public for educational purposes. Do not use it to trade real money without extensive independent validation.

---

License

Personal project. Use at your own risk.
