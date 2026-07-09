"""pdt_tracker -- computes the REAL day-trade count from broker fill history (Rule 7).

FIX (2026-07-06): circuit-breaker.json's day_trades_used_5d was a hardcoded 0,
written once at premarket and never incremented afterward -- confirmed via the
2026-07-06 full-day audit (8 same-day Safe round trips, zero PDT tracking; the
counter can literally never reach PDT_DAY_TRADE_LIMIT=3 because it never moves
off 0). orchestrator.py, cap_admission.py, and pre_order_gate.py each carry a
comment assuming ANOTHER component owns live day-trade tracking; none of them
actually do. This computes the real count directly from Alpaca's own fill
history (broker = source of truth, C11) so risk_gate.check_order's PDT check is
fed a real number instead of a number that can never trip.

Definition (FINRA/Alpaca): a day trade = the same SECURITY (equity/option --
explicitly NOT cryptocurrency, which PDT does not apply to) bought AND sold (or
sold-short and bought-to-cover) within the SAME trading day. Counted over the
trailing 5 BUSINESS days (weekday-only approximation -- no holiday table, so on
a week with a market holiday the window can be a little WIDER than the strict
5 trading days, never narrower -- the conservative direction for a safety gate).

TWO BUGS CAUGHT DURING BUILD, before this ever reached a guard test (verified
2026-07-06 against Safe's real fill history, which returned 11 -- a live
reproduction of both, not a hypothetical):
  1. Crypto round-trips (BTC/USD, UNI/USD -- e.g. the nightly Gamma_DressRehearsal
     $10 BTC test) were counting as day trades. PDT does not apply to crypto.
     Fixed by excluding any symbol containing "/" (the crypto pair convention;
     equity/option symbols never contain one).
  2. Trading-day boundaries were computed from datetime.now(timezone.utc).date()
     -- which reads as the NEXT calendar day any time after 20:00 ET (UTC is
     always 4-5h ahead), a live instance of this codebase's own "stale-clock"
     failure class. Fixed by converting every timestamp through et_clock.et_now()
     before taking .date(), matching the rest of the codebase's ET convention.

Fail-open (rail-2): any fetch error returns 0, matching today's pre-fix
behavior exactly -- a failed live count can only let a trade through that a
working count would have blocked, never invent a NEW block on real money.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from et_clock import et_now  # noqa: E402  -- naive ET datetime from a UTC-aware one


def _is_crypto_symbol(symbol: str) -> bool:
    """Alpaca crypto pairs are always written as 'BTC/USD' etc; equities and
    OCC option symbols never contain '/'. PDT does not apply to crypto."""
    return "/" in (symbol or "")


def trailing_business_days(as_of_et: datetime, n: int = 5) -> set:
    """PURE. The N most recent WEEKDAY calendar dates strictly before
    as_of_et's date (today itself is added separately by the caller -- see
    compute_day_trades_used_5d). as_of_et must already be an ET-calendar date
    (naive, matching et_clock.et_now()'s convention) -- NOT a raw UTC datetime,
    or the boundary silently shifts a day late in the ET evening (the exact bug
    this module was built to avoid repeating)."""
    days: set = set()
    d = as_of_et.date()
    while len(days) < n:
        d = d - timedelta(days=1)
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            days.add(d)
    return days


def compute_day_trades_used_5d(activities: list, as_of_et: datetime) -> int:
    """PURE. activities = Alpaca FILL-activity rows (dicts with at least
    "symbol", "side", "transaction_time" -- transaction_time is UTC, converted
    to ET internally). as_of_et is an ET-calendar reference point (naive).
    Returns the count of (symbol, ET-date) pairs with BOTH a buy and a sell
    fill on the same ET calendar date, within the trailing 5 business days
    INCLUDING today -- crypto symbols excluded (PDT doesn't apply to them)."""
    window = trailing_business_days(as_of_et, 5)
    window.add(as_of_et.date())

    by_symbol_date: dict = {}
    for a in activities or []:
        if not isinstance(a, dict):
            continue
        symbol = a.get("symbol")
        side = str(a.get("side") or "").lower()
        ts = a.get("transaction_time")
        if not symbol or side not in ("buy", "sell") or not ts or _is_crypto_symbol(symbol):
            continue
        try:
            dt_utc = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        d = et_now(dt_utc).date()
        if d not in window:
            continue
        sides = by_symbol_date.setdefault((symbol, d), set())
        sides.add(side)

    return sum(1 for sides in by_symbol_date.values() if {"buy", "sell"} <= sides)


def _fetch_fill_activities(creds: dict, after_iso: str, timeout: float = 10.0) -> list:
    """Isolated I/O: pull ALL FILL activities since after_iso, paginating via
    Alpaca's page_token cursor. Fail-open -> [] on any error."""
    out: list = []
    page_token: Optional[str] = None
    base = creds["base_url"].rstrip("/") + "/v2/account/activities/FILL"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    for _ in range(20):  # hard cap on pages -- never loop forever on a malformed cursor
        url = f"{base}?after={after_iso}&direction=asc&page_size=100"
        if page_token:
            url += f"&page_token={page_token}"
        try:
            req = urllib.request.Request(url, headers=headers)
            data = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except Exception:
            break
        if not isinstance(data, list) or not data:
            break
        out.extend(data)
        if len(data) < 100:
            break
        last = data[-1]
        page_token = last.get("id") if isinstance(last, dict) else None
        if not page_token:
            break
    return out


def fetch_day_trades_used_5d(creds: dict, as_of_utc: Optional[datetime] = None) -> int:
    """Live: pull ~10 calendar days of FILL activities from Alpaca and compute
    the real trailing-5-business-day day-trade count. Fail-open -> 0 (never
    raises) -- see module docstring for why 0-on-failure is the safe direction.

    as_of_utc (if given) must be a UTC-aware datetime -- it is converted to ET
    internally via et_clock.et_now(), matching every fill timestamp's own
    conversion, so the two are never compared across mismatched clocks."""
    now_utc = as_of_utc or datetime.now(timezone.utc)
    try:
        after = (now_utc - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        activities = _fetch_fill_activities(creds, after)
        return compute_day_trades_used_5d(activities, et_now(now_utc))
    except Exception:
        return 0
