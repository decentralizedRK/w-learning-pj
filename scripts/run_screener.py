"""Run daily stock screener for F&O universe.

Usage:
    python -m scripts.run_screener
    python -m scripts.run_screener --top 10 --output signals.json
    python -m scripts.run_screener --universe RELIANCE,TCS,INFY
"""

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger

from config.fo_segments import SEGMENT_MAP
from config.logging_config import setup_logging
from data.fetchers import get_fetcher
from data.fetchers.nse_symbols import fetch_fo_universe, get_lot_size
from indicators.technical import TechnicalIndicators
from strategies.momentum_futures import MomentumFuturesCoveredCall
from strategies.ranker import MomentumRanker
from strategies.screener import UniverseScreener


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily F&O stock screener")
    parser.add_argument(
        "--strategy",
        default="config/strategies/momentum_futures_covered_call.yaml",
        help="Strategy YAML path",
    )
    parser.add_argument(
        "--universe", default=None,
        help="Comma-separated symbols (default: full F&O universe)",
    )
    parser.add_argument("--top", type=int, default=5, help="Show top N ranked candidates")
    parser.add_argument("--output", default=None, help="Output JSON path for signals")
    parser.add_argument(
        "--lookback-days", type=int, default=90,
        help="Days of historical data to fetch",
    )
    args = parser.parse_args()

    setup_logging()

    strategy = MomentumFuturesCoveredCall.from_yaml(Path(args.strategy))

    if strategy.config.screening is None or strategy.config.ranking is None:
        print("Error: strategy YAML must have screening and ranking sections")
        return

    live_universe = fetch_fo_universe()
    universe = args.universe.split(",") if args.universe else sorted(live_universe.keys())

    screener = UniverseScreener(strategy.config.screening)
    rank_config = strategy.config.ranking
    rank_config_with_top = type(rank_config)(
        factors=rank_config.factors, top_n=args.top
    )
    ranker = MomentumRanker(rank_config_with_top)

    fetcher = get_fetcher()
    end = date.today()
    start = end - timedelta(days=args.lookback_days)

    enriched_data: dict[str, pd.DataFrame] = {}
    nifty_roc = None

    logger.info(f"Screening {len(universe)} stocks ({start} to {end})")

    for symbol in ["NIFTY"] + [s for s in universe if s != "NIFTY"]:
        equity_df = fetcher.fetch_equity_ohlcv(symbol, start, end)
        if equity_df.empty:
            logger.debug(f"No data for {symbol}")
            continue

        enriched = TechnicalIndicators.add_all_strategy_indicators(equity_df.copy())
        enriched = TechnicalIndicators.add_roc(enriched, 20)
        enriched = TechnicalIndicators.add_volume_ratio(enriched, 20)

        lot_size = get_lot_size(symbol, end, live_data=live_universe)
        enriched["lot_value"] = enriched["close"] * lot_size
        enriched["_lot_size"] = lot_size
        enriched["symbol"] = symbol

        enriched = strategy.generate_signals(enriched)

        if symbol == "NIFTY":
            last_row = enriched.iloc[-1] if not enriched.empty else None
            if last_row is not None and not pd.isna(last_row.get("roc_20", float("nan"))):
                nifty_roc = float(last_row["roc_20"])

        if symbol in universe:
            enriched_data[symbol] = enriched

    candidates = screener.screen_latest(enriched_data)

    if candidates.empty:
        print("\nNo stocks pass screening criteria today.")
        return

    ranked = ranker.rank(candidates, nifty_roc=nifty_roc)

    print(f"\n{'='*70}")
    print(f"  SCREENER RESULTS — {end}")
    print(f"  Universe: {len(universe)} stocks | Screened: {len(candidates)} passed")
    print(f"{'='*70}\n")

    print(f"{'Rank':<6}{'Symbol':<12}{'Close':>10}{'ROC(20)':>10}{'ADX':>8}"
          f"{'RSI':>8}{'Score':>10}{'Entry?':>8}")
    print("-" * 72)

    for i, (_, row) in enumerate(ranked.iterrows()):
        entry = "YES" if row.get("entry_signal", False) else "no"
        roc = row.get("roc_20", 0)
        adx = row.get("adx", 0)
        rsi = row.get("rsi", 0)
        score = row.get("composite_score", 0)
        print(
            f"{i+1:<6}{row['symbol']:<12}{row['close']:>10,.0f}"
            f"{roc:>10.1f}{adx:>8.1f}{rsi:>8.1f}{score:>10.3f}{entry:>8}"
        )

    if args.output:
        sym_to_segment = {}
        for seg_key, symbols_list in SEGMENT_MAP.items():
            label = seg_key.replace("_FO", "").lower()
            for s in symbols_list:
                sym_to_segment[s] = label

        def _stock_record(row: pd.Series) -> dict:
            return {
                "symbol": row["symbol"],
                "close": float(row["close"]),
                "roc_20": float(row.get("roc_20", 0)),
                "adx": float(row.get("adx", 0)),
                "rsi": float(row.get("rsi", 0)),
                "composite_score": float(row.get("composite_score", 0)),
                "entry_signal": bool(row.get("entry_signal", False)),
                "segment": sym_to_segment.get(row["symbol"], "other"),
                "date": str(end),
            }

        top_picks = [_stock_record(row) for _, row in ranked.iterrows()]

        segments: dict[str, list[dict]] = {
            "largecap": [], "midcap": [], "smallcap": [],
        }
        for sym, df in enriched_data.items():
            if df.empty:
                continue
            last = df.iloc[-1]
            rec = _stock_record(last)
            seg = rec["segment"]
            if seg in segments:
                segments[seg].append(rec)
        for seg_list in segments.values():
            seg_list.sort(key=lambda r: r["composite_score"], reverse=True)

        output_data = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "top_picks": top_picks,
            "segments": segments,
        }
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nSignals written to {output_path}")


if __name__ == "__main__":
    main()
