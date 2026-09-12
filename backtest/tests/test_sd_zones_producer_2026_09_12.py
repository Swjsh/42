"""Guards for setup/scripts/sd_zones_producer.py (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item b).

WHAT THIS CLOSES: item (a) proved `data_get_pine_boxes(study_filter="Smart Money")` reads
the LuxAlgo Smart Money Concepts order-block boxes headlessly over CDP. This module turns
those boxes into a scored SHADOW file (`automation/state/sd-zones.json`) reusing the
ALREADY-RATIFIED `_uniform_touches`/`_zone_width` math from `refresh_levels_intraday.py`
by import -- zero edits to that frozen file.

Covers, offline (no live CDP dependency -- must pass with TradingView Desktop closed):
  1. Fail-open: CDP down -> status=SKIPPED_TV_DOWN, exit 0, PRIOR zones/drawn preserved
     (never wiped to empty on a TV-down tick -- distinct from a "no data yet" run).
  2. --dry-run computes + logs but NEVER constructs TvChart and NEVER writes a stamp.
  3. Classification: a box zone's kind (supply/demand) follows its position relative to
     spot, and touches_uniform reuses `_uniform_touches` unchanged -- proven by a synthetic
     bar grid with a KNOWN respect count on each side.
  4. SAFETY (mirrors test_trendline_headless_draw_2026_09_03.py's own priority):
     `remove_own_drawings` only ever targets `rectangle`-named shapes that are EITHER
     recorded in our own state OR TAG-prefixed -- a `horizontal_line`/`trend_line` (even
     tagged) and an untagged/unrecorded `rectangle` (J's own manual box) must both survive.
  5. Idempotency: a second run with the first run's `drawn` list as prior state removes
     exactly those entities and none of a chart's other pre-existing rectangles.
  6. Never touches key-levels.json / heartbeat_core -- this module writes ONLY sd-zones.json.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sd_zones_producer as szp  # noqa: E402
import tv_cdp  # noqa: E402


# --------------------------------------------------------------------------- fixtures/helpers

def _grid(date: str, touches_r=(), touches_s=(), r_price: float = 752.0, s_price: float = 748.0):
    """One session of 5m bars: filler chop closing 750.0 (inside every nearby zone), with
    crafted rejections of r_price (close back BELOW) and bounces off s_price (close back
    ABOVE) at the given HH:MM times. Mirrors test_refresh_levels_intraday.py's own `_grid`
    fixture shape (kept local rather than imported, per that test module's own convention)."""
    rows = []
    for hm in ("08:00", "08:30", "09:00"):
        rows.append({"date": date, "hm": hm, "high": 750.3, "low": 749.7, "close": 750.0})
    t = dt.datetime(2026, 1, 1, 9, 30)
    while t <= dt.datetime(2026, 1, 1, 15, 55):
        hm = t.strftime("%H:%M")
        row = {"date": date, "hm": hm, "high": 750.2, "low": 749.8, "close": 750.0}
        if hm in touches_r:
            row.update(high=r_price + 0.1, low=751.2, close=r_price - 0.4)
        elif hm in touches_s:
            row.update(low=s_price - 0.1, high=748.8, close=s_price + 0.4)
        rows.append(row)
        t += dt.timedelta(minutes=5)
    return rows


def _bars_df() -> pd.DataFrame:
    rows = _grid("2026-09-11", touches_r=("10:00", "11:00", "13:00"), touches_s=("10:30", "14:00"))
    return pd.DataFrame(rows)


class _FakeChart:
    """Stands in for tv_cdp.TvChart -- in-memory shape store + a fixed pine-box payload."""

    def __init__(self, shapes: list[dict] | None = None, boxes: list[dict] | None = None,
                 spot: float = 750.0, symbol_: str = "BATS:SPY"):
        self._shapes = {s["id"]: dict(s) for s in (shapes or [])}
        self._boxes = boxes if boxes is not None else []
        self._spot = spot
        self._symbol = symbol_
        self._next = 0
        self.removed_ids: list[str] = []
        self.created: list[dict] = []

    def __enter__(self) -> "_FakeChart":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def require_chart_api(self) -> None:
        return None

    def symbol(self) -> str:
        return self._symbol

    def last_price(self) -> float | None:
        return self._spot

    def pine_boxes(self, study_filter: str = "") -> list[dict]:
        return [{"name": "Smart Money Concepts [LuxAlgo]", "total_boxes": len(self._boxes),
                 "zones": list(self._boxes)}] if self._boxes else []

    def list_shapes(self) -> list[dict]:
        return [{"id": sid, "name": s["name"]} for sid, s in self._shapes.items()]

    def shape_text(self, entity_id: str) -> str | None:
        s = self._shapes.get(entity_id)
        return s.get("text") if s else None

    def remove_entity(self, entity_id: str) -> bool:
        if entity_id in self._shapes:
            del self._shapes[entity_id]
            self.removed_ids.append(entity_id)
            return True
        return False

    def create_rectangle(self, point, point2, text, overrides=None) -> str:
        self._next += 1
        eid = f"fake{self._next}"
        self._shapes[eid] = {"id": eid, "name": "rectangle", "text": text}
        self.created.append({"entity_id": eid, "point": point, "point2": point2, "text": text})
        return eid


def _down_factory():
    """Raises exactly what the real client raises at construction (TvChart.__init__
    eagerly calls find_chart_target())."""
    raise tv_cdp.TvCdpError("fake: CDP not reachable on 127.0.0.1:9222 -- TradingView Desktop not running?")


def _never_call_factory():
    def _boom(*a, **kw):
        raise AssertionError("TvChart must never be constructed on a --dry-run invocation")
    return _boom


# --------------------------------------------------------------------------- 1. fail-open

def test_fail_open_on_cdp_down_preserves_prior_zones_and_exits_0(tmp_path, monkeypatch):
    stamp = tmp_path / "sd-zones.json"
    prior = {"schema_version": 1, "zones": [{"low": 1.0, "high": 2.0, "mid": 1.5,
             "kind": "demand", "touches_uniform": 4, "source_study": "x"}],
             "drawn": [{"entity_id": "old1"}]}
    stamp.write_text(json.dumps(prior), encoding="utf-8")

    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    monkeypatch.setattr(szp, "TvChart", _down_factory)

    rc = szp.main([])
    assert rc == 0, "TradingView down is the normal off-hours state -- must exit 0"

    out = json.loads(stamp.read_text(encoding="utf-8"))
    assert out["status"] == "SKIPPED_TV_DOWN"
    assert out["zones"] == prior["zones"], "prior zones must be preserved untouched, never wiped to empty"
    assert out["drawn"] == prior["drawn"]


def test_unexpected_exception_never_raises_uncaught(tmp_path, monkeypatch):
    stamp = tmp_path / "sd-zones.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())

    real_status_md = REPO / "automation" / "overnight" / "STATUS.md"
    real_before = real_status_md.read_text(encoding="utf-8") if real_status_md.exists() else None

    class _BoomChart(_FakeChart):
        def require_chart_api(self):
            raise RuntimeError("boom: unexpected chart-api failure")

    monkeypatch.setattr(szp, "TvChart", lambda: _BoomChart())

    rc = szp.main([])  # must not raise
    assert rc == 1
    out = json.loads(stamp.read_text(encoding="utf-8"))
    assert out["status"] == "ERROR"
    assert "boom" in out["reason"]

    fake_status_md = szp.STATUS_MD
    assert fake_status_md.exists()
    assert "boom" in fake_status_md.read_text(encoding="utf-8")
    real_after = real_status_md.read_text(encoding="utf-8") if real_status_md.exists() else None
    assert real_after == real_before, "the REAL production STATUS.md must be byte-identical before/after"


def test_bar_fetch_failure_never_raises_uncaught(tmp_path, monkeypatch):
    stamp = tmp_path / "sd-zones.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "STATUS_MD", tmp_path / "STATUS.md")

    def _boom_bars():
        raise RuntimeError("REST 500")

    monkeypatch.setattr(szp, "_spy_bars", _boom_bars)
    monkeypatch.setattr(szp, "TvChart", _never_call_factory())

    rc = szp.main([])
    assert rc == 1
    out = json.loads(stamp.read_text(encoding="utf-8"))
    assert out["status"] == "ERROR"
    assert "REST 500" in out["reason"]


# --------------------------------------------------------------------------- 2. dry-run

def test_dry_run_reads_the_chart_but_writes_no_stamp_and_draws_nothing(tmp_path, monkeypatch):
    """Unlike trendline_headless_draw's dry-run (whose compute step is pure REST bars, no
    CDP), this producer's "compute" IS a live pine-box read -- there is no offline
    equivalent, so --dry-run legitimately still opens TvChart to READ. What --dry-run
    guarantees is no FILE write and no chart MUTATION (no draw/remove), never that CDP is
    untouched."""
    stamp = tmp_path / "sd-zones.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "STATUS_MD", tmp_path / "STATUS.md")   # 00:22 ET 2026-09-12: an earlier cut leaked into the real STATUS.md
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    boxes = [{"low": 751.8, "high": 752.2}]
    chart = _FakeChart(boxes=boxes, spot=750.0)
    monkeypatch.setattr(szp, "TvChart", lambda: chart)

    rc = szp.main(["--dry-run"])
    assert rc == 0
    assert not stamp.exists(), "--dry-run must never write the stamp"
    assert chart.created == [], "--dry-run must never draw, even if a real zone was computed"


# --------------------------------------------------------------------------- 3. classification

def test_classify_zones_kind_and_touches_match_position_and_respect_count():
    df = _bars_df()
    spot = 750.0
    # resistance box centred on 752.0 (3 respects in the grid); demand box on 748.0 (2 respects)
    raw = [{"low": 751.8, "high": 752.2}, {"low": 747.8, "high": 748.2}]
    zones = szp.classify_zones(raw, spot, df)
    by_mid = {round(z["mid"]): z for z in zones}
    assert by_mid[752]["kind"] == "supply"
    assert by_mid[752]["touches_uniform"] == 3
    assert by_mid[748]["kind"] == "demand"
    assert by_mid[748]["touches_uniform"] == 2


def test_classify_zones_zero_height_box_falls_back_to_default_zone_width():
    df = _bars_df()
    zones = szp.classify_zones([{"low": 755.0, "high": 755.0}], 750.0, df)
    assert len(zones) == 1
    assert zones[0]["high"] > zones[0]["low"], "a degenerate zero-height box must get a non-zero fallback width"


def test_end_to_end_run_with_fake_chart_writes_full_schema(tmp_path, monkeypatch):
    stamp = tmp_path / "sd-zones.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    boxes = [{"low": 751.8, "high": 752.2}, {"low": 747.8, "high": 748.2}]
    monkeypatch.setattr(szp, "TvChart", lambda: _FakeChart(boxes=boxes, spot=750.0))

    rc = szp.main([])
    assert rc == 0
    out = json.loads(stamp.read_text(encoding="utf-8"))
    for key in ("schema_version", "as_of", "study_filter", "status", "spot",
                "chart_symbol", "zones", "drawn"):
        assert key in out, f"stamp missing required key: {key}"
    assert out["status"] == "OK"
    assert len(out["zones"]) == 2
    for z in out["zones"]:
        for key in ("low", "high", "mid", "kind", "touches_uniform", "source_study"):
            assert key in z
    assert out["drawn"] == [], "no --draw flag was passed, drawn must stay empty/carried-forward"


# --------------------------------------------------------------------------- 4. safety (load-bearing)

def test_remove_own_drawings_never_touches_a_horizontal_line_even_if_tagged():
    chart = _FakeChart(shapes=[
        {"id": "hl1", "name": "horizontal_line", "text": f"{szp.TAG}IMPOSTOR KEY LEVEL"},
        {"id": "rec1", "name": "rectangle", "text": f"{szp.TAG}real orphan"},
    ])
    state = {"drawn": []}
    removed = szp.remove_own_drawings(chart, state, dry_run=False)
    removed_ids = {r["entity_id"] for r in removed}
    assert removed_ids == {"rec1"}
    assert "hl1" in chart._shapes, "a horizontal_line must NEVER be removed by this function, tag or no tag"


def test_remove_own_drawings_leaves_untagged_unrecorded_rectangle_alone():
    """J's own manually-drawn rectangle must survive untouched."""
    chart = _FakeChart(shapes=[
        {"id": "manual1", "name": "rectangle", "text": "J's hand-drawn box"},
        {"id": "ours1", "name": "rectangle", "text": f"{szp.TAG}supply 9t"},
    ])
    state = {"drawn": [{"entity_id": "ours1"}]}
    removed = szp.remove_own_drawings(chart, state, dry_run=False)
    removed_ids = {r["entity_id"] for r in removed}
    assert removed_ids == {"ours1"}
    assert "manual1" in chart._shapes, "J's untagged, unrecorded rectangle must never be removed"


def test_remove_own_drawings_recovers_tagged_orphan_when_state_is_lost():
    chart = _FakeChart(shapes=[
        {"id": "orphan1", "name": "rectangle", "text": f"{szp.TAG}demand 5t | orphaned"},
    ])
    state = {"drawn": []}  # state lost
    removed = szp.remove_own_drawings(chart, state, dry_run=False)
    assert {r["entity_id"] for r in removed} == {"orphan1"}
    assert removed[0]["why"] == "tagged_orphan"


# --------------------------------------------------------------------------- 5. idempotency

def test_second_run_removes_exactly_first_runs_rectangles_and_nothing_else():
    other_shapes = [{"id": f"other{i}", "name": "rectangle", "text": ""} for i in range(3)]
    chart = _FakeChart(shapes=list(other_shapes))
    zones = szp.classify_zones([{"low": 751.8, "high": 752.2}], 750.0, _bars_df())
    assert zones

    drawn1 = szp.draw_zones(chart, zones, dry_run=False)
    state_after_run1 = {"drawn": drawn1}
    assert len(chart._shapes) == len(other_shapes) + len(drawn1)

    removed = szp.remove_own_drawings(chart, state_after_run1, dry_run=False)
    assert {r["entity_id"] for r in removed} == {d["entity_id"] for d in drawn1}
    for other in other_shapes:
        assert other["id"] in chart._shapes, "pre-existing OTHER rectangles must survive untouched"


# --------------------------------------------------------------------------- 6. scope discipline

def test_module_never_imports_heartbeat_core_or_writes_key_levels():
    src = (REPO / "setup" / "scripts" / "sd_zones_producer.py").read_text(encoding="utf-8")
    assert "import heartbeat_core" not in src and "from heartbeat_core" not in src
    assert "KEY_LEVELS" not in src, "no key-levels.json path constant -- this module must not be able to write it"
    assert szp.STATE_FILE.name == "sd-zones.json", "the producer must write ONLY the shadow file, never key-levels.json"


def test_trading_path_never_references_the_shadow_file():
    """Consumer-side pin of the SHADOW contract (the module-side pin above covers the producer's
    own imports/writes): the engine and the fleet signal builder never mention sd-zones.json.
    Promotion happens through a pre-registered checkpoint row, never through a quiet read."""
    core = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    fleet = (REPO / "automation" / "state" / "fleet" / "build_shared_signal.py").read_text(encoding="utf-8")
    for text, name in ((core, "heartbeat_core.py"), (fleet, "build_shared_signal.py")):
        assert "sd-zones" not in text and "sd_zones" not in text, f"{name} references the shadow file"


# --------------------------------------------------------------------------- 7. forward-clock accrual (item d)

def test_end_to_end_ok_run_archives_a_daily_snapshot_and_advances_the_clock(tmp_path, monkeypatch):
    stamp = tmp_path / "sd-zones.json"
    archive_dir = tmp_path / "archive"
    clock_file = tmp_path / "clock.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(szp, "FORWARD_CLOCK_FILE", clock_file)
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    monkeypatch.setattr(szp, "et_now", lambda: dt.datetime(2026, 9, 14, 9, 0))
    boxes = [{"low": 751.8, "high": 752.2}]
    monkeypatch.setattr(szp, "TvChart", lambda: _FakeChart(boxes=boxes, spot=750.0))

    rc = szp.main([])
    assert rc == 0

    archived = archive_dir / "2026-09-14.json"
    assert archived.exists(), "a real OK capture must write a same-day archive snapshot"
    snap = json.loads(archived.read_text(encoding="utf-8"))
    assert snap["date"] == "2026-09-14"
    assert len(snap["zones"]) == 1

    clock = json.loads(clock_file.read_text(encoding="utf-8"))
    assert clock["archived_dates"] == ["2026-09-14"]
    assert clock["sessions_accrued"] == 1
    assert clock["eligible_for_forward_read"] is False


def test_dry_run_never_archives_or_advances_the_clock(tmp_path, monkeypatch):
    stamp = tmp_path / "sd-zones.json"
    archive_dir = tmp_path / "archive"
    clock_file = tmp_path / "clock.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(szp, "FORWARD_CLOCK_FILE", clock_file)
    monkeypatch.setattr(szp, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    boxes = [{"low": 751.8, "high": 752.2}]
    monkeypatch.setattr(szp, "TvChart", lambda: _FakeChart(boxes=boxes, spot=750.0))

    rc = szp.main(["--dry-run"])
    assert rc == 0
    assert not archive_dir.exists(), "--dry-run must never create an archive snapshot"
    assert not clock_file.exists(), "--dry-run must never advance the forward clock"


def test_tv_down_skip_never_archives_or_advances_the_clock(tmp_path, monkeypatch):
    """A SKIPPED_TV_DOWN tick carries forward YESTERDAY's zones -- counting it as a new
    'session accrued' would silently inflate the forward-read eligibility clock with days
    TV never actually answered."""
    stamp = tmp_path / "sd-zones.json"
    archive_dir = tmp_path / "archive"
    clock_file = tmp_path / "clock.json"
    stamp.write_text(json.dumps({"schema_version": 1, "zones": [], "drawn": []}), encoding="utf-8")
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(szp, "FORWARD_CLOCK_FILE", clock_file)
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    monkeypatch.setattr(szp, "TvChart", _down_factory)

    rc = szp.main([])
    assert rc == 0
    assert not archive_dir.exists(), "a TV-down skip must never archive a snapshot"
    assert not clock_file.exists(), "a TV-down skip must never advance the forward clock"


def test_forward_clock_is_idempotent_across_same_day_reruns(tmp_path, monkeypatch):
    clock_file = tmp_path / "clock.json"
    monkeypatch.setattr(szp, "FORWARD_CLOCK_FILE", clock_file)
    c1 = szp.update_forward_clock("2026-09-14")
    c2 = szp.update_forward_clock("2026-09-14")
    assert c1 == c2
    assert c2["sessions_accrued"] == 1

    c3 = szp.update_forward_clock("2026-09-15")
    assert c3["sessions_accrued"] == 2
    assert c3["archived_dates"] == ["2026-09-14", "2026-09-15"]
    assert c3["first_archived_date"] == "2026-09-14"


def test_forward_clock_becomes_eligible_at_ten_accrued_sessions(tmp_path, monkeypatch):
    clock_file = tmp_path / "clock.json"
    monkeypatch.setattr(szp, "FORWARD_CLOCK_FILE", clock_file)
    days = [f"2026-{9 if d <= 30 else 10:02d}-{d if d <= 30 else d - 30:02d}" for d in range(14, 24)]
    clock = None
    for day in days:
        clock = szp.update_forward_clock(day)
    assert clock["sessions_accrued"] == 10
    assert clock["eligible_for_forward_read"] is True


# --------------------------------------------------------------------------- input trim (2026-09-12)

class _EvalChart(_FakeChart):
    """A fake chart that also answers `evaluate` the way the live page API does for the trim JS."""

    def __init__(self, *a, before: dict | None = None, **k):
        super().__init__(*a, **k)
        self.evaluated: list[str] = []
        self._before = before or {"in_3": True, "in_21": False}     # TradingView defaults after a relaunch

    def evaluate(self, js: str):
        self.evaluated.append(js)
        need = [k for k, v in szp.SD_STUDY_INPUTS.items() if self._before.get(k) != v]
        return [{"id": "foIsMP", "name": "Smart Money Concepts [LuxAlgo]", "changed": len(need),
                 "before": list(self._before.items()), "after": list(szp.SD_STUDY_INPUTS.items())}]


def test_producer_enforces_the_study_input_trim_before_reading_boxes(tmp_path, monkeypatch):
    """Verified 2026-09-12 01:28 ET: the trim set via page API + Ctrl+S did NOT survive a cold TV
    relaunch (defaults came back, 10 boxes -> 5). The producer therefore sets in_3=false /
    in_21=true itself on every fire and records what it did."""
    stamp = tmp_path / "sd-zones.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    monkeypatch.setattr(szp, "STUDY_RECOMPUTE_WAIT_S", 0)
    chart = _EvalChart(boxes=[{"low": 751.8, "high": 752.2}], spot=750.0)
    monkeypatch.setattr(szp, "TvChart", lambda: chart)
    assert szp.main([]) == 0
    enf = json.loads(stamp.read_text(encoding="utf-8"))["inputs_enforced"]
    assert enf["status"] == "ok" and enf["changed"] == 2
    assert enf["wanted"] == {"in_3": False, "in_21": True}
    assert len(chart.evaluated) == 1 and "setInputValues" in chart.evaluated[0]


def test_producer_input_enforcement_is_fail_open(tmp_path, monkeypatch):
    """A chart client without `evaluate` (or a JS failure) must not cost the fire its box read."""
    stamp = tmp_path / "sd-zones.json"
    monkeypatch.setattr(szp, "STATE_FILE", stamp)
    monkeypatch.setattr(szp, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(szp, "_spy_bars", lambda: _bars_df())
    chart = _FakeChart(boxes=[{"low": 751.8, "high": 752.2}], spot=750.0)      # no evaluate at all
    monkeypatch.setattr(szp, "TvChart", lambda: chart)
    assert szp.main([]) == 0
    doc = json.loads(stamp.read_text(encoding="utf-8"))
    assert doc["inputs_enforced"]["status"] == "unavailable" and len(doc["zones"]) == 1

