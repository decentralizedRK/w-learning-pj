from datetime import date

import pandas as pd

from config.constants import OIBuildup
from indicators.oi_analysis import OIAnalyzer
from indicators.technical import TechnicalIndicators
from strategies.rule_evaluator import RuleEvaluator
from strategies.rule_schema import EntryRuleConfig, ScreenConfig


class UniverseScreener:
    def __init__(
        self,
        config: ScreenConfig,
        evaluator: RuleEvaluator | None = None,
    ):
        self.config = config
        self.evaluator = evaluator or RuleEvaluator()

    def enrich_for_screening(
        self,
        equity_df: pd.DataFrame,
        futures_df: pd.DataFrame,
        lot_size: int,
        pcr_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        enriched = TechnicalIndicators.add_all_strategy_indicators(equity_df.copy())

        if not futures_df.empty and "oi" in futures_df.columns:
            fut_cols = [c for c in ["date", "oi", "expiry"] if c in futures_df.columns]
            fut_subset = futures_df[fut_cols].copy()
            if "oi" in fut_subset.columns:
                fut_subset["oi_change_raw"] = fut_subset["oi"].diff()
                oi_cols = fut_subset[["date", "oi", "oi_change_raw"]]
                enriched = enriched.merge(oi_cols, on="date", how="left")
                enriched["oi"] = enriched["oi"].fillna(0)
                enriched = OIAnalyzer.add_oi_buildup(enriched)
                if "expiry" in fut_subset.columns:
                    expiry_map = fut_subset.drop_duplicates("date")[["date", "expiry"]]
                    enriched = enriched.merge(expiry_map, on="date", how="left")

        if pcr_df is not None and not pcr_df.empty:
            pcr_daily = pcr_df.groupby("date")["pcr"].mean().reset_index()
            enriched = enriched.merge(pcr_daily, on="date", how="left")
            enriched["pcr"] = enriched["pcr"].fillna(0)

        for col in ["positive_oi_buildup", "pcr", "oi_buildup"]:
            if col not in enriched.columns:
                if col == "positive_oi_buildup":
                    enriched[col] = False
                elif col == "pcr":
                    enriched[col] = 0.0
                elif col == "oi_buildup":
                    enriched[col] = OIBuildup.SHORT_BUILDUP.value

        enriched = TechnicalIndicators.add_roc(enriched, 20)
        enriched = TechnicalIndicators.add_volume_ratio(enriched, 20)
        enriched["lot_value"] = enriched["close"] * lot_size
        enriched["_lot_size"] = lot_size

        return enriched

    def screen_on_date(
        self,
        enriched_data: dict[str, pd.DataFrame],
        screen_date: date,
    ) -> pd.DataFrame:
        entry_rule = EntryRuleConfig(conditions=self.config.conditions)
        candidates = []

        for symbol, df in enriched_data.items():
            if "date" not in df.columns:
                continue

            date_col = df["date"]
            if hasattr(date_col.iloc[0], "date"):
                mask = date_col.apply(
                    lambda d: d.date() if isinstance(d, pd.Timestamp) else d
                ) == screen_date
            else:
                mask = date_col == screen_date

            matching = df[mask]
            if matching.empty:
                continue

            data_before = df[df.index <= matching.index[0]]
            if len(data_before) < self.config.min_data_days:
                continue

            row = matching.iloc[0]
            if self.evaluator.evaluate_entry(entry_rule, row):
                row_dict = row.to_dict()
                row_dict["symbol"] = symbol
                candidates.append(row_dict)

        if not candidates:
            return pd.DataFrame()

        return pd.DataFrame(candidates)

    def screen_latest(
        self,
        enriched_data: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        max_date = None
        for df in enriched_data.values():
            if "date" not in df.columns or df.empty:
                continue
            last = df["date"].iloc[-1]
            if isinstance(last, pd.Timestamp):
                last = last.date()
            if max_date is None or last > max_date:
                max_date = last

        if max_date is None:
            return pd.DataFrame()

        return self.screen_on_date(enriched_data, max_date)
