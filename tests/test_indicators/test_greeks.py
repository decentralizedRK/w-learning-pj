import pytest

from indicators.greeks import GreeksCalculator


class TestGreeksCalculator:
    def test_compute_greeks_with_iv(self):
        result = GreeksCalculator.compute_greeks(
            underlying_price=22000, strike=22500, days_to_expiry=30, iv=15.0
        )
        assert "delta" in result
        assert "gamma" in result
        assert "theta" in result
        assert "vega" in result
        assert 0 < result["delta"] < 1

    def test_compute_greeks_requires_iv_or_price(self):
        with pytest.raises(ValueError):
            GreeksCalculator.compute_greeks(22000, 22500, 30)

    def test_select_otm_call_strike(self):
        strikes = [22000, 22500, 23000, 23500, 24000]
        result = GreeksCalculator.select_otm_call_strike(22000, strikes)
        assert result is not None
        assert result >= 22000 * 1.03
        assert result <= 22000 * 1.05

    def test_select_otm_call_strike_no_candidates(self):
        strikes = [22000, 22100]
        result = GreeksCalculator.select_otm_call_strike(22000, strikes)
        assert result is None

    def test_estimate_option_premium(self):
        premium = GreeksCalculator.estimate_option_premium(
            22000, 22500, 30, iv=15.0
        )
        assert premium >= 0
