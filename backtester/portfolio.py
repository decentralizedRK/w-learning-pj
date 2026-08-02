from dataclasses import dataclass
from datetime import date

from loguru import logger

from backtester.costs import IndianFnOCostModel


@dataclass
class Position:
    symbol: str
    entry_date: date
    entry_price: float
    lots: int
    lot_size: int
    stop_loss: float
    target: float
    expiry: date
    hedge_strike: float | None = None
    hedge_premium_collected: float = 0.0
    highest_price_since_entry: float = 0.0
    current_trailing_stop: float = 0.0
    entry_costs: float = 0.0

    def __post_init__(self) -> None:
        if self.highest_price_since_entry == 0:
            self.highest_price_since_entry = self.entry_price
        if self.current_trailing_stop == 0:
            self.current_trailing_stop = self.stop_loss


class Portfolio:
    def __init__(
        self,
        initial_capital: float,
        cost_model: IndianFnOCostModel,
        max_positions: int = 3,
        risk_per_trade_pct: float = 0.5,
        trailing_step_pct: float = 0.5,
        margin_pct: float = 20.0,
        max_total_margin_pct: float = 75.0,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.cost_model = cost_model
        self.max_positions = max_positions
        self.risk_per_trade_pct = risk_per_trade_pct
        self.trailing_step_pct = trailing_step_pct
        self.margin_pct = margin_pct
        self.max_total_margin_pct = max_total_margin_pct
        self.positions: list[Position] = []
        self.closed_trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self._current_prices: dict[str, float] = {}

    def update_current_prices(self, prices: dict[str, float]) -> None:
        self._current_prices.update(prices)

    def can_open_position(self) -> bool:
        return len(self.positions) < self.max_positions

    def total_margin_used(self) -> float:
        return sum(
            self._current_prices.get(pos.symbol, pos.entry_price)
            * pos.lot_size
            * pos.lots
            * (self.margin_pct / 100)
            for pos in self.positions
        )

    def unrealized_pnl(self) -> float:
        return sum(
            (self._current_prices.get(p.symbol, p.entry_price) - p.entry_price)
            * p.lot_size
            * p.lots
            for p in self.positions
        )

    def available_capital(self) -> float:
        return self.capital + self.unrealized_pnl()

    def can_afford_margin(self, price: float, lot_size: int, lots: int) -> bool:
        new_margin = price * lot_size * lots * (self.margin_pct / 100)
        return (self.total_margin_used() + new_margin) <= self.available_capital() * (
            self.max_total_margin_pct / 100
        )

    def open_position(
        self,
        symbol: str,
        trade_date: date,
        entry_price: float,
        stop_loss: float,
        target: float,
        lots: int,
        lot_size: int,
        expiry: date,
        hedge_strike: float | None = None,
        hedge_premium: float = 0,
    ) -> Position | None:
        if not self.can_open_position():
            return None

        costs = self.cost_model.compute_round_trip_cost(
            entry_price, entry_price, lot_size, lots, hedge_premium, 0
        )
        entry_cost = costs["futures_entry"] + costs["option_entry"]

        position = Position(
            symbol=symbol,
            entry_date=trade_date,
            entry_price=entry_price,
            lots=lots,
            lot_size=lot_size,
            stop_loss=stop_loss,
            target=target,
            expiry=expiry,
            hedge_strike=hedge_strike,
            hedge_premium_collected=hedge_premium * lot_size * lots if hedge_premium else 0,
            entry_costs=entry_cost,
        )

        self.positions.append(position)

        logger.debug(
            f"OPEN {symbol} @ {entry_price:.0f} | {lots}x{lot_size} | "
            f"SL={stop_loss:.0f} TGT={target:.0f} | Cost={entry_cost:.0f}"
        )
        return position

    def update_trailing_stops(self, current_prices: dict[str, float]) -> None:
        self.update_current_prices(current_prices)
        for pos in self.positions:
            price = current_prices.get(pos.symbol)
            if price is None or price <= pos.highest_price_since_entry:
                continue

            pos.highest_price_since_entry = price
            move_pct = (price - pos.entry_price) / pos.entry_price * 100
            trail_steps = int(move_pct / self.trailing_step_pct)
            if trail_steps > 0:
                trail_offset = trail_steps * self.trailing_step_pct / 100
                new_stop = pos.entry_price * (1 + trail_offset) - (
                    pos.entry_price - pos.stop_loss
                )
                if new_stop > pos.current_trailing_stop:
                    pos.current_trailing_stop = new_stop

    def close_position(
        self,
        position: Position,
        exit_date: date,
        exit_price: float,
        exit_reason: str,
        hedge_exit_premium: float = 0,
    ) -> dict:
        futures_pnl = (exit_price - position.entry_price) * position.lot_size * position.lots
        hedge_pnl = position.hedge_premium_collected - (
            hedge_exit_premium * position.lot_size * position.lots
        )

        exit_costs_data = self.cost_model.compute_round_trip_cost(
            position.entry_price, exit_price,
            position.lot_size, position.lots, 0, hedge_exit_premium
        )
        total_exit_cost = exit_costs_data["futures_exit"] + exit_costs_data["option_exit"]

        gross_pnl = futures_pnl + hedge_pnl
        net_pnl = gross_pnl - position.entry_costs - total_exit_cost

        trade_record = {
            "symbol": position.symbol,
            "entry_date": position.entry_date,
            "exit_date": exit_date,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "lots": position.lots,
            "lot_size": position.lot_size,
            "stop_loss": position.stop_loss,
            "target": position.target,
            "exit_reason": exit_reason,
            "futures_pnl": round(futures_pnl, 2),
            "hedge_premium_collected": round(position.hedge_premium_collected, 2),
            "hedge_pnl": round(hedge_pnl, 2),
            "gross_pnl": round(gross_pnl, 2),
            "total_costs": round(position.entry_costs + total_exit_cost, 2),
            "net_pnl": round(net_pnl, 2),
            "holding_days": (exit_date - position.entry_date).days,
        }

        self.closed_trades.append(trade_record)
        self.positions.remove(position)
        self.capital += net_pnl

        logger.debug(
            f"CLOSE {position.symbol} @ {exit_price:.0f} | {exit_reason} | "
            f"Net P&L={net_pnl:+.0f} | Days={trade_record['holding_days']}"
        )
        return trade_record

    def record_equity(self, trade_date: date, current_prices: dict[str, float]) -> None:
        self.update_current_prices(current_prices)
        unr_pnl = self.unrealized_pnl()
        self.equity_curve.append({
            "date": trade_date,
            "capital": round(self.capital, 2),
            "unrealized_pnl": round(unr_pnl, 2),
            "portfolio_value": round(self.capital + unr_pnl, 2),
            "open_positions": len(self.positions),
        })
