"""One-off probe: binary-search Alpaca's true SPY 0DTE option-bar availability
floor between 2024-01-02 and 2024-02-15.

Established (verified this session via Alpaca MCP round-trips on the existing
paper key): zero option bars on 2024-01-05 and 2024-01-12; real 5-min OHLCV
present on 2024-02-01, 2024-03-01, 2024-05-01, 2024-07-01, 2024-09-03,
2024-12-02. This script narrows the floor date within (2024-01-12, 2024-02-01].

For each candidate date: fetch the SPY daily close (stocks/bars, feed=iex, same
feed extend_data_v2.py uses), build 0DTE OCC symbols at ATM +/- 2 strikes
(call+put), and query v1beta1/options/bars. A date "has data" if ANY of those
6 contracts returns >=1 bar.

Usage:
    python _probe_opra_floor.py 2024-01-16 2024-01-18 2024-01-22 2024-01-24 ...
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from _alpaca_creds import resolve_alpaca_creds

STOCK_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
OPT_URL = "https://data.alpaca.markets/v1beta1/options/bars"


def daily_close(date: dt.date, key: str, secret: str) -> float | None:
    params = {
        "timeframe": "1Day",
        "start": f"{date.isoformat()}T00:00:00Z",
        "end": f"{(date + dt.timedelta(days=1)).isoformat()}T00:00:00Z",
        "limit": 5,
        "feed": "iex",
    }
    url = f"{STOCK_URL}?{urlencode(params)}"
    req = Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    try:
        data = json.loads(urlopen(req, timeout=30).read())
    except Exception as exc:
        print(f"  [stock fetch error] {date}: {exc}")
        return None
    bars = data.get("bars", []) or []
    if not bars:
        return None
    return float(bars[-1]["c"])


def option_symbol(trade_date: dt.date, strike: int, side: str) -> str:
    yymmdd = trade_date.strftime("%y%m%d")
    return f"SPY{yymmdd}{side}{int(round(strike)) * 1000:08d}"


def probe_date(date: dt.date, key: str, secret: str) -> dict:
    close = daily_close(date, key, secret)
    if close is None:
        return {"date": date.isoformat(), "close": None, "has_data": False, "detail": "no SPY daily bar"}
    atm = int(round(close))
    symbols = []
    for offset in range(-2, 3):
        for side in ("C", "P"):
            symbols.append(option_symbol(date, atm + offset, side))
    params = {
        "symbols": ",".join(symbols),
        "timeframe": "5Min",
        "start": f"{date.isoformat()}T13:30:00Z",
        "end": f"{date.isoformat()}T21:00:00Z",
        "limit": 2000,
    }
    url = f"{OPT_URL}?{urlencode(params)}"
    req = Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    try:
        payload = json.loads(urlopen(req, timeout=30).read())
    except Exception as exc:
        return {"date": date.isoformat(), "close": close, "has_data": False, "detail": f"opt fetch error: {exc}"}
    bars_map = payload.get("bars", {}) or {}
    total_bars = sum(len(v) for v in bars_map.values())
    contracts_with_data = [s for s, v in bars_map.items() if v]
    return {
        "date": date.isoformat(),
        "close": close,
        "atm": atm,
        "has_data": total_bars > 0,
        "total_bars": total_bars,
        "contracts_with_data": contracts_with_data,
    }


def main() -> int:
    creds = resolve_alpaca_creds()
    dates = [dt.date.fromisoformat(d) for d in sys.argv[1:]]
    if not dates:
        print("usage: _probe_opra_floor.py YYYY-MM-DD [YYYY-MM-DD ...]")
        return 2
    for d in dates:
        result = probe_date(d, creds.key, creds.secret)
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
