"""single_instance.py -- OS-level single-instance guard (Windows msvcrt.locking), reusable
across long-lived --loop launchers.

WHY THIS EXISTS (queue.md TWIN-LOOP-SINGLETON-GUARD, filed 2026-09-15). crypto_twin_health.py
--loop has NO single-instance guard (grep for lock/pidfile/mutex found nothing before this
file). Confirmed via automation/state/logs/proc-trace-2026-09-09.jsonl: 22 distinct
`crypto_twin_health.py --live --loop --duration-sec 86400` pids launched between 09:46:46 and
23:01:45 ET on 2026-09-09, median gap ~300s, every one spawned by supervisor_keepalive.py's
`_spawn_crypto_twin()` -> `crypto_twin_keepalive.launch_loop()` (parent_cmdline in the trace
is always supervisor_keepalive.py). Root cause: at that time the process-table probe
(`_check_crypto_twin`) used the pre-fix wmic-based reader, which Windows 11 24H2+ broke (see
_proc_table.py's own docstring / commit 584ebc12's CIM migration) -- every 5-min supervisor
fire read an EMPTY table, concluded no loop was alive, and relaunched a duplicate. Those
duplicates interleaved appends into automation/state/crypto-twin/decisions.jsonl: 191
truncated rows + 1 NUL block between 12:03 and 22:58 ET that day, with neighbouring rows
~0.5s apart instead of the expected once-per-60s cadence.

The wmic->CIM fix (584ebc12) makes today's probe accurate again, but crypto_twin_health.py
itself still has no independent guarantee -- any FUTURE probe failure (a different bug, a
timeout, a CIM hiccup) brings duplicate writers straight back. This module is that
independent, process-external guarantee: it does not trust any launcher's liveness check at
all.

DESIGN: `acquire_lock(lock_path)` opens/creates `lock_path` and takes a non-blocking
exclusive `msvcrt.locking()` byte-range lock on it, held for as long as the returned
`LockHandle` (or the underlying file object) stays open. Windows releases the lock
automatically when the holding process dies for ANY reason (clean exit, kill, crash) --
there is therefore no stale-lock TTL/takeover logic to write or get wrong, unlike a
file-existence-based lock (matches the discipline documented in
setup/scripts/heartbeat_core.py's `_acquire_claim` and backtest/futures/futures_claim.py).
A losing caller gets `None` back and MUST NOT do any further work (no tick, no ledger write).

`is_legacy_process_running(markers, own_pid)` is a SEPARATE, one-time rollout-safety check:
a process already running from BEFORE this guard shipped (e.g. pid 17552, started
2026-09-14 21:51:50 local, the live twin loop at the time this module was authored) holds no
lock at all, so without this check a new instance would take the lock and run ALONGSIDE it
rather than refusing to start. It scans the live process table (via `_proc_table`, the same
wmic-removal-proof CIM reader every other keepalive in this repo now uses) for another
process whose full command line contains every string in `markers`, excluding `own_pid`.
Fail-open on a process-table read error (never blocks a legitimate start because of a
transient probe hiccup -- this codebase's NEVER-BLIND discipline: a guard that fails closed
on its own read error is worse than the race it prevents).

CONTRACT:
    acquire_lock(lock_path: Path) -> LockHandle | None
    is_legacy_process_running(markers: Sequence[str], own_pid: int,
                               process_table_text_fn=_proc_table.process_table_text) -> bool

Windows-only (`msvcrt`), matching the rest of this codebase's lock primitives.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import _proc_table  # noqa: E402


class LockHandle:
    """Wraps the open, locked file object. Keep a reference alive for the process's entire
    lifetime -- letting it (or the process) be garbage-collected/exit releases the OS lock.
    `release()` is explicit and idempotent, provided for tests and any caller that wants a
    clean early release rather than waiting for process exit."""

    def __init__(self, fileobj):
        self._f = fileobj
        self._released = False

    def release(self) -> None:
        if self._released or self._f is None:
            return
        try:
            import msvcrt  # noqa: PLC0415 -- Windows-only primitive, imported where used
            self._f.seek(0)
            msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:  # noqa: BLE001 -- best-effort; process exit releases regardless
            pass
        finally:
            try:
                self._f.close()
            except Exception:  # noqa: BLE001
                pass
            self._released = True


def acquire_lock(lock_path: Path) -> Optional[LockHandle]:
    """Non-blocking attempt to take an exclusive OS-level lock on `lock_path` (file created
    if missing). Returns a LockHandle to keep referenced for the process lifetime, or None
    if another live process already holds it (or the file could not be opened/locked for any
    other OSError reason -- fail CLOSED here, on purpose: this is the one guard whose entire
    job is to refuse a second writer, so an ambiguous lock error must never be treated as
    'go ahead')."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = open(lock_path, "a+b")
    except OSError:
        return None
    try:
        import msvcrt  # noqa: PLC0415 -- Windows-only primitive, imported where used
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        try:
            f.close()
        except Exception:  # noqa: BLE001
            pass
        return None
    return LockHandle(f)


def is_legacy_process_running(
    markers: Sequence[str],
    own_pid: int,
    process_table_text_fn=_proc_table.process_table_text,
) -> bool:
    """True iff a LIVE process (excluding own_pid) has ALL `markers` as substrings of its
    full command line. Rollout-safety check only -- see module docstring. Fail-open (returns
    False) on a process-table read error: a transient probe hiccup must never block a
    legitimate start."""
    try:
        text = process_table_text_fn()
    except Exception:  # noqa: BLE001
        return False
    try:
        table = _proc_table.parse_process_table(text)
    except Exception:  # noqa: BLE001
        return False
    for pid, cmdline in table.items():
        if pid == own_pid:
            continue
        if all(m in cmdline for m in markers):
            return True
    return False
