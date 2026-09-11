# Risky-vs-safes weekly divergence -- 2026-08-09

Window (sessions): 2026-08-03, 2026-08-04, 2026-08-05, 2026-08-06, 2026-08-07

One line per J's ask: how many trades did each risk arm take that the safes did not, and what did that cohort pay (REAL closed fills, FIFO).

## risky-1: took **9** trades the safes did not; that cohort paid **$-1217.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|
| 2026-08-04T09:46 | SPY260804C00762000 | 5 | vwap_continuation | normal | BASE | $-75.00 |
| 2026-08-04T09:50 | SPY260804C00763000 | 5 | vwap_continuation | normal | BASE | $+640.00 |
| 2026-08-05T09:58 | SPY260805C00776000 | 5 | vwap_continuation | normal | BASE | $-485.00 |
| 2026-08-05T10:06 | SPY260805C00776000 | 5 | vwap_continuation | normal | BASE | $-485.00 |
| 2026-08-05T10:10 | SPY260805C00776000 | 5 | vwap_continuation | normal | BASE | $-485.00 |
| 2026-08-05T10:14 | SPY260805C00776000 | 5 | vwap_continuation | normal | BASE | $-485.00 |
| 2026-08-05T10:18 | SPY260805C00776000 | 5 | vwap_continuation | normal | BASE | $-485.00 |
| 2026-08-05T11:48 | SPY260805P00772000 | 5 | ribbon_ride | normal | BASE | $+347.00 |
| 2026-08-06T10:32 | SPY260806P00770000 | 5 | ribbon_ride | normal | BASE | $+296.00 |

## risky-3: took **13** trades the safes did not; that cohort paid **$-3376.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|
| 2026-08-04T09:46 | SPY260804C00762000 | 8 | vwap_continuation | normal | BASE | $-104.00 |
| 2026-08-04T09:50 | SPY260804C00763000 | 8 | vwap_continuation | normal | BASE | $+340.00 |
| 2026-08-04T09:54 | SPY260804C00763000 | 8 | vwap_continuation | normal | BASE | $+340.00 |
| 2026-08-04T09:57 | SPY260804C00763000 | 8 | vwap_continuation | normal | BASE | $+340.00 |
| 2026-08-04T10:35 | SPY260804C00765000 | 8 | vwap_continuation | normal | BASE | $-80.00 |
| 2026-08-05T09:58 | SPY260805C00776000 | 8 | vwap_continuation | normal | BASE | $-794.00 |
| 2026-08-05T10:06 | SPY260805C00776000 | 8 | vwap_continuation | normal | BASE | $-794.00 |
| 2026-08-05T10:10 | SPY260805C00776000 | 8 | vwap_continuation | normal | BASE | $-794.00 |
| 2026-08-05T10:14 | SPY260805C00776000 | 8 | vwap_continuation | normal | BASE | $-794.00 |
| 2026-08-05T10:18 | SPY260805C00776000 | 8 | vwap_continuation | normal | BASE | $-794.00 |
| 2026-08-05T11:48 | SPY260805P00772000 | 8 | ribbon_ride | normal | BASE | $-664.00 |
| 2026-08-06T10:32 | SPY260806P00770000 | 8 | ribbon_ride | normal | BASE | $+830.00 |
| 2026-08-07T12:40 | SPY260807C00774000 | 12 | ribbon_ride | normal | ELITE | $-408.00 |

_Source: setup/scripts/full_send_vs_gated.py --weekly (Gamma_RiskyDivergenceWeekly). Real-fill P&L via fills_fifo (the same FIFO fleet_arm_replay anchors against). Core-safe counting is extra_exec-aware (L244)._
