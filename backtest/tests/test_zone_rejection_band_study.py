"""Guards for zone_rejection_band_study.py's frozen decision rule (2026-09-03 run task).

Pre-reg: analysis/recommendations/prereg-zone-rejection-band-2026-07-17.json (frozen
2026-07-17, decision_rule + ratification_gates sections). This suite does NOT re-run the
full historical backtest (that is the multi-minute measurement run itself, exercised
manually via `python backtest/tools/zone_rejection_band_study.py`) -- it unit-tests the
PURE post-processing functions the frozen decision rule is built from: compute_cell_gates
(the 5-gate ratification vector), compute_cell_decision (ship_ready), select_winner (the
highest-OOS-delta / largest-n tie-break), cell_metrics's verdict ladder, and the
2026-09-03-added best_day_concentration disclosure helper.

RED-proof design: every gate/tie-break clause below has a test that flips exactly that
clause on a synthetic "would otherwise ship" fixture and asserts the frozen behavior does
NOT change (i.e. a regression that loosens/reorders the rule turns these RED). At least
two independent mutations are exercised for both compute_cell_decision (gate-5-of-5
required; n>0 required) and select_winner (OOS-delta ranking; n tie-break).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from zone_rejection_band_study import (  # noqa: E402
    best_day_concentration,
    cell_metrics,
    compute_cell_decision,
    compute_cell_gates,
    preflight,
    select_winner,
)


# ---------------------------------------------------------------------------------------------
# preflight() -- hash/version pin must still match the frozen prereg on disk
# ---------------------------------------------------------------------------------------------
def test_preflight_pins_frozen_prereg():
    pf = preflight()
    assert pf["ok"] is True
    assert pf["version"] == 1
    assert pf["recomputed_sha16"] == pf["stored_sha16"] == pf["expected_sha16"]


# ---------------------------------------------------------------------------------------------
# compute_cell_gates -- the 5-gate ratification vector, ANDed
# ---------------------------------------------------------------------------------------------
_ALL_PASS_METRICS = {"oos_positive": True, "wf_ge_070": True, "sub_window_stable": True,
                      "anchor_no_regression": True, "bh_fdr_survivor": True}


def test_compute_cell_gates_all_pass():
    g = compute_cell_gates(_ALL_PASS_METRICS)
    assert g["all_5_pass"] is True
    for k in _ALL_PASS_METRICS:
        assert g[k] is True


def test_compute_cell_gates_one_fail_fails_all():
    """MUTATION-CATCHING: exactly one gate false (bh_fdr_survivor, the easiest to
    accidentally drop from an 'all()' call during a refactor) must fail the aggregate."""
    m = dict(_ALL_PASS_METRICS, bh_fdr_survivor=False)
    g = compute_cell_gates(m)
    assert g["all_5_pass"] is False
    assert g["bh_fdr_survivor"] is False


# ---------------------------------------------------------------------------------------------
# compute_cell_decision -- ship_ready = all_5_pass AND n>0 (frozen decision_rule text)
# ---------------------------------------------------------------------------------------------
def test_compute_cell_decision_ships_when_all_5_pass_and_n_positive():
    g = compute_cell_gates(_ALL_PASS_METRICS)
    d = compute_cell_decision(g, n=15)
    assert d["ship_ready"] is True
    assert d["fails"] == []
    assert d["evidence_thin"] is False


def test_compute_cell_decision_mutation_zero_n_never_ships():
    """MUTATION 1: all 5 gates PASS but n==0 (a degenerate NO_EPISODES cell whose gates
    can vacuously all be True/None-coerced) must still NOT be ship_ready -- guards against
    dropping the explicit `n > 0` guard from the frozen rule."""
    g = compute_cell_gates(_ALL_PASS_METRICS)
    d = compute_cell_decision(g, n=0)
    assert d["ship_ready"] is False


def test_compute_cell_decision_mutation_single_gate_fail_never_ships():
    """MUTATION 2: 4-of-5 gates pass (only wf_ge_070 fails) -- still must NOT ship. Guards
    against a regression that ships on a majority-gate-pass threshold instead of all-5."""
    m = dict(_ALL_PASS_METRICS, wf_ge_070=False)
    g = compute_cell_gates(m)
    d = compute_cell_decision(g, n=20)
    assert d["ship_ready"] is False
    assert "wf_ge_070" in d["fails"]


def test_compute_cell_decision_thin_evidence_still_ships_labeled_thin():
    """evidence_n>=15 is ADVISORY per the frozen prereg (ratification_gates.5_evidence_n_
    advisory) -- a thin-n cell with all 5 REAL gates passing ships, labeled thin, not
    blocked."""
    g = compute_cell_gates(_ALL_PASS_METRICS)
    d = compute_cell_decision(g, n=3)
    assert d["ship_ready"] is True
    assert d["evidence_thin"] is True


# ---------------------------------------------------------------------------------------------
# select_winner -- highest OOS delta expectancy per trade, tie-break larger n
# ---------------------------------------------------------------------------------------------
def _cells_out(overrides: dict) -> dict:
    base = {"oos_delta_mean": 0.0, "n": 0}
    out = {}
    for lbl, ov in overrides.items():
        out[lbl] = dict(base, **ov)
    return out


def test_select_winner_none_when_no_ship_ready_cells():
    cells_out = _cells_out({"a": {"oos_delta_mean": 50.0, "n": 20}})
    decisions = {"a": {"ship_ready": False}}
    assert select_winner(cells_out, decisions, ["a"]) is None


def test_select_winner_picks_highest_oos_delta_mean():
    cells_out = _cells_out({"a": {"oos_delta_mean": 10.0, "n": 20}, "b": {"oos_delta_mean": 40.0, "n": 5}})
    decisions = {"a": {"ship_ready": True}, "b": {"ship_ready": True}}
    assert select_winner(cells_out, decisions, ["a", "b"]) == "b"


def test_select_winner_mutation_ties_break_on_larger_n():
    """MUTATION: equal oos_delta_mean, different n -- frozen rule says tie-break on the
    LARGER n. Catches a regression that tie-breaks on cell label/insertion order instead."""
    cells_out = _cells_out({"a": {"oos_delta_mean": 25.0, "n": 6}, "b": {"oos_delta_mean": 25.0, "n": 30}})
    decisions = {"a": {"ship_ready": True}, "b": {"ship_ready": True}}
    assert select_winner(cells_out, decisions, ["a", "b"]) == "b"


def test_select_winner_excludes_non_ship_ready_even_if_best_oos():
    """MUTATION: a NON-ship-ready cell has the best raw oos_delta_mean -- must still be
    excluded from the winner pool. Catches a regression that ranks winner over the FULL
    cell set instead of only decisions[...]['ship_ready'] cells."""
    cells_out = _cells_out({"a": {"oos_delta_mean": 999.0, "n": 1}, "b": {"oos_delta_mean": 5.0, "n": 20}})
    decisions = {"a": {"ship_ready": False}, "b": {"ship_ready": True}}
    assert select_winner(cells_out, decisions, ["a", "b"]) == "b"


# ---------------------------------------------------------------------------------------------
# cell_metrics -- the verdict ladder (frozen ab_delta_per_trade_v2026_07_16 WF form)
# ---------------------------------------------------------------------------------------------
def _ep(date: str, delta: float) -> dict:
    return {"date": date, "delta": delta, "proximity_cents": 0.1, "atr_at_fire": 1.0}


def test_cell_metrics_no_episodes():
    m = cell_metrics([])
    assert m["n"] == 0
    assert m["verdict_ladder"] == "NO_EPISODES"


def test_cell_metrics_pass_ladder_requires_wf_ge_070():
    # IS positive, OOS/IS ratio exactly at the 0.70 bar -> PASS
    members = [_ep("2025-06-01", 100.0), _ep("2026-02-01", 70.0)]
    m = cell_metrics(members)
    assert m["is_delta_positive"] is True
    assert m["wf_delta"] == 0.70
    assert m["verdict_ladder"] == "PASS"


def test_cell_metrics_mutation_wf_below_070_fails_even_with_is_positive():
    """MUTATION: IS positive but WF ratio just under 0.70 -- must be FAIL_WF_BELOW_BAR,
    not PASS. Catches a regression that uses a > 0 check instead of >= 0.70."""
    members = [_ep("2025-06-01", 100.0), _ep("2026-02-01", 69.99)]
    m = cell_metrics(members)
    assert m["wf_delta"] < 0.70
    assert m["verdict_ladder"] == "FAIL_WF_BELOW_BAR"


def test_cell_metrics_insufficient_regime_shift_when_is_negative_oos_positive():
    members = [_ep("2025-06-01", -50.0), _ep("2026-02-01", 50.0)]
    m = cell_metrics(members)
    assert m["is_delta_positive"] is False
    assert m["oos_positive"] is True
    assert m["verdict_ladder"] == "INSUFFICIENT_REGIME_SHIFT"


def test_cell_metrics_fail_no_improvement_when_both_sides_non_positive():
    members = [_ep("2025-06-01", -50.0), _ep("2026-02-01", -10.0)]
    m = cell_metrics(members)
    assert m["verdict_ladder"] == "FAIL_NO_IMPROVEMENT"


# ---------------------------------------------------------------------------------------------
# best_day_concentration -- 2026-09-03 addition, not part of the frozen gate set
# ---------------------------------------------------------------------------------------------
def test_best_day_concentration_empty_population():
    c = best_day_concentration([])
    assert c["n_days"] == 0
    assert c["best_day"] is None


def test_best_day_concentration_single_dominant_day():
    pop = [_ep("2026-03-01", 500.0), _ep("2026-03-02", 10.0), _ep("2026-03-03", -5.0)]
    c = best_day_concentration(pop)
    assert c["best_day"] == "2026-03-01"
    assert c["n_days"] == 3
    assert c["total_delta"] == 505.0
    assert c["best_day_share_of_total"] > 0.9


def test_best_day_concentration_sums_same_day_episodes():
    pop = [_ep("2026-03-01", 100.0), _ep("2026-03-01", 50.0), _ep("2026-03-02", 20.0)]
    c = best_day_concentration(pop)
    assert c["n_days"] == 2
    assert c["best_day"] == "2026-03-01"
    assert c["best_day_delta"] == 150.0
