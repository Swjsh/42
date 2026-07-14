# free-model-audit — heartbeat_veto — 2026-07-13

**Subject:** `heartbeat_veto`  
**Generated:** 2026-07-13T21:00:02  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 2 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 2 |
| Correct | 1 |
| Wrong | 1 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 1/2 = **50.0%** |
| Graded via counterfactual replay | 2 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 0 / 0 |
| TRUE vetoes (correctly blocked a loser/marginal) | 0 |
| FALSE vetoes (wrongly blocked a winner) | 0 |
| **Veto-only accuracy** (the safety-net's actual job) | n/a |
| GO decisions graded | 2 / 2 |
| **GO-only accuracy** (fill went on to be non-losing) | **50.0%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 0 / 0 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 108 |
| Cumulative correct-grade rate | **70.4%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-07-13T12:39:04 | go | counterfactual | OK | replay pnl=$61.80 symbol=SPY260713P00750000 strike=750 equity_method=reason_text_scan |
| core:safe:2026-07-13T12:40:04 | go | counterfactual | XX | replay pnl=$-187.50 symbol=SPY260713P00750000 strike=750 equity_method=reason_text_scan |

## Verdict

**NOT YET CONFIDENT** — cumulative 70.4% (bar 85%), streak 0/3 consecutive runs above bar.

