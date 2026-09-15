"""Guard: crypto_twin_health.run_loop()'s single-instance guard -- TWIN-LOOP-SINGLETON-GUARD
(2026-09-15). Proves a second instance exits cleanly WITHOUT ticking (no decisions.jsonl
write, no health-file write) whenever either the legacy-process check or the OS-level lock
says another instance is already running. See single_instance.py's own module docstring for
the 2026-09-09 22-duplicate-loop / decisions.jsonl-corruption incident this closes.

Zero real subprocess calls, zero real file locking -- both checks are injected fakes, same
injectable-everything discipline as test_crypto_twin_health_loop_2026_09_05.py.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import crypto_twin_health as cth  # noqa: E402
import single_instance  # noqa: E402


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _ok_result(action: str = "HOLD") -> dict:
    return {"row": {"action": action}, "health": {}, "soak_row": None, "error": None}


def test_second_instance_exits_zero_without_ticking_when_legacy_process_present(tmp_path):
    """The rollout-safety check: a pre-guard instance (no lock held) is already running ->
    a new instance must refuse to tick anything."""
    clock = _FakeClock()
    calls: list[int] = []
    logged: list[str] = []
    decisions_path = tmp_path / "decisions.jsonl"

    rc = cth.run_loop(
        live=True, interval_sec=60, duration_sec=0,
        stop_file=tmp_path / "crypto-twin.stop", health_path=tmp_path / "twin-health.json",
        tick_fn=lambda **kw: (calls.append(1), _ok_result())[1],
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=logged.append,
        lock_path=tmp_path / "twin-loop.lock",
        legacy_check_fn=lambda markers, own_pid: True,
        acquire_lock_fn=lambda path: pytest.fail("must not attempt to acquire the lock "
                                                   "when a legacy process is already found"),
        pid_fn=lambda: 424242,
    )
    assert rc == 0
    assert calls == []  # never ticked
    assert not decisions_path.exists()  # never touched any ledger
    assert not (tmp_path / "twin-health.json").exists()
    assert any("already running" in line or "legacy" in line.lower() for line in logged)


def test_second_instance_exits_zero_without_ticking_when_lock_refused(tmp_path):
    """No legacy process, but the OS-level lock is already held by a live --loop process ->
    refuse to tick anything."""
    clock = _FakeClock()
    calls: list[int] = []
    logged: list[str] = []

    rc = cth.run_loop(
        live=True, interval_sec=60, duration_sec=0,
        stop_file=tmp_path / "crypto-twin.stop", health_path=tmp_path / "twin-health.json",
        tick_fn=lambda **kw: (calls.append(1), _ok_result())[1],
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=logged.append,
        lock_path=tmp_path / "twin-loop.lock",
        legacy_check_fn=lambda markers, own_pid: False,
        acquire_lock_fn=lambda path: None,  # refused: another instance holds it
        pid_fn=lambda: 424242,
    )
    assert rc == 0
    assert calls == []
    assert not (tmp_path / "twin-health.json").exists()
    assert any("lock" in line.lower() for line in logged)


def test_first_instance_ticks_normally_when_both_checks_pass(tmp_path):
    """Sanity: the guard must not block a legitimate solo instance -- ticks proceed exactly
    as before once legacy_check_fn=False and acquire_lock_fn succeeds."""
    clock = _FakeClock()
    stop_file = tmp_path / "crypto-twin.stop"
    calls: list[int] = []

    def tick_fn(*, live, health_path):  # noqa: ANN001
        calls.append(1)
        if len(calls) == 3:
            stop_file.write_text("stop")
        return _ok_result()

    class _FakeLock:
        released = False

        def release(self):
            self.released = True

    fake_lock = _FakeLock()

    rc = cth.run_loop(
        live=False, interval_sec=1, duration_sec=0, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json", tick_fn=tick_fn,
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=lambda m: None,
        lock_path=tmp_path / "twin-loop.lock",
        legacy_check_fn=lambda markers, own_pid: False,
        acquire_lock_fn=lambda path: fake_lock,
        pid_fn=lambda: 1234,
    )
    assert rc == 0
    assert len(calls) == 3


def test_run_loop_defaults_wire_to_the_real_single_instance_module():
    """Structural check (mirrors test_loop_uses_the_real_run_tick_with_health_by_default):
    a real --loop invocation with no overrides must go through the real, production
    single_instance guard -- never a silently-no-op stub."""
    sig = inspect.signature(cth.run_loop)
    assert sig.parameters["acquire_lock_fn"].default is single_instance.acquire_lock
    assert sig.parameters["legacy_check_fn"].default is single_instance.is_legacy_process_running


def test_run_loop_default_lock_path_is_under_crypto_twin_state_dir():
    sig = inspect.signature(cth.run_loop)
    default_lock_path = sig.parameters["lock_path"].default
    assert default_lock_path == cth.LOCK_PATH
    parts = default_lock_path.parts
    assert "crypto-twin" in parts
    assert default_lock_path.name == "twin-loop.lock"
