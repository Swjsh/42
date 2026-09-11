# free-model-audit — prospector — 2026-08-06

**Subject:** `prospector`  
**Generated:** 2026-08-06T21:00:13  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 10 |
| Already graded (skipped, dedupe) | 2 |
| Newly graded this run | 8 |
| Correct | 0 |
| Wrong | 0 |
| Ungraded (insufficient data) | 8 |
| This-run correct-grade rate | 0/0 = **0.0%** |
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
| Evidence points | 0 |
| Cumulative correct-grade rate | **0.0%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| promoted:tv_community_indicators:auto-support-resistance-zones-by-zeiierm:2026-08-05 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:auto-support-resistance-zones-by-zeiierm' --  |
| promoted:tv_community_indicators:order-flow-heatmap-by-luxalgo-public-pin:2026-08-05 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:order-flow-heatmap-by-luxalgo-public-pin' --  |
| promoted:tv_community_indicators:harmonic-pattern-indicator-by-alex-grove:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:harmonic-pattern-indicator-by-alex-grove' --  |
| promoted:options_structure_metrics:intraday-spy-0dte-putcall-ratio-pcr-by-s:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:intraday-spy-0dte-putcall-ratio-pcr-by-s' - |
| promoted:academic_intraday_anomalies:opening-range-breakout-orb-earlysession-:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:opening-range-breakout-orb-earlysession-' |
| promoted:options_structure_metrics:spy-0dte-implied-volatility-skew-iv-call:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-implied-volatility-skew-iv-call' - |
| promoted:options_structure_metrics:spy-0dte-max-pain-pin-level:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-max-pain-pin-level' -- still pendi |
| promoted:academic_intraday_anomalies:vwap-reversion-price-tends-to-revert-tow:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:vwap-reversion-price-tends-to-revert-tow' |

## Verdict

**INSUFFICIENT EVIDENCE** — 0/15 graded points. Keep auditing every 2 days.

