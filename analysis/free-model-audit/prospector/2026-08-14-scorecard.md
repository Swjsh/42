# free-model-audit — prospector — 2026-08-14

**Subject:** `prospector`  
**Generated:** 2026-08-14T21:00:04  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 14 |
| Already graded (skipped, dedupe) | 6 |
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
| promoted:microstructure_internals:finra-daily-short-sale-volume-total-shor:2026-08-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:finra-daily-short-sale-volume-total-shor' -- |
| promoted:data_feeds_free:fred-macroeconomic-indicators-feed-eg-10:2026-08-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:fred-macroeconomic-indicators-feed-eg-10' -- still pe |
| promoted:data_feeds_free:iex-cloud-free-realtime-lastsale-and-nbb:2026-08-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:iex-cloud-free-realtime-lastsale-and-nbb' -- still pe |
| promoted:microstructure_internals:trin-arms-index-advancing-issues-declini:2026-08-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='microstructure_internals:trin-arms-index-advancing-issues-declini' -- |
| promoted:data_feeds_free:us-treasury-daily-treasury-yield-curve-r:2026-08-13 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:us-treasury-daily-treasury-yield-curve-r' -- still pe |
| promoted:tv_community_indicators:market-profile-tpo-built-in-indicator-di:2026-08-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:market-profile-tpo-built-in-indicator-di' --  |
| promoted:tv_community_indicators:order-flow-imbalance-ofi-by-luxalgo-publ:2026-08-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='tv_community_indicators:order-flow-imbalance-ofi-by-luxalgo-publ' --  |
| promoted:data_feeds_free:reddit-rwallstreetbets-sentiment-via-pus:2026-08-14 | promoted | ungraded_insufficient_data | ? | no downstream kill row or recommendations artifact yet for dedupe_key='data_feeds_free:reddit-rwallstreetbets-sentiment-via-pus' -- still pe |

## Verdict

**INSUFFICIENT EVIDENCE** — 0/15 graded points. Keep auditing every 2 days.

