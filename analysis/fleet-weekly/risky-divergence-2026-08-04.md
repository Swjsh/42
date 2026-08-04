# Risky-vs-safes weekly divergence -- 2026-08-04

Window (sessions): 2026-07-28, 2026-07-29, 2026-07-30, 2026-07-31, 2026-08-03

One line per J's ask: how many trades did each risk arm take that the safes did not, and what did that cohort pay (REAL closed fills, FIFO).

## risky-1: took **0** trades the safes did not; that cohort paid **$+0.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|

## risky-3: took **4** trades the safes did not; that cohort paid **$-229.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|
| 2026-07-30T11:34 | SPY260730P00733000 | 5 | ribbon_ride | normal | BASE | $-165.00 |
| 2026-07-30T11:43 | SPY260730P00734000 | 5 | ribbon_ride | normal | BASE | $-110.00 |
| 2026-07-31T12:19 | SPY260731C00746000 | 5 | ribbon_ride | normal | ELITE | $+126.00 |
| 2026-07-31T13:25 | SPY260731C00747000 | 5 | ribbon_ride | normal | ELITE | $-80.00 |

_Source: setup/scripts/full_send_vs_gated.py --weekly (Gamma_RiskyDivergenceWeekly). Real-fill P&L via fills_fifo (the same FIFO fleet_arm_replay anchors against). Core-safe counting is extra_exec-aware (L244)._
