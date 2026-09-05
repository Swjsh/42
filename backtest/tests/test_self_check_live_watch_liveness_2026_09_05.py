"""Guard for setup/scripts/self_check.py::check_live_watch_liveness -- self-audit gap
batch 2026-09-01 item 6 ("Live-watch writer has no dead-man switch... if a real position
is open and the writer dies, nothing alerts"). VERIFIED gap: check_live_watch_field_
completeness's own docstring claimed live-watch.json freshness was "owned by other
surfaces (engine-health.json)" -- grepped engine_health.py and dead_mans_switch.py,
zero live_watch references in either. Nothing anywhere checked whether Gamma_LiveWatch
was still alive until this check shipped.

Pure-logic + tmp_path only -- no live state touched, no network. Age is computed by
self_check._age_min via the REAL wall clock (os.stat mtime vs dt.datetime.now()), so
staleness is driven by os.utime() on the fixture file, not by the injected `now` param
(that param only gates the RTH window, matching every sibling staleness check in this
file, e.g. check_quote_recorder_alive / check_dress_rehearsal).
"""
from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

RTH_NOW = dt.datetime(2026, 9, 1, 10, 15, 0)   # Tuesday mid-RTH
PRE_OPEN_NOW = dt.datetime(2026, 9, 1, 9, 26, 0)   # inside the 09:25 startup slack
POST_CLOSE_NOW = dt.datetime(2026, 9, 1, 16, 30, 0)   # after the RTH window
WEEKEND_NOW = dt.datetime(2026, 9, 5, 10, 15, 0)   # Saturday


def _sc():
    return importlib.import_module("self_check")


def _touch(p: Path, age_minutes: float) -> None:
    p.write_text("{}", encoding="utf-8")
    ts = time.time() - age_minutes * 60
    os.utime(p, (ts, ts))


def test_weekend_is_silent_regardless_of_file_state(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    # even a nonexistent file must not fire on a weekend
    assert sc.check_live_watch_liveness(WEEKEND_NOW, path=p) == []
    _touch(p, age_minutes=999)
    assert sc.check_live_watch_liveness(WEEKEND_NOW, path=p) == []


def test_before_startup_slack_is_silent(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    assert sc.check_live_watch_liveness(PRE_OPEN_NOW, path=p) == []


def test_after_rth_window_is_silent(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    assert sc.check_live_watch_liveness(POST_CLOSE_NOW, path=p) == []


def test_missing_file_in_rth_is_red(tmp_path):
    sc = _sc()
    p = tmp_path / "no-file.json"
    out = sc.check_live_watch_liveness(RTH_NOW, path=p)
    assert len(out) == 1
    assert "LIVE-WATCH WRITER RED" in out[0]
    assert "never ticked" in out[0]


def test_fresh_file_in_rth_is_clean(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    _touch(p, age_minutes=0.5)
    assert sc.check_live_watch_liveness(RTH_NOW, path=p) == []


def test_stale_file_in_rth_is_red(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    _touch(p, age_minutes=10.0)
    out = sc.check_live_watch_liveness(RTH_NOW, path=p)
    assert len(out) == 1
    assert "LIVE-WATCH WRITER RED" in out[0]
    assert "10m stale" in out[0]


def test_just_under_threshold_is_not_yet_stale(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    _touch(p, age_minutes=3.5)   # comfortably under the 4m threshold; exact-boundary
                                 # timing is inherently flaky (test setup itself takes time)
    assert sc.check_live_watch_liveness(RTH_NOW, path=p) == []


def test_red_problem_classifies_as_broken_not_degraded():
    sc = _sc()
    msg = "LIVE-WATCH WRITER RED: live-watch.json is 10m stale during RTH."
    assert sc._problem_is_broken(msg) is True


def test_gap_is_real_no_dead_man_switch_existed_elsewhere():
    """RED-PROOF of the underlying claim: before this fire, nothing else in the repo
    checked live-watch.json liveness. This is a structural sentinel, not a behavior
    test -- it fails loudly if a future refactor silently reintroduces a duplicate/
    conflicting liveness surface without updating this comment."""
    eh = (SCRIPTS / "engine_health.py").read_text(encoding="utf-8")
    dms = (SCRIPTS / "dead_mans_switch.py").read_text(encoding="utf-8")
    assert "live_watch" not in eh and "live-watch" not in eh
    assert "live_watch" not in dms and "live-watch" not in dms
