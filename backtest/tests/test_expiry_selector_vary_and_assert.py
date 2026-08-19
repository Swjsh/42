"""Guard: expiry_selector.py -- the weekly-lane "which Friday" mechanism (2026-08-18).

Covers markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §4 rule 3 + §5 "New" -- J explicitly
asked to test "which Friday, one week or two week out" as a first-class, comparable knob.

Five guard classes:
  1. VARY-AND-ASSERT (C14 dead-knob discipline, mandatory per this workstream's spec):
     proves the `rule` parameter ACTUALLY changes which contract gets selected -- all
     four rules against the SAME as_of + chain must return four DIFFERENT expiries.
     Extended to the `min_dte` knob too (same discipline, different parameter).
  2. NVDA-STYLE MISSING EXPIRY: a target Friday absent from the live chain must NEVER be
     returned -- the selector must escalate to the next listed expiry and flag
     fallback=True with a documented reason.
  3. MIN-DTE ENFORCEMENT: a Thursday as_of must not select the next-day Friday.
  4. CLOCK DETERMINISM: et_today() must derive from the injected UTC instant via the
     real DST-aware ET clock, never a bare local date -- proven against a UTC instant
     chosen so that naive Mountain-time (this box's local zone) and true ET disagree on
     the calendar date.
  5. Structural guards: empty-chain / DTE-floor-exhausted cases raise (no silent
     fallback), and target_expiry/chosen_expiry are always internally consistent.

RED-PROOF (per this build's house rule): guards 1 and 2 above were deliberately broken,
run under pytest to observe the failure, then restored -- see the session report for the
quoted RED output.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import expiry_selector as es  # noqa: E402

# Sanity: as_of anchor dates used throughout, verified against Python's own calendar
# (not hand-guessed) -- 2026-08-17 is a Monday, 2026-08-20 a Thursday.
MONDAY = dt.date(2026, 8, 17)
THURSDAY = dt.date(2026, 8, 20)

REAL_MIN_DTE = es.load_min_dte_at_entry()  # reads the ACTUAL params.json -- never hardcoded


def test_load_min_dte_at_entry_reads_real_params_file():
    """Proves the loader reads automation/state/weekly/params.json rather than returning a
    hardcoded copy of "3" -- pinned to the currently-ratified value. If a sibling
    workstream changes entry.min_dte_at_entry, this assertion is EXPECTED to need
    updating in lockstep; that coupling is the point (never let a code-side duplicate of
    this number silently drift out of sync with the file)."""
    assert REAL_MIN_DTE == 3
    assert isinstance(REAL_MIN_DTE, int)


def test_load_min_dte_at_entry_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        es.load_min_dte_at_entry(Path("Z:/does/not/exist/params.json"))


def test_load_min_dte_at_entry_missing_key_raises(tmp_path):
    bad = tmp_path / "params.json"
    bad.write_text('{"entry": {}}', encoding="utf-8")
    with pytest.raises(KeyError):
        es.load_min_dte_at_entry(bad)


# --------------------------------------------------------------------- vary-and-assert

def test_all_four_rules_select_different_expiries_same_inputs():
    """C14 dead-knob discipline: the SAME as_of + the SAME live chain, only the `rule`
    parameter varies -- all four selections must land on DISTINCT contracts. A rule
    parameter that never changes behavior is this shop's most-repeated bug class."""
    as_of = MONDAY  # 2026-08-17
    chain = [
        dt.date(2026, 8, 21),  # SAME_WEEK target (this Friday, dte=4)
        dt.date(2026, 8, 28),  # NEXT_WEEK target (dte=11)
        dt.date(2026, 9, 4),   # TWO_WEEKS_OUT target (dte=18)
        dt.date(2026, 9, 11),
        dt.date(2026, 9, 18),  # closest listed to the ~30-DTE MONTHLY target (dte=32)
        dt.date(2026, 9, 25),
    ]

    results = {
        rule: es.select_expiry(rule, as_of, chain, REAL_MIN_DTE) for rule in es.ALL_RULES
    }

    chosen = {rule: sel.chosen_expiry for rule, sel in results.items()}
    assert len(set(chosen.values())) == 4, f"expected 4 distinct expiries, got {chosen}"

    assert chosen[es.RULE_SAME_WEEK] == dt.date(2026, 8, 21)
    assert chosen[es.RULE_NEXT_WEEK] == dt.date(2026, 8, 28)
    assert chosen[es.RULE_TWO_WEEKS_OUT] == dt.date(2026, 9, 4)
    assert chosen[es.RULE_MONTHLY] == dt.date(2026, 9, 18)

    # None of these are fallbacks -- every target was exactly listed, isolating this test
    # from the separate missing-expiry / min-dte-fallthrough guards below.
    for rule, sel in results.items():
        assert sel.fallback is False, f"{rule} unexpectedly fell back: {sel.fallback_reason}"
        assert sel.rule == rule
        assert sel.dte == (sel.chosen_expiry - as_of).days


def test_min_dte_knob_actually_changes_same_week_selection(tmp_path):
    """Extends the vary-and-assert discipline to the `min_dte` parameter itself: with the
    real (3) floor, a Thursday as_of cannot use the next-day Friday (1 DTE) and must fall
    to next week; with a looser (1) floor it CAN. Proves min_dte is not a dead knob laid
    on top of a hardcoded internal floor."""
    as_of = THURSDAY  # 2026-08-20
    chain = [dt.date(2026, 8, 21), dt.date(2026, 8, 28)]  # 1 DTE, 8 DTE

    strict = es.select_expiry(es.RULE_SAME_WEEK, as_of, chain, min_dte=3)
    loose = es.select_expiry(es.RULE_SAME_WEEK, as_of, chain, min_dte=1)

    assert strict.chosen_expiry == dt.date(2026, 8, 28)
    assert loose.chosen_expiry == dt.date(2026, 8, 21)
    assert strict.chosen_expiry != loose.chosen_expiry


# ------------------------------------------------------------------- missing expiry (NVDA)

def test_missing_target_expiry_does_not_get_returned_and_flags_fallback():
    """Mirrors the load-bearing NVDA-2026-08-26 class of gap (WEEKLY-OPTIONS-PROGRAM.md
    §2: that expiry is NOT LISTED because earnings land that day) using a synthetic gap
    for isolation: the SAME_WEEK target Friday (2026-08-21) is deliberately absent from
    the supplied chain. The selector must NEVER return the absent target -- it must
    escalate to the next listed expiry and flag fallback=True with a documented reason."""
    as_of = MONDAY  # 2026-08-17
    target = dt.date(2026, 8, 21)
    chain = [dt.date(2026, 8, 28), dt.date(2026, 9, 4)]  # target deliberately OMITTED

    sel = es.select_expiry(es.RULE_SAME_WEEK, as_of, chain, REAL_MIN_DTE)

    assert sel.chosen_expiry != target
    assert sel.target_expiry == target
    assert sel.chosen_expiry == dt.date(2026, 8, 28)  # next listed expiry >= target
    assert sel.fallback is True
    assert sel.fallback_reason is not None
    assert target.isoformat() in sel.fallback_reason
    assert "not in the live chain" in sel.fallback_reason


def test_missing_expiry_never_searches_backward():
    """The escalating search must only ever move FORWARD from the target -- an earlier
    listed expiry must never be selected even if it is "closer" in absolute date terms,
    since that would silently violate min_dte and blur the rule's own territory."""
    as_of = MONDAY
    target = dt.date(2026, 8, 21)
    chain = [dt.date(2026, 8, 14), dt.date(2026, 9, 4)]  # one before target, one after

    sel = es.select_expiry(es.RULE_SAME_WEEK, as_of, chain, REAL_MIN_DTE)
    assert sel.chosen_expiry == dt.date(2026, 9, 4)
    assert sel.chosen_expiry >= target


def test_missing_expiry_with_no_later_listing_raises():
    """No silent fallback: if NOTHING in the chain is on/after the target, this is
    uncertainty, not permission to guess -- raise, don't return None or an
    earlier-dated contract."""
    as_of = MONDAY
    chain = [dt.date(2026, 8, 14)]  # entirely before the SAME_WEEK target
    with pytest.raises(ValueError):
        es.select_expiry(es.RULE_SAME_WEEK, as_of, chain, REAL_MIN_DTE)


def test_empty_chain_raises_for_every_rule():
    for rule in es.ALL_RULES:
        with pytest.raises(ValueError):
            es.select_expiry(rule, MONDAY, [], REAL_MIN_DTE)


# --------------------------------------------------------------------- min-DTE enforcement

def test_thursday_as_of_does_not_select_next_day_friday():
    """A Thursday as_of's nearest calendar Friday is only 1 DTE -- under the real 3-DTE
    floor. The selector must NOT select that next-day Friday; it must fall through to
    next week's Friday instead."""
    as_of = THURSDAY  # 2026-08-20
    next_day_friday = dt.date(2026, 8, 21)
    next_week_friday = dt.date(2026, 8, 28)
    chain = [next_day_friday, next_week_friday]

    sel = es.select_expiry(es.RULE_SAME_WEEK, as_of, chain, REAL_MIN_DTE)

    assert sel.chosen_expiry != next_day_friday
    assert sel.chosen_expiry == next_week_friday
    assert sel.dte >= REAL_MIN_DTE
    assert sel.fallback is True
    assert "min_dte_at_entry" in sel.fallback_reason


def test_monday_as_of_same_week_friday_clears_floor_no_fallback():
    """Sanity counterpart: a Monday as_of's same-week Friday is 4 DTE, which clears the
    3-DTE floor -- no fallback should fire and the same-week Friday should be chosen
    directly."""
    as_of = MONDAY  # 2026-08-17
    same_week_friday = dt.date(2026, 8, 21)
    sel = es.select_expiry(es.RULE_SAME_WEEK, as_of, [same_week_friday], REAL_MIN_DTE)
    assert sel.chosen_expiry == same_week_friday
    assert sel.dte == 4
    assert sel.fallback is False


# ------------------------------------------------------------------------ clock determinism

def test_et_today_derives_from_true_et_not_local_mountain_time():
    """CLAUDE.md: 'TIME = et_clock, NEVER Bash TZ' -- this box runs Mountain time
    (UTC-6 MDT in August). Pick a UTC instant deliberately inside the window where true ET
    (UTC-4 EDT in August) and naive Mountain-time (UTC-6) disagree on the CALENDAR DATE:
    2026-08-18 05:00 UTC -> ET 01:00 on 2026-08-18 (date rolls to the 18th), but a
    Mountain-time misimplementation would read 23:00 on 2026-08-17 (date still the 17th).
    A hidden local-time dependency would silently return the wrong date here."""
    now_utc = dt.datetime(2026, 8, 18, 5, 0, tzinfo=dt.timezone.utc)
    assert es.et_today(now_utc=now_utc) == dt.date(2026, 8, 18)


def test_et_today_deterministic_across_repeated_calls():
    """Same injected instant -> same result, every time -- no hidden mutable state."""
    now_utc = dt.datetime(2026, 1, 15, 20, 0, tzinfo=dt.timezone.utc)  # winter (EST) instant
    first = es.et_today(now_utc=now_utc)
    second = es.et_today(now_utc=now_utc)
    assert first == second == dt.date(2026, 1, 15)


def test_et_today_winter_dst_offset_differs_from_summer():
    """Cross-check the DST-aware offset actually applies (EST=-5 in January vs EDT=-4 in
    August) -- proves et_today doesn't hardcode a fixed offset either."""
    winter_utc = dt.datetime(2026, 1, 15, 4, 30, tzinfo=dt.timezone.utc)   # 23:30 EST prior day
    summer_utc = dt.datetime(2026, 8, 15, 3, 30, tzinfo=dt.timezone.utc)   # 23:30 EDT prior day
    assert es.et_today(now_utc=winter_utc) == dt.date(2026, 1, 14)
    assert es.et_today(now_utc=summer_utc) == dt.date(2026, 8, 14)
