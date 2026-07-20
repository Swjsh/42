"""fetch_spy_1min_sight_staleness.py -- one-off fetch of 2026-07-14 1-min SIP SPY bars
for the DECISION-ROW-SPY-STALENESS investigation (automation/overnight/queue.md, filed
2026-07-20 ~18:30 ET). Reuses the exact fetch shape already established by
backtest/tools/fetch_premium_stop_counterfactual_1min.py (same STOCK_URL, same to_et()
fixed -04:00 EDT convention, same output schema) -- 07-15/16/17/20 are already cached at
backtest/data/highres/SPY_1m_<date>.csv from that prior run; only 07-14 is missing.

Report-only. No trading-path file touched. $0 (existing paper-key market-data entitlement).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import masked, resolve_alpaca_creds  # noqa: E402

STOCK_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
ROOT = Path(__file__).resolve().parents[1]
HIRES_DIR = ROOT / "data" / "highres"
DATES = ["2026-07-14"]


def alpaca_get(url: str, params: dict, key: str, secret: str) -> dict:
    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code} for {url}: {body}")
        return {}


def fetch_spy_1min_sip(date_str: str, key: str, secret: str) -> list[dict]:
    start_utc = f"{date_str}T13:00:00Z"
    end_utc = f"{date_str}T20:30:00Z"
    payload = alpaca_get(STOCK_URL, {
        "timeframe": "1Min", "start": start_utc, "end": end_utc,
        "limit": 1000, "feed": "sip",
    }, key, secret)
    return payload.get("bars", []) or []


def to_et(ts_iso: str) -> dt.datetime:
    ts_utc = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    return ts_utc - dt.timedelta(hours=4)


def main() -> int:
    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")
    HIRES_DIR.mkdir(parents=True, exist_ok=True)
    for date_str in DATES:
        out = HIRES_DIR / f"SPY_1m_{date_str}.csv"
        if out.exists():
            print(f"  SPY {date_str}: already cached -> {out.name}")
            continue
        bars = fetch_spy_1min_sip(date_str, creds.key, creds.secret)
        rows = [{
            "timestamp_et": to_et(b["t"]).strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "vwap": b.get("vw", b["c"]),
        } for b in bars]
        if rows:
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp_et", "open", "high", "low",
                                                   "close", "volume", "vwap"])
                w.writeheader()
                w.writerows(rows)
            print(f"  SPY {date_str}: {len(rows)} 1-min SIP bars -> {out.name}")
        else:
            print(f"  SPY {date_str}: EMPTY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
