# free-model-audit — heartbeat_veto — 2026-08-08

**Subject:** `heartbeat_veto`  
**Generated:** 2026-08-08T21:00:08  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 38 |
| Already graded (skipped, dedupe) | 8 |
| Newly graded this run | 30 |
| Correct | 4 |
| Wrong | 26 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 4/30 = **13.3%** |
| Graded via counterfactual replay | 30 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 0 / 0 |
| TRUE vetoes (correctly blocked a loser/marginal) | 0 |
| FALSE vetoes (wrongly blocked a winner) | 0 |
| **Veto-only accuracy** (the safety-net's actual job) | n/a |
| GO decisions graded | 30 / 30 |
| **GO-only accuracy** (fill went on to be non-losing) | **13.3%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 0 / 0 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 426 |
| Cumulative correct-grade rate | **61.3%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-08-07T09:46:03 | go | counterfactual | XX | real fill pnl=$-153.00 symbol=SPY260807C00772000 |
| core:bold:2026-08-07T09:46:35 | go | counterfactual | XX | replay pnl=$-94.50 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-07T09:47:03 | go | counterfactual | XX | replay pnl=$-202.50 symbol=SPY260807C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-07T09:48:03 | go | counterfactual | XX | replay pnl=$-190.50 symbol=SPY260807C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-07T09:47:54 | go | counterfactual | XX | replay pnl=$-94.50 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T09:48:22 | go | counterfactual | XX | replay pnl=$-85.50 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-07T09:49:03 | go | counterfactual | XX | replay pnl=$-219.00 symbol=SPY260807C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-07T09:50:03 | go | counterfactual | XX | replay pnl=$-225.00 symbol=SPY260807C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-07T09:49:58 | go | counterfactual | XX | replay pnl=$-99.00 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T09:50:27 | go | counterfactual | XX | replay pnl=$-93.00 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-07T12:06:03 | go | counterfactual | XX | real fill pnl=$-183.00 symbol=SPY260807C00773000 |
| core:bold:2026-08-07T12:06:35 | go | counterfactual | XX | replay pnl=$-48.00 symbol=SPY260807C00775000 strike=775 equity_method=reason_text_scan |
| core:safe:2026-08-07T12:07:03 | go | counterfactual | XX | replay pnl=$-168.00 symbol=SPY260807C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-07T12:07:22 | go | counterfactual | XX | replay pnl=$-48.00 symbol=SPY260807C00775000 strike=775 equity_method=reason_text_scan |
| core:safe:2026-08-07T12:08:03 | go | counterfactual | XX | replay pnl=$-159.00 symbol=SPY260807C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-07T12:08:18 | go | counterfactual | XX | replay pnl=$-43.50 symbol=SPY260807C00775000 strike=775 equity_method=reason_text_scan |
| core:safe:2026-08-07T12:09:03 | go | counterfactual | XX | replay pnl=$-156.00 symbol=SPY260807C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-07T12:09:50 | go | counterfactual | XX | replay pnl=$-42.00 symbol=SPY260807C00775000 strike=775 equity_method=reason_text_scan |
| core:safe:2026-08-07T12:10:04 | go | counterfactual | XX | replay pnl=$-163.50 symbol=SPY260807C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-07T12:10:39 | go | counterfactual | XX | replay pnl=$-45.00 symbol=SPY260807C00775000 strike=775 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:36:04 | go | counterfactual | OK | replay pnl=$13.80 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:37:04 | go | counterfactual | OK | replay pnl=$13.80 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:38:04 | go | counterfactual | OK | replay pnl=$12.60 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:39:04 | go | counterfactual | XX | replay pnl=$-45.00 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:40:04 | go | counterfactual | XX | replay pnl=$-48.00 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:41:04 | go | counterfactual | XX | replay pnl=$-49.50 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:42:04 | go | counterfactual | OK | replay pnl=$17.40 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:43:05 | go | counterfactual | XX | replay pnl=$-46.50 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:44:04 | go | counterfactual | XX | replay pnl=$-51.00 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |
| core:bold:2026-08-07T12:45:05 | go | counterfactual | XX | replay pnl=$-54.00 symbol=SPY260807C00774000 strike=774 equity_method=reason_text_scan |

## Verdict

**NOT YET CONFIDENT** — cumulative 61.3% (bar 85%), streak 0/3 consecutive runs above bar.


## Veto reason-class breakdown (VETO-HTF-CONFLICT-REGRADE, 2026-07-16 queue item)

Every graded VETO item, keyword-classified by its free-model reason string(s) into {htf_conflict, spread_data_doubt, other} -- see `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class`. Filed because the pre-registered study `vwapcont-htf-precheck-2026-07-16` (analysis/recommendations/vwapcont-htf-precheck-2026-07-16.json, verdict KILL) found the HTF-OPPOSED vwap_continuation cohort OUTPERFORMS the aligned cohort (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried, mechanism fits C28 -- the 15m ribbon lags, fast signals catch reversals first). The veto layer's single most common cited reason is exactly this HTF-conflict framing, so its false-veto rate is graded as its OWN cohort here, not blended into the overall veto accuracy above.

| Reason class | Vetoes tagged | Graded | TRUE veto | FALSE veto | Ungraded | False-veto rate |
|---|---|---|---|---|---|---|
| htf_conflict | 125 | 125 | 71 | 54 | 0 | **43.2%** |
| spread_data_doubt | 6 | 6 | 1 | 5 | 0 | **83.3%** |
| other | 9 | 9 | 1 | 8 | 0 | **88.9%** |

**INSUFFICIENT CONTRAST** -- htf_conflict false-veto rate 43.2% (n=125) graded, but the other-classes comparison n=15 is below the 5-item floor or not elevated. Do NOT touch the veto sysmsg yet.

