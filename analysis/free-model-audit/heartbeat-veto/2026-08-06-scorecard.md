# free-model-audit — heartbeat_veto — 2026-08-06

**Subject:** `heartbeat_veto`  
**Generated:** 2026-08-06T21:00:11  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 116 |
| Already graded (skipped, dedupe) | 71 |
| Newly graded this run | 45 |
| Correct | 21 |
| Wrong | 24 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 21/45 = **46.7%** |
| Graded via counterfactual replay | 45 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 30 / 30 |
| TRUE vetoes (correctly blocked a loser/marginal) | 9 |
| FALSE vetoes (wrongly blocked a winner) | 21 |
| **Veto-only accuracy** (the safety-net's actual job) | **30.0%** |
| GO decisions graded | 15 / 15 |
| **GO-only accuracy** (fill went on to be non-losing) | **80.0%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 4 / 30 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 396 |
| Cumulative correct-grade rate | **64.9%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-08-05T11:46:03 | veto | counterfactual | XX | replay pnl=$99.00 symbol=SPY260805P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:47:01 | veto | counterfactual | XX | replay pnl=$54.60 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:47:03 | veto | counterfactual | XX | replay pnl=$102.00 symbol=SPY260805P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:47:23 | veto | counterfactual | XX | replay pnl=$54.60 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:48:03 | go | counterfactual | XX | real fill pnl=$-255.00 symbol=SPY260805P00772000 |
| core:safe:2026-08-05T11:49:03 | veto | counterfactual | XX | replay pnl=$109.20 symbol=SPY260805P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:49:08 | veto | counterfactual | XX | replay pnl=$58.80 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:49:19 | go | counterfactual | OK | replay pnl=$58.80 symbol=SPY260805P00770000 strike=770 equity_method=reason_text_scan |
| core:safe:2026-08-05T11:50:04 | veto | counterfactual | XX | replay pnl=$108.60 symbol=SPY260805P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:50:24 | go | counterfactual | OK | replay pnl=$58.20 symbol=SPY260805P00770000 strike=770 equity_method=reason_text_scan |
| core:safe:2026-08-05T11:51:03 | go | counterfactual | OK | replay pnl=$83.40 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:51:28 | veto | counterfactual | XX | replay pnl=$43.80 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:52:03 | veto | counterfactual | XX | replay pnl=$84.60 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:52:23 | veto | counterfactual | XX | replay pnl=$44.40 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:53:03 | veto | counterfactual | XX | replay pnl=$77.40 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:53:20 | veto | counterfactual | XX | replay pnl=$40.20 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:54:03 | veto | counterfactual | XX | replay pnl=$81.00 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:55:05 | veto | counterfactual | XX | replay pnl=$84.60 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:55:19 | go | counterfactual | OK | replay pnl=$44.40 symbol=SPY260805P00769000 strike=769 equity_method=reason_text_scan |
| core:safe:2026-08-05T11:56:03 | veto | counterfactual | XX | replay pnl=$91.80 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:56:19 | veto | counterfactual | XX | replay pnl=$48.00 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:57:04 | veto | counterfactual | OK | replay pnl=$-244.50 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:57:25 | veto | counterfactual | XX | replay pnl=$51.60 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:58:07 | veto | counterfactual | XX | replay pnl=$89.40 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:58:24 | veto | counterfactual | XX | replay pnl=$46.20 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T11:59:03 | veto | counterfactual | OK | replay pnl=$-246.00 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T11:59:20 | veto | counterfactual | XX | replay pnl=$52.20 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T12:00:04 | veto | counterfactual | OK | replay pnl=$-243.00 symbol=SPY260805P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T12:00:22 | veto | counterfactual | XX | replay pnl=$51.00 symbol=SPY260805P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T12:11:03 | veto | counterfactual | OK | replay pnl=$-208.50 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T12:11:27 | veto | counterfactual | OK | replay pnl=$-108.00 symbol=SPY260805P00768000 strike=768 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T12:12:03 | veto | counterfactual | OK | replay pnl=$-214.50 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T12:13:03 | veto | counterfactual | OK | replay pnl=$-216.00 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T12:14:03 | go | counterfactual | XX | replay pnl=$-198.00 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-05T12:14:22 | veto | counterfactual | OK | replay pnl=$-99.00 symbol=SPY260805P00768000 strike=768 equity_method=current_snapshot_fallback |
| core:safe:2026-08-05T12:15:03 | go | counterfactual | XX | replay pnl=$-192.00 symbol=SPY260805P00770000 strike=770 equity_method=current_snapshot_fallback |
| extra:safe:2026-08-05T14:06:03:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-127.50 symbol=SPY260805C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-06T10:31:03 | go | counterfactual | OK | real fill pnl=$375.00 symbol=SPY260806P00770000 |
| core:safe:2026-08-06T10:32:03 | go | counterfactual | OK | replay pnl=$71.40 symbol=SPY260806P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-06T10:32:48 | go | counterfactual | OK | replay pnl=$34.80 symbol=SPY260806P00768000 strike=768 equity_method=reason_text_scan |
| core:safe:2026-08-06T10:33:03 | go | counterfactual | OK | replay pnl=$69.00 symbol=SPY260806P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-06T10:34:01 | go | counterfactual | OK | replay pnl=$30.00 symbol=SPY260806P00768000 strike=768 equity_method=reason_text_scan |
| core:safe:2026-08-06T10:34:03 | go | counterfactual | OK | replay pnl=$61.80 symbol=SPY260806P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-06T10:35:03 | go | counterfactual | OK | replay pnl=$57.60 symbol=SPY260806P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-06T10:34:56 | go | counterfactual | OK | replay pnl=$30.00 symbol=SPY260806P00768000 strike=768 equity_method=reason_text_scan |

## Verdict

**NOT YET CONFIDENT** — cumulative 64.9% (bar 85%), streak 0/3 consecutive runs above bar.


## Veto reason-class breakdown (VETO-HTF-CONFLICT-REGRADE, 2026-07-16 queue item)

Every graded VETO item, keyword-classified by its free-model reason string(s) into {htf_conflict, spread_data_doubt, other} -- see `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class`. Filed because the pre-registered study `vwapcont-htf-precheck-2026-07-16` (analysis/recommendations/vwapcont-htf-precheck-2026-07-16.json, verdict KILL) found the HTF-OPPOSED vwap_continuation cohort OUTPERFORMS the aligned cohort (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried, mechanism fits C28 -- the 15m ribbon lags, fast signals catch reversals first). The veto layer's single most common cited reason is exactly this HTF-conflict framing, so its false-veto rate is graded as its OWN cohort here, not blended into the overall veto accuracy above.

| Reason class | Vetoes tagged | Graded | TRUE veto | FALSE veto | Ungraded | False-veto rate |
|---|---|---|---|---|---|---|
| htf_conflict | 95 | 95 | 62 | 33 | 0 | **34.7%** |
| spread_data_doubt | 6 | 6 | 1 | 5 | 0 | **83.3%** |
| other | 9 | 9 | 1 | 8 | 0 | **88.9%** |

**INSUFFICIENT CONTRAST** -- htf_conflict false-veto rate 34.7% (n=95) graded, but the other-classes comparison n=15 is below the 5-item floor or not elevated. Do NOT touch the veto sysmsg yet.

