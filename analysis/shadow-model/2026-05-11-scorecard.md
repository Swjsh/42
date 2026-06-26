# Nemotron Shadow Model Scorecard — 2026-05-11

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-05-11  
**Generated:** 2026-06-16T01:26:37Z  
**Accounts:** bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 6 |
| Overall agreement | 4/6 = **66.7%** |
| Decision-tick agreement | 3/3 = **100.0%** |
| Avg latency per call | 28086ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 09:39 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 09:57 | `HOLD` | `HOLD` | OK |  |
| bold | 10:03 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:06 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 10:15 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 10:25 | `ENTER_BULL` | `ENTER_BULL` | OK | DT |

## Disagreements

### bold 10:06  
- Real: `HOLD` (bull=9 bear=4)
- Shadow: `HOLD_DEV` (bull=9 bear=4)
- Reason: bull_score 9-10 with no position indicates near-miss setup

### bold 10:15  
- Real: `HOLD` (bull=9 bear=4)
- Shadow: `HOLD_DEV` (bull=9 bear=4)
- Reason: bull_score 9 near-miss, awaiting trigger

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 66.7% | Decision-tick: 100.0% | N=6 | Rate-limited: 0 | Parse errors: 0*
