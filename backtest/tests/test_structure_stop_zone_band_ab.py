"""Guard for structure_stop_zone_band_ab.py's ONE novel piece of logic: build_verdicts'
sub-window sign-flip / underpowered classification. Everything else the study runs
(structure_stop_signal_time, replay_structure_aware, prepare_layer_a/prepare_positions) is
already covered by test_structure_stop_study.py -- this file does not re-test that machinery,
only the sweep-specific verdict logic added on top of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import structure_stop_zone_band_ab as ssz  # noqa: E402


def _layer_a(control_exp, cand_exp):
    return {"candidates": {"BAND-00": {"expectancy": control_exp},
                           "X": {"expectancy": cand_exp}}}


def _layer_b(control_total, cand_total, n_recoverable=68):
    return {"candidates": {"BAND-00": {"anchor_total": control_total},
                           "X": {"anchor_total": cand_total}},
           "n_recoverable_trigger_level": n_recoverable}


def _sub_windows(ctl_first, ctl_second, x_first, x_second):
    return {"first_half": {"BAND-00": {"anchor_total": ctl_first}, "X": {"anchor_total": x_first}},
           "second_half": {"BAND-00": {"anchor_total": ctl_second}, "X": {"anchor_total": x_second}}}


def test_candidate_ids_and_buffers_are_consistent():
    assert ssz.CONTROL_ID in ssz.CANDIDATE_IDS
    assert ssz.CANDIDATE_BUFFERS[ssz.CONTROL_ID] == 0.0
    assert sorted(ssz.CANDIDATE_BUFFERS.values()) == list(ssz.CANDIDATE_BUFFERS.values()), (
        "buffers should be monotonically increasing in declaration order for readable sweep output")
    assert len(set(ssz.CANDIDATE_BUFFERS.values())) == len(ssz.CANDIDATE_BUFFERS), "no duplicate buffer widths"


def test_pass_requires_both_layers():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-40.0)     # X beats control on layer(a)
    layer_b = _layer_b(control_total=-900.7, cand_total=-800.0, n_recoverable=68)  # X beats control layer(b) too
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=-450, x_second=-350)
    ssz.CANDIDATE_IDS = ("BAND-00", "X")  # type: ignore[assignment]
    try:
        v = ssz.build_verdicts(layer_a, layer_b, sub)
        assert v["X"]["overall"] == "PASS"
    finally:
        ssz.CANDIDATE_IDS = tuple(ssz.CANDIDATE_BUFFERS.keys())  # restore module state


def test_fail_when_only_one_layer_beats_control():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-52.0)      # X WORSE on layer(a)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0, n_recoverable=68)  # X better layer(b)
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1600, x_second=-450)
    ssz.CANDIDATE_IDS = ("BAND-00", "X")  # type: ignore[assignment]
    try:
        v = ssz.build_verdicts(layer_a, layer_b, sub)
        assert v["X"]["overall"] == "FAIL"
    finally:
        ssz.CANDIDATE_IDS = tuple(ssz.CANDIDATE_BUFFERS.keys())


def test_sign_flip_detected_and_disclosed():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-40.0)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0, n_recoverable=68)
    # first half swings hugely positive, second half slightly negative -- the exact shape this
    # fire's real run produced for BAND-10/12/15/20
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1700, x_second=-450)
    ssz.CANDIDATE_IDS = ("BAND-00", "X")  # type: ignore[assignment]
    try:
        v = ssz.build_verdicts(layer_a, layer_b, sub)
        assert v["X"]["sub_window_sign_flip"] is True
        assert v["X"]["sub_window_delta_first_half"] > 0
        assert v["X"]["sub_window_delta_second_half"] < 0
    finally:
        ssz.CANDIDATE_IDS = tuple(ssz.CANDIDATE_BUFFERS.keys())


def test_underpowered_flagged_below_15_recoverable():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-30.0)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0, n_recoverable=9)  # below floor
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1600, x_second=-350)
    ssz.CANDIDATE_IDS = ("BAND-00", "X")  # type: ignore[assignment]
    try:
        v = ssz.build_verdicts(layer_a, layer_b, sub)
        assert v["X"]["underpowered_lt15"] is True
        assert v["X"]["overall"] == "INCONCLUSIVE_UNDERPOWERED", (
            "a PASS on both layers with n_recoverable<15 must be downgraded, never silently "
            "reported as a clean PASS (evidence-floor doctrine)")
    finally:
        ssz.CANDIDATE_IDS = tuple(ssz.CANDIDATE_BUFFERS.keys())


def test_control_never_appears_in_its_own_verdicts():
    layer_a = _layer_a(control_exp=-47.34, cand_exp=-40.0)
    layer_b = _layer_b(control_total=-900.7, cand_total=800.0)
    sub = _sub_windows(ctl_first=-500, ctl_second=-400, x_first=1600, x_second=-350)
    ssz.CANDIDATE_IDS = ("BAND-00", "X")  # type: ignore[assignment]
    try:
        v = ssz.build_verdicts(layer_a, layer_b, sub)
        assert "BAND-00" not in v, "control is the baseline, never graded against itself"
    finally:
        ssz.CANDIDATE_IDS = tuple(ssz.CANDIDATE_BUFFERS.keys())


def test_real_run_output_matches_disclosed_reject_all_result():
    """RED-proof anchor: pins this fire's actual verdict shape so a future refactor of
    build_verdicts can't silently flip the disclosed REJECT_ALL finding without a test noticing."""
    import json
    out_path = REPO / "analysis" / "recommendations" / "structure-stop-zone-band-2026-07-20.json"
    if not out_path.exists():
        return  # study output not present in this environment -- not a hard dependency
    d = json.loads(out_path.read_text(encoding="utf-8"))
    for cid, v in d["verdicts"].items():
        assert v["overall"] in ("FAIL", "INCONCLUSIVE_UNDERPOWERED"), (
            f"{cid} unexpectedly PASSed -- re-verify against the disclosed REJECT_ALL finding "
            f"before wiring a structure_stop_buffer change into strategies.py")
