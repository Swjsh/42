# free-model-audit — heartbeat_veto — 2026-08-04

**Subject:** `heartbeat_veto`  
**Generated:** 2026-08-04T21:00:15  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 71 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 71 |
| Correct | 54 |
| Wrong | 17 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 54/71 = **76.1%** |
| Graded via counterfactual replay | 71 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 10 / 10 |
| TRUE vetoes (correctly blocked a loser/marginal) | 0 |
| FALSE vetoes (wrongly blocked a winner) | 10 |
| **Veto-only accuracy** (the safety-net's actual job) | **0.0%** |
| GO decisions graded | 61 / 61 |
| **GO-only accuracy** (fill went on to be non-losing) | **88.5%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 5 / 10 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 351 |
| Cumulative correct-grade rate | **67.2%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-08-04T09:56:03 | go | counterfactual | OK | real fill pnl=$383.00 symbol=SPY260804C00763000 |
| core:bold:2026-08-04T09:56:51 | go | counterfactual | OK | real fill pnl=$614.00 symbol=SPY260804C00763000 |
| core:safe:2026-08-04T09:57:07 | go | counterfactual | OK | replay pnl=$415.40 symbol=SPY260804C00763000 strike=763 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T09:57:26 | go | counterfactual | OK | replay pnl=$182.90 symbol=SPY260804C00765000 strike=765 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T09:58:03 | go | counterfactual | OK | replay pnl=$468.10 symbol=SPY260804C00763000 strike=763 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T09:58:24 | go | counterfactual | OK | replay pnl=$210.80 symbol=SPY260804C00765000 strike=765 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T10:06:03 | go | counterfactual | OK | replay pnl=$94.20 symbol=SPY260804C00764000 strike=764 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T10:06:41 | go | counterfactual | OK | replay pnl=$42.00 symbol=SPY260804C00766000 strike=766 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T10:07:05 | go | counterfactual | OK | replay pnl=$98.40 symbol=SPY260804C00764000 strike=764 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T10:07:45 | go | counterfactual | OK | replay pnl=$43.80 symbol=SPY260804C00766000 strike=766 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T10:08:03 | veto | counterfactual | XX | replay pnl=$98.40 symbol=SPY260804C00764000 strike=764 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T10:09:04 | go | counterfactual | OK | replay pnl=$92.40 symbol=SPY260804C00764000 strike=764 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T10:09:32 | go | counterfactual | OK | replay pnl=$41.40 symbol=SPY260804C00766000 strike=766 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T10:08:54 | go | counterfactual | OK | replay pnl=$43.80 symbol=SPY260804C00766000 strike=766 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T10:10:04 | go | counterfactual | OK | replay pnl=$97.20 symbol=SPY260804C00764000 strike=764 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T10:10:57 | go | counterfactual | OK | replay pnl=$43.80 symbol=SPY260804C00766000 strike=766 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T11:26:04 | go | counterfactual | XX | real fill pnl=$-60.00 symbol=SPY260804C00768000 |
| core:bold:2026-08-04T11:27:05 | go | counterfactual | OK | replay pnl=$111.60 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T11:28:04 | veto | counterfactual | XX | replay pnl=$114.70 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T11:51:04 | go | counterfactual | XX | real fill pnl=$-75.00 symbol=SPY260804C00769000 |
| core:bold:2026-08-04T11:52:06 | go | counterfactual | OK | replay pnl=$155.00 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T11:53:05 | go | counterfactual | OK | replay pnl=$120.90 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T12:26:03 | veto | counterfactual | XX | replay pnl=$292.20 symbol=SPY260804C00769000 strike=769 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T12:26:55 | go | counterfactual | OK | replay pnl=$151.90 symbol=SPY260804C00771000 strike=771 equity_method=reason_text_scan |
| core:safe:2026-08-04T12:27:05 | veto | counterfactual | XX | replay pnl=$292.60 symbol=SPY260804C00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T12:28:04 | go | counterfactual | OK | real fill pnl=$375.00 symbol=SPY260804C00769000 |
| core:bold:2026-08-04T12:27:56 | go | counterfactual | OK | replay pnl=$151.90 symbol=SPY260804C00771000 strike=771 equity_method=reason_text_scan |
| core:bold:2026-08-04T12:28:37 | go | counterfactual | OK | replay pnl=$155.00 symbol=SPY260804C00771000 strike=771 equity_method=reason_text_scan |
| core:safe:2026-08-04T12:36:03 | go | counterfactual | OK | replay pnl=$300.70 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T12:36:42 | go | counterfactual | OK | replay pnl=$102.30 symbol=SPY260804C00772000 strike=772 equity_method=reason_text_scan |
| core:safe:2026-08-04T12:38:03 | go | counterfactual | OK | replay pnl=$266.60 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T12:37:03 | go | counterfactual | OK | replay pnl=$288.30 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T12:38:20 | go | counterfactual | OK | replay pnl=$89.90 symbol=SPY260804C00772000 strike=772 equity_method=reason_text_scan |
| core:bold:2026-08-04T12:38:18 | veto | counterfactual | XX | replay pnl=$89.90 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T12:46:03 | go | counterfactual | OK | replay pnl=$203.20 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T12:46:23 | go | counterfactual | OK | replay pnl=$127.10 symbol=SPY260804C00772000 strike=772 equity_method=reason_text_scan |
| core:safe:2026-08-04T12:47:05 | go | counterfactual | OK | replay pnl=$202.00 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T12:48:04 | go | counterfactual | OK | replay pnl=$204.40 symbol=SPY260804C00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T12:48:20 | veto | counterfactual | XX | replay pnl=$124.00 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T12:48:38 | go | counterfactual | OK | replay pnl=$124.00 symbol=SPY260804C00772000 strike=772 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:06:03 | veto | counterfactual | XX | replay pnl=$122.00 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:06:39 | go | counterfactual | OK | replay pnl=$25.20 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:07:05 | go | counterfactual | OK | replay pnl=$76.80 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:07:34 | go | counterfactual | OK | replay pnl=$31.20 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:08:04 | go | counterfactual | OK | replay pnl=$78.60 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:08:41 | go | counterfactual | OK | replay pnl=$31.20 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:09:04 | go | counterfactual | OK | replay pnl=$74.40 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:09:31 | go | counterfactual | OK | replay pnl=$28.80 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:10:06 | veto | counterfactual | XX | replay pnl=$73.20 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:10:52 | go | counterfactual | OK | replay pnl=$29.40 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:21:03 | go | counterfactual | OK | replay pnl=$81.00 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:21:26 | go | counterfactual | OK | replay pnl=$33.60 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:22:03 | go | counterfactual | OK | replay pnl=$76.80 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:22:19 | go | counterfactual | OK | replay pnl=$31.80 symbol=SPY260804C00773000 strike=773 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:23:04 | veto | counterfactual | XX | replay pnl=$84.00 symbol=SPY260804C00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T13:41:03 | go | counterfactual | XX | real fill pnl=$-96.00 symbol=SPY260804C00772000 |
| core:bold:2026-08-04T13:41:33 | go | counterfactual | OK | replay pnl=$26.40 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:42:03 | go | counterfactual | OK | replay pnl=$74.40 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:42:24 | go | counterfactual | OK | replay pnl=$28.20 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:43:04 | go | counterfactual | OK | replay pnl=$72.00 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:43:27 | go | counterfactual | OK | replay pnl=$27.00 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:44:04 | go | counterfactual | OK | replay pnl=$77.40 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:44:26 | go | counterfactual | OK | replay pnl=$30.60 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:45:05 | go | counterfactual | OK | replay pnl=$84.00 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:45:29 | go | counterfactual | OK | replay pnl=$32.40 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:46:03 | go | counterfactual | XX | replay pnl=$-219.00 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:46:24 | veto | counterfactual | XX | replay pnl=$36.00 symbol=SPY260804C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-04T13:47:04 | go | counterfactual | XX | replay pnl=$-237.00 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:47:19 | go | counterfactual | OK | replay pnl=$40.20 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |
| core:safe:2026-08-04T13:48:04 | go | counterfactual | XX | replay pnl=$-277.50 symbol=SPY260804C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-04T13:48:26 | go | counterfactual | XX | replay pnl=$-124.50 symbol=SPY260804C00774000 strike=774 equity_method=reason_text_scan |

## Verdict

**NOT YET CONFIDENT** — cumulative 67.2% (bar 85%), streak 0/3 consecutive runs above bar.


## Veto reason-class breakdown (VETO-HTF-CONFLICT-REGRADE, 2026-07-16 queue item)

Every graded VETO item, keyword-classified by its free-model reason string(s) into {htf_conflict, spread_data_doubt, other} -- see `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class`. Filed because the pre-registered study `vwapcont-htf-precheck-2026-07-16` (analysis/recommendations/vwapcont-htf-precheck-2026-07-16.json, verdict KILL) found the HTF-OPPOSED vwap_continuation cohort OUTPERFORMS the aligned cohort (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried, mechanism fits C28 -- the 15m ribbon lags, fast signals catch reversals first). The veto layer's single most common cited reason is exactly this HTF-conflict framing, so its false-veto rate is graded as its OWN cohort here, not blended into the overall veto accuracy above.

| Reason class | Vetoes tagged | Graded | TRUE veto | FALSE veto | Ungraded | False-veto rate |
|---|---|---|---|---|---|---|
| htf_conflict | 94 | 94 | 62 | 32 | 0 | **34.0%** |
| spread_data_doubt | 2 | 2 | 1 | 1 | 0 | **50.0%** |
| other | 4 | 4 | 1 | 3 | 0 | **75.0%** |

**INSUFFICIENT CONTRAST** -- htf_conflict false-veto rate 34.0% (n=94) graded, but the other-classes comparison n=6 is below the 5-item floor or not elevated. Do NOT touch the veto sysmsg yet.

