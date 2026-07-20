"""Graduated guard (2026-07-14 stash-drop data-loss incident + 2026-07-20 recurrence).

The live decision ledgers are continuously written, tracked-but-rarely-committed files.
On 2026-07-14 a tree-wide `git stash` + `git stash drop` in the shared checkout reverted
them to a 3-week-old commit, destroying 2026-06-27..07-13 history (recovered via
`git fsck --unreachable` -> branch recovery/stash-data-loss-2026-07-14).

Fix: the ledgers are gitignored + untracked so no routine git operation can ever touch
them again. This guard REDs if any of them becomes trackable again.

2026-07-20 SAME MECHANISM RECURRED on a different file class: circuit-breaker*.json +
today-bias.json (overwritten-in-place JSON snapshots, not append logs) were also
tracked-but-rarely-committed and got silently reverted BACKWARD to 2026-07-14 content
twice in one day by `git stash`/`checkout` operations colliding with live writers. Same
fix applied (see STATE_SNAPSHOTS below) -- a re-violated lesson graduated to code per
OP-25. See automation/overnight/queue.md STATE-FILE-REVERSION-2026-07-20.
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

# 2026-07-20 STATE-FILE-REVERSION incident: same mechanism, different files. These are
# overwritten-in-place JSON snapshots (not append logs) that were last committed 2026-07-14
# but written continuously since -- a `git stash`/`checkout`/`reset` in the shared checkout
# silently reverts kill-switch state + morning bias BACKWARD to that stale snapshot.
# Reproduced live twice the same day (04:27/05:58 ET premarket, 18:40 ET mid-session).
STATE_SNAPSHOTS = [
    "automation/state/circuit-breaker.json",
    "automation/state/aggressive/circuit-breaker.json",
    "automation/state/fleet/risky-1/circuit-breaker.json",
    "automation/state/fleet/risky-3/circuit-breaker.json",
    "automation/state/fleet/safe-1/circuit-breaker.json",
    "automation/state/fleet/safe-3/circuit-breaker.json",
    "automation/state/today-bias.json",
    "automation/state/futures/today-bias.json",
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


def test_state_snapshots_are_gitignored():
    for path in STATE_SNAPSHOTS:
        r = subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"{path} is NOT gitignored -- a tree-wide git stash/checkout/reset in the "
            f"shared checkout can silently revert live kill-switch/bias state backward "
            f"to a stale committed snapshot (2026-07-20 STATE-FILE-REVERSION incident, "
            f"reproduced twice same day). Re-add it to .gitignore and `git rm --cached` it."
        )


def test_state_snapshots_are_untracked():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", *STATE_SNAPSHOTS],
        capture_output=True,
        text=True,
    )
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"Still tracked in the index (gitignore alone does not untrack): {tracked}. "
        f"Run `git rm --cached <path>` for each."
    )
