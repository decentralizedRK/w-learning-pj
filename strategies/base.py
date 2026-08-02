from abc import ABC, abstractmethod

import pandas as pd

from strategies.rule_evaluator import RuleEvaluator
from strategies.rule_schema import StrategyConfig


class BaseStrategy(ABC):
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.evaluator = RuleEvaluator()

    @abstractmethod
    def prepare_data(
        self,
        equity_df: pd.DataFrame,
        futures_df: pd.DataFrame,
        options_df: pd.DataFrame | None = None,
        pcr_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame: ...

    @abstractmethod
    def generate_signals(self, enriched_df: pd.DataFrame) -> pd.DataFrame: ...
