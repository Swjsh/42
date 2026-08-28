"""Guard tests for self_check.check_quote_recorder_alive (Task B1, 2026-08-28) -- the
STATUS.md 'Known broken' liveness check for quote_recorder.py's independent exit-quote
side-channel. Pure filesystem/time logic, no network, no broker.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import self_check as sc  # noqa: E402

NOW = dt.datetime(2026, 8, 28, 10, 0, 0)


def _touch_with_age(path: Path, minutes_old: float) -> None:
    ts = (dt.datetime.now() - dt.timedelta(minutes=minutes_old)).timestamp()
    os.utime(path, (ts, ts))


def test_never_deployed_is_silent(tmp_path):
    """A status file that has never been written (recorder's scheduled task not yet
    registered) must never alarm -- 'not yet turned on' is not a fault."""
    sp = tmp_path / "quote-recorder-status.json"
    assert sc.check_quote_recorder_alive(NOW, status_path=sp) == []


def test_fresh_status_is_silent(tmp_path):
    sp = tmp_path / "quote-recorder-status.json"
    sp.write_text(json.dumps({"consecutive_cycle_failures": 0}), encoding="utf-8")
    assert sc.check_quote_recorder_alive(NOW, status_path=sp) == []


def test_stale_status_is_red_and_classifies_broken(tmp_path):
    """Once the file exists (daemon ran at least once) and goes stale past the worst-case
    cadence (5m off-hours skip + buffer), this must fire RED and self_check's own
    _problem_is_broken classifier must read it as BROKEN (drives Discord + STATUS.md
    verdict escalation)."""
    sp = tmp_path / "quote-recorder-status.json"
    sp.write_text(json.dumps({"consecutive_cycle_failures": 0}), encoding="utf-8")
    _touch_with_age(sp, minutes_old=20)
    problems = sc.check_quote_recorder_alive(NOW, status_path=sp)
    assert len(problems) == 1
    assert "QUOTE-RECORDER RED" in problems[0]
    assert sc._problem_is_broken(problems[0]) is True


def test_just_under_staleness_threshold_is_silent(tmp_path):
    sp = tmp_path / "quote-recorder-status.json"
    sp.write_text(json.dumps({"consecutive_cycle_failures": 0}), encoding="utf-8")
    _touch_with_age(sp, minutes_old=5)  # well under the 8-minute threshold
    assert sc.check_quote_recorder_alive(NOW, status_path=sp) == []


def test_high_consecutive_failures_is_degraded_not_broken(tmp_path):
    """Daemon alive (fresh write) but mostly failing its cycles -> DEGRADED, never BROKEN --
    the process is producing signal about itself, just not producing quote rows."""
    sp = tmp_path / "quote-recorder-status.json"
    sp.write_text(json.dumps({"consecutive_cycle_failures": 7,
                              "last_cycle_errors": {"safe-2": "HTTP 401"}}), encoding="utf-8")
    problems = sc.check_quote_recorder_alive(NOW, status_path=sp)
    assert len(problems) == 1
    assert "QUOTE-RECORDER DEGRADED" in problems[0]
    assert sc._problem_is_broken(problems[0]) is False


def test_low_consecutive_failures_is_silent(tmp_path):
    sp = tmp_path / "quote-recorder-status.json"
    sp.write_text(json.dumps({"consecutive_cycle_failures": 2}), encoding="utf-8")
    assert sc.check_quote_recorder_alive(NOW, status_path=sp) == []


def test_corrupt_status_file_is_degraded(tmp_path):
    sp = tmp_path / "quote-recorder-status.json"
    sp.write_text("{not valid json", encoding="utf-8")
    problems = sc.check_quote_recorder_alive(NOW, status_path=sp)
    assert len(problems) == 1
    assert "QUOTE-RECORDER DEGRADED" in problems[0]


def test_registered_in_main_aggregator():
    """Wiring check: the aggregator's run() must actually call check_quote_recorder_alive
    (not just define it) -- guards against the function existing but never being invoked."""
    src = (REPO / "setup" / "scripts" / "self_check.py").read_text(encoding="utf-8")
    assert "problems.extend(check_quote_recorder_alive(now))" in src
