"""Karpathy data flywheel: append today's bars to the canonical backtest dataset.

Run after EOD-summary, post-close. Reads the most recent spy_5m_*.csv and
vix_5m_*.csv files in backtest/data/, fetches missing bars from yfinance for
[last_end_date+1, today], appends them, writes a NEW dated file, and updates
analysis/backtests/data-versions.jsonl with the new file hash.

Idempotent: if today's bars are already in the latest file, exits NOOP.
Atomic: writes to a temp file first, then renames into place.

Usage:
    python tools/append_today.py
    python tools/append_today.py --dry-run   (show what would happen)
    python tools/append_today.py --as-of 2026-05-09  (override "today" for tests)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytz

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.fetch_data import fetch  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ET = pytz.timezone("America/New_York")
VERSIONS_LOG = REPO / "analysis" / "backtests" / "data-versions.jsonl"

FILE_RE = re.compile(r"^(spy|vix)_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")


def _find_latest(symbol: str) -> Path | None:
    """Return path to the file with the latest end_date for the given symbol."""
    candidates: list[tuple[dt.date, Path]] = []
    for p in DATA_DIR.glob(f"{symbol}_5m_*.csv"):
        m = FILE_RE.match(p.name)
        if not m:
            continue
        end = dt.date.fromisoformat(m.group(3))
        candidates.append((end, p))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _file_range(path: Path) -> tuple[dt.date, dt.date]:
    """Parse start/end dates out of the filename."""
    m = FILE_RE.match(path.name)
    if not m:
        raise ValueError(f"Cannot parse range from filename: {path.name}")
    return dt.date.fromisoformat(m.group(2)), dt.date.fromisoformat(m.group(3))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_weekend(d: dt.date) -> bool:
    return d.weekday() >= 5


def _atomic_write(target: Path, df: pd.DataFrame) -> None:
    """Write df to target via temp file + atomic rename."""
    tmp = target.with_suffix(target.suffix + ".pending")
    df.to_csv(tmp, index=False)
    tmp.replace(target)


def append_symbol(
    symbol: str,
    today: dt.date,
    dry_run: bool = False,
) -> dict:
    """Append today's bars for one symbol. Returns a result dict.

    Result keys: status, action, latest_path, new_path, bars_added, hash_old, hash_new.
    """
    yf_symbol = "SPY" if symbol == "spy" else "^VIX"

    latest = _find_latest(symbol)
    if latest is None:
        return {
            "status": "error",
            "action": "abort",
            "reason": f"no existing {symbol}_5m_*.csv in {DATA_DIR}",
        }

    file_start, file_end = _file_range(latest)

    if file_end >= today:
        return {
            "status": "ok",
            "action": "noop",
            "reason": f"latest file already covers through {file_end}",
            "latest_path": str(latest),
            "hash_old": _sha256(latest),
        }

    # Fetch missing window. yfinance treats `end` as exclusive, so add 1 day.
    fetch_start = (file_end + dt.timedelta(days=1)).isoformat()
    fetch_end = (today + dt.timedelta(days=1)).isoformat()

    new_bars = fetch(yf_symbol, fetch_start, fetch_end, include_premarket=True)
    if new_bars.empty:
        return {
            "status": "ok",
            "action": "noop",
            "reason": f"yfinance returned 0 bars for {fetch_start}..{fetch_end} (likely all weekend/holiday)",
            "latest_path": str(latest),
            "hash_old": _sha256(latest),
        }

    existing = pd.read_csv(latest)
    combined = pd.concat([existing, new_bars], ignore_index=True)
    # Dedupe on timestamp_et (keep last — newer fetch wins on collision)
    combined["timestamp_et"] = pd.to_datetime(combined["timestamp_et"])
    combined = combined.drop_duplicates(subset=["timestamp_et"], keep="last")
    combined = combined.sort_values("timestamp_et").reset_index(drop=True)
    combined["timestamp_et"] = combined["timestamp_et"].astype(str)

    new_end = today
    new_path = DATA_DIR / f"{symbol}_5m_{file_start.isoformat()}_{new_end.isoformat()}.csv"

    if dry_run:
        return {
            "status": "ok",
            "action": "would_write",
            "latest_path": str(latest),
            "new_path": str(new_path),
            "bars_existing": len(existing),
            "bars_new": len(new_bars),
            "bars_combined": len(combined),
        }

    _atomic_write(new_path, combined)

    return {
        "status": "ok",
        "action": "appended",
        "latest_path": str(latest),
        "new_path": str(new_path),
        "bars_existing": len(existing),
        "bars_new": len(new_bars),
        "bars_combined": len(combined),
        "hash_old": _sha256(latest),
        "hash_new": _sha256(new_path),
    }


def log_version(symbol: str, result: dict, today: dt.date) -> None:
    """Append a row to data-versions.jsonl describing the append outcome."""
    VERSIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "as_of": today.isoformat(),
        **{k: v for k, v in result.items() if k != "reason" or v is not None},
    }
    with VERSIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None, help="Override 'today' (ISO date)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = (
        dt.date.fromisoformat(args.as_of)
        if args.as_of
        else dt.datetime.now(ET).date()
    )

    if _is_weekend(today):
        print(f"NOOP: {today} is a weekend — no bars to append.")
        return 0

    print(f"Append today: {today.isoformat()}{' (dry-run)' if args.dry_run else ''}")
    print(f"  data dir: {DATA_DIR}")

    overall_status = 0
    for symbol in ("spy", "vix"):
        print(f"\n[{symbol.upper()}]")
        result = append_symbol(symbol, today, dry_run=args.dry_run)
        for k, v in result.items():
            print(f"  {k}: {v}")
        if not args.dry_run:
            log_version(symbol, result, today)
        if result["status"] == "error":
            overall_status = 1

    print(f"\nDone. Versions logged to: {VERSIONS_LOG}")
    return overall_status


if __name__ == "__main__":
    raise SystemExit(main())
