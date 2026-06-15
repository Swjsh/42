# Combination Search Leaderboard -- 2025-12-01 to 2025-12-05

**Days with data:** 5  
**Total graded hits:** 56  
**Detectors in corpus:** 9  
**Combo space size:** 3,888  
**Combos passing all gates:** 0  

**Gates:**  
- `min_n` >= 5
- `win_rate` >= 50.0%
- `min_months_active` >= 1
- `max_month_concentration` <= 0.60

> **Ranking metric:** `final_score = edge_capture_dollars * sharpe_proxy` (per OP-16). Edge-capture is the sum of signed next-bar moves; sharpe-proxy is avg/std of those moves.

## Top 20 Combos (all gates PASS)

| # | Combo | N | WR | EdgeCap $ | AvgMv $ | Sharpe | Score |
|---|-------|---|----|-----------|---------|--------|-------|
| — | _no combo passed all gates_ | | | | | | |

## Best Combo Per Detector (gates-passing only)

| Detector | Best combo | N | WR | EdgeCap $ | Score |
|----------|------------|---|----|-----------|-------|
| `double_bottom` | _no passing combo_ | — | — | — | — |
| `double_bottom_contra` | _no passing combo_ | — | — | — | — |
| `double_top` | _no passing combo_ | — | — | — | — |
| `failed_breakdown_wick` | _no passing combo_ | — | — | — | — |
| `failed_breakdown_wick_contra` | _no passing combo_ | — | — | — | — |
| `fbw_at_PDL` | _no passing combo_ | — | — | — | — |
| `momentum_acceleration` | _no passing combo_ | — | — | — | — |
| `momentum_acceleration_contra` | _no passing combo_ | — | — | — | — |
| `ral_at_PDH` | _no passing combo_ | — | — | — | — |

## Top Failing Combos (for diagnostic context)

| Combo | N | WR | EdgeCap $ | Score | Gate failures |
|-------|---|----|-----------|-------|---------------|
| momentum_acceleration | prox=NEAR_NAMED | conf=HIGH | 1 | 100.0% | +1.020 | +1.0200 | n<5, month_share>0.60 |
| momentum_acceleration | prox=NEAR_NAMED | conf=HIGH | time=AFTERNOON | 1 | 100.0% | +1.020 | +1.0200 | n<5, month_share>0.60 |
| momentum_acceleration | regime=CONTRARY | prox=NEAR_NAMED | 1 | 100.0% | +1.020 | +1.0200 | n<5, month_share>0.60 |
| momentum_acceleration | regime=CONTRARY | prox=NEAR_NAMED | time=AFTERNOON | 1 | 100.0% | +1.020 | +1.0200 | n<5, month_share>0.60 |
| momentum_acceleration | regime=CONTRARY | prox=NEAR_NAMED | conf=HIGH | 1 | 100.0% | +1.020 | +1.0200 | n<5, month_share>0.60 |

---

*Per CLAUDE.md OP-22 + OP-25: observer-only research. No production doctrine modified. Winning combos qualify for OP-21 watch-only promotion path, not direct heartbeat wiring.*