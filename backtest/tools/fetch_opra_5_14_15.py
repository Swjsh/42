"""Fetch OPRA option bars for 2026-05-14 and 2026-05-15 (missing from main cache).

Main cache (expand_opra_cache.py) ran start=2025-01-01 end=2026-05-12 and is complete.
This script patches in the two missing trading days so the Stage 4 grinder can fire on
5/14 and 5/15 J-anchor days.

Coverage: ATM ± 5 strikes for both C and P sides.
  2026-05-14: SPY close 748.08 → ATM=748 → strikes 743-753
  2026-05-15: SPY close 739.08 → ATM=739 → strikes 734-744

Run:
    python tools/fetch_opra_5_14_15.py
"""

from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import csv
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
OPTIONS_DIR = REPO / "data" / "options"
OPTIONS_DIR.mkdir(parents=True, exist_ok=True)

ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "PK33J2RV4PNIY6TCOLUG3WYGRX")
ALPACA_SECRET = os.environ.get(
    "ALPACA_API_SECRET", "FxbJshSbhJ8Rn7KPENssS4eWsLpxCyYeyxavxywV9Bbs"
)
ALPACA_OPTIONS_URL = "https://data.alpaca.markets/v1beta1/options/bars"
SLEEP = 0.31  # ~190 req/min — safe under Alpaca free-tier 200 req/min


def option_symbol(trade_date: dt.date, strike: int, side: str) -> str:
    yymmdd = trade_date.strftime("%y%m%d")
    s = side.upper()
    return f"SPY{yymmdd}{s}{int(round(strike)) * 1000:08d}"


def fetch_contract_bars(symbol: str, trade_date: dt.date) -> list[dict]:
    """Fetch 5-minute OHLCV bars for a 0DTE contract on trade_date.

    Matches expand_opra_cache.py exactly — no feed/currency params, UTC window,
    timestamp converted to ET-offset string (-04:00 always for consistency).
    """
    start_utc = f"{trade_date.isoformat()}T13:30:00Z"
    end_utc   = f"{trade_date.isoformat()}T21:00:00Z"

    params = {
        "symbols": symbol,
        "timeframe": "5Min",
        "start": start_utc,
        "end":   end_utc,
        "limit": 200,
    }
    url = f"{ALPACA_OPTIONS_URL}?{urlencode(params)}"
    req = Request(url, headers={
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    })
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    bars_raw = data.get("bars", {}).get(symbol, []) or []
    rows = []
    for b in bars_raw:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = ts_utc - dt.timedelta(hours=4)  # always -04:00 to match cache schema
        rows.append({
            "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open":  b["o"],
            "high":  b["h"],
            "low":   b["l"],
            "close": b["c"],
            "volume": b["v"],
            "vwap": b.get("vw", b["c"]),
            "trade_count": b.get("n", 0),
        })
    return rows


def write_cache(symbol: str, rows: list[dict]) -> None:
    path = OPTIONS_DIR / f"{symbol}.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp_et", "open", "high", "low", "close",
            "volume", "vwap", "trade_count",
        ])
        writer.writeheader()
        writer.writerows(rows)


def write_empty_sentinel(symbol: str) -> None:
    (OPTIONS_DIR / f"{symbol}.csv.empty").touch()


def build_targets() -> list[tuple[dt.date, str]]:
    days = [
        (dt.date(2026, 5, 14), 748),  # SPY close 748.08
        (dt.date(2026, 5, 15), 739),  # SPY close 739.08
    ]
    targets: list[tuple[dt.date, str]] = []
    strikes_half = 5
    for trade_date, atm in days:
        for offset in range(-strikes_half, strikes_half + 1):
            strike = atm + offset
            for side in ("C", "P"):
                symbol = option_symbol(trade_date, strike, side)
                csv_path = OPTIONS_DIR / f"{symbol}.csv"
                sentinel = OPTIONS_DIR / f"{symbol}.csv.empty"
                if csv_path.exists() and csv_path.stat().st_size > 100:
                    logger.info("SKIP (cached) %s", symbol)
                    continue
                if sentinel.exists():
                    logger.info("SKIP (empty sentinel) %s", symbol)
                    continue
                targets.append((trade_date, symbol))
    return targets


def main() -> None:
    targets = build_targets()
    logger.info("Fetching %d contracts for 2026-05-14 + 2026-05-15", len(targets))
    for i, (trade_date, symbol) in enumerate(targets, 1):
        attempt = 0
        while True:
            attempt += 1
            try:
                rows = fetch_contract_bars(symbol, trade_date)
                if rows:
                    write_cache(symbol, rows)
                    logger.info("[%d/%d] OK   %s  %d bars", i, len(targets), symbol, len(rows))
                else:
                    write_empty_sentinel(symbol)
                    logger.info("[%d/%d] EMPTY %s", i, len(targets), symbol)
                break
            except HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:200]
                if e.code == 429 and attempt <= 5:
                    backoff = min(60, 2 ** attempt)
                    logger.warning("429 %s — backoff %ds", symbol, backoff)
                    time.sleep(backoff)
                    continue
                logger.error("HTTPError %d %s: %s", e.code, symbol, body)
                break
            except (URLError, TimeoutError) as e:
                if attempt <= 3:
                    time.sleep(2 ** attempt)
                    continue
                logger.error("URLError %s: %s", symbol, e)
                break
            except Exception as e:  # noqa: BLE001
                logger.error("Error %s: %s", symbol, e)
                break
        time.sleep(SLEEP)

    # Verify
    found_14 = len(list(OPTIONS_DIR.glob("SPY260514*.csv")))
    found_15 = len(list(OPTIONS_DIR.glob("SPY260515*.csv")))
    logger.info("Done. 5/14 files: %d  5/15 files: %d", found_14, found_15)


if __name__ == "__main__":
    main()
