"""pdt_tracker -- computes the REAL margin-style day-trade count from broker
fill history (Rule 7, LEGACY mode).

STATUS UPDATE (2026-07-14): this module's count is now the TRADING gate feed
ONLY under params.pdt_gate_mode == "margin_pdt" (the pre-2026-07-14 default,
kept for one-line revert). Both core accounts (Gamma-Safe-2 PA3DHPT7KIQE,
Gamma-Risky-2 PA33W2KUAT40) are CASH accounts (verified live: multiplier=1,
Alpaca reports pattern_day_trader/daytrade_count as null) -- PDT never
applied to them; the margin-style count this module computes was blocking
real entries on a rule that doesn't govern these accounts (see
markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md and
backtest/lib/risk_gate.py's CODE_SETTLEMENT docs). Both accounts' params.json
now default to pdt_gate_mode="cash_settlement", which gates on
setup/scripts/settlement_ledger.py instead. This module is NOT deleted: (a)
it remains the live gate for any future margin-account caller, and (b) its
fetch_day_trades_used_5d / fetch_day_trades_detail outputs are still consumed
as a VISIBILITY surface (self_check.py, firm_brief.py) and still written to
circuit-breaker.json by heartbeat_core.py -- unrelated to which rule gates
the order.

STATUS UPDATE (2026-08-18, markdown/trading-knowledge/REGULATORY-BROKER-
LANDSCAPE-2026-08-18.md + analysis/deep-research/PDT-CODE-ALIGNMENT-AUDIT-
2026-08-18.md): the account-numbers/"CASH account" premise two paragraphs up
was already stale by 2026-08-06 (those accounts were deleted in the 2026-08-03
fleet rebuild; current core accounts read multiplier=4, margin) and is wrong
in principle -- Alpaca sells no cash-account product at all. Separately and
more fundamentally, FINRA eliminated the margin-PDT rule this module
reconstructs, effective 2026-06-04 (SR-FINRA-2025-017); a 2026-08-18 live read
of both current core accounts found the pattern_day_trader/daytrade_count
fields entirely ABSENT from Alpaca's account payload (replaced by
intraday_adjustments) -- these accounts are confirmed on Alpaca's NEW
intraday-margin regime. Net effect: this module no longer reconstructs a
broker-mirrored rule at all -- it is LOCAL POLICY WITH AN OBSOLETE RATIONALE,
kept alive only as (a) a VISIBILITY surface (self_check.py / firm_brief.py /
circuit-breaker.json's day_trades_used_5d) and (b) the dormant legacy gate for
fleet arms, where it is structurally inert today (fleet_live.py's default
`day_trades_legacy` path reads the now-absent broker field, always 0). Do NOT
re-arm params.fleet_pdt_enforce against this module's count without first
addressing (1)/(2) above -- it would enforce a retired rule using a definition
neither FINRA nor our own broker tracks any more.

ORIGINAL DOCSTRING (below) describes the margin-PDT count itself, unchanged:

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

VISIBILITY EXTENSION (2026-07-14): compute_day_trades_detail / next_rolloff_date
/ fetch_day_trades_detail add "which dates qualified" + "when does the count
next drop" for the PDT VISIBILITY instrument (self_check.py + firm_brief.py) --
the 2026-07-13 scar where core Safe was silently PDT-blocked all day on a
day-trade count it INHERITED from an account repoint (commit 61cfca0), and
nobody knew until a manual review found it (analysis/daily-brief/
2026-07-13-FULL-AUDIT.md #2). fetch_day_trades_detail deliberately does NOT
fail-open to 0 like the trading path above -- a monitoring surface showing a
fake "0 used" on a fetch error is worse than an honest UNKNOWN.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
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


def compute_day_trades_detail(activities: list, as_of_et: datetime) -> dict:
    """PURE. Same inputs/window as compute_day_trades_used_5d (below, now a thin
    wrapper around this) but ALSO returns WHICH ET-calendar dates qualified --
    the count alone can't answer "when does this roll off", which the PDT
    VISIBILITY instrument (self_check.py/firm_brief.py, 2026-07-14) needs (the
    2026-07-13 scar: core Safe was silently PDT-blocked all day on an inherited
    count and nobody knew until a manual review found it -- see
    analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2). Returns
    {"count": int, "dates": sorted list of UNIQUE ISO date strings that had at
    least one qualifying (symbol, date) pair}. count matches
    compute_day_trades_used_5d's original semantics EXACTLY -- it counts
    (symbol, date) PAIRS, not distinct dates (2 different symbols day-traded
    on the SAME date is 2 day trades, per FINRA counting the same security
    rule per-security, not per-day) -- dates is a SEPARATE, deduped view used
    only to find the earliest date for next_rolloff_date, never used for the
    count itself."""
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

    qualifying_pairs = [(sym, d) for (sym, d), sides in by_symbol_date.items()
                        if {"buy", "sell"} <= sides]
    dates = sorted({d.isoformat() for _sym, d in qualifying_pairs})
    return {"count": len(qualifying_pairs), "dates": dates}


def compute_day_trades_used_5d(activities: list, as_of_et: datetime) -> int:
    """PURE. activities = Alpaca FILL-activity rows (dicts with at least
    "symbol", "side", "transaction_time" -- transaction_time is UTC, converted
    to ET internally). as_of_et is an ET-calendar reference point (naive).
    Returns the count of (symbol, ET-date) pairs with BOTH a buy and a sell
    fill on the same ET calendar date, within the trailing 5 business days
    INCLUDING today -- crypto symbols excluded (PDT doesn't apply to them).
    Thin wrapper over compute_day_trades_detail -- byte-identical behavior,
    unchanged since 2026-07-06 (test_pdt_tracker_2026_07_06.py pins it)."""
    return compute_day_trades_detail(activities, as_of_et)["count"]


def next_rolloff_date(qualifying_dates: list, as_of_et: datetime) -> Optional[str]:
    """PURE. Given compute_day_trades_detail()'s sorted ISO date list, returns
    the ISO date on which the EARLIEST qualifying date exits the trailing
    window -- i.e. the next date the day-trade count will DECREASE, assuming
    no new day trades happen meanwhile. None when there are no qualifying
    dates (nothing to roll off).

    The window (see trailing_business_days + compute_day_trades_detail) is 6
    business days wide (today + 5 preceding business days): a date D stays in
    window(X) for every X in {D, D+1bd, ..., D+5bd} and drops out at X=D+6bd
    -- so the rolloff date is exactly the earliest qualifying date plus 6
    business days. as_of_et is accepted for signature symmetry with the rest
    of this module but the result does not depend on it (business-day
    arithmetic is date-relative, not "as of now" relative)."""
    if not qualifying_dates:
        return None
    d = date.fromisoformat(min(qualifying_dates))
    added = 0
    while added < 6:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.isoformat()


def _fetch_fill_activities(creds: dict, after_iso: str, timeout: float = 10.0,
                            *, strict: bool = False) -> list:
    """Isolated I/O: pull ALL FILL activities since after_iso, paginating via
    Alpaca's page_token cursor. Fail-open -> [] on any error by default
    (strict=False, unchanged since 2026-07-06 -- the TRADING gate's contract:
    a failed live count can only let a trade through that a working count
    would have blocked, never invent a new block on real money).

    strict=True (additive, 2026-07-14): RE-RAISES instead of swallowing --
    for the VISIBILITY-only fetch_day_trades_detail below, where a silent []
    on a fetch error would masquerade as "0 day trades used", which is worse
    for a monitoring surface than an honest UNKNOWN (OP-33: never imply it
    works). Never used by the trading-critical fetch_day_trades_used_5d path."""
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
            if strict:
                raise
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


def fetch_day_trades_detail(creds: dict, as_of_utc: Optional[datetime] = None) -> dict:
    """VISIBILITY-ONLY variant of fetch_day_trades_used_5d (2026-07-14, PDT
    visibility instrument -- the 2026-07-13 scar: core Safe was silently
    PDT-blocked ALL DAY on a day-trade count it INHERITED from the account's
    prior life as fleet arm safe-1 [account repoint, commit 61cfca0], and
    nobody knew until a manual review found it, not an instrument --
    analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2).

    Unlike fetch_day_trades_used_5d, this does NOT fail-open to a fake 0 on a
    fetch error -- for a monitoring/glance surface, a silent 0 that actually
    means "couldn't check" is worse than an honest "unknown" (OP-33: never
    imply it works). The TRADING gate (fetch_day_trades_used_5d, above) is
    UNCHANGED and keeps its fail-open-to-0 contract; this is a separate,
    additive function for glance surfaces only (self_check.py / firm_brief.py)
    -- never consumed by risk_gate.check_order.

    Returns on success:
        {"ok": True, "count": int, "dates": [...], "rolloff_date": iso|None,
         "as_of_et": iso}
    Returns on any fetch/parse error:
        {"ok": False, "error": "<ExceptionType>: <short message>"}
    """
    now_utc = as_of_utc or datetime.now(timezone.utc)
    try:
        after = (now_utc - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        activities = _fetch_fill_activities(creds, after, strict=True)
        as_of_et = et_now(now_utc)
        detail = compute_day_trades_detail(activities, as_of_et)
        return {
            "ok": True,
            "count": detail["count"],
            "dates": detail["dates"],
            "rolloff_date": next_rolloff_date(detail["dates"], as_of_et),
            "as_of_et": as_of_et.isoformat(),
        }
    except Exception as e:  # noqa: BLE001 -- caller needs the message, not a raise
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
