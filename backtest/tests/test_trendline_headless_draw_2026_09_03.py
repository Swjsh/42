"""Guards for setup/scripts/trendline_headless_draw.py (TRENDLINE-DRAW-HEADLESS, 2026-09-03).

WHAT THIS CLOSES: `trendline-draw-state.json` last_run 2026-08-27 status=skipped
reason='budget conservation' -- premarket Step 5c (LLM-discretionary) chose not to run a
$0 deterministic job. `trendline_chart_draw.py` already computed what to draw but its own
header claimed drawing "cannot run from a headless scheduled task", a constraint
`Gamma_ChartAutoDraw` (2026-08-06) had already disproved. This module is the headless
runner: compute via `trendline_chart_draw.compute_draw_payload` (imported), draw via
`tv_cdp.TvChart` -- verified LIVE this session against the real TradingView chart (create
-> readback -> remove, then a full production run: drew 2 real lines, left the chart's 22
OTHER pre-existing trend_line shapes untouched, redrew idempotently on a second run).

Covers, offline (no live CDP dependency -- must pass with TradingView Desktop closed):
  1. Fail-open: CDP down -> status=SKIPPED_TV_DOWN, exit 0, prior `drawn` bookkeeping
     preserved untouched (never invented, never dropped).
  2. --dry-run computes + logs but NEVER constructs TvChart and NEVER writes a stamp.
  3. Stamp schema: every key a consumer (self_check) or a human reading the file by hand
     needs is present on a real successful run.
  4. SAFETY (the load-bearing half, mirrors test_draw_key_levels_2026_08_06.py's own
     priority): `remove_own_lines` only ever targets `trend_line`-named shapes that are
     EITHER recorded in our own state OR TAG-prefixed -- a `horizontal_line` (even one
     with matching text) and an untagged/unrecorded `trend_line` (J's own manual line)
     must both survive untouched.
  5. Idempotency: a second run with the first run's `drawn` list as prior state removes
     exactly those entities and none of a chart's other pre-existing trend lines.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "setup" / "scripts"),
           str(REPO / "backtest" / "autoresearch")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto.lib.bar import Bar  # noqa: E402

import trendline_headless_draw as thd  # noqa: E402
import tv_cdp  # noqa: E402


# --------------------------------------------------------------------------- fixtures/helpers

def _bar(i: int, low: float, high: float, close: float | None = None) -> Bar:
    c = close if close is not None else (low + high) / 2
    return Bar(
        open_time=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5 * i),
        open=c, high=high, low=low, close=c, volume=1000.0,
        granularity_seconds=300, source="test",
    )


def _synthetic_bars(n: int = 40, pivots=(2, 10, 18)) -> tuple[Bar, ...]:
    """A clean ascending-support structure -- enough for compute_draw_payload to find at
    least one real, non-empty line (mirrors test_trendline_chart_draw.py's own fixture
    shape; kept local and minimal rather than importing that test module)."""
    base, slope = 500.0, 0.05
    bars = []
    for i in range(n):
        lv = base + slope * i
        if i in pivots:
            bars.append(_bar(i, low=lv, high=lv + 1.5))
        else:
            bars.append(_bar(i, low=lv + 0.5, high=lv + 2.0))
    return tuple(bars)


class _FakeChart:
    """Stands in for tv_cdp.TvChart -- an in-memory shape store so remove/create/list/text
    behave like the real CDP client without touching a live TradingView session."""

    def __init__(self, shapes: list[dict] | None = None):
        # shapes: [{"id":..., "name":..., "text":...}, ...]
        self._shapes = {s["id"]: dict(s) for s in (shapes or [])}
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
        return "BATS:SPY"

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

    def create_trend_line(self, point, point2, text, overrides=None) -> str:
        self._next += 1
        eid = f"fake{self._next}"
        self._shapes[eid] = {"id": eid, "name": "trend_line", "text": text}
        self.created.append({"entity_id": eid, "point": point, "point2": point2, "text": text})
        return eid


def _down_factory():
    """Stands in for tv_cdp.TvChart when TradingView/CDP is unreachable -- raises exactly
    what the real client raises at construction time (TvChart.__init__ eagerly calls
    find_chart_target())."""
    raise tv_cdp.TvCdpError("fake: CDP not reachable on 127.0.0.1:9222 -- TradingView Desktop not running?")


def _never_call_factory():
    """A TvChart stand-in that fails the test if it is ever constructed -- used to prove
    --dry-run never touches CDP at all."""
    def _boom(*a, **kw):
        raise AssertionError("TvChart must never be constructed on a --dry-run invocation")
    return _boom


# --------------------------------------------------------------------------- 1. fail-open

def test_fail_open_on_cdp_down_writes_skipped_tv_down_and_exits_0(tmp_path, monkeypatch):
    stamp = tmp_path / "trendline-headless-draw.json"
    prior = {"schema_version": 1, "drawn": [{"entity_id": "old1", "line_id": "TL-old"}]}
    stamp.write_text(json.dumps(prior), encoding="utf-8")

    monkeypatch.setattr(thd, "STATE_FILE", stamp)
    monkeypatch.setattr(thd, "fetch_bars", lambda n_days=3: _synthetic_bars())
    monkeypatch.setattr(thd, "TvChart", _down_factory)

    rc = thd.main([])
    assert rc == 0, "TradingView down is the normal off-hours state -- must exit 0, never raise into the scheduler"

    out = json.loads(stamp.read_text(encoding="utf-8"))
    assert out["status"] == "SKIPPED_TV_DOWN"
    assert out["n_drawn"] == 0
    assert out["drawn"] == prior["drawn"], "prior bookkeeping must be preserved untouched on a TV-down skip"


def test_unexpected_exception_never_raises_uncaught(tmp_path, monkeypatch):
    """A genuine bug inside the CDP session (not TV-down) must still never propagate an
    unhandled exception into the scheduler -- it is caught, stamped ERROR, and returns 1."""
    stamp = tmp_path / "trendline-headless-draw.json"
    monkeypatch.setattr(thd, "STATE_FILE", stamp)
    monkeypatch.setattr(thd, "fetch_bars", lambda n_days=3: _synthetic_bars())

    class _BoomChart(_FakeChart):
        def require_chart_api(self):
            raise RuntimeError("boom: unexpected chart-api failure")

    monkeypatch.setattr(thd, "TvChart", lambda: _BoomChart())

    rc = thd.main([])  # must not raise
    assert rc == 1
    out = json.loads(stamp.read_text(encoding="utf-8"))
    assert out["status"] == "ERROR"
    assert "boom" in out["reason"]


# --------------------------------------------------------------------------- 2. dry-run

def test_dry_run_never_constructs_tvchart_and_writes_no_stamp(tmp_path, monkeypatch):
    stamp = tmp_path / "trendline-headless-draw.json"
    monkeypatch.setattr(thd, "STATE_FILE", stamp)
    monkeypatch.setattr(thd, "fetch_bars", lambda n_days=3: _synthetic_bars())
    monkeypatch.setattr(thd, "TvChart", _never_call_factory())

    rc = thd.main(["--dry-run"])
    assert rc == 0
    assert not stamp.exists(), "--dry-run must compute + log only, never write the stamp"


def test_dry_run_computes_a_real_nonempty_payload(tmp_path, monkeypatch, capsys):
    stamp = tmp_path / "trendline-headless-draw.json"
    monkeypatch.setattr(thd, "STATE_FILE", stamp)
    monkeypatch.setattr(thd, "fetch_bars", lambda n_days=3: _synthetic_bars())
    monkeypatch.setattr(thd, "TvChart", _never_call_factory())

    rc = thd.main(["--dry-run"])
    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "DRY_RUN"
    assert printed["n_drawn"] >= 1, "the synthetic ascending-support fixture must yield at least one real line"


# --------------------------------------------------------------------------- 3. stamp schema

def test_successful_run_stamp_has_full_schema(tmp_path, monkeypatch):
    stamp = tmp_path / "trendline-headless-draw.json"
    monkeypatch.setattr(thd, "STATE_FILE", stamp)
    monkeypatch.setattr(thd, "fetch_bars", lambda n_days=3: _synthetic_bars())
    monkeypatch.setattr(thd, "TvChart", lambda: _FakeChart())

    rc = thd.main([])
    assert rc == 0
    out = json.loads(stamp.read_text(encoding="utf-8"))
    for key in ("schema_version", "as_of", "tag", "dry_run", "symbol", "timeframe",
                "status", "n_drawn", "drawn", "removed", "chart_symbol", "n_candidates", "errors"):
        assert key in out, f"stamp missing required key: {key}"
    assert out["status"] == "OK"
    assert out["n_drawn"] >= 1
    assert len(out["drawn"]) == out["n_drawn"]
    for d in out["drawn"]:
        for key in ("entity_id", "line_id", "kind", "anchor_mode"):
            assert key in d


# --------------------------------------------------------------------------- 4. safety (load-bearing)

def test_remove_own_lines_never_touches_a_horizontal_line_even_if_tagged():
    """A key-level horizontal_line drawn by draw_key_levels.py must be structurally
    unreachable, even in the adversarial case where its text happens to start with OUR
    tag (should never happen in practice -- draw_key_levels.py uses a different tag -- but
    this pins the safety boundary is the shape filter, not just the text prefix)."""
    chart = _FakeChart(shapes=[
        {"id": "hl1", "name": "horizontal_line", "text": f"{thd.TAG}IMPOSTOR KEY LEVEL"},
        {"id": "tl1", "name": "trend_line", "text": f"{thd.TAG}real orphan"},
    ])
    state = {"drawn": []}
    removed = thd.remove_own_lines(chart, state, dry_run=False)
    removed_ids = {r["entity_id"] for r in removed}
    assert removed_ids == {"tl1"}
    assert "hl1" in chart._shapes, "a horizontal_line must NEVER be removed by this function, tag or no tag"


def test_remove_own_lines_leaves_untagged_unrecorded_trend_line_alone():
    """J's own manually-drawn trend line: a trend_line shape that is neither recorded in
    our state nor TAG-prefixed must survive -- this is the 'never delete J's own work'
    guarantee for the trend_line surface."""
    chart = _FakeChart(shapes=[
        {"id": "manual1", "name": "trend_line", "text": "J's hand-drawn channel line"},
        {"id": "ours1", "name": "trend_line", "text": f"{thd.TAG}[WICK] SUPPORT"},
    ])
    state = {"drawn": [{"entity_id": "ours1"}]}
    removed = thd.remove_own_lines(chart, state, dry_run=False)
    removed_ids = {r["entity_id"] for r in removed}
    assert removed_ids == {"ours1"}
    assert "manual1" in chart._shapes, "J's untagged, unrecorded trend line must never be removed"


def test_remove_own_lines_recovers_tagged_orphan_when_state_is_lost():
    """If the stamp file is lost/corrupt (state = {"drawn": []}), a previously-drawn TAG-
    prefixed line must still be found and cleaned via the text-prefix recovery path."""
    chart = _FakeChart(shapes=[
        {"id": "orphan1", "name": "trend_line", "text": f"{thd.TAG}[WICK] RESISTANCE | orphaned"},
    ])
    state = {"drawn": []}  # state lost
    removed = thd.remove_own_lines(chart, state, dry_run=False)
    assert {r["entity_id"] for r in removed} == {"orphan1"}
    assert removed[0]["why"] == "tagged_orphan"


# --------------------------------------------------------------------------- 5. idempotency

def test_second_run_removes_exactly_first_runs_lines_and_nothing_else():
    """End-to-end: run 1 draws N lines onto a chart that already has OTHER (untagged)
    trend lines; run 2, seeded with run 1's own `drawn` state, must remove exactly those
    N entities and leave every other shape (including the newly-created ones from run 1
    that get redrawn) alone -- mirrors the real idempotency verified live this session
    (removed=1 drawn=2, then removed=2 drawn=2 on a real chart with 22 untouched others)."""
    other_shapes = [{"id": f"other{i}", "name": "trend_line", "text": ""} for i in range(5)]
    chart = _FakeChart(shapes=list(other_shapes))

    payload = thd.tcd.compute_draw_payload(_synthetic_bars(), symbol="SPY", timeframe="5m")
    lines = payload["lines"]
    assert lines, "fixture must yield at least one real line to draw"

    drawn1 = thd.draw_lines(chart, lines, dry_run=False)
    state_after_run1 = {"drawn": drawn1}
    assert len(chart._shapes) == len(other_shapes) + len(drawn1)

    removed = thd.remove_own_lines(chart, state_after_run1, dry_run=False)
    assert {r["entity_id"] for r in removed} == {d["entity_id"] for d in drawn1}
    for other in other_shapes:
        assert other["id"] in chart._shapes, "an unrelated pre-existing trend_line must survive a redraw cycle"
