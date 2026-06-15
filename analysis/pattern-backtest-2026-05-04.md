# Pattern Backtest -- 2026-05-04

- bars: 78
- heartbeat decisions logged: 0
- detectors run: double_bottom, double_top, failed_breakdown_wick, rejection_at_level_bearish
- total pattern hits: 11

## Summary by detector

| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| double_bottom | 4 | 2 | 2 | 50.0 | 0 | 0 | 0 | 4 |
| double_top | 5 | 2 | 3 | 40.0 | 0 | 0 | 0 | 5 |
| failed_breakdown_wick | 2 | 0 | 2 | 0.0 | 0 | 0 | 0 | 2 |
| rejection_at_level_bearish | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |

## Hits detail

- **11:40** failed_breakdown_wick (bullish, conf 0.594) @ close $718.32 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **11:50** failed_breakdown_wick (bullish, conf 0.62) @ close $718.04 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:00** double_top (bearish, conf 0.72) @ close $717.26 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:05** double_top (bearish, conf 0.768) @ close $716.12 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:10** double_top (bearish, conf 0.775) @ close $715.94 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:15** double_top (bearish, conf 0.723) @ close $717.19 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:20** double_bottom (bullish, conf 0.629) @ close $717.44 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:25** double_bottom (bullish, conf 0.611) @ close $717.00 -- grade: **WIN** -- heartbeat: **pattern_only**
- **12:25** double_top (bearish, conf 0.731) @ close $717.00 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:30** double_bottom (bullish, conf 0.634) @ close $717.56 -- grade: **LOSS** -- heartbeat: **pattern_only**
- **12:35** double_bottom (bullish, conf 0.604) @ close $716.83 -- grade: **WIN** -- heartbeat: **pattern_only**