# Same-bar cooldown ship-gate: wall-clock bar mapping does not transfer to engine bar identity

**Date:** 2026-08-06 (evening Fix+Ship lane)
**Theme:** C6/C21/L251 sibling — two bar-identity conventions silently disagree on gate eligibility

## Symptom

LEVER-ENTRY-COUNT-2026-08-06.md §2d measured the fleet SAME-BAR cooldown at Wed +$202 /
Tue +$144 / 0 of 26 days harmed, "blocks exactly 3 positions, preserves the 09:57 +$524
rescue". KEEP-LOSSES-SMALL-2026-08-06.md rated it the #1 SHIP-ELIGIBLE lever. The ship-gate
replay through the PRODUCTION bar identity produced the OPPOSITE result: blocks NOTHING on
Wednesday, and on Tuesday blocks exactly the +$524 winner the study said it preserves.
Net on the motivating tape: **−$524**, meeting the prereg's own kill criterion on day 0.

## Root cause

The study keyed each entry to its **wall-clock last-closed 5m bar** (entry 09:50 → bar
09:45). The live consult keys on the **engine's `trigger_bar_et`** (core `bar_ctx.
timestamp_et`, trig_idx = n−2 over the bar cache), which lags wall clock by one bar at
most tick offsets — and the lag is **tick-phase-dependent**, so pairwise bar-EQUALITY
relations (the entire content of a same-bar rule) do not survive the mapping change.
Real joins: Tue 09:50→09:40, 09:54→09:45, 09:57→09:45 (blocked pair is 09:54/09:57, not
09:50/09:54); Wed 09:58/10:06/10:10/10:14/10:18 → 09:50/09:55/10:00/10:05/10:10, all
advancing, zero blocks.

## Fix / rule

Before shipping ANY bar-keyed gate (same-bar, N-bar cooldown, bar-advance qualifier),
replay the counterfactual **through the engine's own bar identity** — join each real
entry row to its `core_tick_id` → core-decisions `trigger_bar_et` and walk the exact
production functions (`exit_actuator.same_bar_cooldown_active`/`record_entry_bar`).
A wall-clock derivation of "which bar was this entry on" is a DIFFERENT engine (L251)
and its blocked set is fiction. Concretely shipped: wiring landed DISARMED
(`fleet_live.FLEET_SAME_BAR_COOLDOWN = False`, default pinned by guard test), outcome
recorded in analysis/recommendations/fleet-same-bar-cooldown-OUTCOME-2026-08-06.json.

## Guard

- `automation/state/fleet/test_fleet_same_bar_cooldown.py::test_default_is_disarmed_do_not_arm_verdict`
- Replay evidence: analysis/deep-research/SHIP-LOG-2026-08-06-EVENING.md
