# free-model-audit — swarm_consult — 2026-08-26

**Subject:** `swarm_consult`  
**Generated:** 2026-08-26T23:50:52  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 4 |
| Already graded (skipped, dedupe) | 1 |
| Newly graded this run | 3 |
| Correct | 1 |
| Wrong | 2 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 1/3 = **33.3%** |
| Graded via counterfactual replay | 0 |
| Graded via blind Sonnet judgment (fallback) | 3 |

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
| Evidence points | 21 |
| Cumulative correct-grade rate | **19.0%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| consult:2026-08-26-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer identifies 8 specific, evidence-grounded gaps (churn loop bug, bear direction kill |
| consult:2026-08-24-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind answer identifies 8 specific, evidence-grounded infrastructure gaps (CDP watchdog probe dept |
| consult:2026-08-23-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | OK | blind-reanswer agreement=True reason=Both reach the same core conclusions: fix gate revalidation (naive mean → robust stats + auto-write las |

## Verdict

**NOT YET CONFIDENT** — cumulative 19.0% (bar 85%), streak 0/3 consecutive runs above bar.

