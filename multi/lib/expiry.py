"""multi/lib/expiry.py — expiry selection from the LIVE listed option chain.

FORKED FROM (not imported from — J directive 2026-08-19: copy, don't touch the
original) the SHAPE of `crypto/lib/strike_selection.py`'s tier-table pattern
(a small pure dataclass + a lookup function + fail-loud on out-of-domain input),
applied to the SPY engine's expiry rule
(automation/state/multi/params.json#entry.expiry_rule =
"this_friday_if_dte_ge_3_else_next_friday").

WHY THIS MODULE NEVER COMPUTES A CALENDAR FRIDAY — NOT EVEN AS A HEURISTIC
------------------------------------------------------------------------------
The SPY 0DTE engine's Friday-arithmetic rule is safe ONLY because SPY has a
LISTED expiry on every trading day (0DTE, by definition). Single names are a
different world: most only list WEEKLY or MONTHLY expiries, several liquid
names list on Monday/Wednesday/Friday (not just Friday), and — the verified
real case that drove this design (J-supplied 2026-08-19) — a name can be
MISSING its otherwise-regular expiry entirely: NVDA's 2026-08-26 expiry (a
Wednesday listing, confirmed not a Friday) is not listed because NVDA reports
earnings that day. A pure calendar heuristic (even "next Friday" used only as a
diagnostic) would have missed that exact case, because 2026-08-26 isn't a
Friday in the first place — the gap isn't Friday-shaped, it's cadence-shaped,
and cadence is different per name and not something calendar math can derive.

So this module makes NO assumption about a name's listing cadence anywhere in
its logic, not even as a comparison. It always chooses from
`available_expiries` — the caller's live chain read (e.g. distinct
`expiration_date` values from a real option-contracts query). Fallback
detection is driven by an EXPLICIT `target_expiry` the caller supplies (their
own expectation of what should be listed, from whatever domain knowledge they
have — e.g. "this name has listed every Friday for months" or a known
catalyst-adjusted date) rather than by this module guessing a cadence:

  * `target_expiry` given AND listed AND clears min_dte -> select it,
    `fallback=False`.
  * `target_expiry` given but NOT listed (or doesn't clear min_dte) -> select
    the nearest LISTED expiry that does clear min_dte instead, and flag
    `fallback=True` with the reason.
  * `target_expiry` omitted -> select the nearest listed expiry clearing
    min_dte with no fallback tracking (there is nothing to have fallen back
    FROM — omitting it is a legitimate choice, not a degraded path).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# --- Stable decision codes (public contract) ----------------------------------
CODE_SELECTED = "SELECTED"
CODE_SELECTED_FALLBACK = "SELECTED_FALLBACK"
CODE_NO_LISTED_EXPIRY = "NO_LISTED_EXPIRY"
CODE_UNREADABLE_INPUT = "UNREADABLE_INPUT"


@dataclass(frozen=True)
class ExpirySelection:
    """Result of `select_expiry`. Use `.ok` or `bool(result)`."""

    ok: bool
    code: str
    reason: str
    expiry: Optional[str] = None  # ISO date string, e.g. "2026-09-04"
    dte: Optional[int] = None
    fallback: bool = False
    fallback_reason: Optional[str] = None

    def __bool__(self) -> bool:
        return self.ok


def now_et() -> datetime:
    """Current time in ET, DST-aware, via the stdlib `zoneinfo` IANA database —
    NEVER a fixed UTC offset. (Project-wide lesson, project CLAUDE.md: this rig
    runs Mountain time; `timezone(timedelta(hours=-4))` is wrong for roughly
    half the year and silently wrong across DST transitions either way.)
    `zoneinfo` correctly picks EDT/EST for the given instant with no hand-rolled
    date math."""
    return datetime.now(ET)


def _parse_iso_date(x: Any) -> Optional[date]:
    """Parse a date/datetime/ISO-date-string into a `date`. Returns None (never
    raises) for anything unparseable — the caller aggregates and fails closed
    if NOTHING parses."""
    if isinstance(x, datetime):
        return x.astimezone(ET).date() if x.tzinfo is not None else x.date()
    if isinstance(x, date):
        return x
    if isinstance(x, str):
        try:
            return date.fromisoformat(x.strip()[:10])
        except ValueError:
            return None
    return None


def select_expiry(
    *,
    symbol: Any,
    available_expiries: Optional[Sequence[Any]],
    params: Optional[Mapping[str, Any]],
    target_expiry: Optional[Any] = None,
    as_of: Optional[datetime] = None,
) -> ExpirySelection:
    """Pick the nearest LISTED expiry (from `available_expiries`) that clears
    `entry.min_dte_at_entry` (days-to-expiry counted from `as_of`, ET).

    Args:
        symbol: underlying ticker, used only for messages.
        available_expiries: the caller's LIVE chain read — an iterable of
            dates/datetimes/ISO-date-strings. This is the ONLY source of truth
            for what is tradeable; entries that fail to parse are dropped (and
            reported if NONE parse), never guessed at.
        params: must carry `entry.min_dte_at_entry` (int, days). Reads the
            `entry` sub-mapping if present, else the top-level mapping (so a
            flat params dict, as tests often pass, also works).
        target_expiry: OPTIONAL — the caller's own expectation of what should
            be listed (date/datetime/ISO string), from whatever domain
            knowledge they have. This module never derives a target itself
            (see module docstring for why — cadence varies per name and isn't
            calendar-derivable). When supplied and it IS listed and clears
            min_dte, it is selected directly. When supplied but missing or
            too-near, the nearest listed alternative is selected instead and
            `fallback=True` is set with a stated reason — this is how a case
            like NVDA's missing 2026-08-26 expiry gets recorded rather than
            silently substituted.
        as_of: the "today" to measure DTE from, as an aware datetime. Defaults
            to `now_et()`. Passed explicitly by tests for determinism —
            production callers should rely on the default (never hardcode a
            date in a call site).

    Returns:
        `ExpirySelection(ok=True, expiry=..., dte=..., fallback=...)` on
        success.

    FAIL CLOSED (`ok=False`): blank/missing symbol, missing/non-mapping params,
    missing/unreadable `min_dte_at_entry`, empty/unparseable
    `available_expiries`, or no listed expiry clears the minimum DTE.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        return ExpirySelection(False, CODE_UNREADABLE_INPUT,
                                f"symbol missing/blank ({symbol!r})")
    if params is None or not isinstance(params, Mapping):
        return ExpirySelection(False, CODE_UNREADABLE_INPUT,
                                "params missing or not a mapping")

    entry_block = params.get("entry")
    entry_block = entry_block if isinstance(entry_block, Mapping) else params
    min_dte_raw = entry_block.get("min_dte_at_entry")
    try:
        if min_dte_raw is None or isinstance(min_dte_raw, bool):
            raise TypeError
        min_dte = int(min_dte_raw)
    except (TypeError, ValueError):
        return ExpirySelection(
            False, CODE_UNREADABLE_INPUT,
            f"params.entry.min_dte_at_entry missing/unreadable ({min_dte_raw!r})",
        )
    if min_dte < 0:
        return ExpirySelection(False, CODE_UNREADABLE_INPUT,
                                f"min_dte_at_entry must be >= 0 (got {min_dte})")

    if not available_expiries:
        return ExpirySelection(
            False, CODE_NO_LISTED_EXPIRY,
            f"{symbol}: no expiries supplied by the live chain read",
        )

    parsed: list[date] = []
    for raw in available_expiries:
        d = _parse_iso_date(raw)
        if d is not None:
            parsed.append(d)
    if not parsed:
        return ExpirySelection(
            False, CODE_NO_LISTED_EXPIRY,
            f"{symbol}: none of the {len(available_expiries)} supplied expiries "
            f"were parseable dates",
        )

    listed = sorted(set(parsed))
    today = (as_of or now_et())
    today_d = today.astimezone(ET).date() if today.tzinfo is not None else today.date()

    candidates = [(d, (d - today_d).days) for d in listed if (d - today_d).days >= min_dte]
    if not candidates:
        nearest = listed[0]
        return ExpirySelection(
            False, CODE_NO_LISTED_EXPIRY,
            f"{symbol}: no listed expiry clears min_dte_at_entry={min_dte} "
            f"(nearest listed is {nearest.isoformat()}, {(nearest - today_d).days} DTE, "
            f"of {len(listed)} listed expiries)",
        )
    nearest_chosen, nearest_dte = candidates[0]

    target_d = _parse_iso_date(target_expiry) if target_expiry is not None else None

    if target_d is not None:
        target_dte = (target_d - today_d).days
        if target_d in listed and target_dte >= min_dte:
            return ExpirySelection(
                True, CODE_SELECTED,
                f"{symbol}: selected target expiry {target_d.isoformat()} ({target_dte} DTE)",
                expiry=target_d.isoformat(), dte=target_dte,
                fallback=False, fallback_reason=None,
            )
        if target_d not in listed:
            why = f"target expiry {target_d.isoformat()} is not in {symbol}'s live listed chain"
        else:
            why = (f"target expiry {target_d.isoformat()} is listed but only "
                   f"{target_dte} DTE < min_dte_at_entry {min_dte}")
        fallback_reason = (
            f"{why} — fell back to the next LISTED expiry clearing min_dte, "
            f"{nearest_chosen.isoformat()} ({nearest_dte} DTE)"
        )
        return ExpirySelection(
            True, CODE_SELECTED_FALLBACK,
            f"{symbol}: selected {nearest_chosen.isoformat()} ({nearest_dte} DTE) — "
            f"FALLBACK: {fallback_reason}",
            expiry=nearest_chosen.isoformat(), dte=nearest_dte,
            fallback=True, fallback_reason=fallback_reason,
        )

    # No target supplied — plain nearest-listed-clearing-min-dte selection, no
    # fallback tracking (nothing was "fallen back from").
    return ExpirySelection(
        True, CODE_SELECTED,
        f"{symbol}: selected {nearest_chosen.isoformat()} ({nearest_dte} DTE)",
        expiry=nearest_chosen.isoformat(), dte=nearest_dte,
        fallback=False, fallback_reason=None,
    )
