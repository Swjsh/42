# Lesson candidate: a free-model's own output-token cap can silently truncate mid-sentence, indistinguishable from a complete thought

**Class:** C7 (silent success is failure — audit outputs, not exit codes)

**Observed:** `analysis/self-audit/new-gaps-flagged.md`'s 2026-09-01T17:31:48 batch
(12 gaps) had its 12th item read "Systemic The live-watch field-completeness fix
is sound, but the" — a mid-clause fragment with no visible truncation marker,
sitting alongside 11 genuine gaps for an entire day before being noticed.

**Root cause (one sentence):** `swarm_consult.py`'s per-perspective call caps
generation at `max_tokens_per_perspective` (default 2500); one free-tier model
(`liquid/lfm-2.5-2.6b:free`) hit that cap exactly (`output_tokens: 2500`) mid-
sentence on the LAST line of its response, and the consumer (`self_audit.py`'s
`_extract_gaps`) had a length-based soft-truncate (240 chars, marks itself with
`" [...]"`) but no signal for a truncation that happens to already be short —
so a genuinely incomplete LLM response was indistinguishable from a short,
complete one.

**Fixed (this instance only):** `self_audit.py::_mark_if_incomplete` marks any
bullet ending on a dangling function word (article/conjunction/preposition —
the narrow, specific signature of a token-cutoff mid-clause) with the same
`[...]` marker. Also bumped `self_audit.py`'s own `--max-tokens-per-perspective`
2500→4000 to reduce recurrence frequency.

**Why this belongs in LESSONS-LEARNED (broader than one script):** any OTHER
`swarm_consult.py` consumer that extracts free-form bullets/prose from a
perspective or synthesis response has the SAME latent exposure — a small
free-tier model hitting its token cap produces a plausible-looking but
incomplete fragment, and nothing in the shared harness flags it. Worth
checking: `chef.py`, `swarm decision engine` callers, `free_model_audit.py`,
and any other `swarm_consult.py`-based extractor for the same missing signal.
A shared `mark_if_incomplete`-style helper in `swarm_consult.py` itself
(checked once, used by every consumer) would be more leveraged than fixing
each consumer independently.

**Guard shipped:** `backtest/tests/test_self_audit_incomplete_marker_2026_09_02.py`
(7 tests, RED-proofed live).
