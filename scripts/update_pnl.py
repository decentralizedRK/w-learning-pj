"""Fetch current positions and compute P&L from Zerodha.

Usage:
    python -m scripts.update_pnl
    python -m scripts.update_pnl --output reports/pnl/latest.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Update P&L from Zerodha positions")
    parser.add_argument("--output", default=None, help="Output JSON path for P&L report")
    args = parser.parse_args()

    setup_logging()

    broker = ZerodhaBroker()
    if not broker.authenticate():
        logger.error("Kite authentication failed — token may be expired")
        sys.exit(1)

    positions = broker.get_positions()
    active = [p for p in positions if p.get("quantity", 0) != 0]

    if not active:
        print("No open positions.")
        return

    symbols = list({p["tradingsymbol"] for p in active if "tradingsymbol" in p})
    ltps = broker.get_ltp(symbols, exchange="NFO") if symbols else {}

    total_pnl = 0.0
    total_unrealized = 0.0
    report_rows = []

    print(f"\n{'='*70}")
    print(f"  P&L REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    print(
        f"{'Symbol':<18}{'Qty':>8}{'Avg Price':>12}{'LTP':>10}"
        f"{'Day P&L':>12}{'Total P&L':>12}"
    )
    print("-" * 72)

    for pos in active:
        symbol = pos.get("tradingsymbol", "")
        qty = pos.get("quantity", 0)
        avg_price = pos.get("average_price", 0)
        ltp = ltps.get(symbol, pos.get("last_price", 0))
        day_pnl = pos.get("pnl", 0)
        unrealized = (ltp - avg_price) * qty

        total_pnl += day_pnl
        total_unrealized += unrealized

        print(
            f"{symbol:<18}{qty:>8}{avg_price:>12,.2f}{ltp:>10,.2f}"
            f"{day_pnl:>12,.2f}{unrealized:>12,.2f}"
        )

        report_rows.append({
            "symbol": symbol,
            "quantity": qty,
            "average_price": avg_price,
            "ltp": ltp,
            "day_pnl": round(day_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
        })

    print("-" * 72)
    print(f"{'TOTAL':<18}{'':>8}{'':>12}{'':>10}{total_pnl:>12,.2f}{total_unrealized:>12,.2f}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": datetime.now().isoformat(),
            "positions": report_rows,
            "total_day_pnl": round(total_pnl, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
        }
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
