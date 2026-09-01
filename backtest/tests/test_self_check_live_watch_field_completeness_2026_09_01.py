"""Guard for setup/scripts/self_check.py::check_live_watch_field_completeness -- self-audit
gap batch 2026-08-30 item 7 ("Live watch lacks enforcement of REQUIRED_POSITION_FIELDS
completeness"). The 2026-08-01 build (WS7) only proved every REQUIRED_POSITION_FIELDS
value populates on a SYNTHETIC position (--dry-run-synthetic); nothing enforced it live, on
a REAL in-trade position, until this check. Pure-logic + tmp_path only -- no live state
touched, no network.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

NOW = dt.datetime(2026, 9, 1, 10, 15, 0)  # Tuesday mid-RTH


def _sc():
    return importlib.import_module("self_check")


def _lw_fields():
    return importlib.import_module("live_watch").REQUIRED_POSITION_FIELDS


def _full_pos(**overrides) -> dict:
    """A position dict with every REQUIRED_POSITION_FIELDS key populated non-null."""
    base = {k: 1 for k in _lw_fields()}
    base.update(overrides)
    return base


def test_missing_file_is_silent(tmp_path):
    sc = _sc()
    assert sc.check_live_watch_field_completeness(NOW, path=tmp_path / "no-file.json") == []


def test_corrupt_artifact_is_silent_not_a_crash(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    p.write_text("{not json", encoding="utf-8")
    assert sc.check_live_watch_field_completeness(NOW, path=p) == []


def test_non_dict_snapshot_is_silent(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert sc.check_live_watch_field_completeness(NOW, path=p) == []


def test_no_arms_in_trade_is_silent(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    p.write_text(json.dumps({"arms": {"safe-2": {"in_trade": False, "position": None}}}),
                encoding="utf-8")
    assert sc.check_live_watch_field_completeness(NOW, path=p) == []


def test_in_trade_with_missing_position_dict_is_silent(tmp_path):
    """in_trade True but position not yet assembled (arm-build failure) -- fail-open,
    another surface (fill-funnel / engine-health) owns "is the arm actually broken"."""
    sc = _sc()
    p = tmp_path / "live-watch.json"
    p.write_text(json.dumps({"arms": {"safe-2": {"in_trade": True, "position": None}}}),
                encoding="utf-8")
    assert sc.check_live_watch_field_completeness(NOW, path=p) == []


def test_in_trade_all_fields_populated_is_silent(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    snap = {"arms": {"safe-2": {"in_trade": True, "position": _full_pos()}}}
    p.write_text(json.dumps(snap), encoding="utf-8")
    assert sc.check_live_watch_field_completeness(NOW, path=p) == []


def test_in_trade_missing_field_flags_the_arm_and_field(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    pos = _full_pos(mid=None, dist_to_stop_pct=None)
    snap = {"arms": {"bold-2": {"in_trade": True, "position": pos}}}
    p.write_text(json.dumps(snap), encoding="utf-8")
    problems = sc.check_live_watch_field_completeness(NOW, path=p)
    assert len(problems) == 1
    assert "bold-2" in problems[0]
    assert "mid" in problems[0] and "dist_to_stop_pct" in problems[0]


def test_missing_field_classifies_degraded_not_broken(tmp_path):
    """VISIBILITY ONLY per WS7's own contract -- a null field on a real position must
    stay DEGRADED, never escalate self_check's aggregate verdict to BROKEN."""
    sc = _sc()
    p = tmp_path / "live-watch.json"
    pos = _full_pos(qty=None)
    snap = {"arms": {"safe-2": {"in_trade": True, "position": pos}}}
    p.write_text(json.dumps(snap), encoding="utf-8")
    problems = sc.check_live_watch_field_completeness(NOW, path=p)
    assert problems and not any(sc._problem_is_broken(pr) for pr in problems)


def test_multiple_in_trade_arms_each_evaluated_independently(tmp_path):
    sc = _sc()
    p = tmp_path / "live-watch.json"
    snap = {"arms": {
        "safe-2": {"in_trade": True, "position": _full_pos()},
        "bold-2": {"in_trade": True, "position": _full_pos(hwm_premium=None)},
        "risky-1": {"in_trade": False, "position": _full_pos(qty=None)},
    }}
    p.write_text(json.dumps(snap), encoding="utf-8")
    problems = sc.check_live_watch_field_completeness(NOW, path=p)
    assert len(problems) == 1
    assert "bold-2" in problems[0]
    assert "safe-2" not in problems[0] and "risky-1" not in problems[0]


def test_registered_in_main_aggregator():
    """Wiring check: run() must actually call the new check (matches the existing
    check_futures_health precedent's own wiring test)."""
    sc = _sc()
    src = Path(sc.__file__).read_text(encoding="utf-8")
    assert "problems.extend(check_live_watch_field_completeness(now))" in src
