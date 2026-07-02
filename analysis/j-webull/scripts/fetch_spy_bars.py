"""Fetch SPY 5m + daily bars 2021-06-01..2023-10-31 (Alpaca data REST, IEX feed, raw).

Keys loaded at runtime from project-root .mcp.json (never hardcoded).
Writes analysis/j-webull/cache/spy_5m_2021-06-01_2023-10-31.csv (+ daily).
Idempotent: skips fetch if cache file already exists and is non-trivial.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[3]
CACHE = REPO / "analysis" / "j-webull" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

START, END = "2021-06-01", "2023-10-31"
BASE = "https://data.alpaca.markets/v2/stocks/SPY/bars"


def load_keys() -> dict:
    mcp = json.loads((REPO / ".mcp.json").read_text())
    env = mcp["mcpServers"]["alpaca"]["env"]
    return {
        "APCA-API-KEY-ID": env["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"],
    }


def fetch(timeframe: str, out: Path) -> pd.DataFrame:
    if out.exists() and out.stat().st_size > 10_000:
        print(f"cache hit: {out.name}")
        return pd.read_csv(out)
    headers = load_keys()
    rows, token = [], None
    while True:
        params = {
            "timeframe": timeframe,
            "start": f"{START}T00:00:00Z",
            "end": f"{END}T23:59:59Z",
            "limit": 10000,
            "adjustment": "raw",
            "feed": "iex",
        }
        if token:
            params["page_token"] = token
        r = requests.get(BASE, headers=headers, params=params, timeout=60)
        if r.status_code != 200:
            print(f"HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr)
            sys.exit(1)
        j = r.json()
        rows.extend(j.get("bars") or [])
        token = j.get("next_page_token")
        print(f"  {timeframe}: {len(rows)} bars so far", flush=True)
        if not token:
            break
        time.sleep(0.35)  # stay polite on the shared-pool key (C10)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} bars)")
    return df


if __name__ == "__main__":
    m5 = fetch("5Min", CACHE / f"spy_5m_{START}_{END}.csv")
    d1 = fetch("1Day", CACHE / f"spy_daily_{START}_{END}.csv")
    print("5m bars:", len(m5), "daily bars:", len(d1))
