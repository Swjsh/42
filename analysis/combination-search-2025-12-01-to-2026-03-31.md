# Combination Search Leaderboard -- 2025-12-01 to 2026-03-31

**Days with data:** 79  
**Total graded hits:** 1,256  
**Detectors in corpus:** 13  
**Combo space size:** 5,616  
**Combos passing all gates:** 94  

**Gates:**  
- `min_n` >= 20
- `win_rate` >= 55.0%
- `min_months_active` >= 2
- `max_month_concentration` <= 0.60

> **Ranking metric:** `final_score = edge_capture_dollars * sharpe_proxy` (per OP-16). Edge-capture is the sum of signed next-bar moves; sharpe-proxy is avg/std of those moves.

## Top 20 Combos (all gates PASS)

| # | Combo | N | WR | EdgeCap $ | AvgMv $ | Sharpe | Score |
|---|-------|---|----|-----------|---------|--------|-------|
| 1 | momentum_acceleration | prox=NOT_NEAR_NAMED | time=AFTERNOON | 21 | 66.7% | +12.485 | +0.5945 | 0.722 | +9.0116 |
| 2 | momentum_acceleration | regime=ALIGNED | time=AFTERNOON | 21 | 61.9% | +12.360 | +0.5886 | 0.670 | +8.2759 |
| 3 | momentum_acceleration | time=AFTERNOON | 27 | 63.0% | +13.430 | +0.4974 | 0.610 | +8.1903 |
| 4 | momentum_acceleration | 100 | 56.0% | +23.395 | +0.2339 | 0.318 | +7.4426 |
| 5 | momentum_acceleration | prox=NOT_NEAR_NAMED | conf=MID | 34 | 61.8% | +12.615 | +0.3710 | 0.450 | +5.6790 |
| 6 | momentum_acceleration | conf=MID | 42 | 57.1% | +13.310 | +0.3169 | 0.406 | +5.4016 |
| 7 | momentum_acceleration | regime=ALIGNED | prox=NOT_NEAR_NAMED | conf=MID | 23 | 56.5% | +9.945 | +0.4324 | 0.463 | +4.6056 |
| 8 | failed_breakdown_wick | conf=LOW | time=AFTERNOON | 26 | 65.4% | +7.840 | +0.3015 | 0.497 | +3.8978 |
| 9 | rejection_at_level_bearish | prox=NOT_NEAR_NAMED | 43 | 67.4% | +9.748 | +0.2267 | 0.394 | +3.8379 |
| 10 | failed_breakdown_wick | regime=ALIGNED | 20 | 70.0% | +7.122 | +0.3561 | 0.459 | +3.2683 |
| 11 | double_bottom | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 43 | 65.1% | +6.940 | +0.1614 | 0.407 | +2.8236 |
| 12 | failed_breakdown_wick | prox=NOT_NEAR_NAMED | conf=LOW | time=AFTERNOON | 20 | 70.0% | +5.910 | +0.2955 | 0.476 | +2.8163 |
| 13 | double_bottom | prox=NOT_NEAR_NAMED | conf=LOW | time=AFTERNOON | vix=LOW_VOL | 35 | 68.6% | +6.385 | +0.1824 | 0.438 | +2.7974 |
| 14 | rejection_at_level_bearish | prox=NOT_NEAR_NAMED | time=MORNING | 22 | 72.7% | +5.283 | +0.2401 | 0.435 | +2.2986 |
| 15 | failed_breakdown_wick | conf=LOW | vix=HIGH_VOL | 21 | 61.9% | +6.350 | +0.3024 | 0.357 | +2.2660 |
| 16 | double_bottom | conf=LOW | vix=LOW_VOL | 51 | 60.8% | +6.560 | +0.1286 | 0.324 | +2.1256 |
| 17 | rejection_at_level_bearish | regime=ALIGNED | prox=NOT_NEAR_NAMED | 27 | 70.4% | +5.503 | +0.2038 | 0.379 | +2.0839 |
| 18 | rejection_at_level_bearish | vix=LOW_VOL | 22 | 59.1% | +5.175 | +0.2352 | 0.389 | +2.0106 |
| 19 | rejection_at_level_bearish | prox=NOT_NEAR_NAMED | time=AFTERNOON | 21 | 61.9% | +4.465 | +0.2126 | 0.355 | +1.5836 |
| 20 | failed_breakdown_wick | 76 | 55.3% | +9.599 | +0.1263 | 0.164 | +1.5716 |

## Best Combo Per Detector (gates-passing only)

| Detector | Best combo | N | WR | EdgeCap $ | Score |
|----------|------------|---|----|-----------|-------|
| `double_bottom` | double_bottom | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 43 | 65.1% | +6.940 | +2.8236 |
| `double_bottom_contra` | double_bottom_contra | conf=MID | time=AFTERNOON | vix=HIGH_VOL | 27 | 59.3% | +3.317 | +0.7065 |
| `double_top` | double_top | conf=MID | time=MORNING | 68 | 55.9% | +6.395 | +0.7137 |
| `double_top_contra` | _no passing combo_ | — | — | — | — |
| `failed_breakdown_wick` | failed_breakdown_wick | conf=LOW | time=AFTERNOON | 26 | 65.4% | +7.840 | +3.8978 |
| `failed_breakdown_wick_contra` | failed_breakdown_wick_contra | prox=NOT_NEAR_NAMED | time=AFTERNOON | 27 | 55.6% | +2.440 | +0.4189 |
| `fbw_at_PDL` | _no passing combo_ | — | — | — | — |
| `head_and_shoulders_top` | head_and_shoulders_top | prox=NOT_NEAR_NAMED | vix=HIGH_VOL | 50 | 60.0% | +4.750 | +0.6510 |
| `momentum_acceleration` | momentum_acceleration | prox=NOT_NEAR_NAMED | time=AFTERNOON | 21 | 66.7% | +12.485 | +9.0116 |
| `momentum_acceleration_contra` | momentum_acceleration_contra | 34 | 58.8% | +3.020 | +0.3700 |
| `ral_at_PDH` | _no passing combo_ | — | — | — | — |
| `rejection_at_level_bearish` | rejection_at_level_bearish | prox=NOT_NEAR_NAMED | 43 | 67.4% | +9.748 | +3.8379 |
| `rejection_at_level_bearish_contra` | _no passing combo_ | — | — | — | — |

## Top Failing Combos (for diagnostic context)

| Combo | N | WR | EdgeCap $ | Score | Gate failures |
|-------|---|----|-----------|-------|---------------|
| rejection_at_level_bearish | regime=CONTRARY | prox=NOT_NEAR_NAMED | conf=LOW | vix=LOW_VOL | 2 | 100.0% | +2.770 | +255.7633 | n<20 |
| failed_breakdown_wick_contra | conf=HIGH | time=MORNING | vix=HIGH_VOL | 3 | 100.0% | +2.810 | +76.8899 | n<20, month_share>0.60 |
| failed_breakdown_wick_contra | regime=CONTRARY | conf=HIGH | time=MORNING | vix=HIGH_VOL | 3 | 100.0% | +2.810 | +76.8899 | n<20, month_share>0.60 |
| failed_breakdown_wick_contra | prox=NOT_NEAR_NAMED | conf=LOW | time=AFTERNOON | vix=HIGH_VOL | 2 | 100.0% | +2.225 | +52.1118 | n<20, months<2, month_share>0.60 |
| failed_breakdown_wick_contra | regime=CONTRARY | prox=NOT_NEAR_NAMED | conf=LOW | time=AFTERNOON | vix=HIGH_VOL | 2 | 100.0% | +2.225 | +52.1118 | n<20, months<2, month_share>0.60 |

---

*Per CLAUDE.md OP-22 + OP-25: observer-only research. No production doctrine modified. Winning combos qualify for OP-21 watch-only promotion path, not direct heartbeat wiring.*