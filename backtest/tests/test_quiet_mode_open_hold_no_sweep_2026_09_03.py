"""An OPEN quiet-mode hold must suspend the catch-up sweep, not fuel it.

Live incident 2026-09-03 00:45 ET (found while closing GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-
EVENING): from 23:47 ET the sweep started the SAME five CATCHUP_ELIGIBLE tasks on every
5-minute enforcer cycle -- 41 sweeps, McpDailyAudit (~$0.10, LLM) twelve times an hour --
with each task's real LastRunTime advancing every cycle. Mechanism, one sentence:
`parse_quiet_holds` closes an unterminated trailing hold at `now`, so while a hold is OPEN
(a 'QUIET HELD past the clock' with no later 'QUIET OFF' -- which is exactly the state the
LOUD-band presence path leaves behind when it routes a fullscreen app to the research band
instead of a blackout) `latest_hold_end` advances every cycle and the idempotency test
`last_run >= latest_hold_end` can never be satisfied, while the research band still calls
the sweep. Catch-up is for AFTER a hold closes; an open hold must return an empty sweep.
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
qm = importlib.import_module("quiet_mode")
sts = importlib.import_module("scheduled_task_staleness")

ET = dt.timezone(dt.timedelta(hours=-4))
NOW = dt.datetime(2026, 9, 3, 0, 45, tzinfo=ET)
HOLD_START = dt.datetime(2026, 9, 2, 23, 50, tzinfo=ET)
CLOSED_HOLDS = [(HOLD_START, dt.datetime(2026, 9, 3, 0, 10, tzinfo=ET))]
OPEN_HOLDS = [(HOLD_START, NOW)]  # parse_quiet_holds' own shape for an unterminated hold


def _row(name, *, missed=3, last_run="2026-09-03T00:39:06-04:00"):
    return {"name": name, "state": "Ready", "lastRun": last_run, "nextRun": None,
            "lastResult": 0, "missedRuns": missed, "triggerKind": "MSFT_TaskDailyTrigger",
            "startBound": "2026-08-20T23:20:00-04:00", "repeat": None, "repeatFor": None}


@pytest.fixture(autouse=True)
def _isolate_log_file(monkeypatch, tmp_path):
    monkeypatch.setattr(qm, "LOG_FILE", tmp_path / "quiet-mode.log")


def _sweep(holds, rows, monkeypatch):
    monkeypatch.setattr(qm, "_in_trading_band", lambda now: False)
    with patch.object(sts, "query_tasks", return_value=rows), \
         patch.object(sts, "attribute_quiet_hold", return_value="fell inside a hold"), \
         patch.object(sts, "parse_quiet_holds", return_value=holds), \
         patch.object(qm, "_ps") as mock_ps:
        started = qm._catchup_sweep(NOW)
    return started, mock_ps


def test_open_hold_starts_nothing(monkeypatch):
    names = sorted(qm.CATCHUP_ELIGIBLE)[:3]
    started, ps = _sweep(OPEN_HOLDS, [_row(n) for n in names], monkeypatch)
    assert started == [], started
    ps.assert_not_called()


def test_open_hold_starts_nothing_even_for_the_heavy_tier(monkeypatch):
    for gate in ("_in_loud_heavy_band",):
        monkeypatch.setattr(qm, gate, lambda now: True)
    monkeypatch.setattr(qm, "_heavy_process_running", lambda: False)
    rows = [_row(n) for n in sorted(qm.HEAVY_CATCHUP_ELIGIBLE)]
    started, ps = _sweep(OPEN_HOLDS, rows, monkeypatch)
    assert started == []
    ps.assert_not_called()


def test_closed_hold_still_catches_up_the_control_case(monkeypatch):
    """Control: the same rows under a CLOSED hold with last_run BEFORE the close still start."""
    name = sorted(qm.CATCHUP_ELIGIBLE)[0]
    started, ps = _sweep(CLOSED_HOLDS, [_row(name, last_run="2026-09-02T23:00:00-04:00")], monkeypatch)
    assert started == [name]
    ps.assert_called_once()


def test_open_hold_is_logged_once_per_sweep_so_the_deferral_is_visible(monkeypatch, tmp_path):
    names = sorted(qm.CATCHUP_ELIGIBLE)[:1]
    _sweep(OPEN_HOLDS, [_row(n) for n in names], monkeypatch)
    text = (tmp_path / "quiet-mode.log").read_text(encoding="utf-8")
    assert "deferred" in text and "OPEN" in text, text


def test_conftest_isolation_is_active_for_any_quiet_mode_test():
    """The conftest autouse fixture must have redirected LOG_FILE away from automation/state
    before this test body runs -- this is what makes the live-log pollution structurally
    impossible rather than per-file discipline."""
    assert "automation" not in str(qm.LOG_FILE).replace("\\", "/").split("/"), qm.LOG_FILE
