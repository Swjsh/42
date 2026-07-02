# Lesson candidate — a "flagged-for-fix" research caveat re-labelled a guarded, lesson-encoded INTENTIONAL design as a bug

**Date:** 2026-07-02
**Source fire:** conductor, PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB frame-audit
**Themes:** C7 (silent success/measurement integrity) · C14 (dead-knob class) · corollary to L156, L197

## Symptom
The HIGH queue item `PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB` instructed: "`_params_to_kwargs` silently DROPS the v15 chandelier keys → every params-path A/B models exits WITHOUT the chandelier … Fix the kwargs mapping, add a vary-and-assert guard (chandelier key change must alter backtest exits)." Executing it as written would have (a) VIOLATED L156, (b) RED'd its existing guard `test_profit_lock_not_in_baseline.py`, and (c) re-introduced the exact measurement-integrity foot-gun L156 was written to prevent.

## Root cause
The behavior is INTENTIONAL, lesson-encoded (L156), and guard-protected — the chandelier is regime-conditional (net-negative on the volume-dominant trending IS windows), so mapping it into the params→baseline path would permanently bias every candidate comparison negative. The "dead-knob / flagged-for-fix" label originated in a research doc (`analysis/j-webull/PHASEC-port/RESULTS.md` caveat 7), which called the drop "C14 dead-knob class — flagged for fix as a separate task." That mislabel was transcribed verbatim into the queue as a HIGH actionable fix. Two false claims rode along: (1) it's a bug (it's design); (2) "every A/B verdict is suspect" (false — the drop is SYMMETRIC across both A/B arms, so relative verdicts are unaffected; only the baseline's absolute-vs-live P&L is conservative, which is the tradeoff L156 chose).

## Fix / guardrail
Before queueing (or executing) any "flagged-for-fix / dead-knob / silently-drops X" caveat as an actionable fix, verify it is NOT an intentional design by grepping the guards + LESSONS-LEARNED for the symbol (`grep -rn "profit_lock\|chandelier" backtest/tests` surfaces `test_profit_lock_not_in_baseline.py` → L156 in seconds). A behavior protected by a graduated guard is a design decision until proven otherwise; a research caveat is a hypothesis, not a work order. Generalizable rule: **a "dead-knob" is only dead if no guard and no lesson defends its absence — check both before proposing to restore it.** This fire also strengthened the L156 guard to use the REAL production key names (`v15_profit_lock_*`) + a non-vacuous real-params.json bite, so the misdiagnosis-applied-as-code cannot land silently.

## Related
- L156 (chandelier is regime-conditional; do NOT map profit_lock_* into `_params_to_kwargs`)
- L197 (a guard can bake in a frame you later need to correct — corollary: a guard can also correctly DEFEND a frame a later caveat wrongly attacks)
- OP-16 sim-accuracy gate (the caveat invoked this class by name — but symmetric absence ≠ sim-inaccuracy for relative A/B)
