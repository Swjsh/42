# Lesson: a stub's own pipeline docstring cited a dependency script as callable that was never actually built

**Filed:** 2026-07-23 ~06:xx ET, conductor (AFTERHOURS), during EDGE-MATRIX-NIGHTLY-RERUN Step 1.

**Symptom:** `backtest/tools/edge_matrix_rerun.py`'s own docstring (written 2026-07-23, same
session as the frozen edge-matrix build) named `python backtest/tools/build_day_inventory.py
--extend` as "Step 1" of its pipeline, with a full prose spec of what it does (TRUE-ET frame,
per-day source dedupe, OPRA coverage census). The file `build_day_inventory.py` did not exist
anywhere in the repo -- confirmed via `Glob "**/build_day_inventory*"` -> zero hits, before
building it this fire. The item queued in `queue.md` (`EDGE-MATRIX-NIGHTLY-RERUN`) had been
surfaced by `task_scorer.py --top` as the ranked-#1 MED item across MULTIPLE prior conductor
fires (visible in `STATUS.md`'s own history: "`task_scorer.py --top` surfaced
`EDGE-MATRIX-NIGHTLY-RERUN` (MED) again" appears at least 3 times before this fire) and was
skipped each time in favor of higher-priority HIGH items -- nobody had actually opened the stub
file to check whether its own named Step 1 dependency existed until this fire did.

**Root cause:** a design docstring written in the SAME session as a big pipeline build
(`EDGE-MATRIX-2026-07-23.md`, 6 family runners, ~98 cells) narrated the FULL intended
end-to-end loop, including steps that were merely planned, not yet built -- and used
present-tense "PIPELINE (what --refresh runs, in order)" prose indistinguishable from a
description of working code. `cmd_refresh()` itself DID correctly self-report `STATUS: STUB`
and refuse to fire silently ("Refusing to fire them implicitly from a stub") -- the CLI
entry point was honest. But the prose ABOVE it (the docstring, which is what a human or a
future conductor fire reads FIRST, before ever running `--status`) was not similarly
hedged for its cited sub-dependency; it read as a spec of an existing pipeline, not a wishlist.

**Generalizable pattern:** when a stub script's docstring narrates a multi-step pipeline
and names OTHER scripts as steps, a reader (human or a future Claude fire) will reasonably
assume those named scripts exist and do what's described -- unless the docstring explicitly
marks each named dependency's build status. This is the "prose claims capability, code lacks
it" shape (adjacent to C14 dead/unapplied-knob class, but for TOOLING references rather than
config knobs) applied to inter-script dependencies in a stub's own spec.

**Fix applied this fire (not just noted):** built the actual `build_day_inventory.py`
(Step 1), with 17 guard tests, RED-proofed live. Also corrected `edge_matrix_rerun.py`'s
Step 1 docstring block to state the ACTUAL shipped filename/behavior (`day-inventory-
extended.json`, not the originally-proposed `-<today>.json` which would have collided with
the frozen original's own filename) instead of leaving the aspirational text unchanged next
to now-real code.

**Suggested guard (for lesson-author to size):** a repo-wide sweep (or a narrow pytest
collected from stub-marked files: `grep -l "STATUS: STUB" backtest/tools/*.py`) that, for
every script path a docstring names as a pipeline step (`python backtest/tools/<name>.py`
pattern in a `"""..."""` block), asserts that path actually exists on disk. Cheap, mechanical,
catches exactly this class before a future conductor fire wastes a STAGE 1 pick assuming a
named tool works. Scope this narrowly (stub-tagged files only) to avoid false positives on
docstrings describing genuinely external/future tooling.
