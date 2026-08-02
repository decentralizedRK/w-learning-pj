import pytest

from backtester.costs import IndianFnOCostModel


@pytest.fixture
def cost_model():
    return IndianFnOCostModel()


class TestIndianFnOCostModel:
    def test_futures_buy_cost(self, cost_model):
        result = cost_model.compute_futures_cost(22000, 75, 1, "buy")
        assert result["brokerage"] == 20.0
        assert result["stt"] == 0
        assert result["stamp_duty"] > 0
        assert result["total"] > 20

    def test_futures_sell_cost(self, cost_model):
        result = cost_model.compute_futures_cost(22000, 75, 1, "sell")
        assert result["stt"] > 0
        assert result["stamp_duty"] == 0

    def test_options_sell_cost(self, cost_model):
        result = cost_model.compute_options_cost(150, 75, 1, "sell")
        assert result["stt"] > 0
        assert result["stamp_duty"] == 0

    def test_options_buy_cost(self, cost_model):
        result = cost_model.compute_options_cost(150, 75, 1, "buy")
        assert result["stt"] == 0
        assert result["stamp_duty"] > 0

    def test_round_trip_cost(self, cost_model):
        result = cost_model.compute_round_trip_cost(
            entry_price=22000, exit_price=22300,
            lot_size=75, lots=1,
            hedge_premium_entry=150, hedge_premium_exit=50,
        )
        assert result["futures_entry"] > 0
        assert result["futures_exit"] > 0
        assert result["option_entry"] > 0
        assert result["option_exit"] > 0
        assert result["total"] == pytest.approx(
            result["futures_entry"] + result["futures_exit"]
            + result["option_entry"] + result["option_exit"]
        )

    def test_round_trip_no_hedge(self, cost_model):
        result = cost_model.compute_round_trip_cost(
            entry_price=22000, exit_price=22300,
            lot_size=75, lots=1,
        )
        assert result["option_entry"] == 0
        assert result["option_exit"] == 0

    def test_gst_applied_correctly(self, cost_model):
        result = cost_model.compute_futures_cost(22000, 75, 1, "buy")
        turnover = 22000 * 75 * 1
        expected_exchange = turnover * cost_model.futures_exchange_charge
        expected_sebi = turnover * cost_model.sebi_fee
        expected_gst = (20 + expected_exchange + expected_sebi) * 0.18
        assert result["gst"] == pytest.approx(expected_gst, rel=0.01)
