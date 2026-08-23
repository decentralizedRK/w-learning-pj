"""Fetch portfolio holdings and positions from Kite, compute P&L, run technicals.

Usage:
    python -m scripts.portfolio_snapshot
    python -m scripts.portfolio_snapshot --output dashboard/data/portfolio.json
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from loguru import logger

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging
from data.fetchers import get_fetcher
from indicators.technical import TechnicalIndicators
from monitoring.threshold import check as check_threshold
from notifications import notify


def _technical_summary(symbol: str, fetcher) -> dict:
    """Fetch recent OHLCV and compute technical indicators for a symbol."""
    end = date.today()
    start = end - timedelta(days=90)
    try:
        df = fetcher.fetch_equity_ohlcv(symbol, start, end)
        if df.empty or len(df) < 20:
            return {}
        enriched = TechnicalIndicators.add_all_strategy_indicators(df.copy())
        enriched = TechnicalIndicators.add_roc(enriched, 20)
        last = enriched.iloc[-1]
        sma_50 = float(last.get("sma_50", 0)) if "sma_50" in enriched.columns else None
        sma_200 = float(last.get("sma_200", 0)) if "sma_200" in enriched.columns else None
        trend = "UPTREND"
        if sma_50 and sma_200:
            if sma_50 < sma_200:
                trend = "DOWNTREND"
        elif sma_50 is None:
            trend = "N/A"
        macd_val = float(last.get("macd", 0))
        macd_sig = float(last.get("macd_signal", 0))
        return {
            "rsi": round(float(last.get("rsi", 0)), 1),
            "adx": round(float(last.get("adx", 0)), 1),
            "roc_20": round(float(last.get("roc_20", 0)), 1),
            "macd_signal": "bullish" if macd_val > macd_sig else "bearish",
            "trend": trend,
        }
    except Exception as e:
        logger.debug(f"Technicals failed for {symbol}: {e}")
        return {}


def build_snapshot(broker: ZerodhaBroker, fetcher) -> dict:
    holdings = broker.get_holdings()
    positions = broker.get_positions()

    total_invested = 0.0
    total_current = 0.0
    holding_records = []

    for h in holdings:
        qty = h.get("quantity", 0)
        if qty == 0:
            continue
        symbol = h.get("tradingsymbol", "")
        avg_price = h.get("average_price", 0)
        ltp = h.get("last_price", 0)
        close_price = h.get("close_price", ltp)
        invested = avg_price * qty
        current = ltp * qty
        pnl = current - invested
        pnl_pct = (pnl / invested * 100) if invested else 0
        day_change = ltp - close_price
        day_change_pct = (day_change / close_price * 100) if close_price else 0

        total_invested += invested
        total_current += current

        technicals = _technical_summary(symbol, fetcher)

        should_alert, band, _ = check_threshold(symbol, ltp, avg_price)
        if should_alert:
            notify(
                f"*{symbol}* crossed *{band}%* band\n"
                f"CMP: {ltp:,.2f} | Avg: {avg_price:,.2f}"
            )

        holding_records.append({
            "symbol": symbol,
            "qty": qty,
            "avg_price": float(avg_price),
            "ltp": float(ltp),
            "day_change_pct": round(day_change_pct, 2),
            "invested": round(invested, 2),
            "current": round(current, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_pct": 0.0,
            "alert_band": band if band < 0 else None,
            **technicals,
        })

    if total_current > 0:
        for h in holding_records:
            h["weight_pct"] = round(h["current"] / total_current * 100, 1)

    holding_records.sort(key=lambda x: x["pnl"], reverse=True)
    runners = holding_records[:5]
    draggers = holding_records[-5:][::-1] if len(holding_records) > 5 else []

    position_records = []
    for p in positions:
        qty = p.get("quantity", 0)
        if qty == 0:
            continue
        position_records.append({
            "symbol": p.get("tradingsymbol", ""),
            "qty": qty,
            "entry_price": float(p.get("average_price", 0)),
            "ltp": float(p.get("last_price", 0)),
            "pnl": float(p.get("pnl", 0)),
            "product": p.get("product", ""),
            "exchange": p.get("exchange", ""),
        })

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0

    return {
        "timestamp": date.today().isoformat(),
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "holdings": holding_records,
        "positions": position_records,
        "runners": runners,
        "draggers": draggers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio snapshot from Kite")
    parser.add_argument(
        "--output", default="dashboard/data/portfolio.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    setup_logging()

    broker = ZerodhaBroker()
    if not broker.authenticate():
        logger.error("Kite auth failed — cannot fetch portfolio")
        return

    fetcher = get_fetcher()
    snapshot = build_snapshot(broker, fetcher)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    n = len(snapshot["holdings"])
    pnl = snapshot["total_pnl"]
    logger.info(f"Snapshot: {n} holdings, P&L: {pnl:+,.0f}")

    if n > 0:
        msg = (
            f"*Portfolio Snapshot*\n"
            f"Holdings: {n}\n"
            f"Invested: ₹{snapshot['total_invested']:,.0f}\n"
            f"Current: ₹{snapshot['total_current']:,.0f}\n"
            f"P&L: ₹{pnl:+,.0f} ({snapshot['total_pnl_pct']:+.1f}%)"
        )
        if snapshot["runners"]:
            top = snapshot["runners"][0]
            msg += f"\nTop: {top['symbol']} ({top['pnl_pct']:+.1f}%)"
        notify(msg)


if __name__ == "__main__":
    main()
