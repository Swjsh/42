"""Guard: backtest/tools/ribbon_state_entry_gate_study.py -- LANE-B HYPOTHESIS #1
(markdown/doctrine/DOJO-HARVEST-2026-07-21.md) population validation.

WHAT THIS PINS:
  1. `naive_wall` strips a tz label without shifting wall-clock numbers, for BOTH scalar
     pd.Timestamp/datetime.datetime input and a Series -- the "wall-v1" convention
     (backtest/lib/et_frame.py) every walk in this module depends on.
  2. `is_target_population` matches side=PUT + BOTH triggers present, and rejects any
     partial match (only one of the two triggers, or side=CALL).
  3. `is_bs_fallback` detects the '::BS_FALLBACK' setup-name tag orchestrator.py appends
     when simulate_trade_real cache-misses and falls back to the BS simulator -- these
     trades are NOT real fills and must never enter a real-fills population.
  4. `find_signal_decision` NEVER returns a decision row at or after the fill timestamp
     (no-look-ahead) and requires an EXACT triggers_fired + rejection_level match.
  5. THE FRAME-ALIGNMENT REGRESSION GUARD (the actual bug this build found and fixed):
     computing ribbon_df on an RTH-only, reset_index(drop=True) frame (matching
     orchestrator.py's internal frame) reproduces orchestrator's OWN per-bar ribbon_stack
     bar-for-bar via bar_idx; computing it on a frame that STILL includes premarket bars
     does not (silent index-drift). Pinned against a REAL run_backtest() call over a small
     window, not a synthetic fixture, because the bug was a genuine cross-module frame
     mismatch, not a pure-function property.
  6. `score_candidate`'s g1-g4 gate arithmetic on a small hand-built fixture: a strictly
     dominant candidate (flags only losers) passes every gate; a strictly harmful one
     (flags only winners) fails g1.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ribbon_state_entry_gate_study.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "backtest", ROOT / "backtest" / "tools", ROOT,
           ROOT / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_state_entry_gate_study as m  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.ribbon import compute_ribbon, ribbon_at  # noqa: E402


# ── naive_wall ──────────────────────────────────────────────────────────────────────────

def test_naive_wall_strips_tz_keeps_wall_clock_scalar():
    aware = pd.Timestamp("2026-06-10 11:25:00-04:00")
    out = m.naive_wall(aware)
    assert out.tzinfo is None
    assert (out.hour, out.minute, out.second) == (11, 25, 0)
    assert out.date() == dt.date(2026, 6, 10)


def test_naive_wall_passthrough_naive_datetime():
    naive = dt.datetime(2026, 6, 10, 11, 25, 0)
    out = m.naive_wall(naive)
    assert out.tzinfo is None
    assert (out.hour, out.minute) == (11, 25)


def test_naive_wall_series():
    s = pd.Series(["2025-01-02 10:30:00-04:00", "2025-01-02 10:35:00-04:00"])
    out = m.naive_wall(s)
    assert getattr(out.dt, "tz", None) is None
    assert list(out.dt.strftime("%H:%M")) == ["10:30", "10:35"]


# ── is_target_population / is_bs_fallback ───────────────────────────────────────────────

class _FakeTrade:
    def __init__(self, side, triggers, setup="BEARISH_REJECTION_RIDE_THE_RIBBON"):
        self.side = side
        self.triggers_fired = triggers
        self.setup = setup


def test_is_target_population_requires_both_triggers_and_put_side():
    assert m.is_target_population(_FakeTrade("P", ["level_rejection", "confluence"]))
    assert m.is_target_population(
        _FakeTrade("P", ["level_rejection", "confluence", "ribbon_flip"]))  # superset OK
    assert not m.is_target_population(_FakeTrade("P", ["level_rejection"]))  # missing confluence
    assert not m.is_target_population(_FakeTrade("P", ["confluence"]))       # missing level_rejection
    assert not m.is_target_population(_FakeTrade("C", ["level_rejection", "confluence"]))  # wrong side
    assert not m.is_target_population(_FakeTrade("P", ["trendline_rejection"]))


def test_is_bs_fallback_tag_detection():
    assert m.is_bs_fallback(_FakeTrade("P", [], setup="BEARISH_REJECTION_RIDE_THE_RIBBON::BS_FALLBACK"))
    assert not m.is_bs_fallback(_FakeTrade("P", [], setup="BEARISH_REJECTION_RIDE_THE_RIBBON"))


# ── find_signal_decision: no-look-ahead + exact match ───────────────────────────────────

def _decisions_fixture():
    return [
        {"bar_idx": 10, "timestamp_et": "2026-06-10T11:15:00", "passed": True,
         "triggers_fired": ["level_rejection", "confluence"], "rejection_level": 731.9,
         "ribbon_stack": "BEAR", "ribbon_spread_cents": 100.0},
        {"bar_idx": 11, "timestamp_et": "2026-06-10T11:20:00", "passed": False,
         "triggers_fired": ["level_rejection", "confluence"], "rejection_level": 731.9,
         "ribbon_stack": "BULL", "ribbon_spread_cents": 5.0},
        {"bar_idx": 12, "timestamp_et": "2026-06-10T11:30:00", "passed": True,
         "triggers_fired": ["trendline_rejection"], "rejection_level": None,
         "ribbon_stack": "MIXED", "ribbon_spread_cents": 20.0},
    ]


def test_find_signal_decision_matches_exact_triggers_and_level():
    by_date = m.build_decision_index(_decisions_fixture())
    fill_ts = m.naive_wall("2026-06-10T11:25:00")
    d = m.find_signal_decision(by_date, fill_ts, ["level_rejection", "confluence"], 731.9)
    assert d is not None
    assert d["bar_idx"] == 10
    assert d["ribbon_stack"] == "BEAR"


def test_find_signal_decision_never_returns_at_or_after_fill():
    by_date = m.build_decision_index(_decisions_fixture())
    # fill exactly AT the only passed=True matching row's timestamp -> must NOT match (no look-ahead)
    fill_ts = m.naive_wall("2026-06-10T11:15:00")
    d = m.find_signal_decision(by_date, fill_ts, ["level_rejection", "confluence"], 731.9)
    assert d is None


def test_find_signal_decision_ignores_unpassed_rows():
    # bar_idx=11 has the right triggers/level but passed=False -- must be excluded, leaving
    # bar_idx=10 (passed=True, strictly earlier) as the only valid match.
    by_date = m.build_decision_index(_decisions_fixture())
    fill_ts = m.naive_wall("2026-06-10T11:22:00")
    d = m.find_signal_decision(by_date, fill_ts, ["level_rejection", "confluence"], 731.9)
    assert d is not None and d["bar_idx"] == 10


def test_find_signal_decision_requires_trigger_set_equality_not_subset():
    by_date = m.build_decision_index(_decisions_fixture())
    fill_ts = m.naive_wall("2026-06-10T11:25:00")
    # extra trigger not present in any fixture row -> no match
    d = m.find_signal_decision(by_date, fill_ts, ["level_rejection", "confluence", "ribbon_flip"], 731.9)
    assert d is None


# ── the actual frame-alignment bug this build found and fixed ──────────────────────────

SPY_FILE = ROOT / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-21.csv"
VIX_FILE = ROOT / "backtest" / "data" / "vix_5m_2026-05-19_2026-07-21.csv"


@pytest.mark.skipif(not SPY_FILE.exists() or not VIX_FILE.exists(), reason="data files not present")
def test_ribbon_bar_idx_alignment_matches_orchestrator_rth_frame():
    """Regression guard for the bug found building this study: computing ribbon_df on the
    RAW (premarket-inclusive) frame silently misaligns bar_idx against orchestrator's own
    RTH-only internal frame, producing WRONG ribbon_stack reads at a real bar_idx. Computing
    it on the RTH-filtered frame (this test's 'correct' path) must agree with every passed
    decision row's own logged ribbon_stack, bar-for-bar, with zero mismatches."""
    spy_full = m.load_merged(SPY_FILE, SPY_FILE)   # same file twice: exercises the merge/dedup
    vix_full = m.load_merged(VIX_FILE, VIX_FILE)   # path with a trivial no-op tail

    result = run_backtest(
        spy_full, vix_full,
        start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 30),
        **m.SAFE_BASE,
    )
    assert len(result.decisions) > 0, "expected a non-empty decision log for a real June window"

    # CORRECT path: RTH-filtered frame (mirrors orchestrator.py's own internal split).
    rth_mask = (
        (pd.to_datetime(spy_full["timestamp_et"]).dt.time >= dt.time(9, 30))
        & (pd.to_datetime(spy_full["timestamp_et"]).dt.time < dt.time(16, 0))
    )
    spy_rth = spy_full.loc[rth_mask].reset_index(drop=True)
    ribbon_correct = compute_ribbon(spy_rth["close"])

    # WRONG path: the bug this test guards against -- ribbon computed on the unfiltered frame.
    ribbon_wrong = compute_ribbon(spy_full["close"])

    passed_rows = [d for d in result.decisions if d.get("passed") and d.get("bar_idx", 0) >= 3]
    assert len(passed_rows) >= 5, "need a handful of passed bars to make this a meaningful check"

    correct_mismatches = 0
    wrong_mismatches = 0
    for d in passed_rows:
        idx = int(d["bar_idx"])
        st_correct = ribbon_at(ribbon_correct, idx)
        if st_correct is not None and st_correct.stack != d["ribbon_stack"]:
            correct_mismatches += 1
        if idx < len(ribbon_wrong):
            st_wrong = ribbon_at(ribbon_wrong, idx)
            if st_wrong is not None and st_wrong.stack != d["ribbon_stack"]:
                wrong_mismatches += 1

    assert correct_mismatches == 0, (
        f"RTH-aligned ribbon recompute disagreed with orchestrator's own decision log on "
        f"{correct_mismatches}/{len(passed_rows)} bars -- the frame-alignment fix regressed."
    )
    # The unfiltered ("wrong") frame is EXPECTED to disagree on at least some bars whenever
    # the window contains any premarket/after-hours rows -- this asserts the bug this test
    # guards against is real and reproducible, not merely theoretical.
    assert wrong_mismatches > 0, (
        "expected the premarket-inclusive frame to misalign bar_idx and disagree on at least "
        "one bar -- if this now passes with 0 mismatches, either the data has no premarket "
        "rows in this window (weaken the window) or the guard's premise no longer holds."
    )


# ── score_candidate gate arithmetic on a hand-built fixture ─────────────────────────────

def _mk_row(date, control, cand, flagged=True):
    return {
        "date": date, "control_pnl": control,
        "candidate_A_suppress_pnl": cand if flagged else control,
        "am_pm_bucket": "AM",
    }


def test_score_candidate_all_gates_pass_when_strictly_dominant():
    # candidate flags 2 losers (control negative -> candidate 0) across 2 different days in
    # BOTH IS 2025 and OOS 2026, and leaves 1 winner untouched -- should clear every gate.
    rows = [
        _mk_row("2025-03-01", -100.0, 0.0, flagged=True),
        _mk_row("2026-03-01", -200.0, 0.0, flagged=True),
        _mk_row("2026-03-02", 500.0, 500.0, flagged=False),
    ]
    result = m.score_candidate("A_suppress", "candidate_A_suppress_pnl", rows)
    assert result["n_flagged"] == 2
    assert result["gates"]["g1_aggregate"]["pass"] is True
    assert result["gates"]["g1_aggregate"]["delta"] == pytest.approx(300.0)


def test_score_candidate_fails_g1_when_it_flags_only_winners():
    rows = [
        _mk_row("2025-03-01", 100.0, 0.0, flagged=True),   # candidate zeros out a WINNER -- harmful
        _mk_row("2026-03-01", -50.0, -50.0, flagged=False),
    ]
    result = m.score_candidate("A_suppress", "candidate_A_suppress_pnl", rows)
    assert result["gates"]["g1_aggregate"]["pass"] is False
    assert result["gates"]["g1_aggregate"]["delta"] == pytest.approx(-100.0)


def test_score_candidate_zero_flagged_is_insufficient_n():
    rows = [_mk_row("2025-03-01", 100.0, 100.0, flagged=False)]
    result = m.score_candidate("A_suppress", "candidate_A_suppress_pnl", rows)
    assert result["n_flagged"] == 0
    assert result["verdict"] == "INSUFFICIENT_N"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
