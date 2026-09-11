# free-model-audit — twin_review — 2026-08-10

**Subject:** `twin_review`  
**Generated:** 2026-08-10T21:06:16  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 27 |
| Already graded (skipped, dedupe) | 1 |
| Newly graded this run | 26 |
| Correct | 10 |
| Wrong | 16 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 10/26 = **38.5%** |
| Graded via counterfactual replay | 0 |
| Graded via blind Sonnet judgment (fallback) | 0 |

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
| Evidence points | 29 |
| Cumulative correct-grade rate | **44.8%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| review:2026-07-14 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=2 reasons=[LOW_UPTIME: |
| review:2026-07-15 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-16 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-17 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-18 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-20 | CONCERNING | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-21 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-22 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-23 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-25 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-26 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-27 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-28 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-29 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-30 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-07-31 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-01 | DEGRADED | deterministic_cross_check | OK | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-02 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-03 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-04 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-05 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-06 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-07 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-08 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-09 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |
| review:2026-08-10 | HEALTHY | deterministic_cross_check | XX | sentinel_verdict=YELLOW (maps to expected_llm_assessment=DEGRADED) source=reconstructed_evaluate_call incidents_today=0 reasons=[LOW_UPTIME: |

## Verdict

**NOT YET CONFIDENT** — cumulative 44.8% (bar 85%), streak 0/3 consecutive runs above bar.

