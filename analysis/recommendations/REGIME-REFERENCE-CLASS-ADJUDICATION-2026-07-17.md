# The 2025-vs-2026 reference-class question — frozen adjudication plan (Fable/Opus, 2026-07-17)

> Successor-in-spirit to WF-GATE-METHODOLOGY-2026-07-16 (does NOT supersede it until this
> completes + self-validates). This resolves WHICH in-sample data is the correct reference
> class for judging whether a 2026 config change is real vs overfit.

## The observation (5+ independent studies, same signature)
Every recent candidate parks on: **negative IS_delta in 2025, positive OOS_delta in 2026 YTD**
→ INSUFFICIENT_REGIME_SHIFT. Studies: bold-strike-axis (ATM), bold-strike-deltawf-readjudication,
elite-bear-level-reject-gate (goal L1), pong-resting-limit, zone-rejection-band. Five costumes,
one question. It blocks: Bold ATM tier, fleet strike tier, zone bands, the goal loop's decision
levers. This is THE constraint on profitability right now.

## The two interpretations (both dangerous to get wrong)
- **(A) Recency overfitting.** The 2026 "edges" are curve-fit to recent tape; 2025's disagreement
  is the honest out-of-sample truth screaming "this doesn't generalize." Acting on these = ship
  mirages that lose real money. (The elite-bear lever's fable-too-good hunt — top-3 trades carry
  the whole edge, placebo doesn't clear — is direct evidence THIS interpretation is live.)
- **(B) Genuine regime break.** 2026's market character (post-SS-B era, the gap-down/chop VIX
  regime we've traded all month) differs structurally from 2025, so 2025 is the WRONG reference
  class — the gate is rejecting regime-appropriate edges by testing them against irrelevant tape.
- **Getting (A) wrong** (treating overfit as regime-shift) → ratify money-losers.
  **Getting (B) wrong** (treating regime-shift as overfit) → reject real edges forever, stay
  unprofitable by construction. Both failure modes are expensive. This is not a pick-one.

## The resolution: regime-CONDITIONED validation, NOT drop-2025
Replace calendar IS/OOS with regime membership. Classify every historical period by its regime
(VIX band + trend character — use the existing context-bundle / market_structure primitives, the
same ones live). Then a candidate is REAL iff it works consistently WITHIN its target regime
ACROSS the whole history — including the (fewer) 2025 periods that share 2026's regime — not just
in 2026 calendar time. Overfit shows as "works in 2026 clock-time regardless of regime"; real
shows as "works in regime-X whenever regime-X occurred." This keeps an out-of-sample check (real,
not dropped) while removing the calendar confound.

## THE ANTI-METHODOLOGY-SHOPPING SAFEGUARD (non-negotiable — this is what makes it honest)
The obvious trap: reach for regime-conditioning BECAUSE it passes more candidates (motivated
reasoning). Guard against it with a MANDATORY self-validation BEFORE this methodology adjudicates
a single live candidate:
1. **Known-BAD reference must be KILLED by it.** Run through regime-conditioned validation: (a) the
   NLWB pattern (known-dead, real-fills FAILED 2026-05-21, WR 47.8%/-$1,294), (b) a pure-noise
   placebo (random-entry cohort), (c) 2-3 more killed candidates from the registry. If
   regime-conditioning PASSES any known-fake → it is methodology-shopping → REJECT it, keep
   calendar WF, and interpretation (A) stands (the parked edges are overfit; the honest goal
   ceiling is "today's specific outcome is largely noise, don't chase it").
2. **Known-GOOD reference must be PASSED by it.** J's OP-16 anchor trades / the setups we have
   real conviction are edges must survive. If it kills known-good too → it's just stricter, not
   better.
3. Pre-commit the pass/kill criteria + the regime classifier definition in a frozen prereg BEFORE
   running any of the above. No post-hoc tuning of the regime bands to get a desired answer.
Only if it correctly KILLS all known-bad AND PASSES all known-good is it allowed to re-adjudicate
the 5 parked candidates. If it fails self-validation, the honest answer to J is (A), stated plainly.

## Consumers waiting on the verdict
Goal L1 (elite-bear), Bold ATM tier, fleet strike tier (L4), zone bands, pong. All stay PARKED
under calendar-WF until this self-validates one way or the other.

## Execution
Opus drafted this frame. Sonnet runs the computation: freeze the prereg, build the regime
classifier, run the known-bad/known-good self-validation, report whether it earns the right to
adjudicate. NOTHING re-adjudicates or ships until self-validation passes. Weekend-appropriate.
