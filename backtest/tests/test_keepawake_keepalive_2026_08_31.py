"""Guard: the keepawake watchdog must actually RESTART a dead daemon, not just no-op.

SCAR (2026-08-31): market_hours_keepawake.py died silently at 09:23 ET, 99 ticks in, empty
stderr. Nothing restarted it because nothing watched it -- Gamma_MarketKeepAwake is a single
07:45 ET fire with no keepalive. The box was free to idle-sleep mid-session for 13 minutes
until a human happened to read engine-health.json.

The failure mode this guard exists to prevent is a watchdog that LOOKS installed but never
fires -- the C7 family (silent success is failure). So these tests exercise the RESTART
branch, not just the outside-window no-op that any broken build would also pass.
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

ka = importlib.import_module("market_keepawake_keepalive")


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect every file the module writes so tests never touch live state."""
    monkeypatch.setattr(ka, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(ka, "BEAT", tmp_path / "beat.json")
    monkeypatch.setattr(ka, "LOG_DIR", tmp_path)
    return tmp_path


def _at(monkeypatch, when: dt.datetime) -> None:
    monkeypatch.setattr(ka, "et_now", lambda: when)


IN_WINDOW = dt.datetime(2026, 9, 1, 10, 30, 0)      # Tuesday, mid-RTH
OUT_WINDOW = dt.datetime(2026, 9, 1, 23, 30, 0)     # Tuesday night
WEEKEND = dt.datetime(2026, 9, 5, 10, 30, 0)        # Saturday mid-day


def _write_beat(path: Path, when: dt.datetime) -> None:
    path.write_text(json.dumps({"last_assert_et": when.isoformat(timespec="seconds")}),
                    encoding="utf-8")


def test_restarts_when_process_is_gone(sandbox, monkeypatch):
    """THE scar case: heartbeat looks recent but the process is dead."""
    _at(monkeypatch, IN_WINDOW)
    _write_beat(ka.BEAT, IN_WINDOW - dt.timedelta(minutes=1))   # fresh beat
    monkeypatch.setattr(ka, "daemon_pids", lambda: ([], True))  # ...but no process
    called = []
    monkeypatch.setattr(ka, "relaunch", lambda: called.append(True) or True)

    assert ka.main() == 0
    assert called, "watchdog did NOT restart a dead daemon"
    st = json.loads(ka.STATUS.read_text(encoding="utf-8"))
    assert st["action"] == "restarted"
    assert "no live process" in st["reason"]


def test_restarts_when_heartbeat_is_stale(sandbox, monkeypatch):
    """Wedged, not dead: process exists but stopped writing its beat."""
    _at(monkeypatch, IN_WINDOW)
    _write_beat(ka.BEAT, IN_WINDOW - dt.timedelta(minutes=11))
    monkeypatch.setattr(ka, "daemon_pids", lambda: ([1234], True))
    called = []
    monkeypatch.setattr(ka, "relaunch", lambda: called.append(True) or True)

    assert ka.main() == 0
    assert called, "watchdog did NOT restart a wedged daemon"
    assert "stale" in json.loads(ka.STATUS.read_text(encoding="utf-8"))["reason"]


def test_noop_when_healthy(sandbox, monkeypatch):
    """A healthy daemon must NOT be respawned -- duplicates are the opposite failure."""
    _at(monkeypatch, IN_WINDOW)
    _write_beat(ka.BEAT, IN_WINDOW - dt.timedelta(seconds=30))
    monkeypatch.setattr(ka, "daemon_pids", lambda: ([1234], True))
    monkeypatch.setattr(ka, "relaunch", lambda: pytest.fail("restarted a HEALTHY daemon"))

    assert ka.main() == 0
    st = json.loads(ka.STATUS.read_text(encoding="utf-8"))
    assert st["action"] == "noop"
    assert "alive" in st["reason"]


def test_fails_open_when_enumeration_breaks(sandbox, monkeypatch):
    """Unknown liveness must never trigger a blind spawn loop (OP-25: guards fail open)."""
    _at(monkeypatch, IN_WINDOW)
    _write_beat(ka.BEAT, IN_WINDOW - dt.timedelta(minutes=30))
    monkeypatch.setattr(ka, "daemon_pids", lambda: ([], False))
    monkeypatch.setattr(ka, "relaunch", lambda: pytest.fail("spawned on unknown liveness"))

    assert ka.main() == 0
    assert json.loads(ka.STATUS.read_text(encoding="utf-8"))["action"] == "skipped_unknown_liveness"


@pytest.mark.parametrize("when", [OUT_WINDOW, WEEKEND], ids=["after_hours", "weekend"])
def test_noop_outside_daemon_window(sandbox, monkeypatch, when):
    _at(monkeypatch, when)
    monkeypatch.setattr(ka, "relaunch", lambda: pytest.fail("restarted outside the window"))
    assert ka.main() == 0
    assert json.loads(ka.STATUS.read_text(encoding="utf-8"))["action"] == "noop"


def test_missing_heartbeat_file_counts_as_down(sandbox, monkeypatch):
    """No beat file at all == daemon never started today. Must restart, not crash."""
    _at(monkeypatch, IN_WINDOW)
    monkeypatch.setattr(ka, "daemon_pids", lambda: ([1234], True))
    called = []
    monkeypatch.setattr(ka, "relaunch", lambda: called.append(True) or True)

    assert ka.main() == 0
    assert called, "missing heartbeat did not trigger a restart"
    assert "unreadable" in json.loads(ka.STATUS.read_text(encoding="utf-8"))["reason"]
