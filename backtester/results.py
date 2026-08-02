from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from pandas.api.types import is_float_dtype, is_integer_dtype

from backtester.regimes import MARKET_REGIMES, filter_trades_by_regime
from config.constants import RBI_REPO_RATE


@dataclass
class BacktestResult:
    symbol: str
    start_date: date
    end_date: date
    initial_capital: float
    final_capital: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_costs: float = 0.0
    net_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_holding_days: float = 0.0
    max_consecutive_losses: int = 0
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    regime_results: dict = field(default_factory=dict)

    def compute_metrics(self, closed_trades: list[dict], equity_data: list[dict]) -> None:
        if not closed_trades:
            return

        self.trades = pd.DataFrame(closed_trades)
        self.equity_curve = pd.DataFrame(equity_data)

        self.total_trades = len(closed_trades)
        self.winning_trades = len(self.trades[self.trades["net_pnl"] > 0])
        self.losing_trades = len(self.trades[self.trades["net_pnl"] <= 0])
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0

        self.total_pnl = self.trades["gross_pnl"].sum()
        self.total_costs = self.trades["total_costs"].sum()
        self.net_pnl = self.trades["net_pnl"].sum()
        self.final_capital = self.initial_capital + self.net_pnl

        self.avg_trade_pnl = self.trades["net_pnl"].mean()
        self.avg_holding_days = self.trades["holding_days"].mean()

        gross_profit = self.trades[self.trades["net_pnl"] > 0]["net_pnl"].sum()
        gross_loss = abs(self.trades[self.trades["net_pnl"] <= 0]["net_pnl"].sum())
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        winners = self.trades[self.trades["net_pnl"] > 0]
        losers = self.trades[self.trades["net_pnl"] <= 0]
        avg_win = winners["net_pnl"].mean() if self.winning_trades > 0 else 0
        avg_loss = abs(losers["net_pnl"].mean()) if self.losing_trades > 0 else 0
        self.expectancy = (self.win_rate * avg_win) - ((1 - self.win_rate) * avg_loss)

        if not self.equity_curve.empty and "portfolio_value" in self.equity_curve.columns:
            eq = self.equity_curve["portfolio_value"]
            running_max = eq.cummax()
            drawdowns = (eq - running_max) / running_max * 100
            self.max_drawdown_pct = abs(drawdowns.min())

            in_drawdown = drawdowns < 0
            if in_drawdown.any():
                groups = (~in_drawdown).cumsum()
                dd_groups = in_drawdown.groupby(groups)
                self.max_drawdown_duration_days = dd_groups.sum().max()

            days = (self.end_date - self.start_date).days
            years = days / 365.25
            if years > 0 and self.final_capital > 0:
                self.cagr = ((self.final_capital / self.initial_capital) ** (1 / years) - 1) * 100

            daily_returns = eq.pct_change().dropna()
            if len(daily_returns) > 1 and daily_returns.std() > 0:
                rf_daily = (1 + RBI_REPO_RATE / 100) ** (1 / 252) - 1
                excess_returns = daily_returns - rf_daily
                self.sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
                downside = excess_returns[excess_returns < 0]
                if len(downside) > 0 and downside.std() > 0:
                    self.sortino_ratio = (excess_returns.mean() / downside.std()) * np.sqrt(252)

        losses = self.trades["net_pnl"] < 0
        max_consec = 0
        current_consec = 0
        for is_loss in losses:
            if is_loss:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0
        self.max_consecutive_losses = max_consec

        for regime_name in MARKET_REGIMES:
            regime_trades = filter_trades_by_regime(closed_trades, regime_name)
            if regime_trades:
                regime_df = pd.DataFrame(regime_trades)
                self.regime_results[regime_name] = {
                    "trades": len(regime_trades),
                    "net_pnl": round(regime_df["net_pnl"].sum(), 2),
                    "win_rate": len(regime_df[regime_df["net_pnl"] > 0]) / len(regime_df),
                    "avg_pnl": round(regime_df["net_pnl"].mean(), 2),
                }

    @staticmethod
    def _df_to_records(df: pd.DataFrame) -> list[dict]:
        if df.empty:
            return []
        result_df = df.copy()
        for col in result_df.columns:
            if pd.api.types.is_datetime64_any_dtype(result_df[col]):
                result_df[col] = result_df[col].dt.strftime("%Y-%m-%d")
            elif result_df[col].apply(lambda v: isinstance(v, date)).any():
                result_df[col] = result_df[col].apply(
                    lambda v: v.isoformat() if isinstance(v, date) else v
                )
            elif is_float_dtype(result_df[col]):
                result_df[col] = result_df[col].astype(float)
            elif is_integer_dtype(result_df[col]):
                result_df[col] = result_df[col].astype(int)
        return result_df.to_dict(orient="records")

    def to_dict(self) -> dict:
        trades_list = self._df_to_records(self.trades)
        equity_list = self._df_to_records(self.equity_curve)

        return {
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": float(self.initial_capital),
            "final_capital": float(round(self.final_capital, 2)),
            "total_trades": int(self.total_trades),
            "winning_trades": int(self.winning_trades),
            "losing_trades": int(self.losing_trades),
            "win_rate": float(round(self.win_rate * 100, 1)),
            "total_pnl": float(round(self.total_pnl, 2)),
            "total_costs": float(round(self.total_costs, 2)),
            "net_pnl": float(round(self.net_pnl, 2)),
            "max_drawdown_pct": float(round(self.max_drawdown_pct, 1)),
            "max_drawdown_duration_days": int(self.max_drawdown_duration_days),
            "cagr": float(round(self.cagr, 1)),
            "sharpe_ratio": float(round(self.sharpe_ratio, 2)),
            "sortino_ratio": float(round(self.sortino_ratio, 2)),
            "profit_factor": float(round(self.profit_factor, 2)),
            "expectancy": float(round(self.expectancy, 2)),
            "avg_trade_pnl": float(round(self.avg_trade_pnl, 2)),
            "avg_holding_days": float(round(self.avg_holding_days, 1)),
            "max_consecutive_losses": int(self.max_consecutive_losses),
            "regime_results": self.regime_results,
            "trades": trades_list,
            "equity_curve": equity_list,
        }

    def summary(self) -> str:
        lines = [
            f"=== Backtest: {self.symbol} "
            f"({self.start_date} to {self.end_date}) ===",
            f"Capital: {self.initial_capital:,.0f} -> "
            f"{self.final_capital:,.0f}",
            f"Net P&L: {self.net_pnl:+,.0f} | "
            f"Total Costs: {self.total_costs:,.0f}",
            f"CAGR: {self.cagr:.1f}% | Sharpe: "
            f"{self.sharpe_ratio:.2f} | "
            f"Sortino: {self.sortino_ratio:.2f}",
            f"Trades: {self.total_trades} | "
            f"Win: {self.winning_trades} | "
            f"Loss: {self.losing_trades} | "
            f"Win Rate: {self.win_rate:.1%}",
            f"Avg P&L: {self.avg_trade_pnl:+,.0f} | "
            f"Avg Hold: {self.avg_holding_days:.0f} days",
            f"Max DD: {self.max_drawdown_pct:.1f}% | "
            f"Max Consec Loss: {self.max_consecutive_losses}",
            f"Profit Factor: {self.profit_factor:.2f} | "
            f"Expectancy: {self.expectancy:+,.0f}",
        ]
        if self.regime_results:
            lines.append("\n--- Regime Breakdown ---")
            for name, metrics in self.regime_results.items():
                lines.append(
                    f"  {name}: {metrics['trades']} trades, "
                    f"P&L={metrics['net_pnl']:+,.0f}, "
                    f"Win={metrics['win_rate']:.0%}"
                )
        return "\n".join(lines)
