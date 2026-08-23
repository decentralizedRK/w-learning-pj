import time
from datetime import date, datetime, timedelta

import pandas as pd
from loguru import logger

from broker.zerodha import ZerodhaBroker
from data.fetchers.base import BaseFetcher

VALID_INTERVALS = [
    "minute", "3minute", "5minute", "10minute",
    "15minute", "30minute", "60minute", "day",
]
HIST_API_RATE_LIMIT = 3


class KiteFetcher(BaseFetcher):
    """Fetches data from Zerodha Kite API.

    Supports historical OHLCV data if the Kite Connect app has historical
    data permissions enabled. Also provides live LTP, positions, and holdings.
    """

    def __init__(self, broker: ZerodhaBroker):
        self.broker = broker

    def fetch_equity_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        from data.fetchers.instrument_lookup import InstrumentLookup

        lookup = InstrumentLookup(self.broker._get_kite())
        token = lookup.get_token(symbol)
        if token is None:
            logger.error(f"Could not find instrument token for {symbol}")
            return pd.DataFrame()

        df = self.fetch_historical(
            instrument_token=token,
            from_date=datetime.combine(start, datetime.min.time()),
            to_date=datetime.combine(end, datetime.min.time()),
            interval="day",
        )
        if df.empty:
            return df

        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["symbol"] = symbol
        df = df[["symbol", "date", "open", "high", "low", "close", "volume"]]
        return df

    def fetch_historical(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day",
        continuous: bool = False,
        oi: bool = False,
    ) -> pd.DataFrame:
        if interval not in VALID_INTERVALS:
            raise ValueError(f"Invalid interval '{interval}'. Must be one of {VALID_INTERVALS}")

        kite = self.broker._get_kite()
        records = kite.historical_data(
            instrument_token, from_date, to_date, interval,
            continuous=continuous, oi=oi,
        )
        df = pd.DataFrame(records)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
        return df

    def fetch_historical_chunked(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day",
        continuous: bool = False,
        oi: bool = False,
    ) -> pd.DataFrame:
        """Fetch large date ranges by splitting into chunks.

        Intraday intervals are limited to 60 days per request; 'day' to 2000 days.
        """
        max_days = 2000 if interval == "day" else 60
        chunks = []
        current = from_date

        while current < to_date:
            chunk_end = min(current + timedelta(days=max_days), to_date)
            df = self.fetch_historical(
                instrument_token, current, chunk_end, interval, continuous, oi,
            )
            if not df.empty:
                chunks.append(df)
            current = chunk_end + timedelta(days=1)
            time.sleep(1.0 / HIST_API_RATE_LIMIT)

        if not chunks:
            return pd.DataFrame()
        return pd.concat(chunks).sort_index()

    def fetch_live_ltp(self, symbols: list[str]) -> dict[str, float]:
        return self.broker.get_ltp(symbols)

    def fetch_live_positions(self) -> pd.DataFrame:
        positions = self.broker.get_positions()
        if not positions:
            return pd.DataFrame()
        return pd.DataFrame(positions)

    def fetch_live_holdings(self) -> pd.DataFrame:
        holdings = self.broker.get_holdings()
        if not holdings:
            return pd.DataFrame()
        return pd.DataFrame(holdings)

    def fetch_futures_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        logger.warning("Use JugaadFetcher for historical F&O bhavcopy data")
        return pd.DataFrame()

    def fetch_option_chain_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        logger.warning("Use JugaadFetcher for historical options bhavcopy data")
        return pd.DataFrame()
