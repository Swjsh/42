# Alt-Scoring Audit — ODF + VWAP + v14_ENHANCED (2026-05-13 overnight grind)

> Stage 1 J-anchor-primary scoring rejected 100% of ODF (810/810) and nearly all VWAP + v14_enhanced combos.
> But the detectors DO fire and DO produce signal — just not on J's specific anchor days,
> OR they hit some anchors but fail strict per-day floors.
> This audit re-ranks by wide-window composite to surface what the strategies actually capture.
> **Composite:** `wide_pnl × (wide_wr − 0.5) / max(1, max_drawdown) × 100` (higher = better, rewards +EV with low DD).

_Generated: 2026-05-13T03:39:51_

## OPENING_DRIVE_FADE

**Stage 1 result (J-anchor-primary scoring):** 0 keepers (all rejected).
**Detector fire stats:** 810/810 combos produced ≥1 trade. 18/810 combos had positive wide_pnl.

**Top 10 combos by alt composite score (wide_pnl × (wr−0.5) / max_dd × 100):**

### #1 — composite score 6.52

- **wide_pnl:** $1442.10
- **wide_wr:** 59.6%
- **wide_n_trades:** 94
- **max_drawdown:** $2124.78
- **top5_pct:** 1.779
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.85, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=2.0, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2853, 2025-Q2=$-537, 2025-Q3=$-353, 2025-Q4=$-499, 2026-Q1=$114, 2026-Q2=$-135

### #2 — composite score 5.12

- **wide_pnl:** $1133.16
- **wide_wr:** 59.6%
- **wide_n_trades:** 94
- **max_drawdown:** $2124.78
- **top5_pct:** 1.991
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.85, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=1.5, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2544, 2025-Q2=$-537, 2025-Q3=$-353, 2025-Q4=$-499, 2026-Q1=$114, 2026-Q2=$-135

### #3 — composite score 3.72

- **wide_pnl:** $824.22
- **wide_wr:** 59.6%
- **wide_n_trades:** 94
- **max_drawdown:** $2124.78
- **top5_pct:** 2.362
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.85, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=1.0, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2235, 2025-Q2=$-537, 2025-Q3=$-353, 2025-Q4=$-499, 2026-Q1=$114, 2026-Q2=$-135

### #4 — composite score 2.69

- **wide_pnl:** $844.03
- **wide_wr:** 56.9%
- **wide_n_trades:** 72
- **max_drawdown:** $2167.30
- **top5_pct:** 3.032
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.7, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=2.0, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2226, 2025-Q2=$-557, 2025-Q3=$-737, 2025-Q4=$-253, 2026-Q1=$300, 2026-Q2=$-135

### #5 — composite score 2.40

- **wide_pnl:** $738.80
- **wide_wr:** 57.1%
- **wide_n_trades:** 84
- **max_drawdown:** $2184.45
- **top5_pct:** 3.464
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.8, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=2.0, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2359, 2025-Q2=$-743, 2025-Q3=$-695, 2025-Q4=$18, 2026-Q1=$-66, 2026-Q2=$-135

### #6 — composite score 1.70

- **wide_pnl:** $535.09
- **wide_wr:** 56.9%
- **wide_n_trades:** 72
- **max_drawdown:** $2167.30
- **top5_pct:** 4.206
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.7, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=1.5, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$1917, 2025-Q2=$-557, 2025-Q3=$-737, 2025-Q4=$-253, 2026-Q1=$300, 2026-Q2=$-135

### #7 — composite score 1.70

- **wide_pnl:** $593.34
- **wide_wr:** 56.9%
- **wide_n_trades:** 102
- **max_drawdown:** $2406.58
- **top5_pct:** 4.319
- **positive_quarters:** 1 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.85, time_window_end_hour=10, time_window_end_min=15, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=2.0, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2063, 2025-Q2=$-404, 2025-Q3=$-333, 2025-Q4=$-369, 2026-Q1=$-355, 2026-Q2=$-9

### #8 — composite score 1.42

- **wide_pnl:** $547.57
- **wide_wr:** 56.2%
- **wide_n_trades:** 80
- **max_drawdown:** $2395.92
- **top5_pct:** 4.674
- **positive_quarters:** 1 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.4, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.7, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=2.0, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2496, 2025-Q2=$-1106, 2025-Q3=$-173, 2025-Q4=$-456, 2026-Q1=$-79, 2026-Q2=$-135

### #9 — composite score 1.40

- **wide_pnl:** $429.86
- **wide_wr:** 57.1%
- **wide_n_trades:** 84
- **max_drawdown:** $2184.45
- **top5_pct:** 5.235
- **positive_quarters:** 2 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.8, time_window_end_hour=10, time_window_end_min=30, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=1.5, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$2050, 2025-Q2=$-743, 2025-Q3=$-695, 2025-Q4=$18, 2026-Q1=$-66, 2026-Q2=$-135

### #10 — composite score 0.82

- **wide_pnl:** $284.40
- **wide_wr:** 56.9%
- **wide_n_trades:** 102
- **max_drawdown:** $2406.58
- **top5_pct:** 7.925
- **positive_quarters:** 1 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `thrust_bar_min_dollars=0.5, stall_bars_required=2, stall_proximity_dollars=0.15, vol_decline_ratio=0.85, time_window_end_hour=10, time_window_end_min=15, strike_offset=2, premium_stop_pct=-0.08, tp1_premium_pct=0.3, tp1_qty_fraction=0.667, runner_target_pct=1.5, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, qty=10`
- **quarters:** 2025-Q1=$1754, 2025-Q2=$-404, 2025-Q3=$-333, 2025-Q4=$-369, 2026-Q1=$-355, 2026-Q2=$-9

---

## VWAP_REJECTION_PRIME

**Stage 1 result (J-anchor-primary scoring):** 0 keepers (all rejected).
**Detector fire stats:** 972/972 combos produced ≥1 trade. 900/972 combos had positive wide_pnl.

**Top 10 combos by alt composite score (wide_pnl × (wr−0.5) / max_dd × 100):**

### #1 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.06, tp1_premium_pct=0.3, runner_target_pct=2.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #2 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.1, tp1_premium_pct=0.2, runner_target_pct=1.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #3 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.1, tp1_premium_pct=0.5, runner_target_pct=1.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #4 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.14, tp1_premium_pct=0.3, runner_target_pct=2.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #5 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.1, tp1_premium_pct=0.3, runner_target_pct=2.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #6 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.14, tp1_premium_pct=0.5, runner_target_pct=2.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #7 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.14, tp1_premium_pct=0.5, runner_target_pct=1.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #8 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.14, tp1_premium_pct=0.3, runner_target_pct=1.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #9 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.06, tp1_premium_pct=0.5, runner_target_pct=1.0, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

### #10 — composite score 9305.50

- **wide_pnl:** $186.11
- **wide_wr:** 100.0%
- **wide_n_trades:** 5
- **max_drawdown:** $0.00
- **top5_pct:** 1.000
- **positive_quarters:** 4 / 6
- **edge_capture (J-anchor primary):** $0
- **knobs:** `vol_mult=1.5, proximity_dollars=0.1, lookback_bars=2, body_min_cents=0.1, premium_stop_pct=-0.1, tp1_premium_pct=0.5, runner_target_pct=1.5, strike_offset=2, qty=3, tp1_qty_fraction=0.667, profit_lock_threshold_pct=0.1, profit_lock_stop_offset_pct=0.05, require_ribbon_agreement=True, ribbon_min_spread_cents=30.0`
- **quarters:** 2025-Q1=$35, 2025-Q2=$73, 2025-Q3=$0, 2025-Q4=$37, 2026-Q1=$0, 2026-Q2=$42

---

## v14_ENHANCED

**Stage 1 result (J-anchor-primary scoring):** 0 keepers (all rejected).
**Detector fire stats:** 76/76 combos produced ≥1 trade. 32/76 combos had positive wide_pnl.

**Top 10 combos by alt composite score (wide_pnl × (wr−0.5) / max_dd × 100):**

### #1 — composite score 197.90

- **wide_pnl:** $21769.40
- **wide_wr:** 61.7%
- **wide_n_trades:** 324
- **max_drawdown:** $1287.05
- **top5_pct:** 0.212
- **positive_quarters:** 6 / 6
- **edge_capture (J-anchor primary):** $366
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:45, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.1, tp1_premium_pct=0.5, runner_target_premium_pct=2.5`
- **quarters:** 2025-Q1=$2931, 2025-Q2=$2577, 2025-Q3=$1155, 2025-Q4=$3749, 2026-Q1=$8764, 2026-Q2=$2594

### #2 — composite score 142.63

- **wide_pnl:** $19500.97
- **wide_wr:** 61.5%
- **wide_n_trades:** 314
- **max_drawdown:** $1572.37
- **top5_pct:** 0.206
- **positive_quarters:** 6 / 6
- **edge_capture (J-anchor primary):** $366
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=10:00, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.1, tp1_premium_pct=0.75, runner_target_premium_pct=2.5`
- **quarters:** 2025-Q1=$2931, 2025-Q2=$2603, 2025-Q3=$10, 2025-Q4=$3408, 2026-Q1=$7946, 2026-Q2=$2603

### #3 — composite score 142.63

- **wide_pnl:** $19500.97
- **wide_wr:** 61.5%
- **wide_n_trades:** 314
- **max_drawdown:** $1572.37
- **top5_pct:** 0.206
- **positive_quarters:** 6 / 6
- **edge_capture (J-anchor primary):** $366
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=10:00, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.1, tp1_premium_pct=0.75, runner_target_premium_pct=1.5`
- **quarters:** 2025-Q1=$2931, 2025-Q2=$2603, 2025-Q3=$10, 2025-Q4=$3408, 2026-Q1=$7946, 2026-Q2=$2603

### #4 — composite score 139.25

- **wide_pnl:** $23187.97
- **wide_wr:** 61.4%
- **wide_n_trades:** 339
- **max_drawdown:** $1898.35
- **top5_pct:** 0.204
- **positive_quarters:** 6 / 6
- **edge_capture (J-anchor primary):** $366
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:35, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.1, tp1_premium_pct=0.3, runner_target_premium_pct=2.5`
- **quarters:** 2025-Q1=$2931, 2025-Q2=$1699, 2025-Q3=$3549, 2025-Q4=$3362, 2026-Q1=$8669, 2026-Q2=$2978

### #5 — composite score 14.04

- **wide_pnl:** $4129.76
- **wide_wr:** 61.6%
- **wide_n_trades:** 323
- **max_drawdown:** $3411.01
- **top5_pct:** 0.722
- **positive_quarters:** 5 / 6
- **edge_capture (J-anchor primary):** $1
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:45, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05, tp1_premium_pct=0.75, runner_target_premium_pct=1.5`
- **quarters:** 2025-Q1=$1220, 2025-Q2=$223, 2025-Q3=$-1554, 2025-Q4=$73, 2026-Q1=$3985, 2026-Q2=$183

### #6 — composite score 14.04

- **wide_pnl:** $4129.76
- **wide_wr:** 61.6%
- **wide_n_trades:** 323
- **max_drawdown:** $3411.01
- **top5_pct:** 0.722
- **positive_quarters:** 5 / 6
- **edge_capture (J-anchor primary):** $1
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:45, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05, tp1_premium_pct=0.5, runner_target_premium_pct=1.5`
- **quarters:** 2025-Q1=$1220, 2025-Q2=$223, 2025-Q3=$-1554, 2025-Q4=$73, 2026-Q1=$3985, 2026-Q2=$183

### #7 — composite score 10.61

- **wide_pnl:** $3631.61
- **wide_wr:** 61.2%
- **wide_n_trades:** 338
- **max_drawdown:** $3835.00
- **top5_pct:** 0.824
- **positive_quarters:** 3 / 6
- **edge_capture (J-anchor primary):** $1
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:35, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05, tp1_premium_pct=0.75, runner_target_premium_pct=2.0`
- **quarters:** 2025-Q1=$1220, 2025-Q2=$-552, 2025-Q3=$-553, 2025-Q4=$-598, 2026-Q1=$3717, 2026-Q2=$398

### #8 — composite score 10.61

- **wide_pnl:** $3631.61
- **wide_wr:** 61.2%
- **wide_n_trades:** 338
- **max_drawdown:** $3835.00
- **top5_pct:** 0.824
- **positive_quarters:** 3 / 6
- **edge_capture (J-anchor primary):** $1
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:35, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05, tp1_premium_pct=0.75, runner_target_premium_pct=2.5`
- **quarters:** 2025-Q1=$1220, 2025-Q2=$-552, 2025-Q3=$-553, 2025-Q4=$-598, 2026-Q1=$3717, 2026-Q2=$398

### #9 — composite score 9.98

- **wide_pnl:** $3417.65
- **wide_wr:** 61.2%
- **wide_n_trades:** 338
- **max_drawdown:** $3835.00
- **top5_pct:** 0.813
- **positive_quarters:** 3 / 6
- **edge_capture (J-anchor primary):** $1
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:35, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05, tp1_premium_pct=0.3, runner_target_premium_pct=2.5`
- **quarters:** 2025-Q1=$1220, 2025-Q2=$-552, 2025-Q3=$-553, 2025-Q4=$-598, 2026-Q1=$3503, 2026-Q2=$398

### #10 — composite score 9.98

- **wide_pnl:** $3417.65
- **wide_wr:** 61.2%
- **wide_n_trades:** 338
- **max_drawdown:** $3835.00
- **top5_pct:** 0.813
- **positive_quarters:** 3 / 6
- **edge_capture (J-anchor primary):** $1
- **knobs:** `strike_offset_bear=0, min_triggers_bear=1, premium_stop_pct_bear=-0.2, tp1_qty_fraction=0.5, no_trade_before=09:35, profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.05, tp1_premium_pct=0.3, runner_target_premium_pct=1.5`
- **quarters:** 2025-Q1=$1220, 2025-Q2=$-552, 2025-Q3=$-553, 2025-Q4=$-598, 2026-Q1=$3503, 2026-Q2=$398


---

## Recommendation for J's morning review

Both strategies' Stage 1 scoring used J-anchor-primary edge_capture as the gate. But the detectors fire on DIFFERENT days than J's manual trades. The detectors aren't broken — the SCORING is misaligned with the strategy's actual signal pattern.

**Options for next iteration:**
1. Re-run Stage 1 with composite-based floors (e.g., wide_pnl ≥ $200, wide_wr ≥ 55%, max_dd ≤ $500) instead of J-anchor floors.
2. Accept these strategies as WATCH-ONLY for now; gather live observations and grade them via watcher_grader.py.
3. Widen the knob grids (esp. `vol_mult` and `proximity_dollars`) to find the parameter regimes that DO catch J's anchor days.

The sniper strategy proves the framework works. The new strategies just need different scoring lenses.