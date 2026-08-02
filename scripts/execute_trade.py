"""Execute a single trade on Zerodha via Kite API.

Usage:
    python -m scripts.execute_trade --symbol RELIANCE25AUGFUT \
        --exchange NFO --action BUY --quantity 250
"""

import argparse
import sys

from loguru import logger

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute trade on Zerodha")
    parser.add_argument("--symbol", required=True, help="Trading symbol (e.g. RELIANCE25AUGFUT)")
    parser.add_argument("--exchange", default="NFO", choices=["NSE", "NFO", "BSE"])
    parser.add_argument(
        "--action", required=True, choices=["BUY", "SELL"], help="Transaction type"
    )
    parser.add_argument("--quantity", required=True, type=int, help="Order quantity")
    parser.add_argument(
        "--order-type", default="MARKET", choices=["MARKET", "LIMIT", "SL", "SL-M"]
    )
    parser.add_argument("--price", type=float, default=0, help="Limit price (for LIMIT/SL)")
    parser.add_argument(
        "--trigger-price", type=float, default=0, help="Trigger price (for SL/SL-M)"
    )
    parser.add_argument(
        "--product", default="NRML", choices=["NRML", "MIS", "CNC"], help="Product type"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print order details without placing"
    )
    args = parser.parse_args()

    setup_logging()

    broker = ZerodhaBroker()
    if not broker.authenticate():
        logger.error("Kite authentication failed — token may be expired")
        sys.exit(1)

    print(f"\nOrder: {args.action} {args.quantity} {args.symbol} @ {args.order_type}")
    if args.price:
        print(f"Price: {args.price}")
    if args.trigger_price:
        print(f"Trigger: {args.trigger_price}")
    print(f"Exchange: {args.exchange} | Product: {args.product}")

    if args.dry_run:
        print("\n[DRY RUN] Order not placed.")
        return

    response = broker.place_order(
        symbol=args.symbol,
        exchange=args.exchange,
        transaction_type=args.action,
        quantity=args.quantity,
        order_type=args.order_type,
        price=args.price,
        trigger_price=args.trigger_price,
        product=args.product,
    )

    print(f"\nStatus: {response.status}")
    print(f"Order ID: {response.order_id}")
    if response.message:
        print(f"Message: {response.message}")

    if response.status == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
