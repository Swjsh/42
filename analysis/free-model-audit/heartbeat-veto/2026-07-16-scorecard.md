# free-model-audit — heartbeat_veto — 2026-07-16

**Subject:** `heartbeat_veto`  
**Generated:** 2026-07-16T19:20:10  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 77 |
| Already graded (skipped, dedupe) | 43 |
| Newly graded this run | 34 |
| Correct | 21 |
| Wrong | 13 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 21/34 = **61.8%** |
| Graded via counterfactual replay | 34 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 24 / 24 |
| TRUE vetoes (correctly blocked a loser/marginal) | 13 |
| FALSE vetoes (wrongly blocked a winner) | 11 |
| **Veto-only accuracy** (the safety-net's actual job) | **54.2%** |
| GO decisions graded | 10 / 10 |
| **GO-only accuracy** (fill went on to be non-losing) | **80.0%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 4 / 24 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 185 |
| Cumulative correct-grade rate | **67.6%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-07-15T13:56:04 | go | counterfactual | XX | real fill pnl=$-117.00 symbol=SPY260715C00754000 |
| core:bold:2026-07-15T13:56:36 | go | counterfactual | OK | replay pnl=$-9.00 symbol=SPY260715C00757000 strike=757 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T13:57:14 | veto | counterfactual | XX | replay pnl=$49.80 symbol=SPY260715C00754000 strike=754 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T13:57:40 | go | counterfactual | OK | replay pnl=$-9.00 symbol=SPY260715C00757000 strike=757 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T13:58:03 | go | counterfactual | OK | replay pnl=$47.40 symbol=SPY260715C00754000 strike=754 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T13:58:38 | go | counterfactual | OK | replay pnl=$3.00 symbol=SPY260715C00757000 strike=757 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T13:59:03 | go | counterfactual | OK | replay pnl=$45.00 symbol=SPY260715C00754000 strike=754 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T13:59:20 | go | counterfactual | OK | replay pnl=$3.00 symbol=SPY260715C00757000 strike=757 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:00:05 | veto | counterfactual | XX | replay pnl=$45.00 symbol=SPY260715C00754000 strike=754 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T14:00:31 | go | counterfactual | OK | replay pnl=$2.40 symbol=SPY260715C00757000 strike=757 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:01:03 | veto | counterfactual | OK | replay pnl=$-72.00 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:02:04 | veto | counterfactual | OK | replay pnl=$-70.50 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:03:03 | veto | counterfactual | OK | replay pnl=$-69.00 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:04:03 | go | counterfactual | XX | replay pnl=$-75.00 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:05:04 | veto | counterfactual | XX | replay pnl=$26.40 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:16:04 | veto | counterfactual | XX | replay pnl=$60.60 symbol=SPY260715P00755000 strike=755 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T14:16:27 | veto | counterfactual | OK | replay pnl=$-16.50 symbol=SPY260715P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:17:04 | veto | counterfactual | XX | replay pnl=$58.80 symbol=SPY260715P00755000 strike=755 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T14:17:27 | veto | counterfactual | OK | replay pnl=$-15.00 symbol=SPY260715P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:18:03 | go | counterfactual | OK | replay pnl=$59.40 symbol=SPY260715P00755000 strike=755 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T14:18:19 | veto | counterfactual | OK | replay pnl=$-16.50 symbol=SPY260715P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:19:03 | veto | counterfactual | XX | replay pnl=$59.40 symbol=SPY260715P00755000 strike=755 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T14:19:29 | veto | counterfactual | OK | replay pnl=$-15.00 symbol=SPY260715P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:20:05 | veto | counterfactual | XX | replay pnl=$85.80 symbol=SPY260715P00755000 strike=755 equity_method=current_snapshot_fallback |
| core:bold:2026-07-15T14:20:34 | veto | counterfactual | XX | replay pnl=$24.80 symbol=SPY260715P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:21:04 | veto | counterfactual | XX | replay pnl=$19.80 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:22:04 | veto | counterfactual | XX | replay pnl=$20.40 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| core:safe:2026-07-15T14:23:03 | veto | counterfactual | XX | replay pnl=$89.90 symbol=SPY260715P00754000 strike=754 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-16T09:54:04:vwap_continuation | veto | counterfactual | OK | replay pnl=$-198.00 symbol=SPY260716P00751000 strike=751 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-16T09:55:04:vwap_continuation | veto | counterfactual | OK | replay pnl=$-201.00 symbol=SPY260716P00751000 strike=751 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-16T09:57:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-264.00 symbol=SPY260716P00752000 strike=752 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-16T09:58:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-235.50 symbol=SPY260716P00752000 strike=752 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-16T09:59:02:vwap_continuation | veto | counterfactual | OK | replay pnl=$-225.00 symbol=SPY260716P00752000 strike=752 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-16T10:00:04:vwap_continuation | veto | counterfactual | OK | replay pnl=$-183.00 symbol=SPY260716P00752000 strike=752 equity_method=current_snapshot_fallback |

## Verdict

**NOT YET CONFIDENT** — cumulative 67.6% (bar 85%), streak 0/3 consecutive runs above bar.


## Veto reason-class breakdown (VETO-HTF-CONFLICT-REGRADE, 2026-07-16 queue item)

Every graded VETO item, keyword-classified by its free-model reason string(s) into {htf_conflict, spread_data_doubt, other} -- see `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class`. Filed because the pre-registered study `vwapcont-htf-precheck-2026-07-16` (analysis/recommendations/vwapcont-htf-precheck-2026-07-16.json, verdict KILL) found the HTF-OPPOSED vwap_continuation cohort OUTPERFORMS the aligned cohort (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried, mechanism fits C28 -- the 15m ribbon lags, fast signals catch reversals first). The veto layer's single most common cited reason is exactly this HTF-conflict framing, so its false-veto rate is graded as its OWN cohort here, not blended into the overall veto accuracy above.

| Reason class | Vetoes tagged | Graded | TRUE veto | FALSE veto | Ungraded | False-veto rate |
|---|---|---|---|---|---|---|
| htf_conflict | 49 | 49 | 38 | 11 | 0 | **22.4%** |
| spread_data_doubt | 1 | 1 | 1 | 0 | 0 | **0.0%** |
| other | 2 | 2 | 1 | 1 | 0 | **50.0%** |

**INSUFFICIENT CONTRAST** -- htf_conflict false-veto rate 22.4% (n=49) graded, but the other-classes comparison n=3 is below the 5-item floor or not elevated. Do NOT touch the veto sysmsg yet.

