from datetime import date as d

import pytest

from backtester.engine import BacktestEngine, MultiSymbolBacktestEngine
from backtester.portfolio import Position
from config.fo_segments import LARGECAP_FO, MIDCAP_FO, SEGMENT_MAP, SMALLCAP_FO
from strategies.momentum_futures import MomentumFuturesCoveredCall
from strategies.ranker import MomentumRanker
from strategies.rule_schema import (
    Comparison,
    ConditionConfig,
    EntryRuleConfig,
    ExitRuleConfig,
    RankConfig,
    RankingFactor,
    ScreenConfig,
    StrategyConfig,
)
from strategies.screener import UniverseScreener


@pytest.fixture
def strategy():
    config = StrategyConfig(
        name="test",
        entry=EntryRuleConfig(conditions=[
            ConditionConfig(indicator="adx", comparison=Comparison.GT, value=25),
        ]),
        exit=ExitRuleConfig(conditions=[
            ConditionConfig(indicator="rsi", comparison=Comparison.LT, value=40),
        ]),
    )
    return MomentumFuturesCoveredCall(config)


@pytest.fixture
def screener():
    config = ScreenConfig(conditions=[
        ConditionConfig(indicator="adx", comparison=Comparison.GT, value=20),
    ])
    return UniverseScreener(config)


@pytest.fixture
def ranker():
    config = RankConfig(
        factors=[RankingFactor(name="roc_20", weight=1.0)],
        top_n=5,
    )
    return MomentumRanker(config)


@pytest.fixture
def engine(strategy, screener, ranker):
    return MultiSymbolBacktestEngine(
        strategy=strategy,
        screener=screener,
        ranker=ranker,
        universe=["RELIANCE", "TCS"],
        initial_capital=1_000_000,
    )


class TestMultiSymbolBacktestEngine:
    def test_margin_check_sufficient(self, engine):
        assert engine._check_margin(price=500, lots=1, lot_size=100) is True

    def test_margin_check_insufficient(self, engine):
        assert engine._check_margin(price=50000, lots=100, lot_size=500) is False

    def test_no_duplicate_positions(self, engine):
        engine.portfolio.open_position(
            symbol="RELIANCE",
            trade_date=d(2025, 1, 1),
            entry_price=2500,
            stop_loss=2400,
            target=2700,
            lots=1,
            lot_size=250,
            expiry=d(2025, 1, 30),
        )
        held = {p.symbol for p in engine.portfolio.positions}
        assert "RELIANCE" in held
        assert engine.portfolio.can_open_position() is True

    def test_respects_max_positions(self, engine):
        for i, sym in enumerate(["SYM_A", "SYM_B", "SYM_C"]):
            engine.portfolio.open_position(
                symbol=sym,
                trade_date=d(2025, 1, 1),
                entry_price=1000,
                stop_loss=950,
                target=1100,
                lots=1,
                lot_size=100,
                expiry=d(2025, 1, 30),
            )
        assert engine.portfolio.can_open_position() is False


class TestStrikeIntervals:
    def test_strike_interval_low_price(self):
        assert BacktestEngine._strike_interval(200) == 2.5

    def test_strike_interval_mid_price(self):
        assert BacktestEngine._strike_interval(400) == 5.0

    def test_strike_interval_high_price(self):
        assert BacktestEngine._strike_interval(800) == 10.0

    def test_strike_interval_large_cap(self):
        assert BacktestEngine._strike_interval(2000) == 50.0

    def test_strike_interval_very_high_price(self):
        assert BacktestEngine._strike_interval(6000) == 100.0

    def test_generate_strikes_covers_otm_range(self, engine):
        strikes = engine._generate_strikes(500)
        target_min = 500 * 1.03
        target_max = 500 * 1.05
        otm_candidates = [s for s in strikes if target_min <= s <= target_max]
        assert len(otm_candidates) > 0


class TestHedgeExitEstimation:
    def test_hedge_exit_otm(self, engine):
        pos = Position(
            symbol="RELIANCE", entry_date=d(2025, 1, 1),
            entry_price=2500, lots=1, lot_size=250,
            stop_loss=2400, target=2700, expiry=d(2025, 1, 30),
            hedge_strike=2600,
        )
        premium = engine._estimate_hedge_exit(pos, 2500, d(2025, 1, 15))
        assert premium >= 0
        assert premium < 100

    def test_hedge_exit_itm(self, engine):
        pos = Position(
            symbol="RELIANCE", entry_date=d(2025, 1, 1),
            entry_price=2500, lots=1, lot_size=250,
            stop_loss=2400, target=2800, expiry=d(2025, 1, 30),
            hedge_strike=2600,
        )
        premium = engine._estimate_hedge_exit(pos, 2700, d(2025, 1, 15))
        intrinsic = 2700 - 2600
        assert premium == pytest.approx(intrinsic * 1.05)

    def test_hedge_exit_no_hedge(self, engine):
        pos = Position(
            symbol="RELIANCE", entry_date=d(2025, 1, 1),
            entry_price=2500, lots=1, lot_size=250,
            stop_loss=2400, target=2700, expiry=d(2025, 1, 30),
        )
        assert engine._estimate_hedge_exit(pos, 2500, d(2025, 1, 15)) == 0


class TestResolveUniverse:
    def test_fo_universe_returns_full_list(self):
        result = MultiSymbolBacktestEngine._resolve_universe(["FO_UNIVERSE"])
        assert len(result) > 100

    def test_largecap_segment(self):
        result = MultiSymbolBacktestEngine._resolve_universe(["LARGECAP_FO"])
        assert set(result) == set(LARGECAP_FO)
        assert len(result) > 0

    def test_midcap_segment(self):
        result = MultiSymbolBacktestEngine._resolve_universe(["MIDCAP_FO"])
        assert set(result) == set(MIDCAP_FO)
        assert len(result) > 0

    def test_smallcap_segment(self):
        result = MultiSymbolBacktestEngine._resolve_universe(["SMALLCAP_FO"])
        assert set(result) == set(SMALLCAP_FO)
        assert len(result) > 0

    def test_multiple_segments_merged(self):
        result = MultiSymbolBacktestEngine._resolve_universe(
            ["LARGECAP_FO", "MIDCAP_FO"]
        )
        assert set(result) == set(LARGECAP_FO) | set(MIDCAP_FO)
        assert len(result) == len(set(LARGECAP_FO) | set(MIDCAP_FO))

    def test_all_segments_merged(self):
        result = MultiSymbolBacktestEngine._resolve_universe(
            ["LARGECAP_FO", "MIDCAP_FO", "SMALLCAP_FO"]
        )
        expected = set(LARGECAP_FO) | set(MIDCAP_FO) | set(SMALLCAP_FO)
        assert set(result) == expected

    def test_explicit_symbols_passthrough(self):
        result = MultiSymbolBacktestEngine._resolve_universe(["RELIANCE", "TCS"])
        assert result == ["RELIANCE", "TCS"]

    def test_empty_config_returns_full_list(self):
        result = MultiSymbolBacktestEngine._resolve_universe([])
        assert len(result) > 100

    def test_segment_map_has_all_keys(self):
        assert set(SEGMENT_MAP.keys()) == {"LARGECAP_FO", "MIDCAP_FO", "SMALLCAP_FO"}
