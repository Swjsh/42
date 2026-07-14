# free-model-audit — heartbeat_veto — 2026-07-14

**Subject:** `heartbeat_veto`  
**Generated:** 2026-07-14T16:20:51  
**Confidence bar:** >=85% correct-grade rate over >=15 graded evidence points, sustained across >=3 consecutive runs (same bar as the Nemotron shadow-model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).

## This run

| Metric | Value |
|---|---|
| Items collected | 45 |
| Already graded (skipped, dedupe) | 2 |
| Newly graded this run | 43 |
| Correct | 28 |
| Wrong | 15 |
| Ungraded (insufficient data) | 0 |
| This-run correct-grade rate | 28/43 = **65.1%** |
| Graded via counterfactual replay | 43 |
| Graded via blind Sonnet judgment (fallback) | 0 |

## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)

| Metric | Value |
|---|---|
| Vetoes graded | 37 / 37 |
| TRUE vetoes (correctly blocked a loser/marginal) | 26 |
| FALSE vetoes (wrongly blocked a winner) | 11 |
| **Veto-only accuracy** (the safety-net's actual job) | **70.3%** |
| GO decisions graded | 6 / 6 |
| **GO-only accuracy** (fill went on to be non-losing) | **33.3%** |
| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to veto, a lone GO is enough to pass) | 4 / 37 |

**Read this split, not just the blended rate above.** The blended "correct-grade rate" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT the same finding as a low veto-only rate — only the latter says the safety net itself is unreliable. Read both numbers above before concluding which one moved.

## Cumulative (all-time, this subject)

| Metric | Value |
|---|---|
| Evidence points | 151 |
| Cumulative correct-grade rate | **68.9%** |
| Consecutive runs above bar | 0 / 3 |
| Confident | no |
| Current cadence | every 2 day(s) |

## Detail

| item_id | decision | grading_method | correct | evidence |
|---|---|---|---|---|
| core:safe:2026-07-14T10:36:03 | veto | counterfactual | XX | replay pnl=$76.20 symbol=SPY260714C00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T10:36:32 | veto | counterfactual | OK | replay pnl=$-39.00 symbol=SPY260714C00755000 strike=755 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T10:37:03 | veto | counterfactual | XX | replay pnl=$72.60 symbol=SPY260714C00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T10:37:20 | go | counterfactual | XX | replay pnl=$-36.00 symbol=SPY260714C00755000 strike=755 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T10:38:03 | go | counterfactual | OK | replay pnl=$76.80 symbol=SPY260714C00752000 strike=752 equity_method=reason_text_scan |
| core:bold:2026-07-14T10:38:25 | veto | counterfactual | OK | replay pnl=$-36.00 symbol=SPY260714C00755000 strike=755 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:16:04 | veto | counterfactual | OK | replay pnl=$-130.50 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T13:16:30 | veto | counterfactual | OK | replay pnl=$-25.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:17:03 | veto | counterfactual | OK | replay pnl=$-138.00 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T13:18:06 | veto | counterfactual | OK | replay pnl=$-22.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:18:03 | veto | counterfactual | OK | replay pnl=$-123.00 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T13:18:35 | veto | counterfactual | OK | replay pnl=$-22.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:31:03 | veto | counterfactual | XX | replay pnl=$31.80 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:32:03 | veto | counterfactual | XX | replay pnl=$38.40 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:33:04 | veto | counterfactual | OK | replay pnl=$-99.00 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:34:03 | veto | counterfactual | OK | replay pnl=$-105.00 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T13:33:23 | veto | counterfactual | OK | replay pnl=$6.60 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T13:34:19 | veto | counterfactual | OK | replay pnl=$-18.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:35:03 | veto | counterfactual | OK | replay pnl=$-117.00 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T13:35:25 | veto | counterfactual | OK | replay pnl=$-21.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:36:03 | go | counterfactual | XX | replay pnl=$-118.50 symbol=SPY260714P00752000 strike=752 equity_method=reason_text_scan |
| core:bold:2026-07-14T13:36:31 | veto | counterfactual | OK | replay pnl=$-21.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:37:03 | go | counterfactual | XX | replay pnl=$-100.50 symbol=SPY260714P00752000 strike=752 equity_method=reason_text_scan |
| core:bold:2026-07-14T13:37:20 | veto | counterfactual | OK | replay pnl=$-18.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:38:03 | go | counterfactual | XX | replay pnl=$-103.50 symbol=SPY260714P00752000 strike=752 equity_method=reason_text_scan |
| core:safe:2026-07-14T13:39:03 | veto | counterfactual | XX | replay pnl=$37.20 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T13:40:03 | veto | counterfactual | XX | replay pnl=$36.60 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T14:26:03 | veto | counterfactual | XX | replay pnl=$18.60 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T14:27:03 | veto | counterfactual | XX | replay pnl=$19.80 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T14:28:03 | veto | counterfactual | XX | replay pnl=$18.60 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T14:29:03 | veto | counterfactual | XX | replay pnl=$19.80 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:safe:2026-07-14T14:30:03 | veto | counterfactual | XX | replay pnl=$21.60 symbol=SPY260714P00752000 strike=752 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:38:04 | veto | counterfactual | OK | replay pnl=$3.60 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:39:04 | veto | counterfactual | OK | replay pnl=$3.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:40:04 | veto | counterfactual | OK | replay pnl=$3.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:41:04 | go | counterfactual | OK | replay pnl=$-10.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:42:04 | veto | counterfactual | OK | replay pnl=$3.60 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:43:04 | veto | counterfactual | OK | replay pnl=$-10.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:44:04 | veto | counterfactual | OK | replay pnl=$3.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:45:04 | veto | counterfactual | OK | replay pnl=$-9.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:46:04 | veto | counterfactual | OK | replay pnl=$-9.00 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:50:04 | veto | counterfactual | OK | replay pnl=$-7.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |
| core:bold:2026-07-14T14:51:04 | veto | counterfactual | OK | replay pnl=$-7.50 symbol=SPY260714P00749000 strike=749 equity_method=current_snapshot_fallback |

## Verdict

**NOT YET CONFIDENT** — cumulative 68.9% (bar 85%), streak 0/3 consecutive runs above bar.

