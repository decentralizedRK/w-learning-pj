"""Fetch live trading data from Zerodha and publish JSON for the dashboard.

Usage:
    python -m scripts.publish_dashboard_data --output dashboard/data
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging

INDEX_INSTRUMENTS = {
    "NIFTY 50": "NSE:NIFTY 50",
    "NIFTY BANK": "NSE:NIFTY BANK",
    "NIFTY MID SELECT": "NSE:NIFTY MID SELECT",
    "NIFTY SMLCAP 100": "NSE:NIFTY SMLCAP 100",
}


def fetch_indices(broker: ZerodhaBroker) -> list[dict]:
    try:
        kite = broker._get_kite()
        instruments = list(INDEX_INSTRUMENTS.values())
        data = kite.ltp(instruments)
        result = []
        for name, key in INDEX_INSTRUMENTS.items():
            info = data.get(key, {})
            result.append({
                "name": name,
                "price": info.get("last_price", 0),
                "instrument_key": key,
            })
        return result
    except Exception as e:
        logger.error(f"Failed to fetch indices: {e}")
        return []


def fetch_positions(broker: ZerodhaBroker) -> list[dict]:
    positions = broker.get_positions()
    result = []
    for pos in positions:
        qty = pos.get("quantity", 0)
        if qty == 0:
            continue
        avg = pos.get("average_price", 0)
        ltp = pos.get("last_price", 0)
        pnl = pos.get("pnl", 0)
        pnl_pct = ((ltp - avg) / avg * 100) if avg > 0 else 0
        result.append({
            "symbol": pos.get("tradingsymbol", ""),
            "exchange": pos.get("exchange", ""),
            "quantity": qty,
            "average_price": round(avg, 2),
            "ltp": round(ltp, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "product": pos.get("product", ""),
        })
    return result


def fetch_completed_trades(broker: ZerodhaBroker) -> list[dict]:
    orders = broker.get_orders()
    result = []
    for order in orders:
        if order.get("status") != "COMPLETE":
            continue
        result.append({
            "order_id": order.get("order_id", ""),
            "symbol": order.get("tradingsymbol", ""),
            "exchange": order.get("exchange", ""),
            "action": order.get("transaction_type", ""),
            "quantity": order.get("filled_quantity", order.get("quantity", 0)),
            "price": round(order.get("average_price", 0), 2),
            "order_type": order.get("order_type", ""),
            "product": order.get("product", ""),
            "timestamp": str(order.get("order_timestamp", "")),
        })
    return result


def fetch_margins(broker: ZerodhaBroker) -> dict:
    margins = broker.get_margins()
    seg = margins.get("equity", {})
    available = seg.get("available", {})
    utilised = seg.get("utilised", {})
    total_available = available.get("live_balance", 0) + available.get("collateral", 0)
    total_used = utilised.get("span", 0) + utilised.get("exposure", 0)
    total_capital = total_available + total_used
    utilization_pct = (total_used / total_capital * 100) if total_capital > 0 else 0
    return {
        "total_capital": round(total_capital, 2),
        "margin_used": round(total_used, 2),
        "margin_available": round(total_available, 2),
        "utilization_pct": round(utilization_pct, 1),
    }


def compute_stats(positions: list[dict], trades: list[dict]) -> dict:
    winning = [p for p in positions if p["pnl"] > 0]
    losing = [p for p in positions if p["pnl"] < 0]
    total_pnl = sum(p["pnl"] for p in positions)
    total_positions = len(positions)
    win_rate = (len(winning) / total_positions * 100) if total_positions > 0 else 0

    gross_profit = sum(p["pnl"] for p in winning)
    gross_loss = abs(sum(p["pnl"] for p in losing))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

    avg_win = (gross_profit / len(winning)) if winning else 0
    avg_loss = (gross_loss / len(losing)) if losing else 0
    avg_rr = (avg_win / avg_loss) if avg_loss > 0 else 0

    return {
        "total_positions": total_positions,
        "winning": len(winning),
        "losing": len(losing),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_risk_reward": round(avg_rr, 2),
        "total_trades_today": len(trades),
    }


def write_json(data: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish dashboard data")
    parser.add_argument(
        "--output", default="dashboard/data", help="Output directory for JSON files"
    )
    args = parser.parse_args()

    setup_logging()
    out = Path(args.output)

    broker = ZerodhaBroker()
    if not broker.authenticate():
        logger.error("Kite authentication failed — token may be expired")
        status = {"error": "auth_failed", "timestamp": datetime.now().isoformat()}
        write_json(status, out / "status.json")
        sys.exit(1)

    timestamp = datetime.now().isoformat()

    indices = fetch_indices(broker)
    write_json({"timestamp": timestamp, "indices": indices}, out / "indices.json")
    logger.info(f"Wrote indices: {len(indices)} entries")

    positions = fetch_positions(broker)
    write_json({"timestamp": timestamp, "positions": positions}, out / "positions.json")
    logger.info(f"Wrote positions: {len(positions)} entries")

    trades = fetch_completed_trades(broker)
    write_json({"timestamp": timestamp, "trades": trades}, out / "trades.json")
    logger.info(f"Wrote trades: {len(trades)} entries")

    margins = fetch_margins(broker)
    margins["timestamp"] = timestamp
    write_json(margins, out / "margins.json")
    logger.info("Wrote margins")

    stats = compute_stats(positions, trades)
    stats["timestamp"] = timestamp
    write_json(stats, out / "stats.json")
    logger.info("Wrote stats")

    logger.info(f"Dashboard data published to {out}")


if __name__ == "__main__":
    main()
