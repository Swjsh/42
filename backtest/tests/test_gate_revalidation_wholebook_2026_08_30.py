"""Guard tests for backtest/tools/gate_revalidation_bearish_fill_bar_wholebook_2026_08_30.py
(GATE-RECENCY-REVALIDATION whole-book A/B -- the last open sub-item of the 2026-08-08 HIGH
queue item, closing the gap GATE-REVALIDATION-FILING-2026-08-21.md named: a refused-cohort
P&L is only an UPPER bound on a gate's cost, because it ignores the downstream NOT_FLAT
effect of letting a refused entry occupy the book's one seat.

Pure unit tests on synthetic fixtures for `simulate_book_competition` (the day-level,
one-seat-at-a-time state machine) -- no live core-decisions.jsonl / OPRA cache dependency,
so these stay green regardless of what today's ledger looks like. Also pins the CURRENT
(correct, do-not-flip-without-a-fresh-scorecard) `require_bearish_fill_bar` value, same
convention as every sibling in this gate-revalidation family.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import gate_revalidation_bearish_fill_bar_wholebook_2026_08_30 as wb  # noqa: E402

BOLD_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"


def _ev(hhmm: str, kind: str, hold_min: float, pnl: float, day="2026-06-25") -> dict:
    ts = dt.datetime.fromisoformat(f"{day}T{hhmm}:00")
    return {"ts": ts, "kind": kind, "exit_time": ts + dt.timedelta(minutes=hold_min), "pnl": pnl}


# ==================================================================== simulate_book_competition
def test_taken_event_alone_credited_to_both_books():
    """A single TAKEN event with no competitor is eligible in both A and B -- the gate being
    on/off makes no difference when there's nothing else in the day."""
    events = [_ev("09:40", "TAKEN_BEAR", 20, 100.0)]
    out = wb.simulate_book_competition(events)
    d = dt.date(2026, 6, 25)
    assert out["day_pnl_a"][d] == 100.0
    assert out["day_pnl_b"][d] == 100.0
    assert out["n_gate_entries_let_in"] == 0
    assert out["n_bumped"] == 0


def test_refused_gate_event_alone_only_credited_to_book_b():
    """A single REFUSED_GATE event never enters book A (matches live GATE-ON reality) but
    DOES enter book B (GATE OFF, nothing else competing for the seat)."""
    events = [_ev("09:40", "REFUSED_GATE", 20, 50.0)]
    out = wb.simulate_book_competition(events)
    d = dt.date(2026, 6, 25)
    assert out["day_pnl_a"][d] == 0.0
    assert out["day_pnl_b"][d] == 50.0
    assert out["n_gate_entries_let_in"] == 1
    assert out["n_bumped"] == 0


def test_refused_gate_bumps_a_later_taken_event_under_book_b():
    """THE core scenario GATE-REVALIDATION-FILING-2026-08-21.md named: an early
    REFUSED_GATE entry that would have been let in under GATE-OFF occupies the seat for its
    whole hold, blocking a later TAKEN event that happened for real under GATE-ON. Book A
    should show only the taken trade; book B should show only the refused-gate trade (worse,
    since the refused trade here loses money) -- this is exactly how a gate can look
    profitable in isolation (the refused cohort alone) while the whole-book effect differs."""
    events = [
        _ev("09:40", "REFUSED_GATE", 30, -80.0),   # would occupy the seat 09:40-10:10 under B
        _ev("09:55", "TAKEN_BULL", 20, 200.0),      # real trade, inside that window
    ]
    out = wb.simulate_book_competition(events)
    d = dt.date(2026, 6, 25)
    assert out["day_pnl_a"][d] == 200.0     # book A: only the real taken trade fires
    assert out["day_pnl_b"][d] == -80.0     # book B: the gate-refused trade wins the seat
    assert out["n_gate_entries_let_in"] == 1
    assert out["n_bumped"] == 1             # the 09:55 taken trade was bumped out under B


def test_taken_event_that_arrives_after_the_gate_trade_exits_is_not_bumped():
    """If the refused-gate trade's hold ends BEFORE the next taken event's timestamp, both
    can coexist in book B -- no bump."""
    events = [
        _ev("09:40", "REFUSED_GATE", 10, -30.0),   # exits 09:50
        _ev("09:55", "TAKEN_BULL", 20, 150.0),      # starts after 09:50 -- seat is free
    ]
    out = wb.simulate_book_competition(events)
    d = dt.date(2026, 6, 25)
    assert out["day_pnl_a"][d] == 150.0
    assert out["day_pnl_b"][d] == -30.0 + 150.0
    assert out["n_bumped"] == 0


def test_two_taken_events_same_day_not_falsely_counted_as_bumped():
    """Two real TAKEN events that naturally collide (second arrives while the first is still
    open) are a normal same-book NOT_FLAT collision in BOTH books -- must not be counted as a
    B-caused bump (regression guard: an earlier draft of this state machine double-counted
    this case)."""
    events = [
        _ev("09:40", "TAKEN_BEAR", 30, 100.0),      # occupies 09:40-10:10 in BOTH books
        _ev("09:50", "TAKEN_BULL", 20, 999.0),       # collides in A too -- not a B-only bump
    ]
    out = wb.simulate_book_competition(events)
    assert out["n_bumped"] == 0
    assert out["n_gate_entries_let_in"] == 0


def test_resets_the_seat_at_each_new_calendar_day():
    """A position must not carry over an occupied seat across a day boundary -- each day
    starts flat in both books."""
    events = [
        _ev("15:50", "TAKEN_BEAR", 300, 50.0, day="2026-06-25"),   # would still be "open" at
        _ev("09:40", "TAKEN_BULL", 20, 75.0, day="2026-06-26"),     # 09:40 the next day if not reset
    ]
    out = wb.simulate_book_competition(events)
    d1, d2 = dt.date(2026, 6, 25), dt.date(2026, 6, 26)
    assert out["day_pnl_a"][d1] == 50.0
    assert out["day_pnl_a"][d2] == 75.0     # NOT bumped by the prior day's still-open position
    assert out["n_bumped"] == 0


def test_empty_input_returns_empty_books():
    out = wb.simulate_book_competition([])
    assert out["day_pnl_a"] == {}
    assert out["day_pnl_b"] == {}
    assert out["n_bumped"] == 0
    assert out["n_gate_entries_let_in"] == 0


# ==================================================================== _typed_events ==========
def test_typed_events_filters_account_verdict_armed_and_dedupes_raw_fires():
    rows = [
        {"account": "bold", "verdict": "ENTER_BEAR", "armed": True, "ts_et": "2026-06-25T09:40:00"},
        {"account": "bold", "verdict": "ENTER_BEAR", "armed": True, "ts_et": "2026-06-25T09:41:00"},  # same cluster
        {"account": "bold", "verdict": "ENTER_BEAR", "armed": False, "ts_et": "2026-06-25T10:00:00"},  # unarmed
        {"account": "safe", "verdict": "ENTER_BEAR", "armed": True, "ts_et": "2026-06-25T11:00:00"},  # wrong account
        {"account": "bold", "verdict": "HOLD", "armed": True, "ts_et": "2026-06-25T12:00:00"},  # wrong verdict
    ]
    out = wb._typed_events(rows, "bold", "ENTER_BEAR", "TAKEN_BEAR")
    assert len(out) == 1  # the two 09:40/09:41 raw fires cluster into one event
    assert out[0]["_kind"] == "TAKEN_BEAR"
    assert out[0]["ts_et"] == "2026-06-25T09:40:00"


# ==================================================================== pin the live value ======
def test_require_bearish_fill_bar_unchanged_pending_reratification():
    """GATE-RECENCY-REVALIDATION-2026-08-30-WHOLEBOOK: still NOT-UNBLOCK-ELIGIBLE (fails
    G_drop3/G_bhfdr) even after accounting for the whole-book NOT_FLAT competition effect --
    the third independent method (refused-cohort 08-08, refused-cohort-extended 08-23,
    whole-book 08-30) to reach the same verdict. Pins the CURRENT (correct) value so an
    accidental flip is caught in CI, not live."""
    params = json.loads(BOLD_PARAMS.read_text(encoding="utf-8"))
    assert params["require_bearish_fill_bar"] is True
