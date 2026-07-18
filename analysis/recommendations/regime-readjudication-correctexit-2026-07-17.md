# ITERATION 7 -- elite-bear L1 regime-conditioned re-adjudication under the CORRECT exit shape

Generated 2026-07-17T20:44:16.400562. Runner: `backtest/tools/regime_readjudication_correctexit.py`.

n_total_trades=205, n_removed(ELITE-bear PUT)=17, n_replayed=16 (n_no_local_bars=1).

## Cross-check vs exit-variant-ab.py's independently-computed control_pnl

source available: True. n_checked=16, n_match=16, n_mismatch=0.

## Before / after (SAME n, SAME trades, only the exit model changed)

| | WRONG exit (simulate_trade_real shape) | CORRECT exit (exit_manager_walk, strategies.py shape) |
|---|---|---|
| verdict | INSUFFICIENT_REGIME_SHIFT | FAIL |
| ladder_verdict | INSUFFICIENT_REGIME_SHIFT | FAIL |
| target_regime_bucket | MID_uptrend | MID_uptrend |
| n_bucket | 8 | 8 |
| regime_is_delta_mean | 0.0 | -135.03 |
| regime_oos_delta_mean | 58.0 | -40.86 |
| wf_delta | None | 0.303 |
| gates | {'1_regime_oos_positive': True, '2_wf_delta_ge_070': False, '3_sub_window_stable': True, '4_bh_fdr_survivor': False, '5_concentration_survives_ex_top3': False} | {'1_regime_oos_positive': False, '2_wf_delta_ge_070': False, '3_sub_window_stable': False, '4_bh_fdr_survivor': False, '5_concentration_survives_ex_top3': False} |
| concentration_check | {'oos_top3_dropped': [{'date': '2026-05-04', 'pnl': 232.0}, {'date': '2026-04-29', 'pnl': -0.0}, {'date': '2026-05-04', 'pnl': -0.0}], 'oos_mean_ex_top3': 0.0, 'survives_ex_top3': False} | {'oos_top3_dropped': [{'date': '2026-05-18', 'pnl': -446.45}, {'date': '2026-05-04', 'pnl': 232.0}, {'date': '2026-05-04', 'pnl': 102.0}], 'oos_mean_ex_top3': -51.0, 'survives_ex_top3': False} |

## Iteration-5's ORIGINAL result (different n -- its own independent cohort_elite_bear() call, wrong-exit shape, shown for the ledger only)

verdict=INSUFFICIENT_REGIME_SHIFT ladder=INSUFFICIENT_REGIME_SHIFT bucket=MID_downtrend n_bucket=8

**FLIP TO PASS UNDER CORRECT EXIT: False**

---
_Source: `backtest/tools/regime_readjudication_correctexit.py`. GOAL DISPOSITION lives in `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 7, not this file._
