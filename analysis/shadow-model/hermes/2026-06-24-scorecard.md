# hermes Shadow Model Scorecard — 2026-06-24

**Model:** `nousresearch/hermes-3-llama-3.1-405b:free`  
**Evaluation date:** 2026-06-24  
**Generated:** 2026-06-25T03:23:09Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 8 |
| Overall agreement | 3/8 = **37.5%** |
| Decision-tick agreement | 2/2 = **100.0%** |
| Avg latency per call | 177128ms |
| Rate-limited (429) | 5 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |
| Non-DT ticks skipped (--dt-only) | 1 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 14:03 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |
| safe | 14:13 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |
| safe | 14:15 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |
| safe | 14:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:33 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |
| safe | 14:36 | `HOLD` | `HOLD` | OK |  |
| safe | 14:39 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:55 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |

## Disagreements

### safe 14:03  
- Real: `HOLD_DEV` (bull=4 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'nousresearch/hermes-3-llama-3.1-405b:free is temporarily rate-limited upstream. Ple

### safe 14:13  
- Real: `HOLD_DEV` (bull=4 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'nousresearch/hermes-3-llama-3.1-405b:free is temporarily rate-limited upstream. Ple

### safe 14:15  
- Real: `HOLD_DEV` (bull=4 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'nousresearch/hermes-3-llama-3.1-405b:free is temporarily rate-limited upstream. Ple

### safe 14:33  
- Real: `HOLD_DEV` (bull=4 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'nousresearch/hermes-3-llama-3.1-405b:free is temporarily rate-limited upstream. Ple

### safe 14:55  
- Real: `HOLD_DEV` (bull=6 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'nousresearch/hermes-3-llama-3.1-405b:free is temporarily rate-limited upstream. Ple

## Verdict

**INCONCLUSIVE — rate-limited (5/8 ticks).**  
Too many RATE_LIMITED responses to assess `hermes`'s capability. Re-run with `--dt-only` to skip non-DT quota burns, or wait for rate-limit reset.

---
*Overall: 37.5% | Decision-tick: 100.0% | N=8 | Rate-limited: 5 | Parse errors: 0*
