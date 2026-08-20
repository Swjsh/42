"""Backfill backtest/data/spy_sip_cache/ (spy_5m_{date}.json, spy_1m_{date}.json)
from 2024-01-01 through the day before the existing live-window cache begins,
so engine-replay depth stops being capped at 35 days.

WHY THIS EXISTS (2026-08-19/20 night session): the engine-replay population was
capped at 35 trading days because backtest/data/spy_sip_cache only held the live
window (2026-06-26 onward). Verified live on the existing paper key ($0):
/v2/stocks/SPY/bars returns full RTH+extended-hours 5m bars for 2024-01-02,
2025-01-02, and 2025-06-02 -- so a ~2.5-year backfill is one script away.

THE DST TRAP (this is the whole reason this file is careful): the cache format
stores NAIVE ET wall-clock timestamps (e.g. "2026-06-26T09:30:00", no offset).
This repo has a documented scar exactly here -- backtest/lib/et_frame.py
describes a writer (tools/extend_data_v2.py) that applies a FIXED -04:00
offset year-round, mislabeling every EST-month (winter) bar +1h and clipping
the last true RTH hour. This script NEVER does that: every UTC->ET conversion
goes through zoneinfo.ZoneInfo("America/New_York").astimezone(), the same
DST-correct primitive backtest/tools/alpaca_bars.py already uses. Verified
correct BEFORE this bulk write via
backtest/tools/_verify_dst_frame_2024_backfill.py (2025-01-02 EST vs
2025-06-02 EDT both land their 09:30 ET bar at naive wall-clock 09:30:00,
despite the raw UTC offsets differing by an hour). A regression guard lives at
backtest/tests/test_spy_sip_cache_dst_guard.py.

Window: [04:00, 20:00) ET wall time (premarket + RTH + after-hours), matching
the existing cache files' convention exactly (verified against
spy_sip_cache/spy_5m_2026-06-26.json: first bar 04:00:00, last bar 19:55:00).

Fetched per calendar month (not per trading day) to keep request count low --
~30 months x (1 call for 5m + up to ~3 paginated calls for 1m) rather than
~630 trading days x 2 calls. cache-and-skip: a day already on disk (both
timeframes) is never re-fetched; a whole month is skipped up front if every
weekday in range already has both files.

Usage:
    python tools/backfill_spy_sip_cache_2024.py --plan-only
    python tools/backfill_spy_sip_cache_2024.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import masked, resolve_alpaca_creds  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO / "data" / "spy_sip_cache"

SPY_BARS_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
ET = ZoneInfo("America/New_York")

WINDOW_START = dt.time(4, 0)   # inclusive
WINDOW_END = dt.time(20, 0)    # exclusive

START_DATE = dt.date(2024, 1, 1)
# Day before the existing live-window cache begins -- verified via
# `ls backtest/data/spy_sip_cache` this session: earliest existing file is
# spy_5m_2026-06-26.json. Backfilling up to (not including) that date closes
# the gap without touching or duplicating already-live-captured days.
END_DATE = dt.date(2026, 6, 25)

PAGE_SLEEP_S = 0.2
CHUNK_SLEEP_S = 0.3
REQUEST_TIMEOUT_S = 60


def month_chunks(start: dt.date, end: dt.date):
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        if cur.month == 12:
            nxt = dt.date(cur.year + 1, 1, 1)
        else:
            nxt = dt.date(cur.year, cur.month + 1, 1)
        chunk_start = max(cur, start)
        chunk_end = min(nxt - dt.timedelta(days=1), end)
        yield chunk_start, chunk_end
        cur = nxt


def weekdays_in_range(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def cache_path(timeframe: str, day: dt.date) -> Path:
    return CACHE_DIR / f"spy_{timeframe}_{day.isoformat()}.json"


def chunk_fully_cached(timeframe: str, start: dt.date, end: dt.date) -> bool:
    """Approximate skip check: every WEEKDAY in range already has a file.
    Holidays never get a file (Alpaca returns zero bars), so a month with a
    holiday will always re-issue one API call -- correct behavior (never
    silently assume a missing file means "holiday, skip"), just not free.
    """
    return all(cache_path(timeframe, d).exists() for d in weekdays_in_range(start, end))


def to_et_naive(raw_ts: str) -> dt.datetime:
    ts_utc = dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    return ts_utc.astimezone(ET).replace(tzinfo=None)


def fetch_range(creds, timeframe: str, start: dt.date, end: dt.date) -> list[dict]:
    """Fetch raw Alpaca bars for [start, end] inclusive, paginated. Wide UTC
    bounds (07:00Z start covers 04:00 ET in both EDT=08:00Z/EST=09:00Z; end+1
    day 02:00Z covers 20:00 ET in both EDT=00:00Z/EST=01:00Z next day) -- the
    precise ET-window cut happens AFTER conversion, in bucket_by_day(), so
    the wide UTC fetch bound itself can never clip or leak a bar across DST.
    """
    tf_param = "5Min" if timeframe == "5m" else "1Min"
    start_utc = f"{start.isoformat()}T07:00:00Z"
    end_utc = f"{(end + dt.timedelta(days=1)).isoformat()}T02:00:00Z"
    raw: list[dict] = []
    page_token = None
    pages = 0
    while True:
        params = {
            "timeframe": tf_param, "start": start_utc, "end": end_utc,
            "limit": 10000, "feed": "sip",
        }
        if page_token:
            params["page_token"] = page_token
        req = Request(f"{SPY_BARS_URL}?{urlencode(params)}",
                       headers={"APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret})
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                payload = json.loads(resp.read())
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            print(f"    HTTPError {exc.code} fetching {timeframe} {start}..{end}: {body}")
            return raw
        except URLError as exc:
            print(f"    URLError fetching {timeframe} {start}..{end}: {exc}")
            return raw
        raw.extend(payload.get("bars", []) or [])
        pages += 1
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        time.sleep(PAGE_SLEEP_S)
    return raw


def bucket_by_day(raw_bars: list[dict]) -> dict[dt.date, list[dict]]:
    by_day: dict[dt.date, list[dict]] = {}
    for b in raw_bars:
        et_naive = to_et_naive(b["t"])
        if not (WINDOW_START <= et_naive.time() < WINDOW_END):
            continue
        rec = {
            "t": et_naive.strftime("%Y-%m-%dT%H:%M:%S"),
            "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"],
        }
        by_day.setdefault(et_naive.date(), []).append(rec)
    for day, bars in by_day.items():
        bars.sort(key=lambda r: r["t"])
    return by_day


def write_day(timeframe: str, day: dt.date, bars: list[dict]) -> None:
    path = cache_path(timeframe, day)
    path.write_text(json.dumps({"bars": bars}), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true",
                     help="print month chunks + skip/fetch decision, no network calls")
    args = ap.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    chunks = list(month_chunks(START_DATE, END_DATE))
    print(f"target range: {START_DATE} .. {END_DATE} ({len(chunks)} month chunks)")

    if args.plan_only:
        for cs, ce in chunks:
            skip5 = chunk_fully_cached("5m", cs, ce)
            skip1 = chunk_fully_cached("1m", cs, ce)
            print(f"  {cs}..{ce}: 5m={'skip' if skip5 else 'fetch'} 1m={'skip' if skip1 else 'fetch'}")
        return 0

    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")

    totals = {"5m": {"days_written": 0, "days_skipped": 0, "chunks_skipped": 0, "chunks_fetched": 0},
              "1m": {"days_written": 0, "days_skipped": 0, "chunks_skipped": 0, "chunks_fetched": 0}}

    for timeframe in ("5m", "1m"):
        print(f"\n=== {timeframe} ===")
        for cs, ce in chunks:
            if chunk_fully_cached(timeframe, cs, ce):
                totals[timeframe]["chunks_skipped"] += 1
                # still count the already-present weekday files for the report
                totals[timeframe]["days_skipped"] += sum(1 for _ in weekdays_in_range(cs, ce))
                continue
            raw = fetch_range(creds, timeframe, cs, ce)
            totals[timeframe]["chunks_fetched"] += 1
            if not raw:
                print(f"  {cs}..{ce}: 0 bars returned")
                time.sleep(CHUNK_SLEEP_S)
                continue
            by_day = bucket_by_day(raw)
            written = 0
            skipped = 0
            for day, bars in sorted(by_day.items()):
                if cache_path(timeframe, day).exists():
                    skipped += 1
                    continue
                write_day(timeframe, day, bars)
                written += 1
            totals[timeframe]["days_written"] += written
            totals[timeframe]["days_skipped"] += skipped
            print(f"  {cs}..{ce}: {len(raw)} raw bars -> {len(by_day)} days "
                  f"({written} written, {skipped} already-present skipped)")
            time.sleep(CHUNK_SLEEP_S)

    print("\n=== SUMMARY ===")
    for tf, t in totals.items():
        print(f"{tf}: days_written={t['days_written']} days_skipped={t['days_skipped']} "
              f"chunks_fetched={t['chunks_fetched']} chunks_skipped={t['chunks_skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
