# free-model-audit — prospector — 2026-07-15

**Subject:** `prospector`  
**Generated:** 2026-07-15T00:28:39  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 31 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 31 |
| Correct | 0 |
| Wrong | 0 |
| Ungraded (insufficient data) | 31 |
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
| promoted:gex_flip_from_banked_cboe:2026-07-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='gex_flip_from_banked_cboe' -- still pending |
| promoted:vix1d_gate:2026-07-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='vix1d_gate' -- still pending |
| promoted:data_feeds_free:cboe-buywrite-index-bxm-real-time-levels:2026-07-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:cboe-buywrite-index-bxm-real-time-levels' -- still pe |
| promoted:data_feeds_free:fred-daily-treasury-par-yield-curve-10y-:2026-07-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:fred-daily-treasury-par-yield-curve-10y-' -- still pe |
| promoted:data_feeds_free:nyse-openbook-auction-imbalance-data-pre:2026-07-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:nyse-openbook-auction-imbalance-data-pre' -- still pe |
| promoted:data_feeds_free:tick-index-nyse-tick:2026-07-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:tick-index-nyse-tick' -- still pending |
| promoted:data_feeds_free:treasury-treasury-bills-3-month-yield-fl:2026-07-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:treasury-treasury-bills-3-month-yield-fl' -- still pe |
| promoted:volume_shelf_tv_vp:2026-07-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='volume_shelf_tv_vp' -- still pending |
| promoted:tv_community_indicators:auto-support-resistance-zones-community-:2026-07-11 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:auto-support-resistance-zones-community-' --  |
| promoted:data_feeds_free:flowalgo-free-tier-spy-options-flow-with:2026-07-11 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:flowalgo-free-tier-spy-options-flow-with' -- still pe |
| promoted:tv_community_indicators:market-profile-tpo-built-in-indicator-pl:2026-07-11 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:market-profile-tpo-built-in-indicator-pl' --  |
| promoted:qqq_divergence_confluence:2026-07-11 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='qqq_divergence_confluence' -- still pending |
| promoted:data_feeds_free:treasuriesgov-real-time-2y-and-10y-yield:2026-07-11 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:treasuriesgov-real-time-2y-and-10y-yield' -- still pe |
| promoted:tv_community_indicators:volume-profile-visible-range-vpvr-shows-:2026-07-11 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:volume-profile-visible-range-vpvr-shows-' --  |
| promoted:options_structure_metrics:0dte-gamma-concentration-gamma-wall-iden:2026-07-12 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:0dte-gamma-concentration-gamma-wall-iden' - |
| promoted:options_structure_metrics:0dte-iv-skew-slope-25-delta-put-vs-25-de:2026-07-12 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:0dte-iv-skew-slope-25-delta-put-vs-25-de' - |
| promoted:cross_asset_signals:10y2y-treasury-yield-spread-ust10yust2y-:2026-07-12 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:10y2y-treasury-yield-spread-ust10yust2y-' -- stil |
| promoted:options_structure_metrics:cboe-vix1d-index-tracking:2026-07-12 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:cboe-vix1d-index-tracking' -- still pending |
| promoted:options_structure_metrics:intraday-putcall-volume-ratio-5-minute-b:2026-07-12 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:intraday-putcall-volume-ratio-5-minute-b' - |
| promoted:cross_asset_signals:vix-term-structure-slope-vix1d-minus-vix:2026-07-12 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:vix-term-structure-slope-vix1d-minus-vix' -- stil |
| promoted:futures_positioning:cftc-commitments-of-traders-large-specul:2026-07-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:cftc-commitments-of-traders-large-specul' -- stil |
| promoted:futures_positioning:cme-group-open-interest-change-oi-delta-:2026-07-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:cme-group-open-interest-change-oi-delta-' -- stil |
| promoted:futures_positioning:futures-term-structure-basis-between-fro:2026-07-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:futures-term-structure-basis-between-fro' -- stil |
| promoted:microstructure_internals:nyse-advance-decline-line-add-tracking-c:2026-07-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:nyse-advance-decline-line-add-tracking-c' -- |
| promoted:microstructure_internals:nyse-tick-index-measuring-net-upticks-vs:2026-07-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:nyse-tick-index-measuring-net-upticks-vs' -- |
| promoted:microstructure_internals:trinarms-index-combining-advancingdeclin:2026-07-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:trinarms-index-combining-advancingdeclin' -- |
| promoted:microstructure_internals:finra-daily-short-sale-volume-aggregated:2026-07-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:finra-daily-short-sale-volume-aggregated' -- |
| promoted:data_feeds_free:fred-daily-treasury-par-yield-curve-10y-:2026-07-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:fred-daily-treasury-par-yield-curve-10y-' -- still pe |
| promoted:data_feeds_free:iex-cloud-realtime-quotes-for-spy:2026-07-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:iex-cloud-realtime-quotes-for-spy' -- still pending |
| promoted:vix1d_gate:2026-07-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='vix1d_gate' -- still pending |
| promoted:volume_shelf_tv_vp:2026-07-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='volume_shelf_tv_vp' -- still pending |

## Verdict

**INSUFFICIENT EVIDENCE** — 0/15 graded points. Keep auditing every 2 days.

