"""GUARD for setup/scripts/pdt_blocked_counterfactual.py -- the PDT-BLOCKED-COUNTERFACTUAL-
2026-08-11 prereg runner (analysis/recommendations/prereg-pdt-blocked-counterfactual-
2026-08-11.json, status FROZEN_BEFORE_RUNNER).

Pure-function tests on SYNTHETIC inputs only -- no network, no OPRA bar cache, no ledger I/O.
Covers the two load-bearing pieces of logic that must never silently drift:

  1. compute_gates(day_pnls) -- the frozen prereg's G1-G4 decision logic. Each test isolates
     ONE gate at a time (arrange a day_pnls dict where exactly one gate is on the boundary) so
     a regression that breaks a single gate's condition fails a single, obviously-named test.
  2. canonical_shape / resolve_trigger_level -- the date-keyed exit-shape resolution the
     module docstring commits to BEFORE any P&L is computed (pre-STOP-B literal below
     2026-07-09, current ribbon_ride shape with pre_tp1_* ladder knobs forced off at/after
     it). A regression here would silently re-price the whole population under the wrong
     historical shape.

RED-PROOF: run with the gate functions' comparison operators flipped (see the module's own
`pass` conditions) and confirm the corresponding test fails -- exercised manually below each
gate test's docstring; the report for this session quotes the actual RED run.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pdt_blocked_counterfactual as pbc  # noqa: E402


# ---------------------------------------------------------------------------------------
# compute_gates -- G1 net_positive
# ---------------------------------------------------------------------------------------
def test_g1_passes_on_positive_net():
    gates = pbc.compute_gates({"2026-07-08": 10.0, "2026-07-09": 5.0})
    assert gates["G1_net_positive"]["pass"] is True
    assert gates["G1_net_positive"]["net_total"] == 15.0


def test_g1_fails_on_zero_net():
    """Net exactly 0 is NOT positive -- the gate is a strict '> 0', not '>= 0'."""
    gates = pbc.compute_gates({"2026-07-08": 10.0, "2026-07-09": -10.0})
    assert gates["G1_net_positive"]["pass"] is False
    assert gates["G1_net_positive"]["net_total"] == 0.0


def test_g1_fails_on_negative_net():
    gates = pbc.compute_gates({"2026-07-08": -1.0})
    assert gates["G1_net_positive"]["pass"] is False


# ---------------------------------------------------------------------------------------
# compute_gates -- G2 day_balance (profitable days > losing days)
# ---------------------------------------------------------------------------------------
def test_g2_passes_when_more_profitable_days_than_losing():
    gates = pbc.compute_gates({"d1": 100.0, "d2": 50.0, "d3": -10.0})
    assert gates["G2_day_balance"]["pass"] is True
    assert gates["G2_day_balance"]["profitable_days"] == 2
    assert gates["G2_day_balance"]["losing_days"] == 1


def test_g2_fails_on_tie():
    """Equal profitable/losing day counts must NOT pass -- the gate is a strict '>'."""
    gates = pbc.compute_gates({"d1": 100.0, "d2": -50.0})
    assert gates["G2_day_balance"]["pass"] is False
    assert gates["G2_day_balance"]["profitable_days"] == 1
    assert gates["G2_day_balance"]["losing_days"] == 1


def test_g2_fails_when_losing_days_dominate():
    gates = pbc.compute_gates({"d1": 100.0, "d2": -10.0, "d3": -10.0})
    assert gates["G2_day_balance"]["pass"] is False


def test_g2_flat_days_excluded_from_both_sides():
    """A day that nets to exactly $0 counts as neither profitable nor losing."""
    gates = pbc.compute_gates({"d1": 100.0, "d2": 0.0, "d3": -50.0})
    assert gates["G2_day_balance"]["profitable_days"] == 1
    assert gates["G2_day_balance"]["losing_days"] == 1
    assert gates["G2_day_balance"]["flat_days"] == 1
    assert gates["G2_day_balance"]["pass"] is False  # tie 1-1


# ---------------------------------------------------------------------------------------
# compute_gates -- G3 drop_best (net - best_day >= 0, i.e. the rest of the cohort alone
# must not be net-negative)
# ---------------------------------------------------------------------------------------
def test_g3_passes_when_rest_of_cohort_still_nonnegative():
    """best day $60, other days net +$10 -> dropping best still leaves >=0."""
    gates = pbc.compute_gates({"d1": 60.0, "d2": 5.0, "d3": 5.0})
    assert gates["G3_drop_best"]["pass"] is True
    assert gates["G3_drop_best"]["net_minus_best_day"] == 10.0
    assert gates["G3_drop_best"]["best_day"] == "d1"


def test_g3_fails_when_all_the_edge_is_one_day():
    """The frozen prereg's own worry: one lucky day carrying the whole result."""
    gates = pbc.compute_gates({"d1": 1000.0, "d2": -5.0, "d3": -5.0})
    assert gates["G3_drop_best"]["pass"] is False
    assert gates["G3_drop_best"]["net_minus_best_day"] == -10.0


def test_g3_boundary_exactly_zero_passes():
    """net - best_day == 0 exactly must pass ('>= 0', not a strict '>')."""
    gates = pbc.compute_gates({"d1": 10.0, "d2": -10.0, "d3": 20.0})
    # net = 20, best = 20 (d3) -> net-best = 0
    assert gates["G3_drop_best"]["net_minus_best_day"] == 0.0
    assert gates["G3_drop_best"]["pass"] is True


# ---------------------------------------------------------------------------------------
# compute_gates -- G4 not_concentrated (no single day > 60% of a POSITIVE net)
# ---------------------------------------------------------------------------------------
def test_g4_passes_when_well_distributed():
    gates = pbc.compute_gates({"d1": 40.0, "d2": 30.0, "d3": 30.0})
    assert gates["G4_not_concentrated"]["pass"] is True
    assert gates["G4_not_concentrated"]["best_day_pct_of_net"] == 0.4


def test_g4_fails_when_one_day_is_most_of_the_net():
    gates = pbc.compute_gates({"d1": 90.0, "d2": 5.0, "d3": 5.0})
    assert gates["G4_not_concentrated"]["pass"] is False
    assert gates["G4_not_concentrated"]["best_day_pct_of_net"] == 0.9


def test_g4_boundary_exactly_60_pct_passes():
    """Exactly 60% must pass ('<=', not a strict '<') -- matches the prereg's own wording
    'more than 60%' (i.e. only STRICTLY over 60% fails)."""
    gates = pbc.compute_gates({"d1": 60.0, "d2": 40.0})
    assert gates["G4_not_concentrated"]["best_day_pct_of_net"] == 0.6
    assert gates["G4_not_concentrated"]["pass"] is True


def test_g4_undefined_and_fails_when_net_not_positive():
    """'60% of a POSITIVE net' is undefined when net <= 0 -- the gate cannot pass, and the
    percentage is reported as None rather than a misleading number."""
    gates = pbc.compute_gates({"d1": 10.0, "d2": -20.0})
    assert gates["G4_not_concentrated"]["pass"] is False
    assert gates["G4_not_concentrated"]["best_day_pct_of_net"] is None


# ---------------------------------------------------------------------------------------
# compute_gates -- ALL/AND semantics + empty input
# ---------------------------------------------------------------------------------------
def test_all_pass_requires_every_gate():
    """Three gates pass, G4 fails on concentration -> all_pass must be False (AND, not
    majority-vote)."""
    day_pnls = {"d1": 1000.0, "d2": 10.0, "d3": 10.0}  # G1/G2/G3 pass, G4 fails (concentrated)
    gates = pbc.compute_gates(day_pnls)
    assert gates["G1_net_positive"]["pass"] is True
    assert gates["G2_day_balance"]["pass"] is True
    assert gates["G3_drop_best"]["pass"] is True
    assert gates["G4_not_concentrated"]["pass"] is False
    assert gates["all_pass"] is False


def test_all_four_gates_pass_together():
    day_pnls = {"d1": 30.0, "d2": 25.0, "d3": 25.0, "d4": -5.0}
    gates = pbc.compute_gates(day_pnls)
    assert gates["all_pass"] is True


def test_empty_day_pnls_fails_closed():
    gates = pbc.compute_gates({})
    assert gates["all_pass"] is False
    assert gates["G1_net_positive"]["net_total"] == 0.0
    assert gates["n_days"] == 0


# ---------------------------------------------------------------------------------------
# canonical_shape -- date-keyed exit shape resolution (STOP-B ship boundary 2026-07-09)
# ---------------------------------------------------------------------------------------
def test_canonical_shape_before_stopb_is_the_git_recovered_prior_literal():
    shape = pbc.canonical_shape("2026-07-08")
    assert shape["stop_mode"] == "premium"
    assert shape["tp1_premium_pct"] == 1.5
    assert shape["tp1_qty_fraction"] == 0.8
    assert shape["profit_lock_mode"] == "fixed"
    assert shape["premium_stop_pct"] == -0.20


def test_canonical_shape_on_stopb_ship_date_is_the_new_shape():
    """The ship date itself (2026-07-09) is INCLUSIVE of the new shape -- '<' not '<=' in
    the boundary check."""
    shape = pbc.canonical_shape("2026-07-09")
    assert shape["stop_mode"] == "structure"
    assert shape["profit_lock_mode"] == "trailing"


def test_canonical_shape_after_stopb_disables_pre_tp1_ladder_knobs():
    """pre_tp1_ladder etc. postdate this study window (shipped 2026-08-10) -- must be
    forced None even though the CURRENT strategies.py registry carries them, or a position
    priced today would silently get pre-TP1 protection it never had live."""
    shape = pbc.canonical_shape("2026-08-04")
    assert shape.get("pre_tp1_ladder") is None
    assert shape.get("pre_tp1_trail_arm_pct") is None
    assert shape.get("pre_tp1_trail_pct") is None
    assert shape.get("pre_tp1_be_floor_arm_pct") is None
    assert shape.get("pre_tp1_floor_pct") is None


def test_canonical_shape_far_pre_stopb_date_still_uses_prior_literal():
    shape = pbc.canonical_shape("2026-06-01")
    assert shape["stop_mode"] == "premium"


# ---------------------------------------------------------------------------------------
# resolve_trigger_level -- structure-mode eligibility
# ---------------------------------------------------------------------------------------
def test_resolve_trigger_level_zero_before_stopb_even_if_level_logged():
    """A trigger level logged on a pre-STOP-B date must NOT arm structure mode -- the
    feature did not exist yet, regardless of what data happens to be present."""
    assert pbc.resolve_trigger_level("2026-07-08", 743.0) == 0.0


def test_resolve_trigger_level_zero_when_level_missing():
    assert pbc.resolve_trigger_level("2026-08-04", None) == 0.0


def test_resolve_trigger_level_passes_through_after_stopb():
    assert pbc.resolve_trigger_level("2026-08-04", 768.94) == 768.94


def test_resolve_trigger_level_zero_on_nonpositive_level():
    assert pbc.resolve_trigger_level("2026-08-04", 0.0) == 0.0
    assert pbc.resolve_trigger_level("2026-08-04", -1.0) == 0.0


def test_resolve_trigger_level_zero_on_unparseable_level():
    assert pbc.resolve_trigger_level("2026-08-04", "not-a-number") == 0.0


# ---------------------------------------------------------------------------------------
# day_pnls_from_priced -- aggregation helper feeding compute_gates
# ---------------------------------------------------------------------------------------
def test_day_pnls_from_priced_sums_multiple_intents_same_day():
    priced = [
        {"date": "2026-08-04", "pnl": 100.0},
        {"date": "2026-08-04", "pnl": -30.0},
        {"date": "2026-08-05", "pnl": 5.0},
    ]
    day_pnls = pbc.day_pnls_from_priced(priced)
    assert day_pnls == {"2026-08-04": 70.0, "2026-08-05": 5.0}


def test_day_pnls_from_priced_empty_input():
    assert pbc.day_pnls_from_priced([]) == {}
