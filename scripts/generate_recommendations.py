"""Generate buy/hold/exit recommendations from screener signals + portfolio.

Combines screener composite score with technical indicators to produce
actionable signals for portfolio holdings and entry candidates.

Usage:
    python -m scripts.generate_recommendations
    python -m scripts.generate_recommendations --output dashboard/data/recommendations.json
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from config.logging_config import setup_logging
from notifications import notify


def _action_label(score: float, rsi: float, trend: str, in_portfolio: bool) -> str:
    if in_portfolio:
        if score >= 0.7 and rsi < 70 and trend == "UPTREND":
            return "STRONG BUY"
        if score >= 0.5 and rsi < 65:
            return "ACCUMULATE"
        if score >= 0.3:
            return "HOLD"
        if score >= 0.15 or rsi > 70:
            return "MONITOR"
        return "EXIT"
    else:
        if score >= 0.7 and rsi < 70:
            return "ENTRY SIGNAL"
        if score >= 0.5:
            return "WATCH"
        return "NO SIGNAL"


def _reason(score: float, rsi: float, adx: float, trend: str) -> str:
    parts = []
    if rsi > 70:
        parts.append("RSI overbought")
    elif rsi < 30:
        parts.append("RSI oversold")
    else:
        parts.append("RSI neutral")

    if adx > 30:
        parts.append(f"strong trend (ADX {adx:.0f})")
    elif adx > 20:
        parts.append(f"moderate trend (ADX {adx:.0f})")
    else:
        parts.append("weak trend")

    parts.append(trend.lower())
    return ", ".join(parts)


def generate(signals_path: Path, portfolio_path: Path) -> dict:
    signals_data = {}
    if signals_path.exists():
        with open(signals_path) as f:
            signals_data = json.load(f)

    portfolio_data = {}
    if portfolio_path.exists():
        with open(portfolio_path) as f:
            portfolio_data = json.load(f)

    held_symbols = {
        h["symbol"] for h in portfolio_data.get("holdings", [])
    }

    all_screened = []
    for seg_stocks in (signals_data.get("segments") or {}).values():
        all_screened.extend(seg_stocks)
    for pick in signals_data.get("top_picks", []):
        if not any(s["symbol"] == pick["symbol"] for s in all_screened):
            all_screened.append(pick)

    screened_map = {s["symbol"]: s for s in all_screened}

    portfolio_actions = []
    for h in portfolio_data.get("holdings", []):
        sym = h["symbol"]
        sc = screened_map.get(sym, {})
        score = sc.get("composite_score", 0)
        rsi = h.get("rsi", sc.get("rsi", 50))
        adx = h.get("adx", sc.get("adx", 0))
        trend = h.get("trend", "N/A")

        action = _action_label(score, rsi, trend, in_portfolio=True)
        reason = _reason(score, rsi, adx, trend)

        portfolio_actions.append({
            "symbol": sym,
            "action": action,
            "score": round(score, 3),
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "trend": trend,
            "pnl_pct": h.get("pnl_pct", 0),
            "reason": reason,
        })

    portfolio_actions.sort(key=lambda x: x["score"], reverse=True)

    entry_signals = []
    for pick in signals_data.get("top_picks", []):
        sym = pick["symbol"]
        if sym in held_symbols:
            continue
        score = pick.get("composite_score", 0)
        rsi = pick.get("rsi", 50)
        adx = pick.get("adx", 0)
        trend = "UPTREND" if pick.get("entry_signal") else "N/A"

        action = _action_label(score, rsi, trend, in_portfolio=False)
        reason = _reason(score, rsi, adx, trend)

        entry_signals.append({
            "symbol": sym,
            "action": action,
            "score": round(score, 3),
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "segment": pick.get("segment", ""),
            "close": pick.get("close", 0),
            "reason": reason,
        })

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "portfolio_actions": portfolio_actions,
        "entry_signals": entry_signals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate trading recommendations")
    parser.add_argument(
        "--output", default="dashboard/data/recommendations.json",
    )
    parser.add_argument(
        "--signals", default="dashboard/data/signals.json",
    )
    parser.add_argument(
        "--portfolio", default="dashboard/data/portfolio.json",
    )
    args = parser.parse_args()

    setup_logging()

    result = generate(Path(args.signals), Path(args.portfolio))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    n_actions = len(result["portfolio_actions"])
    n_entry = len([e for e in result["entry_signals"] if e["action"] == "ENTRY SIGNAL"])
    logger.info(f"Recommendations: {n_actions} portfolio, {n_entry} entry signals")

    if n_entry > 0:
        top = result["entry_signals"][:5]
        lines = [f"*Entry Signals ({n_entry})*"]
        for s in top:
            lines.append(f"  {s['symbol']}: {s['action']} ({s['score']:.2f})")
        notify("\n".join(lines))


if __name__ == "__main__":
    main()
