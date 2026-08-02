from pathlib import Path

import pandas as pd
from loguru import logger

from backtester.results import BacktestResult


class TearsheetGenerator:
    def __init__(self, result: BacktestResult):
        self.result = result

    def generate_html(
        self, output_path: Path, benchmark: str = "^NSEI"
    ) -> Path | None:
        try:
            import quantstats as qs
        except ImportError:
            logger.error("quantstats not installed")
            return None

        if self.result.equity_curve.empty:
            logger.warning("No equity curve data for tearsheet")
            return None

        eq = self.result.equity_curve.copy()
        eq["date"] = pd.to_datetime(eq["date"])
        eq = eq.set_index("date")
        returns = eq["portfolio_value"].pct_change().dropna()
        returns.index = pd.to_datetime(returns.index)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            qs.reports.html(
                returns,
                benchmark=benchmark,
                output=str(output_path),
                title=(
                    f"Backtest: {self.result.symbol} "
                    f"({self.result.start_date} to {self.result.end_date})"
                ),
                download_filename=str(output_path),
            )
            logger.info(f"Tearsheet saved to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to generate tearsheet: {e}")
            return None

    def generate_regime_report(self) -> pd.DataFrame:
        if not self.result.regime_results:
            return pd.DataFrame()
        rows = []
        for name, metrics in self.result.regime_results.items():
            rows.append({"regime": name, **metrics})
        return pd.DataFrame(rows)

    def print_summary(self) -> None:
        print(self.result.summary())
