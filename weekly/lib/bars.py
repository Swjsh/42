"""bars.py -- Daily + 1Hour bar fetch for the weekly-options lane (arm weekly-1).

WHY THE CLOSED-BAR RULE (lesson C6, no-look-ahead): a bar is usable for a
decision only once it has actually closed. Alpaca's bars endpoint will
happily hand back an IN-PROGRESS bar for "today" (1Day) or "this hour"
(1Hour) while the market is still trading it -- treating that bar's high/
low/close as final would be reading a price move that, from the market's
own perspective, hasn't finished happening yet. This module computes every
bar's close time explicitly and DROPS any bar whose close time is still in
the future relative to now-ET. Every other weekly-lane module (zones.py,
trigger.py) must only ever consume frames produced by this file -- never
re-fetch or re-filter bars themselves.

Credentials: reused verbatim from backtest/tools/_alpaca_creds.py (env
ALPACA_API_KEY/ALPACA_SECRET_KEY win; else the `alpaca` server's env block
in the project-root .mcp.json -- the same Safe-2 paper key sight_beacon.py
and fleet_broker.py already use for market-data reads). No new credential-
resolution logic, and no secret is ever read into a variable this module
prints or logs (masked() exists in _alpaca_creds.py for that reason -- this
file never calls it because it never logs a key at all).

Timezone: every "now" and every bar timestamp is computed via real UTC
(`datetime.now(timezone.utc)`) converted through `zoneinfo.ZoneInfo
("America/New_York")` -- never a hardcoded -4/-5 offset, and never the local
machine clock (this box runs Mountain time; Bash `TZ=America/New_York` is
confirmed broken here). This deliberately does NOT reuse
setup/scripts/et_clock.py's `ET_TZ`: verified during this build,
`_EasternTZ.utcoffset(None)` (the recursion-guard branch in et_clock.py)
unconditionally returns a hardcoded EST (-5h) offset. Pandas' vectorized
Series/DataFrame dtype inference probes exactly `tzinfo.utcoffset(None)` to
decide whether a custom tzinfo is a fixed offset, and silently applies that
single -5h value to the WHOLE column -- during EDT (roughly mid-March to
early-November, i.e. most of the trading year) this shifts every bar
timestamp in a DataFrame by a full hour versus its correct, per-value
`.astimezone(ET_TZ)` result (reproduced live: a scalar `dt.astimezone(ET_TZ)`
returns the correct `...T00:00:00-04:00`, but `pd.DataFrame({"t": [dt]})`
built from the SAME value silently renders `...T23:00:00-04:00`). This is a
real defect in the shared et_clock.py module, out of this file's ownership
scope -- flagged in the build report rather than patched here.
`ZoneInfo("America/New_York")` is real IANA tzdata (no recursion-guard
approximation) and is the pattern `backtest/tools/alpaca_bars.py` and
`backtest/lib/et_frame.py`'s et-v2 convention already use for this exact
pandas-facing purpose.

Scope: this module only READS stock bars (GET .../bars). It places, cancels,
and modifies nothing -- Stage A of the weekly lane is shadow-only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

if TYPE_CHECKING:
    from crypto.lib.bar import Bar

# weekly/lib/bars.py -> weekly/lib -> weekly -> 42/ (repo root)
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT / "backtest" / "tools"), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _alpaca_creds import resolve_alpaca_creds  # noqa: E402  -- reused verbatim, see module docstring

DATA_HOST = "https://data.alpaca.markets"
ET = ZoneInfo("America/New_York")  # see module docstring re: why not et_clock.py's ET_TZ
Timeframe = Literal["1Day", "1Hour"]

_GRANULARITY_TD: dict[str, timedelta] = {"1Day": timedelta(days=1), "1Hour": timedelta(hours=1)}
GRANULARITY_SECONDS: dict[str, int] = {"1Day": 86_400, "1Hour": 3_600}

RTH_OPEN_MIN = 9 * 60 + 30  # 09:30 ET, minutes-since-midnight
RTH_CLOSE_MIN = 16 * 60  # 16:00 ET


class BarFetchError(RuntimeError):
    """Raised on an empty, short, or failed Alpaca bar response.

    Never swallowed to fall through to a silently-short frame (CLAUDE.md's
    "no silent fallbacks" + lesson C7 -- a producer that exits clean while
    quietly writing a truncated/stale frame is this shop's #1 documented
    failure class). Callers must handle this explicitly, not catch-and-hope.
    """


def _bar_close_et(open_et: datetime, timeframe: str) -> datetime:
    """Close time of a bar, in ET.

    1Hour: mechanical open + 1h.

    1Day: the session's RTH close (16:00 ET) of the SAME calendar day the bar
    is dated for -- NOT open + 24h. Alpaca stamps a daily bar's `t` at
    midnight ET of the session date, so open + 24h would compute "closed"
    only at midnight the NEXT day -- which reads today's still-forming daily
    bar as OPEN for the entire 16:00-23:59 ET post-close window, exactly the
    look-ahead gap the closed-bar filter exists to close (lesson C6).

    Known, documented gap: early-close (half) sessions are not modeled --
    every day is treated as a 16:00 ET close. This is the conservative
    direction (it can only make an early-closed day's bar look "not yet
    closed" for a few extra hours after the real close, never the reverse --
    it can never admit a bar before it has actually finished trading).
    """
    if timeframe == "1Day":
        return open_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_et + _GRANULARITY_TD[timeframe]


def _fetch_raw_bars(symbol: str, timeframe: str, limit: int, feed: str, timeout: int) -> list[dict]:
    if timeframe not in _GRANULARITY_TD:
        raise ValueError(f"unsupported timeframe {timeframe!r}; expected one of {tuple(_GRANULARITY_TD)}")
    creds = resolve_alpaca_creds()
    params = {
        "timeframe": timeframe,
        "limit": limit,
        "feed": feed,
        "adjustment": "raw",
        # newest-first so a `limit`-capped response can never truncate the
        # NEWEST bar off the tail (the exact 2026-06-26 sight_beacon scar --
        # sort=asc + a low limit silently froze the frame on a stale session).
        "sort": "desc",
    }
    url = f"{DATA_HOST}/v2/stocks/{symbol}/bars?{urlencode(params)}"
    req = Request(url, headers={
        "APCA-API-KEY-ID": creds.key,
        "APCA-API-SECRET-KEY": creds.secret,
        "accept": "application/json",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- fixed https host, not user input
            payload = json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError) as exc:
        raise BarFetchError(
            f"{symbol} {timeframe}: Alpaca bar fetch failed: {type(exc).__name__}: {exc}"
        ) from exc
    bars = payload.get("bars")
    if not bars:
        raise BarFetchError(f"{symbol} {timeframe}: Alpaca returned zero bars (response keys={list(payload)})")
    return list(reversed(bars))  # desc -> asc (oldest first)


def _bars_to_frame(raw: list[dict], timeframe: str, now_et: datetime, min_bars: int, symbol: str) -> pd.DataFrame:
    """Pure filtering/framing step, separated from the network call so it is
    unit-testable with hand-built bar dicts and a fixed `now_et` -- no
    network, no mocking urlopen.

    Drops:
      - any bar whose close time (`_bar_close_et`) is still in the future
        relative to `now_et` (no-look-ahead, lesson C6);
      - for 1Hour, any bar not FULLY inside RTH [09:30, 16:00) ET -- this
        removes pre/post-market bars AND the low-count trailing partial hour
        (whichever alignment convention the feed uses: a bar opening before
        09:30 carries pre-market volume, and a bar that would close after
        16:00 carries fewer than 60 real trading minutes).

    Raises BarFetchError (never a silently short/empty frame) if fewer than
    `min_bars` bars survive both filters.
    """
    rows = []
    for b in raw:
        open_et = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        close_et = _bar_close_et(open_et, timeframe)
        if close_et > now_et:
            continue  # still in progress -- look-ahead guard
        if timeframe == "1Hour":
            open_min = open_et.hour * 60 + open_et.minute
            close_min = close_et.hour * 60 + close_et.minute
            same_day = open_et.date() == close_et.date()
            if not same_day or open_min < RTH_OPEN_MIN or close_min > RTH_CLOSE_MIN:
                continue  # outside RTH, or a low-count partial hour at the tail
        rows.append({
            "timestamp_et": open_et,
            "open": float(b["o"]),
            "high": float(b["h"]),
            "low": float(b["l"]),
            "close": float(b["c"]),
            "volume": float(b["v"]),
        })

    if len(rows) < min_bars:
        raise BarFetchError(
            f"{symbol} {timeframe}: only {len(rows)} closed bar(s) survived filtering "
            f"(min_bars={min_bars}, raw_count={len(raw)}) -- refusing to return a short frame"
        )

    df = pd.DataFrame(rows).set_index("timestamp_et").sort_index()
    df.index.name = "timestamp_et"
    return df


def fetch_bars(
    symbol: str,
    timeframe: Timeframe,
    *,
    limit: int = 300,
    feed: str = "iex",
    min_bars: int = 5,
    now_et: datetime | None = None,
    timeout: int = 15,
) -> pd.DataFrame:
    """Fetch closed Daily or 1Hour bars for `symbol` from Alpaca.

    Returns a DataFrame indexed by an ET-aware DatetimeIndex (name
    'timestamp_et'), columns open/high/low/close/volume, oldest-first.
    Raises BarFetchError on a failed fetch or an insufficient closed-bar
    count -- never a silently short/empty frame.
    """
    if now_et is None:
        now_et = datetime.now(timezone.utc).astimezone(ET)
    raw = _fetch_raw_bars(symbol, timeframe, limit, feed, timeout)
    return _bars_to_frame(raw, timeframe, now_et, min_bars, symbol)


def fetch_daily(
    symbol: str, *, limit: int = 300, feed: str = "iex", min_bars: int = 30,
    now_et: datetime | None = None,
) -> pd.DataFrame:
    """Daily bars, closed-only. `min_bars` defaults to 30 -- NOT enough to
    seed a 50-day EMA. A caller feeding zones.compute_zones's ema_20_50
    family must pass min_bars>=51 explicitly, or that family's 50-length leg
    will simply be absent from the result (zones.py documents this as a
    graceful skip, not an error)."""
    return fetch_bars(symbol, "1Day", limit=limit, feed=feed, min_bars=min_bars, now_et=now_et)


def fetch_hourly(
    symbol: str, *, limit: int = 300, feed: str = "iex", min_bars: int = 10,
    now_et: datetime | None = None,
) -> pd.DataFrame:
    """1Hour bars, closed + RTH-only."""
    return fetch_bars(symbol, "1Hour", limit=limit, feed=feed, min_bars=min_bars, now_et=now_et)


def dataframe_to_bars(df: pd.DataFrame, timeframe: Timeframe, source: str) -> "tuple[Bar, ...]":
    """Convert a bars DataFrame (as returned by fetch_bars/fetch_daily/
    fetch_hourly) into an immutable tuple[crypto.lib.bar.Bar, ...] -- the
    shared value type crypto/lib's market_structure, trendlines, and
    indicators modules all consume. This is what lets zones.py/trigger.py
    reuse that ATR/EMA/swing/structure logic instead of a second
    implementation (CLAUDE.md: reuse, don't reimplement).
    """
    from crypto.lib.bar import Bar  # local import: keeps this module importable standalone

    granularity = GRANULARITY_SECONDS[timeframe]
    out = []
    for ts, row in df.iterrows():
        open_time = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        out.append(Bar(
            open_time=open_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            granularity_seconds=granularity,
            source=source,
        ))
    return tuple(out)
