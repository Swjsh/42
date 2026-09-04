---
filed: 2026-09-04
filed_by: conductor AFTERHOURS 05:30 ET fire
kind: lesson
status: pending
---

# A non-atomic `write_bytes()` on a shared artifact read by the full test suite produced a "flaky" test that survived a scoped pytest retry three times in one night

## Symptom

`tests/test_regime_early_classifier_guards.py::test_build_regime_early_classifier_walk_forward_no_leakage`
appeared in `guard_runner_full.py`'s `still_failing_after_retry` list three separate times on
2026-09-04 (00:01, 00:36, 03:42 ET), yet never reproduced when re-run directly, standalone or
scoped together with its full-suite co-failure, hours apart. Two earlier conductor fires (01:03 ET,
03:59 ET) investigated it, found nothing, and correctly declined to guess a fix -- this is the right
call when a hypothesis can't be confirmed, but the SAME test kept re-appearing, which is the signal
that something real (not noise) was underneath.

## Root cause

`backtest/lib/regime_slice.py::load_library()` memoizes the on-disk `analysis/regime-library/
day-archetypes.json` artifact in a module-level `_cache` dict, and the builder that produces that
artifact (`backtest/tools/build_day_archetypes.py::main()`) wrote it with a direct
`OUT_JSON.write_bytes(payload)` -- which truncates the file in place *before* writing the new bytes.
Any reader that opens the file in that truncate-to-write window sees a torn/incomplete JSON body.
This project runs several parallel Claude sessions overnight, and regime-library research was
active work that same night (day-type grinder, structure-classifier shadow) -- exactly the
concurrent-writer condition. The full test suite (12,000+ tests, ~30-40 min) is a wide enough
window for a `load_library()` call to land inside someone else's in-place rewrite of the artifact,
while a direct standalone or scoped-pair re-run minutes/hours later never overlaps that window.

## Fix

`build_day_archetypes.py::main()` now writes to a same-directory `.tmp` sibling and calls
`os.replace(tmp, OUT_JSON)` -- the same idiom already used by
`backtest/autoresearch/trendline_watch.py` and the `futures/` writers. A concurrent reader now
always sees either the complete old file or the complete new one, never a partial one.

## Guard

`backtest/tests/test_regime_library_guards.py::test_write_uses_temp_file_and_atomic_replace` +
`::test_write_never_truncates_target_before_the_swap` -- RED-proofed live via `git stash` on the
source file alone (both fail against the pre-fix `OUT_JSON.write_bytes(payload)`, one showing the
real target file truncated to 0 bytes by a simulated interruption).

## Pattern (for the L## writeup)

Same class as the STATUS.md writer bug fixed 2026-09-03 (`_find_real_heading`): a shared JSON/text
artifact with an in-place, non-atomic writer, read by many consumers across a long-running process,
on a box that runs several parallel sessions overnight. **Any producer script that writes an
artifact another process reads live should use temp-file + `os.replace`, never a direct
`write_bytes`/`write_text` on the real path** -- grep `backtest/tools/*.py` and `backtest/lib/*.py`
for other `OUT_JSON.write_bytes(` / `.write_text(` calls without a `.tmp`+`os.replace` pair as a
follow-up sweep (not done this fire -- scope discipline, single bounded item).

## Files

- `backtest/tools/build_day_archetypes.py` (fix, commit pending)
- `backtest/tests/test_regime_library_guards.py` (2 new guard tests, commit pending)
- `automation/state/logs/guard-flaky-tests.jsonl` (the evidence trail -- 3 occurrences)
