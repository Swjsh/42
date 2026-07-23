# Engine full-history replay -- CURRENT LIVE core-Safe engine, 2025-01-02..2026-07-22

Generated 2026-07-22T20:52:52.372265. Runner: `backtest/tools/engine_fullhist_replay.py`.
Runtime: entry=113.1s exit=2.5s total=115.9s.

## Scope disclosure

RIDE_THE_RIBBON family only (BEARISH_REJECTION + BULLISH_RECLAIM) -- the two setups `orchestrator.run_backtest` models. Extra setups (bollinger_squeeze, vwap_continuation, vwap_reclaim_failed_break, vix_regime_dayside, double_bottom_base_quiet, gap_and_go) are NOT included -- no full-history batch-replay harness exists for them yet. This UNDERSTATES total Safe P&L. Safe account only (Bold/aggressive not run).

Exit shape: REAL `exit_manager.plan_exit_actions` via `strategies.py#RIBBON_RIDE.exit` (NOT `simulate_trade_real`'s params.json-top-level-keys shape, which is KNOWN-DIVERGENT -- see SIM-EXIT-SHAPE-PARITY-AUDIT). Every raw entry's `dollar_pnl` was discarded and re-derived via `exit_manager_walk.walk_exit_manager`.

Correct exit shape used: `{'premium_stop_pct': -0.2, 'tp1_premium_pct': 1.0, 'tp1_qty_fraction': 0.667, 'profit_lock_mode': 'trailing', 'runner_target_pct': 99.0, 'trail_pct': 0.15, 'profit_lock_arm_pct': 0.05, 'stop_mode': 'structure', 'catastrophe_stop_pct': -0.5, 'profit_lock_arm_scope': 'post_tp1'}`

## Sanity anchors (fidelity check, task step 5 -- TRADE-LEVEL, corrected vs ground truth)

> Task brief's anchor wording was imprecise (corrected against journal/trades.csv ground truth, account_id=='safe'): 2026-07-17's +$342 is core_safe+core_bold COMBINED (core_safe alone=$151.00, 4 ribbon_ride entries); 2026-07-21 genuinely has ONE near-zero core_safe entry, not zero.

- 2026-07-17 core_safe: replayed P&L sum $+404.40 vs live $151.00 (pnl_sum_pass=False); TRADE-LEVEL match: 2/4 live entries reproduced by strike+side (pass=False)
- 2026-07-21 (quiet day, 1 near-zero entry expected): matched 1/1 (pass=True)
- 2026-07-22 (expect zero entries): n_entries=0 (pass=True)
- **ALL TRADE-LEVEL ANCHORS PASS: False**

### 2026-07-17 detail

| Expected (live core_safe) | Replay match |
|---|---|
| 11:40 tier=ELITE pnl=$-102 | time=13:55 tier=SUPER pnl=$+459.00 |
| 13:01 tier=TRENDLINE pnl=$+241 | time=13:15 tier=TRENDLINE pnl=$-54.60 |
| 11:06 strike=744P tier=ELITE live_pnl=$-37 | **NO MATCH -- replay never took this trade** |
| 14:49 strike=743P tier=TRENDLINE live_pnl=$-56 | **NO MATCH -- replay never took this trade** |

## Headline

| Metric | Value |
|---|---|
| Total P&L (18mo) | $+5,064.75 |
| N trades | 190 |
| Win rate | 0.2947 |
| Profit factor | 1.333 |
| Avg P&L / trade | $+26.66 |
| Max drawdown | $-2,233.40 on 2025-06-12 |
| $/calendar-day (avg over all 387 RTH days) | $+13.09 |
| $/calendar-day (median) | $+0.00 |
| $/trading-day (avg, only the 141 days it fired) | $+35.92 |
| $/trading-day (median) | $-63.00 |
| % of days it trades at all | 36.4% |

## J-framing: FOCUS-DOCTRINE $100-200/day goal at $2K

- Actual $/calendar-day: $+13.09 (meets $100 floor: False)
- Actual $/trading-day (days it fires): $+35.92 (meets $100 floor: False)
- Fires on 36.4% of trading days

## Per-regime

| Regime | N | Total P&L | WR | Avg/trade |
|---|---|---|---|---|
| 2025H1 | 38 | $-55.55 | 0.2368 | $-1.46 |
| 2025H2 | 72 | $+1,633.60 | 0.2361 | $+22.69 |
| 2026 | 80 | $+3,486.70 | 0.375 | $+43.58 |

## Per-setup / per-side / per-tier

| Setup | N | Total P&L | WR |
|---|---|---|---|
| BEARISH_REJECTION_RIDE_THE_RIBBON | 151 | $+2,729.35 | 0.2649 |
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 39 | $+2,335.40 | 0.4103 |

| Side | N | Total P&L | WR |
|---|---|---|---|
| C | 39 | $+2,335.40 | 0.4103 |
| P | 151 | $+2,729.35 | 0.2649 |

| Tier | N | Total P&L | WR |
|---|---|---|---|
| ELITE | 11 | $+2,758.20 | 0.7273 |
| LEVEL | 18 | $-990.45 | 0.2778 |
| SUPER | 37 | $+5,127.10 | 0.5135 |
| TRENDLINE | 124 | $-1,830.10 | 0.1935 |

## Best 10 days

| Date | P&L |
|---|---|
| 2026-05-18 | $+1,465.10 |
| 2026-06-08 | $+971.90 |
| 2025-08-22 | $+841.35 |
| 2026-06-11 | $+752.00 |
| 2025-01-10 | $+717.55 |
| 2026-01-29 | $+656.85 |
| 2025-06-13 | $+656.00 |
| 2026-02-26 | $+636.05 |
| 2025-02-21 | $+616.00 |
| 2025-08-12 | $+572.00 |

## Worst 10 days

| Date | P&L |
|---|---|
| 2026-06-25 | $-825.00 |
| 2026-06-26 | $-708.00 |
| 2025-01-29 | $-420.60 |
| 2026-06-09 | $-390.00 |
| 2026-06-17 | $-355.50 |
| 2025-08-11 | $-331.80 |
| 2026-06-29 | $-324.00 |
| 2025-09-26 | $-308.00 |
| 2025-09-17 | $-298.20 |
| 2026-06-22 | $-292.00 |

## Data quality

- Raw entries from run_backtest: 206
- Replayed (correct-shape exit derived): 190
- Excluded, no OPRA cache: 16
- Excluded, no SPY day: 0

---
_Source: `backtest/tools/engine_fullhist_replay.py`. Raw JSON with full trade log + equity curve: `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`._
