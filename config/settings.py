from datetime import date
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QOS_", extra="ignore")

    database_url: str = "postgresql+psycopg://quantos:localdev@localhost:5432/quantos"

    data_dir: Path = Path("data_store")
    parquet_dir: Path = Path("data_store/parquet")

    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    initial_capital: float = 1_000_000
    risk_per_trade_pct: float = 0.5
    max_concurrent_positions: int = 3

    backtest_start: date = date(2020, 1, 1)
    backtest_end: date = date(2025, 12, 31)

    strategy_config_path: Path = Field(
        default=Path("config/strategies/momentum_futures_covered_call.yaml")
    )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
