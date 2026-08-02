from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

from backtester.costs import IndianFnOCostModel
from backtester.portfolio import Portfolio
from backtester.results import BacktestResult
from config.fo_segments import SEGMENT_MAP
from data.fetchers.nse_symbols import FO_STOCK_LIST, get_lot_size
from data.storage.duckdb_engine import DuckDBEngine
from indicators.greeks import GreeksCalculator
from indicators.technical import TechnicalIndicators
from strategies.momentum_futures import MomentumFuturesCoveredCall
from strategies.ranker import MomentumRanker
from strategies.screener import UniverseScreener


class BacktestEngine:
    def __init__(
        self,
        strategy: MomentumFuturesCoveredCall,
        initial_capital: float = 1_000_000,
        parquet_dir: Path = Path("data_store/parquet"),
    ):
        self.strategy = strategy
        self.cost_model = IndianFnOCostModel()
        self.portfolio = Portfolio(
            initial_capital=initial_capital,
            cost_model=self.cost_model,
            max_positions=strategy.config.position_sizing.max_concurrent_positions,
            risk_per_trade_pct=strategy.config.position_sizing.risk_per_trade_pct,
            trailing_step_pct=strategy.config.stop_loss.trailing_step_pct,
            margin_pct=strategy.config.capacity.margin_pct,
            max_total_margin_pct=strategy.config.capacity.max_total_margin_pct,
        )
        self.duckdb = DuckDBEngine(parquet_dir)
        self.greeks = GreeksCalculator()

    def run(self, symbol: str, start: date, end: date) -> BacktestResult:
        logger.info(f"Starting backtest: {symbol} from {start} to {end}")

        equity_df = self.duckdb.query_equity(symbol, start, end)
        if equity_df.empty:
            logger.error(f"No equity data for {symbol}")
            return self._empty_result(symbol, start, end)

        futures_df = self.duckdb.query_near_month_futures(symbol, start, end)
        pcr_df = self.duckdb.compute_pcr_series(symbol, start, end)

        enriched = self.strategy.prepare_data(equity_df, futures_df, pcr_df=pcr_df)
        enriched = self.strategy.generate_signals(enriched)

        expiries = self._build_expiry_calendar(futures_df)

        for idx, row in enriched.iterrows():
            current_date = row["date"]
            if isinstance(current_date, pd.Timestamp):
                current_date = current_date.date()

            current_price = row["close"]
            current_expiry = self._get_current_expiry(current_date, expiries)

            for pos in list(self.portfolio.positions):
                if pos.symbol != symbol:
                    continue

                if row["low"] <= pos.current_trailing_stop:
                    exit_price = min(row["open"], pos.current_trailing_stop)
                    h = self._estimate_hedge_exit(pos, exit_price, current_date)
                    self.portfolio.close_position(
                        pos, current_date, exit_price, "stop_loss", h
                    )
                    continue

                if row["high"] >= pos.target:
                    exit_price = max(row["open"], pos.target)
                    h = self._estimate_hedge_exit(pos, exit_price, current_date)
                    self.portfolio.close_position(
                        pos, current_date, exit_price, "target", h
                    )
                    continue

                if row.get("exit_signal", False):
                    h = self._estimate_hedge_exit(pos, current_price, current_date)
                    self.portfolio.close_position(
                        pos, current_date, current_price, "signal_exit", h
                    )
                    continue

                if current_expiry and self.strategy.should_roll(
                    current_date, pos.expiry, row
                ):
                    h = self._estimate_hedge_exit(pos, current_price, current_date)
                    self.portfolio.close_position(
                        pos, current_date, current_price, "roll", h
                    )

            self.portfolio.update_trailing_stops({symbol: current_price})

            if row.get("entry_signal", False) and self.portfolio.can_open_position():
                atr = row.get("atr", current_price * 0.008)
                if pd.isna(atr):
                    atr = current_price * 0.008

                lot_size = get_lot_size(symbol, current_date)
                sl = self.strategy.compute_stop_loss(current_price, atr)
                target = self.strategy.compute_target(current_price, sl)
                lots = self.strategy.compute_position_size(
                    self.portfolio.capital, current_price, sl, lot_size
                )
                if lots <= 0:
                    continue

                hedge_premium = 0.0
                hedge_strike = None
                if self.strategy.config.hedge.enabled and current_expiry:
                    available_strikes = self._generate_strikes(current_price)
                    hedge_info = self.strategy.select_hedge(
                        current_price, current_date, current_expiry, available_strikes
                    )
                    if hedge_info:
                        hedge_strike = hedge_info["strike"]
                        hedge_premium = hedge_info["premium"]

                self.portfolio.open_position(
                    symbol=symbol,
                    trade_date=current_date,
                    entry_price=current_price,
                    stop_loss=sl,
                    target=target,
                    lots=lots,
                    lot_size=lot_size,
                    expiry=current_expiry or current_date,
                    hedge_strike=hedge_strike,
                    hedge_premium=hedge_premium,
                )

            self.portfolio.record_equity(current_date, {symbol: current_price})

        for pos in list(self.portfolio.positions):
            last_price = enriched.iloc[-1]["close"]
            last_date = enriched.iloc[-1]["date"]
            if isinstance(last_date, pd.Timestamp):
                last_date = last_date.date()
            h = self._estimate_hedge_exit(pos, last_price, last_date)
            self.portfolio.close_position(
                pos, last_date, last_price, "end_of_backtest", h
            )

        result = BacktestResult(
            symbol=symbol,
            start_date=start,
            end_date=end,
            initial_capital=self.portfolio.initial_capital,
            final_capital=self.portfolio.capital,
        )
        result.compute_metrics(self.portfolio.closed_trades, self.portfolio.equity_curve)
        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"Net P&L: {result.net_pnl:+,.0f}"
        )
        return result

    def _build_expiry_calendar(self, futures_df: pd.DataFrame) -> list[date]:
        if futures_df.empty or "expiry" not in futures_df.columns:
            return []
        expiries = sorted(futures_df["expiry"].dropna().unique())
        return [e.date() if isinstance(e, pd.Timestamp) else e for e in expiries]

    def _get_current_expiry(self, current_date: date, expiries: list[date]) -> date | None:
        for exp in expiries:
            if exp >= current_date:
                return exp
        return expiries[-1] if expiries else None

    @staticmethod
    def _strike_interval(price: float) -> float:
        if price <= 250:
            return 2.5
        if price <= 500:
            return 5.0
        if price <= 1000:
            return 10.0
        if price <= 2500:
            return 50.0
        if price <= 5000:
            return 50.0
        return 100.0

    def _generate_strikes(self, price: float) -> list[float]:
        interval = self._strike_interval(price)
        base = round(price / interval) * interval
        return [base + i * interval for i in range(-20, 21)]

    def _estimate_hedge_exit(
        self, position, underlying_price: float, current_date: date
    ) -> float:
        if position.hedge_strike is None:
            return 0
        days_remaining = max(1, (position.expiry - current_date).days)
        if underlying_price < position.hedge_strike:
            return max(0, self.greeks.estimate_option_premium(
                underlying_price, position.hedge_strike, days_remaining, iv=15.0
            ))
        intrinsic = underlying_price - position.hedge_strike
        return intrinsic * 1.05

    def _empty_result(self, symbol: str, start: date, end: date) -> BacktestResult:
        return BacktestResult(
            symbol=symbol,
            start_date=start,
            end_date=end,
            initial_capital=self.portfolio.initial_capital,
            final_capital=self.portfolio.initial_capital,
        )


class MultiSymbolBacktestEngine:
    def __init__(
        self,
        strategy: MomentumFuturesCoveredCall,
        screener: UniverseScreener,
        ranker: MomentumRanker,
        universe: list[str] | None = None,
        initial_capital: float = 1_000_000,
        parquet_dir: Path = Path("data_store/parquet"),
        margin_pct: float = 20.0,
        max_position_value_pct: float = 30.0,
        max_total_margin_pct: float = 75.0,
    ):
        self.strategy = strategy
        self.screener = screener
        self.ranker = ranker
        self.universe = universe or self._resolve_universe(strategy.config.universe)
        self.cost_model = IndianFnOCostModel()
        self.margin_pct = margin_pct
        self.max_position_value_pct = max_position_value_pct
        self.portfolio = Portfolio(
            initial_capital=initial_capital,
            cost_model=self.cost_model,
            max_positions=strategy.config.position_sizing.max_concurrent_positions,
            risk_per_trade_pct=strategy.config.position_sizing.risk_per_trade_pct,
            trailing_step_pct=strategy.config.stop_loss.trailing_step_pct,
            margin_pct=margin_pct,
            max_total_margin_pct=max_total_margin_pct,
        )
        self.duckdb = DuckDBEngine(parquet_dir)
        self.greeks = GreeksCalculator()

    @staticmethod
    def _resolve_universe(universe_config: list[str]) -> list[str]:
        if not universe_config:
            return FO_STOCK_LIST
        if "FO_UNIVERSE" in universe_config:
            return FO_STOCK_LIST
        segment_keys = [k for k in universe_config if k in SEGMENT_MAP]
        if segment_keys:
            seen: set[str] = set()
            merged: list[str] = []
            for key in segment_keys:
                for sym in SEGMENT_MAP[key]:
                    if sym not in seen:
                        seen.add(sym)
                        merged.append(sym)
            return merged
        return universe_config

    def run(self, start: date, end: date) -> BacktestResult:
        logger.info(
            f"Multi-symbol backtest: {len(self.universe)} stocks, {start} to {end}"
        )

        enriched_data, nifty_enriched = self._preload_all_data(start, end)
        if not enriched_data:
            return self._empty_result(start, end)

        all_dates = sorted({
            d for df in enriched_data.values()
            for d in self._extract_dates(df)
            if start <= d <= end
        })

        if not all_dates:
            return self._empty_result(start, end)

        expiry_calendar = self._build_expiry_calendar(enriched_data)

        for trading_date in all_dates:
            current_expiry = self._get_current_expiry(trading_date, expiry_calendar)

            self._manage_positions(trading_date, enriched_data, current_expiry)

            if self.portfolio.can_open_position():
                self._screen_rank_enter(
                    trading_date, enriched_data, nifty_enriched, current_expiry
                )

            current_prices = {}
            for sym, df in enriched_data.items():
                row = self._get_row(df, trading_date)
                if row is not None:
                    current_prices[sym] = row["close"]
            self.portfolio.record_equity(trading_date, current_prices)

        self._close_remaining(enriched_data, all_dates[-1])

        result = BacktestResult(
            symbol="FO_UNIVERSE",
            start_date=start,
            end_date=end,
            initial_capital=self.portfolio.initial_capital,
            final_capital=self.portfolio.capital,
        )
        result.compute_metrics(
            self.portfolio.closed_trades, self.portfolio.equity_curve
        )
        logger.info(
            f"Multi-symbol backtest complete: {result.total_trades} trades, "
            f"Net P&L: {result.net_pnl:+,.0f}"
        )
        return result

    def _preload_all_data(
        self, start: date, end: date
    ) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
        enriched_data: dict[str, pd.DataFrame] = {}

        for symbol in self.universe:
            equity_df = self.duckdb.query_equity(symbol, start, end)
            if equity_df.empty:
                logger.debug(f"No data for {symbol}, skipping")
                continue

            futures_df = self.duckdb.query_near_month_futures(symbol, start, end)
            pcr_df = self.duckdb.compute_pcr_series(symbol, start, end)

            enriched = self.strategy.prepare_data(
                equity_df, futures_df, pcr_df=pcr_df
            )
            enriched = self.strategy.generate_signals(enriched)

            lot_size = get_lot_size(symbol, end)
            enriched = TechnicalIndicators.add_roc(enriched, 20)
            enriched = TechnicalIndicators.add_volume_ratio(enriched, 20)
            enriched["lot_value"] = enriched["close"] * lot_size
            enriched["_lot_size"] = lot_size
            enriched["symbol"] = symbol

            enriched_data[symbol] = enriched

        nifty_enriched = pd.DataFrame()
        if "NIFTY" not in enriched_data:
            nifty_equity = self.duckdb.query_equity("NIFTY", start, end)
            if not nifty_equity.empty:
                nifty_enriched = TechnicalIndicators.add_all_strategy_indicators(
                    nifty_equity.copy()
                )
                nifty_enriched = TechnicalIndicators.add_roc(nifty_enriched, 20)
        else:
            nifty_enriched = enriched_data["NIFTY"]

        return enriched_data, nifty_enriched

    def _extract_dates(self, df: pd.DataFrame) -> list[date]:
        if "date" not in df.columns or df.empty:
            return []
        dates = []
        for d in df["date"]:
            if isinstance(d, pd.Timestamp):
                dates.append(d.date())
            else:
                dates.append(d)
        return dates

    def _get_row(self, df: pd.DataFrame, trading_date: date) -> pd.Series | None:
        if "date" not in df.columns:
            return None
        for idx, row in df.iterrows():
            d = row["date"]
            if isinstance(d, pd.Timestamp):
                d = d.date()
            if d == trading_date:
                return row
        return None

    def _build_expiry_calendar(
        self, enriched_data: dict[str, pd.DataFrame]
    ) -> list[date]:
        expiries = set()
        for df in enriched_data.values():
            if "expiry" in df.columns:
                for e in df["expiry"].dropna().unique():
                    if isinstance(e, pd.Timestamp):
                        expiries.add(e.date())
                    else:
                        expiries.add(e)
        return sorted(expiries)

    def _get_current_expiry(
        self, current_date: date, expiries: list[date]
    ) -> date | None:
        for exp in expiries:
            if exp >= current_date:
                return exp
        return expiries[-1] if expiries else None

    def _get_nifty_roc(
        self, nifty_df: pd.DataFrame, trading_date: date
    ) -> float | None:
        if nifty_df.empty or "roc_20" not in nifty_df.columns:
            return None
        row = self._get_row(nifty_df, trading_date)
        if row is not None:
            val = row.get("roc_20")
            if val is not None and not pd.isna(val):
                return float(val)
        return None

    def _manage_positions(
        self,
        trading_date: date,
        enriched_data: dict[str, pd.DataFrame],
        current_expiry: date | None,
    ) -> None:
        for pos in list(self.portfolio.positions):
            df = enriched_data.get(pos.symbol)
            if df is None:
                continue
            row = self._get_row(df, trading_date)
            if row is None:
                continue

            if row["low"] <= pos.current_trailing_stop:
                exit_price = min(row["open"], pos.current_trailing_stop)
                h = self._estimate_hedge_exit(pos, exit_price, trading_date)
                self.portfolio.close_position(
                    pos, trading_date, exit_price, "stop_loss", h
                )
                continue

            if row["high"] >= pos.target:
                exit_price = max(row["open"], pos.target)
                h = self._estimate_hedge_exit(pos, exit_price, trading_date)
                self.portfolio.close_position(
                    pos, trading_date, exit_price, "target", h
                )
                continue

            if row.get("exit_signal", False):
                h = self._estimate_hedge_exit(pos, row["close"], trading_date)
                self.portfolio.close_position(
                    pos, trading_date, row["close"], "signal_exit", h
                )
                continue

            if current_expiry and self.strategy.should_roll(
                trading_date, pos.expiry, row
            ):
                h = self._estimate_hedge_exit(pos, row["close"], trading_date)
                self.portfolio.close_position(
                    pos, trading_date, row["close"], "roll", h
                )

        prices = {}
        for pos in self.portfolio.positions:
            df = enriched_data.get(pos.symbol)
            if df is not None:
                row = self._get_row(df, trading_date)
                if row is not None:
                    prices[pos.symbol] = row["close"]
        self.portfolio.update_trailing_stops(prices)

    def _screen_rank_enter(
        self,
        trading_date: date,
        enriched_data: dict[str, pd.DataFrame],
        nifty_enriched: pd.DataFrame,
        current_expiry: date | None,
    ) -> None:
        candidates = self.screener.screen_on_date(enriched_data, trading_date)
        if candidates.empty:
            return

        nifty_roc = self._get_nifty_roc(nifty_enriched, trading_date)
        ranked = self.ranker.rank(candidates, nifty_roc=nifty_roc)

        held_symbols = {p.symbol for p in self.portfolio.positions}

        for _, cand_row in ranked.iterrows():
            if not self.portfolio.can_open_position():
                break

            symbol = cand_row["symbol"]
            if symbol in held_symbols:
                continue

            if not cand_row.get("entry_signal", False):
                continue

            lot_size = int(cand_row.get("_lot_size", get_lot_size(symbol, trading_date)))
            close = cand_row["close"]
            atr = cand_row.get("atr", close * 0.008)
            if pd.isna(atr):
                atr = close * 0.008

            sl = self.strategy.compute_stop_loss(close, atr)
            lots = self.strategy.compute_position_size(
                self.portfolio.capital, close, sl, lot_size
            )
            if lots <= 0:
                continue

            if not self._check_margin(close, lots, lot_size):
                logger.debug(f"Insufficient margin for {symbol}, skipping")
                continue

            target = self.strategy.compute_target(close, sl)

            hedge_premium = 0.0
            hedge_strike = None
            if self.strategy.config.hedge.enabled and current_expiry:
                available_strikes = self._generate_strikes(close)
                hedge_info = self.strategy.select_hedge(
                    close, trading_date, current_expiry, available_strikes
                )
                if hedge_info:
                    hedge_strike = hedge_info["strike"]
                    hedge_premium = hedge_info["premium"]

            self.portfolio.open_position(
                symbol=symbol,
                trade_date=trading_date,
                entry_price=close,
                stop_loss=sl,
                target=target,
                lots=lots,
                lot_size=lot_size,
                expiry=current_expiry or trading_date,
                hedge_strike=hedge_strike,
                hedge_premium=hedge_premium,
            )
            held_symbols.add(symbol)
            logger.info(
                f"[SCREEN->ENTER] {symbol} @ {close:.0f} | "
                f"Score={cand_row.get('composite_score', 0):.3f}"
            )

    def _check_margin(
        self, price: float, lots: int, lot_size: int
    ) -> bool:
        contract_value = price * lot_size * lots
        required_margin = contract_value * (self.margin_pct / 100)
        if required_margin > self.portfolio.capital * 0.9:
            return False
        if contract_value > self.portfolio.capital * (self.max_position_value_pct / 100):
            return False
        if not self.portfolio.can_afford_margin(price, lot_size, lots):
            return False
        return True

    def _generate_strikes(self, price: float) -> list[float]:
        interval = BacktestEngine._strike_interval(price)
        base = round(price / interval) * interval
        return [base + i * interval for i in range(-20, 21)]

    def _estimate_hedge_exit(
        self, position, underlying_price: float, current_date: date
    ) -> float:
        if position.hedge_strike is None:
            return 0
        days_remaining = max(1, (position.expiry - current_date).days)
        if underlying_price < position.hedge_strike:
            return max(0, self.greeks.estimate_option_premium(
                underlying_price, position.hedge_strike, days_remaining, iv=15.0
            ))
        intrinsic = underlying_price - position.hedge_strike
        return intrinsic * 1.05

    def _close_remaining(
        self, enriched_data: dict[str, pd.DataFrame], last_date: date
    ) -> None:
        for pos in list(self.portfolio.positions):
            df = enriched_data.get(pos.symbol)
            if df is not None and not df.empty:
                last_price = df.iloc[-1]["close"]
            else:
                last_price = pos.entry_price
            h = self._estimate_hedge_exit(pos, last_price, last_date)
            self.portfolio.close_position(
                pos, last_date, last_price, "end_of_backtest", h
            )

    def _empty_result(self, start: date, end: date) -> BacktestResult:
        return BacktestResult(
            symbol="FO_UNIVERSE",
            start_date=start,
            end_date=end,
            initial_capital=self.portfolio.initial_capital,
            final_capital=self.portfolio.initial_capital,
        )
