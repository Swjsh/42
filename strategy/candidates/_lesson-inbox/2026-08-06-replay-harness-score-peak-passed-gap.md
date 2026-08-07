# Lesson candidate: a new required signal field (score_peak_passed) shipped in production but never wired into the offline replay harness that mirrors it

**Date:** 2026-08-06
**Source:** Gamma_Conductor fire (after-hours, fixing STATUS.md `### BROKEN:` fleet replay REDs)
**Theme fit:** C14 (dead/translated-but-unapplied knobs) + C6 (producer/consumer contract) + C7 (silent success -- a TOTAL mismatch, not a partial one, is the tell)

## Symptom
`backtest/tests/test_replay_fleet_arms.py::{test_missed_within_ratchet, test_three_arms_
entry_faithful}` failed with risky-3 `missed=16, matched=0/16` -- not a 1-2 bar drift like
every other known parity gap in this file, a **total** mismatch: the signal-driven replay
produced ZERO entries for risky-3 across the entire fidelity window.

## Root cause
`fleet_executor._effective_passed()` was extended 2026-07-23 (GATE-TIERS-IMPLEMENT) to read
`block['score_peak_passed']` instead of `block['passed']` for any arm whose accounts.json
carries a `gate_params.hard_skip_verdicts` key -- **even an empty list is enough to flip the
branch** (`"hard_skip_verdicts" in gate_params`, not `bool(...)`). The live producer
(`build_shared_signal.py::_bold_passed_blocks_from_row`) was updated the same day to emit
`score_peak_passed` alongside `passed`. But `backtest/replay_fleet_arms.py` -- the standalone
offline harness that reconstructs the SAME signal shape to prove signal-path vs backtest
entry-fidelity -- was never updated. Its `_synth_signal()` only ever set `passed`;
`score_peak_passed` was silently `None` on every synthetic block, forever. risky-3 is the
ONLY arm with `gate_params.hard_skip_verdicts` set today, so it was the only one silently
zeroed -- and it stayed that way from 2026-07-23 to 2026-08-06 (13 days) until this fire's
root-cause dig, because the fidelity gate's own failure message ("missed=16 > cap 0") reads
identically whether the cause is a REAL regression or a harness wiring gap.

## Fix (shipped this fire, commit `9c302f99`)
`_score_peak_passed_for_verdict()` mirrors `build_shared_signal._score_peak_check` exactly
(same score/trigger/action inputs `_passed_for_arm` already derived) and populates
`score_peak_passed` on every synthetic side-block, peak-gating `triggers_fired`/
`setup_name`/`confluence` the same way production's `_bold_passed_blocks_from_row` does.
risky-3: matched 0/16 -> 16/16. Also incidentally resolved risky-1's long-standing "KNOWN
extra=1, window-truncation false-positive at bar 1801" note -- that was misdiagnosed at the
time; it was the SAME wiring gap, not a level-state edge case. Ratchet tightened, guard
promoted (risky-1 now in the strict entry-faithful pin).

## Second-order finding (same fire, different mechanism)
The full fleet suite also turned up 2 REDs in `test_fleet_arm_parity.py` that were NOT
listed in STATUS.md's "6 pre-existing REDs" -- stale ATM-strike-at-$2K assertions against
THE SAME EVENING's earlier S3 ship (risky-3's ATM-tier-extension per-arm kill,
`3ac1d7b2`). The kill's own "vary-and-assert guard 6/6" did not include this test file, so
a same-night, self-inflicted regression sat undetected until this fire ran the full `-k
fleet` suite instead of just the named 6. Fixed same commit.

## Generalizable principle
When a producer's emitted signal SHAPE changes (a new field a consumer starts requiring),
every OFFLINE REPLICA of that producer (test fixtures, standalone replay harnesses, sim
signal-synthesizers) must be updated in the SAME change, or it silently drifts to a
permanently-wrong state that only announces itself as an opaque downstream assertion
failure. **A TOTAL mismatch (0/N, not N-1/N) on a parity gate is a strong prior that the
harness itself broke, not that the thing under test regressed** -- worth checking BEFORE
assuming a real trading-path regression. Separately: a same-night ship's own "guard 6/6"
scope is not the same as "ran the full test suite" -- a bounded vary-and-assert guard can
still miss a sibling test file that encodes the same fact a different way.
