# Exit-quality A/B -- exit_wider_trail_25 (GOAL-REPLAY-TODAY-GREEN iteration 6, step 3)

Generated 2026-07-17T20:27:32.695173. Runner: `backtest/tools/exit_variant_ab.py`.

**Control shape:** `{'premium_stop_pct': -0.2, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'runner_target_pct': 99.0, 'trail_pct': 0.15, 'profit_lock_arm_pct': 0.05, 'stop_mode': 'structure', 'catastrophe_stop_pct': -0.5, 'profit_lock_arm_scope': 'post_tp1'}`

**Candidate shape:** `{'premium_stop_pct': -0.2, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'runner_target_pct': 99.0, 'trail_pct': 0.25, 'profit_lock_arm_pct': 0.05, 'stop_mode': 'structure', 'catastrophe_stop_pct': -0.5, 'profit_lock_arm_scope': 'post_tp1'}`

Window ['2025-01-02', '2026-07-08'], n_ribbon_ride_trades=188, n_replayed=188, cache_misses=0.

## Full-population result

| control total | candidate total | delta |
|--:|--:|--:|
| $5,547.70 | $4,734.40 | $-813.30 |

## Calendar WF disclosure (cross-check only)

{'is_2025_delta': -12.2, 'n_is': 110, 'oos_2026_delta': -801.1, 'n_oos': 78, 'wf_gate_cohort_normalized': 92.603, 'note': "cross-check only, calendar-year split -- the ladder decision uses the regime-conditioned result below (iteration 5's earned methodology)"}

## Regime-conditioned validation (the earned methodology, iteration 5)

Target bucket: **MID_uptrend** (n_bucket=115, concentration=61.2%)

regime-IS delta_mean=$1.51/tr (n=57) -> regime-OOS delta_mean=$-5.05/tr (n=58), WF=-3.34

| gate | result |
|---|:--:|
| 1_regime_oos_positive | False |
| 2_wf_delta_ge_070 | False |
| 3_sub_window_stable | False |
| 4_bh_fdr_survivor | False |
| 5_concentration_survives_ex_top3 | False |

**Ladder verdict: FAIL. Overall: FAIL.**

## Concentration check (fable-too-good hunt)

{'top3_dropped': [{'date': '2025-09-25', 'pnl': 250.0}, {'date': '2025-12-11', 'pnl': 231.8}, {'date': '2025-08-22', 'pnl': -74.7}], 'delta_ex_top3': -1220.4, 'survives_ex_top3': False}

## OP-16 anchor cross-check (disclosure only)

{'j_winners_delta': -20.6, 'j_losers_delta': -28.4, 'note': "delta = candidate-minus-control on ribbon_ride trades landing on J's OP-16 anchor dates -- disclosure only, not a formal gate here (regime validator already ran its own gates)"}

## Disclosed limitations

See module docstring: ribbon_flip_back OFF for this population, TRENDLINE-tier entries fall back to the shape's premium floor rather than a historical key-level lookup, qty is backtest-sizing not live-sizing.

---
_Source: `backtest/tools/exit_variant_ab.py`. SHIP DECISION lives in `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 6, not this file._
