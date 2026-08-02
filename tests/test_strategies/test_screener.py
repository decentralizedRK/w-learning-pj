from datetime import date

import pandas as pd
import pytest

from strategies.rule_schema import Comparison, ConditionConfig, ScreenConfig
from strategies.screener import UniverseScreener


@pytest.fixture
def screen_config():
    return ScreenConfig(
        conditions=[
            ConditionConfig(indicator="close", comparison=Comparison.GT, reference="ema_20"),
            ConditionConfig(indicator="ema_20", comparison=Comparison.GT, reference="ema_50"),
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=20),
            ConditionConfig(
                indicator="rsi", comparison=Comparison.BETWEEN, value_min=40, value_max=75
            ),
        ],
        min_data_days=5,
    )


@pytest.fixture
def screener(screen_config):
    return UniverseScreener(screen_config)


def _make_enriched(
    symbol: str,
    close: float = 2500,
    ema_20: float = 2400,
    ema_50: float = 2300,
    adx: float = 28,
    rsi: float = 60,
    n_rows: int = 10,
) -> pd.DataFrame:
    dates = [date(2025, 1, i + 1) for i in range(n_rows)]
    rows = []
    for d in dates:
        rows.append({
            "date": d,
            "close": close,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "adx": adx,
            "rsi": rsi,
            "volume": 1_000_000,
            "volume_sma_20": 800_000,
        })
    return pd.DataFrame(rows)


class TestUniverseScreener:
    def test_passes_all_conditions(self, screener):
        data = {"RELIANCE": _make_enriched("RELIANCE")}
        result = screener.screen_on_date(data, date(2025, 1, 10))
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "RELIANCE"

    def test_fails_adx_below_threshold(self, screener):
        data = {"RELIANCE": _make_enriched("RELIANCE", adx=15)}
        result = screener.screen_on_date(data, date(2025, 1, 10))
        assert result.empty

    def test_fails_ema_not_aligned(self, screener):
        data = {"RELIANCE": _make_enriched("RELIANCE", ema_20=2200, ema_50=2300)}
        result = screener.screen_on_date(data, date(2025, 1, 10))
        assert result.empty

    def test_screen_on_date_returns_passing_symbols(self, screener):
        data = {
            "RELIANCE": _make_enriched("RELIANCE"),
            "TCS": _make_enriched("TCS"),
            "INFY": _make_enriched("INFY", adx=15),
            "SBIN": _make_enriched("SBIN"),
            "HDFCBANK": _make_enriched("HDFCBANK", rsi=30),
        }
        result = screener.screen_on_date(data, date(2025, 1, 10))
        assert len(result) == 3
        symbols = set(result["symbol"])
        assert symbols == {"RELIANCE", "TCS", "SBIN"}

    def test_screen_on_date_skips_insufficient_data(self, screener):
        data = {"RELIANCE": _make_enriched("RELIANCE", n_rows=3)}
        result = screener.screen_on_date(data, date(2025, 1, 3))
        assert result.empty

    def test_screen_on_date_empty_when_none_pass(self, screener):
        data = {
            "RELIANCE": _make_enriched("RELIANCE", adx=10),
            "TCS": _make_enriched("TCS", rsi=30),
        }
        result = screener.screen_on_date(data, date(2025, 1, 10))
        assert result.empty
