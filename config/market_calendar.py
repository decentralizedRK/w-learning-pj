from datetime import datetime, time, timedelta

import pytz
from loguru import logger

try:
    import pandas_market_calendars as mcal

    _HAS_MCAL = True
except ImportError:
    _HAS_MCAL = False
    logger.debug("pandas_market_calendars not installed, using weekday check only")

IST = pytz.timezone("Asia/Kolkata")

_TZ = {
    "NSE": pytz.timezone("Asia/Kolkata"),
    "BSE": pytz.timezone("Asia/Kolkata"),
}

_HOURS = {
    "NSE": (time(9, 15), time(15, 30)),
    "BSE": (time(9, 15), time(15, 30)),
}

_CAL_ID = {
    "NSE": "XBOM",
    "BSE": "XBOM",
}


def is_market_open(exchange: str = "NSE") -> bool:
    exchange = exchange.upper()
    tz = _TZ[exchange]
    open_t, close_t = _HOURS[exchange]
    now = datetime.now(tz)

    if _HAS_MCAL:
        try:
            cal = mcal.get_calendar(_CAL_ID[exchange])
            today = now.strftime("%Y-%m-%d")
            if cal.schedule(start_date=today, end_date=today).empty:
                return False
        except Exception:
            if now.weekday() >= 5:
                return False
    elif now.weekday() >= 5:
        return False

    return open_t <= now.time() <= close_t


def next_open(exchange: str = "NSE") -> str:
    exchange = exchange.upper()
    tz = _TZ[exchange]
    open_t, _ = _HOURS[exchange]
    now = datetime.now(tz)

    candidate = now.replace(
        hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0,
    )
    if now.time() >= open_t:
        candidate += timedelta(days=1)

    cal = None
    if _HAS_MCAL:
        try:
            cal = mcal.get_calendar(_CAL_ID[exchange])
        except Exception:
            pass

    for _ in range(10):
        day_str = candidate.strftime("%Y-%m-%d")
        if cal is not None:
            try:
                if not cal.schedule(start_date=day_str, end_date=day_str).empty:
                    break
            except Exception:
                if candidate.weekday() < 5:
                    break
        elif candidate.weekday() < 5:
            break
        candidate += timedelta(days=1)

    return candidate.astimezone(IST).strftime("%d %b %Y %H:%M IST")
