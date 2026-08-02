from datetime import date

import pytest

from strategies.momentum_futures import MomentumFuturesCoveredCall
from strategies.rule_schema import (
    Comparison,
    ConditionConfig,
    EntryRuleConfig,
    ExitRuleConfig,
    HedgeConfig,
    PositionSizingConfig,
    StopLossConfig,
    StrategyConfig,
    TargetConfig,
)


@pytest.fixture
def strategy():
    config = StrategyConfig(
        name="test_strategy",
        entry=EntryRuleConfig(conditions=[
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25),
        ]),
        exit=ExitRuleConfig(conditions=[
            ConditionConfig(indicator="rsi", comparison=Comparison.LT, value=40),
        ]),
        stop_loss=StopLossConfig(initial_atr_multiple=1.5, initial_percent=0.8),
        position_sizing=PositionSizingConfig(risk_per_trade_pct=0.5),
        target=TargetConfig(risk_reward_ratio=2.0),
        hedge=HedgeConfig(enabled=True, otm_pct_min=3.0, otm_pct_max=5.0),
    )
    return MomentumFuturesCoveredCall(config)


class TestMomentumFuturesCoveredCall:
    def test_compute_stop_loss_atr_based(self, strategy):
        sl = strategy.compute_stop_loss(entry_price=22000, atr=200)
        atr_sl = 22000 - (1.5 * 200)
        pct_sl = 22000 * (1 - 0.8 / 100)
        assert sl == min(atr_sl, pct_sl)

    def test_compute_stop_loss_percent_based(self, strategy):
        sl = strategy.compute_stop_loss(entry_price=22000, atr=50)
        atr_sl = 22000 - (1.5 * 50)
        pct_sl = 22000 * (1 - 0.8 / 100)
        assert sl == min(atr_sl, pct_sl)

    def test_compute_position_size(self, strategy):
        lots = strategy.compute_position_size(
            capital=1_000_000, entry_price=22000, stop_loss=21700, lot_size=75
        )
        risk_amount = 1_000_000 * 0.005
        risk_per_lot = 300 * 75
        expected = int(risk_amount / risk_per_lot)
        assert lots == expected

    def test_compute_position_size_skips_when_risk_too_high(self, strategy):
        lots = strategy.compute_position_size(
            capital=100_000, entry_price=22000, stop_loss=21000, lot_size=75
        )
        assert lots == 0

    def test_compute_target(self, strategy):
        target = strategy.compute_target(entry_price=22000, stop_loss=21700)
        risk = 22000 - 21700
        assert target == 22000 + (2.0 * risk)

    def test_select_hedge(self, strategy):
        strikes = [s for s in range(22000, 24000, 100)]
        result = strategy.select_hedge(
            entry_price=22000,
            entry_date=date(2024, 6, 1),
            expiry=date(2024, 6, 27),
            available_strikes=strikes,
        )
        assert result is not None
        assert "strike" in result
        assert "premium" in result
        assert result["strike"] >= 22000 * 1.03

    def test_should_roll_far_from_expiry(self, strategy):
        import pandas as pd
        row = pd.Series({"adx": 30})
        assert strategy.should_roll(date(2024, 6, 1), date(2024, 6, 27), row) is False

    def test_should_roll_near_expiry_invalid(self, strategy):
        import pandas as pd
        row = pd.Series({"adx": 20})
        result = strategy.should_roll(date(2024, 6, 23), date(2024, 6, 27), row)
        assert result is False
