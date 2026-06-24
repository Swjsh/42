# Nemotron Shadow Model Scorecard — 2026-05-19

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-05-19  
**Generated:** 2026-06-24T23:19:48Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 3 |
| Overall agreement | 3/3 = **100.0%** |
| Decision-tick agreement | 2/2 = **100.0%** |
| Avg latency per call | 14396ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 18:06:21Z | `ENTER` | `HOLD` | OK | DT |
| safe | 18:20:17Z | `EXIT_STOP` | `EXIT_STOP` | OK | DT |
| safe | 10:25 | `HOLD` | `HOLD` | OK |  |

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 100.0% | Decision-tick: 100.0% | N=3 | Rate-limited: 0 | Parse errors: 0*
