"""Instrument token lookup for Kite Connect API.

Maps stock symbols to instrument tokens needed for historical data API calls.
Caches instrument lists daily to avoid repeated API calls.
"""

import json
from datetime import datetime
from pathlib import Path

from kiteconnect import KiteConnect
from loguru import logger

COMMON_INDICES = {
    "NIFTY": {"exchange": "NSE", "tradingsymbol": "NIFTY 50", "instrument_token": 256265},
    "NIFTY50": {"exchange": "NSE", "tradingsymbol": "NIFTY 50", "instrument_token": 256265},
    "BANKNIFTY": {"exchange": "NSE", "tradingsymbol": "NIFTY BANK", "instrument_token": 260105},
    "SENSEX": {"exchange": "BSE", "tradingsymbol": "SENSEX", "instrument_token": 265},
    "FINNIFTY": {
        "exchange": "NSE", "tradingsymbol": "NIFTY FIN SERVICE",
        "instrument_token": 257801,
    },
    "MIDCPNIFTY": {
        "exchange": "NSE", "tradingsymbol": "NIFTY MID SELECT",
        "instrument_token": 288009,
    },
}


class InstrumentLookup:
    def __init__(self, kite: KiteConnect, cache_dir: Path | None = None):
        self.kite = kite
        self._instruments: list[dict] = []
        if cache_dir is None:
            from config.settings import settings
            self._cache_dir = settings.data_dir / "cache"
        else:
            self._cache_dir = cache_dir

    def load_instruments(self, exchange: str = "NSE", force_refresh: bool = False) -> list[dict]:
        cache_path = self._cache_dir / f"kite_instruments_{exchange.lower()}.json"

        if not force_refresh and cache_path.exists():
            mod_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if mod_time.date() == datetime.now().date():
                with open(cache_path) as f:
                    self._instruments = json.load(f)
                return self._instruments

        self._instruments = self.kite.instruments(exchange)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(self._instruments, f, default=str)
        logger.info(f"Cached {len(self._instruments)} {exchange} instruments")
        return self._instruments

    def find_instrument(self, symbol: str, exchange: str = "NSE") -> dict | None:
        upper = symbol.upper().replace(" ", "")

        if upper in COMMON_INDICES:
            return COMMON_INDICES[upper]

        if not self._instruments:
            self.load_instruments(exchange)

        for inst in self._instruments:
            if inst["tradingsymbol"].upper().replace(" ", "") == upper:
                return inst

        matches = [i for i in self._instruments if upper in i["tradingsymbol"].upper()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            names = [m["tradingsymbol"] for m in matches[:5]]
            logger.warning(f"Multiple matches for '{symbol}': {names}")
            return None

        return None

    def get_token(self, symbol: str, exchange: str = "NSE") -> int | None:
        inst = self.find_instrument(symbol, exchange)
        if inst:
            return inst["instrument_token"]
        return None
