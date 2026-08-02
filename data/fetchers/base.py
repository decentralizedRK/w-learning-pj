from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class BaseFetcher(ABC):
    @abstractmethod
    def fetch_equity_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...

    @abstractmethod
    def fetch_futures_bhavcopy(self, trade_date: date) -> pd.DataFrame: ...

    @abstractmethod
    def fetch_option_chain_bhavcopy(self, trade_date: date) -> pd.DataFrame: ...
