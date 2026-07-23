"""Fill the small OPRA straggler gap at the LEADING edge of the option cache.

Context (2026-07-22 audit, see analysis/edge-matrix/OPRA-BACKFILL-REPORT.md):
the requested "backfill OPRA backward to 2026-01-02" was found ALREADY DONE
(381/386 SPY-covered days have real OPRA fills, spanning 2025-01-02 through
2026-07-17, verified against analysis/edge-matrix/day-inventory-2026-07-23.json).
The only genuine gap left is 5 of the most RECENT trading days that simply
hadn't been fetched yet. This script closes that gap using the SAME
fetch_contract_bars/write_cache functions as expand_opra_cache.py (same auth
path via _alpaca_creds.resolve_alpaca_creds, same CSV schema) — it does not
introduce a new fetch or auth path.

Strike range per day = [floor(day_low)-3, ceil(day_high)+3] by $1, both C/P,
using the day's actual RTH low/high pulled from the newest rolling SPY 5m
master that covers it (spy_5m_2026-05-19_2026-07-22.csv at time of writing).

Usage:
    python tools/_backfill_opra_recent_gap.py --plan-only
    python tools/_backfill_opra_recent_gap.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from expand_opra_cache import (  # noqa: E402
    already_cached,
    fetch_contract_bars,
    option_symbol,
    write_cache,
    write_empty_sentinel,
)
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402

DATA_DIR = REPO / "data"
PROGRESS_FILE = REPO.parent / "analysis" / "edge-matrix" / "opra-backfill-progress.json"

MASTER = DATA_DIR / "spy_5m_2026-05-19_2026-07-22.csv"
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)


def load_day_ranges(dates: list[str]) -> dict[str, tuple[float, float, float]]:
    df = pd.read_csv(MASTER)
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = df["ts"].dt.date.astype(str)
    out = {}
    for d in dates:
        day = df[df["date"] == d]
        rth = day[(day["ts"].dt.time >= RTH_START) & (day["ts"].dt.time < RTH_END)]
        if len(rth) == 0:
            continue
        out[d] = (float(rth["low"].min()), float(rth["high"].max()), float(rth["close"].iloc[-1]))
    return out


def build_contracts(day_ranges: dict[str, tuple[float, float, float]]) -> list[tuple[dt.date, str]]:
    contracts = []
    for d, (low, high, _close) in sorted(day_ranges.items()):
        trade_date = dt.date.fromisoformat(d)
        lo = math.floor(low) - 3
        hi = math.ceil(high) + 3
        for strike in range(lo, hi + 1):
            for side in ("C", "P"):
                contracts.append((trade_date, option_symbol(trade_date, strike, side)))
    return contracts


def write_progress(payload: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", default=None, help="Override target dates YYYY-MM-DD")
    ap.add_argument("--sleep", type=float, default=0.35, help="Seconds between requests (~170/min)")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args(argv)

    target_dates = args.dates or ["2026-07-15", "2026-07-16", "2026-07-20", "2026-07-21", "2026-07-22"]
    day_ranges = load_day_ranges(target_dates)
    missing = [d for d in target_dates if d not in day_ranges]
    if missing:
        print(f"WARN: no RTH bars in master for: {missing} (will be skipped)")

    contracts = build_contracts(day_ranges)
    to_fetch = [(d, s) for d, s in contracts if not already_cached(s)]
    print(f"Days: {sorted(day_ranges.keys())}")
    for d, (lo, hi, c) in sorted(day_ranges.items()):
        print(f"  {d}: low={lo:.2f} high={hi:.2f} close={c:.2f}")
    print(f"Total contracts (both sides, all target days): {len(contracts)}")
    print(f"Already cached: {len(contracts) - len(to_fetch)}  |  To fetch: {len(to_fetch)}")

    if args.plan_only:
        return 0

    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={creds.key[:4]}... source={creds.source}")

    fetched, empty, errors = 0, 0, []
    started = dt.datetime.now(dt.timezone.utc)
    for i, (trade_date, symbol) in enumerate(to_fetch, 1):
        attempt = 0
        while True:
            attempt += 1
            try:
                rows = fetch_contract_bars(symbol, trade_date, creds.key, creds.secret)
                if rows:
                    write_cache(symbol, rows)
                    fetched += 1
                    print(f"[{i}/{len(to_fetch)}] OK    {symbol}  {len(rows)} bars")
                else:
                    write_empty_sentinel(symbol)
                    empty += 1
                    print(f"[{i}/{len(to_fetch)}] EMPTY {symbol}  no bars")
                break
            except HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:200]
                if e.code == 429 and attempt < 5:
                    backoff = min(60, 2 ** attempt)
                    print(f"[{i}/{len(to_fetch)}] 429 {symbol} — backoff {backoff}s (attempt {attempt})")
                    time.sleep(backoff)
                    continue
                errors.append({"symbol": symbol, "date": trade_date.isoformat(), "http_code": e.code, "body": body})
                print(f"[{i}/{len(to_fetch)}] FAIL  {symbol}  HTTP {e.code}: {body}")
                break
            except (URLError, TimeoutError) as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                errors.append({"symbol": symbol, "date": trade_date.isoformat(), "error": repr(e)})
                print(f"[{i}/{len(to_fetch)}] FAIL  {symbol}  {e}")
                break
        if i % 10 == 0 or i == len(to_fetch):
            elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
            write_progress({
                "job": "opra_recent_gap_backfill",
                "target_dates": target_dates,
                "day_ranges": {d: {"low": lo, "high": hi, "close": c} for d, (lo, hi, c) in day_ranges.items()},
                "total_contracts": len(contracts),
                "already_cached_before": len(contracts) - len(to_fetch),
                "to_fetch": len(to_fetch),
                "fetched_this_run": fetched,
                "empty_this_run": empty,
                "errors_count": len(errors),
                "errors_sample": errors[-5:],
                "elapsed_seconds": int(elapsed),
                "last_update": dt.datetime.now(dt.timezone.utc).isoformat(),
                "status": "running" if i < len(to_fetch) else "completed",
            })
        time.sleep(args.sleep)

    print(f"\nDone. fetched={fetched} empty={empty} errors={len(errors)}")
    if errors:
        for e in errors[:10]:
            print(" -", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
