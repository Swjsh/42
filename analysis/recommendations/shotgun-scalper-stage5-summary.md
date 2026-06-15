# SHOTGUN_SCALPER Stage 5 — Ratification Scorecard

Generated: 2026-05-16T23:55:04.658565+00:00
Source: stage4  |  Input keepers: 7  |  Stage5 passed: 5

## Summary of all candidates

| Rank | TP | Stop | Strike | Vol | Wide P&L | Sharpe | Dir | WF Test | Stage5 |
|------|-----|------|--------|-----|----------|--------|-----|---------|--------|
| 1 | 1.5 | -0.35 | 2 | 1.2 | $18340 | 4.50 | 3/5 | $5681 | PASS |
| 2 | 0.75 | -0.35 | 2 | 1.2 | $22084 | 5.09 | 3/5 | $7642 | PASS |
| 3 | 0.75 | -0.35 | 1 | 1.2 | $14254 | 3.73 | 3/5 | $4660 | PASS |
| 4 | 1.5 | -0.35 | 2 | 1.0 | $17480 | 3.93 | 4/5 | $5987 | PASS |
| 5 | 1.0 | -0.3 | 1 | 1.0 | $8254 | 2.01 | 4/5 | $3031 | PASS |
| 6 | 1.0 | -0.35 | 2 | 0.6 | $14582 | 2.93 | 3/5 | $5448 | FAIL |
| 7 | 1.5 | -0.35 | 2 | 0.6 | $14144 | 2.93 | 3/5 | $4591 | FAIL |

## Best candidate: Rank #1

**Combo:** `{'tp_premium_pct': 1.5, 'stop_premium_pct': -0.35, 'time_stop_min': 12, 'strike_offset': 2, 'chandelier_arm_pct': 0.4, 'vol_ratio_threshold': 1.2}`

| Metric | Value | Gate |
|--------|-------|------|
| walk_forward | PASS | OK |
| directional | PASS | OK |
| sharpe | PASS | OK |
| wide_pnl | PASS | OK |
| max_drawdown | PASS | OK |
| positive_q6 | PASS | OK |
| edge_capture | PASS | OK |

### Quarter P&L breakdown

| Quarter | P&L |
|---------|-----|
| 2025-Q1 | $2704 |
| 2025-Q2 | $4160 |
| 2025-Q3 | $2757 |
| 2025-Q4 | $3037 |
| 2026-Q1 | $2840 |
| 2026-Q2 | $2841 |

### OP 20 Disclosures

- 1. ACCOUNT SIZE: Baseline qty=3 contracts / $1000 paper. Headline P&L (18340) scales with qty — at $1K paper, 3-contract positions represent high % risk.

- 2. SAMPLE BIAS: Top-5 best days = 16.3% of total P&L. Selected from Stage 4 grid of 288 combos — winner's curse applies. Out-of-sample walk-forward test below partially corrects for this.

- 3. OUT-OF-SAMPLE: walk-forward train=2025 (12659) test=2026 (5681). Result: PASS (PASS: test window net-positive, all test quarters positive). Full OPRA real-fills used throughout (no BS sim).

- 4. REAL-FILLS: All simulation uses Alpaca OPRA option bars (5-min OHLCV). No Black-Scholes pricing. Entry approx = VWAP of next 5m bar after signal. Slippage not explicitly modeled — bid/ask spread implicit in VWAP vs last.

- 5. FAILURE MODES: (a) Worst quarter=2025-Q1 (2704). (b) Max drawdown=1341 = 7.3% of total P&L. (c) Engine fires LONG on 4/29 (J SHORT) and 5/15 (J SHORT) — structural trendline-bias miss. (d) 5-trade/day cap: misses alpha on high-conviction days (5/04 engine fired 4 but J ran 10).

- 6. CONCENTRATION: top-5 days = 16.3% of 18340 P&L (PASS). N=1204 trades over 16 months. Sharpe=4.50, expectancy=15.23/trade.


### Direction detail (J anchor days)

- **2026-04-29**: YES same-dir (short), 1 fires
- **2026-05-01**: YES same-dir (short), 5 fires
- **2026-05-04**: YES same-dir (short), 4 fires
- **2026-05-14**: miss (j=long, engine=no-fire)
- **2026-05-15**: miss (j=short, engine=['long', 'long'])
- **2026-05-05**: caught loss (engine $-3.00)
- **2026-05-06**: AVOIDED loss (engine $231.00)
- **2026-05-07**: AVOIDED loss (engine $95.85)