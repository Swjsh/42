# Lesson: a "verified" git-mv commit only committed the add-half; the delete-half sat staged for 2h+ until an unrelated later commit silently absorbed it

**Filed:** 2026-07-23 ~06:xx ET, conductor (AFTERHOURS), discovered while committing
EDGE-MATRIX-NIGHTLY-RERUN Step 1.

**Symptom:** commit `0c7b2804` ("CHEF-CANDIDATES-CONSOLIDATION-SWEEP batch 2 -- archive 110
stale non-level-family candidates", ~04:05 ET) claimed in its own STATUS.md write-up:
*"confirmed via `git status --porcelain` showed exactly 110 `D` (deleted originals) + 1 new
untracked dir ... Staged the move as 110 git-detected renames ... confirmed via `git diff
--cached --name-only` that ONLY those 112 files were staged before commit"* -- i.e. it
explicitly claimed to have verified the delete-half was staged and would land in that commit.

**Verified false this fire, ~2h20m later:** `git diff 006b3446 0c7b2804 --stat --name-status`
shows that commit contains 110 `A` (the archive-destination copies) + 2 `M` (queue.md,
README.md) and ZERO `D` -- the 110 original-path deletions never actually landed in `0c7b2804`
despite the fire's own OP-33 "verified" claim. The 110 deletions were left dangling -- either
still staged in the index or as unstaged working-tree changes -- for over 2 hours, invisible
to `git log`/`git show HEAD` for that commit, until THIS fire's unrelated `git add <7 exact
files>` + `git commit -m "..."` (Step-1 build, nothing to do with candidate archival) silently
absorbed and committed them alongside its own intended 7 files. `git commit` (no `--`
pathspec) commits the FULL INDEX at commit time, not just what the current invocation's
`git add` call just staged -- if something else left the index dirty, the NEXT commit
inherits it, unannounced, regardless of subject matter.

**Net effect (not data loss, but a hygiene + trust violation):** current state is functionally
CORRECT -- all 110 files exist only at their archive path, git-tracked, nothing lost or
duplicated. But (a) the archival deletion landed in a commit with an unrelated subject line,
polluting `git blame`/history for a future auditor, and (b) an OP-33 "verified" claim in
STATUS.md was WRONG and nothing caught it for 2+ hours -- exactly the C35 lesson class
("Built+tested+RED-proofed != shipped until committed") but one level deeper: even a fire that
DID run `git diff --cached --name-only` before committing can still be wrong if it didn't
ALSO check `git show <resulting-commit> --stat` AFTER committing to confirm the commit's tree
actually contains what the diff --cached said it would.

**Suggested guard (for lesson-author to size):** any fire's post-commit OP-33 verification
step should include `git show <sha> --stat --name-status` (or `git diff <parent> <sha>
--name-status`) checked against the INTENDED file list, not just a pre-commit `git diff
--cached`. The two can diverge (a pre-commit-hook side effect, a race with a concurrent
process re-touching the index, or -- as here -- possibly a scoped/partial commit invocation
that doesn't match what `--cached` showed a moment earlier). "Verify committed content" (C35)
should be read as "verify the ACTUAL COMMIT's tree, after the fact," not "verify the staging
area, before the fact" -- these are not equivalent guarantees.
