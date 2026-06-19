---
proposed_id: L76
title: Premium stops chop out BULLISH_RECLAIM in low-VIX grind-up (bull analog of L51/L55)
date_observed: 2026-05-31
source: missed-week backtest 2026-05-26..29 (analysis/missed-week-2026-05-26_29.md, analysis/backtests/_TRUTH.md)
severity: HIGH
cross_ref: [L51, L55, L73, L74]
---

## Symptom
Machine offline 2026-05-23..05-30 (J moved house). On return (2026-05-31) we backtested
production v15.2 against real Alpaca data for the 4 missed trading days (05-26,27,28,29).
The tape was a low-VIX (15-16, MID regime) bull grind: SPY 750.0 -> 756.4 (+0.85%), every
target day closed at/above its open.

The engine behaved CORRECTLY on direction -- it fired BULLISH_RECLAIM_RIDE_THE_RIBBON calls
WITH the uptrend (not bearish puts; an earlier "bearish regime mismatch" hypothesis was
WRONG). Yet it still LOST net per-contract on the missed days:
  - SAFE overlay (ATM, -8% stop): -$10.6 / contract-sum, 1W / 3L
  - BOLD overlay (ITM-2, -15% stop): -$117.4 / contract-sum, 2W / 6L
Nearly every loss exited via EXIT_ALL_PREMIUM_STOP. The single clean winner was 05-29 (the
one trend-day with follow-through). 05-26/27/28 calls were stopped on shallow retest dips
that then resumed higher.

## Root cause
A BULLISH_RECLAIM entry sits right at the level it just reclaimed. In a low-VIX slow grind,
a routine retest wick pushes the option premium down 8-15% (tripping the Safe -8% / Bold
-15% premium stop) BEFORE the grind resumes -- so the engine is repeatedly right on
direction but shaken out on a noise retest. Bull mirror of L51 (violent bounce on level-break
entries), L55 (premium stops vs first-strike bull bounce), L74 (ATM delta + theta + stop
misfire on retest wick). The premium stop is calibrated to conviction moves, not grind chop.

## Fix direction (DRAFT -- needs OOS + real-fills validation before any ratification)
BULL-side only (do NOT touch bear side -- L73: VIX-character gates are setup-specific):
  1. low-VIX (VIX<16) + side=C + BULLISH_RECLAIM -> CHART stop (reclaimed_level - buffer)
     instead of premium stop (survives the retest wick); OR
  2. widen the bull premium stop in low-VIX regimes; OR
  3. require confluence (not lone level_reclaim) for bull reclaims in grind regimes.
Discriminator: entry sits < $0.50 above reclaimed level on a sub-1.0x-vol bar in low-VIX
-> premium stop structurally doomed.

## Evidence
analysis/backtests/_TRUTH.md ; missed_week_{safe,bold}/{trades,decisions}.csv ;
_missed_week_facts.json ; run_id 2026-05-31_a6a17222_0605ef_9c5dea.

## Guardrail
FINDING + DRAFT direction, NOT a doctrine change. Rule 9: exit-rule changes are J's, on a
weekend, in writing. Routed in parallel to strategy/candidates/ + a Kitchen cook task.
