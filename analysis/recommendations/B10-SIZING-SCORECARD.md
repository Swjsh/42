# B10 — Sizing & Compounding the 3-Edge Book (within J's hard caps)

- Run: 2026-06-21  |  Window: 2025-01-01..2026-05-15  |  Trading days: 342
- Fills: real OPRA via lib.simulator_real (reuses B9 detect+fill pipeline; C1)  |  Baseline qty: 3
- B9 cross-check: Safe qty3 $14608.16 (B9 $14608.16), Bold qty3 $18784.32 (B9 $18784.32) — match=True

## VERDICT: **SIZING_SPEC_PRODUCED**  |  respects_hard_caps = **True**

## Safe-2 — ATM, edges e1+e2+e4

**Per-trade return-on-capital** (n=301): mean=0.16142, std=0.50087, downside=0.05476, WR=0.5249, avg_win=0.37897, avg_loss=-0.07895, worst=-0.08, median_premium=$1.38

**Per-day return** (n=149): mean=0.19759, std=0.64761, worst_day=-0.08, day_WR=0.5705

**Kelly (fraction of equity as premium/trade):** full=0.4259 (continuous 0.6434, discrete 0.4259), half=0.213, **quarter=0.1065 (RECOMMENDED)**

### Compounding sims (replay measured returns, compound from start equity)

| sizing | final $ | total ret% | CAGR% | maxDD% | kill trips | ruin | ->$5K | ->$10K | ->$25K |
|---|---|---|---|---|---|---|---|---|---|
| v15_current | 49290.31 | 2364.5 | 22484.0 | 6.0 | 0 | False | 7 | 18 | 90 |
| full_kelly | 423926723.99 | 21196236.2 | 101899634588.4 | 30.4 | 0 | False | 6 | 9 | 15 |
| half_kelly | 16222458.81 | 811022.9 | 408640241.2 | 22.6 | 0 | False | 7 | 14 | 15 |
| quarter_kelly | 251483.74 | 12474.2 | 355366.1 | 11.9 | 0 | False | 13 | 17 | 90 |
| v15_stressed50 | 21823.19 | 991.2 | 5593.2 | 6.7 | 0 | False | 15 | 91 | None |
| half_kelly_stressed50 | 215740.81 | 10687.0 | 274181.9 | 11.9 | 0 | False | 15 | 32 | 92 |
| quarter_kelly_stressed50 | 27620.51 | 1281.0 | 8380.0 | 6.0 | 0 | False | 15 | 95 | 122 |

### Monte-Carlo risk-of-ruin (2000 day-block bootstrap paths — the HONEST risk number)

| fraction | ruin rate | final $ P05 | final $ median | final $ P95 | maxDD% med | maxDD% P95 | kill trips P95 |
|---|---|---|---|---|---|---|---|
| quarter_kelly | 0.0 | 63157.37 | 239740.8 | 1251055.74 | 5.8 | 11.9 | 0.0 |
| quarter_kelly_stressed50 | 0.0 | 12455.97 | 24363.92 | 57512.27 | 3.5 | 7.1 | 0.0 |
| half_kelly | 0.0 | 1288052.06 | 15186424.9 | 296052763.95 | 9.8 | 21.1 | 0.0 |
| half_kelly_stressed50 | 0.0 | 56792.11 | 209954.29 | 1098817.11 | 5.8 | 12.0 | 0.0 |

_day-block bootstrap (resample whole days w/ replacement, 342-day paths). Final-equity dispersion is wide because compounding a positive-mean bull-tape edge over 342 days is explosive in the lucky tail — read the P05 + ruin_rate + max_dd, NOT the median terminal $, as the risk signal._

**Recommended (quarter-Kelly) ruin under 50% stress: 0.0 -> safe=True**

### Concrete SIZING-SPEC — contracts per equity tier (quarter-Kelly, clamped to caps)

| equity | recommended | kelly wanted | per-trade cap (Rule 6) | clamp | v15 base (%eq, breach?) | v15 elite (%eq, breach?) |
|---|---|---|---|---|---|---|
| $2000 | **3** | 1 | 4 | min_floor | 5 (34.5%, BREACH) | 8 (55.2%, BREACH) |
| $5000 | **3** | 3 | 10 | None | 5 (13.8%, ok) | 8 (22.1%, ok) |
| $10000 | **7** | 7 | 21 | None | 10 (13.8%, ok) | 15 (20.7%, ok) |
| $25000 | **19** | 19 | 54 | None | 10 (5.5%, ok) | 15 (8.3%, ok) |

**v15 vs recommended:** v15 BREACHES Rule 6 at $2K: nominal base 5 contracts = 34.5% of equity (cap 30%); elite 8 = 55.2%. The Rule 6 cap MUST clip these to 4. Quarter-Kelly+min-3 floor = 3 contracts (20.7% of equity) sits safely inside the cap and is the correct sub-$5K size.

## Bold — ITM-2, edges e1+e2

**Per-trade return-on-capital** (n=225): mean=0.15149, std=0.29232, downside=0.05491, WR=0.5244, avg_win=0.36075, avg_loss=-0.07928, worst=-0.08, median_premium=$2.57

**Per-day return** (n=149): mean=0.15583, std=0.28901, worst_day=-0.08, day_WR=0.5638

**Kelly (fraction of equity as premium/trade):** full=0.4199 (continuous 1.7728, discrete 0.4199), half=0.2099, **quarter=0.105 (RECOMMENDED)**

### Compounding sims (replay measured returns, compound from start equity)

| sizing | final $ | total ret% | CAGR% | maxDD% | kill trips | ruin | ->$5K | ->$10K | ->$25K |
|---|---|---|---|---|---|---|---|---|---|
| v15_current | 66077.64 | 3849.6 | 50044.1 | 4.7 | 0 | False | 7 | 19 | 77 |
| full_kelly | 377258597.36 | 22549726.5 | 113145730681.2 | 31.0 | 0 | False | 7 | 14 | 34 |
| half_kelly | 1204295.98 | 71884.2 | 6797795.6 | 16.7 | 0 | False | 16 | 49 | 91 |
| quarter_kelly | 89843.9 | 5270.2 | 84212.8 | 8.6 | 0 | False | 17 | 75 | 105 |
| v15_stressed50 | 30774.96 | 1739.5 | 13670.8 | 5.0 | 0 | False | 17 | 76 | 118 |
| half_kelly_stressed50 | 58393.92 | 3390.4 | 40583.7 | 8.6 | 0 | False | 42 | 97 | 114 |
| quarter_kelly_stressed50 | 16986.36 | 915.3 | 4940.2 | 4.1 | 0 | False | 45 | 109 | None |

### Monte-Carlo risk-of-ruin (2000 day-block bootstrap paths — the HONEST risk number)

| fraction | ruin rate | final $ P05 | final $ median | final $ P95 | maxDD% med | maxDD% P95 | kill trips P95 |
|---|---|---|---|---|---|---|---|
| quarter_kelly | 0.0 | 31310.55 | 77448.14 | 200581.33 | 4.8 | 10.0 | 0.0 |
| quarter_kelly_stressed50 | 0.0 | 9549.74 | 14712.4 | 23476.5 | 4.1 | 11.9 | 0.0 |
| half_kelly | 0.0 | 234328.75 | 1347870.3 | 8402685.36 | 8.1 | 17.2 | 0.0 |
| half_kelly_stressed50 | 0.0 | 21508.82 | 52983.2 | 135996.35 | 4.9 | 9.5 | 0.0 |

_day-block bootstrap (resample whole days w/ replacement, 342-day paths). Final-equity dispersion is wide because compounding a positive-mean bull-tape edge over 342 days is explosive in the lucky tail — read the P05 + ruin_rate + max_dd, NOT the median terminal $, as the risk signal._

**Recommended (quarter-Kelly) ruin under 50% stress: 0.0 -> safe=True**

### Concrete SIZING-SPEC — contracts per equity tier (quarter-Kelly, clamped to caps)

| equity | recommended | kelly wanted | per-trade cap (Rule 6) | clamp | v15 base (%eq, breach?) | v15 elite (%eq, breach?) |
|---|---|---|---|---|---|---|
| $2000 | **3** | 0 | 3 | min_floor | 5 (64.2%, BREACH) | 8 (102.8%, BREACH) |
| $5000 | **3** | 2 | 9 | min_floor | 5 (25.7%, ok) | 8 (41.1%, ok) |
| $10000 | **4** | 4 | 19 | None | 10 (25.7%, ok) | 15 (38.5%, ok) |
| $25000 | **10** | 10 | 48 | None | 10 (10.3%, ok) | 15 (15.4%, ok) |

**v15 vs recommended:** v15 BREACHES Rule 6 at $2K: nominal base 5 contracts = 64.2% of equity (cap 50%); elite 8 = 102.8%. The Rule 6 cap MUST clip these to 3. Quarter-Kelly+min-3 floor = 3 contracts (38.5% of equity) sits safely inside the cap and is the correct sub-$5K size.

## How to read this / disclosure

- **kelly_unit**: Kelly fraction = fraction of EQUITY deployed as option premium per trade; full-Kelly = min(continuous m/v, discrete two-outcome) for conservatism. We recommend QUARTER-Kelly as the practical fraction (0DTE fat tails + bull-regime-flattered edge).
- **hard_caps_never_exceeded**: every proposed contract count is CLAMPED to Rule 6 (per-trade cap + min-3 floor); where Kelly wants more we FLAG 'edge supports X, capped at Y' and clamp — never override.
- **bull_regime_caveat**: the measured Sharpe (~4.5-4.7) reflects a 2025-26 BULL tape and will NOT hold in chop/bear. We re-run every sizing with a 50% edge haircut (stressed50 rows) — the recommended fraction must still avoid ruin under that stress. Size for the WORSE regime.
- **compounding_replay**: per-trade measured returns replayed chronologically; equity compounds; daily kill switch enforced intraday vs SoD equity; ruin = equity < 10% of start.
- **real_fills**: real OPRA fills (C1); per-trade EXPECTANCY not WR (OP-14); SPY-dir != option edge (C3).
