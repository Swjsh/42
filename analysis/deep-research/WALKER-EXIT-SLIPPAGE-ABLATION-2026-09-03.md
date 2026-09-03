# WALKER-EXIT-SLIPPAGE-ABLATION -- 2026-09-03

RESEARCH -- decides nothing, arms nothing, ships nothing. Full pre-registration in `backtest/tools/exit_slippage_ablation_research.py`'s module docstring, written before this script ran.

live setting: SKIPPED. analysis/pain-ledger/latency.json carries no dollar-denominated exit-slippage field -- it measures pipeline TIME latency in seconds (bar_close_ts_to_core_verdict_ts_s, etc.), scoped to ENTRY fills only, on arms safe-3/risky-1/risky-3 (not safe-2/bold-2, the PDT anchor's own arms). Skipped, not guessed at.

## 3x2 table (setting x anchor)

| setting | anchor | n | ratio | median $ | sign % |
|---|---|---|---|---|---|
| default | PDT (1min) | 41 | 2.0128 | 15.0 | 97.6% |
| default | V9 (121-pop) | 121 | 0.6452 | 15.0 | 89.3% |
| zero | PDT (1min) | 41 | 1.7163 | 15.0 | 97.6% |
| zero | V9 (121-pop) | 121 | 0.8181 | 15.0 | 90.1% |
| live | both | -- | SKIPPED | -- | -- |

## PDT agree-rows-only subset

| setting | n agree rows | ratio | median $ |
|---|---|---|---|
| default | 36 | 1.9842 | 15.0 |
| zero | 36 | 1.5277 | 15.0 |

## PDT split by recorded stop_mode (default slippage only)

| stop_mode | n | ratio | median $ |
|---|---|---|---|
| premium | 20 | 1.6102 | 29.4 |
| structure_or_other | 21 | 1.1063 | 6.0 |

## Conclusion

Slippage is a REAL but PARTIAL contributor -- both anchors move toward 1.0 when zeroed (PDT 2.0128->1.7163, V9 0.6452->0.8181), yet the PASS/FAIL verdict does not flip (pdt_still_fails_at_zero=True) because the premium_stop bucket (20/41 rows, ratio 1.6102 -- a stage exit_slippage structurally NEVER touches) is biased on its own: the residual is population composition/small-n (n=41, premium_stop-heavy, loss-skewed), not the slippage asymmetry alone.

(pdt_moved_toward_one_at_zero_slippage=True, v9_moved_toward_one_at_zero_slippage=True)
