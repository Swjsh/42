"""Extend SPY + VIX 5-min data to an arbitrary start date.

SPY: Alpaca IEX feed (multi-year history).
VIX: yfinance 1-hour, then forward-filled to 5-min in `_align_vix_to_spy`.

Usage:
    python tools/extend_data_v2.py --start 2025-06-01 --end 2026-05-07
    python tools/extend_data_v2.py --start 2025-01-01 --end 2026-05-07 --no-vix

Writes:
    data/spy_5m_{start}_{end}.csv
    data/vix_5m_{start}_{end}.csv  (5-min, forward-filled from 1-h)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import time
from pathlib import Path
from typing import Iterator
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from _alpaca_creds import masked, resolve_alpaca_creds

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

SPY_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"


def _month_windows(start: dt.date, end: dt.date) -> Iterator[tuple[dt.date, dt.date]]:
    """Yield (start, end) pairs broken into ~30-day chunks (Alpaca paging is fine
    but smaller windows are easier to retry on failure)."""
    cur = start
    while cur <= end:
        nxt = min(cur + dt.timedelta(days=30), end)
        yield cur, nxt
        cur = nxt + dt.timedelta(days=1)


def fetch_spy_window(
    start_date: dt.date, end_date: dt.date, key: str, secret: str
) -> list[dict]:
    """Fetch SPY 5-min from Alpaca for [start, end]. Pages through if needed."""
    rows: list[dict] = []
    page_token: str | None = None
    while True:
        params = {
            "timeframe": "5Min",
            "start": f"{start_date.isoformat()}T13:00:00Z",
            "end": f"{end_date.isoformat()}T20:30:00Z",
            "limit": 10000,
            "feed": "iex",
        }
        if page_token:
            params["page_token"] = page_token
        url = f"{SPY_URL}?{urlencode(params)}"
        req = Request(
            url,
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
            },
        )
        try:
            data = json.loads(urlopen(req, timeout=60).read())
        except Exception as exc:
            logger.warning("SPY fetch failed for %s..%s: %s", start_date, end_date, exc)
            return rows
        bars = data.get("bars", []) or []
        for b in bars:
            ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
            ts_et = ts_utc - dt.timedelta(hours=4)
            rows.append(
                {
                    "timestamp_et": ts_et.strftime("%Y-%m-%d %H:%M:%S-04:00"),
                    "open": b["o"],
                    "high": b["h"],
                    "low": b["l"],
                    "close": b["c"],
                    "volume": b["v"],
                }
            )
        page_token = data.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.15)
    return rows


def fetch_vix_5m_via_1h(start_date: dt.date, end_date: dt.date) -> list[dict]:
    """yfinance VIX hourly, then up-sample to 5-min via forward-fill.

    yfinance's 5m endpoint is limited to ~60 days. The 1h endpoint goes back
    multiple years. The orchestrator's `_align_vix_to_spy` does forward-fill
    anyway, so 1-hour VIX granularity is acceptable.
    """
    import yfinance as yf

    end_d = end_date + dt.timedelta(days=1)
    df = yf.download(
        "^VIX",
        start=start_date.isoformat(),
        end=end_d.isoformat(),
        interval="1h",
        progress=False,
        auto_adjust=False,
    )
    if df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    if "datetime" in df.columns:
        df = df.rename(columns={"datetime": "ts"})
    elif "date" in df.columns:
        df = df.rename(columns={"date": "ts"})
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    df["ts"] = df["ts"].dt.tz_convert("America/New_York")
    rows: list[dict] = []
    for _, r in df.iterrows():
        ts = r["ts"]
        rows.append(
            {
                "timestamp_et": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r.get("volume", 0)) if not pd.isna(r.get("volume", 0)) else 0,
            }
        )
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        logger.warning("no rows to write to %s", path)
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    logger.info("wrote %d rows -> %s", len(rows), path.name)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    ap.add_argument("--no-vix", action="store_true", help="Skip VIX fetch")
    ap.add_argument("--no-spy", action="store_true", help="Skip SPY fetch")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if start > end:
        ap.error("start must be <= end")

    if not args.no_spy:
        # Resolve creds lazily on the fetch path — skipped entirely with --no-spy.
        creds = resolve_alpaca_creds()
        logger.info("Alpaca creds: key=%s source=%s", masked(creds.key), creds.source)
        all_spy: list[dict] = []
        for w_start, w_end in _month_windows(start, end):
            chunk = fetch_spy_window(w_start, w_end, creds.key, creds.secret)
            logger.info("SPY %s..%s -> %d bars", w_start, w_end, len(chunk))
            all_spy.extend(chunk)
            time.sleep(0.2)
        # Deduplicate by timestamp + sort
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in all_spy:
            ts = r["timestamp_et"]
            if ts in seen:
                continue
            seen.add(ts)
            deduped.append(r)
        deduped.sort(key=lambda r: r["timestamp_et"])
        spy_path = DATA / f"spy_5m_{start}_{end}.csv"
        write_csv(deduped, spy_path)

    if not args.no_vix:
        vix_rows = fetch_vix_5m_via_1h(start, end)
        vix_path = DATA / f"vix_5m_{start}_{end}.csv"
        write_csv(vix_rows, vix_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
