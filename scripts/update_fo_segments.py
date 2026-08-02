"""Refresh F&O market-cap segment lists from NSE index constituents.

Usage:
    python -m scripts.update_fo_segments
"""

from datetime import date
from pathlib import Path

from loguru import logger

from config.constants import FO_LOT_SIZES

INDEX_TO_SEGMENT = {
    "NIFTY 50": "LARGECAP_FO",
    "NIFTY MIDCAP 150": "MIDCAP_FO",
    "NIFTY SMLCAP 250": "SMALLCAP_FO",
}

OUTPUT_PATH = Path("config/fo_segments.py")


def fetch_segment_lists() -> dict[str, list[str]]:
    from jugaad_data.nse import NSELive

    nse = NSELive()
    fo_set = set(FO_LOT_SIZES.keys())
    segments: dict[str, list[str]] = {}

    for index_name, segment_key in INDEX_TO_SEGMENT.items():
        try:
            data = nse.live_index(index_name)
            constituents = [
                item["symbol"] for item in data.get("data", []) if "symbol" in item
            ]
            fo_eligible = sorted(set(constituents) & fo_set)
            segments[segment_key] = fo_eligible
            logger.info(f"{segment_key}: {len(fo_eligible)} F&O stocks from {index_name}")
        except Exception as e:
            logger.error(f"Failed to fetch {index_name}: {e}")
            segments[segment_key] = []

    return segments


def _format_list(symbols: list[str]) -> str:
    if not symbols:
        return "[]"
    items = ",\n".join(f'    "{s}"' for s in symbols)
    return f"[\n{items},\n]"


def write_segments_file(segments: dict[str, list[str]], today: str) -> None:
    lines = [f'LAST_UPDATED = "{today}"', ""]

    for segment_key in ["LARGECAP_FO", "MIDCAP_FO", "SMALLCAP_FO"]:
        symbols = segments.get(segment_key, [])
        lines.append(f"{segment_key}: list[str] = {_format_list(symbols)}")
        lines.append("")

    lines.append("SEGMENT_MAP: dict[str, list[str]] = {")
    for segment_key in ["LARGECAP_FO", "MIDCAP_FO", "SMALLCAP_FO"]:
        lines.append(f'    "{segment_key}": {segment_key},')
    lines.append("}")
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))
    logger.info(f"Updated {OUTPUT_PATH}")


def main() -> None:
    from config.logging_config import setup_logging

    setup_logging()

    logger.info("Fetching index constituents from NSE...")
    segments = fetch_segment_lists()

    total = sum(len(v) for v in segments.values())
    if total == 0:
        logger.error("All segment fetches failed, not overwriting existing file")
        return

    write_segments_file(segments, date.today().isoformat())
    logger.info(
        f"Done: {len(segments.get('LARGECAP_FO', []))} large, "
        f"{len(segments.get('MIDCAP_FO', []))} mid, "
        f"{len(segments.get('SMALLCAP_FO', []))} small"
    )


if __name__ == "__main__":
    main()
