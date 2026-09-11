# free-model-audit — swarm_consult — 2026-08-10

**Subject:** `swarm_consult`  
**Generated:** 2026-08-10T21:06:15  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 5 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 5 |
| Correct | 2 |
| Wrong | 3 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 2/5 = **40.0%** |
| Graded via counterfactual replay | 0 |
| Graded via blind Sonnet judgment (fallback) | 5 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 0 / 0 |
| TRUE vetoes (correctly blocked a loser/marginal) | 0 |
| FALSE vetoes (wrongly blocked a winner) | 0 |
| **Veto-only accuracy** (the safety-net's actual job) | n/a |
| GO decisions graded | 0 / 0 |
| **GO-only accuracy** (fill went on to be non-losing) | n/a |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 0 / 0 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 10 |
| Cumulative correct-grade rate | **30.0%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| consult:2026-08-08-173002-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | OK | blind-reanswer agreement=True reason=Both answers identify the conductor budget multiplier as the top priority blocking all autonomous work, |
| consult:2026-08-07-173002-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer surfaces 4 gaps absent from the swarm's synthesis (bull re-eval overdue, per-arm f |
| consult:2026-08-06-173002-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer identifies specific, verified, numbered gaps (bull direction n=80 past re-eval thr |
| consult:2026-08-05-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer focuses on concrete operational gaps like overtrading gates, negative-expectancy b |
| consult:2026-08-04-173003-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | OK | blind-reanswer agreement=True reason=Both answers center on the same top priorities: VBS wrapper exit-code blindness poisoning all health si |

## Verdict

**INSUFFICIENT EVIDENCE** — 10/15 graded points. Keep auditing every 2 days.

