"""Guards for setup/scripts/j_drawn_lines_capture.py + j_drawn_lines_score.py
(TRENDLINE-J-DRAWN-LINES-LEDGER, 2026-09-03).

Covers, offline (no live CDP dependency -- must pass with TradingView Desktop closed):
  1. Engine-line exclusion: a "[GTL] "-tagged trend_line never enters the population.
  2. Dedupe: an already-known entity_id is never re-appended / re-timestamped.
  3. Resolution restore: the fake chart's resolution is switched to canonical/alt and
     restored to its original value by the time capture's main() returns.
  4. SAFETY: the fake chart never exposes create/remove methods -- any accidental mutating
     call raises AttributeError and fails the test loudly (mirrors
     test_trendline_headless_draw_2026_09_03.py's own safety-first priority).
  5. No-look-ahead: a line is never scored on or before its own first_seen_date_et.
  6. Summary shape: j_drawn_lines_score.summarize() returns the decision/timeframes keys a
     consumer needs.
  plus line-shape classification, break-stops-scoring, and extend_right capping.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tv_cdp  # noqa: E402
import j_drawn_lines_capture as cap  # noqa: E402
import j_drawn_lines_score as scr  # noqa: E402


# --------------------------------------------------------------------------- fixtures/helpers

class _FakeChart:
    """Stands in for tv_cdp.TvChart. Implements list_shapes()/shape_text() directly (like
    the trendline_headless_draw sibling's own _FakeChart) and evaluate() via pattern
    matching for the handful of raw-JS calls j_drawn_lines_capture.py issues (resolution
    get/set, getPoints, getProperties). Deliberately exposes NO create_trend_line /
    remove_entity -- any accidental call raises AttributeError (safety net, see test 4)."""

    def __init__(self, shapes: dict[str, dict], resolution: str = "15"):
        # shapes: {entity_id: {"name", "text", "points": [{time,price}x2], "extend_right", "extend_left"}}
        self._shapes = shapes
        self.resolution = resolution
        self.resolutions_seen: list[str] = [resolution]

    def __enter__(self) -> "_FakeChart":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def require_chart_api(self) -> None:
        return None

    def symbol(self) -> str:
        return "BATS:SPY"

    def list_shapes(self) -> list[dict]:
        return [{"id": eid, "name": s["name"]} for eid, s in self._shapes.items()]

    def shape_text(self, entity_id: str) -> str | None:
        s = self._shapes.get(entity_id)
        return s.get("text") if s else None

    def evaluate(self, expr: str):
        if expr == f"{tv_cdp.CHART_API}.resolution()":
            return self.resolution
        m = re.search(r"setResolution\((.*?), \{\}\)", expr)
        if m:
            self.resolution = json.loads(m.group(1))
            self.resolutions_seen.append(self.resolution)
            return None
        m = re.search(r"getShapeById\((.*?)\)", expr)
        if m and "getPoints" in expr:
            eid = json.loads(m.group(1))
            return self._shapes.get(eid, {}).get("points")
        if m and ("getProperties" in expr or "extendRight" in expr):
            eid = json.loads(m.group(1))
            s = self._shapes.get(eid, {})
            return {"extend_right": s.get("extend_right", False),
                    "extend_left": s.get("extend_left", False),
                    "intervals_visibilities": s.get("intervals_visibilities")}
        raise AssertionError(f"unexpected evaluate() call in test: {expr[:200]}")


def _shape(text: str, points: list[dict], extend_right: bool = True) -> dict:
    return {"name": "trend_line", "text": text, "points": points,
            "extend_right": extend_right, "extend_left": False}


def _patch_tvchart(monkeypatch, chart: _FakeChart):
    monkeypatch.setattr(cap, "TvChart", lambda *a, **kw: chart)


# --------------------------------------------------------------------------- capture: 1. exclusion

def test_engine_tagged_line_excluded_from_population(tmp_path, monkeypatch):
    shapes = {
        "eng1": _shape("[GTL] [WICK] SUPPORT", [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]),
        "human1": _shape("", [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]),
    }
    chart = _FakeChart(shapes)
    _patch_tvchart(monkeypatch, chart)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cap, "LEDGER", ledger)
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(cap, "STATE_DIR", tmp_path)

    rc = cap.main([])
    assert rc == 0
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    ids = {r["entity_id"] for r in rows}
    assert "human1" in ids
    assert "eng1" not in ids


# --------------------------------------------------------------------------- capture: 2. dedupe

def test_dedupe_known_entity_id_never_reappended(tmp_path, monkeypatch):
    shapes = {"h1": _shape("", [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}])}
    chart = _FakeChart(shapes)
    _patch_tvchart(monkeypatch, chart)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cap, "LEDGER", ledger)
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(cap, "STATE_DIR", tmp_path)

    assert cap.main([]) == 0
    rows1 = ledger.read_text(encoding="utf-8").splitlines()
    assert len(rows1) == 1
    first_seen = json.loads(rows1[0])["first_seen_et"]

    assert cap.main([]) == 0  # second run, same chart state
    rows2 = ledger.read_text(encoding="utf-8").splitlines()
    assert len(rows2) == 1  # never re-appended
    assert json.loads(rows2[0])["first_seen_et"] == first_seen  # never re-timestamped


# --------------------------------------------------------------------------- capture: 3. resolution restore

def test_resolution_switched_and_restored(tmp_path, monkeypatch):
    shapes = {"h1": _shape("", [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}])}
    chart = _FakeChart(shapes, resolution="60")  # some unrelated original resolution
    _patch_tvchart(monkeypatch, chart)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cap, "LEDGER", ledger)
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(cap, "STATE_DIR", tmp_path)
    monkeypatch.setattr(cap, "SETTLE_SEC", 0.0)

    assert cap.main([]) == 0
    # switched to canonical "5" then alt "15" then restored to "60"
    assert chart.resolutions_seen == ["60", "5", "15", "60"]
    assert chart.resolution == "60"
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["resolution_restored_ok"] is True
    assert state["original_resolution"] == "60"
    assert state["restored_resolution"] == "60"


# --------------------------------------------------------------------------- capture: 4. SAFETY

def test_capture_never_calls_a_mutating_chart_method(tmp_path, monkeypatch):
    """The fake chart deliberately has no create_trend_line/remove_entity -- if capture
    ever called one, AttributeError would propagate and this test would fail loudly."""
    shapes = {"h1": _shape("", [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}])}
    chart = _FakeChart(shapes)
    assert not hasattr(chart, "create_trend_line")
    assert not hasattr(chart, "remove_entity")
    assert not hasattr(chart, "create_horizontal_line")
    _patch_tvchart(monkeypatch, chart)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cap, "LEDGER", ledger)
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(cap, "STATE_DIR", tmp_path)

    assert cap.main([]) == 0  # would have raised AttributeError if it tried to mutate


# --------------------------------------------------------------------------- capture: fail-open + dry-run

def test_fail_open_on_cdp_down(tmp_path, monkeypatch):
    def _boom(*a, **kw):
        raise tv_cdp.TvCdpError("fake: CDP not reachable")
    monkeypatch.setattr(cap, "TvChart", _boom)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cap, "LEDGER", ledger)
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(cap, "STATE_DIR", tmp_path)

    rc = cap.main([])
    assert rc == 0
    assert not ledger.exists()
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "SKIPPED_TV_DOWN"


def test_dry_run_never_writes_ledger(tmp_path, monkeypatch):
    shapes = {"h1": _shape("", [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}])}
    chart = _FakeChart(shapes)
    _patch_tvchart(monkeypatch, chart)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(cap, "LEDGER", ledger)
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(cap, "STATE_DIR", tmp_path)

    assert cap.main(["--dry-run"]) == 0
    assert not ledger.exists()


# --------------------------------------------------------------------------- capture: pure helpers

def test_line_shape_classification_and_timeframe_is_other():
    canonical = {
        "rise": {"text": "", "points": [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]},
        "fall": {"text": "", "points": [{"time": 100, "price": 2.0}, {"time": 200, "price": 1.0}]},
        "flat": {"text": "", "points": [{"time": 100, "price": 1.0}, {"time": 200, "price": 1.0}]},
    }
    rows, stats = cap.build_ledger_rows(canonical, {}, set(), "2026-09-03T18:00:00-04:00", "2026-09-03")
    by_id = {r["entity_id"]: r for r in rows}
    assert by_id["rise"]["line_shape"] == "rising"
    assert by_id["fall"]["line_shape"] == "falling"
    assert by_id["flat"]["line_shape"] == "flat"
    assert all(r["timeframe"] == "other" for r in rows)


def test_drift_detected_flag_set_when_alt_reading_differs():
    canonical = {"h1": {"text": "", "points": [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]}}
    alt_same = {"h1": {"text": "", "points": [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]}}
    alt_diff = {"h1": {"text": "", "points": [{"time": 900, "price": 1.0}, {"time": 200, "price": 2.0}]}}

    rows_same, _ = cap.build_ledger_rows(canonical, alt_same, set(), "t", "2026-09-03")
    assert rows_same[0]["drift_detected"] is False

    rows_diff, _ = cap.build_ledger_rows(canonical, alt_diff, set(), "t", "2026-09-03")
    assert rows_diff[0]["drift_detected"] is True


# --------------------------------------------------------------------------- score: no-look-ahead

def _bar5m(t_dt: dt.datetime, o, h, l, c) -> dict:
    return {"t_dt": t_dt, "t_unix": int(t_dt.timestamp()), "o": o, "h": h, "l": l, "c": c, "v": 1000.0}


def test_no_lookahead_line_not_scored_on_or_before_first_seen_date():
    a_time = int(dt.datetime(2026, 9, 3, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    b_time = a_time + 3600
    line_row = {
        "kind": "line", "entity_id": "h1", "first_seen_date_et": "2026-09-03",
        "in_sample": True, "line_shape": "rising", "extend_right": True,
        "anchor1": {"time": a_time, "price": 100.0}, "anchor2": {"time": b_time, "price": 101.0},
    }
    # bars ONLY on the same day as first_seen -- must produce zero events (no look-ahead)
    same_day = dt.datetime(2026, 9, 3, 9, 30, tzinfo=dt.timezone.utc)
    bars_by_date = {"2026-09-03": [_bar5m(same_day + dt.timedelta(minutes=5 * i), 100 + i * 0.01,
                                           100.5 + i * 0.01, 99.5 + i * 0.01, 100 + i * 0.01)
                                    for i in range(40)]}
    rows = scr.score_line(line_row, bars_by_date, set())
    assert rows == []


def test_scoring_starts_next_session_and_break_stops_further_events():
    a_time = int(dt.datetime(2026, 9, 3, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    b_time = a_time + 900  # +15 min, price rises $1
    line_row = {
        "entity_id": "h1", "first_seen_date_et": "2026-09-03", "line_shape": "rising",
        "extend_right": True,
        "anchor1": {"time": a_time, "price": 100.0}, "anchor2": {"time": b_time, "price": 101.0},
    }
    day2 = dt.datetime(2026, 9, 4, 9, 30, tzinfo=dt.timezone.utc)
    bars = []
    # line value at day2 09:30 = 100 + rate*(t-a_time); rate = 1/900 = 0.001111/sec
    # build a session that touches then breaks
    t = day2
    rate = (101.0 - 100.0) / (b_time - a_time)
    for i in range(30):
        tt = t + dt.timedelta(minutes=5 * i)
        lv = 100.0 + rate * (int(tt.timestamp()) - a_time)
        if i < 10:
            bars.append(_bar5m(tt, lv, lv + 0.5, lv, lv + 0.05))       # touch-ish (close>line, low~=line)
        else:
            bars.append(_bar5m(tt, lv, lv, lv - 5.0, lv - 5.0))         # hard break, closes well below
    bars_by_date = {"2026-09-04": bars}
    rows = scr.score_line(line_row, bars_by_date, set())
    kinds = [r["event_type"] for r in rows]
    assert "break" in kinds
    break_idx = kinds.index("break")
    assert all(k == "touch" for k in kinds[:break_idx])
    assert kinds.count("break") == 1
    # nothing scored after the break bar
    assert kinds[break_idx:] == ["break"]


def test_extend_right_false_caps_scoring_at_anchor2_time():
    a_time = int(dt.datetime(2026, 9, 3, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    b_time = a_time + 900
    line_row = {
        "entity_id": "h1", "first_seen_date_et": "2026-09-03", "line_shape": "rising",
        "extend_right": False,
        "anchor1": {"time": a_time, "price": 100.0}, "anchor2": {"time": b_time, "price": 101.0},
    }
    # every bar on day2 is far AFTER anchor2.time (b_time is on 09-03) -> nothing should score
    day2 = dt.datetime(2026, 9, 4, 9, 30, tzinfo=dt.timezone.utc)
    bars = [_bar5m(day2 + dt.timedelta(minutes=5 * i), 100, 100.5, 99.5, 100) for i in range(10)]
    rows = scr.score_line(line_row, {"2026-09-04": bars}, set())
    assert rows == []


def test_non_rising_line_never_scored():
    a_time = int(dt.datetime(2026, 9, 3, 9, 30, tzinfo=dt.timezone.utc).timestamp())
    line_row = {
        "entity_id": "h1", "first_seen_date_et": "2026-09-03", "line_shape": "falling",
        "extend_right": True,
        "anchor1": {"time": a_time, "price": 101.0}, "anchor2": {"time": a_time + 900, "price": 100.0},
    }
    day2 = dt.datetime(2026, 9, 4, 9, 30, tzinfo=dt.timezone.utc)
    bars = [_bar5m(day2 + dt.timedelta(minutes=5 * i), 100, 100.5, 99.5, 100) for i in range(10)]
    assert scr.score_line(line_row, {"2026-09-04": bars}, set()) == []


# --------------------------------------------------------------------------- score: summary shape

def test_summary_shape_has_decision_and_timeframes():
    rows = [{
        "kind": "line", "entity_id": "h1", "first_seen_date_et": "2026-08-01",
        "in_sample": True, "line_shape": "rising",
    }]
    summary = scr.summarize(rows, {})
    assert "decision" in summary
    assert "timeframes" in summary
    assert "other" in summary["timeframes"]
    d = summary["decision"]
    for key in ("n_lines_forward", "bar_met", "date_gate_open", "status"):
        assert key in d
    assert d["status"] == "ACCRUING"  # zero forward lines can never meet the bar
