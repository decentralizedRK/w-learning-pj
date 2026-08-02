from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
from loguru import logger


class DuckDBEngine:
    def __init__(self, parquet_base: Path):
        self.parquet_base = parquet_base
        self.conn = duckdb.connect()

    def _glob(self, data_type: str, symbol: str) -> str:
        return str(self.parquet_base / data_type / symbol / "*.parquet")

    def query_equity(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        glob = self._glob("equity", symbol)
        try:
            return self.conn.sql(f"""
                SELECT * FROM read_parquet('{glob}')
                WHERE date BETWEEN '{start}' AND '{end}'
                ORDER BY date
            """).df()
        except Exception as e:
            logger.error(f"DuckDB equity query failed for {symbol}: {e}")
            return pd.DataFrame()

    def query_futures(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        glob = self._glob("futures", symbol)
        try:
            return self.conn.sql(f"""
                SELECT * FROM read_parquet('{glob}')
                WHERE date BETWEEN '{start}' AND '{end}'
                ORDER BY date, expiry
            """).df()
        except Exception as e:
            logger.error(f"DuckDB futures query failed for {symbol}: {e}")
            return pd.DataFrame()

    def query_near_month_futures(
        self, symbol: str, start: date, end: date
    ) -> pd.DataFrame:
        glob = self._glob("futures", symbol)
        try:
            return self.conn.sql(f"""
                WITH ranked AS (
                    SELECT *,
                        ROW_NUMBER() OVER (PARTITION BY date ORDER BY expiry) as rn
                    FROM read_parquet('{glob}')
                    WHERE date BETWEEN '{start}' AND '{end}'
                    AND expiry >= date
                )
                SELECT * EXCLUDE (rn) FROM ranked WHERE rn = 1
                ORDER BY date
            """).df()
        except Exception as e:
            logger.error(f"DuckDB near-month futures query failed for {symbol}: {e}")
            return pd.DataFrame()

    def query_options(
        self,
        symbol: str,
        start: date,
        end: date,
        option_type: str | None = None,
    ) -> pd.DataFrame:
        glob = self._glob("options", symbol)
        where = f"WHERE date BETWEEN '{start}' AND '{end}'"
        if option_type:
            where += f" AND option_type = '{option_type}'"
        try:
            return self.conn.sql(f"""
                SELECT * FROM read_parquet('{glob}')
                {where}
                ORDER BY date, expiry, strike
            """).df()
        except Exception as e:
            logger.error(f"DuckDB options query failed for {symbol}: {e}")
            return pd.DataFrame()

    def compute_pcr_series(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        glob = self._glob("options", symbol)
        try:
            return self.conn.sql(f"""
                SELECT
                    date,
                    expiry,
                    SUM(CASE WHEN option_type = 'CE' THEN oi ELSE 0 END) as total_ce_oi,
                    SUM(CASE WHEN option_type = 'PE' THEN oi ELSE 0 END) as total_pe_oi,
                    CASE
                        WHEN SUM(CASE WHEN option_type = 'CE' THEN oi ELSE 0 END) > 0
                        THEN CAST(SUM(CASE WHEN option_type = 'PE' THEN oi ELSE 0 END) AS DOUBLE)
                             / SUM(CASE WHEN option_type = 'CE' THEN oi ELSE 0 END)
                        ELSE 0
                    END as pcr
                FROM read_parquet('{glob}')
                WHERE date BETWEEN '{start}' AND '{end}'
                GROUP BY date, expiry
                ORDER BY date, expiry
            """).df()
        except Exception as e:
            logger.error(f"DuckDB PCR query failed for {symbol}: {e}")
            return pd.DataFrame()
