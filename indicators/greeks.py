import mibian

from config.constants import RBI_REPO_RATE


class GreeksCalculator:
    @staticmethod
    def compute_greeks(
        underlying_price: float,
        strike: float,
        days_to_expiry: int,
        interest_rate: float = RBI_REPO_RATE,
        iv: float | None = None,
        option_price: float | None = None,
        option_type: str = "CE",
    ) -> dict[str, float]:
        days = max(1, days_to_expiry)

        if iv is not None:
            bs = mibian.BS(
                [underlying_price, strike, interest_rate, days], volatility=iv
            )
        elif option_price is not None:
            if option_type == "CE":
                bs = mibian.BS(
                    [underlying_price, strike, interest_rate, days],
                    callPrice=option_price,
                )
            else:
                bs = mibian.BS(
                    [underlying_price, strike, interest_rate, days],
                    putPrice=option_price,
                )
        else:
            raise ValueError("Either iv or option_price must be provided")

        if option_type == "CE":
            return {
                "delta": bs.callDelta,
                "gamma": bs.gamma,
                "theta": bs.callTheta,
                "vega": bs.vega,
                "call_price": bs.callPrice,
                "put_price": bs.putPrice,
            }
        else:
            return {
                "delta": bs.putDelta,
                "gamma": bs.gamma,
                "theta": bs.putTheta,
                "vega": bs.vega,
                "call_price": bs.callPrice,
                "put_price": bs.putPrice,
            }

    @staticmethod
    def select_otm_call_strike(
        underlying_price: float,
        available_strikes: list[float],
        otm_pct_min: float = 3.0,
        otm_pct_max: float = 5.0,
    ) -> float | None:
        target_min = underlying_price * (1 + otm_pct_min / 100)
        target_max = underlying_price * (1 + otm_pct_max / 100)
        candidates = [s for s in available_strikes if target_min <= s <= target_max]
        if not candidates:
            return None
        return min(candidates)

    @staticmethod
    def estimate_option_premium(
        underlying_price: float,
        strike: float,
        days_to_expiry: int,
        iv: float = 15.0,
        option_type: str = "CE",
    ) -> float:
        greeks = GreeksCalculator.compute_greeks(
            underlying_price, strike, days_to_expiry, iv=iv, option_type=option_type
        )
        key = "call_price" if option_type == "CE" else "put_price"
        return max(0, greeks.get(key, 0))
