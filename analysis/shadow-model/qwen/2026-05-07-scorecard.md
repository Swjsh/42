# qwen Shadow Model Scorecard — 2026-05-07

**Model:** `qwen/qwen3-next-80b-a3b-instruct:free`  
**Evaluation date:** 2026-05-07  
**Generated:** 2026-06-25T03:04:39Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 5 |
| Overall agreement | 2/5 = **40.0%** |
| Decision-tick agreement | 0/0 = **0%** |
| Avg latency per call | 122050ms |
| Rate-limited (429) | 3 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |
| Non-DT ticks skipped (--dt-only) | 2 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 10:30 | `HOLD` | `HOLD` | OK |  |
| safe | 10:33 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |
| safe | 10:51 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |
| safe | 14:53 | `ERROR_TV` | `ERROR_TV` | OK |  |
| safe | 12:04 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |

## Disagreements

### safe 10:33  
- Real: `HOLD_DEV` (bull=7 bear=4)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream. Please 

### safe 10:51  
- Real: `HOLD_DEV` (bull=9 bear=4)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream. Please 

### safe 12:04  
- Real: `HOLD_DEV` (bull=4 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream. Please 

## Verdict

**INCONCLUSIVE — no decision ticks in sample.**  
All ticks were plain HOLD or HOLD_RUNNER. This day had no entries, exits, or near-misses. Run on a day with ENTER_BULL/ENTER_BEAR/EXIT_*/HOLD_DEV ticks to get a meaningful evaluation.

---
*Overall: 40.0% | Decision-tick: 0.0% | N=5 | Rate-limited: 3 | Parse errors: 0*
