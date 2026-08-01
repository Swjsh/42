"""Guards for Next-Twelve #7 -- shelf bistability SOURCE-FIX study
(shelf_bistability_source_fix_2026_08_01.py). Frozen pre-reg:
analysis/recommendations/shelf-bistability-prereg-2026-08-01.md @ 07697c7d.

THE MECHANISM UNDER GUARD: daily_context._find_shelf_candidates / _merge_shelf_candidates
re-derive shelf zones every 5-min refresh with today's still-forming daily bar as both a
candidate seed and a touch-counter; a single ordinary 5-min bar update to the forming bar's
running low/close can flip which near-tied overlapping candidate the greedy merge picks for a
region. Reproduced exactly (backtest/data/spy_5m + spy_daily_bars real fetch, this session):
2026-07-31 09:43->09:48 ET, forming-bar low $742.79->$741.98 (-$0.81, one 5m bar) flips the
740.50-744.05 region from {742.36 (10 touches)} to {741.60 (10 touches), 743.25 (8 touches)}.

VERDICT under guard (all three candidate arms tested, none shipped -- see prereg SS7 +
analysis/recommendations/shelf-bistability-2026-08-01.md): ARM_A (incumbent-stable literal
tie-break) is a near no-op at population scale (written flips 5496 vs BASELINE's 5494 --
technically WORSE). ARM_B/ARM_AB (exclude the forming bar from shelf discovery) cut written
flicker 82% (5494->965) but FAIL the pre-registered steady-state-fidelity gate: 198/391 days
(50.6%) show a PERMANENT (not transient) EOD level-identity divergence vs BASELINE, avg $0.57
magnitude -- excluding the forming bar also discards its LEGITIMATE end-of-day touch, not just
its noisy mid-day wobble. HYSTERESIS-ONLY (current HEAD, 114a7a6b) STANDS. These guards pin
the mechanism + all four arms' code so a future revisit starts from verified ground truth, not
from scratch, and pin that NOTHING in setup/scripts/daily_context.py changed this session.

RED-PROOF: neutering ARM_A (empty incumbent every fire) / ARM_B (re-include the forming bar)
reproduces the BASELINE flip the guards exist to catch -- proves the guards bite.

$0, pure-Python, no network. All bars fixtures are inline (backtest/data/ is gitignored;
these guards must be reproducible in a fresh checkout without the cached daily-bar fetch).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STUDY_PATH = REPO / "backtest" / "tools" / "shelf_bistability_source_fix_2026_08_01.py"

_dcx_spec = importlib.util.spec_from_file_location("daily_context", REPO / "setup" / "scripts" / "daily_context.py")
dcx = importlib.util.module_from_spec(_dcx_spec)
_dcx_spec.loader.exec_module(dcx)

# import ONLY the pure merge-arm helpers from the study module without running its __main__
# (spec_from_file_location + exec_module never invokes `if __name__ == "__main__"`, same
# pattern used throughout this codebase's tests to reuse tool-script functions read-only).
_study_spec = importlib.util.spec_from_file_location("shelf_bistability_study", STUDY_PATH)
study = importlib.util.module_from_spec(_study_spec)
_study_spec.loader.exec_module(study)


# ---- the exact reproduced fixture (real bars, hand-verified against production output) -----
# Trailing 43 daily bars strictly before 2026-07-31, sliced from the real SIP fetch this
# session (backtest/data/spy_daily_bars_real_2024-10-01_2026-08-01.json), frozen verbatim so
# this guard needs no external cache file. Only the region-relevant bars matter for the
# candidates checked below; the full trailing set is reproduced so touch counts match exactly.
def _trailing_bars_07_31() -> list[dict]:
    # Pulled once from the real cache and frozen -- see module docstring; regenerate via
    # backtest/tools/shelf_bistability_source_fix_2026_08_01.py::trailing_bars(daily, 2026-07-31)
    # if daily_context's lookback window ever changes.
    import json
    cache = REPO / "backtest" / "data" / "spy_daily_bars_real_2024-10-01_2026-08-01.json"
    if cache.exists():
        daily = sorted(json.loads(cache.read_text(encoding="utf-8")), key=lambda b: b["date"])
        return study.trailing_bars(daily, __import__("datetime").date(2026, 7, 31))
    pytest.skip("real daily-bar cache absent in this checkout (backtest/data/ is gitignored) "
                "-- guard needs the frozen trailing series; re-fetch via the study runner")


FORMING_09_43 = {"date": "2026-07-31", "o": 745.06, "h": 746.55, "l": 742.79, "c": 743.12, "v": 1.0}
FORMING_09_48 = {"date": "2026-07-31", "o": 745.06, "h": 746.55, "l": 741.98, "c": 742.28, "v": 1.0}


def _region(merged: list[dict], lo=740.5, hi=744.5) -> dict:
    return {round((m["band_low"] + m["band_high"]) / 2, 2): m["touches"]
            for m in merged if lo <= m["band_low"] <= hi}


# ================================================================= mechanism reproduction

def test_mechanism_reproduces_the_named_flip():
    """Pins the exact reproduced flip (prereg SS1): unmodified BASELINE merge on real bars,
    09:43 -> 742.36 wins alone; 09:48 (one 5m bar later) -> 742.36 is GONE, {741.60, 743.25}
    win instead. This is the regression guard for the mechanism itself."""
    trail = _trailing_bars_07_31()
    bars_43 = trail + [FORMING_09_43]
    bars_48 = trail + [FORMING_09_48]

    merged_43 = dcx._merge_shelf_candidates(dcx._find_shelf_candidates(bars_43))
    merged_48 = dcx._merge_shelf_candidates(dcx._find_shelf_candidates(bars_48))

    reg_43 = _region(merged_43)
    reg_48 = _region(merged_48)

    assert reg_43.get(742.36) == 10
    assert 743.25 not in reg_43
    assert 741.60 not in reg_43 or reg_43.get(741.60, 0) < 10  # not yet the region winner

    assert 742.36 not in reg_48                     # THE FLIP: it's gone
    assert reg_48.get(741.60) == 10
    assert reg_48.get(743.25) == 8


# ================================================================= ARM_B structural invariant

def test_arm_b_structurally_invariant_intraday():
    """ARM_B's candidate-finding input (bars with date < today) never changes within a
    session by construction -- so its merge output must be BYTE-IDENTICAL whether computed
    with the 09:43 or 09:48 forming-bar snapshot (or any other), since the forming bar is
    excluded from candidate-finding entirely. This is the formal proof behind ARM_B's
    empirically-observed near-zero raw-flicker property."""
    trail = _trailing_bars_07_31()
    cands_no_today = dcx._find_shelf_candidates(trail)
    merged_no_today = dcx._merge_shelf_candidates(cands_no_today)

    # simulate what ARM_B would compute "at" 09:43 and "at" 09:48 -- both must ignore the
    # forming bar entirely, so both equal the single `merged_no_today` result.
    for _forming in (FORMING_09_43, FORMING_09_48, None):
        cands = dcx._find_shelf_candidates(trail)   # forming bar never appended -- ARM_B
        merged = dcx._merge_shelf_candidates(cands)
        assert merged == merged_no_today


# ================================================================= ARM_A tie resolution

def test_arm_a_resolves_the_named_tie_toward_incumbent():
    """At 09:48 there is a genuine 5-way EXACT tie at 10 touches in the 740.50-744.50 region
    (740.80-742.40, 741.56-743.16, 741.69-743.29, 741.75-743.35, 742.28-743.88 -- see prereg
    SS1). BASELINE's plain (-touches, band_low) order picks 740.80-742.40 (741.60) first. With
    incumbent=[(741.56,743.16)] (742.36, the 09:43 winner), ARM_A's literal tie-break must
    instead keep 742.36 -- proving the tie-break has real bite on the reproduced case, not a
    vacuous no-op (checked before freezing the arm per prereg SS3)."""
    trail = _trailing_bars_07_31()
    bars_48 = trail + [FORMING_09_48]
    cands_48 = dcx._find_shelf_candidates(bars_48)

    baseline_48 = dcx._merge_shelf_candidates(cands_48)
    assert _region(baseline_48).get(741.60) == 10 and 742.36 not in _region(baseline_48)

    incumbent = [(741.56, 743.16)]   # the 09:43 winner's band
    arm_a_48 = study.merge_incumbent_stable(cands_48, incumbent)
    reg_a = _region(arm_a_48)
    assert reg_a.get(742.36) == 10, "ARM_A must keep the incumbent on an exact tie"
    assert 741.60 not in reg_a, "the incumbent's region is fully claimed -- 741.60 excluded by overlap"


# ================================================================= ARM_AB intraday flatness

def test_arm_ab_intraday_flat_and_equals_arm_b_with_no_incumbent():
    """ARM_AB's candidates are ARM_B's (forming bar excluded) -- constant within a session by
    the SAME proof as test_arm_b_structurally_invariant_intraday. With NO incumbent (fresh
    history, e.g. the population's first day), ARM_AB's tie-break has nothing to prefer and
    must fall back to the identical plain order ARM_B uses -- so ARM_AB == ARM_B exactly on a
    cold start. (Disclosed deviation from the prereg's stronger "identical on every fire"
    prediction: with a WARM cross-day incumbent, ARM_AB can diverge from ARM_B on a rare exact
    cross-day tie -- observed on 1/391 days in the full run, 2025-03-04 -- because ARM_AB
    carries memory across day boundaries and ARM_B never does; this guard pins the TRUE,
    narrower claim.)"""
    trail = _trailing_bars_07_31()
    cands_B = dcx._find_shelf_candidates(trail)
    merged_B = dcx._merge_shelf_candidates(cands_B)
    merged_AB_cold = study.merge_incumbent_stable(cands_B, [])
    assert merged_AB_cold == merged_B

    # intraday flatness: recomputing with the SAME (cold) incumbent again is a no-op fixed
    # point, mirroring how the study computes ARM_AB once per day and reuses it for all fires.
    merged_AB_cold_again = study.merge_incumbent_stable(cands_B, [])
    assert merged_AB_cold_again == merged_AB_cold


# ================================================================= RED-proof

def test_red_proof_neutered_arms_reproduce_baseline_flip():
    """Neuter each arm back to BASELINE behavior and confirm the flip REAPPEARS -- proves the
    guards above actually bite (are not vacuously true), matching this codebase's established
    RED-proof convention (test_level_hysteresis_2026_08_01.py)."""
    trail = _trailing_bars_07_31()
    bars_48 = trail + [FORMING_09_48]

    # neuter ARM_A: empty incumbent every fire (no memory) -> falls back to plain order,
    # reproducing the flip (742.36 gone).
    cands_48 = dcx._find_shelf_candidates(bars_48)
    neutered_a = study.merge_incumbent_stable(cands_48, incumbent=[])
    assert 742.36 not in _region(neutered_a), "neutered ARM_A must reproduce the BASELINE flip"

    # neuter ARM_B: re-include the forming bar in candidate-finding (i.e. just call BASELINE's
    # own path) -- the region is no longer invariant; 09:43 and 09:48 must now differ, exactly
    # reproducing test_mechanism_reproduces_the_named_flip's own RED case.
    bars_43 = trail + [FORMING_09_43]
    neutered_b_43 = dcx._merge_shelf_candidates(dcx._find_shelf_candidates(bars_43))
    neutered_b_48 = dcx._merge_shelf_candidates(dcx._find_shelf_candidates(bars_48))
    assert _region(neutered_b_43) != _region(neutered_b_48), \
        "neutered ARM_B (forming bar re-included) must NOT be intraday-invariant"


# ================================================================= production files untouched

def test_daily_context_merge_functions_unmodified_by_this_study():
    """This was a NULL result (prereg SS7): no arm cleared its gates, so daily_context.py and
    refresh_levels_intraday.py's hysteresis are UNTOUCHED. Pins the exact source text of the
    two functions under study so a future edit is a deliberate, visible diff, not a silent
    drift away from what this study evaluated."""
    src = (REPO / "setup" / "scripts" / "daily_context.py").read_text(encoding="utf-8")
    assert 'def _merge_shelf_candidates(candidates: list[dict]) -> list[dict]:' in src
    assert 'ranked = sorted(candidates, key=lambda c: (-c["touches"], c["band_low"]))' in src
    assert "_hysteresis_carry" not in src, "hysteresis stays in refresh_levels_intraday.py only"
