# Nemotron Shadow Model Scorecard — 2026-05-13

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-05-13  
**Generated:** 2026-06-16T01:32:34Z  
**Accounts:** bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 10 |
| Overall agreement | 10/10 = **100.0%** |
| Decision-tick agreement | 3/3 = **100.0%** |
| Avg latency per call | 32228ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 12:03 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:00 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:06 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 15:09 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:12 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:15 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 15:21 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:27 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:36 | `HOLD` | `HOLD_RUNNER` | OK |  |
| bold | 15:48 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 100.0% | Decision-tick: 100.0% | N=10 | Rate-limited: 0 | Parse errors: 0*
