from datetime import date

import pytest

from backtester.results import BacktestResult


class TestBacktestResult:
    def test_compute_metrics(self):
        result = BacktestResult(
            symbol="NIFTY",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=1_000_000,
            final_capital=1_000_000,
        )
        trades = [
            {
                "symbol": "NIFTY", "entry_date": date(2024, 1, 5),
                "exit_date": date(2024, 1, 15), "entry_price": 22000,
                "exit_price": 22300, "lots": 1, "lot_size": 75,
                "stop_loss": 21700, "target": 22600, "exit_reason": "target",
                "futures_pnl": 22500, "hedge_premium_collected": 1000,
                "hedge_pnl": 800, "gross_pnl": 23300, "total_costs": 200,
                "net_pnl": 23100, "holding_days": 10,
            },
            {
                "symbol": "NIFTY", "entry_date": date(2024, 2, 1),
                "exit_date": date(2024, 2, 10), "entry_price": 22500,
                "exit_price": 22200, "lots": 1, "lot_size": 75,
                "stop_loss": 22200, "target": 23100, "exit_reason": "stop_loss",
                "futures_pnl": -22500, "hedge_premium_collected": 900,
                "hedge_pnl": 600, "gross_pnl": -21900, "total_costs": 180,
                "net_pnl": -22080, "holding_days": 9,
            },
        ]
        equity = [
            {
                "date": date(2024, 1, 5), "capital": 1_000_000,
                "unrealized_pnl": 0, "portfolio_value": 1_000_000,
                "open_positions": 1,
            },
            {
                "date": date(2024, 1, 15), "capital": 1_023_100,
                "unrealized_pnl": 0, "portfolio_value": 1_023_100,
                "open_positions": 0,
            },
            {
                "date": date(2024, 2, 1), "capital": 1_023_100,
                "unrealized_pnl": 0, "portfolio_value": 1_023_100,
                "open_positions": 1,
            },
            {
                "date": date(2024, 2, 10), "capital": 1_001_020,
                "unrealized_pnl": 0, "portfolio_value": 1_001_020,
                "open_positions": 0,
            },
        ]

        result.compute_metrics(trades, equity)

        assert result.total_trades == 2
        assert result.winning_trades == 1
        assert result.losing_trades == 1
        assert result.win_rate == pytest.approx(0.5)
        assert result.net_pnl == pytest.approx(23100 - 22080)

    def test_empty_trades(self):
        result = BacktestResult(
            symbol="NIFTY", start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31), initial_capital=1_000_000,
            final_capital=1_000_000,
        )
        result.compute_metrics([], [])
        assert result.total_trades == 0

    def test_summary_output(self):
        result = BacktestResult(
            symbol="NIFTY", start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31), initial_capital=1_000_000,
            final_capital=1_200_000, net_pnl=200_000,
        )
        s = result.summary()
        assert "NIFTY" in s
        assert "1,000,000" in s
