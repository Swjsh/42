# A population A/B whose CONTROL cannot express the live baseline inflates every cell — slice to where the treatment BINDS

**Date:** 2026-08-10 evening
**Where:** `backtest/tools/ladder_population_killcheck.py` first full run (GIVEBACK-RATCHET-2026-08-10)
**Class:** C4/C7 sibling — a harness's blind spot flatters whatever resembles the blind spot

## Symptom

The ladder population kill-check's headline table showed every cell +$7k..+$31k vs control,
GIVEBACK trail cells beating even the live ACTUAL exits by +$7.8k, 16/20 losing days flipping,
all BH-PASS at p=0.0001. Textbook too-good.

## Root cause (one sentence)

The replay harness has no SPY feed, so structure/ribbon exits — the live engine's PRIMARY exit
on this population — cannot fire in ANY arm, which makes CONTROL a strawman that rides every
loser to the −50% cap (~$23k worse than the same fills' live actuals over 21 days), so "beats
control" measured mostly "has any floor at all", and the tight GIVEBACK trails additionally
harvested the 5m optimistic intra-bar convention (arm on the bar's high, fill at the floor on
the same bar's low) — the same %-trail shape a proper walk_exit_manager study had already
measured as a −$7,759 G_RUNNER failure.

## The fix that made the number honest

Slice the population to where the treatment BINDS — positions whose replay MFE ≥ the lowest
rung (+50%). Below that the ladder is guard-tested inert (`test_below_trail_arm_nothing_engages`),
so production behavior is byte-identical to control and every sub-binding difference the harness
shows is pure harness error. On the binding slice, compare treatment vs ACTUAL (not vs the
strawman control), decomposed by live outcome:

- cohort A (live TP1'd, already banking): the treatment's real COST (clip −$3,759 / n=40)
- cohort B (live never banked, the defect class): the treatment's real RESCUE (+$10,214 / n=73)

Net +$6,454 / 21 days, p=0.0073 day-clustered — a PASS with its price tag visible, instead of a
+$31k headline that was mostly strawman.

## Generalization

Before quoting any population A/B: ask "can the harness's CONTROL arm express what the live
system actually does?" If not, (a) restrict to the subpopulation where the treatment changes
behavior at all, (b) compare against ACTUAL there, (c) decompose by live outcome so cost and
rescue are separate numbers. A treatment that is inert below its arm threshold makes the
binding-slice restriction exact, not an approximation.

## Cross-refs

- Runner + artifacts: `analysis/recommendations/giveback-ratchet-population-2026-08-10.{json,md}`
- Prereg: `analysis/recommendations/prereg-giveback-ratchet-2026-08-10.json`
- The prior honest %-trail study this run's GIVEBACK rows contradicted: HOLD-WINNERS-2026-08-06
