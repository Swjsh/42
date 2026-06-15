# CHART READING SCORE — does the visual quality of the setup predict winners?

Built from 312 OOS real-fills trades. Each trade scored 0-10 on:

- **Ribbon duration** (how long established)
- **Ribbon momentum** (spreading vs compressing)
- **Rejection candle** (wick direction, body size)
- **Volume conviction** (vs 20-bar avg)
- **EMA distance** (how close to the ribbon at entry)
- **Failed today penalty** (-2 if prior stop)

## Score by quartile

| quartile | n | WR | per-trade /c | verdict |
|---|---|---|---|---|
| Q1(low) | 78 | 0.23 | -4.7 | **SKIP** |
| Q2 | 78 | 0.31 | +4.2 | **SELECTIVE** |
| Q3 | 78 | 0.36 | +11.9 | **ENTER** |
| Q4(high) | 78 | 0.31 | +3.2 | **SELECTIVE** |

## By individual feature (top correlation with winning)
| feature | winners mean | losers mean | signal strength |
|---|---|---|---|
| chart_score | 3.77 | 3.53 |  |
| ribbon_duration | 17.74 | 24.87 | ★★ |
| ribbon_momentum | 3.89 | -1.59 | ★★★★★ |
| wick_favor | 0.57 | 0.49 | ★ |
| volume_conv | 1.01 | 0.93 |  |
| ema_dist_cents | 70.18 | 64.05 |  |
| failed_today | 0.27 | 0.28 |  |