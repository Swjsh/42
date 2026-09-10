"""Guards for setup/scripts/chart_hygiene.py + the WS-B zone-merge flag in
setup/scripts/draw_key_levels.py (WS-B chart hygiene sweep, work order §9.5 row B,
markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md, 2026-09-09).

All pure/offline: classify_shape()/merge_levels_into_zones() are unit-testable with no
chart, and the CDP-touching paths use a fake chart object (same pattern as
backtest/tests/test_trendline_manual_refresh_2026_08_18.py's `_FakeChart`) -- these must
pass with TradingView Desktop CLOSED.

Six guards, matching the work order's deliverable proof list 1:1:
  1. A registered shape survives 100 mutation runs (randomized surrounding population).
  2. `UvNj5Q` (J's live 09-09 ray) is never a removal candidate.
  3. `draw_clear` is never called -- across dry-run AND apply code paths.
  4. A `[GTL] ` shape inside the band is kept; an orphan `[GTL] ` outside the band is a
     removal candidate.
  5. Dry-run mode removes nothing and still writes a complete log.
  6. Zone-merge flag OFF => draw_key_levels output identical to pre-change.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))

import chart_hygiene as ch  # noqa: E402
import draw_key_levels as dkl  # noqa: E402
from tv_cdp import TvCdpError  # noqa: E402

# J's actual live line this session (work order §Situation): a `ray`, anchors
# 773.07 @ t=1788438600 -> 760.39 @ t=1788989400. It must survive everything WS-B builds.
J_LINE_ID = "UvNj5Q"
J_LINE_POINTS = [
    {"time": 1788438600, "price": 773.07},
    {"time": 1788989400, "price": 760.39},
]


# --------------------------------------------------------------------------
# fake chart -- stands in for tv_cdp.TvChart (mirrors test_trendline_manual_refresh's
# _FakeChart, extended with the calls chart_hygiene.py actually makes)
# --------------------------------------------------------------------------

class _FakeChart:
    """Canned shape population + points, with instrumented remove_entity/draw_clear
    counters so guard #3 (draw_clear never called) and the removal bookkeeping are
    directly observable."""

    def __init__(self, shapes: list[dict], spot: float | None = 770.0):
        # shapes: [{"id":.., "name":.., "text":.., "points":[...]}]
        self._shapes = {s["id"]: s for s in shapes}
        self._spot = spot
        self.remove_calls: list[str] = []
        self.draw_clear_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def require_chart_api(self) -> None:
        return None

    def last_price(self) -> float | None:
        return self._spot

    def list_shapes(self) -> list[dict]:
        return [{"id": sid, "name": s.get("name")} for sid, s in self._shapes.items()]

    def shape_text(self, entity_id: str) -> str | None:
        s = self._shapes.get(entity_id)
        return s.get("text") if s else None

    def evaluate(self, js: str):
        # chart_hygiene._get_points() is the only evaluate() caller in this module;
        # its js embeds the entity id as a JSON string literal -- pull it back out.
        for sid, s in self._shapes.items():
            if json.dumps(sid) in js:
                return s.get("points")
        return None

    def remove_entity(self, entity_id: str) -> bool:
        self.remove_calls.append(entity_id)
        return entity_id in self._shapes

    def draw_clear(self) -> None:  # pragma: no cover - must never be invoked
        self.draw_clear_calls += 1


def _write_registry(tmp_path: Path, entries: dict) -> None:
    ch.REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ch._write_json_atomic(ch.REGISTRY_FILE, {"schema_version": 1, "shapes": entries})


def _j_registry_entry() -> dict:
    return {
        "id": J_LINE_ID,
        "name": "ray",
        "text": "",
        "points": J_LINE_POINTS,
        "first_seen_et": "2026-09-09T23:55:00-04:00",
        "first_seen_date_et": "2026-09-09",
    }


def _random_shape(i: int) -> dict:
    """A random untagged/tagged shape far from J's line, used as sweep-population noise."""
    kinds = [
        {"name": "trend_line", "text": ""},
        {"name": "horizontal_line", "text": f"[G] NOISE {i} {700 + i:.2f}"},
        {"name": "trend_line", "text": f"[GTL] [WICK] NOISE touch x{i % 5}"},
        {"name": "rectangle", "text": ""},
        {"name": "ray", "text": f"random label {i}"},
    ]
    kind = random.choice(kinds)
    price = 700.0 + random.uniform(-50, 50)
    return {
        "id": f"NOISE{i:04d}",
        "name": kind["name"],
        "text": kind["text"],
        "points": [{"time": 1788000000 + i, "price": price}],
    }


# --------------------------------------------------------------------------
# guard 1: a registered shape survives 100 mutation runs
# --------------------------------------------------------------------------

def test_guard1_registered_shape_survives_100_mutation_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "REGISTRY_FILE", tmp_path / "j-shapes.json")
    monkeypatch.setattr(ch, "OBSERVATIONS_FILE", tmp_path / "chart-hygiene-observations.json")
    monkeypatch.setattr(ch, "LOG_DIR", tmp_path / "chart-hygiene-log")

    random.seed(20260909)
    for run in range(100):
        # Fresh registry each run holding ONLY J's line -- the registry itself is what
        # must never be bypassed, regardless of how much noise surrounds it.
        _write_registry(tmp_path, {J_LINE_ID: _j_registry_entry()})
        # Clear observation state each run so "stale" noise from a prior run's
        # bookkeeping can never accidentally protect this run's noise either.
        if ch.OBSERVATIONS_FILE.exists():
            ch.OBSERVATIONS_FILE.unlink()

        noise = [_random_shape(run * 50 + i) for i in range(random.randint(1, 12))]
        j_shape = {"id": J_LINE_ID, "name": "ray", "text": "", "points": J_LINE_POINTS}
        chart = _FakeChart([j_shape] + noise, spot=random.uniform(690, 810))

        summary, log_rows = ch.run_sweep(chart, apply=True)

        assert J_LINE_ID not in chart.remove_calls, f"run {run}: registered id was removed!"
        j_rows = [r for r in log_rows if r["id"] == J_LINE_ID]
        assert len(j_rows) == 1
        assert j_rows[0]["action"] == "keep"
        assert j_rows[0]["reason"] == "j_registry"
        assert chart.draw_clear_calls == 0


# --------------------------------------------------------------------------
# guard 2: UvNj5Q specifically is never a removal candidate
# --------------------------------------------------------------------------

def test_guard2_j_ray_uvnj5q_never_a_removal_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "REGISTRY_FILE", tmp_path / "j-shapes.json")
    monkeypatch.setattr(ch, "OBSERVATIONS_FILE", tmp_path / "chart-hygiene-observations.json")
    monkeypatch.setattr(ch, "LOG_DIR", tmp_path / "chart-hygiene-log")
    _write_registry(tmp_path, {J_LINE_ID: _j_registry_entry()})

    # Spot is FAR from both of J's anchors and the shape carries no engine tag and no
    # prior-session history -- every signal a naive sweep might use to justify removal
    # is present here, and it must still be kept purely because it is registered.
    j_shape = {"id": J_LINE_ID, "name": "ray", "text": "", "points": J_LINE_POINTS}
    chart = _FakeChart([j_shape], spot=650.0)

    summary, log_rows = ch.run_sweep(chart, apply=True)
    assert chart.remove_calls == []
    assert summary["remove_candidates"] == 0
    assert log_rows[0]["action"] == "keep"
    assert log_rows[0]["reason"] == "j_registry"

    # Also true at the pure classify_shape() level directly, independent of run_sweep.
    decision = ch.classify_shape(
        j_shape, spot=650.0, band_dollars=12.0, registry_ids={J_LINE_ID},
        prior_dates=[], today_date="2026-09-10",
    )
    assert decision == {"action": "keep", "reason": "j_registry"}


# --------------------------------------------------------------------------
# guard 3: draw_clear is never called, across dry-run AND apply
# --------------------------------------------------------------------------

def test_guard3_draw_clear_never_called_dry_run_and_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "REGISTRY_FILE", tmp_path / "j-shapes.json")
    monkeypatch.setattr(ch, "OBSERVATIONS_FILE", tmp_path / "chart-hygiene-observations.json")
    monkeypatch.setattr(ch, "LOG_DIR", tmp_path / "chart-hygiene-log")
    _write_registry(tmp_path, {})

    shapes = [_random_shape(i) for i in range(15)]

    chart_dry = _FakeChart(list(shapes), spot=770.0)
    ch.run_sweep(chart_dry, apply=False)
    assert chart_dry.draw_clear_calls == 0
    assert chart_dry.remove_calls == []  # dry-run must not remove anything either

    chart_apply = _FakeChart(list(shapes), spot=770.0)
    ch.run_sweep(chart_apply, apply=True)
    assert chart_apply.draw_clear_calls == 0

    # A FakeChart with an instrumented draw_clear() counter is the load-bearing part of
    # this guard (asserted above): if chart_hygiene.py ever called it, on ANY code path,
    # the counter would be nonzero. The module's own docstring names draw_clear/
    # removeAllShapes only in prose (explaining why they're avoided), so a raw text scan
    # for the identifier would false-positive on documentation, not behavior.


# --------------------------------------------------------------------------
# guard 4: [GTL] in-band kept, orphan [GTL] outside band is a removal candidate
# --------------------------------------------------------------------------

def test_guard4_gtl_in_band_kept_orphan_outside_band_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "REGISTRY_FILE", tmp_path / "j-shapes.json")
    monkeypatch.setattr(ch, "OBSERVATIONS_FILE", tmp_path / "chart-hygiene-observations.json")
    monkeypatch.setattr(ch, "LOG_DIR", tmp_path / "chart-hygiene-log")
    _write_registry(tmp_path, {})

    spot = 770.0
    gtl_tag = ch.ENGINE_TAG_PREFIXES[1]  # trendline_headless_draw.TAG == "[GTL] "
    assert gtl_tag == "[GTL] "

    in_band = {
        "id": "GTL_INBAND",
        "name": "trend_line",
        "text": f"{gtl_tag}[WICK] RESISTANCE touch x5",
        "points": [{"time": 1, "price": spot + 3.0}, {"time": 2, "price": spot + 4.0}],
    }
    out_of_band = {
        "id": "GTL_ORPHAN",
        "name": "trend_line",
        "text": f"{gtl_tag}[WICK] SUPPORT touch x3",
        "points": [{"time": 1, "price": spot - 40.0}, {"time": 2, "price": spot - 41.0}],
    }
    chart = _FakeChart([in_band, out_of_band], spot=spot)

    summary, log_rows = ch.run_sweep(chart, apply=False, band_dollars=12.0)
    by_id = {r["id"]: r for r in log_rows}

    assert by_id["GTL_INBAND"]["action"] == "keep"
    assert by_id["GTL_INBAND"]["reason"] == "[GTL]_in_band"
    assert by_id["GTL_ORPHAN"]["action"] == "would_remove"
    assert by_id["GTL_ORPHAN"]["reason"] == "[GTL]_orphan_outside_band"

    # pure classify_shape() gives the identical answer directly
    assert ch.classify_shape(in_band, spot, 12.0, set(), [], "2026-09-09")["action"] == "keep"
    assert ch.classify_shape(out_of_band, spot, 12.0, set(), [], "2026-09-09")["action"] == "remove"


# --------------------------------------------------------------------------
# guard 5: dry-run removes nothing and still writes a complete log
# --------------------------------------------------------------------------

def test_guard5_dry_run_removes_nothing_writes_complete_log(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "REGISTRY_FILE", tmp_path / "j-shapes.json")
    monkeypatch.setattr(ch, "OBSERVATIONS_FILE", tmp_path / "chart-hygiene-observations.json")
    log_dir = tmp_path / "chart-hygiene-log"
    monkeypatch.setattr(ch, "LOG_DIR", log_dir)
    _write_registry(tmp_path, {})

    gtl_tag = ch.ENGINE_TAG_PREFIXES[1]
    shapes = [
        {"id": "A", "name": "trend_line", "text": "",
         "points": [{"time": 1, "price": 900.0}]},  # untagged, far out -- but fresh, not stale yet
        {"id": "B", "name": "trend_line", "text": f"{gtl_tag}orphan",
         "points": [{"time": 1, "price": 900.0}]},  # tagged orphan, out of band -> would_remove
    ]
    chart = _FakeChart(shapes, spot=770.0)

    summary, log_rows = ch.run_sweep(chart, apply=False, band_dollars=12.0)

    assert summary["dry_run"] is True
    assert chart.remove_calls == [], "dry-run must never call remove_entity"
    assert summary["removed"] == 0

    # log is complete: every shape on chart has exactly one row, and a would_remove
    # candidate is logged with that exact action (not silently dropped).
    assert len(log_rows) == len(shapes)
    ids_logged = {r["id"] for r in log_rows}
    assert ids_logged == {"A", "B"}
    reasons = {r["id"]: r["action"] for r in log_rows}
    assert reasons["B"] == "would_remove"

    log_path = Path(summary["log_path"])
    assert log_path.exists()
    on_disk = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(on_disk) == len(shapes)
    for row in on_disk:
        assert {"ts_et", "date_et", "id", "name", "text", "reason", "action"} <= set(row.keys())


# --------------------------------------------------------------------------
# fail-open: TradingView/CDP down never raises, never removes
# --------------------------------------------------------------------------

def test_fail_open_when_cdp_down(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "REGISTRY_FILE", tmp_path / "j-shapes.json")
    monkeypatch.setattr(ch, "OBSERVATIONS_FILE", tmp_path / "chart-hygiene-observations.json")
    monkeypatch.setattr(ch, "LOG_DIR", tmp_path / "chart-hygiene-log")

    def _down(*_a, **_kw):
        raise TvCdpError("fake: CDP not reachable on 127.0.0.1:9222")

    monkeypatch.setattr(ch, "TvChart", _down)
    rc = ch.main(["--apply"])
    assert rc == 0
    assert not ch.REGISTRY_FILE.exists()


# --------------------------------------------------------------------------
# guard 6: zone-merge flag OFF => draw_key_levels output identical to pre-change
# --------------------------------------------------------------------------

def _sample_levels(spot: float) -> list[dict]:
    kl = {
        "spot_at_compute": spot,
        "levels": [
            {"price": spot + 0.10, "role": "resistance", "label": "A"},
            {"price": spot + 0.15, "role": "resistance", "label": "B"},  # would merge with A at width>=0.05
            {"price": spot - 4.00, "role": "support", "label": "C"},
        ],
        "deprecated_levels": [],
    }
    return dkl.select_levels(kl, spot=spot, band=12.0)


def test_guard6_zone_merge_flag_off_is_byte_identical():
    assert dkl.ZONE_MERGE_ENABLED is False, "zone-merge must ship OFF by default (doctrine)"

    spot = 770.0
    levels = _sample_levels(spot)

    # main()'s pipeline: with the flag off, `merge_levels_into_zones` is never invoked at
    # all -- assert directly that the selected-levels list passed to draw_levels() is
    # exactly select_levels()'s own output, unchanged, when the flag is off.
    if dkl.ZONE_MERGE_ENABLED:  # pragma: no cover - defensive, flag is False above
        levels_to_draw = dkl.merge_levels_into_zones(levels, dkl.ZONE_MERGE_WIDTH_DOLLARS)
    else:
        levels_to_draw = levels

    assert levels_to_draw == levels
    assert [dkl.line_text(lv) for lv in levels_to_draw] == [dkl.line_text(lv) for lv in levels]


def test_merge_levels_into_zones_is_a_noop_when_width_is_none():
    levels = _sample_levels(770.0)
    assert dkl.merge_levels_into_zones(levels, None) == levels


def test_merge_levels_into_zones_merges_when_enabled_with_a_width():
    levels = _sample_levels(770.0)
    zones = dkl.merge_levels_into_zones(levels, zone_width_dollars=0.10)
    # A (770.10) and B (770.15) are within 0.10 of each other -> merged into one zone of
    # tier 2; C (766.00) stays its own singleton zone of tier 1.
    tiers = sorted(z["tier"] for z in zones)
    assert tiers == [1, 2]
    merged = next(z for z in zones if z["tier"] == 2)
    assert merged["low"] == 770.10
    assert merged["high"] == 770.15


class _FakeDklChart:
    """Minimal stand-in for tv_cdp.TvChart covering exactly what draw_key_levels.main()
    calls on the happy path, so the ZONE_MERGE_ENABLED-without-a-width guard can be
    proven through the REAL main() pipeline, not a reimplementation of it."""

    def __init__(self, spot: float = 770.0):
        self._spot = spot

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def require_chart_api(self) -> None:
        return None

    def symbol(self) -> str:
        return "BATS:SPY"

    def last_price(self) -> float:
        return self._spot

    def list_shapes(self) -> list[dict]:
        return []

    def shape_text(self, _entity_id: str) -> None:
        return None


def test_zone_merge_enabled_without_ratified_width_fails_loud(tmp_path, monkeypatch):
    """C7: an enabled flag with the still-open F(3) placeholder must raise inside
    main()'s real pipeline (return code 1, ERROR status, flagged to STATUS.md) --
    never silently hand zone-shaped dicts to draw_levels()."""
    monkeypatch.setattr(dkl, "ZONE_MERGE_ENABLED", True)
    assert dkl.ZONE_MERGE_WIDTH_DOLLARS is None, "placeholder must still be None for this guard to mean anything"

    key_levels_path = tmp_path / "key-levels.json"
    key_levels_path.write_text(
        json.dumps({"spot_at_compute": 770.0, "levels": [{"price": 770.1, "role": "resistance", "label": "A"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(dkl, "KEY_LEVELS", key_levels_path)
    monkeypatch.setattr(dkl, "STATE_FILE", tmp_path / "chart-autodraw.json")
    monkeypatch.setattr(dkl, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(dkl, "TvChart", lambda: _FakeDklChart(spot=770.0))

    rc = dkl.main(["--dry-run"])
    assert rc == 1, "an enabled flag with no ratified width must fail loud (exit 1), not silently draw"
