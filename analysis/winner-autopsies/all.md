# Winner autopsy — all winners to date

_Generated 2026-09-10T16:27:17.947886 ET · real OPRA 1-min bars · entry+1 convention · $0 (pure Python)._

> **DESCRIPTIVE ONLY.** This report measures; it ratifies nothing. Every exit variant below is a replay, not a proposal. Any change to a live exit knob requires its own pre-registered A/B — a good-looking number on a small winner population is an anecdote, not evidence.

## Capture rate — how much of what our winners offered did we keep?

- **CAPTURE (honest headline): 90.1%** of the best single fixed policy, over **n=106** winners.
  - Realized (broker fills): **$24,318.00**
  - Best single fixed policy: `hold_to_time_stop` → $26,978.50
- Disclosure — *hindsight shape-picking* (best variant chosen per trade, NOT live-selectable): 42.5% of $57,205.53.
- Disclosure — *oracle* (sell 100% at the post-entry high; no live rule can do this): 28.3% of $85,903.00.

**⚠ WINNERS-ONLY SAMPLE — this is NOT a policy comparison.** Every number here is computed over trades that ALREADY WON. That conditions on the outcome: a policy's column total answers 'what would this policy have made on the trades our current exits happened to win', NOT 'what would this policy make'. Switching policy changes which trades win at all, and says nothing about its effect on the losers — which vastly outnumber these. A capture rate above 100% therefore means our shipped exits top this menu ON WINNERS; it is NOT evidence that the menu's runner-up should be adopted, and a capture rate below 100% is NOT evidence that it should. Only a pre-registered A/B over the FULL trade population can support an exit change.

## The runner question (J 2026-07-31: "stay in longer, or get better exits?")

- **34 of 54** scaled-out winners had the RUNNER realize a **lower price than TP1** — the runner leg, which exists to capture the upside, came out worse than the leg that took profit early.
- **14 of 54** gave back ≥25% of the premium the runner had already reached.
- **Median runner-leg giveback: 19.7%** of its own peak (n=54 runner legs).

_This is a DESCRIPTIVE recurrence, not a mandate. Note the two answers point in opposite directions: the giveback is real, but the 'just hold longer' policies (`trail_only_no_tp1` / `hold_to_time_stop`) are usually the WORST column in the table above. 'Exit better' and 'stay in longer' are different hypotheses and only the first is supported here — both need their own pre-registered A/B over the full population before anything is armed._
- Attribution coverage: 88.1% of exit legs matched to an engine stage (22/185 unattributed and shown as `?`).

### Fixed-policy totals over the same winners

| Policy | Total P&L | vs realized |
|---|---:|---:|
| **(shipped, realized)** | **$24,318.00** | — |
| `hold_to_time_stop` | $26,978.50 | $2,660.50 |
| `all_out_at_tp1_100` | $21,019.50 | $-3,298.50 |
| `tp1_100_trail_10` | $20,778.90 | $-3,539.10 |
| `tp1_100_trail_20` | $20,419.70 | $-3,898.30 |
| `all_out_at_tp1_50` | $13,365.00 | $-10,953.00 |
| `tp1_30_trail_125` | $9,494.55 | $-14,823.45 |
| `trail_only_no_tp1` | $4,963.00 | $-19,355.00 |

_Every policy above is live-executable: each is a replay through the real `exit_manager.plan_exit_actions` on real 1-min OPRA bars. The menu is declared once in `EXIT_MENU` and is never fitted per-run._

### Capture by ENTRY WAVE — which impulse leaked the money?

| # | wave | ET | arms | n | realized | best fixed policy | that policy | capture | ORACLE (unreachable) |
|---:|---|---|---|---:|---:|---|---:|---:|---:|
| 1 | `742C` | 11:49:02–11:49:02 | 2 | 2 | $797.00 | `tp1_100_trail_20` | $411.00 | 193.9% | $1,469.00 |
| 2 | `740C` | 12:51:14–12:51:14 | 1 | 1 | $290.00 | `tp1_100_trail_10` | $261.60 | 110.9% | $425.00 |
| 3 | `753C` | 11:34:26–11:34:26 | 1 | 1 | $8.00 | `trail_only_no_tp1` | $8.00 | 100.0% | $112.00 |
| 4 | `741/750C` | 17:36:34–11:07:02 | 2 | 4 | $39.00 | `all_out_at_tp1_50` | $119.00 | 32.8% | $405.00 |
| 5 | `746C` | 13:01:03–13:01:03 | 1 | 1 | $241.00 | `hold_to_time_stop` | $474.00 | 50.8% | $930.00 |
| 6 | `743/745C` | 13:51:21–14:12:28 | 3 | 4 | $547.00 | `all_out_at_tp1_100` | $493.00 | 110.9% | $1,510.00 |
| 7 | `734/741C` | 17:50:25–10:04:48 | 3 | 3 | $202.00 | `all_out_at_tp1_100` | $1,120.50 | 18.0% | $3,550.00 |
| 8 | `740/746/747/754C` | 14:34:47–09:42:03 | 3 | 8 | $1,821.00 | `hold_to_time_stop` | $5,519.00 | 33.0% | $10,340.00 |
| 9 | `757/763C` | 17:21:50–09:58:05 | 5 | 6 | $2,602.00 | `hold_to_time_stop` | $20,088.00 | 13.0% | $21,852.00 |
| 10 | `769C` | 11:52:08–12:28:04 | 4 | 4 | $2,192.00 | `hold_to_time_stop` | $3,394.00 | 64.6% | $4,914.00 |
| 11 | `770/771/772/773/775C` | 13:24:07–09:46:06 | 4 | 9 | $2,405.00 | `all_out_at_tp1_100` | $1,361.50 | 176.6% | $7,272.00 |
| 12 | `771C` | 13:44:03–13:44:03 | 1 | 1 | $195.00 | `all_out_at_tp1_100` | $147.00 | 132.7% | $372.00 |
| 13 | `770/771/773C` | 13:31:05–09:58:05 | 3 | 7 | $714.00 | `trail_only_no_tp1` | $200.00 | 357.0% | $2,080.00 |
| 14 | `772C` | 09:58:05–11:26:04 | 2 | 2 | $20.00 | `tp1_30_trail_125` | $176.90 | 11.3% | $243.00 |
| 15 | `773C` | 09:46:04–09:46:04 | 1 | 2 | $15.00 | `trail_only_no_tp1` | $-15.00 | n/a | $415.00 |
| 16 | `773/777/779C` | 10:04:05–09:52:04 | 5 | 7 | $2,152.00 | `tp1_100_trail_10` | $1,841.90 | 116.8% | $3,784.00 |
| 17 | `775/777C` | 09:51:03–13:06:04 | 4 | 4 | $892.00 | `all_out_at_tp1_100` | $1,078.00 | 82.8% | $1,827.00 |
| 18 | `768/770C` | 14:36:03–11:50:05 | 4 | 5 | $863.00 | `all_out_at_tp1_50` | $920.00 | 93.8% | $1,847.00 |
| 19 | `771C` | 10:42:05–10:42:05 | 1 | 1 | $3.00 | `trail_only_no_tp1` | $3.00 | 100.0% | $36.00 |
| 20 | `766C` | 12:56:03–12:56:03 | 1 | 1 | $191.00 | `hold_to_time_stop` | $639.00 | 29.9% | $933.00 |
| 21 | `764C` | 12:57:05–13:16:05 | 2 | 2 | $280.00 | `hold_to_time_stop` | $765.00 | 36.6% | $2,340.00 |
| 22 | `763/765/766/768C` | 14:01:04–11:07:05 | 5 | 7 | $1,170.00 | `all_out_at_tp1_50` | $1,267.50 | 92.3% | $2,568.00 |
| 23 | `766C` | 11:07:05–11:07:05 | 2 | 2 | $40.00 | `trail_only_no_tp1` | $48.00 | 83.3% | $352.00 |
| 24 | `766/768/770C` | 14:57:06–09:42:05 | 5 | 6 | $1,117.00 | `tp1_100_trail_10` | $2,677.20 | 41.7% | $5,006.00 |
| 25 | `770/772C` | 11:52:06–11:51:04 | 3 | 3 | $815.00 | `all_out_at_tp1_100` | $1,089.00 | 74.8% | $1,361.00 |
| 26 | `771/773C` | 12:31:03–10:22:05 | 4 | 5 | $2,433.00 | `tp1_100_trail_20` | $2,743.60 | 88.7% | $4,145.00 |
| 27 | `762/767/770/772/774C` | 13:21:03–11:21:04 | 4 | 8 | $2,274.00 | `hold_to_time_stop` | $2,875.00 | 79.1% | $5,815.00 |

_A wave = every arm's entry into ONE impulse (new wave after a >15-minute gap). The per-wave `best fixed policy` is a HINDSIGHT pick over a handful of positions — it localises WHERE capture leaked, it does not nominate a shape. The ORACLE column is the sell-everything-at-the-high bound: **unreachable by any live rule**, printed only to size the universe, and never a target._

## Per-winner anatomy

### 2026-07-02 · safe-1 · `SPY260702P00742000` · realized $306.00

- **Entry** 11:49:02 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE)_
- **Strike** 742 (trigger None, offset None), quoted premium 0.49, filled **0.5** × 3, stop `?`.
- **Entry fill quality** — paid 6.4% above the signal minute's low (bar 0.47–0.61).
- **High-water WHILE IN THE TRADE** 2.24 (348.0% vs entry) at 2026-07-02T17:04:00Z UTC · 25 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.33 (366.0%) at 2026-07-02T17:05:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:58:03 | 2 | 1.32 | 164.0% | `tp1` | 1.38 | $12.00 (4.3%) |
  | 13:04:03 | 1 | 1.92 | 284.0% | `runner_target` | 2.24 | $32.00 (14.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:52:02 | 3 | 0.63 | 0.62 | no | 0.424 | — |
  | 11:55:03 | 3 | 0.61 | 0.6 | no | 0.424 | — |
  | 11:58:02 | 3 | 0.73 | 0.68 | no | 0.424 | — |
  | 12:01:02 | 3 | 0.68 | 0.67 | no | 0.424 | — |
  | 12:04:02 | 3 | 0.77 | 0.76 | no | 0.424 | — |
  | 12:07:02 | 3 | 0.76 | 0.75 | no | 0.424 | — |
  | 12:10:02 | 3 | 0.79 | 0.74 | no | 0.424 | — |
  | 12:13:02 | 3 | 0.54 | 0.53 | no | 0.424 | — |
  | 12:16:02 | 3 | 0.6 | 0.59 | no | 0.424 | — |
  | 12:19:02 | 3 | 0.65 | 0.64 | no | 0.424 | — |
  | 12:22:02 | 3 | 0.8 | 0.79 | no | 0.424 | — |
  | 12:25:02 | 3 | 0.81 | 0.8 | no | 0.424 | — |
  | 12:28:02 | 3 | 0.76 | 0.75 | no | 0.424 | — |
  | 12:31:02 | 3 | 0.87 | 0.86 | no | 0.424 | — |
  | 12:34:02 | 3 | 0.93 | 0.92 | no | 0.424 | — |
  | 12:37:02 | 3 | 1.02 | 1.01 | no | 0.424 | — |
  | 12:40:02 | 3 | 1.05 | 1.0 | no | 0.424 | — |
  | 12:43:02 | 3 | 0.97 | 0.95 | no | 0.424 | — |
  | 12:46:02 | 3 | 0.93 | 0.92 | no | 0.424 | — |
  | 12:49:02 | 3 | 0.85 | 0.83 | no | 0.424 | — |
  | 12:52:02 | 3 | 0.88 | 0.87 | no | 0.424 | — |
  | 12:55:02 | 3 | 0.97 | 0.96 | no | 0.424 | — |
  | 12:58:02 | 3 | 1.35 | 1.33 | yes | 0.53 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +150%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:01:02 | 1 | 1.34 | 1.32 | yes | 0.53 | — |
  | 13:04:02 | 1 | 1.96 | 1.93 | yes | 0.53 | **SELL_ALL 1 `runner_target`** (runner_target @ +250%) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_20` at $154.00 (realized $306.00, delta $-152.00); oracle $549.00.
- **Parity control** — this trade's own as-placed shape, replayed: $275.00 vs $306.00 realized (gap $-31.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$306.00** |
  | `tp1_100_trail_20` | $154.00 |
  | `all_out_at_tp1_100` | $150.00 |
  | `tp1_100_trail_10` | $145.40 |
  | `all_out_at_tp1_50` | $75.00 |
  | `trail_only_no_tp1` | $66.00 |
  | `tp1_30_trail_125` | $43.00 |
  | `hold_to_time_stop` | $-75.00 |

### 2026-07-02 · risky-3 · `SPY260702P00742000` · realized $491.00

- **Entry** 11:49:02 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE)_
- **Strike** 742 (trigger None, offset None), quoted premium 0.52, filled **0.49** × 5, stop `?`.
- **Entry fill quality** — paid 4.3% above the signal minute's low (bar 0.47–0.61).
- **High-water WHILE IN THE TRADE** 2.33 (375.5% vs entry) at 2026-07-02T17:05:00Z UTC · 40 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.33 (375.5%) at 2026-07-02T17:05:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:58:05 | 4 | 1.36 | 177.6% | `tp1` | 1.38 | $8.00 (1.5%) |
  | 13:49:04 | 1 | 1.92 | 291.8% | `runner_target` | 2.33 | $41.00 (17.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:52:02 | 5 | 0.63 | 0.58 | no | 0.44 | — |
  | 11:55:03 | 5 | 0.62 | 0.61 | no | 0.44 | — |
  | 11:58:02 | 5 | 0.72 | 0.67 | no | 0.44 | — |
  | 12:01:02 | 5 | 0.69 | 0.64 | no | 0.44 | — |
  | 12:04:02 | 5 | 0.76 | 0.71 | no | 0.44 | — |
  | 12:07:02 | 5 | 0.74 | 0.73 | no | 0.44 | — |
  | 12:10:02 | 5 | 0.79 | 0.74 | no | 0.44 | — |
  | 12:13:02 | 5 | 0.58 | 0.53 | no | 0.44 | — |
  | 12:16:02 | 5 | 0.59 | 0.58 | no | 0.44 | — |
  | 12:19:02 | 5 | 0.66 | 0.61 | no | 0.44 | — |
  | 12:22:02 | 5 | 0.75 | 0.74 | no | 0.44 | — |
  | 12:25:02 | 5 | 0.8 | 0.75 | no | 0.44 | — |
  | 12:28:02 | 5 | 0.76 | 0.75 | no | 0.44 | — |
  | 12:31:02 | 5 | 0.92 | 0.91 | no | 0.44 | — |
  | 12:34:02 | 5 | 0.93 | 0.92 | no | 0.44 | — |
  | 12:37:02 | 5 | 1.02 | 1.01 | no | 0.44 | — |
  | 12:40:02 | 5 | 1.09 | 1.04 | no | 0.44 | — |
  | 12:43:02 | 5 | 0.95 | 0.9 | no | 0.44 | — |
  | 12:46:02 | 5 | 0.91 | 0.9 | no | 0.44 | — |
  | 12:49:02 | 5 | 0.87 | 0.86 | no | 0.44 | — |
  | 12:52:02 | 5 | 0.88 | 0.87 | no | 0.44 | — |
  | 12:55:02 | 5 | 0.94 | 0.93 | no | 0.44 | — |
  | 12:58:02 | 5 | 1.41 | 1.35 | yes | 0.55 | **SELL_PARTIAL 4 `tp1`** (tp1 @ +150%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:01:02 | 1 | 1.34 | 1.28 | yes | 0.55 | — |
  | 13:04:02 | 1 | 1.92 | 1.89 | yes | 0.55 | — |
  | 13:07:02 | 1 | 1.39 | 1.38 | yes | 0.55 | — |
  | 13:10:02 | 1 | 1.55 | 1.53 | yes | 0.55 | — |
  | 13:13:02 | 1 | 1.66 | 1.64 | yes | 0.55 | — |
  | 13:16:02 | 1 | 1.38 | 1.32 | yes | 0.55 | — |
  | 13:19:02 | 1 | 1.42 | 1.41 | yes | 0.55 | — |
  | 13:22:02 | 1 | 1.37 | 1.36 | yes | 0.55 | — |
  | 13:25:02 | 1 | 1.59 | 1.58 | yes | 0.55 | — |
  | 13:28:02 | 1 | 1.56 | 1.53 | yes | 0.55 | — |
  | 13:31:02 | 1 | 1.29 | 1.28 | yes | 0.55 | — |
  | 13:34:02 | 1 | 1.28 | 1.27 | yes | 0.55 | — |
  | 13:37:02 | 1 | 1.78 | 1.72 | yes | 0.55 | — |
  | 13:40:02 | 1 | 1.88 | 1.86 | yes | 0.55 | — |
  | 13:43:02 | 1 | 1.7 | 1.69 | yes | 0.55 | — |
  | 13:46:02 | 1 | 1.77 | 1.71 | yes | 0.55 | — |
  | 13:49:02 | 1 | 1.97 | 1.96 | yes | 0.55 | **SELL_ALL 1 `runner_target`** (runner_target @ +250%) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_20` at $257.00 (realized $491.00, delta $-234.00); oracle $920.00.
- **Parity control** — this trade's own as-placed shape, replayed: $416.50 vs $491.00 realized (gap $-74.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$491.00** |
  | `tp1_100_trail_20` | $257.00 |
  | `all_out_at_tp1_100` | $245.00 |
  | `tp1_100_trail_10` | $239.80 |
  | `all_out_at_tp1_50` | $122.50 |
  | `trail_only_no_tp1` | $115.00 |
  | `tp1_30_trail_125` | $72.80 |
  | `hold_to_time_stop` | $-122.50 |

### 2026-07-02 · bold-2 · `SPY260702P00740000` · realized $290.00

- **Entry** 12:51:14 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.42** × 5, stop `?`.
- **Entry fill quality** — paid 13.5% above the signal minute's low (bar 0.37–0.47).
- **High-water WHILE IN THE TRADE** 1.27 (202.4% vs entry) at 2026-07-02T17:05:00Z UTC · 78 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.27 (202.4%) at 2026-07-02T17:05:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:05:06 | 4 | 1.16 | 176.2% | `tp1` | 1.27 | $44.00 (8.7%) |
  | 14:09:05 | 1 | 0.36 | -14.3% | `be_stop` | 1.27 | $91.00 (71.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 12:52:09 | 5 | 0.42 | 0.37 | no | 0.344 | — |
  | 12:53:19 | 5 | 0.38 | 0.37 | no | 0.344 | — |
  | 12:54:18 | 5 | 0.36 | 0.35 | no | 0.344 | — |
  | 12:55:38 | 5 | 0.5 | 0.49 | no | 0.344 | — |
  | 12:56:04 | 5 | 0.55 | 0.5 | no | 0.344 | — |
  | 12:57:05 | 5 | 0.62 | 0.61 | no | 0.344 | — |
  | 12:58:05 | 5 | 0.63 | 0.62 | no | 0.344 | — |
  | 12:59:04 | 5 | 0.55 | 0.54 | no | 0.344 | — |
  | 13:00:05 | 5 | 0.57 | 0.56 | no | 0.344 | — |
  | 13:01:05 | 5 | 0.63 | 0.58 | no | 0.344 | — |
  | 13:02:04 | 5 | 0.71 | 0.7 | no | 0.344 | — |
  | 13:03:04 | 5 | 0.79 | 0.78 | no | 0.344 | — |
  | 13:04:05 | 5 | 1.05 | 1.04 | no | 0.344 | — |
  | 13:05:05 | 5 | 1.15 | 1.14 | yes | 0.43 | **SELL_PARTIAL 4 `tp1`** (tp1 @ +150%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:06:05 | 1 | 0.98 | 0.93 | yes | 0.43 | — |
  | 13:07:05 | 1 | 0.69 | 0.68 | yes | 0.43 | — |
  | 13:08:04 | 1 | 0.81 | 0.8 | yes | 0.43 | — |
  | 13:09:05 | 1 | 0.71 | 0.66 | yes | 0.43 | — |
  | 13:10:05 | 1 | 0.74 | 0.69 | yes | 0.43 | — |
  | 13:11:04 | 1 | 0.83 | 0.78 | yes | 0.43 | — |
  | 13:12:05 | 1 | 0.8 | 0.75 | yes | 0.43 | — |
  | 13:13:04 | 1 | 0.77 | 0.76 | yes | 0.43 | — |
  | 13:14:04 | 1 | 0.7 | 0.69 | yes | 0.43 | — |
  | 13:15:05 | 1 | 0.73 | 0.72 | yes | 0.43 | — |
  | 13:16:04 | 1 | 0.61 | 0.6 | yes | 0.43 | — |
  | 13:17:04 | 1 | 0.55 | 0.5 | yes | 0.43 | — |
  | 13:18:04 | 1 | 0.7 | 0.69 | yes | 0.43 | — |
  | 13:19:04 | 1 | 0.69 | 0.64 | yes | 0.43 | — |
  | 13:20:05 | 1 | 0.76 | 0.75 | yes | 0.43 | — |
  | 13:21:04 | 1 | 0.71 | 0.7 | yes | 0.43 | — |
  | 13:22:04 | 1 | 0.65 | 0.6 | yes | 0.43 | — |
  | 13:23:04 | 1 | 0.72 | 0.71 | yes | 0.43 | — |
  | 13:24:05 | 1 | 0.71 | 0.7 | yes | 0.43 | — |
  | 13:25:04 | 1 | 0.75 | 0.74 | yes | 0.43 | — |
  | 13:26:04 | 1 | 0.72 | 0.71 | yes | 0.43 | — |
  | 13:27:05 | 1 | 0.73 | 0.72 | yes | 0.43 | — |
  | 13:28:04 | 1 | 0.72 | 0.71 | yes | 0.43 | — |
  | 13:29:04 | 1 | 0.67 | 0.66 | yes | 0.43 | — |
  | 13:30:05 | 1 | 0.67 | 0.66 | yes | 0.43 | — |
  | 13:31:04 | 1 | 0.6 | 0.55 | yes | 0.43 | — |
  | 13:32:04 | 1 | 0.61 | 0.6 | yes | 0.43 | — |
  | 13:33:05 | 1 | 0.57 | 0.56 | yes | 0.43 | — |
  | 13:34:04 | 1 | 0.51 | 0.5 | yes | 0.43 | — |
  | 13:35:05 | 1 | 0.65 | 0.64 | yes | 0.43 | — |
  | 13:36:04 | 1 | 0.71 | 0.66 | yes | 0.43 | — |
  | 13:37:04 | 1 | 0.83 | 0.82 | yes | 0.43 | — |
  | 13:38:04 | 1 | 0.82 | 0.77 | yes | 0.43 | — |
  | 13:39:04 | 1 | 0.8 | 0.79 | yes | 0.43 | — |
  | 13:40:04 | 1 | 0.82 | 0.81 | yes | 0.43 | — |
  | 13:41:04 | 1 | 0.83 | 0.82 | yes | 0.43 | — |
  | 13:42:04 | 1 | 0.79 | 0.78 | yes | 0.43 | — |
  | 13:43:05 | 1 | 0.74 | 0.73 | yes | 0.43 | — |
  | 13:44:04 | 1 | 0.68 | 0.67 | yes | 0.43 | — |
  | 13:45:05 | 1 | 0.75 | 0.7 | yes | 0.43 | — |
  | 13:46:05 | 1 | 0.81 | 0.76 | yes | 0.43 | — |
  | 13:47:05 | 1 | 0.86 | 0.85 | yes | 0.43 | — |
  | 13:48:04 | 1 | 1.05 | 1.04 | yes | 0.43 | — |
  | 13:49:04 | 1 | 0.87 | 0.86 | yes | 0.43 | — |
  | 13:50:04 | 1 | 0.91 | 0.9 | yes | 0.43 | — |
  | 13:51:04 | 1 | 0.98 | 0.97 | yes | 0.43 | — |
  | 13:52:04 | 1 | 0.89 | 0.88 | yes | 0.43 | — |
  | 13:53:04 | 1 | 0.83 | 0.82 | yes | 0.43 | — |
  | 13:54:09 | 1 | 0.76 | 0.75 | yes | 0.43 | — |
  | 13:55:15 | 1 | 0.73 | 0.68 | yes | 0.43 | — |
  | 13:56:04 | 1 | 0.81 | 0.8 | yes | 0.43 | — |
  | 13:57:04 | 1 | 0.88 | 0.83 | yes | 0.43 | — |
  | 13:58:05 | 1 | 0.89 | 0.88 | yes | 0.43 | — |
  | 13:59:04 | 1 | 1.1 | 1.09 | yes | 0.43 | — |
  | 14:00:05 | 1 | 1.04 | 1.03 | yes | 0.43 | — |
  | 14:01:05 | 1 | 0.92 | 0.9 | yes | 0.43 | — |
  | 14:02:15 | 1 | 0.89 | 0.84 | yes | 0.43 | — |
  | 14:03:05 | 1 | 0.88 | 0.87 | yes | 0.43 | — |
  | 14:04:13 | 1 | 0.79 | 0.74 | yes | 0.43 | — |
  | 14:05:10 | 1 | 0.69 | 0.68 | yes | 0.43 | — |
  | 14:06:04 | 1 | 0.48 | 0.47 | yes | 0.43 | — |
  | 14:07:05 | 1 | 0.46 | 0.45 | yes | 0.43 | — |
  | 14:08:04 | 1 | 0.45 | 0.44 | yes | 0.43 | — |
  | 14:09:04 | 1 | 0.4 | 0.39 | yes | 0.43 | **SELL_ALL 1 `be_stop`** (runner_stop @ 0.43) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $261.60 (realized $290.00, delta $-28.40); oracle $425.00.
- **Parity control** — this trade's own as-placed shape, replayed: $37.80 vs $290.00 realized (gap $-252.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$290.00** |
  | `tp1_100_trail_10` | $261.60 |
  | `tp1_100_trail_20` | $237.20 |
  | `all_out_at_tp1_100` | $210.00 |
  | `all_out_at_tp1_50` | $105.00 |
  | `tp1_30_trail_125` | $62.65 |
  | `trail_only_no_tp1` | $25.00 |
  | `hold_to_time_stop` | $-105.00 |

### 2026-07-06 · safe-2 · `SPY260706P00750000` · realized $9.00

- **Entry** ? ET — `?` (?), quality **?**, trigger **None**, risk `None`.
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.54** × 3, stop `?`.
- **Entry fill quality** — paid 17.4% above the signal minute's low (bar 0.46–0.59).
- **High-water WHILE IN THE TRADE** 0.6 (11.1% vs entry) at 2026-07-06T17:37:00Z UTC · 5 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.92 (70.4%) at 2026-07-06T17:42:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:37:27 | 2 | 0.57 | 5.6% | `?` | 0.6 | $6.00 (5.0%) |
  | 13:37:28 | 1 | 0.57 | 5.6% | `?` | 0.6 | $3.00 (5.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:37:27 | 3 | 0.59 | 0.58 | no | 0.5428 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:38:27 | 3 | 0.53 | 0.52 | no | 0.506 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:39:27 | 3 | 0.56 | 0.55 | no | 0.4968 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:40:27 | 3 | 0.57 | 0.56 | no | 0.4876 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:41:27 | 3 | 0.6 | 0.59 | no | 0.5704 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $81.00 (realized $9.00, delta $72.00); oracle $114.00.
- **Parity control** — this trade's own as-placed shape, replayed: $32.40 vs $9.00 realized (gap $23.40 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$9.00** |
  | `all_out_at_tp1_50` | $81.00 |
  | `tp1_30_trail_125` | $58.90 |
  | `trail_only_no_tp1` | $0.00 |
  | `all_out_at_tp1_100` | $-81.00 |
  | `tp1_100_trail_20` | $-81.00 |
  | `tp1_100_trail_10` | $-81.00 |
  | `hold_to_time_stop` | $-81.00 |

### 2026-07-06 · safe-2 · `SPY260706P00750000` · realized $9.00

- **Entry** ? ET — `?` (?), quality **?**, trigger **None**, risk `None`.
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.5** × 3, stop `?`.
- **Entry fill quality** — paid 8.7% above the signal minute's low (bar 0.46–0.54).
- **High-water WHILE IN THE TRADE** 0.54 (8.0% vs entry) at 2026-07-06T17:39:00Z UTC · 5 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.92 (84.0%) at 2026-07-06T17:42:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:39:27 | 3 | 0.53 | 6.0% | `ribbon_flip` | 0.54 | $3.00 (1.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:37:27 | 3 | 0.59 | 0.58 | no | 0.5428 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:38:27 | 3 | 0.53 | 0.52 | no | 0.506 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:39:27 | 3 | 0.56 | 0.55 | no | 0.4968 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:40:27 | 3 | 0.57 | 0.56 | no | 0.4876 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:41:27 | 3 | 0.6 | 0.59 | no | 0.5704 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $75.00 (realized $9.00, delta $66.00); oracle $126.00.
- **Parity control** — this trade's own as-placed shape, replayed: $30.00 vs $9.00 realized (gap $21.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$9.00** |
  | `all_out_at_tp1_50` | $75.00 |
  | `tp1_30_trail_125` | $60.50 |
  | `trail_only_no_tp1` | $3.00 |
  | `all_out_at_tp1_100` | $-75.00 |
  | `tp1_100_trail_20` | $-75.00 |
  | `tp1_100_trail_10` | $-75.00 |
  | `hold_to_time_stop` | $-75.00 |

### 2026-07-06 · safe-2 · `SPY260706P00750000` · realized $6.00

- **Entry** ? ET — `?` (?), quality **?**, trigger **None**, risk `None`.
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.52** × 3, stop `?`.
- **Entry fill quality** — paid 13.0% above the signal minute's low (bar 0.46–0.54).
- **High-water WHILE IN THE TRADE** 0.61 (17.3% vs entry) at 2026-07-06T17:40:00Z UTC · 5 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.92 (76.9%) at 2026-07-06T17:42:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:40:28 | 3 | 0.54 | 3.9% | `ribbon_flip` | 0.61 | $21.00 (11.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:37:27 | 3 | 0.59 | 0.58 | no | 0.5428 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:38:27 | 3 | 0.53 | 0.52 | no | 0.506 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:39:27 | 3 | 0.56 | 0.55 | no | 0.4968 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:40:27 | 3 | 0.57 | 0.56 | no | 0.4876 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 13:41:27 | 3 | 0.6 | 0.59 | no | 0.5704 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $78.00 (realized $6.00, delta $72.00); oracle $120.00.
- **Parity control** — this trade's own as-placed shape, replayed: $31.20 vs $6.00 realized (gap $25.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$6.00** |
  | `all_out_at_tp1_50` | $78.00 |
  | `tp1_30_trail_125` | $59.70 |
  | `trail_only_no_tp1` | $12.00 |
  | `all_out_at_tp1_100` | $-78.00 |
  | `tp1_100_trail_20` | $-78.00 |
  | `tp1_100_trail_10` | $-78.00 |
  | `hold_to_time_stop` | $-78.00 |

### 2026-07-06 · safe-1 · `SPY260706C00753000` · realized $8.00

- **Entry** 11:34:26 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE)_
- **Strike** 753 (trigger None, offset None), quoted premium 0.1, filled **0.1** × 8, stop `?`.
- **Entry fill quality** — paid 11.1% above the signal minute's low (bar 0.09–0.12).
- **High-water WHILE IN THE TRADE** 0.12 (20.0% vs entry) at 2026-07-06T17:15:00Z UTC · 5 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.24 (140.0%) at 2026-07-06T19:21:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:16:28 | 8 | 0.11 | 10.0% | `premium_stop` | 0.12 | $8.00 (8.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:37:26 | 8 | 0.09 | 0.04 | no | 0.104 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.1) |
  | 12:43:27 | 8 | 0.08 | 0.07 | no | 0.056 | — |
  | 12:46:26 | 8 | 0.04 | 0.03 | no | 0.056 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.06) |
  | 13:16:26 | 8 | 0.14 | 0.09 | no | 0.12 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.12) |
  | 14:25:26 | 8 | 0.13 | 0.08 | no | 0.128 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.13) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $8.00 (realized $8.00, delta $0.00); oracle $112.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-16.00 vs $8.00 realized (gap $-24.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$8.00** |
  | `trail_only_no_tp1` | $8.00 |
  | `all_out_at_tp1_100` | $-40.00 |
  | `all_out_at_tp1_50` | $-40.00 |
  | `tp1_30_trail_125` | $-40.00 |
  | `tp1_100_trail_20` | $-40.00 |
  | `tp1_100_trail_10` | $-40.00 |
  | `hold_to_time_stop` | $-40.00 |

### 2026-07-17 · risky-3 · `SPY260717P00741000` · realized $15.00

- **Entry** 11:07:02 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **ELITE**, trigger **744.82**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (ELITE)_
- **Strike** 741 (trigger 744.82, offset -3.82), quoted premium 0.49, filled **0.46** × 5, stop `STRUCTURE@744.82 (cat -50%)`.
- **Entry fill quality** — paid 7.0% above the signal minute's low (bar 0.43–0.53).
- **High-water WHILE IN THE TRADE** 0.53 (15.2% vs entry) at 2026-07-17T15:12:00Z UTC · 2 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.55 (19.6%) at 2026-07-17T15:15:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:13:03 | 2 | 0.49 | 6.5% | `?` | 0.53 | $8.00 (7.5%) |
  | 11:13:03 | 3 | 0.49 | 6.5% | `?` | 0.53 | $12.00 (7.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:10:03 | 5 | 0.38 | 0.37 | no | 0.265 | — |
  | 11:13:01 | 5 | 0.48 | 0.47 | no | 0.265 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 744.82) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $-30.00 (realized $15.00, delta $-45.00); oracle $45.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-115.00 vs $15.00 realized (gap $-130.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$15.00** |
  | `trail_only_no_tp1` | $-30.00 |
  | `all_out_at_tp1_100` | $-115.00 |
  | `all_out_at_tp1_50` | $-115.00 |
  | `tp1_30_trail_125` | $-115.00 |
  | `tp1_100_trail_20` | $-115.00 |
  | `tp1_100_trail_10` | $-115.00 |
  | `hold_to_time_stop` | $-115.00 |

### 2026-07-17 · safe-2 · `SPY260717P00745000` · realized $105.00

- **Entry** 11:40:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.0** × 3, stop `STRUCTURE@745.89 (cat -50%)`.
- **Entry fill quality** — paid 4.2% above the signal minute's low (bar 0.96–1.08).
- **High-water WHILE IN THE TRADE** 1.87 (87.0% vs entry) at 2026-07-17T18:16:00Z UTC · 37 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.89 (189.0%) at 2026-07-17T19:25:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:05:04 | 2 | 1.28 | 28.0% | `tp1` | 1.42 | $28.00 (9.9%) |
  | 14:24:03 | 1 | 1.49 | 49.0% | `trail` | 1.87 | $38.00 (20.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:41:03 | 3 | 1.26 | 1.25 | no | 0.56 | — |
  | 11:42:03 | 3 | 1.26 | 1.25 | no | 0.56 | — |
  | 11:43:03 | 3 | 1.3 | 1.29 | no | 0.56 | — |
  | 11:44:03 | 3 | 1.31 | 1.3 | no | 0.56 | — |
  | 11:45:04 | 3 | 1.26 | 1.25 | no | 0.56 | — |
  | 11:46:03 | 3 | 1.4 | 1.35 | no | 0.56 | — |
  | 11:47:03 | 3 | 1.16 | 1.15 | no | 0.56 | — |
  | 11:48:03 | 3 | 1.21 | 1.2 | no | 0.56 | — |
  | 11:49:03 | 3 | 1.25 | 1.24 | no | 0.56 | — |
  | 11:50:03 | 3 | 1.14 | 1.13 | no | 0.56 | — |
  | 11:51:03 | 3 | 1.25 | 1.2 | no | 0.56 | — |
  | 11:52:03 | 3 | 1.19 | 1.18 | no | 0.56 | — |
  | 11:53:03 | 3 | 1.22 | 1.21 | no | 0.56 | — |
  | 11:54:03 | 3 | 1.09 | 1.08 | no | 0.56 | — |
  | 11:55:03 | 3 | 0.9 | 0.85 | no | 0.56 | — |
  | 11:56:03 | 3 | 0.79 | 0.74 | no | 0.56 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 745.89) |
  | 14:04:03 | 3 | 0.94 | 0.93 | no | 0.9292 | — |
  | 14:05:03 | 3 | 1.33 | 1.32 | yes | 1.01 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +30%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:06:03 | 1 | 1.31 | 1.25 | yes | 1.1305 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:07:03 | 1 | 1.41 | 1.4 | yes | 1.1985 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:08:03 | 1 | 1.31 | 1.26 | yes | 1.1985 | — |
  | 14:09:03 | 1 | 1.26 | 1.25 | yes | 1.1985 | — |
  | 14:10:03 | 1 | 1.39 | 1.38 | yes | 1.1985 | — |
  | 14:11:03 | 1 | 1.43 | 1.38 | yes | 1.2155 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:12:03 | 1 | 1.41 | 1.39 | yes | 1.2155 | — |
  | 14:13:03 | 1 | 1.49 | 1.48 | yes | 1.2665 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:14:03 | 1 | 1.39 | 1.38 | yes | 1.2665 | — |
  | 14:15:03 | 1 | 1.5 | 1.45 | yes | 1.275 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:16:03 | 1 | 1.83 | 1.77 | yes | 1.5555 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:17:04 | 1 | 1.72 | 1.67 | yes | 1.5555 | — |
  | 14:18:03 | 1 | 1.63 | 1.6 | yes | 1.5555 | — |
  | 14:19:03 | 1 | 1.83 | 1.8 | yes | 1.5555 | — |
  | 14:20:03 | 1 | 1.66 | 1.65 | yes | 1.5555 | — |
  | 14:21:07 | 1 | 1.82 | 1.75 | yes | 1.5555 | — |
  | 14:22:03 | 1 | 1.62 | 1.6 | yes | 1.5555 | — |
  | 14:23:03 | 1 | 1.65 | 1.63 | yes | 1.5555 | — |
  | 14:24:03 | 1 | 1.53 | 1.46 | yes | 1.5555 | **SELL_ALL 1 `trail`** (runner_stop @ 1.56) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $300.00 (realized $105.00, delta $195.00); oracle $567.00.
- **Parity control** — this trade's own as-placed shape, replayed: $60.00 vs $105.00 realized (gap $-45.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$105.00** |
  | `all_out_at_tp1_100` | $300.00 |
  | `tp1_100_trail_10` | $286.30 |
  | `tp1_100_trail_20` | $265.60 |
  | `all_out_at_tp1_50` | $150.00 |
  | `hold_to_time_stop` | $123.00 |
  | `tp1_30_trail_125` | $91.25 |
  | `trail_only_no_tp1` | $60.00 |

### 2026-07-17 · safe-2 · `SPY260717P00746000` · realized $241.00

- **Entry** 13:01:03 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.78** × 3, stop `STRUCTURE@747.25 (cat -50%)`.
- **Entry fill quality** — paid 8.3% above the signal minute's low (bar 0.72–0.82).
- **High-water WHILE IN THE TRADE** 2.07 (165.4% vs entry) at 2026-07-17T17:58:00Z UTC · 62 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 3.88 (397.4%) at 2026-07-17T19:25:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:52:03 | 2 | 1.56 | 100.0% | `tp1` | 1.72 | $32.00 (9.3%) |
  | 14:03:03 | 1 | 1.63 | 109.0% | `trail` | 2.07 | $44.00 (21.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:02:04 | 3 | 0.85 | 0.84 | no | 0.4 | — |
  | 13:03:03 | 3 | 0.82 | 0.81 | no | 0.4 | — |
  | 13:04:03 | 3 | 0.86 | 0.85 | no | 0.4 | — |
  | 13:05:03 | 3 | 0.91 | 0.9 | no | 0.4 | — |
  | 13:06:03 | 3 | 0.91 | 0.9 | no | 0.4 | — |
  | 13:07:03 | 3 | 0.75 | 0.74 | no | 0.4 | — |
  | 13:08:03 | 3 | 0.74 | 0.73 | no | 0.4 | — |
  | 13:09:03 | 3 | 0.73 | 0.72 | no | 0.4 | — |
  | 13:10:03 | 3 | 0.74 | 0.73 | no | 0.4 | — |
  | 13:11:03 | 3 | 0.71 | 0.66 | no | 0.4 | — |
  | 13:12:03 | 3 | 0.72 | 0.71 | no | 0.4 | — |
  | 13:13:03 | 3 | 0.75 | 0.74 | no | 0.4 | — |
  | 13:14:03 | 3 | 0.8 | 0.79 | no | 0.4 | — |
  | 13:15:03 | 3 | 0.96 | 0.91 | no | 0.4 | — |
  | 13:16:04 | 3 | 0.86 | 0.85 | no | 0.4 | — |
  | 13:17:04 | 3 | 0.75 | 0.7 | no | 0.4 | — |
  | 13:18:04 | 3 | 0.79 | 0.78 | no | 0.4 | — |
  | 13:19:03 | 3 | 0.87 | 0.86 | no | 0.4 | — |
  | 13:20:03 | 3 | 0.99 | 0.98 | no | 0.4 | — |
  | 13:21:03 | 3 | 1.06 | 1.05 | no | 0.4 | — |
  | 13:22:03 | 3 | 0.98 | 0.97 | no | 0.4 | — |
  | 13:23:03 | 3 | 0.93 | 0.92 | no | 0.4 | — |
  | 13:24:03 | 3 | 1.0 | 0.95 | no | 0.4 | — |
  | 13:25:03 | 3 | 0.97 | 0.96 | no | 0.4 | — |
  | 13:26:03 | 3 | 0.79 | 0.78 | no | 0.4 | — |
  | 13:27:03 | 3 | 0.7 | 0.69 | no | 0.4 | — |
  | 13:28:03 | 3 | 0.69 | 0.68 | no | 0.4 | — |
  | 13:29:03 | 3 | 0.72 | 0.71 | no | 0.4 | — |
  | 13:30:03 | 3 | 0.73 | 0.72 | no | 0.4 | — |
  | 13:31:03 | 3 | 0.7 | 0.69 | no | 0.4 | — |
  | 13:32:03 | 3 | 0.77 | 0.76 | no | 0.4 | — |
  | 13:33:03 | 3 | 0.78 | 0.77 | no | 0.4 | — |
  | 13:34:03 | 3 | 0.73 | 0.72 | no | 0.4 | — |
  | 13:35:03 | 3 | 0.77 | 0.72 | no | 0.4 | — |
  | 13:36:03 | 3 | 0.96 | 0.95 | no | 0.4 | — |
  | 13:37:03 | 3 | 1.02 | 1.01 | no | 0.4 | — |
  | 13:38:03 | 3 | 0.97 | 0.96 | no | 0.4 | — |
  | 13:39:03 | 3 | 1.12 | 1.11 | no | 0.4 | — |
  | 13:40:03 | 3 | 1.08 | 1.07 | no | 0.4 | — |
  | 13:41:03 | 3 | 1.23 | 1.22 | no | 0.4 | — |
  | 13:42:03 | 3 | 1.13 | 1.07 | no | 0.4 | — |
  | 13:43:03 | 3 | 1.25 | 1.24 | no | 0.4 | — |
  | 13:44:03 | 3 | 1.26 | 1.25 | no | 0.4 | — |
  | 13:45:03 | 3 | 1.32 | 1.3 | no | 0.4 | — |
  | 13:46:03 | 3 | 1.21 | 1.2 | no | 0.4 | — |
  | 13:47:03 | 3 | 1.34 | 1.33 | no | 0.4 | — |
  | 13:48:03 | 3 | 1.2 | 1.18 | no | 0.4 | — |
  | 13:49:03 | 3 | 1.26 | 1.25 | no | 0.4 | — |
  | 13:50:03 | 3 | 1.2 | 1.19 | no | 0.4 | — |
  | 13:51:03 | 3 | 1.57 | 1.49 | no | 0.4 | — |
  | 13:52:03 | 3 | 1.62 | 1.54 | yes | 0.8 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:53:03 | 1 | 1.69 | 1.67 | yes | 1.4365 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:54:03 | 1 | 1.67 | 1.64 | yes | 1.4365 | — |
  | 13:55:03 | 1 | 1.72 | 1.63 | yes | 1.462 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:56:03 | 1 | 1.76 | 1.75 | yes | 1.496 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:57:03 | 1 | 1.97 | 1.96 | yes | 1.6745 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:58:03 | 1 | 1.97 | 1.94 | yes | 1.6745 | — |
  | 13:59:03 | 1 | 1.98 | 1.9 | yes | 1.683 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:00:03 | 1 | 1.87 | 1.8 | yes | 1.683 | — |
  | 14:01:03 | 1 | 1.92 | 1.9 | yes | 1.683 | — |
  | 14:02:03 | 1 | 1.92 | 1.9 | yes | 1.683 | — |
  | 14:03:03 | 1 | 1.62 | 1.61 | yes | 1.683 | **SELL_ALL 1 `trail`** (runner_stop @ 1.68) |

- **This trade's variant grid** — best was `hold_to_time_stop` at $474.00 (realized $241.00, delta $233.00); oracle $930.00.
- **Parity control** — this trade's own as-placed shape, replayed: $46.80 vs $241.00 realized (gap $-194.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$241.00** |
  | `hold_to_time_stop` | $474.00 |
  | `tp1_100_trail_20` | $243.60 |
  | `all_out_at_tp1_100` | $234.00 |
  | `tp1_100_trail_10` | $232.80 |
  | `all_out_at_tp1_50` | $117.00 |
  | `tp1_30_trail_125` | $68.55 |
  | `trail_only_no_tp1` | $18.00 |

### 2026-07-17 · bold-2 · `SPY260717P00743000` · realized $191.00

- **Entry** 13:51:21 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.38** × 5, stop `STRUCTURE@745.98 (cat -50%)`.
- **Entry fill quality** — paid 8.6% above the signal minute's low (bar 0.35–0.41).
- **High-water WHILE IN THE TRADE** 0.89 (134.2% vs entry) at 2026-07-17T18:27:00Z UTC · 39 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.25 (228.9%) at 2026-07-17T19:25:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:27:04 | 3 | 0.85 | 123.7% | `tp1` | 0.89 | $12.00 (4.5%) |
  | 14:30:04 | 2 | 0.63 | 65.8% | `trail` | 0.89 | $52.00 (29.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:52:17 | 5 | 0.37 | 0.36 | no | 0.215 | — |
  | 13:53:18 | 5 | 0.46 | 0.45 | no | 0.215 | — |
  | 13:54:16 | 5 | 0.41 | 0.4 | no | 0.215 | — |
  | 13:55:19 | 5 | 0.4 | 0.39 | no | 0.215 | — |
  | 13:56:15 | 5 | 0.49 | 0.48 | no | 0.215 | — |
  | 13:57:21 | 5 | 0.55 | 0.5 | no | 0.215 | — |
  | 13:58:16 | 5 | 0.57 | 0.56 | no | 0.215 | — |
  | 13:59:16 | 5 | 0.56 | 0.51 | no | 0.215 | — |
  | 14:00:21 | 5 | 0.47 | 0.46 | no | 0.215 | — |
  | 14:01:20 | 5 | 0.51 | 0.46 | no | 0.215 | — |
  | 14:02:20 | 5 | 0.51 | 0.5 | no | 0.215 | — |
  | 14:03:20 | 5 | 0.39 | 0.38 | no | 0.215 | — |
  | 14:04:19 | 5 | 0.39 | 0.34 | no | 0.215 | — |
  | 14:05:19 | 5 | 0.56 | 0.51 | no | 0.215 | — |
  | 14:06:05 | 5 | 0.51 | 0.5 | no | 0.215 | — |
  | 14:07:05 | 5 | 0.55 | 0.54 | no | 0.215 | — |
  | 14:08:05 | 5 | 0.47 | 0.46 | no | 0.215 | — |
  | 14:09:05 | 5 | 0.51 | 0.5 | no | 0.215 | — |
  | 14:10:05 | 5 | 0.49 | 0.48 | no | 0.215 | — |
  | 14:11:05 | 5 | 0.57 | 0.56 | no | 0.215 | — |
  | 14:12:05 | 5 | 0.57 | 0.52 | no | 0.215 | — |
  | 14:13:04 | 5 | 0.56 | 0.55 | no | 0.215 | — |
  | 14:14:05 | 5 | 0.56 | 0.55 | no | 0.215 | — |
  | 14:15:05 | 5 | 0.55 | 0.54 | no | 0.215 | — |
  | 14:16:05 | 5 | 0.77 | 0.72 | no | 0.215 | — |
  | 14:17:06 | 5 | 0.76 | 0.71 | no | 0.215 | — |
  | 14:18:04 | 5 | 0.69 | 0.68 | no | 0.215 | — |
  | 14:19:04 | 5 | 0.78 | 0.73 | no | 0.215 | — |
  | 14:20:04 | 5 | 0.69 | 0.68 | no | 0.215 | — |
  | 14:21:08 | 5 | 0.72 | 0.71 | no | 0.215 | — |
  | 14:22:04 | 5 | 0.68 | 0.63 | no | 0.215 | — |
  | 14:23:04 | 5 | 0.67 | 0.66 | no | 0.215 | — |
  | 14:24:04 | 5 | 0.6 | 0.59 | no | 0.215 | — |
  | 14:25:04 | 5 | 0.74 | 0.73 | no | 0.215 | — |
  | 14:26:04 | 5 | 0.8 | 0.79 | no | 0.215 | — |
  | 14:27:03 | 5 | 0.88 | 0.87 | yes | 0.43 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:28:03 | 2 | 0.86 | 0.8 | yes | 0.748 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:29:04 | 2 | 0.77 | 0.76 | yes | 0.748 | — |
  | 14:30:04 | 2 | 0.67 | 0.66 | yes | 0.748 | **SELL_ALL 2 `trail`** (runner_stop @ 0.75) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $190.00 (realized $191.00, delta $-1.00); oracle $435.00.
- **Parity control** — this trade's own as-placed shape, replayed: $34.20 vs $191.00 realized (gap $-156.80 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$191.00** |
  | `all_out_at_tp1_100` | $190.00 |
  | `tp1_100_trail_10` | $182.00 |
  | `tp1_100_trail_20` | $166.00 |
  | `all_out_at_tp1_50` | $95.00 |
  | `tp1_30_trail_125` | $57.47 |
  | `trail_only_no_tp1` | $20.00 |
  | `hold_to_time_stop` | $-95.00 |

### 2026-07-17 · risky-3 · `SPY260717P00743000` · realized $233.00

- **Entry** 13:52:02 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **745.98**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE)_
- **Strike** 743 (trigger 745.98, offset -2.98), quoted premium 0.41, filled **0.39** × 5, stop `STRUCTURE@745.98 (cat -50%)`.
- **Entry fill quality** — paid 11.4% above the signal minute's low (bar 0.35–0.45).
- **High-water WHILE IN THE TRADE** 1.25 (220.5% vs entry) at 2026-07-17T19:25:00Z UTC · 32 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.25 (220.5%) at 2026-07-17T19:25:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 15:16:04 | 3 | 0.98 | 151.3% | `tp1` | 1.05 | $21.00 (6.7%) |
  | 15:28:04 | 2 | 0.67 | 71.8% | `trail` | 1.25 | $116.00 (46.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:55:02 | 5 | 0.42 | 0.41 | no | 0.22 | — |
  | 13:58:02 | 5 | 0.55 | 0.54 | no | 0.22 | — |
  | 14:01:01 | 5 | 0.53 | 0.52 | no | 0.22 | — |
  | 14:04:02 | 5 | 0.36 | 0.31 | no | 0.22 | — |
  | 14:07:02 | 5 | 0.59 | 0.54 | no | 0.22 | — |
  | 14:10:03 | 5 | 0.54 | 0.53 | no | 0.22 | — |
  | 14:13:01 | 5 | 0.59 | 0.58 | no | 0.22 | — |
  | 14:16:02 | 5 | 0.74 | 0.73 | no | 0.22 | — |
  | 14:19:01 | 5 | 0.77 | 0.72 | no | 0.22 | — |
  | 14:22:02 | 5 | 0.68 | 0.63 | no | 0.22 | — |
  | 14:25:03 | 5 | 0.74 | 0.73 | no | 0.22 | — |
  | 14:28:02 | 5 | 0.86 | 0.8 | no | 0.22 | — |
  | 14:31:01 | 5 | 0.49 | 0.48 | no | 0.22 | — |
  | 14:34:02 | 5 | 0.75 | 0.74 | no | 0.22 | — |
  | 14:37:02 | 5 | 0.65 | 0.6 | no | 0.22 | — |
  | 14:40:03 | 5 | 0.6 | 0.59 | no | 0.22 | — |
  | 14:43:01 | 5 | 0.84 | 0.83 | no | 0.22 | — |
  | 14:46:02 | 5 | 0.77 | 0.76 | no | 0.22 | — |
  | 14:49:01 | 5 | 0.54 | 0.53 | no | 0.22 | — |
  | 14:52:02 | 5 | 0.54 | 0.53 | no | 0.22 | — |
  | 14:55:02 | 5 | 0.35 | 0.34 | no | 0.22 | — |
  | 14:58:02 | 5 | 0.31 | 0.3 | no | 0.22 | — |
  | 15:01:01 | 5 | 0.46 | 0.41 | no | 0.22 | — |
  | 15:04:02 | 5 | 0.45 | 0.44 | no | 0.22 | — |
  | 15:07:02 | 5 | 0.55 | 0.54 | no | 0.22 | — |
  | 15:10:03 | 5 | 0.54 | 0.53 | no | 0.22 | — |
  | 15:13:01 | 5 | 0.83 | 0.82 | no | 0.22 | — |
  | 15:16:02 | 5 | 1.02 | 0.97 | yes | 0.44 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 15:19:01 | 2 | 0.96 | 0.94 | yes | 0.867 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:22:02 | 2 | 0.95 | 0.94 | yes | 0.867 | — |
  | 15:25:02 | 2 | 1.11 | 1.1 | yes | 0.9435 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:28:02 | 2 | 0.74 | 0.69 | yes | 0.9435 | **SELL_ALL 2 `trail`** (runner_stop @ 0.94) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $195.00 (realized $233.00, delta $-38.00); oracle $430.00.
- **Parity control** — this trade's own as-placed shape, replayed: $179.00 vs $233.00 realized (gap $-54.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$233.00** |
  | `all_out_at_tp1_100` | $195.00 |
  | `tp1_100_trail_10` | $183.00 |
  | `tp1_100_trail_20` | $167.00 |
  | `all_out_at_tp1_50` | $97.50 |
  | `tp1_30_trail_125` | $57.67 |
  | `trail_only_no_tp1` | $15.00 |
  | `hold_to_time_stop` | $-97.50 |

### 2026-07-21 · safe-2 · `SPY260721P00745000` · realized $18.00

- **Entry** ? ET — `?` (?), quality **?**, trigger **None**, risk `None`.
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.28** × 3, stop `?`.
- **Entry fill quality** — paid 2.4% above the signal minute's low (bar 1.25–1.38).
- **High-water WHILE IN THE TRADE** 1.36 (6.2% vs entry) at 2026-07-21T14:13:00Z UTC · 9 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.54 (20.3%) at 2026-07-21T14:16:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:13:04 | 3 | 1.34 | 4.7% | `ribbon_flip` | 1.36 | $6.00 (1.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:54:02 | 3 | 1.51 | 1.5 | no | 1.4168 | — |
  | 09:55:03 | 3 | 1.57 | 1.51 | no | 1.4168 | — |
  | 09:56:02 | 3 | 1.6 | 1.59 | no | 1.4168 | — |
  | 09:57:03 | 3 | 1.67 | 1.66 | no | 1.4168 | — |
  | 09:58:02 | 3 | 1.59 | 1.58 | no | 1.4168 | — |
  | 09:59:02 | 3 | 1.6 | 1.55 | no | 1.4168 | — |
  | 10:00:04 | 3 | 1.33 | 1.32 | no | 1.4168 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 1.42) |
  | 10:12:03 | 3 | 1.29 | 1.28 | no | 1.3536 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 1.35) |
  | 10:13:03 | 3 | 1.34 | 1.33 | no | 1.2236 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $-36.00 (realized $18.00, delta $-54.00); oracle $78.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-192.00 vs $18.00 realized (gap $-210.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$18.00** |
  | `trail_only_no_tp1` | $-36.00 |
  | `all_out_at_tp1_100` | $-192.00 |
  | `all_out_at_tp1_50` | $-192.00 |
  | `tp1_30_trail_125` | $-192.00 |
  | `tp1_100_trail_20` | $-192.00 |
  | `tp1_100_trail_10` | $-192.00 |
  | `hold_to_time_stop` | $-192.00 |

### 2026-07-28 · safe-2 · `SPY260728P00741000` · realized $15.00

- **Entry** ? ET — `?` (?), quality **?**, trigger **None**, risk `None`.
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.85** × 3, stop `?`.
- **Entry fill quality** — paid 14.9% above the signal minute's low (bar 0.74–0.91).
- **High-water WHILE IN THE TRADE** 0.95 (11.8% vs entry) at 2026-07-28T17:51:00Z UTC · 1 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.11 (30.6%) at 2026-07-28T17:55:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:51:04 | 3 | 0.9 | 5.9% | `ribbon_flip` | 0.95 | $15.00 (5.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:51:03 | 3 | 0.92 | 0.91 | no | 0.828 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_30_trail_125` at $63.13 (realized $15.00, delta $48.13); oracle $78.00.
- **Parity control** — this trade's own as-placed shape, replayed: $51.00 vs $15.00 realized (gap $36.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$15.00** |
  | `tp1_30_trail_125` | $63.13 |
  | `trail_only_no_tp1` | $36.00 |
  | `all_out_at_tp1_100` | $-127.50 |
  | `all_out_at_tp1_50` | $-127.50 |
  | `tp1_100_trail_20` | $-127.50 |
  | `tp1_100_trail_10` | $-127.50 |
  | `hold_to_time_stop` | $-127.50 |

### 2026-07-29 · safe-3 · `SPY260729P00734000` · realized $72.00

- **Entry** 10:04:48 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **ELITE**, trigger **737.57**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (ELITE)_
- **Strike** 734 (trigger 737.57, offset -3.57), quoted premium 1.54, filled **1.56** × 3, stop `STRUCTURE@737.57 (cat -50%)`.
- **Entry fill quality** — paid 1.3% above the signal minute's low (bar 1.54–1.68).
- **High-water WHILE IN THE TRADE** 1.85 (18.6% vs entry) at 2026-07-29T14:07:00Z UTC · 1 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 5.9 (278.2%) at 2026-07-29T20:04:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:07:48 | 3 | 1.8 | 15.4% | `structure_stop` | 1.85 | $15.00 (2.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:07:47 | 3 | 1.78 | 1.77 | no | 0.79 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 737.57) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $468.00 (realized $72.00, delta $396.00); oracle $1,302.00.
- **Parity control** — this trade's own as-placed shape, replayed: $436.00 vs $72.00 realized (gap $364.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$72.00** |
  | `all_out_at_tp1_100` | $468.00 |
  | `tp1_100_trail_10` | $444.00 |
  | `tp1_100_trail_20` | $412.00 |
  | `all_out_at_tp1_50` | $234.00 |
  | `tp1_30_trail_125` | $165.10 |
  | `trail_only_no_tp1` | $39.00 |
  | `hold_to_time_stop` | $-234.00 |

### 2026-07-29 · risky-3 · `SPY260729P00734000` · realized $115.00

- **Entry** 10:04:48 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **ELITE**, trigger **737.57**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (ELITE)_
- **Strike** 734 (trigger 737.57, offset -3.57), quoted premium 1.56, filled **1.56** × 5, stop `STRUCTURE@737.57 (cat -50%)`.
- **Entry fill quality** — paid 1.3% above the signal minute's low (bar 1.54–1.68).
- **High-water WHILE IN THE TRADE** 1.85 (18.6% vs entry) at 2026-07-29T14:07:00Z UTC · 1 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 5.9 (278.2%) at 2026-07-29T20:04:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:07:50 | 5 | 1.79 | 14.7% | `structure_stop` | 1.85 | $30.00 (3.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:07:47 | 5 | 1.82 | 1.77 | no | 0.805 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 737.57) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $780.00 (realized $115.00, delta $665.00); oracle $2,170.00.
- **Parity control** — this trade's own as-placed shape, replayed: $716.00 vs $115.00 realized (gap $601.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$115.00** |
  | `all_out_at_tp1_100` | $780.00 |
  | `tp1_100_trail_10` | $732.00 |
  | `tp1_100_trail_20` | $668.00 |
  | `all_out_at_tp1_50` | $390.00 |
  | `tp1_30_trail_125` | $258.70 |
  | `trail_only_no_tp1` | $65.00 |
  | `hold_to_time_stop` | $-390.00 |

### 2026-07-29 · safe-3 · `SPY260729C00740000` · realized $265.00

- **Entry** 14:34:47 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **736.76**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE)_
- **Strike** 740 (trigger 736.76, offset 3.24), quoted premium 0.85, filled **0.85** × 3, stop `STRUCTURE@736.76 (cat -50%)`.
- **Entry fill quality** — paid 13.3% above the signal minute's low (bar 0.75–0.91).
- **High-water WHILE IN THE TRADE** 3.23 (280.0% vs entry) at 2026-07-29T18:54:00Z UTC · 10 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 3.23 (280.0%) at 2026-07-29T18:54:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:43:48 | 2 | 1.79 | 110.6% | `tp1` | 1.91 | $24.00 (6.3%) |
  | 15:04:48 | 1 | 1.62 | 90.6% | `trail` | 3.23 | $161.00 (49.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:37:47 | 3 | 0.97 | 0.96 | no | 0.445 | — |
  | 14:40:48 | 3 | 1.7 | 1.68 | no | 0.445 | — |
  | 14:43:47 | 3 | 1.85 | 1.8 | yes | 0.89 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:46:49 | 1 | 2.23 | 2.22 | yes | 1.8955 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:49:47 | 1 | 2.89 | 2.82 | yes | 2.4565 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:52:47 | 1 | 2.73 | 2.61 | yes | 2.4565 | — |
  | 14:55:47 | 1 | 2.98 | 2.97 | yes | 2.533 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:58:48 | 1 | 2.72 | 2.66 | yes | 2.533 | — |
  | 15:01:48 | 1 | 2.83 | 2.77 | yes | 2.533 | — |
  | 15:04:47 | 1 | 1.66 | 1.64 | yes | 2.533 | **SELL_ALL 1 `trail`** (runner_stop @ 2.53) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $256.00 (realized $265.00, delta $-9.00); oracle $714.00.
- **Parity control** — this trade's own as-placed shape, replayed: $251.25 vs $265.00 realized (gap $-13.75 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$265.00** |
  | `tp1_100_trail_10` | $256.00 |
  | `all_out_at_tp1_100` | $255.00 |
  | `tp1_100_trail_20` | $237.00 |
  | `all_out_at_tp1_50` | $127.50 |
  | `tp1_30_trail_125` | $102.50 |
  | `trail_only_no_tp1` | $21.00 |
  | `hold_to_time_stop` | $-127.50 |

### 2026-07-29 · risky-1 · `SPY260729C00740000` · realized $418.00

- **Entry** 14:34:47 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **736.76**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE)_
- **Strike** 740 (trigger 736.76, offset 3.24), quoted premium 0.86, filled **0.84** × 5, stop `STRUCTURE@736.76 (cat -50%)`.
- **Entry fill quality** — paid 12.0% above the signal minute's low (bar 0.75–0.91).
- **High-water WHILE IN THE TRADE** 3.23 (284.5% vs entry) at 2026-07-29T18:54:00Z UTC · 10 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 3.23 (284.5%) at 2026-07-29T18:54:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:40:49 | 1 | 1.68 | 100.0% | `?` | 1.7 | $2.00 (1.2%) |
  | 14:40:49 | 2 | 1.69 | 101.2% | `trail` | 1.7 | $2.00 (0.6%) |
  | 15:04:49 | 2 | 1.66 | 97.6% | `trail` | 3.23 | $314.00 (48.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:37:47 | 5 | 0.97 | 0.96 | no | 0.45 | — |
  | 14:40:48 | 5 | 1.7 | 1.68 | yes | 0.9 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:43:47 | 2 | 1.84 | 1.81 | yes | 1.564 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:46:49 | 2 | 2.19 | 2.15 | yes | 1.8615 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:49:47 | 2 | 2.9 | 2.83 | yes | 2.465 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:52:47 | 2 | 2.72 | 2.69 | yes | 2.465 | — |
  | 14:55:47 | 2 | 2.98 | 2.97 | yes | 2.533 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:58:48 | 2 | 2.79 | 2.76 | yes | 2.533 | — |
  | 15:01:48 | 2 | 2.83 | 2.77 | yes | 2.533 | — |
  | 15:04:47 | 2 | 1.67 | 1.62 | yes | 2.533 | **SELL_ALL 2 `trail`** (runner_stop @ 2.53) |

- **Tags:** `runner_material_giveback`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $426.00 (realized $418.00, delta $8.00); oracle $1,195.00.
- **Parity control** — this trade's own as-placed shape, replayed: $231.00 vs $418.00 realized (gap $-187.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$418.00** |
  | `tp1_100_trail_10` | $426.00 |
  | `all_out_at_tp1_100` | $420.00 |
  | `tp1_100_trail_20` | $388.00 |
  | `all_out_at_tp1_50` | $210.00 |
  | `tp1_30_trail_125` | $153.30 |
  | `trail_only_no_tp1` | $40.00 |
  | `hold_to_time_stop` | $-210.00 |

### 2026-07-29 · risky-3 · `SPY260729C00740000` · realized $471.00

- **Entry** 14:34:47 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **736.76**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE)_
- **Strike** 740 (trigger 736.76, offset 3.24), quoted premium 0.85, filled **0.842** × 5, stop `STRUCTURE@736.76 (cat -50%)`.
- **Entry fill quality** — paid 12.3% above the signal minute's low (bar 0.75–0.91).
- **High-water WHILE IN THE TRADE** 3.23 (283.6% vs entry) at 2026-07-29T18:54:00Z UTC · 10 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 3.23 (283.6%) at 2026-07-29T18:54:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:43:49 | 3 | 1.82 | 116.1% | `tp1` | 1.91 | $27.00 (4.7%) |
  | 15:04:50 | 2 | 1.73 | 105.5% | `trail` | 3.23 | $300.00 (46.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:37:47 | 5 | 0.97 | 0.96 | no | 0.445 | — |
  | 14:40:48 | 5 | 1.71 | 1.66 | no | 0.445 | — |
  | 14:43:47 | 5 | 1.82 | 1.76 | yes | 0.89 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:46:49 | 2 | 2.19 | 2.15 | yes | 1.752 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:49:47 | 2 | 2.9 | 2.83 | yes | 2.32 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:52:47 | 2 | 2.75 | 2.73 | yes | 2.32 | — |
  | 14:55:47 | 2 | 3.02 | 2.92 | yes | 2.416 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:58:48 | 2 | 2.79 | 2.76 | yes | 2.416 | — |
  | 15:01:48 | 2 | 2.89 | 2.8 | yes | 2.416 | — |
  | 15:04:47 | 2 | 1.73 | 1.7 | yes | 2.416 | **SELL_ALL 2 `trail`** (runner_stop @ 2.42) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $426.20 (realized $471.00, delta $-44.80); oracle $1,194.00.
- **Parity control** — this trade's own as-placed shape, replayed: $416.70 vs $471.00 realized (gap $-54.30 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$471.00** |
  | `tp1_100_trail_10` | $426.20 |
  | `all_out_at_tp1_100` | $421.00 |
  | `tp1_100_trail_20` | $388.20 |
  | `all_out_at_tp1_50` | $210.50 |
  | `tp1_30_trail_125` | $153.34 |
  | `trail_only_no_tp1` | $39.00 |
  | `hold_to_time_stop` | $-210.50 |

### 2026-07-31 · risky-3 · `SPY260731C00746000` · realized $126.00

- **Entry** 12:19:02 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **743.25**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 746 (trigger 743.25, offset 2.75), quoted premium 0.3, filled **0.33** × 5, stop `STRUCTURE@743.25 (cat -50%)`.
- **Entry fill quality** — paid 13.8% above the signal minute's low (bar 0.29–0.33). ⚠ **filled at the entry bar's HIGH**
- **High-water WHILE IN THE TRADE** 0.71 (115.1% vs entry) at 2026-07-31T16:35:00Z UTC · 8 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.83 (757.6%) at 2026-07-31T19:54:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:34:04 | 3 | 0.65 | 97.0% | `tp1` | 0.67 | $6.00 (3.0%) |
  | 12:43:03 | 2 | 0.48 | 45.5% | `trail` | 0.71 | $46.00 (32.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 12:22:03 | 5 | 0.41 | 0.4 | no | 0.17 | — |
  | 12:25:03 | 5 | 0.54 | 0.49 | no | 0.17 | — |
  | 12:28:02 | 5 | 0.41 | 0.4 | no | 0.17 | — |
  | 12:31:02 | 5 | 0.58 | 0.57 | no | 0.17 | — |
  | 12:34:02 | 5 | 0.69 | 0.64 | yes | 0.34 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:37:03 | 2 | 0.59 | 0.58 | yes | 0.552 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:40:04 | 2 | 0.58 | 0.57 | yes | 0.552 | — |
  | 12:43:02 | 2 | 0.51 | 0.5 | yes | 0.552 | **SELL_ALL 2 `trail`** (runner_stop @ 0.55) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $1,000.00 (realized $126.00, delta $874.00); oracle $1,250.00.
- **Parity control** — this trade's own as-placed shape, replayed: $148.50 vs $126.00 realized (gap $22.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$126.00** |
  | `hold_to_time_stop` | $1,000.00 |
  | `all_out_at_tp1_100` | $165.00 |
  | `tp1_100_trail_10` | $151.80 |
  | `tp1_100_trail_20` | $146.60 |
  | `all_out_at_tp1_50` | $82.50 |
  | `tp1_30_trail_125` | $56.47 |
  | `trail_only_no_tp1` | $15.00 |

### 2026-07-31 · safe-3 · `SPY260731C00747000` · realized $75.00

- **Entry** 12:31:02 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **743.56**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE)_
- **Strike** 747 (trigger 743.56, offset 3.44), quoted premium 0.33, filled **0.3** × 3, stop `STRUCTURE@743.56 (cat -50%)`.
- **Entry fill quality** — paid 3.5% above the signal minute's low (bar 0.29–0.36).
- **High-water WHILE IN THE TRADE** 0.74 (146.7% vs entry) at 2026-07-31T17:36:00Z UTC · 23 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.9 (533.3%) at 2026-07-31T19:54:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:31:03 | 2 | 0.61 | 103.3% | `tp1` | 0.71 | $20.00 (14.1%) |
  | 13:40:04 | 1 | 0.43 | 43.3% | `trail` | 0.74 | $31.00 (41.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 12:34:02 | 3 | 0.36 | 0.35 | no | 0.155 | — |
  | 12:37:03 | 3 | 0.34 | 0.33 | no | 0.155 | — |
  | 12:40:04 | 3 | 0.32 | 0.31 | no | 0.155 | — |
  | 12:43:02 | 3 | 0.29 | 0.24 | no | 0.155 | — |
  | 12:46:03 | 3 | 0.26 | 0.21 | no | 0.155 | — |
  | 12:49:03 | 3 | 0.29 | 0.28 | no | 0.155 | — |
  | 12:52:03 | 3 | 0.34 | 0.29 | no | 0.155 | — |
  | 12:55:03 | 3 | 0.29 | 0.24 | no | 0.155 | — |
  | 12:58:02 | 3 | 0.32 | 0.27 | no | 0.155 | — |
  | 13:01:03 | 3 | 0.31 | 0.3 | no | 0.155 | — |
  | 13:04:03 | 3 | 0.37 | 0.36 | no | 0.155 | — |
  | 13:07:02 | 3 | 0.29 | 0.28 | no | 0.155 | — |
  | 13:10:04 | 3 | 0.28 | 0.27 | no | 0.155 | — |
  | 13:13:03 | 3 | 0.35 | 0.34 | no | 0.155 | — |
  | 13:16:03 | 3 | 0.34 | 0.33 | no | 0.155 | — |
  | 13:19:02 | 3 | 0.35 | 0.34 | no | 0.155 | — |
  | 13:22:03 | 3 | 0.34 | 0.29 | no | 0.155 | — |
  | 13:25:03 | 3 | 0.54 | 0.53 | no | 0.155 | — |
  | 13:28:02 | 3 | 0.6 | 0.59 | no | 0.155 | — |
  | 13:31:02 | 3 | 0.64 | 0.63 | yes | 0.31 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:34:02 | 1 | 0.73 | 0.72 | yes | 0.6205 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:37:03 | 1 | 0.72 | 0.71 | yes | 0.6205 | — |
  | 13:40:04 | 1 | 0.46 | 0.41 | yes | 0.6205 | **SELL_ALL 1 `trail`** (runner_stop @ 0.62) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $327.00 (realized $75.00, delta $252.00); oracle $480.00.
- **Parity control** — this trade's own as-placed shape, replayed: $92.12 vs $75.00 realized (gap $17.12 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$75.00** |
  | `hold_to_time_stop` | $327.00 |
  | `tp1_100_trail_10` | $93.90 |
  | `all_out_at_tp1_100` | $90.00 |
  | `tp1_100_trail_20` | $86.80 |
  | `all_out_at_tp1_50` | $45.00 |
  | `tp1_30_trail_125` | $22.12 |
  | `trail_only_no_tp1` | $3.00 |

### 2026-08-03 · safe-2 · `SPY260803C00757000` · realized $68.00

- **Entry** ? ET — `?` (?), quality **?**, trigger **None**, risk `None`.
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.53** × 3, stop `?`.
- **Entry fill quality** — paid 10.4% above the signal minute's low (bar 0.48–0.54).
- **High-water WHILE IN THE TRADE** 0.93 (75.5% vs entry) at 2026-08-03T17:35:00Z UTC · 19 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.73 (226.4%) at 2026-08-03T19:02:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:31:04 | 2 | 0.74 | 39.6% | `tp1` | 0.76 | $4.00 (2.6%) |
  | 13:40:04 | 1 | 0.79 | 49.1% | `trail` | 0.93 | $14.00 (15.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:22:04 | 3 | 0.56 | 0.55 | no | 0.5244 | — |
  | 13:23:03 | 3 | 0.59 | 0.58 | no | 0.5244 | — |
  | 13:24:03 | 3 | 0.65 | 0.64 | no | 0.5244 | — |
  | 13:25:03 | 3 | 0.67 | 0.66 | no | 0.5244 | — |
  | 13:26:03 | 3 | 0.62 | 0.61 | no | 0.5244 | — |
  | 13:27:03 | 3 | 0.62 | 0.61 | no | 0.5244 | — |
  | 13:28:03 | 3 | 0.71 | 0.7 | no | 0.5244 | — |
  | 13:29:03 | 3 | 0.72 | 0.71 | no | 0.5244 | — |
  | 13:30:03 | 3 | 0.73 | 0.72 | no | 0.5244 | — |
  | 13:31:03 | 3 | 0.77 | 0.76 | yes | 0.57 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +30%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:32:03 | 1 | 0.74 | 0.73 | yes | 0.6545 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:33:03 | 1 | 0.73 | 0.72 | yes | 0.6545 | — |
  | 13:34:03 | 1 | 0.75 | 0.74 | yes | 0.6545 | — |
  | 13:35:03 | 1 | 0.88 | 0.87 | yes | 0.748 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:36:03 | 1 | 0.93 | 0.92 | yes | 0.7905 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:37:03 | 1 | 0.87 | 0.86 | yes | 0.7905 | — |
  | 13:38:03 | 1 | 0.84 | 0.83 | yes | 0.7905 | — |
  | 13:39:03 | 1 | 0.81 | 0.8 | yes | 0.7905 | — |
  | 13:40:03 | 1 | 0.82 | 0.77 | yes | 0.7905 | **SELL_ALL 1 `trail`** (runner_stop @ 0.79) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_100_trail_20` at $183.40 (realized $68.00, delta $115.40); oracle $360.00.
- **Parity control** — this trade's own as-placed shape, replayed: $91.80 vs $68.00 realized (gap $23.80 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$68.00** |
  | `tp1_100_trail_20` | $183.40 |
  | `hold_to_time_stop` | $180.00 |
  | `tp1_100_trail_10` | $160.10 |
  | `all_out_at_tp1_100` | $159.00 |
  | `all_out_at_tp1_50` | $79.50 |
  | `tp1_30_trail_125` | $48.80 |
  | `trail_only_no_tp1` | $21.00 |

### 2026-08-03 · safe-3 · `SPY260803C00754000` · realized $145.00

- **Entry** 09:42:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **750.98**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 754 (trigger 750.98, offset 3.02), quoted premium 0.39, filled **0.37** × 3, stop `STRUCTURE@750.98 (cat -50%)`.
- **Entry fill quality** — paid 19.4% above the signal minute's low (bar 0.31–0.39).
- **High-water WHILE IN THE TRADE** 1.0 (170.3% vs entry) at 2026-08-03T14:03:00Z UTC · 23 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.61 (1146.0%) at 2026-08-03T19:28:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:03:05 | 2 | 0.92 | 148.7% | `tp1` | 1.0 | $16.00 (8.0%) |
  | 10:05:05 | 1 | 0.72 | 94.6% | `trail` | 1.0 | $28.00 (28.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:03 | 3 | 0.33 | 0.32 | no | 0.21 | — |
  | 09:44:03 | 3 | 0.34 | 0.33 | no | 0.21 | — |
  | 09:45:03 | 3 | 0.42 | 0.41 | no | 0.21 | — |
  | 09:46:03 | 3 | 0.39 | 0.34 | no | 0.21 | — |
  | 09:47:03 | 3 | 0.38 | 0.33 | no | 0.21 | — |
  | 09:48:03 | 3 | 0.48 | 0.47 | no | 0.21 | — |
  | 09:49:03 | 3 | 0.4 | 0.39 | no | 0.21 | — |
  | 09:50:04 | 3 | 0.43 | 0.42 | no | 0.21 | — |
  | 09:51:03 | 3 | 0.43 | 0.42 | no | 0.21 | — |
  | 09:52:03 | 3 | 0.53 | 0.52 | no | 0.21 | — |
  | 09:53:03 | 3 | 0.56 | 0.55 | no | 0.21 | — |
  | 09:54:03 | 3 | 0.64 | 0.59 | no | 0.21 | — |
  | 09:55:04 | 3 | 0.6 | 0.54 | no | 0.21 | — |
  | 09:56:03 | 3 | 0.69 | 0.68 | no | 0.21 | — |
  | 09:57:03 | 3 | 0.66 | 0.61 | no | 0.21 | — |
  | 09:58:04 | 3 | 0.7 | 0.69 | no | 0.21 | — |
  | 09:59:04 | 3 | 0.73 | 0.72 | no | 0.21 | — |
  | 10:00:04 | 3 | 0.81 | 0.74 | no | 0.21 | — |
  | 10:01:03 | 3 | 0.76 | 0.75 | no | 0.21 | — |
  | 10:02:04 | 3 | 0.77 | 0.76 | no | 0.21 | — |
  | 10:03:03 | 3 | 0.95 | 0.9 | yes | 0.42 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:04:03 | 1 | 0.86 | 0.85 | yes | 0.8075 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:05:04 | 1 | 0.72 | 0.71 | yes | 0.8075 | **SELL_ALL 1 `trail`** (runner_stop @ 0.81) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $1,095.00 (realized $145.00, delta $950.00); oracle $1,272.00.
- **Parity control** — this trade's own as-placed shape, replayed: $109.62 vs $145.00 realized (gap $-35.38 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$145.00** |
  | `hold_to_time_stop` | $1,095.00 |
  | `tp1_100_trail_10` | $111.70 |
  | `all_out_at_tp1_100` | $111.00 |
  | `tp1_100_trail_20` | $103.40 |
  | `all_out_at_tp1_50` | $55.50 |
  | `tp1_30_trail_125` | $30.70 |
  | `trail_only_no_tp1` | $0.00 |

### 2026-08-03 · risky-1 · `SPY260803C00754000` · realized $145.00

- **Entry** 09:42:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **750.98**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 754 (trigger 750.98, offset 3.02), quoted premium 0.36, filled **0.37** × 5, stop `STRUCTURE@750.98 (cat -50%)`.
- **Entry fill quality** — paid 19.4% above the signal minute's low (bar 0.31–0.39).
- **High-water WHILE IN THE TRADE** 1.0 (170.3% vs entry) at 2026-08-03T14:03:00Z UTC · 22 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.61 (1146.0%) at 2026-08-03T19:28:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:54:05 | 1 | 0.6 | 62.2% | `?` | 0.63 | $3.00 (4.8%) |
  | 09:54:05 | 1 | 0.6 | 62.2% | `?` | 0.63 | $3.00 (4.8%) |
  | 09:54:05 | 1 | 0.6 | 62.2% | `?` | 0.63 | $3.00 (4.8%) |
  | 10:04:05 | 2 | 0.75 | 102.7% | `trail` | 1.0 | $50.00 (25.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:03 | 5 | 0.3 | 0.29 | no | 0.205 | — |
  | 09:44:03 | 5 | 0.34 | 0.33 | no | 0.205 | — |
  | 09:45:03 | 5 | 0.43 | 0.42 | no | 0.205 | — |
  | 09:46:03 | 5 | 0.4 | 0.35 | no | 0.205 | — |
  | 09:47:03 | 5 | 0.38 | 0.37 | no | 0.205 | — |
  | 09:48:03 | 5 | 0.48 | 0.47 | no | 0.205 | — |
  | 09:49:03 | 5 | 0.4 | 0.39 | no | 0.205 | — |
  | 09:50:04 | 5 | 0.43 | 0.42 | no | 0.205 | — |
  | 09:51:03 | 5 | 0.43 | 0.42 | no | 0.205 | — |
  | 09:52:03 | 5 | 0.52 | 0.51 | no | 0.205 | — |
  | 09:53:03 | 5 | 0.57 | 0.52 | no | 0.205 | — |
  | 09:54:03 | 5 | 0.63 | 0.58 | yes | 0.41 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 09:55:04 | 2 | 0.62 | 0.61 | yes | 0.5355 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 09:56:03 | 2 | 0.69 | 0.68 | yes | 0.5865 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 09:57:03 | 2 | 0.65 | 0.64 | yes | 0.5865 | — |
  | 09:58:04 | 2 | 0.68 | 0.63 | yes | 0.5865 | — |
  | 09:59:04 | 2 | 0.75 | 0.74 | yes | 0.6375 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:00:04 | 2 | 0.81 | 0.8 | yes | 0.6885 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:01:03 | 2 | 0.77 | 0.72 | yes | 0.6885 | — |
  | 10:02:04 | 2 | 0.77 | 0.76 | yes | 0.6885 | — |
  | 10:03:03 | 2 | 0.95 | 0.94 | yes | 0.8075 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:04:03 | 2 | 0.76 | 0.75 | yes | 0.8075 | **SELL_ALL 2 `trail`** (runner_stop @ 0.81) |

- **Tags:** `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $1,825.00 (realized $145.00, delta $1,680.00); oracle $2,120.00.
- **Parity control** — this trade's own as-placed shape, replayed: $91.76 vs $145.00 realized (gap $-53.24 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$145.00** |
  | `hold_to_time_stop` | $1,825.00 |
  | `tp1_100_trail_10` | $186.40 |
  | `all_out_at_tp1_100` | $185.00 |
  | `tp1_100_trail_20` | $169.80 |
  | `all_out_at_tp1_50` | $92.50 |
  | `tp1_30_trail_125` | $52.90 |
  | `trail_only_no_tp1` | $0.00 |

### 2026-08-03 · risky-3 · `SPY260803C00754000` · realized $176.00

- **Entry** 09:42:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **750.98**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 754 (trigger 750.98, offset 3.02), quoted premium 0.35, filled **0.38** × 5, stop `STRUCTURE@750.98 (cat -50%)`.
- **Entry fill quality** — paid 22.6% above the signal minute's low (bar 0.31–0.39).
- **High-water WHILE IN THE TRADE** 1.0 (163.2% vs entry) at 2026-08-03T14:03:00Z UTC · 23 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.61 (1113.2%) at 2026-08-03T19:28:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:01:06 | 3 | 0.73 | 92.1% | `tp1` | 0.83 | $30.00 (12.0%) |
  | 10:05:06 | 1 | 0.74 | 94.7% | `?` | 1.0 | $26.00 (26.0%) |
  | 10:05:06 | 1 | 0.73 | 92.1% | `?` | 1.0 | $27.00 (27.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:03 | 5 | 0.3 | 0.29 | no | 0.19 | — |
  | 09:44:03 | 5 | 0.34 | 0.33 | no | 0.19 | — |
  | 09:45:03 | 5 | 0.44 | 0.43 | no | 0.19 | — |
  | 09:46:03 | 5 | 0.4 | 0.39 | no | 0.19 | — |
  | 09:47:03 | 5 | 0.38 | 0.33 | no | 0.19 | — |
  | 09:48:03 | 5 | 0.48 | 0.47 | no | 0.19 | — |
  | 09:49:03 | 5 | 0.4 | 0.39 | no | 0.19 | — |
  | 09:50:04 | 5 | 0.41 | 0.4 | no | 0.19 | — |
  | 09:51:03 | 5 | 0.4 | 0.39 | no | 0.19 | — |
  | 09:52:03 | 5 | 0.52 | 0.51 | no | 0.19 | — |
  | 09:53:03 | 5 | 0.57 | 0.52 | no | 0.19 | — |
  | 09:54:03 | 5 | 0.63 | 0.58 | no | 0.19 | — |
  | 09:55:04 | 5 | 0.61 | 0.6 | no | 0.19 | — |
  | 09:56:03 | 5 | 0.69 | 0.64 | no | 0.19 | — |
  | 09:57:03 | 5 | 0.66 | 0.6 | no | 0.19 | — |
  | 09:58:04 | 5 | 0.68 | 0.63 | no | 0.19 | — |
  | 09:59:04 | 5 | 0.74 | 0.73 | no | 0.19 | — |
  | 10:00:04 | 5 | 0.75 | 0.74 | no | 0.19 | — |
  | 10:01:03 | 5 | 0.77 | 0.76 | yes | 0.38 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:02:04 | 2 | 0.79 | 0.73 | yes | 0.632 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:03:03 | 2 | 0.95 | 0.94 | yes | 0.76 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:04:03 | 2 | 0.78 | 0.77 | yes | 0.76 | — |
  | 10:05:04 | 2 | 0.73 | 0.72 | yes | 0.76 | **SELL_ALL 2 `trail`** (runner_stop @ 0.76) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $1,820.00 (realized $176.00, delta $1,644.00); oracle $2,115.00.
- **Parity control** — this trade's own as-placed shape, replayed: $183.24 vs $176.00 realized (gap $7.24 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$176.00** |
  | `hold_to_time_stop` | $1,820.00 |
  | `all_out_at_tp1_100` | $190.00 |
  | `tp1_100_trail_10` | $187.40 |
  | `tp1_100_trail_20` | $170.80 |
  | `all_out_at_tp1_50` | $95.00 |
  | `tp1_30_trail_125` | $53.10 |
  | `trail_only_no_tp1` | $-5.00 |

### 2026-08-04 · risky-1 · `SPY260804C00763000` · realized $640.00

- **Entry** 09:50:06 ET — `VWAP_CONTINUATION` (ENTER_BULL), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation C (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 763 (trigger None, offset None), quoted premium 1.17, filled **1.39** × 5, stop `1.30 (-6%)`.
- **Entry fill quality** — paid 18.8% above the signal minute's low (bar 1.17–1.5).
- **High-water WHILE IN THE TRADE** 5.02 (261.1% vs entry) at 2026-08-04T15:25:00Z UTC · 95 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 10.34 (643.9%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:06:06 | 4 | 2.12 | 52.5% | `tp1` | 2.27 | $60.00 (6.6%) |
  | 11:25:06 | 1 | 4.87 | 250.4% | `runner_target` | 5.02 | $15.00 (3.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:51:05 | 5 | 1.42 | 1.41 | no | 1.3066 | — |
  | 09:52:05 | 5 | 1.43 | 1.42 | no | 1.3066 | — |
  | 09:53:04 | 5 | 1.46 | 1.45 | no | 1.3066 | — |
  | 09:54:05 | 5 | 1.56 | 1.54 | no | 1.3066 | — |
  | 09:55:05 | 5 | 1.65 | 1.64 | no | 1.3066 | — |
  | 09:56:05 | 5 | 1.39 | 1.37 | no | 1.3066 | — |
  | 09:57:07 | 5 | 1.41 | 1.4 | no | 1.3066 | — |
  | 09:58:05 | 5 | 1.4 | 1.39 | no | 1.3066 | — |
  | 09:59:05 | 5 | 1.53 | 1.52 | no | 1.3066 | — |
  | 10:00:06 | 5 | 1.56 | 1.54 | no | 1.3066 | — |
  | 10:01:05 | 5 | 1.69 | 1.67 | no | 1.3066 | — |
  | 10:02:05 | 5 | 1.86 | 1.8 | no | 1.3066 | — |
  | 10:03:05 | 5 | 1.95 | 1.9 | no | 1.3066 | — |
  | 10:04:05 | 5 | 2.04 | 1.98 | no | 1.3066 | — |
  | 10:05:05 | 5 | 1.88 | 1.86 | no | 1.3066 | — |
  | 10:06:05 | 5 | 2.11 | 2.1 | yes | 1.39 | **SELL_PARTIAL 4 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:07:06 | 1 | 2.24 | 2.18 | yes | 1.39 | — |
  | 10:08:05 | 1 | 2.26 | 2.22 | yes | 1.39 | — |
  | 10:09:05 | 1 | 2.3 | 2.28 | yes | 1.39 | — |
  | 10:10:06 | 1 | 2.19 | 2.17 | yes | 1.39 | — |
  | 10:11:05 | 1 | 2.28 | 2.23 | yes | 1.39 | — |
  | 10:12:05 | 1 | 2.33 | 2.31 | yes | 1.39 | — |
  | 10:13:05 | 1 | 2.46 | 2.45 | yes | 1.39 | — |
  | 10:14:04 | 1 | 2.53 | 2.49 | yes | 1.39 | — |
  | 10:15:05 | 1 | 2.6 | 2.58 | yes | 1.39 | — |
  | 10:16:04 | 1 | 2.68 | 2.65 | yes | 1.39 | — |
  | 10:17:05 | 1 | 2.64 | 2.63 | yes | 1.39 | — |
  | 10:18:04 | 1 | 2.91 | 2.89 | yes | 1.39 | — |
  | 10:19:04 | 1 | 2.95 | 2.84 | yes | 1.39 | — |
  | 10:20:05 | 1 | 2.83 | 2.79 | yes | 1.39 | — |
  | 10:21:05 | 1 | 2.59 | 2.49 | yes | 1.39 | — |
  | 10:22:05 | 1 | 2.37 | 2.35 | yes | 1.39 | — |
  | 10:23:04 | 1 | 2.32 | 2.3 | yes | 1.39 | — |
  | 10:24:04 | 1 | 2.42 | 2.38 | yes | 1.39 | — |
  | 10:25:05 | 1 | 2.28 | 2.21 | yes | 1.39 | — |
  | 10:26:04 | 1 | 2.58 | 2.56 | yes | 1.39 | — |
  | 10:27:08 | 1 | 2.56 | 2.54 | yes | 1.39 | — |
  | 10:28:06 | 1 | 2.53 | 2.51 | yes | 1.39 | — |
  | 10:29:06 | 1 | 2.24 | 2.22 | yes | 1.39 | — |
  | 10:30:06 | 1 | 2.33 | 2.3 | yes | 1.39 | — |
  | 10:31:06 | 1 | 2.11 | 2.04 | yes | 1.39 | — |
  | 10:32:06 | 1 | 2.12 | 2.11 | yes | 1.39 | — |
  | 10:33:06 | 1 | 2.54 | 2.47 | yes | 1.39 | — |
  | 10:34:06 | 1 | 2.54 | 2.53 | yes | 1.39 | — |
  | 10:35:05 | 1 | 2.69 | 2.61 | yes | 1.39 | — |
  | 10:36:05 | 1 | 2.65 | 2.59 | yes | 1.39 | — |
  | 10:37:05 | 1 | 2.57 | 2.54 | yes | 1.39 | — |
  | 10:38:04 | 1 | 2.66 | 2.57 | yes | 1.39 | — |
  | 10:39:05 | 1 | 2.65 | 2.63 | yes | 1.39 | — |
  | 10:40:04 | 1 | 2.72 | 2.63 | yes | 1.39 | — |
  | 10:41:04 | 1 | 2.81 | 2.71 | yes | 1.39 | — |
  | 10:42:04 | 1 | 2.84 | 2.76 | yes | 1.39 | — |
  | 10:43:04 | 1 | 2.89 | 2.84 | yes | 1.39 | — |
  | 10:44:05 | 1 | 3.08 | 3.05 | yes | 1.39 | — |
  | 10:45:07 | 1 | 3.05 | 3.03 | yes | 1.39 | — |
  | 10:46:05 | 1 | 3.03 | 3.0 | yes | 1.39 | — |
  | 10:47:04 | 1 | 3.09 | 3.06 | yes | 1.39 | — |
  | 10:48:04 | 1 | 3.13 | 3.07 | yes | 1.39 | — |
  | 10:49:04 | 1 | 3.26 | 3.17 | yes | 1.39 | — |
  | 10:50:05 | 1 | 3.34 | 3.23 | yes | 1.39 | — |
  | 10:51:05 | 1 | 3.25 | 3.19 | yes | 1.39 | — |
  | 10:52:05 | 1 | 3.18 | 3.15 | yes | 1.39 | — |
  | 10:53:05 | 1 | 3.27 | 3.2 | yes | 1.39 | — |
  | 10:54:04 | 1 | 3.23 | 3.2 | yes | 1.39 | — |
  | 10:55:05 | 1 | 3.35 | 3.25 | yes | 1.39 | — |
  | 10:56:04 | 1 | 3.35 | 3.24 | yes | 1.39 | — |
  | 10:57:05 | 1 | 3.42 | 3.4 | yes | 1.39 | — |
  | 10:58:05 | 1 | 3.46 | 3.37 | yes | 1.39 | — |
  | 10:59:04 | 1 | 3.64 | 3.62 | yes | 1.39 | — |
  | 11:00:05 | 1 | 3.66 | 3.56 | yes | 1.39 | — |
  | 11:01:04 | 1 | 3.66 | 3.61 | yes | 1.39 | — |
  | 11:02:05 | 1 | 3.91 | 3.85 | yes | 1.39 | — |
  | 11:03:05 | 1 | 3.86 | 3.84 | yes | 1.39 | — |
  | 11:04:04 | 1 | 4.12 | 3.96 | yes | 1.39 | — |
  | 11:05:05 | 1 | 4.19 | 4.16 | yes | 1.39 | — |
  | 11:06:05 | 1 | 3.92 | 3.89 | yes | 1.39 | — |
  | 11:07:05 | 1 | 3.96 | 3.93 | yes | 1.39 | — |
  | 11:08:05 | 1 | 3.8 | 3.78 | yes | 1.39 | — |
  | 11:09:04 | 1 | 3.88 | 3.8 | yes | 1.39 | — |
  | 11:10:05 | 1 | 4.14 | 4.07 | yes | 1.39 | — |
  | 11:11:05 | 1 | 4.01 | 4.0 | yes | 1.39 | — |
  | 11:12:05 | 1 | 4.09 | 4.03 | yes | 1.39 | — |
  | 11:13:05 | 1 | 4.16 | 4.14 | yes | 1.39 | — |
  | 11:14:04 | 1 | 4.34 | 4.3 | yes | 1.39 | — |
  | 11:15:05 | 1 | 4.14 | 4.11 | yes | 1.39 | — |
  | 11:16:04 | 1 | 4.46 | 4.31 | yes | 1.39 | — |
  | 11:17:04 | 1 | 4.48 | 4.43 | yes | 1.39 | — |
  | 11:18:04 | 1 | 4.46 | 4.36 | yes | 1.39 | — |
  | 11:19:04 | 1 | 4.56 | 4.4 | yes | 1.39 | — |
  | 11:20:05 | 1 | 4.59 | 4.56 | yes | 1.39 | — |
  | 11:21:04 | 1 | 4.65 | 4.51 | yes | 1.39 | — |
  | 11:22:04 | 1 | 4.7 | 4.57 | yes | 1.39 | — |
  | 11:23:04 | 1 | 4.59 | 4.56 | yes | 1.39 | — |
  | 11:24:04 | 1 | 4.81 | 4.78 | yes | 1.39 | — |
  | 11:25:05 | 1 | 4.92 | 4.8 | yes | 1.39 | **SELL_ALL 1 `runner_target`** (runner_target @ +250%) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $4,145.00 (realized $640.00, delta $3,505.00); oracle $4,475.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-41.70 vs $640.00 realized (gap $-681.70 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$640.00** |
  | `hold_to_time_stop` | $4,145.00 |
  | `all_out_at_tp1_100` | $695.00 |
  | `tp1_100_trail_10` | $679.00 |
  | `tp1_100_trail_20` | $619.00 |
  | `all_out_at_tp1_50` | $347.50 |
  | `tp1_30_trail_125` | $215.92 |
  | `trail_only_no_tp1` | $5.00 |

### 2026-08-04 · risky-3 · `SPY260804C00763000` · realized $524.00

- **Entry** 09:50:06 ET — `VWAP_CONTINUATION` (ENTER_BULL), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation C (BASE)_
- **Strike** 763 (trigger None, offset None), quoted premium 1.46, filled **1.4** × 8, stop `1.37 (-6%)`.
- **Entry fill quality** — paid 6.9% above the signal minute's low (bar 1.31–1.46).
- **High-water WHILE IN THE TRADE** 3.0 (114.3% vs entry) at 2026-08-04T14:19:00Z UTC · 30 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 10.34 (638.6%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:04:07 | 6 | 1.99 | 42.1% | `tp1` | 2.03 | $24.00 (2.0%) |
  | 10:23:06 | 2 | 2.25 | 60.7% | `trail` | 3.0 | $150.00 (25.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:51:05 | 8 | 1.39 | 1.38 | no | 1.3724 | — |
  | 09:52:05 | 8 | 1.38 | 1.36 | no | 1.3724 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 1.37) |
  | 09:55:05 | 8 | 1.64 | 1.62 | no | 1.4288 | — |
  | 09:56:05 | 8 | 1.39 | 1.37 | no | 1.4288 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 1.43) |
  | 09:58:05 | 8 | 1.39 | 1.38 | no | 1.316 | — |
  | 09:59:05 | 8 | 1.53 | 1.52 | no | 1.316 | — |
  | 10:00:06 | 8 | 1.56 | 1.54 | no | 1.316 | — |
  | 10:01:05 | 8 | 1.69 | 1.67 | no | 1.316 | — |
  | 10:02:05 | 8 | 1.83 | 1.82 | no | 1.316 | — |
  | 10:03:05 | 8 | 1.91 | 1.89 | no | 1.316 | — |
  | 10:04:05 | 8 | 2.03 | 2.02 | yes | 1.4 | **SELL_PARTIAL 6 `tp1`** (tp1 @ +40%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:05:05 | 2 | 1.88 | 1.86 | yes | 1.624 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:06:05 | 2 | 2.13 | 2.12 | yes | 1.704 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:07:06 | 2 | 2.23 | 2.21 | yes | 1.784 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:08:05 | 2 | 2.31 | 2.28 | yes | 1.848 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:09:05 | 2 | 2.3 | 2.28 | yes | 1.848 | — |
  | 10:10:06 | 2 | 2.23 | 2.22 | yes | 1.848 | — |
  | 10:11:05 | 2 | 2.3 | 2.22 | yes | 1.848 | — |
  | 10:12:05 | 2 | 2.34 | 2.27 | yes | 1.872 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:13:05 | 2 | 2.46 | 2.45 | yes | 1.968 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:14:04 | 2 | 2.48 | 2.44 | yes | 1.984 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:15:05 | 2 | 2.55 | 2.52 | yes | 2.04 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:16:04 | 2 | 2.68 | 2.65 | yes | 2.144 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:17:05 | 2 | 2.64 | 2.63 | yes | 2.144 | — |
  | 10:18:04 | 2 | 2.91 | 2.89 | yes | 2.328 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:19:04 | 2 | 2.86 | 2.85 | yes | 2.328 | — |
  | 10:20:05 | 2 | 2.86 | 2.83 | yes | 2.328 | — |
  | 10:21:05 | 2 | 2.59 | 2.49 | yes | 2.328 | — |
  | 10:22:05 | 2 | 2.37 | 2.36 | yes | 2.328 | — |
  | 10:23:04 | 2 | 2.25 | 2.23 | yes | 2.328 | **SELL_ALL 2 `trail`** (runner_stop @ 2.33) |

- **Tags:** `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $6,624.00 (realized $524.00, delta $6,100.00); oracle $7,152.00.
- **Parity control** — this trade's own as-placed shape, replayed: $432.24 vs $524.00 realized (gap $-91.76 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$524.00** |
  | `hold_to_time_stop` | $6,624.00 |
  | `all_out_at_tp1_100` | $1,120.00 |
  | `tp1_100_trail_10` | $1,090.00 |
  | `tp1_100_trail_20` | $1,000.00 |
  | `all_out_at_tp1_50` | $560.00 |
  | `tp1_30_trail_125` | $348.24 |
  | `trail_only_no_tp1` | $88.00 |

### 2026-08-04 · safe-2 · `SPY260804C00763000` · realized $383.00

- **Entry** 09:56:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.35** × 3, stop `STRUCTURE@763.10 (cat -50%)`.
- **Entry fill quality** — paid 7.1% above the signal minute's low (bar 1.26–1.4).
- **High-water WHILE IN THE TRADE** 3.0 (122.2% vs entry) at 2026-08-04T14:19:00Z UTC · 25 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 10.34 (665.9%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:16:04 | 2 | 2.7 | 100.0% | `tp1` | 2.73 | $6.00 (1.1%) |
  | 10:21:04 | 1 | 2.48 | 83.7% | `trail` | 3.0 | $52.00 (17.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:57:07 | 3 | 1.41 | 1.4 | no | 0.675 | — |
  | 09:58:03 | 3 | 1.36 | 1.35 | no | 0.675 | — |
  | 09:59:03 | 3 | 1.54 | 1.53 | no | 0.675 | — |
  | 10:00:04 | 3 | 1.56 | 1.52 | no | 0.675 | — |
  | 10:01:03 | 3 | 1.67 | 1.65 | no | 0.675 | — |
  | 10:02:03 | 3 | 1.82 | 1.81 | no | 0.675 | — |
  | 10:03:03 | 3 | 1.95 | 1.93 | no | 0.675 | — |
  | 10:04:03 | 3 | 2.05 | 2.04 | no | 0.675 | — |
  | 10:05:03 | 3 | 1.9 | 1.84 | no | 0.675 | — |
  | 10:06:03 | 3 | 2.15 | 2.13 | no | 0.675 | — |
  | 10:07:05 | 3 | 2.25 | 2.23 | no | 0.675 | — |
  | 10:08:03 | 3 | 2.3 | 2.29 | no | 0.675 | — |
  | 10:09:04 | 3 | 2.33 | 2.3 | no | 0.675 | — |
  | 10:10:04 | 3 | 2.23 | 2.21 | no | 0.675 | — |
  | 10:11:03 | 3 | 2.27 | 2.25 | no | 0.675 | — |
  | 10:12:03 | 3 | 2.3 | 2.28 | no | 0.675 | — |
  | 10:13:03 | 3 | 2.45 | 2.44 | no | 0.675 | — |
  | 10:14:03 | 3 | 2.54 | 2.51 | no | 0.675 | — |
  | 10:15:03 | 3 | 2.59 | 2.57 | no | 0.675 | — |
  | 10:16:03 | 3 | 2.74 | 2.72 | yes | 1.35 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:17:04 | 1 | 2.61 | 2.58 | yes | 2.329 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:18:03 | 1 | 3.0 | 2.97 | yes | 2.55 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:19:03 | 1 | 2.93 | 2.88 | yes | 2.55 | — |
  | 10:20:03 | 1 | 2.85 | 2.83 | yes | 2.55 | — |
  | 10:21:03 | 1 | 2.53 | 2.52 | yes | 2.55 | **SELL_ALL 1 `trail`** (runner_stop @ 2.55) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $2,499.00 (realized $383.00, delta $2,116.00); oracle $2,697.00.
- **Parity control** — this trade's own as-placed shape, replayed: $418.50 vs $383.00 realized (gap $35.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$383.00** |
  | `hold_to_time_stop` | $2,499.00 |
  | `all_out_at_tp1_100` | $405.00 |
  | `tp1_100_trail_10` | $398.70 |
  | `tp1_100_trail_20` | $375.00 |
  | `all_out_at_tp1_50` | $202.50 |
  | `tp1_30_trail_125` | $134.12 |
  | `trail_only_no_tp1` | $-3.00 |

### 2026-08-04 · bold-2 · `SPY260804C00763000` · realized $614.00

- **Entry** 09:56:51 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.38** × 5, stop `STRUCTURE@763.10 (cat -50%)`.
- **Entry fill quality** — paid 5.3% above the signal minute's low (bar 1.31–1.46).
- **High-water WHILE IN THE TRADE** 3.0 (117.4% vs entry) at 2026-08-04T14:19:00Z UTC · 25 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 10.34 (649.3%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:16:05 | 3 | 2.68 | 94.2% | `tp1` | 2.73 | $15.00 (1.8%) |
  | 10:21:06 | 2 | 2.5 | 81.2% | `trail` | 3.0 | $100.00 (16.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:57:26 | 5 | 1.44 | 1.43 | no | 0.69 | — |
  | 09:58:24 | 5 | 1.44 | 1.43 | no | 0.69 | — |
  | 09:59:04 | 5 | 1.51 | 1.46 | no | 0.69 | — |
  | 10:00:05 | 5 | 1.51 | 1.49 | no | 0.69 | — |
  | 10:01:05 | 5 | 1.68 | 1.66 | no | 0.69 | — |
  | 10:02:04 | 5 | 1.85 | 1.84 | no | 0.69 | — |
  | 10:03:04 | 5 | 1.94 | 1.93 | no | 0.69 | — |
  | 10:04:05 | 5 | 2.02 | 1.96 | no | 0.69 | — |
  | 10:05:04 | 5 | 1.91 | 1.86 | no | 0.69 | — |
  | 10:06:41 | 5 | 2.19 | 2.12 | no | 0.69 | — |
  | 10:07:45 | 5 | 2.23 | 2.22 | no | 0.69 | — |
  | 10:08:54 | 5 | 2.35 | 2.27 | no | 0.69 | — |
  | 10:09:32 | 5 | 2.19 | 2.17 | no | 0.69 | — |
  | 10:10:57 | 5 | 2.33 | 2.32 | no | 0.69 | — |
  | 10:11:05 | 5 | 2.23 | 2.2 | no | 0.69 | — |
  | 10:12:05 | 5 | 2.33 | 2.31 | no | 0.69 | — |
  | 10:13:05 | 5 | 2.47 | 2.45 | no | 0.69 | — |
  | 10:14:04 | 5 | 2.5 | 2.48 | no | 0.69 | — |
  | 10:15:05 | 5 | 2.6 | 2.58 | no | 0.69 | — |
  | 10:16:04 | 5 | 2.76 | 2.65 | yes | 1.38 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:17:05 | 2 | 2.65 | 2.58 | yes | 2.346 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:18:04 | 2 | 2.99 | 2.95 | yes | 2.5415 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:19:04 | 2 | 2.91 | 2.87 | yes | 2.5415 | — |
  | 10:20:05 | 2 | 2.89 | 2.85 | yes | 2.5415 | — |
  | 10:21:05 | 2 | 2.55 | 2.53 | yes | 2.5415 | **SELL_ALL 2 `trail`** (runner_stop @ 2.54) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $4,150.00 (realized $614.00, delta $3,536.00); oracle $4,480.00.
- **Parity control** — this trade's own as-placed shape, replayed: $814.20 vs $614.00 realized (gap $200.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$614.00** |
  | `hold_to_time_stop` | $4,150.00 |
  | `all_out_at_tp1_100` | $690.00 |
  | `tp1_100_trail_10` | $678.00 |
  | `tp1_100_trail_20` | $618.00 |
  | `all_out_at_tp1_50` | $345.00 |
  | `tp1_30_trail_125` | $215.72 |
  | `trail_only_no_tp1` | $65.00 |

### 2026-08-04 · safe-3 · `SPY260804C00763000` · realized $373.00

- **Entry** 09:58:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **763.1**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 763 (trigger 763.1, offset -0.1), quoted premium 1.38, filled **1.38** × 3, stop `STRUCTURE@763.10 (cat -50%)`.
- **Entry fill quality** — paid 3.0% above the signal minute's low (bar 1.34–1.54).
- **High-water WHILE IN THE TRADE** 3.0 (117.4% vs entry) at 2026-08-04T14:19:00Z UTC · 23 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 10.34 (649.3%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:16:05 | 2 | 2.68 | 94.2% | `tp1` | 2.73 | $10.00 (1.8%) |
  | 10:21:06 | 1 | 2.51 | 81.9% | `trail` | 3.0 | $49.00 (16.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:59:05 | 3 | 1.51 | 1.46 | no | 0.69 | — |
  | 10:00:06 | 3 | 1.51 | 1.49 | no | 0.69 | — |
  | 10:01:05 | 3 | 1.68 | 1.66 | no | 0.69 | — |
  | 10:02:05 | 3 | 1.85 | 1.84 | no | 0.69 | — |
  | 10:03:05 | 3 | 1.94 | 1.93 | no | 0.69 | — |
  | 10:04:05 | 3 | 2.02 | 1.96 | no | 0.69 | — |
  | 10:05:05 | 3 | 1.91 | 1.86 | no | 0.69 | — |
  | 10:06:05 | 3 | 2.14 | 2.12 | no | 0.69 | — |
  | 10:07:06 | 3 | 2.19 | 2.18 | no | 0.69 | — |
  | 10:08:05 | 3 | 2.26 | 2.22 | no | 0.69 | — |
  | 10:09:05 | 3 | 2.26 | 2.24 | no | 0.69 | — |
  | 10:10:06 | 3 | 2.19 | 2.17 | no | 0.69 | — |
  | 10:11:05 | 3 | 2.27 | 2.26 | no | 0.69 | — |
  | 10:12:05 | 3 | 2.33 | 2.31 | no | 0.69 | — |
  | 10:13:05 | 3 | 2.47 | 2.45 | no | 0.69 | — |
  | 10:14:04 | 3 | 2.53 | 2.49 | no | 0.69 | — |
  | 10:15:05 | 3 | 2.6 | 2.58 | no | 0.69 | — |
  | 10:16:04 | 3 | 2.76 | 2.65 | yes | 1.38 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:17:05 | 1 | 2.65 | 2.58 | yes | 2.346 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:18:04 | 1 | 2.99 | 2.95 | yes | 2.5415 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:19:04 | 1 | 2.91 | 2.87 | yes | 2.5415 | — |
  | 10:20:05 | 1 | 2.89 | 2.85 | yes | 2.5415 | — |
  | 10:21:05 | 1 | 2.55 | 2.53 | yes | 2.5415 | **SELL_ALL 1 `trail`** (runner_stop @ 2.54) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $2,490.00 (realized $373.00, delta $2,117.00); oracle $2,688.00.
- **Parity control** — this trade's own as-placed shape, replayed: $400.50 vs $373.00 realized (gap $27.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$373.00** |
  | `hold_to_time_stop` | $2,490.00 |
  | `all_out_at_tp1_100` | $414.00 |
  | `tp1_100_trail_10` | $408.00 |
  | `tp1_100_trail_20` | $378.00 |
  | `trail_only_no_tp1` | $291.00 |
  | `all_out_at_tp1_50` | $207.00 |
  | `tp1_30_trail_125` | $132.92 |

### 2026-08-04 · safe-3 · `SPY260804C00769000` · realized $378.00

- **Entry** 11:52:08 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **768.61**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 769 (trigger 768.61, offset 0.39), quoted premium 1.21, filled **1.33** × 3, stop `STRUCTURE@768.61 (cat -50%)`.
- **Entry fill quality** — paid 1.5% above the signal minute's low (bar 1.31–1.37).
- **High-water WHILE IN THE TRADE** 3.04 (128.6% vs entry) at 2026-08-04T17:17:00Z UTC · 60 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.4 (230.8%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:08:07 | 2 | 2.61 | 96.2% | `tp1` | 2.74 | $26.00 (4.7%) |
  | 13:23:07 | 1 | 2.55 | 91.7% | `trail` | 3.04 | $49.00 (16.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:53:06 | 3 | 1.25 | 1.24 | no | 0.605 | — |
  | 11:54:06 | 3 | 0.95 | 0.94 | no | 0.605 | — |
  | 11:55:07 | 3 | 0.95 | 0.94 | no | 0.605 | — |
  | 11:56:04 | 3 | 1.03 | 1.02 | no | 0.605 | — |
  | 11:57:05 | 3 | 1.03 | 1.02 | no | 0.605 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 768.61) |
  | 12:29:06 | 3 | 1.37 | 1.32 | no | 0.665 | — |
  | 12:30:05 | 3 | 1.26 | 1.25 | no | 0.665 | — |
  | 12:31:05 | 3 | 1.32 | 1.31 | no | 0.665 | — |
  | 12:32:06 | 3 | 1.37 | 1.36 | no | 0.665 | — |
  | 12:33:05 | 3 | 1.41 | 1.4 | no | 0.665 | — |
  | 12:34:04 | 3 | 1.52 | 1.51 | no | 0.665 | — |
  | 12:35:05 | 3 | 1.47 | 1.41 | no | 0.665 | — |
  | 12:36:04 | 3 | 1.44 | 1.43 | no | 0.665 | — |
  | 12:37:05 | 3 | 1.56 | 1.51 | no | 0.665 | — |
  | 12:38:05 | 3 | 1.45 | 1.44 | no | 0.665 | — |
  | 12:39:07 | 3 | 1.41 | 1.35 | no | 0.665 | — |
  | 12:40:07 | 3 | 1.47 | 1.42 | no | 0.665 | — |
  | 12:41:05 | 3 | 1.42 | 1.41 | no | 0.665 | — |
  | 12:42:05 | 3 | 1.46 | 1.45 | no | 0.665 | — |
  | 12:43:04 | 3 | 1.48 | 1.46 | no | 0.665 | — |
  | 12:44:04 | 3 | 1.58 | 1.56 | no | 0.665 | — |
  | 12:45:05 | 3 | 1.72 | 1.7 | no | 0.665 | — |
  | 12:46:05 | 3 | 1.89 | 1.88 | no | 0.665 | — |
  | 12:47:08 | 3 | 1.77 | 1.76 | no | 0.665 | — |
  | 12:48:07 | 3 | 1.78 | 1.77 | no | 0.665 | — |
  | 12:49:06 | 3 | 1.71 | 1.7 | no | 0.665 | — |
  | 12:50:08 | 3 | 1.86 | 1.84 | no | 0.665 | — |
  | 12:51:05 | 3 | 1.91 | 1.84 | no | 0.665 | — |
  | 12:52:06 | 3 | 1.87 | 1.86 | no | 0.665 | — |
  | 12:53:05 | 3 | 1.84 | 1.82 | no | 0.665 | — |
  | 12:54:05 | 3 | 1.92 | 1.9 | no | 0.665 | — |
  | 12:55:06 | 3 | 1.85 | 1.83 | no | 0.665 | — |
  | 12:56:06 | 3 | 1.82 | 1.76 | no | 0.665 | — |
  | 12:57:06 | 3 | 1.84 | 1.83 | no | 0.665 | — |
  | 12:58:07 | 3 | 1.88 | 1.86 | no | 0.665 | — |
  | 12:59:05 | 3 | 1.84 | 1.83 | no | 0.665 | — |
  | 13:00:05 | 3 | 1.95 | 1.86 | no | 0.665 | — |
  | 13:01:05 | 3 | 2.24 | 2.17 | no | 0.665 | — |
  | 13:02:05 | 3 | 2.3 | 2.28 | no | 0.665 | — |
  | 13:03:05 | 3 | 2.24 | 2.22 | no | 0.665 | — |
  | 13:04:05 | 3 | 2.44 | 2.43 | no | 0.665 | — |
  | 13:05:05 | 3 | 2.61 | 2.52 | no | 0.665 | — |
  | 13:06:04 | 3 | 2.42 | 2.39 | no | 0.665 | — |
  | 13:07:07 | 3 | 2.46 | 2.45 | no | 0.665 | — |
  | 13:08:06 | 3 | 2.66 | 2.63 | yes | 1.33 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:09:06 | 1 | 2.65 | 2.62 | yes | 2.261 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:10:08 | 1 | 2.6 | 2.58 | yes | 2.261 | — |
  | 13:11:04 | 1 | 2.48 | 2.46 | yes | 2.261 | — |
  | 13:12:05 | 1 | 2.67 | 2.59 | yes | 2.2695 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:13:05 | 1 | 2.67 | 2.64 | yes | 2.2695 | — |
  | 13:14:04 | 1 | 2.66 | 2.65 | yes | 2.2695 | — |
  | 13:15:06 | 1 | 2.74 | 2.72 | yes | 2.329 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:16:05 | 1 | 2.76 | 2.74 | yes | 2.346 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:17:05 | 1 | 2.86 | 2.83 | yes | 2.431 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:18:04 | 1 | 3.02 | 3.01 | yes | 2.567 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:19:05 | 1 | 2.89 | 2.87 | yes | 2.567 | — |
  | 13:20:05 | 1 | 2.94 | 2.92 | yes | 2.567 | — |
  | 13:21:04 | 1 | 2.65 | 2.63 | yes | 2.567 | — |
  | 13:22:04 | 1 | 2.65 | 2.63 | yes | 2.567 | — |
  | 13:23:06 | 1 | 2.55 | 2.51 | yes | 2.567 | **SELL_ALL 1 `trail`** (runner_stop @ 2.57) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `hold_to_time_stop` at $636.00 (realized $378.00, delta $258.00); oracle $921.00.
- **Parity control** — this trade's own as-placed shape, replayed: $372.75 vs $378.00 realized (gap $-5.25 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$378.00** |
  | `hold_to_time_stop` | $636.00 |
  | `tp1_100_trail_20` | $473.80 |
  | `all_out_at_tp1_100` | $399.00 |
  | `tp1_100_trail_10` | $379.60 |
  | `all_out_at_tp1_50` | $199.50 |
  | `tp1_30_trail_125` | $186.55 |
  | `trail_only_no_tp1` | $24.00 |

### 2026-08-04 · risky-1 · `SPY260804C00769000` · realized $651.00

- **Entry** 11:52:08 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **768.61**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 769 (trigger 768.61, offset 0.39), quoted premium 1.23, filled **1.33** × 5, stop `STRUCTURE@768.61 (cat -50%)`.
- **Entry fill quality** — paid 1.5% above the signal minute's low (bar 1.31–1.37).
- **High-water WHILE IN THE TRADE** 4.26 (220.3% vs entry) at 2026-08-04T17:49:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.4 (230.8%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:01:07 | 2 | 2.19 | 64.7% | `trail` | 2.32 | $26.00 (5.6%) |
  | 13:01:07 | 1 | 2.2 | 65.4% | `?` | 2.32 | $12.00 (5.2%) |
  | 13:51:07 | 2 | 3.29 | 147.4% | `trail` | 4.26 | $194.00 (22.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:53:06 | 5 | 1.25 | 1.24 | no | 0.605 | — |
  | 11:54:06 | 5 | 0.95 | 0.94 | no | 0.605 | — |
  | 11:55:07 | 5 | 0.96 | 0.95 | no | 0.605 | — |
  | 11:56:04 | 5 | 1.03 | 1.02 | no | 0.605 | — |
  | 11:57:05 | 5 | 1.02 | 1.01 | no | 0.605 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 768.61) |
  | 12:29:06 | 5 | 1.37 | 1.36 | no | 0.665 | — |
  | 12:30:05 | 5 | 1.24 | 1.19 | no | 0.665 | — |
  | 12:31:05 | 5 | 1.32 | 1.31 | no | 0.665 | — |
  | 12:32:06 | 5 | 1.41 | 1.36 | no | 0.665 | — |
  | 12:33:05 | 5 | 1.41 | 1.4 | no | 0.665 | — |
  | 12:34:04 | 5 | 1.52 | 1.51 | no | 0.665 | — |
  | 12:35:05 | 5 | 1.47 | 1.41 | no | 0.665 | — |
  | 12:36:04 | 5 | 1.46 | 1.4 | no | 0.665 | — |
  | 12:37:05 | 5 | 1.56 | 1.55 | no | 0.665 | — |
  | 12:38:05 | 5 | 1.4 | 1.39 | no | 0.665 | — |
  | 12:39:07 | 5 | 1.41 | 1.36 | no | 0.665 | — |
  | 12:40:07 | 5 | 1.44 | 1.43 | no | 0.665 | — |
  | 12:41:05 | 5 | 1.46 | 1.45 | no | 0.665 | — |
  | 12:42:05 | 5 | 1.46 | 1.45 | no | 0.665 | — |
  | 12:43:04 | 5 | 1.48 | 1.46 | no | 0.665 | — |
  | 12:44:04 | 5 | 1.58 | 1.56 | no | 0.665 | — |
  | 12:45:05 | 5 | 1.78 | 1.77 | no | 0.665 | — |
  | 12:46:05 | 5 | 1.85 | 1.84 | no | 0.665 | — |
  | 12:47:08 | 5 | 1.83 | 1.81 | no | 0.665 | — |
  | 12:48:07 | 5 | 1.83 | 1.77 | no | 0.665 | — |
  | 12:49:06 | 5 | 1.71 | 1.7 | no | 0.665 | — |
  | 12:50:08 | 5 | 1.81 | 1.8 | no | 0.665 | — |
  | 12:51:05 | 5 | 1.91 | 1.84 | no | 0.665 | — |
  | 12:52:06 | 5 | 1.87 | 1.86 | no | 0.665 | — |
  | 12:53:05 | 5 | 1.83 | 1.82 | no | 0.665 | — |
  | 12:54:05 | 5 | 1.92 | 1.9 | no | 0.665 | — |
  | 12:55:06 | 5 | 1.85 | 1.83 | no | 0.665 | — |
  | 12:56:06 | 5 | 1.82 | 1.76 | no | 0.665 | — |
  | 12:57:06 | 5 | 1.89 | 1.88 | no | 0.665 | — |
  | 12:58:07 | 5 | 1.88 | 1.86 | no | 0.665 | — |
  | 12:59:05 | 5 | 1.84 | 1.83 | no | 0.665 | — |
  | 13:00:05 | 5 | 1.95 | 1.86 | no | 0.665 | — |
  | 13:01:05 | 5 | 2.24 | 2.17 | yes | 1.33 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:02:05 | 2 | 2.3 | 2.28 | yes | 1.955 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:03:05 | 2 | 2.24 | 2.22 | yes | 1.955 | — |
  | 13:04:05 | 2 | 2.44 | 2.43 | yes | 2.074 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:05:05 | 2 | 2.54 | 2.52 | yes | 2.159 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:06:04 | 2 | 2.39 | 2.37 | yes | 2.159 | — |
  | 13:07:07 | 2 | 2.49 | 2.39 | yes | 2.159 | — |
  | 13:08:06 | 2 | 2.66 | 2.63 | yes | 2.261 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:09:06 | 2 | 2.72 | 2.64 | yes | 2.312 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:10:08 | 2 | 2.6 | 2.53 | yes | 2.312 | — |
  | 13:11:04 | 2 | 2.54 | 2.52 | yes | 2.312 | — |
  | 13:12:05 | 2 | 2.67 | 2.59 | yes | 2.312 | — |
  | 13:13:05 | 2 | 2.67 | 2.66 | yes | 2.312 | — |
  | 13:14:04 | 2 | 2.63 | 2.61 | yes | 2.312 | — |
  | 13:15:06 | 2 | 2.74 | 2.73 | yes | 2.329 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:16:05 | 2 | 2.76 | 2.74 | yes | 2.346 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:17:05 | 2 | 2.86 | 2.75 | yes | 2.431 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:18:04 | 2 | 3.02 | 3.01 | yes | 2.567 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:19:05 | 2 | 2.89 | 2.87 | yes | 2.567 | — |
  | 13:20:05 | 2 | 2.91 | 2.85 | yes | 2.567 | — |
  | 13:21:04 | 2 | 2.65 | 2.63 | yes | 2.567 | — |
  | 13:22:04 | 2 | 2.68 | 2.61 | yes | 2.567 | — |
  | 13:23:06 | 2 | 2.6 | 2.57 | yes | 2.567 | — |
  | 13:24:07 | 2 | 2.72 | 2.7 | yes | 2.567 | — |
  | 13:25:08 | 2 | 2.72 | 2.71 | yes | 2.567 | — |
  | 13:26:04 | 2 | 2.98 | 2.86 | yes | 2.567 | — |
  | 13:27:05 | 2 | 2.84 | 2.77 | yes | 2.567 | — |
  | 13:28:05 | 2 | 2.87 | 2.78 | yes | 2.567 | — |
  | 13:29:05 | 2 | 2.77 | 2.74 | yes | 2.567 | — |
  | 13:30:05 | 2 | 2.75 | 2.72 | yes | 2.567 | — |
  | 13:31:05 | 2 | 2.67 | 2.65 | yes | 2.567 | — |
  | 13:32:05 | 2 | 2.72 | 2.7 | yes | 2.567 | — |
  | 13:33:04 | 2 | 2.78 | 2.7 | yes | 2.567 | — |
  | 13:34:04 | 2 | 2.73 | 2.7 | yes | 2.567 | — |
  | 13:35:05 | 2 | 2.8 | 2.78 | yes | 2.567 | — |
  | 13:36:04 | 2 | 2.92 | 2.82 | yes | 2.567 | — |
  | 13:37:04 | 2 | 3.14 | 3.13 | yes | 2.669 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:38:04 | 2 | 3.1 | 3.05 | yes | 2.669 | — |
  | 13:39:04 | 2 | 3.11 | 3.02 | yes | 2.669 | — |
  | 13:40:05 | 2 | 3.2 | 3.18 | yes | 2.72 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:41:04 | 2 | 3.37 | 3.32 | yes | 2.8645 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:42:06 | 2 | 3.45 | 3.35 | yes | 2.9325 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:43:07 | 2 | 3.43 | 3.41 | yes | 2.9325 | — |
  | 13:44:07 | 2 | 3.5 | 3.48 | yes | 2.975 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:45:08 | 2 | 3.72 | 3.69 | yes | 3.162 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:46:05 | 2 | 3.72 | 3.7 | yes | 3.162 | — |
  | 13:47:05 | 2 | 3.93 | 3.79 | yes | 3.3405 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:48:06 | 2 | 4.01 | 3.94 | yes | 3.4085 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:49:06 | 2 | 4.29 | 4.28 | yes | 3.6465 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:50:08 | 2 | 3.92 | 3.89 | yes | 3.6465 | — |
  | 13:51:05 | 2 | 3.35 | 3.31 | yes | 3.6465 | **SELL_ALL 2 `trail`** (runner_stop @ 3.65) |

- **This trade's variant grid** — best was `hold_to_time_stop` at $1,060.00 (realized $651.00, delta $409.00); oracle $1,535.00.
- **Parity control** — this trade's own as-placed shape, replayed: $413.00 vs $651.00 realized (gap $-238.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$651.00** |
  | `hold_to_time_stop` | $1,060.00 |
  | `tp1_100_trail_20` | $814.60 |
  | `all_out_at_tp1_100` | $665.00 |
  | `tp1_100_trail_10` | $626.20 |
  | `all_out_at_tp1_50` | $332.50 |
  | `tp1_30_trail_125` | $266.35 |
  | `trail_only_no_tp1` | $40.00 |

### 2026-08-04 · risky-3 · `SPY260804C00769000` · realized $788.00

- **Entry** 11:52:08 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **768.61**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 769 (trigger 768.61, offset 0.39), quoted premium 1.23, filled **1.32** × 5, stop `STRUCTURE@768.61 (cat -50%)`.
- **Entry fill quality** — paid 0.8% above the signal minute's low (bar 1.31–1.37).
- **High-water WHILE IN THE TRADE** 4.26 (222.7% vs entry) at 2026-08-04T17:49:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.4 (233.3%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:08:08 | 3 | 2.6 | 97.0% | `tp1` | 2.74 | $42.00 (5.1%) |
  | 13:51:08 | 2 | 3.34 | 153.0% | `trail` | 4.26 | $184.00 (21.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:53:06 | 5 | 1.25 | 1.24 | no | 0.605 | — |
  | 11:54:06 | 5 | 0.94 | 0.93 | no | 0.605 | — |
  | 11:55:07 | 5 | 0.97 | 0.96 | no | 0.605 | — |
  | 11:56:04 | 5 | 1.07 | 1.02 | no | 0.605 | — |
  | 11:57:05 | 5 | 1.02 | 1.01 | no | 0.605 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 768.61) |
  | 12:29:06 | 5 | 1.37 | 1.36 | no | 0.66 | — |
  | 12:30:05 | 5 | 1.2 | 1.15 | no | 0.66 | — |
  | 12:31:05 | 5 | 1.27 | 1.25 | no | 0.66 | — |
  | 12:32:06 | 5 | 1.41 | 1.36 | no | 0.66 | — |
  | 12:33:05 | 5 | 1.4 | 1.39 | no | 0.66 | — |
  | 12:34:04 | 5 | 1.51 | 1.5 | no | 0.66 | — |
  | 12:35:05 | 5 | 1.42 | 1.41 | no | 0.66 | — |
  | 12:36:04 | 5 | 1.46 | 1.4 | no | 0.66 | — |
  | 12:37:05 | 5 | 1.57 | 1.5 | no | 0.66 | — |
  | 12:38:05 | 5 | 1.4 | 1.39 | no | 0.66 | — |
  | 12:39:07 | 5 | 1.38 | 1.37 | no | 0.66 | — |
  | 12:40:07 | 5 | 1.48 | 1.47 | no | 0.66 | — |
  | 12:41:05 | 5 | 1.46 | 1.45 | no | 0.66 | — |
  | 12:42:05 | 5 | 1.46 | 1.45 | no | 0.66 | — |
  | 12:43:04 | 5 | 1.49 | 1.48 | no | 0.66 | — |
  | 12:44:04 | 5 | 1.64 | 1.61 | no | 0.66 | — |
  | 12:45:05 | 5 | 1.78 | 1.77 | no | 0.66 | — |
  | 12:46:05 | 5 | 1.9 | 1.87 | no | 0.66 | — |
  | 12:47:08 | 5 | 1.83 | 1.81 | no | 0.66 | — |
  | 12:48:07 | 5 | 1.83 | 1.77 | no | 0.66 | — |
  | 12:49:06 | 5 | 1.76 | 1.75 | no | 0.66 | — |
  | 12:50:08 | 5 | 1.86 | 1.81 | no | 0.66 | — |
  | 12:51:05 | 5 | 1.91 | 1.84 | no | 0.66 | — |
  | 12:52:06 | 5 | 1.83 | 1.81 | no | 0.66 | — |
  | 12:53:05 | 5 | 1.83 | 1.82 | no | 0.66 | — |
  | 12:54:05 | 5 | 1.97 | 1.95 | no | 0.66 | — |
  | 12:55:06 | 5 | 1.84 | 1.83 | no | 0.66 | — |
  | 12:56:06 | 5 | 1.82 | 1.8 | no | 0.66 | — |
  | 12:57:06 | 5 | 1.89 | 1.88 | no | 0.66 | — |
  | 12:58:07 | 5 | 1.88 | 1.82 | no | 0.66 | — |
  | 12:59:05 | 5 | 1.79 | 1.78 | no | 0.66 | — |
  | 13:00:05 | 5 | 1.92 | 1.91 | no | 0.66 | — |
  | 13:01:05 | 5 | 2.25 | 2.17 | no | 0.66 | — |
  | 13:02:05 | 5 | 2.3 | 2.28 | no | 0.66 | — |
  | 13:03:05 | 5 | 2.24 | 2.22 | no | 0.66 | — |
  | 13:04:05 | 5 | 2.44 | 2.38 | no | 0.66 | — |
  | 13:05:05 | 5 | 2.54 | 2.52 | no | 0.66 | — |
  | 13:06:04 | 5 | 2.39 | 2.37 | no | 0.66 | — |
  | 13:07:07 | 5 | 2.49 | 2.39 | no | 0.66 | — |
  | 13:08:06 | 5 | 2.66 | 2.65 | yes | 1.32 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:09:06 | 2 | 2.72 | 2.64 | yes | 2.176 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:10:08 | 2 | 2.58 | 2.55 | yes | 2.176 | — |
  | 13:11:04 | 2 | 2.58 | 2.49 | yes | 2.176 | — |
  | 13:12:05 | 2 | 2.61 | 2.57 | yes | 2.176 | — |
  | 13:13:05 | 2 | 2.67 | 2.66 | yes | 2.176 | — |
  | 13:14:04 | 2 | 2.63 | 2.61 | yes | 2.176 | — |
  | 13:15:06 | 2 | 2.82 | 2.74 | yes | 2.256 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:16:05 | 2 | 2.85 | 2.82 | yes | 2.28 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:17:05 | 2 | 2.87 | 2.84 | yes | 2.296 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:18:04 | 2 | 3.0 | 2.98 | yes | 2.4 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:19:05 | 2 | 2.94 | 2.84 | yes | 2.4 | — |
  | 13:20:05 | 2 | 2.92 | 2.89 | yes | 2.4 | — |
  | 13:21:04 | 2 | 2.62 | 2.61 | yes | 2.4 | — |
  | 13:22:04 | 2 | 2.68 | 2.61 | yes | 2.4 | — |
  | 13:23:06 | 2 | 2.6 | 2.57 | yes | 2.4 | — |
  | 13:24:07 | 2 | 2.77 | 2.76 | yes | 2.4 | — |
  | 13:25:08 | 2 | 2.77 | 2.75 | yes | 2.4 | — |
  | 13:26:04 | 2 | 2.98 | 2.86 | yes | 2.4 | — |
  | 13:27:05 | 2 | 2.84 | 2.77 | yes | 2.4 | — |
  | 13:28:05 | 2 | 2.87 | 2.78 | yes | 2.4 | — |
  | 13:29:05 | 2 | 2.79 | 2.77 | yes | 2.4 | — |
  | 13:30:05 | 2 | 2.75 | 2.72 | yes | 2.4 | — |
  | 13:31:05 | 2 | 2.67 | 2.65 | yes | 2.4 | — |
  | 13:32:05 | 2 | 2.72 | 2.7 | yes | 2.4 | — |
  | 13:33:04 | 2 | 2.78 | 2.7 | yes | 2.4 | — |
  | 13:34:04 | 2 | 2.73 | 2.7 | yes | 2.4 | — |
  | 13:35:05 | 2 | 2.88 | 2.84 | yes | 2.4 | — |
  | 13:36:04 | 2 | 2.91 | 2.83 | yes | 2.4 | — |
  | 13:37:04 | 2 | 3.11 | 3.02 | yes | 2.488 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:38:04 | 2 | 3.11 | 3.09 | yes | 2.488 | — |
  | 13:39:04 | 2 | 3.07 | 3.03 | yes | 2.488 | — |
  | 13:40:05 | 2 | 3.25 | 3.19 | yes | 2.6 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:41:04 | 2 | 3.36 | 3.35 | yes | 2.688 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:42:06 | 2 | 3.45 | 3.35 | yes | 2.76 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:43:07 | 2 | 3.4 | 3.38 | yes | 2.76 | — |
  | 13:44:07 | 2 | 3.42 | 3.37 | yes | 2.76 | — |
  | 13:45:08 | 2 | 3.71 | 3.62 | yes | 2.968 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:46:05 | 2 | 3.7 | 3.68 | yes | 2.968 | — |
  | 13:47:05 | 2 | 3.97 | 3.82 | yes | 3.176 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:48:06 | 2 | 4.01 | 3.94 | yes | 3.208 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:49:06 | 2 | 4.36 | 4.33 | yes | 3.488 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:50:08 | 2 | 3.91 | 3.81 | yes | 3.488 | — |
  | 13:51:05 | 2 | 3.39 | 3.37 | yes | 3.488 | **SELL_ALL 2 `trail`** (runner_stop @ 3.49) |

- **This trade's variant grid** — best was `hold_to_time_stop` at $1,065.00 (realized $788.00, delta $277.00); oracle $1,540.00.
- **Parity control** — this trade's own as-placed shape, replayed: $611.50 vs $788.00 realized (gap $-176.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$788.00** |
  | `hold_to_time_stop` | $1,065.00 |
  | `tp1_100_trail_20` | $813.60 |
  | `all_out_at_tp1_100` | $660.00 |
  | `tp1_100_trail_10` | $625.20 |
  | `all_out_at_tp1_50` | $330.00 |
  | `tp1_30_trail_125` | $266.15 |
  | `trail_only_no_tp1` | $20.00 |

### 2026-08-04 · safe-2 · `SPY260804C00769000` · realized $375.00

- **Entry** 12:28:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.34** × 3, stop `STRUCTURE@768.94 (cat -50%)`.
- **Entry fill quality** — paid 2.3% above the signal minute's low (bar 1.31–1.37).
- **High-water WHILE IN THE TRADE** 3.04 (126.9% vs entry) at 2026-08-04T17:17:00Z UTC · 55 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.4 (228.4%) at 2026-08-04T19:46:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:08:06 | 2 | 2.61 | 94.8% | `tp1` | 2.74 | $26.00 (4.7%) |
  | 13:23:05 | 1 | 2.55 | 90.3% | `trail` | 3.04 | $49.00 (16.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 12:29:04 | 3 | 1.37 | 1.36 | no | 0.67 | — |
  | 12:30:04 | 3 | 1.34 | 1.33 | no | 0.67 | — |
  | 12:31:03 | 3 | 1.34 | 1.33 | no | 0.67 | — |
  | 12:32:03 | 3 | 1.41 | 1.4 | no | 0.67 | — |
  | 12:33:03 | 3 | 1.44 | 1.43 | no | 0.67 | — |
  | 12:34:03 | 3 | 1.52 | 1.5 | no | 0.67 | — |
  | 12:35:03 | 3 | 1.42 | 1.41 | no | 0.67 | — |
  | 12:36:03 | 3 | 1.46 | 1.45 | no | 0.67 | — |
  | 12:37:03 | 3 | 1.55 | 1.54 | no | 0.67 | — |
  | 12:38:03 | 3 | 1.45 | 1.4 | no | 0.67 | — |
  | 12:39:05 | 3 | 1.37 | 1.36 | no | 0.67 | — |
  | 12:40:06 | 3 | 1.47 | 1.42 | no | 0.67 | — |
  | 12:41:03 | 3 | 1.42 | 1.4 | no | 0.67 | — |
  | 12:42:03 | 3 | 1.41 | 1.4 | no | 0.67 | — |
  | 12:43:03 | 3 | 1.51 | 1.46 | no | 0.67 | — |
  | 12:44:03 | 3 | 1.59 | 1.58 | no | 0.67 | — |
  | 12:45:03 | 3 | 1.78 | 1.72 | no | 0.67 | — |
  | 12:46:03 | 3 | 1.9 | 1.84 | no | 0.67 | — |
  | 12:47:05 | 3 | 1.83 | 1.76 | no | 0.67 | — |
  | 12:48:04 | 3 | 1.83 | 1.82 | no | 0.67 | — |
  | 12:49:04 | 3 | 1.77 | 1.76 | no | 0.67 | — |
  | 12:50:06 | 3 | 1.88 | 1.86 | no | 0.67 | — |
  | 12:51:03 | 3 | 1.91 | 1.85 | no | 0.67 | — |
  | 12:52:04 | 3 | 1.89 | 1.83 | no | 0.67 | — |
  | 12:53:03 | 3 | 1.86 | 1.83 | no | 0.67 | — |
  | 12:54:03 | 3 | 1.95 | 1.9 | no | 0.67 | — |
  | 12:55:04 | 3 | 1.88 | 1.82 | no | 0.67 | — |
  | 12:56:03 | 3 | 1.82 | 1.81 | no | 0.67 | — |
  | 12:57:03 | 3 | 1.87 | 1.86 | no | 0.67 | — |
  | 12:58:06 | 3 | 1.89 | 1.82 | no | 0.67 | — |
  | 12:59:03 | 3 | 1.84 | 1.83 | no | 0.67 | — |
  | 13:00:03 | 3 | 1.93 | 1.91 | no | 0.67 | — |
  | 13:01:03 | 3 | 2.18 | 2.17 | no | 0.67 | — |
  | 13:02:03 | 3 | 2.3 | 2.27 | no | 0.67 | — |
  | 13:03:03 | 3 | 2.28 | 2.22 | no | 0.67 | — |
  | 13:04:03 | 3 | 2.44 | 2.41 | no | 0.67 | — |
  | 13:05:03 | 3 | 2.56 | 2.51 | no | 0.67 | — |
  | 13:06:03 | 3 | 2.38 | 2.36 | no | 0.67 | — |
  | 13:07:05 | 3 | 2.46 | 2.44 | no | 0.67 | — |
  | 13:08:04 | 3 | 2.69 | 2.59 | yes | 1.34 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:09:04 | 1 | 2.69 | 2.67 | yes | 2.2865 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:10:06 | 1 | 2.6 | 2.58 | yes | 2.2865 | — |
  | 13:11:03 | 1 | 2.5 | 2.48 | yes | 2.2865 | — |
  | 13:12:03 | 1 | 2.68 | 2.65 | yes | 2.2865 | — |
  | 13:13:03 | 1 | 2.73 | 2.66 | yes | 2.3205 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:14:03 | 1 | 2.67 | 2.63 | yes | 2.3205 | — |
  | 13:15:05 | 1 | 2.82 | 2.79 | yes | 2.397 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:16:03 | 1 | 2.8 | 2.79 | yes | 2.397 | — |
  | 13:17:03 | 1 | 2.85 | 2.78 | yes | 2.4225 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:18:03 | 1 | 3.02 | 3.0 | yes | 2.567 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:19:03 | 1 | 2.88 | 2.86 | yes | 2.567 | — |
  | 13:20:03 | 1 | 2.94 | 2.89 | yes | 2.567 | — |
  | 13:21:03 | 1 | 2.66 | 2.59 | yes | 2.567 | — |
  | 13:22:03 | 1 | 2.7 | 2.68 | yes | 2.567 | — |
  | 13:23:04 | 1 | 2.58 | 2.53 | yes | 2.567 | **SELL_ALL 1 `trail`** (runner_stop @ 2.57) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `hold_to_time_stop` at $633.00 (realized $375.00, delta $258.00); oracle $918.00.
- **Parity control** — this trade's own as-placed shape, replayed: $291.40 vs $375.00 realized (gap $-83.60 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$375.00** |
  | `hold_to_time_stop` | $633.00 |
  | `tp1_100_trail_20` | $474.80 |
  | `all_out_at_tp1_100` | $402.00 |
  | `tp1_100_trail_10` | $380.60 |
  | `all_out_at_tp1_50` | $201.00 |
  | `tp1_30_trail_125` | $186.15 |
  | `trail_only_no_tp1` | $21.00 |

### 2026-08-04 · safe-3 · `SPY260804C00771000` · realized $9.00

- **Entry** 13:24:07 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **771.28**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 771 (trigger 771.28, offset -0.28), quoted premium 1.42, filled **1.4** × 3, stop `STRUCTURE@771.28 (cat -50%)`.
- **Entry fill quality** — paid 4.5% above the signal minute's low (bar 1.34–1.42).
- **High-water WHILE IN THE TRADE** 1.52 (8.6% vs entry) at 2026-08-04T17:26:00Z UTC · 3 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.6 (85.7%) at 2026-08-04T17:49:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:27:06 | 2 | 1.43 | 2.1% | `?` | 1.52 | $18.00 (5.9%) |
  | 13:27:06 | 1 | 1.43 | 2.1% | `?` | 1.52 | $9.00 (5.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:25:08 | 3 | 1.41 | 1.36 | no | 0.7 | — |
  | 13:26:04 | 3 | 1.52 | 1.51 | no | 0.7 | — |
  | 13:27:05 | 3 | 1.46 | 1.41 | no | 0.7 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 771.28) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $210.00 (realized $9.00, delta $201.00); oracle $360.00.
- **Parity control** — this trade's own as-placed shape, replayed: $78.00 vs $9.00 realized (gap $69.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$9.00** |
  | `all_out_at_tp1_50` | $210.00 |
  | `tp1_30_trail_125` | $171.50 |
  | `all_out_at_tp1_100` | $78.00 |
  | `tp1_100_trail_20` | $78.00 |
  | `tp1_100_trail_10` | $78.00 |
  | `hold_to_time_stop` | $78.00 |
  | `trail_only_no_tp1` | $3.00 |

### 2026-08-05 · risky-1 · `SPY260805P00772000` · realized $347.00

- **Entry** 11:48:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **772.33**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 772 (trigger 772.33, offset -0.33), quoted premium 1.73, filled **1.69** × 5, stop `STRUCTURE@772.33 (cat -50%)`.
- **Entry fill quality** — paid 3.0% above the signal minute's low (bar 1.64–1.74).
- **High-water WHILE IN THE TRADE** 2.75 (62.7% vs entry) at 2026-08-05T16:09:00Z UTC · 29 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.75 (62.7%) at 2026-08-05T16:09:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:09:05 | 3 | 2.62 | 55.0% | `tp1` | 2.75 | $39.00 (4.7%) |
  | 12:17:05 | 2 | 2.03 | 20.1% | `trail` | 2.75 | $144.00 (26.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:49:04 | 5 | 1.67 | 1.62 | no | 0.845 | — |
  | 11:50:05 | 5 | 1.79 | 1.77 | no | 0.845 | — |
  | 11:51:04 | 5 | 1.83 | 1.81 | no | 0.845 | — |
  | 11:52:04 | 5 | 1.93 | 1.88 | no | 0.845 | — |
  | 11:53:04 | 5 | 1.86 | 1.85 | no | 0.845 | — |
  | 11:54:04 | 5 | 1.78 | 1.73 | no | 0.845 | — |
  | 11:55:06 | 5 | 1.86 | 1.85 | no | 0.845 | — |
  | 11:56:04 | 5 | 1.97 | 1.91 | no | 0.845 | — |
  | 11:57:06 | 5 | 2.21 | 2.19 | no | 0.845 | — |
  | 11:58:09 | 5 | 2.17 | 2.15 | no | 0.845 | — |
  | 11:59:04 | 5 | 1.99 | 1.94 | no | 0.845 | — |
  | 12:00:05 | 5 | 2.24 | 2.18 | no | 0.845 | — |
  | 12:01:04 | 5 | 2.26 | 2.16 | no | 0.845 | — |
  | 12:02:04 | 5 | 2.27 | 2.24 | no | 0.845 | — |
  | 12:03:04 | 5 | 2.53 | 2.43 | no | 0.845 | — |
  | 12:04:04 | 5 | 2.28 | 2.19 | no | 0.845 | — |
  | 12:05:05 | 5 | 2.17 | 2.15 | no | 0.845 | — |
  | 12:06:04 | 5 | 2.25 | 2.21 | no | 0.845 | — |
  | 12:07:04 | 5 | 2.48 | 2.41 | no | 0.845 | — |
  | 12:08:04 | 5 | 2.47 | 2.44 | no | 0.845 | — |
  | 12:09:04 | 5 | 2.68 | 2.64 | yes | 1.69 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:10:06 | 2 | 2.51 | 2.48 | yes | 2.278 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:11:04 | 2 | 2.62 | 2.57 | yes | 2.278 | — |
  | 12:12:05 | 2 | 2.52 | 2.5 | yes | 2.278 | — |
  | 12:13:04 | 2 | 2.57 | 2.51 | yes | 2.278 | — |
  | 12:14:04 | 2 | 2.59 | 2.48 | yes | 2.278 | — |
  | 12:15:05 | 2 | 2.46 | 2.37 | yes | 2.278 | — |
  | 12:16:04 | 2 | 2.32 | 2.3 | yes | 2.278 | — |
  | 12:17:04 | 2 | 2.07 | 2.01 | yes | 2.278 | **SELL_ALL 2 `trail`** (runner_stop @ 2.28) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $422.50 (realized $347.00, delta $75.50); oracle $530.00.
- **Parity control** — this trade's own as-placed shape, replayed: $367.00 vs $347.00 realized (gap $20.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$347.00** |
  | `all_out_at_tp1_50` | $422.50 |
  | `tp1_30_trail_125` | $246.43 |
  | `trail_only_no_tp1` | $65.00 |
  | `all_out_at_tp1_100` | $-422.50 |
  | `tp1_100_trail_20` | $-422.50 |
  | `tp1_100_trail_10` | $-422.50 |
  | `hold_to_time_stop` | $-422.50 |

### 2026-08-06 · safe-2 · `SPY260806P00770000` · realized $375.00

- **Entry** 10:31:03 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.28** × 3, stop `STRUCTURE@771.50 (cat -50%)`.
- **Entry fill quality** — paid 12.3% above the signal minute's low (bar 1.14–1.29).
- **High-water WHILE IN THE TRADE** 2.8 (118.8% vs entry) at 2026-08-06T16:16:00Z UTC · 108 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.8 (118.8%) at 2026-08-06T16:16:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:16:04 | 2 | 2.71 | 111.7% | `tp1` | 2.8 | $18.00 (3.2%) |
  | 12:19:04 | 1 | 2.17 | 69.5% | `trail` | 2.8 | $63.00 (22.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:32:03 | 3 | 1.23 | 1.18 | no | 0.64 | — |
  | 10:33:03 | 3 | 1.2 | 1.19 | no | 0.64 | — |
  | 10:34:03 | 3 | 1.17 | 1.16 | no | 0.64 | — |
  | 10:35:03 | 3 | 1.04 | 1.03 | no | 0.64 | — |
  | 10:36:03 | 3 | 0.95 | 0.94 | no | 0.64 | — |
  | 10:37:03 | 3 | 1.12 | 1.11 | no | 0.64 | — |
  | 10:38:03 | 3 | 1.26 | 1.21 | no | 0.64 | — |
  | 10:39:03 | 3 | 1.38 | 1.32 | no | 0.64 | — |
  | 10:40:03 | 3 | 1.52 | 1.51 | no | 0.64 | — |
  | 10:41:03 | 3 | 1.38 | 1.37 | no | 0.64 | — |
  | 10:42:03 | 3 | 1.21 | 1.2 | no | 0.64 | — |
  | 10:43:03 | 3 | 1.08 | 1.07 | no | 0.64 | — |
  | 10:44:03 | 3 | 1.06 | 1.05 | no | 0.64 | — |
  | 10:45:03 | 3 | 1.3 | 1.29 | no | 0.64 | — |
  | 10:46:03 | 3 | 1.36 | 1.35 | no | 0.64 | — |
  | 10:47:03 | 3 | 1.46 | 1.45 | no | 0.64 | — |
  | 10:48:03 | 3 | 1.37 | 1.32 | no | 0.64 | — |
  | 10:49:03 | 3 | 1.41 | 1.4 | no | 0.64 | — |
  | 10:50:03 | 3 | 1.54 | 1.53 | no | 0.64 | — |
  | 10:51:03 | 3 | 1.34 | 1.29 | no | 0.64 | — |
  | 10:52:03 | 3 | 1.36 | 1.34 | no | 0.64 | — |
  | 10:53:03 | 3 | 1.35 | 1.34 | no | 0.64 | — |
  | 10:54:03 | 3 | 1.37 | 1.36 | no | 0.64 | — |
  | 10:55:03 | 3 | 1.03 | 1.02 | no | 0.64 | — |
  | 10:56:03 | 3 | 1.03 | 1.02 | no | 0.64 | — |
  | 10:57:03 | 3 | 0.93 | 0.92 | no | 0.64 | — |
  | 10:58:03 | 3 | 0.82 | 0.81 | no | 0.64 | — |
  | 10:59:03 | 3 | 0.89 | 0.88 | no | 0.64 | — |
  | 11:00:03 | 3 | 0.81 | 0.8 | no | 0.64 | — |
  | 11:01:03 | 3 | 0.87 | 0.82 | no | 0.64 | — |
  | 11:02:03 | 3 | 0.91 | 0.9 | no | 0.64 | — |
  | 11:03:03 | 3 | 1.04 | 0.99 | no | 0.64 | — |
  | 11:04:03 | 3 | 1.18 | 1.17 | no | 0.64 | — |
  | 11:05:03 | 3 | 1.13 | 1.08 | no | 0.64 | — |
  | 11:06:03 | 3 | 1.03 | 0.98 | no | 0.64 | — |
  | 11:07:03 | 3 | 1.01 | 0.96 | no | 0.64 | — |
  | 11:08:03 | 3 | 0.94 | 0.93 | no | 0.64 | — |
  | 11:09:03 | 3 | 0.99 | 0.98 | no | 0.64 | — |
  | 11:10:03 | 3 | 0.95 | 0.94 | no | 0.64 | — |
  | 11:11:03 | 3 | 0.92 | 0.87 | no | 0.64 | — |
  | 11:12:03 | 3 | 0.99 | 0.94 | no | 0.64 | — |
  | 11:13:03 | 3 | 1.02 | 1.01 | no | 0.64 | — |
  | 11:14:03 | 3 | 1.15 | 1.1 | no | 0.64 | — |
  | 11:15:03 | 3 | 1.25 | 1.24 | no | 0.64 | — |
  | 11:16:06 | 3 | 1.2 | 1.19 | no | 0.64 | — |
  | 11:17:03 | 3 | 1.18 | 1.13 | no | 0.64 | — |
  | 11:18:03 | 3 | 1.45 | 1.39 | no | 0.64 | — |
  | 11:19:03 | 3 | 1.56 | 1.55 | no | 0.64 | — |
  | 11:20:03 | 3 | 1.82 | 1.81 | no | 0.64 | — |
  | 11:21:03 | 3 | 1.74 | 1.72 | no | 0.64 | — |
  | 11:22:03 | 3 | 1.75 | 1.69 | no | 0.64 | — |
  | 11:23:03 | 3 | 1.92 | 1.9 | no | 0.64 | — |
  | 11:24:03 | 3 | 1.74 | 1.72 | no | 0.64 | — |
  | 11:25:03 | 3 | 1.81 | 1.8 | no | 0.64 | — |
  | 11:26:03 | 3 | 1.73 | 1.71 | no | 0.64 | — |
  | 11:27:03 | 3 | 1.83 | 1.78 | no | 0.64 | — |
  | 11:28:03 | 3 | 1.84 | 1.83 | no | 0.64 | — |
  | 11:29:03 | 3 | 1.66 | 1.64 | no | 0.64 | — |
  | 11:30:03 | 3 | 1.58 | 1.56 | no | 0.64 | — |
  | 11:31:03 | 3 | 1.47 | 1.46 | no | 0.64 | — |
  | 11:32:03 | 3 | 1.83 | 1.81 | no | 0.64 | — |
  | 11:33:03 | 3 | 1.9 | 1.87 | no | 0.64 | — |
  | 11:34:03 | 3 | 1.91 | 1.88 | no | 0.64 | — |
  | 11:35:03 | 3 | 2.03 | 2.02 | no | 0.64 | — |
  | 11:36:03 | 3 | 1.94 | 1.93 | no | 0.64 | — |
  | 11:37:03 | 3 | 2.15 | 2.13 | no | 0.64 | — |
  | 11:38:03 | 3 | 1.97 | 1.96 | no | 0.64 | — |
  | 11:39:03 | 3 | 1.95 | 1.93 | no | 0.64 | — |
  | 11:40:04 | 3 | 1.95 | 1.89 | no | 0.64 | — |
  | 11:41:03 | 3 | 1.77 | 1.76 | no | 0.64 | — |
  | 11:42:04 | 3 | 1.99 | 1.97 | no | 0.64 | — |
  | 11:43:03 | 3 | 2.12 | 2.11 | no | 0.64 | — |
  | 11:44:03 | 3 | 2.1 | 2.08 | no | 0.64 | — |
  | 11:45:03 | 3 | 2.17 | 2.15 | no | 0.64 | — |
  | 11:46:04 | 3 | 2.04 | 2.0 | no | 0.64 | — |
  | 11:47:03 | 3 | 1.55 | 1.52 | no | 0.64 | — |
  | 11:48:03 | 3 | 1.63 | 1.61 | no | 0.64 | — |
  | 11:49:03 | 3 | 1.36 | 1.35 | no | 0.64 | — |
  | 11:50:04 | 3 | 1.52 | 1.51 | no | 0.64 | — |
  | 11:51:03 | 3 | 1.39 | 1.38 | no | 0.64 | — |
  | 11:52:04 | 3 | 1.75 | 1.73 | no | 0.64 | — |
  | 11:53:03 | 3 | 1.74 | 1.72 | no | 0.64 | — |
  | 11:54:03 | 3 | 1.95 | 1.93 | no | 0.64 | — |
  | 11:55:04 | 3 | 2.39 | 2.36 | no | 0.64 | — |
  | 11:56:03 | 3 | 2.19 | 2.15 | no | 0.64 | — |
  | 11:57:03 | 3 | 2.27 | 2.24 | no | 0.64 | — |
  | 11:58:03 | 3 | 2.1 | 2.02 | no | 0.64 | — |
  | 11:59:03 | 3 | 2.19 | 2.16 | no | 0.64 | — |
  | 12:00:04 | 3 | 2.24 | 2.21 | no | 0.64 | — |
  | 12:01:04 | 3 | 2.43 | 2.4 | no | 0.64 | — |
  | 12:02:03 | 3 | 2.43 | 2.41 | no | 0.64 | — |
  | 12:03:03 | 3 | 2.27 | 2.25 | no | 0.64 | — |
  | 12:04:03 | 3 | 2.53 | 2.5 | no | 0.64 | — |
  | 12:05:03 | 3 | 2.4 | 2.33 | no | 0.64 | — |
  | 12:06:03 | 3 | 2.2 | 2.12 | no | 0.64 | — |
  | 12:07:03 | 3 | 2.33 | 2.3 | no | 0.64 | — |
  | 12:08:03 | 3 | 2.29 | 2.27 | no | 0.64 | — |
  | 12:09:03 | 3 | 2.19 | 2.16 | no | 0.64 | — |
  | 12:10:04 | 3 | 2.03 | 2.02 | no | 0.64 | — |
  | 12:11:03 | 3 | 2.15 | 2.11 | no | 0.64 | — |
  | 12:12:03 | 3 | 2.38 | 2.35 | no | 0.64 | — |
  | 12:13:03 | 3 | 2.39 | 2.37 | no | 0.64 | — |
  | 12:14:03 | 3 | 2.5 | 2.42 | no | 0.64 | — |
  | 12:15:04 | 3 | 2.45 | 2.36 | no | 0.64 | — |
  | 12:16:03 | 3 | 2.7 | 2.67 | yes | 1.28 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:17:03 | 1 | 2.54 | 2.5 | yes | 2.295 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:18:03 | 1 | 2.42 | 2.35 | yes | 2.295 | — |
  | 12:19:03 | 1 | 2.21 | 2.14 | yes | 2.295 | **SELL_ALL 1 `trail`** (runner_stop @ 2.29) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $384.00 (realized $375.00, delta $9.00); oracle $456.00.
- **Parity control** — this trade's own as-placed shape, replayed: $76.80 vs $375.00 realized (gap $-298.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$375.00** |
  | `all_out_at_tp1_100` | $384.00 |
  | `tp1_100_trail_10` | $359.30 |
  | `tp1_100_trail_20` | $333.60 |
  | `hold_to_time_stop` | $279.00 |
  | `all_out_at_tp1_50` | $192.00 |
  | `tp1_30_trail_125` | $115.05 |
  | `trail_only_no_tp1` | $24.00 |

### 2026-08-06 · risky-1 · `SPY260806P00770000` · realized $296.00

- **Entry** 10:32:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **771.5**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 770 (trigger 771.5, offset -1.5), quoted premium 1.23, filled **1.23** × 5, stop `STRUCTURE@771.50 (cat -50%)`.
- **Entry fill quality** — paid 6.0% above the signal minute's low (bar 1.16–1.33).
- **High-water WHILE IN THE TRADE** 2.03 (65.0% vs entry) at 2026-08-06T15:23:00Z UTC · 57 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.8 (127.6%) at 2026-08-06T16:16:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:23:06 | 3 | 1.95 | 58.5% | `tp1` | 2.03 | $24.00 (3.9%) |
  | 11:29:06 | 2 | 1.63 | 32.5% | `trail` | 2.03 | $80.00 (19.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:33:04 | 5 | 1.18 | 1.17 | no | 0.615 | — |
  | 10:34:04 | 5 | 1.17 | 1.12 | no | 0.615 | — |
  | 10:35:04 | 5 | 1.0 | 0.99 | no | 0.615 | — |
  | 10:36:04 | 5 | 0.98 | 0.97 | no | 0.615 | — |
  | 10:37:04 | 5 | 1.19 | 1.13 | no | 0.615 | — |
  | 10:38:04 | 5 | 1.27 | 1.22 | no | 0.615 | — |
  | 10:39:04 | 5 | 1.33 | 1.32 | no | 0.615 | — |
  | 10:40:05 | 5 | 1.45 | 1.44 | no | 0.615 | — |
  | 10:41:04 | 5 | 1.32 | 1.31 | no | 0.615 | — |
  | 10:42:05 | 5 | 1.2 | 1.19 | no | 0.615 | — |
  | 10:43:04 | 5 | 1.11 | 1.06 | no | 0.615 | — |
  | 10:44:05 | 5 | 1.04 | 0.99 | no | 0.615 | — |
  | 10:45:05 | 5 | 1.28 | 1.27 | no | 0.615 | — |
  | 10:46:04 | 5 | 1.39 | 1.34 | no | 0.615 | — |
  | 10:47:04 | 5 | 1.43 | 1.42 | no | 0.615 | — |
  | 10:48:04 | 5 | 1.33 | 1.32 | no | 0.615 | — |
  | 10:49:04 | 5 | 1.41 | 1.4 | no | 0.615 | — |
  | 10:50:05 | 5 | 1.51 | 1.5 | no | 0.615 | — |
  | 10:51:04 | 5 | 1.36 | 1.35 | no | 0.615 | — |
  | 10:52:05 | 5 | 1.38 | 1.37 | no | 0.615 | — |
  | 10:53:04 | 5 | 1.34 | 1.33 | no | 0.615 | — |
  | 10:54:04 | 5 | 1.36 | 1.35 | no | 0.615 | — |
  | 10:55:05 | 5 | 1.08 | 1.03 | no | 0.615 | — |
  | 10:56:05 | 5 | 1.05 | 1.04 | no | 0.615 | — |
  | 10:57:04 | 5 | 0.93 | 0.88 | no | 0.615 | — |
  | 10:58:04 | 5 | 0.85 | 0.8 | no | 0.615 | — |
  | 10:59:04 | 5 | 0.94 | 0.89 | no | 0.615 | — |
  | 11:00:05 | 5 | 0.81 | 0.8 | no | 0.615 | — |
  | 11:01:04 | 5 | 0.82 | 0.81 | no | 0.615 | — |
  | 11:02:05 | 5 | 0.86 | 0.85 | no | 0.615 | — |
  | 11:03:04 | 5 | 1.1 | 1.05 | no | 0.615 | — |
  | 11:04:05 | 5 | 1.13 | 1.12 | no | 0.615 | — |
  | 11:05:05 | 5 | 1.06 | 1.05 | no | 0.615 | — |
  | 11:06:04 | 5 | 1.03 | 1.02 | no | 0.615 | — |
  | 11:07:04 | 5 | 1.02 | 1.01 | no | 0.615 | — |
  | 11:08:04 | 5 | 0.9 | 0.89 | no | 0.615 | — |
  | 11:09:04 | 5 | 1.03 | 1.02 | no | 0.615 | — |
  | 11:10:05 | 5 | 1.0 | 0.99 | no | 0.615 | — |
  | 11:11:04 | 5 | 0.93 | 0.92 | no | 0.615 | — |
  | 11:12:05 | 5 | 1.0 | 0.99 | no | 0.615 | — |
  | 11:13:04 | 5 | 1.07 | 1.02 | no | 0.615 | — |
  | 11:14:04 | 5 | 1.13 | 1.12 | no | 0.615 | — |
  | 11:15:05 | 5 | 1.23 | 1.21 | no | 0.615 | — |
  | 11:16:04 | 5 | 1.2 | 1.15 | no | 0.615 | — |
  | 11:17:04 | 5 | 1.17 | 1.16 | no | 0.615 | — |
  | 11:18:04 | 5 | 1.42 | 1.37 | no | 0.615 | — |
  | 11:19:04 | 5 | 1.63 | 1.57 | no | 0.615 | — |
  | 11:20:05 | 5 | 1.81 | 1.74 | no | 0.615 | — |
  | 11:21:04 | 5 | 1.67 | 1.66 | no | 0.615 | — |
  | 11:22:04 | 5 | 1.76 | 1.7 | no | 0.615 | — |
  | 11:23:04 | 5 | 2.0 | 1.96 | yes | 1.23 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:24:04 | 2 | 1.74 | 1.73 | yes | 1.7 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:25:05 | 2 | 1.85 | 1.84 | yes | 1.7 | — |
  | 11:26:04 | 2 | 1.73 | 1.72 | yes | 1.7 | — |
  | 11:27:04 | 2 | 1.83 | 1.78 | yes | 1.7 | — |
  | 11:28:04 | 2 | 1.8 | 1.79 | yes | 1.7 | — |
  | 11:29:04 | 2 | 1.69 | 1.67 | yes | 1.7 | **SELL_ALL 2 `trail`** (runner_stop @ 1.7) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $615.00 (realized $296.00, delta $319.00); oracle $785.00.
- **Parity control** — this trade's own as-placed shape, replayed: $271.00 vs $296.00 realized (gap $-25.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$296.00** |
  | `all_out_at_tp1_100` | $615.00 |
  | `tp1_100_trail_10` | $585.60 |
  | `tp1_100_trail_20` | $534.20 |
  | `hold_to_time_stop` | $490.00 |
  | `all_out_at_tp1_50` | $307.50 |
  | `tp1_30_trail_125` | $181.23 |
  | `trail_only_no_tp1` | $65.00 |

### 2026-08-06 · risky-3 · `SPY260806P00770000` · realized $830.00

- **Entry** 10:32:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **771.5**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE)_
- **Strike** 770 (trigger 771.5, offset -1.5), quoted premium 1.26, filled **1.28** × 8, stop `STRUCTURE@771.50 (cat -50%)`.
- **Entry fill quality** — paid 10.3% above the signal minute's low (bar 1.16–1.33).
- **High-water WHILE IN THE TRADE** 2.57 (100.8% vs entry) at 2026-08-06T16:01:00Z UTC · 98 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.8 (118.8%) at 2026-08-06T16:16:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:04:07 | 5 | 2.49 | 94.5% | `tp1` | 2.57 | $40.00 (3.1%) |
  | 12:10:08 | 3 | 2.03 | 58.6% | `trail` | 2.57 | $162.00 (21.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:33:04 | 8 | 1.2 | 1.19 | no | 0.64 | — |
  | 10:34:04 | 8 | 1.19 | 1.13 | no | 0.64 | — |
  | 10:35:04 | 8 | 1.04 | 1.03 | no | 0.64 | — |
  | 10:36:04 | 8 | 0.99 | 0.97 | no | 0.64 | — |
  | 10:37:04 | 8 | 1.16 | 1.15 | no | 0.64 | — |
  | 10:38:04 | 8 | 1.23 | 1.21 | no | 0.64 | — |
  | 10:39:04 | 8 | 1.33 | 1.32 | no | 0.64 | — |
  | 10:40:05 | 8 | 1.48 | 1.47 | no | 0.64 | — |
  | 10:41:04 | 8 | 1.41 | 1.4 | no | 0.64 | — |
  | 10:42:05 | 8 | 1.2 | 1.19 | no | 0.64 | — |
  | 10:43:04 | 8 | 1.12 | 1.11 | no | 0.64 | — |
  | 10:44:05 | 8 | 1.04 | 1.03 | no | 0.64 | — |
  | 10:45:05 | 8 | 1.26 | 1.25 | no | 0.64 | — |
  | 10:46:04 | 8 | 1.39 | 1.34 | no | 0.64 | — |
  | 10:47:04 | 8 | 1.43 | 1.42 | no | 0.64 | — |
  | 10:48:04 | 8 | 1.36 | 1.34 | no | 0.64 | — |
  | 10:49:04 | 8 | 1.41 | 1.4 | no | 0.64 | — |
  | 10:50:05 | 8 | 1.51 | 1.5 | no | 0.64 | — |
  | 10:51:04 | 8 | 1.35 | 1.34 | no | 0.64 | — |
  | 10:52:05 | 8 | 1.33 | 1.32 | no | 0.64 | — |
  | 10:53:04 | 8 | 1.35 | 1.34 | no | 0.64 | — |
  | 10:54:04 | 8 | 1.36 | 1.35 | no | 0.64 | — |
  | 10:55:05 | 8 | 1.09 | 1.08 | no | 0.64 | — |
  | 10:56:05 | 8 | 1.05 | 1.04 | no | 0.64 | — |
  | 10:57:04 | 8 | 0.93 | 0.88 | no | 0.64 | — |
  | 10:58:04 | 8 | 0.85 | 0.8 | no | 0.64 | — |
  | 10:59:04 | 8 | 0.95 | 0.9 | no | 0.64 | — |
  | 11:00:05 | 8 | 0.81 | 0.8 | no | 0.64 | — |
  | 11:01:04 | 8 | 0.81 | 0.8 | no | 0.64 | — |
  | 11:02:05 | 8 | 0.9 | 0.89 | no | 0.64 | — |
  | 11:03:04 | 8 | 1.1 | 1.05 | no | 0.64 | — |
  | 11:04:05 | 8 | 1.18 | 1.17 | no | 0.64 | — |
  | 11:05:05 | 8 | 1.09 | 1.04 | no | 0.64 | — |
  | 11:06:04 | 8 | 1.03 | 1.02 | no | 0.64 | — |
  | 11:07:04 | 8 | 1.04 | 1.03 | no | 0.64 | — |
  | 11:08:04 | 8 | 0.94 | 0.93 | no | 0.64 | — |
  | 11:09:04 | 8 | 0.98 | 0.97 | no | 0.64 | — |
  | 11:10:05 | 8 | 1.0 | 0.99 | no | 0.64 | — |
  | 11:11:04 | 8 | 0.94 | 0.93 | no | 0.64 | — |
  | 11:12:05 | 8 | 0.99 | 0.94 | no | 0.64 | — |
  | 11:13:04 | 8 | 1.07 | 1.02 | no | 0.64 | — |
  | 11:14:04 | 8 | 1.16 | 1.15 | no | 0.64 | — |
  | 11:15:05 | 8 | 1.23 | 1.21 | no | 0.64 | — |
  | 11:16:04 | 8 | 1.2 | 1.19 | no | 0.64 | — |
  | 11:17:04 | 8 | 1.17 | 1.16 | no | 0.64 | — |
  | 11:18:04 | 8 | 1.42 | 1.37 | no | 0.64 | — |
  | 11:19:04 | 8 | 1.63 | 1.57 | no | 0.64 | — |
  | 11:20:05 | 8 | 1.81 | 1.78 | no | 0.64 | — |
  | 11:21:04 | 8 | 1.67 | 1.66 | no | 0.64 | — |
  | 11:22:04 | 8 | 1.77 | 1.75 | no | 0.64 | — |
  | 11:23:04 | 8 | 2.01 | 1.95 | no | 0.64 | — |
  | 11:24:04 | 8 | 1.66 | 1.64 | no | 0.64 | — |
  | 11:25:05 | 8 | 1.85 | 1.84 | no | 0.64 | — |
  | 11:26:04 | 8 | 1.73 | 1.68 | no | 0.64 | — |
  | 11:27:04 | 8 | 1.79 | 1.78 | no | 0.64 | — |
  | 11:28:04 | 8 | 1.82 | 1.8 | no | 0.64 | — |
  | 11:29:04 | 8 | 1.69 | 1.67 | no | 0.64 | — |
  | 11:30:05 | 8 | 1.54 | 1.49 | no | 0.64 | — |
  | 11:31:04 | 8 | 1.53 | 1.48 | no | 0.64 | — |
  | 11:32:05 | 8 | 1.91 | 1.84 | no | 0.64 | — |
  | 11:33:05 | 8 | 1.88 | 1.86 | no | 0.64 | — |
  | 11:34:05 | 8 | 1.91 | 1.9 | no | 0.64 | — |
  | 11:35:06 | 8 | 2.07 | 2.04 | no | 0.64 | — |
  | 11:36:05 | 8 | 1.93 | 1.91 | no | 0.64 | — |
  | 11:37:05 | 8 | 2.17 | 2.14 | no | 0.64 | — |
  | 11:38:06 | 8 | 1.98 | 1.97 | no | 0.64 | — |
  | 11:39:05 | 8 | 1.93 | 1.92 | no | 0.64 | — |
  | 11:40:06 | 8 | 2.0 | 1.98 | no | 0.64 | — |
  | 11:41:05 | 8 | 1.84 | 1.78 | no | 0.64 | — |
  | 11:42:06 | 8 | 1.99 | 1.97 | no | 0.64 | — |
  | 11:43:05 | 8 | 2.13 | 2.05 | no | 0.64 | — |
  | 11:44:05 | 8 | 2.13 | 2.06 | no | 0.64 | — |
  | 11:45:06 | 8 | 2.11 | 2.08 | no | 0.64 | — |
  | 11:46:06 | 8 | 2.06 | 2.03 | no | 0.64 | — |
  | 11:47:05 | 8 | 1.62 | 1.61 | no | 0.64 | — |
  | 11:48:06 | 8 | 1.68 | 1.62 | no | 0.64 | — |
  | 11:49:06 | 8 | 1.36 | 1.35 | no | 0.64 | — |
  | 11:50:06 | 8 | 1.5 | 1.48 | no | 0.64 | — |
  | 11:51:05 | 8 | 1.41 | 1.4 | no | 0.64 | — |
  | 11:52:06 | 8 | 1.68 | 1.66 | no | 0.64 | — |
  | 11:53:05 | 8 | 1.77 | 1.76 | no | 0.64 | — |
  | 11:54:06 | 8 | 2.0 | 1.97 | no | 0.64 | — |
  | 11:55:06 | 8 | 2.43 | 2.4 | no | 0.64 | — |
  | 11:56:05 | 8 | 2.18 | 2.09 | no | 0.64 | — |
  | 11:57:05 | 8 | 2.25 | 2.17 | no | 0.64 | — |
  | 11:58:06 | 8 | 2.09 | 2.06 | no | 0.64 | — |
  | 11:59:05 | 8 | 2.21 | 2.18 | no | 0.64 | — |
  | 12:00:07 | 8 | 2.28 | 2.24 | no | 0.64 | — |
  | 12:01:07 | 8 | 2.43 | 2.42 | no | 0.64 | — |
  | 12:02:05 | 8 | 2.42 | 2.35 | no | 0.64 | — |
  | 12:03:05 | 8 | 2.29 | 2.22 | no | 0.64 | — |
  | 12:04:05 | 8 | 2.56 | 2.48 | yes | 1.28 | **SELL_PARTIAL 5 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:05:05 | 3 | 2.42 | 2.38 | yes | 2.048 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:06:05 | 3 | 2.21 | 2.18 | yes | 2.048 | — |
  | 12:07:05 | 3 | 2.39 | 2.28 | yes | 2.048 | — |
  | 12:08:05 | 3 | 2.24 | 2.14 | yes | 2.048 | — |
  | 12:09:06 | 3 | 2.26 | 2.22 | yes | 2.048 | — |
  | 12:10:06 | 3 | 2.12 | 2.03 | yes | 2.048 | **SELL_ALL 3 `trail`** (runner_stop @ 2.05) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $1,024.00 (realized $830.00, delta $194.00); oracle $1,216.00.
- **Parity control** — this trade's own as-placed shape, replayed: $930.61 vs $830.00 realized (gap $100.61 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$830.00** |
  | `all_out_at_tp1_100` | $1,024.00 |
  | `tp1_100_trail_10` | $949.90 |
  | `tp1_100_trail_20` | $872.80 |
  | `hold_to_time_stop` | $744.00 |
  | `all_out_at_tp1_50` | $512.00 |
  | `tp1_30_trail_125` | $306.90 |
  | `trail_only_no_tp1` | $64.00 |

### 2026-08-10 · risky-3 · `SPY260810C00775000` · realized $362.00

- **Entry** 09:35:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **772.86**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 775 (trigger 772.86, offset 2.14), quoted premium 0.54, filled **0.41** × 10, stop `0.43 (-20%)`.
- **Entry fill quality** — paid 0.0% above the signal minute's low (bar 0.41–0.46).
- **High-water WHILE IN THE TRADE** 0.89 (117.1% vs entry) at 2026-08-10T14:48:00Z UTC · 59 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.89 (117.1%) at 2026-08-10T14:48:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:47:07 | 6 | 0.8 | 95.1% | `tp1` | 0.88 | $48.00 (9.1%) |
  | 10:52:08 | 4 | 0.73 | 78.0% | `trail` | 0.89 | $64.00 (18.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:36:05 | 5 | 0.57 | 0.52 | no | 0.44 | — |
  | 09:37:04 | 5 | 0.53 | 0.52 | no | 0.44 | — |
  | 09:38:04 | 5 | 0.46 | 0.45 | no | 0.44 | — |
  | 09:39:04 | 5 | 0.46 | 0.45 | no | 0.44 | — |
  | 09:40:06 | 5 | 0.38 | 0.37 | no | 0.44 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.44) |
  | 09:59:04 | 10 | 0.44 | 0.43 | no | 0.328 | — |
  | 10:00:07 | 10 | 0.47 | 0.42 | no | 0.328 | — |
  | 10:01:06 | 10 | 0.47 | 0.46 | no | 0.328 | — |
  | 10:02:05 | 10 | 0.46 | 0.45 | no | 0.328 | — |
  | 10:03:04 | 10 | 0.53 | 0.48 | no | 0.328 | — |
  | 10:04:04 | 10 | 0.51 | 0.5 | no | 0.328 | — |
  | 10:05:06 | 10 | 0.54 | 0.49 | no | 0.328 | — |
  | 10:06:06 | 10 | 0.49 | 0.48 | no | 0.328 | — |
  | 10:07:05 | 10 | 0.54 | 0.53 | no | 0.328 | — |
  | 10:08:05 | 10 | 0.49 | 0.48 | no | 0.328 | — |
  | 10:09:04 | 10 | 0.57 | 0.56 | no | 0.328 | — |
  | 10:10:06 | 10 | 0.56 | 0.55 | no | 0.328 | — |
  | 10:11:06 | 10 | 0.64 | 0.63 | no | 0.328 | — |
  | 10:12:06 | 10 | 0.62 | 0.57 | no | 0.328 | — |
  | 10:13:05 | 10 | 0.58 | 0.53 | no | 0.328 | — |
  | 10:14:05 | 10 | 0.65 | 0.6 | no | 0.328 | — |
  | 10:15:06 | 10 | 0.62 | 0.61 | no | 0.328 | — |
  | 10:16:06 | 10 | 0.67 | 0.66 | no | 0.328 | — |
  | 10:17:05 | 10 | 0.68 | 0.67 | no | 0.328 | — |
  | 10:18:05 | 10 | 0.65 | 0.64 | no | 0.328 | — |
  | 10:19:05 | 10 | 0.57 | 0.56 | no | 0.328 | — |
  | 10:20:06 | 10 | 0.63 | 0.62 | no | 0.328 | — |
  | 10:21:07 | 10 | 0.68 | 0.63 | no | 0.328 | — |
  | 10:22:06 | 10 | 0.68 | 0.63 | no | 0.328 | — |
  | 10:23:04 | 10 | 0.66 | 0.65 | no | 0.328 | — |
  | 10:24:05 | 10 | 0.65 | 0.6 | no | 0.328 | — |
  | 10:25:06 | 10 | 0.55 | 0.54 | no | 0.328 | — |
  | 10:26:05 | 10 | 0.61 | 0.6 | no | 0.328 | — |
  | 10:27:05 | 10 | 0.66 | 0.61 | no | 0.328 | — |
  | 10:28:05 | 10 | 0.65 | 0.6 | no | 0.328 | — |
  | 10:29:04 | 10 | 0.65 | 0.64 | no | 0.328 | — |
  | 10:30:07 | 10 | 0.68 | 0.67 | no | 0.328 | — |
  | 10:31:06 | 10 | 0.67 | 0.66 | no | 0.328 | — |
  | 10:32:05 | 10 | 0.74 | 0.73 | no | 0.328 | — |
  | 10:33:05 | 10 | 0.75 | 0.74 | no | 0.328 | — |
  | 10:34:05 | 10 | 0.72 | 0.71 | no | 0.328 | — |
  | 10:35:07 | 10 | 0.72 | 0.71 | no | 0.328 | — |
  | 10:36:07 | 10 | 0.73 | 0.72 | no | 0.328 | — |
  | 10:37:06 | 10 | 0.74 | 0.69 | no | 0.328 | — |
  | 10:38:05 | 10 | 0.68 | 0.67 | no | 0.328 | — |
  | 10:39:04 | 10 | 0.71 | 0.7 | no | 0.328 | — |
  | 10:40:06 | 10 | 0.62 | 0.61 | no | 0.328 | — |
  | 10:41:05 | 10 | 0.72 | 0.71 | no | 0.328 | — |
  | 10:42:05 | 10 | 0.72 | 0.67 | no | 0.328 | — |
  | 10:43:05 | 10 | 0.73 | 0.68 | no | 0.328 | — |
  | 10:44:05 | 10 | 0.68 | 0.67 | no | 0.328 | — |
  | 10:45:06 | 10 | 0.71 | 0.66 | no | 0.328 | — |
  | 10:46:06 | 10 | 0.81 | 0.8 | no | 0.328 | — |
  | 10:47:05 | 10 | 0.83 | 0.78 | yes | 0.41 | **SELL_PARTIAL 6 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:48:05 | 4 | 0.89 | 0.88 | yes | 0.7565 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:49:05 | 4 | 0.88 | 0.87 | yes | 0.7565 | — |
  | 10:50:07 | 4 | 0.9 | 0.89 | yes | 0.765 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:51:06 | 4 | 0.79 | 0.78 | yes | 0.765 | — |
  | 10:52:06 | 4 | 0.76 | 0.75 | yes | 0.765 | **SELL_ALL 4 `trail`** (runner_stop @ 0.77) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $410.00 (realized $362.00, delta $48.00); oracle $480.00.
- **Parity control** — this trade's own as-placed shape, replayed: $393.52 vs $362.00 realized (gap $31.52 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$362.00** |
  | `all_out_at_tp1_100` | $410.00 |
  | `tp1_100_trail_10` | $402.40 |
  | `tp1_100_trail_20` | $366.80 |
  | `all_out_at_tp1_50` | $205.00 |
  | `trail_only_no_tp1` | $160.00 |
  | `tp1_30_trail_125` | $130.14 |
  | `hold_to_time_stop` | $-205.00 |

### 2026-08-11 · risky-3 · `SPY260811P00771000` · realized $90.00

- **Entry** 09:46:06 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE)_
- **Strike** 771 (trigger None, offset None), quoted premium 0.46, filled **0.45** × 10, stop `0.43 (-6%)`.
- **Entry fill quality** — paid -13.5% above the signal minute's low (bar 0.52–0.62).
- **High-water WHILE IN THE TRADE** 0.6 (33.3% vs entry) at 2026-08-11T13:47:00Z UTC · 4 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.73 (284.4%) at 2026-08-11T18:29:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:47:09 | 10 | 0.54 | 20.0% | `premium_stop` | 0.6 | $60.00 (10.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:06 | 10 | 0.51 | 0.5 | no | 0.423 | **SELL_ALL 10 `ribbon_flip`** (ribbon_flip_back) |
  | 09:52:05 | 8 | 0.63 | 0.62 | no | 0.4982 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |
  | 09:56:05 | 0 | None | None | no | None | — |
  | 09:57:05 | 10 | 0.46 | 0.41 | no | 0.4606 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.46) |

- **This trade's variant grid** — best was `tp1_30_trail_125` at $131.74 (realized $90.00, delta $41.74); oracle $1,280.00.
- **Parity control** — this trade's own as-placed shape, replayed: $144.00 vs $90.00 realized (gap $54.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$90.00** |
  | `tp1_30_trail_125` | $131.74 |
  | `trail_only_no_tp1` | $80.00 |
  | `all_out_at_tp1_100` | $-225.00 |
  | `all_out_at_tp1_50` | $-225.00 |
  | `tp1_100_trail_20` | $-225.00 |
  | `tp1_100_trail_10` | $-225.00 |
  | `hold_to_time_stop` | $-225.00 |

### 2026-08-11 · risky-3 · `SPY260811P00771000` · realized $56.00

- **Entry** 09:46:06 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE)_
- **Strike** 771 (trigger None, offset None), quoted premium 0.46, filled **0.53** × 8, stop `0.43 (-6%)`.
- **Entry fill quality** — paid -8.6% above the signal minute's low (bar 0.58–0.63).
- **High-water WHILE IN THE TRADE** 0.58 (9.4% vs entry) at 2026-08-11T13:52:00Z UTC · 4 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.73 (226.4%) at 2026-08-11T18:29:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:52:09 | 8 | 0.6 | 13.2% | `ribbon_flip` | 0.58 | $-16.00 (-3.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:06 | 10 | 0.51 | 0.5 | no | 0.423 | **SELL_ALL 10 `ribbon_flip`** (ribbon_flip_back) |
  | 09:52:05 | 8 | 0.63 | 0.62 | no | 0.4982 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |
  | 09:56:05 | 0 | None | None | no | None | — |
  | 09:57:05 | 10 | 0.46 | 0.41 | no | 0.4606 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.46) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $-48.00 (realized $56.00, delta $-104.00); oracle $960.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-25.44 vs $56.00 realized (gap $-81.44 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$56.00** |
  | `trail_only_no_tp1` | $-48.00 |
  | `all_out_at_tp1_100` | $-212.00 |
  | `all_out_at_tp1_50` | $-212.00 |
  | `tp1_30_trail_125` | $-212.00 |
  | `tp1_100_trail_20` | $-212.00 |
  | `tp1_100_trail_10` | $-212.00 |
  | `hold_to_time_stop` | $-212.00 |

### 2026-08-11 · risky-1 · `SPY260811P00773000` · realized $40.00

- **Entry** 09:46:06 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 773 (trigger None, offset None), quoted premium 0.98, filled **1.16** × 5, stop `0.92 (-6%)`.
- **Entry fill quality** — paid 4.5% above the signal minute's low (bar 1.11–1.25).
- **High-water WHILE IN THE TRADE** 1.11 (-4.3% vs entry) at 2026-08-11T13:56:00Z UTC · 8 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 3.57 (207.8%) at 2026-08-11T18:29:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:56:07 | 5 | 1.24 | 6.9% | `ribbon_flip` | 1.11 | $-65.00 (-11.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:06 | 0 | None | None | no | None | — |
  | 09:48:06 | 0 | None | None | no | None | — |
  | 09:49:05 | 0 | None | None | no | None | — |
  | 09:50:06 | 0 | None | None | no | None | — |
  | 09:51:05 | 0 | None | None | no | None | — |
  | 09:52:05 | 0 | None | None | no | None | — |
  | 09:53:05 | 5 | 1.27 | 1.26 | no | 1.269 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.27) |
  | 09:56:05 | 5 | 1.23 | 1.22 | no | 1.0904 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $-290.00 (realized $40.00, delta $-330.00); oracle $1,205.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-34.80 vs $40.00 realized (gap $-74.80 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$40.00** |
  | `all_out_at_tp1_100` | $-290.00 |
  | `all_out_at_tp1_50` | $-290.00 |
  | `tp1_30_trail_125` | $-290.00 |
  | `tp1_100_trail_20` | $-290.00 |
  | `tp1_100_trail_10` | $-290.00 |
  | `trail_only_no_tp1` | $-290.00 |
  | `hold_to_time_stop` | $-290.00 |

### 2026-08-11 · bold-2 · `SPY260811P00771000` · realized $297.00

- **Entry** 13:31:05 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.66** × 5, stop `STRUCTURE@771.00 (cat -50%)`.
- **Entry fill quality** — paid 8.2% above the signal minute's low (bar 0.61–0.71).
- **High-water WHILE IN THE TRADE** 1.73 (162.1% vs entry) at 2026-08-11T18:29:00Z UTC · 55 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.73 (162.1%) at 2026-08-11T18:29:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:41:06 | 3 | 1.29 | 95.5% | `tp1` | 1.73 | $132.00 (25.4%) |
  | 14:46:06 | 2 | 1.2 | 81.8% | `trail` | 1.73 | $106.00 (30.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:32:05 | 5 | 0.79 | 0.78 | no | 0.395 | — |
  | 13:33:05 | 5 | 0.77 | 0.76 | no | 0.395 | — |
  | 13:34:04 | 5 | 0.77 | 0.76 | no | 0.395 | — |
  | 13:35:06 | 5 | 0.67 | 0.66 | no | 0.395 | — |
  | 13:36:05 | 5 | 0.64 | 0.63 | no | 0.395 | — |
  | 13:37:04 | 5 | 0.6 | 0.59 | no | 0.395 | — |
  | 13:38:05 | 5 | 0.68 | 0.63 | no | 0.395 | — |
  | 13:39:05 | 5 | 0.76 | 0.75 | no | 0.395 | — |
  | 13:40:06 | 5 | 0.67 | 0.66 | no | 0.395 | — |
  | 13:41:05 | 5 | 0.61 | 0.6 | no | 0.395 | — |
  | 13:42:05 | 5 | 0.58 | 0.57 | no | 0.395 | — |
  | 13:43:05 | 5 | 0.53 | 0.52 | no | 0.395 | — |
  | 13:45:10 | 5 | 0.53 | 0.48 | no | 0.395 | — |
  | 13:45:42 | 5 | 0.5 | 0.49 | no | 0.395 | — |
  | 13:46:06 | 5 | 0.53 | 0.52 | no | 0.395 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 771.0) |
  | 14:08:08 | 5 | 0.62 | 0.61 | no | 0.33 | — |
  | 14:08:44 | 5 | 0.67 | 0.66 | no | 0.33 | — |
  | 14:09:52 | 5 | 0.74 | 0.73 | no | 0.33 | — |
  | 14:11:19 | 5 | 0.68 | 0.67 | no | 0.33 | — |
  | 14:11:54 | 5 | 0.64 | 0.63 | no | 0.33 | — |
  | 14:13:13 | 5 | 0.6 | 0.59 | no | 0.33 | — |
  | 14:13:47 | 5 | 0.68 | 0.67 | no | 0.33 | — |
  | 14:14:44 | 5 | 0.61 | 0.6 | no | 0.33 | — |
  | 14:15:41 | 5 | 0.6 | 0.59 | no | 0.33 | — |
  | 14:16:05 | 5 | 0.66 | 0.61 | no | 0.33 | — |
  | 14:17:04 | 5 | 0.67 | 0.66 | no | 0.33 | — |
  | 14:18:05 | 5 | 0.74 | 0.73 | no | 0.33 | — |
  | 14:19:05 | 5 | 0.63 | 0.62 | no | 0.33 | — |
  | 14:20:07 | 5 | 0.7 | 0.65 | no | 0.33 | — |
  | 14:21:05 | 5 | 0.8 | 0.79 | no | 0.33 | — |
  | 14:22:06 | 5 | 0.94 | 0.88 | no | 0.33 | — |
  | 14:23:05 | 5 | 0.85 | 0.84 | no | 0.33 | — |
  | 14:24:05 | 5 | 0.92 | 0.91 | no | 0.33 | — |
  | 14:25:06 | 5 | 0.86 | 0.81 | no | 0.33 | — |
  | 14:26:05 | 5 | 0.77 | 0.76 | no | 0.33 | — |
  | 14:27:04 | 5 | 0.9 | 0.89 | no | 0.33 | — |
  | 14:28:05 | 5 | 1.13 | 1.07 | no | 0.858 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:29:04 | 5 | 1.21 | 1.15 | no | 1.056 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:30:06 | 5 | 1.3 | 1.29 | no | 1.056 | — |
  | 14:31:45 | 5 | 1.31 | 1.29 | no | 1.056 | — |
  | 14:33:14 | 5 | 1.2 | 1.18 | no | 1.056 | — |
  | 14:33:49 | 5 | 1.22 | 1.21 | no | 1.056 | — |
  | 14:35:00 | 5 | 1.25 | 1.23 | no | 1.056 | — |
  | 14:35:44 | 5 | 1.09 | 1.08 | no | 1.056 | — |
  | 14:36:06 | 5 | 1.14 | 1.12 | no | 1.056 | — |
  | 14:37:05 | 5 | 1.14 | 1.12 | no | 1.056 | — |
  | 14:38:05 | 5 | 1.24 | 1.22 | no | 1.056 | — |
  | 14:39:04 | 5 | 1.18 | 1.17 | no | 1.056 | — |
  | 14:40:05 | 5 | 1.29 | 1.28 | no | 1.056 | — |
  | 14:41:05 | 5 | 1.32 | 1.26 | yes | 0.66 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:42:05 | 2 | 1.45 | 1.39 | yes | 1.2325 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:43:04 | 2 | 1.38 | 1.36 | yes | 1.2325 | — |
  | 14:44:04 | 2 | 1.3 | 1.28 | yes | 1.2325 | — |
  | 14:45:05 | 2 | 1.31 | 1.3 | yes | 1.2325 | — |
  | 14:46:05 | 2 | 1.24 | 1.22 | yes | 1.2325 | **SELL_ALL 2 `trail`** (runner_stop @ 1.23) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $377.40 (realized $297.00, delta $80.40); oracle $535.00.
- **Parity control** — this trade's own as-placed shape, replayed: $198.00 vs $297.00 realized (gap $-99.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$297.00** |
  | `tp1_100_trail_10` | $377.40 |
  | `tp1_100_trail_20` | $342.80 |
  | `all_out_at_tp1_100` | $330.00 |
  | `all_out_at_tp1_50` | $165.00 |
  | `hold_to_time_stop` | $130.00 |
  | `tp1_30_trail_125` | $99.82 |
  | `trail_only_no_tp1` | $15.00 |

### 2026-08-11 · risky-1 · `SPY260811P00771000` · realized $266.00

- **Entry** 13:32:07 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **771.0**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE); qty clamped 8->5: recency RED_
- **Strike** 771 (trigger 771.0, offset 0.0), quoted premium 0.76, filled **0.64** × 5, stop `STRUCTURE@771.00 (cat -50%)`.
- **Entry fill quality** — paid 4.9% above the signal minute's low (bar 0.61–0.71).
- **High-water WHILE IN THE TRADE** 1.73 (170.3% vs entry) at 2026-08-11T18:29:00Z UTC · 39 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.73 (170.3%) at 2026-08-11T18:29:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:28:08 | 3 | 1.12 | 75.0% | `tp1` | 1.32 | $60.00 (15.2%) |
  | 14:32:08 | 2 | 1.25 | 95.3% | `trail` | 1.73 | $96.00 (27.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:33:06 | 5 | 0.76 | 0.75 | no | 0.39 | — |
  | 13:34:06 | 5 | 0.77 | 0.76 | no | 0.39 | — |
  | 13:35:07 | 5 | 0.67 | 0.66 | no | 0.39 | — |
  | 13:36:07 | 5 | 0.65 | 0.64 | no | 0.39 | — |
  | 13:37:07 | 5 | 0.6 | 0.59 | no | 0.39 | — |
  | 13:38:06 | 5 | 0.69 | 0.68 | no | 0.39 | — |
  | 13:39:06 | 5 | 0.74 | 0.73 | no | 0.39 | — |
  | 13:40:08 | 5 | 0.66 | 0.65 | no | 0.39 | — |
  | 13:41:06 | 5 | 0.66 | 0.61 | no | 0.39 | — |
  | 13:42:06 | 5 | 0.58 | 0.57 | no | 0.39 | — |
  | 13:43:07 | 5 | 0.53 | 0.48 | no | 0.39 | — |
  | 13:44:06 | 5 | 0.53 | 0.48 | no | 0.39 | — |
  | 13:45:08 | 5 | 0.51 | 0.5 | no | 0.39 | — |
  | 13:46:07 | 5 | 0.54 | 0.52 | no | 0.39 | — |
  | 13:47:07 | 5 | 0.52 | 0.51 | no | 0.39 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 771.0) |
  | 14:09:06 | 5 | 0.65 | 0.64 | no | 0.32 | — |
  | 14:10:08 | 5 | 0.68 | 0.67 | no | 0.32 | — |
  | 14:11:07 | 5 | 0.7 | 0.69 | no | 0.32 | — |
  | 14:12:06 | 5 | 0.66 | 0.61 | no | 0.32 | — |
  | 14:13:06 | 5 | 0.65 | 0.64 | no | 0.32 | — |
  | 14:14:06 | 5 | 0.67 | 0.66 | no | 0.32 | — |
  | 14:15:08 | 5 | 0.66 | 0.61 | no | 0.32 | — |
  | 14:16:06 | 5 | 0.62 | 0.61 | no | 0.32 | — |
  | 14:17:06 | 5 | 0.72 | 0.71 | no | 0.32 | — |
  | 14:18:06 | 5 | 0.74 | 0.73 | no | 0.32 | — |
  | 14:19:06 | 5 | 0.66 | 0.65 | no | 0.32 | — |
  | 14:20:07 | 5 | 0.7 | 0.65 | no | 0.32 | — |
  | 14:21:06 | 5 | 0.85 | 0.79 | no | 0.32 | — |
  | 14:22:06 | 5 | 0.93 | 0.91 | no | 0.32 | — |
  | 14:23:06 | 5 | 0.9 | 0.88 | no | 0.32 | — |
  | 14:24:06 | 5 | 0.94 | 0.93 | no | 0.32 | — |
  | 14:25:07 | 5 | 0.81 | 0.8 | no | 0.32 | — |
  | 14:26:06 | 5 | 0.82 | 0.81 | no | 0.32 | — |
  | 14:27:06 | 5 | 0.87 | 0.85 | no | 0.32 | — |
  | 14:28:06 | 5 | 1.16 | 1.14 | yes | 0.64 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:29:05 | 2 | 1.2 | 1.19 | yes | 1.02 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:30:07 | 2 | 1.34 | 1.33 | yes | 1.139 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:31:06 | 2 | 1.58 | 1.52 | yes | 1.343 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:32:07 | 2 | 1.28 | 1.27 | yes | 1.343 | **SELL_ALL 2 `trail`** (runner_stop @ 1.34) |

- **Tags:** `runner_material_giveback`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $375.40 (realized $266.00, delta $109.40); oracle $545.00.
- **Parity control** — this trade's own as-placed shape, replayed: $141.24 vs $266.00 realized (gap $-124.76 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$266.00** |
  | `tp1_100_trail_10` | $375.40 |
  | `tp1_100_trail_20` | $340.80 |
  | `all_out_at_tp1_100` | $320.00 |
  | `all_out_at_tp1_50` | $160.00 |
  | `hold_to_time_stop` | $140.00 |
  | `tp1_30_trail_125` | $99.42 |
  | `trail_only_no_tp1` | $-10.00 |

### 2026-08-11 · safe-2 · `SPY260811P00771000` · realized $195.00

- **Entry** 13:44:03 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.49** × 3, stop `STRUCTURE@771.45 (cat -50%)`.
- **Entry fill quality** — paid 4.3% above the signal minute's low (bar 0.47–0.54).
- **High-water WHILE IN THE TRADE** 1.73 (253.1% vs entry) at 2026-08-11T18:29:00Z UTC · 47 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.73 (253.1%) at 2026-08-11T18:29:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:28:05 | 2 | 1.09 | 122.4% | `tp1` | 1.32 | $46.00 (17.4%) |
  | 14:32:05 | 1 | 1.24 | 153.1% | `trail` | 1.73 | $49.00 (28.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:46:04 | 3 | 0.53 | 0.52 | no | 0.245 | — |
  | 13:47:03 | 3 | 0.51 | 0.5 | no | 0.245 | — |
  | 13:48:04 | 3 | 0.48 | 0.43 | no | 0.245 | — |
  | 13:49:04 | 3 | 0.43 | 0.42 | no | 0.245 | — |
  | 13:50:05 | 3 | 0.52 | 0.51 | no | 0.245 | — |
  | 13:51:03 | 3 | 0.49 | 0.48 | no | 0.245 | — |
  | 13:52:04 | 3 | 0.47 | 0.46 | no | 0.245 | — |
  | 13:53:03 | 3 | 0.49 | 0.48 | no | 0.245 | — |
  | 13:54:04 | 3 | 0.49 | 0.48 | no | 0.245 | — |
  | 13:55:04 | 3 | 0.47 | 0.46 | no | 0.245 | — |
  | 13:56:04 | 3 | 0.46 | 0.45 | no | 0.245 | — |
  | 13:57:04 | 3 | 0.51 | 0.5 | no | 0.245 | — |
  | 13:58:04 | 3 | 0.48 | 0.47 | no | 0.245 | — |
  | 13:59:03 | 3 | 0.47 | 0.42 | no | 0.245 | — |
  | 14:00:05 | 3 | 0.48 | 0.43 | no | 0.245 | — |
  | 14:01:03 | 3 | 0.52 | 0.47 | no | 0.245 | — |
  | 14:02:04 | 3 | 0.55 | 0.54 | no | 0.245 | — |
  | 14:03:04 | 3 | 0.58 | 0.57 | no | 0.245 | — |
  | 14:04:03 | 3 | 0.53 | 0.52 | no | 0.245 | — |
  | 14:05:05 | 3 | 0.55 | 0.54 | no | 0.245 | — |
  | 14:06:04 | 3 | 0.58 | 0.57 | no | 0.245 | — |
  | 14:07:03 | 3 | 0.71 | 0.66 | no | 0.245 | — |
  | 14:08:04 | 3 | 0.66 | 0.65 | no | 0.245 | — |
  | 14:09:04 | 3 | 0.68 | 0.67 | no | 0.245 | — |
  | 14:10:04 | 3 | 0.71 | 0.7 | no | 0.245 | — |
  | 14:11:04 | 3 | 0.7 | 0.69 | no | 0.245 | — |
  | 14:12:04 | 3 | 0.66 | 0.65 | no | 0.245 | — |
  | 14:13:04 | 3 | 0.65 | 0.64 | no | 0.245 | — |
  | 14:14:04 | 3 | 0.68 | 0.67 | no | 0.245 | — |
  | 14:15:04 | 3 | 0.66 | 0.64 | no | 0.245 | — |
  | 14:16:04 | 3 | 0.66 | 0.61 | no | 0.245 | — |
  | 14:17:03 | 3 | 0.71 | 0.7 | no | 0.245 | — |
  | 14:18:04 | 3 | 0.7 | 0.69 | no | 0.245 | — |
  | 14:19:04 | 3 | 0.67 | 0.62 | no | 0.245 | — |
  | 14:20:05 | 3 | 0.66 | 0.65 | no | 0.245 | — |
  | 14:21:04 | 3 | 0.82 | 0.77 | no | 0.637 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:22:04 | 3 | 0.9 | 0.88 | no | 0.784 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:23:04 | 3 | 0.85 | 0.84 | no | 0.784 | — |
  | 14:24:04 | 3 | 0.96 | 0.91 | no | 0.784 | — |
  | 14:25:04 | 3 | 0.86 | 0.85 | no | 0.784 | — |
  | 14:26:04 | 3 | 0.81 | 0.8 | no | 0.784 | — |
  | 14:27:03 | 3 | 0.92 | 0.9 | no | 0.784 | — |
  | 14:28:04 | 3 | 1.09 | 1.07 | yes | 0.49 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:29:03 | 1 | 1.22 | 1.19 | yes | 1.037 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:30:04 | 1 | 1.29 | 1.28 | yes | 1.0965 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:31:03 | 1 | 1.62 | 1.55 | yes | 1.377 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:32:04 | 1 | 1.28 | 1.26 | yes | 1.377 | **SELL_ALL 1 `trail`** (runner_stop @ 1.38) |

- **Tags:** `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $147.00 (realized $195.00, delta $-48.00); oracle $372.00.
- **Parity control** — this trade's own as-placed shape, replayed: $220.50 vs $195.00 realized (gap $25.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$195.00** |
  | `all_out_at_tp1_100` | $147.00 |
  | `tp1_100_trail_10` | $138.10 |
  | `hold_to_time_stop` | $129.00 |
  | `tp1_100_trail_20` | $128.20 |
  | `all_out_at_tp1_50` | $73.50 |
  | `tp1_30_trail_125` | $42.52 |
  | `trail_only_no_tp1` | $-3.00 |

### 2026-08-12 · risky-1 · `SPY260812P00773000` · realized $40.00

- **Entry** 09:46:04 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 773 (trigger None, offset None), quoted premium 1.67, filled **1.44** × 5, stop `1.57 (-6%)`.
- **Entry fill quality** — paid 6.7% above the signal minute's low (bar 1.35–1.54).
- **High-water WHILE IN THE TRADE** 1.58 (9.7% vs entry) at 2026-08-12T13:54:00Z UTC · 11 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.92 (33.3%) at 2026-08-12T14:31:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:54:08 | 5 | 1.52 | 5.6% | `ribbon_flip` | 1.58 | $30.00 (3.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:05 | 5 | 1.63 | 1.61 | no | 1.5228 | — |
  | 09:48:04 | 5 | 1.56 | 1.55 | no | 1.5228 | — |
  | 09:49:05 | 5 | 1.54 | 1.49 | no | 1.5228 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.52) |
  | 09:53:05 | 5 | 1.52 | 1.5 | no | 1.3536 | — |
  | 09:54:04 | 5 | 1.52 | 1.5 | no | 1.3536 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 10:01:05 | 5 | 1.67 | 1.65 | no | 1.4288 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:25:06 | 5 | 0.77 | 0.76 | no | 0.39 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:33:06 | 5 | 0.65 | 0.64 | no | 0.35 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:49:05 | 5 | 0.66 | 0.61 | no | 0.305 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:53:04 | 5 | 0.62 | 0.57 | no | 0.295 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:56:05 | 5 | 0.7 | 0.69 | no | 0.33 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_30_trail_125` at $196.80 (realized $40.00, delta $156.80); oracle $240.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-43.20 vs $40.00 realized (gap $-83.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$40.00** |
  | `tp1_30_trail_125` | $196.80 |
  | `trail_only_no_tp1` | $60.00 |
  | `all_out_at_tp1_100` | $-360.00 |
  | `all_out_at_tp1_50` | $-360.00 |
  | `tp1_100_trail_20` | $-360.00 |
  | `tp1_100_trail_10` | $-360.00 |
  | `hold_to_time_stop` | $-360.00 |

### 2026-08-12 · risky-1 · `SPY260812P00773000` · realized $55.00

- **Entry** 09:46:04 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 773 (trigger None, offset None), quoted premium 1.67, filled **1.52** × 5, stop `1.57 (-6%)`.
- **Entry fill quality** — paid -3.8% above the signal minute's low (bar 1.58–1.77).
- **High-water WHILE IN THE TRADE** 1.63 (7.2% vs entry) at 2026-08-12T14:01:00Z UTC · 11 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.92 (26.3%) at 2026-08-12T14:31:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:01:07 | 5 | 1.63 | 7.2% | `ribbon_flip` | 1.63 | $0.00 (0.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:05 | 5 | 1.63 | 1.61 | no | 1.5228 | — |
  | 09:48:04 | 5 | 1.56 | 1.55 | no | 1.5228 | — |
  | 09:49:05 | 5 | 1.54 | 1.49 | no | 1.5228 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.52) |
  | 09:53:05 | 5 | 1.52 | 1.5 | no | 1.3536 | — |
  | 09:54:04 | 5 | 1.52 | 1.5 | no | 1.3536 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 10:01:05 | 5 | 1.67 | 1.65 | no | 1.4288 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:25:06 | 5 | 0.77 | 0.76 | no | 0.39 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:33:06 | 5 | 0.65 | 0.64 | no | 0.35 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:49:05 | 5 | 0.66 | 0.61 | no | 0.305 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:53:04 | 5 | 0.62 | 0.57 | no | 0.295 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:56:05 | 5 | 0.7 | 0.69 | no | 0.33 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $15.00 (realized $55.00, delta $-40.00); oracle $200.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-45.60 vs $55.00 realized (gap $-100.60 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$55.00** |
  | `trail_only_no_tp1` | $15.00 |
  | `all_out_at_tp1_100` | $-380.00 |
  | `all_out_at_tp1_50` | $-380.00 |
  | `tp1_30_trail_125` | $-380.00 |
  | `tp1_100_trail_20` | $-380.00 |
  | `tp1_100_trail_10` | $-380.00 |
  | `hold_to_time_stop` | $-380.00 |

### 2026-08-12 · risky-1 · `SPY260812P00773000` · realized $10.00

- **Entry** 09:46:04 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 773 (trigger None, offset None), quoted premium 1.67, filled **0.61** × 5, stop `1.57 (-6%)`.
- **Entry fill quality** — paid 1.7% above the signal minute's low (bar 0.6–0.67).
- **High-water WHILE IN THE TRADE** 0.68 (11.5% vs entry) at 2026-08-12T17:49:00Z UTC · 11 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.05 (72.1%) at 2026-08-12T19:55:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:49:07 | 5 | 0.63 | 3.3% | `ribbon_flip` | 0.68 | $25.00 (7.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:05 | 5 | 1.63 | 1.61 | no | 1.5228 | — |
  | 09:48:04 | 5 | 1.56 | 1.55 | no | 1.5228 | — |
  | 09:49:05 | 5 | 1.54 | 1.49 | no | 1.5228 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.52) |
  | 09:53:05 | 5 | 1.52 | 1.5 | no | 1.3536 | — |
  | 09:54:04 | 5 | 1.52 | 1.5 | no | 1.3536 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 10:01:05 | 5 | 1.67 | 1.65 | no | 1.4288 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:25:06 | 5 | 0.77 | 0.76 | no | 0.39 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:33:06 | 5 | 0.65 | 0.64 | no | 0.35 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:49:05 | 5 | 0.66 | 0.61 | no | 0.305 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:53:04 | 5 | 0.62 | 0.57 | no | 0.295 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:56:05 | 5 | 0.7 | 0.69 | no | 0.33 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $-5.00 (realized $10.00, delta $-15.00); oracle $220.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-18.30 vs $10.00 realized (gap $-28.30 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$10.00** |
  | `trail_only_no_tp1` | $-5.00 |
  | `all_out_at_tp1_100` | $-152.50 |
  | `all_out_at_tp1_50` | $-152.50 |
  | `tp1_30_trail_125` | $-152.50 |
  | `tp1_100_trail_20` | $-152.50 |
  | `tp1_100_trail_10` | $-152.50 |
  | `hold_to_time_stop` | $-152.50 |

### 2026-08-12 · risky-1 · `SPY260812P00773000` · realized $5.00

- **Entry** 09:46:04 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 773 (trigger None, offset None), quoted premium 1.67, filled **0.66** × 5, stop `1.57 (-6%)`.
- **Entry fill quality** — paid 1.5% above the signal minute's low (bar 0.65–0.74).
- **High-water WHILE IN THE TRADE** 0.71 (7.6% vs entry) at 2026-08-12T17:56:00Z UTC · 11 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.05 (59.1%) at 2026-08-12T19:55:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:56:07 | 5 | 0.67 | 1.5% | `ribbon_flip` | 0.71 | $20.00 (5.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:05 | 5 | 1.63 | 1.61 | no | 1.5228 | — |
  | 09:48:04 | 5 | 1.56 | 1.55 | no | 1.5228 | — |
  | 09:49:05 | 5 | 1.54 | 1.49 | no | 1.5228 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.52) |
  | 09:53:05 | 5 | 1.52 | 1.5 | no | 1.3536 | — |
  | 09:54:04 | 5 | 1.52 | 1.5 | no | 1.3536 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 10:01:05 | 5 | 1.67 | 1.65 | no | 1.4288 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:25:06 | 5 | 0.77 | 0.76 | no | 0.39 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:33:06 | 5 | 0.65 | 0.64 | no | 0.35 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:49:05 | 5 | 0.66 | 0.61 | no | 0.305 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:53:04 | 5 | 0.62 | 0.57 | no | 0.295 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 13:56:05 | 5 | 0.7 | 0.69 | no | 0.33 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $-10.00 (realized $5.00, delta $-15.00); oracle $195.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-19.80 vs $5.00 realized (gap $-24.80 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$5.00** |
  | `trail_only_no_tp1` | $-10.00 |
  | `all_out_at_tp1_100` | $-165.00 |
  | `all_out_at_tp1_50` | $-165.00 |
  | `tp1_30_trail_125` | $-165.00 |
  | `tp1_100_trail_20` | $-165.00 |
  | `tp1_100_trail_10` | $-165.00 |
  | `hold_to_time_stop` | $-165.00 |

### 2026-08-12 · risky-3 · `SPY260812P00771000` · realized $32.00

- **Entry** 09:46:04 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE)_
- **Strike** 771 (trigger None, offset None), quoted premium 0.83, filled **0.7** × 8, stop `0.78 (-6%)`.
- **Entry fill quality** — paid 6.1% above the signal minute's low (bar 0.66–0.75).
- **High-water WHILE IN THE TRADE** 0.82 (17.1% vs entry) at 2026-08-12T13:53:00Z UTC · 6 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.05 (50.0%) at 2026-08-12T14:31:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:54:09 | 1 | 0.74 | 5.7% | `?` | 0.82 | $8.00 (9.8%) |
  | 09:54:09 | 7 | 0.74 | 5.7% | `?` | 0.82 | $56.00 (9.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:05 | 8 | 0.87 | 0.86 | no | 0.7708 | — |
  | 09:48:04 | 8 | 0.8 | 0.79 | no | 0.7708 | — |
  | 09:49:05 | 8 | 0.73 | 0.72 | no | 0.7708 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.77) |
  | 09:53:05 | 8 | 0.78 | 0.77 | no | 0.658 | — |
  | 09:54:04 | 8 | 0.76 | 0.75 | no | 0.658 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |
  | 10:01:05 | 8 | 0.84 | 0.79 | no | 0.7426 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $280.00 (realized $32.00, delta $248.00); oracle $280.00.
- **Parity control** — this trade's own as-placed shape, replayed: $168.00 vs $32.00 realized (gap $136.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$32.00** |
  | `all_out_at_tp1_50` | $280.00 |
  | `tp1_30_trail_125` | $161.00 |
  | `trail_only_no_tp1` | $88.00 |
  | `all_out_at_tp1_100` | $-280.00 |
  | `tp1_100_trail_20` | $-280.00 |
  | `tp1_100_trail_10` | $-280.00 |
  | `hold_to_time_stop` | $-280.00 |

### 2026-08-12 · risky-3 · `SPY260812P00771000` · realized $16.00

- **Entry** 09:46:04 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE)_
- **Strike** 771 (trigger None, offset None), quoted premium 0.83, filled **0.79** × 8, stop `0.78 (-6%)`.
- **Entry fill quality** — paid 0.0% above the signal minute's low (bar 0.79–0.9).
- **High-water WHILE IN THE TRADE** 0.81 (2.5% vs entry) at 2026-08-12T14:01:00Z UTC · 6 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.05 (32.9%) at 2026-08-12T14:31:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:01:09 | 2 | 0.81 | 2.5% | `?` | 0.81 | $0.00 (0.0%) |
  | 10:01:09 | 6 | 0.81 | 2.5% | `?` | 0.81 | $0.00 (0.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:47:05 | 8 | 0.87 | 0.86 | no | 0.7708 | — |
  | 09:48:04 | 8 | 0.8 | 0.79 | no | 0.7708 | — |
  | 09:49:05 | 8 | 0.73 | 0.72 | no | 0.7708 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.77) |
  | 09:53:05 | 8 | 0.78 | 0.77 | no | 0.658 | — |
  | 09:54:04 | 8 | 0.76 | 0.75 | no | 0.658 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |
  | 10:01:05 | 8 | 0.84 | 0.79 | no | 0.7426 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_30_trail_125` at $167.96 (realized $16.00, delta $151.96); oracle $208.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-37.92 vs $16.00 realized (gap $-53.92 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$16.00** |
  | `tp1_30_trail_125` | $167.96 |
  | `trail_only_no_tp1` | $56.00 |
  | `all_out_at_tp1_100` | $-316.00 |
  | `all_out_at_tp1_50` | $-316.00 |
  | `tp1_100_trail_20` | $-316.00 |
  | `tp1_100_trail_10` | $-316.00 |
  | `hold_to_time_stop` | $-316.00 |

### 2026-08-12 · risky-1 · `SPY260812P00772000` · realized $5.00

- **Entry** 09:58:05 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE); qty clamped 8->5: FULL_SEND min size_
- **Strike** 772 (trigger None, offset None), quoted premium 1.25, filled **0.8** × 5, stop `1.17 (-6%)`.
- **Entry fill quality** — paid 11.1% above the signal minute's low (bar 0.72–0.84).
- **High-water WHILE IN THE TRADE** 0.86 (7.5% vs entry) at 2026-08-12T15:31:00Z UTC · 4 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.1 (37.5%) at 2026-08-12T15:34:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:31:07 | 5 | 0.81 | 1.2% | `ribbon_flip` | 0.86 | $25.00 (5.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:59:04 | 5 | 1.13 | 1.08 | no | 1.1844 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.18) |
  | 10:04:05 | 5 | 1.27 | 1.26 | no | 1.1656 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 11:28:05 | 5 | 0.96 | 0.91 | no | 0.475 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |
  | 11:31:05 | 5 | 0.77 | 0.76 | no | 0.4 | **SELL_ALL 5 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_30_trail_125` at $112.25 (realized $5.00, delta $107.25); oracle $150.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-24.00 vs $5.00 realized (gap $-29.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$5.00** |
  | `tp1_30_trail_125` | $112.25 |
  | `trail_only_no_tp1` | $20.00 |
  | `all_out_at_tp1_100` | $-200.00 |
  | `all_out_at_tp1_50` | $-200.00 |
  | `tp1_100_trail_20` | $-200.00 |
  | `tp1_100_trail_10` | $-200.00 |
  | `hold_to_time_stop` | $-200.00 |

### 2026-08-12 · risky-3 · `SPY260812P00770000` · realized $8.00

- **Entry** 09:58:05 ET — `VWAP_CONTINUATION` (ENTER_BEAR), quality **BASE**, trigger **None**, risk `ALLOW`.
  - engine's own words: _vwap_continuation P (BASE)_
- **Strike** 770 (trigger None, offset None), quoted premium 0.65, filled **0.6** × 8, stop `0.61 (-6%)`.
- **Entry fill quality** — paid 1.7% above the signal minute's low (bar 0.59–0.64).
- **High-water WHILE IN THE TRADE** 0.69 (15.0% vs entry) at 2026-08-12T14:04:00Z UTC · 3 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.69 (15.0%) at 2026-08-12T14:04:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:04:10 | 2 | 0.61 | 1.7% | `?` | 0.69 | $16.00 (11.6%) |
  | 10:04:10 | 6 | 0.61 | 1.7% | `?` | 0.69 | $48.00 (11.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:59:04 | 8 | 0.51 | 0.5 | no | 0.5922 | **SELL_ALL 8 `premium_stop`** (premium_stop @ 0.59) |
  | 10:04:05 | 8 | 0.64 | 0.63 | no | 0.564 | **SELL_ALL 8 `ribbon_flip`** (ribbon_flip_back) |
  | 11:28:05 | 10 | 0.35 | 0.3 | no | 0.272 | **SELL_ALL 10 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $-24.00 (realized $8.00, delta $-32.00); oracle $72.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-28.80 vs $8.00 realized (gap $-36.80 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$8.00** |
  | `trail_only_no_tp1` | $-24.00 |
  | `all_out_at_tp1_100` | $-240.00 |
  | `all_out_at_tp1_50` | $-240.00 |
  | `tp1_30_trail_125` | $-240.00 |
  | `tp1_100_trail_20` | $-240.00 |
  | `tp1_100_trail_10` | $-240.00 |
  | `hold_to_time_stop` | $-240.00 |

### 2026-08-12 · safe-3 · `SPY260812C00773000` · realized $45.00

- **Entry** 10:04:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **772.1**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 773 (trigger 772.1, offset 0.9), quoted premium 1.04, filled **0.56** × 3, stop `STRUCTURE@772.10 (cat -50%)`.
- **Entry fill quality** — paid 7.7% above the signal minute's low (bar 0.52–0.58).
- **High-water WHILE IN THE TRADE** 0.9 (60.7% vs entry) at 2026-08-12T18:42:00Z UTC · 95 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.9 (60.7%) at 2026-08-12T18:42:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:55:08 | 3 | 0.71 | 26.8% | `premium_stop` | 0.9 | $57.00 (21.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:05:06 | 3 | 0.98 | 0.97 | no | 0.51 | — |
  | 10:06:05 | 3 | 0.97 | 0.96 | no | 0.51 | — |
  | 10:07:05 | 3 | 1.06 | 1.01 | no | 0.51 | — |
  | 10:08:06 | 3 | 0.97 | 0.96 | no | 0.51 | — |
  | 10:09:05 | 3 | 0.98 | 0.93 | no | 0.51 | — |
  | 10:10:07 | 3 | 1.06 | 1.05 | no | 0.51 | — |
  | 10:11:06 | 3 | 1.04 | 1.03 | no | 0.51 | — |
  | 10:12:05 | 3 | 1.11 | 1.1 | no | 0.51 | — |
  | 10:13:05 | 3 | 1.03 | 1.02 | no | 0.51 | — |
  | 10:14:05 | 3 | 0.95 | 0.9 | no | 0.51 | — |
  | 10:15:07 | 3 | 1.04 | 0.99 | no | 0.51 | — |
  | 10:16:05 | 3 | 0.94 | 0.93 | no | 0.51 | — |
  | 10:17:05 | 3 | 1.06 | 1.05 | no | 0.51 | — |
  | 10:18:05 | 3 | 0.99 | 0.98 | no | 0.51 | — |
  | 10:19:04 | 3 | 1.13 | 1.08 | no | 0.51 | — |
  | 10:20:07 | 3 | 1.05 | 1.0 | no | 0.51 | — |
  | 10:21:06 | 3 | 0.98 | 0.97 | no | 0.51 | — |
  | 10:22:07 | 3 | 0.94 | 0.93 | no | 0.51 | — |
  | 10:23:06 | 3 | 1.08 | 1.07 | no | 0.51 | — |
  | 10:24:06 | 3 | 1.11 | 1.1 | no | 0.51 | — |
  | 10:25:07 | 3 | 1.23 | 1.18 | no | 0.51 | — |
  | 10:26:05 | 3 | 1.16 | 1.15 | no | 0.51 | — |
  | 10:27:05 | 3 | 1.24 | 1.23 | no | 0.51 | — |
  | 10:28:05 | 3 | 1.29 | 1.24 | no | 0.51 | — |
  | 10:29:05 | 3 | 1.24 | 1.23 | no | 0.51 | — |
  | 10:30:07 | 3 | 1.12 | 1.11 | no | 0.51 | — |
  | 10:31:06 | 3 | 1.06 | 1.05 | no | 0.51 | — |
  | 10:32:06 | 3 | 1.06 | 1.04 | no | 0.51 | — |
  | 10:33:05 | 3 | 0.95 | 0.94 | no | 0.51 | — |
  | 10:34:04 | 3 | 1.0 | 0.95 | no | 0.51 | — |
  | 10:35:06 | 3 | 0.89 | 0.87 | no | 0.51 | — |
  | 10:36:05 | 3 | 0.89 | 0.84 | no | 0.51 | — |
  | 10:37:05 | 3 | 0.87 | 0.86 | no | 0.51 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 772.1) |
  | 12:59:05 | 3 | 0.65 | 0.64 | no | 0.34 | — |
  | 13:00:07 | 3 | 0.69 | 0.64 | no | 0.34 | — |
  | 13:01:05 | 3 | 0.73 | 0.68 | no | 0.34 | — |
  | 13:02:07 | 3 | 0.67 | 0.66 | no | 0.34 | — |
  | 13:03:05 | 3 | 0.66 | 0.65 | no | 0.34 | — |
  | 13:04:05 | 3 | 0.74 | 0.73 | no | 0.34 | — |
  | 13:05:06 | 3 | 0.73 | 0.72 | no | 0.34 | — |
  | 13:06:05 | 3 | 0.73 | 0.72 | no | 0.34 | — |
  | 13:07:06 | 3 | 0.77 | 0.76 | no | 0.34 | — |
  | 13:08:05 | 3 | 0.86 | 0.85 | no | 0.34 | — |
  | 13:09:05 | 3 | 0.82 | 0.81 | no | 0.34 | — |
  | 13:10:07 | 3 | 0.71 | 0.66 | no | 0.34 | — |
  | 13:11:06 | 3 | 0.72 | 0.71 | no | 0.34 | — |
  | 13:12:05 | 3 | 0.65 | 0.64 | no | 0.34 | — |
  | 13:13:05 | 3 | 0.69 | 0.68 | no | 0.34 | — |
  | 13:14:06 | 3 | 0.65 | 0.64 | no | 0.34 | — |
  | 13:15:06 | 3 | 0.68 | 0.63 | no | 0.34 | — |
  | 13:16:06 | 3 | 0.56 | 0.55 | no | 0.34 | — |
  | 13:17:06 | 3 | 0.56 | 0.51 | no | 0.34 | — |
  | 13:18:06 | 3 | 0.56 | 0.55 | no | 0.34 | — |
  | 13:19:05 | 3 | 0.55 | 0.5 | no | 0.34 | — |
  | 13:20:07 | 3 | 0.53 | 0.52 | no | 0.34 | — |
  | 13:21:06 | 3 | 0.58 | 0.53 | no | 0.34 | — |
  | 13:22:06 | 3 | 0.6 | 0.55 | no | 0.34 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 772.89) |
  | 14:18:05 | 3 | 0.54 | 0.53 | no | 0.28 | — |
  | 14:19:05 | 3 | 0.57 | 0.52 | no | 0.28 | — |
  | 14:20:07 | 3 | 0.63 | 0.58 | no | 0.28 | — |
  | 14:21:05 | 3 | 0.54 | 0.53 | no | 0.28 | — |
  | 14:22:06 | 3 | 0.58 | 0.53 | no | 0.28 | — |
  | 14:23:05 | 3 | 0.57 | 0.52 | no | 0.28 | — |
  | 14:24:05 | 3 | 0.6 | 0.59 | no | 0.28 | — |
  | 14:25:06 | 3 | 0.69 | 0.68 | no | 0.28 | — |
  | 14:26:05 | 3 | 0.64 | 0.63 | no | 0.28 | — |
  | 14:27:05 | 3 | 0.65 | 0.64 | no | 0.28 | — |
  | 14:28:05 | 3 | 0.62 | 0.61 | no | 0.28 | — |
  | 14:29:04 | 3 | 0.63 | 0.62 | no | 0.28 | — |
  | 14:30:06 | 3 | 0.61 | 0.6 | no | 0.28 | — |
  | 14:31:05 | 3 | 0.65 | 0.64 | no | 0.28 | — |
  | 14:32:05 | 3 | 0.72 | 0.67 | no | 0.28 | — |
  | 14:33:05 | 3 | 0.78 | 0.77 | no | 0.28 | — |
  | 14:34:05 | 3 | 0.77 | 0.76 | no | 0.28 | — |
  | 14:35:06 | 3 | 0.74 | 0.69 | no | 0.28 | — |
  | 14:36:05 | 3 | 0.78 | 0.77 | no | 0.28 | — |
  | 14:37:05 | 3 | 0.8 | 0.75 | no | 0.28 | — |
  | 14:38:05 | 3 | 0.76 | 0.75 | no | 0.28 | — |
  | 14:39:04 | 3 | 0.79 | 0.78 | no | 0.28 | — |
  | 14:40:06 | 3 | 0.79 | 0.78 | no | 0.28 | — |
  | 14:41:05 | 3 | 0.82 | 0.81 | no | 0.28 | — |
  | 14:42:05 | 3 | 0.88 | 0.87 | no | 0.728 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:43:04 | 3 | 0.81 | 0.8 | no | 0.728 | — |
  | 14:44:05 | 3 | 0.85 | 0.8 | no | 0.728 | — |
  | 14:45:06 | 3 | 0.82 | 0.77 | no | 0.728 | — |
  | 14:46:05 | 3 | 0.74 | 0.73 | no | 0.728 | — |
  | 14:47:05 | 3 | 0.82 | 0.77 | no | 0.728 | — |
  | 14:48:05 | 3 | 0.8 | 0.79 | no | 0.728 | — |
  | 14:49:05 | 3 | 0.79 | 0.78 | no | 0.728 | — |
  | 14:50:06 | 3 | 0.83 | 0.78 | no | 0.728 | — |
  | 14:51:05 | 3 | 0.79 | 0.77 | no | 0.728 | — |
  | 14:52:06 | 3 | 0.86 | 0.81 | no | 0.728 | — |
  | 14:53:05 | 3 | 0.8 | 0.79 | no | 0.728 | — |
  | 14:54:05 | 3 | 0.78 | 0.77 | no | 0.728 | — |
  | 14:55:06 | 3 | 0.7 | 0.69 | no | 0.728 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 0.73) |

- **This trade's variant grid** — best was `all_out_at_tp1_50` at $84.00 (realized $45.00, delta $39.00); oracle $102.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-84.00 vs $45.00 realized (gap $-129.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$45.00** |
  | `all_out_at_tp1_50` | $84.00 |
  | `tp1_30_trail_125` | $46.73 |
  | `trail_only_no_tp1` | $6.00 |
  | `all_out_at_tp1_100` | $-84.00 |
  | `tp1_100_trail_20` | $-84.00 |
  | `tp1_100_trail_10` | $-84.00 |
  | `hold_to_time_stop` | $-84.00 |

### 2026-08-12 · risky-1 · `SPY260812C00773000` · realized $122.00

- **Entry** 10:05:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **772.1**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 773 (trigger 772.1, offset 0.9), quoted premium 0.94, filled **0.554** × 5, stop `STRUCTURE@772.10 (cat -50%)`.
- **Entry fill quality** — paid 6.5% above the signal minute's low (bar 0.52–0.58).
- **High-water WHILE IN THE TRADE** 0.9 (62.5% vs entry) at 2026-08-12T18:42:00Z UTC · 85 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.9 (62.5%) at 2026-08-12T18:42:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:41:07 | 3 | 0.83 | 49.8% | `tp1` | 0.88 | $15.00 (5.7%) |
  | 14:46:07 | 2 | 0.75 | 35.4% | `trail` | 0.9 | $30.00 (16.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:06:05 | 5 | 0.97 | 0.96 | no | 0.46 | — |
  | 10:07:05 | 5 | 1.02 | 1.01 | no | 0.46 | — |
  | 10:08:06 | 5 | 1.0 | 0.99 | no | 0.46 | — |
  | 10:09:05 | 5 | 0.98 | 0.97 | no | 0.46 | — |
  | 10:10:07 | 5 | 1.06 | 1.05 | no | 0.46 | — |
  | 10:11:06 | 5 | 1.04 | 1.03 | no | 0.46 | — |
  | 10:12:05 | 5 | 1.11 | 1.1 | no | 0.46 | — |
  | 10:13:05 | 5 | 1.03 | 0.98 | no | 0.46 | — |
  | 10:14:05 | 5 | 0.95 | 0.9 | no | 0.46 | — |
  | 10:15:07 | 5 | 1.04 | 1.03 | no | 0.46 | — |
  | 10:16:05 | 5 | 0.93 | 0.88 | no | 0.46 | — |
  | 10:17:05 | 5 | 1.05 | 1.04 | no | 0.46 | — |
  | 10:18:05 | 5 | 1.02 | 0.97 | no | 0.46 | — |
  | 10:19:04 | 5 | 1.14 | 1.13 | no | 0.46 | — |
  | 10:20:07 | 5 | 1.01 | 1.0 | no | 0.46 | — |
  | 10:21:06 | 5 | 0.94 | 0.93 | no | 0.46 | — |
  | 10:22:07 | 5 | 0.94 | 0.93 | no | 0.46 | — |
  | 10:23:06 | 5 | 1.09 | 1.08 | no | 0.46 | — |
  | 10:24:06 | 5 | 1.13 | 1.12 | no | 0.46 | — |
  | 10:25:07 | 5 | 1.24 | 1.19 | no | 0.46 | — |
  | 10:26:05 | 5 | 1.16 | 1.15 | no | 0.46 | — |
  | 10:27:05 | 5 | 1.29 | 1.28 | no | 0.46 | — |
  | 10:28:05 | 5 | 1.25 | 1.24 | no | 0.46 | — |
  | 10:29:05 | 5 | 1.2 | 1.19 | no | 0.46 | — |
  | 10:30:07 | 5 | 1.11 | 1.06 | no | 0.46 | — |
  | 10:31:06 | 5 | 1.08 | 1.07 | no | 0.46 | — |
  | 10:32:06 | 5 | 1.04 | 0.99 | no | 0.46 | — |
  | 10:33:05 | 5 | 0.95 | 0.94 | no | 0.46 | — |
  | 10:34:04 | 5 | 0.99 | 0.98 | no | 0.46 | — |
  | 10:35:06 | 5 | 0.89 | 0.88 | no | 0.46 | — |
  | 10:36:05 | 5 | 0.9 | 0.89 | no | 0.46 | — |
  | 10:37:05 | 5 | 0.87 | 0.86 | no | 0.46 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 772.1) |
  | 12:59:05 | 5 | 0.65 | 0.6 | no | 0.335 | — |
  | 13:00:07 | 5 | 0.67 | 0.66 | no | 0.335 | — |
  | 13:01:05 | 5 | 0.73 | 0.72 | no | 0.335 | — |
  | 13:02:07 | 5 | 0.66 | 0.65 | no | 0.335 | — |
  | 13:03:05 | 5 | 0.71 | 0.66 | no | 0.335 | — |
  | 13:04:05 | 5 | 0.74 | 0.73 | no | 0.335 | — |
  | 13:05:06 | 5 | 0.73 | 0.68 | no | 0.335 | — |
  | 13:06:05 | 5 | 0.73 | 0.72 | no | 0.335 | — |
  | 13:07:06 | 5 | 0.77 | 0.76 | no | 0.335 | — |
  | 13:08:05 | 5 | 0.86 | 0.85 | no | 0.335 | — |
  | 13:09:05 | 5 | 0.82 | 0.81 | no | 0.335 | — |
  | 13:10:07 | 5 | 0.68 | 0.67 | no | 0.335 | — |
  | 13:11:06 | 5 | 0.72 | 0.71 | no | 0.335 | — |
  | 13:12:05 | 5 | 0.65 | 0.64 | no | 0.335 | — |
  | 13:13:05 | 5 | 0.69 | 0.68 | no | 0.335 | — |
  | 13:14:06 | 5 | 0.69 | 0.68 | no | 0.335 | — |
  | 13:15:06 | 5 | 0.68 | 0.63 | no | 0.335 | — |
  | 13:16:06 | 5 | 0.6 | 0.55 | no | 0.335 | — |
  | 13:17:06 | 5 | 0.56 | 0.55 | no | 0.335 | — |
  | 13:18:06 | 5 | 0.52 | 0.51 | no | 0.335 | — |
  | 13:19:05 | 5 | 0.51 | 0.5 | no | 0.335 | — |
  | 13:20:07 | 5 | 0.57 | 0.52 | no | 0.335 | — |
  | 13:21:06 | 5 | 0.56 | 0.51 | no | 0.335 | — |
  | 13:22:06 | 5 | 0.6 | 0.59 | no | 0.335 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 772.89) |
  | 14:18:05 | 5 | 0.54 | 0.53 | no | 0.277 | — |
  | 14:19:05 | 5 | 0.54 | 0.53 | no | 0.277 | — |
  | 14:20:07 | 5 | 0.62 | 0.61 | no | 0.277 | — |
  | 14:21:05 | 5 | 0.54 | 0.53 | no | 0.277 | — |
  | 14:22:06 | 5 | 0.58 | 0.53 | no | 0.277 | — |
  | 14:23:05 | 5 | 0.57 | 0.56 | no | 0.277 | — |
  | 14:24:05 | 5 | 0.61 | 0.56 | no | 0.277 | — |
  | 14:25:06 | 5 | 0.7 | 0.65 | no | 0.277 | — |
  | 14:26:05 | 5 | 0.64 | 0.59 | no | 0.277 | — |
  | 14:27:05 | 5 | 0.64 | 0.59 | no | 0.277 | — |
  | 14:28:05 | 5 | 0.61 | 0.56 | no | 0.277 | — |
  | 14:29:04 | 5 | 0.63 | 0.62 | no | 0.277 | — |
  | 14:30:06 | 5 | 0.57 | 0.56 | no | 0.277 | — |
  | 14:31:05 | 5 | 0.64 | 0.63 | no | 0.277 | — |
  | 14:32:05 | 5 | 0.72 | 0.71 | no | 0.277 | — |
  | 14:33:05 | 5 | 0.74 | 0.73 | no | 0.277 | — |
  | 14:34:05 | 5 | 0.73 | 0.72 | no | 0.277 | — |
  | 14:35:06 | 5 | 0.74 | 0.73 | no | 0.277 | — |
  | 14:36:05 | 5 | 0.78 | 0.77 | no | 0.277 | — |
  | 14:37:05 | 5 | 0.8 | 0.79 | no | 0.277 | — |
  | 14:38:05 | 5 | 0.76 | 0.75 | no | 0.277 | — |
  | 14:39:04 | 5 | 0.79 | 0.74 | no | 0.277 | — |
  | 14:40:06 | 5 | 0.79 | 0.74 | no | 0.277 | — |
  | 14:41:05 | 5 | 0.86 | 0.85 | yes | 0.554 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:42:05 | 2 | 0.88 | 0.87 | yes | 0.748 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:43:04 | 2 | 0.86 | 0.85 | yes | 0.748 | — |
  | 14:44:05 | 2 | 0.85 | 0.84 | yes | 0.748 | — |
  | 14:45:06 | 2 | 0.82 | 0.81 | yes | 0.748 | — |
  | 14:46:05 | 2 | 0.74 | 0.73 | yes | 0.748 | **SELL_ALL 2 `trail`** (runner_stop @ 0.75) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $138.50 (realized $122.00, delta $16.50); oracle $173.00.
- **Parity control** — this trade's own as-placed shape, replayed: $129.80 vs $122.00 realized (gap $7.80 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$122.00** |
  | `all_out_at_tp1_50` | $138.50 |
  | `tp1_30_trail_125` | $80.21 |
  | `trail_only_no_tp1` | $13.00 |
  | `all_out_at_tp1_100` | $-138.50 |
  | `tp1_100_trail_20` | $-138.50 |
  | `tp1_100_trail_10` | $-138.50 |
  | `hold_to_time_stop` | $-138.50 |

### 2026-08-12 · safe-2 · `SPY260812P00772000` · realized $15.00

- **Entry** 11:26:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.79** × 3, stop `STRUCTURE@772.39 (cat -50%)`.
- **Entry fill quality** — paid 1.3% above the signal minute's low (bar 0.78–0.86).
- **High-water WHILE IN THE TRADE** 0.97 (22.8% vs entry) at 2026-08-12T15:32:00Z UTC · 2 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.1 (39.2%) at 2026-08-12T15:34:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:32:04 | 3 | 0.84 | 6.3% | `ribbon_flip` | 0.97 | $39.00 (13.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:27:04 | 3 | 0.92 | 0.91 | no | 0.475 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |
  | 11:32:03 | 3 | 0.86 | 0.85 | no | 0.395 | **SELL_ALL 3 `ribbon_flip`** (ribbon_flip_back) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_30_trail_125` at $64.65 (realized $15.00, delta $49.65); oracle $93.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-118.50 vs $15.00 realized (gap $-133.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$15.00** |
  | `tp1_30_trail_125` | $64.65 |
  | `trail_only_no_tp1` | $45.00 |
  | `all_out_at_tp1_100` | $-118.50 |
  | `all_out_at_tp1_50` | $-118.50 |
  | `tp1_100_trail_20` | $-118.50 |
  | `tp1_100_trail_10` | $-118.50 |
  | `hold_to_time_stop` | $-118.50 |

### 2026-08-13 · safe-2 · `SPY260813C00777000` · realized $332.00

- **Entry** 09:51:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.03** × 3, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 3.0% above the signal minute's low (bar 1.0–1.12).
- **High-water WHILE IN THE TRADE** 2.7 (162.1% vs entry) at 2026-08-13T14:32:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.7 (162.1%) at 2026-08-13T14:32:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:19:04 | 2 | 2.1 | 103.9% | `tp1` | 2.14 | $8.00 (1.9%) |
  | 10:42:05 | 1 | 2.21 | 114.6% | `trail` | 2.7 | $49.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:52:03 | 3 | 1.12 | 1.07 | no | 0.515 | — |
  | 09:53:03 | 3 | 1.05 | 1.0 | no | 0.515 | — |
  | 09:54:03 | 3 | 1.02 | 1.01 | no | 0.515 | — |
  | 09:55:04 | 3 | 1.14 | 1.09 | no | 0.515 | — |
  | 09:56:03 | 3 | 1.09 | 1.04 | no | 0.515 | — |
  | 09:57:03 | 3 | 1.22 | 1.21 | no | 0.515 | — |
  | 09:58:03 | 3 | 1.32 | 1.31 | no | 0.515 | — |
  | 09:59:03 | 3 | 1.43 | 1.42 | no | 0.515 | — |
  | 10:00:05 | 3 | 1.38 | 1.37 | no | 0.515 | — |
  | 10:01:04 | 3 | 1.68 | 1.67 | no | 1.339 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:02:03 | 3 | 1.78 | 1.75 | no | 1.339 | — |
  | 10:03:03 | 3 | 1.92 | 1.86 | no | 1.648 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:04:03 | 3 | 1.78 | 1.73 | no | 1.648 | — |
  | 10:05:04 | 3 | 1.87 | 1.85 | no | 1.648 | — |
  | 10:06:03 | 3 | 1.87 | 1.86 | no | 1.648 | — |
  | 10:07:03 | 3 | 1.82 | 1.75 | no | 1.648 | — |
  | 10:08:03 | 3 | 1.73 | 1.71 | no | 1.648 | — |
  | 10:09:03 | 3 | 1.8 | 1.79 | no | 1.648 | — |
  | 10:10:05 | 3 | 1.85 | 1.78 | no | 1.648 | — |
  | 10:11:04 | 3 | 1.83 | 1.81 | no | 1.648 | — |
  | 10:12:04 | 3 | 1.98 | 1.97 | no | 1.648 | — |
  | 10:13:04 | 3 | 2.02 | 2.0 | no | 1.648 | — |
  | 10:14:04 | 3 | 2.01 | 2.0 | no | 1.648 | — |
  | 10:15:04 | 3 | 1.99 | 1.98 | no | 1.648 | — |
  | 10:16:04 | 3 | 1.93 | 1.92 | no | 1.648 | — |
  | 10:17:04 | 3 | 1.81 | 1.8 | no | 1.648 | — |
  | 10:18:04 | 3 | 1.95 | 1.93 | no | 1.648 | — |
  | 10:19:03 | 3 | 2.15 | 2.1 | yes | 1.03 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:20:04 | 1 | 2.05 | 1.99 | yes | 1.8275 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:21:04 | 1 | 2.05 | 2.03 | yes | 1.8275 | — |
  | 10:22:04 | 1 | 2.3 | 2.29 | yes | 1.955 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:23:04 | 1 | 2.5 | 2.46 | yes | 2.125 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:04 | 1 | 2.55 | 2.53 | yes | 2.1675 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:25:05 | 1 | 2.49 | 2.47 | yes | 2.1675 | — |
  | 10:26:04 | 1 | 2.53 | 2.51 | yes | 2.1675 | — |
  | 10:27:04 | 1 | 2.56 | 2.54 | yes | 2.176 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:28:04 | 1 | 2.48 | 2.46 | yes | 2.176 | — |
  | 10:29:03 | 1 | 2.56 | 2.54 | yes | 2.176 | — |
  | 10:30:05 | 1 | 2.58 | 2.55 | yes | 2.193 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:31:04 | 1 | 2.45 | 2.44 | yes | 2.193 | — |
  | 10:32:04 | 1 | 2.57 | 2.55 | yes | 2.193 | — |
  | 10:33:04 | 1 | 2.65 | 2.62 | yes | 2.2525 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:34:04 | 1 | 2.56 | 2.48 | yes | 2.2525 | — |
  | 10:35:05 | 1 | 2.51 | 2.48 | yes | 2.2525 | — |
  | 10:36:04 | 1 | 2.68 | 2.65 | yes | 2.278 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:37:04 | 1 | 2.61 | 2.59 | yes | 2.278 | — |
  | 10:38:04 | 1 | 2.49 | 2.47 | yes | 2.278 | — |
  | 10:39:05 | 1 | 2.39 | 2.36 | yes | 2.278 | — |
  | 10:40:06 | 1 | 2.46 | 2.44 | yes | 2.278 | — |
  | 10:41:04 | 1 | 2.31 | 2.3 | yes | 2.278 | — |
  | 10:42:04 | 1 | 2.21 | 2.2 | yes | 2.278 | **SELL_ALL 1 `trail`** (runner_stop @ 2.28) |
  | 14:37:04 | 3 | 0.67 | 0.66 | no | 0.33 | — |
  | 14:38:04 | 3 | 0.66 | 0.61 | no | 0.33 | — |
  | 14:39:04 | 3 | 0.68 | 0.63 | no | 0.33 | — |
  | 14:40:05 | 3 | 0.72 | 0.7 | no | 0.33 | — |
  | 14:41:04 | 3 | 0.69 | 0.68 | no | 0.33 | — |
  | 14:42:04 | 3 | 0.92 | 0.91 | no | 0.33 | — |
  | 14:43:04 | 3 | 0.88 | 0.83 | no | 0.33 | — |
  | 14:44:04 | 3 | 0.83 | 0.82 | no | 0.33 | — |
  | 14:45:05 | 3 | 0.9 | 0.84 | no | 0.33 | — |
  | 14:46:04 | 3 | 0.85 | 0.83 | no | 0.33 | — |
  | 14:47:04 | 3 | 0.97 | 0.95 | no | 0.33 | — |
  | 14:48:04 | 3 | 0.98 | 0.92 | no | 0.33 | — |
  | 14:49:04 | 3 | 0.92 | 0.91 | no | 0.33 | — |
  | 14:50:05 | 3 | 0.99 | 0.98 | no | 0.858 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:51:04 | 3 | 1.01 | 0.95 | no | 0.858 | — |
  | 14:52:05 | 3 | 0.99 | 0.93 | no | 0.858 | — |
  | 14:53:04 | 3 | 1.01 | 1.0 | no | 0.858 | — |
  | 14:54:04 | 3 | 1.11 | 1.08 | no | 0.858 | — |
  | 14:55:05 | 3 | 1.05 | 1.04 | no | 0.858 | — |
  | 14:56:04 | 3 | 1.07 | 1.06 | no | 0.858 | — |
  | 14:57:04 | 3 | 1.06 | 1.04 | no | 0.858 | — |
  | 14:58:04 | 3 | 0.97 | 0.96 | no | 0.858 | — |
  | 14:59:04 | 3 | 0.96 | 0.91 | no | 0.858 | — |
  | 15:00:05 | 3 | 0.97 | 0.96 | no | 0.858 | — |
  | 15:01:05 | 3 | 1.04 | 1.03 | no | 0.858 | — |
  | 15:02:04 | 3 | 1.09 | 1.08 | no | 0.858 | — |
  | 15:03:04 | 3 | 1.04 | 1.03 | no | 0.858 | — |
  | 15:04:04 | 3 | 1.1 | 1.09 | no | 0.858 | — |
  | 15:05:05 | 3 | 1.05 | 1.03 | no | 0.858 | — |
  | 15:06:04 | 3 | 1.12 | 1.11 | no | 0.858 | — |
  | 15:07:04 | 3 | 1.29 | 1.24 | no | 1.056 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 15:08:04 | 3 | 1.34 | 1.33 | yes | 0.66 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 15:09:04 | 1 | 1.44 | 1.43 | yes | 1.224 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:10:05 | 1 | 1.45 | 1.44 | yes | 1.2325 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:11:04 | 1 | 1.39 | 1.37 | yes | 1.2325 | — |
  | 15:12:04 | 1 | 1.33 | 1.31 | yes | 1.2325 | — |
  | 15:13:04 | 1 | 1.18 | 1.16 | yes | 1.2325 | **SELL_ALL 1 `trail`** (runner_stop @ 1.23) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_20` at $319.00 (realized $332.00, delta $-13.00); oracle $501.00.
- **Parity control** — this trade's own as-placed shape, replayed: $206.00 vs $332.00 realized (gap $-126.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$332.00** |
  | `tp1_100_trail_20` | $319.00 |
  | `all_out_at_tp1_100` | $309.00 |
  | `tp1_100_trail_10` | $290.20 |
  | `all_out_at_tp1_50` | $154.50 |
  | `tp1_30_trail_125` | $105.80 |
  | `trail_only_no_tp1` | $12.00 |
  | `hold_to_time_stop` | $-154.50 |

### 2026-08-13 · safe-2 · `SPY260813C00777000` · realized $181.00

- **Entry** 09:51:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.66** × 3, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 10.0% above the signal minute's low (bar 0.6–0.68).
- **High-water WHILE IN THE TRADE** 1.5 (127.3% vs entry) at 2026-08-13T19:09:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.5 (127.3%) at 2026-08-13T19:09:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 15:08:05 | 2 | 1.3 | 97.0% | `tp1` | 1.45 | $30.00 (10.3%) |
  | 15:13:05 | 1 | 1.19 | 80.3% | `trail` | 1.5 | $31.00 (20.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:52:03 | 3 | 1.12 | 1.07 | no | 0.515 | — |
  | 09:53:03 | 3 | 1.05 | 1.0 | no | 0.515 | — |
  | 09:54:03 | 3 | 1.02 | 1.01 | no | 0.515 | — |
  | 09:55:04 | 3 | 1.14 | 1.09 | no | 0.515 | — |
  | 09:56:03 | 3 | 1.09 | 1.04 | no | 0.515 | — |
  | 09:57:03 | 3 | 1.22 | 1.21 | no | 0.515 | — |
  | 09:58:03 | 3 | 1.32 | 1.31 | no | 0.515 | — |
  | 09:59:03 | 3 | 1.43 | 1.42 | no | 0.515 | — |
  | 10:00:05 | 3 | 1.38 | 1.37 | no | 0.515 | — |
  | 10:01:04 | 3 | 1.68 | 1.67 | no | 1.339 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:02:03 | 3 | 1.78 | 1.75 | no | 1.339 | — |
  | 10:03:03 | 3 | 1.92 | 1.86 | no | 1.648 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:04:03 | 3 | 1.78 | 1.73 | no | 1.648 | — |
  | 10:05:04 | 3 | 1.87 | 1.85 | no | 1.648 | — |
  | 10:06:03 | 3 | 1.87 | 1.86 | no | 1.648 | — |
  | 10:07:03 | 3 | 1.82 | 1.75 | no | 1.648 | — |
  | 10:08:03 | 3 | 1.73 | 1.71 | no | 1.648 | — |
  | 10:09:03 | 3 | 1.8 | 1.79 | no | 1.648 | — |
  | 10:10:05 | 3 | 1.85 | 1.78 | no | 1.648 | — |
  | 10:11:04 | 3 | 1.83 | 1.81 | no | 1.648 | — |
  | 10:12:04 | 3 | 1.98 | 1.97 | no | 1.648 | — |
  | 10:13:04 | 3 | 2.02 | 2.0 | no | 1.648 | — |
  | 10:14:04 | 3 | 2.01 | 2.0 | no | 1.648 | — |
  | 10:15:04 | 3 | 1.99 | 1.98 | no | 1.648 | — |
  | 10:16:04 | 3 | 1.93 | 1.92 | no | 1.648 | — |
  | 10:17:04 | 3 | 1.81 | 1.8 | no | 1.648 | — |
  | 10:18:04 | 3 | 1.95 | 1.93 | no | 1.648 | — |
  | 10:19:03 | 3 | 2.15 | 2.1 | yes | 1.03 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:20:04 | 1 | 2.05 | 1.99 | yes | 1.8275 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:21:04 | 1 | 2.05 | 2.03 | yes | 1.8275 | — |
  | 10:22:04 | 1 | 2.3 | 2.29 | yes | 1.955 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:23:04 | 1 | 2.5 | 2.46 | yes | 2.125 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:04 | 1 | 2.55 | 2.53 | yes | 2.1675 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:25:05 | 1 | 2.49 | 2.47 | yes | 2.1675 | — |
  | 10:26:04 | 1 | 2.53 | 2.51 | yes | 2.1675 | — |
  | 10:27:04 | 1 | 2.56 | 2.54 | yes | 2.176 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:28:04 | 1 | 2.48 | 2.46 | yes | 2.176 | — |
  | 10:29:03 | 1 | 2.56 | 2.54 | yes | 2.176 | — |
  | 10:30:05 | 1 | 2.58 | 2.55 | yes | 2.193 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:31:04 | 1 | 2.45 | 2.44 | yes | 2.193 | — |
  | 10:32:04 | 1 | 2.57 | 2.55 | yes | 2.193 | — |
  | 10:33:04 | 1 | 2.65 | 2.62 | yes | 2.2525 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:34:04 | 1 | 2.56 | 2.48 | yes | 2.2525 | — |
  | 10:35:05 | 1 | 2.51 | 2.48 | yes | 2.2525 | — |
  | 10:36:04 | 1 | 2.68 | 2.65 | yes | 2.278 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:37:04 | 1 | 2.61 | 2.59 | yes | 2.278 | — |
  | 10:38:04 | 1 | 2.49 | 2.47 | yes | 2.278 | — |
  | 10:39:05 | 1 | 2.39 | 2.36 | yes | 2.278 | — |
  | 10:40:06 | 1 | 2.46 | 2.44 | yes | 2.278 | — |
  | 10:41:04 | 1 | 2.31 | 2.3 | yes | 2.278 | — |
  | 10:42:04 | 1 | 2.21 | 2.2 | yes | 2.278 | **SELL_ALL 1 `trail`** (runner_stop @ 2.28) |
  | 14:37:04 | 3 | 0.67 | 0.66 | no | 0.33 | — |
  | 14:38:04 | 3 | 0.66 | 0.61 | no | 0.33 | — |
  | 14:39:04 | 3 | 0.68 | 0.63 | no | 0.33 | — |
  | 14:40:05 | 3 | 0.72 | 0.7 | no | 0.33 | — |
  | 14:41:04 | 3 | 0.69 | 0.68 | no | 0.33 | — |
  | 14:42:04 | 3 | 0.92 | 0.91 | no | 0.33 | — |
  | 14:43:04 | 3 | 0.88 | 0.83 | no | 0.33 | — |
  | 14:44:04 | 3 | 0.83 | 0.82 | no | 0.33 | — |
  | 14:45:05 | 3 | 0.9 | 0.84 | no | 0.33 | — |
  | 14:46:04 | 3 | 0.85 | 0.83 | no | 0.33 | — |
  | 14:47:04 | 3 | 0.97 | 0.95 | no | 0.33 | — |
  | 14:48:04 | 3 | 0.98 | 0.92 | no | 0.33 | — |
  | 14:49:04 | 3 | 0.92 | 0.91 | no | 0.33 | — |
  | 14:50:05 | 3 | 0.99 | 0.98 | no | 0.858 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:51:04 | 3 | 1.01 | 0.95 | no | 0.858 | — |
  | 14:52:05 | 3 | 0.99 | 0.93 | no | 0.858 | — |
  | 14:53:04 | 3 | 1.01 | 1.0 | no | 0.858 | — |
  | 14:54:04 | 3 | 1.11 | 1.08 | no | 0.858 | — |
  | 14:55:05 | 3 | 1.05 | 1.04 | no | 0.858 | — |
  | 14:56:04 | 3 | 1.07 | 1.06 | no | 0.858 | — |
  | 14:57:04 | 3 | 1.06 | 1.04 | no | 0.858 | — |
  | 14:58:04 | 3 | 0.97 | 0.96 | no | 0.858 | — |
  | 14:59:04 | 3 | 0.96 | 0.91 | no | 0.858 | — |
  | 15:00:05 | 3 | 0.97 | 0.96 | no | 0.858 | — |
  | 15:01:05 | 3 | 1.04 | 1.03 | no | 0.858 | — |
  | 15:02:04 | 3 | 1.09 | 1.08 | no | 0.858 | — |
  | 15:03:04 | 3 | 1.04 | 1.03 | no | 0.858 | — |
  | 15:04:04 | 3 | 1.1 | 1.09 | no | 0.858 | — |
  | 15:05:05 | 3 | 1.05 | 1.03 | no | 0.858 | — |
  | 15:06:04 | 3 | 1.12 | 1.11 | no | 0.858 | — |
  | 15:07:04 | 3 | 1.29 | 1.24 | no | 1.056 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 15:08:04 | 3 | 1.34 | 1.33 | yes | 0.66 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 15:09:04 | 1 | 1.44 | 1.43 | yes | 1.224 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:10:05 | 1 | 1.45 | 1.44 | yes | 1.2325 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:11:04 | 1 | 1.39 | 1.37 | yes | 1.2325 | — |
  | 15:12:04 | 1 | 1.33 | 1.31 | yes | 1.2325 | — |
  | 15:13:04 | 1 | 1.18 | 1.16 | yes | 1.2325 | **SELL_ALL 1 `trail`** (runner_stop @ 1.23) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $198.00 (realized $181.00, delta $17.00); oracle $252.00.
- **Parity control** — this trade's own as-placed shape, replayed: $132.00 vs $181.00 realized (gap $-49.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$181.00** |
  | `all_out_at_tp1_100` | $198.00 |
  | `tp1_100_trail_10` | $196.50 |
  | `tp1_100_trail_20` | $186.00 |
  | `all_out_at_tp1_50` | $99.00 |
  | `trail_only_no_tp1` | $60.00 |
  | `tp1_30_trail_125` | $57.60 |
  | `hold_to_time_stop` | $6.00 |

### 2026-08-13 · bold-2 · `SPY260813C00777000` · realized $534.00

- **Entry** 09:51:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.01** × 5, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 1.0% above the signal minute's low (bar 1.0–1.12).
- **High-water WHILE IN THE TRADE** 2.7 (167.3% vs entry) at 2026-08-13T14:32:00Z UTC · 51 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.7 (167.3%) at 2026-08-13T14:32:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:12:06 | 3 | 1.99 | 97.0% | `tp1` | 2.07 | $24.00 (3.9%) |
  | 10:42:08 | 2 | 2.21 | 118.8% | `trail` | 2.7 | $98.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:52:05 | 5 | 1.12 | 1.1 | no | 0.505 | — |
  | 09:53:05 | 5 | 1.01 | 1.0 | no | 0.505 | — |
  | 09:54:05 | 5 | 1.05 | 1.04 | no | 0.505 | — |
  | 09:55:05 | 5 | 1.09 | 1.08 | no | 0.505 | — |
  | 09:56:06 | 5 | 1.06 | 1.05 | no | 0.505 | — |
  | 09:57:05 | 5 | 1.22 | 1.21 | no | 0.505 | — |
  | 09:58:05 | 5 | 1.31 | 1.3 | no | 0.505 | — |
  | 09:59:04 | 5 | 1.47 | 1.46 | no | 0.505 | — |
  | 10:00:06 | 5 | 1.42 | 1.41 | no | 0.505 | — |
  | 10:01:06 | 5 | 1.69 | 1.68 | no | 1.313 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:02:05 | 5 | 1.77 | 1.76 | no | 1.616 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:03:05 | 5 | 1.92 | 1.91 | no | 1.616 | — |
  | 10:04:05 | 5 | 1.78 | 1.73 | no | 1.616 | — |
  | 10:05:05 | 5 | 1.92 | 1.86 | no | 1.616 | — |
  | 10:06:04 | 5 | 1.86 | 1.84 | no | 1.616 | — |
  | 10:07:04 | 5 | 1.78 | 1.77 | no | 1.616 | — |
  | 10:08:04 | 5 | 1.72 | 1.71 | no | 1.616 | — |
  | 10:09:05 | 5 | 1.84 | 1.83 | no | 1.616 | — |
  | 10:10:06 | 5 | 1.8 | 1.78 | no | 1.616 | — |
  | 10:11:05 | 5 | 1.83 | 1.81 | no | 1.616 | — |
  | 10:12:05 | 5 | 2.03 | 2.02 | yes | 1.01 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:13:05 | 2 | 2.0 | 1.98 | yes | 1.7255 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:14:05 | 2 | 2.02 | 2.0 | yes | 1.7255 | — |
  | 10:15:06 | 2 | 2.04 | 1.96 | yes | 1.734 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:16:05 | 2 | 2.02 | 1.98 | yes | 1.734 | — |
  | 10:17:05 | 2 | 1.86 | 1.84 | yes | 1.734 | — |
  | 10:18:05 | 2 | 1.94 | 1.91 | yes | 1.734 | — |
  | 10:19:05 | 2 | 2.16 | 2.06 | yes | 1.836 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:20:06 | 2 | 2.0 | 1.97 | yes | 1.836 | — |
  | 10:21:05 | 2 | 2.1 | 2.03 | yes | 1.836 | — |
  | 10:22:05 | 2 | 2.29 | 2.27 | yes | 1.9465 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:23:06 | 2 | 2.48 | 2.44 | yes | 2.108 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:06 | 2 | 2.57 | 2.53 | yes | 2.1845 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:25:06 | 2 | 2.5 | 2.48 | yes | 2.1845 | — |
  | 10:26:07 | 2 | 2.51 | 2.48 | yes | 2.1845 | — |
  | 10:27:07 | 2 | 2.53 | 2.47 | yes | 2.1845 | — |
  | 10:28:06 | 2 | 2.46 | 2.43 | yes | 2.1845 | — |
  | 10:29:05 | 2 | 2.57 | 2.54 | yes | 2.1845 | — |
  | 10:30:07 | 2 | 2.54 | 2.47 | yes | 2.1845 | — |
  | 10:31:06 | 2 | 2.47 | 2.39 | yes | 2.1845 | — |
  | 10:32:06 | 2 | 2.62 | 2.54 | yes | 2.227 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:33:05 | 2 | 2.61 | 2.6 | yes | 2.227 | — |
  | 10:34:06 | 2 | 2.52 | 2.51 | yes | 2.227 | — |
  | 10:35:07 | 2 | 2.57 | 2.51 | yes | 2.227 | — |
  | 10:36:06 | 2 | 2.58 | 2.56 | yes | 2.227 | — |
  | 10:37:06 | 2 | 2.58 | 2.55 | yes | 2.227 | — |
  | 10:38:06 | 2 | 2.52 | 2.49 | yes | 2.227 | — |
  | 10:39:06 | 2 | 2.36 | 2.33 | yes | 2.227 | — |
  | 10:40:08 | 2 | 2.5 | 2.43 | yes | 2.227 | — |
  | 10:41:06 | 2 | 2.29 | 2.28 | yes | 2.227 | — |
  | 10:42:06 | 2 | 2.25 | 2.2 | yes | 2.227 | **SELL_ALL 2 `trail`** (runner_stop @ 2.23) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_20` at $533.00 (realized $534.00, delta $-1.00); oracle $845.00.
- **Parity control** — this trade's own as-placed shape, replayed: $303.00 vs $534.00 realized (gap $-231.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$534.00** |
  | `tp1_100_trail_20` | $533.00 |
  | `all_out_at_tp1_100` | $505.00 |
  | `tp1_100_trail_10` | $475.40 |
  | `all_out_at_tp1_50` | $252.50 |
  | `tp1_30_trail_125` | $149.70 |
  | `trail_only_no_tp1` | $30.00 |
  | `hold_to_time_stop` | $-252.50 |

### 2026-08-13 · safe-3 · `SPY260813C00777000` · realized $348.00

- **Entry** 09:52:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **776.85**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 777 (trigger 776.85, offset 0.15), quoted premium 1.08, filled **1.09** × 3, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 12.4% above the signal minute's low (bar 0.97–1.12).
- **High-water WHILE IN THE TRADE** 2.7 (147.7% vs entry) at 2026-08-13T14:32:00Z UTC · 87 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.7 (147.7%) at 2026-08-13T14:32:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:22:08 | 1 | 2.27 | 108.3% | `trail` | 2.4 | $13.00 (5.4%) |
  | 10:22:08 | 1 | 2.27 | 108.3% | `trail` | 2.4 | $13.00 (5.4%) |
  | 10:42:09 | 1 | 2.21 | 102.8% | `trail` | 2.7 | $49.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:53:05 | 3 | 1.01 | 1.0 | no | 0.545 | — |
  | 09:54:05 | 3 | 1.02 | 1.01 | no | 0.545 | — |
  | 09:55:06 | 3 | 1.13 | 1.08 | no | 0.545 | — |
  | 09:56:05 | 3 | 1.06 | 1.05 | no | 0.545 | — |
  | 09:57:05 | 3 | 1.22 | 1.21 | no | 0.545 | — |
  | 09:58:05 | 3 | 1.31 | 1.3 | no | 0.545 | — |
  | 09:59:05 | 3 | 1.47 | 1.42 | no | 0.545 | — |
  | 10:00:07 | 3 | 1.37 | 1.36 | no | 0.545 | — |
  | 10:01:06 | 3 | 1.69 | 1.68 | no | 1.417 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:02:05 | 3 | 1.77 | 1.76 | no | 1.417 | — |
  | 10:03:05 | 3 | 1.86 | 1.85 | no | 1.417 | — |
  | 10:04:05 | 3 | 1.78 | 1.77 | no | 1.417 | — |
  | 10:05:06 | 3 | 1.86 | 1.85 | no | 1.417 | — |
  | 10:06:04 | 3 | 1.86 | 1.84 | no | 1.417 | — |
  | 10:07:04 | 3 | 1.78 | 1.77 | no | 1.417 | — |
  | 10:08:04 | 3 | 1.72 | 1.71 | no | 1.417 | — |
  | 10:09:04 | 3 | 1.84 | 1.79 | no | 1.417 | — |
  | 10:10:08 | 3 | 1.81 | 1.79 | no | 1.417 | — |
  | 10:11:05 | 3 | 1.83 | 1.81 | no | 1.417 | — |
  | 10:12:06 | 3 | 2.05 | 2.02 | no | 1.744 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:13:06 | 3 | 2.03 | 1.95 | no | 1.744 | — |
  | 10:14:06 | 3 | 2.01 | 2.0 | no | 1.744 | — |
  | 10:15:07 | 3 | 2.02 | 2.0 | no | 1.744 | — |
  | 10:16:06 | 3 | 2.0 | 1.94 | no | 1.744 | — |
  | 10:17:06 | 3 | 1.85 | 1.84 | no | 1.744 | — |
  | 10:18:05 | 3 | 1.94 | 1.91 | no | 1.744 | — |
  | 10:19:05 | 3 | 2.14 | 2.12 | no | 1.744 | — |
  | 10:20:07 | 3 | 2.0 | 1.98 | no | 1.744 | — |
  | 10:21:06 | 3 | 2.06 | 2.02 | no | 1.744 | — |
  | 10:22:06 | 3 | 2.26 | 2.24 | yes | 1.09 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:23:06 | 1 | 2.47 | 2.39 | yes | 2.0995 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:07 | 1 | 2.49 | 2.46 | yes | 2.1165 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:25:07 | 1 | 2.42 | 2.4 | yes | 2.1165 | — |
  | 10:26:06 | 1 | 2.45 | 2.43 | yes | 2.1165 | — |
  | 10:27:07 | 1 | 2.53 | 2.47 | yes | 2.1505 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:28:06 | 1 | 2.47 | 2.45 | yes | 2.1505 | — |
  | 10:29:05 | 1 | 2.61 | 2.58 | yes | 2.2185 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:30:08 | 1 | 2.48 | 2.43 | yes | 2.2185 | — |
  | 10:31:06 | 1 | 2.47 | 2.39 | yes | 2.2185 | — |
  | 10:32:07 | 1 | 2.64 | 2.6 | yes | 2.244 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:33:06 | 1 | 2.59 | 2.57 | yes | 2.244 | — |
  | 10:34:06 | 1 | 2.55 | 2.52 | yes | 2.244 | — |
  | 10:35:07 | 1 | 2.57 | 2.51 | yes | 2.244 | — |
  | 10:36:07 | 1 | 2.59 | 2.57 | yes | 2.244 | — |
  | 10:37:07 | 1 | 2.57 | 2.54 | yes | 2.244 | — |
  | 10:38:07 | 1 | 2.53 | 2.5 | yes | 2.244 | — |
  | 10:39:06 | 1 | 2.36 | 2.33 | yes | 2.244 | — |
  | 10:40:09 | 1 | 2.42 | 2.41 | yes | 2.244 | — |
  | 10:41:07 | 1 | 2.37 | 2.34 | yes | 2.244 | — |
  | 10:42:07 | 1 | 2.25 | 2.23 | yes | 2.244 | **SELL_ALL 1 `trail`** (runner_stop @ 2.24) |
  | 14:38:06 | 3 | 0.62 | 0.61 | no | 0.325 | — |
  | 14:39:07 | 3 | 0.69 | 0.68 | no | 0.325 | — |
  | 14:40:08 | 3 | 0.74 | 0.73 | no | 0.325 | — |
  | 14:41:07 | 3 | 0.73 | 0.72 | no | 0.325 | — |
  | 14:42:08 | 3 | 0.92 | 0.91 | no | 0.325 | — |
  | 14:43:06 | 3 | 0.85 | 0.84 | no | 0.325 | — |
  | 14:44:07 | 3 | 0.89 | 0.84 | no | 0.325 | — |
  | 14:45:09 | 3 | 0.94 | 0.93 | no | 0.325 | — |
  | 14:46:07 | 3 | 0.87 | 0.85 | no | 0.325 | — |
  | 14:47:07 | 3 | 0.96 | 0.91 | no | 0.325 | — |
  | 14:48:07 | 3 | 0.94 | 0.93 | no | 0.325 | — |
  | 14:49:08 | 3 | 0.94 | 0.92 | no | 0.325 | — |
  | 14:50:09 | 3 | 0.97 | 0.95 | no | 0.325 | — |
  | 14:51:07 | 3 | 0.97 | 0.95 | no | 0.325 | — |
  | 14:52:08 | 3 | 0.97 | 0.96 | no | 0.325 | — |
  | 14:53:07 | 3 | 1.03 | 1.02 | no | 0.845 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:54:07 | 3 | 1.1 | 1.09 | no | 0.845 | — |
  | 14:55:08 | 3 | 1.1 | 1.05 | no | 0.845 | — |
  | 14:56:07 | 3 | 1.07 | 1.06 | no | 0.845 | — |
  | 14:57:07 | 3 | 1.01 | 1.0 | no | 0.845 | — |
  | 14:58:07 | 3 | 0.99 | 0.97 | no | 0.845 | — |
  | 14:59:07 | 3 | 0.93 | 0.91 | no | 0.845 | — |
  | 15:00:09 | 3 | 0.97 | 0.95 | no | 0.845 | — |
  | 15:01:08 | 3 | 1.05 | 1.04 | no | 0.845 | — |
  | 15:02:08 | 3 | 1.07 | 1.06 | no | 0.845 | — |
  | 15:03:06 | 3 | 1.06 | 1.0 | no | 0.845 | — |
  | 15:04:07 | 3 | 1.06 | 1.05 | no | 0.845 | — |
  | 15:05:08 | 3 | 1.04 | 1.02 | no | 0.845 | — |
  | 15:06:07 | 3 | 1.18 | 1.17 | no | 1.04 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 15:07:07 | 3 | 1.27 | 1.26 | no | 1.04 | — |
  | 15:08:07 | 3 | 1.28 | 1.27 | no | 1.04 | — |
  | 15:09:07 | 3 | 1.42 | 1.41 | yes | 0.65 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 15:10:08 | 1 | 1.41 | 1.4 | yes | 1.207 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:11:08 | 1 | 1.38 | 1.32 | yes | 1.207 | — |
  | 15:12:07 | 1 | 1.37 | 1.35 | yes | 1.207 | — |
  | 15:13:07 | 1 | 1.23 | 1.21 | yes | 1.207 | — |
  | 15:14:07 | 1 | 1.06 | 1.04 | yes | 1.207 | **SELL_ALL 1 `trail`** (runner_stop @ 1.21) |

- **This trade's variant grid** — best was `tp1_100_trail_10` at $352.00 (realized $348.00, delta $4.00); oracle $483.00.
- **Parity control** — this trade's own as-placed shape, replayed: $345.25 vs $348.00 realized (gap $-2.75 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$348.00** |
  | `tp1_100_trail_10` | $352.00 |
  | `all_out_at_tp1_100` | $327.00 |
  | `tp1_100_trail_20` | $325.00 |
  | `all_out_at_tp1_50` | $163.50 |
  | `tp1_30_trail_125` | $103.40 |
  | `trail_only_no_tp1` | $15.00 |
  | `hold_to_time_stop` | $-163.50 |

### 2026-08-13 · safe-3 · `SPY260813C00777000` · realized $199.00

- **Entry** 09:52:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **776.85**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 777 (trigger 776.85, offset 0.15), quoted premium 1.08, filled **0.65** × 3, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 6.6% above the signal minute's low (bar 0.61–0.66).
- **High-water WHILE IN THE TRADE** 1.5 (130.8% vs entry) at 2026-08-13T19:09:00Z UTC · 87 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.5 (130.8%) at 2026-08-13T19:09:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 15:09:09 | 2 | 1.44 | 121.5% | `tp1` | 1.5 | $12.00 (4.0%) |
  | 15:14:08 | 1 | 1.06 | 63.1% | `trail` | 1.5 | $44.00 (29.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:53:05 | 3 | 1.01 | 1.0 | no | 0.545 | — |
  | 09:54:05 | 3 | 1.02 | 1.01 | no | 0.545 | — |
  | 09:55:06 | 3 | 1.13 | 1.08 | no | 0.545 | — |
  | 09:56:05 | 3 | 1.06 | 1.05 | no | 0.545 | — |
  | 09:57:05 | 3 | 1.22 | 1.21 | no | 0.545 | — |
  | 09:58:05 | 3 | 1.31 | 1.3 | no | 0.545 | — |
  | 09:59:05 | 3 | 1.47 | 1.42 | no | 0.545 | — |
  | 10:00:07 | 3 | 1.37 | 1.36 | no | 0.545 | — |
  | 10:01:06 | 3 | 1.69 | 1.68 | no | 1.417 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:02:05 | 3 | 1.77 | 1.76 | no | 1.417 | — |
  | 10:03:05 | 3 | 1.86 | 1.85 | no | 1.417 | — |
  | 10:04:05 | 3 | 1.78 | 1.77 | no | 1.417 | — |
  | 10:05:06 | 3 | 1.86 | 1.85 | no | 1.417 | — |
  | 10:06:04 | 3 | 1.86 | 1.84 | no | 1.417 | — |
  | 10:07:04 | 3 | 1.78 | 1.77 | no | 1.417 | — |
  | 10:08:04 | 3 | 1.72 | 1.71 | no | 1.417 | — |
  | 10:09:04 | 3 | 1.84 | 1.79 | no | 1.417 | — |
  | 10:10:08 | 3 | 1.81 | 1.79 | no | 1.417 | — |
  | 10:11:05 | 3 | 1.83 | 1.81 | no | 1.417 | — |
  | 10:12:06 | 3 | 2.05 | 2.02 | no | 1.744 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:13:06 | 3 | 2.03 | 1.95 | no | 1.744 | — |
  | 10:14:06 | 3 | 2.01 | 2.0 | no | 1.744 | — |
  | 10:15:07 | 3 | 2.02 | 2.0 | no | 1.744 | — |
  | 10:16:06 | 3 | 2.0 | 1.94 | no | 1.744 | — |
  | 10:17:06 | 3 | 1.85 | 1.84 | no | 1.744 | — |
  | 10:18:05 | 3 | 1.94 | 1.91 | no | 1.744 | — |
  | 10:19:05 | 3 | 2.14 | 2.12 | no | 1.744 | — |
  | 10:20:07 | 3 | 2.0 | 1.98 | no | 1.744 | — |
  | 10:21:06 | 3 | 2.06 | 2.02 | no | 1.744 | — |
  | 10:22:06 | 3 | 2.26 | 2.24 | yes | 1.09 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:23:06 | 1 | 2.47 | 2.39 | yes | 2.0995 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:07 | 1 | 2.49 | 2.46 | yes | 2.1165 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:25:07 | 1 | 2.42 | 2.4 | yes | 2.1165 | — |
  | 10:26:06 | 1 | 2.45 | 2.43 | yes | 2.1165 | — |
  | 10:27:07 | 1 | 2.53 | 2.47 | yes | 2.1505 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:28:06 | 1 | 2.47 | 2.45 | yes | 2.1505 | — |
  | 10:29:05 | 1 | 2.61 | 2.58 | yes | 2.2185 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:30:08 | 1 | 2.48 | 2.43 | yes | 2.2185 | — |
  | 10:31:06 | 1 | 2.47 | 2.39 | yes | 2.2185 | — |
  | 10:32:07 | 1 | 2.64 | 2.6 | yes | 2.244 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:33:06 | 1 | 2.59 | 2.57 | yes | 2.244 | — |
  | 10:34:06 | 1 | 2.55 | 2.52 | yes | 2.244 | — |
  | 10:35:07 | 1 | 2.57 | 2.51 | yes | 2.244 | — |
  | 10:36:07 | 1 | 2.59 | 2.57 | yes | 2.244 | — |
  | 10:37:07 | 1 | 2.57 | 2.54 | yes | 2.244 | — |
  | 10:38:07 | 1 | 2.53 | 2.5 | yes | 2.244 | — |
  | 10:39:06 | 1 | 2.36 | 2.33 | yes | 2.244 | — |
  | 10:40:09 | 1 | 2.42 | 2.41 | yes | 2.244 | — |
  | 10:41:07 | 1 | 2.37 | 2.34 | yes | 2.244 | — |
  | 10:42:07 | 1 | 2.25 | 2.23 | yes | 2.244 | **SELL_ALL 1 `trail`** (runner_stop @ 2.24) |
  | 14:38:06 | 3 | 0.62 | 0.61 | no | 0.325 | — |
  | 14:39:07 | 3 | 0.69 | 0.68 | no | 0.325 | — |
  | 14:40:08 | 3 | 0.74 | 0.73 | no | 0.325 | — |
  | 14:41:07 | 3 | 0.73 | 0.72 | no | 0.325 | — |
  | 14:42:08 | 3 | 0.92 | 0.91 | no | 0.325 | — |
  | 14:43:06 | 3 | 0.85 | 0.84 | no | 0.325 | — |
  | 14:44:07 | 3 | 0.89 | 0.84 | no | 0.325 | — |
  | 14:45:09 | 3 | 0.94 | 0.93 | no | 0.325 | — |
  | 14:46:07 | 3 | 0.87 | 0.85 | no | 0.325 | — |
  | 14:47:07 | 3 | 0.96 | 0.91 | no | 0.325 | — |
  | 14:48:07 | 3 | 0.94 | 0.93 | no | 0.325 | — |
  | 14:49:08 | 3 | 0.94 | 0.92 | no | 0.325 | — |
  | 14:50:09 | 3 | 0.97 | 0.95 | no | 0.325 | — |
  | 14:51:07 | 3 | 0.97 | 0.95 | no | 0.325 | — |
  | 14:52:08 | 3 | 0.97 | 0.96 | no | 0.325 | — |
  | 14:53:07 | 3 | 1.03 | 1.02 | no | 0.845 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:54:07 | 3 | 1.1 | 1.09 | no | 0.845 | — |
  | 14:55:08 | 3 | 1.1 | 1.05 | no | 0.845 | — |
  | 14:56:07 | 3 | 1.07 | 1.06 | no | 0.845 | — |
  | 14:57:07 | 3 | 1.01 | 1.0 | no | 0.845 | — |
  | 14:58:07 | 3 | 0.99 | 0.97 | no | 0.845 | — |
  | 14:59:07 | 3 | 0.93 | 0.91 | no | 0.845 | — |
  | 15:00:09 | 3 | 0.97 | 0.95 | no | 0.845 | — |
  | 15:01:08 | 3 | 1.05 | 1.04 | no | 0.845 | — |
  | 15:02:08 | 3 | 1.07 | 1.06 | no | 0.845 | — |
  | 15:03:06 | 3 | 1.06 | 1.0 | no | 0.845 | — |
  | 15:04:07 | 3 | 1.06 | 1.05 | no | 0.845 | — |
  | 15:05:08 | 3 | 1.04 | 1.02 | no | 0.845 | — |
  | 15:06:07 | 3 | 1.18 | 1.17 | no | 1.04 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 15:07:07 | 3 | 1.27 | 1.26 | no | 1.04 | — |
  | 15:08:07 | 3 | 1.28 | 1.27 | no | 1.04 | — |
  | 15:09:07 | 3 | 1.42 | 1.41 | yes | 0.65 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 15:10:08 | 1 | 1.41 | 1.4 | yes | 1.207 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 15:11:08 | 1 | 1.38 | 1.32 | yes | 1.207 | — |
  | 15:12:07 | 1 | 1.37 | 1.35 | yes | 1.207 | — |
  | 15:13:07 | 1 | 1.23 | 1.21 | yes | 1.207 | — |
  | 15:14:07 | 1 | 1.06 | 1.04 | yes | 1.207 | **SELL_ALL 1 `trail`** (runner_stop @ 1.21) |

- **Tags:** `runner_underperformed_tp1`, `runner_material_giveback`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $195.50 (realized $199.00, delta $-3.50); oracle $255.00.
- **Parity control** — this trade's own as-placed shape, replayed: $196.25 vs $199.00 realized (gap $-2.75 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$199.00** |
  | `tp1_100_trail_10` | $195.50 |
  | `all_out_at_tp1_100` | $195.00 |
  | `tp1_100_trail_20` | $185.00 |
  | `all_out_at_tp1_50` | $97.50 |
  | `tp1_30_trail_125` | $58.00 |
  | `trail_only_no_tp1` | $9.00 |
  | `hold_to_time_stop` | $9.00 |

### 2026-08-13 · risky-1 · `SPY260813C00777000` · realized $405.00

- **Entry** 09:52:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **776.85**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 777 (trigger 776.85, offset 0.15), quoted premium 1.08, filled **1.08** × 5, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 11.3% above the signal minute's low (bar 0.97–1.12).
- **High-water WHILE IN THE TRADE** 2.7 (150.0% vs entry) at 2026-08-13T14:32:00Z UTC · 72 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.7 (150.0%) at 2026-08-13T14:32:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:01:08 | 1 | 1.67 | 54.6% | `?` | 1.71 | $4.00 (2.3%) |
  | 10:01:08 | 2 | 1.68 | 55.6% | `trail` | 1.71 | $6.00 (1.8%) |
  | 10:42:10 | 2 | 2.21 | 104.6% | `trail` | 2.7 | $98.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:53:05 | 5 | 1.0 | 0.99 | no | 0.54 | — |
  | 09:54:05 | 5 | 1.07 | 1.02 | no | 0.54 | — |
  | 09:55:06 | 5 | 1.13 | 1.12 | no | 0.54 | — |
  | 09:56:05 | 5 | 1.06 | 1.05 | no | 0.54 | — |
  | 09:57:05 | 5 | 1.23 | 1.22 | no | 0.54 | — |
  | 09:58:05 | 5 | 1.31 | 1.3 | no | 0.54 | — |
  | 09:59:05 | 5 | 1.47 | 1.46 | no | 0.54 | — |
  | 10:00:07 | 5 | 1.42 | 1.41 | no | 0.54 | — |
  | 10:01:06 | 5 | 1.69 | 1.63 | yes | 1.08 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:02:05 | 2 | 1.79 | 1.73 | yes | 1.5215 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:03:05 | 2 | 1.92 | 1.9 | yes | 1.632 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:04:05 | 2 | 1.75 | 1.73 | yes | 1.632 | — |
  | 10:05:06 | 2 | 1.92 | 1.91 | yes | 1.632 | — |
  | 10:06:04 | 2 | 1.85 | 1.83 | yes | 1.632 | — |
  | 10:07:04 | 2 | 1.82 | 1.8 | yes | 1.632 | — |
  | 10:08:04 | 2 | 1.77 | 1.71 | yes | 1.632 | — |
  | 10:09:04 | 2 | 1.84 | 1.83 | yes | 1.632 | — |
  | 10:10:08 | 2 | 1.85 | 1.84 | yes | 1.632 | — |
  | 10:11:05 | 2 | 1.83 | 1.82 | yes | 1.632 | — |
  | 10:12:06 | 2 | 2.03 | 2.01 | yes | 1.7255 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:13:06 | 2 | 2.01 | 2.0 | yes | 1.7255 | — |
  | 10:14:06 | 2 | 2.06 | 2.04 | yes | 1.751 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:15:07 | 2 | 1.98 | 1.96 | yes | 1.751 | — |
  | 10:16:06 | 2 | 2.0 | 1.98 | yes | 1.751 | — |
  | 10:17:06 | 2 | 1.86 | 1.84 | yes | 1.751 | — |
  | 10:18:05 | 2 | 1.93 | 1.91 | yes | 1.751 | — |
  | 10:19:05 | 2 | 2.16 | 2.14 | yes | 1.836 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:20:07 | 2 | 2.02 | 2.0 | yes | 1.836 | — |
  | 10:21:06 | 2 | 2.11 | 2.04 | yes | 1.836 | — |
  | 10:22:06 | 2 | 2.31 | 2.29 | yes | 1.9635 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:23:06 | 2 | 2.49 | 2.47 | yes | 2.1165 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:07 | 2 | 2.47 | 2.43 | yes | 2.1165 | — |
  | 10:25:07 | 2 | 2.5 | 2.46 | yes | 2.125 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:26:06 | 2 | 2.45 | 2.43 | yes | 2.125 | — |
  | 10:27:07 | 2 | 2.49 | 2.45 | yes | 2.125 | — |
  | 10:28:06 | 2 | 2.49 | 2.46 | yes | 2.125 | — |
  | 10:29:05 | 2 | 2.61 | 2.53 | yes | 2.2185 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:30:08 | 2 | 2.53 | 2.51 | yes | 2.2185 | — |
  | 10:31:06 | 2 | 2.44 | 2.39 | yes | 2.2185 | — |
  | 10:32:07 | 2 | 2.65 | 2.61 | yes | 2.2525 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:33:06 | 2 | 2.62 | 2.57 | yes | 2.2525 | — |
  | 10:34:06 | 2 | 2.55 | 2.52 | yes | 2.2525 | — |
  | 10:35:07 | 2 | 2.57 | 2.54 | yes | 2.2525 | — |
  | 10:36:07 | 2 | 2.58 | 2.57 | yes | 2.2525 | — |
  | 10:37:07 | 2 | 2.57 | 2.54 | yes | 2.2525 | — |
  | 10:38:07 | 2 | 2.5 | 2.43 | yes | 2.2525 | — |
  | 10:39:06 | 2 | 2.41 | 2.4 | yes | 2.2525 | — |
  | 10:40:09 | 2 | 2.49 | 2.48 | yes | 2.2525 | — |
  | 10:41:07 | 2 | 2.35 | 2.33 | yes | 2.2525 | — |
  | 10:42:07 | 2 | 2.25 | 2.24 | yes | 2.2525 | **SELL_ALL 2 `trail`** (runner_stop @ 2.25) |
  | 14:38:06 | 5 | 0.67 | 0.66 | no | 0.325 | — |
  | 14:39:07 | 5 | 0.69 | 0.64 | no | 0.325 | — |
  | 14:40:08 | 5 | 0.74 | 0.69 | no | 0.325 | — |
  | 14:41:07 | 5 | 0.73 | 0.72 | no | 0.325 | — |
  | 14:42:08 | 5 | 0.96 | 0.94 | no | 0.325 | — |
  | 14:43:06 | 5 | 0.89 | 0.88 | no | 0.325 | — |
  | 14:44:07 | 5 | 0.89 | 0.84 | no | 0.325 | — |
  | 14:45:09 | 5 | 0.93 | 0.91 | no | 0.325 | — |
  | 14:46:07 | 5 | 0.87 | 0.86 | no | 0.325 | — |
  | 14:47:07 | 5 | 0.96 | 0.91 | no | 0.325 | — |
  | 14:48:07 | 5 | 0.94 | 0.93 | no | 0.325 | — |
  | 14:49:08 | 5 | 0.92 | 0.87 | no | 0.325 | — |
  | 14:50:09 | 5 | 0.96 | 0.91 | no | 0.325 | — |
  | 14:51:07 | 5 | 1.0 | 0.95 | yes | 0.65 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:52:08 | 2 | 0.98 | 0.96 | yes | 0.85 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:53:07 | 2 | 1.03 | 1.01 | yes | 0.8755 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:54:07 | 2 | 1.1 | 1.05 | yes | 0.935 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:55:08 | 2 | 1.09 | 1.08 | yes | 0.935 | — |
  | 14:56:07 | 2 | 1.03 | 1.02 | yes | 0.935 | — |
  | 14:57:07 | 2 | 1.05 | 1.04 | yes | 0.935 | — |
  | 14:58:07 | 2 | 0.99 | 0.98 | yes | 0.935 | — |
  | 14:59:07 | 2 | 0.93 | 0.91 | yes | 0.935 | **SELL_ALL 2 `trail`** (runner_stop @ 0.94) |

- **This trade's variant grid** — best was `tp1_100_trail_10` at $594.00 (realized $405.00, delta $189.00); oracle $810.00.
- **Parity control** — this trade's own as-placed shape, replayed: $296.00 vs $405.00 realized (gap $-109.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$405.00** |
  | `tp1_100_trail_10` | $594.00 |
  | `all_out_at_tp1_100` | $540.00 |
  | `tp1_100_trail_20` | $540.00 |
  | `all_out_at_tp1_50` | $270.00 |
  | `tp1_30_trail_125` | $168.60 |
  | `trail_only_no_tp1` | $30.00 |
  | `hold_to_time_stop` | $-270.00 |

### 2026-08-13 · risky-1 · `SPY260813C00777000` · realized $152.00

- **Entry** 09:52:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **776.85**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 777 (trigger 776.85, offset 0.15), quoted premium 1.08, filled **0.65** × 5, stop `STRUCTURE@776.85 (cat -50%)`.
- **Entry fill quality** — paid 6.6% above the signal minute's low (bar 0.61–0.66).
- **High-water WHILE IN THE TRADE** 1.1 (69.2% vs entry) at 2026-08-13T18:54:00Z UTC · 72 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.5 (130.8%) at 2026-08-13T19:09:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:51:09 | 3 | 0.97 | 49.2% | `tp1` | 1.02 | $15.00 (4.9%) |
  | 14:59:10 | 2 | 0.93 | 43.1% | `trail` | 1.1 | $34.00 (15.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:53:05 | 5 | 1.0 | 0.99 | no | 0.54 | — |
  | 09:54:05 | 5 | 1.07 | 1.02 | no | 0.54 | — |
  | 09:55:06 | 5 | 1.13 | 1.12 | no | 0.54 | — |
  | 09:56:05 | 5 | 1.06 | 1.05 | no | 0.54 | — |
  | 09:57:05 | 5 | 1.23 | 1.22 | no | 0.54 | — |
  | 09:58:05 | 5 | 1.31 | 1.3 | no | 0.54 | — |
  | 09:59:05 | 5 | 1.47 | 1.46 | no | 0.54 | — |
  | 10:00:07 | 5 | 1.42 | 1.41 | no | 0.54 | — |
  | 10:01:06 | 5 | 1.69 | 1.63 | yes | 1.08 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:02:05 | 2 | 1.79 | 1.73 | yes | 1.5215 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:03:05 | 2 | 1.92 | 1.9 | yes | 1.632 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:04:05 | 2 | 1.75 | 1.73 | yes | 1.632 | — |
  | 10:05:06 | 2 | 1.92 | 1.91 | yes | 1.632 | — |
  | 10:06:04 | 2 | 1.85 | 1.83 | yes | 1.632 | — |
  | 10:07:04 | 2 | 1.82 | 1.8 | yes | 1.632 | — |
  | 10:08:04 | 2 | 1.77 | 1.71 | yes | 1.632 | — |
  | 10:09:04 | 2 | 1.84 | 1.83 | yes | 1.632 | — |
  | 10:10:08 | 2 | 1.85 | 1.84 | yes | 1.632 | — |
  | 10:11:05 | 2 | 1.83 | 1.82 | yes | 1.632 | — |
  | 10:12:06 | 2 | 2.03 | 2.01 | yes | 1.7255 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:13:06 | 2 | 2.01 | 2.0 | yes | 1.7255 | — |
  | 10:14:06 | 2 | 2.06 | 2.04 | yes | 1.751 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:15:07 | 2 | 1.98 | 1.96 | yes | 1.751 | — |
  | 10:16:06 | 2 | 2.0 | 1.98 | yes | 1.751 | — |
  | 10:17:06 | 2 | 1.86 | 1.84 | yes | 1.751 | — |
  | 10:18:05 | 2 | 1.93 | 1.91 | yes | 1.751 | — |
  | 10:19:05 | 2 | 2.16 | 2.14 | yes | 1.836 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:20:07 | 2 | 2.02 | 2.0 | yes | 1.836 | — |
  | 10:21:06 | 2 | 2.11 | 2.04 | yes | 1.836 | — |
  | 10:22:06 | 2 | 2.31 | 2.29 | yes | 1.9635 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:23:06 | 2 | 2.49 | 2.47 | yes | 2.1165 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:24:07 | 2 | 2.47 | 2.43 | yes | 2.1165 | — |
  | 10:25:07 | 2 | 2.5 | 2.46 | yes | 2.125 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:26:06 | 2 | 2.45 | 2.43 | yes | 2.125 | — |
  | 10:27:07 | 2 | 2.49 | 2.45 | yes | 2.125 | — |
  | 10:28:06 | 2 | 2.49 | 2.46 | yes | 2.125 | — |
  | 10:29:05 | 2 | 2.61 | 2.53 | yes | 2.2185 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:30:08 | 2 | 2.53 | 2.51 | yes | 2.2185 | — |
  | 10:31:06 | 2 | 2.44 | 2.39 | yes | 2.2185 | — |
  | 10:32:07 | 2 | 2.65 | 2.61 | yes | 2.2525 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:33:06 | 2 | 2.62 | 2.57 | yes | 2.2525 | — |
  | 10:34:06 | 2 | 2.55 | 2.52 | yes | 2.2525 | — |
  | 10:35:07 | 2 | 2.57 | 2.54 | yes | 2.2525 | — |
  | 10:36:07 | 2 | 2.58 | 2.57 | yes | 2.2525 | — |
  | 10:37:07 | 2 | 2.57 | 2.54 | yes | 2.2525 | — |
  | 10:38:07 | 2 | 2.5 | 2.43 | yes | 2.2525 | — |
  | 10:39:06 | 2 | 2.41 | 2.4 | yes | 2.2525 | — |
  | 10:40:09 | 2 | 2.49 | 2.48 | yes | 2.2525 | — |
  | 10:41:07 | 2 | 2.35 | 2.33 | yes | 2.2525 | — |
  | 10:42:07 | 2 | 2.25 | 2.24 | yes | 2.2525 | **SELL_ALL 2 `trail`** (runner_stop @ 2.25) |
  | 14:38:06 | 5 | 0.67 | 0.66 | no | 0.325 | — |
  | 14:39:07 | 5 | 0.69 | 0.64 | no | 0.325 | — |
  | 14:40:08 | 5 | 0.74 | 0.69 | no | 0.325 | — |
  | 14:41:07 | 5 | 0.73 | 0.72 | no | 0.325 | — |
  | 14:42:08 | 5 | 0.96 | 0.94 | no | 0.325 | — |
  | 14:43:06 | 5 | 0.89 | 0.88 | no | 0.325 | — |
  | 14:44:07 | 5 | 0.89 | 0.84 | no | 0.325 | — |
  | 14:45:09 | 5 | 0.93 | 0.91 | no | 0.325 | — |
  | 14:46:07 | 5 | 0.87 | 0.86 | no | 0.325 | — |
  | 14:47:07 | 5 | 0.96 | 0.91 | no | 0.325 | — |
  | 14:48:07 | 5 | 0.94 | 0.93 | no | 0.325 | — |
  | 14:49:08 | 5 | 0.92 | 0.87 | no | 0.325 | — |
  | 14:50:09 | 5 | 0.96 | 0.91 | no | 0.325 | — |
  | 14:51:07 | 5 | 1.0 | 0.95 | yes | 0.65 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:52:08 | 2 | 0.98 | 0.96 | yes | 0.85 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:53:07 | 2 | 1.03 | 1.01 | yes | 0.8755 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:54:07 | 2 | 1.1 | 1.05 | yes | 0.935 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:55:08 | 2 | 1.09 | 1.08 | yes | 0.935 | — |
  | 14:56:07 | 2 | 1.03 | 1.02 | yes | 0.935 | — |
  | 14:57:07 | 2 | 1.05 | 1.04 | yes | 0.935 | — |
  | 14:58:07 | 2 | 0.99 | 0.98 | yes | 0.935 | — |
  | 14:59:07 | 2 | 0.93 | 0.91 | yes | 0.935 | **SELL_ALL 2 `trail`** (runner_stop @ 0.94) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $326.00 (realized $152.00, delta $174.00); oracle $425.00.
- **Parity control** — this trade's own as-placed shape, replayed: $146.00 vs $152.00 realized (gap $-6.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$152.00** |
  | `tp1_100_trail_10` | $326.00 |
  | `all_out_at_tp1_100` | $325.00 |
  | `tp1_100_trail_20` | $305.00 |
  | `all_out_at_tp1_50` | $162.50 |
  | `tp1_30_trail_125` | $97.00 |
  | `trail_only_no_tp1` | $15.00 |
  | `hold_to_time_stop` | $15.00 |

### 2026-08-13 · risky-3 · `SPY260813C00779000` · realized $366.00

- **Entry** 09:52:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **776.85**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 779 (trigger 776.85, offset 2.15), quoted premium 0.35, filled **0.36** × 10, stop `0.28 (-20%)`.
- **Entry fill quality** — paid 16.1% above the signal minute's low (bar 0.31–0.37).
- **High-water WHILE IN THE TRADE** 0.78 (116.7% vs entry) at 2026-08-13T14:02:00Z UTC · 12 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.23 (241.7%) at 2026-08-13T14:32:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:03:09 | 6 | 0.75 | 108.3% | `tp1` | 0.78 | $18.00 (3.9%) |
  | 10:04:09 | 4 | 0.69 | 91.7% | `trail` | 0.78 | $36.00 (11.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:53:05 | 10 | 0.31 | 0.3 | no | 0.288 | — |
  | 09:54:05 | 10 | 0.36 | 0.31 | no | 0.288 | — |
  | 09:55:06 | 10 | 0.38 | 0.37 | no | 0.288 | — |
  | 09:56:05 | 10 | 0.37 | 0.32 | no | 0.288 | — |
  | 09:57:05 | 10 | 0.44 | 0.39 | no | 0.288 | — |
  | 09:58:05 | 10 | 0.46 | 0.41 | no | 0.288 | — |
  | 09:59:05 | 10 | 0.53 | 0.48 | no | 0.288 | — |
  | 10:00:07 | 10 | 0.49 | 0.48 | no | 0.288 | — |
  | 10:01:06 | 10 | 0.67 | 0.66 | no | 0.576 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:02:05 | 10 | 0.7 | 0.69 | no | 0.576 | — |
  | 10:03:05 | 10 | 0.79 | 0.74 | yes | 0.36 | **SELL_PARTIAL 6 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:04:05 | 4 | 0.72 | 0.67 | yes | 0.6715 | **SELL_ALL 4 `trail`** (runner_stop @ 0.67) |

- **Tags:** `runner_underperformed_tp1`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $360.00 (realized $366.00, delta $-6.00); oracle $870.00.
- **Parity control** — this trade's own as-placed shape, replayed: $345.00 vs $366.00 realized (gap $-21.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$366.00** |
  | `all_out_at_tp1_100` | $360.00 |
  | `tp1_100_trail_10` | $352.80 |
  | `tp1_100_trail_20` | $337.60 |
  | `all_out_at_tp1_50` | $180.00 |
  | `tp1_30_trail_125` | $126.40 |
  | `trail_only_no_tp1` | $10.00 |
  | `hold_to_time_stop` | $-180.00 |

### 2026-08-17 · bold-2 · `SPY260817P00775000` · realized $360.00

- **Entry** 13:06:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.72** × 5, stop `STRUCTURE@775.09 (cat -50%)`.
- **Entry fill quality** — paid 9.1% above the signal minute's low (bar 0.66–0.73).
- **High-water WHILE IN THE TRADE** 1.63 (126.4% vs entry) at 2026-08-17T17:27:00Z UTC · 27 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.51 (248.6%) at 2026-08-17T20:00:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:26:04 | 3 | 1.5 | 108.3% | `tp1` | 1.58 | $24.00 (5.1%) |
  | 13:33:04 | 2 | 1.35 | 87.5% | `trail` | 1.63 | $56.00 (17.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:07:04 | 5 | 0.75 | 0.7 | no | 0.36 | — |
  | 13:08:04 | 5 | 0.75 | 0.74 | no | 0.36 | — |
  | 13:09:05 | 5 | 0.74 | 0.73 | no | 0.36 | — |
  | 13:10:04 | 5 | 0.75 | 0.74 | no | 0.36 | — |
  | 13:11:04 | 5 | 0.75 | 0.7 | no | 0.36 | — |
  | 13:12:04 | 5 | 0.65 | 0.64 | no | 0.36 | — |
  | 13:13:03 | 5 | 0.77 | 0.76 | no | 0.36 | — |
  | 13:14:04 | 5 | 0.76 | 0.75 | no | 0.36 | — |
  | 13:15:04 | 5 | 0.93 | 0.92 | no | 0.36 | — |
  | 13:16:04 | 5 | 0.92 | 0.91 | no | 0.36 | — |
  | 13:17:04 | 5 | 0.95 | 0.9 | no | 0.36 | — |
  | 13:18:04 | 5 | 0.89 | 0.87 | no | 0.36 | — |
  | 13:19:04 | 5 | 0.96 | 0.93 | no | 0.36 | — |
  | 13:20:04 | 5 | 0.99 | 0.98 | no | 0.36 | — |
  | 13:21:04 | 5 | 1.02 | 1.01 | no | 0.36 | — |
  | 13:22:03 | 5 | 1.11 | 1.09 | no | 0.936 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:23:04 | 5 | 1.14 | 1.12 | no | 0.936 | — |
  | 13:24:04 | 5 | 1.4 | 1.35 | no | 1.152 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:25:04 | 5 | 1.43 | 1.38 | no | 1.152 | — |
  | 13:26:04 | 5 | 1.55 | 1.48 | yes | 0.72 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:27:04 | 2 | 1.5 | 1.43 | yes | 1.3175 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:28:04 | 2 | 1.5 | 1.47 | yes | 1.3175 | — |
  | 13:29:04 | 2 | 1.6 | 1.54 | yes | 1.36 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:30:04 | 2 | 1.51 | 1.48 | yes | 1.36 | — |
  | 13:31:03 | 2 | 1.52 | 1.51 | yes | 1.36 | — |
  | 13:32:04 | 2 | 1.57 | 1.5 | yes | 1.36 | — |
  | 13:33:04 | 2 | 1.39 | 1.32 | yes | 1.36 | **SELL_ALL 2 `trail`** (runner_stop @ 1.36) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `hold_to_time_stop` at $675.00 (realized $360.00, delta $315.00); oracle $895.00.
- **Parity control** — this trade's own as-placed shape, replayed: $486.00 vs $360.00 realized (gap $126.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$360.00** |
  | `hold_to_time_stop` | $675.00 |
  | `all_out_at_tp1_100` | $360.00 |
  | `tp1_100_trail_10` | $351.00 |
  | `tp1_100_trail_20` | $332.80 |
  | `all_out_at_tp1_50` | $180.00 |
  | `tp1_30_trail_125` | $99.28 |
  | `trail_only_no_tp1` | $-20.00 |

### 2026-08-18 · safe-2 · `SPY260818P00768000` · realized $82.00

- **Entry** 14:36:03 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.31** × 3, stop `STRUCTURE@768.52 (cat -50%)`.
- **Entry fill quality** — paid 3.3% above the signal minute's low (bar 0.3–0.32).
- **High-water WHILE IN THE TRADE** 0.63 (103.2% vs entry) at 2026-08-18T19:00:00Z UTC · 25 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.05 (238.7%) at 2026-08-18T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 15:00:04 | 2 | 0.61 | 96.8% | `tp1` | 0.63 | $4.00 (3.2%) |
  | 15:01:04 | 1 | 0.53 | 71.0% | `trail` | 0.63 | $10.00 (15.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:37:03 | 3 | 0.3 | 0.29 | no | 0.155 | — |
  | 14:38:03 | 3 | 0.28 | 0.27 | no | 0.155 | — |
  | 14:39:03 | 3 | 0.32 | 0.31 | no | 0.155 | — |
  | 14:40:03 | 3 | 0.29 | 0.28 | no | 0.155 | — |
  | 14:41:03 | 3 | 0.38 | 0.33 | no | 0.155 | — |
  | 14:42:03 | 3 | 0.37 | 0.36 | no | 0.155 | — |
  | 14:43:03 | 3 | 0.36 | 0.31 | no | 0.155 | — |
  | 14:44:03 | 3 | 0.36 | 0.35 | no | 0.155 | — |
  | 14:45:03 | 3 | 0.41 | 0.4 | no | 0.155 | — |
  | 14:46:03 | 3 | 0.4 | 0.39 | no | 0.155 | — |
  | 14:47:03 | 3 | 0.42 | 0.41 | no | 0.155 | — |
  | 14:48:03 | 3 | 0.38 | 0.33 | no | 0.155 | — |
  | 14:49:03 | 3 | 0.4 | 0.39 | no | 0.155 | — |
  | 14:50:03 | 3 | 0.38 | 0.37 | no | 0.155 | — |
  | 14:51:03 | 3 | 0.45 | 0.44 | no | 0.155 | — |
  | 14:52:03 | 3 | 0.45 | 0.44 | no | 0.155 | — |
  | 14:53:03 | 3 | 0.51 | 0.5 | no | 0.403 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:54:03 | 3 | 0.45 | 0.44 | no | 0.403 | — |
  | 14:55:03 | 3 | 0.55 | 0.54 | no | 0.496 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:56:03 | 3 | 0.51 | 0.5 | no | 0.496 | — |
  | 14:57:03 | 3 | 0.54 | 0.53 | no | 0.496 | — |
  | 14:58:03 | 3 | 0.52 | 0.51 | no | 0.496 | — |
  | 14:59:03 | 3 | 0.59 | 0.54 | no | 0.496 | — |
  | 15:00:03 | 3 | 0.62 | 0.57 | yes | 0.31 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 15:01:03 | 1 | 0.52 | 0.51 | yes | 0.527 | **SELL_ALL 1 `trail`** (runner_stop @ 0.53) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $93.00 (realized $82.00, delta $11.00); oracle $222.00.
- **Parity control** — this trade's own as-placed shape, replayed: $62.00 vs $82.00 realized (gap $-20.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$82.00** |
  | `all_out_at_tp1_100` | $93.00 |
  | `tp1_100_trail_10` | $87.70 |
  | `tp1_100_trail_20` | $81.40 |
  | `all_out_at_tp1_50` | $46.50 |
  | `tp1_30_trail_125` | $23.47 |
  | `hold_to_time_stop` | $9.00 |
  | `trail_only_no_tp1` | $6.00 |

### 2026-08-18 · bold-2 · `SPY260818P00768000` · realized $80.00

- **Entry** 14:40:05 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.31** × 5, stop `STRUCTURE@768.52 (cat -50%)`.
- **Entry fill quality** — paid 3.3% above the signal minute's low (bar 0.3–0.35).
- **High-water WHILE IN THE TRADE** 0.63 (103.2% vs entry) at 2026-08-18T19:00:00Z UTC · 23 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.05 (238.7%) at 2026-08-18T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 15:03:05 | 5 | 0.47 | 51.6% | `premium_stop` | 0.63 | $80.00 (25.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:41:05 | 5 | 0.38 | 0.37 | no | 0.155 | — |
  | 14:42:05 | 5 | 0.36 | 0.35 | no | 0.155 | — |
  | 14:43:05 | 5 | 0.36 | 0.31 | no | 0.155 | — |
  | 14:44:04 | 5 | 0.37 | 0.36 | no | 0.155 | — |
  | 14:45:04 | 5 | 0.37 | 0.36 | no | 0.155 | — |
  | 14:46:05 | 5 | 0.4 | 0.35 | no | 0.155 | — |
  | 14:47:05 | 5 | 0.39 | 0.38 | no | 0.155 | — |
  | 14:48:05 | 5 | 0.38 | 0.37 | no | 0.155 | — |
  | 14:49:05 | 5 | 0.36 | 0.35 | no | 0.155 | — |
  | 14:50:05 | 5 | 0.42 | 0.41 | no | 0.155 | — |
  | 14:51:04 | 5 | 0.41 | 0.4 | no | 0.155 | — |
  | 14:52:04 | 5 | 0.41 | 0.4 | no | 0.155 | — |
  | 14:53:04 | 5 | 0.46 | 0.45 | no | 0.155 | — |
  | 14:54:04 | 5 | 0.45 | 0.44 | no | 0.155 | — |
  | 14:55:04 | 5 | 0.55 | 0.54 | no | 0.496 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:56:04 | 5 | 0.56 | 0.54 | no | 0.496 | — |
  | 14:57:04 | 5 | 0.54 | 0.53 | no | 0.496 | — |
  | 14:58:04 | 5 | 0.56 | 0.51 | no | 0.496 | — |
  | 14:59:04 | 5 | 0.58 | 0.53 | no | 0.496 | — |
  | 15:00:05 | 5 | 0.58 | 0.57 | no | 0.496 | — |
  | 15:01:04 | 5 | 0.56 | 0.55 | no | 0.496 | — |
  | 15:02:04 | 5 | 0.53 | 0.52 | no | 0.496 | — |
  | 15:03:04 | 5 | 0.46 | 0.45 | no | 0.496 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.5) |

- **Tags:** `runner_material_giveback`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $155.00 (realized $80.00, delta $75.00); oracle $370.00.
- **Parity control** — this trade's own as-placed shape, replayed: $93.00 vs $80.00 realized (gap $13.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$80.00** |
  | `all_out_at_tp1_100` | $155.00 |
  | `tp1_100_trail_10` | $144.40 |
  | `tp1_100_trail_20` | $131.80 |
  | `all_out_at_tp1_50` | $77.50 |
  | `tp1_30_trail_125` | $42.07 |
  | `trail_only_no_tp1` | $20.00 |
  | `hold_to_time_stop` | $15.00 |

### 2026-08-19 · safe-3 · `SPY260819C00771000` · realized $3.00

- **Entry** 10:42:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **770.85**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 771 (trigger 770.85, offset 0.15), quoted premium 1.04, filled **0.54** × 3, stop `STRUCTURE@770.85 (cat -50%)`.
- **Entry fill quality** — paid 1.9% above the signal minute's low (bar 0.53–0.59).
- **High-water WHILE IN THE TRADE** 0.66 (22.2% vs entry) at 2026-08-19T16:39:00Z UTC · 15 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.66 (22.2%) at 2026-08-19T16:39:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:42:06 | 3 | 0.55 | 1.8% | `structure_stop` | 0.66 | $33.00 (16.7%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:43:04 | 3 | 1.1 | 1.05 | no | 0.525 | — |
  | 10:44:04 | 3 | 1.04 | 1.03 | no | 0.525 | — |
  | 10:45:05 | 3 | 1.06 | 1.01 | no | 0.525 | — |
  | 10:46:05 | 3 | 1.14 | 1.13 | no | 0.525 | — |
  | 10:47:05 | 3 | 1.11 | 1.1 | no | 0.525 | — |
  | 10:48:05 | 3 | 1.04 | 1.03 | no | 0.525 | — |
  | 10:49:04 | 3 | 1.0 | 0.95 | no | 0.525 | — |
  | 10:50:06 | 3 | 0.89 | 0.88 | no | 0.525 | — |
  | 10:51:05 | 3 | 0.94 | 0.93 | no | 0.525 | — |
  | 10:52:05 | 3 | 1.0 | 0.99 | no | 0.525 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 770.85) |
  | 12:38:05 | 3 | 0.59 | 0.54 | no | 0.27 | — |
  | 12:39:04 | 3 | 0.61 | 0.6 | no | 0.27 | — |
  | 12:40:06 | 3 | 0.62 | 0.61 | no | 0.27 | — |
  | 12:41:04 | 3 | 0.57 | 0.56 | no | 0.27 | — |
  | 12:42:05 | 3 | 0.58 | 0.57 | no | 0.27 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 770.59) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $3.00 (realized $3.00, delta $0.00); oracle $36.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-81.00 vs $3.00 realized (gap $-84.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$3.00** |
  | `trail_only_no_tp1` | $3.00 |
  | `all_out_at_tp1_100` | $-81.00 |
  | `all_out_at_tp1_50` | $-81.00 |
  | `tp1_30_trail_125` | $-81.00 |
  | `tp1_100_trail_20` | $-81.00 |
  | `tp1_100_trail_10` | $-81.00 |
  | `hold_to_time_stop` | $-81.00 |

### 2026-08-19 · bold-2 · `SPY260819C00770000` · realized $195.00

- **Entry** 11:49:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.38** × 5, stop `STRUCTURE@770.10 (cat -50%)`.
- **Entry fill quality** — paid 24.3% above the signal minute's low (bar 1.11–1.41).
- **High-water WHILE IN THE TRADE** 2.19 (58.7% vs entry) at 2026-08-19T16:19:00Z UTC · 34 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.19 (58.7%) at 2026-08-19T16:19:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:23:05 | 5 | 1.77 | 28.3% | `premium_stop` | 2.19 | $210.00 (19.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:50:04 | 5 | 1.1 | 1.09 | no | 0.69 | — |
  | 11:51:04 | 5 | 1.18 | 1.17 | no | 0.69 | — |
  | 11:52:04 | 5 | 1.14 | 1.13 | no | 0.69 | — |
  | 11:53:04 | 5 | 1.13 | 1.11 | no | 0.69 | — |
  | 11:54:04 | 5 | 1.06 | 1.01 | no | 0.69 | — |
  | 11:55:07 | 5 | 0.98 | 0.97 | no | 0.69 | — |
  | 11:56:04 | 5 | 1.03 | 1.02 | no | 0.69 | — |
  | 11:57:04 | 5 | 1.02 | 0.97 | no | 0.69 | — |
  | 11:58:04 | 5 | 1.0 | 0.99 | no | 0.69 | — |
  | 11:59:04 | 5 | 1.15 | 1.14 | no | 0.69 | — |
  | 12:00:04 | 5 | 1.19 | 1.18 | no | 0.69 | — |
  | 12:01:04 | 5 | 1.32 | 1.31 | no | 0.69 | — |
  | 12:02:04 | 5 | 1.42 | 1.37 | no | 0.69 | — |
  | 12:03:04 | 5 | 1.57 | 1.51 | no | 0.69 | — |
  | 12:04:03 | 5 | 1.59 | 1.57 | no | 0.69 | — |
  | 12:05:04 | 5 | 1.71 | 1.65 | no | 0.69 | — |
  | 12:06:04 | 5 | 1.73 | 1.71 | no | 0.69 | — |
  | 12:07:04 | 5 | 1.68 | 1.66 | no | 0.69 | — |
  | 12:08:04 | 5 | 1.89 | 1.83 | no | 0.69 | — |
  | 12:09:04 | 5 | 1.77 | 1.7 | no | 0.69 | — |
  | 12:10:04 | 5 | 1.78 | 1.76 | no | 0.69 | — |
  | 12:11:04 | 5 | 1.88 | 1.85 | no | 0.69 | — |
  | 12:12:04 | 5 | 1.81 | 1.79 | no | 0.69 | — |
  | 12:13:04 | 5 | 1.89 | 1.87 | no | 0.69 | — |
  | 12:14:04 | 5 | 1.83 | 1.82 | no | 0.69 | — |
  | 12:15:04 | 5 | 1.84 | 1.82 | no | 0.69 | — |
  | 12:16:04 | 5 | 2.04 | 2.02 | no | 0.69 | — |
  | 12:17:04 | 5 | 2.1 | 2.08 | no | 1.794 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:18:04 | 5 | 2.05 | 2.02 | no | 1.794 | — |
  | 12:19:04 | 5 | 2.19 | 2.13 | no | 1.794 | — |
  | 12:20:04 | 5 | 2.08 | 2.06 | no | 1.794 | — |
  | 12:21:04 | 5 | 2.01 | 1.95 | no | 1.794 | — |
  | 12:22:04 | 5 | 1.87 | 1.84 | no | 1.794 | — |
  | 12:23:04 | 5 | 1.76 | 1.74 | no | 1.794 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 1.79) |

- **This trade's variant grid** — best was `all_out_at_tp1_50` at $345.00 (realized $195.00, delta $150.00); oracle $405.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-345.00 vs $195.00 realized (gap $-540.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$195.00** |
  | `all_out_at_tp1_50` | $345.00 |
  | `tp1_30_trail_125` | $202.60 |
  | `trail_only_no_tp1` | $50.00 |
  | `all_out_at_tp1_100` | $-345.00 |
  | `tp1_100_trail_20` | $-345.00 |
  | `tp1_100_trail_10` | $-345.00 |
  | `hold_to_time_stop` | $-345.00 |

### 2026-08-19 · safe-3 · `SPY260819C00770000` · realized $207.00

- **Entry** 11:50:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **770.1**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 770 (trigger 770.1, offset -0.1), quoted premium 1.15, filled **1.14** × 3, stop `STRUCTURE@770.10 (cat -50%)`.
- **Entry fill quality** — paid 7.5% above the signal minute's low (bar 1.06–1.21).
- **High-water WHILE IN THE TRADE** 2.19 (92.1% vs entry) at 2026-08-19T16:19:00Z UTC · 32 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.19 (92.1%) at 2026-08-19T16:19:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:22:06 | 3 | 1.83 | 60.5% | `premium_stop` | 2.19 | $108.00 (16.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:51:04 | 3 | 1.18 | 1.17 | no | 0.57 | — |
  | 11:52:05 | 3 | 1.13 | 1.12 | no | 0.57 | — |
  | 11:53:04 | 3 | 1.13 | 1.11 | no | 0.57 | — |
  | 11:54:05 | 3 | 1.05 | 1.0 | no | 0.57 | — |
  | 11:55:08 | 3 | 0.94 | 0.93 | no | 0.57 | — |
  | 11:56:05 | 3 | 1.04 | 1.02 | no | 0.57 | — |
  | 11:57:05 | 3 | 1.02 | 1.01 | no | 0.57 | — |
  | 11:58:05 | 3 | 0.96 | 0.95 | no | 0.57 | — |
  | 11:59:05 | 3 | 1.15 | 1.1 | no | 0.57 | — |
  | 12:00:05 | 3 | 1.22 | 1.2 | no | 0.57 | — |
  | 12:01:05 | 3 | 1.31 | 1.3 | no | 0.57 | — |
  | 12:02:05 | 3 | 1.42 | 1.41 | no | 0.57 | — |
  | 12:03:04 | 3 | 1.57 | 1.51 | no | 0.57 | — |
  | 12:04:05 | 3 | 1.56 | 1.54 | no | 0.57 | — |
  | 12:05:06 | 3 | 1.63 | 1.62 | no | 0.57 | — |
  | 12:06:05 | 3 | 1.72 | 1.7 | no | 1.482 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:07:05 | 3 | 1.67 | 1.65 | no | 1.482 | — |
  | 12:08:05 | 3 | 1.88 | 1.85 | no | 1.482 | — |
  | 12:09:05 | 3 | 1.76 | 1.7 | no | 1.482 | — |
  | 12:10:06 | 3 | 1.8 | 1.77 | no | 1.482 | — |
  | 12:11:04 | 3 | 1.88 | 1.85 | no | 1.482 | — |
  | 12:12:05 | 3 | 1.87 | 1.79 | no | 1.482 | — |
  | 12:13:05 | 3 | 1.94 | 1.92 | no | 1.482 | — |
  | 12:14:05 | 3 | 1.8 | 1.77 | no | 1.482 | — |
  | 12:15:06 | 3 | 1.85 | 1.78 | no | 1.482 | — |
  | 12:16:05 | 3 | 2.0 | 1.94 | no | 1.824 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:17:04 | 3 | 2.1 | 2.08 | no | 1.824 | — |
  | 12:18:05 | 3 | 2.05 | 2.04 | no | 1.824 | — |
  | 12:19:04 | 3 | 2.19 | 2.13 | no | 1.824 | — |
  | 12:20:06 | 3 | 2.09 | 2.06 | no | 1.824 | — |
  | 12:21:05 | 3 | 1.95 | 1.94 | no | 1.824 | — |
  | 12:22:05 | 3 | 1.83 | 1.79 | no | 1.824 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 1.82) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $171.00 (realized $207.00, delta $-36.00); oracle $315.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-171.00 vs $207.00 realized (gap $-378.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$207.00** |
  | `all_out_at_tp1_50` | $171.00 |
  | `tp1_30_trail_125` | $115.40 |
  | `trail_only_no_tp1` | $15.00 |
  | `all_out_at_tp1_100` | $-171.00 |
  | `tp1_100_trail_20` | $-171.00 |
  | `tp1_100_trail_10` | $-171.00 |
  | `hold_to_time_stop` | $-171.00 |

### 2026-08-19 · risky-1 · `SPY260819C00770000` · realized $299.00

- **Entry** 11:50:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **770.1**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 770 (trigger 770.1, offset -0.1), quoted premium 1.1, filled **1.12** × 5, stop `STRUCTURE@770.10 (cat -50%)`.
- **Entry fill quality** — paid 5.7% above the signal minute's low (bar 1.06–1.21).
- **High-water WHILE IN THE TRADE** 2.19 (95.5% vs entry) at 2026-08-19T16:19:00Z UTC · 32 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.19 (95.5%) at 2026-08-19T16:19:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:05:08 | 3 | 1.65 | 47.3% | `tp1` | 1.69 | $12.00 (2.4%) |
  | 12:22:07 | 2 | 1.82 | 62.5% | `trail` | 2.19 | $74.00 (16.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:51:04 | 5 | 1.18 | 1.17 | no | 0.56 | — |
  | 11:52:05 | 5 | 1.1 | 1.08 | no | 0.56 | — |
  | 11:53:04 | 5 | 1.12 | 1.11 | no | 0.56 | — |
  | 11:54:05 | 5 | 1.04 | 0.99 | no | 0.56 | — |
  | 11:55:08 | 5 | 0.92 | 0.91 | no | 0.56 | — |
  | 11:56:05 | 5 | 1.03 | 1.02 | no | 0.56 | — |
  | 11:57:05 | 5 | 0.98 | 0.97 | no | 0.56 | — |
  | 11:58:05 | 5 | 0.99 | 0.98 | no | 0.56 | — |
  | 11:59:05 | 5 | 1.15 | 1.1 | no | 0.56 | — |
  | 12:00:05 | 5 | 1.21 | 1.19 | no | 0.56 | — |
  | 12:01:05 | 5 | 1.34 | 1.32 | no | 0.56 | — |
  | 12:02:05 | 5 | 1.46 | 1.44 | no | 0.56 | — |
  | 12:03:04 | 5 | 1.57 | 1.55 | no | 0.56 | — |
  | 12:04:05 | 5 | 1.6 | 1.59 | no | 0.56 | — |
  | 12:05:06 | 5 | 1.69 | 1.64 | yes | 1.12 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:06:05 | 2 | 1.71 | 1.68 | yes | 1.4535 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:07:05 | 2 | 1.62 | 1.61 | yes | 1.4535 | — |
  | 12:08:05 | 2 | 1.85 | 1.84 | yes | 1.5725 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:09:05 | 2 | 1.75 | 1.73 | yes | 1.5725 | — |
  | 12:10:06 | 2 | 1.83 | 1.81 | yes | 1.5725 | — |
  | 12:11:04 | 2 | 1.92 | 1.85 | yes | 1.632 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:12:05 | 2 | 1.82 | 1.79 | yes | 1.632 | — |
  | 12:13:05 | 2 | 1.93 | 1.91 | yes | 1.6405 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:14:05 | 2 | 1.88 | 1.85 | yes | 1.6405 | — |
  | 12:15:06 | 2 | 1.84 | 1.83 | yes | 1.6405 | — |
  | 12:16:05 | 2 | 2.01 | 1.98 | yes | 1.7085 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:17:04 | 2 | 2.1 | 2.02 | yes | 1.785 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:18:05 | 2 | 2.05 | 2.03 | yes | 1.785 | — |
  | 12:19:04 | 2 | 2.2 | 2.13 | yes | 1.87 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:20:06 | 2 | 2.1 | 2.08 | yes | 1.87 | — |
  | 12:21:05 | 2 | 2.0 | 1.97 | yes | 1.87 | — |
  | 12:22:05 | 2 | 1.83 | 1.81 | yes | 1.87 | **SELL_ALL 2 `trail`** (runner_stop @ 1.87) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $280.00 (realized $299.00, delta $-19.00); oracle $535.00.
- **Parity control** — this trade's own as-placed shape, replayed: $266.00 vs $299.00 realized (gap $-33.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$299.00** |
  | `all_out_at_tp1_50` | $280.00 |
  | `tp1_30_trail_125` | $183.40 |
  | `trail_only_no_tp1` | $-10.00 |
  | `all_out_at_tp1_100` | $-280.00 |
  | `tp1_100_trail_20` | $-280.00 |
  | `tp1_100_trail_10` | $-280.00 |
  | `hold_to_time_stop` | $-280.00 |

### 2026-08-20 · safe-2 · `SPY260820P00766000` · realized $191.00

- **Entry** 12:56:03 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.7** × 3, stop `STRUCTURE@766.63 (cat -50%)`.
- **Entry fill quality** — paid 7.7% above the signal minute's low (bar 0.65–0.73).
- **High-water WHILE IN THE TRADE** 1.48 (111.4% vs entry) at 2026-08-20T17:20:00Z UTC · 26 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 3.81 (444.3%) at 2026-08-20T19:58:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:20:05 | 1 | 1.39 | 98.6% | `trail` | 1.48 | $9.00 (6.1%) |
  | 13:20:05 | 1 | 1.39 | 98.6% | `trail` | 1.48 | $9.00 (6.1%) |
  | 13:22:04 | 1 | 1.23 | 75.7% | `trail` | 1.48 | $25.00 (16.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 12:57:03 | 3 | 0.71 | 0.66 | no | 0.35 | — |
  | 12:58:03 | 3 | 0.66 | 0.65 | no | 0.35 | — |
  | 12:59:03 | 3 | 0.65 | 0.6 | no | 0.35 | — |
  | 13:00:04 | 3 | 0.59 | 0.54 | no | 0.35 | — |
  | 13:01:03 | 3 | 0.64 | 0.63 | no | 0.35 | — |
  | 13:02:03 | 3 | 0.73 | 0.68 | no | 0.35 | — |
  | 13:03:03 | 3 | 0.69 | 0.68 | no | 0.35 | — |
  | 13:04:03 | 3 | 0.68 | 0.67 | no | 0.35 | — |
  | 13:05:04 | 3 | 0.69 | 0.68 | no | 0.35 | — |
  | 13:06:03 | 3 | 0.76 | 0.75 | no | 0.35 | — |
  | 13:07:03 | 3 | 0.85 | 0.8 | no | 0.35 | — |
  | 13:08:03 | 3 | 0.87 | 0.86 | no | 0.35 | — |
  | 13:09:03 | 3 | 0.87 | 0.86 | no | 0.35 | — |
  | 13:10:04 | 3 | 0.87 | 0.86 | no | 0.35 | — |
  | 13:11:03 | 3 | 0.92 | 0.91 | no | 0.35 | — |
  | 13:12:03 | 3 | 0.87 | 0.82 | no | 0.35 | — |
  | 13:13:03 | 3 | 0.83 | 0.82 | no | 0.35 | — |
  | 13:14:03 | 3 | 0.95 | 0.94 | no | 0.35 | — |
  | 13:15:04 | 3 | 0.98 | 0.97 | no | 0.35 | — |
  | 13:16:03 | 3 | 1.14 | 1.13 | no | 0.91 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:17:03 | 3 | 1.3 | 1.25 | no | 1.12 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:18:03 | 3 | 1.36 | 1.35 | no | 1.12 | — |
  | 13:19:03 | 3 | 1.32 | 1.29 | no | 1.12 | — |
  | 13:20:04 | 3 | 1.47 | 1.44 | yes | 0.7 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:21:03 | 1 | 1.33 | 1.3 | yes | 1.2495 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:22:03 | 1 | 1.27 | 1.21 | yes | 1.2495 | **SELL_ALL 1 `trail`** (runner_stop @ 1.25) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $639.00 (realized $191.00, delta $448.00); oracle $933.00.
- **Parity control** — this trade's own as-placed shape, replayed: $315.00 vs $191.00 realized (gap $124.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$191.00** |
  | `hold_to_time_stop` | $639.00 |
  | `all_out_at_tp1_100` | $210.00 |
  | `tp1_100_trail_10` | $203.20 |
  | `tp1_100_trail_20` | $188.40 |
  | `all_out_at_tp1_50` | $105.00 |
  | `tp1_30_trail_125` | $52.50 |
  | `trail_only_no_tp1` | $6.00 |

### 2026-08-20 · bold-2 · `SPY260820P00764000` · realized $90.00

- **Entry** 12:57:05 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (SKIP_MIN_PREMIUM_FLOOR), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.34** × 5, stop `?`.
- **Entry fill quality** — paid 13.3% above the signal minute's low (bar 0.3–0.4).
- **High-water WHILE IN THE TRADE** 0.64 (88.2% vs entry) at 2026-08-20T17:42:00Z UTC · 29 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.9 (458.8%) at 2026-08-20T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:45:06 | 5 | 0.52 | 52.9% | `premium_stop` | 0.64 | $60.00 (18.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:17:05 | 5 | 0.41 | 0.4 | no | 0.17 | — |
  | 13:18:05 | 5 | 0.44 | 0.43 | no | 0.17 | — |
  | 13:19:05 | 5 | 0.39 | 0.38 | no | 0.17 | — |
  | 13:20:07 | 5 | 0.47 | 0.42 | no | 0.17 | — |
  | 13:21:04 | 5 | 0.42 | 0.37 | no | 0.17 | — |
  | 13:22:05 | 5 | 0.38 | 0.37 | no | 0.17 | — |
  | 13:23:04 | 5 | 0.34 | 0.33 | no | 0.17 | — |
  | 13:24:04 | 5 | 0.33 | 0.32 | no | 0.17 | — |
  | 13:25:05 | 5 | 0.39 | 0.38 | no | 0.17 | — |
  | 13:26:04 | 5 | 0.42 | 0.41 | no | 0.17 | — |
  | 13:27:04 | 5 | 0.4 | 0.35 | no | 0.17 | — |
  | 13:28:04 | 5 | 0.47 | 0.46 | no | 0.17 | — |
  | 13:29:04 | 5 | 0.45 | 0.44 | no | 0.17 | — |
  | 13:30:05 | 5 | 0.45 | 0.44 | no | 0.17 | — |
  | 13:31:06 | 5 | 0.44 | 0.43 | no | 0.17 | — |
  | 13:32:05 | 5 | 0.41 | 0.4 | no | 0.17 | — |
  | 13:33:04 | 5 | 0.45 | 0.44 | no | 0.17 | — |
  | 13:34:04 | 5 | 0.46 | 0.45 | no | 0.17 | — |
  | 13:35:05 | 5 | 0.51 | 0.46 | no | 0.442 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:36:04 | 5 | 0.47 | 0.46 | no | 0.442 | — |
  | 13:37:04 | 5 | 0.51 | 0.5 | no | 0.442 | — |
  | 13:38:04 | 5 | 0.57 | 0.56 | no | 0.442 | — |
  | 13:39:04 | 5 | 0.54 | 0.53 | no | 0.442 | — |
  | 13:40:05 | 5 | 0.54 | 0.53 | no | 0.442 | — |
  | 13:41:04 | 5 | 0.6 | 0.59 | no | 0.544 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:42:04 | 5 | 0.59 | 0.58 | no | 0.544 | — |
  | 13:43:04 | 5 | 0.62 | 0.57 | no | 0.544 | — |
  | 13:44:04 | 5 | 0.59 | 0.58 | no | 0.544 | — |
  | 13:45:05 | 5 | 0.54 | 0.49 | no | 0.544 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.54) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $255.00 (realized $90.00, delta $165.00); oracle $780.00.
- **Parity control** — this trade's own as-placed shape, replayed: $30.60 vs $90.00 realized (gap $-59.40 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$90.00** |
  | `hold_to_time_stop` | $255.00 |
  | `tp1_100_trail_20` | $178.00 |
  | `all_out_at_tp1_100` | $170.00 |
  | `tp1_100_trail_10` | $161.80 |
  | `all_out_at_tp1_50` | $85.00 |
  | `tp1_30_trail_125` | $49.67 |
  | `trail_only_no_tp1` | $30.00 |

### 2026-08-20 · risky-3 · `SPY260820P00764000` · realized $190.00

- **Entry** 13:16:05 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **766.64**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE); qty clamped 8->5: recency RED_
- **Strike** 764 (trigger 766.64, offset -2.64), quoted premium 0.33, filled **0.34** × 10, stop `0.26 (-20%)`.
- **Entry fill quality** — paid 13.3% above the signal minute's low (bar 0.3–0.4).
- **High-water WHILE IN THE TRADE** 0.64 (88.2% vs entry) at 2026-08-20T17:42:00Z UTC · 29 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.9 (458.8%) at 2026-08-20T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:45:09 | 10 | 0.53 | 55.9% | `premium_stop` | 0.64 | $110.00 (17.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:17:05 | 10 | 0.41 | 0.4 | no | 0.272 | — |
  | 13:18:05 | 10 | 0.43 | 0.42 | no | 0.272 | — |
  | 13:19:04 | 10 | 0.39 | 0.38 | no | 0.272 | — |
  | 13:20:07 | 10 | 0.46 | 0.45 | no | 0.272 | — |
  | 13:21:05 | 10 | 0.38 | 0.37 | no | 0.272 | — |
  | 13:22:06 | 10 | 0.33 | 0.32 | no | 0.272 | — |
  | 13:23:04 | 10 | 0.34 | 0.33 | no | 0.272 | — |
  | 13:24:05 | 10 | 0.33 | 0.32 | no | 0.272 | — |
  | 13:25:06 | 10 | 0.39 | 0.38 | no | 0.272 | — |
  | 13:26:05 | 10 | 0.42 | 0.41 | no | 0.272 | — |
  | 13:27:05 | 10 | 0.36 | 0.35 | no | 0.272 | — |
  | 13:28:05 | 10 | 0.46 | 0.41 | no | 0.272 | — |
  | 13:29:04 | 10 | 0.45 | 0.44 | no | 0.272 | — |
  | 13:30:07 | 10 | 0.41 | 0.4 | no | 0.272 | — |
  | 13:31:04 | 10 | 0.44 | 0.43 | no | 0.272 | — |
  | 13:32:06 | 10 | 0.4 | 0.39 | no | 0.272 | — |
  | 13:33:04 | 10 | 0.45 | 0.44 | no | 0.272 | — |
  | 13:34:05 | 10 | 0.43 | 0.42 | no | 0.272 | — |
  | 13:35:06 | 10 | 0.5 | 0.49 | no | 0.272 | — |
  | 13:36:06 | 10 | 0.47 | 0.46 | no | 0.272 | — |
  | 13:37:04 | 10 | 0.53 | 0.52 | no | 0.442 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:38:05 | 10 | 0.57 | 0.56 | no | 0.442 | — |
  | 13:39:04 | 10 | 0.49 | 0.48 | no | 0.442 | — |
  | 13:40:07 | 10 | 0.53 | 0.52 | no | 0.442 | — |
  | 13:41:04 | 10 | 0.55 | 0.54 | no | 0.442 | — |
  | 13:42:05 | 10 | 0.59 | 0.58 | no | 0.442 | — |
  | 13:43:04 | 10 | 0.62 | 0.61 | no | 0.544 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 13:44:05 | 10 | 0.61 | 0.6 | no | 0.544 | — |
  | 13:45:07 | 10 | 0.55 | 0.54 | no | 0.544 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.54) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $510.00 (realized $190.00, delta $320.00); oracle $1,560.00.
- **Parity control** — this trade's own as-placed shape, replayed: $316.48 vs $190.00 realized (gap $126.48 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$190.00** |
  | `hold_to_time_stop` | $510.00 |
  | `tp1_100_trail_20` | $356.00 |
  | `all_out_at_tp1_100` | $340.00 |
  | `tp1_100_trail_10` | $323.60 |
  | `all_out_at_tp1_50` | $170.00 |
  | `tp1_30_trail_125` | $99.34 |
  | `trail_only_no_tp1` | $60.00 |

### 2026-08-20 · safe-2 · `SPY260820P00765000` · realized $174.00

- **Entry** 14:01:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.04** × 3, stop `STRUCTURE@764.96 (cat -50%)`.
- **Entry fill quality** — paid 5.1% above the signal minute's low (bar 0.99–1.12).
- **High-water WHILE IN THE TRADE** 1.84 (76.9% vs entry) at 2026-08-20T18:10:00Z UTC · 12 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.96 (184.6%) at 2026-08-20T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:12:05 | 3 | 1.62 | 55.8% | `premium_stop` | 1.84 | $66.00 (12.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:32:03 | 3 | 0.79 | 0.74 | no | 0.7544 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 0.75) |
  | 14:02:03 | 3 | 1.12 | 1.06 | no | 0.52 | — |
  | 14:03:03 | 3 | 1.23 | 1.21 | no | 0.52 | — |
  | 14:04:03 | 3 | 1.26 | 1.23 | no | 0.52 | — |
  | 14:05:04 | 3 | 1.2 | 1.18 | no | 0.52 | — |
  | 14:06:03 | 3 | 1.43 | 1.42 | no | 0.52 | — |
  | 14:07:03 | 3 | 1.46 | 1.45 | no | 0.52 | — |
  | 14:08:03 | 3 | 1.56 | 1.54 | no | 1.352 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:09:03 | 3 | 1.58 | 1.57 | no | 1.352 | — |
  | 14:10:05 | 3 | 1.61 | 1.59 | no | 1.352 | — |
  | 14:11:04 | 3 | 1.86 | 1.84 | no | 1.664 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:12:04 | 3 | 1.68 | 1.64 | no | 1.664 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 1.66) |

- **This trade's variant grid** — best was `all_out_at_tp1_100` at $312.00 (realized $174.00, delta $138.00); oracle $576.00.
- **Parity control** — this trade's own as-placed shape, replayed: $281.00 vs $174.00 realized (gap $107.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$174.00** |
  | `all_out_at_tp1_100` | $312.00 |
  | `tp1_100_trail_10` | $300.20 |
  | `tp1_100_trail_20` | $278.40 |
  | `hold_to_time_stop` | $219.00 |
  | `all_out_at_tp1_50` | $156.00 |
  | `trail_only_no_tp1` | $108.00 |
  | `tp1_30_trail_125` | $92.28 |

### 2026-08-20 · bold-2 · `SPY260820P00763000` · realized $85.00

- **Entry** 14:01:07 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (SKIP_MIN_PREMIUM_FLOOR), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.34** × 5, stop `?`.
- **Entry fill quality** — paid 9.7% above the signal minute's low (bar 0.31–0.36).
- **High-water WHILE IN THE TRADE** 0.67 (97.1% vs entry) at 2026-08-20T18:11:00Z UTC · 10 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.95 (179.4%) at 2026-08-20T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:13:05 | 5 | 0.51 | 50.0% | `premium_stop` | 0.67 | $80.00 (23.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:04:05 | 5 | 0.36 | 0.35 | no | 0.17 | — |
  | 14:05:06 | 5 | 0.32 | 0.31 | no | 0.17 | — |
  | 14:06:04 | 5 | 0.42 | 0.41 | no | 0.17 | — |
  | 14:07:04 | 5 | 0.49 | 0.44 | no | 0.17 | — |
  | 14:08:04 | 5 | 0.52 | 0.47 | no | 0.442 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:09:04 | 5 | 0.48 | 0.47 | no | 0.442 | — |
  | 14:10:06 | 5 | 0.53 | 0.48 | no | 0.442 | — |
  | 14:11:05 | 5 | 0.67 | 0.66 | no | 0.544 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:12:05 | 5 | 0.56 | 0.55 | no | 0.544 | — |
  | 14:13:04 | 5 | 0.5 | 0.49 | no | 0.544 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.54) |

- **This trade's variant grid** — best was `all_out_at_tp1_100` at $170.00 (realized $85.00, delta $85.00); oracle $305.00.
- **Parity control** — this trade's own as-placed shape, replayed: $30.60 vs $85.00 realized (gap $-54.40 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$85.00** |
  | `all_out_at_tp1_100` | $170.00 |
  | `tp1_100_trail_10` | $165.40 |
  | `tp1_100_trail_20` | $150.80 |
  | `all_out_at_tp1_50` | $85.00 |
  | `tp1_30_trail_125` | $49.67 |
  | `trail_only_no_tp1` | $0.00 |
  | `hold_to_time_stop` | $-45.00 |

### 2026-08-20 · risky-3 · `SPY260820P00763000` · realized $180.00

- **Entry** 14:03:04 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (ENTER_BEAR), quality **BASE**, trigger **764.96**, risk `ALLOW`.
  - engine's own words: _ribbon_ride P (BASE); qty clamped 8->5: recency RED_
- **Strike** 763 (trigger 764.96, offset -1.96), quoted premium 0.32, filled **0.35** × 10, stop `0.26 (-20%)`.
- **Entry fill quality** — paid 12.9% above the signal minute's low (bar 0.31–0.36).
- **High-water WHILE IN THE TRADE** 0.67 (91.4% vs entry) at 2026-08-20T18:11:00Z UTC · 9 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.95 (171.4%) at 2026-08-20T19:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:12:08 | 10 | 0.53 | 51.4% | `premium_stop` | 0.67 | $140.00 (20.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:04:05 | 10 | 0.36 | 0.35 | no | 0.28 | — |
  | 14:05:07 | 10 | 0.32 | 0.31 | no | 0.28 | — |
  | 14:06:05 | 10 | 0.45 | 0.4 | no | 0.28 | — |
  | 14:07:05 | 10 | 0.47 | 0.46 | no | 0.28 | — |
  | 14:08:05 | 10 | 0.52 | 0.51 | no | 0.28 | — |
  | 14:09:04 | 10 | 0.52 | 0.51 | no | 0.28 | — |
  | 14:10:08 | 10 | 0.54 | 0.49 | no | 0.455 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:11:05 | 10 | 0.65 | 0.59 | no | 0.56 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:12:06 | 10 | 0.52 | 0.51 | no | 0.56 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.56) |

- **This trade's variant grid** — best was `all_out_at_tp1_100` at $350.00 (realized $180.00, delta $170.00); oracle $600.00.
- **Parity control** — this trade's own as-placed shape, replayed: $325.48 vs $180.00 realized (gap $145.48 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$180.00** |
  | `all_out_at_tp1_100` | $350.00 |
  | `tp1_100_trail_10` | $332.80 |
  | `tp1_100_trail_20` | $303.60 |
  | `all_out_at_tp1_50` | $175.00 |
  | `tp1_30_trail_125` | $99.74 |
  | `trail_only_no_tp1` | $80.00 |
  | `hold_to_time_stop` | $-100.00 |

### 2026-08-21 · bold-2 · `SPY260821C00768000` · realized $159.00

- **Entry** 11:06:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (SKIP_MIN_PREMIUM_FLOOR), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier SUPER)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.37** × 5, stop `?`.
- **Entry fill quality** — paid 27.6% above the signal minute's low (bar 0.29–0.39).
- **High-water WHILE IN THE TRADE** 0.74 (100.0% vs entry) at 2026-08-21T15:53:00Z UTC · 22 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.74 (100.0%) at 2026-08-21T15:53:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:54:05 | 3 | 0.72 | 94.6% | `tp1` | 0.74 | $6.00 (2.7%) |
  | 11:55:06 | 2 | 0.64 | 73.0% | `trail` | 0.74 | $20.00 (13.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:08:04 | 5 | 0.29 | 0.24 | no | 0.15 | — |
  | 11:09:04 | 5 | 0.27 | 0.22 | no | 0.15 | — |
  | 11:10:05 | 5 | 0.24 | 0.23 | no | 0.15 | — |
  | 11:11:04 | 5 | 0.23 | 0.22 | no | 0.15 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 766.15) |
  | 11:38:04 | 5 | 0.33 | 0.28 | no | 0.185 | — |
  | 11:39:04 | 5 | 0.3 | 0.29 | no | 0.185 | — |
  | 11:40:05 | 5 | 0.47 | 0.42 | no | 0.185 | — |
  | 11:41:04 | 5 | 0.54 | 0.53 | no | 0.185 | — |
  | 11:42:04 | 5 | 0.53 | 0.52 | no | 0.185 | — |
  | 11:43:04 | 5 | 0.52 | 0.51 | no | 0.185 | — |
  | 11:44:05 | 5 | 0.48 | 0.43 | no | 0.185 | — |
  | 11:45:05 | 5 | 0.55 | 0.54 | no | 0.185 | — |
  | 11:46:06 | 5 | 0.54 | 0.53 | no | 0.185 | — |
  | 11:47:04 | 5 | 0.48 | 0.47 | no | 0.185 | — |
  | 11:48:04 | 5 | 0.5 | 0.49 | no | 0.185 | — |
  | 11:49:04 | 5 | 0.41 | 0.4 | no | 0.185 | — |
  | 11:50:05 | 5 | 0.44 | 0.43 | no | 0.185 | — |
  | 11:51:04 | 5 | 0.55 | 0.5 | no | 0.185 | — |
  | 11:52:04 | 5 | 0.62 | 0.61 | no | 0.481 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:53:04 | 5 | 0.7 | 0.69 | no | 0.592 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:54:04 | 5 | 0.75 | 0.7 | yes | 0.37 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:55:05 | 2 | 0.63 | 0.62 | yes | 0.6375 | **SELL_ALL 2 `trail`** (runner_stop @ 0.64) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $185.00 (realized $159.00, delta $26.00); oracle $185.00.
- **Parity control** — this trade's own as-placed shape, replayed: $33.30 vs $159.00 realized (gap $-125.70 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$159.00** |
  | `all_out_at_tp1_100` | $185.00 |
  | `tp1_100_trail_10` | $170.20 |
  | `tp1_100_trail_20` | $155.40 |
  | `all_out_at_tp1_50` | $92.50 |
  | `tp1_30_trail_125` | $59.02 |
  | `trail_only_no_tp1` | $30.00 |
  | `hold_to_time_stop` | $-92.50 |

### 2026-08-21 · safe-3 · `SPY260821C00766000` · realized $90.00

- **Entry** 11:07:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **766.15**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 766 (trigger 766.15, offset -0.15), quoted premium 1.08, filled **1.36** × 3, stop `STRUCTURE@766.15 (cat -50%)`.
- **Entry fill quality** — paid 15.2% above the signal minute's low (bar 1.18–1.4).
- **High-water WHILE IN THE TRADE** 2.1 (54.4% vs entry) at 2026-08-21T15:53:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.1 (54.4%) at 2026-08-21T15:53:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:57:06 | 3 | 1.66 | 22.1% | `structure_stop` | 2.1 | $132.00 (20.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:08:06 | 3 | 1.04 | 1.03 | no | 0.54 | — |
  | 11:09:04 | 3 | 0.96 | 0.95 | no | 0.54 | — |
  | 11:10:06 | 3 | 0.88 | 0.83 | no | 0.54 | — |
  | 11:11:04 | 3 | 0.86 | 0.85 | no | 0.54 | — |
  | 11:12:05 | 3 | 0.89 | 0.88 | no | 0.54 | — |
  | 11:13:04 | 3 | 0.9 | 0.85 | no | 0.54 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 766.15) |
  | 11:38:05 | 3 | 1.21 | 1.2 | no | 0.68 | — |
  | 11:39:04 | 3 | 1.26 | 1.21 | no | 0.68 | — |
  | 11:40:07 | 3 | 1.5 | 1.48 | no | 0.68 | — |
  | 11:41:04 | 3 | 1.7 | 1.62 | no | 0.68 | — |
  | 11:42:06 | 3 | 1.76 | 1.7 | no | 0.68 | — |
  | 11:43:04 | 3 | 1.69 | 1.67 | no | 0.68 | — |
  | 11:44:06 | 3 | 1.61 | 1.55 | no | 0.68 | — |
  | 11:45:07 | 3 | 1.71 | 1.68 | no | 0.68 | — |
  | 11:46:06 | 3 | 1.73 | 1.71 | no | 0.68 | — |
  | 11:47:05 | 3 | 1.69 | 1.67 | no | 0.68 | — |
  | 11:48:05 | 3 | 1.58 | 1.56 | no | 0.68 | — |
  | 11:49:04 | 3 | 1.5 | 1.44 | no | 0.68 | — |
  | 11:50:07 | 3 | 1.57 | 1.55 | no | 0.68 | — |
  | 11:51:04 | 3 | 1.76 | 1.74 | no | 0.68 | — |
  | 11:52:05 | 3 | 1.9 | 1.84 | no | 0.68 | — |
  | 11:53:04 | 3 | 2.09 | 2.02 | no | 1.768 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:54:05 | 3 | 2.05 | 2.03 | no | 1.768 | — |
  | 11:55:07 | 3 | 1.96 | 1.94 | no | 1.768 | — |
  | 11:56:07 | 3 | 1.82 | 1.8 | no | 1.768 | — |
  | 11:57:04 | 3 | 1.7 | 1.67 | no | 1.768 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 1.77) |
  | 12:28:05 | 3 | 1.12 | 1.07 | no | 0.5 | — |
  | 12:29:04 | 3 | 1.13 | 1.12 | no | 0.5 | — |
  | 12:30:08 | 3 | 1.12 | 1.07 | no | 0.5 | — |
  | 12:31:04 | 3 | 1.04 | 0.99 | no | 0.5 | — |
  | 12:32:06 | 3 | 0.92 | 0.87 | no | 0.5 | — |
  | 12:33:05 | 3 | 0.97 | 0.96 | no | 0.5 | — |
  | 12:34:06 | 3 | 0.94 | 0.89 | no | 0.5 | — |
  | 12:35:07 | 3 | 0.85 | 0.84 | no | 0.5 | — |
  | 12:36:05 | 3 | 0.86 | 0.85 | no | 0.5 | — |
  | 12:37:04 | 3 | 0.88 | 0.87 | no | 0.5 | — |
  | 12:38:05 | 3 | 0.93 | 0.92 | no | 0.5 | — |
  | 12:39:04 | 3 | 0.97 | 0.96 | no | 0.5 | — |
  | 12:40:07 | 3 | 1.05 | 1.04 | no | 0.5 | — |
  | 12:41:04 | 3 | 1.05 | 1.0 | no | 0.5 | — |
  | 12:42:05 | 3 | 1.02 | 0.97 | no | 0.5 | — |
  | 12:43:04 | 3 | 1.05 | 1.0 | no | 0.5 | — |
  | 12:44:05 | 3 | 0.97 | 0.92 | no | 0.5 | — |
  | 12:45:07 | 3 | 0.95 | 0.94 | no | 0.5 | — |
  | 12:46:06 | 3 | 0.84 | 0.83 | no | 0.5 | — |
  | 12:47:05 | 3 | 0.86 | 0.85 | no | 0.5 | — |
  | 12:48:05 | 3 | 0.87 | 0.82 | no | 0.5 | — |
  | 12:49:05 | 3 | 0.91 | 0.9 | no | 0.5 | — |
  | 12:50:08 | 3 | 0.8 | 0.79 | no | 0.5 | — |
  | 12:51:05 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 12:52:07 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 12:53:05 | 3 | 0.76 | 0.71 | no | 0.5 | — |
  | 12:54:05 | 3 | 0.77 | 0.76 | no | 0.5 | — |
  | 12:55:06 | 3 | 0.76 | 0.75 | no | 0.5 | — |
  | 12:56:05 | 3 | 0.73 | 0.72 | no | 0.5 | — |
  | 12:57:04 | 3 | 0.73 | 0.72 | no | 0.5 | — |
  | 12:58:05 | 3 | 0.86 | 0.85 | no | 0.5 | — |
  | 12:59:04 | 3 | 0.94 | 0.89 | no | 0.5 | — |
  | 13:00:07 | 3 | 0.93 | 0.92 | no | 0.5 | — |
  | 13:01:04 | 3 | 0.92 | 0.91 | no | 0.5 | — |
  | 13:02:06 | 3 | 0.91 | 0.9 | no | 0.5 | — |
  | 13:03:04 | 3 | 0.82 | 0.81 | no | 0.5 | — |
  | 13:04:05 | 3 | 0.84 | 0.83 | no | 0.5 | — |
  | 13:05:07 | 3 | 0.8 | 0.79 | no | 0.5 | — |
  | 13:06:05 | 3 | 0.79 | 0.78 | no | 0.5 | — |
  | 13:07:04 | 3 | 0.88 | 0.87 | no | 0.5 | — |
  | 13:08:05 | 3 | 0.87 | 0.86 | no | 0.5 | — |
  | 13:09:05 | 3 | 0.97 | 0.92 | no | 0.5 | — |
  | 13:10:07 | 3 | 0.83 | 0.82 | no | 0.5 | — |
  | 13:11:05 | 3 | 0.8 | 0.75 | no | 0.5 | — |
  | 13:12:06 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 13:13:04 | 3 | 0.77 | 0.75 | no | 0.5 | — |
  | 13:14:05 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 13:15:06 | 3 | 0.74 | 0.73 | no | 0.5 | — |
  | 13:16:06 | 3 | 0.74 | 0.73 | no | 0.5 | — |
  | 13:17:04 | 3 | 0.78 | 0.77 | no | 0.5 | — |
  | 13:18:06 | 3 | 0.72 | 0.67 | no | 0.5 | — |
  | 13:19:04 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 13:20:06 | 3 | 0.7 | 0.69 | no | 0.5 | — |
  | 13:21:05 | 3 | 0.69 | 0.68 | no | 0.5 | — |
  | 13:22:06 | 3 | 0.64 | 0.63 | no | 0.5 | — |
  | 13:23:04 | 3 | 0.55 | 0.54 | no | 0.5 | — |
  | 13:24:05 | 3 | 0.58 | 0.53 | no | 0.5 | — |
  | 13:25:06 | 3 | 0.54 | 0.53 | no | 0.5 | — |
  | 13:26:05 | 3 | 0.58 | 0.53 | no | 0.5 | — |
  | 13:27:05 | 3 | 0.56 | 0.51 | no | 0.5 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 766.01) |
  | 13:36:05 | 3 | 0.45 | 0.44 | no | 0.21 | — |
  | 13:37:04 | 3 | 0.5 | 0.49 | no | 0.21 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 765.71) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $204.00 (realized $90.00, delta $114.00); oracle $222.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-204.00 vs $90.00 realized (gap $-294.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$90.00** |
  | `all_out_at_tp1_50` | $204.00 |
  | `tp1_30_trail_125` | $102.23 |
  | `trail_only_no_tp1` | $39.00 |
  | `all_out_at_tp1_100` | $-204.00 |
  | `tp1_100_trail_20` | $-204.00 |
  | `tp1_100_trail_10` | $-204.00 |
  | `hold_to_time_stop` | $-204.00 |

### 2026-08-21 · safe-3 · `SPY260821C00766000` · realized $15.00

- **Entry** 11:07:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **766.15**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 766 (trigger 766.15, offset -0.15), quoted premium 1.08, filled **0.42** × 3, stop `STRUCTURE@766.15 (cat -50%)`.
- **Entry fill quality** — paid 5.0% above the signal minute's low (bar 0.4–0.45).
- **High-water WHILE IN THE TRADE** 0.51 (21.4% vs entry) at 2026-08-21T17:37:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.86 (104.8%) at 2026-08-21T19:49:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:37:05 | 3 | 0.47 | 11.9% | `structure_stop` | 0.51 | $12.00 (7.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:08:06 | 3 | 1.04 | 1.03 | no | 0.54 | — |
  | 11:09:04 | 3 | 0.96 | 0.95 | no | 0.54 | — |
  | 11:10:06 | 3 | 0.88 | 0.83 | no | 0.54 | — |
  | 11:11:04 | 3 | 0.86 | 0.85 | no | 0.54 | — |
  | 11:12:05 | 3 | 0.89 | 0.88 | no | 0.54 | — |
  | 11:13:04 | 3 | 0.9 | 0.85 | no | 0.54 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 766.15) |
  | 11:38:05 | 3 | 1.21 | 1.2 | no | 0.68 | — |
  | 11:39:04 | 3 | 1.26 | 1.21 | no | 0.68 | — |
  | 11:40:07 | 3 | 1.5 | 1.48 | no | 0.68 | — |
  | 11:41:04 | 3 | 1.7 | 1.62 | no | 0.68 | — |
  | 11:42:06 | 3 | 1.76 | 1.7 | no | 0.68 | — |
  | 11:43:04 | 3 | 1.69 | 1.67 | no | 0.68 | — |
  | 11:44:06 | 3 | 1.61 | 1.55 | no | 0.68 | — |
  | 11:45:07 | 3 | 1.71 | 1.68 | no | 0.68 | — |
  | 11:46:06 | 3 | 1.73 | 1.71 | no | 0.68 | — |
  | 11:47:05 | 3 | 1.69 | 1.67 | no | 0.68 | — |
  | 11:48:05 | 3 | 1.58 | 1.56 | no | 0.68 | — |
  | 11:49:04 | 3 | 1.5 | 1.44 | no | 0.68 | — |
  | 11:50:07 | 3 | 1.57 | 1.55 | no | 0.68 | — |
  | 11:51:04 | 3 | 1.76 | 1.74 | no | 0.68 | — |
  | 11:52:05 | 3 | 1.9 | 1.84 | no | 0.68 | — |
  | 11:53:04 | 3 | 2.09 | 2.02 | no | 1.768 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:54:05 | 3 | 2.05 | 2.03 | no | 1.768 | — |
  | 11:55:07 | 3 | 1.96 | 1.94 | no | 1.768 | — |
  | 11:56:07 | 3 | 1.82 | 1.8 | no | 1.768 | — |
  | 11:57:04 | 3 | 1.7 | 1.67 | no | 1.768 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 1.77) |
  | 12:28:05 | 3 | 1.12 | 1.07 | no | 0.5 | — |
  | 12:29:04 | 3 | 1.13 | 1.12 | no | 0.5 | — |
  | 12:30:08 | 3 | 1.12 | 1.07 | no | 0.5 | — |
  | 12:31:04 | 3 | 1.04 | 0.99 | no | 0.5 | — |
  | 12:32:06 | 3 | 0.92 | 0.87 | no | 0.5 | — |
  | 12:33:05 | 3 | 0.97 | 0.96 | no | 0.5 | — |
  | 12:34:06 | 3 | 0.94 | 0.89 | no | 0.5 | — |
  | 12:35:07 | 3 | 0.85 | 0.84 | no | 0.5 | — |
  | 12:36:05 | 3 | 0.86 | 0.85 | no | 0.5 | — |
  | 12:37:04 | 3 | 0.88 | 0.87 | no | 0.5 | — |
  | 12:38:05 | 3 | 0.93 | 0.92 | no | 0.5 | — |
  | 12:39:04 | 3 | 0.97 | 0.96 | no | 0.5 | — |
  | 12:40:07 | 3 | 1.05 | 1.04 | no | 0.5 | — |
  | 12:41:04 | 3 | 1.05 | 1.0 | no | 0.5 | — |
  | 12:42:05 | 3 | 1.02 | 0.97 | no | 0.5 | — |
  | 12:43:04 | 3 | 1.05 | 1.0 | no | 0.5 | — |
  | 12:44:05 | 3 | 0.97 | 0.92 | no | 0.5 | — |
  | 12:45:07 | 3 | 0.95 | 0.94 | no | 0.5 | — |
  | 12:46:06 | 3 | 0.84 | 0.83 | no | 0.5 | — |
  | 12:47:05 | 3 | 0.86 | 0.85 | no | 0.5 | — |
  | 12:48:05 | 3 | 0.87 | 0.82 | no | 0.5 | — |
  | 12:49:05 | 3 | 0.91 | 0.9 | no | 0.5 | — |
  | 12:50:08 | 3 | 0.8 | 0.79 | no | 0.5 | — |
  | 12:51:05 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 12:52:07 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 12:53:05 | 3 | 0.76 | 0.71 | no | 0.5 | — |
  | 12:54:05 | 3 | 0.77 | 0.76 | no | 0.5 | — |
  | 12:55:06 | 3 | 0.76 | 0.75 | no | 0.5 | — |
  | 12:56:05 | 3 | 0.73 | 0.72 | no | 0.5 | — |
  | 12:57:04 | 3 | 0.73 | 0.72 | no | 0.5 | — |
  | 12:58:05 | 3 | 0.86 | 0.85 | no | 0.5 | — |
  | 12:59:04 | 3 | 0.94 | 0.89 | no | 0.5 | — |
  | 13:00:07 | 3 | 0.93 | 0.92 | no | 0.5 | — |
  | 13:01:04 | 3 | 0.92 | 0.91 | no | 0.5 | — |
  | 13:02:06 | 3 | 0.91 | 0.9 | no | 0.5 | — |
  | 13:03:04 | 3 | 0.82 | 0.81 | no | 0.5 | — |
  | 13:04:05 | 3 | 0.84 | 0.83 | no | 0.5 | — |
  | 13:05:07 | 3 | 0.8 | 0.79 | no | 0.5 | — |
  | 13:06:05 | 3 | 0.79 | 0.78 | no | 0.5 | — |
  | 13:07:04 | 3 | 0.88 | 0.87 | no | 0.5 | — |
  | 13:08:05 | 3 | 0.87 | 0.86 | no | 0.5 | — |
  | 13:09:05 | 3 | 0.97 | 0.92 | no | 0.5 | — |
  | 13:10:07 | 3 | 0.83 | 0.82 | no | 0.5 | — |
  | 13:11:05 | 3 | 0.8 | 0.75 | no | 0.5 | — |
  | 13:12:06 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 13:13:04 | 3 | 0.77 | 0.75 | no | 0.5 | — |
  | 13:14:05 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 13:15:06 | 3 | 0.74 | 0.73 | no | 0.5 | — |
  | 13:16:06 | 3 | 0.74 | 0.73 | no | 0.5 | — |
  | 13:17:04 | 3 | 0.78 | 0.77 | no | 0.5 | — |
  | 13:18:06 | 3 | 0.72 | 0.67 | no | 0.5 | — |
  | 13:19:04 | 3 | 0.72 | 0.71 | no | 0.5 | — |
  | 13:20:06 | 3 | 0.7 | 0.69 | no | 0.5 | — |
  | 13:21:05 | 3 | 0.69 | 0.68 | no | 0.5 | — |
  | 13:22:06 | 3 | 0.64 | 0.63 | no | 0.5 | — |
  | 13:23:04 | 3 | 0.55 | 0.54 | no | 0.5 | — |
  | 13:24:05 | 3 | 0.58 | 0.53 | no | 0.5 | — |
  | 13:25:06 | 3 | 0.54 | 0.53 | no | 0.5 | — |
  | 13:26:05 | 3 | 0.58 | 0.53 | no | 0.5 | — |
  | 13:27:05 | 3 | 0.56 | 0.51 | no | 0.5 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 766.01) |
  | 13:36:05 | 3 | 0.45 | 0.44 | no | 0.21 | — |
  | 13:37:04 | 3 | 0.5 | 0.49 | no | 0.21 | **SELL_ALL 3 `structure_stop`** (structure_stop @ 765.71) |

- **This trade's variant grid** — best was `trail_only_no_tp1` at $18.00 (realized $15.00, delta $3.00); oracle $132.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-63.00 vs $15.00 realized (gap $-78.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$15.00** |
  | `trail_only_no_tp1` | $18.00 |
  | `all_out_at_tp1_100` | $-63.00 |
  | `all_out_at_tp1_50` | $-63.00 |
  | `tp1_30_trail_125` | $-63.00 |
  | `tp1_100_trail_20` | $-63.00 |
  | `tp1_100_trail_10` | $-63.00 |
  | `hold_to_time_stop` | $-63.00 |

### 2026-08-21 · risky-1 · `SPY260821C00766000` · realized $262.00

- **Entry** 11:07:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **766.15**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 766 (trigger 766.15, offset -0.15), quoted premium 1.1, filled **1.38** × 5, stop `STRUCTURE@766.15 (cat -50%)`.
- **Entry fill quality** — paid 17.0% above the signal minute's low (bar 1.18–1.4).
- **High-water WHILE IN THE TRADE** 2.1 (52.2% vs entry) at 2026-08-21T15:53:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.1 (52.2%) at 2026-08-21T15:53:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:53:06 | 3 | 2.06 | 49.3% | `tp1` | 2.1 | $12.00 (1.9%) |
  | 11:57:07 | 2 | 1.67 | 21.0% | `trail` | 2.1 | $86.00 (20.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:08:06 | 5 | 1.07 | 1.02 | no | 0.535 | — |
  | 11:09:04 | 5 | 0.96 | 0.95 | no | 0.535 | — |
  | 11:10:06 | 5 | 0.89 | 0.88 | no | 0.535 | — |
  | 11:11:04 | 5 | 0.86 | 0.81 | no | 0.535 | — |
  | 11:12:05 | 5 | 0.94 | 0.89 | no | 0.535 | — |
  | 11:13:04 | 5 | 0.9 | 0.85 | no | 0.535 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 766.15) |
  | 11:38:05 | 5 | 1.2 | 1.19 | no | 0.69 | — |
  | 11:39:04 | 5 | 1.26 | 1.25 | no | 0.69 | — |
  | 11:40:07 | 5 | 1.46 | 1.43 | no | 0.69 | — |
  | 11:41:04 | 5 | 1.66 | 1.62 | no | 0.69 | — |
  | 11:42:06 | 5 | 1.71 | 1.69 | no | 0.69 | — |
  | 11:43:04 | 5 | 1.65 | 1.59 | no | 0.69 | — |
  | 11:44:06 | 5 | 1.62 | 1.61 | no | 0.69 | — |
  | 11:45:07 | 5 | 1.75 | 1.73 | no | 0.69 | — |
  | 11:46:06 | 5 | 1.68 | 1.67 | no | 0.69 | — |
  | 11:47:05 | 5 | 1.7 | 1.67 | no | 0.69 | — |
  | 11:48:05 | 5 | 1.58 | 1.55 | no | 0.69 | — |
  | 11:49:04 | 5 | 1.49 | 1.44 | no | 0.69 | — |
  | 11:50:07 | 5 | 1.58 | 1.56 | no | 0.69 | — |
  | 11:51:04 | 5 | 1.74 | 1.73 | no | 0.69 | — |
  | 11:52:05 | 5 | 1.91 | 1.89 | no | 0.69 | — |
  | 11:53:04 | 5 | 2.09 | 2.04 | yes | 1.38 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:54:05 | 2 | 2.1 | 2.08 | yes | 1.785 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:55:07 | 2 | 1.98 | 1.96 | yes | 1.785 | — |
  | 11:56:07 | 2 | 1.83 | 1.82 | yes | 1.785 | — |
  | 11:57:04 | 2 | 1.7 | 1.64 | yes | 1.785 | **SELL_ALL 2 `trail`** (runner_stop @ 1.78) |
  | 12:28:05 | 5 | 1.14 | 1.13 | no | 0.495 | — |
  | 12:29:04 | 5 | 1.13 | 1.12 | no | 0.495 | — |
  | 12:30:08 | 5 | 1.07 | 1.06 | no | 0.495 | — |
  | 12:31:04 | 5 | 1.04 | 0.99 | no | 0.495 | — |
  | 12:32:06 | 5 | 0.9 | 0.89 | no | 0.495 | — |
  | 12:33:05 | 5 | 0.98 | 0.97 | no | 0.495 | — |
  | 12:34:06 | 5 | 0.94 | 0.93 | no | 0.495 | — |
  | 12:35:07 | 5 | 0.85 | 0.84 | no | 0.495 | — |
  | 12:36:05 | 5 | 0.88 | 0.83 | no | 0.495 | — |
  | 12:37:04 | 5 | 0.92 | 0.87 | no | 0.495 | — |
  | 12:38:05 | 5 | 0.88 | 0.87 | no | 0.495 | — |
  | 12:39:04 | 5 | 1.01 | 1.0 | no | 0.495 | — |
  | 12:40:07 | 5 | 1.05 | 1.0 | no | 0.495 | — |
  | 12:41:04 | 5 | 1.05 | 1.0 | no | 0.495 | — |
  | 12:42:05 | 5 | 1.02 | 1.01 | no | 0.495 | — |
  | 12:43:04 | 5 | 1.02 | 1.01 | no | 0.495 | — |
  | 12:44:05 | 5 | 0.98 | 0.97 | no | 0.495 | — |
  | 12:45:07 | 5 | 0.94 | 0.89 | no | 0.495 | — |
  | 12:46:06 | 5 | 0.84 | 0.83 | no | 0.495 | — |
  | 12:47:05 | 5 | 0.86 | 0.81 | no | 0.495 | — |
  | 12:48:05 | 5 | 0.87 | 0.86 | no | 0.495 | — |
  | 12:49:05 | 5 | 0.91 | 0.9 | no | 0.495 | — |
  | 12:50:08 | 5 | 0.78 | 0.77 | no | 0.495 | — |
  | 12:51:05 | 5 | 0.72 | 0.71 | no | 0.495 | — |
  | 12:52:07 | 5 | 0.76 | 0.71 | no | 0.495 | — |
  | 12:53:05 | 5 | 0.77 | 0.72 | no | 0.495 | — |
  | 12:54:05 | 5 | 0.77 | 0.72 | no | 0.495 | — |
  | 12:55:06 | 5 | 0.76 | 0.75 | no | 0.495 | — |
  | 12:56:05 | 5 | 0.76 | 0.75 | no | 0.495 | — |
  | 12:57:04 | 5 | 0.75 | 0.74 | no | 0.495 | — |
  | 12:58:05 | 5 | 0.86 | 0.85 | no | 0.495 | — |
  | 12:59:04 | 5 | 0.94 | 0.89 | no | 0.495 | — |
  | 13:00:07 | 5 | 0.98 | 0.97 | no | 0.495 | — |
  | 13:01:04 | 5 | 0.91 | 0.9 | no | 0.495 | — |
  | 13:02:06 | 5 | 0.91 | 0.86 | no | 0.495 | — |
  | 13:03:04 | 5 | 0.86 | 0.85 | no | 0.495 | — |
  | 13:04:05 | 5 | 0.88 | 0.87 | no | 0.495 | — |
  | 13:05:07 | 5 | 0.79 | 0.78 | no | 0.495 | — |
  | 13:06:05 | 5 | 0.79 | 0.78 | no | 0.495 | — |
  | 13:07:04 | 5 | 0.87 | 0.82 | no | 0.495 | — |
  | 13:08:05 | 5 | 0.87 | 0.86 | no | 0.495 | — |
  | 13:09:05 | 5 | 0.94 | 0.93 | no | 0.495 | — |
  | 13:10:07 | 5 | 0.87 | 0.86 | no | 0.495 | — |
  | 13:11:05 | 5 | 0.79 | 0.74 | no | 0.495 | — |
  | 13:12:06 | 5 | 0.76 | 0.71 | no | 0.495 | — |
  | 13:13:04 | 5 | 0.76 | 0.71 | no | 0.495 | — |
  | 13:14:05 | 5 | 0.72 | 0.71 | no | 0.495 | — |
  | 13:15:06 | 5 | 0.69 | 0.68 | no | 0.495 | — |
  | 13:16:06 | 5 | 0.78 | 0.77 | no | 0.495 | — |
  | 13:17:04 | 5 | 0.74 | 0.73 | no | 0.495 | — |
  | 13:18:06 | 5 | 0.73 | 0.72 | no | 0.495 | — |
  | 13:19:04 | 5 | 0.67 | 0.66 | no | 0.495 | — |
  | 13:20:06 | 5 | 0.72 | 0.71 | no | 0.495 | — |
  | 13:21:05 | 5 | 0.64 | 0.63 | no | 0.495 | — |
  | 13:22:06 | 5 | 0.6 | 0.59 | no | 0.495 | — |
  | 13:23:04 | 5 | 0.59 | 0.58 | no | 0.495 | — |
  | 13:24:05 | 5 | 0.57 | 0.56 | no | 0.495 | — |
  | 13:25:06 | 5 | 0.58 | 0.57 | no | 0.495 | — |
  | 13:26:05 | 5 | 0.58 | 0.53 | no | 0.495 | — |
  | 13:27:05 | 5 | 0.56 | 0.55 | no | 0.495 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 766.01) |
  | 13:36:05 | 5 | 0.45 | 0.4 | no | 0.21 | — |
  | 13:37:04 | 5 | 0.5 | 0.45 | no | 0.21 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 765.71) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $345.00 (realized $262.00, delta $83.00); oracle $360.00.
- **Parity control** — this trade's own as-placed shape, replayed: $298.50 vs $262.00 realized (gap $36.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$262.00** |
  | `all_out_at_tp1_50` | $345.00 |
  | `tp1_30_trail_125` | $211.35 |
  | `trail_only_no_tp1` | $55.00 |
  | `all_out_at_tp1_100` | $-345.00 |
  | `tp1_100_trail_20` | $-345.00 |
  | `tp1_100_trail_10` | $-345.00 |
  | `hold_to_time_stop` | $-345.00 |

### 2026-08-21 · risky-1 · `SPY260821C00766000` · realized $25.00

- **Entry** 11:07:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **766.15**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 766 (trigger 766.15, offset -0.15), quoted premium 1.1, filled **0.42** × 5, stop `STRUCTURE@766.15 (cat -50%)`.
- **Entry fill quality** — paid 5.0% above the signal minute's low (bar 0.4–0.45).
- **High-water WHILE IN THE TRADE** 0.51 (21.4% vs entry) at 2026-08-21T17:37:00Z UTC · 88 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.86 (104.8%) at 2026-08-21T19:49:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:37:06 | 5 | 0.47 | 11.9% | `structure_stop` | 0.51 | $20.00 (7.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:08:06 | 5 | 1.07 | 1.02 | no | 0.535 | — |
  | 11:09:04 | 5 | 0.96 | 0.95 | no | 0.535 | — |
  | 11:10:06 | 5 | 0.89 | 0.88 | no | 0.535 | — |
  | 11:11:04 | 5 | 0.86 | 0.81 | no | 0.535 | — |
  | 11:12:05 | 5 | 0.94 | 0.89 | no | 0.535 | — |
  | 11:13:04 | 5 | 0.9 | 0.85 | no | 0.535 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 766.15) |
  | 11:38:05 | 5 | 1.2 | 1.19 | no | 0.69 | — |
  | 11:39:04 | 5 | 1.26 | 1.25 | no | 0.69 | — |
  | 11:40:07 | 5 | 1.46 | 1.43 | no | 0.69 | — |
  | 11:41:04 | 5 | 1.66 | 1.62 | no | 0.69 | — |
  | 11:42:06 | 5 | 1.71 | 1.69 | no | 0.69 | — |
  | 11:43:04 | 5 | 1.65 | 1.59 | no | 0.69 | — |
  | 11:44:06 | 5 | 1.62 | 1.61 | no | 0.69 | — |
  | 11:45:07 | 5 | 1.75 | 1.73 | no | 0.69 | — |
  | 11:46:06 | 5 | 1.68 | 1.67 | no | 0.69 | — |
  | 11:47:05 | 5 | 1.7 | 1.67 | no | 0.69 | — |
  | 11:48:05 | 5 | 1.58 | 1.55 | no | 0.69 | — |
  | 11:49:04 | 5 | 1.49 | 1.44 | no | 0.69 | — |
  | 11:50:07 | 5 | 1.58 | 1.56 | no | 0.69 | — |
  | 11:51:04 | 5 | 1.74 | 1.73 | no | 0.69 | — |
  | 11:52:05 | 5 | 1.91 | 1.89 | no | 0.69 | — |
  | 11:53:04 | 5 | 2.09 | 2.04 | yes | 1.38 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:54:05 | 2 | 2.1 | 2.08 | yes | 1.785 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:55:07 | 2 | 1.98 | 1.96 | yes | 1.785 | — |
  | 11:56:07 | 2 | 1.83 | 1.82 | yes | 1.785 | — |
  | 11:57:04 | 2 | 1.7 | 1.64 | yes | 1.785 | **SELL_ALL 2 `trail`** (runner_stop @ 1.78) |
  | 12:28:05 | 5 | 1.14 | 1.13 | no | 0.495 | — |
  | 12:29:04 | 5 | 1.13 | 1.12 | no | 0.495 | — |
  | 12:30:08 | 5 | 1.07 | 1.06 | no | 0.495 | — |
  | 12:31:04 | 5 | 1.04 | 0.99 | no | 0.495 | — |
  | 12:32:06 | 5 | 0.9 | 0.89 | no | 0.495 | — |
  | 12:33:05 | 5 | 0.98 | 0.97 | no | 0.495 | — |
  | 12:34:06 | 5 | 0.94 | 0.93 | no | 0.495 | — |
  | 12:35:07 | 5 | 0.85 | 0.84 | no | 0.495 | — |
  | 12:36:05 | 5 | 0.88 | 0.83 | no | 0.495 | — |
  | 12:37:04 | 5 | 0.92 | 0.87 | no | 0.495 | — |
  | 12:38:05 | 5 | 0.88 | 0.87 | no | 0.495 | — |
  | 12:39:04 | 5 | 1.01 | 1.0 | no | 0.495 | — |
  | 12:40:07 | 5 | 1.05 | 1.0 | no | 0.495 | — |
  | 12:41:04 | 5 | 1.05 | 1.0 | no | 0.495 | — |
  | 12:42:05 | 5 | 1.02 | 1.01 | no | 0.495 | — |
  | 12:43:04 | 5 | 1.02 | 1.01 | no | 0.495 | — |
  | 12:44:05 | 5 | 0.98 | 0.97 | no | 0.495 | — |
  | 12:45:07 | 5 | 0.94 | 0.89 | no | 0.495 | — |
  | 12:46:06 | 5 | 0.84 | 0.83 | no | 0.495 | — |
  | 12:47:05 | 5 | 0.86 | 0.81 | no | 0.495 | — |
  | 12:48:05 | 5 | 0.87 | 0.86 | no | 0.495 | — |
  | 12:49:05 | 5 | 0.91 | 0.9 | no | 0.495 | — |
  | 12:50:08 | 5 | 0.78 | 0.77 | no | 0.495 | — |
  | 12:51:05 | 5 | 0.72 | 0.71 | no | 0.495 | — |
  | 12:52:07 | 5 | 0.76 | 0.71 | no | 0.495 | — |
  | 12:53:05 | 5 | 0.77 | 0.72 | no | 0.495 | — |
  | 12:54:05 | 5 | 0.77 | 0.72 | no | 0.495 | — |
  | 12:55:06 | 5 | 0.76 | 0.75 | no | 0.495 | — |
  | 12:56:05 | 5 | 0.76 | 0.75 | no | 0.495 | — |
  | 12:57:04 | 5 | 0.75 | 0.74 | no | 0.495 | — |
  | 12:58:05 | 5 | 0.86 | 0.85 | no | 0.495 | — |
  | 12:59:04 | 5 | 0.94 | 0.89 | no | 0.495 | — |
  | 13:00:07 | 5 | 0.98 | 0.97 | no | 0.495 | — |
  | 13:01:04 | 5 | 0.91 | 0.9 | no | 0.495 | — |
  | 13:02:06 | 5 | 0.91 | 0.86 | no | 0.495 | — |
  | 13:03:04 | 5 | 0.86 | 0.85 | no | 0.495 | — |
  | 13:04:05 | 5 | 0.88 | 0.87 | no | 0.495 | — |
  | 13:05:07 | 5 | 0.79 | 0.78 | no | 0.495 | — |
  | 13:06:05 | 5 | 0.79 | 0.78 | no | 0.495 | — |
  | 13:07:04 | 5 | 0.87 | 0.82 | no | 0.495 | — |
  | 13:08:05 | 5 | 0.87 | 0.86 | no | 0.495 | — |
  | 13:09:05 | 5 | 0.94 | 0.93 | no | 0.495 | — |
  | 13:10:07 | 5 | 0.87 | 0.86 | no | 0.495 | — |
  | 13:11:05 | 5 | 0.79 | 0.74 | no | 0.495 | — |
  | 13:12:06 | 5 | 0.76 | 0.71 | no | 0.495 | — |
  | 13:13:04 | 5 | 0.76 | 0.71 | no | 0.495 | — |
  | 13:14:05 | 5 | 0.72 | 0.71 | no | 0.495 | — |
  | 13:15:06 | 5 | 0.69 | 0.68 | no | 0.495 | — |
  | 13:16:06 | 5 | 0.78 | 0.77 | no | 0.495 | — |
  | 13:17:04 | 5 | 0.74 | 0.73 | no | 0.495 | — |
  | 13:18:06 | 5 | 0.73 | 0.72 | no | 0.495 | — |
  | 13:19:04 | 5 | 0.67 | 0.66 | no | 0.495 | — |
  | 13:20:06 | 5 | 0.72 | 0.71 | no | 0.495 | — |
  | 13:21:05 | 5 | 0.64 | 0.63 | no | 0.495 | — |
  | 13:22:06 | 5 | 0.6 | 0.59 | no | 0.495 | — |
  | 13:23:04 | 5 | 0.59 | 0.58 | no | 0.495 | — |
  | 13:24:05 | 5 | 0.57 | 0.56 | no | 0.495 | — |
  | 13:25:06 | 5 | 0.58 | 0.57 | no | 0.495 | — |
  | 13:26:05 | 5 | 0.58 | 0.53 | no | 0.495 | — |
  | 13:27:05 | 5 | 0.56 | 0.55 | no | 0.495 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 766.01) |
  | 13:36:05 | 5 | 0.45 | 0.4 | no | 0.21 | — |
  | 13:37:04 | 5 | 0.5 | 0.45 | no | 0.21 | **SELL_ALL 5 `structure_stop`** (structure_stop @ 765.71) |

- **This trade's variant grid** — best was `trail_only_no_tp1` at $30.00 (realized $25.00, delta $5.00); oracle $220.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-105.00 vs $25.00 realized (gap $-130.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$25.00** |
  | `trail_only_no_tp1` | $30.00 |
  | `all_out_at_tp1_100` | $-105.00 |
  | `all_out_at_tp1_50` | $-105.00 |
  | `tp1_30_trail_125` | $-105.00 |
  | `tp1_100_trail_20` | $-105.00 |
  | `tp1_100_trail_10` | $-105.00 |
  | `hold_to_time_stop` | $-105.00 |

### 2026-08-21 · risky-3 · `SPY260821C00768000` · realized $220.00

- **Entry** 11:07:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **766.15**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 768 (trigger 766.15, offset 1.85), quoted premium 0.32, filled **0.42** × 10, stop `0.26 (-20%)`.
- **Entry fill quality** — paid 10.5% above the signal minute's low (bar 0.38–0.51).
- **High-water WHILE IN THE TRADE** 0.74 (76.2% vs entry) at 2026-08-21T15:53:00Z UTC · 19 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.74 (76.2%) at 2026-08-21T15:53:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:55:11 | 10 | 0.64 | 52.4% | `premium_stop` | 0.74 | $100.00 (13.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:08:06 | 10 | 0.3 | 0.29 | no | 0.24 | — |
  | 11:09:04 | 10 | 0.27 | 0.26 | no | 0.24 | — |
  | 11:10:06 | 10 | 0.24 | 0.19 | no | 0.24 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.24) |
  | 11:38:05 | 10 | 0.32 | 0.27 | no | 0.312 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.31) |
  | 11:41:04 | 10 | 0.54 | 0.53 | no | 0.336 | — |
  | 11:42:06 | 10 | 0.57 | 0.56 | no | 0.336 | — |
  | 11:43:04 | 10 | 0.51 | 0.5 | no | 0.336 | — |
  | 11:44:06 | 10 | 0.45 | 0.44 | no | 0.336 | — |
  | 11:45:07 | 10 | 0.56 | 0.55 | no | 0.336 | — |
  | 11:46:06 | 10 | 0.49 | 0.44 | no | 0.336 | — |
  | 11:47:05 | 10 | 0.52 | 0.51 | no | 0.336 | — |
  | 11:48:05 | 10 | 0.48 | 0.47 | no | 0.336 | — |
  | 11:49:04 | 10 | 0.41 | 0.36 | no | 0.336 | — |
  | 11:50:07 | 10 | 0.45 | 0.44 | no | 0.336 | — |
  | 11:51:04 | 10 | 0.53 | 0.52 | no | 0.336 | — |
  | 11:52:05 | 10 | 0.64 | 0.59 | no | 0.546 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:53:04 | 10 | 0.71 | 0.7 | no | 0.546 | — |
  | 11:54:05 | 10 | 0.74 | 0.73 | no | 0.672 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:55:07 | 10 | 0.63 | 0.62 | no | 0.672 | **SELL_ALL 10 `premium_stop`** (premium_stop @ 0.67) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `all_out_at_tp1_50` at $210.00 (realized $220.00, delta $-10.00); oracle $320.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-84.00 vs $220.00 realized (gap $-304.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$220.00** |
  | `all_out_at_tp1_50` | $210.00 |
  | `tp1_30_trail_125` | $120.04 |
  | `trail_only_no_tp1` | $60.00 |
  | `all_out_at_tp1_100` | $-210.00 |
  | `tp1_100_trail_20` | $-210.00 |
  | `tp1_100_trail_10` | $-210.00 |
  | `hold_to_time_stop` | $-210.00 |

### 2026-08-26 · safe-3 · `SPY260826C00766000` · realized $39.00

- **Entry** 14:57:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **766.38**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 766 (trigger 766.38, offset -0.38), quoted premium 1.48, filled **1.5** × 3, stop `STRUCTURE@766.38 (cat -50%)`.
- **Entry fill quality** — paid 0.7% above the signal minute's low (bar 1.49–1.58).
- **High-water WHILE IN THE TRADE** 2.08 (38.7% vs entry) at 2026-08-26T19:04:00Z UTC · 43 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.08 (38.7%) at 2026-08-26T19:04:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 15:40:07 | 3 | 1.63 | 8.7% | `time_stop` | 2.08 | $135.00 (21.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 14:58:06 | 3 | 1.57 | 1.51 | no | 0.75 | — |
  | 14:59:05 | 3 | 1.61 | 1.56 | no | 0.75 | — |
  | 15:00:07 | 3 | 1.56 | 1.51 | no | 0.75 | — |
  | 15:01:05 | 3 | 1.83 | 1.82 | no | 0.75 | — |
  | 15:02:05 | 3 | 1.87 | 1.84 | no | 0.75 | — |
  | 15:03:05 | 3 | 1.95 | 1.88 | no | 0.75 | — |
  | 15:04:05 | 3 | 1.92 | 1.86 | no | 0.75 | — |
  | 15:05:06 | 3 | 2.06 | 1.99 | no | 0.75 | — |
  | 15:06:05 | 3 | 1.91 | 1.89 | no | 0.75 | — |
  | 15:07:05 | 3 | 1.91 | 1.89 | no | 0.75 | — |
  | 15:08:05 | 3 | 1.9 | 1.89 | no | 0.75 | — |
  | 15:09:05 | 3 | 1.83 | 1.77 | no | 0.75 | — |
  | 15:10:06 | 3 | 1.87 | 1.86 | no | 0.75 | — |
  | 15:11:05 | 3 | 1.88 | 1.86 | no | 0.75 | — |
  | 15:12:06 | 3 | 1.92 | 1.91 | no | 0.75 | — |
  | 15:13:06 | 3 | 1.88 | 1.82 | no | 0.75 | — |
  | 15:14:05 | 3 | 1.84 | 1.77 | no | 0.75 | — |
  | 15:15:06 | 3 | 1.89 | 1.87 | no | 0.75 | — |
  | 15:16:05 | 3 | 1.94 | 1.92 | no | 0.75 | — |
  | 15:17:05 | 3 | 1.95 | 1.94 | no | 0.75 | — |
  | 15:18:05 | 3 | 1.98 | 1.97 | no | 0.75 | — |
  | 15:19:05 | 3 | 2.01 | 1.96 | no | 0.75 | — |
  | 15:20:07 | 3 | 1.98 | 1.93 | no | 0.75 | — |
  | 15:21:05 | 3 | 1.8 | 1.79 | no | 0.75 | — |
  | 15:22:06 | 3 | 1.83 | 1.81 | no | 0.75 | — |
  | 15:23:05 | 3 | 1.82 | 1.77 | no | 0.75 | — |
  | 15:24:05 | 3 | 1.83 | 1.82 | no | 0.75 | — |
  | 15:25:06 | 3 | 1.93 | 1.85 | no | 0.75 | — |
  | 15:26:05 | 3 | 1.91 | 1.86 | no | 0.75 | — |
  | 15:27:05 | 3 | 1.93 | 1.92 | no | 0.75 | — |
  | 15:28:06 | 3 | 1.85 | 1.84 | no | 0.75 | — |
  | 15:29:06 | 3 | 1.83 | 1.78 | no | 0.75 | — |
  | 15:30:07 | 3 | 1.75 | 1.74 | no | 0.75 | — |
  | 15:31:05 | 3 | 1.72 | 1.69 | no | 0.75 | — |
  | 15:32:06 | 3 | 1.7 | 1.68 | no | 0.75 | — |
  | 15:33:05 | 3 | 1.8 | 1.75 | no | 0.75 | — |
  | 15:34:05 | 3 | 1.71 | 1.7 | no | 0.75 | — |
  | 15:35:06 | 3 | 1.69 | 1.68 | no | 0.75 | — |
  | 15:36:05 | 3 | 1.69 | 1.67 | no | 0.75 | — |
  | 15:37:05 | 3 | 1.66 | 1.65 | no | 0.75 | — |
  | 15:38:05 | 3 | 1.67 | 1.66 | no | 0.75 | — |
  | 15:39:05 | 3 | 1.61 | 1.6 | no | 0.75 | — |
  | 15:40:06 | 3 | 1.66 | 1.65 | no | 0.75 | **SELL_ALL 3 `time_stop`** (time_stop_15:40) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_30_trail_125` at $122.00 (realized $39.00, delta $83.00); oracle $174.00.
- **Parity control** — this trade's own as-placed shape, replayed: $84.00 vs $39.00 realized (gap $45.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$39.00** |
  | `tp1_30_trail_125` | $122.00 |
  | `all_out_at_tp1_100` | $84.00 |
  | `all_out_at_tp1_50` | $84.00 |
  | `tp1_100_trail_20` | $84.00 |
  | `tp1_100_trail_10` | $84.00 |
  | `hold_to_time_stop` | $84.00 |
  | `trail_only_no_tp1` | $42.00 |

### 2026-08-27 · safe-2 · `SPY260827C00768000` · realized $138.00

- **Entry** 09:41:02 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.58** × 3, stop `STRUCTURE@767.35 (cat -50%)`.
- **Entry fill quality** — paid 1.3% above the signal minute's low (bar 1.56–1.86).
- **High-water WHILE IN THE TRADE** 2.49 (57.6% vs entry) at 2026-08-27T14:37:00Z UTC · 59 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.41 (179.1%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:40:04 | 3 | 2.04 | 29.1% | `premium_stop` | 2.49 | $135.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:42:03 | 3 | 1.7 | 1.69 | no | 0.79 | — |
  | 09:43:03 | 3 | 1.76 | 1.75 | no | 0.79 | — |
  | 09:44:03 | 3 | 1.66 | 1.65 | no | 0.79 | — |
  | 09:45:03 | 3 | 2.17 | 2.14 | no | 0.79 | — |
  | 09:46:03 | 3 | 2.34 | 2.32 | no | 0.79 | — |
  | 09:47:03 | 3 | 1.97 | 1.95 | no | 0.79 | — |
  | 09:48:03 | 3 | 1.71 | 1.7 | no | 0.79 | — |
  | 09:49:03 | 3 | 1.61 | 1.6 | no | 0.79 | — |
  | 09:50:04 | 3 | 1.57 | 1.51 | no | 0.79 | — |
  | 09:51:03 | 3 | 1.84 | 1.83 | no | 0.79 | — |
  | 09:52:03 | 3 | 1.94 | 1.87 | no | 0.79 | — |
  | 09:53:03 | 3 | 2.02 | 2.01 | no | 0.79 | — |
  | 09:54:03 | 3 | 2.06 | 2.05 | no | 0.79 | — |
  | 09:55:04 | 3 | 2.09 | 2.01 | no | 0.79 | — |
  | 09:56:02 | 3 | 1.86 | 1.85 | no | 0.79 | — |
  | 09:57:03 | 3 | 1.52 | 1.47 | no | 0.79 | — |
  | 09:58:04 | 3 | 1.42 | 1.41 | no | 0.79 | — |
  | 09:59:03 | 3 | 1.49 | 1.47 | no | 0.79 | — |
  | 10:00:04 | 3 | 1.6 | 1.59 | no | 0.79 | — |
  | 10:01:03 | 3 | 1.62 | 1.56 | no | 0.79 | — |
  | 10:02:03 | 3 | 1.73 | 1.72 | no | 0.79 | — |
  | 10:03:03 | 3 | 1.65 | 1.63 | no | 0.79 | — |
  | 10:04:03 | 3 | 1.88 | 1.87 | no | 0.79 | — |
  | 10:05:03 | 3 | 1.79 | 1.78 | no | 0.79 | — |
  | 10:06:03 | 3 | 1.88 | 1.87 | no | 0.79 | — |
  | 10:07:03 | 3 | 1.48 | 1.47 | no | 0.79 | — |
  | 10:08:03 | 3 | 1.69 | 1.68 | no | 0.79 | — |
  | 10:09:03 | 3 | 1.55 | 1.54 | no | 0.79 | — |
  | 10:10:03 | 3 | 1.61 | 1.56 | no | 0.79 | — |
  | 10:11:02 | 3 | 1.83 | 1.82 | no | 0.79 | — |
  | 10:12:03 | 3 | 1.78 | 1.76 | no | 0.79 | — |
  | 10:13:03 | 3 | 1.73 | 1.71 | no | 0.79 | — |
  | 10:14:03 | 3 | 1.85 | 1.83 | no | 0.79 | — |
  | 10:15:03 | 3 | 1.66 | 1.65 | no | 0.79 | — |
  | 10:16:03 | 3 | 1.84 | 1.83 | no | 0.79 | — |
  | 10:17:03 | 3 | 1.75 | 1.73 | no | 0.79 | — |
  | 10:18:03 | 3 | 1.93 | 1.91 | no | 0.79 | — |
  | 10:19:03 | 3 | 2.0 | 1.99 | no | 0.79 | — |
  | 10:20:03 | 3 | 1.96 | 1.95 | no | 0.79 | — |
  | 10:21:03 | 3 | 2.15 | 2.14 | no | 0.79 | — |
  | 10:22:03 | 3 | 1.89 | 1.82 | no | 0.79 | — |
  | 10:23:03 | 3 | 1.9 | 1.88 | no | 0.79 | — |
  | 10:24:03 | 3 | 2.01 | 1.95 | no | 0.79 | — |
  | 10:25:03 | 3 | 2.06 | 2.04 | no | 0.79 | — |
  | 10:26:02 | 3 | 2.09 | 2.07 | no | 0.79 | — |
  | 10:27:03 | 3 | 2.31 | 2.24 | no | 0.79 | — |
  | 10:28:03 | 3 | 2.32 | 2.22 | no | 0.79 | — |
  | 10:29:03 | 3 | 2.1 | 2.09 | no | 0.79 | — |
  | 10:30:04 | 3 | 2.21 | 2.17 | no | 0.79 | — |
  | 10:31:03 | 3 | 1.96 | 1.89 | no | 0.79 | — |
  | 10:32:03 | 3 | 1.97 | 1.94 | no | 0.79 | — |
  | 10:33:03 | 3 | 1.96 | 1.9 | no | 0.79 | — |
  | 10:34:03 | 3 | 2.15 | 2.13 | no | 0.79 | — |
  | 10:35:03 | 3 | 2.09 | 2.01 | no | 0.79 | — |
  | 10:36:03 | 3 | 2.29 | 2.27 | no | 0.79 | — |
  | 10:37:03 | 3 | 2.37 | 2.35 | no | 2.054 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:38:03 | 3 | 2.33 | 2.3 | no | 2.054 | — |
  | 10:39:03 | 3 | 2.22 | 2.21 | no | 2.054 | — |
  | 10:40:03 | 3 | 2.07 | 2.05 | no | 2.054 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 2.05) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $474.00 (realized $138.00, delta $336.00); oracle $849.00.
- **Parity control** — this trade's own as-placed shape, replayed: $316.00 vs $138.00 realized (gap $178.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$138.00** |
  | `all_out_at_tp1_100` | $474.00 |
  | `tp1_100_trail_10` | $455.00 |
  | `tp1_100_trail_20` | $422.00 |
  | `hold_to_time_stop` | $276.00 |
  | `all_out_at_tp1_50` | $237.00 |
  | `tp1_30_trail_125` | $143.30 |
  | `trail_only_no_tp1` | $36.00 |

### 2026-08-27 · bold-2 · `SPY260827C00770000` · realized $95.00

- **Entry** 09:41:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.72** × 5, stop `STRUCTURE@767.35 (cat -50%)`.
- **Entry fill quality** — paid 5.9% above the signal minute's low (bar 0.68–0.85).
- **High-water WHILE IN THE TRADE** 1.23 (70.8% vs entry) at 2026-08-27T13:46:00Z UTC · 6 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.5 (247.2%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:47:06 | 5 | 0.91 | 26.4% | `premium_stop` | 1.23 | $160.00 (26.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:42:05 | 5 | 0.75 | 0.74 | no | 0.36 | — |
  | 09:43:04 | 5 | 0.8 | 0.79 | no | 0.36 | — |
  | 09:44:05 | 5 | 0.77 | 0.76 | no | 0.36 | — |
  | 09:45:05 | 5 | 1.04 | 1.03 | no | 0.36 | — |
  | 09:46:05 | 5 | 1.18 | 1.17 | no | 0.936 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 09:47:05 | 5 | 0.93 | 0.88 | no | 0.936 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.94) |

- **Tags:** `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $360.00 (realized $95.00, delta $265.00); oracle $890.00.
- **Parity control** — this trade's own as-placed shape, replayed: $216.00 vs $95.00 realized (gap $121.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$95.00** |
  | `all_out_at_tp1_100` | $360.00 |
  | `tp1_100_trail_10` | $358.20 |
  | `tp1_100_trail_20` | $334.40 |
  | `all_out_at_tp1_50` | $180.00 |
  | `tp1_30_trail_125` | $116.77 |
  | `trail_only_no_tp1` | $20.00 |
  | `hold_to_time_stop` | $-180.00 |

### 2026-08-27 · safe-3 · `SPY260827C00768000` · realized $285.00

- **Entry** 09:42:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **767.35**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 768 (trigger 767.35, offset 0.65), quoted premium 1.64, filled **1.65** × 3, stop `STRUCTURE@767.35 (cat -50%)`.
- **Entry fill quality** — paid 15.4% above the signal minute's low (bar 1.43–1.74).
- **High-water WHILE IN THE TRADE** 2.93 (77.6% vs entry) at 2026-08-27T15:01:00Z UTC · 82 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.41 (167.3%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:04:07 | 3 | 2.6 | 57.6% | `premium_stop` | 2.93 | $99.00 (11.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:04 | 3 | 1.75 | 1.74 | no | 0.825 | — |
  | 09:44:04 | 3 | 1.77 | 1.76 | no | 0.825 | — |
  | 09:45:05 | 3 | 2.18 | 2.11 | no | 0.825 | — |
  | 09:46:05 | 3 | 2.35 | 2.33 | no | 0.825 | — |
  | 09:47:05 | 3 | 2.02 | 1.95 | no | 0.825 | — |
  | 09:48:05 | 3 | 1.69 | 1.68 | no | 0.825 | — |
  | 09:49:05 | 3 | 1.54 | 1.53 | no | 0.825 | — |
  | 09:50:06 | 3 | 1.56 | 1.5 | no | 0.825 | — |
  | 09:51:05 | 3 | 1.82 | 1.81 | no | 0.825 | — |
  | 09:52:05 | 3 | 1.91 | 1.9 | no | 0.825 | — |
  | 09:53:05 | 3 | 2.0 | 1.98 | no | 0.825 | — |
  | 09:54:05 | 3 | 2.15 | 2.06 | no | 0.825 | — |
  | 09:55:06 | 3 | 2.01 | 1.99 | no | 0.825 | — |
  | 09:56:05 | 3 | 1.82 | 1.81 | no | 0.825 | — |
  | 09:57:05 | 3 | 1.52 | 1.47 | no | 0.825 | — |
  | 09:58:07 | 3 | 1.43 | 1.41 | no | 0.825 | — |
  | 09:59:05 | 3 | 1.47 | 1.45 | no | 0.825 | — |
  | 10:00:07 | 3 | 1.63 | 1.62 | no | 0.825 | — |
  | 10:01:05 | 3 | 1.58 | 1.57 | no | 0.825 | — |
  | 10:02:05 | 3 | 1.7 | 1.69 | no | 0.825 | — |
  | 10:03:05 | 3 | 1.67 | 1.66 | no | 0.825 | — |
  | 10:04:05 | 3 | 1.88 | 1.87 | no | 0.825 | — |
  | 10:05:06 | 3 | 1.77 | 1.76 | no | 0.825 | — |
  | 10:06:05 | 3 | 1.89 | 1.87 | no | 0.825 | — |
  | 10:07:05 | 3 | 1.41 | 1.4 | no | 0.825 | — |
  | 10:08:05 | 3 | 1.65 | 1.6 | no | 0.825 | — |
  | 10:09:05 | 3 | 1.52 | 1.51 | no | 0.825 | — |
  | 10:10:06 | 3 | 1.61 | 1.56 | no | 0.825 | — |
  | 10:11:05 | 3 | 1.82 | 1.8 | no | 0.825 | — |
  | 10:12:05 | 3 | 1.74 | 1.72 | no | 0.825 | — |
  | 10:13:05 | 3 | 1.77 | 1.71 | no | 0.825 | — |
  | 10:14:05 | 3 | 1.83 | 1.82 | no | 0.825 | — |
  | 10:15:06 | 3 | 1.7 | 1.65 | no | 0.825 | — |
  | 10:16:05 | 3 | 1.88 | 1.82 | no | 0.825 | — |
  | 10:17:05 | 3 | 1.76 | 1.74 | no | 0.825 | — |
  | 10:18:05 | 3 | 1.88 | 1.87 | no | 0.825 | — |
  | 10:19:05 | 3 | 1.97 | 1.95 | no | 0.825 | — |
  | 10:20:06 | 3 | 1.94 | 1.91 | no | 0.825 | — |
  | 10:21:05 | 3 | 2.06 | 2.05 | no | 0.825 | — |
  | 10:22:05 | 3 | 1.95 | 1.93 | no | 0.825 | — |
  | 10:23:05 | 3 | 1.99 | 1.97 | no | 0.825 | — |
  | 10:24:05 | 3 | 2.0 | 1.92 | no | 0.825 | — |
  | 10:25:06 | 3 | 2.03 | 1.97 | no | 0.825 | — |
  | 10:26:05 | 3 | 2.12 | 2.1 | no | 0.825 | — |
  | 10:27:05 | 3 | 2.34 | 2.31 | no | 0.825 | — |
  | 10:28:06 | 3 | 2.32 | 2.3 | no | 0.825 | — |
  | 10:29:05 | 3 | 2.16 | 2.14 | no | 0.825 | — |
  | 10:30:07 | 3 | 2.23 | 2.22 | no | 0.825 | — |
  | 10:31:05 | 3 | 1.95 | 1.94 | no | 0.825 | — |
  | 10:32:05 | 3 | 2.0 | 1.99 | no | 0.825 | — |
  | 10:33:05 | 3 | 1.97 | 1.96 | no | 0.825 | — |
  | 10:34:05 | 3 | 2.13 | 2.11 | no | 0.825 | — |
  | 10:35:06 | 3 | 2.11 | 2.05 | no | 0.825 | — |
  | 10:36:05 | 3 | 2.29 | 2.28 | no | 0.825 | — |
  | 10:37:05 | 3 | 2.35 | 2.33 | no | 0.825 | — |
  | 10:38:05 | 3 | 2.33 | 2.3 | no | 0.825 | — |
  | 10:39:05 | 3 | 2.26 | 2.24 | no | 0.825 | — |
  | 10:40:06 | 3 | 2.1 | 2.07 | no | 0.825 | — |
  | 10:41:05 | 3 | 2.08 | 2.06 | no | 0.825 | — |
  | 10:42:05 | 3 | 2.13 | 2.11 | no | 0.825 | — |
  | 10:43:05 | 3 | 2.15 | 2.11 | no | 0.825 | — |
  | 10:44:05 | 3 | 2.14 | 2.13 | no | 0.825 | — |
  | 10:45:06 | 3 | 2.11 | 2.1 | no | 0.825 | — |
  | 10:46:05 | 3 | 2.26 | 2.24 | no | 0.825 | — |
  | 10:47:05 | 3 | 2.21 | 2.19 | no | 0.825 | — |
  | 10:48:05 | 3 | 2.05 | 2.03 | no | 0.825 | — |
  | 10:49:05 | 3 | 2.39 | 2.29 | no | 0.825 | — |
  | 10:50:06 | 3 | 2.6 | 2.5 | no | 2.145 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:51:05 | 3 | 2.6 | 2.59 | no | 2.145 | — |
  | 10:52:05 | 3 | 2.53 | 2.5 | no | 2.145 | — |
  | 10:53:06 | 3 | 2.67 | 2.64 | no | 2.145 | — |
  | 10:54:06 | 3 | 2.42 | 2.4 | no | 2.145 | — |
  | 10:55:06 | 3 | 2.57 | 2.55 | no | 2.145 | — |
  | 10:56:05 | 3 | 2.32 | 2.23 | no | 2.145 | — |
  | 10:57:06 | 3 | 2.29 | 2.25 | no | 2.145 | — |
  | 10:58:05 | 3 | 2.41 | 2.38 | no | 2.145 | — |
  | 10:59:05 | 3 | 2.69 | 2.59 | no | 2.145 | — |
  | 11:00:07 | 3 | 2.68 | 2.65 | no | 2.145 | — |
  | 11:01:05 | 3 | 2.8 | 2.78 | no | 2.145 | — |
  | 11:02:05 | 3 | 2.82 | 2.81 | no | 2.145 | — |
  | 11:03:05 | 3 | 2.89 | 2.79 | no | 2.64 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:04:06 | 3 | 2.65 | 2.64 | no | 2.64 | **SELL_ALL 3 `premium_stop`** (premium_stop @ 2.64) |

- **This trade's variant grid** — best was `all_out_at_tp1_100` at $495.00 (realized $285.00, delta $210.00); oracle $828.00.
- **Parity control** — this trade's own as-placed shape, replayed: $453.75 vs $285.00 realized (gap $168.75 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$285.00** |
  | `all_out_at_tp1_100` | $495.00 |
  | `tp1_100_trail_10` | $462.00 |
  | `tp1_100_trail_20` | $429.00 |
  | `hold_to_time_stop` | $255.00 |
  | `all_out_at_tp1_50` | $247.50 |
  | `tp1_30_trail_125` | $148.38 |
  | `trail_only_no_tp1` | $9.00 |

### 2026-08-27 · risky-1 · `SPY260827C00768000` · realized $475.00

- **Entry** 09:42:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **767.35**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 768 (trigger 767.35, offset 0.65), quoted premium 1.67, filled **1.66** × 5, stop `STRUCTURE@767.35 (cat -50%)`.
- **Entry fill quality** — paid 16.1% above the signal minute's low (bar 1.43–1.74).
- **High-water WHILE IN THE TRADE** 3.3 (98.8% vs entry) at 2026-08-27T15:19:00Z UTC · 106 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.41 (165.7%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:50:08 | 3 | 2.51 | 51.2% | `tp1` | 2.66 | $45.00 (5.6%) |
  | 11:28:07 | 1 | 2.76 | 66.3% | `?` | 3.3 | $54.00 (16.4%) |
  | 11:28:07 | 1 | 2.76 | 66.3% | `?` | 3.3 | $54.00 (16.4%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:04 | 5 | 1.72 | 1.7 | no | 0.83 | — |
  | 09:44:04 | 5 | 1.92 | 1.91 | no | 0.83 | — |
  | 09:45:05 | 5 | 2.22 | 2.2 | no | 0.83 | — |
  | 09:46:05 | 5 | 2.42 | 2.35 | no | 0.83 | — |
  | 09:47:05 | 5 | 1.98 | 1.95 | no | 0.83 | — |
  | 09:48:05 | 5 | 1.63 | 1.62 | no | 0.83 | — |
  | 09:49:05 | 5 | 1.55 | 1.53 | no | 0.83 | — |
  | 09:50:06 | 5 | 1.53 | 1.52 | no | 0.83 | — |
  | 09:51:05 | 5 | 1.86 | 1.85 | no | 0.83 | — |
  | 09:52:05 | 5 | 1.94 | 1.93 | no | 0.83 | — |
  | 09:53:05 | 5 | 2.0 | 1.95 | no | 0.83 | — |
  | 09:54:05 | 5 | 2.12 | 2.1 | no | 0.83 | — |
  | 09:55:06 | 5 | 2.03 | 1.94 | no | 0.83 | — |
  | 09:56:05 | 5 | 1.82 | 1.76 | no | 0.83 | — |
  | 09:57:05 | 5 | 1.52 | 1.47 | no | 0.83 | — |
  | 09:58:07 | 5 | 1.43 | 1.41 | no | 0.83 | — |
  | 09:59:05 | 5 | 1.52 | 1.5 | no | 0.83 | — |
  | 10:00:07 | 5 | 1.66 | 1.61 | no | 0.83 | — |
  | 10:01:05 | 5 | 1.62 | 1.61 | no | 0.83 | — |
  | 10:02:05 | 5 | 1.64 | 1.63 | no | 0.83 | — |
  | 10:03:05 | 5 | 1.67 | 1.62 | no | 0.83 | — |
  | 10:04:05 | 5 | 1.9 | 1.87 | no | 0.83 | — |
  | 10:05:06 | 5 | 1.76 | 1.74 | no | 0.83 | — |
  | 10:06:05 | 5 | 1.83 | 1.81 | no | 0.83 | — |
  | 10:07:05 | 5 | 1.54 | 1.53 | no | 0.83 | — |
  | 10:08:05 | 5 | 1.61 | 1.59 | no | 0.83 | — |
  | 10:09:05 | 5 | 1.54 | 1.53 | no | 0.83 | — |
  | 10:10:06 | 5 | 1.61 | 1.56 | no | 0.83 | — |
  | 10:11:05 | 5 | 1.81 | 1.8 | no | 0.83 | — |
  | 10:12:05 | 5 | 1.74 | 1.73 | no | 0.83 | — |
  | 10:13:05 | 5 | 1.77 | 1.71 | no | 0.83 | — |
  | 10:14:05 | 5 | 1.83 | 1.78 | no | 0.83 | — |
  | 10:15:06 | 5 | 1.7 | 1.65 | no | 0.83 | — |
  | 10:16:05 | 5 | 1.84 | 1.83 | no | 0.83 | — |
  | 10:17:05 | 5 | 1.76 | 1.75 | no | 0.83 | — |
  | 10:18:05 | 5 | 1.91 | 1.9 | no | 0.83 | — |
  | 10:19:05 | 5 | 1.97 | 1.96 | no | 0.83 | — |
  | 10:20:06 | 5 | 2.02 | 2.0 | no | 0.83 | — |
  | 10:21:05 | 5 | 2.07 | 2.04 | no | 0.83 | — |
  | 10:22:05 | 5 | 1.94 | 1.93 | no | 0.83 | — |
  | 10:23:05 | 5 | 1.93 | 1.92 | no | 0.83 | — |
  | 10:24:05 | 5 | 1.92 | 1.9 | no | 0.83 | — |
  | 10:25:06 | 5 | 2.02 | 1.96 | no | 0.83 | — |
  | 10:26:05 | 5 | 2.12 | 2.07 | no | 0.83 | — |
  | 10:27:05 | 5 | 2.29 | 2.27 | no | 0.83 | — |
  | 10:28:06 | 5 | 2.3 | 2.28 | no | 0.83 | — |
  | 10:29:05 | 5 | 2.11 | 2.07 | no | 0.83 | — |
  | 10:30:07 | 5 | 2.28 | 2.25 | no | 0.83 | — |
  | 10:31:05 | 5 | 1.95 | 1.94 | no | 0.83 | — |
  | 10:32:05 | 5 | 1.99 | 1.92 | no | 0.83 | — |
  | 10:33:05 | 5 | 1.87 | 1.86 | no | 0.83 | — |
  | 10:34:05 | 5 | 2.15 | 2.13 | no | 0.83 | — |
  | 10:35:06 | 5 | 2.11 | 2.05 | no | 0.83 | — |
  | 10:36:05 | 5 | 2.25 | 2.22 | no | 0.83 | — |
  | 10:37:05 | 5 | 2.36 | 2.35 | no | 0.83 | — |
  | 10:38:05 | 5 | 2.37 | 2.29 | no | 0.83 | — |
  | 10:39:05 | 5 | 2.25 | 2.22 | no | 0.83 | — |
  | 10:40:06 | 5 | 2.09 | 2.0 | no | 0.83 | — |
  | 10:41:05 | 5 | 2.06 | 2.04 | no | 0.83 | — |
  | 10:42:05 | 5 | 2.17 | 2.16 | no | 0.83 | — |
  | 10:43:05 | 5 | 2.18 | 2.12 | no | 0.83 | — |
  | 10:44:05 | 5 | 2.15 | 2.11 | no | 0.83 | — |
  | 10:45:06 | 5 | 2.11 | 2.1 | no | 0.83 | — |
  | 10:46:05 | 5 | 2.25 | 2.23 | no | 0.83 | — |
  | 10:47:05 | 5 | 2.25 | 2.22 | no | 0.83 | — |
  | 10:48:05 | 5 | 2.07 | 2.05 | no | 0.83 | — |
  | 10:49:05 | 5 | 2.39 | 2.29 | no | 0.83 | — |
  | 10:50:06 | 5 | 2.6 | 2.5 | yes | 1.66 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:51:05 | 2 | 2.58 | 2.55 | yes | 2.21 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:52:05 | 2 | 2.53 | 2.51 | yes | 2.21 | — |
  | 10:53:06 | 2 | 2.63 | 2.61 | yes | 2.2355 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:54:06 | 2 | 2.47 | 2.37 | yes | 2.2355 | — |
  | 10:55:06 | 2 | 2.58 | 2.51 | yes | 2.2355 | — |
  | 10:56:05 | 2 | 2.34 | 2.27 | yes | 2.2355 | — |
  | 10:57:06 | 2 | 2.29 | 2.25 | yes | 2.2355 | — |
  | 10:58:05 | 2 | 2.39 | 2.36 | yes | 2.2355 | — |
  | 10:59:05 | 2 | 2.7 | 2.68 | yes | 2.295 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:00:07 | 2 | 2.68 | 2.65 | yes | 2.295 | — |
  | 11:01:05 | 2 | 2.82 | 2.74 | yes | 2.397 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:02:05 | 2 | 2.82 | 2.81 | yes | 2.397 | — |
  | 11:03:05 | 2 | 2.83 | 2.81 | yes | 2.4055 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:04:06 | 2 | 2.68 | 2.65 | yes | 2.4055 | — |
  | 11:05:07 | 2 | 2.96 | 2.93 | yes | 2.516 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:06:06 | 2 | 2.89 | 2.88 | yes | 2.516 | — |
  | 11:07:05 | 2 | 2.82 | 2.79 | yes | 2.516 | — |
  | 11:08:05 | 2 | 2.68 | 2.67 | yes | 2.516 | — |
  | 11:09:05 | 2 | 2.83 | 2.81 | yes | 2.516 | — |
  | 11:10:07 | 2 | 2.88 | 2.86 | yes | 2.516 | — |
  | 11:11:06 | 2 | 2.84 | 2.83 | yes | 2.516 | — |
  | 11:12:05 | 2 | 2.92 | 2.89 | yes | 2.516 | — |
  | 11:13:05 | 2 | 2.84 | 2.81 | yes | 2.516 | — |
  | 11:14:05 | 2 | 2.94 | 2.89 | yes | 2.516 | — |
  | 11:15:06 | 2 | 3.12 | 3.01 | yes | 2.652 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:16:05 | 2 | 3.28 | 3.19 | yes | 2.788 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:17:05 | 2 | 3.33 | 3.31 | yes | 2.8305 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:18:05 | 2 | 3.28 | 3.27 | yes | 2.8305 | — |
  | 11:19:05 | 2 | 3.23 | 3.21 | yes | 2.8305 | — |
  | 11:20:07 | 2 | 3.14 | 3.1 | yes | 2.8305 | — |
  | 11:21:05 | 2 | 3.22 | 3.2 | yes | 2.8305 | — |
  | 11:22:06 | 2 | 3.11 | 3.05 | yes | 2.8305 | — |
  | 11:23:05 | 2 | 3.17 | 3.14 | yes | 2.8305 | — |
  | 11:24:05 | 2 | 3.2 | 3.19 | yes | 2.8305 | — |
  | 11:25:06 | 2 | 3.07 | 3.04 | yes | 2.8305 | — |
  | 11:26:05 | 2 | 2.91 | 2.89 | yes | 2.8305 | — |
  | 11:27:05 | 2 | 2.93 | 2.9 | yes | 2.8305 | — |
  | 11:28:05 | 2 | 2.83 | 2.74 | yes | 2.8305 | **SELL_ALL 2 `trail`** (runner_stop @ 2.83) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $959.80 (realized $475.00, delta $484.80); oracle $1,375.00.
- **Parity control** — this trade's own as-placed shape, replayed: $352.74 vs $475.00 realized (gap $-122.26 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$475.00** |
  | `tp1_100_trail_10` | $959.80 |
  | `tp1_100_trail_20` | $871.60 |
  | `all_out_at_tp1_100` | $830.00 |
  | `hold_to_time_stop` | $420.00 |
  | `all_out_at_tp1_50` | $415.00 |
  | `tp1_30_trail_125` | $247.58 |
  | `trail_only_no_tp1` | $10.00 |

### 2026-08-27 · risky-3 · `SPY260827C00770000` · realized $85.00

- **Entry** 09:42:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **767.35**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 770 (trigger 767.35, offset 2.65), quoted premium 0.7, filled **0.72** × 5, stop `0.56 (-20%)`.
- **Entry fill quality** — paid 18.0% above the signal minute's low (bar 0.61–0.77).
- **High-water WHILE IN THE TRADE** 1.23 (70.8% vs entry) at 2026-08-27T13:46:00Z UTC · 5 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.5 (247.2%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 09:47:08 | 5 | 0.89 | 23.6% | `premium_stop` | 1.23 | $170.00 (27.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:04 | 5 | 0.76 | 0.75 | no | 0.576 | — |
  | 09:44:04 | 5 | 0.94 | 0.92 | no | 0.576 | — |
  | 09:45:05 | 5 | 1.05 | 1.04 | no | 0.576 | — |
  | 09:46:05 | 5 | 1.19 | 1.18 | no | 0.936 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 09:47:05 | 5 | 0.93 | 0.92 | no | 0.936 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.94) |

- **Tags:** `runner_material_giveback`, `captured_under_half`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $360.00 (realized $85.00, delta $275.00); oracle $890.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-72.00 vs $85.00 realized (gap $-157.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$85.00** |
  | `all_out_at_tp1_100` | $360.00 |
  | `tp1_100_trail_10` | $358.20 |
  | `tp1_100_trail_20` | $334.40 |
  | `all_out_at_tp1_50` | $180.00 |
  | `tp1_30_trail_125` | $116.77 |
  | `trail_only_no_tp1` | $5.00 |
  | `hold_to_time_stop` | $-180.00 |

### 2026-08-27 · bold-2 · `SPY260827C00772000` · realized $159.00

- **Entry** 11:51:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (SKIP_MIN_PREMIUM_FLOOR), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.34** × 5, stop `?`.
- **Entry fill quality** — paid 6.2% above the signal minute's low (bar 0.32–0.39).
- **High-water WHILE IN THE TRADE** 0.74 (117.7% vs entry) at 2026-08-27T16:45:00Z UTC · 55 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.9 (164.7%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:46:04 | 3 | 0.71 | 108.8% | `tp1` | 0.74 | $9.00 (4.0%) |
  | 12:48:04 | 2 | 0.58 | 70.6% | `trail` | 0.74 | $32.00 (21.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:54:04 | 5 | 0.37 | 0.32 | no | 0.17 | — |
  | 11:55:04 | 5 | 0.38 | 0.37 | no | 0.17 | — |
  | 11:56:03 | 5 | 0.35 | 0.34 | no | 0.17 | — |
  | 11:57:04 | 5 | 0.34 | 0.33 | no | 0.17 | — |
  | 11:58:04 | 5 | 0.39 | 0.34 | no | 0.17 | — |
  | 11:59:04 | 5 | 0.33 | 0.32 | no | 0.17 | — |
  | 12:00:05 | 5 | 0.34 | 0.33 | no | 0.17 | — |
  | 12:01:04 | 5 | 0.34 | 0.33 | no | 0.17 | — |
  | 12:02:04 | 5 | 0.32 | 0.31 | no | 0.17 | — |
  | 12:03:03 | 5 | 0.38 | 0.33 | no | 0.17 | — |
  | 12:04:04 | 5 | 0.42 | 0.41 | no | 0.17 | — |
  | 12:05:09 | 5 | 0.39 | 0.34 | no | 0.17 | — |
  | 12:06:04 | 5 | 0.33 | 0.32 | no | 0.17 | — |
  | 12:07:04 | 5 | 0.32 | 0.27 | no | 0.17 | — |
  | 12:08:04 | 5 | 0.29 | 0.28 | no | 0.17 | — |
  | 12:09:04 | 5 | 0.29 | 0.24 | no | 0.17 | — |
  | 12:10:04 | 5 | 0.25 | 0.24 | no | 0.17 | — |
  | 12:11:03 | 5 | 0.3 | 0.29 | no | 0.17 | — |
  | 12:12:04 | 5 | 0.29 | 0.28 | no | 0.17 | — |
  | 12:13:04 | 5 | 0.3 | 0.25 | no | 0.17 | — |
  | 12:14:03 | 5 | 0.26 | 0.25 | no | 0.17 | — |
  | 12:15:04 | 5 | 0.26 | 0.25 | no | 0.17 | — |
  | 12:16:04 | 5 | 0.32 | 0.31 | no | 0.17 | — |
  | 12:17:04 | 5 | 0.32 | 0.27 | no | 0.17 | — |
  | 12:18:04 | 5 | 0.31 | 0.26 | no | 0.17 | — |
  | 12:19:03 | 5 | 0.29 | 0.28 | no | 0.17 | — |
  | 12:20:05 | 5 | 0.28 | 0.23 | no | 0.17 | — |
  | 12:21:03 | 5 | 0.28 | 0.23 | no | 0.17 | — |
  | 12:22:04 | 5 | 0.2 | 0.19 | no | 0.17 | — |
  | 12:23:03 | 5 | 0.25 | 0.24 | no | 0.17 | — |
  | 12:24:03 | 5 | 0.27 | 0.26 | no | 0.17 | — |
  | 12:25:04 | 5 | 0.26 | 0.25 | no | 0.17 | — |
  | 12:26:03 | 5 | 0.26 | 0.25 | no | 0.17 | — |
  | 12:27:03 | 5 | 0.27 | 0.26 | no | 0.17 | — |
  | 12:28:04 | 5 | 0.34 | 0.33 | no | 0.17 | — |
  | 12:29:04 | 5 | 0.35 | 0.34 | no | 0.17 | — |
  | 12:30:04 | 5 | 0.35 | 0.34 | no | 0.17 | — |
  | 12:31:05 | 5 | 0.3 | 0.29 | no | 0.17 | — |
  | 12:32:05 | 5 | 0.38 | 0.33 | no | 0.17 | — |
  | 12:33:04 | 5 | 0.39 | 0.34 | no | 0.17 | — |
  | 12:34:04 | 5 | 0.32 | 0.31 | no | 0.17 | — |
  | 12:35:05 | 5 | 0.41 | 0.36 | no | 0.17 | — |
  | 12:36:04 | 5 | 0.38 | 0.37 | no | 0.17 | — |
  | 12:37:04 | 5 | 0.44 | 0.43 | no | 0.17 | — |
  | 12:38:04 | 5 | 0.47 | 0.46 | no | 0.17 | — |
  | 12:39:04 | 5 | 0.48 | 0.47 | no | 0.17 | — |
  | 12:40:04 | 5 | 0.55 | 0.5 | no | 0.442 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:41:03 | 5 | 0.6 | 0.59 | no | 0.544 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:42:04 | 5 | 0.6 | 0.59 | no | 0.544 | — |
  | 12:43:04 | 5 | 0.6 | 0.55 | no | 0.544 | — |
  | 12:44:04 | 5 | 0.63 | 0.58 | no | 0.544 | — |
  | 12:45:04 | 5 | 0.61 | 0.6 | no | 0.544 | — |
  | 12:46:04 | 5 | 0.74 | 0.73 | yes | 0.34 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:47:04 | 2 | 0.64 | 0.63 | yes | 0.629 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:48:04 | 2 | 0.6 | 0.59 | yes | 0.629 | **SELL_ALL 2 `trail`** (runner_stop @ 0.63) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $170.00 (realized $159.00, delta $11.00); oracle $280.00.
- **Parity control** — this trade's own as-placed shape, replayed: $30.60 vs $159.00 realized (gap $-128.40 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$159.00** |
  | `all_out_at_tp1_100` | $170.00 |
  | `tp1_100_trail_10` | $167.20 |
  | `tp1_100_trail_20` | $152.40 |
  | `all_out_at_tp1_50` | $85.00 |
  | `tp1_30_trail_125` | $53.17 |
  | `trail_only_no_tp1` | $35.00 |
  | `hold_to_time_stop` | $-85.00 |

### 2026-08-27 · safe-3 · `SPY260827C00770000` · realized $303.00

- **Entry** 11:52:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **769.52**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 770 (trigger 769.52, offset 0.48), quoted premium 1.15, filled **1.13** × 3, stop `STRUCTURE@769.52 (cat -50%)`.
- **Entry fill quality** — paid 5.6% above the signal minute's low (bar 1.07–1.3).
- **High-water WHILE IN THE TRADE** 2.5 (121.2% vs entry) at 2026-08-27T17:10:00Z UTC · 96 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.5 (121.2%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:00:08 | 2 | 2.21 | 95.6% | `tp1` | 2.3 | $18.00 (3.9%) |
  | 13:28:06 | 1 | 2.0 | 77.0% | `trail` | 2.5 | $50.00 (20.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:53:05 | 3 | 1.27 | 1.25 | no | 0.565 | — |
  | 11:54:05 | 3 | 1.27 | 1.26 | no | 0.565 | — |
  | 11:55:06 | 3 | 1.42 | 1.37 | no | 0.565 | — |
  | 11:56:05 | 3 | 1.28 | 1.27 | no | 0.565 | — |
  | 11:57:05 | 3 | 1.29 | 1.27 | no | 0.565 | — |
  | 11:58:05 | 3 | 1.39 | 1.38 | no | 0.565 | — |
  | 11:59:05 | 3 | 1.34 | 1.29 | no | 0.565 | — |
  | 12:00:07 | 3 | 1.28 | 1.27 | no | 0.565 | — |
  | 12:01:05 | 3 | 1.26 | 1.25 | no | 0.565 | — |
  | 12:02:06 | 3 | 1.28 | 1.27 | no | 0.565 | — |
  | 12:03:05 | 3 | 1.38 | 1.37 | no | 0.565 | — |
  | 12:04:05 | 3 | 1.46 | 1.45 | no | 0.565 | — |
  | 12:05:10 | 3 | 1.38 | 1.32 | no | 0.565 | — |
  | 12:06:05 | 3 | 1.24 | 1.19 | no | 0.565 | — |
  | 12:07:05 | 3 | 1.18 | 1.17 | no | 0.565 | — |
  | 12:08:05 | 3 | 1.17 | 1.16 | no | 0.565 | — |
  | 12:09:05 | 3 | 1.18 | 1.17 | no | 0.565 | — |
  | 12:10:07 | 3 | 1.19 | 1.14 | no | 0.565 | — |
  | 12:11:05 | 3 | 1.31 | 1.3 | no | 0.565 | — |
  | 12:12:06 | 3 | 1.19 | 1.18 | no | 0.565 | — |
  | 12:13:05 | 3 | 1.18 | 1.13 | no | 0.565 | — |
  | 12:14:05 | 3 | 1.19 | 1.18 | no | 0.565 | — |
  | 12:15:07 | 3 | 1.22 | 1.21 | no | 0.565 | — |
  | 12:16:05 | 3 | 1.29 | 1.28 | no | 0.565 | — |
  | 12:17:06 | 3 | 1.24 | 1.23 | no | 0.565 | — |
  | 12:18:06 | 3 | 1.22 | 1.17 | no | 0.565 | — |
  | 12:19:05 | 3 | 1.17 | 1.16 | no | 0.565 | — |
  | 12:20:07 | 3 | 1.13 | 1.12 | no | 0.565 | — |
  | 12:21:05 | 3 | 1.15 | 1.1 | no | 0.565 | — |
  | 12:22:05 | 3 | 1.02 | 1.01 | no | 0.565 | — |
  | 12:23:05 | 3 | 1.1 | 1.05 | no | 0.565 | — |
  | 12:24:05 | 3 | 1.16 | 1.11 | no | 0.565 | — |
  | 12:25:05 | 3 | 1.12 | 1.11 | no | 0.565 | — |
  | 12:26:05 | 3 | 1.13 | 1.08 | no | 0.565 | — |
  | 12:27:05 | 3 | 1.17 | 1.16 | no | 0.565 | — |
  | 12:28:05 | 3 | 1.3 | 1.28 | no | 0.565 | — |
  | 12:29:05 | 3 | 1.36 | 1.3 | no | 0.565 | — |
  | 12:30:06 | 3 | 1.38 | 1.37 | no | 0.565 | — |
  | 12:31:05 | 3 | 1.32 | 1.3 | no | 0.565 | — |
  | 12:32:05 | 3 | 1.39 | 1.37 | no | 0.565 | — |
  | 12:33:05 | 3 | 1.46 | 1.41 | no | 0.565 | — |
  | 12:34:05 | 3 | 1.41 | 1.4 | no | 0.565 | — |
  | 12:35:06 | 3 | 1.48 | 1.47 | no | 0.565 | — |
  | 12:36:05 | 3 | 1.58 | 1.52 | no | 0.565 | — |
  | 12:37:05 | 3 | 1.6 | 1.54 | no | 0.565 | — |
  | 12:38:05 | 3 | 1.73 | 1.71 | no | 1.469 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:39:05 | 3 | 1.71 | 1.69 | no | 1.469 | — |
  | 12:40:06 | 3 | 1.82 | 1.79 | no | 1.469 | — |
  | 12:41:05 | 3 | 1.89 | 1.88 | no | 1.469 | — |
  | 12:42:05 | 3 | 1.92 | 1.87 | no | 1.469 | — |
  | 12:43:05 | 3 | 1.93 | 1.91 | no | 1.469 | — |
  | 12:44:05 | 3 | 1.94 | 1.93 | no | 1.469 | — |
  | 12:45:06 | 3 | 2.02 | 1.98 | no | 1.808 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:46:05 | 3 | 2.16 | 2.08 | no | 1.808 | — |
  | 12:47:05 | 3 | 1.98 | 1.96 | no | 1.808 | — |
  | 12:48:05 | 3 | 1.93 | 1.91 | no | 1.808 | — |
  | 12:49:05 | 3 | 2.09 | 2.06 | no | 1.808 | — |
  | 12:50:06 | 3 | 2.07 | 1.97 | no | 1.808 | — |
  | 12:51:05 | 3 | 1.96 | 1.94 | no | 1.808 | — |
  | 12:52:05 | 3 | 2.06 | 1.99 | no | 1.808 | — |
  | 12:53:05 | 3 | 2.12 | 2.09 | no | 1.808 | — |
  | 12:54:05 | 3 | 2.15 | 2.14 | no | 1.808 | — |
  | 12:55:05 | 3 | 2.15 | 2.13 | no | 1.808 | — |
  | 12:56:05 | 3 | 2.02 | 2.0 | no | 1.808 | — |
  | 12:57:05 | 3 | 2.16 | 2.14 | no | 1.808 | — |
  | 12:58:06 | 3 | 2.12 | 2.09 | no | 1.808 | — |
  | 12:59:05 | 3 | 2.11 | 2.09 | no | 1.808 | — |
  | 13:00:07 | 3 | 2.26 | 2.23 | yes | 1.13 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:01:05 | 1 | 2.26 | 2.18 | yes | 1.921 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:02:06 | 1 | 2.31 | 2.27 | yes | 1.9635 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:03:05 | 1 | 2.27 | 2.25 | yes | 1.9635 | — |
  | 13:04:05 | 1 | 2.3 | 2.26 | yes | 1.9635 | — |
  | 13:05:06 | 1 | 2.22 | 2.2 | yes | 1.9635 | — |
  | 13:06:06 | 1 | 2.22 | 2.18 | yes | 1.9635 | — |
  | 13:07:05 | 1 | 2.04 | 2.02 | yes | 1.9635 | — |
  | 13:08:06 | 1 | 2.2 | 2.16 | yes | 1.9635 | — |
  | 13:09:05 | 1 | 2.31 | 2.28 | yes | 1.9635 | — |
  | 13:10:07 | 1 | 2.4 | 2.39 | yes | 2.04 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:11:05 | 1 | 2.42 | 2.36 | yes | 2.057 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:12:06 | 1 | 2.43 | 2.39 | yes | 2.0655 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:13:05 | 1 | 2.35 | 2.34 | yes | 2.0655 | — |
  | 13:14:05 | 1 | 2.36 | 2.27 | yes | 2.0655 | — |
  | 13:15:07 | 1 | 2.34 | 2.29 | yes | 2.0655 | — |
  | 13:16:05 | 1 | 2.39 | 2.37 | yes | 2.0655 | — |
  | 13:17:05 | 1 | 2.35 | 2.32 | yes | 2.0655 | — |
  | 13:18:05 | 1 | 2.33 | 2.3 | yes | 2.0655 | — |
  | 13:19:05 | 1 | 2.33 | 2.3 | yes | 2.0655 | — |
  | 13:20:07 | 1 | 2.27 | 2.25 | yes | 2.0655 | — |
  | 13:21:05 | 1 | 2.35 | 2.24 | yes | 2.0655 | — |
  | 13:22:06 | 1 | 2.37 | 2.3 | yes | 2.0655 | — |
  | 13:23:05 | 1 | 2.27 | 2.22 | yes | 2.0655 | — |
  | 13:24:05 | 1 | 2.4 | 2.36 | yes | 2.0655 | — |
  | 13:25:07 | 1 | 2.33 | 2.3 | yes | 2.0655 | — |
  | 13:26:05 | 1 | 2.24 | 2.22 | yes | 2.0655 | — |
  | 13:27:05 | 1 | 2.11 | 2.08 | yes | 2.0655 | — |
  | 13:28:05 | 1 | 2.0 | 1.97 | yes | 2.0655 | **SELL_ALL 1 `trail`** (runner_stop @ 2.07) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $339.00 (realized $303.00, delta $36.00); oracle $411.00.
- **Parity control** — this trade's own as-placed shape, replayed: $316.88 vs $303.00 realized (gap $13.88 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$303.00** |
  | `all_out_at_tp1_100` | $339.00 |
  | `tp1_100_trail_10` | $322.70 |
  | `tp1_100_trail_20` | $313.00 |
  | `all_out_at_tp1_50` | $169.50 |
  | `tp1_30_trail_125` | $144.67 |
  | `trail_only_no_tp1` | $3.00 |
  | `hold_to_time_stop` | $-169.50 |

### 2026-08-27 · risky-1 · `SPY260827C00770000` · realized $353.00

- **Entry** 11:52:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **769.52**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 770 (trigger 769.52, offset 0.48), quoted premium 1.15, filled **1.16** × 5, stop `STRUCTURE@769.52 (cat -50%)`.
- **Entry fill quality** — paid 8.4% above the signal minute's low (bar 1.07–1.3).
- **High-water WHILE IN THE TRADE** 2.5 (115.5% vs entry) at 2026-08-27T17:10:00Z UTC · 96 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.5 (115.5%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:40:08 | 3 | 1.77 | 52.6% | `tp1` | 1.92 | $45.00 (7.8%) |
  | 13:28:08 | 2 | 2.01 | 73.3% | `trail` | 2.5 | $98.00 (19.6%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:53:05 | 5 | 1.27 | 1.26 | no | 0.58 | — |
  | 11:54:05 | 5 | 1.31 | 1.26 | no | 0.58 | — |
  | 11:55:06 | 5 | 1.41 | 1.4 | no | 0.58 | — |
  | 11:56:05 | 5 | 1.28 | 1.27 | no | 0.58 | — |
  | 11:57:05 | 5 | 1.27 | 1.22 | no | 0.58 | — |
  | 11:58:05 | 5 | 1.38 | 1.37 | no | 0.58 | — |
  | 11:59:05 | 5 | 1.35 | 1.34 | no | 0.58 | — |
  | 12:00:07 | 5 | 1.28 | 1.27 | no | 0.58 | — |
  | 12:01:05 | 5 | 1.21 | 1.2 | no | 0.58 | — |
  | 12:02:06 | 5 | 1.28 | 1.26 | no | 0.58 | — |
  | 12:03:05 | 5 | 1.38 | 1.37 | no | 0.58 | — |
  | 12:04:05 | 5 | 1.47 | 1.45 | no | 0.58 | — |
  | 12:05:10 | 5 | 1.37 | 1.36 | no | 0.58 | — |
  | 12:06:05 | 5 | 1.2 | 1.18 | no | 0.58 | — |
  | 12:07:05 | 5 | 1.18 | 1.17 | no | 0.58 | — |
  | 12:08:05 | 5 | 1.17 | 1.16 | no | 0.58 | — |
  | 12:09:05 | 5 | 1.14 | 1.13 | no | 0.58 | — |
  | 12:10:07 | 5 | 1.19 | 1.18 | no | 0.58 | — |
  | 12:11:05 | 5 | 1.31 | 1.26 | no | 0.58 | — |
  | 12:12:06 | 5 | 1.19 | 1.18 | no | 0.58 | — |
  | 12:13:05 | 5 | 1.17 | 1.16 | no | 0.58 | — |
  | 12:14:05 | 5 | 1.2 | 1.19 | no | 0.58 | — |
  | 12:15:07 | 5 | 1.22 | 1.17 | no | 0.58 | — |
  | 12:16:05 | 5 | 1.29 | 1.28 | no | 0.58 | — |
  | 12:17:06 | 5 | 1.24 | 1.23 | no | 0.58 | — |
  | 12:18:06 | 5 | 1.22 | 1.17 | no | 0.58 | — |
  | 12:19:05 | 5 | 1.18 | 1.17 | no | 0.58 | — |
  | 12:20:07 | 5 | 1.17 | 1.16 | no | 0.58 | — |
  | 12:21:05 | 5 | 1.13 | 1.08 | no | 0.58 | — |
  | 12:22:05 | 5 | 1.02 | 1.01 | no | 0.58 | — |
  | 12:23:05 | 5 | 1.07 | 1.06 | no | 0.58 | — |
  | 12:24:05 | 5 | 1.16 | 1.15 | no | 0.58 | — |
  | 12:25:05 | 5 | 1.08 | 1.07 | no | 0.58 | — |
  | 12:26:05 | 5 | 1.13 | 1.08 | no | 0.58 | — |
  | 12:27:05 | 5 | 1.17 | 1.16 | no | 0.58 | — |
  | 12:28:05 | 5 | 1.34 | 1.29 | no | 0.58 | — |
  | 12:29:05 | 5 | 1.35 | 1.3 | no | 0.58 | — |
  | 12:30:06 | 5 | 1.38 | 1.32 | no | 0.58 | — |
  | 12:31:05 | 5 | 1.35 | 1.29 | no | 0.58 | — |
  | 12:32:05 | 5 | 1.46 | 1.44 | no | 0.58 | — |
  | 12:33:05 | 5 | 1.42 | 1.41 | no | 0.58 | — |
  | 12:34:05 | 5 | 1.41 | 1.4 | no | 0.58 | — |
  | 12:35:06 | 5 | 1.47 | 1.46 | no | 0.58 | — |
  | 12:36:05 | 5 | 1.6 | 1.58 | no | 0.58 | — |
  | 12:37:05 | 5 | 1.59 | 1.58 | no | 0.58 | — |
  | 12:38:05 | 5 | 1.73 | 1.71 | no | 0.58 | — |
  | 12:39:05 | 5 | 1.7 | 1.68 | no | 0.58 | — |
  | 12:40:06 | 5 | 1.82 | 1.79 | yes | 1.16 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 12:41:05 | 2 | 1.89 | 1.88 | yes | 1.6065 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:42:05 | 2 | 1.87 | 1.86 | yes | 1.6065 | — |
  | 12:43:05 | 2 | 1.93 | 1.91 | yes | 1.6405 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:44:05 | 2 | 1.89 | 1.88 | yes | 1.6405 | — |
  | 12:45:06 | 2 | 2.01 | 1.98 | yes | 1.7085 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:46:05 | 2 | 2.14 | 2.09 | yes | 1.819 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:47:05 | 2 | 1.98 | 1.96 | yes | 1.819 | — |
  | 12:48:05 | 2 | 1.99 | 1.96 | yes | 1.819 | — |
  | 12:49:05 | 2 | 2.1 | 2.04 | yes | 1.819 | — |
  | 12:50:06 | 2 | 2.07 | 2.03 | yes | 1.819 | — |
  | 12:51:05 | 2 | 2.01 | 1.99 | yes | 1.819 | — |
  | 12:52:05 | 2 | 2.02 | 1.99 | yes | 1.819 | — |
  | 12:53:05 | 2 | 2.12 | 2.09 | yes | 1.819 | — |
  | 12:54:05 | 2 | 2.21 | 2.13 | yes | 1.8785 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 12:55:05 | 2 | 2.1 | 2.09 | yes | 1.8785 | — |
  | 12:56:05 | 2 | 1.99 | 1.96 | yes | 1.8785 | — |
  | 12:57:05 | 2 | 2.11 | 2.09 | yes | 1.8785 | — |
  | 12:58:06 | 2 | 2.13 | 2.04 | yes | 1.8785 | — |
  | 12:59:05 | 2 | 2.1 | 2.08 | yes | 1.8785 | — |
  | 13:00:07 | 2 | 2.26 | 2.23 | yes | 1.921 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:01:05 | 2 | 2.2 | 2.16 | yes | 1.921 | — |
  | 13:02:06 | 2 | 2.3 | 2.27 | yes | 1.955 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:03:05 | 2 | 2.2 | 2.16 | yes | 1.955 | — |
  | 13:04:05 | 2 | 2.25 | 2.2 | yes | 1.955 | — |
  | 13:05:06 | 2 | 2.17 | 2.15 | yes | 1.955 | — |
  | 13:06:06 | 2 | 2.2 | 2.11 | yes | 1.955 | — |
  | 13:07:05 | 2 | 2.02 | 1.97 | yes | 1.955 | — |
  | 13:08:06 | 2 | 2.2 | 2.16 | yes | 1.955 | — |
  | 13:09:05 | 2 | 2.3 | 2.21 | yes | 1.955 | — |
  | 13:10:07 | 2 | 2.42 | 2.32 | yes | 2.057 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:11:05 | 2 | 2.4 | 2.38 | yes | 2.057 | — |
  | 13:12:06 | 2 | 2.43 | 2.39 | yes | 2.0655 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:13:05 | 2 | 2.37 | 2.34 | yes | 2.0655 | — |
  | 13:14:05 | 2 | 2.34 | 2.31 | yes | 2.0655 | — |
  | 13:15:07 | 2 | 2.4 | 2.37 | yes | 2.0655 | — |
  | 13:16:05 | 2 | 2.36 | 2.31 | yes | 2.0655 | — |
  | 13:17:05 | 2 | 2.35 | 2.32 | yes | 2.0655 | — |
  | 13:18:05 | 2 | 2.32 | 2.29 | yes | 2.0655 | — |
  | 13:19:05 | 2 | 2.28 | 2.27 | yes | 2.0655 | — |
  | 13:20:07 | 2 | 2.26 | 2.24 | yes | 2.0655 | — |
  | 13:21:05 | 2 | 2.33 | 2.26 | yes | 2.0655 | — |
  | 13:22:06 | 2 | 2.38 | 2.35 | yes | 2.0655 | — |
  | 13:23:05 | 2 | 2.26 | 2.18 | yes | 2.0655 | — |
  | 13:24:05 | 2 | 2.4 | 2.37 | yes | 2.0655 | — |
  | 13:25:07 | 2 | 2.27 | 2.26 | yes | 2.0655 | — |
  | 13:26:05 | 2 | 2.24 | 2.22 | yes | 2.0655 | — |
  | 13:27:05 | 2 | 2.18 | 2.14 | yes | 2.0655 | — |
  | 13:28:05 | 2 | 1.98 | 1.97 | yes | 2.0655 | **SELL_ALL 2 `trail`** (runner_stop @ 2.07) |

- **This trade's variant grid** — best was `all_out_at_tp1_100` at $580.00 (realized $353.00, delta $227.00); oracle $670.00.
- **Parity control** — this trade's own as-placed shape, replayed: $321.74 vs $353.00 realized (gap $-31.26 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$353.00** |
  | `all_out_at_tp1_100` | $580.00 |
  | `tp1_100_trail_10` | $535.40 |
  | `tp1_100_trail_20` | $516.00 |
  | `all_out_at_tp1_50` | $290.00 |
  | `tp1_30_trail_125` | $213.07 |
  | `trail_only_no_tp1` | $-10.00 |
  | `hold_to_time_stop` | $-290.00 |

### 2026-08-27 · safe-2 · `SPY260827C00771000` · realized $184.00

- **Entry** 12:31:03 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.71** × 3, stop `STRUCTURE@770.59 (cat -50%)`.
- **Entry fill quality** — paid 1.4% above the signal minute's low (bar 0.7–0.8).
- **High-water WHILE IN THE TRADE** 1.48 (108.5% vs entry) at 2026-08-27T17:01:00Z UTC · 36 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 1.62 (128.2%) at 2026-08-27T17:10:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 13:01:03 | 1 | 1.39 | 95.8% | `trail` | 1.48 | $9.00 (6.1%) |
  | 13:01:04 | 1 | 1.38 | 94.4% | `trail` | 1.48 | $10.00 (6.8%) |
  | 13:07:03 | 1 | 1.2 | 69.0% | `trail` | 1.48 | $28.00 (18.9%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 12:32:03 | 3 | 0.76 | 0.75 | no | 0.355 | — |
  | 12:33:03 | 3 | 0.82 | 0.81 | no | 0.355 | — |
  | 12:34:03 | 3 | 0.78 | 0.77 | no | 0.355 | — |
  | 12:35:03 | 3 | 0.85 | 0.8 | no | 0.355 | — |
  | 12:36:03 | 3 | 0.84 | 0.83 | no | 0.355 | — |
  | 12:37:03 | 3 | 0.91 | 0.86 | no | 0.355 | — |
  | 12:38:03 | 3 | 0.98 | 0.97 | no | 0.355 | — |
  | 12:39:03 | 3 | 0.97 | 0.96 | no | 0.355 | — |
  | 12:40:03 | 3 | 1.1 | 1.09 | no | 0.923 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:41:02 | 3 | 1.15 | 1.14 | no | 0.923 | — |
  | 12:42:03 | 3 | 1.17 | 1.15 | no | 0.923 | — |
  | 12:43:03 | 3 | 1.16 | 1.11 | no | 0.923 | — |
  | 12:44:03 | 3 | 1.18 | 1.17 | no | 0.923 | — |
  | 12:45:03 | 3 | 1.24 | 1.23 | no | 0.923 | — |
  | 12:46:03 | 3 | 1.3 | 1.29 | no | 1.136 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:47:03 | 3 | 1.23 | 1.22 | no | 1.136 | — |
  | 12:48:03 | 3 | 1.17 | 1.16 | no | 1.136 | — |
  | 12:49:03 | 3 | 1.28 | 1.26 | no | 1.136 | — |
  | 12:50:03 | 3 | 1.21 | 1.19 | no | 1.136 | — |
  | 12:51:03 | 3 | 1.22 | 1.21 | no | 1.136 | — |
  | 12:52:03 | 3 | 1.26 | 1.21 | no | 1.136 | — |
  | 12:53:03 | 3 | 1.32 | 1.31 | no | 1.136 | — |
  | 12:54:03 | 3 | 1.33 | 1.32 | no | 1.136 | — |
  | 12:55:03 | 3 | 1.36 | 1.35 | no | 1.136 | — |
  | 12:56:02 | 3 | 1.18 | 1.17 | no | 1.136 | — |
  | 12:57:03 | 3 | 1.28 | 1.26 | no | 1.136 | — |
  | 12:58:03 | 3 | 1.29 | 1.28 | no | 1.136 | — |
  | 12:59:03 | 3 | 1.26 | 1.24 | no | 1.136 | — |
  | 13:00:04 | 3 | 1.37 | 1.35 | no | 1.136 | — |
  | 13:01:03 | 3 | 1.42 | 1.41 | yes | 0.71 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 13:02:03 | 1 | 1.46 | 1.45 | yes | 1.241 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 13:03:03 | 1 | 1.4 | 1.37 | yes | 1.241 | — |
  | 13:04:03 | 1 | 1.45 | 1.42 | yes | 1.241 | — |
  | 13:05:03 | 1 | 1.4 | 1.33 | yes | 1.241 | — |
  | 13:06:03 | 1 | 1.35 | 1.34 | yes | 1.241 | — |
  | 13:07:03 | 1 | 1.22 | 1.21 | yes | 1.241 | **SELL_ALL 1 `trail`** (runner_stop @ 1.24) |

- **This trade's variant grid** — best was `all_out_at_tp1_100` at $213.00 (realized $184.00, delta $29.00); oracle $273.00.
- **Parity control** — this trade's own as-placed shape, replayed: $142.00 vs $184.00 realized (gap $-42.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$184.00** |
  | `all_out_at_tp1_100` | $213.00 |
  | `tp1_100_trail_10` | $204.20 |
  | `tp1_100_trail_20` | $189.40 |
  | `all_out_at_tp1_50` | $106.50 |
  | `tp1_30_trail_125` | $91.47 |
  | `trail_only_no_tp1` | $12.00 |
  | `hold_to_time_stop` | $-106.50 |

### 2026-08-28 · safe-2 · `SPY260828C00771000` · realized $527.00

- **Entry** 10:21:02 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **1.74** × 3, stop `STRUCTURE@770.27 (cat -50%)`.
- **Entry fill quality** — paid 1.2% above the signal minute's low (bar 1.72–1.92).
- **High-water WHILE IN THE TRADE** 4.46 (156.3% vs entry) at 2026-08-28T15:01:00Z UTC · 48 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.46 (156.3%) at 2026-08-28T15:01:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:53:03 | 2 | 3.46 | 98.9% | `tp1` | 3.73 | $54.00 (7.2%) |
  | 11:09:03 | 1 | 3.57 | 105.2% | `trail` | 4.46 | $89.00 (20.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:22:03 | 3 | 1.86 | 1.85 | no | 0.87 | — |
  | 10:23:02 | 3 | 2.02 | 1.98 | no | 0.87 | — |
  | 10:24:03 | 3 | 1.59 | 1.58 | no | 0.87 | — |
  | 10:25:03 | 3 | 1.69 | 1.63 | no | 0.87 | — |
  | 10:26:03 | 3 | 1.44 | 1.43 | no | 0.87 | — |
  | 10:27:03 | 3 | 1.51 | 1.5 | no | 0.87 | — |
  | 10:28:03 | 3 | 1.26 | 1.24 | no | 0.87 | — |
  | 10:29:02 | 3 | 1.32 | 1.3 | no | 0.87 | — |
  | 10:30:04 | 3 | 1.45 | 1.44 | no | 0.87 | — |
  | 10:31:03 | 3 | 1.41 | 1.4 | no | 0.87 | — |
  | 10:32:03 | 3 | 1.49 | 1.43 | no | 0.87 | — |
  | 10:33:02 | 3 | 1.58 | 1.57 | no | 0.87 | — |
  | 10:34:03 | 3 | 1.88 | 1.87 | no | 0.87 | — |
  | 10:35:03 | 3 | 1.95 | 1.94 | no | 0.87 | — |
  | 10:36:03 | 3 | 2.02 | 1.96 | no | 0.87 | — |
  | 10:37:03 | 3 | 2.06 | 2.03 | no | 0.87 | — |
  | 10:38:03 | 3 | 2.14 | 2.12 | no | 0.87 | — |
  | 10:39:02 | 3 | 2.26 | 2.24 | no | 0.87 | — |
  | 10:40:04 | 3 | 2.04 | 2.01 | no | 0.87 | — |
  | 10:41:02 | 3 | 2.32 | 2.31 | no | 0.87 | — |
  | 10:42:03 | 3 | 2.32 | 2.31 | no | 0.87 | — |
  | 10:43:02 | 3 | 2.45 | 2.39 | no | 0.87 | — |
  | 10:44:03 | 3 | 2.52 | 2.49 | no | 0.87 | — |
  | 10:45:03 | 3 | 2.92 | 2.81 | no | 2.262 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:46:02 | 3 | 2.64 | 2.62 | no | 2.262 | — |
  | 10:47:03 | 3 | 2.84 | 2.81 | no | 2.262 | — |
  | 10:48:03 | 3 | 2.95 | 2.94 | no | 2.262 | — |
  | 10:49:02 | 3 | 3.12 | 3.07 | no | 2.784 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:50:03 | 3 | 3.06 | 3.04 | no | 2.784 | — |
  | 10:51:03 | 3 | 3.33 | 3.3 | no | 2.784 | — |
  | 10:52:03 | 3 | 3.33 | 3.21 | no | 2.784 | — |
  | 10:53:02 | 3 | 3.55 | 3.52 | yes | 1.74 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:54:03 | 1 | 3.78 | 3.76 | yes | 3.213 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:55:03 | 1 | 3.8 | 3.77 | yes | 3.23 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:56:03 | 1 | 3.94 | 3.91 | yes | 3.349 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:57:03 | 1 | 3.98 | 3.95 | yes | 3.383 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:58:03 | 1 | 4.0 | 3.98 | yes | 3.4 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:59:02 | 1 | 4.14 | 4.11 | yes | 3.519 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:00:03 | 1 | 4.2 | 4.18 | yes | 3.57 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:01:03 | 1 | 4.4 | 4.37 | yes | 3.74 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:02:03 | 1 | 4.28 | 4.18 | yes | 3.74 | — |
  | 11:03:02 | 1 | 4.16 | 4.13 | yes | 3.74 | — |
  | 11:04:03 | 1 | 4.23 | 4.2 | yes | 3.74 | — |
  | 11:05:03 | 1 | 4.06 | 4.03 | yes | 3.74 | — |
  | 11:06:03 | 1 | 4.08 | 4.06 | yes | 3.74 | — |
  | 11:07:03 | 1 | 4.03 | 3.93 | yes | 3.74 | — |
  | 11:08:03 | 1 | 3.86 | 3.85 | yes | 3.74 | — |
  | 11:09:02 | 1 | 3.66 | 3.63 | yes | 3.74 | **SELL_ALL 1 `trail`** (runner_stop @ 3.74) |

- **This trade's variant grid** — best was `tp1_100_trail_10` at $575.40 (realized $527.00, delta $48.40); oracle $816.00.
- **Parity control** — this trade's own as-placed shape, replayed: $348.00 vs $527.00 realized (gap $-179.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$527.00** |
  | `tp1_100_trail_10` | $575.40 |
  | `tp1_100_trail_20` | $530.80 |
  | `all_out_at_tp1_100` | $522.00 |
  | `all_out_at_tp1_50` | $261.00 |
  | `tp1_30_trail_125` | $137.77 |
  | `trail_only_no_tp1` | $-24.00 |
  | `hold_to_time_stop` | $-261.00 |

### 2026-08-28 · bold-2 · `SPY260828C00773000` · realized $509.00

- **Entry** 10:21:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.73** × 5, stop `STRUCTURE@770.27 (cat -50%)`.
- **Entry fill quality** — paid 1.4% above the signal minute's low (bar 0.72–0.83).
- **High-water WHILE IN THE TRADE** 2.66 (264.4% vs entry) at 2026-08-28T15:01:00Z UTC · 47 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.66 (264.4%) at 2026-08-28T15:01:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:49:04 | 3 | 1.48 | 102.7% | `tp1` | 1.59 | $33.00 (6.9%) |
  | 11:08:05 | 2 | 2.15 | 194.5% | `trail` | 2.66 | $102.00 (19.2%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:22:05 | 5 | 0.8 | 0.79 | no | 0.365 | — |
  | 10:23:04 | 5 | 0.84 | 0.79 | no | 0.365 | — |
  | 10:24:05 | 5 | 0.65 | 0.64 | no | 0.365 | — |
  | 10:25:05 | 5 | 0.69 | 0.68 | no | 0.365 | — |
  | 10:26:04 | 5 | 0.59 | 0.58 | no | 0.365 | — |
  | 10:27:04 | 5 | 0.56 | 0.55 | no | 0.365 | — |
  | 10:28:04 | 5 | 0.48 | 0.43 | no | 0.365 | — |
  | 10:29:03 | 5 | 0.5 | 0.49 | no | 0.365 | — |
  | 10:30:05 | 5 | 0.58 | 0.57 | no | 0.365 | — |
  | 10:31:04 | 5 | 0.53 | 0.52 | no | 0.365 | — |
  | 10:32:04 | 5 | 0.57 | 0.56 | no | 0.365 | — |
  | 10:33:03 | 5 | 0.62 | 0.61 | no | 0.365 | — |
  | 10:34:04 | 5 | 0.79 | 0.74 | no | 0.365 | — |
  | 10:35:04 | 5 | 0.87 | 0.82 | no | 0.365 | — |
  | 10:36:04 | 5 | 0.89 | 0.88 | no | 0.365 | — |
  | 10:37:04 | 5 | 0.9 | 0.89 | no | 0.365 | — |
  | 10:38:04 | 5 | 0.88 | 0.87 | no | 0.365 | — |
  | 10:39:03 | 5 | 1.01 | 1.0 | no | 0.365 | — |
  | 10:40:05 | 5 | 0.89 | 0.88 | no | 0.365 | — |
  | 10:41:03 | 5 | 1.07 | 1.06 | no | 0.365 | — |
  | 10:42:04 | 5 | 0.99 | 0.94 | no | 0.365 | — |
  | 10:43:03 | 5 | 1.09 | 1.08 | no | 0.365 | — |
  | 10:44:04 | 5 | 1.22 | 1.21 | no | 0.949 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:45:04 | 5 | 1.37 | 1.36 | no | 1.168 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:46:03 | 5 | 1.26 | 1.25 | no | 1.168 | — |
  | 10:47:04 | 5 | 1.42 | 1.36 | no | 1.168 | — |
  | 10:48:04 | 5 | 1.43 | 1.38 | no | 1.168 | — |
  | 10:49:03 | 5 | 1.52 | 1.51 | yes | 0.73 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:50:04 | 2 | 1.57 | 1.52 | yes | 1.3345 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:51:04 | 2 | 1.75 | 1.74 | yes | 1.4875 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:52:04 | 2 | 1.67 | 1.65 | yes | 1.4875 | — |
  | 10:53:03 | 2 | 1.82 | 1.81 | yes | 1.547 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:54:04 | 2 | 2.1 | 2.08 | yes | 1.785 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:55:04 | 2 | 2.09 | 2.02 | yes | 1.785 | — |
  | 10:56:05 | 2 | 2.2 | 2.12 | yes | 1.87 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:57:05 | 2 | 2.24 | 2.2 | yes | 1.904 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:58:05 | 2 | 2.31 | 2.27 | yes | 1.9635 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:59:03 | 2 | 2.32 | 2.29 | yes | 1.972 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:00:05 | 2 | 2.39 | 2.37 | yes | 2.0315 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:01:04 | 2 | 2.66 | 2.57 | yes | 2.261 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:02:05 | 2 | 2.54 | 2.51 | yes | 2.261 | — |
  | 11:03:04 | 2 | 2.38 | 2.37 | yes | 2.261 | — |
  | 11:04:05 | 2 | 2.44 | 2.39 | yes | 2.261 | — |
  | 11:05:05 | 2 | 2.32 | 2.28 | yes | 2.261 | — |
  | 11:06:04 | 2 | 2.35 | 2.29 | yes | 2.261 | — |
  | 11:07:04 | 2 | 2.29 | 2.27 | yes | 2.261 | — |
  | 11:08:04 | 2 | 2.21 | 2.18 | yes | 2.261 | **SELL_ALL 2 `trail`** (runner_stop @ 2.26) |

- **This trade's variant grid** — best was `tp1_100_trail_20` at $584.00 (realized $509.00, delta $75.00); oracle $965.00.
- **Parity control** — this trade's own as-placed shape, replayed: $584.00 vs $509.00 realized (gap $75.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$509.00** |
  | `tp1_100_trail_20` | $584.00 |
  | `all_out_at_tp1_100` | $365.00 |
  | `tp1_100_trail_10` | $350.20 |
  | `all_out_at_tp1_50` | $182.50 |
  | `tp1_30_trail_125` | $100.35 |
  | `trail_only_no_tp1` | $60.00 |
  | `hold_to_time_stop` | $-182.50 |

### 2026-08-28 · safe-3 · `SPY260828C00771000` · realized $563.00

- **Entry** 10:22:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **770.27**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 8->3: recency RED_
- **Strike** 771 (trigger 770.27, offset 0.73), quoted premium 1.81, filled **1.84** × 3, stop `STRUCTURE@770.27 (cat -50%)`.
- **Entry fill quality** — paid 4.0% above the signal minute's low (bar 1.77–2.05).
- **High-water WHILE IN THE TRADE** 4.46 (142.4% vs entry) at 2026-08-28T15:01:00Z UTC · 47 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.46 (142.4%) at 2026-08-28T15:01:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:54:06 | 2 | 3.77 | 104.9% | `tp1` | 3.89 | $24.00 (3.1%) |
  | 11:09:06 | 1 | 3.61 | 96.2% | `trail` | 4.46 | $85.00 (19.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:23:05 | 3 | 1.9 | 1.89 | no | 0.92 | — |
  | 10:24:05 | 3 | 1.57 | 1.56 | no | 0.92 | — |
  | 10:25:07 | 3 | 1.68 | 1.66 | no | 0.92 | — |
  | 10:26:05 | 3 | 1.47 | 1.46 | no | 0.92 | — |
  | 10:27:05 | 3 | 1.51 | 1.5 | no | 0.92 | — |
  | 10:28:06 | 3 | 1.24 | 1.19 | no | 0.92 | — |
  | 10:29:05 | 3 | 1.31 | 1.3 | no | 0.92 | — |
  | 10:30:07 | 3 | 1.48 | 1.47 | no | 0.92 | — |
  | 10:31:05 | 3 | 1.4 | 1.39 | no | 0.92 | — |
  | 10:32:05 | 3 | 1.47 | 1.45 | no | 0.92 | — |
  | 10:33:05 | 3 | 1.57 | 1.52 | no | 0.92 | — |
  | 10:34:05 | 3 | 1.89 | 1.87 | no | 0.92 | — |
  | 10:35:06 | 3 | 2.01 | 2.0 | no | 0.92 | — |
  | 10:36:05 | 3 | 1.99 | 1.97 | no | 0.92 | — |
  | 10:37:05 | 3 | 2.06 | 2.05 | no | 0.92 | — |
  | 10:38:05 | 3 | 2.12 | 2.06 | no | 0.92 | — |
  | 10:39:05 | 3 | 2.22 | 2.2 | no | 0.92 | — |
  | 10:40:06 | 3 | 2.06 | 2.03 | no | 0.92 | — |
  | 10:41:05 | 3 | 2.4 | 2.3 | no | 0.92 | — |
  | 10:42:05 | 3 | 2.25 | 2.22 | no | 0.92 | — |
  | 10:43:05 | 3 | 2.45 | 2.43 | no | 0.92 | — |
  | 10:44:05 | 3 | 2.67 | 2.61 | no | 0.92 | — |
  | 10:45:06 | 3 | 2.84 | 2.82 | no | 2.392 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:46:05 | 3 | 2.66 | 2.65 | no | 2.392 | — |
  | 10:47:05 | 3 | 2.94 | 2.9 | no | 2.392 | — |
  | 10:48:05 | 3 | 2.89 | 2.87 | no | 2.392 | — |
  | 10:49:05 | 3 | 3.05 | 3.02 | no | 2.392 | — |
  | 10:50:06 | 3 | 3.15 | 3.08 | no | 2.392 | — |
  | 10:51:05 | 3 | 3.35 | 3.33 | no | 2.944 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 10:52:05 | 3 | 3.28 | 3.21 | no | 2.944 | — |
  | 10:53:05 | 3 | 3.47 | 3.45 | no | 2.944 | — |
  | 10:54:05 | 3 | 3.85 | 3.75 | yes | 1.84 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:55:06 | 1 | 3.81 | 3.78 | yes | 3.2725 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:56:05 | 1 | 3.85 | 3.83 | yes | 3.2725 | — |
  | 10:57:05 | 1 | 3.99 | 3.96 | yes | 3.3915 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:58:06 | 1 | 4.07 | 4.04 | yes | 3.4595 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:59:05 | 1 | 4.14 | 3.98 | yes | 3.519 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:00:07 | 1 | 4.11 | 4.08 | yes | 3.519 | — |
  | 11:01:05 | 1 | 4.47 | 4.32 | yes | 3.7995 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:02:06 | 1 | 4.31 | 4.28 | yes | 3.7995 | — |
  | 11:03:05 | 1 | 4.13 | 4.06 | yes | 3.7995 | — |
  | 11:04:05 | 1 | 4.22 | 4.1 | yes | 3.7995 | — |
  | 11:05:06 | 1 | 4.01 | 3.99 | yes | 3.7995 | — |
  | 11:06:05 | 1 | 4.16 | 4.13 | yes | 3.7995 | — |
  | 11:07:05 | 1 | 4.0 | 3.97 | yes | 3.7995 | — |
  | 11:08:05 | 1 | 3.92 | 3.81 | yes | 3.7995 | — |
  | 11:09:05 | 1 | 3.64 | 3.63 | yes | 3.7995 | **SELL_ALL 1 `trail`** (runner_stop @ 3.8) |

- **Tags:** `runner_underperformed_tp1`
- **This trade's variant grid** — best was `tp1_100_trail_10` at $585.40 (realized $563.00, delta $22.40); oracle $786.00.
- **Parity control** — this trade's own as-placed shape, replayed: $574.25 vs $563.00 realized (gap $11.25 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$563.00** |
  | `tp1_100_trail_10` | $585.40 |
  | `all_out_at_tp1_100` | $552.00 |
  | `tp1_100_trail_20` | $540.80 |
  | `all_out_at_tp1_50` | $276.00 |
  | `tp1_30_trail_125` | $181.90 |
  | `trail_only_no_tp1` | $-54.00 |
  | `hold_to_time_stop` | $-276.00 |

### 2026-08-28 · risky-1 · `SPY260828C00771000` · realized $650.00

- **Entry** 10:22:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **770.27**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: recency RED_
- **Strike** 771 (trigger 770.27, offset 0.73), quoted premium 1.83, filled **1.85** × 5, stop `STRUCTURE@770.27 (cat -50%)`.
- **Entry fill quality** — paid 4.5% above the signal minute's low (bar 1.77–2.05).
- **High-water WHILE IN THE TRADE** 4.46 (141.1% vs entry) at 2026-08-28T15:01:00Z UTC · 47 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.46 (141.1%) at 2026-08-28T15:01:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 10:45:09 | 3 | 2.87 | 55.1% | `tp1` | 2.92 | $15.00 (1.7%) |
  | 11:09:07 | 2 | 3.57 | 93.0% | `trail` | 4.46 | $178.00 (20.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 10:23:05 | 5 | 1.89 | 1.88 | no | 0.925 | — |
  | 10:24:05 | 5 | 1.58 | 1.56 | no | 0.925 | — |
  | 10:25:07 | 5 | 1.7 | 1.69 | no | 0.925 | — |
  | 10:26:05 | 5 | 1.48 | 1.47 | no | 0.925 | — |
  | 10:27:05 | 5 | 1.47 | 1.46 | no | 0.925 | — |
  | 10:28:06 | 5 | 1.26 | 1.25 | no | 0.925 | — |
  | 10:29:05 | 5 | 1.33 | 1.32 | no | 0.925 | — |
  | 10:30:07 | 5 | 1.52 | 1.46 | no | 0.925 | — |
  | 10:31:05 | 5 | 1.42 | 1.41 | no | 0.925 | — |
  | 10:32:05 | 5 | 1.56 | 1.55 | no | 0.925 | — |
  | 10:33:05 | 5 | 1.55 | 1.54 | no | 0.925 | — |
  | 10:34:05 | 5 | 1.89 | 1.87 | no | 0.925 | — |
  | 10:35:06 | 5 | 2.04 | 2.03 | no | 0.925 | — |
  | 10:36:05 | 5 | 2.04 | 2.03 | no | 0.925 | — |
  | 10:37:05 | 5 | 2.13 | 2.05 | no | 0.925 | — |
  | 10:38:05 | 5 | 2.12 | 2.1 | no | 0.925 | — |
  | 10:39:05 | 5 | 2.23 | 2.22 | no | 0.925 | — |
  | 10:40:06 | 5 | 2.04 | 2.0 | no | 0.925 | — |
  | 10:41:05 | 5 | 2.39 | 2.31 | no | 0.925 | — |
  | 10:42:05 | 5 | 2.24 | 2.22 | no | 0.925 | — |
  | 10:43:05 | 5 | 2.44 | 2.35 | no | 0.925 | — |
  | 10:44:05 | 5 | 2.67 | 2.61 | no | 0.925 | — |
  | 10:45:06 | 5 | 2.84 | 2.82 | yes | 1.85 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 10:46:05 | 2 | 2.65 | 2.64 | yes | 2.414 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:47:05 | 2 | 2.92 | 2.91 | yes | 2.482 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:48:05 | 2 | 2.89 | 2.87 | yes | 2.482 | — |
  | 10:49:05 | 2 | 3.05 | 3.02 | yes | 2.5925 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:50:06 | 2 | 3.18 | 3.14 | yes | 2.703 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:51:05 | 2 | 3.37 | 3.34 | yes | 2.8645 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:52:05 | 2 | 3.34 | 3.31 | yes | 2.8645 | — |
  | 10:53:05 | 2 | 3.39 | 3.34 | yes | 2.8815 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:54:05 | 2 | 3.82 | 3.73 | yes | 3.247 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:55:06 | 2 | 3.78 | 3.71 | yes | 3.247 | — |
  | 10:56:05 | 2 | 3.91 | 3.89 | yes | 3.3235 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:57:05 | 2 | 3.99 | 3.96 | yes | 3.3915 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:58:06 | 2 | 4.09 | 4.06 | yes | 3.4765 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 10:59:05 | 2 | 3.97 | 3.96 | yes | 3.4765 | — |
  | 11:00:07 | 2 | 4.11 | 4.08 | yes | 3.4935 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:01:05 | 2 | 4.36 | 4.35 | yes | 3.706 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:02:06 | 2 | 4.3 | 4.28 | yes | 3.706 | — |
  | 11:03:05 | 2 | 4.18 | 4.03 | yes | 3.706 | — |
  | 11:04:05 | 2 | 4.23 | 4.2 | yes | 3.706 | — |
  | 11:05:06 | 2 | 4.14 | 4.11 | yes | 3.706 | — |
  | 11:06:05 | 2 | 4.14 | 4.03 | yes | 3.706 | — |
  | 11:07:05 | 2 | 3.98 | 3.95 | yes | 3.706 | — |
  | 11:08:05 | 2 | 3.85 | 3.83 | yes | 3.706 | — |
  | 11:09:05 | 2 | 3.7 | 3.68 | yes | 3.706 | **SELL_ALL 2 `trail`** (runner_stop @ 3.71) |

- **This trade's variant grid** — best was `tp1_100_trail_10` at $987.80 (realized $650.00, delta $337.80); oracle $1,305.00.
- **Parity control** — this trade's own as-placed shape, replayed: $688.00 vs $650.00 realized (gap $38.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$650.00** |
  | `tp1_100_trail_10` | $987.80 |
  | `all_out_at_tp1_100` | $925.00 |
  | `tp1_100_trail_20` | $898.60 |
  | `all_out_at_tp1_50` | $462.50 |
  | `tp1_30_trail_125` | $292.50 |
  | `trail_only_no_tp1` | $-95.00 |
  | `hold_to_time_stop` | $-462.50 |

### 2026-09-01 · safe-2 · `SPY260901P00762000` · realized $338.00

- **Entry** 13:21:03 ET — `BEARISH_REJECTION_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier TRENDLINE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.94** × 3, stop `STRUCTURE@762.39 (cat -50%)`.
- **Entry fill quality** — paid 3.3% above the signal minute's low (bar 0.91–1.03).
- **High-water WHILE IN THE TRADE** 2.59 (175.5% vs entry) at 2026-09-01T18:45:00Z UTC · 87 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.59 (175.5%) at 2026-09-01T18:45:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 14:43:04 | 2 | 2.04 | 117.0% | `tp1` | 2.22 | $36.00 (8.1%) |
  | 14:48:04 | 1 | 2.12 | 125.5% | `trail` | 2.59 | $47.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 13:22:03 | 3 | 0.91 | 0.9 | no | 0.47 | — |
  | 13:23:03 | 3 | 0.97 | 0.96 | no | 0.47 | — |
  | 13:24:03 | 3 | 1.02 | 0.97 | no | 0.47 | — |
  | 13:25:03 | 3 | 0.96 | 0.91 | no | 0.47 | — |
  | 13:26:03 | 3 | 1.07 | 1.05 | no | 0.47 | — |
  | 13:27:03 | 3 | 1.22 | 1.21 | no | 0.47 | — |
  | 13:28:03 | 3 | 0.97 | 0.96 | no | 0.47 | — |
  | 13:29:03 | 3 | 0.95 | 0.94 | no | 0.47 | — |
  | 13:30:04 | 3 | 0.9 | 0.88 | no | 0.47 | — |
  | 13:31:03 | 3 | 0.86 | 0.85 | no | 0.47 | — |
  | 13:32:03 | 3 | 0.77 | 0.72 | no | 0.47 | — |
  | 13:33:03 | 3 | 0.83 | 0.81 | no | 0.47 | — |
  | 13:34:03 | 3 | 0.8 | 0.75 | no | 0.47 | — |
  | 13:35:04 | 3 | 0.75 | 0.74 | no | 0.47 | — |
  | 13:36:03 | 3 | 0.69 | 0.68 | no | 0.47 | — |
  | 13:37:03 | 3 | 0.75 | 0.74 | no | 0.47 | — |
  | 13:38:03 | 3 | 0.72 | 0.71 | no | 0.47 | — |
  | 13:39:03 | 3 | 0.78 | 0.73 | no | 0.47 | — |
  | 13:40:04 | 3 | 0.77 | 0.76 | no | 0.47 | — |
  | 13:41:03 | 3 | 0.78 | 0.73 | no | 0.47 | — |
  | 13:42:03 | 3 | 0.68 | 0.67 | no | 0.47 | — |
  | 13:43:03 | 3 | 0.62 | 0.61 | no | 0.47 | — |
  | 13:44:03 | 3 | 0.65 | 0.64 | no | 0.47 | — |
  | 13:45:04 | 3 | 0.66 | 0.65 | no | 0.47 | — |
  | 13:46:03 | 3 | 0.7 | 0.65 | no | 0.47 | — |
  | 13:47:03 | 3 | 0.86 | 0.85 | no | 0.47 | — |
  | 13:48:03 | 3 | 0.76 | 0.75 | no | 0.47 | — |
  | 13:49:03 | 3 | 0.82 | 0.81 | no | 0.47 | — |
  | 13:50:04 | 3 | 0.92 | 0.91 | no | 0.47 | — |
  | 13:51:03 | 3 | 0.9 | 0.89 | no | 0.47 | — |
  | 13:52:03 | 3 | 0.82 | 0.81 | no | 0.47 | — |
  | 13:53:03 | 3 | 0.89 | 0.88 | no | 0.47 | — |
  | 13:54:03 | 3 | 0.92 | 0.91 | no | 0.47 | — |
  | 13:55:22 | 3 | 0.91 | 0.9 | no | 0.47 | — |
  | 13:56:03 | 3 | 0.94 | 0.88 | no | 0.47 | — |
  | 13:57:03 | 3 | 0.97 | 0.96 | no | 0.47 | — |
  | 13:58:03 | 3 | 0.94 | 0.93 | no | 0.47 | — |
  | 13:59:03 | 3 | 0.76 | 0.71 | no | 0.47 | — |
  | 14:00:04 | 3 | 0.77 | 0.72 | no | 0.47 | — |
  | 14:01:03 | 3 | 0.81 | 0.8 | no | 0.47 | — |
  | 14:02:03 | 3 | 0.84 | 0.78 | no | 0.47 | — |
  | 14:03:03 | 3 | 0.7 | 0.69 | no | 0.47 | — |
  | 14:04:07 | 3 | 0.85 | 0.8 | no | 0.47 | — |
  | 14:05:04 | 3 | 0.86 | 0.85 | no | 0.47 | — |
  | 14:06:03 | 3 | 0.95 | 0.94 | no | 0.47 | — |
  | 14:07:03 | 3 | 0.98 | 0.97 | no | 0.47 | — |
  | 14:08:03 | 3 | 0.84 | 0.83 | no | 0.47 | — |
  | 14:09:03 | 3 | 0.87 | 0.86 | no | 0.47 | — |
  | 14:10:04 | 3 | 0.86 | 0.85 | no | 0.47 | — |
  | 14:11:03 | 3 | 0.91 | 0.9 | no | 0.47 | — |
  | 14:12:03 | 3 | 0.9 | 0.89 | no | 0.47 | — |
  | 14:13:04 | 3 | 0.93 | 0.92 | no | 0.47 | — |
  | 14:14:03 | 3 | 1.04 | 1.03 | no | 0.47 | — |
  | 14:15:04 | 3 | 1.03 | 1.02 | no | 0.47 | — |
  | 14:16:03 | 3 | 0.99 | 0.98 | no | 0.47 | — |
  | 14:17:03 | 3 | 0.95 | 0.9 | no | 0.47 | — |
  | 14:18:03 | 3 | 0.74 | 0.73 | no | 0.47 | — |
  | 14:19:03 | 3 | 0.73 | 0.72 | no | 0.47 | — |
  | 14:20:04 | 3 | 0.79 | 0.78 | no | 0.47 | — |
  | 14:21:03 | 3 | 0.76 | 0.75 | no | 0.47 | — |
  | 14:22:03 | 3 | 0.81 | 0.76 | no | 0.47 | — |
  | 14:23:03 | 3 | 0.81 | 0.8 | no | 0.47 | — |
  | 14:24:03 | 3 | 0.87 | 0.81 | no | 0.47 | — |
  | 14:25:04 | 3 | 0.95 | 0.94 | no | 0.47 | — |
  | 14:26:03 | 3 | 0.86 | 0.85 | no | 0.47 | — |
  | 14:27:03 | 3 | 0.93 | 0.88 | no | 0.47 | — |
  | 14:28:03 | 3 | 1.14 | 1.08 | no | 0.47 | — |
  | 14:29:03 | 3 | 1.19 | 1.17 | no | 0.47 | — |
  | 14:30:04 | 3 | 1.08 | 1.07 | no | 0.47 | — |
  | 14:31:03 | 3 | 1.19 | 1.18 | no | 0.47 | — |
  | 14:32:03 | 3 | 1.34 | 1.33 | no | 0.47 | — |
  | 14:33:03 | 3 | 1.18 | 1.17 | no | 0.47 | — |
  | 14:34:03 | 3 | 1.4 | 1.34 | no | 0.47 | — |
  | 14:35:04 | 3 | 1.41 | 1.4 | no | 1.222 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:36:03 | 3 | 1.4 | 1.38 | no | 1.222 | — |
  | 14:37:03 | 3 | 1.44 | 1.41 | no | 1.222 | — |
  | 14:38:03 | 3 | 1.52 | 1.51 | no | 1.222 | — |
  | 14:39:03 | 3 | 1.53 | 1.52 | no | 1.222 | — |
  | 14:40:03 | 3 | 1.62 | 1.55 | no | 1.222 | — |
  | 14:41:03 | 3 | 1.66 | 1.61 | no | 1.504 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 14:42:03 | 3 | 1.84 | 1.82 | no | 1.504 | — |
  | 14:43:03 | 3 | 2.12 | 2.03 | yes | 0.94 | **SELL_PARTIAL 2 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 14:44:03 | 1 | 2.22 | 2.2 | yes | 1.887 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:45:04 | 1 | 2.31 | 2.3 | yes | 1.9635 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:46:03 | 1 | 2.61 | 2.58 | yes | 2.2185 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 14:47:03 | 1 | 2.28 | 2.24 | yes | 2.2185 | — |
  | 14:48:03 | 1 | 2.16 | 2.13 | yes | 2.2185 | **SELL_ALL 1 `trail`** (runner_stop @ 2.22) |

- **Tags:** `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `tp1_100_trail_20` at $301.20 (realized $338.00, delta $-36.80); oracle $495.00.
- **Parity control** — this trade's own as-placed shape, replayed: $188.00 vs $338.00 realized (gap $-150.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$338.00** |
  | `tp1_100_trail_20` | $301.20 |
  | `tp1_100_trail_10` | $293.80 |
  | `all_out_at_tp1_100` | $282.00 |
  | `all_out_at_tp1_50` | $141.00 |
  | `tp1_30_trail_125` | $93.65 |
  | `trail_only_no_tp1` | $18.00 |
  | `hold_to_time_stop` | $0.00 |

### 2026-09-02 · bold-2 · `SPY260902C00767000` · realized $55.00

- **Entry** 11:56:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (PLACED), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.31** × 5, stop `STRUCTURE@765.14 (cat -50%)`.
- **Entry fill quality** — paid 6.9% above the signal minute's low (bar 0.29–0.32).
- **High-water WHILE IN THE TRADE** 0.5 (61.3% vs entry) at 2026-09-02T15:59:00Z UTC · 6 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.5 (61.3%) at 2026-09-02T15:59:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 12:02:05 | 5 | 0.42 | 35.5% | `premium_stop` | 0.5 | $40.00 (16.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:57:04 | 5 | 0.32 | 0.27 | no | 0.155 | — |
  | 11:58:04 | 5 | 0.36 | 0.35 | no | 0.155 | — |
  | 11:59:04 | 5 | 0.47 | 0.46 | no | 0.403 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 12:00:06 | 5 | 0.48 | 0.43 | no | 0.403 | — |
  | 12:01:05 | 5 | 0.44 | 0.43 | no | 0.403 | — |
  | 12:02:04 | 5 | 0.41 | 0.4 | no | 0.403 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.4) |

- **This trade's variant grid** — best was `all_out_at_tp1_50` at $77.50 (realized $55.00, delta $22.50); oracle $95.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-77.50 vs $55.00 realized (gap $-132.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$55.00** |
  | `all_out_at_tp1_50` | $77.50 |
  | `tp1_30_trail_125` | $49.95 |
  | `trail_only_no_tp1` | $10.00 |
  | `all_out_at_tp1_100` | $-77.50 |
  | `tp1_100_trail_20` | $-77.50 |
  | `tp1_100_trail_10` | $-77.50 |
  | `hold_to_time_stop` | $-77.50 |

### 2026-09-03 · bold-2 · `SPY260903C00772000` · realized $199.00

- **Entry** 09:41:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (SKIP_MIN_PREMIUM_FLOOR), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.37** × 5, stop `?`.
- **Entry fill quality** — paid 23.3% above the signal minute's low (bar 0.3–0.39).
- **High-water WHILE IN THE TRADE** 0.98 (164.9% vs entry) at 2026-09-03T15:19:00Z UTC · 31 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.1 (467.6%) at 2026-09-03T18:15:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:16:04 | 3 | 0.78 | 110.8% | `tp1` | 0.85 | $21.00 (8.2%) |
  | 11:21:05 | 2 | 0.75 | 102.7% | `trail` | 0.98 | $46.00 (23.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:05 | 5 | 0.34 | 0.33 | no | 0.185 | — |
  | 09:44:05 | 5 | 0.31 | 0.26 | no | 0.185 | — |
  | 09:45:06 | 5 | 0.36 | 0.31 | no | 0.185 | — |
  | 09:46:06 | 5 | 0.31 | 0.3 | no | 0.185 | — |
  | 09:47:05 | 5 | 0.36 | 0.35 | no | 0.185 | — |
  | 09:48:05 | 5 | 0.37 | 0.36 | no | 0.185 | — |
  | 09:49:05 | 5 | 0.31 | 0.26 | no | 0.185 | — |
  | 09:50:06 | 5 | 0.33 | 0.32 | no | 0.185 | — |
  | 09:51:05 | 5 | 0.31 | 0.3 | no | 0.185 | — |
  | 09:52:04 | 5 | 0.38 | 0.33 | no | 0.185 | — |
  | 09:53:04 | 5 | 0.29 | 0.28 | no | 0.185 | — |
  | 09:54:04 | 5 | 0.25 | 0.24 | no | 0.185 | — |
  | 09:55:05 | 5 | 0.3 | 0.29 | no | 0.185 | — |
  | 09:56:04 | 5 | 0.26 | 0.21 | no | 0.185 | — |
  | 09:57:05 | 5 | 0.2 | 0.19 | no | 0.185 | — |
  | 09:58:04 | 5 | 0.23 | 0.18 | no | 0.185 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.18) |
  | 11:07:04 | 5 | 0.33 | 0.32 | no | 0.185 | — |
  | 11:08:04 | 5 | 0.36 | 0.35 | no | 0.185 | — |
  | 11:09:04 | 5 | 0.44 | 0.39 | no | 0.185 | — |
  | 11:10:05 | 5 | 0.41 | 0.36 | no | 0.185 | — |
  | 11:11:04 | 5 | 0.47 | 0.46 | no | 0.185 | — |
  | 11:12:04 | 5 | 0.54 | 0.53 | no | 0.185 | — |
  | 11:13:04 | 5 | 0.58 | 0.53 | no | 0.481 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:14:04 | 5 | 0.66 | 0.61 | no | 0.592 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:15:05 | 5 | 0.7 | 0.69 | no | 0.592 | — |
  | 11:16:04 | 5 | 0.8 | 0.79 | yes | 0.37 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:17:04 | 2 | 0.87 | 0.86 | yes | 0.7395 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:18:04 | 2 | 0.81 | 0.8 | yes | 0.7395 | — |
  | 11:19:04 | 2 | 0.92 | 0.91 | yes | 0.782 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:20:07 | 2 | 0.99 | 0.94 | yes | 0.8415 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:21:04 | 2 | 0.74 | 0.73 | yes | 0.8415 | **SELL_ALL 2 `trail`** (runner_stop @ 0.84) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $465.00 (realized $199.00, delta $266.00); oracle $865.00.
- **Parity control** — this trade's own as-placed shape, replayed: $218.30 vs $199.00 realized (gap $19.30 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$199.00** |
  | `hold_to_time_stop` | $465.00 |
  | `tp1_100_trail_20` | $193.80 |
  | `tp1_100_trail_10` | $190.00 |
  | `all_out_at_tp1_100` | $185.00 |
  | `all_out_at_tp1_50` | $92.50 |
  | `tp1_30_trail_125` | $64.27 |
  | `trail_only_no_tp1` | $5.00 |

### 2026-09-03 · safe-3 · `SPY260903C00770000` · realized $507.00

- **Entry** 09:42:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **769.36**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty capped 8->5: tight-ladder max_contracts_per_entry_
- **Strike** 770 (trigger 769.36, offset 0.64), quoted premium 1.1, filled **1.17** × 5, stop `STRUCTURE@769.36 (cat -50%)`.
- **Entry fill quality** — paid 2.6% above the signal minute's low (bar 1.14–1.32).
- **High-water WHILE IN THE TRADE** 2.38 (103.4% vs entry) at 2026-09-03T15:19:00Z UTC · 33 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.0 (241.9%) at 2026-09-03T18:15:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:19:06 | 3 | 2.32 | 98.3% | `tp1` | 2.38 | $18.00 (2.5%) |
  | 11:21:06 | 2 | 1.98 | 69.2% | `trail` | 2.38 | $80.00 (16.8%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:05 | 5 | 1.02 | 1.01 | no | 0.555 | — |
  | 09:44:05 | 5 | 0.95 | 0.94 | no | 0.555 | — |
  | 09:45:06 | 5 | 1.09 | 1.08 | no | 0.555 | — |
  | 09:46:05 | 5 | 1.07 | 1.02 | no | 0.555 | — |
  | 09:47:05 | 5 | 1.09 | 1.08 | no | 0.555 | — |
  | 09:48:05 | 5 | 1.13 | 1.08 | no | 0.555 | — |
  | 09:49:05 | 5 | 0.93 | 0.92 | no | 0.555 | — |
  | 09:50:07 | 5 | 1.02 | 1.01 | no | 0.555 | — |
  | 09:51:05 | 5 | 1.03 | 1.02 | no | 0.555 | — |
  | 09:52:05 | 5 | 1.14 | 1.13 | no | 0.555 | — |
  | 09:53:05 | 5 | 1.05 | 1.0 | no | 0.555 | — |
  | 09:54:05 | 5 | 0.91 | 0.9 | no | 0.555 | — |
  | 09:55:05 | 5 | 0.94 | 0.89 | no | 0.555 | — |
  | 09:56:05 | 5 | 0.83 | 0.82 | no | 0.555 | — |
  | 09:57:05 | 5 | 0.75 | 0.74 | no | 0.555 | — |
  | 09:58:05 | 5 | 0.73 | 0.72 | no | 0.555 | — |
  | 09:59:05 | 5 | 0.8 | 0.75 | no | 0.555 | — |
  | 10:00:07 | 5 | 0.7 | 0.69 | no | 0.555 | — |
  | 10:01:05 | 5 | 0.56 | 0.55 | no | 0.555 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.56) |
  | 11:08:05 | 5 | 1.33 | 1.32 | no | 0.585 | — |
  | 11:09:06 | 5 | 1.4 | 1.39 | no | 0.585 | — |
  | 11:10:07 | 5 | 1.39 | 1.34 | no | 0.585 | — |
  | 11:11:06 | 5 | 1.52 | 1.46 | no | 0.585 | — |
  | 11:12:06 | 5 | 1.78 | 1.77 | no | 1.521 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:13:05 | 5 | 1.73 | 1.71 | no | 1.521 | — |
  | 11:14:05 | 5 | 1.86 | 1.85 | no | 1.521 | — |
  | 11:15:07 | 5 | 1.98 | 1.93 | no | 1.521 | — |
  | 11:16:05 | 5 | 2.08 | 2.02 | no | 1.872 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:17:05 | 5 | 2.25 | 2.23 | no | 1.872 | — |
  | 11:18:05 | 5 | 2.11 | 2.1 | no | 1.872 | — |
  | 11:19:05 | 5 | 2.37 | 2.36 | yes | 1.17 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:20:09 | 2 | 2.36 | 2.35 | yes | 2.0145 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:21:05 | 2 | 1.98 | 1.97 | yes | 2.0145 | **SELL_ALL 2 `trail`** (runner_stop @ 2.01) |

- **Tags:** `runner_underperformed_tp1`, `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $1,020.00 (realized $507.00, delta $513.00); oracle $1,415.00.
- **Parity control** — this trade's own as-placed shape, replayed: $533.50 vs $507.00 realized (gap $26.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$507.00** |
  | `hold_to_time_stop` | $1,020.00 |
  | `trail_only_no_tp1` | $855.00 |
  | `tp1_100_trail_20` | $673.80 |
  | `all_out_at_tp1_100` | $585.00 |
  | `tp1_100_trail_10` | $545.40 |
  | `all_out_at_tp1_50` | $292.50 |
  | `tp1_30_trail_125` | $174.77 |

### 2026-09-03 · risky-1 · `SPY260903C00770000` · realized $343.00

- **Entry** 09:42:05 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **769.36**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: FULL_SEND min size_
- **Strike** 770 (trigger 769.36, offset 0.64), quoted premium 1.1, filled **1.18** × 5, stop `STRUCTURE@769.36 (cat -50%)`.
- **Entry fill quality** — paid 3.5% above the signal minute's low (bar 1.14–1.32).
- **High-water WHILE IN THE TRADE** 2.38 (101.7% vs entry) at 2026-09-03T15:19:00Z UTC · 34 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 4.0 (239.0%) at 2026-09-03T18:15:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:14:07 | 3 | 1.81 | 53.4% | `tp1` | 1.92 | $33.00 (5.7%) |
  | 11:21:07 | 2 | 1.95 | 65.2% | `trail` | 2.38 | $86.00 (18.1%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 09:43:05 | 5 | 1.02 | 1.01 | no | 0.54 | — |
  | 09:44:05 | 5 | 0.95 | 0.94 | no | 0.54 | — |
  | 09:45:06 | 5 | 1.08 | 1.07 | no | 0.54 | — |
  | 09:46:05 | 5 | 1.02 | 1.01 | no | 0.54 | — |
  | 09:47:05 | 5 | 1.09 | 1.04 | no | 0.54 | — |
  | 09:48:05 | 5 | 1.11 | 1.06 | no | 0.54 | — |
  | 09:49:05 | 5 | 0.96 | 0.91 | no | 0.54 | — |
  | 09:50:07 | 5 | 0.97 | 0.96 | no | 0.54 | — |
  | 09:51:05 | 5 | 1.04 | 1.03 | no | 0.54 | — |
  | 09:52:05 | 5 | 1.15 | 1.14 | no | 0.54 | — |
  | 09:53:05 | 5 | 1.05 | 1.04 | no | 0.54 | — |
  | 09:54:05 | 5 | 0.95 | 0.94 | no | 0.54 | — |
  | 09:55:05 | 5 | 0.93 | 0.92 | no | 0.54 | — |
  | 09:56:05 | 5 | 0.84 | 0.83 | no | 0.54 | — |
  | 09:57:05 | 5 | 0.78 | 0.73 | no | 0.54 | — |
  | 09:58:05 | 5 | 0.71 | 0.7 | no | 0.54 | — |
  | 09:59:05 | 5 | 0.81 | 0.8 | no | 0.54 | — |
  | 10:00:07 | 5 | 0.7 | 0.68 | no | 0.54 | — |
  | 10:01:05 | 5 | 0.6 | 0.55 | no | 0.54 | — |
  | 10:02:06 | 5 | 0.5 | 0.49 | no | 0.54 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.54) |
  | 11:08:05 | 5 | 1.32 | 1.31 | no | 0.59 | — |
  | 11:09:06 | 5 | 1.39 | 1.38 | no | 0.59 | — |
  | 11:10:07 | 5 | 1.34 | 1.33 | no | 0.59 | — |
  | 11:11:06 | 5 | 1.48 | 1.47 | no | 0.59 | — |
  | 11:12:06 | 5 | 1.76 | 1.75 | no | 0.59 | — |
  | 11:13:05 | 5 | 1.75 | 1.73 | no | 0.59 | — |
  | 11:14:05 | 5 | 1.83 | 1.78 | yes | 1.18 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:15:07 | 2 | 2.01 | 1.97 | yes | 1.7085 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:16:05 | 2 | 2.08 | 2.07 | yes | 1.768 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:17:05 | 2 | 2.27 | 2.25 | yes | 1.9295 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:18:05 | 2 | 2.16 | 2.1 | yes | 1.9295 | — |
  | 11:19:05 | 2 | 2.38 | 2.29 | yes | 2.023 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:20:09 | 2 | 2.37 | 2.25 | yes | 2.023 | — |
  | 11:21:05 | 2 | 2.03 | 2.02 | yes | 2.023 | **SELL_ALL 2 `trail`** (runner_stop @ 2.02) |

- **Tags:** `captured_under_half`
- **This trade's variant grid** — best was `hold_to_time_stop` at $1,015.00 (realized $343.00, delta $672.00); oracle $1,410.00.
- **Parity control** — this trade's own as-placed shape, replayed: $357.50 vs $343.00 realized (gap $14.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$343.00** |
  | `hold_to_time_stop` | $1,015.00 |
  | `trail_only_no_tp1` | $850.00 |
  | `tp1_100_trail_20` | $674.80 |
  | `all_out_at_tp1_100` | $590.00 |
  | `tp1_100_trail_10` | $546.40 |
  | `all_out_at_tp1_50` | $295.00 |
  | `tp1_30_trail_125` | $174.97 |

### 2026-09-03 · bold-2 · `SPY260903C00774000` · realized $85.00

- **Entry** 11:21:04 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (SKIP_MIN_PREMIUM_FLOOR), quality **?**, trigger **None**, risk `None`.
  - engine's own words: _BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)_
- **Strike** None (trigger None, offset None), quoted premium None, filled **0.39** × 5, stop `?`.
- **Entry fill quality** — paid 5.4% above the signal minute's low (bar 0.37–0.47).
- **High-water WHILE IN THE TRADE** 0.76 (94.9% vs entry) at 2026-09-03T15:31:00Z UTC · 7 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 0.76 (94.9%) at 2026-09-03T15:31:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:34:05 | 5 | 0.56 | 43.6% | `premium_stop` | 0.76 | $100.00 (26.3%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:28:04 | 5 | 0.42 | 0.41 | no | 0.195 | — |
  | 11:29:04 | 5 | 0.49 | 0.48 | no | 0.195 | — |
  | 11:30:06 | 5 | 0.61 | 0.6 | no | 0.507 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:31:04 | 5 | 0.72 | 0.71 | no | 0.624 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:32:04 | 5 | 0.74 | 0.73 | no | 0.624 | — |
  | 11:33:04 | 5 | 0.67 | 0.66 | no | 0.624 | — |
  | 11:34:04 | 5 | 0.55 | 0.54 | no | 0.624 | **SELL_ALL 5 `premium_stop`** (premium_stop @ 0.62) |

- **Tags:** `runner_material_giveback`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $125.00 (realized $85.00, delta $40.00); oracle $185.00.
- **Parity control** — this trade's own as-placed shape, replayed: $35.10 vs $85.00 realized (gap $-49.90 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$85.00** |
  | `trail_only_no_tp1` | $125.00 |
  | `all_out_at_tp1_50` | $97.50 |
  | `tp1_30_trail_125` | $70.80 |
  | `all_out_at_tp1_100` | $-97.50 |
  | `tp1_100_trail_20` | $-97.50 |
  | `tp1_100_trail_10` | $-97.50 |
  | `hold_to_time_stop` | $-97.50 |

### 2026-09-03 · safe-3 · `SPY260903C00772000` · realized $433.00

- **Entry** 11:22:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **771.88**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty capped 8->5: tight-ladder max_contracts_per_entry_
- **Strike** 772 (trigger 771.88, offset 0.12), quoted premium 0.73, filled **0.74** × 5, stop `STRUCTURE@771.88 (cat -50%)`.
- **Entry fill quality** — paid 1.4% above the signal minute's low (bar 0.73–0.93).
- **High-water WHILE IN THE TRADE** 1.88 (154.1% vs entry) at 2026-09-03T15:31:00Z UTC · 12 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.1 (183.8%) at 2026-09-03T18:15:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:30:09 | 3 | 1.63 | 120.3% | `tp1` | 1.83 | $60.00 (10.9%) |
  | 11:34:07 | 2 | 1.57 | 112.2% | `trail` | 1.88 | $62.00 (16.5%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:23:06 | 5 | 0.93 | 0.92 | no | 0.37 | — |
  | 11:24:06 | 5 | 1.05 | 1.04 | no | 0.37 | — |
  | 11:25:06 | 5 | 1.06 | 1.0 | no | 0.37 | — |
  | 11:26:06 | 5 | 1.11 | 1.1 | no | 0.962 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:27:06 | 5 | 1.29 | 1.28 | no | 0.962 | — |
  | 11:28:06 | 5 | 1.41 | 1.36 | no | 1.184 | **RATCHET_STOP  `trail`** (pre_tp1 profit_lock arm/trail) |
  | 11:29:05 | 5 | 1.47 | 1.46 | no | 1.184 | — |
  | 11:30:08 | 5 | 1.63 | 1.62 | yes | 0.74 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +100%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:31:05 | 2 | 1.84 | 1.83 | yes | 1.564 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:32:05 | 2 | 1.84 | 1.78 | yes | 1.564 | — |
  | 11:33:05 | 2 | 1.73 | 1.71 | yes | 1.564 | — |
  | 11:34:06 | 2 | 1.6 | 1.55 | yes | 1.564 | **SELL_ALL 2 `trail`** (runner_stop @ 1.56) |

- **Tags:** `runner_underperformed_tp1`, `shipped_exit_beat_menu`
- **This trade's variant grid** — best was `trail_only_no_tp1` at $405.00 (realized $433.00, delta $-28.00); oracle $680.00.
- **Parity control** — this trade's own as-placed shape, replayed: $394.26 vs $433.00 realized (gap $-38.74 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$433.00** |
  | `trail_only_no_tp1` | $405.00 |
  | `tp1_100_trail_10` | $403.40 |
  | `tp1_100_trail_20` | $374.80 |
  | `all_out_at_tp1_100` | $370.00 |
  | `hold_to_time_stop` | $280.00 |
  | `all_out_at_tp1_50` | $185.00 |
  | `tp1_30_trail_125` | $111.93 |

### 2026-09-03 · risky-1 · `SPY260903C00772000` · realized $314.00

- **Entry** 11:22:06 ET — `BULLISH_RECLAIM_RIDE_THE_RIBBON` (ENTER_BULL), quality **ELITE**, trigger **771.88**, risk `ALLOW`.
  - engine's own words: _ribbon_ride C (ELITE); qty clamped 12->5: FULL_SEND min size_
- **Strike** 772 (trigger 771.88, offset 0.12), quoted premium 0.78, filled **0.76** × 5, stop `STRUCTURE@771.88 (cat -50%)`.
- **Entry fill quality** — paid 4.1% above the signal minute's low (bar 0.73–0.93).
- **High-water WHILE IN THE TRADE** 1.88 (147.4% vs entry) at 2026-09-03T15:31:00Z UTC · 12 managed ticks.
- **High-water AFTER entry, day-scoped** (includes time we were already flat — this is what the oracle bounds, NOT what the position saw): 2.1 (176.3%) at 2026-09-03T18:15:00Z UTC.
- **Exit legs** (which rule closed each, and what it gave back):

  | ET | qty | price | vs entry | closed by | peak avail. | giveback |
  |---|---:|---:|---:|---|---:|---:|
  | 11:27:08 | 3 | 1.26 | 65.8% | `tp1` | 1.43 | $51.00 (11.9%) |
  | 11:34:08 | 2 | 1.58 | 107.9% | `trail` | 1.88 | $60.00 (16.0%) |

- **In-trade timeline** (the engine's own per-tick exit_pass record):

  | ET | open | best | worst | TP1? | runner stop | action |
  |---|---:|---:|---:|---|---:|---|
  | 11:23:06 | 5 | 0.89 | 0.88 | no | 0.38 | — |
  | 11:24:06 | 5 | 1.09 | 1.08 | no | 0.38 | — |
  | 11:25:06 | 5 | 1.06 | 1.0 | no | 0.38 | — |
  | 11:26:06 | 5 | 1.11 | 1.1 | no | 0.38 | — |
  | 11:27:06 | 5 | 1.29 | 1.24 | yes | 0.76 | **SELL_PARTIAL 3 `tp1`** (tp1 @ +50%); **RATCHET_STOP  `tp1`** (runner_stop->BE) |
  | 11:28:06 | 2 | 1.41 | 1.36 | yes | 1.1985 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:29:05 | 2 | 1.52 | 1.47 | yes | 1.292 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:30:08 | 2 | 1.65 | 1.64 | yes | 1.4025 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:31:05 | 2 | 1.86 | 1.85 | yes | 1.581 | **RATCHET_STOP  `trail`** (runner_stop trail/arm) |
  | 11:32:05 | 2 | 1.84 | 1.78 | yes | 1.581 | — |
  | 11:33:05 | 2 | 1.71 | 1.7 | yes | 1.581 | — |
  | 11:34:06 | 2 | 1.62 | 1.57 | yes | 1.581 | **SELL_ALL 2 `trail`** (runner_stop @ 1.58) |

- **This trade's variant grid** — best was `tp1_100_trail_10` at $405.40 (realized $314.00, delta $91.40); oracle $670.00.
- **Parity control** — this trade's own as-placed shape, replayed: $212.24 vs $314.00 realized (gap $-101.76 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$314.00** |
  | `tp1_100_trail_10` | $405.40 |
  | `trail_only_no_tp1` | $395.00 |
  | `all_out_at_tp1_100` | $380.00 |
  | `tp1_100_trail_20` | $376.80 |
  | `hold_to_time_stop` | $270.00 |
  | `all_out_at_tp1_50` | $190.00 |
  | `tp1_30_trail_125` | $112.33 |

---

### Method / known biases (read before quoting any number)

- **Realized** P&L is broker-fill truth from `fills-ledger.jsonl`. Every other number is a replay on real 1-min OPRA bars.
- **entry+1**: a position is not exit-eligible until the bar AFTER its entry bar, matching the live tick order (exits are managed before entries). See `markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md`.
- **Intrabar optimism**: `replay_position` evaluates each bar with its own high as `best_premium` and low as `worst_premium`. A TP that triggers intrabar is assumed filled at the target. This flatters the VARIANTS relative to realized fills, so true capture is likely HIGHER than the headline — the bias runs against us, not for us.
- **Structure stops are not modelled.** `replay_position` never supplies `last_closed_5m_close`, so chart-stop exits cannot fire in any variant; the variants use the -50% premium catastrophe cap instead. Trades whose live exit was `structure_stop` therefore diverge most from their replays.
- **Slippage**: variant fills are modelled at the rule's target price; real fills cross the spread. On 0DTE options this is material.
- **`capture_vs_best_policy` is the only non-hindsight number here.** The per-trade-best and oracle figures are upper bounds published for disclosure.
