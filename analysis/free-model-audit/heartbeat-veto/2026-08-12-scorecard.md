# free-model-audit — heartbeat_veto — 2026-08-12

**Subject:** `heartbeat_veto`  
**Generated:** 2026-08-12T21:00:25  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 161 |
| Already graded (skipped, dedupe) | 34 |
| Newly graded this run | 127 |
| Correct | 89 |
| Wrong | 38 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 89/127 = **70.1%** |
| Graded via counterfactual replay | 127 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 35 / 35 |
| TRUE vetoes (correctly blocked a loser/marginal) | 29 |
| FALSE vetoes (wrongly blocked a winner) | 6 |
| **Veto-only accuracy** (the safety-net's actual job) | **82.9%** |
| GO decisions graded | 92 / 92 |
| **GO-only accuracy** (fill went on to be non-losing) | **65.2%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 10 / 35 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 587 |
| Cumulative correct-grade rate | **63.5%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-08-11T11:51:04 | go | counterfactual | XX | real fill pnl=$-63.00 symbol=SPY260811P00772000 |
| core:safe:2026-08-11T11:52:04 | go | counterfactual | OK | replay pnl=$147.00 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T11:53:04 | go | counterfactual | OK | replay pnl=$146.20 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T11:53:54 | go | counterfactual | XX | real fill pnl=$-145.00 symbol=SPY260811P00772000 |
| core:safe:2026-08-11T11:54:03 | go | counterfactual | OK | replay pnl=$147.00 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T11:55:01 | go | counterfactual | OK | replay pnl=$17.40 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T11:55:04 | go | counterfactual | OK | replay pnl=$146.60 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T11:56:03 | go | counterfactual | OK | replay pnl=$148.60 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T11:55:58 | go | counterfactual | OK | replay pnl=$17.40 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T11:56:50 | go | counterfactual | OK | replay pnl=$16.80 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T11:57:04 | go | counterfactual | OK | replay pnl=$148.20 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T11:58:03 | go | counterfactual | OK | replay pnl=$48.00 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T11:58:10 | veto | counterfactual | OK | replay pnl=$15.00 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T11:59:04 | go | counterfactual | OK | replay pnl=$46.80 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T11:58:55 | go | counterfactual | OK | replay pnl=$15.00 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T12:00:05 | go | counterfactual | OK | replay pnl=$195.30 symbol=SPY260811P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T13:31:05 | go | counterfactual | XX | real fill pnl=$-145.00 symbol=SPY260811P00771000 |
| core:bold:2026-08-11T13:32:05 | go | counterfactual | XX | replay pnl=$-30.00 symbol=SPY260811P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T13:33:05 | go | counterfactual | XX | replay pnl=$-27.00 symbol=SPY260811P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T13:34:04 | go | counterfactual | XX | replay pnl=$-24.00 symbol=SPY260811P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T13:44:03 | go | counterfactual | OK | real fill pnl=$195.00 symbol=SPY260811P00771000 |
| core:safe:2026-08-11T13:45:05 | go | counterfactual | OK | replay pnl=$148.80 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:06:04 | go | counterfactual | OK | replay pnl=$40.80 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T14:07:05 | go | counterfactual | OK | real fill pnl=$297.00 symbol=SPY260811P00771000 |
| core:safe:2026-08-11T14:07:03 | go | counterfactual | OK | replay pnl=$37.80 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:08:04 | go | counterfactual | OK | replay pnl=$41.40 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T14:08:08 | go | counterfactual | OK | replay pnl=$9.00 symbol=SPY260811P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T14:08:44 | go | counterfactual | OK | replay pnl=$9.00 symbol=SPY260811P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:09:04 | go | counterfactual | OK | replay pnl=$43.20 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-11T14:09:52 | go | counterfactual | OK | replay pnl=$9.00 symbol=SPY260811P00769000 strike=769 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:10:04 | go | counterfactual | OK | replay pnl=$41.40 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:11:04 | go | counterfactual | OK | replay pnl=$37.80 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:12:04 | go | counterfactual | OK | replay pnl=$39.00 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:13:04 | go | counterfactual | OK | replay pnl=$39.00 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:14:04 | go | counterfactual | OK | replay pnl=$37.80 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:15:04 | go | counterfactual | OK | replay pnl=$37.80 symbol=SPY260811P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:34:04 | go | counterfactual | XX | replay pnl=$-90.00 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-11T14:35:04 | go | counterfactual | OK | replay pnl=$33.00 symbol=SPY260811P00770000 strike=770 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T09:51:04 | veto | counterfactual | OK | replay pnl=$-148.50 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T09:52:29 | veto | counterfactual | OK | replay pnl=$-48.00 symbol=SPY260812C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T09:52:04 | go | counterfactual | XX | real fill pnl=$-24.00 symbol=SPY260812C00774000 |
| core:safe:2026-08-12T09:53:04 | veto | counterfactual | OK | replay pnl=$-136.50 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T09:53:26 | veto | counterfactual | OK | replay pnl=$-51.00 symbol=SPY260812C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T09:54:03 | go | counterfactual | XX | replay pnl=$-118.50 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T09:53:52 | go | counterfactual | OK | real fill pnl=$-10.00 symbol=SPY260812C00774000 |
| core:bold:2026-08-12T09:54:51 | go | counterfactual | XX | replay pnl=$-45.00 symbol=SPY260812C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T09:55:04 | go | counterfactual | XX | real fill pnl=$-24.00 symbol=SPY260812C00774000 |
| extra:safe:2026-08-12T09:56:03:vwap_reclaim_failed_break | veto | counterfactual | OK | replay pnl=$-271.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:01:04 | veto | counterfactual | OK | replay pnl=$-166.50 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:02:04 | veto | counterfactual | OK | replay pnl=$-156.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:02:37 | go | counterfactual | XX | real fill pnl=$-93.00 symbol=SPY260812C00773000 |
| core:bold:2026-08-12T10:02:45 | go | counterfactual | XX | replay pnl=$-60.00 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:03:03 | go | counterfactual | XX | real fill pnl=$-45.00 symbol=SPY260812C00773000 |
| core:bold:2026-08-12T10:04:22 | go | counterfactual | OK | replay pnl=$20.40 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:04:04 | go | counterfactual | OK | replay pnl=$54.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:05:04 | go | counterfactual | OK | replay pnl=$61.80 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:05:21 | veto | counterfactual | OK | replay pnl=$-60.00 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:05:52 | veto | counterfactual | OK | replay pnl=$-60.00 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:11:03 | go | counterfactual | XX | replay pnl=$-235.50 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:11:42 | go | counterfactual | OK | replay pnl=$39.00 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:12:03 | veto | counterfactual | XX | replay pnl=$91.20 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:12:51 | veto | counterfactual | XX | replay pnl=$36.60 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:13:03 | veto | counterfactual | XX | replay pnl=$88.80 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:13:57 | go | counterfactual | OK | replay pnl=$36.00 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:14:03 | go | counterfactual | OK | replay pnl=$88.20 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:15:04 | veto | counterfactual | OK | replay pnl=$-232.50 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:14:50 | veto | counterfactual | XX | replay pnl=$35.40 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:15:46 | go | counterfactual | OK | replay pnl=$38.40 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:16:04 | go | counterfactual | XX | replay pnl=$-231.00 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:17:00 | veto | counterfactual | XX | replay pnl=$36.60 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:17:04 | go | counterfactual | XX | replay pnl=$-256.50 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:18:02 | go | counterfactual | XX | replay pnl=$-112.50 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:18:03 | go | counterfactual | XX | replay pnl=$-270.00 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:19:03 | go | counterfactual | XX | replay pnl=$-231.00 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:19:16 | go | counterfactual | OK | replay pnl=$36.60 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T10:19:49 | go | counterfactual | OK | replay pnl=$36.60 symbol=SPY260812C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T10:20:04 | go | counterfactual | OK | replay pnl=$90.60 symbol=SPY260812C00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T11:26:04 | go | counterfactual | OK | real fill pnl=$-6.00 symbol=SPY260812P00772000 |
| core:safe:2026-08-12T11:27:04 | go | counterfactual | OK | real fill pnl=$-6.00 symbol=SPY260812P00772000 |
| core:safe:2026-08-12T11:28:03 | veto | counterfactual | OK | replay pnl=$-127.50 symbol=SPY260812P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T11:29:03 | veto | counterfactual | XX | replay pnl=$45.00 symbol=SPY260812P00772000 strike=772 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T11:30:04 | go | counterfactual | OK | real fill pnl=$15.00 symbol=SPY260812P00772000 |
| core:safe:2026-08-12T12:56:04 | go | counterfactual | OK | replay pnl=$40.80 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T12:56:32 | go | counterfactual | XX | real fill pnl=$-75.00 symbol=SPY260812C00773000 |
| core:safe:2026-08-12T12:57:03 | go | counterfactual | OK | replay pnl=$40.80 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T12:57:36 | go | counterfactual | OK | replay pnl=$8.40 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T12:58:03 | go | counterfactual | OK | replay pnl=$38.40 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T12:58:40 | go | counterfactual | OK | replay pnl=$7.80 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T12:59:03 | go | counterfactual | OK | replay pnl=$40.20 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T12:59:44 | go | counterfactual | OK | replay pnl=$7.80 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:00:04 | go | counterfactual | OK | replay pnl=$40.80 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:00:40 | go | counterfactual | XX | replay pnl=$-22.50 symbol=SPY260812C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:16:05 | veto | counterfactual | OK | replay pnl=$-27.00 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:17:05 | veto | counterfactual | OK | replay pnl=$-25.50 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:18:05 | veto | counterfactual | OK | replay pnl=$-25.50 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:19:04 | veto | counterfactual | OK | replay pnl=$-22.50 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:20:06 | veto | counterfactual | OK | replay pnl=$-21.00 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:23:04 | veto | counterfactual | OK | replay pnl=$-24.00 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:31:05 | veto | counterfactual | OK | replay pnl=$-21.00 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:46:04 | veto | counterfactual | OK | replay pnl=$-94.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:46:57 | veto | counterfactual | OK | replay pnl=$-15.00 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:47:04 | veto | counterfactual | OK | replay pnl=$-91.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:48:04 | veto | counterfactual | OK | replay pnl=$-96.00 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:49:04 | go | counterfactual | XX | replay pnl=$-100.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:49:46 | go | counterfactual | XX | real fill pnl=$-35.00 symbol=SPY260812P00773000 |
| core:safe:2026-08-12T13:50:04 | go | counterfactual | XX | replay pnl=$-90.00 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:51:03 | veto | counterfactual | OK | replay pnl=$-90.00 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:52:04 | go | counterfactual | XX | replay pnl=$-88.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:53:03 | veto | counterfactual | OK | replay pnl=$-94.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:54:03 | veto | counterfactual | OK | replay pnl=$-102.00 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T13:55:03 | veto | counterfactual | OK | replay pnl=$-106.50 symbol=SPY260812P00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:55:22 | go | counterfactual | XX | real fill pnl=$-15.00 symbol=SPY260812P00773000 |
| core:bold:2026-08-12T13:55:40 | veto | counterfactual | OK | replay pnl=$-18.00 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:bold:2026-08-12T13:56:04 | veto | counterfactual | OK | replay pnl=$-16.50 symbol=SPY260812P00771000 strike=771 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:16:04 | go | counterfactual | OK | replay pnl=$34.80 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:17:04 | go | counterfactual | OK | replay pnl=$31.20 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:18:04 | go | counterfactual | OK | replay pnl=$32.40 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:26:03 | go | counterfactual | OK | replay pnl=$37.20 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:27:03 | go | counterfactual | OK | replay pnl=$36.60 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:28:04 | go | counterfactual | OK | replay pnl=$36.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:29:03 | go | counterfactual | OK | replay pnl=$33.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:30:04 | go | counterfactual | OK | replay pnl=$37.20 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:36:03 | go | counterfactual | XX | replay pnl=$-117.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:37:04 | go | counterfactual | XX | replay pnl=$-111.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:38:03 | go | counterfactual | XX | replay pnl=$-115.50 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:39:03 | go | counterfactual | XX | replay pnl=$-111.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-12T14:40:04 | go | counterfactual | XX | replay pnl=$-123.00 symbol=SPY260812C00773000 strike=773 equity_method=current_snapshot_fallback |

## Verdict

**NOT YET CONFIDENT** — cumulative 63.5% (bar 85%), streak 0/3 consecutive runs above bar.


## Veto reason-class breakdown (VETO-HTF-CONFLICT-REGRADE, 2026-07-16 queue item)

Every graded VETO item, keyword-classified by its free-model reason string(s) into {htf_conflict, spread_data_doubt, other} -- see `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class`. Filed because the pre-registered study `vwapcont-htf-precheck-2026-07-16` (analysis/recommendations/vwapcont-htf-precheck-2026-07-16.json, verdict KILL) found the HTF-OPPOSED vwap_continuation cohort OUTPERFORMS the aligned cohort (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried, mechanism fits C28 -- the 15m ribbon lags, fast signals catch reversals first). The veto layer's single most common cited reason is exactly this HTF-conflict framing, so its false-veto rate is graded as its OWN cohort here, not blended into the overall veto accuracy above.

| Reason class | Vetoes tagged | Graded | TRUE veto | FALSE veto | Ungraded | False-veto rate |
|---|---|---|---|---|---|---|
| htf_conflict | 125 | 125 | 71 | 54 | 0 | **43.2%** |
| spread_data_doubt | 6 | 6 | 1 | 5 | 0 | **83.3%** |
| other | 9 | 9 | 1 | 8 | 0 | **88.9%** |

**INSUFFICIENT CONTRAST** -- htf_conflict false-veto rate 43.2% (n=125) graded, but the other-classes comparison n=15 is below the 5-item floor or not elevated. Do NOT touch the veto sysmsg yet.

