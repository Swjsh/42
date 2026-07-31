"""Guards against the cohort-A n-inflation that shipped in the first 2026-07-31 filter-5 run.

THE DEFECT, EXACTLY. `backtest/tools/filter5_ribbon_fate_2026_07_31.py#run_arm` patches BOTH
`lib.orchestrator` and `lib.engine.score` with the SAME capture closure -- deliberately, because
each module did `from .filters import evaluate_*` and so holds an INDEPENDENT by-name binding,
and orchestrator.py's per-bar parity cross-check (`_ENGINE_SCORE_ASSERT`) drives every bar
through both. The capture then did a plain `list.append`, so every qualifying bar was recorded
TWICE. Cohort A shipped as "346 bull / 152 bear" full-window and "56 / 48" recent when the true
BAR counts are half that. DAY counts were unaffected -- a set of dates absorbs the duplicate --
which is precisely why the inflation survived review: only the bar counts were wrong, and they
were the numbers quoted to J.

WHY THIS FILE IS TWO LAYERS, NOT ONE:

  1. MECHANISM (`Blockers5Capture`) -- reproduces the dual-binding call pattern and pins that
     one bar seen twice is recorded once. RED-proof: restore `list.append` semantics in
     `Blockers5Capture.add` and `test_bar_seen_by_both_patched_bindings_is_recorded_once` fails
     with 2 != 1.

  2. SHIPPED ARTIFACT (`analysis/recommendations/filter5-ribbon-2026-07-31.json`) -- the mechanism
     guard alone would have passed happily while the committed scorecard still stated the
     inflated numbers to J. A green test over a wrong artifact is the C7 shape this repo keeps
     getting burned by, so the artifact itself is asserted: no cohort-A sample may contain a
     duplicate timestamp. RED-proof: that assertion FAILS against the pre-correction committed
     JSON, where every one of the 16 sampled rows is an exact adjacent duplicate.

Neither layer is decorative: layer 1 stops a re-run from re-inflating, layer 2 stops a correct
re-run from being paired with a stale surface.
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

import filter5_ribbon_fate_2026_07_31 as f5  # noqa: E402

SCORECARD = REPO / "analysis" / "recommendations" / "filter5-ribbon-2026-07-31.json"

# The two module bindings run_arm patches with the SAME closure. Named here so the test reads
# as the mechanism it is guarding rather than as an arbitrary "call it twice".
PATCHED_BINDINGS = ("lib.orchestrator", "lib.engine.score")


def _bar(ts: str = "2026-07-31T10:20:00-04:00", score: int = 10) -> dict:
    return {"date": ts[:10], "timestamp_et": ts, "score": score,
            "triggers": ["level_reclaim", "confluence"], "level": 738.85,
            "ribbon_stack": "MIXED"}


# ----------------------------------------------------------------- layer 1: the mechanism

def test_bar_seen_by_both_patched_bindings_is_recorded_once():
    """THE regression. Both patched modules see the same bar; cohort A must count it once."""
    cap = f5.Blockers5Capture()
    for _binding in PATCHED_BINDINGS:          # orchestrator scores it, engine.score re-scores it
        cap.add("bull", _bar())
    assert len(cap.rows("bull")) == 1, (
        f"cohort A recorded {len(cap.rows('bull'))} rows for ONE bar seen by "
        f"{len(PATCHED_BINDINGS)} patched bindings -- the 2x n-inflation is back")
    assert cap.duplicate_hits == 1


def test_distinct_bars_are_all_kept():
    """Dedupe must key on the timestamp, not collapse the cohort to one row per side."""
    cap = f5.Blockers5Capture()
    for ts in ("2026-07-31T10:20:00-04:00", "2026-07-31T10:25:00-04:00",
               "2026-07-29T13:00:00-04:00"):
        for _binding in PATCHED_BINDINGS:
            cap.add("bull", _bar(ts))
    assert len(cap.rows("bull")) == 3
    assert cap.duplicate_hits == 3


def test_sides_are_independent():
    """A bull and a bear bar at the same instant are two different observations."""
    cap = f5.Blockers5Capture()
    cap.add("bull", _bar())
    cap.add("bear", _bar())
    assert len(cap.rows("bull")) == 1 and len(cap.rows("bear")) == 1
    assert cap.duplicate_hits == 0


def test_first_write_wins_so_rows_are_not_silently_mutated():
    """Dedupe must DROP the duplicate, never overwrite -- otherwise the retained row could
    come from whichever binding happened to run last, making the cohort order-dependent."""
    cap = f5.Blockers5Capture()
    cap.add("bull", _bar(score=10))
    cap.add("bull", _bar(score=999))
    assert cap.rows("bull")[0]["score"] == 10


def test_zero_duplicates_is_itself_an_alarm():
    """If the dual-patch path stops running, cohort A is silently measuring ONE scoring path.
    That must fail loudly rather than quietly halving the counts (C7)."""
    cap = f5.Blockers5Capture()
    cap.add("bull", _bar())
    with pytest.raises(AssertionError, match="parity cross-check"):
        cap.assert_dual_patch_observed()
    cap.add("bull", _bar())              # the second binding reports in
    cap.assert_dual_patch_observed()     # now it is satisfied


def test_run_arm_routes_captures_through_the_dedupe():
    """Structural: re-introducing a bare list for `cand` reinstates the defect verbatim."""
    src = (REPO / "backtest" / "tools" / "filter5_ribbon_fate_2026_07_31.py").read_text(
        encoding="utf-8")
    assert "cand = Blockers5Capture()" in src, (
        "run_arm no longer builds its capture as a Blockers5Capture -- if it is a plain list "
        "again, every bar is recorded once per patched module binding")
    assert 'cand["bull"].append(' not in src and 'cand["bear"].append(' not in src, (
        "run_arm is appending straight into a per-side list again -- that is the 2x path")


# ------------------------------------------------------- layer 2: the SHIPPED artifact

@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_cohort_a_has_no_duplicate_timestamps():
    """The committed surface, not just the code. RED against the pre-correction JSON."""
    cohort = json.loads(SCORECARD.read_text(encoding="utf-8"))[
        "cohort_A_blocked_by_filter5_alone"]
    for side in ("bull", "bear"):
        stamps = [r["timestamp_et"] for r in cohort[side]["sample_recent"]]
        dupes = {s for s in stamps if stamps.count(s) > 1}
        assert not dupes, (
            f"cohort A {side} sample carries duplicate timestamps {sorted(dupes)} -- the "
            f"shipped scorecard is still reporting 2x-inflated bar counts to J")


@pytest.mark.skipif(not SCORECARD.exists(), reason="scorecard not generated yet")
def test_shipped_scorecard_bar_counts_are_at_least_day_counts():
    """Cheap arithmetic invariant that the inflated numbers also had to satisfy, kept because
    it catches the OPPOSITE failure -- an over-aggressive dedupe collapsing real bars."""
    cohort = json.loads(SCORECARD.read_text(encoding="utf-8"))[
        "cohort_A_blocked_by_filter5_alone"]
    for side in ("bull", "bear"):
        s = cohort[side]
        assert s["n_bars_full"] >= s["n_days_full"] > 0
        assert s["n_bars_recent25"] >= s["n_days_recent25"] > 0
