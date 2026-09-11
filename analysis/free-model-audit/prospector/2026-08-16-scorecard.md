# free-model-audit — prospector — 2026-08-16

**Subject:** `prospector`  
**Generated:** 2026-08-16T21:00:10  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 15 |
| Already graded (skipped, dedupe) | 3 |
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
| promoted:tv_community_indicators:auto-support-and-resistance-levels-by-ze:2026-08-15 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:auto-support-and-resistance-levels-by-ze' --  |
| promoted:options_structure_metrics:dealer-gamma-exposure-dge-for-spy-0dte-b:2026-08-15 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:dealer-gamma-exposure-dge-for-spy-0dte-b' - |
| promoted:academic_intraday_anomalies:opening-range-breakout-orb-effect-intrad:2026-08-15 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:opening-range-breakout-orb-effect-intrad' |
| promoted:options_structure_metrics:spy-0dte-implied-volatility-skew-iv-skew:2026-08-15 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-implied-volatility-skew-iv-skew' - |
| promoted:options_structure_metrics:spy-0dte-max-pain-level-derived-from-dai:2026-08-15 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-max-pain-level-derived-from-dai' - |
| promoted:options_structure_metrics:spy-0dte-putcall-ratio-pcr-calculated-fr:2026-08-15 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-putcall-ratio-pcr-calculated-fr' - |
| promoted:cross_asset_signals:10y-2y-us-treasury-yield-spread-ust10y-u:2026-08-16 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:10y-2y-us-treasury-yield-spread-ust10y-u' -- stil |
| promoted:futures_positioning:cftc-commitments-of-traders-largespecula:2026-08-16 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:cftc-commitments-of-traders-largespecula' -- stil |
| promoted:cross_asset_signals:intraday-moves-of-the-us-dollar-index-dx:2026-08-16 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:intraday-moves-of-the-us-dollar-index-dx' -- stil |
| promoted:academic_intraday_anomalies:overnight-gapfill-in-equity-index-future:2026-08-16 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:overnight-gapfill-in-equity-index-future' |
| promoted:academic_intraday_anomalies:turnofmonth-futures-momentum-mesmnq-exhi:2026-08-16 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:turnofmonth-futures-momentum-mesmnq-exhi' |
| promoted:academic_intraday_anomalies:vwap-reversion-anomaly-prices-tend-to-re:2026-08-16 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:vwap-reversion-anomaly-prices-tend-to-re' |

## Verdict

**INSUFFICIENT EVIDENCE** — 0/15 graded points. Keep auditing every 2 days.

