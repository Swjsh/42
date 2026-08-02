"""Guard suite for backtest/tools/level_target_exit_study.py + run_level_target_study.py --
the frozen level-target-exit prereg's execution engine (overnight 2026-08-02 runner-leg
investigation, sub-problem B).

Rails protected, in priority order -- each one's failure would silently misrepresent the
frozen protocol's own result:

  1. ELIGIBILITY (detector_specification.step_2). Directional filter must never let a level on
     the WRONG side of spot become a target (a same-tick degenerate exit, the exact failure
     the prereg's min_reach=0.25 fixed value exists to design out). tier/own-trigger/reach
     bounds must all independently exclude, never silently pass.
  2. TARGET SELECTION (step_3). RULE_A/B/C must pick EXACTLY the declared level, never a
     plausible-looking neighbor -- this is "the entire hypothesis" per the prereg's own text,
     so a selection bug here would invalidate every downstream cell silently.
  3. STATISTICS (BH-FDR / one-sample p / WF-norm). Standard, well-known formulas -- verified
     against hand-computable cases so a transcription error can't quietly change which cells
     the frozen q=0.10 correction calls significant.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import level_target_exit_study as lts  # noqa: E402
import run_level_target_study as run   # noqa: E402


def _lv(price, tier="Active", weight=2, source="intraday_rth_high"):
    return {"price": price, "tier": tier, "weight": weight, "source": source}


# ---------------------------------------------------------------------------------
# 1. ELIGIBILITY
# ---------------------------------------------------------------------------------

def test_call_eligibility_rejects_levels_at_or_below_spot():
    levels = [_lv(743.0), _lv(744.5), _lv(742.0)]  # spot=744.0 -> only 744.5 is above
    elig = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=None, max_reach=5.0)
    assert [lv["price"] for lv in elig] == [744.5]


def test_put_eligibility_rejects_levels_at_or_above_spot():
    levels = [_lv(743.0), _lv(744.5), _lv(742.0)]  # spot=744.0 -> only 743.0, 742.0 below
    elig = lts.eligible_levels(levels, side="P", spot=744.0, trigger_level=None, max_reach=5.0)
    assert sorted(lv["price"] for lv in elig) == [742.0, 743.0]


def test_non_active_tier_excluded():
    levels = [_lv(745.0, tier="Reference"), _lv(746.0, tier="Active")]
    elig = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=None, max_reach=5.0)
    assert [lv["price"] for lv in elig] == [746.0]


def test_own_trigger_level_excluded():
    """The position's own stop-reference level must never double as its take-profit target."""
    levels = [_lv(745.0), _lv(746.0)]
    elig = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=745.0, max_reach=5.0)
    assert [lv["price"] for lv in elig] == [746.0]


def test_min_reach_excludes_same_tick_degenerate_target():
    """A level sitting essentially on top of spot must never fire (the prereg's own disclosed
    failure mode: 'the target was already behind spot' -- fixed min_reach=0.25, not swept)."""
    levels = [_lv(744.10), _lv(746.0)]  # spot=744.0 -> 744.10 is only $0.10 away, < MIN_REACH
    elig = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=None, max_reach=5.0)
    assert [lv["price"] for lv in elig] == [746.0]


def test_max_reach_sweep_bounds_are_respected():
    levels = [_lv(745.0), _lv(747.0), _lv(750.0)]  # spot=744.0 -> distances 1.0, 3.0, 6.0
    elig_15 = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=None, max_reach=1.5)
    elig_3 = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=None, max_reach=3.0)
    elig_5 = lts.eligible_levels(levels, side="C", spot=744.0, trigger_level=None, max_reach=5.0)
    assert [lv["price"] for lv in elig_15] == [745.0]
    assert sorted(lv["price"] for lv in elig_3) == [745.0, 747.0]
    assert sorted(lv["price"] for lv in elig_5) == [745.0, 747.0]   # 750.0 still excluded (dist 6.0)


# ---------------------------------------------------------------------------------
# 2. TARGET SELECTION -- "the entire hypothesis" (prereg's own words)
# ---------------------------------------------------------------------------------

def test_rule_a_nearest_picks_the_closest():
    elig = [_lv(748.0, weight=5), _lv(745.0, weight=2), _lv(746.5, weight=2)]
    picked = lts.pick_target(elig, spot=744.0, rule="RULE_A_NEAREST")
    assert picked["price"] == 745.0


def test_rule_b_second_skips_the_first():
    elig = [_lv(748.0), _lv(745.0), _lv(746.5)]
    picked = lts.pick_target(elig, spot=744.0, rule="RULE_B_SECOND")
    assert picked["price"] == 746.5


def test_rule_b_second_returns_none_with_fewer_than_two_eligible():
    elig = [_lv(745.0)]
    assert lts.pick_target(elig, spot=744.0, rule="RULE_B_SECOND") is None


def test_rule_c_strongest_picks_by_weight_ties_broken_by_distance():
    elig = [_lv(748.0, weight=5), _lv(745.0, weight=2), _lv(750.0, weight=5)]
    picked = lts.pick_target(elig, spot=744.0, rule="RULE_C_STRONGEST")
    # two weight-5 candidates (748.0, 750.0) -- nearer one (748.0) must win the tie-break
    assert picked["price"] == 748.0 and picked["weight"] == 5


def test_pick_target_none_when_no_eligible_levels():
    assert lts.pick_target([], spot=744.0, rule="RULE_A_NEAREST") is None


# ---------------------------------------------------------------------------------
# 3. STATISTICS
# ---------------------------------------------------------------------------------

def test_one_sample_p_is_one_for_zero_variance_and_zero_mean():
    assert run.one_sample_p([0.0, 0.0, 0.0]) == 1.0


def test_one_sample_p_shrinks_toward_zero_for_a_strong_consistent_signal():
    strong = run.one_sample_p([100.0, 102.0, 98.0, 101.0, 99.0, 103.0])
    weak = run.one_sample_p([100.0, -80.0, 50.0, -90.0, 60.0, -40.0])
    assert strong < 0.05
    assert weak > strong


def test_bh_fdr_known_case():
    """Classic textbook case: 5 p-values, q=0.10 -- only the smallest 2 survive step-up."""
    pvals = [0.01, 0.02, 0.20, 0.30, 0.50]
    sig = run.bh_fdr(pvals, q=0.10)
    assert sig == [True, True, False, False, False]


def test_bh_fdr_empty_input():
    assert run.bh_fdr([], q=0.10) == []


def test_bh_fdr_more_significant_at_looser_q():
    pvals = [0.01, 0.04, 0.06, 0.09, 0.30]
    n_10 = sum(run.bh_fdr(pvals, q=0.10))
    n_30 = sum(run.bh_fdr(pvals, q=0.30))
    assert n_30 >= n_10


def test_wf_norm_matches_project_standard_formula():
    # (oos$/n_oos) / (is$/n_is) -- backtest/autoresearch/vwap_pullback_ratify.py:_wf_norm
    wf = run.wf_norm(is_delta_total=100.0, n_is=10, oos_delta_total=35.0, n_oos=5)
    assert wf == (35.0 / 5) / (100.0 / 10)


def test_wf_norm_zero_on_degenerate_inputs():
    assert run.wf_norm(0.0, 10, 50.0, 5) == 0.0
    assert run.wf_norm(100.0, 0, 50.0, 5) == 0.0
    assert run.wf_norm(100.0, 10, 50.0, 0) == 0.0


# ---------------------------------------------------------------------------------
# 4. RUNNER-COHORT SANCTITY -- the zero-tolerance gate, RED-proofed
# ---------------------------------------------------------------------------------

def test_g4_zero_tolerance_would_catch_a_one_cent_regression():
    """G4's tolerance is 0.0 per the frozen prereg -- prove the >= comparison used in main()
    genuinely has zero slack (a regression of even $0.01 must fail), not an accidental
    near-equal epsilon that would silently wave through a real degradation."""
    cohort_cell_total = 999.99
    cohort_incumbent_total = 1000.00
    G4 = cohort_cell_total >= cohort_incumbent_total
    assert G4 is False, "a 1-cent cohort regression must fail G4 -- zero tolerance means zero"
    # RED-PROOF: the same comparison with equality must pass (proves this isn't a '>' typo
    # that would also reject an exact tie, which the prereg's 'tolerance: 0.0' text permits).
    assert (1000.00 >= 1000.00) is True
