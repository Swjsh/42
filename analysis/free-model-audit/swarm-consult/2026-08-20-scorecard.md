# free-model-audit — swarm_consult — 2026-08-20

**Subject:** `swarm_consult`  
**Generated:** 2026-08-20T21:02:06  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 3 |
| Already graded (skipped, dedupe) | 1 |
| Newly graded this run | 2 |
| Correct | 0 |
| Wrong | 2 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 0/2 = **0.0%** |
| Graded via counterfactual replay | 0 |
| Graded via blind Sonnet judgment (fallback) | 2 |

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
| Evidence points | 16 |
| Cumulative correct-grade rate | **18.8%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| consult:2026-08-20-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer identifies specific, verifiable gaps grounded in current live data (Rule 4 adding  |
| consult:2026-08-19-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer prioritizes bull-direction ratification and inter-arm clustering gates as top gaps |

## Verdict

**NOT YET CONFIDENT** — cumulative 18.8% (bar 85%), streak 0/3 consecutive runs above bar.

