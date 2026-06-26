# Nemotron Shadow Model Scorecard — 2026-06-01

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-06-01  
**Generated:** 2026-06-15T23:20:59Z  
**Accounts:** bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 30 |
| Overall agreement | 26/30 = **86.7%** |
| Decision-tick agreement | 9/10 = **90.0%** |
| Avg latency per call | 15085ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 10:42 | `HOLD` | `HOLD` | OK |  |
| bold | 10:48 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 11:00 | `HOLD` | `HOLD` | OK |  |
| bold | 11:09 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 11:27 | `HOLD` | `HOLD` | OK |  |
| bold | 11:36 | `HOLD` | `HOLD` | OK |  |
| bold | 11:45 | `HOLD` | `HOLD` | OK |  |
| bold | 11:48 | `HOLD` | `HOLD` | OK |  |
| bold | 12:18 | `HOLD` | `HOLD` | OK |  |
| bold | 12:21 | `HOLD` | `HOLD` | OK |  |
| bold | 12:48 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:57 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:42 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:00 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:46 | `ENTER_BULL` | `HOLD_DEV` | XX | DT |
| bold | 14:48 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 14:51 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 15:00 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:03 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:06 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:09 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 15:12 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 15:18 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:27 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:30 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:37 | `EXIT_STOP` | `EXIT_STOP` | OK | DT |
| bold | 15:33 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 12:30 | `HOLD` | `HOLD` | OK |  |
| bold | 14:57 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |

## Disagreements

### bold 10:48  
- Real: `HOLD` (bull=10 bear=6)
- Shadow: `HOLD_DEV` (bull=10 bear=6)
- Reason: bull_score 10 near-miss, no trigger, no position

### bold 11:09  
- Real: `HOLD` (bull=10 bear=5)
- Shadow: `HOLD_DEV` (bull=10 bear=5)
- Reason: bull_score 10 near-miss developing, no trigger

### bold 14:46 **[DECISION TICK]**  
- Real: `ENTER_BULL` (bull=10 bear=5)
- Shadow: `HOLD_DEV` (bull=10 bear=5)
- Reason: bull_score 10 near-miss, no trigger, developing setup

### bold 15:12  
- Real: `HOLD` (bull=9 bear=5)
- Shadow: `HOLD_DEV` (bull=9 bear=5)
- Reason: bull_score 9 indicates developing bullish setup; no trigger yet

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **90.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 1 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 86.7% | Decision-tick: 90.0% | N=30 | Rate-limited: 0 | Parse errors: 0*
