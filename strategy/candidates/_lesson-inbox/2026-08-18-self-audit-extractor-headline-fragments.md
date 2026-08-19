# Lesson candidate: self-audit gap extractor produced headline-only fragments for 4 straight days before the root cause got fixed

**Date:** 2026-08-18 (conductor, AFTERHOURS)
**Class:** C7 (silent success is failure -- audit outputs, not exit codes) / re-violated-lesson-graduates-to-guard (OP-25)

## Symptom

`new-gaps-flagged.md`'s 2026-08-15, 08-16, 08-17, and 08-18 batches all landed unreadable,
contextless fragments ("Regime-stamp & bias modules", "Implement the watcher scripts") and
each got its OWN hand-triage note saying, verbatim across 3+ nights, "scaffold-crowding class
as prior batches" -- correctly identifying the SYMPTOM every single time without anyone ever
reading the extraction code to find the actual mechanism.

## Root cause

`self_audit.py`'s perspective bold-bullet regexes (`_NUM_BOLD_LINE_RE`/`_DASH_BOLD_LINE_RE`,
originally `re.findall(r"(?m)^\s*\d+\.\s+\*\*(.+?)\*\*", body)`) captured ONLY the text inside
`**...**` and threw away everything after it on the same line. The model's real perspective
markdown was perfectly readable ("**Implement the watcher scripts** (`order-quality-
watcher.py`, ...) as lightweight services that publish events to `automation/state/`") --
the extractor just discarded the back half. Synthesis bullets got the equivalent full-line-
capture fix on 2026-08-02 (`_strip_bold_label` + `_soft_truncate`); the sibling perspective-
bullet regexes never did, and nobody noticed the two code paths had diverged.

## Fix (this fire, `setup/scripts/self_audit.py`)

- `_join_bold_bullet()`: recombine the bold lead-in with its trailing explanation instead of
  discarding it.
- Extended `_CONSENSUS_LEADIN_RE` for a new lexical noise variant surfaced by the SAME batch:
  "The most rigorous view is Perspective N because..." (a perspective-rating lead-in neither
  `_PERSPECTIVE_REF_RE` nor the existing consensus-leadin patterns matched).
- The join surfaced two LATENT bugs that had been accidentally masked by the old short-capture
  behavior: known prompt-template labels ("Role:"/"Task:"/"Context:") would have started
  leaking once trailing text defeated the trailing-colon scaffold check (`_KNOWN_TEMPLATE_
  LABELS` guard added); and `_norm()` silently glued words together across U+202F narrow
  no-break spaces (fixed to collapse all unicode whitespace before stripping).
- 5 new regression tests in `backtest/tests/test_self_audit_extract.py`, RED-proofed via
  git-stash. 79/79 green.

## Suggested lesson-index entry

Fold into the C7 lessons theme (or start a new C7-adjacent row): **"A recurring self-flagged
noise pattern that gets the SAME hand-triage note 2+ nights running is itself the bug to fix
-- read the producer's code before writing another one-off triage note."** General form: when
an autonomous organ produces the same CLASS of noise repeatedly and each occurrence gets
individually explained away, that repetition count is the signal that the fix belongs in the
producer, not in another round of consumer-side triage.
