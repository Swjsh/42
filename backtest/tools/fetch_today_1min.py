"""fetch_today_1min.py -- bounded 1-minute OPRA fetch for GOAL-REPLAY-TODAY-GREEN iteration 3.

Closes the exit-layer data-resolution gap iteration 2 diagnosed: only 5-min OPRA/SPY
bars were cached for 2026-07-17, but live trades on a ~1-minute clock. This script
fetches EXACTLY the contracts actually traded today (from journal/trades.csv) at
1-minute resolution, plus 1-minute SPY bars (simulate_trade_real's exit loop walks
spy_df and opt_df in LOCKSTEP index-by-index -- feeding it 1-min option bars while
spy_df stays 5-min would desync the walk, so both must move to 1-min together).

NOT a general-purpose backfill tool (see expand_opra_cache.py for that). Single day,
7 contracts, modeled on the existing backtest/tools/fetch_high_res.py pattern/schema.

Output (backtest/data/highres/, today-specific names):
  SPY_1m_2026-07-17.csv
  SPY260717P00741000_1m_2026-07-17.csv
  SPY260717P00742000_1m_2026-07-17.csv
  SPY260717P00743000_1m_2026-07-17.csv
  SPY260717P00744000_1m_2026-07-17.csv
  SPY260717P00745000_1m_2026-07-17.csv
  SPY260717P00746000_1m_2026-07-17.csv
  SPY260717C00746000_1m_2026-07-17.csv  (J-called 746C -- out of grading scope, cached
                                          anyway since the fetch is already in flight)

Cost: 8 REST calls, $0 (existing paper-key market-data entitlement). Run once.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import masked, resolve_alpaca_creds

STOCK_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
OPT_URL = "https://data.alpaca.markets/v1beta1/options/bars"

ROOT = Path(__file__).resolve().parents[1]
HIRES_DIR = ROOT / "data" / "highres"

DATE_STR = "2026-07-17"
CONTRACTS = [
    "SPY260717P00741000",
    "SPY260717P00742000",
    "SPY260717P00743000",
    "SPY260717P00744000",
    "SPY260717P00745000",
    "SPY260717P00746000",
    "SPY260717C00746000",  # J-called, out of grading scope, cached for completeness
]


def alpaca_get(url: str, params: dict, key: str, secret: str) -> dict:
    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    })
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code} for {url}: {body}")
        return {}


def fetch_spy_1min(date_str: str, key: str, secret: str) -> list[dict]:
    start_utc = f"{date_str}T13:00:00Z"   # 09:00 ET (a little premarket pad)
    end_utc = f"{date_str}T20:30:00Z"     # 16:30 ET
    payload = alpaca_get(STOCK_URL, {
        "timeframe": "1Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 1000,
        "feed": "iex",
    }, key, secret)
    return payload.get("bars", []) or []


def fetch_opt_1min(symbol: str, date_str: str, key: str, secret: str) -> list[dict]:
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


def to_et(ts_iso: str) -> dt.datetime:
    ts_utc = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    return ts_utc - dt.timedelta(hours=4)  # matches existing cache convention (fixed -04:00)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")
    HIRES_DIR.mkdir(parents=True, exist_ok=True)

    # SPY 1-min (fetched once, shared across all contracts' exit walks)
    spy_bars = fetch_spy_1min(DATE_STR, creds.key, creds.secret)
    spy_rows = [{
        "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
        "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
        "volume": b["v"], "vwap": b.get("vw", b["c"]),
    } for b in spy_bars]
    if spy_rows:
        spy_path = HIRES_DIR / f"SPY_1m_{DATE_STR}.csv"
        write_csv(spy_path, spy_rows,
                  ["timestamp_et", "open", "high", "low", "close", "volume", "vwap"])
        print(f"  SPY  {DATE_STR}: {len(spy_rows)} 1-min bars -> {spy_path.name}")
    else:
        print(f"  SPY  {DATE_STR}: EMPTY -- 1-min stock bars NOT available, exit walk cannot use 1-min")
    time.sleep(0.3)

    results = {}
    for sym in CONTRACTS:
        opt_bars = fetch_opt_1min(sym, DATE_STR, creds.key, creds.secret)
        opt_rows = [{
            "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "vwap": b.get("vw", b["c"]), "trade_count": b.get("n", 0),
        } for b in opt_bars]
        if opt_rows:
            opt_path = HIRES_DIR / f"{sym}_1m_{DATE_STR}.csv"
            write_csv(opt_path, opt_rows,
                      ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"])
            print(f"  OPT  {sym}: {len(opt_rows)} 1-min bars -> {opt_path.name}")
            results[sym] = len(opt_rows)
        else:
            print(f"  OPT  {sym}: EMPTY -- not cached, exit walk falls back to 5-min for this contract")
            results[sym] = 0
        time.sleep(0.3)

    print("\nSummary:")
    print(f"  SPY 1-min bars: {len(spy_rows)}")
    for sym, n in results.items():
        print(f"  {sym}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
