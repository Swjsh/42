# ARM SCORE LADDER V1 -- Replay Evidence Table (2026-07-27)

ANALYSIS ONLY. No orders placed, no live config touched. Built per J's standing '6 accounts = risk ladder' design (repeated multiple times) after today's 09:40 textbook rejection scored bear_score 9/10 and took NOTHING because entry currently requires zero blockers. This table answers: under a pure score-threshold ladder (no other change), which arms would have entered each of these 10 named anchors, at what size, and would the REAL risk_gate have allowed the order.

**Ladder used (--ladder to change):** `{"risky-3": 7, "risky-1": 8, "bold-2": 8, "safe-3": 9, "safe-2": 9}`

**Calibration anchor (A5, 2026-07-27 09:40) reproduced on first try: YES** (bear_score=9, blockers=[5], level_rejection in raw triggers, rejection_level=744.9 -- pinned by backtest/tests/test_why_not_provenance.py).

## Summary matrix (rows = 10 anchors, cols = 5 arms, cells = IN@score / OUT@score)

| Anchor | Outcome $ | risky-3 | risky-1 | bold-2 | safe-3 | safe-2 |
|---|---|---|---|---|---|---|
| A5_2026-07-27_0940_MISSED | MISSED | IN@9 | IN@9 | IN@9 | IN@9 | IN@9 |
| A1_2026-04-29_710P | +$342 | OUT@6 | OUT@6 | OUT@6 | OUT@6 | OUT@6 |
| A2_2026-05-01_721P | +$470 | OUT@4 | OUT@4 | OUT@4 | OUT@4 | OUT@4 |
| A3_2026-05-04_721P | +$730 | IN@8 | IN@8 | IN@8 | OUT@8 | OUT@8 |
| A4_2026-07-17_746P | +$241 | OUT@7 | OUT@7 | OUT@7 | OUT@7 | OUT@7 |
| A6_2026-05-05_722P | -$260 | OUT@5 | OUT@5 | OUT@5 | OUT@5 | OUT@5 |
| A7_2026-05-06_730P | -$300 | OUT@4 | OUT@4 | OUT@4 | OUT@4 | OUT@4 |
| A8_2026-05-07_734C | -$45 | OUT@9 | OUT@9 | OUT@9 | OUT@9 | OUT@9 |
| A9_2026-05-07_737C | -$120 | OUT@7 | OUT@7 | OUT@7 | OUT@7 | OUT@7 |
| A10_2026-07-23_735P | -$305 | IN@10 | IN@10 | IN@10 | IN@10 | IN@10 |


## Discrimination check -- how many of the 5 LOSERS does each threshold let in

The point of a ladder is discrimination, not just participation. A ladder that lets every loser in at every threshold is not a ladder.

| Arm | Threshold | Losers let IN (of 5) |
|---|---|---|
| FLEET-LOOSE-R (X15Q) | 7 | 1 / 5 |
| FLEET-TIGHT-R (8G19) | 8 | 1 / 5 |
| CORE-BOLD (AT40) | 8 | 1 / 5 |
| FLEET-TIGHT-S (OB0Q) | 9 | 1 / 5 |
| CORE-SAFE (KIQE) | 9 | 1 / 5 |


## Per-anchor detail

### A5_2026-07-27_0940_MISSED -- MISSED (engine took NOTHING; the ladder calibration anchor)
- Date/time: 2026-07-27 09:40 bar, evaluated 09:46-09:50
- Real score: **9** (side=P), blockers=[5], raw triggers=['level_rejection', 'confluence'], rejection/reclaim level=744.9, confluence=744.9
- Levels provenance: PINNED per backtest/tests/test_why_not_provenance.py's real-IEX-bar + 'the real level set' fixture (proven to reproduce the live incident's logged bear_score 9 / blockers [5])

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 9/10 (need 7) | IN | SPY 2026-07-27 740P (OTM-3) | 23 | ALLOW | $0.40 [SYNTHETIC] |
| FLEET-TIGHT-R (8G19) | 9/10 (need 8) | IN | SPY 2026-07-27 740P (OTM-3) | 17 | ALLOW | $0.40 [SYNTHETIC] |
| CORE-BOLD (AT40) | 9/10 (need 8) | IN | SPY 2026-07-27 743P (ATM) | 5 | ALLOW | $1.33 [SYNTHETIC] |
| FLEET-TIGHT-S (OB0Q) | 9/10 (need 9) | IN | SPY 2026-07-27 740P (OTM-3) | 12 | ALLOW | $0.40 [SYNTHETIC] |
| CORE-SAFE (KIQE) | 9/10 (need 9) | IN | SPY 2026-07-27 743P (ATM) | 3 | DENY[RISK_CAP] | $1.33 [SYNTHETIC] |

### A1_2026-04-29_710P -- WINNER (+$342 real, BEARISH_REJECTION_RIDE_THE_RIBBON)
- Date/time: 2026-04-29 10:25:51  
- Time note: matches task brief (~10:25 ET)
- Real score: **6** (side=P), blockers=[6, 8, 9, 10], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 6/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 6/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 6/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 6/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 6/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A2_2026-05-01_721P -- WINNER (+$470 real, BEARISH_REJECTION_RIDE_THE_RIBBON)
- Date/time: 2026-05-01 13:09:14  
- Time note: task brief said ~11:50 ET; REAL fill per journal/trades.csv is 13:09:14 ET -- used the real time
- Real score: **4** (side=P), blockers=[5, 7, 8, 9, 10], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 4/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 4/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 4/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 4/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 4/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A3_2026-05-04_721P -- WINNER (+$730 real, BEARISH_REJECTION_RIDE_THE_RIBBON)
- Date/time: 2026-05-04 10:27:50  
- Time note: matches task brief (entry time from trades.csv)
- Real score: **8** (side=P), blockers=[8, 9], raw triggers=['level_rejection', 'trendline_rejection'], rejection/reclaim level=721.6, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 8/10 (need 7) | IN | SPY 2026-05-04 718P (OTM-3) | 33 | ALLOW | $0.27 [real] |
| FLEET-TIGHT-R (8G19) | 8/10 (need 8) | IN | SPY 2026-05-04 718P (OTM-3) | 26 | ALLOW | $0.27 [real] |
| CORE-BOLD (AT40) | 8/10 (need 8) | IN | SPY 2026-05-04 721P (ATM) | 8 | ALLOW | $0.85 [real] |
| FLEET-TIGHT-S (OB0Q) | 8/10 (need 9) | OUT | -- (score below threshold) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 8/10 (need 9) | OUT | -- (score below threshold) | -- | N/A | -- |

### A4_2026-07-17_746P -- WINNER (+$241 real, BEARISH_REJECTION_RIDE_THE_RIBBON)
- Date/time: 2026-07-17 13:01:19  
- Time note: matches task brief (~13:0x ET); qty/pnl = the 2+1 core-safe fill pair (156+85=241)
- Real score: **7** (side=P), blockers=[5, 9, 10], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 7/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 7/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 7/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 7/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 7/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A6_2026-05-05_722P -- LOSER (-$260 real, UNCATEGORIZED_PROBE)
- Date/time: 2026-05-05 13:00:33  
- Time note: from trades.csv (setup logged as UNCATEGORIZED_PROBE, not the named playbook pattern)
- Real score: **5** (side=P), blockers=[5, 8, 9, 10], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 5/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 5/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 5/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 5/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 5/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A7_2026-05-06_730P -- LOSER (-$300 real, UNCATEGORIZED_HOLD_TO_EXPIRY)
- Date/time: 2026-05-06 13:09:37  
- Time note: from trades.csv
- Real score: **4** (side=P), blockers=[5, 7, 8, 9, 10], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 4/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 4/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 4/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 4/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 4/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A8_2026-05-07_734C -- LOSER (-$45 real, BULLISH_RECLAIM_RIDE_THE_RIBBON)
- Date/time: 2026-05-07 12:30:00  
- Time note: trades.csv records only HH:MM (12:30); no seconds available
- Real score: **9** (side=C), blockers=[5, 11], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 9/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 9/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 9/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 9/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 9/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A9_2026-05-07_737C -- LOSER (-$120 real, UNCATEGORIZED_PROBE_MANUAL)
- Date/time: 2026-05-07 11:14:15  
- Time note: from trades.csv
- Real score: **7** (side=C), blockers=[7, 8, 10, 11], raw triggers=[], rejection/reclaim level=None, confluence=None
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 7/10 (need 7) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-R (8G19) | 7/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-BOLD (AT40) | 7/10 (need 8) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| FLEET-TIGHT-S (OB0Q) | 7/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |
| CORE-SAFE (KIQE) | 7/10 (need 9) | OUT | -- (no level-tied trigger) | -- | N/A | -- |

### A10_2026-07-23_735P -- LOSER (-$305 real, BEARISH_REJECTION_RIDE_THE_RIBBON)
- Date/time: 2026-07-23 11:29:25  
- Time note: task brief said ~13:0x ET; REAL fill per journal/trades.csv is 11:29:25 ET -- used the real time
- Real score: **10** (side=P), blockers=[], raw triggers=['level_rejection', 'confluence'], rejection/reclaim level=737.1171142763585, confluence=737.1171142763585
- Levels provenance: OHLC-derived via backtest.lib.levels._detect_from_history (the real production level-derivation function -- prior-day H/L/C + premarket swing levels) -- PROVISIONAL: production intraday sessions also incorporate live TradingView-drawn levels, memory-scored levels, and swarm input this offline OHLC-only reconstruction cannot recover; no key-levels-history snapshot exists before 2026-07-23

| Arm | Gate x/10 | IN/OUT | Trade | Contracts | risk_gate verdict | Premium (provenance) |
|---|---|---|---|---|---|---|
| FLEET-LOOSE-R (X15Q) | 10/10 (need 7) | IN | SPY 2026-07-23 734P (OTM-3) | 23 | ALLOW | $0.39 [SYNTHETIC] |
| FLEET-TIGHT-R (8G19) | 10/10 (need 8) | IN | SPY 2026-07-23 734P (OTM-3) | 18 | ALLOW | $0.39 [SYNTHETIC] |
| CORE-BOLD (AT40) | 10/10 (need 8) | IN | SPY 2026-07-23 737P (ATM) | 5 | DENY[RISK_CAP] | $2.13 [real] |
| FLEET-TIGHT-S (OB0Q) | 10/10 (need 9) | IN | SPY 2026-07-23 734P (OTM-3) | 12 | ALLOW | $0.39 [SYNTHETIC] |
| CORE-SAFE (KIQE) | 10/10 (need 9) | IN | SPY 2026-07-23 737P (ATM) | 3 | DENY[RISK_CAP] | $2.13 [real] |


## Notes -- provenance, calibration proof, and honest limitations

**Calibration anchor proof (A5):** the pinned construction (`build_calibration_bar_context`, verbatim from `backtest/tests/test_why_not_provenance.py`) reproduces bear_score=9, blockers=[5], `level_rejection` in raw triggers, rejection_level=744.9 -- MATCHES the incident's logged ground truth.

**Disclosed sensitivity finding (A5):** building the SAME bar via this script's general full-pipeline path (used for the other 9 anchors: cached `backtest/data/spy_5m_2026-05-19_2026-07-27.csv`, continuous production ribbon, OHLC-derived levels) does NOT reproduce the pinned ground truth -- it gives bear_score=8, blockers=[5, 9], triggers=['level_rejection'], rejection_level=744.87, confluence=None. The cached 09:40 bar is open=744.970 high=745.065 low=743.440 close=743.450 vs the real IEX bar (open 744.91, high 744.92, low 743.45) the live engine actually read -- a 3-cent level-detection difference (744.87 vs 744.90) breaks the $0.30 confluence match, and the REAL 20-bar volume baseline (895,854) fails filter 9 where the pinned test's hand-built flat-500k warmup passed. This is a genuine feed-provenance finding (SIP/yfinance/IEX patchwork, markdown/infra/DATA-PROVENANCE.md), not a tool bug -- surfaced here rather than hidden. It does not affect anchors 1-4/6-10 (no external IEX ground truth was given for those; their own cached bars are the only source used for them, consistently).

**Premium provenance per row:** see the 'Premium (provenance)' column in each per-anchor table above -- `[real]` = real OPRA cache (backtest/data/options/{OCC symbol}.csv) or the real journal/trades.csv fill for that exact strike; `[SYNTHETIC]` = Black-Scholes fallback (backtest.lib.pricing), used whenever no cached OPRA bars exist for that arm's resolved strike/date (always true for A5 -- 2026-07-27 has zero cached option data; also true for the 3 fleet-arm OTM-3 strikes on A7 (2026-05-06, 727P not cached) and A9 (2026-05-07, 740C not cached), and all fleet-arm OTM-3 strikes on A10 (2026-07-23, only 735/736/737P cached).

**BOLD IS NOT ITM-2** (corrects the task brief -- see module docstring for the full verification): core-Bold (bold-2) resolves via V15_BOLD_CORE_TIERS, which is ATM at its current $0-2K equity tier (repointed 2026-07-18) -- NOT ITM-2. safe-2 and bold-2 therefore propose the IDENTICAL strike for every anchor here.

**Contracts floor is NOT a universal 3** (see module docstring): Safe-family arms (safe-2, safe-3) use min_contracts=3 (automation/state/params.json, matches Rule 6's headline); Bold-family arms (bold-2, risky-1, risky-3) use min_contracts=5 (automation/state/aggressive/params.json). Each row's Contracts column uses the arm's OWN verified floor.

**risk_gate assumptions (disclosed, not hidden):** start_of_day_equity = the SAME current 2026-07-27 equity as `equity` (no historical intraday SoD series exists for these dates and the task explicitly asked for CURRENT equities); kill_switch_tripped=False, day_trades_used_5d=0, current_position_status='flat', prior_stops_today=[] (each anchor evaluated in isolation, not as part of a real day's cumulative state); cash-settlement arms (Safe family) get settled_cash_available=equity, same_day_entries_used=0 (assumes nothing else spent today). These are simplifications appropriate to a single-trade ladder-evidence exercise, not a full-day simulation.

**Bull score scale caveat:** bull_score tops out at 11 (not 10) -- filter 11 is the same trigger-count gate at a different index than bear's filter 10, so evaluate_bullish_setup has 11 filters total. The ladder thresholds (7/8/9) are applied literally to bull_score per the task's explicit instruction, without rescaling.


**Why 6 of the 9 real historical anchors show `triggers_raw=[]` -- investigated, not hand-waved:**
- **A1 (2026-04-29) and A2 (2026-05-01) predate the v15 rule ratification (2026-06-01, per CLAUDE.md).** Replaying them through TODAY's filters.py is not apples-to-apples -- the engine that existed on those dates had different code/thresholds. A2 specifically: probed the task brief's stated ~11:50 ET trigger time (vs. the 13:09:14 real fill used in the table) and confirmed the actual pattern is an FHH (first-hour-high) rejection at ~724.24 -- a real, large-volume rejection bar IS present in the cached data at 11:50 (high 724.38, close 723.48, volume 1,014,537). But firing it requires `bearish_reversal_bypass=True` + `include_first_hour_high=True` in evaluate_bearish_setup -- BOTH are Rule-9-flagged DEFAULT FALSE in production filters.py (never ratified). So even the earlier bar correctly shows NO trigger under CURRENT default settings (bear_score rises from 4 to 6 at 11:50, still zero triggers) -- a genuine, disclosed CAPABILITY GAP between what J's engine caught historically and what today's default-config engine would catch, not a tool bug. Not swapped into the main table because the task's explicit instruction is to use the real trades.csv fill time.
- **A4 (2026-07-17) is a REAL live production entry** (passed=True, score=10, when it actually fired) that this tool's single-isolated-bar / no-day-state reconstruction scores at only 7 with zero triggers. Cross-checked directly against `backtest.lib.orchestrator.run_backtest` (SAFE_BASE_LIVE params, full continuous day simulation) for 2026-07-17: it finds a DIFFERENT trendline_rejection entry at 13:15 (not 13:01), strike 746 -- confirming this is a KNOWN, ALREADY-DOCUMENTED class of discrepancy in this codebase (engine_fullhist_replay.py's own module docstring calls it the 'SIM-EXIT-SHAPE-PARITY trap' -- simulated/reconstructed entries do not always land on the identical bar as live fills, because live decisions carry INTRADAY STATE -- setup-quality escalation locks, day-trade counters, prior stops today -- that a single isolated bar cannot recover). This ladder tool deliberately does NOT model that state (out of scope for a per-anchor score+trigger replay) -- disclosed here rather than papered over.
- **A6, A7, A9 (3 of the 4 remaining losers) are logged in journal/trades.csv under `UNCATEGORIZED_PROBE` / `UNCATEGORIZED_HOLD_TO_EXPIRY` / `UNCATEGORIZED_PROBE_MANUAL`** -- J's OWN labels for discretionary, non-setup-driven trades. An honest engine finding NO trigger for these is the CORRECT, expected result -- exactly the kind of discrimination a ladder should show, not a gap to explain away.
- **A3 (2026-05-04) and A10 (2026-07-23) both reconstruct cleanly** -- real triggers, scores matching what a genuine setup should produce, and A10's score=10/blockers=[] independently matches that this WAS a real passed=True live entry. This is the positive-control evidence that the scoring MECHANISM itself is sound when the underlying bar data is accurate; the gaps above are about (a) pre-v15 vintage, (b) a disabled feature flag, and (c) missing day-level state -- not a broken pipeline.
