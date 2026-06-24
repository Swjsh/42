# Nemotron Shadow Model Scorecard — 2026-06-24

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-06-24  
**Generated:** 2026-06-24T23:30:12Z  
**Accounts:** safe, bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 22 |
| Overall agreement | 22/22 = **100.0%** |
| Decision-tick agreement | 21/21 = **100.0%** |
| Avg latency per call | 8976ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |

## Per-Account Breakdown

| Account | Ticks | Agree | % | DT Ticks | DT Agree | DT % |
|---------|-------|-------|---|----------|----------|------|
| safe | 8 | 8 | 100.0% | 7 | 7 | 100.0% |
| bold | 14 | 14 | 100.0% | 14 | 14 | 100.0% |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 14:03 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:13 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:15 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:36 | `HOLD` | `HOLD` | OK |  |
| safe | 14:39 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:55 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:09 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:15 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 14:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:24 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:34 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:48 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:54 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:06 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 15:18 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 15:21 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 15:24 | `HOLD_DEV` | `HOLD` | OK | DT |
| bold | 15:42 | `HOLD_DEV` | `HOLD` | OK | DT |

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0%** of decision ticks (entries, exits, near-misses, skips). Agreement is high enough to consider running Nemotron as the live heartbeat for rate-pool isolation at $0/mo.  
Next steps: (1) run 3+ more trading days, (2) inspect the 0 decision-tick mismatches for systematic patterns, (3) J ratification before promoting.

---
*Overall: 100.0% | Decision-tick: 100.0% | N=22 | Rate-limited: 0 | Parse errors: 0*
