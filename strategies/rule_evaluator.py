import pandas as pd

from strategies.rule_schema import Comparison, ConditionConfig, EntryRuleConfig, ExitRuleConfig


class RuleEvaluator:
    def evaluate_condition(self, condition: ConditionConfig, data: pd.Series) -> bool:
        indicator_value = data.get(condition.indicator)
        if indicator_value is None or (
            isinstance(indicator_value, float) and pd.isna(indicator_value)
        ):
            return False

        if condition.comparison == Comparison.BETWEEN:
            if condition.value_min is None or condition.value_max is None:
                return False
            return condition.value_min <= float(indicator_value) <= condition.value_max

        if condition.reference:
            compare_value = data.get(condition.reference)
            if compare_value is None or (
                isinstance(compare_value, float) and pd.isna(compare_value)
            ):
                return False
        else:
            compare_value = condition.value

        if compare_value is None:
            return False

        match condition.comparison:
            case Comparison.GT:
                return float(indicator_value) > float(compare_value)
            case Comparison.GTE:
                return float(indicator_value) >= float(compare_value)
            case Comparison.LT:
                return float(indicator_value) < float(compare_value)
            case Comparison.LTE:
                return float(indicator_value) <= float(compare_value)
            case Comparison.EQ:
                if isinstance(condition.value, bool):
                    return bool(indicator_value) == condition.value
                return indicator_value == compare_value
            case _:
                return False

    def evaluate_entry(self, entry_config: EntryRuleConfig, data: pd.Series) -> bool:
        return all(self.evaluate_condition(c, data) for c in entry_config.conditions)

    def evaluate_exit(self, exit_config: ExitRuleConfig, data: pd.Series) -> bool:
        return any(self.evaluate_condition(c, data) for c in exit_config.conditions)

    def evaluate_signals(
        self, entry_config: EntryRuleConfig, exit_config: ExitRuleConfig, df: pd.DataFrame
    ) -> pd.DataFrame:
        result = df.copy()
        result["entry_signal"] = result.apply(
            lambda row: self.evaluate_entry(entry_config, row), axis=1
        )
        result["exit_signal"] = result.apply(
            lambda row: self.evaluate_exit(exit_config, row), axis=1
        )
        return result
