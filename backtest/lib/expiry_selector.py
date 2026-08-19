"""Expiry selector — resolves WHICH Friday (or ~30-DTE monthly) a weekly-lane entry buys,
against the LIVE option chain, never a computed calendar date.

WHY THIS EXISTS (markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §4 rule 3, §5 "New" —
verified 2026-08-18): J explicitly asked to test "which Friday, one week or two week out"
as a first-class, comparable knob. This module is the mechanism: four PURE rules
(SAME_WEEK / NEXT_WEEK / TWO_WEEKS_OUT / MONTHLY), each a function of
(as_of, available_expiries) -> a structured ExpirySelection, so different weekly-1 arms
can be run side-by-side on identical data and diffed.

LOAD-BEARING CONSTRAINT (verified 2026-08-18, WEEKLY-OPTIONS-PROGRAM.md §2): NVDA's
2026-08-26 expiry is NOT LISTED on the live chain because earnings land that day. A rule
that computes "next Friday" arithmetically and returns it WITHOUT checking the live chain
would select a contract that does not exist -- an order-time 404/422 at best, or a silent
wrong-week fill that contaminates the whole DTE comparison this program exists to run, at
worst. Every rule here therefore treats a calendar Friday as a SEARCH TARGET only, and
always returns a member of the caller-supplied `available_expiries` list -- never a
fabricated date. When the exact target isn't listed, the search escalates forward
deterministically (next listed expiry >= target) and the returned ExpirySelection's
`fallback` flag + `fallback_reason` record WHY, so a fallback can never silently
contaminate the arm comparison (a silent fallback would be indistinguishable from a clean
signal in the shadow ledger -- the whole point of the flag).

`min_dte` is READ from automation/state/weekly/params.json's `entry.min_dte_at_entry` (3
as of 2026-08-18) via `load_min_dte_at_entry()` -- NEVER hardcoded here; that file is
owned by a sibling workstream and this module tracks whatever value it holds. The four
rule functions themselves stay PURE (min_dte is an explicit parameter, no file I/O inside
the selection logic) so they are trivially unit-testable in isolation from the params
file; `load_min_dte_at_entry()` is the one I/O seam, meant to be called once by a
production caller (and by this module's own tests, to prove no hardcoded duplicate of "3"
has drifted out of sync with the params file).

Clock discipline: `et_today()` derives "today" from the repo's canonical DST-aware ET
clock (setup/scripts/et_clock.py), never a bare `datetime.date.today()` -- this box runs
Mountain time, so local-as-ET is wrong by 2 hours year-round (CLAUDE.md: "TIME = et_clock,
NEVER Bash TZ"). `now_utc` is injectable for deterministic tests.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_WEEKLY_PARAMS_PATH = _REPO_ROOT / "automation" / "state" / "weekly" / "params.json"
_ET_CLOCK_PATH = _REPO_ROOT / "setup" / "scripts" / "et_clock.py"


def _load_et_clock():
    """Import setup/scripts/et_clock.py by file path -- it is not on sys.path by default
    from backtest/lib. Same importlib.util.spec_from_file_location pattern already used by
    backtest/tests/test_et_clock.py, so importing this module never mutates the persistent
    sys.path (which would risk shadowing an unrelated top-level `et_clock` elsewhere)."""
    spec = importlib.util.spec_from_file_location("et_clock", _ET_CLOCK_PATH)
    assert spec is not None and spec.loader is not None, (
        f"cannot load et_clock from {_ET_CLOCK_PATH}"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_et_clock = _load_et_clock()


def et_today(now_utc: Optional[dt.datetime] = None) -> dt.date:
    """'Today' for expiry selection -- the DST-aware ET calendar date, NEVER
    `datetime.date.today()` (this box runs Mountain time; a bare local date is wrong by 2
    hours year-round, and wrong by a full CALENDAR DAY near midnight ET).

    Pass `now_utc` for deterministic tests -- mirrors `et_clock.et_now`'s own injectable-
    clock contract exactly, so a test can pin a UTC instant and assert the correct ET
    calendar date without depending on the box's local timezone at all.
    """
    return _et_clock.et_now(now_utc=now_utc).date()


RULE_SAME_WEEK = "SAME_WEEK"
RULE_NEXT_WEEK = "NEXT_WEEK"
RULE_TWO_WEEKS_OUT = "TWO_WEEKS_OUT"
RULE_MONTHLY = "MONTHLY"
ALL_RULES = (RULE_SAME_WEEK, RULE_NEXT_WEEK, RULE_TWO_WEEKS_OUT, RULE_MONTHLY)

# Friday-target rules, keyed by how many calendar weeks past the nearest Friday>=as_of
# each one targets. MONTHLY is handled separately (a DTE-distance target, not a week count).
_FRIDAY_WEEKS_OUT = {RULE_SAME_WEEK: 0, RULE_NEXT_WEEK: 1, RULE_TWO_WEEKS_OUT: 2}

# MONTHLY is a ~30-DTE CONTROL arm, not a literal "3rd-Friday-of-month" OCC monthly
# contract lookup -- the live chain already contains whatever monthly-cycle expiries
# exist, so "closest listed DTE to 30" is both simpler and more robust than reimplementing
# OCC's 3rd-Friday calendar rule. Deviation beyond _MONTHLY_TOLERANCE_DAYS from the 30-DTE
# target is flagged as a fallback (the chain has nothing resembling a monthly cycle nearby).
_MONTHLY_TARGET_DTE = 30
_MONTHLY_TOLERANCE_DAYS = 7


@dataclass(frozen=True)
class ExpirySelection:
    """One expiry decision, self-documenting for the shadow ledger / journal.

    `target_expiry` is the CALENDAR date the rule aimed for BEFORE checking the live
    chain (kept for audit trail -- e.g. proving a NVDA-earnings-gap fallback landed on
    the correct next expiry, not an arbitrary one). `chosen_expiry` is always a member of
    the `available_expiries` the caller supplied -- never a fabricated date.
    """

    rule: str
    as_of: dt.date
    target_expiry: dt.date
    chosen_expiry: dt.date
    dte: int
    fallback: bool
    fallback_reason: Optional[str]


def load_min_dte_at_entry(params_path: Path = DEFAULT_WEEKLY_PARAMS_PATH) -> int:
    """Read `entry.min_dte_at_entry` from the weekly-lane params.json.

    NEVER hardcode this value in code -- automation/state/weekly/params.json is owned by
    a sibling workstream; a rule change there (e.g. 3 -> 4) must flow through here
    automatically, not require a matching code edit elsewhere. Fails LOUD (raises) on a
    missing file or missing key -- a missing min-DTE floor is not "assume 3", it is
    "cannot safely select an expiry" (house no-silent-fallback rule).
    """
    if not params_path.exists():
        raise FileNotFoundError(f"weekly-lane params.json not found: {params_path}")
    with params_path.open("r", encoding="utf-8") as f:
        params = json.load(f)
    try:
        return int(params["entry"]["min_dte_at_entry"])
    except KeyError as exc:
        raise KeyError(
            f"weekly-lane params.json at {params_path} has no entry.min_dte_at_entry"
        ) from exc


def _nearest_friday_on_or_after(d: dt.date) -> dt.date:
    """Calendar Friday >= d. A SEARCH TARGET ONLY -- see module docstring's load-bearing
    constraint. Never returned to a caller without first checking it is actually listed
    in `available_expiries`."""
    days_ahead = (4 - d.weekday()) % 7  # datetime weekday: Monday=0 .. Friday=4 .. Sunday=6
    return d + dt.timedelta(days=days_ahead)


def _forward_available(target: dt.date, available_sorted: Sequence[dt.date]) -> Optional[dt.date]:
    """First listed expiry >= target, scanning forward through the (already-sorted) live
    chain -- the "escalating search band" the program doc calls for. Deterministic: always
    the SAME answer for the same (target, chain). Only ever escalates toward LATER dates,
    never backward -- a nearer date would only make min_dte enforcement worse and could
    silently swap a caller into an earlier rule's territory (e.g. SAME_WEEK quietly
    becoming a 0-DTE pick), which is exactly the silent-contamination failure mode this
    module exists to prevent."""
    for candidate in available_sorted:
        if candidate >= target:
            return candidate
    return None


def _select_friday_rule(
    rule: str,
    weeks_out: int,
    as_of: dt.date,
    available_expiries: Sequence[dt.date],
    min_dte: int,
) -> ExpirySelection:
    if not available_expiries:
        raise ValueError(
            f"{rule}: available_expiries is empty for as_of={as_of.isoformat()} -- cannot "
            f"select an expiry without a live chain"
        )
    available_sorted = sorted(set(available_expiries))

    base_friday = _nearest_friday_on_or_after(as_of)
    target = base_friday + dt.timedelta(weeks=weeks_out)
    reasons: list[str] = []

    if weeks_out == 0:
        same_week_dte = (target - as_of).days
        if same_week_dte < min_dte:
            reasons.append(
                f"same-week Friday {target.isoformat()} is {same_week_dte} DTE, under the "
                f"min_dte_at_entry floor of {min_dte} -- advanced to next week's Friday"
            )
            target = target + dt.timedelta(weeks=1)

    if target in available_sorted:
        chosen = target
    else:
        chosen = _forward_available(target, available_sorted)
        if chosen is None:
            raise ValueError(
                f"{rule}: target {target.isoformat()} is not listed and no later expiry "
                f"exists in the supplied chain "
                f"({[d.isoformat() for d in available_sorted]}) -- refusing to silently "
                f"select a wrong-direction contract"
            )
        reasons.append(
            f"target {target.isoformat()} is not in the live chain "
            f"({len(available_sorted)} listed expiries) -- advanced to next listed expiry "
            f"{chosen.isoformat()}"
        )

    dte = (chosen - as_of).days
    return ExpirySelection(
        rule=rule,
        as_of=as_of,
        target_expiry=target,
        chosen_expiry=chosen,
        dte=dte,
        fallback=bool(reasons),
        fallback_reason=" | ".join(reasons) if reasons else None,
    )


def _select_monthly(
    as_of: dt.date, available_expiries: Sequence[dt.date], min_dte: int
) -> ExpirySelection:
    if not available_expiries:
        raise ValueError(
            f"{RULE_MONTHLY}: available_expiries is empty for as_of={as_of.isoformat()}"
        )
    available_sorted = sorted(set(available_expiries))
    target = as_of + dt.timedelta(days=_MONTHLY_TARGET_DTE)

    eligible = [d for d in available_sorted if (d - as_of).days >= min_dte]
    if not eligible:
        raise ValueError(
            f"{RULE_MONTHLY}: no listed expiry clears the min_dte_at_entry floor of "
            f"{min_dte} for as_of={as_of.isoformat()} in "
            f"{[d.isoformat() for d in available_sorted]}"
        )
    chosen = min(eligible, key=lambda d: (abs((d - target).days), d))
    dte = (chosen - as_of).days
    deviation = abs(dte - _MONTHLY_TARGET_DTE)
    fallback = deviation > _MONTHLY_TOLERANCE_DAYS
    reason = None
    if fallback:
        reason = (
            f"closest listed expiry to the ~{_MONTHLY_TARGET_DTE}-DTE monthly control "
            f"target is {chosen.isoformat()} ({dte} DTE, {deviation}d off target) -- no "
            f"listed expiry within the {_MONTHLY_TOLERANCE_DAYS}-day monthly-cycle "
            f"tolerance"
        )
    return ExpirySelection(
        rule=RULE_MONTHLY,
        as_of=as_of,
        target_expiry=target,
        chosen_expiry=chosen,
        dte=dte,
        fallback=fallback,
        fallback_reason=reason,
    )


def select_expiry(
    rule: str,
    as_of: dt.date,
    available_expiries: Sequence[dt.date],
    min_dte: int,
) -> ExpirySelection:
    """Dispatch to the named rule (one of ALL_RULES).

    `min_dte` is REQUIRED (no hardcoded default) -- production callers pass
    `load_min_dte_at_entry()`'s result so params.json stays the only source of truth (see
    that function's docstring); tests pass an explicit value to prove the knob actually
    changes behavior without touching the real params file.
    """
    if rule in _FRIDAY_WEEKS_OUT:
        return _select_friday_rule(
            rule, _FRIDAY_WEEKS_OUT[rule], as_of, available_expiries, min_dte
        )
    if rule == RULE_MONTHLY:
        return _select_monthly(as_of, available_expiries, min_dte)
    raise ValueError(f"unknown expiry rule {rule!r}; expected one of {ALL_RULES}")
