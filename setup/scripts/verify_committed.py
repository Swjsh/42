"""verify_committed -- assert a list of intended paths are TRACKED in git.

The producer/consumer contract applied to the *commit step*. Graduates the
2026-06-19 foot-gun (see markdown/doctrine/LESSONS-LEARNED.md "git commit --only drops
untracked"): `git commit --only <pathspec>` (and bare `git commit <pathspec>`)
commits only the working-tree state of TRACKED files plus already-STAGED changes.
It silently EXCLUDES untracked new files under the pathspec. New files an agent
(or you) created that the background `git add` never staged were dropped -- the
commit reported a large diff (from the modified/staged files) and the omission
went unnoticed. Hours of work were at risk of silent loss.

This is a deliberately tiny, zero-dependency helper so it can be called from a
pre/post-commit checklist OR from a test. It NEVER commits, stages, or mutates
anything -- it only INSPECTS git's index via `git ls-files --error-unmatch`.

Usage (CLI -- exit 0 = all tracked, exit 1 = some untracked):
    python setup/scripts/verify_committed.py path/a.py path/b.py
    python setup/scripts/verify_committed.py --quiet path/a.py     # no stdout, exit code only

Usage (import):
    from verify_committed import find_untracked, assert_all_tracked
    missing = find_untracked(["backtest/lib/risk_gate.py", ...])   # -> list of untracked
    assert_all_tracked(["..."])                                    # raises if any untracked
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Windows: spawn git without allocating a console window (this helper is sometimes
# imported/run under a console-less pythonw parent, where a bare git subprocess flashes
# a conhost window). CLAUDE.md L41 / C8.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class UntrackedFilesError(RuntimeError):
    """Raised when one or more intended paths are not tracked by git."""


def _git_root(start: Path | None = None) -> Path:
    """Return the repo root containing `start` (defaults to this file's repo)."""
    start = start or Path(__file__).resolve()
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(start.parent if start.is_file() else start),
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    if out.returncode != 0:
        raise RuntimeError(f"not a git repo (git rev-parse failed): {out.stderr.strip()}")
    return Path(out.stdout.strip())


def is_tracked(path: str, repo_root: Path | None = None) -> bool:
    """True iff `path` is tracked in git's index (i.e. `git ls-files` knows it).

    Uses `git ls-files --error-unmatch <path>`, which exits non-zero for any
    pathspec that matches no tracked file -- the exact, authoritative check.
    """
    repo_root = repo_root or _git_root()
    res = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    return res.returncode == 0


def find_untracked(paths: list[str], repo_root: Path | None = None) -> list[str]:
    """Return the subset of `paths` that are NOT tracked by git (order preserved)."""
    repo_root = repo_root or _git_root()
    return [p for p in paths if not is_tracked(p, repo_root=repo_root)]


def assert_all_tracked(paths: list[str], repo_root: Path | None = None) -> None:
    """Raise UntrackedFilesError listing every path that is not tracked.

    Call this AFTER a `git commit --only` (or before declaring work durable) with
    the session's known-new files. If any are still untracked, they were dropped
    by the commit and must be `git add`-ed + recommitted.
    """
    missing = find_untracked(paths, repo_root=repo_root)
    if missing:
        raise UntrackedFilesError(
            "These intended paths are NOT tracked by git (a `--only`/pathspec commit "
            "silently DROPS untracked new files). `git add` them and recommit:\n  - "
            + "\n  - ".join(missing)
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assert intended paths are git-tracked.")
    ap.add_argument("paths", nargs="+", help="paths that must be tracked")
    ap.add_argument("--quiet", action="store_true", help="no stdout; exit code only")
    args = ap.parse_args(argv)

    try:
        missing = find_untracked(args.paths)
    except RuntimeError as exc:
        if not args.quiet:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if missing:
        if not args.quiet:
            print("UNTRACKED (would be dropped by a --only commit):", file=sys.stderr)
            for p in missing:
                print(f"  ?? {p}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"OK: all {len(args.paths)} path(s) tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
