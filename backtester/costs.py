from typing import Literal


class IndianFnOCostModel:
    def __init__(self) -> None:
        self.futures_brokerage_per_order: float = 20.0
        self.options_brokerage_per_order: float = 20.0

        self.futures_stt_sell_rate: float = 0.02 / 100
        self.options_stt_sell_rate: float = 0.1 / 100

        self.futures_exchange_charge: float = 0.00173 / 100
        self.options_exchange_charge: float = 0.0350 / 100

        self.sebi_fee: float = 10 / 1_00_00_000  # Rs 10 per crore

        self.gst_rate: float = 18.0 / 100

        self.futures_stamp_duty: float = 0.002 / 100
        self.options_stamp_duty: float = 0.003 / 100

    def compute_futures_cost(
        self, price: float, lot_size: int, lots: int, side: Literal["buy", "sell"]
    ) -> dict[str, float]:
        turnover = price * lot_size * lots

        brokerage = self.futures_brokerage_per_order
        stt = turnover * self.futures_stt_sell_rate if side == "sell" else 0
        exchange = turnover * self.futures_exchange_charge
        sebi = turnover * self.sebi_fee
        stamp = turnover * self.futures_stamp_duty if side == "buy" else 0
        gst = (brokerage + exchange + sebi) * self.gst_rate
        total = brokerage + stt + exchange + sebi + gst + stamp

        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "exchange_charges": round(exchange, 2),
            "sebi_fee": round(sebi, 2),
            "gst": round(gst, 2),
            "stamp_duty": round(stamp, 2),
            "total": round(total, 2),
        }

    def compute_options_cost(
        self, premium: float, lot_size: int, lots: int, side: Literal["buy", "sell"]
    ) -> dict[str, float]:
        turnover = premium * lot_size * lots

        brokerage = self.options_brokerage_per_order
        stt = turnover * self.options_stt_sell_rate if side == "sell" else 0
        exchange = turnover * self.options_exchange_charge
        sebi = turnover * self.sebi_fee
        stamp = turnover * self.options_stamp_duty if side == "buy" else 0
        gst = (brokerage + exchange + sebi) * self.gst_rate
        total = brokerage + stt + exchange + sebi + gst + stamp

        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "exchange_charges": round(exchange, 2),
            "sebi_fee": round(sebi, 2),
            "gst": round(gst, 2),
            "stamp_duty": round(stamp, 2),
            "total": round(total, 2),
        }

    def compute_round_trip_cost(
        self,
        entry_price: float,
        exit_price: float,
        lot_size: int,
        lots: int,
        hedge_premium_entry: float = 0,
        hedge_premium_exit: float = 0,
    ) -> dict[str, float]:
        fut_buy = self.compute_futures_cost(entry_price, lot_size, lots, "buy")
        fut_sell = self.compute_futures_cost(exit_price, lot_size, lots, "sell")

        opt_sell = (
            self.compute_options_cost(hedge_premium_entry, lot_size, lots, "sell")
            if hedge_premium_entry > 0
            else {"total": 0}
        )
        opt_buy = (
            self.compute_options_cost(hedge_premium_exit, lot_size, lots, "buy")
            if hedge_premium_exit > 0
            else {"total": 0}
        )

        return {
            "futures_entry": fut_buy["total"],
            "futures_exit": fut_sell["total"],
            "option_entry": opt_sell["total"],
            "option_exit": opt_buy["total"],
            "total": fut_buy["total"] + fut_sell["total"] + opt_sell["total"] + opt_buy["total"],
        }
