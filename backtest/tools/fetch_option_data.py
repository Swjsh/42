"""Fetch real OPRA option contract bars via Alpaca historical API.

Pre-fetches all contracts referenced by the v5 backtest + J's actual historical
trades, saves to CSV cache at `backtest/data/options/{symbol}.csv`.

The cache is the source of truth for `lib/option_pricing_real.py` — the simulator
never calls Alpaca at runtime; it reads the cached CSVs.

Usage:
    python tools/fetch_option_data.py             # fetch all
    python tools/fetch_option_data.py --check     # just verify what's cached

Output schema (per CSV):
    timestamp_et,open,high,low,close,volume,vwap,trade_count
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from _alpaca_creds import resolve_alpaca_creds

ALPACA_DATA_URL = "https://data.alpaca.markets/v1beta1/options/bars"

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "options"

# Contracts to fetch — derived from:
#   1. analysis/backtests/production_rules_v5_*/trades.csv (engine-fired trades)
#   2. journal/trades.csv historical entries (J's actual trades, for e2e validation)
CONTRACTS = [
    # V5 engine-fired trades
    ("2026-03-18", "SPY260318P00665000"),
    ("2026-03-18", "SPY260318P00662000"),
    ("2026-03-24", "SPY260324P00653000"),
    ("2026-03-26", "SPY260326P00653000"),
    ("2026-03-30", "SPY260330P00634000"),
    ("2026-04-07", "SPY260407P00652000"),
    ("2026-04-21", "SPY260421P00705000"),
    ("2026-04-23", "SPY260423P00708000"),
    ("2026-04-28", "SPY260428P00712000"),
    ("2026-04-29", "SPY260429P00709000"),
    ("2026-05-04", "SPY260504P00719000"),
    ("2026-04-23", "SPY260423P00704000"),  # v6/v7 second-leg strike
    # J's actual trades (for e2e validation)
    ("2026-04-29", "SPY260429P00710000"),
    ("2026-05-01", "SPY260501P00721000"),
    ("2026-05-04", "SPY260504P00721000"),
    ("2026-05-07", "SPY260507C00734000"),
    # J's manual trades NOT in our journal (recovered from broker screenshot)
    ("2026-05-05", "SPY260505P00722000"),
    ("2026-05-06", "SPY260506P00730000"),
    ("2026-05-07", "SPY260507C00737000"),
]


def fetch_contract_bars(symbol: str, trade_date: str, key: str, secret: str) -> list[dict]:
    """Fetch 5-min bars for a single 0DTE contract, scoped to RTH on trade_date.

    Returns list of dicts with normalized field names.
    """
    start_utc = f"{trade_date}T13:30:00Z"   # 09:30 ET
    end_utc = f"{trade_date}T20:30:00Z"     # 16:30 ET (a bit past close)
    params = {
        "symbols": symbol,
        "timeframe": "5Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 200,
    }
    url = f"{ALPACA_DATA_URL}?{urlencode(params)}"
    req = Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    })
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    bars = payload.get("bars", {}).get(symbol, []) or []
    rows = []
    for b in bars:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = ts_utc - dt.timedelta(hours=4)  # ET = UTC-4 during EDT
        rows.append({
            "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"],
            "high": b["h"],
            "low": b["l"],
            "close": b["c"],
            "volume": b["v"],
            "vwap": b.get("vw", b["c"]),
            "trade_count": b.get("n", 0),
        })
    return rows


def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.csv"


def write_cache(symbol: str, rows: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(symbol)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "timestamp_et", "open", "high", "low", "close",
            "volume", "vwap", "trade_count",
        ])
        w.writeheader()
        w.writerows(rows)


def already_cached(symbol: str) -> bool:
    p = cache_path(symbol)
    return p.exists() and p.stat().st_size > 100


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="just report cache status, no fetches")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even if cached")
    args = ap.parse_args(argv)

    cached = sum(1 for _, sym in CONTRACTS if already_cached(sym))
    print(f"Cache: {cached}/{len(CONTRACTS)} contracts cached at {CACHE_DIR}")

    if args.check:
        for date_str, symbol in CONTRACTS:
            status = "OK " if already_cached(symbol) else "MISS"
            path = cache_path(symbol)
            size = path.stat().st_size if path.exists() else 0
            print(f"  [{status}] {date_str}  {symbol}  {size}b")
        return 0

    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={creds.key[:4]}... source={creds.source}")

    fetched = 0
    failed = []
    for date_str, symbol in CONTRACTS:
        if already_cached(symbol) and not args.force:
            print(f"  skip {symbol}  (cached)")
            continue
        try:
            rows = fetch_contract_bars(symbol, date_str, creds.key, creds.secret)
            if not rows:
                print(f"  WARN {symbol}  empty response")
                failed.append((symbol, "empty"))
                continue
            write_cache(symbol, rows)
            print(f"  ok   {symbol}  {len(rows)} bars")
            fetched += 1
            time.sleep(0.25)   # gentle on rate limits
        except Exception as e:
            print(f"  FAIL {symbol}  {e}")
            failed.append((symbol, str(e)))

    print(f"\nFetched {fetched} new, {len(failed)} failed")
    if failed:
        for sym, why in failed:
            print(f"  - {sym}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
