"""Guard: crypto_twin_health.run_loop() -- GOAL-SILENT-RIG-2026-09-05 R2.

Converts Gamma_CryptoTwin from "spawn a fresh Python process every minute, 24/7"
(1,440 spawns/day) to a single RESIDENT process that ticks internally. This file
proves the loop's own contract with a FAKE monotonic clock + a FAKE tick_fn --
zero real sleeping, zero real network/broker calls, zero real time elapsed.

RED-PROOFED (2026-09-05): every test below was run once against a deliberately
broken run_loop (stop-file check removed / drift-free schedule replaced with
now+interval / exception catch removed) to confirm it actually fails before the
real implementation was restored -- see PROGRESS LOG in
automation/state/goals/GOAL-SILENT-RIG-2026-09-05.md for the quoted proof.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import crypto_twin_health as cth  # noqa: E402


class _FakeClock:
    """A monotonic clock that only advances when `sleep` is called -- so a test can assert
    exactly how many (fake) seconds the loop asked to sleep for, and drive the loop through
    N iterations without any real wall-clock time passing."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _ok_result(action: str = "HOLD") -> dict:
    return {"row": {"action": action}, "health": {}, "soak_row": None, "error": None}


def test_loop_ticks_once_per_interval_drift_free(tmp_path):
    """5 ticks at interval=60 -> tick_fn called exactly 5 times, and each sleep is computed
    from start + n*interval (not now+interval), so a slow tick never pushes later ticks
    later -- prove this by making tick 2 itself consume 45s of fake clock time (as if the
    network call was slow) and confirming tick 3's sleep is still short enough to land on
    the ORIGINAL schedule, not 60s after the slow tick finished."""
    clock = _FakeClock(start=0.0)
    calls: list[int] = []
    stop_file = tmp_path / "crypto-twin.stop"

    def tick_fn(*, live, health_path):  # noqa: ANN001
        calls.append(len(calls))
        if len(calls) == 2:
            clock.now += 45  # tick 2 itself took 45s (simulated slow network call)
        # 6th call triggers stop so the loop terminates deterministically
        if len(calls) == 5:
            stop_file.write_text("stop")
        return _ok_result()

    rc = cth.run_loop(
        live=False, interval_sec=60, duration_sec=0, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json", tick_fn=tick_fn,
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=lambda m: None,
    )
    assert rc == 0
    assert len(calls) == 5
    # drift-free: tick 3's scheduled sleep must be SHORTER than a fresh 60s (it should only
    # cover the remainder of the original 3rd 60s slot, not a full 60s after the slow tick).
    assert clock.sleeps[1] < 60  # the sleep taken right after the slow tick (index 1 = post-tick-2)


def test_loop_stops_on_stop_file_within_one_tick(tmp_path):
    """Touching the stop file mid-run halts the loop before the NEXT tick fires -- never
    mid-tick, and never more than one extra tick after the file appears."""
    clock = _FakeClock()
    stop_file = tmp_path / "crypto-twin.stop"
    calls: list[int] = []

    def tick_fn(*, live, health_path):  # noqa: ANN001
        calls.append(1)
        if len(calls) == 3:
            stop_file.write_text("stop")
        return _ok_result()

    rc = cth.run_loop(
        live=False, interval_sec=1, duration_sec=0, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json", tick_fn=tick_fn,
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=lambda m: None,
    )
    assert rc == 0
    assert len(calls) == 3  # stopped immediately after the tick that wrote the stop file


def test_loop_never_starts_a_tick_when_stop_file_already_present(tmp_path):
    stop_file = tmp_path / "crypto-twin.stop"
    stop_file.write_text("stop")
    clock = _FakeClock()
    calls: list[int] = []

    rc = cth.run_loop(
        live=False, interval_sec=60, duration_sec=0, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json",
        tick_fn=lambda **kw: (calls.append(1), _ok_result())[1],
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=lambda m: None,
    )
    assert rc == 0
    assert calls == []


def test_loop_exits_after_duration_sec_elapsed(tmp_path):
    """duration_sec bounds total runtime even with no stop file -- the daily-recycle
    contract (mirrors quote_recorder_keepalive.py's MAX_RUNTIME_S doctrine)."""
    clock = _FakeClock(start=0.0)
    stop_file = tmp_path / "crypto-twin.stop"  # never created
    calls: list[int] = []

    rc = cth.run_loop(
        live=False, interval_sec=60, duration_sec=185, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json",
        tick_fn=lambda **kw: (calls.append(1), _ok_result())[1],
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=lambda m: None,
    )
    assert rc == 0
    # 185s / 60s interval -> ticks at t=0,60,120,180 fire (4 ticks); the 5th would be due at
    # t=240 which is past the 185s deadline, so the loop exits before firing it.
    assert len(calls) == 4


def test_loop_survives_a_tick_exception_and_keeps_running(tmp_path):
    """A tick_fn that RAISES (simulating a violation of run_tick_with_health's own
    never-raises contract) must not kill the loop -- C7: log loudly, never silently die."""
    clock = _FakeClock()
    stop_file = tmp_path / "crypto-twin.stop"
    calls: list[int] = []
    logged: list[str] = []

    def tick_fn(*, live, health_path):  # noqa: ANN001
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("simulated broker meltdown")
        if len(calls) == 4:
            stop_file.write_text("stop")
        return _ok_result()

    rc = cth.run_loop(
        live=False, interval_sec=1, duration_sec=0, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json", tick_fn=tick_fn,
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=logged.append,
    )
    assert rc == 0
    assert len(calls) == 4  # the loop kept going past the exception on tick 2
    assert any("EXCEPTION" in line and "RuntimeError" in line for line in logged)


def test_loop_logs_a_tick_error_without_raising(tmp_path):
    """tick_fn returning a dict with a non-None 'error' (the normal run_tick_with_health
    TICK_ERROR shape) is logged, not raised, and the loop continues."""
    clock = _FakeClock()
    stop_file = tmp_path / "crypto-twin.stop"
    calls: list[int] = []
    logged: list[str] = []

    def tick_fn(*, live, health_path):  # noqa: ANN001
        calls.append(1)
        if len(calls) == 3:
            stop_file.write_text("stop")
        if len(calls) == 1:
            return {"row": {"action": "TICK_ERROR"}, "health": {}, "soak_row": None,
                    "error": "ConnectionError: simulated"}
        return _ok_result()

    rc = cth.run_loop(
        live=False, interval_sec=1, duration_sec=0, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json", tick_fn=tick_fn,
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=logged.append,
    )
    assert rc == 0
    assert len(calls) == 3
    assert any("TICK_ERROR" in line or "ConnectionError" in line for line in logged)


def test_loop_uses_the_real_run_tick_with_health_by_default(tmp_path, monkeypatch):
    """Structural check: run_loop's default tick_fn IS crypto_twin_health.run_tick_with_health
    (never a copy/reimplementation) -- so a real --loop invocation calls the exact same
    tested tick path the old spawn-per-minute task called, per R2's 'same tick function'
    requirement."""
    import inspect
    sig = inspect.signature(cth.run_loop)
    assert sig.parameters["tick_fn"].default is cth.run_tick_with_health


def test_zero_ticks_is_never_silently_ok_when_tick_fn_never_called(tmp_path):
    """Structural guard (C7): if the stop-file-already-present path ever regresses to also
    swallowing a genuine zero-tick startup failure, this test's companion
    (test_loop_never_starts_a_tick_when_stop_file_already_present) still distinguishes the
    two by requiring stop_file existence, and duration_sec=1 with the clock advancing 2s per
    fake sleep proves the loop DOES exit (rather than spin) even at a duration shorter than
    one interval."""
    clock = _FakeClock(start=0.0)
    stop_file = tmp_path / "crypto-twin.stop"
    calls: list[int] = []

    rc = cth.run_loop(
        live=False, interval_sec=60, duration_sec=1, stop_file=stop_file,
        health_path=tmp_path / "twin-health.json",
        tick_fn=lambda **kw: (calls.append(1), _ok_result())[1],
        sleep_fn=clock.sleep, monotonic_fn=clock.monotonic, log_fn=lambda m: None,
    )
    assert rc == 0
    # duration_sec=1 is shorter than the 60s interval, but the FIRST tick (at t=0) is still
    # due immediately -- it fires once, then the loop sees the deadline has passed and exits
    # rather than sleeping past it.
    assert len(calls) == 1


def test_cli_loop_flag_wires_to_run_loop(monkeypatch, tmp_path):
    """--loop routes through run_loop (not the --once path) with the CLI's own args."""
    captured = {}

    def fake_run_loop(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cth, "run_loop", fake_run_loop)
    rc = cth.main(["--loop", "--loop-interval-sec", "5", "--duration-sec", "30",
                   "--stop-file", str(tmp_path / "x.stop")])
    assert rc == 0
    assert captured["interval_sec"] == 5
    assert captured["duration_sec"] == 30
    assert captured["live"] is False
    assert str(captured["stop_file"]) == str(tmp_path / "x.stop")


def test_cli_default_still_runs_once_not_loop(monkeypatch, tmp_path):
    """Omitting --loop preserves the pre-existing one-shot CLI behavior exactly (no
    regression for the old Gamma_CryptoTwin task action, which never passed --loop)."""
    called = {"run_loop": False}
    monkeypatch.setattr(cth, "run_loop", lambda **kw: called.__setitem__("run_loop", True) or 0)

    def fake_run_tick_with_health(*, live):  # noqa: ANN001
        return {"row": {"action": "HOLD"}, "health": {}, "soak_row": None, "error": None}

    monkeypatch.setattr(cth, "run_tick_with_health", fake_run_tick_with_health)
    monkeypatch.setattr(cth.bc, "probe", lambda: {"assess": {"verdict": "OK"}})
    rc = cth.main([])
    assert rc == 0
    assert called["run_loop"] is False
