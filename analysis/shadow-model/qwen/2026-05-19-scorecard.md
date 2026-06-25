# qwen Shadow Model Scorecard — 2026-05-19

**Model:** `qwen/qwen3-next-80b-a3b-instruct:free`  
**Evaluation date:** 2026-05-19  
**Generated:** 2026-06-25T01:49:00Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 3 |
| Overall agreement | 2/3 = **66.7%** |
| Decision-tick agreement | 2/2 = **100.0%** |
| Avg latency per call | 86160ms |
| Rate-limited (429) | 1 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 18:06:21Z | `ENTER` | `HOLD` | OK | DT |
| safe | 18:20:17Z | `EXIT_STOP` | `EXIT_STOP` | OK | DT |
| safe | 10:25 | `HOLD` | `RATE_LIMITED` | XX |  |

## Disagreements

### safe 10:25  
- Real: `HOLD` (bull=8 bear=7)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream. Please 

## Verdict

**INCONCLUSIVE — rate-limited (1/3 ticks).**  
Too many RATE_LIMITED responses to assess Nemotron's capability. Try off-peak hours or add longer delays between calls.

---
*Overall: 66.7% | Decision-tick: 100.0% | N=3 | Rate-limited: 1 | Parse errors: 0*
