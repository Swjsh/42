# Combination Search Leaderboard -- 2025-01-01 to 2026-05-15

**Days with data:** 319  
**Total graded hits:** 5,268  
**Detectors in corpus:** 14  
**Combo space size:** 6,048  
**Combos passing all gates:** 106  

**Gates:**  
- `min_n` >= 40
- `win_rate` >= 57.0%
- `min_months_active` >= 2
- `max_month_concentration` <= 0.60

> **Ranking metric:** `final_score = edge_capture_dollars * sharpe_proxy` (per OP-16). Edge-capture is the sum of signed next-bar moves; sharpe-proxy is avg/std of those moves.

## Top 20 Combos (all gates PASS)

| # | Combo | N | WR | EdgeCap $ | AvgMv $ | Sharpe | Score |
|---|-------|---|----|-----------|---------|--------|-------|
| 1 | momentum_acceleration | regime=ALIGNED | vix=HIGH_VOL | 47 | 59.6% | +24.455 | +0.5203 | 0.293 | +7.1658 |
| 2 | momentum_acceleration | regime=ALIGNED | prox=NOT_NEAR_NAMED | vix=HIGH_VOL | 42 | 59.5% | +22.355 | +0.5323 | 0.285 | +6.3749 |
| 3 | double_bottom | prox=NOT_NEAR_NAMED | time=MORNING | vix=LOW_VOL | 166 | 62.0% | +19.200 | +0.1157 | 0.281 | +5.3933 |
| 4 | double_bottom | regime=CONTRARY | time=MORNING | vix=LOW_VOL | 42 | 61.9% | +9.195 | +0.2189 | 0.432 | +3.9708 |
| 5 | double_bottom_contra | time=MORNING | vix=LOW_VOL | 42 | 61.9% | +9.195 | +0.2189 | 0.432 | +3.9708 |
| 6 | double_bottom_contra | regime=CONTRARY | time=MORNING | vix=LOW_VOL | 42 | 61.9% | +9.195 | +0.2189 | 0.432 | +3.9708 |
| 7 | double_bottom | time=MORNING | vix=LOW_VOL | 201 | 59.7% | +17.980 | +0.0895 | 0.210 | +3.7817 |
| 8 | momentum_acceleration | conf=HIGH | time=MORNING | 50 | 58.0% | +13.365 | +0.2673 | 0.266 | +3.5541 |
| 9 | double_bottom | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 168 | 59.5% | +14.657 | +0.0872 | 0.242 | +3.5457 |
| 10 | double_bottom | conf=HIGH | vix=LOW_VOL | 72 | 59.7% | +9.970 | +0.1385 | 0.310 | +3.0923 |
| 11 | double_bottom | prox=NOT_NEAR_NAMED | conf=HIGH | vix=LOW_VOL | 67 | 59.7% | +9.290 | +0.1387 | 0.307 | +2.8506 |
| 12 | double_bottom | regime=CONTRARY | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 54 | 64.8% | +7.840 | +0.1452 | 0.343 | +2.6855 |
| 13 | double_bottom | conf=LOW | vix=LOW_VOL | 203 | 57.6% | +14.073 | +0.0693 | 0.190 | +2.6731 |
| 14 | double_bottom | conf=HIGH | time=MORNING | vix=LOW_VOL | 44 | 61.4% | +7.360 | +0.1673 | 0.363 | +2.6689 |
| 15 | double_bottom_contra | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 43 | 67.4% | +6.970 | +0.1621 | 0.381 | +2.6578 |
| 16 | double_bottom_contra | regime=CONTRARY | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 43 | 67.4% | +6.970 | +0.1621 | 0.381 | +2.6578 |
| 17 | double_bottom | regime=CONTRARY | vix=LOW_VOL | 110 | 59.1% | +11.850 | +0.1077 | 0.221 | +2.6166 |
| 18 | double_bottom_contra | vix=LOW_VOL | 110 | 59.1% | +11.850 | +0.1077 | 0.221 | +2.6166 |
| 19 | double_bottom_contra | regime=CONTRARY | vix=LOW_VOL | 110 | 59.1% | +11.850 | +0.1077 | 0.221 | +2.6166 |
| 20 | double_bottom | regime=CONTRARY | prox=NOT_NEAR_NAMED | vix=LOW_VOL | 104 | 58.6% | +11.425 | +0.1099 | 0.227 | +2.5901 |

## Best Combo Per Detector (gates-passing only)

| Detector | Best combo | N | WR | EdgeCap $ | Score |
|----------|------------|---|----|-----------|-------|
| `double_bottom` | double_bottom | prox=NOT_NEAR_NAMED | time=MORNING | vix=LOW_VOL | 166 | 62.0% | +19.200 | +5.3933 |
| `double_bottom_contra` | double_bottom_contra | time=MORNING | vix=LOW_VOL | 42 | 61.9% | +9.195 | +3.9708 |
| `double_top` | double_top | regime=ALIGNED | prox=NOT_NEAR_NAMED | conf=LOW | vix=HIGH_VOL | 56 | 57.1% | +5.020 | +0.7402 |
| `double_top_contra` | _no passing combo_ | — | — | — | — |
| `failed_breakdown_wick` | failed_breakdown_wick | conf=MID | time=MORNING | 52 | 59.6% | +6.504 | +0.9300 |
| `failed_breakdown_wick_contra` | failed_breakdown_wick_contra | vix=LOW_VOL | 53 | 60.4% | +2.325 | +0.1680 |
| `fbw_at_PDL` | _no passing combo_ | — | — | — | — |
| `head_and_shoulders_top` | head_and_shoulders_top | prox=NOT_NEAR_NAMED | time=AFTERNOON | vix=HIGH_VOL | 70 | 57.1% | +8.175 | +1.0785 |
| `head_and_shoulders_top_contra` | _no passing combo_ | — | — | — | — |
| `momentum_acceleration` | momentum_acceleration | regime=ALIGNED | vix=HIGH_VOL | 47 | 59.6% | +24.455 | +7.1658 |
| `momentum_acceleration_contra` | momentum_acceleration_contra | time=MORNING | 49 | 59.2% | +3.664 | +0.3434 |
| `ral_at_PDH` | _no passing combo_ | — | — | — | — |
| `rejection_at_level_bearish` | _no passing combo_ | — | — | — | — |
| `rejection_at_level_bearish_contra` | _no passing combo_ | — | — | — | — |

## Top Failing Combos (for diagnostic context)

| Combo | N | WR | EdgeCap $ | Score | Gate failures |
|-------|---|----|-----------|-------|---------------|
| rejection_at_level_bearish | regime=CONTRARY | conf=HIGH | vix=HIGH_VOL | 2 | 100.0% | +15.545 | +16.4778 | n<40 |
| rejection_at_level_bearish | regime=CONTRARY | prox=NOT_NEAR_NAMED | conf=HIGH | vix=HIGH_VOL | 2 | 100.0% | +15.545 | +16.4778 | n<40 |
| rejection_at_level_bearish | conf=HIGH | time=MORNING | 1 | 100.0% | +15.105 | +15.1050 | n<40, months<2, month_share>0.60 |
| rejection_at_level_bearish | conf=HIGH | time=MORNING | vix=HIGH_VOL | 1 | 100.0% | +15.105 | +15.1050 | n<40, months<2, month_share>0.60 |
| rejection_at_level_bearish | prox=NOT_NEAR_NAMED | conf=HIGH | time=MORNING | 1 | 100.0% | +15.105 | +15.1050 | n<40, months<2, month_share>0.60 |

---

*Per CLAUDE.md OP-22 + OP-25: observer-only research. No production doctrine modified. Winning combos qualify for OP-21 watch-only promotion path, not direct heartbeat wiring.*