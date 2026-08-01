"""Guards for backtest/tools/vix_regime_gate_archetype_fate_2026_08_02.py.

THREE LAYERS:

  1. MECHANISM (`Blockers8Capture`) -- same dual-binding dedupe defect
     filter5_ribbon_fate_2026_07_31.py shipped and fixed (test_filter5_capture_no_double_count.py
     is the sibling guard for that file). `run_arm` patches BOTH `lib.orchestrator` and
     `lib.engine.score` with the SAME capture closure (each module holds an INDEPENDENT
     `from .filters import evaluate_*` binding, and orchestrator's per-bar parity cross-check
     drives every bar through both) -- a plain `list.append` would record every qualifying bar
     TWICE. RED-proof: restore `list.append` semantics in `Blockers8Capture.add` and
     `test_bar_seen_by_both_patched_bindings_is_recorded_once` fails with 2 != 1.

  2. VARY-AND-ASSERT (C14 dead-knob discipline, EXECUTION REQUIREMENT 1 of this study's task) --
     `vary_and_assert()` must prove, live against the real filters.py, that vix_soft_mode and
     disable_filters=[8] each actually change evaluate_*'s output. These tests call the SAME
     function main() calls (not a re-implementation) so a regression in the runner's own proof
     is caught here too.

  3. SHIPPED ARTIFACT (`analysis/recommendations/vix-regime-gate-archetype-2026-08-02.json`) --
     the mechanism guard alone would pass happily while a committed scorecard still stated
     inflated numbers. Cohort-A samples must carry no duplicate timestamps; bar counts must be
     >= day counts (catches an over-aggressive dedupe in the other direction).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "lib",
           REPO / "backtest" / "tools", FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import vix_regime_gate_archetype_fate_2026_08_02 as v8  # noqa: E402

SCORECARD = REPO / "analysis" / "recommendations" / "vix-regime-gate-archetype-2026-08-02.json"

PATCHED_BINDINGS = ("lib.orchestrator", "lib.engine.score")


def _bar(ts: str = "2026-07-31T10:20:00-04:00", score: int = 7) -> dict:
    return {"date": ts[:10], "timestamp_et": ts, "score": score,
            "triggers": ["level_rejection"], "level": 738.85,
            "vix_now": 17.10, "vix_prior": 17.40, "ribbon_stack": "BEAR"}


# ----------------------------------------------------------------- layer 1: the mechanism

def test_bar_seen_by_both_patched_bindings_is_recorded_once():
    """THE regression this class exists to prevent. Both patched modules see the same bar;
    cohort A must count it once."""
    cap = v8.Blockers8Capture()
    for _binding in PATCHED_BINDINGS:
        cap.add("bear", _bar())
    assert len(cap.rows("bear")) == 1, (
        f"cohort A recorded {len(cap.rows('bear'))} rows for ONE bar seen by "
        f"{len(PATCHED_BINDINGS)} patched bindings -- the 2x n-inflation filter5's own study "
        f"shipped once is back")
    assert cap.duplicate_hits == 1


def test_distinct_bars_are_all_kept():
    """Dedupe must key on the timestamp, not collapse the cohort to one row per side."""
    cap = v8.Blockers8Capture()
    for ts in ("2026-07-31T10:20:00-04:00", "2026-07-31T10:25:00-04:00",
               "2026-07-29T13:00:00-04:00"):
        for _binding in PATCHED_BINDINGS:
            cap.add("bear", _bar(ts))
    assert len(cap.rows("bear")) == 3
    assert cap.duplicate_hits == 3


def test_sides_are_independent():
    """A bull and a bear bar at the same instant are two different observations."""
    cap = v8.Blockers8Capture()
    cap.add("bull", _bar())
    cap.add("bear", _bar())
    assert len(cap.rows("bull")) == 1 and len(cap.rows("bear")) == 1
    assert cap.duplicate_hits == 0


def test_first_write_wins_so_rows_are_not_silently_mutated():
    """Dedupe must DROP the duplicate, never overwrite -- otherwise the retained row could
    come from whichever binding happened to run last, making the cohort order-dependent."""
    cap = v8.Blockers8Capture()
    cap.add("bear", _bar(score=7))
    cap.add("bear", _bar(score=999))
    assert cap.rows("bear")[0]["score"] == 7


def test_zero_duplicates_is_itself_an_alarm():
    """If the dual-patch path stops running, cohort A is silently measuring ONE scoring path.
    That must fail loudly rather than quietly halving the counts (C7)."""
    cap = v8.Blockers8Capture()
    cap.add("bear", _bar())
    with pytest.raises(AssertionError, match="parity cross-check"):
        cap.assert_dual_patch_observed()
    cap.add("bear", _bar())
    cap.assert_dual_patch_observed()


def test_run_arm_routes_captures_through_the_dedupe():
    """Structural: re-introducing a bare list for `cand` reinstates the defect verbatim."""
    src = (REPO / "backtest" / "tools" /
           "vix_regime_gate_archetype_fate_2026_08_02.py").read_text(encoding="utf-8")
    assert "cand = Blockers8Capture()" in src, (
        "run_arm no longer builds its capture as a Blockers8Capture -- if it is a plain list "
        "again, every bar is recorded once per patched module binding")
    assert 'cand["bull"].append(' not in src and 'cand["bear"].append(' not in src, (
        "run_arm is appending straight into a per-side list again -- that is the 2x path")


# ------------------------------------------------------- layer 2: vary-and-assert (C14)

def test_vary_and_assert_passes_live_against_real_filters():
    """The runner's own dead-knob proof, exercised here as a permanent regression guard.
    If filters.py's VIX gate ever changes shape such that vix_soft_mode or disable_filters=[8]
    stop changing behaviour, this test fails BEFORE any full backtest run would silently
    measure a no-op arm."""
    result = v8.vary_and_assert()
    assert result["overall"].startswith("ALL VARY-AND-ASSERT CHECKS PASSED")
    assert result["bear_probe"]["control_blockers"] == [8]
    assert 8 not in result["bear_probe"]["soft_blockers"]
    assert 8 not in result["bear_probe"]["disable_blockers"]
    assert result["bear_probe"]["soft_bear_score"] == result["bear_probe"]["disable_bear_score"] - 1
    assert result["bull_probe"]["control_blockers"] == [8]
    assert 8 not in result["bull_probe"]["disable_blockers"]
    assert result["signature_check"]["bull_has_vix_soft_mode"] is False
    assert result["signature_check"]["bear_has_vix_soft_mode"] is True


def test_vary_and_assert_bear_probe_isolates_filter_8_alone():
    """Sanity on the FIXTURE itself, not just the flags: if the probe scenario starts also
    tripping some OTHER filter (ribbon/spread/time/volume), blockers != [8] and every
    downstream assertion in vary_and_assert would be proving something about a different
    gate entirely without anyone noticing."""
    ctrl = v8.evaluate_bearish_setup(v8._probe_bear_ctx(17.25, 17.50))
    assert ctrl.blockers == [8]


def test_vary_and_assert_bull_probe_isolates_filter_8_alone():
    ctrl = v8.evaluate_bullish_setup(v8._probe_bull_ctx(17.40, 17.10))
    assert ctrl.blockers == [8]


def test_disable_filters_is_a_dead_knob_would_be_caught():
    """RED-proof by construction: prove the assertion actually discriminates. If filter 8's
    disable check were removed from filters.py (hypothetically), 8 would remain in blockers
    under disable_filters=[8] and vary_and_assert's own assertion would raise. We do not
    monkeypatch filters.py here (too invasive for a unit test) -- instead we assert the
    CURRENT measured behaviour is the discriminating one, i.e. soft != disable != control,
    proving the three arms are not aliases of each other."""
    ctrl = v8.evaluate_bearish_setup(v8._probe_bear_ctx(17.25, 17.50))
    soft = v8.evaluate_bearish_setup(v8._probe_bear_ctx(17.25, 17.50), vix_soft_mode=True)
    delf = v8.evaluate_bearish_setup(v8._probe_bear_ctx(17.25, 17.50), disable_filters=[8])
    # three genuinely distinct observable states -- blockers and/or score differ pairwise
    assert (ctrl.blockers, ctrl.bear_score) != (soft.blockers, soft.bear_score)
    assert (ctrl.blockers, ctrl.bear_score) != (delf.blockers, delf.bear_score)
    assert (soft.blockers, soft.bear_score) != (delf.blockers, delf.bear_score)


# ------------------------------------------------------- layer 3: the SHIPPED artifact

@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_cohort_a_has_no_duplicate_timestamps():
    """The committed surface, not just the code."""
    cohort = json.loads(SCORECARD.read_text(encoding="utf-8"))[
        "cohort_A_blocked_by_filter8_alone"]
    for side in ("bull", "bear"):
        stamps = [r["timestamp_et"] for r in cohort[side]["sample_recent"]]
        dupes = {s for s in stamps if stamps.count(s) > 1}
        assert not dupes, (
            f"cohort A {side} sample carries duplicate timestamps {sorted(dupes)} -- the "
            f"shipped scorecard is reporting 2x-inflated bar counts")


@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_bar_counts_are_at_least_day_counts():
    cohort = json.loads(SCORECARD.read_text(encoding="utf-8"))[
        "cohort_A_blocked_by_filter8_alone"]
    for side in ("bull", "bear"):
        s = cohort[side]
        assert s["n_bars_full"] >= s["n_days_full"] >= 0
        assert s["n_bars_recent25"] >= s["n_days_recent25"] >= 0


@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_reports_n_excluded_no_opra():
    """EXECUTION REQUIREMENT 2 of this study's task: n_excluded_no_opra must be in the
    shipped artifact, not just logged to stdout and lost."""
    doc = json.loads(SCORECARD.read_text(encoding="utf-8"))
    n = doc["opra_exclusions"]["n_excluded_no_opra"]
    assert set(n.keys()) == {"CONTROL", "ARM_A_soft", "ARM_B_delete"}
    assert all(isinstance(v, int) and v >= 0 for v in n.values())


@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_reports_every_gate_for_every_arm():
    doc = json.loads(SCORECARD.read_text(encoding="utf-8"))
    expected_gates = {"G1_recent_window_positive", "G2_day_majority_recent",
                       "G3_survives_drop_best_recent", "G4_runner_anchor_no_regression",
                       "G5_fire_count"}
    for arm in ("ARM_A_soft", "ARM_B_delete"):
        gates = doc["arms"][arm]["gates"]
        assert set(gates.keys()) == expected_gates, f"{arm} gate set mismatch: {gates.keys()}"
        for gid, g in gates.items():
            assert "status" in g and g["status"] in ("PASS", "FAIL", "UNDETERMINED"), (
                f"{arm}.{gid} missing a PASS/FAIL/UNDETERMINED status")


@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_g6_present_and_not_gating():
    """G6 (archetype participation) must be reported for both arms, both windows, and must
    NOT itself carry a pass/fail gate field -- it is descriptive per the frozen prereg."""
    doc = json.loads(SCORECARD.read_text(encoding="utf-8"))
    g6 = doc["archetype_participation_G6"]
    for scope in ("full_population", "recent_window"):
        for arm in ("ARM_A_soft", "ARM_B_delete"):
            delta = g6[scope][f"delta_{arm}_vs_CONTROL"]
            assert isinstance(delta, dict) and len(delta) > 0
            for arch, row in delta.items():
                assert "pass" not in row and "gate" not in row, (
                    f"G6 archetype row {arch} carries a gate-shaped key -- G6 is "
                    f"reported_not_gating per the frozen prereg, it must never gate")


@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_ship_verdict_matches_all_gates_pass():
    """The ship-rule arithmetic itself: an arm's verdict must be SHIP_CANDIDATE iff every one
    of its 5 gates passed (UNDETERMINED counts as not-passed, matching the frozen ship_rule's
    `all(gates pass)` -- G1's own relabeling never flips the underlying boolean)."""
    doc = json.loads(SCORECARD.read_text(encoding="utf-8"))
    for arm, s in doc["arms"].items():
        all_pass = all(g["pass"] for g in s["gates"].values())
        expected_verdict = "SHIP_CANDIDATE" if all_pass else "NULL"
        assert s["verdict"] == expected_verdict, (
            f"{arm}: all_gates_pass={all_pass} but verdict={s['verdict']}")
