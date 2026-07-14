"""Fetch SPY 5-min bars from Alpaca's SIP (consolidated) feed.

Why this exists (premarket-volume incident, 2026-07-14): the daily append
pipeline fetched SPY from yfinance, whose extended-hours intraday bars carry
volume=0 and silently drop the 09:15-09:25 ET bars. Every session appended
since 2026-05-13 had a dead premarket tape. Alpaca SIP is the same source the
2026-05-19..05-29 seed was built from (verified exact to the bar on 2026-05-27:
premarket vol 1,196,584 / 08:30 bar 27,319 both match), so SIP keeps the chain
provenance-consistent. Do NOT use feed="iex" here — IEX premarket is ~0.2% of
consolidated volume (6 bars / 2.7K shares on 2026-05-27) and useless for RVOL.

Schema out: timestamp_et, open, high, low, close, volume — same as fetch_data.py.
Timestamps carry the real per-row ET offset (DST-correct; wall-v1 consumers
normalize via lib/et_frame.py).
"""

from __future__ import annotations

import datetime as dt
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

from _alpaca_creds import resolve_alpaca_creds

SPY_BARS_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
ET = ZoneInfo("America/New_York")

# Session windows (ET wall time, end-exclusive on bar START time)
PREMARKET_START = dt.time(4, 0)
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)

# Alpaca Basic plan delays recent SIP data by 15 minutes: any query whose end
# reaches into the last 15 min returns HTTP 403 (verified live 2026-07-14
# 16:35 ET — same-day fetch 403'd, historical days succeeded).
SIP_DELAY = dt.timedelta(minutes=16)  # 15 min + 1 min buffer


def sip_aged_at(session_date: dt.date) -> dt.datetime:
    """UTC datetime after which the FULL session (through the 15:55 ET bar,
    which finalizes at 16:00) is old enough for a Basic-plan SIP query."""
    close_et = dt.datetime.combine(session_date, RTH_END, tzinfo=ET)
    return close_et.astimezone(dt.timezone.utc) + SIP_DELAY


def fetch_spy_5m_sip(
    start_date: dt.date,
    end_date: dt.date,
    include_premarket: bool = True,
    timeout: int = 60,
) -> pd.DataFrame:
    """Fetch SPY 5-min SIP bars for [start_date, end_date] (both inclusive).

    Returns bars whose ET wall time falls in [04:00, 16:00) when
    include_premarket=True, else [09:30, 16:00). Empty DataFrame on API failure
    (caller decides fallback) — never raises on HTTP errors, but raises
    RuntimeError if credentials cannot be resolved (fail loud, no silent 401).
    """
    creds = resolve_alpaca_creds()

    # Wide UTC bounds (04:00 ET is 08:00Z in EDT, 09:00Z in EST); the precise
    # cut happens on ET wall time below, so DST never clips or leaks bars.
    # The end bound is clamped away from the last 15 minutes so a same-day
    # query never 403s (see SIP_DELAY). Callers wanting the FULL session must
    # wait until sip_aged_at(end_date) before calling.
    start_utc = f"{start_date.isoformat()}T07:00:00Z"
    end_dt = dt.datetime.fromisoformat(f"{end_date.isoformat()}T21:30:00+00:00")
    now_clamp = dt.datetime.now(dt.timezone.utc) - SIP_DELAY
    if end_dt > now_clamp:
        print(f"  note: clamping SIP query end {end_dt:%Y-%m-%dT%H:%MZ} -> "
              f"{now_clamp:%Y-%m-%dT%H:%MZ} (Basic-plan 15-min delay)")
        end_dt = now_clamp
    end_utc = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    raw: list[dict] = []
    page_token: str | None = None
    while True:
        params = {
            "timeframe": "5Min",
            "start": start_utc,
            "end": end_utc,
            "limit": 10000,
            "feed": "sip",
        }
        if page_token:
            params["page_token"] = page_token
        req = Request(
            f"{SPY_BARS_URL}?{urlencode(params)}",
            headers={
                "APCA-API-KEY-ID": creds.key,
                "APCA-API-SECRET-KEY": creds.secret,
            },
        )
        try:
            payload = json.loads(urlopen(req, timeout=timeout).read())
        except Exception as exc:  # noqa: BLE001 — caller falls back, but loudly
            print(f"  WARN: Alpaca SIP fetch failed for {start_date}..{end_date}: {exc}")
            return pd.DataFrame()
        raw.extend(payload.get("bars", []) or [])
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.15)

    if not raw:
        return pd.DataFrame()

    rows = []
    lower = PREMARKET_START if include_premarket else RTH_START
    for b in raw:
        ts_et = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if not (lower <= ts_et.time() < RTH_END):
            continue
        rows.append(
            {
                # isoformat with space sep -> "2026-06-01 04:00:00-04:00": real
                # per-row DST offset, colon style matching the existing chain rows.
                "timestamp_et": ts_et.isoformat(sep=" "),
                "open": b["o"],
                "high": b["h"],
                "low": b["l"],
                "close": b["c"],
                "volume": b["v"],
            }
        )
    return pd.DataFrame(rows, columns=["timestamp_et", "open", "high", "low", "close", "volume"])
