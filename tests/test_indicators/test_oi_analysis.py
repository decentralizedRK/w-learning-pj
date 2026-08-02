import pandas as pd
import pytest

from config.constants import OIBuildup
from indicators.oi_analysis import OIAnalyzer


class TestOIAnalyzer:
    def test_long_buildup(self):
        assert OIAnalyzer.classify_oi_buildup(1.0, 100) == OIBuildup.LONG_BUILDUP.value

    def test_short_buildup(self):
        assert OIAnalyzer.classify_oi_buildup(-1.0, 100) == OIBuildup.SHORT_BUILDUP.value

    def test_long_unwinding(self):
        assert OIAnalyzer.classify_oi_buildup(-1.0, -100) == OIBuildup.LONG_UNWINDING.value

    def test_short_covering(self):
        assert OIAnalyzer.classify_oi_buildup(1.0, -100) == OIBuildup.SHORT_COVERING.value

    def test_add_oi_buildup(self):
        df = pd.DataFrame({
            "close": [100, 102, 101, 103],
            "oi": [1000, 1200, 1100, 1300],
        })
        result = OIAnalyzer.add_oi_buildup(df)
        assert "oi_buildup" in result.columns
        assert "positive_oi_buildup" in result.columns

    def test_zero_change_not_bullish(self):
        result = OIAnalyzer.classify_oi_buildup(0, 0)
        assert result not in (
            OIBuildup.LONG_BUILDUP.value,
            OIBuildup.SHORT_COVERING.value,
        )

    def test_price_up_oi_flat_not_bullish(self):
        result = OIAnalyzer.classify_oi_buildup(1.0, 0)
        assert result not in (
            OIBuildup.LONG_BUILDUP.value,
            OIBuildup.SHORT_COVERING.value,
        )

    def test_compute_pcr(self):
        assert OIAnalyzer.compute_pcr(100_000, 120_000) == pytest.approx(1.2)
        assert OIAnalyzer.compute_pcr(0, 100_000) == 0.0
