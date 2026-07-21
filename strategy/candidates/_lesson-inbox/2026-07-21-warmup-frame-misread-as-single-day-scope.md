# Lesson candidate: a shared "returns full history for warmup" loader got iterated as if it were single-day-scoped

**Date:** 2026-07-21 (conductor, AFTERHOURS fire)
**Where it bit:** `backtest/tools/dojo_exit_diversity_replay.py::extract_entries_and_ribbon`
**Related:** C6 (no look-ahead: filter <= current bar) -- but this is a DIFFERENT failure shape,
worth a distinct angle: not a future-peek, a **wrong-day-scope** contamination.

## Symptom

`analysis/dojo/EXIT-DIVERSITY-2026-07-20.md` produced a VOID "CONTROL_HOLDS" verdict: 4
requested curriculum days inflated to 810 episodes / 270 "entries" (most BS-synthetic, since
OPRA doesn't cover the wrong old dates) -- a `day=2026-06-30` episode carried
`cursor_et=2026-05-21`.

## Root cause

`setup/scripts/dojo/engine_step.py::load_day_bars(replay_day)` is DOCUMENTED (its own
docstring) to return the FULL multi-month cache frame up through `replay_day`, not just that
day's bars -- by design, because the live engine's ribbon/level EMA warmup needs >=80 RTH bars
of prior history. This is the CORRECT contract for its actual consumer
(`heartbeat_core._build_payload`, which internally RTH-filters and windows to the bar it's
scoring).

`dojo_exit_diversity_replay.py`'s entry-scan harness called this same loader, then iterated
**every RTH bar in the returned frame** as if each one belonged to the target day -- treating a
warmup-scoped return value as if it were day-scoped. The function's contract was correct; the
NEW caller silently assumed a narrower scope than the shared function actually promises.

## The general antidote

When reusing a shared loader/producer whose docstring says "returns X for the whole window,
not just the target" (a WARMUP or CONTEXT frame), a new consumer must explicitly re-slice to
its own actual scope of interest BEFORE iterating it as an event stream -- passing the
untrimmed frame through unchanged only where a downstream call (here: `engine_step.step()`,
which itself needs the untrimmed history for warmup) actually requires the full window. Two
different "day" scopes were silently conflated: (a) "days needed as history/warmup context"
and (b) "days whose bars should be treated as candidate iteration/event points." A function
correctly serving (a) does not make its return value safe to iterate as (b) without an
explicit re-slice.

## Suggested class

New sub-bullet under C6 (no look-ahead / bar-scope discipline) or its own C-class if
lesson-author judges it distinct enough: "a warmup/context frame is not an iteration frame --
re-slice to the caller's own actual scope before treating a shared loader's full return value
as an event stream."

## Fix shipped

`day_rth = rth[rth["timestamp"].dt.date == day_date]` -- entry/ribbon cursor loop now walks
only the target day's own RTH bars; `bars` (untrimmed) still passed to `engine_step.step()`
for warmup. Guard: `test_extract_entries_scoped_to_target_day_only`
(`backtest/tests/test_dojo_exit_diversity_replay.py`), RED-proofed via `git stash`.
