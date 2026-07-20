"""fetch_premium_stop_counterfactual_1min.py -- bounded 1-minute OPRA+SPY fetch for LEVER 2
(EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT counterfactual, automation/overnight/queue.md item filed
2026-07-20). Report-only evidence-accumulation fetch, no trading-path code touched.

Fetches EXACTLY the contracts + dates the 11 premium_stop episodes in
analysis/winning-trade-map/episodes-2026-07-13-to-2026-07-20.json traded, at 1-minute
resolution, so exit_manager_walk.walk_exit_manager can replay them under the REAL
RIBBON_RIDE exit shape (structure_stop + chandelier + -50% catastrophe cap) instead of
approximating from 5-min bars. Modeled directly on fetch_today_1min.py's fetch pattern
(same Alpaca REST endpoints, same to_et() DST-correct-for-EDT conversion), extended to:
  (a) multiple dates (07-15, 07-16, 07-20 -- the 3 sessions the 11 episodes span), and
  (b) feed="sip" for the SPY stock leg per task instruction (fetch_today_1min.py used
      "iex" for a same-day intraday fetch; alpaca_bars.py's fetch_spy_5m_sip is this
      codebase's established SIP convention for anything used to build/replay production
      decisions -- matched here). Options bars have no feed param on this endpoint
      (OPRA-sourced regardless, confirmed by fetch_today_1min.py precedent).

Output (backtest/data/highres/, date-suffixed, same schema as fetch_today_1min.py):
  SPY_1m_2026-07-15.csv, SPY_1m_2026-07-16.csv, SPY_1m_2026-07-20.csv
  SPY260715C00757000_1m_2026-07-15.csv, SPY260715C00754000_1m_2026-07-15.csv
  SPY260716P00751000_1m_2026-07-16.csv
  SPY260720C00748000_1m_2026-07-20.csv, SPY260720P00743000_1m_2026-07-20.csv

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

# date -> contracts traded that session among the 11 premium_stop episodes
DATE_CONTRACTS = {
    "2026-07-15": ["SPY260715C00757000", "SPY260715C00754000"],
    "2026-07-16": ["SPY260716P00751000"],
    "2026-07-20": ["SPY260720C00748000", "SPY260720P00743000"],
}


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


def fetch_spy_1min_sip(date_str: str, key: str, secret: str) -> list[dict]:
    start_utc = f"{date_str}T13:00:00Z"   # 09:00 ET premarket pad
    end_utc = f"{date_str}T20:30:00Z"     # 16:30 ET
    payload = alpaca_get(STOCK_URL, {
        "timeframe": "1Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 1000,
        "feed": "sip",
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
    return ts_utc - dt.timedelta(hours=4)  # matches existing cache convention (fixed -04:00,
    # correct for these EDT-season dates -- see lib/et_frame.py: -04:00 is the TRUE ET offset
    # for July, so wall-v1 and et-v2 agree here; no DST correction needed this run.


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

    summary = {}
    for date_str, contracts in DATE_CONTRACTS.items():
        spy_bars = fetch_spy_1min_sip(date_str, creds.key, creds.secret)
        spy_rows = [{
            "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "vwap": b.get("vw", b["c"]),
        } for b in spy_bars]
        if spy_rows:
            spy_path = HIRES_DIR / f"SPY_1m_{date_str}.csv"
            write_csv(spy_path, spy_rows,
                      ["timestamp_et", "open", "high", "low", "close", "volume", "vwap"])
            print(f"  SPY  {date_str}: {len(spy_rows)} 1-min SIP bars -> {spy_path.name}")
        else:
            print(f"  SPY  {date_str}: EMPTY -- 1-min SIP stock bars NOT available")
        summary[f"SPY_{date_str}"] = len(spy_rows)
        time.sleep(0.3)

        for sym in contracts:
            opt_bars = fetch_opt_1min(sym, date_str, creds.key, creds.secret)
            opt_rows = [{
                "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
                "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
                "volume": b["v"], "vwap": b.get("vw", b["c"]), "trade_count": b.get("n", 0),
            } for b in opt_bars]
            if opt_rows:
                opt_path = HIRES_DIR / f"{sym}_1m_{date_str}.csv"
                write_csv(opt_path, opt_rows,
                          ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"])
                print(f"  OPT  {sym}: {len(opt_rows)} 1-min bars -> {opt_path.name}")
            else:
                print(f"  OPT  {sym}: EMPTY -- not cached, replay falls back for this contract")
            summary[sym] = len(opt_rows)
            time.sleep(0.3)

    print("\nSummary:")
    for k, n in summary.items():
        print(f"  {k}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
