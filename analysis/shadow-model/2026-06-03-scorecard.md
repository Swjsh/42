# Nemotron Shadow Model Scorecard — 2026-06-03

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-06-03  
**Generated:** 2026-06-16T00:24:00Z  
**Accounts:** bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 16 |
| Overall agreement | 16/16 = **100.0%** |
| Decision-tick agreement | 0/0 = **0%** |
| Avg latency per call | 18833ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 09:39 | `HOLD` | `HOLD` | OK |  |
| bold | 10:06 | `HOLD` | `HOLD` | OK |  |
| bold | 10:42 | `HOLD` | `HOLD` | OK |  |
| bold | 10:48 | `HOLD` | `HOLD` | OK |  |
| bold | 11:18 | `HOLD` | `HOLD` | OK |  |
| bold | 11:36 | `HOLD` | `HOLD` | OK |  |
| bold | 11:45 | `HOLD` | `HOLD` | OK |  |
| bold | 12:21 | `HOLD` | `HOLD` | OK |  |
| bold | 13:03 | `HOLD` | `HOLD` | OK |  |
| bold | 14:03 | `HOLD` | `HOLD` | OK |  |
| bold | 14:18 | `HOLD` | `HOLD` | OK |  |
| bold | 14:36 | `HOLD` | `HOLD` | OK |  |
| bold | 14:48 | `HOLD` | `HOLD` | OK |  |
| bold | 15:12 | `HOLD` | `HOLD` | OK |  |
| bold | 15:18 | `HOLD` | `HOLD` | OK |  |
| bold | 15:39 | `HOLD` | `HOLD` | OK |  |

## Verdict

**EXCLUDED FROM DT METRIC — PDT-blocked day.**  
2026-06-03 was a PDT_LIMIT day for the Bold (Gamma-Risky-2) account: 3/3 day-trades consumed in the rolling 5-day window, blocking all new entries. Every production tick was `HOLD` — no ENTER, EXIT, or HOLD_DEV signals fire when entries are blocked. The shadow model correctly agrees with all 16 HOLD ticks (100% overall), but this does not test decision quality.

**This day does not count toward the ≥3-day DT metric.** The 3-day promotion verdict (97.1% DT, CANDIDATE TO PROMOTE) stands on 6/01 + 6/15 + 6/02.  
**Next 4th data point:** run v5.0 on **2026-05-18** (25 ticks, pre-PDT-limit day with ENTER and EXIT ticks).

---
*Overall: 100.0% | Decision-tick: 0/0 N/A | N=16 | Rate-limited: 0 | Parse errors: 0*
