# ELITE-tier BEAR level-rejection gate -- OOS A/B (GOAL-REPLAY-TODAY-GREEN iter 4, L1)

Generated: 2026-07-17T19:05:45.911822. Runner: `backtest/tools/elite_bear_level_reject_gate_ab.py`.
WF form: `ab_delta_per_trade_v2026_07_16` (analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md).

**Candidate:** block BEAR-side (PUT) ELITE-tier entries of ribbon_ride (BEARISH_REJECTION/BULLISH_RECLAIM) -- structural mirror of live block_elite_bull
**Control:** current production Safe config (SAFE_BASE dict, faithful to automation/state/params.json read 2026-07-17)

IS window ['2025-01-02', '2025-12-31'], OOS window ['2026-01-02', '2026-07-08'] (spy_5m_2025-01-01_2026-07-08.csv / vix_5m_2025-01-01_2026-07-08.csv).

## Per-period

| period | base pnl | n_base | n_removed | removed pnl | candidate pnl | delta |
|---|--:|--:|--:|--:|--:|--:|
| IS 2025 | $-1,348 | 119 | 6 | $533 | $-1,881 | $-533 |
| OOS 2026 YTD | $-1,553 | 86 | 11 | $-683 | $-870 | $+683 |

WF (gate-cohort norm): **-0.699** (gate-cohort-normalized (directional_gate_battery.py convention, n=affected/removed trades))

WF (full-population norm, disclosed alt): -1.774 (full-population-normalized (level_rejection_gate_sweep.py convention, n=all control trades that period))

## Gates

- `1_oos_positive`: **True**
- `2_wf_ge_070_gate_cohort_form`: **False**
- `3_sub_window_stable`: **False**
- `4_anchor_no_regression`: **True**
- `5_bh_fdr_survivor`: **True**
- `evidence_n_advisory_pass`: **False**

BH-FDR: p=0.03952, threshold=0.1, significant=True -- single-candidate BH-FDR degenerates to a plain one-sided test at alpha

## Anchor (OP-16 J_WINNERS / J_LOSERS)

- Winner days: base=$-256 candidate=$-24 (n_removed=3) -- anchor_no_regression=True
- Loser days: base=$0 candidate=$0 (n_removed=0) -- not_worsened=True

## Sub-window stability

| window | base pnl | delta | n_removed | hurt |
|---|--:|--:|--:|:--:|
| IS_H1_2025 | $-1,149 | $-0 | 5 | False |
| IS_H2_2025 | $-199 | $-533 | 1 | True |
| OOS_Q1_2026 | $340 | $-0 | 2 | False |
| OOS_Q2_2026 | $-1,321 | $+568 | 8 | False |
| OOS_Q3_2026_partial | $-572 | $+115 | 1 | False |

## Concentration check (fable-too-good hunt)

Top-5 OOS removed trades by |pnl|: [{'date': '2026-06-26', 'pnl': -336.0}, {'date': '2026-05-04', 'pnl': -232.0}, {'date': '2026-07-08', 'pnl': -115.14046355059122}, {'date': '2026-01-29', 'pnl': 0.0}, {'date': '2026-02-03', 'pnl': 0.0}]
OOS delta excluding top-3 by magnitude: $-0 (still positive: False)

## Random-removal placebo null

20 seeds, same-count random PUT removal. Null mean OOS delta=$-10.96, real candidate OOS delta=$683.14, p_null(add-one)=0.1429.
20 seeds, same-count random PUT-trade removal from the full OOS control population (any tier) -- tests whether removing ANY n_oos_removed put trades looks this good, or whether the ELITE-tier selection specifically matters.

## VERDICT: INSUFFICIENT_REGIME_SHIFT (all-5-gates=False) -- **PARK_INSUFFICIENT_REGIME_SHIFT**
