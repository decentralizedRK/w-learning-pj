"""Fetch per-ticker news and market headlines for portfolio + screener stocks.

Usage:
    python -m scripts.news_digest
    python -m scripts.news_digest --output dashboard/data/news.json
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import feedparser
import yfinance as yf
from loguru import logger

from config.logging_config import setup_logging
from notifications import notify

RSS_FEEDS = [
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Livemint", "https://www.livemint.com/rss/markets"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
]

MAX_NEWS_AGE_HOURS = 120


def _age_hours(pub_time) -> float | None:
    if pub_time is None:
        return None
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(pub_time) if isinstance(pub_time, str) else pub_time
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (datetime.now(UTC) - dt).total_seconds() / 3600
    except Exception:
        return None


def fetch_ticker_news(ticker: str, max_items: int = 3) -> list[dict]:
    results = []
    try:
        t = yf.Ticker(f"{ticker}.NS")
        news = t.news or []
        for item in news[:max_items]:
            content = item.get("content", {})
            age = _age_hours(content.get("pubDate"))
            if age is not None and age > MAX_NEWS_AGE_HOURS:
                continue
            results.append({
                "title": content.get("title", item.get("title", "")),
                "publisher": content.get("provider", {}).get(
                    "displayName", ""
                ),
                "link": content.get("canonicalUrl", {}).get("url", ""),
                "age_h": round(age, 1) if age else None,
            })
    except Exception as e:
        logger.debug(f"News fetch failed for {ticker}: {e}")

    if not results:
        try:
            query = ticker.replace(".NS", "").replace(".BO", "")
            url = (
                f"https://news.google.com/rss/search?"
                f"q={query}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en"
            )
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                age = _age_hours(entry.get("published"))
                if age is not None and age > MAX_NEWS_AGE_HOURS:
                    continue
                results.append({
                    "title": entry.get("title", ""),
                    "publisher": "Google News",
                    "link": entry.get("link", ""),
                    "age_h": round(age, 1) if age else None,
                })
        except Exception as e:
            logger.debug(f"Google News fallback failed for {ticker}: {e}")

    return results


def fetch_market_headlines(max_per_feed: int = 4) -> list[dict]:
    headlines = []
    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                age = _age_hours(entry.get("published"))
                if age is not None and age > 48:
                    continue
                headlines.append({
                    "source": source,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": (entry.get("summary", "") or "")[:200],
                    "age_h": round(age, 1) if age else None,
                })
        except Exception as e:
            logger.debug(f"RSS feed failed for {source}: {e}")
    return headlines


def main() -> None:
    parser = argparse.ArgumentParser(description="News digest")
    parser.add_argument("--output", default="dashboard/data/news.json")
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

    logger.info(f"Fetching news for {len(symbols)} symbols")

    ticker_news = {}
    for sym in sorted(symbols):
        news = fetch_ticker_news(sym)
        if news:
            ticker_news[sym] = news

    headlines = fetch_market_headlines()

    digest = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "ticker_news": ticker_news,
        "market_headlines": headlines,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(digest, f, indent=2)

    total = sum(len(v) for v in ticker_news.values())
    logger.info(f"News: {total} ticker items, {len(headlines)} headlines")

    notify(
        f"*Morning News Digest*\n"
        f"Ticker news: {total} items for {len(ticker_news)} stocks\n"
        f"Market headlines: {len(headlines)}"
    )


if __name__ == "__main__":
    main()
