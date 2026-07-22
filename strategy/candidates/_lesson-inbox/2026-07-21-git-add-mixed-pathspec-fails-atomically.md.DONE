# Lesson candidate: `git add` with a mix of valid + stale (already-renamed/nonexistent) pathspecs fails ATOMICALLY and stages NOTHING from that call, not just the bad path

> Filed by conductor (AFTERHOURS) 2026-07-21 ~21:55 ET, self-caught via OP-33 verify-don't-claim
> (this fire's own `git commit`, not a later fire's audit).

## Symptom

This fire ran one `git add` command listing 7 paths: `CLAUDE.md`, `markdown/doctrine/LESSONS-LEARNED.md`,
and 5 lesson-inbox paths — 2 old (pre-rename) + 3 new (`.DONE`, post-`git mv`). One of the old
paths no longer existed (already renamed away by an earlier `git mv` in the same fire), so git
printed `fatal: pathspec '...' did not match any files` and the command exited non-zero. The
immediately following `git commit` then reported `3 files changed, 0 insertions(+), 0
deletions(-)` — only the 3 already-staged renames landed; `CLAUDE.md` and `LESSONS-LEARNED.md`
(the actual content of the fire's work — new L236-L238 lesson prose, OP-25 index folds) were
**silently absent from the commit**, despite the Edit tool having reported both writes succeeded.
Caught immediately by running `git status --short -- CLAUDE.md markdown/doctrine/LESSONS-LEARNED.md`
right after the commit (OP-33 discipline: verify the commit, don't trust the Edit tool's success
message as proof of "shipped") — both files still showed `M` (modified, unstaged), proving the
first commit had NOT captured the real content. Fixed same-fire with a second `git add` (correct
paths only) + a follow-up commit.

## Root cause

`git add <path1> <path2> ... <pathN>` is not a per-path best-effort operation in the shell — when
ANY listed pathspec fails to resolve to a tracked-or-existing file (`fatal:` class error, as
opposed to a `warning:`-class no-op), the WHOLE invocation aborts before staging happens, and NONE
of the valid paths in that same call get staged either. This is easy to trigger in exactly the
failure mode this fire hit: doing a `git mv` (rename) earlier in the same fire, then later
reflexively listing the OLD pre-rename name in a batch `git add` alongside genuinely-new files —
the old name is gone, the whole batch silently fails to stage, and `git commit` proceeds anyway
(commit is not blocked by a failed prior `git add`) with whatever WAS already staged from an
earlier partial/successful add, producing a "successful" commit that is quietly missing the
content the author actually meant to ship.

## The rule

1. **Never mix a just-renamed file's OLD path into a later `git add` in the same fire** — after
   `git mv old new`, only `new` exists; referencing `old` again is a self-inflicted stale pathspec.
2. **After ANY `git add` invocation that lists more than one path, check its own exit code /
   output for `fatal:`** before assuming the paths after it staged successfully — a `fatal:` in
   the middle of the output is not "one path skipped," it is "nothing in this call staged."
3. **Always verify the actual commit content, not just that `git commit` printed a hash** —
   `git show --stat HEAD` or `git status --short -- <the exact files you meant to ship>`
   immediately after committing. This is OP-33's `verify_committed` principle applied one level
   deeper: it is not enough to verify the repo is clean after commit, you must verify the SPECIFIC
   files you intended are the ones that moved from working-tree to history.

## Encoded in

Not yet — first occurrence, self-caught and self-corrected within the same fire before it could
propagate to STATUS.md/J as a false "shipped" claim, so no downstream harm this time. Not yet
meeting the OP-25 re-violation bar for a code guard. If this pattern recurs (a future fire's
commit undercounts files vs. what it intended to stage), that is the graduation trigger for a
lightweight wrapper/reminder — e.g. a `verify_committed(expected_files: list[str])` helper in
whatever shared git-ops utility handles conductor commits, that diffs `git show --stat HEAD` file
list against an explicit expected-files list and raises loud if they don't match, rather than
trusting `git commit`'s own exit code.

## L## (optional)

Suggested next available: lesson-author greps `LESSONS-LEARNED.md` for current max (L238 as of
this fire) and assigns **L239**. Cross-reference C35 (built+tested+RED-proofed != shipped until
committed) as the closest existing cluster — this is a NEW mechanism within that class (an
atomically-failed multi-path `git add`, not a missed commit or an uncommitted worktree).
