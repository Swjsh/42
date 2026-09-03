"""Guards for AUTONOMY-METRIC-ZERO-ENTERS-08-31 (automation/overnight/queue.md,
resolved 2026-09-03).

WHAT THIS GUARDS: `conductor_outcome.py`'s `_trend()` used to label ANY
zero-enter day "regressing" without asking whether the zero was a
doctrine-sanctioned gate refusal (`feedback_sitting_out_is_a_valid_day_2026_08_12`)
rather than a funnel miss. The 2026-08-31 replay
(analysis/deep-research/BEAR-08-31-NO-TRIGGER-REPLAY.md) found all 55
bear-score>=9 ticks that day were refused by blocker 8 (the ratified VIX-floor
gate) -- a sanctioned sit-out, not a defect. `_grade_zero_enter_day()` now
grades a zero-enter trading day SAT_OUT_GATED / QUIET / regressing from
core-decisions.jsonl, and `_trend()` treats SAT_OUT_GATED/QUIET as neutral
(excluded from the function-score comparison) rather than as a regression.

These tests RED if:
  1. a fully-gate-refused high-score day (>=100 RTH ticks) stops grading
     SAT_OUT_GATED, or its blocker-id reason regresses.
  2. a day with 0 high-score ticks stops grading QUIET.
  3. a day with an UNblocked high-score tick (funnel miss) stops grading
     regressing (the one grade that must still count as a regression signal).
  4. a SAT_OUT_GATED/QUIET zero-enter day starts dragging the trend to
     "regressing" again (the actual behavioral fix).
  5. the pre-existing byte-identical path (a day WITH enters, or no ledger
     fixture at all) changes shape.

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_conductor_outcome_zero_enter_grading_2026_09_03.py -q
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "setup" / "scripts" / "conductor_outcome.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("conductor_outcome_zerograde", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def co(tmp_path, monkeypatch):
    """Module with ALL path constants redirected to tmp_path."""
    mod = _load_module()
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUTCOMES_FILE", tmp_path / "conductor-outcomes.jsonl")
    monkeypatch.setattr(mod, "METRIC_FILE", tmp_path / "autonomy-metric.json")
    monkeypatch.setattr(mod, "DECISIONS_FILE", tmp_path / "core-decisions.jsonl")
    monkeypatch.setattr(mod, "FLEET_DIR", tmp_path / "fleet")
    monkeypatch.setattr(mod, "TRADES_CSV", tmp_path / "trades.csv")
    return mod


def _row(date, *, bear_score=5, bull_score=5, bear_blockers=None, bull_blockers=None,
         account="safe"):
    return {
        "ts_et": f"{date}T10:00:00",
        "date": date,
        "account": account,
        "verdict": "HOLD",
        "bear_score": bear_score,
        "bull_score": bull_score,
        "bear_blockers": bear_blockers or [],
        "bull_blockers": bull_blockers or [],
    }


def _write_decisions(co, rows):
    co.DECISIONS_FILE.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Shape 1: SAT_OUT_GATED -- >=100 ticks, high-score ticks, every one blocked.
# ---------------------------------------------------------------------------
def test_grade_sat_out_gated_full_session_all_blocked(co):
    day = "2026-08-31"
    rows = [_row(day, bear_score=3, bull_score=3) for _ in range(97)]
    rows += [
        _row(day, bear_score=9, bull_score=3, bear_blockers=[8]),
        _row(day, bear_score=9, bull_score=3, bear_blockers=[8]),
        _row(day, bear_score=10, bull_score=3, bear_blockers=[8, 9]),
    ]
    _write_decisions(co, rows)
    grade = co._grade_zero_enter_day(day)
    assert grade is not None
    assert grade["grade"] == "SAT_OUT_GATED"
    assert grade["ticks"] == 100
    assert grade["high_score_ticks"] == 3
    assert "blocker 8" in grade["reason"]


def test_grade_sat_out_gated_too_few_ticks_is_ungraded(co):
    # Same all-blocked shape but under the 100-tick floor -- must NOT claim
    # SAT_OUT_GATED on a half day / short outage.
    day = "2026-08-31"
    rows = [_row(day, bear_score=3, bull_score=3) for _ in range(10)]
    rows += [_row(day, bear_score=9, bull_score=3, bear_blockers=[8])]
    _write_decisions(co, rows)
    grade = co._grade_zero_enter_day(day)
    assert grade is None


# ---------------------------------------------------------------------------
# Shape 2: QUIET -- 0 high-score ticks all day.
# ---------------------------------------------------------------------------
def test_grade_quiet_no_high_score_ticks(co):
    day = "2026-09-01"
    rows = [_row(day, bear_score=4, bull_score=5) for _ in range(150)]
    _write_decisions(co, rows)
    grade = co._grade_zero_enter_day(day)
    assert grade is not None
    assert grade["grade"] == "QUIET"
    assert grade["high_score_ticks"] == 0
    assert grade["ticks"] == 150


def test_grade_no_ledger_rows_is_ungraded_not_quiet(co):
    # No core-decisions.jsonl rows for the day at all (file missing/empty) --
    # nothing to grade, must return None (never QUIET, which would falsely
    # claim "checked and found nothing").
    _write_decisions(co, [_row("2026-01-01")])  # different day
    grade = co._grade_zero_enter_day("2026-09-02")
    assert grade is None


# ---------------------------------------------------------------------------
# Shape 3: regressing -- a high-score tick with NO blocker recorded (funnel miss).
# ---------------------------------------------------------------------------
def test_grade_regressing_when_a_high_score_tick_is_unblocked(co):
    day = "2026-08-30"
    rows = [_row(day, bear_score=3, bull_score=3) for _ in range(120)]
    rows += [
        _row(day, bear_score=9, bull_score=3, bear_blockers=[8]),
        _row(day, bear_score=9, bull_score=3, bear_blockers=[]),  # NO blocker -- funnel miss
    ]
    _write_decisions(co, rows)
    grade = co._grade_zero_enter_day(day)
    assert grade is not None
    assert grade["grade"] == "regressing"
    assert "NO gate blocker recorded" in grade["reason"]
    assert grade["high_score_ticks"] == 2


# ---------------------------------------------------------------------------
# Shape 4 (the actual fix): SAT_OUT_GATED/QUIET zero-enter days do not
# manufacture a "regressing" trend; a genuine funnel-miss zero-enter day still
# does.
# ---------------------------------------------------------------------------
def _snap(*, day, enters=0, accepted=0, fills=0, setups=0):
    return {
        "trading_day": day,
        "enters_last_trading_day": enters,
        "orders_accepted": accepted,
        "fills": fills,
        "distinct_setups_traded": setups,
    }


def test_sat_out_gated_zero_enter_day_does_not_regress_the_trend(co):
    # Older half: two real-trading days (positive function score).
    co.record(task_id="o1", items_drained=1, function_snapshot=_snap(day="2026-08-27", enters=2, accepted=1, fills=1))
    co.record(task_id="o2", items_drained=1, function_snapshot=_snap(day="2026-08-28", enters=2, accepted=1, fills=1))
    # Recent half: two zero-enter days, BOTH gate-sanctioned sit-outs.
    co.record(task_id="r1", items_drained=1, function_snapshot=_snap(day="2026-08-31", enters=0))
    co.record(task_id="r2", items_drained=1, function_snapshot=_snap(day="2026-09-01", enters=0))
    rows = [_row("2026-08-31", bear_score=3, bull_score=3) for _ in range(97)]
    rows += [_row("2026-08-31", bear_score=9, bull_score=3, bear_blockers=[8]) for _ in range(3)]
    rows += [_row("2026-09-01", bear_score=3, bull_score=3) for _ in range(97)]
    rows += [_row("2026-09-01", bear_score=9, bull_score=3, bear_blockers=[8]) for _ in range(3)]
    _write_decisions(co, rows)

    metric = co.compute_metric(window=20)
    # Both halves drained equally (1 each) -> net_improvement ties -> "flat",
    # never "regressing" purely because the recent half traded zero times.
    assert metric["trend"] != "regressing"
    assert metric["trend"] == "flat"
    assert metric["zero_enter_day_grade"] is not None
    assert metric["zero_enter_day_grade"]["grade"] == "SAT_OUT_GATED"
    assert metric["zero_enter_day_grade"]["trading_day"] == "2026-09-01"


def test_quiet_zero_enter_day_does_not_regress_the_trend(co):
    co.record(task_id="o1", items_drained=1, function_snapshot=_snap(day="2026-08-27", enters=2, accepted=1, fills=1))
    co.record(task_id="o2", items_drained=1, function_snapshot=_snap(day="2026-08-28", enters=2, accepted=1, fills=1))
    co.record(task_id="r1", items_drained=1, function_snapshot=_snap(day="2026-09-02", enters=0))
    rows = [_row("2026-09-02", bear_score=4, bull_score=4) for _ in range(50)]
    _write_decisions(co, rows)

    metric = co.compute_metric(window=20)
    assert metric["trend"] != "regressing"
    assert metric["zero_enter_day_grade"]["grade"] == "QUIET"


def test_funnel_miss_zero_enter_day_still_regresses_the_trend(co):
    # This is the negative control: a genuine funnel miss (unblocked
    # high-score tick) must NOT be swallowed by the fix -- it stays a real
    # regression signal, same as before this change.
    co.record(task_id="o1", items_drained=0, function_snapshot=_snap(day="2026-08-27", enters=2, accepted=1, fills=1))
    co.record(task_id="o2", items_drained=0, function_snapshot=_snap(day="2026-08-28", enters=2, accepted=1, fills=1))
    co.record(task_id="r1", items_drained=0, function_snapshot=_snap(day="2026-08-30", enters=0))
    co.record(task_id="r2", items_drained=0, function_snapshot=_snap(day="2026-08-30", enters=0))
    rows = [_row("2026-08-30", bear_score=3, bull_score=3) for _ in range(120)]
    rows += [_row("2026-08-30", bear_score=9, bull_score=3, bear_blockers=[])]  # unblocked
    _write_decisions(co, rows)

    metric = co.compute_metric(window=20)
    assert metric["trend"] == "regressing"
    assert metric["zero_enter_day_grade"]["grade"] == "regressing"


# ---------------------------------------------------------------------------
# Shape 5: unchanged path -- a day WITH enters carries zero_enter_day_grade
# = None and all pre-existing fields stay exactly as computed before this fix.
# ---------------------------------------------------------------------------
def test_unchanged_path_day_with_enters_grade_is_none(co):
    co.record(task_id="a", function_snapshot=_snap(day="2026-09-02", enters=5, accepted=2, fills=1, setups=2))
    metric = co.compute_metric(window=20)
    assert metric["zero_enter_day_grade"] is None
    # pinned exactly as test_metric_carries_function_fields in
    # test_conductor_outcome_function.py asserts (byte-identical values).
    assert metric["function_latest"]["enters_last_trading_day"] == 5
    assert metric["function_latest"]["orders_accepted"] == 2
    assert metric["function_latest"]["fills"] == 1
    assert metric["function_latest"]["distinct_setups_traded"] == 2
    assert metric["function_latest"]["trading_day"] == "2026-09-02"
    assert metric["function_score_avg"] == 12.0
    assert metric["trend"] == "flat"


def test_unchanged_path_no_ledger_fixture_pins_old_trend_shape(co):
    # No core-decisions.jsonl written at all -- _grade_zero_enter_day must
    # return None for every zero-enter day (ticks==0), so filtering is a
    # no-op and the trend math is IDENTICAL to the pre-fix implementation.
    co.record(task_id="o1", items_drained=3, function_snapshot=_snap(day="2026-06-29"))
    co.record(task_id="o2", items_drained=3, function_snapshot=_snap(day="2026-06-30"))
    co.record(task_id="r1", items_drained=0, function_snapshot=_snap(day="2026-07-01"))
    co.record(task_id="r2", items_drained=0, function_snapshot=_snap(day="2026-07-02"))
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "regressing"
    assert metric["zero_enter_day_grade"] is None
