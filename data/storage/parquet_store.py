from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger


class ParquetStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _path(self, data_type: str, symbol: str, year: int | None = None) -> Path:
        if year:
            return self.base_dir / data_type / symbol / f"{year}.parquet"
        return self.base_dir / data_type / symbol

    def write(self, data_type: str, symbol: str, df: pd.DataFrame) -> Path:
        if df.empty:
            return Path()

        if "date" in df.columns:
            df["_year"] = pd.to_datetime(df["date"]).dt.year
            for year, group in df.groupby("_year"):
                path = self._path(data_type, symbol, int(year))
                path.parent.mkdir(parents=True, exist_ok=True)

                if path.exists():
                    existing = pd.read_parquet(path)
                    new_data = group.drop(columns=["_year"])
                    if data_type == "equity":
                        dedup_cols = ["date"]
                    elif data_type == "options":
                        dedup_cols = ["date", "expiry", "strike", "option_type"]
                    else:
                        dedup_cols = ["date", "expiry"]
                    dedup_cols = [c for c in dedup_cols if c in new_data.columns]
                    combined = pd.concat([existing, new_data]).drop_duplicates(
                        subset=dedup_cols,
                        keep="last",
                    )
                    combined.to_parquet(path, index=False)
                else:
                    group.drop(columns=["_year"]).to_parquet(path, index=False)

                logger.debug(f"Wrote {len(group)} rows to {path}")
        else:
            path = self._path(data_type, symbol)
            path.mkdir(parents=True, exist_ok=True)
            out = path / "data.parquet"
            df.to_parquet(out, index=False)

        return self._path(data_type, symbol)

    def read(
        self, data_type: str, symbol: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        symbol_dir = self._path(data_type, symbol)
        if not symbol_dir.exists():
            return pd.DataFrame()

        parquet_files = sorted(symbol_dir.glob("*.parquet"))
        if not parquet_files:
            return pd.DataFrame()

        frames = []
        for f in parquet_files:
            try:
                year = int(f.stem)
                if start and year < start.year:
                    continue
                if end and year > end.year:
                    continue
            except ValueError:
                pass
            frames.append(pd.read_parquet(f))

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)

        if "date" in df.columns and (start or end):
            df["date"] = pd.to_datetime(df["date"]).dt.date
            if start:
                df = df[df["date"] >= start]
            if end:
                df = df[df["date"] <= end]

        return df.sort_values("date").reset_index(drop=True) if "date" in df.columns else df

    def exists(self, data_type: str, symbol: str) -> bool:
        return self._path(data_type, symbol).exists()
