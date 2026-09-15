"""Guard: setup/scripts/single_instance.py -- TWIN-LOOP-SINGLETON-GUARD (2026-09-15).

Proves the OS-level lock actually excludes a second acquirer, releases correctly, and that
the legacy-process check's pure matching logic is correct against a fake process table (no
real subprocess call). See single_instance.py's own module docstring for the 2026-09-09
22-duplicate-loop / decisions.jsonl-corruption incident this guard closes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import single_instance as si  # noqa: E402


# --- acquire_lock / LockHandle -----------------------------------------------------------

def test_first_instance_acquires_and_second_is_refused(tmp_path):
    lock_path = tmp_path / "twin-loop.lock"
    first = si.acquire_lock(lock_path)
    assert first is not None

    second = si.acquire_lock(lock_path)
    assert second is None  # refused while first still holds the lock

    first.release()


def test_lock_is_released_on_explicit_release_and_can_be_reacquired(tmp_path):
    lock_path = tmp_path / "twin-loop.lock"
    first = si.acquire_lock(lock_path)
    assert first is not None
    first.release()

    second = si.acquire_lock(lock_path)
    assert second is not None  # released -> free to acquire again
    second.release()


def test_lock_release_is_idempotent(tmp_path):
    lock_path = tmp_path / "twin-loop.lock"
    handle = si.acquire_lock(lock_path)
    assert handle is not None
    handle.release()
    handle.release()  # must not raise on a second release


def test_lock_creates_parent_directory_if_missing(tmp_path):
    lock_path = tmp_path / "nested" / "dir" / "twin-loop.lock"
    handle = si.acquire_lock(lock_path)
    assert handle is not None
    assert lock_path.exists()
    handle.release()


def test_lock_released_by_closing_underlying_file_without_explicit_release(tmp_path):
    """Mirrors the real production contract: Windows releases the lock when the holding
    process's file handle is closed / the process exits -- there is no separate
    stale-lock-recovery path to test here, just that closing the handle frees it for a new
    acquirer, same as an explicit release() would."""
    lock_path = tmp_path / "twin-loop.lock"
    first = si.acquire_lock(lock_path)
    assert first is not None
    first._f.close()  # simulates process teardown without going through release()

    second = si.acquire_lock(lock_path)
    assert second is not None
    second.release()


# --- is_legacy_process_running ------------------------------------------------------------

_MATCHING_LINE = (
    'CommandLine=C:\\...\\pythonw.exe C:\\...\\crypto_twin_health.py --live --loop '
    '--duration-sec 86400\nProcessId=17552\n\n'
)
_NON_MATCHING_LINE = (
    'CommandLine=C:\\...\\pythonw.exe C:\\...\\crypto_twin_keepalive.py\nProcessId=4242\n\n'
)


def test_legacy_process_detected_when_markers_match_a_different_pid():
    detected = si.is_legacy_process_running(
        ("crypto_twin_health.py", "--loop"), own_pid=99999,
        process_table_text_fn=lambda: _MATCHING_LINE,
    )
    assert detected is True


def test_legacy_process_not_detected_when_only_own_pid_matches():
    """The running process IS this same pid (e.g. re-checking after acquiring the lock) --
    must not flag itself as a conflicting legacy instance."""
    detected = si.is_legacy_process_running(
        ("crypto_twin_health.py", "--loop"), own_pid=17552,
        process_table_text_fn=lambda: _MATCHING_LINE,
    )
    assert detected is False


def test_legacy_process_not_detected_when_no_process_matches():
    detected = si.is_legacy_process_running(
        ("crypto_twin_health.py", "--loop"), own_pid=1,
        process_table_text_fn=lambda: _NON_MATCHING_LINE,
    )
    assert detected is False


def test_legacy_process_requires_all_markers_present():
    """A one-shot `crypto_twin_health.py --live` (no --loop) must never be mistaken for the
    resident loop -- mirrors crypto_twin_keepalive.is_loop_process_line's own discipline."""
    one_shot = 'CommandLine=...\\crypto_twin_health.py --live\nProcessId=555\n\n'
    detected = si.is_legacy_process_running(
        ("crypto_twin_health.py", "--loop"), own_pid=1,
        process_table_text_fn=lambda: one_shot,
    )
    assert detected is False


def test_legacy_check_fails_open_on_process_table_read_error():
    """A transient probe hiccup must never block a legitimate start (NEVER-BLIND fail-open
    discipline) -- returns False, not raises."""
    def boom():
        raise RuntimeError("simulated PowerShell timeout")

    detected = si.is_legacy_process_running(
        ("crypto_twin_health.py", "--loop"), own_pid=1, process_table_text_fn=boom,
    )
    assert detected is False
