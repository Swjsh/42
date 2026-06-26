# B9 — The 3-Edge VWAP Portfolio (combined real-fills measurement)

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)  |  OOS split: IS=2025 / OOS=2026
- Config: -8% premium stop, qty 3, v15 default exits; edge#4 vix config = {'slope_rule': 'not_rising', 'low_margin': 0.25, 'source': 'b5 robust_clearing_cell'}

## VERDICT: **PORTFOLIO_MEASURED**

- No non-regressive calendar/day-type abstention improved portfolio Sharpe (the book is already lean — see routing tables).

## Standalone edges (real OPRA fills, per tier)

| edge (tier) | n | days | exp/tr | OOS exp/tr | total$ | WR% |
|---|---|---|---|---|---|---|
| #1 vwap_continuation (ATM) | 149 | 149 | $48.33 | $59.81 | $7200.6 | 51.7 |
| #1 vwap_continuation (ITM-2) | 149 | 149 | $78.29 | $105.62 | $11665.56 | 51.7 |
| #1 WP-1 touch-and-go (ATM) | 117 | 117 | $35.88 | $50.15 | $4198.0 | 47.9 |
| #1 WP-1 touch-and-go (ITM-2) | 116 | 116 | $68.11 | $119.34 | $7900.56 | 47.4 |
| #2 reclaim_failed_break (ATM) | 76 | 76 | $53.28 | $28.39 | $4049.0 | 55.3 |
| #2 reclaim_failed_break (ITM-2) | 76 | 76 | $93.67 | $72.11 | $7118.76 | 53.9 |
| #4 vix_regime_dayside (ATM) | 76 | 76 | $44.19 | $79.49 | $3358.56 | 51.3 |

## Portfolio aggregates (combined daily equity vs standalone)

| book | total$ | ann.Sharpe | maxDD$ | % days in mkt | worst day$ | best day$ | day-WR% |
|---|---|---|---|---|---|---|---|
| Safe-2_ATM_base_1+2+4 | $14608.16 | 4.53 | $-836.4 | 43.6% | $-423.36 | $1045.2 | 57.0 |
| Safe-2_ATM_withWP1touchandgo_1tg+2+4 | $11605.56 | 3.93 | $-630.96 | 39.2% | $-423.36 | $1012.2 | 59.0 |
| Bold_ITM2_base_1+2 | $18784.32 | 4.7 | $-847.8 | 43.6% | $-447.36 | $974.8 | 56.4 |
| Bold_ITM2_withWP1touchandgo_1tg+2 | $15019.32 | 3.76 | $-944.88 | 34.5% | $-447.36 | $1064.4 | 51.7 |

## Edge correlation & day-overlap (diversification value)

### Safe-2
- fire-day counts: {'e1': 149, 'e2': 76, 'e4': 76}

| pair | day-overlap (Jaccard) | shared days | daily-P&L corr |
|---|---|---|---|
| e1__e2 | 0.51 | 76 | 0.313 |
| e1__e4 | 0.51 | 76 | 0.54 |
| e2__e4 | 0.382 | 42 | 0.076 |

### Bold
- fire-day counts: {'e1': 149, 'e2': 76}

| pair | day-overlap (Jaccard) | shared days | daily-P&L corr |
|---|---|---|---|
| e1__e2 | 0.51 | 76 | 0.439 |

## Routing / abstention analysis

_a bucket is an ABSTAIN candidate only if its in-market daily MEAN < 0 with >= 4 days; no-regression (L174) requires the abstained days' NET P&L < 0. Sharpe/DD/total deltas are vs the base 3-edge book._

### Safe-2 base book
- base: total=$14608.16 Sharpe=4.53 maxDD=$-836.4 %inMkt=43.6%
  - **day_of_week**: Fri(n=31,mean=$146.77,tot=$4549.96)  Mon(n=33,mean=$132.84,tot=$4383.72)  Thu(n=28,mean=$74.7,tot=$2091.6)  Tue(n=29,mean=$58.27,tot=$1689.88)  Wed(n=28,mean=$67.61,tot=$1893.0)
  - **gap_bucket**: flat_open(n=65,mean=$85.63,tot=$5565.64)  gap_down(n=37,mean=$143.98,tot=$5327.2)  gap_up(n=47,mean=$79.05,tot=$3715.32)
  - **range_bucket**: mid(n=80,mean=$113.11,tot=$9048.56)  narrow(n=46,mean=$49.6,tot=$2281.72)  wide(n=23,mean=$142.52,tot=$3277.88)
  - **trend_side**: down(n=67,mean=$83.61,tot=$5601.64)  up(n=82,mean=$109.84,tot=$9006.52)
  - **opex**: non_opex(n=140,mean=$93.44,tot=$13082.2)  opex(n=9,mean=$169.55,tot=$1525.96)
  - **month_end**: month_end(n=6,mean=$2.08,tot=$12.48)  non_month_end(n=143,mean=$102.07,tot=$14595.68)

### Bold base book
- base: total=$18784.32 Sharpe=4.7 maxDD=$-847.8 %inMkt=43.6%
  - **day_of_week**: Fri(n=30,mean=$143.67,tot=$4310.04)  Mon(n=34,mean=$174.57,tot=$5935.32)  Thu(n=28,mean=$93.54,tot=$2619.16)  Tue(n=29,mean=$95.49,tot=$2769.08)  Wed(n=28,mean=$112.53,tot=$3150.72)
  - **gap_bucket**: flat_open(n=64,mean=$110.78,tot=$7090.24)  gap_down(n=38,mean=$191.28,tot=$7268.48)  gap_up(n=47,mean=$94.16,tot=$4425.6)
  - **range_bucket**: mid(n=80,mean=$137.59,tot=$11007.04)  narrow(n=46,mean=$101.52,tot=$4670.0)  wide(n=23,mean=$135.1,tot=$3107.28)
  - **trend_side**: down(n=67,mean=$95.56,tot=$6402.4)  up(n=82,mean=$151.0,tot=$12381.92)
  - **opex**: non_opex(n=141,mean=$126.03,tot=$17770.44)  opex(n=8,mean=$126.73,tot=$1013.88)
  - **month_end**: month_end(n=7,mean=$125.67,tot=$879.72)  non_month_end(n=142,mean=$126.09,tot=$17904.6)

## How to read this

- **PORTFOLIO_MEASURED**: the combined-book numbers above are the answer — total P&L, per-trade expectancy (standalone table), annualized Sharpe, max DD, % days in market, worst day, vs each edge alone. This directly informs sizing + WP-0 ship order.
- **Correlation/overlap**: low Jaccard + low daily-P&L corr between edges = real diversification (the book's Sharpe should exceed any single edge's).
- **ROUTING_IMPROVEMENT** only if a calendar/day-type abstention raises Sharpe AND the abstained days were net-negative (L174 no-regression) — otherwise it is curve-fit.
- Real OPRA fills; SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY, not WR alone (OP-14). All 3 edges are call/bull-biased on the 2026 bull tape.
