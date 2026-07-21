# git commit -- <pathspec> (without --only) silently resurrects a staged `git rm --cached` deletion

**Date:** 2026-07-20 (conductor, AFTERHOURS)
**Class:** re-violated lesson (2nd occurrence of the SAME symptom — "untrack this live state file" — now root-caused at the git-mechanics level, one level below the state-file-reversion lesson itself)

## What happened

Two separate fires (`25e31e2` then `5a2becb`) both **claimed** to gitignore+untrack
`circuit-breaker*.json`/`today-bias.json` (STATE-FILE-REVERSION incident), both reported
"4/4 green" / "curated safety gate PASS", and **both silently failed to actually untrack
the files** — `git ls-tree HEAD` kept showing the original blobs after each "fix" commit.
A third fire (this one) discovered the guard test was RED at the start (contradicting the
prior "green" claims — an OP-33 violation one level up), root-caused it, and needed **four
attempts** to actually land the fix.

## Root cause (the git mechanic, confirmed empirically)

`git commit -m "..." -- <pathspec>` **without `--only`** does NOT commit the *staged
(index)* content for the given paths. Per git's own docs, when explicit pathspecs are
given to a plain `git commit`, git treats it as "commit the CURRENT WORKING TREE content
of these paths" (equivalent to an implicit `git add <pathspec>` immediately before the
commit) — **not** "commit whatever I already staged for these paths." Since a
`git rm --cached <path>` leaves the file sitting on disk (that is the whole point — only
the index entry is removed), the very next `git commit -- <path>` silently **re-adds it
from disk**, discarding the staged deletion entirely. `git status`/`git diff --cached`
right before the commit correctly show `D` staged — the commit still drops it.

The fix requires ONE of:
1. `git commit --only -- <pathspec>` (forces index-only content for named paths) — but
   this failed with "nothing to commit" in this session when re-run against paths staged
   in an EARLIER, separate tool invocation (suspect: some git 2.43-on-Windows interaction
   between `--only`'s internal diff and a previously-built partial commit tree; not fully
   root-caused, not worth the tokens to chase further since workaround #2 is simpler and
   was verified to work cleanly).
2. **A plain `git commit -m "..."` with NO pathspec at all**, when (and only when) you've
   confirmed via `git diff --cached --stat` (no path filter) that the *entire* staged
   index is exactly the deletions you intend — nothing else. This is what actually worked.
   Confirm-before-commit: `git diff --cached --stat` (must show ONLY your target files) →
   `git commit -m "..."` (no `--`, no pathspec).

**Always verify a claimed untrack with `git ls-tree HEAD -- <path>` (must be empty) in the
SAME fire before writing "N/N green" to STATUS.md** — `git status`/pytest-guard green only
proves the *staged* state is correct, not that the commit actually captured it. This is the
concrete, mechanical form of "verify, don't claim" (OP-33) for this specific operation
class.

## Recommended graduation (OP-25)

This is the SECOND fire to hit this exact mechanic while doing the SAME class of fix
(untrack a live state file) — and `STATE-FILE-REVERSION-AUDIT-FOLLOWUP` (queue.md, MED,
pending) is about to need this exact operation for potentially dozens more files. Two
options, either is fine:
- A tiny reusable helper `setup/scripts/git_untrack_state_file.py` that does
  `git rm --cached` + verifies `git diff --cached --stat` is exactly the target set +
  plain `git commit` + verifies `git ls-tree HEAD` is empty for every target, refusing to
  report success otherwise — so no future fire can repeat this mistake.
- OR fold this prose directly into `markdown/doctrine/LESSONS-LEARNED.md` under the
  STATE-FILE-REVERSION lesson's existing entry (same incident family) with an explicit
  "verify via `git ls-tree HEAD`, not just the guard test" addendum, since the underlying
  guard test itself was proven insufficient to catch this (it reads the *index*, which was
  correctly staged — the commit was the broken step, and the guard doesn't re-check
  post-commit within the same test run).

Either path should be graduated the next time an untrack-a-tracked-file operation is
needed (the audit-followup item is the natural trigger) rather than left as prose only.
