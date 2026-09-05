"""Guard: the Kitchen daemon keepalive must restart-on-stale-code ONLY when idle.

GOAL-RIG-HYGIENE-2026-09-05 H1. Before this fix, `run-kitchen-daemon-keepalive.ps1` only
ever restarted a DEAD or WEDGED (status stale > 25min) daemon -- a shipped fix to
kitchen_daemon.py / kitchen_stage1_runner.py / kitchen_reviewer.py / chef_nemotron.py could
sit un-deployed for hours while the daemon kept running the pre-ship code, because nothing
compared the daemon's start time against the scripts' mtimes.

The failure mode this guard exists to prevent is a decision function that restarts a BUSY
daemon (idle=false) mid-grinder-job -- explicitly forbidden by this goal's OPERATING RULES
-- so these tests exercise both the idle+stale RESTART branch and the busy-refusal branch,
not just the trivial "nothing to do" path any broken build would also pass.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

policy = importlib.import_module("kitchen_daemon_restart_policy")

T0 = dt.datetime(2026, 9, 5, 4, 10, 1, tzinfo=dt.timezone.utc)          # daemon start
BEFORE_START = T0 - dt.timedelta(hours=1)                                # old script edit
AFTER_START = T0 + dt.timedelta(hours=6)                                 # new script edit (shipped later)


def test_pure_no_restart_while_busy_even_if_code_is_stale():
    """THE scar case in reverse: code IS stale, but idle=false must win -- never kill a live job."""
    should, reason = policy.decide_restart(idle=False, daemon_start_utc=T0, script_mtimes_utc=[AFTER_START])
    assert should is False
    assert "busy" in reason


def test_pure_restarts_when_idle_and_code_is_newer_than_daemon_start():
    should, reason = policy.decide_restart(idle=True, daemon_start_utc=T0, script_mtimes_utc=[BEFORE_START, AFTER_START])
    assert should is True
    assert "predates" in reason


def test_pure_no_restart_when_idle_but_code_unchanged_since_start():
    should, reason = policy.decide_restart(idle=True, daemon_start_utc=T0, script_mtimes_utc=[BEFORE_START])
    assert should is False
    assert "current" in reason


def test_pure_refuses_to_restart_blind_when_no_scripts_found():
    should, reason = policy.decide_restart(idle=True, daemon_start_utc=T0, script_mtimes_utc=[])
    assert should is False
    assert "nothing to compare" in reason


@pytest.fixture()
def sandbox(tmp_path):
    status_file = tmp_path / "kitchen-status.json"
    pid_file = tmp_path / "kitchen-daemon.pid"
    script = tmp_path / "watched_script.py"
    script.write_text("# placeholder\n", encoding="utf-8")
    return status_file, pid_file, script


def _write_status(path: Path, idle: bool) -> None:
    path.write_text(json.dumps({"idle": idle, "daemon_pid": 999}), encoding="utf-8")


def _write_pid(path: Path, started_utc: dt.datetime) -> None:
    path.write_text(json.dumps({"pid": 999, "started_at_utc": started_utc.isoformat()}), encoding="utf-8")


def test_smoke_gather_and_decide_restarts_when_idle_and_daemon_predates_edit(sandbox):
    """Smoke of the actual I/O path the keepalive script invokes (decision path only -- no process spawn)."""
    status_file, pid_file, script = sandbox
    old_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    _write_status(status_file, idle=True)
    _write_pid(pid_file, old_start)
    # Touch the watched script AFTER the recorded daemon start.
    import os
    import time
    time.sleep(0.01)
    os.utime(script, None)  # bump mtime to "now", which is after old_start

    should, reason = policy.gather_and_decide(
        status_file=status_file, pid_file=pid_file, watched_scripts=[script]
    )
    assert should is True, reason


def test_smoke_gather_and_decide_never_restarts_when_status_says_busy(sandbox):
    status_file, pid_file, script = sandbox
    old_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    _write_status(status_file, idle=False)
    _write_pid(pid_file, old_start)

    should, reason = policy.gather_and_decide(
        status_file=status_file, pid_file=pid_file, watched_scripts=[script]
    )
    assert should is False
    assert "busy" in reason


def test_smoke_gather_and_decide_missing_files_refuses_blind(tmp_path):
    should, reason = policy.gather_and_decide(
        status_file=tmp_path / "nope-status.json",
        pid_file=tmp_path / "nope-pid.json",
        watched_scripts=[],
    )
    assert should is False
    assert "missing" in reason
