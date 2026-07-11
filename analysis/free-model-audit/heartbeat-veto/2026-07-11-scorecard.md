# free-model-audit — heartbeat_veto — 2026-07-11

**Subject:** `heartbeat_veto`  
**Generated:** 2026-07-11T10:11:06  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 106 |
| Already graded (skipped, dedupe) | 0 |
| Newly graded this run | 106 |
| Correct | 75 |
| Wrong | 31 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 75/106 = **70.8%** |
| Graded via counterfactual replay | 106 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 15 / 15 |
| TRUE vetoes (correctly blocked a loser/marginal) | 14 |
| FALSE vetoes (wrongly blocked a winner) | 1 |
| **Veto-only accuracy** (the safety-net's actual job) | **93.3%** |
| GO decisions graded | 91 / 91 |
| **GO-only accuracy** (fill went on to be non-losing) | **67.0%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 0 / 15 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 106 |
| Cumulative correct-grade rate | **70.8%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:bold:2026-06-25T14:16:05 | go | counterfactual | XX | replay pnl=$-37.50 symbol=SPY260625P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T10:36:03 | go | counterfactual | OK | replay pnl=$65.40 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T10:37:03 | go | counterfactual | XX | replay pnl=$-169.50 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T10:38:03 | go | counterfactual | XX | replay pnl=$-172.50 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T10:39:03 | go | counterfactual | XX | replay pnl=$-178.50 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T10:40:04 | go | counterfactual | XX | replay pnl=$-208.50 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:safe:2026-06-26T14:53:02 | go | counterfactual | OK | replay pnl=$60.00 symbol=SPY260626P00732000 strike=732 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T14:53:10 | go | counterfactual | OK | real fill pnl=$-15.00 symbol=SPY260626P00729000 |
| core:bold:2026-06-26T15:51:03 | go | counterfactual | OK | replay pnl=$0.00 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T15:52:03 | go | counterfactual | OK | replay pnl=$-3.00 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T15:53:03 | go | counterfactual | OK | replay pnl=$3.00 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:bold:2026-06-26T15:54:03 | go | counterfactual | OK | replay pnl=$3.00 symbol=SPY260626P00730000 strike=730 equity_method=current_snapshot_fallback |
| core:safe:2026-07-01T15:51:02 | go | counterfactual | OK | replay pnl=$36.00 symbol=SPY260701P00747000 strike=747 equity_method=current_snapshot_fallback |
| core:bold:2026-07-01T15:51:10 | go | counterfactual | OK | replay pnl=$3.00 symbol=SPY260701P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-01T15:52:02 | go | counterfactual | XX | replay pnl=$-60.00 symbol=SPY260701P00747000 strike=747 equity_method=current_snapshot_fallback |
| core:bold:2026-07-01T15:52:12 | go | counterfactual | OK | replay pnl=$-3.00 symbol=SPY260701P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-01T15:53:02 | go | counterfactual | OK | replay pnl=$0.00 symbol=SPY260701P00747000 strike=747 equity_method=current_snapshot_fallback |
| core:bold:2026-07-01T15:53:16 | go | counterfactual | OK | replay pnl=$3.00 symbol=SPY260701P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-01T15:54:02 | go | counterfactual | XX | replay pnl=$-21.00 symbol=SPY260701P00747000 strike=747 equity_method=current_snapshot_fallback |
| core:bold:2026-07-01T15:54:19 | go | counterfactual | OK | replay pnl=$0.00 symbol=SPY260701P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-01T15:55:03 | go | counterfactual | OK | replay pnl=$18.00 symbol=SPY260701P00747000 strike=747 equity_method=current_snapshot_fallback |
| core:bold:2026-07-01T15:55:14 | go | counterfactual | OK | replay pnl=$0.00 symbol=SPY260701P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T09:30:03 | go | counterfactual | XX | real fill pnl=$-66.00 symbol=SPY260702P00746000 |
| core:bold:2026-07-02T09:30:38 | go | counterfactual | XX | real fill pnl=$-60.00 symbol=SPY260702P00743000 |
| core:safe:2026-07-02T11:46:03 | go | counterfactual | OK | replay pnl=$399.90 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:47:03 | go | counterfactual | OK | replay pnl=$418.50 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:48:03 | go | counterfactual | OK | replay pnl=$403.00 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:49:03 | go | counterfactual | OK | replay pnl=$91.80 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:50:03 | go | counterfactual | OK | replay pnl=$101.40 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:51:03 | go | counterfactual | OK | replay pnl=$97.80 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:52:03 | go | counterfactual | OK | replay pnl=$111.60 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:53:03 | go | counterfactual | OK | replay pnl=$111.60 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:54:03 | go | counterfactual | OK | replay pnl=$99.00 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T11:55:03 | go | counterfactual | OK | replay pnl=$112.20 symbol=SPY260702P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:11:03 | go | counterfactual | OK | replay pnl=$77.40 symbol=SPY260702P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:12:03 | go | counterfactual | OK | replay pnl=$341.00 symbol=SPY260702P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:13:03 | go | counterfactual | OK | replay pnl=$74.40 symbol=SPY260702P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:14:03 | go | counterfactual | OK | replay pnl=$70.20 symbol=SPY260702P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:15:03 | go | counterfactual | OK | replay pnl=$75.00 symbol=SPY260702P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:51:03 | go | counterfactual | XX | real fill pnl=$-69.00 symbol=SPY260702P00743000 |
| core:bold:2026-07-02T12:51:14 | go | counterfactual | OK | real fill pnl=$290.00 symbol=SPY260702P00740000 |
| core:safe:2026-07-02T12:52:03 | go | counterfactual | OK | replay pnl=$69.00 symbol=SPY260702P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:53:03 | go | counterfactual | OK | replay pnl=$80.40 symbol=SPY260702P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:54:03 | go | counterfactual | OK | replay pnl=$78.00 symbol=SPY260702P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T12:54:18 | go | counterfactual | OK | replay pnl=$24.00 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T12:55:03 | go | counterfactual | OK | replay pnl=$91.20 symbol=SPY260702P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T12:55:38 | go | counterfactual | OK | replay pnl=$28.20 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T12:56:04 | go | counterfactual | OK | replay pnl=$36.00 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T12:57:05 | go | counterfactual | OK | replay pnl=$37.20 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T12:58:05 | go | counterfactual | OK | replay pnl=$33.60 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T12:59:04 | go | counterfactual | OK | replay pnl=$31.80 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:bold:2026-07-02T13:00:05 | go | counterfactual | OK | replay pnl=$36.60 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T13:54:03 | go | counterfactual | OK | replay pnl=$66.60 symbol=SPY260702P00741000 strike=741 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T13:55:03 | go | counterfactual | OK | replay pnl=$72.60 symbol=SPY260702P00741000 strike=741 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T14:04:03 | go | counterfactual | XX | replay pnl=$-106.50 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:safe:2026-07-02T14:05:03 | go | counterfactual | XX | replay pnl=$-79.50 symbol=SPY260702P00740000 strike=740 equity_method=current_snapshot_fallback |
| core:safe:2026-07-06T14:21:27 | go | counterfactual | XX | real fill pnl=$-39.00 symbol=SPY260706C00751000 |
| core:safe:2026-07-06T14:22:27 | go | counterfactual | OK | replay pnl=$50.40 symbol=SPY260706C00751000 strike=751 equity_method=current_snapshot_fallback |
| core:safe:2026-07-06T14:23:27 | go | counterfactual | OK | replay pnl=$48.00 symbol=SPY260706C00751000 strike=751 equity_method=current_snapshot_fallback |
| core:safe:2026-07-07T10:46:03 | go | counterfactual | XX | replay pnl=$-189.00 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-07T10:47:03 | go | counterfactual | XX | replay pnl=$-178.50 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-07T10:48:03 | go | counterfactual | XX | replay pnl=$-198.00 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-07T10:49:03 | go | counterfactual | XX | replay pnl=$-187.50 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-07T10:50:03 | go | counterfactual | XX | replay pnl=$-184.50 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T12:11:04 | go | counterfactual | XX | replay pnl=$-21.00 symbol=SPY260707P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T12:36:04 | go | counterfactual | XX | replay pnl=$-37.50 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T12:37:04 | go | counterfactual | XX | replay pnl=$-31.50 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T14:31:04 | go | counterfactual | OK | replay pnl=$4.80 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T14:32:04 | go | counterfactual | OK | replay pnl=$4.80 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T14:33:04 | go | counterfactual | OK | replay pnl=$31.00 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T14:34:04 | go | counterfactual | OK | replay pnl=$31.00 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-07T14:35:04 | go | counterfactual | OK | replay pnl=$5.40 symbol=SPY260707P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-08T09:51:02 | go | counterfactual | OK | replay pnl=$120.60 symbol=SPY260708P00744000 strike=744 equity_method=reason_text_scan |
| extra:safe:2026-07-08T10:04:04:vwap_reclaim_failed_break | veto | counterfactual | OK | replay pnl=$-256.50 symbol=SPY260708C00744000 strike=744 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:06:03 | go | counterfactual | OK | replay pnl=$53.40 symbol=SPY260708P00744000 strike=744 equity_method=reason_text_scan |
| core:bold:2026-07-08T13:06:16 | go | counterfactual | OK | replay pnl=$15.60 symbol=SPY260708P00741000 strike=741 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:07:03 | go | counterfactual | OK | replay pnl=$52.80 symbol=SPY260708P00744000 strike=744 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:08:03 | go | counterfactual | XX | replay pnl=$-144.00 symbol=SPY260708P00744000 strike=744 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:09:02 | go | counterfactual | XX | replay pnl=$-157.50 symbol=SPY260708P00744000 strike=744 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:10:04 | go | counterfactual | XX | replay pnl=$-162.00 symbol=SPY260708P00744000 strike=744 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:31:02 | go | counterfactual | XX | replay pnl=$-142.50 symbol=SPY260708C00746000 strike=746 equity_method=reason_text_scan |
| core:bold:2026-07-08T13:31:32 | go | counterfactual | XX | replay pnl=$-18.00 symbol=SPY260708C00749000 strike=749 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:32:03 | go | counterfactual | XX | replay pnl=$-139.50 symbol=SPY260708C00746000 strike=746 equity_method=reason_text_scan |
| core:bold:2026-07-08T13:32:27 | go | counterfactual | XX | replay pnl=$-19.50 symbol=SPY260708C00749000 strike=749 equity_method=reason_text_scan |
| core:safe:2026-07-08T13:33:02 | go | counterfactual | XX | replay pnl=$-132.00 symbol=SPY260708C00746000 strike=746 equity_method=reason_text_scan |
| core:bold:2026-07-08T13:33:12 | go | counterfactual | XX | replay pnl=$-18.00 symbol=SPY260708C00749000 strike=749 equity_method=reason_text_scan |
| extra:safe:2026-07-09T09:51:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-279.00 symbol=SPY260709C00748000 strike=748 equity_method=reason_text_scan |
| extra:safe:2026-07-09T09:54:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-309.00 symbol=SPY260709C00748000 strike=748 equity_method=reason_text_scan |
| extra:safe:2026-07-09T09:55:04:vwap_continuation | veto | counterfactual | OK | replay pnl=$-328.50 symbol=SPY260709C00748000 strike=748 equity_method=reason_text_scan |
| extra:safe:2026-07-09T09:57:02:vwap_continuation | veto | counterfactual | OK | replay pnl=$-205.50 symbol=SPY260709C00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T09:59:02:vwap_continuation | veto | counterfactual | OK | replay pnl=$-190.50 symbol=SPY260709C00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T10:00:04:vwap_continuation | veto | counterfactual | OK | replay pnl=$-199.50 symbol=SPY260709C00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T10:01:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-208.50 symbol=SPY260709C00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T10:05:04:vwap_continuation | veto | counterfactual | OK | replay pnl=$-186.00 symbol=SPY260709C00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T10:31:03:vwap_reclaim_failed_break | veto | counterfactual | XX | replay pnl=$65.40 symbol=SPY260709C00748000 strike=748 equity_method=reason_text_scan |
| extra:safe:2026-07-09T15:01:03:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-78.00 symbol=SPY260709P00751000 strike=751 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T15:02:04:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-75.00 symbol=SPY260709P00751000 strike=751 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T15:03:04:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-75.00 symbol=SPY260709P00751000 strike=751 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T15:04:04:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-76.50 symbol=SPY260709P00751000 strike=751 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-09T15:05:04:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-78.00 symbol=SPY260709P00751000 strike=751 equity_method=current_snapshot_fallback |
| core:bold:2026-07-10T11:21:05 | go | counterfactual | OK | replay pnl=$4.80 symbol=SPY260710C00756000 strike=756 equity_method=current_snapshot_fallback |
| core:bold:2026-07-10T11:22:05 | go | counterfactual | OK | replay pnl=$4.20 symbol=SPY260710C00756000 strike=756 equity_method=current_snapshot_fallback |
| core:bold:2026-07-10T11:23:04 | go | counterfactual | OK | replay pnl=$5.40 symbol=SPY260710C00756000 strike=756 equity_method=current_snapshot_fallback |
| core:bold:2026-07-10T11:31:05 | go | counterfactual | OK | replay pnl=$-13.50 symbol=SPY260710C00756000 strike=756 equity_method=current_snapshot_fallback |
| core:bold:2026-07-10T11:32:05 | go | counterfactual | OK | replay pnl=$-13.50 symbol=SPY260710C00756000 strike=756 equity_method=current_snapshot_fallback |
| core:bold:2026-07-10T11:33:04 | go | counterfactual | OK | replay pnl=$-13.50 symbol=SPY260710C00756000 strike=756 equity_method=current_snapshot_fallback |

## Verdict

**NOT YET CONFIDENT** — cumulative 70.8% (bar 85%), streak 0/3 consecutive runs above bar.

