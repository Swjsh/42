"""Guards for regime_standdown_study.py (REGIME-STANDDOWN-EARLY-CLASSIFIER-2026-08-02).

Pure-function arithmetic checks on a tiny synthetic fixture -- does NOT re-verify the
classifier's no-lookahead property (that is
backtest/tests/test_regime_early_classifier_guards.py's job); this file is about the ARM
STUDY's own bookkeeping: does evaluate_arm() correctly partition control into kept/removed,
compute the recent-window delta, the drop-best-day, the runner-cohort no-regression ratio,
and the gate booleans, on inputs whose right answer can be hand-checked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "backtest"), str(REPO / "backtest" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regime_standdown_study as rss  # noqa: E402


# ---------------------------------------------------------------------------
# bh_fdr -- standard BH sanity checks
# ---------------------------------------------------------------------------

def test_bh_fdr_empty():
    assert rss.bh_fdr([]) == []


def test_bh_fdr_all_significant():
    # every p-value tiny -> every hypothesis rejected
    assert rss.bh_fdr([0.001, 0.002, 0.003], q=0.10) == [True, True, True]


def test_bh_fdr_none_significant():
    assert rss.bh_fdr([0.9, 0.8, 0.95], q=0.10) == [False, False, False]


def test_bh_fdr_mixed_matches_hand_computed_rank():
    # sorted p: 0.01(rank1) 0.03(rank2) 0.20(rank3) 0.50(rank4), q=0.10, m=4
    # thresholds: 0.10*1/4=.025 0.10*2/4=.05 0.10*3/4=.075 0.10*4/4=.10
    # 0.01<=.025 YES(rank1) ; 0.03<=.05 YES(rank2) ; 0.20<=.075 NO ; 0.50<=.10 NO
    # largest passing rank = 2 -> reject ranks 1,2 only
    pvals = [0.20, 0.01, 0.50, 0.03]   # deliberately out of order
    got = rss.bh_fdr(pvals, q=0.10)
    # 0.01 (idx1) and 0.03 (idx3) are ranks 1,2 -> True; 0.20,0.50 -> False
    assert got == [False, True, False, True]


# ---------------------------------------------------------------------------
# one_sided_mean_below_zero_pvalue
# ---------------------------------------------------------------------------

def test_pvalue_none_for_n_lt_2():
    assert rss.one_sided_mean_below_zero_pvalue([]) is None
    assert rss.one_sided_mean_below_zero_pvalue([-5.0]) is None


def test_pvalue_clearly_negative_mean_is_small():
    vals = [-100.0, -95.0, -110.0, -90.0, -105.0]
    p = rss.one_sided_mean_below_zero_pvalue(vals)
    assert p is not None and p < 0.01


def test_pvalue_clearly_positive_mean_is_large():
    vals = [100.0, 95.0, 110.0, 90.0, 105.0]
    p = rss.one_sided_mean_below_zero_pvalue(vals)
    assert p is not None and p > 0.99


# ---------------------------------------------------------------------------
# runner_cohort / day_sums / recent_n_dates -- exact-string / arithmetic contracts
# ---------------------------------------------------------------------------

def test_runner_cohort_exact_prefix_match_not_substring():
    trades = [
        {"dollar_pnl": 100.0, "exit_reason": "runner_stop @ 1.5"},
        {"dollar_pnl": 50.0, "exit_reason": "ribbon_flip_back"},
        {"dollar_pnl": 25.0, "exit_reason": "not_a_runner_stop_thing"},  # 'runner_stop' NOT at start
    ]
    n, total = rss.runner_cohort(trades)
    assert n == 1 and total == 100.0


def test_day_sums_aggregates_multiple_trades_same_day():
    trades = [{"date": "2026-01-02", "dollar_pnl": 10.0},
              {"date": "2026-01-02", "dollar_pnl": -3.0},
              {"date": "2026-01-03", "dollar_pnl": 5.0}]
    ds = rss.day_sums(trades)
    assert ds == {"2026-01-02": 7.0, "2026-01-03": 5.0}


def test_recent_n_dates_takes_newest_n_sorted():
    dates = ["2026-01-05", "2026-01-01", "2026-01-03", "2026-01-02", "2026-01-04"]
    assert rss.recent_n_dates(dates, 3) == ["2026-01-03", "2026-01-04", "2026-01-05"]


# ---------------------------------------------------------------------------
# evaluate_arm -- end-to-end on a small hand-checkable fixture
# ---------------------------------------------------------------------------

def _lib(dates_and_archs: dict) -> dict:
    return {d: {"archetype": a} for d, a in dates_and_archs.items()}


def test_evaluate_arm_kept_plus_removed_equals_control():
    control = [
        {"date": "2026-01-02", "dollar_pnl": 100.0, "exit_reason": "runner_stop @ 1.0"},
        {"date": "2026-01-03", "dollar_pnl": -50.0, "exit_reason": "premium_stop @ 0.5"},
        {"date": "2026-01-06", "dollar_pnl": 30.0, "exit_reason": "time_stop_15:40"},
    ]
    # skip 2026-01-03 only
    oof = {
        "2026-01-02": {"pred_standdown_direct": False},
        "2026-01-03": {"pred_standdown_direct": True},
        "2026-01-06": {"pred_standdown_direct": False},
    }
    lib = _lib({"2026-01-02": "gap-go", "2026-01-03": "pin-day", "2026-01-06": "range-chop"})
    r = rss.evaluate_arm(control, oof, lib, "TEST_ARM")
    assert r["n_control_trades"] == 3
    assert r["n_removed_trades"] == 1
    assert r["n_kept_trades"] == 2
    assert r["control_total_pnl"] == pytest.approx(80.0)
    assert r["removed_total_pnl"] == pytest.approx(-50.0)
    assert r["kept_total_pnl"] == pytest.approx(130.0)
    assert r["full_population_delta"] == pytest.approx(50.0)   # removing a $-50 loser: book improves by +$50


def test_evaluate_arm_runner_cohort_zero_removed_when_untouched():
    control = [
        {"date": "2026-01-02", "dollar_pnl": 500.0, "exit_reason": "runner_stop @ 2.0"},
        {"date": "2026-01-03", "dollar_pnl": -10.0, "exit_reason": "premium_stop @ 0.5"},
    ]
    oof = {"2026-01-02": {"pred_standdown_direct": False},
           "2026-01-03": {"pred_standdown_direct": True}}
    lib = _lib({"2026-01-02": "gap-go", "2026-01-03": "pin-day"})
    r = rss.evaluate_arm(control, oof, lib, "TEST_ARM")
    g4 = r["gates"]["G4_runner_anchor_no_regression"]
    assert g4["pass"] is True
    assert g4["runner_count_pct_of_control"] == pytest.approx(1.0)
    assert g4["runner_total_pct_of_control"] == pytest.approx(1.0)


def test_evaluate_arm_runner_cohort_regression_fails_gate():
    control = [
        {"date": "2026-01-02", "dollar_pnl": 500.0, "exit_reason": "runner_stop @ 2.0"},
        {"date": "2026-01-03", "dollar_pnl": 500.0, "exit_reason": "runner_stop @ 2.1"},
        {"date": "2026-01-06", "dollar_pnl": -5.0, "exit_reason": "premium_stop @ 0.5"},
    ]
    # both runner trades wrongly flagged standdown -> 0% of runner $ survives
    oof = {"2026-01-02": {"pred_standdown_direct": True},
           "2026-01-03": {"pred_standdown_direct": True},
           "2026-01-06": {"pred_standdown_direct": False}}
    lib = _lib({"2026-01-02": "gap-go", "2026-01-03": "gap-go", "2026-01-06": "pin-day"})
    r = rss.evaluate_arm(control, oof, lib, "TEST_ARM")
    g4 = r["gates"]["G4_runner_anchor_no_regression"]
    assert g4["pass"] is False
    assert g4["runner_total_pct_of_control"] == pytest.approx(0.0)
    assert r["ships"] is False   # a G4 failure alone must fail the whole arm


def test_evaluate_arm_gap_go_removed_breakdown_isolated():
    control = [
        {"date": "2026-01-02", "dollar_pnl": 200.0, "exit_reason": "runner_stop @ 1.0"},
        {"date": "2026-01-03", "dollar_pnl": -40.0, "exit_reason": "premium_stop @ 0.5"},
    ]
    oof = {"2026-01-02": {"pred_standdown_direct": True},
           "2026-01-03": {"pred_standdown_direct": False}}
    lib = _lib({"2026-01-02": "gap-go", "2026-01-03": "gap-fade"})
    r = rss.evaluate_arm(control, oof, lib, "TEST_ARM")
    assert r["gap_go_removed"]["n_trades"] == 1
    assert r["gap_go_removed"]["total_pnl"] == pytest.approx(200.0)
    # the gap-fade trade was correctly NOT flagged in this fixture, so it must not appear removed
    assert "gap-fade" not in r["removed_by_true_archetype"]
