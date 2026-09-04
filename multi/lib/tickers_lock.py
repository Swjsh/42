"""multi/lib/tickers_lock.py -- Windows-safe file lock guarding the TICKERS LANE against a
race between `multi/execute.py`'s 2-minute cadence and `multi/tickers_flatten.py`'s 14:52 ET
EOD safety net (FIX 3, 2026-09-04 adversarial review). Both processes read-modify-write the
same per-arm state files (`exit-state.json`, the day file, the journal); if Task Scheduler
ever overlaps them -- a slow execute.py tick still running at 14:52, or the reverse -- one
process's write can race the other's read.

No fcntl (Windows has none). Uses `os.open(..., O_CREAT|O_EXCL|O_WRONLY)`, the same atomic
"create exclusively or fail" primitive `multi/lib/journal.py::_acquire_lock` already uses for
its own lock-based takeover (commit da8fb973, 2026-08-19) -- this module is the same idea
factored out for reuse outside the journal's own append path.

Deliberately dependency-light: only stdlib + the repo's own `et_clock` (never `datetime.now()`
directly -- this box runs Mountain time; see CLAUDE.md "TIME = et_clock, NEVER Bash TZ").

Usage:
    handle = tickers_lock.acquire(lock_path)
    if handle is None:
        ...another process holds it (log and move on -- never block here)...
    try:
        ...critical section...
    finally:
        tickers_lock.release(handle)

`tickers_flatten.py` (the safety net) must never be blocked indefinitely by a stuck lock --
its own caller polls `acquire()` on a timeout and, if still held, proceeds WITHOUT the lock
anyway (logged LOCK_FORCED) rather than skip the flatten. This module only provides the
primitive; the wait-then-force policy lives in the caller.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = REPO_ROOT / "setup" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402 -- the ONE clock on this rig; diagnostic timestamp only


@dataclass(frozen=True)
class LockHandle:
    """Opaque proof of ownership returned by `acquire()`. Callers should treat this as a
    token -- its only legal use is passing it back to `release()`."""

    path: Path


def acquire(path: Path, *, stale_after_sec: float = 240.0) -> Optional[LockHandle]:
    """Try to exclusively create the lock file at `path`. Returns a `LockHandle` on success,
    `None` if a LIVE holder already has it (never raises, never blocks/spins -- one attempt
    plus, at most, one stale-takeover retry).

    If the file already exists and its mtime is older than `stale_after_sec` (240s default --
    comfortably longer than execute.py's own 90s soft wall-clock budget, so a genuinely still-
    running tick is never mistaken for a crashed one), the stale file is removed and creation
    is retried EXACTLY once. A second collision after that retry (another process won the
    race in between) is reported as held, not force-seized -- this function never loops.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"pid": os.getpid(), "acquired_at_et": et_now().isoformat(timespec="seconds")}).encode("utf-8")
    for attempt in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)
            return LockHandle(path=path)
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0.0  # the file vanished between the failed create and this stat -- treat
                           # as "not provably stale" rather than racing a takeover on a guess
            if attempt == 0 and age > stale_after_sec:
                try:
                    path.unlink()
                except OSError:
                    pass  # another process may have already reclaimed/removed it -- fine,
                          # the loop's second attempt below will report the true current state
                continue
            return None
    return None  # pragma: no cover -- unreachable (the loop always returns inside its body)


def holder_info(path: Path) -> dict:
    """Best-effort {pid, acquired_at_et, age_sec} for whoever currently holds `path`. Never
    raises -- returns `{}` if the file is missing/unreadable/vanishes mid-read (a lock file
    can legitimately disappear between an `acquire()` failure and this diagnostic read; that
    race is not an error, just a slightly stale log line)."""
    info: dict = {}
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    try:
        info["age_sec"] = round(time.time() - path.stat().st_mtime, 1)
    except OSError:
        pass
    return info


def release(handle: Optional[LockHandle]) -> None:
    """Idempotent unlink. `handle=None` (acquire() returned None -- never held it) and an
    already-missing file (someone else's stale-takeover beat us to removing it) are both
    silent no-ops -- always safe to call from a `finally` unconditionally."""
    if handle is None:
        return
    try:
        handle.path.unlink()
    except OSError:
        pass
