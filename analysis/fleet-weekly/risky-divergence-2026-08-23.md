# Risky-vs-safes weekly divergence -- 2026-08-23

Window (sessions): 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21

One line per J's ask: how many trades did each risk arm take that the safes did not, and what did that cohort pay (REAL closed fills, FIFO).

## risky-1: took **0** trades the safes did not; that cohort paid **$+0.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|

## risky-3: took **9** trades the safes did not; that cohort paid **$-181.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|
| 2026-08-17T09:53 | SPY260817P00776000 | 8 | vwap_reclaim_failed_break | normal | BASE | $-136.00 |
| 2026-08-17T09:56 | SPY260817P00776000 | 8 | vwap_reclaim_failed_break | normal | BASE | $-136.00 |
| 2026-08-17T10:23 | SPY260817P00775000 | 8 | vwap_reclaim_failed_break | normal | BASE | $-64.00 |
| 2026-08-19T10:43 | SPY260819C00773000 | 10 | ribbon_ride | normal | ELITE | $-60.00 |
| 2026-08-19T11:51 | SPY260819C00772000 | 10 | ribbon_ride | normal | ELITE | $-90.00 |
| 2026-08-20T13:16 | SPY260820P00764000 | 10 | ribbon_ride | normal | BASE | $+190.00 |
| 2026-08-20T14:03 | SPY260820P00763000 | 10 | ribbon_ride | normal | BASE | $+180.00 |
| 2026-08-21T09:52 | SPY260821P00763000 | 5 | ribbon_ride | normal | BASE | $-85.00 |
| 2026-08-21T11:40 | SPY260821C00768000 | 10 | ribbon_ride | normal | ELITE | $+20.00 |

_Source: setup/scripts/full_send_vs_gated.py --weekly (Gamma_RiskyDivergenceWeekly). Real-fill P&L via fills_fifo (the same FIFO fleet_arm_replay anchors against). Core-safe counting is extra_exec-aware (L244)._
