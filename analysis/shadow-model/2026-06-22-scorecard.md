# Nemotron Shadow Model Scorecard — 2026-06-22

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-06-22  
**Generated:** 2026-06-22T20:42:53Z  
**Accounts:** safe, bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 73 |
| Overall agreement | 61/73 = **83.6%** |
| Decision-tick agreement | 53/61 = **86.9%** |
| Avg latency per call | 32475ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Per-Account Breakdown

| Account | Ticks | Agree | % | DT Ticks | DT Agree | DT % |
|---------|-------|-------|---|----------|----------|------|
| safe | 17 | 16 | 94.1% | 16 | 15 | 93.8% |
| bold | 56 | 45 | 80.4% | 45 | 38 | 84.4% |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 10:13 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 10:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 10:48 | `HOLD_DEV` | `ENTER_BEAR` | XX | DT |
| safe | 11:05 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 11:12 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 11:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 11:27 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 11:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 11:42 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 10:00 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 12:20 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 12:30 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 12:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 12:45 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 13:25 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 13:42 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:51 | `HOLD` | `HOLD` | OK |  |
| bold | 09:39 | `HOLD` | `HOLD` | OK |  |
| bold | 10:03 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 10:21 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:24 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:30 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:39 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:42 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:54 | `HOLD_DEV` | `ENTER_BEAR` | XX | DT |
| bold | 10:57 | `BEAR_FILL_BAR_SKIP` | `ENTER_BEAR` | XX | DT |
| bold | 11:06 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 11:09 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 11:15 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 11:18 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 11:24 | `SKIP_STALE` | `HOLD_DEV` | XX | DT |
| bold | 11:34 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 11:36 | `HOLD` | `HOLD` | OK |  |
| bold | 11:45 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 11:54 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 11:57 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:00 | `HOLD_DEV` | `HOLD` | XX | DT |
| bold | 12:06 | `HOLD_DEV` | `HOLD` | XX | DT |
| bold | 12:12 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:21 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:27 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:30 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:43 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:49 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:54 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:04 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:21 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:30 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:37 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:42 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:48 | `HOLD_DEV` | `HOLD` | XX | DT |
| bold | 13:55 | `HOLD` | `HOLD` | OK |  |
| bold | 14:00 | `HOLD` | `HOLD` | OK |  |
| bold | 14:24 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:53 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:55 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:57 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:00 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:04 | `HOLD_DEV` | `ENTER_BEAR` | XX | DT |
| bold | 15:06 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:09 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 15:24 | `HOLD` | `HOLD` | OK |  |
| bold | 15:32 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:39 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 15:47 | `HOLD` | `HOLD` | OK |  |
| bold | 14:12 | `HOLD` | `HOLD` | OK |  |
| bold | 14:27 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:39 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |

## Disagreements

### safe 10:48 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=4 bear=10)
- Shadow: `ENTER_BEAR` (bull=4 bear=10)
- Reason: Bearish entry: all 10 filters passed, trigger ribbon_flip confirmed, no blockers.

### bold 10:03  
- Real: `HOLD` (bull=10 bear=4)
- Shadow: `HOLD_DEV` (bull=10 bear=4)
- Reason: bull_score 10 near-miss

### bold 10:54 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=6 bear=10)
- Shadow: `ENTER_BEAR` (bull=6 bear=10)
- Reason: Bearish entry: all 10 filters pass, trigger ribbon_flip confirmed, no blockers.

### bold 10:57 **[DECISION TICK]**  
- Real: `BEAR_FILL_BAR_SKIP` (bull=6 bear=10)
- Shadow: `ENTER_BEAR` (bull=6 bear=10)
- Reason: Bearish entry triggered with all filters passed and ribbon_flip signal

### bold 11:18  
- Real: `HOLD` (bull=9 bear=8)
- Shadow: `HOLD_DEV` (bull=9 bear=8)
- Reason: bull_score 9 near-miss triggers HOLD_DEV

### bold 11:24 **[DECISION TICK]**  
- Real: `SKIP_STALE` (bull=9 bear=8)
- Shadow: `HOLD_DEV` (bull=9 bear=8)
- Reason: bull_score 9 near-miss bullish setup awaiting trigger

### bold 12:00 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=5 bear=7)
- Shadow: `HOLD` (bull=5 bear=7)
- Reason: No entry scores met thresholds and no position open

### bold 12:06 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=5 bear=7)
- Shadow: `HOLD` (bull=5 bear=7)
- Reason: Scores below entry thresholds and no trigger present

### bold 13:48 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=8 bear=7)
- Shadow: `HOLD` (bull=8 bear=7)
- Reason: bull_score 8 with BEAR ribbon negates near-miss and bear_score 7 insufficient for entry

### bold 15:04 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=4 bear=10)
- Shadow: `ENTER_BEAR` (bull=4 bear=10)
- Reason: bear_score 10 with trigger present and no blockers

### bold 15:09  
- Real: `HOLD` (bull=4 bear=10)
- Shadow: `HOLD_DEV` (bull=4 bear=10)
- Reason: Bear setup complete but trigger absent, awaiting entry signal

### bold 15:39  
- Real: `HOLD` (bull=4 bear=10)
- Shadow: `HOLD_DEV` (bull=4 bear=10)
- Reason: bear_score 10 but no trigger; waiting for entry trigger

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **86.9%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 8 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 83.6% | Decision-tick: 86.9% | N=73 | Rate-limited: 0 | Parse errors: 0*
