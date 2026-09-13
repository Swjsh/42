"""Test-suite bootstrap.

Puts this directory on `sys.path` so test modules can import shared fixture helpers
(`_broker_request_stub`) at module import time -- before each file's own
`sys.path.insert(...)` block runs, which is too late for a top-level `from ... import`.

Deliberately minimal: no fixtures, no autouse hooks, no collection tweaks. Every test file
here loads production modules by explicit path and manages its own sys.path for those; this
file changes none of that, so adding it cannot alter which module version any test imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# ---------------------------------------------------------------------------------------
# quiet_mode LIVE-LOG ISOLATION (added 2026-09-03 00:50 ET, structural fix for a live incident)
#
# quiet_mode._log() appends to automation/state/quiet-mode.log on disk. Five test files
# imported quiet_mode without redirecting LOG_FILE, so every full-suite run planted fixture
# lines ("QUIET HELD past the clock ... r5apex_dx12.exe", weekday "PRESENCE -> research
# band" lines the real code cannot produce, "scheduler unreachable") into the PRODUCTION
# log. scheduled_task_staleness.parse_quiet_holds then read a phantom OPEN hold, closed it
# at `now`, and quiet_mode's catch-up sweep restarted the same five tasks every 5 minutes
# for an hour (2026-09-02 23:47 -> 2026-09-03 00:43 ET; McpDailyAudit 12x/hour). Fixing it
# per file is how it recurred; this autouse fixture redirects LOG_FILE (and the hold/status
# files beside it) for EVERY test as soon as quiet_mode is imported, regardless of file.
# ---------------------------------------------------------------------------------------
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _quiet_mode_never_touches_live_state(monkeypatch, tmp_path):
    qm = sys.modules.get("quiet_mode")
    if qm is None:
        yield
        return
    for attr in ("LOG_FILE", "HOLD_FILE", "STATUS_FILE", "RESTORE_FILE"):
        if hasattr(qm, attr):
            monkeypatch.setattr(qm, attr, tmp_path / f"quiet-mode-{attr.lower()}")
    yield


# ---------------------------------------------------------------------------------------
# crypto-twin-loop.pid LIVE-STATE GUARD (added 2026-09-13, structural fix for a live incident)
#
# automation/state/crypto-twin-loop.pid names the pid of the REAL resident
# crypto_twin_health.py --loop process (relaunched by Gamma_SupervisorKeepalive). At least
# one test called the real crypto_twin_keepalive.launch_loop() with a monkeypatched
# ctk.PID_FILE, but launch_loop()'s own _write_pid_file(proc.pid) call used a default
# argument (`pid_file: Path = PID_FILE`) BOUND ONCE at module-import time, so the
# monkeypatch never redirected the write -- it landed on the real file, overwriting the
# live loop's actual pid (2024) with the test's fake one (9999) at 10:33:41 ET on
# 2026-09-13 (see test_crypto_twin_keepalive_2026_09_05.py::
# test_launch_loop_command_includes_live_and_loop_flags's docstring for the full story and
# crypto_twin_keepalive.py's _write_pid_file/_read_pid_file for the source-level fix -- both
# now resolve PID_FILE fresh inside the function body instead of via a bound default).
#
# This session-scoped guard is the backstop for the NEXT test that makes the same mistake
# with a DIFFERENT bound-default or a forgotten monkeypatch: it snapshots the real pid
# file's (mtime_ns, sha256) once at session start and asserts it is byte-and-timestamp
# identical at session end, regardless of which test caused the drift.
import hashlib as _hashlib  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CRYPTO_TWIN_PID_FILE = _REPO_ROOT / "automation" / "state" / "crypto-twin-loop.pid"


def _crypto_twin_pid_file_fingerprint():
    p = _CRYPTO_TWIN_PID_FILE
    if not p.exists():
        return None
    try:
        return (p.stat().st_mtime_ns, _hashlib.sha256(p.read_bytes()).hexdigest())
    except OSError:
        return "unreadable"


@_pytest.fixture(scope="session", autouse=True)
def _crypto_twin_pid_file_untouched_by_tests():
    before = _crypto_twin_pid_file_fingerprint()
    yield
    after = _crypto_twin_pid_file_fingerprint()
    assert after == before, (
        f"automation/state/crypto-twin-loop.pid changed during this test session "
        f"(before={before!r}, after={after!r}) -- some test wrote to the LIVE crypto-twin "
        f"pid file instead of fully isolating it via monkeypatch. This is the exact class of "
        f"bug that clobbered the real running loop's pid with a test's fake one on "
        f"2026-09-13 -- see this file's own comment above and "
        f"crypto_twin_keepalive.py::_write_pid_file's docstring."
    )
