import pandas as pd

from config.constants import OIBuildup


class OIAnalyzer:
    @staticmethod
    def classify_oi_buildup(price_change: float, oi_change: float) -> str:
        if price_change > 0 and oi_change > 0:
            return OIBuildup.LONG_BUILDUP.value
        elif price_change < 0 and oi_change > 0:
            return OIBuildup.SHORT_BUILDUP.value
        elif price_change < 0 and oi_change < 0:
            return OIBuildup.LONG_UNWINDING.value
        elif price_change > 0 and oi_change < 0:
            return OIBuildup.SHORT_COVERING.value
        return OIBuildup.LONG_UNWINDING.value

    @staticmethod
    def add_oi_buildup(df: pd.DataFrame) -> pd.DataFrame:
        df["price_change"] = df["close"].diff()
        df["oi_change_val"] = df["oi"].diff() if "oi" in df.columns else 0

        df["oi_buildup"] = df.apply(
            lambda row: OIAnalyzer.classify_oi_buildup(
                row.get("price_change", 0), row.get("oi_change_val", 0)
            ),
            axis=1,
        )
        df["positive_oi_buildup"] = df["oi_buildup"].isin(
            [OIBuildup.LONG_BUILDUP.value, OIBuildup.SHORT_COVERING.value]
        )
        return df

    @staticmethod
    def compute_pcr(ce_oi: int, pe_oi: int) -> float:
        if ce_oi == 0:
            return 0.0
        return pe_oi / ce_oi
