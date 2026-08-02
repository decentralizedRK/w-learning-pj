from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class Comparison(StrEnum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    BETWEEN = "between"


class ConditionConfig(BaseModel):
    indicator: str
    comparison: Comparison
    value: float | str | bool | None = None
    value_min: float | None = None
    value_max: float | None = None
    reference: str | None = None


class EntryRuleConfig(BaseModel):
    conditions: list[ConditionConfig]


class ExitRuleConfig(BaseModel):
    conditions: list[ConditionConfig]


class StopLossConfig(BaseModel):
    initial_type: Literal["atr_multiple", "percent"] = "atr_multiple"
    initial_atr_multiple: float = 1.5
    initial_percent: float = 0.8
    trailing_enabled: bool = True
    trailing_step_pct: float = 0.5


class PositionSizingConfig(BaseModel):
    risk_per_trade_pct: float = 0.5
    max_concurrent_positions: int = 3


class HedgeConfig(BaseModel):
    enabled: bool = True
    otm_pct_min: float = 3.0
    otm_pct_max: float = 5.0
    same_expiry: bool = True


class RollConfig(BaseModel):
    days_before_expiry: int = 5
    roll_if_position_valid: bool = True


class TargetConfig(BaseModel):
    risk_reward_ratio: float = 2.0


class ScreenConfig(BaseModel):
    conditions: list[ConditionConfig]
    min_data_days: int = 60


class RankingFactor(BaseModel):
    name: str
    weight: float = 0.2
    ascending: bool = False


class RankConfig(BaseModel):
    factors: list[RankingFactor]
    top_n: int = 5


class CapacityConfig(BaseModel):
    margin_pct: float = 20.0
    max_position_value_pct: float = 30.0
    max_total_margin_pct: float = 75.0


class StrategyConfig(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    universe: list[str] = []
    timeframe: str = "daily"
    entry: EntryRuleConfig
    exit: ExitRuleConfig
    stop_loss: StopLossConfig = StopLossConfig()
    position_sizing: PositionSizingConfig = PositionSizingConfig()
    hedge: HedgeConfig = HedgeConfig()
    roll: RollConfig = RollConfig()
    target: TargetConfig = TargetConfig()
    accounts: list[str] = []
    screening: ScreenConfig | None = None
    ranking: RankConfig | None = None
    capacity: CapacityConfig = CapacityConfig()
