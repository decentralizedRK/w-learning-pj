# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

QuantOS — a personal quantitative trading platform for Indian F&O markets (NSE/NFO). It screens the F&O universe, ranks stocks by momentum factors, backtests strategies with realistic Indian cost models, and generates signals for live trading via Zerodha Kite or manual execution on Groww.

## Commands

```bash
uv sync                                    # install dependencies
uv run pytest                              # run all tests
uv run pytest tests/test_strategies/       # run one test directory
uv run pytest tests/test_backtester/test_costs.py -k "test_futures"  # run a single test
uv run ruff check .                        # lint
uv run ruff check . --fix                  # lint and auto-fix

# Data pipeline
python -m scripts.build_backtest_db --symbols NIFTY --start 2020-01-01 --end 2025-12-31
python -m scripts.build_backtest_db --symbols NIFTY --equity-only  # skip F&O bhavcopy

# Backtest
python -m scripts.run_backtest --symbol NIFTY --start 2020-01-01 --end 2025-12-31
python -m scripts.run_backtest --multi  # multi-symbol universe backtest (requires screening/ranking in YAML)
python -m scripts.run_backtest --multi --universe RELIANCE,TCS,INFY  # specific universe
```

## Architecture

### Data flow

```
Data Sources → Parquet files → DuckDB (in-memory, reads Parquet globs) → enriched DataFrames → signals → backtest/live
```

1. **Fetchers** (`data/fetchers/`) pull from yfinance (equity OHLCV) and jugaad-data (F&O bhavcopy). Kite fetcher exists for live data.
2. **ParquetStore** writes to `data_store/parquet/{equity,futures,options}/{SYMBOL}/*.parquet`
3. **DuckDBEngine** queries Parquet files directly via glob patterns — no persistent database, just in-memory DuckDB reading Parquet.

### Strategy system: rules are YAML, not code

The core design principle: trading rules live in YAML config files (`config/strategies/`), interpreted by a generic `RuleEvaluator`. Never hardcode entry/exit conditions in Python.

A strategy YAML defines: entry conditions, exit conditions, stop loss, position sizing, hedge parameters, roll rules, screening filters, and ranking factors — all as data.

`StrategyConfig` (Pydantic model in `strategies/rule_schema.py`) is the schema for these YAML files. It contains nested configs: `EntryRuleConfig`, `ExitRuleConfig`, `StopLossConfig`, `ScreenConfig`, `RankConfig`, etc.

`RuleEvaluator` evaluates conditions generically — it compares indicator column values from a DataFrame row against thresholds or other column references. Entry = ALL conditions must pass. Exit = ANY condition triggers.

### Multi-symbol pipeline (the full loop)

For `--multi` backtests, the pipeline is: **Screen → Rank → Enter → Manage → Exit**

1. **UniverseScreener** filters the F&O universe on each trading date using screening conditions from YAML
2. **MomentumRanker** scores candidates by weighted composite of: ROC-20, ADX, relative strength vs NIFTY, OI buildup score, volume ratio
3. **Portfolio** enforces position limits (max 3 concurrent), risk sizing (0.5% per trade), and margin checks
4. **BacktestEngine** iterates daily: manage existing positions (trailing stops, targets, signal exits, expiry rolls), then screen-rank-enter new ones

### Cost model

`IndianFnOCostModel` applies realistic Indian F&O costs: STT (sell-side only for futures), exchange charges, SEBI fee, GST, stamp duty, flat brokerage. Every trade — backtest and live — must go through this model.

### Hedging

Long futures positions are hedged by selling OTM covered calls (3-5% OTM). Hedge selection uses `GreeksCalculator` (Black-Scholes via mibian). Hedge P&L is tracked per-position through entry and exit.

### Broker abstraction

`BaseBroker` → `ZerodhaBroker` (live via Kite API) or `ManualBroker` (signal-only, for manual execution on Groww). The broker layer is separate from the backtest engine.

## Conventions

- Python 3.12+, type hints on all functions
- `ta` library for indicators (NOT pandas-ta — incompatible with Python 3.14)
- Pydantic models for all data structures and configs
- Loguru for logging (no stdlib logging)
- Ruff for linting and formatting (line length 100, target py312)
- All monetary values in INR
- Tests mirror source structure in `tests/`
- Settings via pydantic-settings with `QOS_` env prefix and `.env` file
- OI buildup classification uses the `OIBuildup` StrEnum: long_buildup, short_buildup, long_unwinding, short_covering
- Lot sizes are maintained in `config/constants.py` (`FO_LOT_SIZES` dict) with historical lot size changes for indices in `LOT_SIZE_HISTORY`

## Key design rules

- Rules are data (YAML), not code — the RuleEvaluator interprets them generically
- Indian F&O cost model must be applied to every trade
- Position sizing: 0.5% account risk per trade, max 3 concurrent positions
- All strategies must be backtested across: COVID crash, 2021 bull, 2022 bear, election, budget, RBI policy events
