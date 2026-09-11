# Risky-vs-safes weekly divergence -- 2026-09-06

Window (sessions): 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28

One line per J's ask: how many trades did each risk arm take that the safes did not, and what did that cohort pay (REAL closed fills, FIFO).

## risky-1: took **0** trades the safes did not; that cohort paid **$+0.00**

| minute | symbol | qty | strategy | lane | quality | real P&L |
|---|---|---|---|---|---|---|

_Source: setup/scripts/full_send_vs_gated.py --weekly (Gamma_RiskyDivergenceWeekly). Real-fill P&L via fills_fifo (the same FIFO fleet_arm_replay anchors against). Core-safe counting is extra_exec-aware (L244)._
