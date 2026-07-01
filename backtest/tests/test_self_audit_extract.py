"""Guard for self_audit._extract_gaps / _is_real_gap (the proactive gap-finder organ).

WHY (2026-06-29 conductor): the self-audit organ feeds the conductor work so J does
not have to point gaps out. On 2026-06-29 a whole batch of 12 "gaps" was 100% model
reasoning-scaffold -- "Analyze the Request:", "Role:", "Task:", "Risk score",
"Failure mode", "Rule 9" -- because the bold/bullet harvest grabbed the model's
chain-of-thought + the pre-ship-check template SECTION HEADERS, and 12 scaffold items
from one early perspective crowded the REAL gaps (in a later perspective) out of the
[:12] budget. A self-audit that flags pure noise is a C7 silent-failure in the
self-improvement loop. These tests lock the noise filter so it can't regress.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import self_audit  # noqa: E402

# The EXACT scaffold the 2026-06-29 batch flagged as "gaps" (all 12 were noise) plus
# the template section-headers seen across the 06-27/06-28 perspectives.
SCAFFOLD = [
    "Analyze the Request:", "Role:", "Task:", "Context:", "Constraints:",
    "Specific Output Format:", "Formatting:", "Final Polish:",
    "Identify Gaps (Brainstorming based on Principles & Context):",
    "Refine and Rank the Gaps:", "Drafting the Response (Iterative refinement for tone):",
    "Most likely failure mode", "Worst-case impact on J's environment",
    "Worst-case impact on Pilot/Heartbeat", "Hidden second-order effects",
    "Risk score", "Single most-important question the human reviewer should ask before shipping",
    "Failure mode", "Impact on J", "Impact on Pilot/Heartbeat", "Rule 9 / 10",
    "Rule 9", "Rule 10", "Trade missed", "Wrong direction", "Overfit",
    "First, a ranked list of 6-8 gaps (each with a brief description).",
    "Then, for the top gap (or maybe overall), produce the seven sections as requested.",
    # 2026-07-01 batch: the synthesis echoed a "Question for reviewer" template
    # section-name + cross-referenced each perspective as a bold lead-in. 5 of 9
    # flagged "gaps" were this scaffold -- crowding real gaps out of the [:12] cap.
    "Question for reviewer",
    "Perspective 2 flags the perpetual-RED state and lack of an automatic circuit-breaker as the most dangerous",
    "Perspective 3 zeroes in on an operational oversight: unbounded lesson-inbox CSV growth causing silent crashes",
    "Perspective 4 warns that widening history probes creates a history-slippage feedback loop that overfits",
    "Perspective 5 enumerates a broad checklist (latency failover, liquidity checks, ML retraining, retry logic).",
]

# The EXACT real gaps that must survive (from the 06-28/06-29 batches + perspective 4).
REAL_GAPS = [
    "Filter 5/9 static thresholds",
    "Silent task duplication",
    "Intraday broker degradation blindness",
    "Anchor-day drift undetected",
    "Gamma lacks automated statistical significance checking for new probes (e.g., flagging n<10 as inconclusive).",
    "Slippage analysis is limited to two fixed haircuts; no automated sweep across a range of slippage assumptions.",
    "No automated performance drift detection and kill-switch based on P&L drawdown",
    "Face UI approval button not wired to actuator",
    # non-over-rejection: a genuine gap that merely CONTAINS 'perspective' mid-sentence
    # must survive (the _PERSPECTIVE_REF_RE is anchored to a LEAD-IN + digit only).
    "Filter thresholds lack a per-perspective backtest validation before shipping",
]


@pytest.mark.parametrize("s", SCAFFOLD)
def test_scaffold_rejected(s):
    assert self_audit._is_real_gap(s) is False, f"scaffold leaked: {s!r}"


@pytest.mark.parametrize("s", REAL_GAPS)
def test_real_gaps_kept(s):
    assert self_audit._is_real_gap(s) is True, f"real gap dropped: {s!r}"


def _consult(persp_bodies):
    return {"perspectives": [{"content": b} for b in persp_bodies], "synthesis": {"content": ""}}


def test_scaffold_does_not_crowd_out_real_gaps():
    """THE load-bearing regression: scaffold in an EARLY perspective must not consume
    the [:12] budget before real gaps in a LATER perspective are reached (the exact
    2026-06-29 bug -- 12 scaffold items from perspective 0 starved 4 real gaps)."""
    scaffold_body = "\n".join(f"{i+1}. **{s}**" for i, s in enumerate(SCAFFOLD[:15]))
    real_body = "\n".join(f"- **{g}**" for g in REAL_GAPS[:4])
    gaps = self_audit._extract_gaps(_consult([scaffold_body, real_body]))
    for g in gaps:
        assert self_audit._is_real_gap(g), f"scaffold survived extraction: {g!r}"
    for g in REAL_GAPS[:4]:
        assert g in gaps, f"real gap crowded out: {g!r}"


def test_bite_filter_actually_removes_scaffold():
    """Non-vacuous: a perspective of PURE scaffold extracts to ZERO gaps (proving the
    filter bites -- without it, all 15 headers would be returned)."""
    scaffold_body = "\n".join(f"{i+1}. **{s}**" for i, s in enumerate(SCAFFOLD))
    raw_bolds = [s for s in SCAFFOLD]  # what the harvest would have grabbed
    assert len(raw_bolds) >= 12  # the harvest WOULD have filled the cap with noise
    gaps = self_audit._extract_gaps(_consult([scaffold_body]))
    assert gaps == [], f"pure-scaffold perspective should extract nothing, got {gaps!r}"


def test_no_trailing_colon_or_commit_hash_survives():
    assert self_audit._is_real_gap("Analyze the Context (Recent Commits):") is False
    assert self_audit._is_real_gap("6235d40") is False
    assert self_audit._is_real_gap("657ed9b/e385567/b20cc77") is False


def test_pilot_heartbeat_fused_token_rejected():
    """`Pilot/Heartbeat` normalizes to a fused token 'pilotheartbeat'; the multi-word
    prefix matcher must still reject it (this one leaked on the first fix pass)."""
    assert self_audit._is_real_gap("Impact on Pilot/Heartbeat") is False


def test_real_fixture_06_29_surfaces_real_gaps():
    """Lock the real-world regression against the committed 06-29 consult (skip if absent)."""
    f = REPO / "analysis" / "swarm-consult" / "2026-06-29-173002-audit-audit-project-gamma-autonomous-0dte-spy-options-tr.json"
    if not f.exists():
        pytest.skip("06-29 consult fixture not present")
    import json
    gaps = self_audit._extract_gaps(json.loads(f.read_text(encoding="utf-8")))
    assert gaps, "extractor produced nothing on the real fixture"
    assert not any(g.strip().endswith(":") for g in gaps), "scaffold header leaked"
    # the 4 perspective-4 bold gaps must surface (they were crowded out before the fix)
    for needle in ("Filter 5/9 static thresholds", "Silent task duplication",
                   "Intraday broker degradation blindness", "Anchor-day drift undetected"):
        assert needle in gaps, f"real gap missing from fixture extraction: {needle!r}"
