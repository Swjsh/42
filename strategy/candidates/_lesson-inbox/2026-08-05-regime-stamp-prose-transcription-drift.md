## Lesson candidate: an LLM prompt "carry these 4 fields forward" instruction is not a contract — it silently dropped 3 of 4

**Date:** 2026-08-05
**Source:** conductor fire (AFTERHOURS 20:30 ET), commit `2bbc00fedef9`

**Symptom:** `today-bias.json#regime_context.one_liner` was correctly populated, but
`yesterday_archetype`, `stamp_date`, and `source` were all `null` — flagged
simultaneously by two independent producers today: `monday_verify.py`'s WS6 check
(RED, 16:15 ET) and `self_check.py`'s DEGRADED problem list (20:09 ET).

**Root cause:** `regime_stamp.py` (Gamma_RegimeStamp, 08:22 ET, deterministic Python)
correctly patches all 4 `regime_context` fields into `today-bias.json`. `Gamma_Premarket`
(08:30 ET) is an **LLM-prompt-driven session** that rewrites `today-bias.json` wholesale
and is instructed in `premarket.md` Step 3 (prose) to carry the same 4 fields forward
verbatim. On 2026-08-05 the running Premarket session only transcribed `one_liner`
correctly and silently wrote `null` for the other 3 — no error, no crash, just a quieter
version of the field the instruction asked for.

**Class:** C14 (dead/translated-but-unapplied knobs) has a sibling here worth naming
explicitly: a **producer→consumer handoff where the consumer is an LLM prompt** rather
than code is *never* a reliable contract, even when the prose is completely
unambiguous and even when it worked correctly the previous N days. Prose instructions to
an LLM session degrade silently under context pressure / paraphrase drift; only a second
deterministic writer (or a schema-validated read, per `backtest/lib/contracts/models.py`)
closes the loop.

**Fix shipped this fire:** `regime_stamp.main()` is idempotent and $0. Added a 2nd daily
scheduled-task trigger at 08:40 ET (10 min after Premarket normally finishes) that
re-runs the same script, so the deterministic patch is always the LAST writer regardless
of what the LLM session transcribed. Guard: `backtest/tests/test_regime_stamp_repatch.py`
(4/4) reproduces the exact drift and RED-proofs both triggers stay registered.

**Generalizable guidance for lesson-author:** any `automation/prompts/*.md` step that
says "carry field X from file A into file B" where B is written by that SAME prompt
session is a drift risk. Prefer (a) a deterministic post-patch step re-asserting the
field from the authoritative source, as done here, or (b) a `self_check.py`-style
detector PLUS an automatic remediator (per L252's own lesson: "a detector without an
automatic remediator re-violates on its own schedule") rather than a detector alone.
