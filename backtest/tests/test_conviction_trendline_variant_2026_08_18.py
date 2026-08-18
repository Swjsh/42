"""Guard: conviction v2 (trendline anchor) -- the A/B arm that must stay SHADOW.

WHY IT EXISTS. Two live days, two winners, both entered on `trendline_rejection`:
2026-08-17 bold-2 +$360 and 2026-08-18 safe-2/bold-2 +$162. v0 scored EVERY one of them
**0/8** -- 104 post-fix rows, 100% would_block, outcome join delta_if_armed **-$522**. The
cause is structural, not calibration:

  * C1 pays +2 only for a NAMED HORIZONTAL level. A trendline is SLOPED and has no name, so
    the winner's `trigger_level_exact` is null and C1 is 0 BY CONSTRUCTION.
  * C4 ("puts want the TOP of the envelope") scores a breakdown at the session LOW as bad
    location -- which is exactly what a continuation entry is.

A gate that scores the only lane that fires at mid-VIX as zero can never validate, and
`min_contracts_equity_scaled` re-arm waits on that validation. So v2 generalises the two
components instead of bolting on a 9th:

  C1  "no named level, no trade"  ->  "no ANCHOR, no trade" (horizontal OR quality trendline)
  C4  "range extreme"             ->  "good location" (range extreme OR AT the line)

MAX_SCORE stays 8 so v0/v2 floors compare directly. J's standing instruction: "We'll just
keep it in shadow mode for now still."
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Plain import, matching the sibling conviction guards -- a spec_from_file_location reload
# here collides with whatever already put "conviction" in sys.modules and yields a broken
# module object (the same duplicate-instance class as the 2026-08-15 free-model-audit bug).
import conviction as cv  # noqa: E402

# The REAL same-day wick resistance from 2026-08-18's trendlines-live.json.
GOOD_LINE = {"kind": "resistance", "anchor_family": "wick", "tier": "same_day",
             "current_value": 768.12, "respect_count": 72, "violations": 0}
NOISE_LINE = {"kind": "support", "anchor_family": "body", "tier": "same_day",
              "current_value": 768.15, "respect_count": 3, "violations": 0}
SLICED_LINE = {"kind": "support", "anchor_family": "wick", "tier": "primary",
               "current_value": 768.10, "respect_count": 80, "violations": 25}

# The real 2026-08-18 winner geometry: entry 768.23, session 767.40-772.60, PUT.
WINNER = dict(side="P", entry_level=None, level_records=[],
              triggers_fired=["trendline_rejection"], trigger_close=768.23,
              envelope_high=772.6, envelope_low=767.4, k=0)


def test_v0_is_byte_identical_when_the_new_input_is_absent():
    """The running shadow series must stay comparable -- v2 is OPT-IN. If passing nothing
    changed v0's output, every pre-2026-08-18 row would become incomparable."""
    for side in ("P", "C"):
        for lvl in (None, 768.0):
            for trig in (["trendline_rejection"], ["level_rejection"], []):
                kw = dict(side=side, entry_level=lvl,
                          level_records=[{"label": "X", "price": 768.0}],
                          triggers_fired=trig, trigger_close=768.2,
                          envelope_high=772.6, envelope_low=767.4, k=1)
                assert (cv.score_conviction(**kw).to_dict()
                        == cv.score_conviction(**kw, trendline_records=None).to_dict())


def test_the_real_winner_goes_from_structurally_blind_to_scoring():
    """RED-PROOF, on the actual trade that paid +$82. v0 CANNOT score it above 0; v2 must."""
    v0 = cv.score_conviction(**WINNER)
    v2 = cv.score_conviction(**WINNER, trendline_records=[GOOD_LINE])
    assert v0.total == 0, "v0's blindness is the premise of this whole variant"
    assert v2.total >= 3, f"v2 should credit anchor(+2) and location(+1), got {v2.total}"
    assert v2.components["named_level"] == 2      # C1 satisfied by a SLOPED anchor
    assert v2.components["range_extreme"] == 1    # C4 satisfied by being AT the line
    assert v2.components["location_source"] == "at_trendline"


def test_diagnostics_never_reach_the_total():
    """`trendline_anchor` MIRRORS the C1 point it already granted. Summing the components
    dict would double-count the anchor and inflate every trendline entry by 2 -- the scorer
    uses an explicit allowlist for exactly this reason."""
    v2 = cv.score_conviction(**WINNER, trendline_records=[GOOD_LINE])
    assert v2.components["trendline_anchor"] == 2
    assert v2.total == sum(int(v2.components.get(k) or 0) for k in cv._SCORING_KEYS)
    assert v2.total <= v2.max_score == 8


def test_a_noisy_scribble_earns_nothing():
    """The higher-quality bar is the whole point -- a 3-touch line is not an anchor."""
    v2 = cv.score_conviction(**WINNER, trendline_records=[NOISE_LINE])
    assert v2.components["named_level"] == 0
    assert v2.total == 0


def test_a_repeatedly_sliced_line_earns_nothing():
    """80 respects but 25 violations is a line the tape ignores -- respects alone is the
    C25/L142 trap (high touch_count drives BOTH stars and eventual breaks)."""
    v2 = cv.score_conviction(**WINNER, trendline_records=[SLICED_LINE])
    assert v2.components["named_level"] == 0


def test_location_credit_requires_being_AT_the_line():
    """A quality line 4 dollars away is not this trade's location."""
    far = dict(GOOD_LINE, current_value=772.50)
    v2 = cv.score_conviction(**WINNER, trendline_records=[far])
    assert v2.components["named_level"] == 2, "still a valid anchor"
    assert v2.components["range_extreme"] == 0, "but NOT good location"


def test_no_trendline_trigger_means_no_trendline_credit():
    """v2 must not hand a horizontal-level trade a free anchor because some line happens to
    sit nearby -- the trigger has to actually be a trendline rejection."""
    kw = dict(WINNER, triggers_fired=["level_rejection"])
    v2 = cv.score_conviction(**kw, trendline_records=[GOOD_LINE])
    assert v2.components.get("trendline_anchor", 0) == 0
    assert v2.components["named_level"] == 0


def test_variant_is_wired_shadow_only_beside_v0():
    """AST: heartbeat_core computes the variant and attaches it, and NO branch consumes it.
    The day this becomes a decision input, it must be a deliberate, pre-registered edit."""
    import ast
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert "variant_tl" in src, "the A/B arm is not wired"
    assert "_read_shadow_trendlines" in src
    tree = ast.parse(src)
    for node in ast.walk(tree):          # no `if ... variant_tl ...` control flow anywhere
        if isinstance(node, (ast.If, ast.While)):
            if "variant_tl" in ast.dump(node.test):
                raise AssertionError("variant_tl reached a control-flow branch -- not shadow")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
