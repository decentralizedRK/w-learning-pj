from datetime import date

MARKET_REGIMES: dict[str, tuple[date, date]] = {
    "covid_crash": (date(2020, 2, 1), date(2020, 4, 30)),
    "post_covid_recovery": (date(2020, 5, 1), date(2020, 12, 31)),
    "bull_2021": (date(2021, 1, 1), date(2021, 10, 31)),
    "bear_2022": (date(2022, 1, 1), date(2022, 6, 30)),
    "recovery_2022": (date(2022, 7, 1), date(2022, 12, 31)),
    "sideways_2023": (date(2023, 1, 1), date(2023, 12, 31)),
    "election_2024": (date(2024, 3, 1), date(2024, 6, 30)),
    "budget_2024": (date(2024, 7, 1), date(2024, 7, 31)),
    "full_period": (date(2020, 1, 1), date(2025, 12, 31)),
}


def get_regime_for_date(trade_date: date) -> str:
    for name, (start, end) in MARKET_REGIMES.items():
        if name == "full_period":
            continue
        if start <= trade_date <= end:
            return name
    return "other"


def filter_trades_by_regime(
    trades: list[dict], regime_name: str
) -> list[dict]:
    if regime_name not in MARKET_REGIMES:
        return []
    start, end = MARKET_REGIMES[regime_name]
    return [t for t in trades if start <= t["entry_date"] <= end]
