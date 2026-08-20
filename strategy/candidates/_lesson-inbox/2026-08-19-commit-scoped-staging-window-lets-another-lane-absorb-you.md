# commit_scoped.py protects you from ABSORBING others -- not from BEING absorbed

**Date:** 2026-08-19 (custody lane)
**Family:** C34 (tree-wide git ops in the shared checkout) -- a NEW mechanism, not a
repeat of the 2026-08-01 item (`...shared-index-absorption-between-parallel-lanes.md.DONE`).

## What happened

The custody lane ran `commit_scoped.py "<msg>" <5 paths>` exactly as designed. The safety
gate passed (59 tests). The commit then died with:

    fatal: cannot lock ref 'HEAD': is at df50f823... but expected c10f9279...

All 5 of its files -- `setup/scripts/archive_ledgers.py`,
`setup/scripts/install-ledger-custody.ps1`, `backtest/tests/test_archive_ledgers.py`,
`.gitignore`, `automation/state/SCHEDULED-TASKS.md` -- had landed inside **another lane's**
commit `df50f823 feat(cockpit): the full command center`, a 15-file bare commit.

Content was fine (verified: `git diff --quiet HEAD` clean on all 5, 29/29 tests green).
Attribution was garbage: a data-custody archive is filed under a dashboard commit.

## Root cause (one sentence)

`commit_scoped.py` must `git add` before `git commit -- <paths>` (git refuses a pathspec it
has never seen), and during that add→gate→commit window -- widened to ~6s by the safety gate
itself -- a concurrent lane's **bare `git commit`** snapshots the whole shared `.git/index`
and sweeps the staged-but-uncommitted files of every other lane into its own commit.

## Why the existing fix does not cover this

The 2026-08-01 lesson made *our* commits scoped so we stop absorbing *others*. It is
one-directional. The victim here did everything right; the absorber was the lane running a
bare `git commit`. Scoping your own commit gives you **zero** protection against being
absorbed -- and the safety gate makes your exposure window *longer*, not shorter.

## Candidate fixes (for the lesson-author / graduated guard)

1. **Shrink the window:** run the safety gate BEFORE `git add`, not between add and commit,
   so staged time is milliseconds instead of seconds.
2. **Detect and re-drive:** on `cannot lock ref 'HEAD'`, have `commit_scoped.py` check
   whether the target paths landed in the new HEAD; if so, say so loudly (content safe,
   attribution wrong) instead of returning a bare fatal the caller must interpret.
3. **Stop the absorber:** the pre-commit hook already WARNs on bare-commit heuristics but
   "never blocks". A bare `git commit` with zero pathspec in a checkout with >1 lane's files
   staged is the actual defect -- consider blocking it rather than warning.
4. Worktrees per lane remain the structural answer; the shared checkout is the hazard.

## Verification quoted

    $ git show --name-only --format="" df50f823 | grep archive_ledgers
    setup/scripts/archive_ledgers.py
    $ git diff --quiet HEAD -- setup/scripts/archive_ledgers.py && echo IDENTICAL
    IDENTICAL

No history rewrite was attempted: `main` is shared and other lanes are mid-flight.
