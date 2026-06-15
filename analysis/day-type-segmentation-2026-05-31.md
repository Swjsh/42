# DAY-TYPE SEGMENTATION — how engine performs by intraday market character

Classified from first 15 min of RTH (3×5m bars: gap, direction, range). Engine trades: 312 across 347 OOS days.

| day type | n trades | WR | per-trade /c | total /c | verdict |
|---|---|---|---|---|---|
| GAP_AND_GO | 76 | 0.38 | +8.6 | +651 | **TRADE IT** |
| CHOP | 115 | 0.27 | +4.5 | +513 | **SELECTIVE** |
| REVERSAL | 79 | 0.34 | +4.1 | +322 | **SELECTIVE** |
| TREND_FOLLOW_BULL | 11 | 0.45 | +14.4 | +158 | **TRADE IT** |
| TREND_FOLLOW_BEAR | 4 | 0.00 | -20.1 | -80 | **AVOID** |
| MIXED | 27 | 0.07 | -15.7 | -424 | **AVOID** |

## Key finding
**Best day type: TREND_FOLLOW_BULL (+14.4/trade)** — engine performs best on these days.
**Worst day type: MIXED (-15.7/trade)** — engine loses here; consider sitting out.

## Implication: REGIME-ADAPTIVE FILTER
A classifier that runs at 09:45–09:50 ET (after the first 3 RTH bars) can detect day type
and adjust filter thresholds accordingly:
- On TREND_FOLLOW_BULL days: relax filter (allow more entries, confidence required)
- On MIXED days: tighten filter or suppress all entries (gate = skip day)
This converts a static per-trade gate into a dynamic per-day regime detector,
directly addressing J's 'know what kind of day it is as it's happening' thesis.