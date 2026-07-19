# GT simulator missing a live-only decision-layer gate silently over-counts trades

**Date:** 2026-07-18 (AFTERHOURS conductor fire)
**Source:** REPLAY-FLEET-ARMS-FIDELITY-DRIFT (queue.md), safe-1 `missed=1` at bar 1394

## Symptom
`backtest/replay_fleet_arms.py`'s entry-fidelity gate showed safe-1 under-trading its own
ground truth (`missed=1`) — the signal-driven arm path never entered a trade that
`orchestrator.run_backtest` (GT) took.

## Root cause
`orchestrator.run_backtest` has **zero implementation** of `structure_veto_enabled`
(`gate_params["structure_veto_enabled"]`, `engine_cli.py`) — a live-decision-layer gate
that IS applied by `decide_payload`, the same deterministic brain that drives
`core-decisions.jsonl` / any live-signal replay. Because GT's own trade simulator is
blind to this gate, it can include trades the live decision layer would actually SKIP,
making GT look "ahead" of a perfectly faithful signal-driven replay — the replay wasn't
under-trading; GT was **over-counting**.

## Why the first hypothesis was wrong (and how it was caught)
An earlier session (queue.md history) attributed a *different* bar's mismatch to
window-truncation on `level_states`/`sequence_rejection` accumulation (a real, separately
documented mechanism — see risky-1's `KNOWN_MAX_EXTRA` bar 1801). That hypothesis was
never bar-confirmed (the box was saturated by a concurrent grind both times it was
attempted). This fire re-ran fresh on a quiet box and got a DIFFERENT bar's mismatch
entirely (1394/1761, not 1405) — the stale hypothesis would have been wrong even if
"fixed." **Lesson: a hypothesis filed under time pressure with an unconfirmed bar number
must be re-verified against a FRESH run before acting on it — the mismatch signature can
shift between sessions even when the test still fails the same way (same RED, different
bars).**

## Generalizable lesson
Any harness that treats `run_backtest`'s trade list as ground truth for a comparison
against a live/replayed decision-layer verdict (`decide_payload`, `engine_cli`, etc.) is
only as faithful as the SET OF GATES both paths apply. `run_backtest` and `decide_payload`
are two independently-maintained simulators of "the same" decision — a gate added to one
(here: `structure_veto_enabled`, added under the v15.3 chart-stop-primary rollout) without
a corresponding update to the other creates a **silent, asymmetric drift** that doesn't
throw, doesn't 500, and doesn't fail loudly — it just quietly shows up as "missed"/"extra"
in whatever downstream fidelity gate compares them (C15 — gates interact multiplicatively;
this is the sibling case where a gate MISSING from one path acts identically to a phantom
gate present in the other).

## Fix applied this fire
`_ground_truth_trades` in `backtest/replay_fleet_arms.py` gained a `structure_veto`
post-filter — the SAME pattern already used there for `direction_lock`/elite/
`min_confidence` (gates `run_backtest` cannot express, applied as a post-filter to the
GT trade set instead). Not a new pattern; an existing pattern correctly extended to a
4th gate.

## Graduation candidate (not done this fire — scope)
If a 5th such gate/gap surfaces (a gate live in `decide_payload`/`engine_cli` but absent
from `orchestrator.run_backtest`), the durable fix is a **registry/diff test**: assert
every `gate_params.get("*_enabled")` key `engine_cli.py`'s SKIP_* logic reads has either
(a) a corresponding implementation in `orchestrator.py`, or (b) a named, justified
post-filter in every harness that treats `run_backtest` as ground truth against a
`decide_payload`-driven signal. Today's fix is scoped to `replay_fleet_arms.py` only
(the one harness that hit this); `lesson-author`, use judgment on whether this is common
enough yet (2 known gates so far: `structure_veto`, and implicitly the pre-existing
`min_confidence`/elite/`direction_lock` trio) to warrant the registry now vs. wait for a
3rd occurrence per the standing OP-25 "re-violated lesson graduates" bar.
