import pandas as pd

from config.constants import OIBuildup
from strategies.rule_schema import RankConfig


class MomentumRanker:
    KNOWN_FACTORS = {
        "roc_20", "adx", "relative_strength", "oi_buildup_score", "volume_ratio",
    }

    OI_SCORE_MAP = {
        OIBuildup.LONG_BUILDUP.value: 1.0,
        OIBuildup.SHORT_COVERING.value: 0.5,
        OIBuildup.LONG_UNWINDING.value: 0.0,
        OIBuildup.SHORT_BUILDUP.value: 0.0,
    }

    def __init__(self, config: RankConfig):
        self.config = config

    def _compute_factor_values(
        self,
        candidates: pd.DataFrame,
        nifty_roc: float | None = None,
    ) -> pd.DataFrame:
        df = candidates.copy()

        for factor in self.config.factors:
            col = f"_rank_{factor.name}"
            if factor.name in ("roc_20", "adx", "volume_ratio"):
                raw_col = factor.name
                if raw_col in df.columns:
                    df[col] = df[raw_col].fillna(0)
                else:
                    df[col] = 0.0
            elif factor.name == "relative_strength":
                if nifty_roc is not None and nifty_roc != 0 and "roc_20" in df.columns:
                    df[col] = df["roc_20"].fillna(0) / nifty_roc
                else:
                    df[col] = 1.0
            elif factor.name == "oi_buildup_score":
                if "oi_buildup" in df.columns:
                    df[col] = df["oi_buildup"].map(self.OI_SCORE_MAP).fillna(0.5)
                else:
                    df[col] = 0.5

        return df

    def rank(
        self,
        candidates: pd.DataFrame,
        nifty_roc: float | None = None,
    ) -> pd.DataFrame:
        if candidates.empty:
            return candidates

        df = self._compute_factor_values(candidates, nifty_roc)

        df["composite_score"] = 0.0
        for factor in self.config.factors:
            col = f"_rank_{factor.name}"
            if col not in df.columns:
                continue
            normalized = df[col].rank(pct=True, ascending=not factor.ascending)
            df["composite_score"] += normalized * factor.weight

        df = df.sort_values("composite_score", ascending=False)
        return df.head(self.config.top_n).reset_index(drop=True)
