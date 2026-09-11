# free-model-audit — heartbeat_veto — 2026-08-10

**Subject:** `heartbeat_veto`  
**Generated:** 2026-08-10T21:00:53  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 281 |
| Already graded (skipped, dedupe) | 6 |
| Newly graded this run | 275 |
| Correct | 159 |
| Wrong | 116 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 159/275 = **57.8%** |
| Graded via counterfactual replay | 275 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 64 / 64 |
| TRUE vetoes (correctly blocked a loser/marginal) | 20 |
| FALSE vetoes (wrongly blocked a winner) | 44 |
| **Veto-only accuracy** (the safety-net's actual job) | **31.2%** |
| GO decisions graded | 211 / 211 |
| **GO-only accuracy** (fill went on to be non-losing) | **65.9%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 11 / 64 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 460 |
| Cumulative correct-grade rate | **61.7%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-07-17T11:06:03 | go | counterfactual | XX | real fill pnl=$-36.99 symbol=SPY260717P00744000 |
| core:safe:2026-07-17T11:08:03 | go | counterfactual | OK | replay pnl=$67.80 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T11:07:03 | go | counterfactual | XX | replay pnl=$-201.00 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T11:09:03 | go | counterfactual | OK | replay pnl=$69.60 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T11:40:04 | go | counterfactual | XX | real fill pnl=$-102.00 symbol=SPY260717P00745000 |
| core:safe:2026-07-17T13:01:03 | go | counterfactual | OK | real fill pnl=$241.00 symbol=SPY260717P00746000 |
| core:safe:2026-07-17T13:02:04 | go | counterfactual | OK | replay pnl=$49.80 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:03:03 | go | counterfactual | OK | replay pnl=$48.60 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:51:03 | go | counterfactual | OK | replay pnl=$94.80 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:51:21 | go | counterfactual | OK | real fill pnl=$191.00 symbol=SPY260717P00743000 |
| core:safe:2026-07-17T13:52:03 | go | counterfactual | OK | replay pnl=$170.40 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:52:17 | go | counterfactual | OK | replay pnl=$40.80 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:53:03 | go | counterfactual | OK | replay pnl=$100.20 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:53:18 | go | counterfactual | OK | replay pnl=$42.00 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:54:03 | go | counterfactual | OK | replay pnl=$100.80 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:54:16 | go | counterfactual | OK | replay pnl=$41.40 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:55:03 | go | counterfactual | OK | replay pnl=$104.40 symbol=SPY260717P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:55:19 | go | counterfactual | OK | replay pnl=$45.00 symbol=SPY260717P00744000 strike=744 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:56:03 | go | counterfactual | OK | replay pnl=$77.40 symbol=SPY260717P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:56:15 | go | counterfactual | OK | replay pnl=$31.20 symbol=SPY260717P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:57:03 | go | counterfactual | OK | replay pnl=$78.00 symbol=SPY260717P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:58:03 | go | counterfactual | OK | replay pnl=$79.20 symbol=SPY260717P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:58:16 | go | counterfactual | OK | replay pnl=$31.20 symbol=SPY260717P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T13:59:03 | go | counterfactual | OK | replay pnl=$76.20 symbol=SPY260717P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:bold:2026-07-17T13:59:16 | go | counterfactual | OK | replay pnl=$30.00 symbol=SPY260717P00743000 strike=743 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T14:00:03 | go | counterfactual | OK | replay pnl=$80.40 symbol=SPY260717P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-17T14:49:03 | go | counterfactual | XX | real fill pnl=$-56.00 symbol=SPY260717P00743000 |
| core:safe:2026-07-17T14:50:03 | go | counterfactual | OK | replay pnl=$33.00 symbol=SPY260717P00743000 strike=743 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-20T09:52:03:vix_regime_dayside | veto | counterfactual | OK | replay pnl=$-132.00 symbol=SPY260720C00748000 strike=748 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-20T09:53:02:vix_regime_dayside | veto | counterfactual | OK | replay pnl=$-123.00 symbol=SPY260720C00748000 strike=748 equity_method=current_snapshot_fallback |
| core:safe:2026-07-20T14:01:02 | go | counterfactual | XX | real fill pnl=$-24.00 symbol=SPY260720P00745000 |
| core:safe:2026-07-20T14:02:02 | go | counterfactual | OK | replay pnl=$43.20 symbol=SPY260720P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-20T14:03:02 | go | counterfactual | OK | replay pnl=$49.20 symbol=SPY260720P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-20T14:04:02 | go | counterfactual | OK | replay pnl=$50.40 symbol=SPY260720P00745000 strike=745 equity_method=current_snapshot_fallback |
| core:safe:2026-07-20T14:05:03 | go | counterfactual | OK | replay pnl=$51.60 symbol=SPY260720P00745000 strike=745 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-21T10:20:04:vix_regime_dayside | veto | counterfactual | OK | replay pnl=$-214.50 symbol=SPY260721P00746000 strike=746 equity_method=current_snapshot_fallback |
| core:safe:2026-07-21T14:56:02 | veto | counterfactual | OK | replay pnl=$-49.50 symbol=SPY260721P00748000 strike=748 equity_method=current_snapshot_fallback |
| core:safe:2026-07-21T14:57:03 | veto | counterfactual | OK | replay pnl=$-49.50 symbol=SPY260721P00748000 strike=748 equity_method=current_snapshot_fallback |
| core:safe:2026-07-21T14:58:03 | go | counterfactual | OK | real fill pnl=$0.00 symbol=SPY260721P00748000 |
| core:safe:2026-07-21T14:59:02 | veto | counterfactual | OK | replay pnl=$-45.00 symbol=SPY260721P00748000 strike=748 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-22T13:31:03:bollinger_squeeze | veto | counterfactual | XX | replay pnl=$127.80 symbol=SPY260722P00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-22T13:32:03:bollinger_squeeze | veto | counterfactual | XX | replay pnl=$126.20 symbol=SPY260722P00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-22T13:33:02:bollinger_squeeze | veto | counterfactual | XX | replay pnl=$125.40 symbol=SPY260722P00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-22T13:34:03:bollinger_squeeze | veto | counterfactual | XX | replay pnl=$122.20 symbol=SPY260722P00749000 strike=749 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-23T09:57:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-220.50 symbol=SPY260723C00741000 strike=741 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-23T09:56:03:vwap_continuation | veto | counterfactual | OK | replay pnl=$-237.00 symbol=SPY260723C00741000 strike=741 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-23T09:56:03:vwap_reclaim_failed_break | veto | counterfactual | OK | replay pnl=$-237.00 symbol=SPY260723C00741000 strike=741 equity_method=current_snapshot_fallback |
| core:bold:2026-07-23T11:29:03 | go | counterfactual | XX | real fill pnl=$-305.00 symbol=SPY260723P00735000 |
| core:bold:2026-07-27T12:57:04 | go | counterfactual | XX | real fill pnl=$-355.00 symbol=SPY260727P00737000 |
| core:bold:2026-07-27T12:58:04 | go | counterfactual | OK | replay pnl=$36.60 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-27T12:59:04 | go | counterfactual | OK | replay pnl=$36.60 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-27T13:01:04 | go | counterfactual | OK | replay pnl=$42.60 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-27T13:02:04 | go | counterfactual | XX | replay pnl=$-133.50 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-27T13:03:04 | go | counterfactual | XX | replay pnl=$-130.50 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-27T13:04:04 | go | counterfactual | XX | replay pnl=$-136.50 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-27T13:05:04 | go | counterfactual | XX | replay pnl=$-129.00 symbol=SPY260727P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:safe:2026-07-27T13:31:03 | go | counterfactual | XX | real fill pnl=$-162.00 symbol=SPY260727P00736000 |
| core:safe:2026-07-27T13:32:03 | go | counterfactual | XX | replay pnl=$-117.00 symbol=SPY260727P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-27T13:33:03 | go | counterfactual | OK | replay pnl=$42.60 symbol=SPY260727P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-27T13:34:03 | go | counterfactual | OK | replay pnl=$41.40 symbol=SPY260727P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-27T13:35:04 | go | counterfactual | OK | replay pnl=$43.20 symbol=SPY260727P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:bold:2026-07-28T11:22:04 | go | counterfactual | OK | replay pnl=$48.60 symbol=SPY260728C00742000 strike=742 equity_method=current_snapshot_fallback |
| core:bold:2026-07-28T11:25:05 | go | counterfactual | OK | replay pnl=$58.80 symbol=SPY260728C00742000 strike=742 equity_method=current_snapshot_fallback |
| core:bold:2026-07-28T11:26:04 | go | counterfactual | XX | real fill pnl=$-295.00 symbol=SPY260728C00741000 |
| core:bold:2026-07-28T11:27:04 | go | counterfactual | XX | real fill pnl=$-295.00 symbol=SPY260728C00741000 |
| core:bold:2026-07-28T11:28:04 | go | counterfactual | XX | real fill pnl=$-295.00 symbol=SPY260728C00741000 |
| core:bold:2026-07-28T11:29:04 | go | counterfactual | OK | replay pnl=$31.20 symbol=SPY260728C00743000 strike=743 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-28T13:46:03:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-142.50 symbol=SPY260728P00741000 strike=741 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-28T13:47:03:bollinger_squeeze | veto | counterfactual | OK | replay pnl=$-150.00 symbol=SPY260728P00741000 strike=741 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-28T13:48:03:bollinger_squeeze | veto | counterfactual | XX | replay pnl=$47.40 symbol=SPY260728P00741000 strike=741 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-28T13:49:03:bollinger_squeeze | veto | counterfactual | XX | replay pnl=$45.00 symbol=SPY260728P00741000 strike=741 equity_method=current_snapshot_fallback |
| core:bold:2026-07-28T14:04:04 | go | counterfactual | OK | replay pnl=$-10.50 symbol=SPY260728C00744000 strike=744 equity_method=reason_text_scan |
| core:safe:2026-07-29T10:02:47 | go | counterfactual | OK | replay pnl=$154.20 symbol=SPY260729P00737000 strike=737 equity_method=current_snapshot_fallback |
| core:safe:2026-07-29T10:03:47 | go | counterfactual | OK | replay pnl=$162.00 symbol=SPY260729P00737000 strike=737 equity_method=current_snapshot_fallback |
| core:safe:2026-07-29T10:04:47 | go | counterfactual | OK | replay pnl=$154.20 symbol=SPY260729P00737000 strike=737 equity_method=current_snapshot_fallback |
| core:safe:2026-07-29T10:05:47 | go | counterfactual | OK | replay pnl=$152.40 symbol=SPY260729P00737000 strike=737 equity_method=current_snapshot_fallback |
| core:safe:2026-07-29T10:50:46 | go | counterfactual | OK | replay pnl=$169.80 symbol=SPY260729P00734000 strike=734 equity_method=current_snapshot_fallback |
| core:safe:2026-07-29T11:16:47 | veto | counterfactual | XX | replay pnl=$165.60 symbol=SPY260729P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:safe:2026-07-29T11:20:46 | go | counterfactual | OK | replay pnl=$187.80 symbol=SPY260729P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:bold:2026-07-30T11:31:03 | go | counterfactual | XX | replay pnl=$-154.50 symbol=SPY260730P00732000 strike=732 equity_method=reason_text_scan |
| core:safe:2026-07-30T11:32:02 | go | counterfactual | XX | replay pnl=$-294.00 symbol=SPY260730P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:33:02 | go | counterfactual | XX | replay pnl=$-280.50 symbol=SPY260730P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:34:02 | go | counterfactual | XX | replay pnl=$-225.00 symbol=SPY260730P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:36:02 | go | counterfactual | OK | replay pnl=$81.60 symbol=SPY260730P00735000 strike=735 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:42:02 | go | counterfactual | XX | replay pnl=$-252.00 symbol=SPY260730P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:43:02 | go | counterfactual | XX | replay pnl=$-232.50 symbol=SPY260730P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:44:02 | go | counterfactual | XX | replay pnl=$-235.50 symbol=SPY260730P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:45:02 | go | counterfactual | XX | replay pnl=$-223.50 symbol=SPY260730P00736000 strike=736 equity_method=current_snapshot_fallback |
| core:safe:2026-07-30T11:46:02 | go | counterfactual | XX | replay pnl=$-207.00 symbol=SPY260730P00736000 strike=736 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-30T11:54:02:double_bottom_base_quiet | veto | counterfactual | XX | replay pnl=$385.60 symbol=SPY260730C00737000 strike=737 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-30T11:55:02:double_bottom_base_quiet | veto | counterfactual | XX | replay pnl=$120.00 symbol=SPY260730C00737000 strike=737 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-30T11:56:03:double_bottom_base_quiet | veto | counterfactual | XX | replay pnl=$383.20 symbol=SPY260730C00737000 strike=737 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-30T11:57:02:double_bottom_base_quiet | veto | counterfactual | XX | replay pnl=$120.00 symbol=SPY260730C00737000 strike=737 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-30T11:58:02:double_bottom_base_quiet | veto | counterfactual | XX | replay pnl=$384.80 symbol=SPY260730C00737000 strike=737 equity_method=current_snapshot_fallback |
| extra:safe:2026-07-30T12:00:03:double_bottom_base_quiet | veto | counterfactual | XX | replay pnl=$391.20 symbol=SPY260730C00737000 strike=737 equity_method=current_snapshot_fallback |
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
| core:safe:2026-08-10T09:56:03 | go | counterfactual | XX | real fill pnl=$-141.00 symbol=SPY260810C00773000 |
| core:bold:2026-08-10T09:56:55 | go | counterfactual | XX | real fill pnl=$-270.00 symbol=SPY260810C00773000 |
| core:safe:2026-08-10T09:57:03 | go | counterfactual | OK | replay pnl=$76.20 symbol=SPY260810C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T09:57:48 | go | counterfactual | OK | replay pnl=$25.80 symbol=SPY260810C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T09:58:03 | go | counterfactual | OK | replay pnl=$75.00 symbol=SPY260810C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T09:59:03 | go | counterfactual | OK | replay pnl=$81.00 symbol=SPY260810C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T09:58:59 | go | counterfactual | OK | replay pnl=$25.20 symbol=SPY260810C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:00:04 | go | counterfactual | OK | replay pnl=$79.80 symbol=SPY260810C00773000 strike=773 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T09:59:48 | go | counterfactual | OK | replay pnl=$27.00 symbol=SPY260810C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:00:40 | go | counterfactual | OK | replay pnl=$27.00 symbol=SPY260810C00775000 strike=775 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:11:04 | go | counterfactual | OK | replay pnl=$62.40 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:11:52 | go | counterfactual | OK | replay pnl=$19.80 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:12:04 | go | counterfactual | OK | replay pnl=$64.20 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:12:54 | go | counterfactual | OK | replay pnl=$20.40 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:13:04 | go | counterfactual | OK | replay pnl=$66.60 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:13:59 | go | counterfactual | OK | replay pnl=$21.00 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:14:03 | go | counterfactual | OK | replay pnl=$66.60 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:15:04 | go | counterfactual | OK | replay pnl=$67.20 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:15:17 | go | counterfactual | OK | replay pnl=$21.00 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:15:54 | go | counterfactual | OK | replay pnl=$21.00 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:16:04 | go | counterfactual | OK | replay pnl=$66.60 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:17:00 | go | counterfactual | OK | replay pnl=$19.80 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:17:03 | go | counterfactual | OK | replay pnl=$64.20 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:18:03 | go | counterfactual | OK | replay pnl=$63.00 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:18:26 | go | counterfactual | OK | replay pnl=$18.60 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:31:04 | go | counterfactual | XX | replay pnl=$-187.50 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:32:04 | go | counterfactual | XX | replay pnl=$-187.50 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:32:10 | go | counterfactual | XX | replay pnl=$-55.50 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:33:03 | go | counterfactual | XX | replay pnl=$-180.00 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:32:59 | go | counterfactual | XX | replay pnl=$-55.50 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:33:56 | go | counterfactual | XX | replay pnl=$-54.00 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:34:03 | go | counterfactual | XX | replay pnl=$-187.50 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |
| core:bold:2026-08-10T10:34:51 | go | counterfactual | XX | replay pnl=$-57.00 symbol=SPY260810C00776000 strike=776 equity_method=current_snapshot_fallback |
| core:safe:2026-08-10T10:35:05 | go | counterfactual | XX | replay pnl=$-184.50 symbol=SPY260810C00774000 strike=774 equity_method=current_snapshot_fallback |

## Verdict

**NOT YET CONFIDENT** — cumulative 61.7% (bar 85%), streak 0/3 consecutive runs above bar.


## Veto reason-class breakdown (VETO-HTF-CONFLICT-REGRADE, 2026-07-16 queue item)

Every graded VETO item, keyword-classified by its free-model reason string(s) into {htf_conflict, spread_data_doubt, other} -- see `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class`. Filed because the pre-registered study `vwapcont-htf-precheck-2026-07-16` (analysis/recommendations/vwapcont-htf-precheck-2026-07-16.json, verdict KILL) found the HTF-OPPOSED vwap_continuation cohort OUTPERFORMS the aligned cohort (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried, mechanism fits C28 -- the 15m ribbon lags, fast signals catch reversals first). The veto layer's single most common cited reason is exactly this HTF-conflict framing, so its false-veto rate is graded as its OWN cohort here, not blended into the overall veto accuracy above.

| Reason class | Vetoes tagged | Graded | TRUE veto | FALSE veto | Ungraded | False-veto rate |
|---|---|---|---|---|---|---|
| htf_conflict | 71 | 71 | 51 | 20 | 0 | **28.2%** |
| spread_data_doubt | 2 | 2 | 1 | 1 | 0 | **50.0%** |
| other | 3 | 3 | 1 | 2 | 0 | **66.7%** |

**INSUFFICIENT CONTRAST** -- htf_conflict false-veto rate 28.2% (n=71) graded, but the other-classes comparison n=5 is below the 5-item floor or not elevated. Do NOT touch the veto sysmsg yet.

