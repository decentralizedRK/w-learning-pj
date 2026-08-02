from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf
from loguru import logger

from config.constants import INDEX_TICKER_MAP
from data.fetchers.base import BaseFetcher


class YFinanceFetcher(BaseFetcher):
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir

    def _to_yahoo_ticker(self, symbol: str) -> str:
        if symbol in INDEX_TICKER_MAP:
            return INDEX_TICKER_MAP[symbol]
        return f"{symbol}.NS"

    def _cache_path(self, symbol: str, start: date, end: date) -> Path | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"equity/{symbol}_{start}_{end}.parquet"
        return path

    def fetch_equity_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        cache = self._cache_path(symbol, start, end)
        if cache and cache.exists():
            logger.debug(f"Cache hit: {symbol}")
            return pd.read_parquet(cache)

        yahoo_ticker = self._to_yahoo_ticker(symbol)
        logger.info(f"Fetching {symbol} ({yahoo_ticker}) from {start} to {end}")

        ticker = yf.Ticker(yahoo_ticker)
        df = ticker.history(start=str(start), end=str(end))

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        df["symbol"] = symbol
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[["symbol", "date", "open", "high", "low", "close", "volume"]]

        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)
            logger.debug(f"Cached {len(df)} bars for {symbol}")

        return df

    def fetch_index_ohlcv(self, index: str, start: date, end: date) -> pd.DataFrame:
        return self.fetch_equity_ohlcv(index, start, end)

    def fetch_futures_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        logger.warning("yfinance does not support futures data, use JugaadFetcher")
        return pd.DataFrame()

    def fetch_option_chain_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        logger.warning("yfinance does not support options data, use JugaadFetcher")
        return pd.DataFrame()
