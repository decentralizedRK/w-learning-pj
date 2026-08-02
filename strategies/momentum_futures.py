from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from indicators.greeks import GreeksCalculator
from indicators.oi_analysis import OIAnalyzer
from indicators.technical import TechnicalIndicators
from strategies.base import BaseStrategy
from strategies.rule_schema import StrategyConfig


class MomentumFuturesCoveredCall(BaseStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.indicators = TechnicalIndicators()
        self.oi_analyzer = OIAnalyzer()
        self.greeks_calc = GreeksCalculator()

    @classmethod
    def from_yaml(cls, path: Path) -> "MomentumFuturesCoveredCall":
        with open(path) as f:
            data = yaml.safe_load(f)
        config = StrategyConfig(**data)
        return cls(config)

    def prepare_data(
        self,
        equity_df: pd.DataFrame,
        futures_df: pd.DataFrame,
        options_df: pd.DataFrame | None = None,
        pcr_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        enriched = self.indicators.add_all_strategy_indicators(equity_df.copy())

        if not futures_df.empty and "oi" in futures_df.columns:
            fut_cols = ["date", "oi", "expiry"]
            fut_cols = [c for c in fut_cols if c in futures_df.columns]
            fut_subset = futures_df[fut_cols].copy()

            if "oi" in fut_subset.columns:
                fut_subset["oi_change_raw"] = fut_subset["oi"].diff()
                oi_cols = fut_subset[["date", "oi", "oi_change_raw"]]
                enriched = enriched.merge(oi_cols, on="date", how="left")
                enriched["oi"] = enriched["oi"].fillna(0)
                enriched = self.oi_analyzer.add_oi_buildup(enriched)

                if "expiry" in fut_subset.columns:
                    expiry_map = fut_subset.drop_duplicates("date")[["date", "expiry"]]
                    enriched = enriched.merge(expiry_map, on="date", how="left")

        if pcr_df is not None and not pcr_df.empty:
            pcr_daily = pcr_df.groupby("date")["pcr"].mean().reset_index()
            enriched = enriched.merge(pcr_daily, on="date", how="left")
            enriched["pcr"] = enriched["pcr"].fillna(0)

        for col in ["positive_oi_buildup", "pcr"]:
            if col not in enriched.columns:
                enriched[col] = False if col == "positive_oi_buildup" else 1.0

        return enriched

    def generate_signals(self, enriched_df: pd.DataFrame) -> pd.DataFrame:
        return self.evaluator.evaluate_signals(
            self.config.entry, self.config.exit, enriched_df
        )

    def compute_stop_loss(self, entry_price: float, atr: float) -> float:
        sl_cfg = self.config.stop_loss
        atr_sl = entry_price - (sl_cfg.initial_atr_multiple * atr)
        pct_sl = entry_price * (1 - sl_cfg.initial_percent / 100)
        return min(atr_sl, pct_sl)

    def compute_position_size(
        self, capital: float, entry_price: float, stop_loss: float, lot_size: int
    ) -> int:
        risk_amount = capital * (self.config.position_sizing.risk_per_trade_pct / 100)
        risk_per_lot = abs(entry_price - stop_loss) * lot_size
        if risk_per_lot <= 0:
            return 0
        lots = int(risk_amount / risk_per_lot)
        return max(lots, 0)

    def compute_target(self, entry_price: float, stop_loss: float) -> float:
        risk = entry_price - stop_loss
        return entry_price + (self.config.target.risk_reward_ratio * risk)

    def select_hedge(
        self,
        entry_price: float,
        entry_date: date,
        expiry: date,
        available_strikes: list[float],
    ) -> dict | None:
        if not self.config.hedge.enabled:
            return None

        strike = self.greeks_calc.select_otm_call_strike(
            entry_price,
            available_strikes,
            self.config.hedge.otm_pct_min,
            self.config.hedge.otm_pct_max,
        )
        if strike is None:
            return None

        days_to_expiry = max(1, (expiry - entry_date).days)
        greeks = self.greeks_calc.compute_greeks(
            entry_price, strike, days_to_expiry, iv=15.0, option_type="CE"
        )
        premium = self.greeks_calc.estimate_option_premium(
            entry_price, strike, days_to_expiry, iv=15.0, option_type="CE"
        )
        return {"strike": strike, "greeks": greeks, "premium": premium}

    def should_roll(
        self, current_date: date, expiry: date, enriched_row: pd.Series
    ) -> bool:
        days_remaining = (expiry - current_date).days
        if days_remaining > self.config.roll.days_before_expiry:
            return False
        if self.config.roll.roll_if_position_valid:
            return self.evaluator.evaluate_entry(self.config.entry, enriched_row)
        return True
