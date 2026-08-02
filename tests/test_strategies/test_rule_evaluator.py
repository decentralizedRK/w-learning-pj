import pandas as pd
import pytest

from strategies.rule_evaluator import RuleEvaluator
from strategies.rule_schema import (
    Comparison,
    ConditionConfig,
    EntryRuleConfig,
    ExitRuleConfig,
)


@pytest.fixture
def evaluator():
    return RuleEvaluator()


@pytest.fixture
def bullish_row():
    return pd.Series({
        "close": 22500,
        "ema_20": 22200,
        "ema_50": 22000,
        "adx": 30,
        "rsi": 60,
        "volume": 1_500_000,
        "volume_sma_20": 1_000_000,
        "positive_oi_buildup": True,
        "pcr": 1.1,
    })


class TestRuleEvaluator:
    def test_gt_condition(self, evaluator, bullish_row):
        cond = ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25)
        assert evaluator.evaluate_condition(cond, bullish_row) is True

    def test_gte_condition(self, evaluator, bullish_row):
        cond = ConditionConfig(indicator="pcr", comparison=Comparison.GTE, value=0.9)
        assert evaluator.evaluate_condition(cond, bullish_row) is True

    def test_lt_condition(self, evaluator, bullish_row):
        cond = ConditionConfig(indicator="rsi", comparison=Comparison.LT, value=40)
        assert evaluator.evaluate_condition(cond, bullish_row) is False

    def test_between_condition(self, evaluator, bullish_row):
        cond = ConditionConfig(
            indicator="rsi", comparison=Comparison.BETWEEN, value_min=50, value_max=70
        )
        assert evaluator.evaluate_condition(cond, bullish_row) is True

    def test_reference_condition(self, evaluator, bullish_row):
        cond = ConditionConfig(
            indicator="close", comparison=Comparison.GT, reference="ema_20"
        )
        assert evaluator.evaluate_condition(cond, bullish_row) is True

    def test_bool_eq_condition(self, evaluator, bullish_row):
        cond = ConditionConfig(
            indicator="positive_oi_buildup", comparison=Comparison.EQ, value=True
        )
        assert evaluator.evaluate_condition(cond, bullish_row) is True

    def test_nan_returns_false(self, evaluator):
        row = pd.Series({"adx": float("nan")})
        cond = ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25)
        assert evaluator.evaluate_condition(cond, row) is False

    def test_missing_indicator_returns_false(self, evaluator):
        row = pd.Series({"rsi": 60})
        cond = ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25)
        assert evaluator.evaluate_condition(cond, row) is False

    def test_evaluate_entry_all_conditions(self, evaluator, bullish_row):
        entry = EntryRuleConfig(conditions=[
            ConditionConfig(indicator="close", comparison=Comparison.GT, reference="ema_20"),
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25),
            ConditionConfig(
                indicator="rsi", comparison=Comparison.BETWEEN,
                value_min=50, value_max=70,
            ),
        ])
        assert evaluator.evaluate_entry(entry, bullish_row) is True

    def test_evaluate_entry_fails_if_any_false(self, evaluator, bullish_row):
        entry = EntryRuleConfig(conditions=[
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25),
            ConditionConfig(indicator="rsi", comparison=Comparison.LT, value=40),
        ])
        assert evaluator.evaluate_entry(entry, bullish_row) is False

    def test_evaluate_exit_any_triggers(self, evaluator, bullish_row):
        exit_conf = ExitRuleConfig(conditions=[
            ConditionConfig(indicator="rsi", comparison=Comparison.LT, value=40),
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25),
        ])
        assert evaluator.evaluate_exit(exit_conf, bullish_row) is True

    def test_evaluate_signals_adds_columns(self, evaluator):
        df = pd.DataFrame({
            "close": [100, 105],
            "ema_20": [95, 100],
            "adx": [30, 20],
        })
        entry = EntryRuleConfig(conditions=[
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25),
        ])
        exit_conf = ExitRuleConfig(conditions=[
            ConditionConfig(indicator="adx", comparison=Comparison.LT, value=22),
        ])
        result = evaluator.evaluate_signals(entry, exit_conf, df)
        assert "entry_signal" in result.columns
        assert "exit_signal" in result.columns
        assert result.iloc[0]["entry_signal"]
        assert result.iloc[1]["exit_signal"]
