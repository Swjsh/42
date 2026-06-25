# hermes Shadow Model Scorecard — 2026-05-07

**Model:** `nousresearch/hermes-3-llama-3.1-405b:free`  
**Evaluation date:** 2026-05-07  
**Generated:** 2026-06-25T02:48:06Z  
**Accounts:** safe

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 5 |
| Overall agreement | 4/5 = **80.0%** |
| Decision-tick agreement | 2/2 = **100.0%** |
| Avg latency per call | 86242ms |
| Rate-limited (429) | 1 |
| Parse errors | 0 |
| Other errors | 0 |
| Vocab violations (auto-corrected) | 0 |
| Non-DT ticks skipped (--dt-only) | 2 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| safe | 10:30 | `HOLD` | `HOLD` | OK |  |
| safe | 10:33 | `HOLD_DEV` | `HOLD` | OK | DT |
| safe | 10:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| safe | 14:53 | `ERROR_TV` | `ERROR_TV` | OK |  |
| safe | 12:04 | `HOLD_DEV` | `RATE_LIMITED` | XX |  |

## Disagreements

### safe 12:04  
- Real: `HOLD_DEV` (bull=4 bear=8)
- Shadow: `RATE_LIMITED` (bull=None bear=None)
- Reason: RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', 'code': 429, 'metadata': {'raw': 'nousresearch/hermes-3-llama-3.1-405b:free is temporarily rate-limited upstream. Ple

## Verdict

**INCONCLUSIVE — rate-limited (1/5 ticks).**  
Too many RATE_LIMITED responses to assess `hermes`'s capability. Re-run with `--dt-only` to skip non-DT quota burns, or wait for rate-limit reset.

---
*Overall: 80.0% | Decision-tick: 100.0% | N=5 | Rate-limited: 1 | Parse errors: 0*
