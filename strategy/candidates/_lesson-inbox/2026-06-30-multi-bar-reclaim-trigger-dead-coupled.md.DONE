# Lesson candidate: a trigger gated behind another trigger's precondition is a structurally-DEAD knob

**Date:** 2026-06-30
**Theme:** C14 (dead/translated-but-unapplied knobs — vary-and-assert) + C3 (SPY-price edge structure)
**Source:** BULL-UNBLOCK-REPLAY-PROBE SLICE 3 (the #1 project thread — rig has never filled an ENTER_BULL in 2544 lifetime decisions)

## Symptom
The bull entry path is structurally unreachable on SMOOTH uptrends: `core-decisions.jsonl`
shows 0 ENTER_BULL across the rig's lifetime, and on bull days the reclaim reaches ELITE only
via a single-bar straddle. `detect_sequence_reclaim` (a multi-bar higher-lows reclaim) EXISTS
as a named bull trigger and is wired into `evaluate_bullish_setup`, so it LOOKS like the smooth-
uptrend path is covered. It is not.

## Root cause
In `evaluate_bullish_setup` (`backtest/lib/filters.py` ~L937) the `level_state` that
`detect_sequence_reclaim` needs is looked up ONLY inside `if reclaim_level is not None:`, and
`reclaim_level` comes from `detect_level_reclaim` (the SINGLE-BAR straddle: `low < level < close`).
So the multi-bar `sequence_reclaim` trigger can only ever fire as a REDUNDANT CO-TRIGGER of the
single-bar straddle it is supposed to be an ALTERNATIVE to. On a smooth uptrend that never prints
a straddle, `reclaim_level` is None -> `level_state` is never looked up -> `sequence_reclaim` is
never evaluated -> filter 11 blocks. The one trigger that could catch the smooth-uptrend bull case
is dead-coupled to the case it can't cover.

Proven behaviorally (read-only, `test_bull_sequence_reclaim_coupling.py`): with a valid independent
`broken_to_support` level (3 higher lows, `detect_sequence_reclaim` returns True on it), a bar with
NO straddle yields `triggers_fired == []` and filter-11 blocked; the SAME level_state with a straddle
bar yields `["level_reclaim", "sequence_reclaim"]`. The suppression is real, not vacuous.

## Fix / discipline
- **When a detector is wired but its INPUT is gated behind another detector's precondition, it is a
  DEAD knob** — it cannot fire on the cases it was added to cover. Audit trigger INPUTS, not just
  that the trigger function is called somewhere (C14 vary-and-assert applied to trigger assembly).
- The correct decouple (look up `level_state` independently of `reclaim_level`) is the last untested
  bull-unblock lever but is a filters.py LOGIC change = rail-4 J-gated, and the 25-day OPRA window
  cannot prove any bull sub-lever to significance (SLICE 1+2) -> filed for a future WIDER-DATA probe.
- **Guarded:** `test_bull_sequence_reclaim_coupling.py` pins the coupling as a KNOWN structural fact;
  a future refactor that silently decouples it re-REDs the build so the bull entry surface change is
  conscious and re-runs the bull A/B.

## Project-level conclusion
All three bull-unblock levers now audited on the fresh window (elite-block KEEP / min_triggers thin /
sequence_reclaim structurally coupled off). NEITHER sim-tuning lever unblocks a proposable bull edge.
The 0DTE-SPY bull frontier is DATA-GATED on the 25-day OPRA wall (same wall as range-scalp n=8) —
resolving it needs a wider data window, not more sim tuning.
