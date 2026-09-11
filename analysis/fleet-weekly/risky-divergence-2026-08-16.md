# Risky-vs-safes weekly divergence -- 2026-08-16

Window (sessions): 2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-14

One line per J's ask: how many trades did each risk arm take that the safes did not, and what did that cohort pay (REAL closed fills, FIFO).

## risky-1: took **22** trades the safes did not; that cohort paid **$-711.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|
| 2026-08-10T09:52 | SPY260810P00773000 | 5 | vwap_continuation | normal | BASE | $-440.00 |
| 2026-08-11T09:46 | SPY260811P00773000 | 5 | vwap_continuation | normal | BASE | $+0.00 |
| 2026-08-11T09:52 | SPY260811P00773000 | 5 | vwap_continuation | normal | BASE | $+0.00 |
| 2026-08-11T09:55 | SPY260811P00773000 | 5 | vwap_continuation | normal | BASE | $+0.00 |
| 2026-08-11T11:52 | SPY260811P00772000 | 5 | ribbon_ride | normal | BASE | $-85.00 |
| 2026-08-11T13:32 | SPY260811P00771000 | 5 | ribbon_ride | normal | BASE | $+121.00 |
| 2026-08-11T14:08 | SPY260811P00771000 | 5 | ribbon_ride | normal | BASE | $+121.00 |
| 2026-08-11T14:35 | SPY260811P00770000 | 5 | ribbon_ride | normal | BASE | $-145.00 |
| 2026-08-12T09:46 | SPY260812P00773000 | 5 | vwap_continuation | normal | BASE | $+15.00 |
| 2026-08-12T09:52 | SPY260812P00773000 | 5 | vwap_continuation | normal | BASE | $+15.00 |
| 2026-08-12T09:55 | SPY260812C00774000 | 5 | ribbon_ride | normal | ELITE | $-85.00 |
| 2026-08-12T09:58 | SPY260812P00772000 | 5 | vwap_continuation | normal | BASE | $-85.00 |
| 2026-08-12T10:00 | SPY260812P00773000 | 5 | vwap_continuation | normal | BASE | $+15.00 |
| 2026-08-12T10:03 | SPY260812P00772000 | 5 | vwap_continuation | normal | BASE | $-85.00 |
| 2026-08-12T10:05 | SPY260812C00773000 | 5 | ribbon_ride | normal | ELITE | $+22.00 |
| 2026-08-12T11:27 | SPY260812P00772000 | 5 | ribbon_ride | normal | BASE | $-85.00 |
| 2026-08-12T11:30 | SPY260812P00772000 | 5 | ribbon_ride | normal | BASE | $-85.00 |
| 2026-08-12T13:24 | SPY260812P00773000 | 5 | ribbon_ride | normal | BASE | $+15.00 |
| 2026-08-12T13:32 | SPY260812P00773000 | 5 | ribbon_ride | normal | BASE | $+15.00 |
| 2026-08-12T13:48 | SPY260812P00773000 | 5 | ribbon_ride | normal | BASE | $+15.00 |
| 2026-08-12T13:52 | SPY260812P00773000 | 5 | ribbon_ride | normal | BASE | $+15.00 |
| 2026-08-12T13:55 | SPY260812P00773000 | 5 | ribbon_ride | normal | BASE | $+15.00 |

## risky-3: took **14** trades the safes did not; that cohort paid **$-381.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|
| 2026-08-10T09:52 | SPY260810P00771000 | 8 | vwap_continuation | normal | BASE | $-8.00 |
| 2026-08-11T09:46 | SPY260811P00771000 | 10 | vwap_continuation | normal | BASE | $+96.00 |
| 2026-08-11T09:51 | SPY260811P00771000 | 8 | vwap_continuation | normal | BASE | $+96.00 |
| 2026-08-11T09:55 | SPY260811P00771000 | 10 | vwap_continuation | normal | BASE | $+96.00 |
| 2026-08-11T11:56 | SPY260811P00770000 | 10 | ribbon_ride | normal | BASE | $-53.00 |
| 2026-08-12T09:46 | SPY260812P00771000 | 8 | vwap_continuation | normal | BASE | $-16.00 |
| 2026-08-12T09:52 | SPY260812P00771000 | 8 | vwap_continuation | normal | BASE | $-16.00 |
| 2026-08-12T09:55 | SPY260812C00776000 | 10 | ribbon_ride | normal | ELITE | $-80.00 |
| 2026-08-12T09:58 | SPY260812P00770000 | 8 | vwap_continuation | normal | BASE | $-100.00 |
| 2026-08-12T10:00 | SPY260812P00771000 | 8 | vwap_continuation | normal | BASE | $-16.00 |
| 2026-08-12T10:03 | SPY260812P00770000 | 8 | vwap_continuation | normal | BASE | $-100.00 |
| 2026-08-12T10:05 | SPY260812C00775000 | 10 | ribbon_ride | normal | ELITE | $-90.00 |
| 2026-08-12T11:27 | SPY260812P00770000 | 10 | ribbon_ride | normal | BASE | $-100.00 |
| 2026-08-13T10:27 | SPY260813C00781000 | 10 | ribbon_ride | normal | ELITE | $-90.00 |

_Source: setup/scripts/full_send_vs_gated.py --weekly (Gamma_RiskyDivergenceWeekly). Real-fill P&L via fills_fifo (the same FIFO fleet_arm_replay anchors against). Core-safe counting is extra_exec-aware (L244)._
