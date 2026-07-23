# CLASS-CONDITIONAL EXITS -- 2026-07-23

Generated 2026-07-22T21:50:00.257347. Runner: `backtest/tools/class_conditional_exits_ab.py`. Pre-reg: `analysis/kitchen/prereg-class-conditional-exits-2026-07-23.json`.

Preflight: {'hash_ok': True, 'n_ok': True, 'mechanism_ok': True, 'n_trendline': 124, 'n_trendline_with_trigger_level': 0, 'n_non_trendline': 66, 'n_non_trendline_with_trigger_level': 66}

Control reconciliation vs source replay: 0 mismatches / 190 trades (max |delta| $0.00).

Population: {'n_total': 190, 'n_replayed': 190, 'n_no_opra_excluded': 0, 'n_no_spy_day_excluded': 0, 'n_tuning': 135, 'n_heldout': 55}

## Cells (13, frozen grid)

| cell_id | group | n_real_fills | total_pnl (delta) | day_wr | ex_top3 | held_out | p_raw | q(BH-13) | gates | verdict |
|---|---|--:|--:|--:|--:|--:|--:|--:|:--:|:--:|
| A1_T-CTRL_TR-CTRL | A-tier | 0 | $+0.00 | 0% | $+0.00 | $+0.00 | 1.0 | 1.0 | 0/4 | **CONTROL_HOLDS** |
| A2_T-TIGHT_TR-CTRL | A-tier | 73 | $+1,423.02 | 55% | $+1,075.74 | $-125.00 | 0.04392 | 0.11418 | 3/4 | **CONTROL_HOLDS** |
| A3_T-LOOSE_TR-CTRL | A-tier | 67 | $-640.60 | 4% | $-2,320.50 | $+353.25 | 0.71712 | 0.84751 | 1/4 | **CONTROL_HOLDS** |
| A4_T-CTRL_TR-TIGHT | A-tier | 23 | $+306.60 | 21% | $+217.40 | $+253.85 | 0.00737 | 0.03195 | 3/4 | **CONTROL_HOLDS** |
| A5_T-CTRL_TR-WIDE | A-tier | 23 | $-176.30 | 5% | $-726.75 | $-509.50 | 0.67087 | 0.84751 | 0/4 | **CONTROL_HOLDS** |
| A6_T-TIGHT_TR-TIGHT | A-tier | 95 | $+1,718.72 | 67% | $+1,371.44 | $+100.45 | 0.02029 | 0.06595 | 4/4 | **SHIP** |
| A7_T-TIGHT_TR-WIDE | A-tier | 95 | $+1,268.52 | 55% | $+561.36 | $-577.70 | 0.08527 | 0.18475 | 3/4 | **CONTROL_HOLDS** |
| A8_T-LOOSE_TR-TIGHT | A-tier | 90 | $-343.30 | 18% | $-2,001.30 | $+563.75 | 0.62088 | 0.84751 | 1/4 | **CONTROL_HOLDS** |
| A9_T-LOOSE_TR-WIDE | A-tier | 90 | $-891.25 | 8% | $-2,522.00 | $-244.15 | 0.78421 | 0.84956 | 0/4 | **CONTROL_HOLDS** |
| B1_PRIORCHOP-TIGHT | B-daylag | 24 | $+737.64 | 17% | $+558.12 | $-40.58 | 1e-05 | 0.00011 | 2/4 | **CONTROL_HOLDS** |
| B2_PRIOROTHER-WIDE | B-daylag | 20 | $-60.90 | 5% | $-611.35 | $-422.70 | 0.56178 | 0.84751 | 0/4 | **CONTROL_HOLDS** |
| C1_DIAG-CHOP-TIGHT | C-diagnostic-noncausal | 17 | $+420.56 | 14% | $+278.36 | $+275.72 | 0.00048 | 0.00313 | 3/4 | **NOT_GATE_ELIGIBLE_NONCAUSAL_DIAGNOSTIC** |
| C2_DIAG-NONCHOP-WIDE | C-diagnostic-noncausal | 21 | $-96.10 | 5% | $-646.55 | $-459.90 | 0.59626 | 0.84751 | 0/4 | **NOT_GATE_ELIGIBLE_NONCAUSAL_DIAGNOSTIC** |
