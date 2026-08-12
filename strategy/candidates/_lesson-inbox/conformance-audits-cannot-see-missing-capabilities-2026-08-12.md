---
filed: 2026-08-12
filed_by: fable (capability audit, ~evening)
kind: lesson
status: pending
---

# Months of GREEN audits never noticed the engine cannot decline a trade — conformance audits are structurally blind to MISSING capabilities

## Symptom

2026-08-12: 38 positions, −$900, all five arms red. Every existing audit PASSED on that day's
record: all exits fired from named stages, orders reconciled, guards held, zero error rows,
ledgers complete. J: "What do you mean the engine has no way to sit out? Why is that just now
coming to the surface when we've been building this forever?"

## Root cause — three layers

1. **Every audit in this repo is a CONFORMANCE audit** ("does X behave as specified?").
   A missing capability produces no failing test, no RED, no anomaly — it produces
   plausible-looking activity. Conformance can only inspect code that exists.
2. **The gap was legislated, not overlooked.** Three separate mechanisms exist purely to
   convert silence into trades (PROBE arm, SCORE LADDER, FULL-SEND), each shipped on an
   explicit participation-seeking directive during the learning phase. The system optimized
   for "find more reasons to trade"; "decline the day" was never on any queue because the
   posture pointed the other way. Going live requires REVERSING a posture, not fixing a bug.
3. **Aggregate framing hid per-decision quality.** 38 entries/day across a 5-arm experiment
   matrix read as "learning rate," not as "would a human have taken these?"

## The discovering move (the reusable part)

Audit against the IDEAL, not the spec: enumerate the decision inventory of a disciplined
human operator (for trading: ~17 distinct judgments/day), then ask for each — **does ANY
component have the vocabulary to express this decision at all?** Not "does it work."
Gaps found this way are unknown unknowns by construction: no existing code refers to them,
so no existing audit can flag them. First run (2026-08-12): 3 EXISTS / 4 PARTIAL / 10 ABSENT
— execution hygiene near-perfect, trade judgment near-empty.
Register: analysis/deep-research/2026-08-12-churn/CAPABILITY-AUDIT-2026-08-12.md

## Rule to carry forward

1. **A green conformance suite says the code does what it says. It says NOTHING about whether
   the code can say what the operator needs.** Track the two audit kinds separately.
2. **Re-run the capability audit at every posture change** (paper→live, new strategy family,
   sizing tier), because that is exactly when yesterday's legislated behavior becomes today's
   structural gap.
3. When a directive optimizes one direction ("more participation"), file the reverse
   capability ("decline") as explicit future work AT THAT MOMENT — the cost of building it
   later is a −$900 day and a month of invisible losses.

Kin: C7 (silent success), C32 (capability+data+idle compute ≠ insight unless a fire's job is
"generate the hypothesis"), OP-33e (repeated question = missing instrument).
