# Futures trade autopsy -- 2026-09-03T03:43:53

> Descriptive only (per winner_autopsy.py's own small-n discipline). No hypothesis queued, nothing else appended. SIMULATED and BROKER are never aggregated together.

## BROKER (broker fills)

n=3 -- total_pnl=$-93.75 -- win_rate=0.3333

| date | setup | dir/side | qty | entry->exit | exit_reason | $pnl | MAE(pts) | MFE(pts) | hold |
|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 | OPEN_REJECTION | short/SELL | 1.0 | 7688.75 -> 7685.5 | TP1_FULL | $16.25 | n/a (no_bar_coverage_for_hold_window) | n/a | 1.7m |
| 2026-08-31 | LEVEL_REJECT_LIVE | short/SELL | 1.0 | 7685.75 -> 7699.25 | BROKER_CLOSE | $-67.50 | 22.50 | 0.50 | 60.1m |
| 2026-09-02 | ERL_IRL_SWEEP_FVG | short/SELL | 1.0 | 7681.5 -> 7690.0 | FULL_STOP | $-42.50 | 6.25 | -3.50 | 13.1m |

## SIMULATED (mechanism only -- simulated fills are never edge evidence)

n=11 -- total_pnl=$-404.14 -- win_rate=0.6364

| date | setup | dir/side | qty | entry->exit | exit_reason | $pnl | MAE(pts) | MFE(pts) | hold |
|---|---|---|---|---|---|---|---|---|---|
| 2026-08-10 | OPEN_REJECTION | short/SELL | 1 | 7772.75 -> 7780.8 | FULL_STOP | $-41.49 | 16.00 | -3.75 | 20.0m |
| 2026-08-10 | ERL_IRL_SWEEP_FVG | short/SELL | 1 | 7772.5 -> 7772.0 | TP1_PARTIAL | $1.26 | 6.75 | 0.50 | 50.0m |
| 2026-08-10 | ERL_IRL_SWEEP_FVG | short/SELL | 1 | 7773.0 -> 7771.5 | TP1_PARTIAL | $6.26 | 4.25 | 3.25 | 25.0m |
| 2026-08-11 |  | short/SELL | 1 | 7774.5 -> 7774.0 | TP1_PARTIAL | $1.26 | 11.75 | 5.25 | 70.0m |
| 2026-08-11 |  | short/SELL | 1 | 7766.75 -> 7766.0 | TP1_PARTIAL | $2.51 | 2.25 | 1.75 | 5.0m |
| 2026-08-12 |  | short/SELL | 1 | 7771.25 -> 7771.0 | TP1_PARTIAL | $0.01 | 1.50 | -0.25 | 5.0m |
| 2026-08-12 |  | short/SELL | 1 | 7772.25 -> 7772.0 | TP1_PARTIAL | $0.01 | 1.00 | 0.50 | 5.0m |
| 2026-08-13 |  | short/SELL | 1 | 7803.0 -> 7816.75 | FULL_STOP | $-69.99 | 16.25 | 2.25 | 80.0m |
| 2026-08-31 |  | short/SELL | 1 | 7688.75 -> 7685.5 | TP1_PARTIAL | $15.01 | 6.25 | -2.25 | 5.0m |
| 2026-08-31 |  | short/SELL | 1 | 7682.0 -> 7694.3 | FULL_STOP | $-62.74 | 13.00 | -5.75 | 35.0m |
| 2026-09-01 |  | long/BUY | 1 | 7697.75 -> 7646.75 | FULL_STOP | $-256.24 | 56.75 | -49.50 | 5.0m |

## UNKNOWN (undisclosed -- data hygiene issue)

n=0 -- total_pnl=$0.00 -- win_rate=None

_no closed trips in this class_
