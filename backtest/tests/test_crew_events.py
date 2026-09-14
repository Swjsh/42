"""Guard: setup/scripts/crew_events.py -- the ticker-able crew work log (2026-09-14
company-roster re-point, GOAL-GAMMA-STATION-2026-09-13).

Locks in: append-then-read round trip, the 500-row cap (oldest dropped first, atomic
rewrite), last_row's filter combinations, and that a malformed line/file never raises
(same fail-open contract as station_board.read_jsonl/append_jsonl, which this module
deliberately mirrors). Every test uses tmp_path -- never the real repo's
automation/state/station/crew-events.jsonl.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import crew_events as ce  # noqa: E402


def test_append_then_read_round_trips(tmp_path):
    p = tmp_path / "crew-events.jsonl"
    assert ce.append({"ts_et": "t1", "who": "Chef", "kind": "verdict", "line": "L1", "ref": "c1"}, path=p)
    assert ce.append({"ts_et": "t2", "who": "Coach", "kind": "sectors", "line": "L2", "ref": "r2"}, path=p)

    rows = ce.read_rows(p)
    assert [r["line"] for r in rows] == ["L1", "L2"]


def test_read_rows_missing_file_returns_empty_list(tmp_path):
    assert ce.read_rows(tmp_path / "does-not-exist.jsonl") == []


def test_read_rows_skips_malformed_lines(tmp_path):
    p = tmp_path / "crew-events.jsonl"
    p.write_text('{"a": 1}\nNOT JSON\n{"a": 2}\n', encoding="utf-8")
    assert ce.read_rows(p) == [{"a": 1}, {"a": 2}]


def test_append_caps_at_default_500_dropping_oldest_first(tmp_path):
    p = tmp_path / "crew-events.jsonl"
    for i in range(505):
        ce.append({"ts_et": f"t{i}", "who": "Gamma", "kind": "brief", "line": f"L{i}", "ref": None}, path=p)

    rows = ce.read_rows(p)
    assert len(rows) == 500
    assert rows[0]["line"] == "L5", "the 5 oldest rows (L0-L4) must drop first"
    assert rows[-1]["line"] == "L504", "the newest row must always survive the cap"


def test_append_respects_a_custom_cap(tmp_path):
    p = tmp_path / "crew-events.jsonl"
    for i in range(12):
        ce.append({"line": f"L{i}"}, path=p, cap=10)
    rows = ce.read_rows(p)
    assert len(rows) == 10
    assert rows[0]["line"] == "L2"
    assert rows[-1]["line"] == "L11"


def test_append_never_raises_on_an_unwritable_path(tmp_path):
    # A path whose parent is actually a FILE (not a directory) can never be created --
    # append() must degrade to a logged-by-caller False, never an exception.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad_path = blocker / "crew-events.jsonl"
    assert ce.append({"line": "x"}, path=bad_path) is False


def test_last_row_returns_none_when_file_is_empty(tmp_path):
    assert ce.last_row(path=tmp_path / "nope.jsonl") is None


def test_last_row_returns_the_most_recent_match_only(tmp_path):
    p = tmp_path / "crew-events.jsonl"
    ce.append({"who": "Chef", "kind": "verdict", "ref": "c1", "line": "first"}, path=p)
    ce.append({"who": "Coach", "kind": "sectors", "ref": "sectors.json", "line": "s1"}, path=p)
    ce.append({"who": "Chef", "kind": "verdict", "ref": "c1", "line": "second"}, path=p)
    ce.append({"who": "Chef", "kind": "verdict", "ref": "c2", "line": "other-card"}, path=p)

    latest_c1 = ce.last_row(kind="verdict", who="Chef", ref="c1", path=p)
    assert latest_c1["line"] == "second"

    latest_sectors = ce.last_row(kind="sectors", who="Coach", path=p)
    assert latest_sectors["line"] == "s1"

    assert ce.last_row(kind="task_health", path=p) is None


def test_default_path_points_under_automation_state_station():
    assert ce.DEFAULT_PATH == REPO / "automation" / "state" / "station" / "crew-events.jsonl"
