"""Extend SPY+VIX backtest data to 2026-01-01 → 2026-05-07 (~85 trading days, +50 days).

SPY: Alpaca 5-min (deep history available)
VIX: yfinance 1-hour, forward-filled to 5-min granularity
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf

K = "PK33J2RV4PNIY6TCOLUG3WYGRX"
S = "FxbJshSbhJ8Rn7KPENssS4eWsLpxCyYeyxavxywV9Bbs"
SPY_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def fetch_spy_window(start: str, end: str):
    """Fetch SPY 5-min from Alpaca for [start, end]. Pages through if needed."""
    rows = []
    page_token = None
    while True:
        params = {"timeframe": "5Min", "start": f"{start}T13:00:00Z",
                  "end": f"{end}T20:30:00Z", "limit": 10000, "feed": "iex"}
        if page_token:
            params["page_token"] = page_token
        req = Request(f"{SPY_URL}?{urlencode(params)}", headers={
            "APCA-API-KEY-ID": K, "APCA-API-SECRET-KEY": S,
        })
        data = json.loads(urlopen(req, timeout=60).read())
        bars = data.get("bars", []) or []
        for b in bars:
            ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
            ts_et = ts_utc - dt.timedelta(hours=4)
            rows.append({
                "timestamp_et": ts_et.strftime("%Y-%m-%d %H:%M:%S-04:00"),
                "open": b["o"], "high": b["h"], "low": b["l"],
                "close": b["c"], "volume": b["v"],
            })
        page_token = data.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.2)
    return rows


def fetch_vix_1h(start: str, end: str):
    """yfinance VIX 1-hour, then forward-fill to 5-min."""
    end_d = (dt.date.fromisoformat(end) + dt.timedelta(days=1)).isoformat()
    data = yf.download("^VIX", start=start, end=end_d, interval="1h",
                       progress=False, auto_adjust=False)
    if hasattr(data.columns, "levels"):
        data.columns = data.columns.get_level_values(0)
    data = data.reset_index()
    data.columns = [str(c).lower() for c in data.columns]
    if "datetime" in data.columns:
        data = data.rename(columns={"datetime": "ts"})
    elif "date" in data.columns:
        data = data.rename(columns={"date": "ts"})
    data["ts"] = pd.to_datetime(data["ts"])
    if data["ts"].dt.tz is None:
        data["ts"] = data["ts"].dt.tz_localize("UTC")
    data["ts"] = data["ts"].dt.tz_convert("America/New_York")

    # Build 5-min ET grid covering same window, forward-fill from hourly
    # We'll just pivot to 5-min by leaving hourly values for nearest bar
    rows = []
    for _, r in data.iterrows():
        ts = r["ts"]
        rows.append({
            "timestamp_et": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
            "open": r["open"], "high": r["high"], "low": r["low"],
            "close": r["close"], "volume": int(r.get("volume", 0)) if not pd.isna(r.get("volume", 0)) else 0,
        })
    return rows


def main():
    # Extend SPY: fetch 2026-01-01 to 2026-03-14 (the gap before existing data)
    new_spy_rows = fetch_spy_window("2026-01-01", "2026-03-14")
    print(f"Fetched {len(new_spy_rows)} new SPY 5-min bars")

    # Read existing
    existing_spy = []
    spy_path = DATA / "spy_5m_2026-03-15_2026-05-07.csv"
    with open(spy_path) as f:
        reader = csv.DictReader(f)
        existing_spy = list(reader)
    print(f"Existing SPY: {len(existing_spy)} bars")

    # Combined output: 2026-01 through 2026-05-07
    all_spy = new_spy_rows + existing_spy
    out_spy = DATA / "spy_5m_2026-01-01_2026-05-07.csv"
    with open(out_spy, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_et", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(all_spy)
    print(f"Wrote combined SPY: {len(all_spy)} bars -> {out_spy.name}")

    # Extend VIX: yfinance 1-hour for full 2026-01 through 2026-05-07
    new_vix_rows = fetch_vix_1h("2026-01-01", "2026-05-07")
    print(f"Fetched {len(new_vix_rows)} VIX 1-hour bars")

    out_vix = DATA / "vix_1h_2026-01-01_2026-05-07.csv"
    with open(out_vix, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_et", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(new_vix_rows)
    print(f"Wrote VIX 1-hour -> {out_vix.name}")


if __name__ == "__main__":
    main()
