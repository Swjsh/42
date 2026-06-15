# Pattern Backtest -- 2026-05-19

- bars: 156
- heartbeat decisions logged: 1
- detectors run: double_bottom, double_top, failed_breakdown_wick, rejection_at_level_bearish, momentum_acceleration, inside_bar_consolidation, head_and_shoulders_top, double_bottom_contra, double_top_contra, failed_breakdown_wick_contra, rejection_at_level_bearish_contra, momentum_acceleration_contra, head_and_shoulders_top_contra, ral_at_ActR_741.40, ral_at_RefR_738.86, ral_at_CarR_738.10, fbw_at_ActS_735.40
- total pattern hits: 34

## Summary by detector

| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| double_bottom | 14 | 11 | 3 | 78.6 | 0 | 0 | 0 | 14 |
| double_top | 11 | 5 | 6 | 45.5 | 0 | 0 | 1 | 10 |
| failed_breakdown_wick | 3 | 1 | 1 | 50.0 | 0 | 0 | 0 | 3 |
| rejection_at_level_bearish | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| momentum_acceleration | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| inside_bar_consolidation | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| head_and_shoulders_top | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| double_bottom_contra | 1 | 1 | 0 | 100.0 | 0 | 0 | 0 | 1 |
| double_top_contra | 2 | 1 | 1 | 50.0 | 0 | 0 | 0 | 2 |
| failed_breakdown_wick_contra | 3 | 1 | 1 | 50.0 | 0 | 0 | 0 | 3 |
| rejection_at_level_bearish_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| momentum_acceleration_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| head_and_shoulders_top_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| ral_at_ActR_741.40 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| ral_at_RefR_738.86 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| ral_at_CarR_738.10 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| fbw_at_ActS_735.40 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |

## Hits detail

- **09:30** double_top (bearish, conf 0.661) @ close $734.51 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **09:35** failed_breakdown_wick (bullish, conf 0.64) @ close $735.40 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **09:35** failed_breakdown_wick::contra_regime (bullish, conf 0.69) @ close $735.40 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **09:45** failed_breakdown_wick (bullish, conf 0.624) @ close $734.59 -- grade: **WIN** -- heartbeat: **pattern_only**
- **09:45** failed_breakdown_wick::contra_regime (bullish, conf 0.674) @ close $734.59 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:10** double_top (bearish, conf 0.608) @ close $732.92 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:15** double_top (bearish, conf 0.623) @ close $732.53 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:20** double_top (bearish, conf 0.616) @ close $732.72 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:25** double_top (bearish, conf 0.628) @ close $732.42 -- grade: **WIN** -- heartbeat: **HEARTBEAT_MISS**
- **10:30** double_top (bearish, conf 0.634) @ close $732.27 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:20** double_bottom (bullish, conf 0.55) @ close $734.07 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:20** double_bottom::contra_regime (bullish, conf 0.6) @ close $734.07 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:25** double_bottom (bullish, conf 0.55) @ close $734.49 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:30** double_bottom (bullish, conf 0.7) @ close $734.85 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:35** double_bottom (bullish, conf 0.7) @ close $735.05 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:40** double_bottom (bullish, conf 0.7) @ close $735.44 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:45** double_bottom (bullish, conf 0.7) @ close $735.50 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:50** double_bottom (bullish, conf 0.7) @ close $736.02 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:55** double_bottom (bullish, conf 0.7) @ close $736.12 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:00** double_bottom (bullish, conf 0.7) @ close $736.63 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **13:05** double_bottom (bullish, conf 0.7) @ close $736.62 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:10** double_bottom (bullish, conf 0.7) @ close $736.88 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:15** double_bottom (bullish, conf 0.7) @ close $737.28 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:20** double_bottom (bullish, conf 0.7) @ close $737.50 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **13:25** double_bottom (bullish, conf 0.7) @ close $736.98 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **14:50** double_top (bearish, conf 0.6) @ close $734.89 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:55** double_top (bearish, conf 0.618) @ close $734.45 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:00** double_top (bearish, conf 0.614) @ close $734.56 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:05** double_top (bearish, conf 0.586) @ close $735.24 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:05** double_top::contra_regime (bearish, conf 0.636) @ close $735.24 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:15** double_top (bearish, conf 0.582) @ close $735.34 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:15** double_top::contra_regime (bearish, conf 0.632) @ close $735.34 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:55** failed_breakdown_wick (bullish, conf 0.7) @ close $733.79 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **15:55** failed_breakdown_wick::contra_regime (bullish, conf 0.75) @ close $733.79 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**