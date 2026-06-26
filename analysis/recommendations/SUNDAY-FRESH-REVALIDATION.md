# Sunday Fresh Re-Validation — are the 3 edges STILL ALIVE on the newest data?

- Run: 2026-06-21  |  Fresh window: **2026-05-30..2026-06-18** (14 trading days)
- A1 backfill: BACKFILLED — option cache now ends 2026-06-18 (contract files dated 260618)
- Frame: 2025-01-02..2026-06-18 (master + recent daily concat)  |  Fills: real OPRA via lib.simulator_real.simulate_trade_real (C1)
- Config: -0.08 stop, qty 3, v15 exits; vix-regime cfg = {'slope_rule': 'not_rising', 'low_margin': 0.25, 'source': 'b5 robust_clearing_cell'}

## VERDICT: edges_still_alive = **True**

_The fresh window is ~3 trading weeks — n is small per edge. This is a directional sanity check on the never-before-scored OOS, NOT a standing-bar ratification._

## #1 vwap_continuation (the LIVE edge — its detector is byte-for-byte the live watcher)

- signals: total 167, fresh-window 5
- **ATM (Safe-2 validated)** fresh: n=4 (4d) | exp **$1.98/tr** | total $7.92 | WR 25.0% | POSITIVE | days +1/-3
- **ITM-2 (Bold validated)** fresh: n=5 (5d) | exp **$-84.86/tr** | total $-424.32 | WR 0.0% | NEGATIVE | days +0/-5
- OTM-2 (the LIVE mis-strike) fresh: n=4 (4d) | exp **$6.03/tr** | total $24.12 | WR 25.0% | POSITIVE | days +1/-3
- alive on fresh: **True**

### WP-5 strike A/B on the fresh signal set (does the OTM-2 leak persist?)

| strike | role | fresh n | fresh exp/tr | fresh total | sign | full-OOS-2026 exp/tr |
|---|---|---|---|---|---|---|
| OTM-2 | LIVE Safe-2 tier (the mis-strike leak) | 4 | $6.03 | $24.12 | POSITIVE | $18.36 |
| ATM | validated Safe-2 cell | 4 | $1.98 | $7.92 | POSITIVE | $47.55 |
| ITM-1 | intermediate | 5 | $-30.31 | $-151.56 | NEGATIVE | $56.48 |
| ITM-2 | validated Bold cell | 5 | $-84.86 | $-424.32 | NEGATIVE | $73.66 |

## #2 vwap_reclaim_failed_break (dormant)

- signals: 87
- ATM fresh: n=4 (4d) | exp **$-42.96/tr** | total $-171.84 | WR 0.0% | NEGATIVE | days +0/-4
- ITM-2 fresh: n=5 (5d) | exp **$-85.87/tr** | total $-429.36 | WR 0.0% | NEGATIVE | days +0/-5
- ATM full-OOS-2026: n=23 (23d) | exp **$13.11/tr** | total $301.56 | WR 34.8% | POSITIVE | days +8/-15

## #4 vix_regime_dayside (dormant, ATM)

- cfg: {'slope_rule': 'not_rising', 'low_margin': 0.25, 'source': 'b5 robust_clearing_cell'}  |  signals: 85
- ATM fresh: n=1 (1d) | exp **$-32.4/tr** | total $-32.4 | WR 0.0% | NEGATIVE | days +0/-1
- ATM full-OOS-2026: n=24 (24d) | exp **$29.93/tr** | total $718.2 | WR 41.7% | POSITIVE | days +10/-14

## 3-edge portfolio (fresh window, real fills, per account)

| book | days | total$ | daily mean$ | day +/- | best/worst day | sign |
|---|---|---|---|---|---|---|
| Safe2_ATM_1+2+4 | 4 | $-196.32 | $-49.08 | +1/-3 | $74.16/$-118.8 | NEGATIVE |
| Bold_ITM2_1+2 | 5 | $-853.68 | $-170.74 | +0/-5 | $-128.64/$-292.8 | NEGATIVE |

## How to read this

- **edges_still_alive = live #1 positive-expectancy on the never-scored fresh OOS.** It is the 'are we actually profitable now' answer.
- Small-n caveat: ~3 weeks. A single big day swings the per-trade number. The full-OOS-2026 column is the larger-n companion read.
- Real OPRA fills (C1). Per-trade EXPECTANCY, not WR (OP-14). SPY-direction != option edge (C3/L58).
- RESEARCH ONLY — no live edit on a Sunday (money-path guard).
