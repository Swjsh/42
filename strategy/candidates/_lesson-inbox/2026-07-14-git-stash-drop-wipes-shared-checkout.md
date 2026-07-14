# Tree-wide `git stash` in the shared live checkout is a data-shredder

**Date:** 2026-07-14
**Severity:** CRITICAL — live production data loss (recovered, barely)

## Symptom

`automation/state/core-decisions.jsonl` + all 3 active fleet arms' `decisions.jsonl` reverted
on disk to the last commit that touched them (667217a, 2026-06-26) mid-premarket. ~3 weeks of
live trading-decision history (2026-06-27→07-13) vanished; `git status` showed the files clean.
211 files / ~140K uncommitted lines were affected in total (agent memories, recommendation
scorecards, append-only research logs, trades.csv rows).

## Root cause (one sentence)

A workflow subagent ran `git stash && pytest && git stash pop` in the SHARED main checkout to
test its 3 files in isolation; the `&&`-chained pop never executed, the agent selectively
`git checkout stash@{0} -- <its 3 files>` and then ran `git stash drop` — discarding the only
copy of every OTHER uncommitted change in the tree.

## Why it was recoverable

A dropped stash is a dangling commit, not deleted data: `git fsck --unreachable --no-reflogs`
surfaced it (`232a161`), pinned gc-proof via `git branch recovery/stash-data-loss-2026-07-14`.
Restore = 3-way classify (current==stash → fine; current==pre-stash HEAD → restore;
else diverged → prefix-checked splice-merge `stash + post-wipe tail` for append-only logs).

## The fix / rule

1. **NEVER run tree-wide `git stash`, `git reset --hard`, `git checkout .`, or `git clean` in
   the shared main checkout.** Agents needing a clean tree for a test MUST use a worktree
   (`EnterWorktree` / `git worktree add`) or pathspec-scoped stash (`git stash push -- <paths>`).
2. **If a stash pop fails, the stash is the only copy of everyone else's work — escalate,
   never `git stash drop` after a partial recovery.**
3. Continuously-written state files (decision ledgers) must not be tracked-but-rarely-committed:
   gitignore + untrack them (done for the 4 ledgers 2026-07-14) so routine git ops can never
   touch them. Multi-week uncommitted deltas as the only copy of live data = standing loaded gun.

## Guard candidate

Graduated guard: a test asserting the 4 ledger paths match `.gitignore`
(`git check-ignore automation/state/core-decisions.jsonl` etc.), so a future re-track fails CI.

## Cross-refs

Related lesson family: L-git-commit-only-drops-untracked-2026-06-19 (git ops silently dropping
working state). Reflog signature of this incident: `reset: moving to HEAD` (stash's internal
reset) with NO matching stash entry afterward.
