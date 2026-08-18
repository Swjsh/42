"""Guards for backtest/autoresearch/trendline_manual.py (2026-08-18) -- the intraday manual-
trendline refresh J asked for: "the engine reads his hand-drawn TradingView trendlines ONLY at
premarket, so anything he draws during the session is never seen... I wanna do this on a higher
time frame, though, so we don't have a bunch of small individual trend lines."

Covers exactly the four behaviors this feature exists to guarantee:
  (a) a fresh manual line (drawn today) SURVIVES the age filter
  (b) a 62-day-old line is still DROPPED, with its reason (and age) recorded
  (c) the higher-timeframe significance filter excludes a short/low-touch scribble and keeps
      a long, multi-touch line
  (d) the producer fails OPEN when TV/CDP is down -- writes nothing, leaves prior state, never
      raises, never blocks

All pure/offline: a synthetic bars CSV + a fake CDP chart object stand in for TradingView
Desktop. No live CDP dependency -- these must pass with TradingView Desktop closed.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytz

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backtest" / "autoresearch"))

import trendline_manual as tm  # noqa: E402

ct = tm.compute_trendlines   # the exact module object trendline_manual.py itself calls into
tv_cdp = tm.tv_cdp            # the exact CDP client module trendline_manual.py itself calls into

ET = pytz.timezone("America/New_York")


# --------------------------------------------------------------------------- fixtures/helpers

def _write_synthetic_csv(data_dir: Path, base_date: dt.date, n_bars: int = 25) -> dt.datetime:
    """25 RTH 5-min bars starting 09:30 ET on `base_date`, drifting gently from $700.00 so a
    trendline fit through the first and last bar tracks every intermediate bar closely (a real
    'respected' line), with no reliance on real market data. Returns the first bar's start time.
    """
    lines = ["timestamp_et,open,high,low,close,volume"]
    start = ET.localize(dt.datetime.combine(base_date, dt.time(9, 30)))
    for i in range(n_bars):
        ts = start + dt.timedelta(minutes=5 * i)
        px = 700.00 + 0.02 * i
        lines.append(f"{ts.isoformat()},{px:.2f},{px + 0.05:.2f},{px - 0.05:.2f},{px:.2f},100000")
    path = data_dir / f"spy_5m_{base_date.isoformat()}_{base_date.isoformat()}.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return start


def _drawing(drawing_id: str, t1, p1: float, t2, p2: float) -> dict:
    return {"id": drawing_id, "title": "trendline", "point_count": 2,
            "points": [{"time": int(t1), "price": float(p1)}, {"time": int(t2), "price": float(p2)}]}


class _FakeChart:
    """Stands in for tv_cdp.TvChart -- a context manager returning a canned JS-eval result,
    exactly the shape real_chart_drawings.js / tv_cdp.TvChart.evaluate() would hand back."""

    def __init__(self, result: dict):
        self._result = result

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def require_chart_api(self) -> None:
        return None

    def evaluate(self, _js: str):
        return self._result


def _down_factory():
    """Stands in for tv_cdp.TvChart when TradingView Desktop / CDP is unreachable -- raises
    exactly what the real client raises (TvCdpError) at construction time (mirrors TvChart.
    __init__ eagerly calling find_chart_target())."""
    raise tv_cdp.TvCdpError("fake: CDP not reachable on 127.0.0.1:9222 -- TradingView Desktop not running?")


# --------------------------------------------------------------------------- (a) + (b) + (c)

def test_fresh_significant_scribble_and_old_lines_all_classified_correctly(tmp_path, monkeypatch):
    """One realistic end-to-end refresh() call carrying three manual drawings that must each
    land in a DIFFERENT bucket -- this is exactly the scenario the real chart_drawings.json
    will contain: something fresh + meaningful, something fresh + a scribble, something
    ancient (mirrors the 7 real 62-102-day-old lines found in trendlines.json on 2026-08-18)."""
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    data_dir.mkdir()
    state_dir.mkdir()
    monkeypatch.setattr(ct, "DATA_DIR", data_dir)
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    now = dt.datetime.now(ET)
    # Anchor the synthetic session to YESTERDAY (not today) so every anchor is guaranteed to be
    # in the past relative to "now" regardless of what time of day this test happens to run,
    # while still landing inside the 09:30-16:00 RTH mask `_load_recent_bars` applies.
    base_date = (now - dt.timedelta(days=1)).date()
    bar_start = _write_synthetic_csv(data_dir, base_date)
    t0 = int(bar_start.timestamp())

    # (a)+(c) KEPT: fresh (drawn "yesterday"), spans exactly the 25-bar/120-min window and
    # tracks the synthetic drift bar-for-bar -- must survive age AND clear the significance
    # floor with a real respect count.
    kept_t1, kept_p1 = t0, 700.00
    kept_t2, kept_p2 = t0 + 120 * 60, 700.48

    # (c) SCRIBBLE: equally fresh, but anchors only 5 minutes apart -- must be excluded by the
    # higher-timeframe significance filter despite being perfectly fresh and right on spot.
    scribble_t1, scribble_p1 = t0 + 50 * 60, 700.20
    scribble_t2, scribble_p2 = t0 + 55 * 60, 700.22

    # (b) OLD: anchors 62 days back (matches the real 62.3d-old line found live 2026-08-18) --
    # must be DROPPED by the age filter with the reason + age recorded, regardless of price
    # (compute_trendlines.compute() checks age before distance).
    old_dt = now - dt.timedelta(days=62)
    old_t1 = int(old_dt.timestamp())
    old_t2 = int((old_dt + dt.timedelta(hours=2)).timestamp())

    fake_result = {
        "success": True,
        "count": 3,
        "drawings": [
            _drawing("KEPT01", kept_t1, kept_p1, kept_t2, kept_p2),
            _drawing("SCRIB01", scribble_t1, scribble_p1, scribble_t2, scribble_p2),
            _drawing("OLD0001", old_t1, 650.00, old_t2, 655.00),
        ],
    }

    payload = tm.refresh(chart_factory=lambda: _FakeChart(fake_result))
    assert payload is not None, "refresh() must succeed when CDP is reachable and compute() has valid inputs"

    # chart_drawings.json was actually refreshed from the fake CDP result (the intraday fix).
    cd_on_disk = json.loads((state_dir / "chart_drawings.json").read_text(encoding="utf-8"))
    assert cd_on_disk["count"] == 3
    assert {d["id"] for d in cd_on_disk["drawings"]} == {"KEPT01", "SCRIB01", "OLD0001"}

    # trendlines.json on disk is exactly the payload refresh() returned.
    tl_on_disk = json.loads((state_dir / "trendlines.json").read_text(encoding="utf-8"))
    assert tl_on_disk == payload

    manual_ids = {m["chart_drawing_id"] for m in payload["manual"]}
    significant_ids = {m["chart_drawing_id"] for m in payload["manual_significant"]}
    dropped_by_id = {d["chart_drawing_id"]: d["reason"] for d in payload["manual_dropped"]}

    # (a) fresh, long-span line survives the AGE filter -- it appears in `manual` at all.
    assert "KEPT01" in manual_ids, "a fresh, recently-drawn line must survive the age filter"
    # (c) ... AND clears the higher-timeframe significance floor.
    assert "KEPT01" in significant_ids, "a 120-min-span, tape-tracking line must be significant"
    kept_entry = next(m for m in payload["manual_significant"] if m["chart_drawing_id"] == "KEPT01")
    assert kept_entry["span_minutes"] >= ct.MANUAL_MIN_SIGNIFICANT_SPAN_MINUTES
    assert kept_entry["respect_count_recent"] > 0, (
        "a line built from the tape's own linear drift should register real touches, not the "
        "old touch_count=2 anchor-only placeholder"
    )

    # (c) fresh scribble survives AGE (it's recent) but is excluded by SIGNIFICANCE.
    assert "SCRIB01" in manual_ids, "a fresh scribble still survives the age/distance filter"
    assert "SCRIB01" not in significant_ids, "a 5-minute-span scribble must NOT be significant"
    assert "SCRIB01" in dropped_by_id
    assert "insignificant" in dropped_by_id["SCRIB01"]
    assert "scribble" in dropped_by_id["SCRIB01"]

    # (b) the 62-day-old line is dropped by AGE, with the reason + age recorded.
    assert "OLD0001" not in manual_ids, "a 62-day-old line must be dropped, not merely deprioritized"
    assert "OLD0001" in dropped_by_id
    assert "old" in dropped_by_id["OLD0001"]
    assert f"(> {ct.MANUAL_MAX_AGE_DAYS}d)" in dropped_by_id["OLD0001"]
    old_drop = next(d for d in payload["manual_dropped"] if d["chart_drawing_id"] == "OLD0001")
    assert old_drop["age_days"] > ct.MANUAL_MAX_AGE_DAYS


# --------------------------------------------------------------------------- (d) fail-open

def test_refresh_fails_open_when_cdp_unreachable(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(ct, "STATE_DIR", state_dir)

    # A pre-existing chart_drawings.json must be left byte-for-byte untouched.
    cd_path = state_dir / "chart_drawings.json"
    prior_content = json.dumps({"schema_version": 2, "as_of": "2026-01-01T00:00:00-05:00",
                                 "source": "prior run", "count": 0, "drawings": []}, indent=2)
    cd_path.write_text(prior_content, encoding="utf-8")

    result = tm.refresh(chart_factory=_down_factory)

    assert result is None, "refresh() must return None, never raise, when CDP is unreachable"
    assert cd_path.read_text(encoding="utf-8") == prior_content, "chart_drawings.json must be left untouched"
    assert not (state_dir / "trendlines.json").exists(), "trendlines.json must not be written this cycle"


def test_refresh_chart_drawings_alone_raises_on_cdp_down(tmp_path):
    """The inner function's OWN contract: it RAISES (does not swallow) -- refresh() above is
    the fail-open layer, not this function. Pinned separately so it's clear which layer owns
    which half of the fail-open contract (see the module docstring's FAIL-OPEN section)."""
    out = tmp_path / "chart_drawings.json"
    raised = False
    try:
        tm.refresh_chart_drawings(chart_factory=_down_factory, out_path=out)
    except tv_cdp.TvCdpError:
        raised = True
    assert raised, "refresh_chart_drawings must propagate a CDP failure, not swallow it"
    assert not out.exists(), "no file should be written on a failed pull"


def test_refresh_chart_drawings_writes_expected_shape(tmp_path):
    out = tmp_path / "chart_drawings.json"
    fake_result = {"success": True, "count": 1,
                   "drawings": [_drawing("ABC123", 1000, 700.0, 5000, 701.0)]}
    payload = tm.refresh_chart_drawings(chart_factory=lambda: _FakeChart(fake_result), out_path=out)
    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert on_disk["count"] == 1
    assert on_disk["drawings"][0]["id"] == "ABC123"
    assert on_disk["schema_version"] == 2


def test_refresh_chart_drawings_raises_on_js_reported_failure(tmp_path):
    """CDP itself reachable, but the JS payload reports {success: false} (chart not loaded
    yet, etc.) -- must raise, never silently write an empty/garbage snapshot over good state."""
    out = tmp_path / "chart_drawings.json"
    out.write_text('{"prior": true}', encoding="utf-8")
    fake_result = {"success": False, "error": "no_active_chart_widget"}
    raised_msg = None
    try:
        tm.refresh_chart_drawings(chart_factory=lambda: _FakeChart(fake_result), out_path=out)
    except RuntimeError as exc:
        raised_msg = str(exc)
    assert raised_msg is not None, "a JS-reported failure must raise, not be treated as an empty success"
    assert "no_active_chart_widget" in raised_msg
    assert out.read_text(encoding="utf-8") == '{"prior": true}', "must not overwrite prior state on failure"


# --------------------------------------------------------------------------- wiring

def test_trendline_engine_main_calls_trendline_manual_refresh():
    """Pin the fold-in: Gamma_Trendlines' actual script (trendline_engine.py) must call this
    module as a best-effort step, so the intraday refresh really does ride the existing 5-min
    RTH scheduled task instead of requiring a new one."""
    import inspect
    sys.path.insert(0, str(REPO_ROOT / "backtest" / "autoresearch"))
    import trendline_engine
    src = inspect.getsource(trendline_engine.main)
    assert "import trendline_manual" in src
    assert "trendline_manual.refresh(" in src
    # Must be inside a try/except so it can never raise past main() (fail-open, C7).
    assert "except Exception as exc" in src
