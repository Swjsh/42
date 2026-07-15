# FREE-MODEL AUDIT HARNESS — Claude grades every free-tier model in the loop (Fable design, 2026-07-11)

> J (2026-07-11, reacting to the twin oversight pyramid's nightly free-LLM review): "that is good
> but also worries me about the logic. we need to audit it every other day until we're confident
> in it. audit the logs, logic, thought process, what it vetoed, what it brought to the table,
> what it did in crypto. put it into a reusable harness framework we can benchmark and score to
> improve. anything we create with free stuff needs trained with our smart claude llms."
>
> Standing rule this doc encodes: **no free-tier model earns trust by existing.** Every free-model
> component that can veto, advise, or otherwise influence a decision path gets periodically graded
> by Claude against ground truth (or, absent ground truth, blind independent Claude re-judgment)
> before it's allowed to run unaudited. This generalizes the pattern this codebase already proved
> once — `shadow_model_eval.py` scoring Nemotron against `decisions.jsonl` at a ≥85%/≥15-day bar —
> to every OTHER free-model touchpoint, not just the shadow heartbeat experiment.

## Why this is separate from shadow_model_eval.py

`shadow_model_eval.py` answers one question: "could this free model REPLACE Claude on the
heartbeat." It's a promotion gate for a candidate replacement.

This harness answers a different, ongoing question: "is the free-model logic we've ALREADY WIRED
into a live decision path (veto gates, nightly reviews, idea-scanners) still trustworthy, on a
recurring cadence, forever" — a standing audit, not a one-time promotion exam. It reuses
`shadow_model_eval.py`'s scorecard conventions (markdown + jsonl ledger) rather than inventing new
ones, but the subject matter and cadence model are different.

## Architecture

`setup/scripts/free_model_audit.py` — pluggable `AUDIT_SUBJECTS` registry. Each subject is an
adapter that yields normalized `AuditItem`s for a time window:

```
AuditItem{subject, item_id, timestamp, context, free_model_output, ground_truth_or_None}
```

**Grading — each subject's adapter picks the ground-truth shape that fits it; never fabricate a
grade regardless of which method is used:**
1. **Counterfactual replay (objective, preferred where a $ counterfactual exists).** For a
   VETOED signal: did the blocked entry actually go on to win or lose? Reuses `trade_autopsy.py`'s
   counterfactual-replay mechanism (already built for every REAL fill) applied to the mirror case
   — a signal that never filled. False-veto (blocked a winner) is tracked SEPARATELY from
   true-veto (blocked a loser) — it's the costlier error class on an already-selective production
   gate. Used by `heartbeat_veto`.
2. **Blind Claude re-judgment (fallback).** When replay is genuinely infeasible (missing bar data),
   Claude sees the SAME snapshot the free model saw, answers independently before seeing the free
   model's verdict (no anchoring), then agreement is scored. Used by `heartbeat_veto` as its own
   fallback.
3. **Deterministic cross-check (agreement with a SECOND, independently-computed deterministic
   judge, or record-linkage against a downstream outcome — no LLM call).** Some subjects have no
   "$ counterfactual" question at all — `twin_review`'s nightly free-LLM HEALTHY/DEGRADED/
   CONCERNING read is graded by agreement with `twin_sentinel.py`'s deterministic RED/YELLOW/
   GREEN verdict for the same day (recorded snapshot preferred, `evaluate()`-reconstruction
   fallback since no sentinel-history file exists yet). `prospector`'s idea-promotion judgment is
   graded by pure record-linkage: did the promoted idea later show up as a `kind:"kill"` row in
   ideas-ledger.jsonl, or with a KILL/CLEAR verdict word in an `analysis/recommendations/`
   artifact that mentions its dedupe_key? Both tagged `grading_method: deterministic_cross_check`.
4. `swarm_consult`'s open-ended brainstorm/decide/critique/audit answers have neither a $
   counterfactual nor a second deterministic source, so blind Claude re-judgment (method 2) is
   PROMOTED to its primary (not fallback) method: Claude answers the same question blind, then a
   SEPARATE call scores whether that blind answer and the swarm's synthesis reach the same
   conclusion. Capped at 5 consults/run to bound cost (2 Claude calls per graded item).
5. Every method above is tagged (`counterfactual` / `llm_judgment` / `deterministic_cross_check` /
   `ungraded_insufficient_data`) — never fabricate a grade. Grading calls are Sonnet-tier
   (mechanical bulk work), never Fable, per standing model-routing doctrine.

**Confidence bar (reused, not reinvented):** ≥85% correct-grade rate over ≥15 graded evidence
points, sustained across ≥3 consecutive audit runs — the same numeric bar this codebase already
uses for Nemotron shadow promotion. Below bar: stay on J's every-other-day cadence. At/above bar:
auto-relax that subject to weekly and log it to STATUS.md — no permission needed, this is a
data-driven graduation, not a judgment call.

**Cadence:** ONE scheduled task (`Gamma_FreeModelAudit`), DailyTrigger (proven-safe; this repo has
a documented lesson about interval/one-time triggers going dark silently). The script self-gates
internally against a persisted `last_run_date` — every-other-day by default, catch-up-safe, and
every skip is LOGGED (never a silent no-op).

## Subjects (build order)

| Subject | Stakes | Ground truth | Status |
|---|---|---|---|
| `heartbeat_veto` | **Highest** — blocks real paper trades right now | Counterfactual replay via trade_autopsy.py | B1, first wired |
| `twin_review` | Medium — crypto twin is a $ investment in infra, not P&L | twin-sentinel.json's deterministic verdict (`deterministic_cross_check`) | **B2, WIRED 2026-07-11.** `setup/scripts/free_model_audit_twin_review.py`. Real dry-run: 1/1 evidence point, INSUFFICIENT EVIDENCE (correctly not oversold on day one). |
| `prospector` | Low — idea generation, no order impact | Kill rows in ideas-ledger.jsonl + analysis/recommendations/ artifacts (`deterministic_cross_check`, no LLM call) | **B3, WIRED 2026-07-15.** `setup/scripts/free_model_audit_prospector.py`. Real run: 31/31 promoted ideas graded, INSUFFICIENT EVIDENCE — every promotion is still pending (no idea has cycled through a full battery to a recommendations scorecard yet); honestly reported, not guessed. |
| `swarm_consult` | Low — brainstorm quality, advisory only | Blind Sonnet re-answer + a 2nd Sonnet call scoring agreement (`llm_judgment`), capped at 5 consults/run | **B3, WIRED 2026-07-15.** `setup/scripts/free_model_audit_swarm_consult.py`. Real run: 5/5 graded (the 5 most recent daily "audit" consults, 07-09..07-13), 1/5 agreed with Sonnet's blind re-answer (20%) — INSUFFICIENT EVIDENCE (5/15 floor), correctly not extrapolated from n=5. |

## What "trained with our smart claude llms" means here (stated plainly, not assumed)

Two honest, buildable things — NOT literal fine-tuning of API-hosted free models (not feasible for
most of the roster):
1. **Grading, continuously** (this doc's main subject) — the mechanism above.
2. **Calibration data.** The graded ledger (agree/disagree examples with Claude's independent
   verdict attached) is a growing labeled dataset. For the LOCAL Ollama lanes we actually control
   (qwen3:14b hot-path per brain-sovereignty doctrine), this ledger is the natural source for
   future prompt/rubric calibration — exactly how `shadow_model_eval.py`'s rubric files already
   get iteratively refined from disagreement patterns. No new heavy training pipeline shipped
   tonight; this is the honest state of what's buildable now.

## Non-goals

- Never touches `heartbeat_core.py`, `params*.json`, or places any order — audit is strictly
  read-only on production decision paths.
- Never becomes a NEW single point of failure — if the harness itself breaks, that's a logged
  finding, not a silent block on the veto gate it's auditing (the gate keeps running either way).
- Not a replacement for `shadow_model_eval.py` — both exist, different questions.

## Cross-references

[[free-model-audit-harness]] (memory) · `analysis/free-model-audit/` (scorecard output) ·
`setup/scripts/shadow_model_eval.py` (reused pattern) · `setup/scripts/trade_autopsy.py` (reused
counterfactual mechanism) · CLAUDE.md OP-32 (the free-swarm-validation precedent this generalizes).
