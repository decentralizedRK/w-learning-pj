"""Track dividends, splits, and earnings for portfolio + watchlist stocks.

Usage:
    python -m scripts.corporate_actions
    python -m scripts.corporate_actions --output dashboard/data/corporate_actions.json
"""

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yfinance as yf
from loguru import logger

from config.logging_config import setup_logging
from notifications import notify


def fetch_actions(ticker: str) -> dict:
    result = {"dividends": [], "splits": [], "calendar": {}}
    try:
        t = yf.Ticker(f"{ticker}.NS")

        divs = t.dividends
        if divs is not None and not divs.empty:
            cutoff = datetime.now(UTC) - timedelta(days=180)
            for dt, amount in divs.items():
                if dt.tz_localize(UTC) if dt.tzinfo is None else dt > cutoff:
                    result["dividends"].append({
                        "date": str(dt.date()),
                        "amount": float(amount),
                    })

        splits = t.splits
        if splits is not None and not splits.empty:
            cutoff = datetime.now(UTC) - timedelta(days=365)
            for dt, ratio in splits.items():
                if dt.tz_localize(UTC) if dt.tzinfo is None else dt > cutoff:
                    result["splits"].append({
                        "date": str(dt.date()),
                        "ratio": str(ratio),
                    })

        cal = t.calendar
        if cal is not None and isinstance(cal, dict):
            for key in ["Earnings Date", "Ex-Dividend Date", "Dividend Date"]:
                val = cal.get(key)
                if val is not None:
                    if isinstance(val, list):
                        result["calendar"][key] = [str(v) for v in val]
                    else:
                        result["calendar"][key] = str(val)

    except Exception as e:
        logger.debug(f"Corporate actions failed for {ticker}: {e}")
        result["error"] = str(e)

    return result


def upcoming_events(symbol: str, actions: dict) -> list[dict]:
    events = []
    today = date.today()

    for div in actions.get("dividends", []):
        div_date = date.fromisoformat(div["date"])
        if div_date >= today - timedelta(days=7):
            days_away = (div_date - today).days
            events.append({
                "symbol": symbol,
                "type": "dividend",
                "date": div["date"],
                "detail": f"₹{div['amount']:.2f} per share",
                "days_away": days_away,
            })

    for split in actions.get("splits", []):
        split_date = date.fromisoformat(split["date"])
        if split_date >= today - timedelta(days=7):
            days_away = (split_date - today).days
            events.append({
                "symbol": symbol,
                "type": "split",
                "date": split["date"],
                "detail": f"Ratio: {split['ratio']}",
                "days_away": days_away,
            })

    cal = actions.get("calendar", {})
    for key in ["Earnings Date", "Ex-Dividend Date"]:
        val = cal.get(key)
        if val is None:
            continue
        dates = val if isinstance(val, list) else [val]
        for d in dates:
            try:
                event_date = date.fromisoformat(str(d)[:10])
                days_away = (event_date - today).days
                if -7 <= days_away <= 60:
                    events.append({
                        "symbol": symbol,
                        "type": key.lower().replace(" ", "_"),
                        "date": str(event_date),
                        "detail": key,
                        "days_away": days_away,
                    })
            except ValueError:
                continue

    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Corporate actions tracker")
    parser.add_argument(
        "--output", default="dashboard/data/corporate_actions.json",
    )
    parser.add_argument("--portfolio", default="dashboard/data/portfolio.json")
    parser.add_argument("--signals", default="dashboard/data/signals.json")
    args = parser.parse_args()

    setup_logging()

    symbols = set()
    if Path(args.portfolio).exists():
        with open(args.portfolio) as f:
            data = json.load(f)
        for h in data.get("holdings", []):
            symbols.add(h["symbol"])

    if Path(args.signals).exists():
        with open(args.signals) as f:
            data = json.load(f)
        for pick in data.get("top_picks", [])[:10]:
            symbols.add(pick["symbol"])

    if not symbols:
        symbols = {"RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"}

    logger.info(f"Checking corporate actions for {len(symbols)} symbols")

    all_events = []
    all_actions = {}
    for sym in sorted(symbols):
        actions = fetch_actions(sym)
        all_actions[sym] = actions
        all_events.extend(upcoming_events(sym, actions))

    all_events.sort(key=lambda e: e.get("date", "9999"))

    result = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "events": all_events,
        "by_symbol": {
            sym: {k: v for k, v in a.items() if k != "error"}
            for sym, a in all_actions.items()
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    upcoming = [e for e in all_events if e["days_away"] >= 0]
    logger.info(f"Corporate actions: {len(upcoming)} upcoming events")

    if upcoming:
        lines = [f"*Corporate Actions ({len(upcoming)} upcoming)*"]
        for e in upcoming[:5]:
            lines.append(
                f"  {e['symbol']}: {e['type']} on {e['date']}"
                f" ({e['days_away']}d)"
            )
        notify("\n".join(lines))


if __name__ == "__main__":
    main()
