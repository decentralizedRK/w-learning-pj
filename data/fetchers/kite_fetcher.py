from datetime import date

import pandas as pd
from loguru import logger

from broker.zerodha import ZerodhaBroker
from data.fetchers.base import BaseFetcher


class KiteFetcher(BaseFetcher):
    """Fetches live data from Zerodha Kite API (Personal plan).

    Note: Personal plan does NOT include historical data or WebSocket.
    Use this for live LTP, positions, and holdings only.
    """

    def __init__(self, broker: ZerodhaBroker):
        self.broker = broker

    def fetch_equity_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        logger.warning(
            "Kite Personal API does not support historical data. "
            "Use YFinanceFetcher for historical OHLCV."
        )
        return pd.DataFrame()

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
        logger.warning("Kite Personal API does not support historical F&O data")
        return pd.DataFrame()

    def fetch_option_chain_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        logger.warning("Kite Personal API does not support historical options data")
        return pd.DataFrame()
