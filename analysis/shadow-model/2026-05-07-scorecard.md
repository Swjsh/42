# Nemotron Shadow Model Scorecard — 2026-05-07

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-05-07  
**Generated:** 2026-06-24T23:37:27Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 5 |
| Overall agreement | 5/5 = **100.0%** |
| Decision-tick agreement | 3/3 = **100.0%** |
| Avg latency per call | 9516ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 10:30 | `HOLD` | `HOLD` | OK |  |
| safe | 10:33 | `HOLD_DEV` | `HOLD` | OK | DT |
| safe | 10:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:53 | `ERROR_TV` | `HOLD` | OK |  |
| safe | 12:04 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 100.0% | Decision-tick: 100.0% | N=5 | Rate-limited: 0 | Parse errors: 0*
