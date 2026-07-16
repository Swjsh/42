# vwap_continuation HTF pre-check study -- 2026-07-16

**Verdict: KILL**

HTF-opposed bucket is PROFITABLE on the backtest cohort (n=48, exp=$67.15/tr, WR=72.9%, positive in 0.83 of quarters, still +$38.32/tr after dropping its top-5 winners -- broad-based, not an outlier artifact) -- today's 2 live losses do NOT generalize. A blanket HTF pre-check would forfeit real edge. Notably the ALIGNED bucket is the fragile one here: exp=$8.87/tr headline but drop-top5=$-20.41/tr (NEGATIVE -- its edge is carried by a few large winners). Plausible mechanism (consistent with LESSONS-LEARNED C28 'ribbon flip is a lagging exit'): htf_15m_stack is a SLOW 15m-ribbon read; vwap_continuation's fast intraday VWAP signal can catch a genuine early reversal before the lagging HTF stack flips -- gating on it would filter out early-reversal trades, not bad trades.

## Trigger

2026-07-16 vwap_continuation fired SHORT (751P) x2 while htf_15m_stack==BULL, both losses (-$54, -$14 = -$68); free-model veto engaged only after those 2 losses, then correctly blocked 5 more re-fires citing the same HTF conflict.

## Rule under test

skip vwap_continuation SHORT when htf_15m_stack==BULL; skip LONG when htf_15m_stack==BEAR; MIXED/None -> unchanged (no pre-check gate).

## Backtest cohort (real OPRA fills, ATM tier, J_VWAP_CONT / live config)

Date range 2025-01-02 .. 2026-06-16 (363 trading days)

| bucket | n | exp $/tr | WR% | total $ | drop-top5 $/tr | q+ fraction |
|---|---|---|---|---|---|---|
| aligned | 73 | 8.87 | 75.3 | 647.8 | -20.41 | 0.67 |
| opposed | 48 | 67.15 | 72.9 | 3223.0 | 38.32 | 0.83 |
| neutral | 35 | 42.94 | 77.1 | 1503.0 | 1.26 | 0.83 |

### Per-quarter (backtest, robustness check)

**aligned** exit reasons: {'EXIT_ALL_RIBBON_FLIP_BACK': 7, 'EXIT_ALL_LEVEL_STOP': 13, 'TP1_THEN_RUNNER_RIBBON': 36, 'TP1_THEN_RUNNER_TIME': 13, 'EXIT_ALL_TIME_STOP': 4}
- 2025Q1: n=8 exp=$92.78 total=$742.2
- 2025Q2: n=12 exp=$-66.05 total=$-792.6
- 2025Q3: n=12 exp=$19.23 total=$230.8
- 2025Q4: n=19 exp=$21.84 total=$415.0
- 2026Q1: n=9 exp=$63.67 total=$573.0
- 2026Q2: n=13 exp=$-40.05 total=$-520.6

**opposed** exit reasons: {'EXIT_ALL_RIBBON_FLIP_BACK': 29, 'TP1_THEN_RUNNER_RIBBON': 14, 'TP1_THEN_RUNNER_TIME': 4, 'EXIT_ALL_LEVEL_STOP': 1}
- 2025Q1: n=7 exp=$113.06 total=$791.4
- 2025Q2: n=7 exp=$41.31 total=$289.2
- 2025Q3: n=9 exp=$5.47 total=$49.2
- 2025Q4: n=7 exp=$134.69 total=$942.8
- 2026Q1: n=12 exp=$129.42 total=$1553.0
- 2026Q2: n=6 exp=$-67.1 total=$-402.6

## Live fills (armed 2026-07-01)

n_placed_ticks_raw (tick-level, not distinct trades): 8

| bucket | n | exp $/tr | WR% | total $ |
|---|---|---|---|---|
| aligned | 6 | -32.33 | 0.0 | -194.0 |
| opposed | 2 | -34.0 | 0.0 | -68.0 |
| neutral | 0 | None | None | 0.0 |

Caveat: 2026-07-02 fills are attribution='inferred_ts_strike_match' -- trades.csv labels them setup=UNKNOWN due to a known bug (fixed same-day only for 2026-07-16's rows per that day's journal note, never backfilled for 2026-07-02). Matched here by exact entry timestamp (+/-90s) + strike + side, NOT by editing the ledger. Treat as high-confidence but unconfirmed.

## Kill criterion

if the HTF-opposed bucket (backtest, n>=10) is net PROFITABLE, the pre-check dies regardless of today's 2 live losses.

## Action

STUDY ONLY -- NO PARAMS CHANGED. Recommendation for J's morning review.
