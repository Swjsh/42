"""commit_scoped.py -- pathspec-scoped stage+commit, THE fix for shared-index
absorption in this multi-session checkout.

SCAR (2026-08-01, WEEKEND-TWELVE, Next-Twelve #3): tonight a bare `git commit`
(no pathspec) after a pathspec-scoped `git add` swept every OTHER concurrent
session's staged-but-uncommitted files into the current commit, under the
current commit's message. Content landed correctly in every case (nothing was
lost) but attribution/history was garbage. 5 confirmed incidents in one
session: 482a662a (absorbed WS7 live-watch + WS8 trendline-study artifacts),
da18da34 (absorbed WS12's 4 files), a363bd5f (absorbed WS8's staged prereg --
the sha WS8 then wrongly cited as its own freeze-order proof), be9c1b58
(absorbed the twin lane's SCHEDULED-TASKS.md cadence edit, undisclosed),
90fd1e40 (absorbed the deletion of a sibling lesson-inbox file). Full account:
strategy/candidates/_lesson-inbox/2026-08-01-shared-index-absorption-between-parallel-lanes.md

THE MECHANISM (empirically verified, not assumed -- see that inbox item):
`git commit -- <paths>` builds git a TEMPORARY index scoped to exactly those
paths (git exports `GIT_INDEX_FILE` pointing at a `.git/next-index-*.lock`
file for the duration of the commit, hooks included) and commits ONLY that
content, regardless of what else sits staged in the REAL shared index. A bare
`git commit` has no such scoping -- it snapshots the real `.git/index` as-is,
which in a multi-session checkout may carry other sessions' staged files.
Pathspec-scoped commit is therefore not a weaker convention than `git add`
discipline -- it is a STRUCTURAL guarantee git already provides, this script
just makes it the path of least resistance so nobody reaches for a bare
`git commit` under time pressure (a blocked pre-commit gate, a slow test run).

WHY A TWO-STEP `add` THEN `commit -- <paths>` (not `commit --only` alone):
`git commit -- <path>` refuses a path that has NEVER been staged at all --
"pathspec '<path>' did not match any file(s) known to git" -- so brand-new
untracked files need `git add -- <paths>` first. Both calls are pathspec-
scoped to the SAME explicit path list, so neither step ever touches a file
this invocation wasn't told about.

Usage:
    python setup/scripts/commit_scoped.py "<commit message>" <path> [<path>...]

Exit 0 = committed (pathspec-scoped, sha printed). Non-zero = nothing
committed (bad args, git error, or an index.lock collision that outlived the
retry budget) -- always with a message on stderr. This is a COMMAND, not a
guard: there is no "fail open" here, because refusing to guess at scope and
simply not committing IS the safe behavior. Contrast the pre-commit hook's
new tripwire (setup/git-hooks/pre-commit), which is fail-open BY design
because it can block J's/a session's real commit if it isn't.

Never runs `git add -A` / `git add .` / a bare `git commit` -- those are
exactly the footguns this script exists to replace, and are refused outright
if passed as a "path".
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Retry budget for a transient `.git/index.lock` collision -- the c416de4a
# lesson's own red-flag precondition ("another session is mid-staging RIGHT
# NOW"). Short and bounded: this is a live multi-session checkout, not a
# reason to hang indefinitely.
MAX_LOCK_RETRIES = 5
LOCK_RETRY_DELAY_S = 0.4

# The exact footguns this script exists to replace -- refuse them outright
# rather than silently doing something broader than the caller intended.
_BANNED_PATHSPECS = {"-A", "--all", ".", "*", "-a"}


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True
    )


def _git_with_lock_retry(args: list[str]) -> subprocess.CompletedProcess:
    """Retry ONLY on a transient index.lock collision; any other failure
    (merge conflict, hook rejection, bad pathspec) returns immediately so the
    caller sees the real error instead of a masked retry loop."""
    proc = None
    for attempt in range(MAX_LOCK_RETRIES):
        proc = _git(args)
        if proc.returncode == 0:
            return proc
        if "index.lock" not in (proc.stderr or ""):
            return proc
        if attempt < MAX_LOCK_RETRIES - 1:
            time.sleep(LOCK_RETRY_DELAY_S * (attempt + 1))
    return proc


def commit_scoped(message: str, paths: list[str]) -> int:
    """Stage + commit exactly `paths`, pathspec-scoped at both steps. Returns
    a process exit code (0 = success)."""
    if not message or not message.strip():
        print("[commit_scoped] FAIL: empty commit message.", file=sys.stderr)
        return 2
    if not paths:
        print("[commit_scoped] FAIL: no paths given -- refusing to guess scope. "
              "Name every file explicitly.", file=sys.stderr)
        return 2

    banned = [p for p in paths if p in _BANNED_PATHSPECS]
    if banned:
        print(f"[commit_scoped] FAIL: refusing broad pathspec(s) {banned} -- that is the "
              f"bare-add/bare-commit footgun this script exists to prevent. Name explicit "
              f"file or directory paths instead.", file=sys.stderr)
        return 2

    missing = [p for p in paths if not (REPO / p).exists()]
    if missing:
        print(f"[commit_scoped] FAIL: path(s) not found on disk (typo, or already "
              f"deleted?): {missing}", file=sys.stderr)
        return 2

    add = _git_with_lock_retry(["add", "--", *paths])
    if add.returncode != 0:
        print(f"[commit_scoped] FAIL: git add -- {paths}\n{add.stderr}", file=sys.stderr)
        return add.returncode

    commit = _git_with_lock_retry(["commit", "-m", message, "--", *paths])
    if commit.returncode != 0:
        print(f"[commit_scoped] FAIL: git commit -m <msg> -- {paths}\n"
              f"{commit.stdout}{commit.stderr}", file=sys.stderr)
        return commit.returncode

    sha = _git(["rev-parse", "--short", "HEAD"]).stdout.strip()
    stat = _git(["show", "--stat", "--format=", sha]).stdout.strip()
    print(f"[commit_scoped] OK: {sha} -- {len(paths)} path(s) committed, pathspec-scoped.")
    print(f"[commit_scoped] Any OTHER files already staged in the index were left "
          f"untouched (still staged, for whoever staged them to commit next).")
    print(stat)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        print("[commit_scoped] FAIL: need a commit message and at least one path.",
              file=sys.stderr)
        return 2
    message, paths = argv[0], argv[1:]
    return commit_scoped(message, paths)


if __name__ == "__main__":
    raise SystemExit(main())
