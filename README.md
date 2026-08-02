# QuantOS — Quant Operating System

Personal quantitative trading platform for Indian F&O markets (NSE/NFO).

QuantOS screens the F&O universe, ranks stocks by momentum factors, backtests strategies with realistic Indian cost models, and generates signals for live trading via Zerodha Kite. It runs fully automated on GitHub Actions — screening, backtesting, margin checks, P&L tracking, and a live dashboard — all from a single repo.

---

## What Does It Do?

1. **Screens** ~200 F&O stocks every evening for swing trade candidates
2. **Ranks** them by momentum (ROC, ADX, relative strength, OI buildup, volume)
3. **Backtests** your strategy across 5+ years of data with real Indian F&O costs (STT, GST, stamp duty, exchange charges)
4. **Manages risk** — 0.5% capital risk per trade, max 3 concurrent positions, 75% total margin cap with mark-to-market tracking
5. **Hedges** every long futures position with an OTM covered call
6. **Executes trades** on Zerodha Kite (or generates signals for manual execution on Groww)
7. **Publishes a live dashboard** on GitHub Pages showing positions, P&L, win rate, and index prices

---

## Quick Start

### Prerequisites

- **Python 3.12+** — check with `python --version`
- **[uv](https://docs.astral.sh/uv/)** — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Git** — to clone the repo
- **Zerodha Kite Connect** subscription (optional, only needed for live trading)

### 1. Clone and Install

```bash
git clone <repo-url>
cd quant-os
uv sync
```

This installs all dependencies in an isolated virtual environment. No `pip install`, no `venv` — `uv` handles everything.

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your settings:

```bash
# Required for live trading (skip if only backtesting)
QOS_KITE_API_KEY=your_api_key_here
QOS_KITE_API_SECRET=your_api_secret_here
QOS_KITE_ACCESS_TOKEN=           # refreshed daily, see "Kite Auth" section below

# Trading parameters (defaults are fine to start)
QOS_INITIAL_CAPITAL=1000000      # starting capital in INR
QOS_RISK_PER_TRADE_PCT=0.5       # risk 0.5% of capital per trade
QOS_MAX_CONCURRENT_POSITIONS=3   # max open positions at once

# Data storage (defaults are fine)
QOS_DATA_DIR=data_store
QOS_PARQUET_DIR=data_store/parquet
```

### 3. Download Data

```bash
# Download NIFTY equity + F&O data (2020-2025)
uv run python -m scripts.build_backtest_db --symbols NIFTY --start 2020-01-01 --end 2025-12-31

# Equity data only (much faster, enough for initial backtesting)
uv run python -m scripts.build_backtest_db --symbols NIFTY --equity-only

# Multiple symbols
uv run python -m scripts.build_backtest_db --symbols RELIANCE,TCS,INFY --equity-only
```

### 4. Run Your First Backtest

```bash
uv run python -m scripts.run_backtest --symbol NIFTY --start 2020-01-01 --end 2025-12-31
```

This prints a full performance summary (P&L, CAGR, Sharpe, max drawdown, win rate) and generates an HTML tearsheet in `reports/output/`.

### 5. Screen for Trade Candidates

```bash
# Screen the full F&O universe and show top 10
uv run python -m scripts.run_screener --top 10

# Export as JSON
uv run python -m scripts.run_screener --top 10 --output signals.json
```

---

## Usage Guide

### Backtesting

```bash
# Single symbol with custom capital
uv run python -m scripts.run_backtest --symbol NIFTY --capital 5000000

# Multi-symbol backtest across the full F&O universe
uv run python -m scripts.run_backtest --multi --start 2020-01-01 --end 2025-12-31

# Multi-symbol with specific stocks
uv run python -m scripts.run_backtest --multi --universe RELIANCE,TCS,INFY

# Multi-symbol with market-cap segments (large-cap, mid-cap, or small-cap F&O stocks)
# Set universe in your strategy YAML to: LARGECAP_FO, MIDCAP_FO, SMALLCAP_FO
# You can combine segments — e.g., universe: [LARGECAP_FO, MIDCAP_FO] screens both

# Export results as JSON (for the dashboard)
uv run python -m scripts.run_backtest --symbol NIFTY --json-output results.json

# Skip HTML tearsheet
uv run python -m scripts.run_backtest --symbol NIFTY --no-tearsheet

# Use a custom strategy file
uv run python -m scripts.run_backtest --symbol NIFTY --strategy config/strategies/my_strategy.yaml
```

### Live Trading (Zerodha)

```bash
# Check current margin utilization
uv run python -m scripts.check_margins

# Check P&L of open positions
uv run python -m scripts.update_pnl

# Export P&L as JSON
uv run python -m scripts.update_pnl --json-output pnl.json

# Execute a trade (dry run first!)
uv run python -m scripts.execute_trade \
  --symbol RELIANCE --exchange NFO --quantity 250 \
  --order-type LIMIT --price 2500 --transaction-type BUY \
  --dry-run

# Execute for real (remove --dry-run)
uv run python -m scripts.execute_trade \
  --symbol RELIANCE --exchange NFO --quantity 250 \
  --order-type LIMIT --price 2500 --transaction-type BUY
```

### Kite Access Token

Zerodha Kite access tokens **expire daily**. Before any live trading:

1. Log in to [Kite Connect](https://kite.trade/connect/login)
2. Complete the login flow to get a new `request_token`
3. Exchange it for an `access_token` using your API key/secret
4. Update `QOS_KITE_ACCESS_TOKEN` in your `.env` file (local) or GitHub secret (CI)

If the token is expired, scripts exit gracefully with a clear error message — nothing breaks.

---

## Strategy System

**Trading rules live in YAML, not Python.** You never hardcode entry/exit conditions. Instead, a generic rule evaluator reads conditions from config files.

The default strategy is in [`config/strategies/momentum_futures_covered_call.yaml`](config/strategies/momentum_futures_covered_call.yaml).

### How It Works

```
Screen F&O Universe → Rank by Momentum Score → Enter Top Candidates → Manage Positions → Exit
```

**Entry conditions** (ALL must pass):
- Price above EMA(20), EMA(20) above EMA(50) — trend confirmation
- ADX > 25 — strong trend
- RSI between 50-70 — momentum without being overbought
- Volume above 20-day average — institutional participation
- Positive OI buildup — smart money confirmation
- Put-call ratio >= 0.9 — bullish sentiment

**Exit conditions** (ANY triggers exit):
- EMA(20) crosses below EMA(50) — trend reversal
- RSI drops below 40 — momentum loss

**Risk management:**
- 0.5% of capital risked per trade
- Max 3 concurrent positions
- 75% total margin utilization cap (configurable via YAML)
- ATR-based trailing stop-loss
- 2:1 risk-reward target

**Hedging:**
- Every long futures position gets a covered call (3-5% OTM)
- Premium collected reduces cost basis
- Hedge tracks through entry and exit

### Creating Your Own Strategy

Copy and modify the default YAML:

```bash
cp config/strategies/momentum_futures_covered_call.yaml config/strategies/my_strategy.yaml
```

Key sections you can customize:

```yaml
# Which stocks to screen
universe:
  - "LARGECAP_FO"        # Nifty 50 stocks in F&O
  - "MIDCAP_FO"           # Nifty Midcap 150 stocks in F&O
  # - "SMALLCAP_FO"       # Nifty Smallcap 250 stocks in F&O
  # - "FO_UNIVERSE"       # all ~200 F&O stocks
  # - "RELIANCE"          # or list specific symbols

# Entry conditions — ALL must pass
entry:
  conditions:
    - indicator: "adx"
      comparison: ">"
      value: 25
    - indicator: "rsi"
      comparison: "between"
      value_min: 50
      value_max: 70

# Exit conditions — ANY triggers exit
exit:
  conditions:
    - indicator: "rsi"
      comparison: "<"
      value: 40

# Risk parameters
position_sizing:
  risk_per_trade_pct: 0.5
  max_concurrent_positions: 3

capacity:
  margin_pct: 20.0               # per-trade margin requirement
  max_position_value_pct: 30.0   # max single position as % of capital
  max_total_margin_pct: 75.0     # total margin cap (keeps 25% buffer)

# Ranking factors for screening (weights must sum to 1.0)
ranking:
  factors:
    - name: "roc_20"
      weight: 0.30
    - name: "adx"
      weight: 0.25
    - name: "relative_strength"
      weight: 0.20
    - name: "oi_buildup_score"
      weight: 0.15
    - name: "volume_ratio"
      weight: 0.10
  top_n: 5
```

Available indicators: `close`, `ema_20`, `ema_50`, `adx`, `rsi`, `volume`, `volume_sma_20`, `atr`, `pcr`, `positive_oi_buildup`, `roc_20`, `relative_strength`, `oi_buildup_score`, `volume_ratio`, `lot_value`

Available comparisons: `>`, `>=`, `<`, `<=`, `==`, `between`

---

## GitHub Actions (Automated Workflows)

QuantOS runs fully automated on GitHub Actions. Push to GitHub and enable the workflows — no server needed.

### Setup

1. Push the repo to GitHub
2. Go to **Settings > Secrets and variables > Actions** and add:
   - `QOS_KITE_API_KEY`
   - `QOS_KITE_API_SECRET`
   - `QOS_KITE_ACCESS_TOKEN` (update daily)
3. Go to **Settings > Pages** and set source to `gh-pages` branch
4. Workflows will run on their schedules automatically

### Workflow Summary

| Workflow | Schedule | What It Does |
|---|---|---|
| **CI** | Every push/PR | Runs tests + lint |
| **Daily Screener** | Mon-Fri 12:00 UTC (5:30 PM IST) | Screens F&O universe, uploads signals |
| **Backtest** | Manual trigger | Runs backtest with custom params, publishes results to dashboard |
| **Check Margins** | Manual trigger | Fetches margin utilization from Zerodha |
| **Update P&L** | Every 2hrs during market (9/11/13/15 IST) | Fetches live P&L from Zerodha |
| **Publish Dashboard** | Every 2hrs during market | Updates the live dashboard on GitHub Pages |
| **Execute Trade** | Manual trigger | Places an order on Zerodha (with configurable params) |
| **Update F&O Segments** | Every Sunday 5:30 PM IST | Refreshes large/mid/small-cap F&O stock lists from NSE |

### Running Workflows Manually

Go to **Actions** tab in your GitHub repo > select a workflow > click **Run workflow**.

For **Backtest**, you can configure:
- Symbol, date range, capital
- Multi-symbol mode with universe selection
- Strategy YAML path

For **Execute Trade**, you specify:
- Symbol, exchange, quantity, order type, price, transaction type

---

## Live Dashboard

A dark-themed trading dashboard hosted on GitHub Pages, updated every 2 hours during market hours.

### What It Shows

**Live View** (`index.html`):
- Index ticker cards — NIFTY 50, BANKNIFTY, Midcap Select, Smallcap 100 with live prices
- Stats — Total P&L, Win Rate, Avg Risk/Reward, Margin Utilization
- Open positions table with per-position P&L
- Completed orders table

**Backtest View** (`backtest.html`):
- Performance metrics — Net P&L, CAGR, Sharpe, Max Drawdown, Win Rate, Profit Factor
- Equity curve chart
- Regime breakdown (COVID crash, bull/bear markets, events)
- Full trade log

### Accessing the Dashboard

After enabling GitHub Pages on the `gh-pages` branch:

```
https://<your-username>.github.io/<repo-name>/           # live view
https://<your-username>.github.io/<repo-name>/backtest.html  # backtest results
```

The dashboard auto-refreshes every 60 seconds when open in a browser.

---

## Market-Cap Segments

QuantOS categorizes F&O stocks into segments based on NSE index membership:

| Segment | YAML Key | Description |
|---|---|---|
| Large-cap | `LARGECAP_FO` | Nifty 50 stocks that are in F&O (~49 stocks) |
| Mid-cap | `MIDCAP_FO` | Nifty Midcap 150 stocks that are in F&O (~91 stocks) |
| Small-cap | `SMALLCAP_FO` | Nifty Smallcap 250 stocks that are in F&O (~22 stocks) |
| Full universe | `FO_UNIVERSE` | All ~200 F&O stocks |

These lists are auto-updated weekly (Sunday evening) via GitHub Actions by fetching the latest NSE index constituents and intersecting with the current F&O universe.

You can combine segments in your strategy YAML:
```yaml
universe:
  - "LARGECAP_FO"
  - "MIDCAP_FO"
```
This screens the union of both segments.

---

## Cost Model

Every trade (backtest and live) passes through `IndianFnOCostModel` which applies:

| Cost | Rate |
|---|---|
| STT (futures) | 0.0125% on sell side |
| STT (options) | 0.0625% on sell side |
| Exchange charges | 0.00345% (NSE) |
| SEBI fee | 0.0001% |
| GST | 18% on brokerage + exchange charges |
| Stamp duty | 0.003% on buy side |
| Brokerage | Flat (Zerodha-style) |

This ensures backtest results closely match real trading P&L.

---

## Project Structure

```
quant-os/
├── config/                  Settings, constants, strategy YAML files
│   ├── strategies/          YAML strategy definitions (rules are data)
│   ├── fo_segments.py       Large/mid/small-cap F&O stock lists
│   ├── constants.py         F&O lot sizes, lot size history, repo rate
│   └── settings.py          Pydantic settings (env vars with QOS_ prefix)
├── data/
│   ├── fetchers/            yfinance (equity), jugaad-data (F&O bhavcopy), Kite (live)
│   ├── storage/             ParquetStore (year-partitioned) + DuckDB engine
│   └── models.py            Pydantic data models (OHLCV, futures, options, OI)
├── indicators/              Technical (EMA, ADX, RSI, ATR), OI analysis, Greeks
├── strategies/              Rule evaluator, momentum strategy, screener, ranker
│   └── rule_schema.py       Pydantic schema for strategy YAML
├── backtester/              Simulation engine, portfolio, cost model, regime analysis
├── broker/                  Zerodha Kite (live) + Manual (signal-only for Groww)
├── reports/                 QuantStats HTML tearsheet generation
├── scripts/                 CLI tools (see below)
├── dashboard/               GitHub Pages HTML dashboard
│   ├── index.html           Live trading view
│   └── backtest.html        Backtest results view
├── .github/workflows/       8 automated workflows
└── tests/                   115+ tests across all modules
```

### Scripts

| Script | Purpose |
|---|---|
| `build_backtest_db` | Download historical data (equity + F&O) to Parquet files |
| `run_backtest` | Run single/multi-symbol backtests, generate tearsheets |
| `run_screener` | Screen and rank F&O stocks for trade candidates |
| `check_margins` | Show current margin utilization from Zerodha |
| `update_pnl` | Fetch and display P&L of open positions |
| `execute_trade` | Place orders on Zerodha (supports dry run) |
| `publish_dashboard_data` | Fetch live data from Kite, write JSON for dashboard |
| `update_fo_segments` | Refresh market-cap segment lists from NSE |

All scripts are run with `uv run python -m scripts.<name>`. Use `--help` on any script for options.

---

## Development

```bash
# Install dependencies
uv sync

# Run all tests (115+)
uv run pytest

# Run a specific test file
uv run pytest tests/test_backtester/test_portfolio.py

# Run a single test
uv run pytest tests/test_backtester/test_costs.py -k "test_futures"

# Run with coverage
uv run pytest --cov

# Lint
uv run ruff check .

# Lint and auto-fix
uv run ruff check . --fix
```

### Architecture Overview

```
Data Sources → Parquet files → DuckDB (in-memory) → enriched DataFrames → signals → backtest/live
```

1. **Fetchers** pull from yfinance (equity OHLCV) and jugaad-data (F&O bhavcopy). Kite fetcher handles live data.
2. **ParquetStore** writes year-partitioned files to `data_store/parquet/{equity,futures,options}/{SYMBOL}/`
3. **DuckDB** queries Parquet files directly via glob patterns — no persistent database, just in-memory reads.
4. **RuleEvaluator** interprets YAML conditions against enriched DataFrame rows. Entry = ALL conditions pass. Exit = ANY condition triggers.
5. **Portfolio** manages positions with mark-to-market margin tracking and trailing stops.
6. **CostModel** applies realistic Indian F&O costs to every trade.

### Key Design Principles

- **Rules are data, not code** — trading conditions live in YAML, interpreted by a generic rule evaluator
- **Every trade pays real costs** — the Indian F&O cost model is applied to both backtests and live trades
- **Mark-to-market margin** — margin utilization tracks current prices, not entry prices, and accounts for unrealized P&L
- **Regime-aware testing** — strategies must be tested across COVID crash, 2021 bull, 2022 bear, election, budget, and RBI events

---

## Configuration Reference

All settings use the `QOS_` env prefix and can be set in `.env`:

| Variable | Description | Default |
|---|---|---|
| `QOS_KITE_API_KEY` | Zerodha Kite Connect API key | (empty) |
| `QOS_KITE_API_SECRET` | Zerodha Kite Connect API secret | (empty) |
| `QOS_KITE_ACCESS_TOKEN` | Daily access token | (empty) |
| `QOS_INITIAL_CAPITAL` | Starting capital in INR | `1000000` |
| `QOS_RISK_PER_TRADE_PCT` | Risk per trade as % of capital | `0.5` |
| `QOS_MAX_CONCURRENT_POSITIONS` | Max simultaneous positions | `3` |
| `QOS_DATA_DIR` | Root data directory | `data_store` |
| `QOS_PARQUET_DIR` | Parquet file storage | `data_store/parquet` |
| `QOS_DATABASE_URL` | PostgreSQL connection (optional) | `postgresql+psycopg://...` |

### Strategy YAML Config (capacity section)

These go in your strategy YAML under `capacity:`:

| Field | Description | Default |
|---|---|---|
| `margin_pct` | Per-trade margin requirement (%) | `20.0` |
| `max_position_value_pct` | Max single position as % of capital | `30.0` |
| `max_total_margin_pct` | Total margin cap across all positions (%) | `75.0` |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ with strict type hints |
| Data | Pandas, NumPy, PyArrow/Parquet, DuckDB |
| Indicators | `ta` library (NOT pandas-ta) |
| Config | Pydantic models + pydantic-settings |
| Broker | Zerodha Kite Connect |
| Analytics | QuantStats, mibian (Black-Scholes Greeks) |
| Dashboard | Vanilla HTML/CSS/JS on GitHub Pages |
| CI/CD | GitHub Actions (8 workflows) |
| Testing | pytest (115+ tests) |
| Linting | Ruff |
| Package Manager | uv |

---

## License

Private — not licensed for redistribution.
