"""Downside threshold band monitoring.

Alerts when a holding crosses a new 5% downside band from cost basis.
State is persisted so each band triggers only once.
"""

import json
import math
from pathlib import Path

from loguru import logger

from config.settings import settings

THRESHOLD_STEP = 5


def _state_path() -> Path:
    return settings.data_dir / "alert_state.json"


def load_state() -> dict[str, int]:
    path = _state_path()
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, int]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def reset_ticker(ticker: str) -> None:
    state = load_state()
    state.pop(ticker, None)
    save_state(state)


def reset_all() -> None:
    save_state({})


def check(
    symbol: str, current_price: float, avg_buy_price: float,
) -> tuple[bool, int, float]:
    """Check if a new downside band was crossed.

    Returns (should_alert, band, pct_change).
    band is the 5% step just crossed (e.g. -10 means the -10% threshold).
    Only alerts on downside, once per band.
    """
    if avg_buy_price <= 0:
        return False, 0, 0.0

    pct_change = (current_price - avg_buy_price) / avg_buy_price * 100
    band = math.trunc(pct_change / THRESHOLD_STEP) * THRESHOLD_STEP

    if band >= 0:
        return False, band, pct_change

    state = load_state()
    last_band = state.get(symbol, 0)

    if band < last_band:
        state[symbol] = band
        save_state(state)
        logger.info(f"{symbol} crossed {band}% band ({pct_change:.2f}% from cost)")
        return True, band, pct_change

    return False, band, pct_change
