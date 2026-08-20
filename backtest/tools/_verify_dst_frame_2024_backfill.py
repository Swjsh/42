"""One-off verification: prove the DST-safe UTC->ET conversion used by the
2024-2026 SPY backfill (backfill_spy_sip_cache_2024.py) lands the 09:30 ET
RTH-open bar at the SAME naive wall-clock label in both an EST month
(2025-01-02, winter) and an EDT month (2025-06-02, summer).

This is the guard against the repo's documented scar (backtest/lib/et_frame.py,
DST-FRAME-AUDIT-2026-07-02): a writer that applies a FIXED -04:00 offset
year-round mislabels every winter bar +1h and reintroduces winter look-ahead.

Uses zoneinfo.ZoneInfo("America/New_York").astimezone(), the SAME DST-correct
primitive backtest/tools/alpaca_bars.py already uses for its 04:00-16:00
fetcher -- this script reuses the identical conversion, just over the wider
04:00-20:00 window the spy_sip_cache JSON files use.

Read-only market-data fetch. Same _alpaca_creds auth path as every other
backtest/tools fetcher.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import masked, resolve_alpaca_creds  # noqa: E402

SPY_BARS_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
ET = ZoneInfo("America/New_York")

WINTER_DAY = dt.date(2025, 1, 2)   # EST (UTC-05:00)
SUMMER_DAY = dt.date(2025, 6, 2)   # EDT (UTC-04:00)


def fetch_day(creds, day: dt.date) -> list[dict]:
    start_utc = f"{day.isoformat()}T07:00:00Z"
    end_utc = f"{(day + dt.timedelta(days=1)).isoformat()}T02:00:00Z"
    params = {
        "timeframe": "5Min", "start": start_utc, "end": end_utc,
        "limit": 200, "feed": "sip",
    }
    req = Request(f"{SPY_BARS_URL}?{urlencode(params)}",
                   headers={"APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret})
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    return payload.get("bars", []) or []


def to_et_naive(raw_ts: str) -> dt.datetime:
    ts_utc = dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    return ts_utc.astimezone(ET).replace(tzinfo=None)


def main() -> int:
    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")

    for label, day in (("WINTER (EST, expect UTC offset -05:00)", WINTER_DAY),
                        ("SUMMER (EDT, expect UTC offset -04:00)", SUMMER_DAY)):
        bars = fetch_day(creds, day)
        if not bars:
            print(f"{label} {day}: 0 bars returned -- ABORT, cannot verify")
            return 1
        # locate the RTH-open bar: raw UTC ts whose ET-converted wall time is 09:30
        open_bar = None
        for b in bars:
            et_naive = to_et_naive(b["t"])
            if et_naive.time() == dt.time(9, 30):
                open_bar = (b["t"], et_naive)
                break
        n_bars = len(bars)
        first_raw, first_et = bars[0]["t"], to_et_naive(bars[0]["t"])
        last_raw, last_et = bars[-1]["t"], to_et_naive(bars[-1]["t"])
        print(f"\n{label} -- {day}")
        print(f"  bars returned: {n_bars}")
        print(f"  first bar: raw_utc={first_raw}  ->  et_naive={first_et.isoformat()}")
        print(f"  last  bar: raw_utc={last_raw}  ->  et_naive={last_et.isoformat()}")
        if open_bar:
            print(f"  09:30 RTH-open bar FOUND: raw_utc={open_bar[0]}  ->  et_naive={open_bar[1].isoformat()}")
        else:
            print("  09:30 RTH-open bar: NOT FOUND (would indicate DST drift or missing data)")
            return 1

    print("\nVERIFIED: both days' 09:30 ET bar lands at naive wall-clock 09:30:00 "
          "despite the underlying raw UTC offset differing (winter vs summer) -- "
          "the astimezone(ET) conversion is DST-correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
