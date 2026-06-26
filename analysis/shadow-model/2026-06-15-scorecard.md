# Nemotron Shadow Model Scorecard — 2026-06-15

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-06-15  
**Generated:** 2026-06-15T23:45:49Z  
**Accounts:** bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 44 |
| Overall agreement | 43/44 = **97.7%** |
| Decision-tick agreement | 11/11 = **100.0%** |
| Avg latency per call | 16267ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 10:24 | `ENTER_BULL` | `ENTER_BULL` | OK | DT |
| bold | 09:39 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 09:48 | `HOLD` | `HOLD` | OK |  |
| bold | 09:57 | `HOLD` | `HOLD` | OK |  |
| bold | 10:03 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 10:15 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:27 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 10:30 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 10:33 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 10:39 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 10:45 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 10:48 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 10:51 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 10:57 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:03 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:06 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:15 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:18 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:24 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:33 | `EXIT_TP1` | `EXIT_TP1` | OK | DT |
| bold | 11:36 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:51 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 11:57 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 12:03 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 12:12 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 12:15 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 12:26 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 12:36 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 12:54 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 13:00 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 13:06 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 13:09 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:18 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:21 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:24 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:27 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:30 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:33 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 13:42 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 15:30 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 15:36 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 15:42 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 15:45 | `HOLD_RUNNER` | `HOLD_RUNNER` | OK |  |
| bold | 15:49 | `EXIT_TIME` | `EXIT_TIME` | OK | DT |

## Disagreements

### bold 10:03  
- Real: `HOLD` (bull=9 bear=9)
- Shadow: `HOLD_DEV` (bull=9 bear=9)
- Reason: bull_score 9-10 and bear_score 8-9 indicate developing near-miss setup; no trigger present

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 97.7% | Decision-tick: 100.0% | N=44 | Rate-limited: 0 | Parse errors: 0*
