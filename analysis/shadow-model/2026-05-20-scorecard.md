# Nemotron Shadow Model Scorecard — 2026-05-20

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-05-20  
**Generated:** 2026-06-24T23:24:40Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 6 |
| Overall agreement | 6/6 = **100.0%** |
| Decision-tick agreement | 1/1 = **100.0%** |
| Avg latency per call | 12807ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 10:03 | `HOLD` | `HOLD_RUNNER` | OK |  |
| safe | 10:18 | `HOLD` | `HOLD` | OK |  |
| safe | 10:06 | `EXIT_ALL` | `EXIT_STOP` | OK | DT |
| safe | 10:30 | `HOLD` | `HOLD` | OK |  |
| safe | 14:00:00 | `SKIP_VIX_STALE` | `HOLD` | OK |  |
| safe | 14:27 | `HOLD` | `HOLD` | OK |  |

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 100.0% | Decision-tick: 100.0% | N=6 | Rate-limited: 0 | Parse errors: 0*
