"""Graduated guard (2026-07-14 stash-drop data-loss incident, L-pending).

The live decision ledgers are continuously written, tracked-but-rarely-committed files.
On 2026-07-14 a tree-wide `git stash` + `git stash drop` in the shared checkout reverted
them to a 3-week-old commit, destroying 2026-06-27..07-13 history (recovered via
`git fsck --unreachable` -> branch recovery/stash-data-loss-2026-07-14).

Fix: the ledgers are gitignored + untracked so no routine git operation can ever touch
them again. This guard REDs if any of them becomes trackable again.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

LEDGERS = [
    "automation/state/core-decisions.jsonl",
    "automation/state/fleet/risky-1/decisions.jsonl",
    "automation/state/fleet/risky-3/decisions.jsonl",
    "automation/state/fleet/safe-3/decisions.jsonl",
]


def test_decision_ledgers_are_gitignored():
    for path in LEDGERS:
        r = subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"{path} is NOT gitignored -- a tree-wide git stash/reset in the shared "
            f"checkout can silently destroy its uncommitted live history again "
            f"(2026-07-14 incident). Re-add it to .gitignore and `git rm --cached` it."
        )


def test_decision_ledgers_are_untracked():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", *LEDGERS],
        capture_output=True,
        text=True,
    )
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"Still tracked in the index (gitignore alone does not untrack): {tracked}. "
        f"Run `git rm --cached <path>` for each."
    )
