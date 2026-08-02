"""Run a backtest and generate reports.

Usage:
    python -m scripts.run_backtest --symbol NIFTY --start 2020-01-01 --end 2025-12-31
    python -m scripts.run_backtest --symbol NIFTY --capital 1000000
"""

import argparse
import json
from datetime import date
from pathlib import Path

from backtester.engine import BacktestEngine, MultiSymbolBacktestEngine
from config.logging_config import setup_logging
from config.settings import settings
from reports.tearsheet import TearsheetGenerator
from strategies.momentum_futures import MomentumFuturesCoveredCall
from strategies.ranker import MomentumRanker
from strategies.screener import UniverseScreener


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--symbol", default="NIFTY", help="Symbol to backtest")
    parser.add_argument("--start", default="2020-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
    parser.add_argument("--capital", type=float, default=None, help="Initial capital")
    parser.add_argument(
        "--strategy",
        default="config/strategies/momentum_futures_covered_call.yaml",
        help="Strategy YAML path",
    )
    parser.add_argument("--output", default="reports/output", help="Output directory")
    parser.add_argument("--no-tearsheet", action="store_true", help="Skip HTML tearsheet")
    parser.add_argument("--json-output", default=None, help="Export results as JSON")
    parser.add_argument("--multi", action="store_true", help="Multi-symbol universe backtest")
    parser.add_argument(
        "--universe", default=None,
        help="Comma-separated symbols for multi-symbol mode",
    )
    args = parser.parse_args()

    setup_logging()

    strategy = MomentumFuturesCoveredCall.from_yaml(Path(args.strategy))
    capital = args.capital or settings.initial_capital
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.multi:
        universe = args.universe.split(",") if args.universe else None
        if strategy.config.screening is None or strategy.config.ranking is None:
            print("Error: strategy YAML must have screening and ranking sections for --multi")
            return

        screener = UniverseScreener(strategy.config.screening)
        ranker = MomentumRanker(strategy.config.ranking)

        engine = MultiSymbolBacktestEngine(
            strategy=strategy,
            screener=screener,
            ranker=ranker,
            universe=universe,
            initial_capital=capital,
            parquet_dir=settings.parquet_dir,
            margin_pct=strategy.config.capacity.margin_pct,
            max_position_value_pct=strategy.config.capacity.max_position_value_pct,
            max_total_margin_pct=strategy.config.capacity.max_total_margin_pct,
        )
        result = engine.run(start, end)
        label = "FO_UNIVERSE"
    else:
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=capital,
            parquet_dir=settings.parquet_dir,
        )
        result = engine.run(args.symbol, start, end)
        label = args.symbol

    reporter = TearsheetGenerator(result)
    reporter.print_summary()

    if not args.no_tearsheet:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        tearsheet_path = output_dir / f"{label}_{start}_{end}_tearsheet.html"
        reporter.generate_html(tearsheet_path)

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\nJSON results written to {json_path}")

    if result.regime_results:
        regime_df = reporter.generate_regime_report()
        if not regime_df.empty:
            print("\n--- Regime Breakdown ---")
            print(regime_df.to_string(index=False))


if __name__ == "__main__":
    main()
