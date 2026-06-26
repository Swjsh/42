"""Fetch 1-min SPY bars + 1-min option bars for J's 3 winning trade days.

Lets us see what J was looking at down to the 3-min chart (1-min bars
resampled to 3-min, or stay at 1-min for max fidelity).

Output: backtest/data/highres/SPY_1m_{date}.csv and {option_symbol}_1m_{date}.csv
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from _alpaca_creds import masked, resolve_alpaca_creds

STOCK_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
OPT_URL = "https://data.alpaca.markets/v1beta1/options/bars"

ROOT = Path(__file__).resolve().parents[1]
HIRES_DIR = ROOT / "data" / "highres"

# (date, option_symbol, J_entry_time, J_exit_times)
WIN_DAYS = [
    ("2026-04-29", "SPY260429P00710000"),
    ("2026-05-01", "SPY260501P00721000"),
    ("2026-05-04", "SPY260504P00721000"),
]


def alpaca_get(url, params, key, secret):
    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_spy_1min(date_str, key, secret):
    start_utc = f"{date_str}T13:00:00Z"   # 09:00 ET (premarket too)
    end_utc = f"{date_str}T20:30:00Z"     # 16:30 ET
    payload = alpaca_get(STOCK_URL, {
        "timeframe": "1Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 1000,
        "feed": "iex",  # free tier
    }, key, secret)
    return payload.get("bars", []) or []


def fetch_opt_1min(symbol, date_str, key, secret):
    start_utc = f"{date_str}T13:30:00Z"
    end_utc = f"{date_str}T20:30:00Z"
    payload = alpaca_get(OPT_URL, {
        "symbols": symbol,
        "timeframe": "1Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 1000,
    }, key, secret)
    return payload.get("bars", {}).get(symbol, []) or []


def to_et(ts_iso):
    ts_utc = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    return ts_utc - dt.timedelta(hours=4)


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    # Resolve creds lazily on the fetch path (never at import time).
    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")

    HIRES_DIR.mkdir(parents=True, exist_ok=True)
    for date_str, opt_sym in WIN_DAYS:
        # SPY
        spy_bars = fetch_spy_1min(date_str, creds.key, creds.secret)
        spy_rows = [{
            "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "vwap": b.get("vw", b["c"]),
        } for b in spy_bars]
        if spy_rows:
            spy_path = HIRES_DIR / f"SPY_1m_{date_str}.csv"
            write_csv(spy_path, spy_rows,
                      ["timestamp_et", "open", "high", "low", "close", "volume", "vwap"])
            print(f"  SPY  {date_str}: {len(spy_rows)} 1-min bars -> {spy_path.name}")
        else:
            print(f"  SPY  {date_str}: EMPTY")
        time.sleep(0.3)

        # Option
        opt_bars = fetch_opt_1min(opt_sym, date_str, creds.key, creds.secret)
        opt_rows = [{
            "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "vwap": b.get("vw", b["c"]), "trade_count": b.get("n", 0),
        } for b in opt_bars]
        if opt_rows:
            opt_path = HIRES_DIR / f"{opt_sym}_1m_{date_str}.csv"
            write_csv(opt_path, opt_rows,
                      ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"])
            print(f"  OPT  {opt_sym}: {len(opt_rows)} 1-min bars -> {opt_path.name}")
        else:
            print(f"  OPT  {opt_sym}: EMPTY")
        time.sleep(0.3)


if __name__ == "__main__":
    main()
