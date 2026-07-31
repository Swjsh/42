# Winner autopsy — all winners to date

_Generated 2026-07-31T17:54:26.640955 ET · real OPRA 1-min bars · entry+1 convention · $0 (pure Python)._

> **DESCRIPTIVE ONLY.** This report measures; it ratifies nothing. Every exit variant below is a replay, not a proposal. Any change to a live exit knob requires its own pre-registered A/B — a good-looking number on a small winner population is an anecdote, not evidence.

## Capture rate — how much of what our winners offered did we keep?

- **CAPTURE (honest headline): 101.9%** of the best single fixed policy, over **n=21** winners.
  - Realized (broker fills): **$3,479.00**
  - Best single fixed policy: `all_out_at_tp1_100` → $3,414.50
- Disclosure — *hindsight shape-picking* (best variant chosen per trade, NOT live-selectable): 63.7% of $5,464.93.
- Disclosure — *oracle* (sell 100% at the post-entry high; no live rule can do this): 26.3% of $13,234.00.

**⚠ WINNERS-ONLY SAMPLE — this is NOT a policy comparison.** Every number here is computed over trades that ALREADY WON. That conditions on the outcome: a policy's column total answers 'what would this policy have made on the trades our current exits happened to win', NOT 'what would this policy make'. Switching policy changes which trades win at all, and says nothing about its effect on the losers — which vastly outnumber these. A capture rate above 100% therefore means our shipped exits top this menu ON WINNERS; it is NOT evidence that the menu's runner-up should be adopted, and a capture rate below 100% is NOT evidence that it should. Only a pre-registered A/B over the FULL trade population can support an exit change.

## The runner question (J 2026-07-31: "stay in longer, or get better exits?")

- **7 of 11** scaled-out winners had the RUNNER realize a **lower price than TP1** — the runner leg, which exists to capture the upside, came out worse than the leg that took profit early.
- **7 of 11** gave back ≥25% of the premium the runner had already reached.
- **Median runner-leg giveback: 32.4%** of its own peak (n=11 runner legs).

_This is a DESCRIPTIVE recurrence, not a mandate. Note the two answers point in opposite directions: the giveback is real, but the 'just hold longer' policies (`trail_only_no_tp1` / `hold_to_time_stop`) are usually the WORST column in the table above. 'Exit better' and 'stay in longer' are different hypotheses and only the first is supported here — both need their own pre-registered A/B over the full population before anything is armed._
- Attribution coverage: 86.1% of exit legs matched to an engine stage (5/36 unattributed and shown as `?`).

### Fixed-policy totals over the same winners

| Policy | Total P&L | vs realized |
|---|---:|---:|
| **(shipped, realized)** | **$3,479.00** | — |
| `all_out_at_tp1_100` | $3,414.50 | $-64.50 |
| `tp1_100_trail_10` | $3,352.30 | $-126.70 |
| `tp1_100_trail_20` | $3,108.50 | $-370.50 |
| `all_out_at_tp1_50` | $1,821.00 | $-1,658.00 |
| `tp1_30_trail_125` | $1,260.15 | $-2,218.85 |
| `trail_only_no_tp1` | $-451.50 | $-3,930.50 |
| `hold_to_time_stop` | $-451.50 | $-3,930.50 |

_Every policy above is live-executable: each is a replay through the real `exit_manager.plan_exit_actions` on real 1-min OPRA bars. The menu is declared once in `EXIT_MENU` and is never fitted per-run._

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
  | `tp1_30_trail_125` | $43.00 |
  | `trail_only_no_tp1` | $-75.00 |
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
  | `tp1_30_trail_125` | $72.80 |
  | `trail_only_no_tp1` | $-122.50 |
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
  | `trail_only_no_tp1` | $-105.00 |
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
  | `all_out_at_tp1_100` | $-81.00 |
  | `tp1_100_trail_20` | $-81.00 |
  | `tp1_100_trail_10` | $-81.00 |
  | `trail_only_no_tp1` | $-81.00 |
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
  | `all_out_at_tp1_100` | $-75.00 |
  | `tp1_100_trail_20` | $-75.00 |
  | `tp1_100_trail_10` | $-75.00 |
  | `trail_only_no_tp1` | $-75.00 |
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
  | `all_out_at_tp1_100` | $-78.00 |
  | `tp1_100_trail_20` | $-78.00 |
  | `tp1_100_trail_10` | $-78.00 |
  | `trail_only_no_tp1` | $-78.00 |
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
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $-40.00 (realized $8.00, delta $-48.00); oracle $112.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-16.00 vs $8.00 realized (gap $-24.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$8.00** |
  | `all_out_at_tp1_100` | $-40.00 |
  | `all_out_at_tp1_50` | $-40.00 |
  | `tp1_30_trail_125` | $-40.00 |
  | `tp1_100_trail_20` | $-40.00 |
  | `tp1_100_trail_10` | $-40.00 |
  | `trail_only_no_tp1` | $-40.00 |
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
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $-115.00 (realized $15.00, delta $-130.00); oracle $45.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-115.00 vs $15.00 realized (gap $-130.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$15.00** |
  | `all_out_at_tp1_100` | $-115.00 |
  | `all_out_at_tp1_50` | $-115.00 |
  | `tp1_30_trail_125` | $-115.00 |
  | `tp1_100_trail_20` | $-115.00 |
  | `tp1_100_trail_10` | $-115.00 |
  | `trail_only_no_tp1` | $-115.00 |
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
  | `trail_only_no_tp1` | $123.00 |
  | `hold_to_time_stop` | $123.00 |
  | `tp1_30_trail_125` | $91.25 |

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

- **This trade's variant grid** — best was `trail_only_no_tp1` at $474.00 (realized $241.00, delta $233.00); oracle $930.00.
- **Parity control** — this trade's own as-placed shape, replayed: $46.80 vs $241.00 realized (gap $-194.20 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$241.00** |
  | `trail_only_no_tp1` | $474.00 |
  | `hold_to_time_stop` | $474.00 |
  | `tp1_100_trail_20` | $243.60 |
  | `all_out_at_tp1_100` | $234.00 |
  | `tp1_100_trail_10` | $232.80 |
  | `all_out_at_tp1_50` | $117.00 |
  | `tp1_30_trail_125` | $68.55 |

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
  | `trail_only_no_tp1` | $-95.00 |
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
  | `trail_only_no_tp1` | $-97.50 |
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
- **This trade's variant grid** — best was `all_out_at_tp1_100` at $-192.00 (realized $18.00, delta $-210.00); oracle $78.00.
- **Parity control** — this trade's own as-placed shape, replayed: $-192.00 vs $18.00 realized (gap $-210.00 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$18.00** |
  | `all_out_at_tp1_100` | $-192.00 |
  | `all_out_at_tp1_50` | $-192.00 |
  | `tp1_30_trail_125` | $-192.00 |
  | `tp1_100_trail_20` | $-192.00 |
  | `tp1_100_trail_10` | $-192.00 |
  | `trail_only_no_tp1` | $-192.00 |
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
  | `all_out_at_tp1_100` | $-127.50 |
  | `all_out_at_tp1_50` | $-127.50 |
  | `tp1_100_trail_20` | $-127.50 |
  | `tp1_100_trail_10` | $-127.50 |
  | `trail_only_no_tp1` | $-127.50 |
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
  | `trail_only_no_tp1` | $-234.00 |
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
  | `trail_only_no_tp1` | $-390.00 |
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
  | `trail_only_no_tp1` | $-127.50 |
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
  | `trail_only_no_tp1` | $-210.00 |
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
  | `trail_only_no_tp1` | $-210.50 |
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
- **This trade's variant grid** — best was `trail_only_no_tp1` at $1,000.00 (realized $126.00, delta $874.00); oracle $1,250.00.
- **Parity control** — this trade's own as-placed shape, replayed: $148.50 vs $126.00 realized (gap $22.50 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$126.00** |
  | `trail_only_no_tp1` | $1,000.00 |
  | `hold_to_time_stop` | $1,000.00 |
  | `all_out_at_tp1_100` | $165.00 |
  | `tp1_100_trail_10` | $151.80 |
  | `tp1_100_trail_20` | $146.60 |
  | `all_out_at_tp1_50` | $82.50 |
  | `tp1_30_trail_125` | $56.47 |

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
- **This trade's variant grid** — best was `trail_only_no_tp1` at $327.00 (realized $75.00, delta $252.00); oracle $480.00.
- **Parity control** — this trade's own as-placed shape, replayed: $92.12 vs $75.00 realized (gap $17.12 = slippage + tick granularity + unmodelled structure stop). Treat that gap as the error bar on every variant below.

  | Variant | P&L |
  |---|---:|
  | **(shipped, realized)** | **$75.00** |
  | `trail_only_no_tp1` | $327.00 |
  | `hold_to_time_stop` | $327.00 |
  | `tp1_100_trail_10` | $93.90 |
  | `all_out_at_tp1_100` | $90.00 |
  | `tp1_100_trail_20` | $86.80 |
  | `all_out_at_tp1_50` | $45.00 |
  | `tp1_30_trail_125` | $22.12 |

---

### Method / known biases (read before quoting any number)

- **Realized** P&L is broker-fill truth from `fills-ledger.jsonl`. Every other number is a replay on real 1-min OPRA bars.
- **entry+1**: a position is not exit-eligible until the bar AFTER its entry bar, matching the live tick order (exits are managed before entries). See `markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md`.
- **Intrabar optimism**: `replay_position` evaluates each bar with its own high as `best_premium` and low as `worst_premium`. A TP that triggers intrabar is assumed filled at the target. This flatters the VARIANTS relative to realized fills, so true capture is likely HIGHER than the headline — the bias runs against us, not for us.
- **Structure stops are not modelled.** `replay_position` never supplies `last_closed_5m_close`, so chart-stop exits cannot fire in any variant; the variants use the -50% premium catastrophe cap instead. Trades whose live exit was `structure_stop` therefore diverge most from their replays.
- **Slippage**: variant fills are modelled at the rule's target price; real fills cross the spread. On 0DTE options this is material.
- **`capture_vs_best_policy` is the only non-hindsight number here.** The per-trade-best and oracle figures are upper bounds published for disclosure.
