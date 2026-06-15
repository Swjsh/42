# Autoresearch Watchdog Report — 🔴 ATTENTION NEEDED

_Generated: 2026-05-09T13:15:26Z_

**Total iterations:** 226  ·  **KEEPs:** 7  ·  **Keep rate:** 3.1%

## Issues flagged
- ⚠ [strict] 0 KEEPs in last 10 iterations — possible gate or search-space issue
- ⚠ [strict] 3 REVERTs had val sharpe > 1.0 and pnl > $200 — hard gates may be too strict
- ⚠ [balanced] 0 KEEPs in last 10 iterations — possible gate or search-space issue
- ⚠ [balanced] 0 KEEPs across all 41 iterations — STUCK; review hard gates
- ⚠ [balanced] 3 REVERTs had val sharpe > 1.0 and pnl > $200 — hard gates may be too strict
- ⚠ [aggressive] 0 KEEPs in last 10 iterations — possible gate or search-space issue
- ⚠ [aggressive] 3 REVERTs had val sharpe > 1.0 and pnl > $200 — hard gates may be too strict

## STRICT
- iter=70, kept=2, reverted=68 (keep rate 3%)
- last batch: 0 KEEP / 10 REVERT
- VALIDATE baseline: 4 trades, 50% WR, $109 P&L, sharpe 5.55, W/L 2.44x

**Top KEEPs:**
| iter | change | Δ sharpe | Δ P&L | val sharpe | val WR |
|------|--------|----------|-------|-----------|--------|
| 1 | `f9_vol_mult: 1.0 -> 1.2` | +1.15 | $+307 | 5.55 | 50% |
| 10 | `confluence_tolerance_dollars: 0.2 -> 0.15` | +0.84 | $+180 | 5.55 | 50% |

**Notable REVERTs (good val metrics, rejected anyway):**
- iter 32: `tp1_qty_fraction+premium_stop_pct_bull -> [1.0, -0.08]` | val P&L $433, sharpe 5.02, WR 30% | rejected: hard gate failure: max_dd regression: baseline=-284 candidate=-959 (limit=-497)
- iter 21: `tp1_qty_fraction+level_proximity_dollars -> [1.0, 0.3]` | val P&L $408, sharpe 4.65, WR 30% | rejected: hard gate failure: max_dd regression: baseline=-284 candidate=-1088 (limit=-497)
- iter 25: `tp1_qty_fraction -> 1.0` | val P&L $408, sharpe 4.65, WR 30% | rejected: hard gate failure: max_dd regression: baseline=-284 candidate=-1088 (limit=-497)

**Params that drifted from starting point:**
- `f9_vol_mult`: 1.0 -> 1.2
- `premium_stop_pct`: None -> -0.06
- `strike_offset`: None -> -2
- `min_triggers`: None -> 2
- `vix_rising_deadband`: None -> 0.08
- `level_proximity_dollars`: 0.5 -> 0.4
- `confluence_tolerance_dollars`: 0.3 -> 0.15
- `ribbon_flip_lookback_bars`: 3 -> 2
- `min_triggers_bear`: 2 -> 1
- `min_triggers_bull`: 3 -> 2
- `premium_stop_pct_bear`: -0.06 -> -0.08
- `premium_stop_pct_bull`: -0.08 -> -0.1
- `tp1_premium_pct`: 0.25 -> 0.3
- `runner_target_premium_pct`: 2.0 -> 3.0

**Dead-end params (tried >= 4x, 0 KEEPs):** `ribbon_spread_min_cents`, `min_triggers_bear`, `no_trade_window_end`, `premium_stop_pct_bear`, `min_triggers_bull`, `no_trade_window_start`, `premium_stop_pct_bull`, `tp1_premium_pct`, `tp1_qty_fraction`, `runner_target_premium_pct`

**Mode issues:**
- 0 KEEPs in last 10 iterations — possible gate or search-space issue
- 3 REVERTs had val sharpe > 1.0 and pnl > $200 — hard gates may be too strict

## BALANCED
- iter=41, kept=0, reverted=41 (keep rate 0%)
- last batch: 0 KEEP / 10 REVERT
- VALIDATE baseline: 59 trades, 24% WR, $-57 P&L, sharpe -0.24, W/L 3.10x

**Notable REVERTs (good val metrics, rejected anyway):**
- iter 10: `confluence_tolerance_dollars -> 0.4` | val P&L $482, sharpe 1.75, WR 25% | rejected: hard gate failure: win_rate<40% (got 14%)
- iter 14: `confluence_tolerance_dollars -> 0.4` | val P&L $482, sharpe 1.75, WR 25% | rejected: hard gate failure: win_rate<40% (got 14%)
- iter 13: `no_trade_before -> 09:45` | val P&L $315, sharpe 1.21, WR 27% | rejected: hard gate failure: win_rate<40% (got 15%)

**Params that drifted from starting point:**
- `premium_stop_pct`: None -> -0.08
- `strike_offset`: None -> -2
- `min_triggers`: None -> 1
- `vix_rising_deadband`: None -> 0.05

**Dead-end params (tried >= 4x, 0 KEEPs):** `f9_vol_mult`, `ribbon_spread_min_cents`, `level_proximity_dollars`

**Mode issues:**
- 0 KEEPs in last 10 iterations — possible gate or search-space issue
- 0 KEEPs across all 41 iterations — STUCK; review hard gates
- 3 REVERTs had val sharpe > 1.0 and pnl > $200 — hard gates may be too strict

## AGGRESSIVE
- iter=115, kept=5, reverted=110 (keep rate 4%)
- last batch: 0 KEEP / 10 REVERT
- VALIDATE baseline: 93 trades, 35% WR, $1882 P&L, sharpe 3.77, W/L 2.70x

**Top KEEPs:**
| iter | change | Δ sharpe | Δ P&L | val sharpe | val WR |
|------|--------|----------|-------|-----------|--------|
| 17 | `no_trade_before: 09:35 -> 09:45` | +0.05 | $+124 | 3.61 | 33% |
| 21 | `vix_bear_threshold: 16.0 -> 16.5` | +0.03 | $+57 | 3.61 | 33% |
| 22 | `vix_rising_deadband: 0.02 -> 0.05` | +0.02 | $+27 | 3.77 | 35% |
| 16 | `no_trade_window_start: None -> 12:30` | +0.00 | $+0 | 2.80 | 31% |
| 23 | `strike_offset: -1 -> 0` | +0.00 | $+0 | 3.77 | 35% |

**Notable REVERTs (good val metrics, rejected anyway):**
- iter 20: `ribbon_spread_min_cents -> 15` | val P&L $2089, sharpe 3.65, WR 33% | rejected: sharpe did not improve (-0.013)
- iter 19: `strike_offset -> -2` | val P&L $2047, sharpe 3.61, WR 33% | rejected: sharpe did not improve (-0.000)
- iter 24: `ribbon_spread_min_cents -> 25` | val P&L $2045, sharpe 4.03, WR 36% | rejected: sharpe did not improve (-0.612)

**Params that drifted from starting point:**
- `premium_stop_pct`: None -> -0.15
- `strike_offset`: None -> 0
- `min_triggers`: None -> 1
- `vix_bear_threshold`: 16.0 -> 16.5
- `vix_rising_deadband`: None -> 0.05
- `confluence_tolerance_dollars`: 0.3 -> 0.4
- `ribbon_flip_lookback_bars`: 3 -> 5
- `no_trade_before`: 09:35 -> 09:45
- `no_trade_window_start`: None -> 12:30
- `premium_stop_pct_bear`: -0.15 -> -0.08
- `premium_stop_pct_bull`: -0.2 -> -0.1
- `tp1_premium_pct`: 0.4 -> 0.3
- `tp1_qty_fraction`: 0.333 -> 0.667
- `runner_target_premium_pct`: 5.0 -> 3.0

**Dead-end params (tried >= 4x, 0 KEEPs):** `f9_vol_mult`, `ribbon_spread_min_cents`, `level_proximity_dollars`, `confluence_tolerance_dollars`, `ribbon_flip_lookback_bars`, `no_trade_window_end`, `runner_target_premium_pct`, `time_stop_minutes_before_close`, `strike_offset_bull`, `strike_offset_bear`, `tp1_qty_fraction`, `premium_stop_pct_bull`, `min_triggers_bull`, `premium_stop_pct_bear`, `min_triggers_bear`, `tp1_premium_pct`, `vix_bear_rising_deadband`

**Mode issues:**
- 0 KEEPs in last 10 iterations — possible gate or search-space issue
- 3 REVERTs had val sharpe > 1.0 and pnl > $200 — hard gates may be too strict
