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
    # 2026-07-19: the SAME synthesis cross-reference-noise class as the 07-01 fix,
    # a different lexical family ("all X agree/concur", plural "Perspectives N")
    # that leaked across the 07-09/07-10/07-11/07-13/07-18 batches untouched.
    "All perspectives agree that Gamma lacks continuous, autonomous validation/reconciliation mechanisms to ensure internal c",
    "All agree that missing real-time risk guards (hard stop, position-size limits, gate compliance) can lead to Rule 9/10 vi",
    "All concur that the system should be self-healing: detecting data-feed staleness, order-fill discrepancies, or strategy",
    "All perspectives agree that Project Gamma must eliminate silent gate bugs caused by `is not None` checks, duplicated log",
    "A majority (4/5) agree that Gamma should automatically validate that every gate-read field is actually populated by the",
    "All agree that automated validation/drift detection is missing: configuration drift, fill attribution/P&L reconciliation",
    "There is broad agreement that Gamma's *health-monitoring and self-healing* layer is insufficient: the scheduler (`wscrip",
    "Finally, all concur that Gamma should have an automated kill-switch or circuit-breaker (e.g., a file-trigger or cost l",
    "Perspectives 1, 2, 5 view the guard issue as a symptom of a broader class of problems (lack of pre-flight commit che",
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
    # non-over-rejection: real gaps from the SAME batches the consensus-leadin fix
    # targets, that do NOT open with a consensus lead-in, must still survive.
    "The current dead-knob/reconciliation guard is insufficient: it runs only in CI/test, uses static allow-lists, and cannot",
    "Real-time OPRA data-health gate",
    "The `orchestrator.py` `is not None` Time Bomb.",
    # non-over-rejection: 'majority'/'agree'/'all' mid-sentence (not a lead-in) must survive.
    "Position sizing should scale down after a majority of the week's trades are losers",
]


@pytest.mark.parametrize("s", SCAFFOLD)
def test_scaffold_rejected(s):
    assert self_audit._is_real_gap(s) is False, f"scaffold leaked: {s!r}"


@pytest.mark.parametrize("s", REAL_GAPS)
def test_real_gaps_kept(s):
    assert self_audit._is_real_gap(s) is True, f"real gap dropped: {s!r}"


def _consult(persp_bodies):
    return {"perspectives": [{"content": b} for b in persp_bodies], "synthesis": {"content": ""}}


def _synth_consult(synth_body):
    """Build a consult dict with the bullet(s) in the SYNTHESIS section (the
    unbolded-whole-line harvest path), not the perspective bold-lead-in path."""
    return {"perspectives": [], "synthesis": {"content": synth_body}}


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


def test_synthesis_bullet_soft_truncates_at_word_boundary():
    """2026-08-02: the raw [:120] slice cut mid-word (real observed fragment from the
    2026-08-01 batch: '...they provide a concrete, testable failure mode, '). The fix
    must never end a truncated gap mid-word, and must mark it as truncated."""
    long_sentence = (
        "The most rigorous perspectives are 3 and 5 (near-identical) because they "
        "provide a concrete, testable failure mode, quantified dollar impact, and a "
        "specific remediation step that the conductor can action without further "
        "research, discussion, escalation, or any additional human-in-the-loop "
        "clarification before the next scheduled fire begins its own bounded work."
    )
    body = f"- {long_sentence}"
    gaps = self_audit._extract_gaps(_synth_consult(body))
    assert gaps, "real long gap should survive extraction"
    g = gaps[0]
    assert len(g) <= self_audit._SYNTH_BULLET_LIMIT + len(" [...]")
    assert g.endswith(" [...]"), f"truncated gap must be marked, got {g!r}"
    # never cut mid-word: the char immediately before ' [...]' must not be followed
    # by more letters in the source (i.e. the kept prefix is a real word boundary)
    kept = g[: -len(" [...]")]
    assert long_sentence.startswith(kept)
    next_char_idx = len(kept)
    assert long_sentence[next_char_idx] == " ", "truncation did not land on a word boundary"


def test_bold_label_prefix_stripped_from_synthesis_bullet():
    """2026-08-02: real observed noise -- '**Most rigorous view:** Perspective 2
    provides the most end-to-end causal chain ...' flagged the LABEL, not the gap
    (this exact case is a 'Perspective N ...' cross-ref, itself correctly rejected
    by the existing _PERSPECTIVE_REF_RE filter once the label is stripped -- so this
    test uses a label prefix whose remainder IS a genuine, actionable gap statement).
    The label must be dropped, keeping only the substantive gap statement."""
    body = (
        "- **Key risk:** The recency-confirmation gate never re-validates after a "
        "live flip, letting stale evidence block trades indefinitely"
    )
    gaps = self_audit._extract_gaps(_synth_consult(body))
    assert gaps
    assert not gaps[0].lower().startswith("key risk")
    assert gaps[0].startswith("The recency-confirmation gate")


def test_bullet_with_no_bold_label_unaffected():
    """A synthesis bullet with no bold-label lead-in must pass through unchanged
    (short of the soft-truncate cap) -- the strip must not eat real gap text."""
    body = "- Real-time OPRA data-health gate is missing from the premarket sequence"
    gaps = self_audit._extract_gaps(_synth_consult(body))
    assert gaps == ["Real-time OPRA data-health gate is missing from the premarket sequence"]


def test_real_fixture_06_29_surfaces_real_gaps():
    """Lock the real-world regression against the committed 06-29 consult (skip if absent).

    2026-08-18: needle check changed from exact membership to prefix-match.
    Before the same-day fix (_join_bold_bullet), a perspective bold bullet
    like '1. **Filter 5/9 static thresholds** -- already proven root cause,
    no adaptive mechanism' extracted to ONLY the bold headline, dropping the
    explanation -- exactly the headline-only-fragment bug this same fire
    fixed for perspective bullets (synthesis bullets got the equivalent fix
    2026-08-02). The extractor now correctly KEEPS the full sentence, so the
    old exact-string assertions are stale by design, not a regression --
    updated to assert the real gap still surfaces (as a prefix of the fuller,
    more useful text) rather than re-asserting the old truncated behavior."""
    f = REPO / "analysis" / "swarm-consult" / "2026-06-29-173002-audit-audit-project-gamma-autonomous-0dte-spy-options-tr.json"
    if not f.exists():
        pytest.skip("06-29 consult fixture not present")
    import json
    gaps = self_audit._extract_gaps(json.loads(f.read_text(encoding="utf-8")))
    assert gaps, "extractor produced nothing on the real fixture"
    assert not any(g.strip().endswith(":") for g in gaps), "scaffold header leaked"
    # the 4 perspective-4 bold gaps must surface (they were crowded out before the fix) --
    # now with their full explanation attached, so match by prefix not exact string.
    for needle in ("Filter 5/9 static thresholds", "Silent task duplication",
                   "Intraday broker degradation blindness", "Anchor-day drift undetected"):
        assert any(g.startswith(needle) for g in gaps), \
            f"real gap missing from fixture extraction: {needle!r}"


# --- 2026-08-18 regression: perspective bold-bullet headline-only fragments ------
# 4th day running of the SAME triage class (08-15/16/17/18 batches each hand-triaged
# as "scaffold-crowding noise" without the root cause ever being fixed): the
# perspective numbered/dash bold-bullet regex only ever captured the text INSIDE
# `**...**`, discarding the explanation on the rest of the line -- unlike synthesis
# bullets, which got a full-line-capture fix back on 2026-08-02 (_strip_bold_label).

def test_perspective_bold_bullet_keeps_trailing_explanation():
    """Real observed fragment (2026-08-18 batch): '1. **Implement the watcher
    scripts** (`order-quality-watcher.py`, `margin-checker.py`, etc.) as
    lightweight services that publish events to the existing `automation/state/`
    folder.' used to extract to ONLY 'Implement the watcher scripts' -- an
    unreadable, contextless headline. Must now keep the full sentence."""
    body = (
        "1. **Implement the watcher scripts** (`order-quality-watcher.py`, "
        "`margin-checker.py`, etc.) as lightweight services that publish "
        "events to the existing `automation/state/` folder."
    )
    gaps = self_audit._extract_gaps(_consult([body]))
    assert gaps == [
        "Implement the watcher scripts (`order-quality-watcher.py`, "
        "`margin-checker.py`, etc.) as lightweight services that publish "
        "events to the existing `automation/state/` folder."
    ]


def test_perspective_bold_only_bullet_unaffected():
    """A bold bullet with nothing trailing it on the line (the old common
    case, e.g. real fixture 'Filter 5/9 static thresholds') must still
    extract to exactly the bold text, unchanged."""
    body = "1. **Filter 5/9 static thresholds**"
    gaps = self_audit._extract_gaps(_consult([body]))
    assert gaps == ["Filter 5/9 static thresholds"]


def test_perspective_template_label_bullet_still_rejected():
    """The join must NOT resurrect known prompt-template section labels
    ('Role:', 'Task:', 'Context:', 'Constraints:', 'Formatting:') just
    because instruction-restatement text follows them on the same line --
    these are the model echoing its own prompt skeleton, not a gap."""
    for label, tail in [
        ("Role", "Free-tier reasoning model for Project Gamma."),
        ("Task", "Audit the system for obvious gaps."),
        ("Context", "Recent commits show focus on postmortems."),
        ("Constraints", "Be direct, specific, rigorous. No filler."),
        ("Formatting", "List format as requested. Top 6-8."),
    ]:
        body = f"1. **{label}:** {tail}"
        gaps = self_audit._extract_gaps(_consult([body]))
        assert gaps == [], f"template label leaked through the join: {label!r} -> {gaps!r}"


def test_norm_does_not_glue_words_across_narrow_nbsp():
    """Real observed fixture text uses U+202F (narrow no-break space) inside
    'Rule 10' -- the alnum-strip regex only ever preserved literal ASCII
    ' ', so it silently fused this into 'rule10', defeating the space-anchored
    'rule 9'/'rule 10' scaffold-prefix match once full-line joining (this
    fire) gave the fused text enough words to slip past the old length<3
    guard that had accidentally been masking the bug."""
    assert self_audit._norm("Rule 10 violation") == "rule 10 violation"
    assert self_audit._is_real_gap("Rule 10 Trades occur despite violating a risk limit") is False


def test_most_rigorous_view_is_perspective_n_rejected():
    """Real observed noise (2026-08-18 synthesis 'Key disagreements' section):
    'The most rigorous view is Perspective 5 because it directly addresses
    the primary failure modes...' -- rating one perspective against the
    others, the same cross-reference-noise class as _PERSPECTIVE_REF_RE and
    _CONSENSUS_LEADIN_RE target, just a lead-in shape neither caught."""
    body = (
        "- The most rigorous view is Perspective 5 because it directly "
        "addresses the primary failure modes of a 0DTE SPY options trader."
    )
    gaps = self_audit._extract_gaps(_synth_consult(body))
    assert gaps == [], f"perspective-rating lead-in leaked: {gaps!r}"
    # non-over-rejection: a real gap that merely discusses which view is
    # "rigorous" mid-sentence, not as the bullet's own lead-in, must survive.
    assert self_audit._is_real_gap(
        "Position sizing should weight the most rigorous backtests higher"
    ) is True
