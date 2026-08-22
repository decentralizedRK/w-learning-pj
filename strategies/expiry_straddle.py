"""Expiry-day straddle/directional strategy analysis and backtesting.

Analyzes NIFTY/BANKNIFTY/stock expiry days in the 3:00-3:30 PM window.
Tests straddle and directional strategies with configurable filters and
target/SL combinations to find profitable setups.

Uses spot movement data since Zerodha doesn't provide expired options data.
Premium is estimated (configurable time value per side).
"""

from datetime import time as t

import numpy as np
import pandas as pd
from loguru import logger

from config.constants import LOT_SIZE_HISTORY
from data.fetchers.nse_symbols import get_lot_size


EXPIRY_WEEKDAYS = {3, 4}  # Thursday, Friday


def nearest_strike(price: float, gap: int = 50) -> float:
    return round(price / gap) * gap


def extract_expiry_days(
    df: pd.DataFrame,
    window_start: t = t(15, 0),
    window_end: t = t(15, 29),
    min_candles: int = 5,
) -> list[dict]:
    """Extract per-expiry-day data with pre-3PM context features.

    Args:
        df: Minute-interval OHLCV data with datetime index.
        window_start: Start of analysis window.
        window_end: End of analysis window.
        min_candles: Minimum candles needed in window.

    Returns:
        List of dicts, one per expiry day, with features and minute candles.
    """
    df = df.copy()
    idx = df.index
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_convert("Asia/Kolkata")
    df.index = idx
    df["_date"] = idx.date
    df["_time"] = idx.time
    df["_weekday"] = idx.weekday

    expiry_dates = df[df["_weekday"].isin(EXPIRY_WEEKDAYS)]["_date"].unique()
    days = []

    for expiry_date in expiry_dates:
        day = df[df["_date"] == expiry_date]
        window = day[(day["_time"] >= window_start) & (day["_time"] <= window_end)]
        if window.empty or len(window) < min_candles:
            continue

        pre_window = day[(day["_time"] >= t(9, 15)) & (day["_time"] < window_start)]
        if pre_window.empty:
            continue

        entry_candle = window.iloc[0]
        spot_entry = entry_candle["open"]

        day_open = pre_window.iloc[0]["open"]
        pre_high = pre_window["high"].max()
        pre_low = pre_window["low"].min()
        pre_range = pre_high - pre_low
        pre_close = pre_window.iloc[-1]["close"]
        trend_from_open = pre_close - day_open

        last_30 = day[(day["_time"] >= t(14, 30)) & (day["_time"] < window_start)]
        momentum_30m = (last_30.iloc[-1]["close"] - last_30.iloc[0]["open"]) if not last_30.empty else 0

        last_5 = day[(day["_time"] >= t(14, 55)) & (day["_time"] < window_start)]
        momentum_5m = (last_5.iloc[-1]["close"] - last_5.iloc[0]["open"]) if not last_5.empty else 0

        candles = []
        for i, (ts, row) in enumerate(window.iterrows()):
            candles.append({
                "minute": i,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
            })

        days.append({
            "expiry_date": expiry_date,
            "weekday": pd.Timestamp(expiry_date).day_name(),
            "spot_entry": spot_entry,
            "day_open": day_open,
            "pre_range": pre_range,
            "trend_from_open": trend_from_open,
            "momentum_30m": momentum_30m,
            "momentum_5m": momentum_5m,
            "abs_momentum_30m": abs(momentum_30m),
            "abs_momentum_5m": abs(momentum_5m),
            "candles": candles,
            "exit_close": window.iloc[-1]["close"],
        })

    return days


# ─── Simulation functions ───────────────────────────────────────────


def sim_directional(
    day: dict,
    direction: str,
    target_pts: float,
    sl_pts: float,
    time_value: float = 15,
) -> tuple[float, str, int]:
    """Simulate single-leg directional trade on spot movement.

    Returns: (pnl_pts, exit_reason, exit_minute)
    """
    spot_entry = day["spot_entry"]

    for candle in day["candles"]:
        if direction == "CE":
            favorable = candle["high"] - spot_entry
            adverse = spot_entry - candle["low"]
        else:
            favorable = spot_entry - candle["low"]
            adverse = candle["high"] - spot_entry

        if adverse >= sl_pts:
            return round(-sl_pts - time_value, 2), "SL", candle["minute"]

        if favorable >= target_pts:
            return round(target_pts - time_value, 2), "TARGET", candle["minute"]

    exit_spot = day["candles"][-1]["close"]
    move = (exit_spot - spot_entry) if direction == "CE" else (spot_entry - exit_spot)
    return round(move - time_value, 2), "TIME", len(day["candles"]) - 1


def sim_straddle(
    day: dict,
    target_move_pts: float,
    strike_gap: int = 50,
    time_value: float = 15,
) -> tuple[float, str, int]:
    """Simulate straddle based on absolute spot movement from entry.

    Returns: (pnl_pts, exit_reason, exit_minute)
    """
    spot_entry = day["spot_entry"]
    strike = nearest_strike(spot_entry, strike_gap)

    ce_intrinsic_entry = max(0, spot_entry - strike)
    pe_intrinsic_entry = max(0, strike - spot_entry)
    total_premium = ce_intrinsic_entry + pe_intrinsic_entry + 2 * time_value

    for candle in day["candles"]:
        abs_move = max(abs(candle["high"] - spot_entry), abs(spot_entry - candle["low"]))
        if abs_move >= target_move_pts:
            best_intrinsic = max(
                max(0, candle["high"] - strike),
                max(0, strike - candle["low"]),
            )
            return round(best_intrinsic - total_premium, 2), "TARGET", candle["minute"]

    exit_spot = day["candles"][-1]["close"]
    exit_intrinsic = max(max(0, exit_spot - strike), max(0, strike - exit_spot))
    return round(exit_intrinsic - total_premium, 2), "TIME", len(day["candles"]) - 1


# ─── Strategy runner ────────────────────────────────────────────────


def run_strategy(
    days: list[dict],
    strategy_fn,
    filter_fn=None,
    label: str = "",
    qty: int = 750,
) -> dict | None:
    """Run a strategy across expiry days with optional filter.

    Returns dict with trades, win_rate, rr_ratio, total_pnl, etc.
    """
    trades = []
    for day in days:
        if filter_fn and not filter_fn(day):
            continue
        pnl_pts, reason, exit_min = strategy_fn(day)
        trades.append({
            "date": day["expiry_date"],
            "pnl_pts": pnl_pts,
            "pnl_rs": pnl_pts * qty,
            "reason": reason,
            "exit_min": exit_min,
        })

    if not trades:
        return None

    df = pd.DataFrame(trades)
    total = len(df)
    winners = int((df["pnl_pts"] > 0).sum())
    losers = int((df["pnl_pts"] < 0).sum())
    win_rate = winners / total * 100 if total > 0 else 0
    total_pnl = df["pnl_rs"].sum()
    avg_win = df[df["pnl_pts"] > 0]["pnl_pts"].mean() if winners > 0 else 0
    avg_loss = abs(df[df["pnl_pts"] < 0]["pnl_pts"].mean()) if losers > 0 else 0.01
    rr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    return {
        "label": label,
        "trades": total,
        "winners": winners,
        "losers": losers,
        "win_rate": round(win_rate, 1),
        "avg_win_pts": round(avg_win, 1),
        "avg_loss_pts": round(avg_loss, 1),
        "rr_ratio": round(rr, 2),
        "total_pnl": round(total_pnl),
        "avg_pnl_per_trade": round(total_pnl / total),
        "details": df,
    }


def optimize_strategies(
    days: list[dict],
    symbol: str = "NIFTY",
    num_lots: int = 10,
    strike_gap: int = 50,
    time_value: float = 15,
    min_trades: int = 10,
) -> list[dict]:
    """Test multiple strategy combinations and return all results.

    Tests: directional (follow/contra momentum, follow/contra trend),
    straddle with movement targets, various filters.
    """
    from datetime import date as dt

    lot_size = get_lot_size(symbol, dt.today())
    qty = num_lots * lot_size

    pre_ranges = [d["pre_range"] for d in days]
    mom30_vals = [d["abs_momentum_30m"] for d in days]
    median_range = np.median(pre_ranges)
    p75_range = np.percentile(pre_ranges, 75)
    median_mom30 = np.median(mom30_vals)
    p75_mom30 = np.percentile(mom30_vals, 75)

    logger.info(
        f"Stats: range median={median_range:.0f} p75={p75_range:.0f}, "
        f"mom30 median={median_mom30:.0f} p75={p75_mom30:.0f}"
    )

    results = []

    filters = [
        ("all", None),
        (f"|mom30|>{median_mom30:.0f}", lambda d: d["abs_momentum_30m"] > median_mom30),
        (f"|mom30|>{p75_mom30:.0f}", lambda d: d["abs_momentum_30m"] > p75_mom30),
        (f"range>{p75_range:.0f}", lambda d: d["pre_range"] > p75_range),
    ]

    # Directional: follow 30m momentum
    for target in [20, 30, 40, 50, 60, 80]:
        for sl in [5, 10, 15, 20, 25, 30]:
            if target < 2 * sl:
                continue
            for fname, ffn in filters:
                def fn(d, tgt=target, s=sl):
                    direction = "CE" if d["momentum_30m"] > 0 else "PE"
                    return sim_directional(d, direction, tgt, s, time_value)
                r = run_strategy(days, fn, ffn, f"Follow30m T={target} SL={sl} | {fname}", qty)
                if r and r["trades"] >= min_trades:
                    results.append(r)

    # Directional: contra 30m momentum
    for target in [20, 30, 40, 50, 60, 80]:
        for sl in [5, 10, 15, 20, 25, 30]:
            if target < 2 * sl:
                continue
            for fname, ffn in filters:
                def fn(d, tgt=target, s=sl):
                    direction = "PE" if d["momentum_30m"] > 0 else "CE"
                    return sim_directional(d, direction, tgt, s, time_value)
                r = run_strategy(days, fn, ffn, f"Contra30m T={target} SL={sl} | {fname}", qty)
                if r and r["trades"] >= min_trades:
                    results.append(r)

    # Directional: follow day trend
    for target in [20, 30, 40, 50, 60, 80]:
        for sl in [5, 10, 15, 20, 25, 30]:
            if target < 2 * sl:
                continue
            for min_trend in [0, 50, 100]:
                ffn = (lambda d, mt=min_trend: abs(d["trend_from_open"]) > mt) if min_trend > 0 else None
                def fn(d, tgt=target, s=sl):
                    direction = "CE" if d["trend_from_open"] > 0 else "PE"
                    return sim_directional(d, direction, tgt, s, time_value)
                r = run_strategy(days, fn, ffn, f"DayTrend T={target} SL={sl} | trend>{min_trend}", qty)
                if r and r["trades"] >= min_trades:
                    results.append(r)

    # Directional: contra day trend
    for target in [20, 30, 40, 50, 60, 80]:
        for sl in [5, 10, 15, 20, 25, 30]:
            if target < 2 * sl:
                continue
            for min_trend in [50, 100, 150]:
                ffn = lambda d, mt=min_trend: abs(d["trend_from_open"]) > mt
                def fn(d, tgt=target, s=sl):
                    direction = "PE" if d["trend_from_open"] > 0 else "CE"
                    return sim_directional(d, direction, tgt, s, time_value)
                r = run_strategy(days, fn, ffn, f"ContraDay T={target} SL={sl} | |trend|>{min_trend}", qty)
                if r and r["trades"] >= min_trades:
                    results.append(r)

    # Straddle: various movement targets
    for target_move in [40, 50, 60, 80, 100]:
        for fname, ffn in filters:
            def fn(d, tm=target_move):
                return sim_straddle(d, tm, strike_gap, time_value)
            r = run_strategy(days, fn, ffn, f"Straddle move>{target_move} | {fname}", qty)
            if r and r["trades"] >= min_trades:
                results.append(r)

    return results
