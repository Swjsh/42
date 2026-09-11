# free-model-audit — prospector — 2026-08-08

**Subject:** `prospector`  
**Generated:** 2026-08-08T21:00:11  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 18 |
| Already graded (skipped, dedupe) | 6 |
| Newly graded this run | 12 |
| Correct | 0 |
| Wrong | 0 |
| Ungraded (insufficient data) | 12 |
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
| promoted:cross_asset_signals:10year-vs-2year-treasury-yield-spread-di:2026-08-07 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:10year-vs-2year-treasury-yield-spread-di' -- stil |
| promoted:cross_asset_signals:dxy-dollar-index-momentum:2026-08-07 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:dxy-dollar-index-momentum' -- still pending |
| promoted:academic_intraday_anomalies:lunchlull-volatility-compression-intrada:2026-08-07 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:lunchlull-volatility-compression-intrada' |
| promoted:academic_intraday_anomalies:overnight-gapfill-partial-fill-of-opento:2026-08-07 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:overnight-gapfill-partial-fill-of-opento' |
| promoted:academic_intraday_anomalies:turnofmonth-tom-effect-higher-returns-on:2026-08-07 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:turnofmonth-tom-effect-higher-returns-on' |
| promoted:cross_asset_signals:vix-termstructure-contangobackwardation-:2026-08-07 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:vix-termstructure-contangobackwardation-' -- stil |
| promoted:futures_positioning:cftc-commitments-of-traders-cot-largespe:2026-08-08 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:cftc-commitments-of-traders-cot-largespe' -- stil |
| promoted:futures_positioning:cme-daily-open-interest-and-change-for-e:2026-08-08 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:cme-daily-open-interest-and-change-for-e' -- stil |
| promoted:futures_positioning:futures-curve-and-basis-between-emini-co:2026-08-08 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:futures-curve-and-basis-between-emini-co' -- stil |
| promoted:futures_positioning:globex-overnight-us-night-highlowrange-f:2026-08-08 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:globex-overnight-us-night-highlowrange-f' -- stil |
| promoted:cross_asset_signals:highyield-credit-spread-relative-to-trea:2026-08-08 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:highyield-credit-spread-relative-to-trea' -- stil |
| promoted:cross_asset_signals:weekly-eia-crudeoil-inventory-surprise-d:2026-08-08 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:weekly-eia-crudeoil-inventory-surprise-d' -- stil |

## Verdict

**INSUFFICIENT EVIDENCE** — 0/15 graded points. Keep auditing every 2 days.

