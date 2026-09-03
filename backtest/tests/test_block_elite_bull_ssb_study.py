"""Guards for backtest/tools/block_elite_bull_ssb_study.py -- the OPRA-free characterization
wrapper around the canonical (already-pinned, see test_block_elite_bull_ssb_revalidation.py)
`block_elite_bull_ssb_revalidation.py` runner.

This file pins TWO things specific to the wrapper (the cohort-mining/dedupe/stale-echo rules
themselves are already RED-proofed by test_block_elite_bull_ssb_revalidation.py -- not
re-pinned here, per the no-duplicate-work rule):

  1. OPRA isolation -- the wrapper's source must never call any of the canonical module's
     OPRA-touching functions (rerun_original_probe / prepare_event / fetch_bars_cache_then_live
     / replay_prepared_event / _cached_bars_as_esp_shape). Enforced by an AST walk, not a
     substring search, so it survives reformatting and can't be fooled by a comment.
  2. The wrapper's own evaluate_pass_bar() -- a NOT_RUN-tolerant re-shape of the canonical
     module's frozen 4-condition ladder. Pinned against both fully-determined inputs (mirrors
     the canonical module's cond1..cond4 boolean math) and partially-None inputs (the actual
     shape this run produces), with RED-proof mutations on the verdict ladder.

Fast + deterministic: no network calls, no OPRA reads, no full study run.
"""
import ast
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))
sys.path.insert(0, os.path.join(REPO, "backtest", "tools"))
sys.path.insert(0, os.path.join(REPO, "automation", "state", "fleet"))

import block_elite_bull_ssb_study as s  # noqa: E402

WRAPPER_SRC_PATH = os.path.join(REPO, "backtest", "tools", "block_elite_bull_ssb_study.py")


# ---- 1. OPRA isolation (AST, not substring -- survives reformatting) ----------

def _call_targets_on_m(tree: ast.AST) -> set[str]:
    """Every `m.<name>(...)` call site's <name>, anywhere in the module."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "m":
                names.add(node.func.attr)
    return names


def test_wrapper_never_calls_opra_functions():
    src = open(WRAPPER_SRC_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    called = _call_targets_on_m(tree)
    forbidden_hit = called & set(s.OPRA_BLOCKED_FUNCTIONS)
    assert not forbidden_hit, (
        f"block_elite_bull_ssb_study.py calls OPRA-touching function(s) {forbidden_hit} on "
        f"the canonical module -- these read the OPRA cache, off-limits this session."
    )


def test_opra_blocked_list_is_non_empty_and_matches_canonical_module():
    """Non-vacuous: the forbidden-list itself must actually name real attributes on the
    canonical module (otherwise the AST check above would trivially always pass)."""
    import block_elite_bull_ssb_revalidation as canonical
    assert len(s.OPRA_BLOCKED_FUNCTIONS) >= 3
    for name in s.OPRA_BLOCKED_FUNCTIONS:
        assert hasattr(canonical, name), f"{name} is not even a real function on the canonical module"


def test_wrapper_calls_are_a_strict_subset_of_opra_free_canonical_functions():
    """The wrapper is allowed to call these specific OPRA-free canonical functions and
    nothing else on `m` -- pins the intended surface so a future edit that reaches for a
    new canonical function gets caught here, not discovered at 2am against a live cache."""
    allowed = {"preflight", "load_core_decisions", "mine_elite_extension_events",
               "mine_super_comparison_events", "recover_trigger_level", "N_EVENTS_FLOOR"}
    tree = ast.parse(open(WRAPPER_SRC_PATH, encoding="utf-8").read())
    called = _call_targets_on_m(tree)
    # N_EVENTS_FLOOR is an attribute access, not a call -- check separately.
    assert called <= allowed, f"unexpected canonical-module calls: {called - allowed}"


# ---- 2. evaluate_pass_bar() ----------------------------------------------------

def test_pass_bar_all_pass_when_all_conditions_true():
    r = s.evaluate_pass_bar(ssb_total_pnl=100.0, ssb_drop_top1_pnl=50.0,
                             old_exit_parity_ok=True, n_events=12)
    assert r["all_pass"] is True
    assert r["verdict"] == "UNBLOCK_PROPOSE"


def test_pass_bar_keep_when_a_boolean_condition_fails():
    r = s.evaluate_pass_bar(ssb_total_pnl=-5.0, ssb_drop_top1_pnl=50.0,
                             old_exit_parity_ok=True, n_events=12)
    assert r["all_pass"] is False
    assert r["verdict"] == "KEEP"


def test_pass_bar_keep_when_n_below_floor():
    r = s.evaluate_pass_bar(ssb_total_pnl=100.0, ssb_drop_top1_pnl=50.0,
                             old_exit_parity_ok=True, n_events=11)
    assert r["condition_4_n_events_floor_12"]["result"] is False
    assert r["verdict"] == "KEEP"


def test_pass_bar_n_floor_boundary_inclusive():
    r = s.evaluate_pass_bar(ssb_total_pnl=100.0, ssb_drop_top1_pnl=50.0,
                             old_exit_parity_ok=True, n_events=12)
    assert r["condition_4_n_events_floor_12"]["result"] is True


def test_pass_bar_indeterminate_when_dollar_conditions_not_run():
    """This run's actual shape: conditions 1-3 are None (OPRA-blocked), condition 4 is
    fully computed. Verdict must be INDETERMINATE, never silently KEEP or PROPOSE."""
    r = s.evaluate_pass_bar(ssb_total_pnl=None, ssb_drop_top1_pnl=None,
                             old_exit_parity_ok=None, n_events=28)
    assert r["condition_1_ssb_total_positive"] == "NOT_RUN"
    assert r["condition_2_ssb_drop_top1_positive"] == "NOT_RUN"
    assert r["condition_3_old_exit_parity"] == "NOT_RUN"
    assert r["condition_4_n_events_floor_12"]["result"] is True
    assert r["verdict"] == "INDETERMINATE_CONDITIONS_NOT_RUN"
    assert r["all_pass"] == "NOT_RUN"


def test_pass_bar_indeterminate_even_if_n_also_fails():
    """A NOT_RUN dollar condition must never be masked by also failing condition 4 --
    the report must say INDETERMINATE (some conditions unknown), not KEEP (all conditions
    checked and failed) -- those are different claims and must not be conflated."""
    r = s.evaluate_pass_bar(ssb_total_pnl=None, ssb_drop_top1_pnl=None,
                             old_exit_parity_ok=None, n_events=3)
    assert r["verdict"] == "INDETERMINATE_CONDITIONS_NOT_RUN"


def test_pass_bar_partial_not_run_still_indeterminate():
    """Even ONE NOT_RUN condition (not just all three) must produce INDETERMINATE, not a
    false KEEP/PROPOSE computed from only the known conditions."""
    r = s.evaluate_pass_bar(ssb_total_pnl=100.0, ssb_drop_top1_pnl=50.0,
                             old_exit_parity_ok=None, n_events=12)
    assert r["verdict"] == "INDETERMINATE_CONDITIONS_NOT_RUN"


# ---- 3. part_a reuse is honestly labeled, not silently re-derived -------------

def test_build_part_a_reads_recorded_artifact_and_labels_reuse():
    part_a = s.build_part_a()
    assert part_a["n"] == 7
    assert part_a["old_exit_net_pnl_recorded"] == pytest.approx(-241.26, abs=0.01)
    assert part_a["source"] == "REUSED_PRIOR_ARTIFACT_NOT_RERUN_OPRA_BLOCKED"
