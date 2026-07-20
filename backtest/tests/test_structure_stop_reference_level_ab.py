"""Guard for structure_stop_reference_level_ab.py's novel logic: resolve_zone_boundary,
reference_level_for, and build_verdicts' sub-window sign-flip / underpowered / sign-flip-
downgrade classification. The shared replay machinery (structure_stop_signal_time,
replay_structure_aware, prepare_layer_a/prepare_positions) is already covered by
test_structure_stop_study.py -- this file does not re-test that, only the reference-choice-
specific logic added on top of it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import structure_stop_reference_level_ab as ssr  # noqa: E402


# ---------------------------------------------------------------------------------------------
# resolve_zone_boundary
# ---------------------------------------------------------------------------------------------
def _levelset(active):
    return SimpleNamespace(active=active)


def test_zone_boundary_put_picks_nearest_level_above_trigger():
    ls = _levelset([744.92, 745.14, 745.40, 746.80])
    assert ssr.resolve_zone_boundary(ls, 744.92, "P") == 745.14


def test_zone_boundary_call_picks_nearest_level_below_trigger():
    ls = _levelset([738.0, 740.5, 741.9, 743.2])
    assert ssr.resolve_zone_boundary(ls, 741.9, "C") == 740.5


def test_zone_boundary_none_when_no_level_set():
    assert ssr.resolve_zone_boundary(None, 744.92, "P") is None


def test_zone_boundary_none_when_no_trigger_level():
    ls = _levelset([744.92, 745.14])
    assert ssr.resolve_zone_boundary(ls, None, "P") is None


def test_zone_boundary_none_when_no_level_beyond_trigger():
    ls = _levelset([744.92])   # nothing further above
    assert ssr.resolve_zone_boundary(ls, 744.92, "P") is None


def test_zone_boundary_respects_max_distance():
    ls = _levelset([744.92, 750.0])   # 5.08 away -- beyond the 2.00 default
    assert ssr.resolve_zone_boundary(ls, 744.92, "P", max_distance=2.0) is None


def test_zone_boundary_invalid_side_returns_none():
    ls = _levelset([744.92, 745.14])
    assert ssr.resolve_zone_boundary(ls, 744.92, "X") is None


# ---------------------------------------------------------------------------------------------
# reference_level_for
# ---------------------------------------------------------------------------------------------
def test_reference_ref_exact_always_uses_trigger():
    assert ssr.reference_level_for("REF-EXACT", 744.92, 745.14) == 744.92


def test_reference_ref_zone_uses_zone_when_available():
    assert ssr.reference_level_for("REF-ZONE", 744.92, 745.14) == 745.14


def test_reference_ref_zone_falls_back_to_trigger_when_no_zone():
    assert ssr.reference_level_for("REF-ZONE", 744.92, None) == 744.92


def test_reference_ref_none_always_none_regardless_of_levels():
    assert ssr.reference_level_for("REF-NONE", 744.92, 745.14) is None


# ---------------------------------------------------------------------------------------------
# build_verdicts
# ---------------------------------------------------------------------------------------------
def _layer_a(control_exp, cand_exp):
    return {"candidates": {"REF-EXACT": {"expectancy": control_exp},
                           "X": {"expectancy": cand_exp}}}


def _layer_b(control_total, cand_total, n_recoverable=68):
    return {"candidates": {"REF-EXACT": {"anchor_total": control_total},
                           "X": {"anchor_total": cand_total}},
           "n_recoverable_trigger_level": n_recoverable}


def _sub_windows(ctl_first, ctl_second, x_first, x_second):
    return {"first_half": {"REF-EXACT": {"anchor_total": ctl_first}, "X": {"anchor_total": x_first}},
           "second_half": {"REF-EXACT": {"anchor_total": ctl_second}, "X": {"anchor_total": x_second}}}


def _with_candidate_ids(ids, fn):
    orig = ssr.CANDIDATE_IDS
    ssr.CANDIDATE_IDS = ids  # type: ignore[assignment]
    try:
        return fn()
    finally:
        ssr.CANDIDATE_IDS = orig


def test_pass_requires_both_layers_and_no_sign_flip():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-40.0)
    layer_b = _layer_b(control_total=-900.7, cand_total=-800.0, n_recoverable=68)
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=-450, x_second=-350)
    v = _with_candidate_ids(("REF-EXACT", "X"),
                            lambda: ssr.build_verdicts(layer_a, layer_b, sub))
    assert v["X"]["overall"] == "PASS"


def test_fail_when_only_one_layer_beats_control():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-52.0)      # X WORSE on layer(a)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0)  # X better layer(b)
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1600, x_second=-450)
    v = _with_candidate_ids(("REF-EXACT", "X"),
                            lambda: ssr.build_verdicts(layer_a, layer_b, sub))
    assert v["X"]["overall"] == "FAIL"


def test_pass_downgraded_to_no_ship_on_sign_flip():
    """A candidate that clears BOTH layers but sign-flips across sub-windows must not be
    reported as a clean PASS -- this is the exact shape the real 2026-07-20 run produced for
    REF-ZONE/REF-NONE's layer(b) anchor 'win' (single 2026-07-08 anchor trade driving it,
    C24)."""
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-40.0)       # X beats control layer(a)
    layer_b = _layer_b(control_total=-900.7, cand_total=481.2)   # X beats control layer(b)
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1473.4, x_second=-491.5)
    v = _with_candidate_ids(("REF-EXACT", "X"),
                            lambda: ssr.build_verdicts(layer_a, layer_b, sub))
    assert v["X"]["sub_window_sign_flip"] is True
    assert v["X"]["overall"] == "NO_SHIP_SUBWINDOW_UNSTABLE"


def test_underpowered_flagged_below_15_recoverable():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-30.0)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0, n_recoverable=9)  # below floor
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1600, x_second=-350)
    v = _with_candidate_ids(("REF-EXACT", "X"),
                            lambda: ssr.build_verdicts(layer_a, layer_b, sub))
    assert v["X"]["underpowered_lt15"] is True
    assert v["X"]["overall"] == "INCONCLUSIVE_UNDERPOWERED", (
        "a PASS on both layers + no sign-flip with n_recoverable<15 must be downgraded, never "
        "silently reported as a clean PASS (evidence-floor doctrine)")


def test_control_never_appears_in_its_own_verdicts():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-40.0)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0)
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1600, x_second=-350)
    v = _with_candidate_ids(("REF-EXACT", "X"),
                            lambda: ssr.build_verdicts(layer_a, layer_b, sub))
    assert "REF-EXACT" not in v, "control is the baseline, never graded against itself"


def test_real_run_output_matches_disclosed_no_ship_result():
    """RED-proof anchor: pins this fire's actual verdict shape so a future refactor of
    build_verdicts/resolve_zone_boundary can't silently flip the disclosed NO-SHIP finding
    without a test noticing."""
    import json
    out_path = REPO / "analysis" / "recommendations" / "structure-stop-reference-level-2026-07-20.json"
    if not out_path.exists():
        return  # study output not present in this environment -- not a hard dependency
    d = json.loads(out_path.read_text(encoding="utf-8"))
    for cid, v in d["verdicts"].items():
        assert v["overall"] not in ("PASS",), (
            f"{cid} unexpectedly PASSed cleanly -- re-verify against the disclosed NO-SHIP "
            f"finding before wiring a structure_stop_reference_mode change into strategies.py")
