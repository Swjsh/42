# EXIT-ENGINE-PARITY-RESIDUAL -- per-signal diagnosis (2026-07-23)

Generated 2026-07-23T21:24:37.859340. Runner: `backtest/tools/vwapcont_parity_diagnose.py`. Source study: `backtest/tools/vwapcont_entry_exit_matrix.py#parity_check`.

## Fill coverage

both engines filled: 149 / known scorecard n=149 -- bar-replay-only: 0, sim-only: 0, neither: 9.

## Aggregate reproduction (on the both-filled subset)

bar-replay: $+2,238.70 total (exp $15.02, known scorecard $15.02) | sim: $+8,155.46 total (exp $54.73, known scorecard $54.73).

## Stage-family split (THE finding)

- **Same terminal mechanism** (both engines agree which stage ended the trade): n=96, sum delta=$-1,605.52 (avg $-16.72/tr) -- engines agree WHICH mechanism ended the trade -> remaining delta here is fill-price/timing/rounding, not stage selection.
- **Different terminal mechanism** (engines disagree which stage ended the trade): n=53, sum delta=$-4,311.24 (avg $-81.34/tr) -- engines picked a DIFFERENT mechanism to end the same trade -> exit-priority/tie-break divergence.

## Top stage-pair buckets by |aggregate delta|

| bar-replay stage | sim exit_reason | n | sum delta | avg delta |
|---|---|--:|--:|--:|
| premium_stop | TP1_THEN_RUNNER_RIBBON | 14 | $-2,343.64 | $-167.40 |
| premium_stop | TP1_THEN_RUNNER_TIME | 5 | $-1,820.68 | $-364.14 |
| premium_stop | EXIT_ALL_PREMIUM_STOP | 91 | $-1,645.02 | $-18.08 |
| be_stop | EXIT_ALL_PREMIUM_STOP | 6 | $+866.40 | $+144.40 |
| premium_stop | EXIT_ALL_RIBBON_FLIP_BACK | 4 | $-636.00 | $-159.00 |
| runner_target | TP1_THEN_RUNNER_RIBBON | 2 | $+484.30 | $+242.15 |
| be_stop | EXIT_ALL_RIBBON_FLIP_BACK | 6 | $-446.80 | $-74.47 |
| runner_target | TP1_THEN_RUNNER_TIME | 3 | $-444.80 | $-148.27 |
| premium_stop | EXIT_ALL_TIME_STOP | 1 | $-132.92 | $-132.92 |
| be_stop | EXIT_ALL_LEVEL_STOP | 1 | $+101.60 | $+101.60 |
| runner_target | EXIT_ALL_RIBBON_FLIP_BACK | 3 | $+66.60 | $+22.20 |
| time_stop | TP1_THEN_RUNNER_TIME | 3 | $+50.20 | $+16.73 |
| be_stop | TP1_THEN_RUNNER_RIBBON | 10 | $-16.00 | $-1.60 |

## Root-cause confirmatory test (THE diagnosis)

**Hypothesis:** simulate_trade_real (lib/simulator_real.py:534-535, spy_idx=entry_bar_idx+2 / opt_idx=entry_idx_opt+1) NEVER checks the entry bar's own high/low for a stop/TP1 -- exit-checks start at the bar AFTER entry. replay_structure_aware's norm_bars (load_atm_bars) start AT the entry bar and the exit loop evaluates that SAME bar's high/low on iteration 1 -- one bar earlier than sim. On a volatile entry bar (common right after a breakout/pullback trigger) this can stop bar-replay out before sim ever gets a chance to see the trade run to TP1.

**Test:** re-ran bar-replay on the identical 149-signal population with norm_bars[1:] (entry bar excluded from exit-eligibility, matching sim's convention)

| | bar-replay (entry bar INCLUDED, current) | bar-replay (entry bar EXCLUDED) | sim (known) |
|---|--:|--:|--:|
| exp $/tr | $15.02 | $58.28 | $54.73 |

**CONFIRMED (91.1% of the $39.71/tr aggregate gap closed by removing the single entry-bar-inclusion convention difference; residual $-3.55/tr is consistent with the two previously-confirmed smaller mechanisms (pre-TP1 profit-lock scope + ribbon-flip-back). This is a DISCLOSURE about which of two long-standing, independently-precedented backtest conventions (bar-replay family: t4_exit_matrix/structure_stop_study/this study, vs simulate_trade_real: the ratified ship-gate C1 authority) is more faithful to live risk exposure -- NOT adjudicated here (real-money-adjacent judgment call, escalated separately, not decided at this tier).**


---
_Full per-signal detail (149 rows) in the companion `.json`._
