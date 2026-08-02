from datetime import date

import pytest

from backtester.costs import IndianFnOCostModel
from backtester.portfolio import Portfolio, Position


@pytest.fixture
def portfolio():
    return Portfolio(
        initial_capital=1_000_000,
        cost_model=IndianFnOCostModel(),
        max_positions=3,
        risk_per_trade_pct=0.5,
        trailing_step_pct=0.5,
    )


class TestPosition:
    def test_defaults(self):
        pos = Position(
            symbol="NIFTY", entry_date=date(2024, 6, 1),
            entry_price=22000, lots=1, lot_size=75,
            stop_loss=21700, target=22600, expiry=date(2024, 6, 27),
        )
        assert pos.highest_price_since_entry == 22000
        assert pos.current_trailing_stop == 21700


class TestPortfolio:
    def test_can_open_position(self, portfolio):
        assert portfolio.can_open_position() is True

    def test_open_position(self, portfolio):
        pos = portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=22600,
            lots=1, lot_size=75, expiry=date(2024, 6, 27),
        )
        assert pos is not None
        assert len(portfolio.positions) == 1
        assert portfolio.capital == 1_000_000
        assert pos.entry_costs > 0

    def test_max_positions_enforced(self, portfolio):
        for i in range(3):
            portfolio.open_position(
                symbol=f"SYM{i}", trade_date=date(2024, 6, 1),
                entry_price=22000, stop_loss=21700, target=22600,
                lots=1, lot_size=75, expiry=date(2024, 6, 27),
            )
        result = portfolio.open_position(
            symbol="EXTRA", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=22600,
            lots=1, lot_size=75, expiry=date(2024, 6, 27),
        )
        assert result is None
        assert len(portfolio.positions) == 3

    def test_close_position(self, portfolio):
        pos = portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=22600,
            lots=1, lot_size=75, expiry=date(2024, 6, 27),
        )
        trade = portfolio.close_position(pos, date(2024, 6, 10), 22300, "target")
        assert trade["net_pnl"] > 0
        assert trade["exit_reason"] == "target"
        assert len(portfolio.positions) == 0
        assert len(portfolio.closed_trades) == 1

    def test_record_equity(self, portfolio):
        portfolio.record_equity(date(2024, 6, 1), {"NIFTY": 22000})
        assert len(portfolio.equity_curve) == 1
        assert portfolio.equity_curve[0]["portfolio_value"] == portfolio.capital

    def test_trailing_stop_update(self, portfolio):
        pos = portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=22600,
            lots=1, lot_size=75, expiry=date(2024, 6, 27),
        )
        portfolio.update_trailing_stops({"NIFTY": 22200})
        assert pos.highest_price_since_entry == 22200
        assert pos.current_trailing_stop > 21700

    def test_trailing_stop_multi_step(self, portfolio):
        pos = portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=23000,
            lots=1, lot_size=75, expiry=date(2024, 6, 27),
        )
        portfolio.update_trailing_stops({"NIFTY": 22110})
        stop_after_1 = pos.current_trailing_stop
        assert stop_after_1 > 21700
        assert stop_after_1 < 22000

        portfolio.update_trailing_stops({"NIFTY": 22250})
        stop_after_2 = pos.current_trailing_stop
        assert stop_after_2 > stop_after_1

        portfolio.update_trailing_stops({"NIFTY": 22400})
        stop_after_3 = pos.current_trailing_stop
        assert stop_after_3 > stop_after_2

        assert stop_after_3 - 21700 < (22400 - 22000)

    def test_trailing_stop_never_moves_down(self, portfolio):
        pos = portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=23000,
            lots=1, lot_size=75, expiry=date(2024, 6, 27),
        )
        portfolio.update_trailing_stops({"NIFTY": 22300})
        stop_high = pos.current_trailing_stop

        portfolio.update_trailing_stops({"NIFTY": 22100})
        assert pos.current_trailing_stop == stop_high

    def test_total_margin_used_empty(self, portfolio):
        assert portfolio.total_margin_used() == 0

    def test_total_margin_used_with_positions(self, portfolio):
        portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=22600,
            lots=2, lot_size=75, expiry=date(2024, 6, 27),
        )
        portfolio.update_current_prices({"NIFTY": 22500})
        expected_margin = 22500 * 75 * 2 * (20.0 / 100)
        assert portfolio.total_margin_used() == expected_margin

    def test_total_margin_used_falls_back_to_entry_price(self, portfolio):
        portfolio.open_position(
            symbol="NIFTY", trade_date=date(2024, 6, 1),
            entry_price=22000, stop_loss=21700, target=22600,
            lots=2, lot_size=75, expiry=date(2024, 6, 27),
        )
        expected_margin = 22000 * 75 * 2 * (20.0 / 100)
        assert portfolio.total_margin_used() == expected_margin

    def test_can_afford_margin_under_cap(self, portfolio):
        assert portfolio.can_afford_margin(22000, 75, 1) is True

    def test_can_afford_margin_blocks_when_over_cap(self):
        portfolio = Portfolio(
            initial_capital=1_000_000,
            cost_model=IndianFnOCostModel(),
            margin_pct=20.0,
            max_total_margin_pct=75.0,
        )
        portfolio.open_position(
            symbol="SYM1", trade_date=date(2024, 6, 1),
            entry_price=5000, stop_loss=4800, target=5400,
            lots=10, lot_size=100, expiry=date(2024, 6, 27),
        )
        portfolio.open_position(
            symbol="SYM2", trade_date=date(2024, 6, 1),
            entry_price=5000, stop_loss=4800, target=5400,
            lots=10, lot_size=100, expiry=date(2024, 6, 27),
        )
        portfolio.update_current_prices({"SYM1": 5000, "SYM2": 5000})
        used = portfolio.total_margin_used()
        assert used == 2 * (5000 * 100 * 10 * 0.20)
        assert used == 2_000_000

        assert portfolio.can_afford_margin(5000, 100, 10) is False

    def test_can_afford_margin_allows_small_position(self):
        portfolio = Portfolio(
            initial_capital=1_000_000,
            cost_model=IndianFnOCostModel(),
            margin_pct=20.0,
            max_total_margin_pct=75.0,
        )
        portfolio.open_position(
            symbol="SYM1", trade_date=date(2024, 6, 1),
            entry_price=5000, stop_loss=4800, target=5400,
            lots=5, lot_size=100, expiry=date(2024, 6, 27),
        )
        assert portfolio.can_afford_margin(1000, 50, 1) is True

    def test_can_afford_margin_accounts_for_unrealized_loss(self):
        portfolio = Portfolio(
            initial_capital=1_000_000,
            cost_model=IndianFnOCostModel(),
            margin_pct=20.0,
            max_total_margin_pct=75.0,
        )
        portfolio.open_position(
            symbol="SYM1", trade_date=date(2024, 6, 1),
            entry_price=5000, stop_loss=4800, target=5400,
            lots=5, lot_size=100, expiry=date(2024, 6, 27),
        )
        portfolio.update_current_prices({"SYM1": 5000})
        assert portfolio.can_afford_margin(1000, 50, 1) is True

        portfolio.update_current_prices({"SYM1": 2000})
        assert portfolio.available_capital() < 1_000_000
        assert portfolio.can_afford_margin(1000, 50, 1) is False

    def test_margin_uses_mark_to_market_price(self):
        portfolio = Portfolio(
            initial_capital=1_000_000,
            cost_model=IndianFnOCostModel(),
            margin_pct=20.0,
            max_total_margin_pct=75.0,
        )
        portfolio.open_position(
            symbol="SYM1", trade_date=date(2024, 6, 1),
            entry_price=5000, stop_loss=4800, target=5400,
            lots=5, lot_size=100, expiry=date(2024, 6, 27),
        )
        portfolio.update_current_prices({"SYM1": 6000})
        expected_margin = 6000 * 100 * 5 * 0.20
        assert portfolio.total_margin_used() == expected_margin
