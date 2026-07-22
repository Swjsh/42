# Ribbon-state-at-entry gate on bear entries -- population validation (2026-07-21)

Generated: 2026-07-22T00:06:24.604291. Runner: `backtest/tools/ribbon_state_entry_gate_study.py`.
Frozen pre-reg: `analysis/recommendations/ribbon-state-entry-gate-prereg-2026-07-21.json` (frozen_at 2026-07-21T00:00:00-04:00).

Source: LANE-B HYPOTHESIS #1, `markdown/doctrine/DOJO-HARVEST-2026-07-21.md` -- n=2-day quantified finding (2026-07-17 real fills): bear entries (level_rejection+confluence) into a still-rising BULL ribbon lost -$37/-$102; entries after the ribbon rolled over won +$241/+$191/+$233.

## GROUND-TRUTH CORRECTION (read this first)

Cross-checked the harvest doc's motivating observation against `automation/state/core-decisions.jsonl` (the real live engine's own per-tick record) -- fresh this run, not hand-transcribed:

| time | verdict | ribbon (LIVE engine field) | spread_c | triggers | bear_score |
|---|---|---|--:|---|--:|
| 11:06 | ENTER_BEAR | BEAR | 211.1 | ['level_rejection', 'confluence'] | 10 |
| 11:40 | ENTER_BEAR | BEAR | 195.1 | ['level_rejection', 'confluence'] | 10 |
| 13:01 | ENTER_BEAR | MIXED | 53.7 | ['trendline_rejection'] | 7 |
| 13:51 | ENTER_BEAR | MIXED | 32.1 | ['trendline_rejection'] | 9 |
| 13:52 | ENTER_BEAR | MIXED | 32.1 | ['trendline_rejection'] | 9 |

**The harvest doc's 'same trigger family, ribbon BULL+rising for the losers' characterization does not hold against the live log. Losers fired with ribbon=BEAR (bear_score=10, ribbon strongly stacked, not weak/turning) and triggers=[level_rejection, confluence]. Winners fired with triggers=[trendline_rejection] ONLY -- a DIFFERENT trigger family, via the trendline_only_setup relaxation that bypasses filter_5 (the ribbon-stack requirement) with a score demerit (bear_score 7-9, not 10). The real discriminator visible in the live data is TRIGGER TIER (ELITE static-level-anchored vs TRENDLINE dynamic-only no static level), not ribbon STACK STATE. That correctly-framed hypothesis is ALREADY filed and ALREADY tested: analysis/recommendations/elite-bear-level-reject-gate-ab-2026-07-17.json, verdict PARK_INSUFFICIENT_REGIME_SHIFT (IS delta -$532.80, OOS delta +$683.14, WF gate FAILED, sub_window_stability FAILED).**

## Population

- n_walked = **27** (side=PUT, setup=BEARISH_REJECTION_RIDE_THE_RIBBON, triggers contain BOTH level_rejection AND confluence -- full history 2025-01-02..2026-07-17, the widest OPRA-covered window, 382 distinct trading dates)
- BS-fallback excluded (uncached contract, not a real fill): 3
- signal-bar unmatched (dropped): 0
- ribbon-warmup excluded: 0
- OPRA coverage skip: 0

**WHY n_flagged is 0 for every candidate:** all 27 entries in this population show `stack=BEAR` at signal time -- ZERO show BULL, and `rising_bull_at_entry` fires on 0/27. This is STRUCTURAL, not a coincidence of this sample: `backtest/lib/filters.py` Filter 5 (`ctx.ribbon_now.stack != 'BEAR' -> blockers.append(5)`) already hard-blocks any PUT entry carrying level_rejection/confluence/sequence_rejection triggers unless the ribbon is EXACTLY BEAR-stacked at that instant -- live and backtest alike (`engine/score.py:score_bear` is a byte-identical pass-through to the same `evaluate_bearish_setup`, and `bearish_reversal_bypass`/`allow_one_blocker` have never been set true in `automation/state/params.json`'s history). The literal `rising_bull_at_entry` condition this pre-reg specified is therefore a logical impossibility for this exact trigger family under the CURRENT production filter set -- confirmed two ways: (1) 0/27 in this full-history reconstruction, and (2) the real 2026-07-17 live log itself (see GROUND-TRUTH CORRECTION above).

## Per-trade population

| date | sig time | tier | stack | mom3c | rising_bull | AM/PM | control $ | sim_real $ (disclosed) | exit |
|---|---|---|---|--:|:--:|:--:|--:|--:|---|
| 2025-01-10 | 10:30 | ELITE | BEAR | +76.9 | False | AM | +705.55 | +0.00 | runner_stop @ 4.96 |
| 2025-01-10 | 12:00 | ELITE | BEAR | +5.7 | False | PM | +12.00 | +0.00 | structure_stop @ 580.51 |
| 2025-02-21 | 14:00 | ELITE | BEAR | +36.1 | False | PM | +616.00 | +0.00 | time_stop_15:50 (runner) |
| 2025-06-05 | 14:00 | ELITE | BEAR | +17.1 | False | PM | -230.00 | +0.00 | premium_stop @ 0.46 |
| 2025-06-13 | 14:00 | SUPER | BEAR | +3.4 | False | PM | +656.00 | +0.00 | runner_stop @ 2.81 |
| 2025-06-20 | 13:00 | ELITE | BEAR | -16.1 | False | PM | +397.80 | +0.00 | runner_stop @ 1.99 |
| 2025-10-15 | 13:00 | ELITE | BEAR | +38.8 | False | PM | +483.55 | +532.80 | runner_stop @ 3.26 |
| 2026-01-29 | 11:00 | ELITE | BEAR | +85.7 | False | AM | +656.85 | +0.00 | runner_stop @ 4.6 |
| 2026-02-03 | 13:00 | ELITE | BEAR | +4.3 | False | PM | +380.00 | +0.00 | structure_stop @ 690.545 |
| 2026-02-26 | 11:00 | SUPER | BEAR | -1.0 | False | AM | +636.05 | +0.00 | runner_stop @ 4.7 |
| 2026-04-21 | 14:15 | ELITE | BEAR | -5.2 | False | PM | -336.00 | +0.00 | structure_stop @ 706.1400146484375 |
| 2026-04-28 | 09:50 | SUPER | BEAR | +52.4 | False | AM | -261.00 | +0.00 | ribbon_flip_back |
| 2026-04-29 | 14:05 | SUPER | BEAR | +9.2 | False | PM | -162.00 | -333.00 | structure_stop @ 709.25 |
| 2026-05-04 | 11:15 | SUPER | BEAR | +34.9 | False | AM | +445.00 | +0.00 | runner_stop @ 2.89 |
| 2026-05-18 | 11:00 | ELITE | BEAR | +12.0 | False | AM | +446.45 | +0.00 | runner_stop @ 2.86 |
| 2026-05-21 | 11:30 | SUPER | BEAR | -0.3 | False | AM | -189.00 | -240.00 | structure_stop @ 738.9 |
| 2026-06-08 | 13:30 | SUPER | BEAR | -2.7 | False | PM | +439.90 | +0.00 | runner_stop @ 3.01 |
| 2026-06-08 | 14:35 | SUPER | BEAR | -5.8 | False | PM | +532.00 | +0.00 | runner_stop @ 2.21 |
| 2026-06-09 | 10:45 | SUPER | BEAR | +47.5 | False | AM | -390.00 | -390.00 | premium_stop @ 1.3 |
| 2026-06-17 | 14:00 | SUPER | BEAR | +24.3 | False | PM | -355.50 | -355.50 | premium_stop @ 1.19 |
| 2026-06-22 | 11:45 | ELITE | BEAR | -14.9 | False | AM | -242.00 | +0.00 | premium_stop @ 0.6 |
| 2026-06-22 | 14:55 | SUPER | BEAR | +15.4 | False | PM | -50.00 | +0.00 | structure_stop @ 743.8599853515625 |
| 2026-06-24 | 13:15 | SUPER | BEAR | +58.8 | False | PM | +309.00 | +242.40 | time_stop_15:50 |
| 2026-06-25 | 09:55 | SUPER | BEAR | +40.1 | False | AM | -579.00 | -420.00 | structure_stop @ 730.8400268554688 |
| 2026-06-25 | 13:30 | SUPER | BEAR | -5.6 | False | PM | -246.00 | +0.00 | structure_stop @ 733.4773412770263 |
| 2026-06-26 | 09:45 | ELITE | BEAR | +64.3 | False | AM | -468.00 | -336.00 | structure_stop @ 729.7 |
| 2026-06-26 | 14:45 | SUPER | BEAR | +25.2 | False | PM | -230.00 | +0.00 | structure_stop @ 732.2 |

## Candidate `A_suppress`

n_flagged=0 / n_population=27. control_total=$+2,977.65 candidate_total=$+2,977.65

- g1 aggregate delta: **$+0.00** -- pass=False
- g2 majority of days: up=0 down=0 -- pass=False
- g3 survives drop-best-trade: delta_ex_best=$None -- pass=False
- g4 held-out subset: IS_2025=$0.0 OOS_2026_ex_discovery=$0.0 -- pass=False
- g5 discovery-day contribution: $0.0 (delta excluding discovery day entirely: $0.0)

Advisory BH-FDR: p=None threshold=0.1 significant=False (not gating). evidence_n floor met: False (n_flagged=0, floor=15).

Time-of-day confound: AM n=11 n_flagged=0 mean_flagged_control_pnl=None; PM n=16 n_flagged=0 mean_flagged_control_pnl=None. n too small to isolate the ribbon-state effect WITHIN a fixed time-of-day bucket

### VERDICT `A_suppress`: **INSUFFICIENT_N**

## Candidate `B_detier_half_size`

n_flagged=0 / n_population=27. control_total=$+2,977.65 candidate_total=$+2,977.65

- g1 aggregate delta: **$+0.00** -- pass=False
- g2 majority of days: up=0 down=0 -- pass=False
- g3 survives drop-best-trade: delta_ex_best=$None -- pass=False
- g4 held-out subset: IS_2025=$0.0 OOS_2026_ex_discovery=$0.0 -- pass=False
- g5 discovery-day contribution: $0.0 (delta excluding discovery day entirely: $0.0)

Advisory BH-FDR: p=None threshold=0.1 significant=False (not gating). evidence_n floor met: False (n_flagged=0, floor=15).

Time-of-day confound: AM n=11 n_flagged=0 mean_flagged_control_pnl=None; PM n=16 n_flagged=0 mean_flagged_control_pnl=None. n too small to isolate the ribbon-state effect WITHIN a fixed time-of-day bucket

### VERDICT `B_detier_half_size`: **INSUFFICIENT_N**

## Candidate `C_price_confirmed_suppress_disclosed_only`

n_flagged=0 / n_population=27. control_total=$+2,977.65 candidate_total=$+2,977.65

- g1 aggregate delta: **$+0.00** -- pass=False
- g2 majority of days: up=0 down=0 -- pass=False
- g3 survives drop-best-trade: delta_ex_best=$None -- pass=False
- g4 held-out subset: IS_2025=$0.0 OOS_2026_ex_discovery=$0.0 -- pass=False
- g5 discovery-day contribution: $0.0 (delta excluding discovery day entirely: $0.0)

Advisory BH-FDR: p=None threshold=0.1 significant=False (not gating). evidence_n floor met: False (n_flagged=0, floor=15).

Time-of-day confound: AM n=11 n_flagged=0 mean_flagged_control_pnl=None; PM n=16 n_flagged=0 mean_flagged_control_pnl=None. n too small to isolate the ribbon-state effect WITHIN a fixed time-of-day bucket

### VERDICT `C_price_confirmed_suppress_disclosed_only`: **INSUFFICIENT_N**

## Relationship to the trend-alignment-correlation study (twice-confirmed KILL)

`analysis/recommendations/trend-alignment-correlation.md`: P1 OOS rho=-0.150 (p=0.157, beats-null=False), P2 real-engine rho=-0.143 (p=0.137, beats-null=False) -- MULTI-TIMEFRAME (daily+hourly+15m) trend agreement vs the trade's own side. THIS study measures a DIFFERENT, SAME-TIMEFRAME feature (the 5-min ribbon's own stack + local 3-bar momentum at entry), not cross-timeframe agreement. Related question, different measurement -- this study's verdict stands or falls on its own gates above, it does not inherit the trend-alignment KILL by association.
