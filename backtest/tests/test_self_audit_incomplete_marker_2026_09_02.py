"""Guard for self_audit._mark_if_incomplete (silent model-truncation corruption).

WHY (2026-09-02, root-caused live): the 2026-09-01T17:31:48 self-audit batch's
12th flagged gap landed in new-gaps-flagged.md reading "Systemic The live-watch
field-completeness fix is sound, but the" -- a sentence fragment, no visible
truncation marker. Traced to the SOURCE: `analysis/swarm-consult/2026-09-01-
173002-...json` perspective 3 (model liquid/lfm-2.5-2.6b:free) has
`output_tokens == 2500 == max_tokens_per_perspective` exactly -- the model's
own generation was cut off mid-sentence by the token cap on the LAST line of
its response, so the single-line bullet regex captured the fragment intact and
`_soft_truncate` never fired (it was already under the 240-char limit). The
240-char cut already marks itself with " [...]"; this closes the same gap for
the other truncation source so a reader can tell "genuinely incomplete" from
"short but complete" without re-opening the raw consult JSON.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import self_audit  # noqa: E402


def test_real_observed_fragment_gets_marked():
    """The EXACT fragment that leaked into new-gaps-flagged.md 2026-09-01T17:31:48."""
    body = "- Systemic The live-watch field-completeness fix is sound, but the"
    gaps = self_audit._extract_gaps(self_audit_consult(body))
    assert gaps, "real gap should survive extraction"
    assert gaps[0].endswith(" [...]"), f"mid-sentence fragment must be marked, got {gaps[0]!r}"


def self_audit_consult(synth_body):
    return {"perspectives": [], "synthesis": {"content": synth_body}}


def test_complete_sentence_not_marked():
    body = "- Real-time OPRA data-health gate is missing from the premarket sequence."
    gaps = self_audit._extract_gaps(self_audit_consult(body))
    assert gaps == ["Real-time OPRA data-health gate is missing from the premarket sequence."]


def test_complete_sentence_no_terminal_punctuation_but_closes_paren():
    # A gap ending in a closing paren/bracket/quote is a legitimate complete thought.
    assert self_audit._mark_if_incomplete("The gate never re-validates (see L182)") == \
        "The gate never re-validates (see L182)"


def test_headline_style_gap_without_period_not_marked():
    """The FALSIFIED first draft of this fix required terminal punctuation and
    over-flagged real gap headlines -- caught by test_self_audit_extract.py going
    RED before this shipped. Period-less noun-phrase headlines are normal LLM
    bullet style, not truncation, and must never be marked."""
    assert self_audit._mark_if_incomplete("Filter 5/9 static thresholds") == \
        "Filter 5/9 static thresholds"
    assert self_audit._mark_if_incomplete(
        "Real-time OPRA data-health gate is missing from the premarket sequence"
    ) == "Real-time OPRA data-health gate is missing from the premarket sequence"


def test_already_soft_truncated_not_double_marked():
    assert self_audit._mark_if_incomplete("a long gap statement [...]") == \
        "a long gap statement [...]"


def test_mid_word_cutoff_gets_marked():
    assert self_audit._mark_if_incomplete("the fix is sound, but the") == \
        "the fix is sound, but the [...]"


def test_soft_truncate_marker_not_doubled_up():
    """A bullet that hits BOTH the 240-char soft-truncate AND would otherwise look
    incomplete must end with exactly ONE ' [...]', not two."""
    long_sentence = "word " * 100  # far past _SYNTH_BULLET_LIMIT, no terminal punctuation
    body = f"- {long_sentence}"
    gaps = self_audit._extract_gaps(self_audit_consult(body))
    assert gaps
    assert gaps[0].count("[...]") == 1
