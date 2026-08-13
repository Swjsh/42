"""Guards for the CONVICTION SCORE + escalating ratchet (2026-08-12, Phase A shadow).

WHAT THIS PROTECTS. The engine scored ABSENT OBJECTIONS (`bear_score = 10 - len(blockers)`),
so on a day when nothing objected, everything was a trade — 38 positions, −$900, on a day
with one trade in it. Conviction is the POSITIVE-evidence axis; the ratchet is the sit-out.

THE TWO ORIGIN EXHIBITS (the reason this file exists, per the frozen design memo):
  A) the 2026-08-12 book — longs fired mid-flush and at the TOP of a 3-day range must
     mostly FAIL the base floor (this exhibit FORCED the v0 floor 4 -> 5 calibration);
  B) J's 12:35 bounce — a long at a named, remembered, freshly-tested support level at the
     range LOW must PASS.
If a future weight change flips either exhibit, the score is no longer measuring what it was
built to measure and the change must be re-derived, not assumed (the amend-don't-delete rule).

DEGRADATION IS LOAD-BEARING: every sensor fails to 0 + names itself in degraded_components,
and a fully-degraded read must NEVER silently suppress trading. Worst case = today's
behaviour, loudly labelled.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import conviction as cv  # noqa: E402


# --------------------------------------------------------------------------------------
# The ratchet — the sit-out mechanism itself
# --------------------------------------------------------------------------------------
def test_ratchet_escalates_one_point_per_entry_taken():
    assert cv.effective_floor(0) == 5   # calibrated 4 -> 5 on exhibit A (see conviction.py)
    assert cv.effective_floor(1) == 6
    assert cv.effective_floor(2) == 7
    assert cv.effective_floor(3) == 8   # the 4th entry of a day needs a PERFECT score


def test_ratchet_makes_a_perfect_score_the_ceiling_not_a_loophole():
    """No k can demand more than the max — but at k=3 only an 8 clears, which is the
    intended 'you only need one' behaviour, not an accidental hard stop."""
    assert cv.MAX_SCORE == 8
    assert cv.effective_floor(3) == cv.MAX_SCORE
    assert cv.effective_floor(4) > cv.MAX_SCORE  # 5th entry is unreachable BY DESIGN


def test_ratchet_never_raises_on_garbage_k():
    assert cv.effective_floor(None) == cv.DEFAULT_FLOOR      # type: ignore[arg-type]
    assert cv.effective_floor(-3) == cv.DEFAULT_FLOOR
    assert cv.effective_floor("x") == cv.DEFAULT_FLOOR       # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# EXHIBIT A — the 2026-08-12 book must mostly FAIL
# --------------------------------------------------------------------------------------
def test_exhibit_A_unnamed_level_entry_cannot_clear_even_the_base_floor():
    """'If you can't name the level, there's no trade.' 89% of bear ENTERs came through the
    trendline-only bypass (no named level); that blind cohort is −$1,830 / WR 0.19 / n=124.
    Without C1's +2 the maximum reachable is 6 — but with no level there is also no C2/C3/C7,
    capping realistic scores at 2."""
    r = cv.score_conviction(
        side="P", entry_level=773.00, level_records=[],   # nothing named nearby
        triggers_fired=["level_rejection"], level_states={},
        trigger_close=772.50, envelope_high=775.03, envelope_low=771.30,
        structure_side=None, confluence_zones=[], k=0)
    assert r.components["named_level"] == 0
    assert r.total < cv.effective_floor(0), f"unnamed entry cleared the floor: {r.to_dict()}"
    assert r.would_block is True


def test_exhibit_A_long_at_the_TOP_of_the_range_loses_the_range_component():
    """The 08-12 signature: BULLISH_RECLAIM fired at 773-774, the top of a 3-day range whose
    high band was 774.53-775.03. A call there must NOT collect C4."""
    r = cv.score_conviction(
        side="C", entry_level=773.06,
        level_records=[{"price": 773.06, "label": "MEMORY_RES_225", "memory_score": 80}],
        triggers_fired=["level_reclaim"], level_states={},
        trigger_close=773.54, envelope_high=775.03, envelope_low=771.30,
        structure_side=None, confluence_zones=[], k=0)
    assert r.components["range_extreme"] == 0, (
        f"a long at the top of the range collected the range-extreme point: {r.to_dict()}")
    # THE CALIBRATION THIS EXHIBIT FORCED. At the v0 floor of 4 this entry scored EXACTLY 4
    # (named 2 + remembered 1 + fresh 1, range position 0.601 = mid-range) and PASSED —
    # level identity alone cleared the bar. Floor raised to 5 so a trade must also earn at
    # least one point of CONTEXT. If a future weight change lets this entry pass again, the
    # score has stopped measuring what it was built to measure.
    assert r.total == 4, f"exhibit A's score drifted from 4: {r.to_dict()}"
    assert r.would_block is True, f"08-12's signature entry cleared the floor: {r.to_dict()}"


def test_exhibit_A_the_4th_entry_of_a_churn_day_needs_a_near_perfect_score():
    """Even a decent setup must fail late in a churn day — that is the ratchet doing the
    work a flat trade-cap cannot (a flat cap spends itself on the first two losers)."""
    kw = dict(
        side="C", entry_level=771.44,
        level_records=[{"price": 771.44, "label": "MEMORY_SUP_162", "memory_score": 96}],
        triggers_fired=["level_reclaim", "confluence"], level_states={"771.44": {"bounce_history": []}},
        trigger_close=771.60, envelope_high=775.03, envelope_low=771.30,
        structure_side=None, confluence_zones=[])
    first = cv.score_conviction(**kw, k=0)
    third = cv.score_conviction(**kw, k=2)
    assert first.would_block is False, f"a good setup must pass as entry #1: {first.to_dict()}"
    assert third.would_block is True, "the same setup must NOT pass as the 3rd entry"
    assert third.total == first.total  # identical evidence, different bar


# --------------------------------------------------------------------------------------
# EXHIBIT B — J's 12:35 bounce must PASS
# --------------------------------------------------------------------------------------
def test_exhibit_B_J_1235_bounce_clears_the_base_floor():
    """2026-08-12 12:35 ET: long off 771.3-771.44 support — a NAMED level (MEMORY_SUP_162,
    96 touches), MULTI-DAY (08-10 low 771.91, 08-12 low 771.30), FRESHLY tested, at the
    BOTTOM of the 3-day envelope, inside the 4-source confluence zone 770.48-771.44 that was
    literally on disk and read by nothing. This is the trade the engine must be able to take."""
    r = cv.score_conviction(
        side="C", entry_level=771.44,
        level_records=[{"price": 771.44, "label": "MEMORY_SUP_162",
                        "memory_score": 96, "multi_day": True}],
        triggers_fired=["level_reclaim", "confluence"],
        level_states={"771.44": {"bounce_history": [{"bar_idx": 1}]}},
        trigger_close=772.19, envelope_high=775.03, envelope_low=771.30,
        structure_side="C",
        confluence_zones=[{"low": 770.48, "high": 771.44, "n_sources": 4}],
        k=0)
    assert r.components["named_level"] == 2
    assert r.components["multi_day_memory"] == 1
    assert r.components["fresh_test"] == 1
    assert r.components["range_extreme"] == 1, f"range pos {r.components.get('range_position')}"
    assert r.components["zone_stack"] == 1
    assert r.total >= cv.effective_floor(0), f"J's bounce was BLOCKED: {r.to_dict()}"
    assert r.would_block is False


def test_exhibit_B_survives_losing_the_soft_structure_point():
    """C5 is deliberately SOFT — blocking zero-structure entries costs Tuesday −$2,091
    because early gap entries are always zero-structure. J's bounce must still clear
    floor 4 with structure absent."""
    r = cv.score_conviction(
        side="C", entry_level=771.44,
        level_records=[{"price": 771.44, "label": "MEMORY_SUP_162", "memory_score": 96}],
        triggers_fired=["level_reclaim", "confluence"],
        level_states={"771.44": {"bounce_history": []}},
        trigger_close=772.19, envelope_high=775.03, envelope_low=771.30,
        structure_side=None,
        confluence_zones=[{"low": 770.48, "high": 771.44, "n_sources": 4}], k=0)
    assert "structure" in r.degraded_components
    assert r.would_block is False, f"soft component became load-bearing: {r.to_dict()}"


# --------------------------------------------------------------------------------------
# Degradation contract — a broken sensor must never silently strangle the book
# --------------------------------------------------------------------------------------
def test_every_absent_sensor_names_itself():
    r = cv.score_conviction(side="P", entry_level=None, level_records=None,
                            triggers_fired=None, level_states=None, trigger_close=None,
                            envelope_high=None, envelope_low=None, structure_side=None,
                            confluence_zones=None, k=0)
    for name in ("named_level", "fresh_test", "range_extreme", "structure",
                 "elite_trigger", "zone_stack"):
        assert name in r.degraded_components, f"{name} degraded silently: {r.degraded_components}"
    assert r.total == 0


def test_scoring_never_raises_on_malformed_records():
    """Ledger/state files are a patchwork; a bad row must not take down the tick."""
    for bad in ([{"price": "abc"}], [None], ["not-a-dict"], [{}], [{"price": float("nan")}]):
        r = cv.score_conviction(side="C", entry_level=771.0, level_records=bad,
                                triggers_fired=["x"], level_states={"junk": None},
                                trigger_close=771.0, envelope_high=772.0, envelope_low=770.0,
                                structure_side="C", confluence_zones=[{"low": "x"}], k=0)
        assert 0 <= r.total <= cv.MAX_SCORE


def test_side_polarity_is_not_symmetric():
    """VARY-AND-ASSERT: the SAME location must score the range component for exactly one
    side. Proves C4 reads direction rather than just proximity to an extreme."""
    kw = dict(entry_level=771.44,
              level_records=[{"price": 771.44, "label": "L", "memory_score": 96}],
              triggers_fired=["confluence"], level_states={},
              trigger_close=771.40, envelope_high=775.03, envelope_low=771.30,
              structure_side=None, confluence_zones=[], k=0)
    call = cv.score_conviction(side="C", **kw)
    put = cv.score_conviction(side="P", **kw)
    assert call.components["range_extreme"] == 1
    assert put.components["range_extreme"] == 0


def test_max_score_is_actually_reachable():
    """C13: a tier nobody can reach is a dead knob. A perfect setup must total exactly 8,
    otherwise the k=4 ratchet rung is unsatisfiable and the 5th entry is a silent hard stop."""
    r = cv.score_conviction(
        side="C", entry_level=771.44,
        level_records=[{"price": 771.44, "label": "MEMORY_SUP_162",
                        "memory_score": 99, "multi_day": True}],
        triggers_fired=["level_reclaim", "confluence", "sequence_bull"],
        level_states={"771.44": {"bounce_history": []}},
        trigger_close=771.35, envelope_high=775.03, envelope_low=771.30,
        structure_side="C",
        confluence_zones=[{"low": 770.0, "high": 772.0, "n_sources": 5}], k=0)
    assert r.total == cv.MAX_SCORE == 8, r.to_dict()
    assert r.degraded_components == ()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
