"""Guard for the 2026-07-18 conductor cross-fire lock (self-audit gap closure).

Same-day evidence (automation/overnight/STATUS.md): conductor and conductor-weekend
fired ~16:00-16:20 ET and ~16:02-16:20 ET the SAME afternoon, independently derived
and built the byte-identical fix for F7-EXIT-SELL-ALL-REFIRE (real wasted duplicate
work), and a SEPARATE overlapping pair collided on a `git stash` mid-edit the same
day (SINGLE-STRATEGY-REGISTRY-DESIGN fire had to recover via
`git checkout stash@{0} -- <files>`). This is the exact "cross-fire coordination
(a lock/mutex) to prevent concurrent conductor fires from clobbering" gap Gamma
self-flagged in analysis/self-audit/new-gaps-flagged.md on 2026-07-18.

Enter-ConductorFireLock / Exit-ConductorFireLock in _shared.ps1 give run-conductor.ps1
and run-conductor-weekend.ps1 (the two heavy STAGE 1-5 wrappers that pick from the
SAME queue.md) a shared mutual-exclusion lock file:
  - fresh lock (age < StaleMinutes) held by a live peer -> caller SKIPs, no model spend
  - stale lock (age >= StaleMinutes) -> presumed-dead peer, overwrite and proceed
  - fail-open (rail 2): NEVER blocks J's interactive session, only serializes
    automated conductor fires against each other; a crashed fire's lock just ages out.

Same convention as test_tv_launch_safe_2026_07_06.py (no Pester harness in this repo,
so PS wrapper guards are text-assertion + a real `powershell.exe` subprocess round-trip
against the actual shared function).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"
RUN_CONDUCTOR = SCRIPTS / "run-conductor.ps1"
RUN_CONDUCTOR_WEEKEND = SCRIPTS / "run-conductor-weekend.ps1"
LOCK_FILE = REPO / "automation" / "state" / "conductor-fire.lock"


def test_shared_defines_lock_functions():
    src = SHARED.read_text(encoding="utf-8")
    assert "function Enter-ConductorFireLock" in src
    assert "function Exit-ConductorFireLock" in src
    assert "conductor-fire.lock" in src


def test_run_conductor_acquires_and_releases_the_lock():
    src = RUN_CONDUCTOR.read_text(encoding="utf-8")
    assert "Enter-ConductorFireLock" in src
    assert "Exit-ConductorFireLock" in src
    # Must SKIP (exit 0) without spending, not silently proceed, when the lock
    # is already held -- the whole point is to avoid a duplicate model spend.
    assert re.search(r"if\s*\(-not \$conductorLock\.acquired\)\s*\{", src)
    assert "exit 0" in src
    # Release must live in a finally block so a crashed/early-exited fire still
    # releases promptly (matches the Invoke-TvLaunchSafe / gamma-drive.ps1 pattern).
    assert re.search(r"finally\s*\{[^}]*Exit-ConductorFireLock", src, re.DOTALL)


def test_run_conductor_weekend_acquires_and_releases_the_lock():
    src = RUN_CONDUCTOR_WEEKEND.read_text(encoding="utf-8")
    assert "Enter-ConductorFireLock" in src
    assert "Exit-ConductorFireLock" in src
    assert re.search(r"if\s*\(-not \$conductorLock\.acquired\)\s*\{", src)
    assert "exit 0" in src
    assert re.search(r"finally\s*\{[^}]*Exit-ConductorFireLock", src, re.DOTALL)


def test_both_wrappers_share_the_same_lock_file_helper():
    # Neither wrapper should hand-roll its own Test-Path/Get-Item staleness check --
    # that would silently re-introduce two independent (and driftable) copies of the
    # same logic, the exact class of bug the 2026-07-18 STATUS.md entries document
    # elsewhere (hand-mirrored allowlists drifting from a single source of truth).
    for wrapper in (RUN_CONDUCTOR, RUN_CONDUCTOR_WEEKEND):
        src = wrapper.read_text(encoding="utf-8")
        assert "LastWriteTime" not in src, (
            f"{wrapper.name} has its own inline lock-staleness check -- "
            f"must go through the shared Enter-ConductorFireLock function"
        )


def _run_enter_lock(stale_minutes: int = 20) -> str:
    ps_cmd = (
        f". '{SHARED}'; "
        f"$r = Enter-ConductorFireLock -StaleMinutes {stale_minutes} -LockFile '{LOCK_FILE}'; "
        f"Write-Output \"ACQUIRED=$($r.acquired)\""
    )
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout + out.stderr


def test_fresh_lock_blocks_a_concurrent_acquire():
    """Non-vacuous bite: a FRESH lock file must make Enter-ConductorFireLock report
    acquired=False, and must NOT be overwritten (still present afterward)."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text("held", encoding="utf-8")
    try:
        result = _run_enter_lock(stale_minutes=20)
        assert "ACQUIRED=False" in result, result
        assert LOCK_FILE.exists(), "a fresh lock must not be clobbered by a blocked acquire attempt"
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def test_no_lock_allows_acquire_and_writes_the_file():
    """Non-vacuous bite: with no lock present, Enter-ConductorFireLock must report
    acquired=True and actually create the lock file."""
    LOCK_FILE.unlink(missing_ok=True)
    try:
        result = _run_enter_lock(stale_minutes=20)
        assert "ACQUIRED=True" in result, result
        assert LOCK_FILE.exists(), "a successful acquire must write the lock file"
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def test_stale_lock_is_overwritten_not_honored():
    """Non-vacuous bite: fail-open is the whole point -- a lock older than
    StaleMinutes must be treated as a dead/crashed instance and overwritten,
    never permanently wedging future fires."""
    import os
    import time

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text("held", encoding="utf-8")
    # Back-date the file's mtime by 30 minutes so it reads as stale under a
    # 20-minute threshold.
    old_ts = time.time() - (30 * 60)
    os.utime(LOCK_FILE, (old_ts, old_ts))
    try:
        result = _run_enter_lock(stale_minutes=20)
        assert "ACQUIRED=True" in result, result
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def test_exit_lock_removes_the_file():
    ps_cmd = (
        f". '{SHARED}'; "
        f"'held' | Out-File -FilePath '{LOCK_FILE}' -Encoding utf8 -Force; "
        f"Exit-ConductorFireLock -LockFile '{LOCK_FILE}'; "
        f"Write-Output \"EXISTS=$(Test-Path '{LOCK_FILE}')\""
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )
        result = out.stdout + out.stderr
        assert "EXISTS=False" in result, result
    finally:
        LOCK_FILE.unlink(missing_ok=True)
