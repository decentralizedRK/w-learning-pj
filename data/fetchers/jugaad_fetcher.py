import time as time_mod
from datetime import date, timedelta

import pandas as pd
from loguru import logger

from data.fetchers.base import BaseFetcher


class JugaadFetcher(BaseFetcher):
    def fetch_equity_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        logger.warning("Use YFinanceFetcher for equity OHLCV")
        return pd.DataFrame()

    def fetch_futures_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        try:
            from jugaad_data.nse import bhavcopy_fo_raw
        except ImportError:
            logger.error("jugaad-data not installed")
            return pd.DataFrame()

        try:
            df = bhavcopy_fo_raw(trade_date)
            if df is None or df.empty:
                return pd.DataFrame()

            fut_mask = df["INSTRUMENT"].isin(["FUTSTK", "FUTIDX"])
            fut_df = df[fut_mask].copy()

            fut_df = fut_df.rename(columns={
                "SYMBOL": "symbol",
                "EXPIRY_DT": "expiry",
                "OPEN": "open",
                "HIGH": "high",
                "LOW": "low",
                "CLOSE": "close",
                "SETTLE_PR": "settle_price",
                "CONTRACTS": "volume",
                "OPEN_INT": "oi",
                "CHG_IN_OI": "oi_change",
            })

            fut_df["date"] = trade_date
            fut_df["expiry"] = pd.to_datetime(fut_df["expiry"]).dt.date

            cols = [
                "symbol", "date", "expiry", "open", "high", "low", "close",
                "settle_price", "volume", "oi", "oi_change",
            ]
            return fut_df[[c for c in cols if c in fut_df.columns]]

        except Exception as e:
            logger.error(f"Failed to fetch futures bhavcopy for {trade_date}: {e}")
            return pd.DataFrame()

    def fetch_option_chain_bhavcopy(self, trade_date: date) -> pd.DataFrame:
        try:
            from jugaad_data.nse import bhavcopy_fo_raw
        except ImportError:
            logger.error("jugaad-data not installed")
            return pd.DataFrame()

        try:
            df = bhavcopy_fo_raw(trade_date)
            if df is None or df.empty:
                return pd.DataFrame()

            opt_mask = df["INSTRUMENT"].isin(["OPTSTK", "OPTIDX"])
            opt_df = df[opt_mask].copy()

            opt_df = opt_df.rename(columns={
                "SYMBOL": "symbol",
                "EXPIRY_DT": "expiry",
                "STRIKE_PR": "strike",
                "OPTION_TYP": "option_type",
                "OPEN": "open",
                "HIGH": "high",
                "LOW": "low",
                "CLOSE": "close",
                "CONTRACTS": "volume",
                "OPEN_INT": "oi",
                "CHG_IN_OI": "oi_change",
            })

            opt_df["date"] = trade_date
            opt_df["expiry"] = pd.to_datetime(opt_df["expiry"]).dt.date

            cols = [
                "symbol", "date", "expiry", "strike", "option_type",
                "open", "high", "low", "close", "volume", "oi", "oi_change",
            ]
            return opt_df[[c for c in cols if c in opt_df.columns]]

        except Exception as e:
            logger.error(f"Failed to fetch options bhavcopy for {trade_date}: {e}")
            return pd.DataFrame()

    def fetch_bulk_historical(
        self, start: date, end: date, delay: float = 1.0
    ) -> tuple[list[pd.DataFrame], list[pd.DataFrame]]:
        futures_frames: list[pd.DataFrame] = []
        options_frames: list[pd.DataFrame] = []
        current = start

        while current <= end:
            if current.weekday() < 5:
                logger.info(f"Fetching bhavcopy for {current}")
                fut = self.fetch_futures_bhavcopy(current)
                if not fut.empty:
                    futures_frames.append(fut)
                opt = self.fetch_option_chain_bhavcopy(current)
                if not opt.empty:
                    options_frames.append(opt)
                time_mod.sleep(delay)
            current += timedelta(days=1)

        return futures_frames, options_frames
