import pandas as pd
import pytest

from config.constants import OIBuildup
from strategies.ranker import MomentumRanker
from strategies.rule_schema import RankConfig, RankingFactor


@pytest.fixture
def rank_config():
    return RankConfig(
        factors=[
            RankingFactor(name="roc_20", weight=0.30),
            RankingFactor(name="adx", weight=0.25),
            RankingFactor(name="relative_strength", weight=0.20),
            RankingFactor(name="oi_buildup_score", weight=0.15),
            RankingFactor(name="volume_ratio", weight=0.10),
        ],
        top_n=3,
    )


@pytest.fixture
def ranker(rank_config):
    return MomentumRanker(rank_config)


def _make_candidates(n: int = 3) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "symbol": f"STOCK_{i}",
            "roc_20": (i + 1) * 5.0,
            "adx": 20 + (i + 1) * 5,
            "volume_ratio": 1.0 + i * 0.5,
            "oi_buildup": [
                OIBuildup.SHORT_BUILDUP.value,
                OIBuildup.SHORT_COVERING.value,
                OIBuildup.LONG_BUILDUP.value,
            ][i % 3],
            "close": 1000 + i * 100,
        })
    return pd.DataFrame(rows)


class TestMomentumRanker:
    def test_rank_orders_by_composite_score(self, ranker):
        candidates = _make_candidates(3)
        result = ranker.rank(candidates, nifty_roc=8.0)
        assert result.iloc[0]["symbol"] == "STOCK_2"
        assert result.iloc[0]["composite_score"] >= result.iloc[1]["composite_score"]

    def test_top_n_limits_output(self, ranker):
        candidates = _make_candidates(5)
        result = ranker.rank(candidates, nifty_roc=8.0)
        assert len(result) == 3

    def test_relative_strength_uses_nifty_roc(self, ranker):
        candidates = _make_candidates(2)
        result = ranker._compute_factor_values(candidates, nifty_roc=10.0)
        expected_rs_0 = 5.0 / 10.0
        expected_rs_1 = 10.0 / 10.0
        assert abs(result.iloc[0]["_rank_relative_strength"] - expected_rs_0) < 0.01
        assert abs(result.iloc[1]["_rank_relative_strength"] - expected_rs_1) < 0.01

    def test_oi_buildup_scoring(self, ranker):
        candidates = _make_candidates(3)
        result = ranker._compute_factor_values(candidates, nifty_roc=8.0)
        assert result.iloc[0]["_rank_oi_buildup_score"] == 0.0
        assert result.iloc[1]["_rank_oi_buildup_score"] == 0.5
        assert result.iloc[2]["_rank_oi_buildup_score"] == 1.0

    def test_handles_single_candidate(self, ranker):
        candidates = _make_candidates(1)
        result = ranker.rank(candidates, nifty_roc=8.0)
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "STOCK_0"

    def test_handles_nifty_roc_none(self, ranker):
        candidates = _make_candidates(3)
        result = ranker._compute_factor_values(candidates, nifty_roc=None)
        assert all(result["_rank_relative_strength"] == 1.0)
