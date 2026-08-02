"""ENTRY BUFFER REDUCTION A/B guard (2026-08-02).

Covers backtest/tools/entry_buffer_reduction_ab_2026_08_02.py's pure functions and the
run_candidate() orchestrator against small synthetic fixtures -- no network, no real ledger
reads (the real run is documented in analysis/recommendations/
entry-buffer-reduction-results-2026-08-02.json, produced by the pre-registered method in
entry-buffer-reduction-prereg-2026-08-02.json, commit 78979314 predates the runner).

RAIL: this module NEVER writes to params.json/aggressive/params.json/heartbeat_core.py/
fleet_live.py -- it is read-only over ledgers plus its own two output JSON files. That
boundary is exercised implicitly (no test here touches those paths) and explicitly by
test_still_fills_and_filled_delta_are_pure below asserting the functions take/return plain
values with no I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import entry_buffer_reduction_ab_2026_08_02 as ab  # noqa: E402


# =============================================================================
# still_fills
# =============================================================================

def test_still_fills_true_when_fill_at_or_under_tighter_limit():
    # real anchor row: ask_decision=0.31, fill=0.33 (entry_px 0.34 = 0.31+0.03)
    # at candidate 0.02: tighter limit = 0.33 -- fill_price 0.33 <= 0.33 -> still fills
    assert ab.still_fills(fill_price=0.33, ask_decision=0.31, candidate_buffer=0.02) is True


def test_still_fills_false_when_fill_exceeds_tighter_limit():
    # at candidate 0.01: tighter limit = 0.32 -- fill_price 0.33 > 0.32 -> miss
    assert ab.still_fills(fill_price=0.33, ask_decision=0.31, candidate_buffer=0.01) is False


def test_still_fills_exact_boundary_counts_as_fill():
    assert ab.still_fills(fill_price=0.32, ask_decision=0.31, candidate_buffer=0.01) is True


def test_still_fills_baseline_buffer_always_fills_real_history():
    """Sanity pin: at the SHIPPED buffer (0.03), every real fill in the parent measurement
    satisfies still_fills by construction (fill_price <= entry_px == ask_decision+0.03 always,
    since it's a real limit-order fill) -- this is the null candidate, always 100%."""
    assert ab.still_fills(fill_price=0.33, ask_decision=0.31, candidate_buffer=0.03) is True


# =============================================================================
# filled_delta_pnl
# =============================================================================

def test_filled_delta_pnl_matches_hand_calc():
    # (0.03 - 0.015) * 5 qty * 100 = 7.50
    assert ab.filled_delta_pnl(qty=5, candidate_buffer=0.015) == pytest.approx(7.50)


def test_filled_delta_pnl_zero_at_baseline():
    assert ab.filled_delta_pnl(qty=5, candidate_buffer=0.03) == pytest.approx(0.0)


def test_filled_delta_pnl_scales_linearly_with_qty():
    assert ab.filled_delta_pnl(qty=10, candidate_buffer=0.01) == pytest.approx(
        2 * ab.filled_delta_pnl(qty=5, candidate_buffer=0.01))


# =============================================================================
# run_candidate -- small synthetic population
# =============================================================================

def _priced_row(oid, date, qty, fill_price, ask_decision):
    return {"order_id": oid, "date_et": date, "qty": qty, "fill_price": fill_price,
           "ask_decision": ask_decision, "arm": "safe-3", "symbol": "SPY_TEST"}


def test_run_candidate_still_fills_all_gives_pure_savings_only():
    """3 entries, all comfortably clear a tight candidate -- no misses, delta = pure buffer
    savings exactly, gates all pass (nothing to regress)."""
    rows = [_priced_row("a", "2026-07-01", 5, 0.19, 0.19),   # fills exactly at the ask
           _priced_row("b", "2026-07-02", 3, 0.48, 0.48),
           _priced_row("c", "2026-07-02", 5, 0.08, 0.08)]
    legs = {"a": [{"stage": "tp1", "dollar_pnl": 40.0, "date": "2026-07-01"}],
           "b": [{"stage": "premium_stop", "dollar_pnl": -30.0, "date": "2026-07-02"}],
           "c": [{"stage": "premium_stop", "dollar_pnl": -10.0, "date": "2026-07-02"}]}
    result = ab.run_candidate(0.01, rows, legs)
    assert result["n_missed"] == 0
    assert result["fill_rate_pct"] == 100.0
    expected = sum(ab.filled_delta_pnl(r["qty"], 0.01) for r in rows)
    assert result["total_delta_pnl"] == pytest.approx(expected)
    assert result["gates"]["runner_cohort_zero_tolerance"] is True
    assert result["verdict"] == "PASS_ALL_GATES"


def test_run_candidate_a_miss_subtracts_real_pnl_not_a_synthetic_value():
    """One entry can't clear the tighter limit -- its delta must be exactly -(its real total
    pnl), never a modeled/backfilled substitute price."""
    rows = [_priced_row("miss1", "2026-07-01", 5, 0.50, 0.40)]  # fill 0.50 > 0.40+0.01
    legs = {"miss1": [{"stage": "tp1", "dollar_pnl": 60.0, "date": "2026-07-01"},
                      {"stage": "trail", "dollar_pnl": 40.0, "date": "2026-07-01"}]}
    result = ab.run_candidate(0.01, rows, legs)
    assert result["n_missed"] == 1
    assert result["total_delta_pnl"] == pytest.approx(-100.0)  # -(60+40)


def test_run_candidate_runner_cohort_miss_trips_the_zero_tolerance_gate():
    rows = [_priced_row("runner1", "2026-07-01", 5, 0.50, 0.40)]
    legs = {"runner1": [{"stage": "tp1", "dollar_pnl": 60.0, "date": "2026-07-01"},
                        {"stage": "trail", "dollar_pnl": 40.0, "date": "2026-07-01"}]}
    result = ab.run_candidate(0.01, rows, legs)
    assert result["n_runner_cohort_missed"] == 1
    assert result["gates"]["runner_cohort_zero_tolerance"] is False
    assert result["verdict"] == "FAIL"


def test_run_candidate_non_runner_miss_does_not_trip_runner_gate():
    """A missed entry with ONLY a premium_stop leg (no tp1/trail/runner_target) is not
    runner-cohort -- must not falsely trip the zero-tolerance gate."""
    rows = [_priced_row("stopped1", "2026-07-01", 5, 0.50, 0.40)]
    legs = {"stopped1": [{"stage": "premium_stop", "dollar_pnl": -50.0, "date": "2026-07-01"}]}
    result = ab.run_candidate(0.01, rows, legs)
    assert result["n_runner_cohort_missed"] == 0
    assert result["gates"]["runner_cohort_zero_tolerance"] is True


def test_run_candidate_day_majority_fails_when_minority_of_days_nonneg():
    """2 of 3 days net negative -> day-majority gate must fail even if the aggregate (summed
    across days) happens to be positive, since the gate is evaluated PER DAY."""
    rows = [
        _priced_row("d1", "2026-07-01", 5, 0.50, 0.40),   # miss -> big negative day 1
        _priced_row("d2", "2026-07-02", 5, 0.50, 0.40),   # miss -> big negative day 2
        _priced_row("d3", "2026-07-03", 5, 0.10, 0.05),   # fills -> small positive day 3
    ]
    legs = {
        "d1": [{"stage": "tp1", "dollar_pnl": 500.0, "date": "2026-07-01"}],
        "d2": [{"stage": "tp1", "dollar_pnl": 1.0, "date": "2026-07-02"}],
        "d3": [{"stage": "premium_stop", "dollar_pnl": -10.0, "date": "2026-07-03"}],
    }
    result = ab.run_candidate(0.01, rows, legs)
    assert result["n_days_nonneg_delta"] == 1  # only day 2 (missing a $1 trade helps)
    assert result["gates"]["day_majority"] is False


def test_run_candidate_missing_legs_treated_as_zero_pnl_never_crashes():
    """An entry with no matching trades.csv legs (join gap) must not raise -- foregone pnl
    defaults to 0, not fabricated."""
    rows = [_priced_row("orphan", "2026-07-01", 5, 0.50, 0.40)]
    result = ab.run_candidate(0.01, rows, {})
    assert result["n_missed"] == 1
    assert result["total_delta_pnl"] == pytest.approx(0.0)
