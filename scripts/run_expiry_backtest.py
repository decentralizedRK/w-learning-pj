"""Backtest expiry-day straddle/directional strategies on NIFTY or screened stocks.

Usage:
    # Single symbol (NIFTY default)
    python -m scripts.run_expiry_backtest

    # Specific symbol with custom params
    python -m scripts.run_expiry_backtest --symbol BANKNIFTY --lots 10 --duration 1y

    # Use screened F&O stocks (from run_screener output or live screening)
    python -m scripts.run_expiry_backtest --screened RELIANCE,INFY,TCS

    # Full F&O universe scan (top N by momentum)
    python -m scripts.run_expiry_backtest --scan-universe --top 10

    # Custom time value estimate and strike gap
    python -m scripts.run_expiry_backtest --time-value 20 --strike-gap 100
"""

import argparse
from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

from broker.zerodha import ZerodhaBroker
from config.logging_config import setup_logging
from data.fetchers.instrument_lookup import InstrumentLookup
from data.fetchers.kite_fetcher import KiteFetcher
from strategies.expiry_straddle import (
    extract_expiry_days,
    optimize_strategies,
)


def fetch_minute_data(fetcher: KiteFetcher, token: int, duration_days: int) -> pd.DataFrame:
    to_date = datetime.now()
    from_date = to_date - timedelta(days=duration_days)
    return fetcher.fetch_historical_chunked(
        instrument_token=token,
        from_date=from_date,
        to_date=to_date,
        interval="minute",
    )


def print_result(r: dict) -> None:
    flag = "***" if r["win_rate"] >= 50 and r["rr_ratio"] >= 2.0 else "   "
    print(
        f"  {flag} {r['label']:<70} | N:{r['trades']:>3} | WR:{r['win_rate']:>5.1f}% | "
        f"RR:{r['rr_ratio']:>5.2f}:1 | "
        f"AvgW:{r['avg_win_pts']:>6.1f} AvgL:{r['avg_loss_pts']:>6.1f} | "
        f"P&L: ₹{r['total_pnl']:>+10,}"
    )


def run_for_symbol(
    fetcher: KiteFetcher,
    lookup: InstrumentLookup,
    symbol: str,
    duration_days: int,
    num_lots: int,
    strike_gap: int,
    time_value: float,
    output_csv: str | None,
) -> list[dict]:
    token = lookup.get_token(symbol)
    if token is None:
        logger.error(f"Could not find instrument token for {symbol}")
        return []

    print(f"\n{'='*100}")
    print(
        f"  {symbol} (token: {token}) | {duration_days} days"
        f" | {num_lots} lots | TV: {time_value} pts/side"
    )
    print(f"{'='*100}")

    df = fetch_minute_data(fetcher, token, duration_days)
    if df.empty:
        logger.error(f"No data for {symbol}")
        return []
    print(f"  Fetched {len(df)} minute candles")

    days = extract_expiry_days(df)
    if not days:
        logger.warning(f"No expiry days found for {symbol}")
        return []
    print(f"  Found {len(days)} expiry days\n")

    results = optimize_strategies(
        days,
        symbol=symbol,
        num_lots=num_lots,
        strike_gap=strike_gap,
        time_value=time_value,
    )

    meets_criteria = [r for r in results if r["win_rate"] >= 50 and r["rr_ratio"] >= 2.0]
    meets_50 = [r for r in results if r["win_rate"] >= 50 and r["total_pnl"] > 0]
    profitable = [r for r in results if r["total_pnl"] > 0]

    if meets_criteria:
        print("\n  STRATEGIES MEETING WR>=50% AND RR>=2:1:")
        for r in sorted(meets_criteria, key=lambda x: x["total_pnl"], reverse=True):
            print_result(r)
    elif meets_50:
        print("\n  PROFITABLE STRATEGIES WITH WR>=50%:")
        for r in sorted(meets_50, key=lambda x: x["total_pnl"], reverse=True):
            print_result(r)
    elif profitable:
        print("\n  PROFITABLE STRATEGIES (top 10):")
        for r in sorted(profitable, key=lambda x: x["total_pnl"], reverse=True)[:10]:
            print_result(r)
    else:
        print(f"\n  No profitable strategies found for {symbol}")
        best = sorted(results, key=lambda x: x["win_rate"] * x["rr_ratio"], reverse=True)[:5]
        if best:
            print("  Top 5 by WR×RR score:")
            for r in best:
                print_result(r)

    # Detailed breakdown of best strategy
    best_pool = meets_criteria or meets_50 or profitable or results
    if best_pool:
        best = sorted(best_pool, key=lambda x: x["total_pnl"], reverse=True)[0]
        print(f"\n  BEST: {best['label']}")
        print(f"  Trades:{best['trades']} W:{best['winners']} L:{best['losers']} "
              f"WR:{best['win_rate']}% RR:{best['rr_ratio']}:1 P&L:₹{best['total_pnl']:+,}")

    if output_csv:
        rows = [{k: v for k, v in r.items() if k != "details"} for r in results]
        for row in rows:
            row["symbol"] = symbol
        pd.DataFrame(rows).to_csv(output_csv, index=False)
        print(f"\n  Results saved to {output_csv}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Expiry-day straddle/directional backtest")
    parser.add_argument("--symbol", default="NIFTY", help="Symbol (default: NIFTY)")
    parser.add_argument("--duration", default="1y", help="Duration: 30d, 6m, 1y (default: 1y)")
    parser.add_argument("--lots", type=int, default=10, help="Number of lots (default: 10)")
    parser.add_argument("--strike-gap", type=int, default=50, help="Strike gap (default: 50)")
    parser.add_argument(
        "--time-value", type=float, default=15,
        help="Estimated time value per side (default: 15)",
    )
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument(
        "--screened", default=None, help="Comma-separated screened symbols",
    )
    parser.add_argument(
        "--scan-universe", action="store_true", help="Scan top F&O stocks",
    )
    parser.add_argument(
        "--top", type=int, default=5,
        help="Top N stocks for universe scan (default: 5)",
    )
    args = parser.parse_args()

    setup_logging()

    duration_map = {"d": 1, "m": 30, "y": 365}
    amount = int(args.duration[:-1])
    unit = args.duration[-1].lower()
    duration_days = amount * duration_map.get(unit, 1)

    broker = ZerodhaBroker()
    if not broker.access_token:
        print("Error: No access token. Set QOS_KITE_ACCESS_TOKEN in .env")
        print(f"Login URL: {broker.generate_login_url()}")
        return

    fetcher = KiteFetcher(broker)
    lookup = InstrumentLookup(broker._get_kite())

    if args.scan_universe:
        from data.fetchers.nse_symbols import FO_STOCK_LIST
        symbols = FO_STOCK_LIST[:args.top]
        print(f"Scanning top {args.top} F&O stocks: {', '.join(symbols)}")
    elif args.screened:
        symbols = [s.strip() for s in args.screened.split(",")]
        print(f"Running on screened stocks: {', '.join(symbols)}")
    else:
        symbols = [args.symbol]

    all_results = []
    for symbol in symbols:
        strike_gap = args.strike_gap
        if symbol in ("BANKNIFTY",):
            strike_gap = 100

        output = args.output
        if output and len(symbols) > 1:
            output = output.replace(".csv", f"_{symbol}.csv")

        results = run_for_symbol(
            fetcher, lookup, symbol,
            duration_days, args.lots, strike_gap, args.time_value, output,
        )
        all_results.extend(results)

    if len(symbols) > 1 and all_results:
        print(f"\n{'='*100}")
        print("  CROSS-SYMBOL SUMMARY — best profitable strategy per symbol")
        print(f"{'='*100}")

        by_symbol = {}
        for r in all_results:
            sym = r.get("symbol", symbols[0])
            if sym not in by_symbol or r["total_pnl"] > by_symbol[sym]["total_pnl"]:
                if r["total_pnl"] > 0:
                    by_symbol[sym] = r

        if by_symbol:
            ranked = sorted(
                by_symbol.items(), key=lambda x: x[1]["total_pnl"], reverse=True,
            )
            for sym, r in ranked:
                wr = r["win_rate"]
                rr = r["rr_ratio"]
                pnl = r["total_pnl"]
                print(
                    f"  {sym:<15} {r['label']:<55}"
                    f" WR:{wr:>5.1f}% RR:{rr:>4.2f}:1 P&L:₹{pnl:>+10,}"
                )
        else:
            print("  No profitable strategies found across scanned symbols.")

    print(f"\n  NOTE: Premiums estimated at {args.time_value} pts time value per side.")
    print("  Real premiums depend on IV/VIX. Results are directional guidance, not exact P&L.")


if __name__ == "__main__":
    main()
