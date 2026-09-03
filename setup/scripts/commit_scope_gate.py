"""commit_scope_gate.py -- the automation-only REFUSE decision for the
pre-commit hook (`setup/git-hooks/pre-commit`).

CONTEXT (queue item COMMIT-SCOPED-ENFORCEMENT, filed 2026-08-21, lesson:
strategy/candidates/_lesson-inbox/shared-index-absorption-reverted-live-fix-
2026-08-21.md): the pre-commit hook's existing dir-count WARN (see that file)
is non-blocking by design and got read-and-discounted once already -- one of
the absorbed files that fire was `heartbeat_core.py`, the LIVE trading
engine, briefly reverting a tested fix onto `main`. WARN alone was not
enough for an AUTOMATED fire's own commit (a human is in the loop for an
interactive commit and can read the WARN; an unattended script cannot).

THIS MODULE is the harder half: when the committing process has marked
itself as automation (`GAMMA_AUTO_COMMIT=1` in the environment), the hook
REFUSES the commit outright if the staged set contains any file outside an
explicit allow-list the automation must declare (`GAMMA_COMMIT_PATHSPEC`,
colon-separated pathspecs). No declared pathspec + any staged file = refuse
(automation that doesn't say what it means to commit is exactly the failure
mode this exists to catch). `setup/scripts/commit_scoped.py` sets this env
var itself so it stays the one-call safe path for anyone (automated or
interactive) who wants to just not think about it.

FAIL-OPEN CONTRACT -- load-bearing, do not weaken:
  - This decision function is invoked by the hook ONLY when
    `GAMMA_AUTO_COMMIT=1` is already set. An interactive commit (J's
    session, or any commit without that marker) NEVER reaches this code --
    the hook does the marker check in shell before ever spawning python, at
    zero added cost for the overwhelmingly common interactive-commit case.
  - `GAMMA_COMMIT_SCOPE_OFF=1` is a hard opt-out the hook checks BEFORE
    invoking this module at all -- a genuine multi-scope automated commit
    can always get through. This module has no opinion on that flag.
  - This module never blocks a HUMAN. It only ever runs for a fire that
    self-identified as automation.

Usage (as invoked by the hook):
    printf '%s\n' "$STAGED" | python commit_scope_gate.py
    # reads staged paths on stdin (one per line), GAMMA_COMMIT_PATHSPEC from
    # env. Exit 0 = commit proceeds (nothing to print). Exit 1 = refuse;
    # offending paths are printed to stdout, one per line, for the hook to
    # relay to stderr.

Also importable for tests: `decide(staged_files, pathspec_env) -> (bool, list[str])`.
"""
from __future__ import annotations

import os
import sys


def _pathspec_allows(path: str, pathspecs: list[str]) -> bool:
    """True if `path` is inside (or exactly equal to) one of the declared
    pathspecs. A pathspec `strategy/candidates` allows `strategy/candidates`
    itself and anything under `strategy/candidates/...` -- it does NOT allow
    `strategy/candidates2/foo` (prefix match is directory-boundary-aware)."""
    path = path.strip().strip("/")
    for raw in pathspecs:
        ps = raw.strip().strip("/")
        if not ps:
            continue
        if path == ps or path.startswith(ps + "/"):
            return True
    return False


def decide(staged_files: list[str], pathspec_env: str | None) -> tuple[bool, list[str]]:
    """Return (should_refuse, offending_files).

    Caller MUST have already confirmed the automation marker
    (`GAMMA_AUTO_COMMIT=1`) is set -- this function does not re-check that
    and must never be invoked for an interactive-commit context.
    """
    staged_files = [f for f in staged_files if f.strip()]
    pathspecs = [p for p in (pathspec_env or "").split(":") if p.strip()]
    if not pathspecs:
        # Automation fired without declaring any scope at all. If nothing
        # is staged there's nothing to refuse; if anything IS staged, that
        # is the exact violation this path exists to catch -- declare your
        # scope or be refused.
        return (bool(staged_files), list(staged_files))
    offending = [f for f in staged_files if not _pathspec_allows(f, pathspecs)]
    return (bool(offending), offending)


def main(argv: list[str] | None = None) -> int:
    staged = [ln.rstrip("\n") for ln in sys.stdin if ln.strip()]
    refuse, offending = decide(staged, os.environ.get("GAMMA_COMMIT_PATHSPEC"))
    if refuse:
        for f in offending:
            print(f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
