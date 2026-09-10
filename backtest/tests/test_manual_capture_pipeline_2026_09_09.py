"""Guards for WS-D (markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md #9.5 row D) -- the
one manual-capture pipeline fix, 2026-09-09.

THE DEFECT THIS FILE PINS (Opus-verified this session):
  automation/scripts/compute_trendlines.py::_load_manual_drawings used to filter chart
  shapes by TradingView `title` ALONE ("trendline"/"trend line"). Two consequences:
    1. The engine's OWN auto-drawn lines (setup/scripts/trendline_headless_draw.py,
       TAG="[GTL] ") have title "trendline" too, so they passed straight through and
       were written into trendlines.json with source="manual_chart_draw" -- live proof:
       entity ids 5iZLKB and TJsQJS.
    2. J's hand-drawn RAYS (title "ray") were rejected outright by the title check, even
       though a 2-point ray is exactly as much a trendline as a 2-point "trendline"
       shape -- e.g. J's real lower-wedge line, entity UvNj5Q.
  setup/scripts/j_drawn_lines_capture.py::_non_engine_trend_lines had the SAME "ray"
  blind spot from its own hard `name != "trend_line"` filter.

Also pinned: automation/state/chart_drawings.json carried NO `text` field at all before
this fix (its producer, automation/scripts/read_chart_drawings.js, emitted only
{id, title, point_count, points}) -- so tag-based exclusion was structurally impossible
from that snapshot shape. A drawing with no `text` key is therefore an old-schema
snapshot that cannot be proven non-engine, and must be DROPPED + counted
(n_dropped_no_text), never silently trusted.

All pure/offline: synthetic payloads only, no CDP, no TradingView Desktop dependency --
must pass with TV closed.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytz

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT / "automation" / "scripts"), str(REPO_ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import compute_trendlines as ct  # noqa: E402
import j_drawn_lines_capture as cap  # noqa: E402

ET = pytz.timezone("America/New_York")


def _write_synthetic_csv(data_dir: Path, base_date: dt.date, n_bars: int = 5) -> None:
    """A tiny synthetic SPY 5m CSV so ct.compute() has SOMETHING to read without touching
    the real backtest/data/ directory (mirrors test_trendline_manual_refresh_2026_08_18.py's
    own helper -- kept minimal here since test 4 only cares about the manual-drawing
    counters, not the bar-derived fields)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    lines = ["timestamp_et,open,high,low,close,volume"]
    start = ET.localize(dt.datetime.combine(base_date, dt.time(9, 30)))
    for i in range(n_bars):
        ts = start + dt.timedelta(minutes=5 * i)
        px = 700.00 + 0.01 * i
        lines.append(f"{ts.isoformat()},{px:.2f},{px + 0.05:.2f},{px - 0.05:.2f},{px:.2f},100000")
    (data_dir / f"spy_5m_{base_date.isoformat()}_{base_date.isoformat()}.csv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_chart_drawings(state_dir: Path, drawings: list[dict]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 3,
        "purpose": "test fixture",
        "as_of": "2026-09-09T12:00:00-04:00",
        "source": "synthetic",
        "count": len(drawings),
        "drawings": drawings,
    }
    (state_dir / "chart_drawings.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _pts(t1, p1, t2, p2) -> list[dict]:
    return [{"time": t1, "price": p1}, {"time": t2, "price": p2}]


# --------------------------------------------------------------------------------------- 1

def test_old_behavior_would_have_accepted_engine_tagged_trendline_new_behavior_rejects_it(
    tmp_path, monkeypatch
):
    """RED-proof against the OLD behavior (quoted from the pre-fix source, live before this
    session's edit):

        if (d.get("title") or "").lower() not in ("trendline", "trend line"):
            continue
        ... (no check on `text` at all) ...

    Under that OLD filter, a drawing with title "trendline" and text "[GTL] [WICK]
    SUPPORT touch x3" (the engine's own auto-drawn line, TAG="[GTL] ") would have been
    ACCEPTED and appear in trendlines.json with source="manual_chart_draw" -- this is
    the exact live bug (entity ids 5iZLKB, TJsQJS). The NEW behavior must never emit it
    as manual, and must count it under n_dropped_engine_tag."""
    state_dir = tmp_path / "state"
    drawing = {
        "id": "eng_line_1",
        "title": "trendline",
        "point_count": 2,
        "text": "[GTL] [WICK] SUPPORT touch x3",
        "points": _pts(1000, 700.0, 5000, 701.0),
    }

    # Sanity-check the OLD predicate really would have let this drawing through, so the
    # "before" half of this RED-proof is grounded in the actual removed logic, not a guess.
    old_title_only_filter_accepts = (drawing.get("title") or "").lower() in ("trendline", "trend line")
    assert old_title_only_filter_accepts, "fixture must reproduce the OLD filter's blind spot"

    _write_chart_drawings(state_dir, [drawing])
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    lines, id_lookup, counters = ct._load_manual_drawings()

    assert lines == [], "an engine-tagged [GTL] line must NEVER be emitted as manual"
    assert id_lookup == {}
    assert counters["n_dropped_engine_tag"] == 1
    assert counters["n_dropped_no_text"] == 0


# --------------------------------------------------------------------------------------- 2

def test_ray_two_point_with_empty_text_is_captured_as_manual(tmp_path, monkeypatch):
    """J's real lower-wedge line tonight is a `ray`, id UvNj5Q, anchors
    773.07 @ t=1788438600 -> 760.39 @ t=1788989400. A 2-point ray with empty (non-engine)
    text must be captured as a manual trendline -- the old title-only filter rejected
    every `ray` outright."""
    state_dir = tmp_path / "state"
    drawing = {
        "id": "UvNj5Q",
        "title": "ray",
        "point_count": 2,
        "text": "",
        "points": _pts(1788438600, 773.07, 1788989400, 760.39),
    }
    _write_chart_drawings(state_dir, [drawing])
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    lines, id_lookup, counters = ct._load_manual_drawings()

    assert len(lines) == 1, "a 2-point ray with non-engine text must be captured"
    assert counters["n_rays_captured"] == 1
    assert counters["n_dropped_engine_tag"] == 0
    assert counters["n_dropped_no_text"] == 0
    key = (1788438600, round(773.07, 4), 1788989400, round(760.39, 4))
    assert id_lookup.get(key) == "UvNj5Q"


# --------------------------------------------------------------------------------------- 3

def test_horizontal_ray_one_point_is_not_captured_as_trendline(tmp_path, monkeypatch):
    """A `horizontal ray` (1 point) is a LEVEL, not a trendline -- it must never be
    captured, regardless of text."""
    state_dir = tmp_path / "state"
    drawing = {
        "id": "hray1",
        "title": "horizontal ray",
        "point_count": 1,
        "text": "",
        "points": [{"time": 1778162400, "price": 731.47}],
    }
    _write_chart_drawings(state_dir, [drawing])
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    lines, id_lookup, counters = ct._load_manual_drawings()

    assert lines == []
    assert id_lookup == {}
    assert counters["n_rejected_title"] == 1, "horizontal ray's title alone must reject it"
    assert counters["n_rays_captured"] == 0


# --------------------------------------------------------------------------------------- 4

def test_drawing_with_no_text_key_is_dropped_and_counted(tmp_path, monkeypatch):
    """An old-schema (pre-D1/schema-v3) drawing has NO `text` key at all -- there is no
    way to prove it isn't the engine's own line, so it must be DROPPED, and
    n_dropped_no_text must be exactly 1. A silent zero here must be impossible to
    mistake for 'J drew nothing'."""
    state_dir = tmp_path / "state"
    drawing = {
        "id": "old_schema_1",
        "title": "trendline",
        "point_count": 2,
        # deliberately NO "text" key -- simulates a chart_drawings.json snapshot
        # written before D1 landed.
        "points": _pts(1000, 700.0, 5000, 701.0),
    }
    assert "text" not in drawing
    _write_chart_drawings(state_dir, [drawing])
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    lines, id_lookup, counters = ct._load_manual_drawings()

    assert lines == []
    assert id_lookup == {}
    assert counters["n_dropped_no_text"] == 1
    assert counters["n_dropped_engine_tag"] == 0, "must not be double-counted under the wrong bucket"

    # Also verify the counter surfaces all the way through compute()'s payload -- the
    # deliverable's proof that a silent zero can never masquerade as "nothing drawn".
    # A synthetic 1-day CSV stands in for backtest/data/ so this stays fully offline.
    data_dir = state_dir.parent / "data"
    _write_synthetic_csv(data_dir, dt.datetime.now(ET).date())
    monkeypatch.setattr(ct, "DATA_DIR", data_dir)
    payload = ct.compute(spot=700.5, lookback_sessions=1)
    assert payload["n_dropped_no_text"] == 1


# ------------------------------------------------------------------------------- 4b (Opus review)

def test_drawing_with_null_text_is_dropped_not_treated_as_js(tmp_path, monkeypatch):
    """`text: null` is the RUNTIME failure mode and the dangerous one.

    read_chart_drawings.js fails SOFT to null on any shape exposing neither properties()
    nor getProperties(). If null were coerced to "" (which _is_engine_tagged does, via
    `t = text or ""`), an UNREADABLE ENGINE line would be classified as J's -- silently
    reinstating the exact defect WS-D exists to fix, while every counter still reported
    health. That is worse than the original bug because it is invisible.

    J's own hand-drawn lines carry "" (empty string), never null -- all 23 rows of
    analysis/recommendations/j-drawn-lines-ledger.jsonl are text: "". So null is never J
    and always 'provenance unproven': drop it, and count it in its OWN bucket so the
    unreadable-accessor failure mode is distinguishable from the old-schema one.

    RED-PROOF: before this guard, `_is_engine_tagged(None) -> "" -> False`, so this
    drawing was ACCEPTED and returned as one of J's manual lines.
    """
    state_dir = tmp_path / "state"
    drawing = {
        "id": "unreadable_1",
        "title": "trendline",
        "point_count": 2,
        "text": None,  # JS could not read the shape's properties
        "points": _pts(1000, 700.0, 5000, 701.0),
    }
    _write_chart_drawings(state_dir, [drawing])
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    lines, id_lookup, counters = ct._load_manual_drawings()

    assert lines == [], "a null-text drawing must NEVER be trusted as one of J's lines"
    assert id_lookup == {}
    assert counters["n_dropped_null_text"] == 1
    assert counters["n_dropped_no_text"] == 0, "distinct failure modes must not share a bucket"
    assert counters["n_dropped_engine_tag"] == 0


def test_empty_string_text_is_js_line_but_null_is_not(tmp_path, monkeypatch):
    """The discriminator that makes the guard above safe: "" is kept, None is dropped.
    If these two ever collapse to the same behaviour, either J's real lines vanish or
    unreadable engine lines get adopted -- both silent."""
    state_dir = tmp_path / "state"
    _write_chart_drawings(state_dir, [
        {"id": "js_line", "title": "trendline", "point_count": 2, "text": "",
         "points": _pts(1000, 700.0, 200000, 705.0)},
        {"id": "unreadable", "title": "trendline", "point_count": 2, "text": None,
         "points": _pts(1000, 710.0, 200000, 715.0)},
    ])
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    lines, id_lookup, counters = ct._load_manual_drawings()

    assert len(lines) == 1, "exactly the empty-string line survives"
    assert set(id_lookup.values()) == {"js_line"}
    assert counters["n_dropped_null_text"] == 1

# --------------------------------------------------------------------------------------- 5

class _FakeChart:
    """Minimal stand-in for tv_cdp.TvChart -- list_shapes()/shape_text()/evaluate() only,
    matching the shape backtest/tests/test_j_drawn_lines_2026_09_03.py's own _FakeChart
    already establishes for this module."""

    def __init__(self, shapes: dict[str, dict]):
        self._shapes = shapes

    def list_shapes(self) -> list[dict]:
        return [{"id": eid, "name": s["name"]} for eid, s in self._shapes.items()]

    def shape_text(self, entity_id: str) -> str | None:
        s = self._shapes.get(entity_id)
        return s.get("text") if s else None

    def evaluate(self, expr: str):
        # Only getPoints() calls are issued for a "ray" shape by _non_engine_trend_lines.
        for eid, s in self._shapes.items():
            if eid in expr and "getPoints" in expr:
                return s.get("points")
        raise AssertionError(f"unexpected evaluate() call in test: {expr[:200]}")


def test_non_engine_trend_lines_returns_ray_and_excludes_gtl_tagged_line():
    shapes = {
        "ray1": {"name": "ray", "text": "",
                 "points": [{"time": 1788438600, "price": 773.07}, {"time": 1788989400, "price": 760.39}]},
        "eng1": {"name": "trend_line", "text": "[GTL] [WICK] SUPPORT touch x3",
                 "points": [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]},
        "human1": {"name": "trend_line", "text": "",
                   "points": [{"time": 100, "price": 1.0}, {"time": 200, "price": 2.0}]},
    }
    chart = _FakeChart(shapes)

    out = cap._non_engine_trend_lines(chart)
    ids = {s["id"] for s in out}

    assert "ray1" in ids, "a ray shape must be returned by _non_engine_trend_lines"
    assert "eng1" not in ids, "a [GTL]-texted trend_line must still be excluded"
    assert "human1" in ids


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
