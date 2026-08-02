from datetime import date
from typing import Literal

from pydantic import BaseModel


class OHLCVBar(BaseModel):
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class FuturesData(OHLCVBar):
    expiry: date
    oi: int = 0
    oi_change: int = 0
    settle_price: float = 0.0


class OptionChainRow(BaseModel):
    symbol: str
    date: date
    expiry: date
    strike: float
    option_type: Literal["CE", "PE"]
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int
    oi_change: int = 0
    iv: float | None = None


class OISnapshot(BaseModel):
    symbol: str
    date: date
    expiry: date
    total_ce_oi: int
    total_pe_oi: int
    pcr: float
    max_pain: float | None = None
