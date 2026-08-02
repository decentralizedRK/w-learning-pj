import json
from datetime import date
from pathlib import Path

from loguru import logger

from config.constants import FO_LOT_SIZES, LOT_SIZE_HISTORY

INDEX_SYMBOLS = {
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
    "NIFTY NEXT 50", "NIFTY200", "NIFTYNXT50",
}


def fetch_fo_universe(
    api_key: str = "",
    cache_dir: Path | None = None,
) -> dict[str, int]:
    from config.settings import settings

    api_key = api_key or settings.kite_api_key
    if cache_dir is None:
        cache_dir = settings.data_dir / "cache"

    cache_file = cache_dir / f"fo_instruments_{date.today().isoformat()}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    if not api_key:
        logger.warning("No Kite API key configured, using hardcoded F&O list")
        return dict(FO_LOT_SIZES)

    try:
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
        instruments = kite.instruments("NFO")

        fo_stocks: dict[str, int] = {}
        for inst in instruments:
            if inst["instrument_type"] != "FUT":
                continue
            symbol = inst["name"]
            if symbol in INDEX_SYMBOLS:
                continue
            if symbol not in fo_stocks:
                fo_stocks[symbol] = inst["lot_size"]

        if fo_stocks:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(fo_stocks, f, indent=2, sort_keys=True)
            logger.info(f"Fetched {len(fo_stocks)} F&O stocks from Kite API")
            return fo_stocks

        logger.warning("Kite API returned no stock futures, using hardcoded list")
        return dict(FO_LOT_SIZES)

    except Exception as e:
        logger.warning(f"Kite API fetch failed ({e}), using hardcoded F&O list")
        return dict(FO_LOT_SIZES)


def get_lot_size(
    symbol: str,
    trade_date: date,
    live_data: dict[str, int] | None = None,
) -> int:
    history = LOT_SIZE_HISTORY.get(symbol)
    if history is not None:
        for entry in history:
            entry_from = date.fromisoformat(entry["from"])
            entry_to = date.fromisoformat(entry["to"])
            if entry_from <= trade_date <= entry_to:
                return entry["lot_size"]
        return history[-1]["lot_size"]

    if live_data and symbol in live_data:
        return live_data[symbol]

    lot = FO_LOT_SIZES.get(symbol)
    if lot is None:
        logger.warning(f"Unknown lot size for {symbol}, defaulting to 1")
        return 1
    return lot


FO_STOCK_LIST = sorted(FO_LOT_SIZES.keys())
