# 1,176 files under strategy/candidates/ were never git-added (discovered 2026-07-22 ~22:05 ET)

**Context:** discovered as a side-effect of shipping `CHEF-CANDIDATES-CONSOLIDATION-SWEEP` batch
1 (queue.md) this fire — `git add strategy/candidates/` (before being scoped down to the exact
250 moved files) surfaced **1,176 `??` untracked entries**, spread across the top-level dated
candidates, `_analysis/`, `_chef-inbox/`, and `_lesson-inbox/*.DONE`. Only ~443 of the 1,619
top-level `.md` files this fire scanned were actually tracked in git; the rest have been sitting
on disk, uncommitted, for an unknown span (samples ranged from 2026-06-26 through 2026-07-22,
i.e. this has been accruing continuously, not a one-time gap).

**Why this matters (not just tidiness):**
- **Nothing here is backed by version control.** A disk failure, a bad `rm`, or a careless
  cleanup script wipes it with no recovery path — this is exactly the class of risk OP-22's
  "move not delete" archival policy is meant to guard against, and it's moot if the file was
  never committed in the first place.
- **`_chef-inbox/` and `_analysis/` untracked files are LIVE Kitchen pipeline state** (per
  `_archive/README.md`'s own "Deliberately KEPT" list) — an author picking up inbox work off
  `git log`/`git blame` (a normal debugging move per this repo's own debugging doctrine) would
  see nothing, because there's no commit to find.
- **It silently inflates every future `git add strategy/candidates/`** — this fire had to
  discover and hand-scope around it live rather than trusting a directory-level `git add`; the
  next author who isn't paying attention could accidentally sweep 1,176 unrelated files into an
  unrelated commit (or, working the other direction, could accidentally believe a specific file
  is safely committed when it isn't).

**Recommended fix (NOT attempted this fire — rail 3, one bounded task; also needs a scoping
decision this lesson doesn't make: some of these 1,176 may be genuinely meant to stay
gitignored/ephemeral, so a blind `git add -A` is wrong):**
1. Audit whether `strategy/candidates/` (or a subset of it) is intentionally excluded somewhere
   (check `.gitignore` for a stale/overly-broad pattern — first thing to rule out).
2. If it's an oversight: `git add` the untracked files in dated batches (same 200-300/fire
   cadence as the consolidation sweep) with a commit message per batch, OR one bulk
   "backfill: track N previously-untracked strategy/candidates/ files" commit if J prefers.
3. Graduate a guard: a cheap pre-commit or periodic check that flags `strategy/candidates/`
   untracked-file count exceeding some small threshold (e.g. >20), so this can't silently
   re-accumulate to 1,176 again without anyone noticing (C7: silent success is failure — this
   sat invisible for weeks).

**Filed as:** lesson-inbox item for `lesson-author` to grade/encode an `L##` if it judges this
crosses the bar (a genuine producer-visibility gap, arguably belongs in C34 "tree-wide git ops /
untracked state" or C9 "anchor paths" family — `lesson-author`'s call). Also cross-posted as a
`queue.md` HIGH item (`STRATEGY-CANDIDATES-UNTRACKED-BACKFILL`) for the next AFTERHORS conductor
fire to action per the recommended fix above.
