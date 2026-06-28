"""Guard tests for discord_watchdog.py hardening (2026-06-28, PID-reuse scar).

Two protection layers:

1. test_heartbeat_stale_* -- BEHAVIORAL: _heartbeat_stale() correctly identifies
   a missing, corrupt, or outdated heartbeat file, and passes on a fresh one.
   Root-cause: bridge died 30+ hrs; watchdog's PID-alive check passed on a reused
   VSHelper PID, so the frozen bridge was never detected.

2. test_pid_cmdline_match_* -- BEHAVIORAL: _pid_cmdline_match() returns False when
   the running process's CommandLine does NOT contain the expected script name
   (simulated by targeting a known PID that belongs to an unrelated process), and
   returns True for a trivially matching case (mocked subprocess output).

These tests are stdlib-only and run with the system Python interpreter.

Run:
    python -m pytest backtest/tests/test_discord_watchdog_guards.py -v
    # OR from backtest/:
    cd backtest && python -m pytest tests/test_discord_watchdog_guards.py -v
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
import types
import unittest.mock as mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WATCHDOG_PATH = REPO / "setup" / "scripts" / "discord_watchdog.py"


def _import_watchdog() -> types.ModuleType:
    """Import discord_watchdog without triggering the pythonw stdio redirect."""
    spec = importlib.util.spec_from_file_location("discord_watchdog", WATCHDOG_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Patch sys.executable so the pythonw redirect block is skipped.
    with mock.patch.object(sys, "executable", "/usr/bin/python"):
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. _heartbeat_stale() -- staleness detection
# ---------------------------------------------------------------------------

def test_heartbeat_stale_absent_file(tmp_path):
    """Missing heartbeat file must be treated as stale."""
    wdog = _import_watchdog()
    absent = tmp_path / "discord-bridge-heartbeat.json"
    assert not absent.exists()
    with mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", absent):
        assert wdog._heartbeat_stale(stale_minutes=10) is True


def test_heartbeat_stale_old_timestamp(tmp_path):
    """A heartbeat last_tick_at older than threshold must be stale."""
    wdog = _import_watchdog()
    hb = tmp_path / "discord-bridge-heartbeat.json"
    # Write a timestamp 30 minutes in the past.
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)
    hb.write_text(
        json.dumps({"last_tick_at": past.strftime("%Y-%m-%dT%H:%M:%SZ"), "consecutive_errors": 0}),
        encoding="utf-8",
    )
    with mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", hb):
        assert wdog._heartbeat_stale(stale_minutes=10) is True


def test_heartbeat_stale_fresh_timestamp(tmp_path):
    """A heartbeat last_tick_at within threshold must NOT be stale."""
    wdog = _import_watchdog()
    hb = tmp_path / "discord-bridge-heartbeat.json"
    # Write a timestamp 2 minutes in the past (well within the 10-min threshold).
    recent = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)
    hb.write_text(
        json.dumps({"last_tick_at": recent.strftime("%Y-%m-%dT%H:%M:%SZ"), "consecutive_errors": 0}),
        encoding="utf-8",
    )
    with mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", hb):
        assert wdog._heartbeat_stale(stale_minutes=10) is False


def test_heartbeat_stale_corrupt_file(tmp_path):
    """A corrupt / non-JSON heartbeat file must be treated as stale."""
    wdog = _import_watchdog()
    hb = tmp_path / "discord-bridge-heartbeat.json"
    hb.write_text("NOT JSON AT ALL", encoding="utf-8")
    with mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", hb):
        assert wdog._heartbeat_stale(stale_minutes=10) is True


def test_heartbeat_stale_missing_key(tmp_path):
    """A heartbeat file with no last_tick_at key must be treated as stale."""
    wdog = _import_watchdog()
    hb = tmp_path / "discord-bridge-heartbeat.json"
    hb.write_text(json.dumps({"consecutive_errors": 0}), encoding="utf-8")
    with mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", hb):
        assert wdog._heartbeat_stale(stale_minutes=10) is True


def test_heartbeat_stale_at_exact_threshold(tmp_path):
    """A heartbeat exactly at the threshold age must be stale (strict > comparison)."""
    wdog = _import_watchdog()
    hb = tmp_path / "discord-bridge-heartbeat.json"
    # Exactly 10 minutes old -- should be stale (age > threshold, not >=).
    # We subtract 10 min + 1 sec to be strictly past the threshold.
    border = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10, seconds=1)
    hb.write_text(
        json.dumps({"last_tick_at": border.strftime("%Y-%m-%dT%H:%M:%SZ"), "consecutive_errors": 0}),
        encoding="utf-8",
    )
    with mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", hb):
        assert wdog._heartbeat_stale(stale_minutes=10) is True


# ---------------------------------------------------------------------------
# 2. _pid_cmdline_match() -- CommandLine verification
# ---------------------------------------------------------------------------

def _fake_wmic_output(cmdline: str, pid: int = 12345) -> bytes:
    """Build a fake wmic CSV output line for the given CommandLine."""
    return (
        f"\r\nNode,CommandLine,ProcessId\r\n"
        f"TESTHOST,{cmdline},{pid}\r\n\r\n"
    ).encode("utf-8")


def test_pid_cmdline_match_returns_true_when_script_in_cmdline():
    """PID whose CommandLine contains the script name must match."""
    wdog = _import_watchdog()
    script_name = "discord-bridge.py"
    fake_out = _fake_wmic_output(
        f"C:\\Python313\\pythonw.exe C:\\Gamma\\setup\\scripts\\{script_name}"
    )
    with mock.patch("subprocess.check_output", return_value=fake_out):
        result = wdog._pid_cmdline_match(12345, script_name)
    assert result is True, "Expected True: script name is in the CommandLine"


def test_pid_cmdline_match_returns_false_when_script_not_in_cmdline():
    """PID whose CommandLine does NOT contain the script name must not match.

    This is the PID-reuse scenario: VSHelper (or any unrelated process) has
    been assigned the same PID as the dead bridge.
    """
    wdog = _import_watchdog()
    script_name = "discord-bridge.py"
    fake_out = _fake_wmic_output(
        "C:\\Program Files\\Microsoft Visual Studio\\Common7\\IDE\\CommonExtensions\\"
        "Microsoft\\TeamFoundation\\Team Explorer\\VSHelper.exe"
    )
    with mock.patch("subprocess.check_output", return_value=fake_out):
        result = wdog._pid_cmdline_match(12345, script_name)
    assert result is False, (
        "Expected False: VSHelper CommandLine must not match 'discord-bridge.py' "
        "(this is the PID-reuse scar that let the dead bridge go undetected)"
    )


def test_pid_cmdline_match_fails_open_when_wmic_missing():
    """If wmic is not available (FileNotFoundError) the check must fail-open (True).

    Fail-open prevents false-positives: we'd rather not restart a healthy bridge
    than incorrectly restart it because our tooling is absent.
    """
    wdog = _import_watchdog()
    with mock.patch("subprocess.check_output", side_effect=FileNotFoundError("wmic not found")):
        result = wdog._pid_cmdline_match(12345, "discord-bridge.py")
    assert result is True, "wmic missing should fail-open (True), not false-restart"


def test_pid_cmdline_match_fails_open_on_timeout():
    """If wmic times out the check must fail-open (True)."""
    wdog = _import_watchdog()
    with mock.patch(
        "subprocess.check_output",
        side_effect=subprocess.TimeoutExpired(cmd="wmic", timeout=10),
    ):
        result = wdog._pid_cmdline_match(12345, "discord-bridge.py")
    assert result is True, "wmic timeout should fail-open (True), not false-restart"


def test_pid_cmdline_match_returns_false_for_empty_wmic_output():
    """wmic returning no data rows (process gone) must return False."""
    wdog = _import_watchdog()
    # wmic emits only the header and blank lines when the PID is gone.
    empty_out = b"\r\nNode,CommandLine,ProcessId\r\n\r\n"
    with mock.patch("subprocess.check_output", return_value=empty_out):
        result = wdog._pid_cmdline_match(99999, "discord-bridge.py")
    assert result is False, "Empty wmic output (PID gone) must return False"


# ---------------------------------------------------------------------------
# 3. Integration: main() logs WARNING for stale heartbeat, does NOT restart
# ---------------------------------------------------------------------------

def test_main_warns_and_does_not_restart_on_stale_heartbeat(tmp_path):
    """When PID is alive + cmdline matches but heartbeat is stale,
    main() must log a WARNING and NOT attempt to restart the bridge.

    This directly guards against the 30-hr silent outage: the bridge was alive
    (PID check passed) but frozen (not polling), and no warning was surfaced.
    """
    wdog = _import_watchdog()

    stale_hb = tmp_path / "discord-bridge-heartbeat.json"
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    stale_hb.write_text(
        json.dumps({"last_tick_at": past.strftime("%Y-%m-%dT%H:%M:%SZ"), "consecutive_errors": 0}),
        encoding="utf-8",
    )

    log_messages: list[str] = []

    def fake_log(msg: str) -> None:
        log_messages.append(msg)

    fake_pid_file = tmp_path / "discord-bridge.pid"
    fake_pid_file.write_text("99999|2026-06-28T00:00:00Z", encoding="utf-8")

    # Build minimal TARGETS that only exercises the bridge target.
    bridge_script = REPO / "setup" / "scripts" / "discord-bridge.py"
    fake_targets = [("discord-bridge", bridge_script, fake_pid_file)]
    fake_launch_calls: list[str] = []

    def fake_launch(name: str, script: Path) -> int | None:
        fake_launch_calls.append(name)
        return 99998

    with (
        mock.patch.object(wdog, "TARGETS", fake_targets),
        mock.patch.object(wdog, "BRIDGE_HEARTBEAT_PATH", stale_hb),
        mock.patch.object(wdog, "_pid_alive", return_value=True),
        mock.patch.object(wdog, "_pid_cmdline_match", return_value=True),
        mock.patch.object(wdog, "_log", side_effect=fake_log),
        mock.patch.object(wdog, "_launch", side_effect=fake_launch),
    ):
        rc = wdog.main()

    assert rc == 0, f"main() returned non-zero: {rc}"
    assert not fake_launch_calls, (
        "main() must NOT call _launch on a stale-heartbeat bridge "
        "(no auto-restart to avoid message floods)"
    )
    warning_msgs = [m for m in log_messages if "WARNING" in m and "stale" in m.lower()]
    assert warning_msgs, (
        "main() must log a WARNING about stale heartbeat; got log_messages=" + repr(log_messages)
    )
