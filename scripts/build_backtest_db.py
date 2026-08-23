"""Build the backtesting database from free data sources.

Usage:
    python -m scripts.build_backtest_db --symbols NIFTY --start 2020-01-01
    python -m scripts.build_backtest_db --symbols NIFTY --equity-only
"""

import argparse
from datetime import date, timedelta

from loguru import logger

from config.logging_config import setup_logging
from config.settings import settings
from data.fetchers import get_fetcher
from data.fetchers.jugaad_fetcher import JugaadFetcher
from data.storage.parquet_store import ParquetStore


def build_equity_data(
    symbols: list[str], start: date, end: date, store: ParquetStore
) -> None:
    fetcher = get_fetcher()

    for symbol in symbols:
        logger.info(f"Fetching equity data for {symbol}")
        df = fetcher.fetch_equity_ohlcv(symbol, start, end)
        if not df.empty:
            store.write("equity", symbol, df)
            logger.info(f"  Stored {len(df)} bars for {symbol}")
        else:
            logger.warning(f"  No data for {symbol}")


def build_fo_data(
    symbols: list[str], start: date, end: date, store: ParquetStore
) -> None:
    fetcher = JugaadFetcher()
    current = start

    while current <= end:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        logger.info(f"Fetching F&O bhavcopy for {current}")
        futures_df = fetcher.fetch_futures_bhavcopy(current)
        options_df = fetcher.fetch_option_chain_bhavcopy(current)

        if not futures_df.empty:
            for symbol in symbols:
                sym_fut = futures_df[futures_df["symbol"] == symbol]
                if not sym_fut.empty:
                    store.write("futures", symbol, sym_fut)

        if not options_df.empty:
            for symbol in symbols:
                sym_opt = options_df[options_df["symbol"] == symbol]
                if not sym_opt.empty:
                    store.write("options", symbol, sym_opt)

        current += timedelta(days=1)

        import time
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build backtesting database")
    parser.add_argument("--symbols", default="NIFTY", help="Comma-separated symbols")
    parser.add_argument("--start", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--equity-only", action="store_true", help="Only fetch equity OHLCV")
    args = parser.parse_args()

    setup_logging()

    symbols = [s.strip() for s in args.symbols.split(",")]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    settings.ensure_dirs()
    store = ParquetStore(settings.parquet_dir)

    logger.info(f"Building backtest DB for {symbols} from {start} to {end}")

    build_equity_data(symbols, start, end, store)

    if not args.equity_only:
        build_fo_data(symbols, start, end, store)

    logger.info("Database build complete")


if __name__ == "__main__":
    main()
