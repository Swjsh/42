"""One-off data fetch for late-entry-ceiling-review.json (read-only, no order paths touched).
Pulls REAL Alpaca OPRA 1-min option bars + REAL SPY 1-min/5-min stock bars for the two
identified 15:00-15:35 SKIP_LATE_ENTRY block events (2026-07-06, 2026-07-13), so the
counterfactual replay uses genuine market data, not synthetic bars.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
import fleet_broker as fb  # noqa: E402

OUT = REPO / "analysis" / "recommendations" / "_late_entry_raw_bars.json"


def _hhmm_to_utc(hh, mm):
    utc_hh = (int(hh) + 4) % 24
    return f"{utc_hh:02d}:{mm}:00Z"


def fetch_option_bars(creds, symbol, date_et, start_hhmm="15:00", end_hhmm="16:10"):
    sh, sm = start_hhmm.split(":")
    eh, em = end_hhmm.split(":")
    start = f"{date_et}T{_hhmm_to_utc(sh, sm)}"
    end = f"{date_et}T{_hhmm_to_utc(eh, em)}"
    url = (f"https://data.alpaca.markets/v1beta1/options/bars?symbols={symbol}"
           f"&timeframe=1Min&start={start}&end={end}&limit=1000")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        print(f"OPTION FETCH ERROR {symbol}: {exc}", file=sys.stderr)
        return []
    return (data.get("bars") or {}).get(symbol) or []


def fetch_stock_bars(creds, date_et, timeframe="1Min", start_hhmm="15:00", end_hhmm="16:10"):
    sh, sm = start_hhmm.split(":")
    eh, em = end_hhmm.split(":")
    start = f"{date_et}T{_hhmm_to_utc(sh, sm)}"
    end = f"{date_et}T{_hhmm_to_utc(eh, em)}"
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe={timeframe}"
           f"&start={start}&end={end}&limit=1000&feed=iex")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        print(f"STOCK FETCH ERROR {date_et} {timeframe}: {exc}", file=sys.stderr)
        return []
    return data.get("bars") or []


def main():
    creds_all = fb.load_creds()
    creds = creds_all.get("safe-2") or creds_all.get("safe-1")
    out = {}

    # --- 2026-07-13 event: BEARISH_REJECTION, safe 749P (ATM), bold 746P (OTM-3) ---
    out["2026-07-13_safe_749P"] = fetch_option_bars(creds, "SPY260713P00749000", "2026-07-13",
                                                      "15:15", "16:10")
    out["2026-07-13_bold_746P"] = fetch_option_bars(creds, "SPY260713P00746000", "2026-07-13",
                                                      "15:15", "16:10")
    out["2026-07-13_spy_1min"] = fetch_stock_bars(creds, "2026-07-13", "1Min", "15:10", "16:10")
    out["2026-07-13_spy_5min"] = fetch_stock_bars(creds, "2026-07-13", "5Min", "14:45", "16:10")

    # --- 2026-07-06 event: BULLISH_RECLAIM, fleet arms all 755C @ ELITE, premium ~0.04 ---
    out["2026-07-06_755C"] = fetch_option_bars(creds, "SPY260706C00755000", "2026-07-06",
                                                "15:20", "16:10")
    out["2026-07-06_spy_1min"] = fetch_stock_bars(creds, "2026-07-06", "1Min", "15:15", "16:10")
    out["2026-07-06_spy_5min"] = fetch_stock_bars(creds, "2026-07-06", "5Min", "14:35", "16:10")

    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for k, v in out.items():
        print(k, "->", len(v) if isinstance(v, list) else "n/a", "bars")


if __name__ == "__main__":
    main()
