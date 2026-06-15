# Pattern Backtest -- 2026-05-15

- bars: 156
- heartbeat decisions logged: 0
- detectors run: double_bottom, double_top, failed_breakdown_wick, rejection_at_level_bearish, momentum_acceleration, inside_bar_consolidation, head_and_shoulders_top, double_bottom_contra, double_top_contra, failed_breakdown_wick_contra, rejection_at_level_bearish_contra, momentum_acceleration_contra, head_and_shoulders_top_contra, ral_at_PDH, fbw_at_PDL
- total pattern hits: 39

## Summary by detector

| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| double_bottom | 18 | 8 | 10 | 44.4 | 0 | 0 | 0 | 18 |
| double_top | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| failed_breakdown_wick | 3 | 1 | 2 | 33.3 | 0 | 0 | 0 | 3 |
| rejection_at_level_bearish | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| momentum_acceleration | 2 | 1 | 1 | 50.0 | 0 | 0 | 0 | 2 |
| inside_bar_consolidation | 4 | 0 | 0 | n/a | 0 | 0 | 0 | 4 |
| head_and_shoulders_top | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| double_bottom_contra | 9 | 5 | 4 | 55.6 | 0 | 0 | 0 | 9 |
| double_top_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| failed_breakdown_wick_contra | 3 | 1 | 2 | 33.3 | 0 | 0 | 0 | 3 |
| rejection_at_level_bearish_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| momentum_acceleration_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| head_and_shoulders_top_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| ral_at_PDH | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| fbw_at_PDL | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |

## Hits detail

- **09:30** momentum_acceleration (bearish, conf 0.827) @ close $740.17 -- grade: **WIN** -- heartbeat: **pattern_only**
- **09:45** failed_breakdown_wick (bullish, conf 0.654) @ close $739.65 -- grade: **WIN** -- heartbeat: **pattern_only**
- **09:45** failed_breakdown_wick::contra_regime (bullish, conf 0.704) @ close $739.65 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:10** double_bottom (bullish, conf 0.45) @ close $741.12 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:10** double_bottom::contra_regime (bullish, conf 0.5) @ close $741.12 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:15** double_bottom (bullish, conf 0.6) @ close $741.99 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:15** double_bottom::contra_regime (bullish, conf 0.65) @ close $741.99 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:20** double_bottom (bullish, conf 0.6) @ close $741.89 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:20** double_bottom::contra_regime (bullish, conf 0.65) @ close $741.89 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:25** double_bottom (bullish, conf 0.45) @ close $741.13 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:25** double_bottom::contra_regime (bullish, conf 0.5) @ close $741.13 -- grade: **WIN** -- heartbeat: **pattern_only**
- **11:05** failed_breakdown_wick (bullish, conf 0.628) @ close $741.32 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **11:05** failed_breakdown_wick::contra_regime (bullish, conf 0.678) @ close $741.32 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **11:55** failed_breakdown_wick (bullish, conf 0.603) @ close $740.28 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **11:55** failed_breakdown_wick::contra_regime (bullish, conf 0.653) @ close $740.28 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:15** inside_bar_consolidation (neutral, conf 0.574) @ close $740.28 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **12:20** double_bottom (bullish, conf 0.45) @ close $741.15 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:20** double_bottom::contra_regime (bullish, conf 0.5) @ close $741.15 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:25** double_bottom (bullish, conf 0.45) @ close $741.31 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:25** double_bottom::contra_regime (bullish, conf 0.5) @ close $741.31 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:30** double_bottom (bullish, conf 0.6) @ close $741.41 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:30** double_bottom::contra_regime (bullish, conf 0.65) @ close $741.41 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:35** double_bottom (bullish, conf 0.45) @ close $741.32 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:35** double_bottom::contra_regime (bullish, conf 0.5) @ close $741.32 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:40** double_bottom (bullish, conf 0.6) @ close $741.56 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:40** double_bottom::contra_regime (bullish, conf 0.65) @ close $741.56 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **13:00** inside_bar_consolidation (neutral, conf 0.646) @ close $741.11 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **13:20** double_bottom (bullish, conf 0.55) @ close $742.49 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:25** double_bottom (bullish, conf 0.7) @ close $742.52 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:30** double_bottom (bullish, conf 0.7) @ close $742.82 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **13:35** double_bottom (bullish, conf 0.7) @ close $742.63 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **13:40** double_bottom (bullish, conf 0.55) @ close $742.43 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **13:55** double_bottom (bullish, conf 0.7) @ close $742.96 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:00** double_bottom (bullish, conf 0.7) @ close $743.11 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **14:05** double_bottom (bullish, conf 0.7) @ close $743.03 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **14:10** double_bottom (bullish, conf 0.7) @ close $743.01 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **14:40** inside_bar_consolidation (neutral, conf 0.639) @ close $741.39 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **14:45** inside_bar_consolidation (neutral, conf 0.563) @ close $741.25 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **15:50** momentum_acceleration (bearish, conf 0.711) @ close $738.94 -- grade: **LOSS** -- heartbeat: **pattern_only**