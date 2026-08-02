import pandas as pd
import pytest

from indicators.technical import TechnicalIndicators


@pytest.fixture
def sample_ohlcv():
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    return pd.DataFrame({
        "date": dates,
        "open": [100 + i * 0.5 for i in range(60)],
        "high": [101 + i * 0.5 for i in range(60)],
        "low": [99 + i * 0.5 for i in range(60)],
        "close": [100.5 + i * 0.5 for i in range(60)],
        "volume": [1_000_000 + i * 10_000 for i in range(60)],
    })


class TestTechnicalIndicators:
    def test_add_ema(self, sample_ohlcv):
        df = TechnicalIndicators.add_ema(sample_ohlcv, 20)
        assert "ema_20" in df.columns
        assert df["ema_20"].notna().sum() > 0

    def test_add_adx(self, sample_ohlcv):
        df = TechnicalIndicators.add_adx(sample_ohlcv)
        assert "adx" in df.columns
        assert "adx_pos" in df.columns
        assert "adx_neg" in df.columns

    def test_add_rsi(self, sample_ohlcv):
        df = TechnicalIndicators.add_rsi(sample_ohlcv)
        assert "rsi" in df.columns
        valid_rsi = df["rsi"].dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_add_atr(self, sample_ohlcv):
        df = TechnicalIndicators.add_atr(sample_ohlcv)
        assert "atr" in df.columns
        assert (df["atr"].dropna() >= 0).all()

    def test_add_volume_sma(self, sample_ohlcv):
        df = TechnicalIndicators.add_volume_sma(sample_ohlcv, 20)
        assert "volume_sma_20" in df.columns

    def test_add_all_strategy_indicators(self, sample_ohlcv):
        df = TechnicalIndicators.add_all_strategy_indicators(sample_ohlcv)
        expected = ["ema_20", "ema_50", "adx", "rsi", "atr", "volume_sma_20"]
        for col in expected:
            assert col in df.columns, f"Missing column: {col}"
