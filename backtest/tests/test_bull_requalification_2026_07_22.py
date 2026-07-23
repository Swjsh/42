"""Guard tests for the 2026-07-22 bull-gate ATM/SS-B requalification tooling
(backtest/tools/bull_gate_atm_ssb_requalification.py + bull_elite_atm_decision_log_mining.py).

Pure-function unit tests only (no network, no broker, no full backtest re-run -- that is
exercised manually and its output is committed to analysis/recommendations/). Guards the
grading ladder and the small stats helpers duplicated between the two scripts so a future
edit can't silently flip a KEEP into a RETIRE (or vice versa) without a test catching it.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import bull_gate_atm_ssb_requalification as m1  # noqa: E402
import bull_elite_atm_decision_log_mining as m2  # noqa: E402


def test_drop_top1_removes_single_largest_winner():
    remainder, positive = m1.drop_top1([-10.0, -20.0, 50.0])
    assert remainder == 20.0 - 50.0 == -30.0
    assert positive is False


def test_drop_top1_no_winners_returns_unchanged_total():
    remainder, positive = m1.drop_top1([-10.0, -5.0])
    assert remainder == -15.0
    assert positive is False


def test_drop_top1_empty_is_zero_not_positive():
    remainder, positive = m1.drop_top1([])
    assert remainder == 0.0
    assert positive is False


def test_grade_below_n_floor_never_forces_a_verdict():
    stats = {"n": 9, "total_pnl": 5000.0, "drop_top1_positive": True,
              "half_split": {"both_negative": False}}
    g = m1.grade(stats)
    assert g["verdict"] == "RETEST-INSUFFICIENT-N"
    # even an overwhelmingly positive-looking n<20 cohort must not resolve KEEP or RETIRE
    assert g["verdict"] not in ("KEEP", "RETIRE")


def test_grade_requires_all_three_conditions_for_retire():
    # total positive + stable, but drop_top1 fails -> KEEP (matches the real 2026-07-22
    # decision-log-mining result: n=30, total +$665.60, drop_top1 -$1,420.80 -> KEEP)
    stats = {"n": 30, "total_pnl": 665.6, "drop_top1_positive": False,
              "half_split": {"both_negative": False}}
    g = m1.grade(stats)
    assert g["verdict"] == "KEEP"
    assert g["condition_total_positive"] is True
    assert g["condition_drop_top1_positive"] is False


def test_grade_all_three_conditions_pass_retires():
    stats = {"n": 25, "total_pnl": 500.0, "drop_top1_positive": True,
              "half_split": {"both_negative": False}}
    g = m1.grade(stats)
    assert g["verdict"] == "RETIRE"


def test_grade_both_halves_negative_blocks_retire_even_if_total_positive_is_impossible_but_guards_stability():
    # a cohort whose two halves are BOTH negative can only ever have total <= 0, so this
    # guards the stability condition is actually being checked (not short-circuited away)
    stats = {"n": 25, "total_pnl": -10.0, "drop_top1_positive": False,
              "half_split": {"both_negative": True}}
    g = m1.grade(stats)
    assert g["condition_half_split_not_both_negative"] is False
    assert g["verdict"] == "KEEP"


def test_half_split_stability_matches_manual_split():
    replays = [
        {"entry_ts_et": "2026-07-01T10:00:00", "pnl": -10.0},
        {"entry_ts_et": "2026-07-02T10:00:00", "pnl": -5.0},
        {"entry_ts_et": "2026-07-03T10:00:00", "pnl": 20.0},
        {"entry_ts_et": "2026-07-04T10:00:00", "pnl": 30.0},
    ]
    split = m1.half_split_stability(replays)
    assert split["n_first"] == 2 and split["n_second"] == 2
    assert split["first_half_pnl"] == -15.0
    assert split["second_half_pnl"] == 50.0
    assert split["both_negative"] is False


def test_dedupe_into_events_5min_gap_rule():
    rows = [
        {"ts_et": "2026-07-10T11:21:03", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM"},
        {"ts_et": "2026-07-10T11:22:03", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM"},
        {"ts_et": "2026-07-10T11:23:03", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM"},
        {"ts_et": "2026-07-10T11:31:04", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM"},
    ]
    events = m2.dedupe_into_events(rows, gap_minutes=5)
    # 11:23 -> 11:31 is an 8-minute gap (> 5min threshold) -> 2 events, not 1
    assert len(events) == 2
    assert events[0]["n_ticks"] == 3
    assert events[1]["n_ticks"] == 1


def test_is_open_adjacent_window():
    assert m2.is_open_adjacent({"ts_et": "2026-07-10T09:37:00"}) is True
    assert m2.is_open_adjacent({"ts_et": "2026-07-10T09:45:00"}) is False


def test_strike_offset_atm_is_zero_in_both_scripts():
    """Pins the ONE variable this study corrects vs the 2026-07-10 OTM-2 revalidation --
    a future edit silently reintroducing an OTM offset would invalidate the ATM claim
    made in the requalification report without this guard."""
    assert m1.STRIKE_OFFSET_ATM == 0
    assert m2.STRIKE_OFFSET_ATM == 0


def test_n_floor_matches_op16_evidence_bar():
    assert m1.N_FLOOR == 20
    assert m2.N_FLOOR == 20
