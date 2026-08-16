---
filed: 2026-08-16
filed_by: weekend engine-improvement survey
kind: lesson
status: pending
---

# Counting ROUND TRIPS where the unit is a DECISION inflates n by ~3x — and it reversed a win-rate ranking

## Symptom

Bull vs bear, real fills, since 2026-07-20. Two honest-looking readings of the same ledger:

| unit | bear WR | bull WR | reads as |
|---|--:|--:|---|
| round trips | **31.9%** | 28.3% | bear hits more often |
| independent signals | **14.3%** | **27.0%** | bear hits **half** as often |

Same trades. Same ledger. Opposite conclusion.

## Root cause

`LEVER-CORRELATION-2026-08-06` established the fleet is *"one bet in five sizes"* (r = 0.846,
95.7% sign agreement). When four arms buy the same contract in the same minute, the book made
**one decision** and booked **four round trips**.

Measured inflation across windows: **2.3x – 3.5x**.

The ranking flips because the inflation is **not uniform across outcomes**: bear's *losing*
signals were spread across more arms than its *winning* ones, so per-round-trip counting
double-counts bear's wins relative to its losses. Any metric whose denominator is round trips
is therefore measuring **arm count as much as edge** — and arm count is a sizing policy, not a
property of the signal.

## The part that reaches doctrine

**CLAUDE.md OP-16 states the bull re-evaluation bar as "n >= 20".** In the inflated unit, n=20
round trips can be as few as **6–7 independent decisions**. A bar that reads like "wait for
twenty observations" can be satisfied by six. Every evidence threshold quoted in trade counts
on a correlated fleet has the same problem.

(The same doctrine line's cited evidence — "bull n=80 WR 1.2% −$1,573" — is a 9-day July
window and is now stale: 28.3% WR over 106 RTs since 07-20. Separate defect, same sentence.)

## Generalisations worth keeping

1. **Name the unit before quoting an n.** "n=80" is meaningless without "of what?". On this rig
   the honest unit for a signal-quality question is one **(date, symbol) cluster** — one
   decision — not one fill, not one round trip, not one arm-day.
2. **Correlated replication inflates confidence, never information.** Five arms on one signal
   is five position sizes of the same bet. It is a *paired-treatment* design (which is
   genuinely good for A/B comparisons between arms) and simultaneously *pseudo-replication*
   (which is bad for accumulating independent evidence). The same data is strong for one
   purpose and weak for the other; which one you have depends on the question.
3. **Check whether a summary statistic survives a change of unit.** If WR flips when you
   collapse correlated observations, the original number was describing the sampling structure,
   not the phenomenon. This is cheap to test and it is not routinely done here.
4. **An evidence threshold is part of the claim.** Freezing "n >= 20" without freezing the unit
   leaves the bar free to drift with sizing policy — arm the sixth arm and every threshold in
   the repo silently gets easier.

## Where it landed

Measurement folded into `analysis/deep-research/DIRECTION-SYMMETRY-AUDIT-2026-08-09.md`;
rerunnable as `backtest/tools/direction_edge_by_signal_2026_08_16.py`, which prints both units
side by side specifically so the difference cannot be missed.

Commit: `b0319e3e`.

## Open

Whether OP-16's `n >= 20` should be restated in independent signals is a doctrine edit and
therefore J's call, not a follow-up session's. Flagged, not changed.
