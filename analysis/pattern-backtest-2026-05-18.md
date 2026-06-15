# Pattern Backtest -- 2026-05-18

- bars: 156
- heartbeat decisions logged: 1
- detectors run: double_bottom, double_top, failed_breakdown_wick, rejection_at_level_bearish, momentum_acceleration, inside_bar_consolidation, head_and_shoulders_top, double_bottom_contra, double_top_contra, failed_breakdown_wick_contra, rejection_at_level_bearish_contra, momentum_acceleration_contra, head_and_shoulders_top_contra
- total pattern hits: 39

## Summary by detector

| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| double_bottom | 11 | 4 | 7 | 36.4 | 0 | 0 | 0 | 11 |
| double_top | 6 | 1 | 5 | 16.7 | 0 | 0 | 0 | 6 |
| failed_breakdown_wick | 4 | 4 | 0 | 100.0 | 0 | 0 | 0 | 4 |
| rejection_at_level_bearish | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| momentum_acceleration | 2 | 0 | 2 | 0.0 | 0 | 0 | 0 | 2 |
| inside_bar_consolidation | 4 | 0 | 0 | n/a | 0 | 0 | 0 | 4 |
| head_and_shoulders_top | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| double_bottom_contra | 8 | 4 | 4 | 50.0 | 0 | 0 | 0 | 8 |
| double_top_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| failed_breakdown_wick_contra | 4 | 4 | 0 | 100.0 | 0 | 0 | 0 | 4 |
| rejection_at_level_bearish_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| momentum_acceleration_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| head_and_shoulders_top_contra | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |

## Hits detail

- **09:40** double_top (bearish, conf 0.705) @ close $738.04 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **09:45** failed_breakdown_wick (bullish, conf 0.588) @ close $738.87 -- grade: **WIN** -- heartbeat: **pattern_only**
- **09:45** failed_breakdown_wick::contra_regime (bullish, conf 0.638) @ close $738.87 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:30** double_top (bearish, conf 0.665) @ close $737.43 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:35** double_top (bearish, conf 0.645) @ close $737.93 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **10:35** failed_breakdown_wick (bullish, conf 0.716) @ close $737.93 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:35** failed_breakdown_wick::contra_regime (bullish, conf 0.766) @ close $737.93 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:40** double_top (bearish, conf 0.63) @ close $738.30 -- grade: **WIN** -- heartbeat: **pattern_only**
- **10:50** inside_bar_consolidation (neutral, conf 0.547) @ close $738.17 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **11:30** failed_breakdown_wick (bullish, conf 0.616) @ close $736.51 -- grade: **WIN** -- heartbeat: **pattern_only**
- **11:30** failed_breakdown_wick::contra_regime (bullish, conf 0.666) @ close $736.51 -- grade: **WIN** -- heartbeat: **pattern_only**
- **11:50** double_bottom (bullish, conf 0.673) @ close $736.92 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **11:50** double_bottom::contra_regime (bullish, conf 0.723) @ close $736.92 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:15** double_bottom (bullish, conf 0.624) @ close $737.21 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:15** double_bottom::contra_regime (bullish, conf 0.674) @ close $737.21 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:25** double_top (bearish, conf 0.737) @ close $734.83 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:25** momentum_acceleration (bearish, conf 0.69) @ close $734.83 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:30** double_top (bearish, conf 0.712) @ close $735.45 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:30** failed_breakdown_wick (bullish, conf 0.657) @ close $735.45 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:30** failed_breakdown_wick::contra_regime (bullish, conf 0.707) @ close $735.45 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:50** double_bottom (bullish, conf 0.577) @ close $736.80 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:50** double_bottom::contra_regime (bullish, conf 0.627) @ close $736.80 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:55** double_bottom (bullish, conf 0.564) @ close $736.49 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:55** double_bottom::contra_regime (bullish, conf 0.614) @ close $736.49 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:00** double_bottom (bullish, conf 0.58) @ close $736.89 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:00** double_bottom::contra_regime (bullish, conf 0.63) @ close $736.89 -- grade: **WIN** -- heartbeat: **pattern_only**
- **13:25** inside_bar_consolidation (neutral, conf 0.55) @ close $737.36 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **15:00** double_bottom (bullish, conf 0.719) @ close $736.41 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:00** momentum_acceleration (bullish, conf 0.85) @ close $736.41 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:05** double_bottom (bullish, conf 0.715) @ close $736.30 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:10** double_bottom (bullish, conf 0.705) @ close $736.06 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:10** inside_bar_consolidation (neutral, conf 0.683) @ close $736.06 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **15:15** double_bottom (bullish, conf 0.692) @ close $735.75 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:15** inside_bar_consolidation (neutral, conf 0.597) @ close $735.75 -- grade: **NEUTRAL** -- heartbeat: **pattern_only**
- **15:15** double_bottom::contra_regime (bullish, conf 0.742) @ close $735.75 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:20** double_bottom (bullish, conf 0.67) @ close $735.21 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:20** double_bottom::contra_regime (bullish, conf 0.72) @ close $735.21 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:25** double_bottom (bullish, conf 0.683) @ close $735.52 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:25** double_bottom::contra_regime (bullish, conf 0.733) @ close $735.52 -- grade: **WIN** -- heartbeat: **pattern_only**