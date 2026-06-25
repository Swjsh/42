# qwen Shadow Model Scorecard — 2026-05-20

**Model:** `qwen/qwen3-next-80b-a3b-instruct:free`  
**Evaluation date:** 2026-05-20  
**Generated:** 2026-06-25T03:11:08Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 6 |
| Overall agreement | 5/6 = **83.3%** |
| Decision-tick agreement | 0/0 = **0%** |
| Avg latency per call | 34782ms |
| Rate-limited (429) | 1 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |
| Non-DT ticks skipped (--dt-only) | 5 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 10:03 | `HOLD` | `HOLD` | OK |  |
| safe | 10:18 | `HOLD` | `HOLD` | OK |  |
| safe | 10:06 | `EXIT_ALL` | `RATE_LIMITED` | XX |  |
| safe | 10:30 | `HOLD` | `HOLD` | OK |  |
| safe | 14:00:00 | `SKIP_VIX_STALE` | `SKIP_VIX_STALE` | OK |  |
| safe | 14:27 | `HOLD` | `HOLD` | OK |  |

## Disagreements

### safe 10:06  
- Real: `EXIT_ALL` (bull=0 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream. Please 

## Verdict

**INCONCLUSIVE — no decision ticks in sample.**  
All ticks were plain HOLD or HOLD_RUNNER. This day had no entries, exits, or near-misses. Run on a day with ENTER_BULL/ENTER_BEAR/EXIT_*/HOLD_DEV ticks to get a meaningful evaluation.

---
*Overall: 83.3% | Decision-tick: 0.0% | N=6 | Rate-limited: 1 | Parse errors: 0*
