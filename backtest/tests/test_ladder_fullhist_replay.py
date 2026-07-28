"""Guard tests for backtest/tools/ladder_fullhist_replay.py -- the SCORE LADDER full-history
proof engine (analysis-only, no orders, no live config touched).

Per task spec, three guards (fast, pure-function-level -- do NOT re-run the full 386-day
replay; that is exercised manually via `python backtest/tools/ladder_fullhist_replay.py`):

  1. CALIBRATION -- the 2026-07-27 09:40 pinned ground truth (bear_score=9/blockers=[5]/
     rejection_level=744.9) reports an EXACT match; a hand-built off-by-one row (the tool's
     OWN empirically-verified general-pipeline output: bear_score=8/blockers=[5,9]/
     rejection_level=745.0) reports "roughly reproduces" but NOT exact -- RED-proofed by
     showing exact_match is actually sensitive to the inputs (not vacuously True/False).
  2. ENTRY+1 CONVENTION -- the trigger bar's own option quote is never eligible as the entry
     price; the NEXT SPY bar's corresponding option bar's OPEN is used. RED-proofed by a decoy
     value planted on the trigger bar's own option row (must never be picked) and a case
     where NO bar exists at/after the next SPY bar (must exclude, never fall back).
  3. ONE-POSITION-AT-A-TIME (NOT_FLAT) DISCIPLINE -- a second candidate whose trigger bar
     falls inside an already-open synthetic position's holding window must never enter.
     RED-proofed by asserting exactly 1 trade results from 2 qualifying candidates.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
TOOLS_DIR = REPO / "backtest" / "tools"
for _p in (str(REPO), str(FLEET_DIR), str(TOOLS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
import ladder_fullhist_replay as lfr  # noqa: E402


def _mk_naive_frame(day: dt.date, times: list[dt.time], closes: list[float]) -> pd.DataFrame:
    rows = [{"timestamp_et": pd.Timestamp(dt.datetime.combine(day, t)), "close": c}
            for t, c in zip(times, closes)]
    return pd.DataFrame(rows)


def _mk_opt_bar(day: dt.date, t: dt.time, open_: float) -> dict:
    return {"timestamp_et": pd.Timestamp(dt.datetime.combine(day, t)), "open": open_,
            "high": open_, "low": open_, "close": open_, "volume": 1, "vwap": open_,
            "trade_count": 1}


EMPTY_RIBBON_LOOKUP = pd.DataFrame({
    "timestamp_et": pd.Series([], dtype="datetime64[ns]"), "stack": pd.Series([], dtype=object),
})


# =============================================================================== 1. calibration

def test_calibration_2026_07_27_0940_pinned_ground_truth_is_exact_match():
    idx = 42
    row = {"bar_idx": idx, "timestamp_et": dt.datetime(2026, 7, 27, 9, 40),
           "bear_score": 9, "blockers": [5], "triggers_fired": ["level_rejection"],
           "rejection_level": 744.9, "passed": False}
    cal = lfr.check_calibration([row], {idx: False})
    assert cal["found"] is True
    assert cal["exact_match_pinned_ground_truth"] is True
    assert cal["roughly_reproduces"] is True
    assert cal["floor_7_would_qualify"] is True
    assert cal["floor_8_would_qualify"] is True
    assert cal["floor_9_would_qualify"] is True


def test_calibration_general_pipeline_output_roughly_reproduces_but_not_exact():
    """The tool's OWN actual general-pipeline output for this bar (empirically verified when
    building this tool, see ladder_fullhist_replay.py's module docstring): bear_score=8,
    blockers=[5,9], rejection_level=745.0 -- the SAME known feed-provenance gap
    arm_score_ladder_replay.py root-caused same day. RED-proof: this must NOT be reported as
    an exact match (proving exact_match is sensitive to its inputs, not hardcoded True)."""
    idx = 43
    row = {"bar_idx": idx, "timestamp_et": dt.datetime(2026, 7, 27, 9, 40),
           "bear_score": 8, "blockers": [5, 9], "triggers_fired": ["level_rejection"],
           "rejection_level": 745.0, "passed": False}
    cal = lfr.check_calibration([row], {idx: False})
    assert cal["found"] is True
    assert cal["exact_match_pinned_ground_truth"] is False
    assert cal["roughly_reproduces"] is True
    assert cal["floor_7_would_qualify"] is True
    assert cal["floor_8_would_qualify"] is True
    assert cal["floor_9_would_qualify"] is False, "score 8 must NOT clear the floor-9 lane"


def test_calibration_missing_bar_is_disclosed_not_fabricated():
    cal = lfr.check_calibration([], {})
    assert cal["found"] is False


def test_ladder_candidate_red_proof_bull_passed_blocks_it():
    """If the bull side ALSO passed this tick (production would ENTER_BULL, not emit a plain
    HOLD), the ladder candidate filter must reject it -- proves is_ladder_candidate actually
    reads bull_passed rather than ignoring it (mirrors _ladder_block_from_row's 'neither bear
    nor bull' requirement)."""
    row = {"bar_idx": 1, "timestamp_et": dt.datetime(2026, 7, 27, 9, 40), "bear_score": 9,
           "blockers": [5], "triggers_fired": ["level_rejection"], "rejection_level": 744.9,
           "passed": False}
    assert lfr.is_ladder_candidate(row, bull_passed=False) is True
    assert lfr.is_ladder_candidate(row, bull_passed=True) is False


def test_ladder_candidate_requires_production_level_tied_set_not_the_broader_research_set():
    """trendline_rejection is level-tied in arm_score_ladder_replay.py's own research set but
    is explicitly EXCLUDED from build_shared_signal.LADDER_LEVEL_TIED (the production gate
    this tool must mirror) -- a bar whose ONLY trigger is trendline_rejection must be OUT."""
    row = {"bar_idx": 2, "timestamp_et": dt.datetime(2026, 7, 27, 9, 40), "bear_score": 9,
           "blockers": [5], "triggers_fired": ["trendline_rejection"], "rejection_level": 744.9,
           "passed": False}
    assert lfr.is_ladder_candidate(row, bull_passed=False) is False


# =============================================================================== 2. entry+1

def test_entry_plus_one_uses_next_bar_open_not_trigger_bars_own_quote():
    day = dt.date(2099, 1, 6)
    spy_rth = _mk_naive_frame(day, [dt.time(9, 35), dt.time(9, 40), dt.time(9, 45)],
                               [600.0, 600.0, 600.0])
    # decoy at the TRIGGER bar's own timestamp (09:35) -- must never be picked.
    opt_bars = pd.DataFrame([
        _mk_opt_bar(day, dt.time(9, 35), 99.0),
        _mk_opt_bar(day, dt.time(9, 40), 1.5),
    ])
    res = lfr.resolve_ladder_entry(spy_rth, 0, strike=600, trade_date=day, vix_now=15.0,
                                    spot=600.0, opt_loader=lambda sym: opt_bars)
    assert res["ok"] is True
    assert res["entry_premium"] == 1.5, (
        "must be the NEXT bar's open (1.5), not the trigger bar's own decoy quote (99.0)")
    assert res["entry_time_et"] == dt.datetime.combine(day, dt.time(9, 40))


def test_entry_plus_one_red_proof_trigger_bars_own_quote_never_falls_back():
    """If the option cache has ONLY the trigger bar's own bar (nothing at/after the next SPY
    bar), the candidate must be EXCLUDED -- never silently fall back to the entry-ineligible
    trigger-bar quote."""
    day = dt.date(2099, 1, 7)
    spy_rth = _mk_naive_frame(day, [dt.time(9, 35), dt.time(9, 40)], [600.0, 600.0])
    opt_bars = pd.DataFrame([_mk_opt_bar(day, dt.time(9, 35), 99.0)])
    res = lfr.resolve_ladder_entry(spy_rth, 0, strike=600, trade_date=day, vix_now=15.0,
                                    spot=600.0, opt_loader=lambda sym: opt_bars)
    assert res["ok"] is False
    assert res["reason"] == "opra_cached_but_no_bar_at_or_after_next"
    assert res["synthetic_entry_premium"] is not None, "still disclosed for transparency"


def test_next_bar_same_day_none_at_day_boundary():
    day = dt.date(2099, 1, 8)
    next_day = dt.date(2099, 1, 9)
    frame = pd.concat([
        _mk_naive_frame(day, [dt.time(15, 30), dt.time(15, 35)], [600.0, 600.0]),
        _mk_naive_frame(next_day, [dt.time(9, 30)], [601.0]),
    ], ignore_index=True)
    assert lfr.next_bar_same_day(frame, 0) == 1          # 15:30 -> 15:35, same day
    assert lfr.next_bar_same_day(frame, 1) is None        # 15:35 -> next row is a DIFFERENT day
    assert lfr.next_bar_same_day(frame, 2) is None        # last row in the frame, no next row


# =============================================================================== 3. one-position

def test_one_position_at_a_time_blocks_overlapping_second_candidate():
    day = dt.date(2099, 1, 5)
    spy_rth = _mk_naive_frame(
        day, [dt.time(9, 35), dt.time(9, 40), dt.time(9, 45), dt.time(9, 50), dt.time(9, 55)],
        [600.0, 600.0, 600.0, 600.0, 600.0],
    )
    # Two qualifying candidates: bar 0 (09:35) and bar 2 (09:45). Both level-tied, both clear
    # floor 7. rejection_level=999.0 (well above the flat 600.0 spot path) so the structure
    # stop never fires and the position rides to data-exhaustion force-close.
    candidates = [
        {"bar_idx": 0, "spy_close": 600.0, "vix": 15.0, "bear_score": 9, "blockers": [5],
         "triggers_fired": ["level_rejection"], "rejection_level": 999.0},
        {"bar_idx": 2, "spy_close": 600.0, "vix": 15.0, "bear_score": 9, "blockers": [5],
         "triggers_fired": ["level_rejection"], "rejection_level": 999.0},
    ]
    # ALL candidates resolve against the SAME flat-priced synthetic contract -- the first
    # entry (09:40 open) holds, flat, through 09:55 (data-exhausted force-close at 09:55,
    # strictly after candidate 2's 09:45 trigger), so candidate 2 must be skipped (NOT_FLAT).
    opt_bars = pd.DataFrame([
        _mk_opt_bar(day, dt.time(9, 40), 1.0), _mk_opt_bar(day, dt.time(9, 45), 1.0),
        _mk_opt_bar(day, dt.time(9, 50), 1.0), _mk_opt_bar(day, dt.time(9, 55), 1.0),
    ])
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    trades, excluded = lfr.run_lane(
        7, candidates, spy_rth, ribbon_lookup=EMPTY_RIBBON_LOOKUP, exit_shape=exit_shape,
        opt_loader=lambda sym: opt_bars,
    )
    assert len(trades) == 1, (
        f"expected exactly 1 trade -- candidate 2's trigger (09:45) falls inside candidate "
        f"1's still-open position window, so NOT_FLAT must block it. Got {len(trades)}."
    )
    assert trades[0]["trigger_bar_idx"] == 0
    assert len(excluded) == 0, "neither candidate should be OPRA-excluded in this fixture"


def test_one_position_at_a_time_red_proof_a_later_non_overlapping_candidate_DOES_enter():
    """Anti-vacuity companion: a candidate whose trigger falls AFTER the first position's own
    resolution must still enter -- proves the NOT_FLAT block is genuinely time-scoped, not a
    blanket 'only ever 1 trade per lane' bug."""
    day = dt.date(2099, 1, 5)
    spy_rth = _mk_naive_frame(
        day, [dt.time(9, 35), dt.time(9, 40), dt.time(10, 30), dt.time(10, 35)],
        [600.0, 600.0, 600.0, 600.0],
    )
    candidates = [
        {"bar_idx": 0, "spy_close": 600.0, "vix": 15.0, "bear_score": 9, "blockers": [5],
         "triggers_fired": ["level_rejection"], "rejection_level": 999.0},
        {"bar_idx": 2, "spy_close": 600.0, "vix": 15.0, "bear_score": 9, "blockers": [5],
         "triggers_fired": ["level_rejection"], "rejection_level": 999.0},
    ]

    def fake_loader(symbol: str):
        # Give each trigger its OWN short-lived contract so the first position resolves
        # (data-exhausted) well before the second candidate's 10:30 trigger.
        if symbol == lfr.option_symbol(day, 600, "P") and "first" not in fake_loader.seen:
            fake_loader.seen.add("first")
            return pd.DataFrame([_mk_opt_bar(day, dt.time(9, 40), 1.0)])
        return pd.DataFrame([_mk_opt_bar(day, dt.time(10, 35), 1.0)])
    fake_loader.seen = set()

    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    trades, _excluded = lfr.run_lane(
        7, candidates, spy_rth, ribbon_lookup=EMPTY_RIBBON_LOOKUP, exit_shape=exit_shape,
        opt_loader=fake_loader,
    )
    assert len(trades) == 2, "a non-overlapping later candidate must still enter"
    assert [t["trigger_bar_idx"] for t in trades] == [0, 2]
