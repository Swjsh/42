# Pattern Backtest -- 2026-05-01

- bars: 78
- heartbeat decisions logged: 0
- detectors run: double_bottom, double_top, failed_breakdown_wick, rejection_at_level_bearish
- total pattern hits: 8

## Summary by detector

| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| double_bottom | 3 | 2 | 1 | 66.7 | 0 | 0 | 0 | 3 |
| double_top | 4 | 3 | 1 | 75.0 | 0 | 0 | 0 | 4 |
| failed_breakdown_wick | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| rejection_at_level_bearish | 1 | 1 | 0 | 100.0 | 0 | 0 | 0 | 1 |

## Hits detail

- **11:50** rejection_at_level_bearish (bearish, conf 0.663) @ close $723.48 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:35** double_top (bearish, conf 0.596) @ close $721.35 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:40** double_top (bearish, conf 0.601) @ close $721.22 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:45** double_top (bearish, conf 0.606) @ close $721.11 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:50** double_top (bearish, conf 0.608) @ close $721.05 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:20** double_bottom (bullish, conf 0.613) @ close $722.25 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:25** double_bottom (bullish, conf 0.62) @ close $722.42 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:30** double_bottom (bullish, conf 0.613) @ close $722.25 -- grade: **WIN** -- heartbeat: **pattern_only**