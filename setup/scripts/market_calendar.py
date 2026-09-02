"""market_calendar.py -- shared Alpaca trading-calendar helper (holidays + early closes).

WHY THIS EXISTS (B2, 2026-09-01): calendar.json already tracked full-day holidays
(engine_health.py:_refresh_calendar_from_alpaca) but DISCARDED the per-date 'close'
field Alpaca's /v2/calendar returns -- so nothing on the rig could tell an early close
(13:00 ET Thanksgiving-eve / Christmas-eve) from a normal 16:00 day. The live broker
calendar has 2026-11-27 and 2026-12-24 both closing 13:00 ET; every scheduled flatten
fires 15:52/15:55 ET -- AFTER expiry on those two days. A 0DTE contract that expired
worthless two hours before the flatten ran is not "flattened late", it is a contract
the flatten never had a chance to close while it still had value.

This module is the ONE place that knows how to read/refresh that calendar so
engine_health.py (holiday self-heal, visibility) and eod_flatten.py (the
--only-if-early-close sweep) can never drift on the schema. Pure stdlib
(urllib/json), $0, fail-open: any network or parse error leaves the existing
cache alone and callers get None (unknown) rather than a guessed value.

SCHEMA (automation/state/calendar.json):
    {
      "source": "alpaca_v2_calendar",
      "fetched_at_et": "...",
      "year_range": ["YYYY-01-01", "YYYY-12-31"],
      "holidays": ["YYYY-MM-DD", ...],          # unchanged, full-day closures
      "early_closes": {"YYYY-MM-DD": "HH:MM"}   # NEW -- only dates where close != 16:00
    }
Backward compatible: a calendar.json with no 'early_closes' key reads as {} (every
date defaults to DEFAULT_CLOSE), so the pre-existing file and every holiday consumer
keep working unchanged.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from et_clock import et_now  # noqa: E402

REPO = _HERE.parents[1]
CAL_PATH = REPO / "automation" / "state" / "calendar.json"
SECRETS_PATH = REPO / "automation" / "state" / "fleet" / "secrets.json"

DEFAULT_CLOSE = "16:00"


def _secrets_creds() -> Optional[dict]:
    """Any one usable Alpaca creds dict from secrets.json -- the calendar endpoint is
    account-agnostic (same trading calendar for every paper account), so ANY key works."""
    try:
        secrets = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        accounts = secrets.get("accounts", secrets)
        creds = next(
            (c for c in accounts.values() if isinstance(c, dict) and (c.get("key") or c.get("api_key"))),
            None,
        )
        if not creds:
            return None
        key = creds.get("key") or creds.get("api_key")
        secret = creds.get("secret") or creds.get("secret_key")
        base = (creds.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
        return {"key": key, "secret": secret, "base_url": base}
    except Exception:  # noqa: BLE001 -- self-heal path, never raise
        return None


def fetch_calendar_days(year: int, creds: Optional[dict] = None, timeout: int = 10) -> Optional[list]:
    """Raw GET /v2/calendar for `year`. Returns the parsed day-list or None on ANY failure
    (missing creds, network, bad JSON) -- callers treat None as 'still unknown', never as
    'zero trading days'."""
    creds = creds or _secrets_creds()
    if not creds:
        return None
    try:
        req = urllib.request.Request(
            f"{creds['base_url']}/v2/calendar?start={year}-01-01&end={year}-12-31",
            headers={"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- fixed https host
            return json.loads(resp.read())
    except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError):
        return None


def refresh_calendar_from_alpaca(cal_path: Path, year: int, creds: Optional[dict] = None) -> bool:
    """Rebuild cal_path from the live Alpaca /v2/calendar for `year`. Writes BOTH
    'holidays' (weekday dates absent from the response) and 'early_closes' (dates
    present with a 'close' other than 16:00). Fail-open: any error leaves the
    existing file untouched and returns False -- this is the ONLY writer of
    calendar.json, shared by engine_health's holiday self-heal and any early-close
    visibility check.
    """
    days = fetch_calendar_days(year, creds)
    if days is None:
        return False
    try:
        open_dates = {d["date"] for d in days}
        early_closes: dict[str, str] = {}
        for d in days:
            close = d.get("close")
            if close and close != DEFAULT_CLOSE:
                early_closes[d["date"]] = close
        d = datetime(year, 1, 1)
        end = datetime(year, 12, 31)
        holidays = []
        while d <= end:
            if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in open_dates:
                holidays.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
        cal_path.write_text(json.dumps({
            "source": "alpaca_v2_calendar",
            "fetched_at_et": et_now().isoformat(),
            "year_range": [f"{year}-01-01", f"{year}-12-31"],
            "holidays": sorted(holidays),
            "early_closes": early_closes,
        }, indent=2), encoding="utf-8")
        return True
    except (KeyError, ValueError, TypeError, OSError):
        return False


def cached_close(date_str: str, cal_path: Path = CAL_PATH) -> Optional[str]:
    """Read today's scheduled close ('HH:MM') straight from the cache, with NO network
    fallback. Returns None if the cache is absent/unreadable/doesn't cover `date_str`'s
    year -- that is the signal to the caller that the cache alone cannot answer this,
    never a guess of '16:00'."""
    try:
        data = json.loads(cal_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    year = date_str[:4]
    year_range = data.get("year_range") or ["", ""]
    if not any(year in str(v) for v in year_range):
        return None
    early_closes = data.get("early_closes") or {}
    return str(early_closes.get(date_str, DEFAULT_CLOSE))


def market_close_et(date_str: str, cal_path: Path = CAL_PATH, creds: Optional[dict] = None) -> Optional[str]:
    """Today's scheduled market close ('HH:MM' ET) for `date_str`. Cache first; if the
    cache doesn't cover this date's year, self-heal via a live full-year refresh (same
    self-heal contract as engine_health._load_holidays) and re-read. Returns None only
    if BOTH the cache and the live refresh fail -- an unknown calendar state, never a
    default assumption."""
    close = cached_close(date_str, cal_path)
    if close is not None:
        return close
    year = int(date_str[:4])
    if refresh_calendar_from_alpaca(cal_path, year, creds=creds):
        return cached_close(date_str, cal_path)
    return None


def early_close_today(cal_path: Path = CAL_PATH, creds: Optional[dict] = None) -> Optional[dict]:
    """Visibility helper for engine_health's non-critical checks. Returns:
      {'early_close': True,  'close': 'HH:MM'}  -- today closes early
      {'early_close': False, 'close': '16:00'}   -- today is a normal full day
      None                                        -- calendar state unknown (cache miss
                                                      AND live refresh failed)
    Never raises."""
    today = et_now().strftime("%Y-%m-%d")
    close = market_close_et(today, cal_path, creds=creds)
    if close is None:
        return None
    return {"early_close": close != DEFAULT_CLOSE, "close": close}
