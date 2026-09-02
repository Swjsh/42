"""A registered bar must be SATISFIABLE by construction. Guards the prod-shadow designation.

THE SCAR (2026-09-02). `automation/state/prod-shadow-designation.json` was registered on
2026-09-01T20:22 with `window_start 2026-09-01`, `window_end 2026-09-29`, `min_days 20`.
That window contains **exactly 20 trading days**, and a "scored day" requires a FILL
(`go_live_gate.py`: `days_scored = len({r["date"] for r in window_rows})` over trade rows).
So the bar demanded a fill on EVERY trading day -- 100% participation -- from an engine that
sits out ~40% of days BY DESIGN ("sitting out is a valid day", J 2026-08-12).

It was never satisfiable, and nothing said so. The gate reported a truthful-looking
`days_scored=0/20 INSUFFICIENT_DAYS` every run, which reads like "not yet" rather than
"never". Two trading days into the window the ceiling was already 18/20 and the criterion the
entire 2026-10-30 decision rests on was dead, silently.

WHAT THIS FILE PREVENTS: not that specific mistake, but the CLASS -- any future designation
whose day-count bar exceeds what its own window can physically deliver at the engine's
measured duty cycle. A bar you cannot reach is not a strict bar, it is a broken instrument,
and it fails in the most expensive direction: it looks like rigour.

DELIBERATELY NOT ASSERTED HERE: anything about safe-3's returns. Reachability is a property
of the calendar and the fill cadence, both knowable before any P&L exists. Keeping this test
outcome-independent is what stops it becoming a lever for widening a window that is merely
inconvenient.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DESIGNATION = REPO / "automation" / "state" / "prod-shadow-designation.json"
LEDGER = REPO / "analysis" / "trades-enriched.jsonl"

# US market holidays that fall inside any plausible designation window. Only ones that
# actually land in a window matter; a missing holiday makes this test slightly OPTIMISTIC
# about trading days, which is the safe direction for a reachability check (it would let a
# marginal bar through, never fail a good one).
MARKET_HOLIDAYS = {
    dt.date(2026, 9, 7),    # Labor Day
    dt.date(2026, 11, 26),  # Thanksgiving
    dt.date(2026, 12, 25),  # Christmas
}

# The floor participation rate a designation must remain satisfiable at. Set from the WORST
# measured arm rather than the designated one, so a designation cannot be tuned to the single
# arm that happens to trade most often.
PARTICIPATION_FLOOR = 0.47


def _trading_days(a: dt.date, b: dt.date) -> int:
    n, d = 0, a
    while d <= b:
        if d.weekday() < 5 and d not in MARKET_HOLIDAYS:
            n += 1
        d += dt.timedelta(days=1)
    return n


def _date(s: str) -> dt.date:
    return dt.date(*(int(x) for x in str(s)[:10].split("-")))


@pytest.fixture(scope="module")
def designation() -> dict:
    if not DESIGNATION.exists():
        pytest.skip("no prod-shadow designation registered")
    return json.loads(DESIGNATION.read_text(encoding="utf-8"))


def measured_participation(arm: str) -> "tuple[int, int]":
    """(days_with_fills, trading_days_spanned) for an arm, from the real ledger."""
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    days = sorted({r["date"] for r in rows if r.get("arm") == arm and r.get("date")})
    if not days:
        return 0, 0
    return len(days), _trading_days(_date(days[0]), _date(days[-1]))


# ---------------------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------------------

def test_the_bar_is_reachable_at_the_participation_floor(designation):
    """min_days must be attainable inside the window at a realistic fill cadence.

    This is the test that would have failed on 2026-09-01 the moment the designation was
    written: 20 trading days x 0.47 = 9 expected scored days against a bar of 20.
    """
    start, end = _date(designation["window_start"]), _date(designation["window_end"])
    min_days = int(designation["min_days"])
    td = _trading_days(start, end)
    attainable = td * PARTICIPATION_FLOOR
    assert attainable >= min_days, (
        f"UNSATISFIABLE BAR: window {start}..{end} has {td} trading days; at the "
        f"{PARTICIPATION_FLOOR:.0%} participation floor that yields ~{attainable:.0f} scored "
        f"days against min_days={min_days}. A bar that cannot be reached is a broken "
        f"instrument, not a strict one -- widen the window or justify a lower min_days, and "
        f"say which of the two you changed and why (they are different questions)."
    )


def test_the_bar_could_not_require_perfect_participation(designation):
    """The specific 2026-09-01 defect: min_days == trading days in the window.

    Distinct from the test above because it names the mistake in a way a reader recognises --
    a bar equal to the window length always means 'a fill every single day', which no
    strategy that is allowed to sit out can ever satisfy.
    """
    td = _trading_days(_date(designation["window_start"]), _date(designation["window_end"]))
    min_days = int(designation["min_days"])
    assert min_days < td, (
        f"min_days={min_days} equals or exceeds the window's {td} trading days -- this "
        f"demands a fill on EVERY day, i.e. 100% participation, from an engine whose own "
        f"doctrine says sitting out is a valid day"
    )


def test_reachability_uses_a_floor_not_the_designated_arms_own_rate(designation):
    """The floor must not be tuned to whichever arm trades most. Pinned so a future edit
    cannot quietly raise it to make a marginal window pass."""
    assert PARTICIPATION_FLOOR <= 0.50, (
        "the participation floor has drifted above 50% -- at that point it is assuming the "
        "engine trades most days, which is the assumption that broke the original bar"
    )


def test_the_designated_arm_actually_clears_the_floor(designation):
    """Sanity in the other direction: if the designated arm's MEASURED participation is below
    the floor, the floor is fiction and the window is still too short for that arm."""
    if not LEDGER.exists():
        pytest.skip("ledger absent")
    arm = designation["arm"]
    filled, spanned = measured_participation(arm)
    if spanned == 0:
        pytest.skip(f"no fills recorded for {arm}")
    rate = filled / spanned
    assert rate >= PARTICIPATION_FLOOR * 0.9, (
        f"{arm} filled {filled}/{spanned} trading days ({rate:.0%}), below the "
        f"{PARTICIPATION_FLOOR:.0%} floor this reachability check assumes. Either the floor "
        f"is wrong or this arm cannot supply the evidence the criterion needs."
    )


# ---------------------------------------------------------------------------------------
# The change itself must stay honest
# ---------------------------------------------------------------------------------------

def test_the_evidence_bar_was_not_quietly_lowered(designation):
    """2026-09-02 widened the WINDOW and left min_days at 20. If a later edit lowers min_days
    instead, that is a change to the statistical content of the criterion and must be argued
    on its own terms -- not smuggled in as a calendar fix."""
    assert int(designation["min_days"]) >= 20, (
        f"min_days dropped to {designation['min_days']}. Widening a window is a calendar "
        f"question; lowering min_days is a statistics question. They must never be traded "
        f"off against each other silently -- see _superseded_2026_09_02 in the designation."
    )


def test_a_superseded_designation_records_what_changed_and_why(designation):
    """A bar that moves without a written reason is a bar nobody can audit."""
    sup = designation.get("_superseded_2026_09_02")
    if sup is None:
        pytest.skip("designation has not been superseded")
    for key in ("original", "what_changed", "why", "why_this_is_not_result_shopping",
                "authority", "revoke"):
        assert sup.get(key), f"supersession record is missing '{key}'"
    assert sup["original"].get("min_days") == int(designation["min_days"]), (
        "the supersession claims min_days was unchanged but the numbers disagree"
    )
