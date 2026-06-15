"""Merge multiple SPY/VIX 5-min CSV files into a single master training set.

Reads any spy_5m_*.csv / vix_5m_*.csv files in data/ that match a given pattern,
deduplicates by timestamp, sorts ascending, and writes the combined file.

Usage:
    python tools/merge_data.py --start 2025-01-01 --end 2026-05-07
    python tools/merge_data.py --start 2025-01-01 --end 2026-05-07 --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"


def merge_pattern(pattern: str, start: dt.date, end: dt.date, out_name: str, dry_run: bool) -> None:
    files = sorted(DATA.glob(pattern))
    if not files:
        logger.warning("no files matching %s", pattern)
        return
    frames: list[pd.DataFrame] = []
    for f in files:
        if f.name == out_name:
            continue
        df = pd.read_csv(f)
        frames.append(df)
        logger.info("loaded %s -> %d rows", f.name, len(df))
    if not frames:
        return
    combined = pd.concat(frames, ignore_index=True)
    combined["_ts"] = pd.to_datetime(combined["timestamp_et"], utc=True, errors="coerce")
    combined = combined.dropna(subset=["_ts"])
    # Filter to window (inclusive)
    mask = (combined["_ts"].dt.date >= start) & (combined["_ts"].dt.date <= end)
    combined = combined[mask]
    # Dedupe by timestamp string and sort
    combined = combined.drop_duplicates(subset=["timestamp_et"], keep="first")
    combined = combined.sort_values("_ts").drop(columns=["_ts"]).reset_index(drop=True)
    out_path = DATA / out_name
    logger.info("combined %d unique rows -> %s", len(combined), out_path.name)
    if not dry_run:
        combined.to_csv(out_path, index=False)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    merge_pattern("spy_5m_*.csv", start, end, f"spy_5m_{start}_{end}.csv", args.dry_run)
    merge_pattern("vix_5m_*.csv", start, end, f"vix_5m_{start}_{end}.csv", args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
