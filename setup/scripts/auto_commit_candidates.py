"""Periodic auto-committer for strategy/candidates/ (L242 re-violation guard).

SCAR: L242 (2026-07-22) -- 1,176 untracked strategy/candidates/ files sat
uncommitted for weeks with no disk-loss recovery path. self_check.py's
CANDIDATES-UNTRACKED check (threshold 20) was added as a DETECTOR, but
detection-only re-violated within 24h: a 2026-07-23 conductor fire had to
manually clear 41 more untracked files (chef-nemo/kitchen/prospector output)
that had piled up since the prior day's backfill. Per OP-25, a re-violated
lesson graduates from prose/manual-cleanup to an enforced guard -- this is
that guard: a small, low-effort, fail-open PREVENTER that keeps the
untracked count below self_check's DEGRADED threshold automatically,
instead of relying on a human/conductor fire noticing it.

Design:
  - Scoped ONLY to strategy/candidates/ (pathspec) -- never touches any
    other path, never `git add -A`.
  - Threshold LOWER than self_check.py's CANDIDATES_CANDIDATES_UNTRACKED_THRESHOLD
    (this fires at >=10; self_check flags DEGRADED at >20) so the preventer
    acts before the detector would ever need to complain.
  - Fail-open (OP-25/C7): any git error is logged and the script exits 0.
    Never raises, never blocks, never touches another process's stage.
  - Idempotent / safe to run frequently: if there is nothing to commit, it
    is a silent no-op (logged at DEBUG level only).
  - No push -- local commit only. Push discipline (never during RTH) is
    unaffected since this never pushes.

Usage: python setup/scripts/auto_commit_candidates.py
Exit code: always 0 (fail-open).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANDIDATES_PATH = "strategy/candidates"
COMMIT_THRESHOLD = 10  # lower than self_check.py's DEGRADED threshold (20) -- preventive
LOG_PATH = REPO / "automation" / "state" / "auto-commit-candidates-log.jsonl"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _log(event: dict) -> None:
    event["ts_utc"] = datetime.now(timezone.utc).isoformat()
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            import json

            f.write(json.dumps(event) + "\n")
    except Exception:
        pass  # fail-open: logging itself must never crash the script


def main() -> int:
    try:
        status = _run(["git", "status", "--short", "--", CANDIDATES_PATH])
        if status.returncode != 0:
            _log({"event": "SKIP", "reason": "git_status_failed", "stderr": status.stderr[:500]})
            return 0

        lines = [ln for ln in status.stdout.splitlines() if ln.strip()]
        n = len(lines)

        if n < COMMIT_THRESHOLD:
            _log({"event": "QUIET", "untracked_or_modified": n, "threshold": COMMIT_THRESHOLD})
            return 0

        add = _run(["git", "add", "--", CANDIDATES_PATH])
        if add.returncode != 0:
            _log({"event": "SKIP", "reason": "git_add_failed", "stderr": add.stderr[:500]})
            return 0

        # Verify something is actually staged before committing (avoid empty-commit noise).
        diff = _run(["git", "diff", "--cached", "--stat", "--", CANDIDATES_PATH])
        if not diff.stdout.strip():
            _log({"event": "SKIP", "reason": "nothing_staged_after_add", "raw_status_lines": n})
            return 0

        msg = (
            f"chore: auto-commit {n} strategy/candidates/ changes "
            f"(auto_commit_candidates.py, L242 prevention guard)"
        )
        commit = _run(["git", "commit", "-m", msg])
        if commit.returncode != 0:
            _log({
                "event": "SKIP",
                "reason": "git_commit_failed",
                "stderr": commit.stderr[:800],
                "stdout": commit.stdout[:800],
            })
            return 0

        _log({"event": "COMMITTED", "n_changes": n, "message": msg})
        return 0
    except Exception as exc:  # noqa: BLE001 -- fail-open is the whole point
        _log({"event": "ERROR", "exception": repr(exc)[:500]})
        return 0


if __name__ == "__main__":
    sys.exit(main())
