"""Check current margin utilization on Zerodha.

Usage:
    python -m scripts.check_margins
"""

import sys

from loguru import logger

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging


def main() -> None:
    setup_logging()

    broker = ZerodhaBroker()
    if not broker.authenticate():
        logger.error("Kite authentication failed — token may be expired")
        sys.exit(1)

    margins = broker.get_margins()
    positions = broker.get_positions()

    for segment in ("equity", "commodity"):
        seg_data = margins.get(segment)
        if seg_data is None:
            continue
        available = seg_data.get("available", {})
        utilised = seg_data.get("utilised", {})
        total_available = available.get("live_balance", 0) + available.get("collateral", 0)
        total_used = utilised.get("span", 0) + utilised.get("exposure", 0)
        total_capital = total_available + total_used

        utilization_pct = (total_used / total_capital * 100) if total_capital > 0 else 0

        print(f"\n{'='*50}")
        print(f"  {segment.upper()} MARGINS")
        print(f"{'='*50}")
        print(f"  Total capital:  {total_capital:>15,.2f}")
        print(f"  Margin used:    {total_used:>15,.2f}")
        print(f"  Available:      {total_available:>15,.2f}")
        print(f"  Utilization:    {utilization_pct:>14.1f}%")

        if utilization_pct > 75:
            print("  WARNING: Margin utilization above 75% buffer threshold")

    if positions:
        print(f"\n{'='*50}")
        print(f"  OPEN POSITIONS: {len(positions)}")
        print(f"{'='*50}")
        print(f"{'Symbol':<15}{'Qty':>8}{'LTP':>10}{'P&L':>12}")
        print("-" * 45)
        for pos in positions:
            if pos.get("quantity", 0) == 0:
                continue
            print(
                f"{pos.get('tradingsymbol', ''):<15}"
                f"{pos.get('quantity', 0):>8}"
                f"{pos.get('last_price', 0):>10,.2f}"
                f"{pos.get('pnl', 0):>12,.2f}"
            )
    else:
        print("\nNo open positions.")


if __name__ == "__main__":
    main()
