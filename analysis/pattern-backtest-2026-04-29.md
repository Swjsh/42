# Pattern Backtest -- 2026-04-29

- bars: 78
- heartbeat decisions logged: 0
- detectors run: double_bottom, double_top, failed_breakdown_wick, rejection_at_level_bearish
- total pattern hits: 6

## Summary by detector

| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| double_bottom | 3 | 2 | 1 | 66.7 | 0 | 0 | 0 | 3 |
| double_top | 2 | 0 | 2 | 0.0 | 0 | 0 | 0 | 2 |
| failed_breakdown_wick | 1 | 1 | 0 | 100.0 | 0 | 0 | 0 | 1 |
| rejection_at_level_bearish | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |

## Hits detail

- **11:50** double_top (bearish, conf 0.647) @ close $709.55 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **14:40** double_top (bearish, conf 0.749) @ close $708.70 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **14:45** failed_breakdown_wick (bullish, conf 0.612) @ close $709.47 -- grade: **WIN** -- heartbeat: **pattern_only**
- **14:55** double_bottom (bullish, conf 0.737) @ close $710.57 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **15:00** double_bottom (bullish, conf 0.729) @ close $710.39 -- grade: **WIN** -- heartbeat: **pattern_only**
- **15:05** double_bottom (bullish, conf 0.732) @ close $710.46 -- grade: **WIN** -- heartbeat: **pattern_only**