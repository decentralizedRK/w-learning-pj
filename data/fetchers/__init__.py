from loguru import logger

from data.fetchers.base import BaseFetcher
from data.fetchers.yfinance_fetcher import YFinanceFetcher


def get_fetcher() -> BaseFetcher:
    """Return KiteFetcher if Kite credentials are valid, else YFinanceFetcher."""
    from config.settings import settings

    if settings.kite_api_key and settings.kite_access_token:
        try:
            from broker.zerodha import ZerodhaBroker
            from data.fetchers.kite_fetcher import KiteFetcher

            broker = ZerodhaBroker()
            broker.authenticate()
            logger.info("Using Kite API for market data")
            return KiteFetcher(broker)
        except Exception as e:
            logger.warning(f"Kite auth failed ({e}), falling back to yfinance")

    logger.info("Using yfinance for market data")
    return YFinanceFetcher(cache_dir=settings.parquet_dir / "cache")
