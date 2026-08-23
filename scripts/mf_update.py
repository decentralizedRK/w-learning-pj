"""Fetch mutual fund NAVs and auto-record SIP purchases.

Usage:
    python -m scripts.mf_update
    python -m scripts.mf_update --output dashboard/data/mf_snapshot.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import pytz
import requests
from loguru import logger

from config.logging_config import setup_logging
from notifications import notify

IST = pytz.timezone("Asia/Kolkata")
MF_PORTFOLIO_PATH = Path("config/mf_portfolio.json")
AMFI_NAV_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"

_amfi_cache: dict[str, float] = {}


def _fetch_nav_numeric(scheme_code: str) -> float | None:
    try:
        resp = requests.get(
            f"https://api.mfapi.in/mf/{scheme_code}", timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                return float(data["data"][0]["nav"])
    except Exception as e:
        logger.warning(f"mfapi.in failed for {scheme_code}: {e}")
    return None


def _fetch_nav_isin(isin: str) -> float | None:
    global _amfi_cache
    if not _amfi_cache:
        try:
            resp = requests.get(AMFI_NAV_URL, timeout=15)
            for line in resp.text.splitlines():
                parts = line.split(";")
                if len(parts) >= 5:
                    code_isin = parts[1].strip()
                    try:
                        nav = float(parts[4].strip())
                        _amfi_cache[code_isin] = nav
                    except ValueError:
                        continue
        except Exception as e:
            logger.warning(f"AMFI NAV fetch failed: {e}")
            return None

    return _amfi_cache.get(isin)


def fetch_nav(scheme_code: str) -> float | None:
    if scheme_code.isdigit():
        return _fetch_nav_numeric(scheme_code)
    return _fetch_nav_isin(scheme_code)


def should_record_sip(fund: dict, today: datetime) -> bool:
    if fund.get("sip_amount", 0) <= 0:
        return False
    sip_day = fund.get("sip_date", 1)
    if abs(today.day - sip_day) > 2:
        return False
    last_recorded = fund.get("last_sip_recorded", "")
    if last_recorded:
        last_dt = datetime.fromisoformat(last_recorded)
        if last_dt.year == today.year and last_dt.month == today.month:
            return False
    return True


def record_sip(fund: dict, nav: float, today: datetime) -> dict:
    sip_amount = fund["sip_amount"]
    new_units = sip_amount / nav
    old_units = fund["units"]
    old_avg = fund["avg_nav"]
    total_cost = old_units * old_avg + sip_amount
    fund["units"] = old_units + new_units
    fund["avg_nav"] = total_cost / fund["units"]
    fund["last_sip_recorded"] = today.strftime("%Y-%m-%d")
    logger.info(
        f"SIP recorded: {fund['name'][:40]} | "
        f"{new_units:.3f} units @ {nav:.4f}"
    )
    return {
        "fund": fund["name"],
        "amount": sip_amount,
        "nav": nav,
        "units": round(new_units, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mutual fund NAV update")
    parser.add_argument(
        "--output", default="dashboard/data/mf_snapshot.json",
    )
    args = parser.parse_args()

    setup_logging()

    if not MF_PORTFOLIO_PATH.exists():
        logger.error(f"{MF_PORTFOLIO_PATH} not found")
        return

    with open(MF_PORTFOLIO_PATH) as f:
        mf_data = json.load(f)

    funds = mf_data.get("funds", [])
    today = datetime.now(IST)
    sip_events = []
    total_invested = 0.0
    total_current = 0.0
    fund_records = []

    for fund in funds:
        nav = fetch_nav(fund["scheme_code"])
        if nav is None:
            logger.warning(f"NAV unavailable for {fund['name'][:40]}")
            continue

        if should_record_sip(fund, today):
            event = record_sip(fund, nav, today)
            sip_events.append(event)

        invested = fund["units"] * fund["avg_nav"]
        current = fund["units"] * nav
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0

        total_invested += invested
        total_current += current

        fund_records.append({
            "name": fund["name"],
            "scheme_code": fund["scheme_code"],
            "units": round(fund["units"], 3),
            "avg_nav": round(fund["avg_nav"], 4),
            "current_nav": round(nav, 4),
            "invested": round(invested, 2),
            "current": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "sip_amount": fund.get("sip_amount", 0),
        })

    if sip_events:
        with open(MF_PORTFOLIO_PATH, "w") as f:
            json.dump(mf_data, f, indent=2)
        logger.info(f"Updated {MF_PORTFOLIO_PATH} with {len(sip_events)} SIPs")

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0

    snapshot = {
        "timestamp": datetime.now(IST).isoformat(timespec="seconds"),
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "sip_recorded_today": len(sip_events) > 0,
        "funds": fund_records,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    logger.info(f"MF snapshot: {len(fund_records)} funds, P&L: {total_pnl:+,.0f}")

    msg = (
        f"*MF Update*\n"
        f"Funds: {len(fund_records)}\n"
        f"Invested: ₹{total_invested:,.0f}\n"
        f"Current: ₹{total_current:,.0f}\n"
        f"P&L: ₹{total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)"
    )
    if sip_events:
        msg += f"\nSIPs recorded: {len(sip_events)}"
    notify(msg)


if __name__ == "__main__":
    main()
