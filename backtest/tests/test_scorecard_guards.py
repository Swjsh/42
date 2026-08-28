"""Unit tests for setup/scripts/lib/scorecard_guards.py (built 2026-08-27,
AUDIT-CORRECTIONS-2026-08-27) -- the four structural guard fields every A/B scorecard now
carries: (i) day-level bootstrap CI + P(pnl<=0)/P(PF<=1.0), (ii) ex-best-day sign-flip,
(iii) signal-cluster count, (iv) Benjamini-Hochberg FDR across a sweep.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name, rel_path):
    path = os.path.join(ROOT, *rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sg = _load("scorecard_guards", ("setup", "scripts", "lib", "scorecard_guards.py"))


# --------------------------------------------------------------------------- #
# Guard (i): day-level bootstrap
# --------------------------------------------------------------------------- #

def test_bootstrap_insufficient_days_returns_none_not_fabricated():
    """1 day (or 0) cannot estimate variance -- must report None, never a fake-precise CI."""
    result = sg.day_level_bootstrap({"2026-08-01": [100.0, -20.0]}, n_boot=500)
    assert result["insufficient_days"] is True
    assert result["pnl_ci_low"] is None
    assert result["p_pnl_le_0"] is None


def test_bootstrap_all_positive_days_gives_low_p_pnl_le_0():
    """5 days, every day strictly positive -> resampling ANY combination of days is still
    strictly positive -> P(pnl<=0) must be exactly 0.0 (deterministic floor, not just low)."""
    day_pnls = {f"2026-08-0{i}": [50.0, 30.0] for i in range(1, 6)}
    result = sg.day_level_bootstrap(day_pnls, n_boot=1000, seed=7)
    assert result["p_pnl_le_0"] == 0.0
    assert result["pnl_ci_low"] > 0


def test_bootstrap_mixed_days_gives_intermediate_probability():
    """3 clearly losing days + 2 clearly winning days, winners bigger -> some resamples land
    net negative (all-losing-day draws) -> P(pnl<=0) strictly between 0 and 1."""
    day_pnls = {
        "2026-08-01": [-100.0], "2026-08-02": [-100.0], "2026-08-03": [-100.0],
        "2026-08-04": [500.0], "2026-08-05": [500.0],
    }
    result = sg.day_level_bootstrap(day_pnls, n_boot=2000, seed=7)
    assert 0.0 < result["p_pnl_le_0"] < 1.0


def test_bootstrap_is_deterministic_given_same_seed():
    day_pnls = {"2026-08-01": [10.0, -5.0], "2026-08-02": [-8.0], "2026-08-03": [20.0]}
    r1 = sg.day_level_bootstrap(day_pnls, n_boot=500, seed=42)
    r2 = sg.day_level_bootstrap(day_pnls, n_boot=500, seed=42)
    assert r1 == r2


def test_bootstrap_pf_undefined_when_no_losses():
    """Every trade a winner -> gross loss is always 0 in every resample -> PF is undefined
    (never fabricated as infinity)."""
    day_pnls = {"2026-08-01": [10.0], "2026-08-02": [20.0], "2026-08-03": [5.0]}
    result = sg.day_level_bootstrap(day_pnls, n_boot=200, seed=1)
    assert result["pf_mean"] is None
    assert result["pf_undefined_resamples"] == 200


# --------------------------------------------------------------------------- #
# Guard (ii): ex-best-day sign flip
# --------------------------------------------------------------------------- #

def test_ex_best_day_flip_detected_when_edge_is_one_day():
    """Total is positive ONLY because of one huge day; removing it goes negative -> FAIL."""
    day_pnls = {"2026-08-01": 2000.0, "2026-08-02": -300.0, "2026-08-03": -400.0,
                "2026-08-04": -500.0}
    result = sg.ex_best_day(day_pnls)
    assert result["total_pnl"] == 800.0
    assert result["best_day"] == "2026-08-01"
    assert result["ex_best_day_pnl"] == -1200.0
    assert result["auto_fail_sign_flips_ex_best_day"] is True


def test_ex_best_day_no_flip_when_edge_is_robust():
    """Positive total that stays positive after dropping the best day -> PASS (no flip)."""
    day_pnls = {"2026-08-01": 500.0, "2026-08-02": 300.0, "2026-08-03": 200.0}
    result = sg.ex_best_day(day_pnls)
    assert result["auto_fail_sign_flips_ex_best_day"] is False
    assert result["ex_best_day_pnl"] == 500.0


def test_ex_best_day_empty_input_never_fabricates():
    result = sg.ex_best_day({})
    assert result["auto_fail_sign_flips_ex_best_day"] is False
    assert result["best_day"] is None
    assert result["n_days"] == 0


# --------------------------------------------------------------------------- #
# Guard (iii): signal-cluster count
# --------------------------------------------------------------------------- #

def test_signal_cluster_collapses_near_simultaneous_entries():
    """5 arms firing the SAME signal within seconds on the same symbol/date must collapse
    to ONE cluster -- this is the real-tape pattern from 2026-08-04 11:52 verified 2026-08-27."""
    entries = [
        {"date": "2026-08-04", "sym": "SPY260804C00769000", "entry_ts_et": "2026-08-04T11:51:41"},
        {"date": "2026-08-04", "sym": "SPY260804C00769000", "entry_ts_et": "2026-08-04T11:52:09"},
        {"date": "2026-08-04", "sym": "SPY260804C00769000", "entry_ts_et": "2026-08-04T11:52:10"},
        {"date": "2026-08-04", "sym": "SPY260804C00769000", "entry_ts_et": "2026-08-04T11:52:12"},
    ]
    result = sg.signal_cluster_n(entries, window_s=60)
    assert result["fill_n"] == 4
    assert result["signal_cluster_n"] == 1
    assert result["cluster_sizes"] == [4]


def test_signal_cluster_separates_genuinely_distinct_re_triggers():
    """Two entries on the SAME symbol/date but ~10 minutes apart are a re-trigger, not the
    same signal instance -- must stay 2 separate clusters (real-tape pattern: risky arms
    re-entering the same strike after their gate re-fires, per 2026-08-04 09:46 vs 09:50-58)."""
    entries = [
        {"date": "2026-08-04", "sym": "SPY260804C00763000", "entry_ts_et": "2026-08-04T09:50:07"},
        {"date": "2026-08-04", "sym": "SPY260804C00763000", "entry_ts_et": "2026-08-04T09:58:06"},
    ]
    result = sg.signal_cluster_n(entries, window_s=60)
    assert result["signal_cluster_n"] == 2
    assert result["cluster_sizes"] == [1, 1]


def test_signal_cluster_transitive_chaining():
    """A within window of B, B within window of C (but A-C exceeds window) -> ALL THREE
    cluster together (chained), not split."""
    entries = [
        {"date": "2026-08-04", "sym": "X", "entry_ts_et": "2026-08-04T10:00:00"},
        {"date": "2026-08-04", "sym": "X", "entry_ts_et": "2026-08-04T10:00:50"},
        {"date": "2026-08-04", "sym": "X", "entry_ts_et": "2026-08-04T10:01:40"},
    ]
    result = sg.signal_cluster_n(entries, window_s=60)
    assert result["signal_cluster_n"] == 1
    assert result["cluster_sizes"] == [3]


def test_signal_cluster_different_symbols_never_merge():
    entries = [
        {"date": "2026-08-04", "sym": "SPY260804C00769000", "entry_ts_et": "2026-08-04T11:52:00"},
        {"date": "2026-08-04", "sym": "SPY260804P00760000", "entry_ts_et": "2026-08-04T11:52:01"},
    ]
    result = sg.signal_cluster_n(entries, window_s=60)
    assert result["signal_cluster_n"] == 2


def test_signal_cluster_unparseable_timestamp_becomes_own_singleton():
    entries = [
        {"date": "2026-08-04", "sym": "X", "entry_ts_et": None},
        {"date": "2026-08-04", "sym": "X", "entry_ts_et": "not-a-timestamp"},
    ]
    result = sg.signal_cluster_n(entries, window_s=60)
    assert result["fill_n"] == 2
    assert result["signal_cluster_n"] == 2, "unparseable timestamps must never be silently merged"


# --------------------------------------------------------------------------- #
# Guard (iv): Benjamini-Hochberg FDR
# --------------------------------------------------------------------------- #

def test_bh_all_significant_when_all_pvalues_tiny():
    pvalues = {"a": 0.001, "b": 0.002, "c": 0.003}
    result = sg.benjamini_hochberg(pvalues, q=0.10)
    assert result["m"] == 3
    assert set(result["rejected"]) == {"a", "b", "c"}


def test_bh_none_significant_when_all_pvalues_large():
    pvalues = {"a": 0.9, "b": 0.8, "c": 0.7}
    result = sg.benjamini_hochberg(pvalues, q=0.10)
    assert result["rejected"] == []
    assert result["threshold_rank"] == 0


def test_bh_classic_worked_example():
    """Standard textbook BH check: p=[0.01,0.02,0.03,0.04,0.5], q=0.10, m=5.
    Critical values: 0.02,0.04,0.06,0.08,0.10. Largest k with p_(k)<=crit_(k):
    k=1: 0.01<=0.02 ok; k=2: 0.02<=0.04 ok; k=3: 0.03<=0.06 ok; k=4: 0.04<=0.08 ok;
    k=5: 0.5<=0.10 NO. So k=4 -> reject ranks 1-4, i.e. a,b,c,d significant, e not."""
    pvalues = {"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.04, "e": 0.5}
    result = sg.benjamini_hochberg(pvalues, q=0.10)
    assert result["threshold_rank"] == 4
    assert set(result["rejected"]) == {"a", "b", "c", "d"}
    assert "e" not in result["rejected"]


def test_bh_excludes_none_pvalues_without_biasing_correction():
    pvalues = {"a": 0.01, "b": None, "c": 0.5}
    result = sg.benjamini_hochberg(pvalues, q=0.10)
    assert result["m"] == 2, "the None-pvalue cell must not count toward m"
    assert result["excluded_no_pvalue"] == ["b"]


def test_bh_more_cells_tested_is_stricter_all_else_equal():
    """The same p-value that clears FDR in a small sweep can fail in a larger one -- this is
    the multiple-comparisons correction actually doing its job, pinned as a regression guard
    against a future scorecard silently reverting to uncorrected per-cell p-values."""
    small_sweep = {"a": 0.03, "b": 0.9}
    large_sweep = {"a": 0.03, "b": 0.9, "c": 0.85, "d": 0.8, "e": 0.75, "f": 0.7, "g": 0.65}
    small = sg.benjamini_hochberg(small_sweep, q=0.10)
    large = sg.benjamini_hochberg(large_sweep, q=0.10)
    assert "a" in small["rejected"]
    assert "a" not in large["rejected"], (
        "with 7 cells tested, rank-1 p=0.03 needs <= (1/7)*0.10=0.0143 to survive FDR"
    )


# --------------------------------------------------------------------------- #
# Bundle
# --------------------------------------------------------------------------- #

def test_compute_cell_guards_bundles_three_of_four():
    day_trade_pnls = {
        "2026-08-01": [100.0, -20.0],
        "2026-08-02": [50.0],
        "2026-08-03": [-30.0, 10.0],
    }
    entries = [
        {"date": "2026-08-01", "sym": "X", "entry_ts_et": "2026-08-01T10:00:00"},
        {"date": "2026-08-01", "sym": "X", "entry_ts_et": "2026-08-01T10:00:05"},
    ]
    result = sg.compute_cell_guards(day_trade_pnls, entries, n_boot=300, seed=3)
    assert "bootstrap" in result and "ex_best_day" in result and "signal_cluster" in result
    assert result["signal_cluster"]["signal_cluster_n"] == 1
    assert result["ex_best_day"]["total_pnl"] == 110.0
