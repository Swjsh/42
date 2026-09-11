# free-model-audit — prospector — 2026-08-10

**Subject:** `prospector`  
**Generated:** 2026-08-10T21:01:01  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 52 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 52 |
| Correct | 0 |
| Wrong | 0 |
| Ungraded (insufficient data) | 52 |
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
| promoted:tv_community_indicators:auto-supportresistance-zones-by-luxalgo-:2026-07-22 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:auto-supportresistance-zones-by-luxalgo-' --  |
| promoted:tv_community_indicators:harmonic-pattern-finder-by-chrismoody-de:2026-07-22 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:harmonic-pattern-finder-by-chrismoody-de' --  |
| promoted:tv_community_indicators:order-flow-imbalance-ofi-by-sanjay-cumul:2026-07-22 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:order-flow-imbalance-ofi-by-sanjay-cumul' --  |
| promoted:academic_intraday_anomalies:overnight-gap-fill-probability-based-on-:2026-07-23 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:overnight-gap-fill-probability-based-on-' |
| promoted:options_structure_metrics:spy-0dte-max-pain-level-strike-with-high:2026-07-23 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-max-pain-level-strike-with-high' - |
| promoted:academic_intraday_anomalies:the-lunchtime-lull-volatility-compressio:2026-07-23 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:the-lunchtime-lull-volatility-compressio' |
| promoted:academic_intraday_anomalies:the-opening-range-breakout-orb-predictiv:2026-07-23 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:the-opening-range-breakout-orb-predictiv' |
| promoted:cross_asset_signals:frontmonth-wti-crude-oil-price-change:2026-07-25 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:frontmonth-wti-crude-oil-price-change' -- still p |
| promoted:cross_asset_signals:intraday-moves-in-the-us-dollar-index-dx:2026-07-25 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:intraday-moves-in-the-us-dollar-index-dx' -- stil |
| promoted:futures_positioning:cftc-commitments-of-traders-cot-large-sp:2026-07-26 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:cftc-commitments-of-traders-cot-large-sp' -- stil |
| promoted:futures_positioning:frontmonth-to-secondmonth-basis-term-str:2026-07-26 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:frontmonth-to-secondmonth-basis-term-str' -- stil |
| promoted:futures_positioning:overnight-globex-session-highlowrange-fo:2026-07-26 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='futures_positioning:overnight-globex-session-highlowrange-fo' -- stil |
| promoted:data_feeds_free:nymex-cme-daily-open-interest-for-cme-mi:2026-07-27 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:nymex-cme-daily-open-interest-for-cme-mi' -- still pe |
| promoted:options_structure_metrics:0dte-gamma-concentration-index-sum-of-ga:2026-07-28 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:0dte-gamma-concentration-index-sum-of-ga' - |
| promoted:tv_community_indicators:anchored-vwap-avwap-by-zeiierman-public-:2026-07-28 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:anchored-vwap-avwap-by-zeiierman-public-' --  |
| promoted:options_structure_metrics:spy-0dte-putcall-ratio-ratio-of-total-0d:2026-07-28 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-putcall-ratio-ratio-of-total-0d' - |
| promoted:options_structure_metrics:spy-dark-pool-short-volume-ratio-proport:2026-07-28 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-dark-pool-short-volume-ratio-proport' - |
| promoted:academic_intraday_anomalies:intraday-vwap-mean-reversion:2026-07-29 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:intraday-vwap-mean-reversion' -- still pe |
| promoted:academic_intraday_anomalies:turnofthemonth-effect-in-equity-index-fu:2026-07-29 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:turnofthemonth-effect-in-equity-index-fu' |
| promoted:data_feeds_free:fred-macroeconomic-indicators-eg-initial:2026-08-01 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:fred-macroeconomic-indicators-eg-initial' -- still pe |
| promoted:data_feeds_free:reddit-wallstreetbets-sentiment-via-push:2026-08-02 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:reddit-wallstreetbets-sentiment-via-push' -- still pe |
| promoted:data_feeds_free:cme-order-imbalance-indicator-oib-for-cm:2026-08-04 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:cme-order-imbalance-indicator-oib-for-cm' -- still pe |
| promoted:cross_asset_signals:ice-bofa-us-high-yield-oas-credit-spread:2026-08-04 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='cross_asset_signals:ice-bofa-us-high-yield-oas-credit-spread' -- stil |
| promoted:tv_community_indicators:auto-support-resistance-zones-by-zeiierm:2026-08-05 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:auto-support-resistance-zones-by-zeiierm' --  |
| promoted:tv_community_indicators:order-flow-heatmap-by-luxalgo-public-pin:2026-08-05 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:order-flow-heatmap-by-luxalgo-public-pin' --  |
| promoted:tv_community_indicators:harmonic-pattern-indicator-by-alex-grove:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:harmonic-pattern-indicator-by-alex-grove' --  |
| promoted:options_structure_metrics:intraday-spy-0dte-putcall-ratio-pcr-by-s:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:intraday-spy-0dte-putcall-ratio-pcr-by-s' - |
| promoted:academic_intraday_anomalies:opening-range-breakout-orb-earlysession-:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:opening-range-breakout-orb-earlysession-' |
| promoted:options_structure_metrics:spy-0dte-implied-volatility-skew-iv-call:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-implied-volatility-skew-iv-call' - |
| promoted:options_structure_metrics:spy-0dte-max-pain-pin-level:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='options_structure_metrics:spy-0dte-max-pain-pin-level' -- still pendi |
| promoted:academic_intraday_anomalies:vwap-reversion-price-tends-to-revert-tow:2026-08-06 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='academic_intraday_anomalies:vwap-reversion-price-tends-to-revert-tow' |
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
| promoted:microstructure_internals:advancedecline-line-add-net-number-of-ad:2026-08-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:advancedecline-line-add-net-number-of-ad' -- |
| promoted:microstructure_internals:finra-daily-shortsale-volume-total-share:2026-08-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:finra-daily-shortsale-volume-total-share' -- |
| promoted:data_feeds_free:fred-macroeconomic-releases-eg-initial-j:2026-08-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:fred-macroeconomic-releases-eg-initial-j' -- still pe |
| promoted:microstructure_internals:nyse-tick-index-realtime-net-uptickdownt:2026-08-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:nyse-tick-index-realtime-net-uptickdownt' -- |
| promoted:microstructure_internals:trin-arms-index-ratio-of-advancing-volum:2026-08-09 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:trin-arms-index-ratio-of-advancing-volum' -- |
| promoted:tv_community_indicators:auto-fibonacci-retracement-levels-by-zei:2026-08-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:auto-fibonacci-retracement-levels-by-zei' --  |
| promoted:tv_community_indicators:cumulative-delta-order-flow-by-lazybear-:2026-08-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:cumulative-delta-order-flow-by-lazybear-' --  |
| promoted:data_feeds_free:iex-cloud-free-delayed-us-equity-quotes-:2026-08-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:iex-cloud-free-delayed-us-equity-quotes-' -- still pe |
| promoted:data_feeds_free:quiver-quant-free-unusual-options-activi:2026-08-10 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:quiver-quant-free-unusual-options-activi' -- still pe |

## Verdict

**INSUFFICIENT EVIDENCE** — 0/15 graded points. Keep auditing every 2 days.

