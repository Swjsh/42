# BOLD-SELECTIVE-FALLBACK-2026-08-02 -- iteration 3, selective qty=3 fallback

Generated 2026-08-02T01:17:56.459540. Runner: `backtest/tools/bold_selective_fallback_2026_08_02.py`.
Prereg (frozen first): `analysis\recommendations\prereg-bold-selective-fallback-2026-08-02.json` (2026-08-02T03:15:00-04:00).
Account: core_bold (Gamma-Bold-2, PA33W2KUAT40). Equity: $1,197.52. Window: 2025-01-02..2026-07-22. Gate state held fixed: block_elite_bull=True (current live).

## OVERALL VERDICT: NULL

Ship cells: NONE

## Parity guards (must hold before any cell's own numbers are trusted)

- Unsequenced union vs iter2: n=286 (expected 286) total=$+10,528.60 (expected $+10,528.60) OK=True
- Control sequential vs iter2: n=153 (expected 153) total=$+7,578.40 (expected $+7,578.40) OK=True
- Runner cohort crosscheck: n=32 (expected 32) total=$+14,539.40 (expected $+14,539.40) OK=True

## CONTROL_SEQUENTIAL (unchanged baseline, all cells compare against this)

n=153 total=$+7,578.40 WR=0.3399 recent25=$+2,841.40 drop_best_remainder=$+6,583.40

## Per-cell results (ALL cells reported, including losers)

### A_tier_bar -- tier in {SUPER, ELITE} -- NULL

| Gate | Result |
|---|---|
| G1_recent25_positive_PRIMARY | PASS |
| G2_day_majority | FAIL |
| G3_drop_best_still_positive | PASS |
| G4_pnl_not_degraded_vs_both_baselines | PASS |
| G5_runner_cohort_ZERO_TOLERANCE | FAIL |
| G6_rule6_floor_respected | PASS |
| G7_kill_switch_and_risk_cap_bind_at_both_tiers | PASS |
| G8_not_a_dead_knob_C14 | PASS |
| G9_gain_is_not_mostly_preemption | PASS |
| G10_material_fallback_fires_NEW | PASS |

- Fire counts: fallback_before_filter=130 after_filter=28 actually_placed=28
- SELECTIVE_SEQUENTIAL: n=179 total=$+10,006.20 WR=0.3575 recent25=$+1,688.70 drop_best_remainder=$+9,011.20 (still +)
- Day-majority: up=59 down=75 neutral=0 pass=False
- Runner cohort (G5): n=32 control_sum=$+14,539.40 selective_sum=$+13,493.00 missing=2 flips=0 pass=False
- Decomposition: added n=28 total=$+3,474.20 | preempted n=2 total=$+1,046.40 | gain_over_control=$+2,427.80 identity_holds=True pct_from_preemption=-43.1

### B_time_of_day_cutoff -- entry_time_et >= 12:00 ET -- NULL

| Gate | Result |
|---|---|
| G1_recent25_positive_PRIMARY | PASS |
| G2_day_majority | FAIL |
| G3_drop_best_still_positive | PASS |
| G4_pnl_not_degraded_vs_both_baselines | PASS |
| G5_runner_cohort_ZERO_TOLERANCE | FAIL |
| G6_rule6_floor_respected | PASS |
| G7_kill_switch_and_risk_cap_bind_at_both_tiers | PASS |
| G8_not_a_dead_knob_C14 | PASS |
| G9_gain_is_not_mostly_preemption | PASS |
| G10_material_fallback_fires_NEW | PASS |

- Fire counts: fallback_before_filter=130 after_filter=41 actually_placed=41
- SELECTIVE_SEQUENTIAL: n=188 total=$+10,549.40 WR=0.3457 recent25=$+3,364.30 drop_best_remainder=$+9,554.40 (still +)
- Day-majority: up=61 down=89 neutral=0 pass=False
- Runner cohort (G5): n=32 control_sum=$+14,539.40 selective_sum=$+14,007.40 missing=1 flips=0 pass=False
- Decomposition: added n=41 total=$+3,092.00 | preempted n=6 total=$+121.00 | gain_over_control=$+2,971.00 identity_holds=True pct_from_preemption=-4.1

### C_level_anchored -- has >=1 level-tied trigger -- NULL

| Gate | Result |
|---|---|
| G1_recent25_positive_PRIMARY | PASS |
| G2_day_majority | FAIL |
| G3_drop_best_still_positive | PASS |
| G4_pnl_not_degraded_vs_both_baselines | PASS |
| G5_runner_cohort_ZERO_TOLERANCE | FAIL |
| G6_rule6_floor_respected | PASS |
| G7_kill_switch_and_risk_cap_bind_at_both_tiers | PASS |
| G8_not_a_dead_knob_C14 | PASS |
| G9_gain_is_not_mostly_preemption | PASS |
| G10_material_fallback_fires_NEW | PASS |

- Fire counts: fallback_before_filter=130 after_filter=88 actually_placed=88
- SELECTIVE_SEQUENTIAL: n=233 total=$+9,264.75 WR=0.3433 recent25=$+1,416.15 drop_best_remainder=$+8,269.75 (still +)
- Day-majority: up=73 down=92 neutral=0 pass=False
- Runner cohort (G5): n=32 control_sum=$+14,539.40 selective_sum=$+13,493.00 missing=2 flips=0 pass=False
- Decomposition: added n=88 total=$+2,057.75 | preempted n=8 total=$+371.40 | gain_over_control=$+1,686.35 identity_holds=True pct_from_preemption=-22.0

---
_Source: `backtest/tools/bold_selective_fallback_2026_08_02.py`. Raw JSON: `analysis/recommendations/bold-selective-fallback-2026-08-02.json`._
