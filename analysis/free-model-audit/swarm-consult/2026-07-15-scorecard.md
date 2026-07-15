# free-model-audit — swarm_consult — 2026-07-15

**Subject:** `swarm_consult`  
**Generated:** 2026-07-15T00:34:14  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 5 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 5 |
| Correct | 1 |
| Wrong | 4 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 1/5 = **20.0%** |
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
| Evidence points | 5 |
| Cumulative correct-grade rate | **20.0%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| consult:2026-07-13-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind answer focuses on verifiable live risks (stale OPRA cache, recency gate wiring, bull-directi |
| consult:2026-07-12-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The independent answer focuses on trading-system gaps (bull direction P&L bleed, body trendline family |
| consult:2026-07-11-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | OK | blind-reanswer agreement=True reason=Both answers identify the same core gaps: silent `is not None` gate bugs, bull-direction live fills nee |
| consult:2026-07-10-173001-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer focuses on live-capital-burning gaps (bull direction kill brake, recency RED not g |
| consult:2026-07-09-173002-audit-audit-project-gamma-autonomous-0dte-spy-options-tr | audit | llm_judgment | XX | blind-reanswer agreement=False reason=The blind re-answer identifies 8 specific, concrete, code-level gaps (recency gate not mechanically en |

## Verdict

**INSUFFICIENT EVIDENCE** — 5/15 graded points. Keep auditing every 2 days.

