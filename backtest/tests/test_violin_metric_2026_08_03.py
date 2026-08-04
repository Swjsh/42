"""Guard — violin_metric.py (LANE-4, 2026-08-03): the violin coverage metric must measure
what it claims: tape-respected levels vs engine levels_active AT THE MOMENT OF THE TOUCH.

RED-proofs:
  * test_late_level_is_a_miss_with_latency — the 08-03 shape (final premarket low active
    only ~15 min after the respect) grades as NOT covered, with the latency measured;
    moving the same level's first appearance before the touch flips it to covered — the
    deadline comparison is load-bearing, not decorative.
  * test_premarket_respect_uses_window_open_deadline — a premarket respect is covered iff
    the level is active by 09:36 (the engine cannot tick premarket); 09:44 is a miss.

$0, pure-Python, no network (frame + timeline injected). History writes -> tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "setup" / "scripts" / "violin_metric.py"
_spec = importlib.util.spec_from_file_location("violin_metric", MOD)
vm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vm)

RLI = REPO / "setup" / "scripts" / "refresh_levels_intraday.py"
_rspec = importlib.util.spec_from_file_location("rli_for_frames", RLI)
rli = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(rli)

DATE = "2026-08-03"


def _frame(rows):
    df = pd.DataFrame([{"t": f"{DATE}T{int(hm[:2]) + 4:02d}:{hm[3:]}:00Z", "open": o,
                        "high": h, "low": lo, "close": c, "volume": v}
                       for hm, o, h, lo, c, v in rows])
    return rli._decorate_frame(df)


def _the_0803_shape() -> pd.DataFrame:
    """Minimal tape: premarket drift, 09:25 dump into 749.33, RTH open flush + rally."""
    rows = [(f"{h:02d}:{m:02d}", 750.8, 751.2, 750.4, 750.8, 30_000.0)
            for h in (8,) for m in range(0, 60, 5)]
    rows += [("09:00", 750.8, 751.2, 750.3, 750.6, 30_000.0),
             ("09:05", 750.6, 750.9, 750.2, 750.5, 30_000.0),
             ("09:10", 750.5, 750.8, 750.1, 750.4, 30_000.0),
             ("09:15", 750.4, 750.7, 750.0, 750.3, 30_000.0),
             ("09:20", 750.3, 750.5, 749.8, 749.9, 60_000.0),
             ("09:25", 749.9, 750.0, 749.33, 749.4, 90_000.0),   # the dump bar (final PML)
             ("09:30", 749.4, 750.8, 748.8, 750.74, 1_500_000.0),  # flush + reclaim
             ("09:35", 750.7, 751.4, 750.5, 751.2, 800_000.0),     # reaction >= +0.50
             ("09:40", 751.2, 751.8, 751.0, 751.5, 700_000.0),
             ("09:45", 751.5, 751.9, 751.2, 751.7, 600_000.0)]
    return _frame(rows)


def _timeline(first_ts_with_level: str, level: float = 749.33):
    """Engine tick timeline: level absent before `first_ts_with_level`, present after."""
    ticks = []
    for hm in ("09:30:04", "09:36:03", "09:40:03", "09:44:03", "09:50:03"):
        ts = f"{DATE}T{hm}"
        levels = [751.55, 748.5] + ([level] if ts >= first_ts_with_level else [])
        ticks.append((ts, levels))
    return ticks


class TestCoverageGrading:
    def _episodes(self):
        df = _the_0803_shape()
        uni = vm.build_universe(df, DATE)
        eps = vm.scan_respects(df, DATE, uni)
        pml = [e for e in eps if e["source"] == "premarket_low"]
        assert pml, "the 09:30 bar must register a premarket_low respect at 749.33"
        assert pml[0]["price"] == pytest.approx(749.33)
        return eps, pml[0]

    def test_late_level_is_a_miss_with_latency(self):
        """The real 08-03 grade: 749.33 first active 09:44:03, touch closed 09:35 -> MISS,
        latency ~9 min. RED-proof half: first-active 09:30:04 -> COVERED, latency 0."""
        eps, pml = self._episodes()
        vm.grade_episodes(eps, _timeline(f"{DATE}T09:44:03"))
        assert pml["covered_at_touch"] is False
        assert pml["latency_min"] == pytest.approx(9.1, abs=0.2)
        vm.grade_episodes(eps, _timeline(f"{DATE}T09:30:04"))
        assert pml["covered_at_touch"] is True
        assert pml["latency_min"] == 0.0

    def test_never_active_is_a_miss_with_null_latency(self):
        eps, pml = self._episodes()
        vm.grade_episodes(eps, _timeline(f"{DATE}T23:59:59"))  # never appears
        assert pml["covered_at_touch"] is False and pml["latency_min"] is None

    def test_premarket_respect_uses_window_open_deadline(self):
        """A file-layer level respected PREMARKET is covered iff active by 09:36 —
        the engine does not tick before 09:30, so touch-time coverage would be unfair."""
        df = _the_0803_shape()
        # synthetic file-layer level at 750.00 respected by the 09:05..09:15 lows
        uni = [{"price": 750.00, "source": "daily_context_shelf", "role": "support"}]
        eps = vm.scan_respects(df, DATE, uni)
        pre_eps = [e for e in eps if e["premarket"]]
        assert pre_eps, "premarket respect episodes must be detectable"
        vm.grade_episodes(eps, _timeline(f"{DATE}T09:36:03", level=750.00))
        assert all(e["covered_at_touch"] for e in pre_eps)
        vm.grade_episodes(eps, _timeline(f"{DATE}T09:44:03", level=750.00))
        assert all(not e["covered_at_touch"] for e in pre_eps)

    def test_summarize_math(self):
        eps, _ = self._episodes()
        vm.grade_episodes(eps, _timeline(f"{DATE}T09:44:03"))
        s = vm.summarize(DATE, eps, timeline_len=5)
        assert s["respected_total"] == len(eps) >= 1
        assert 0 <= s["covered_total"] <= s["respected_total"]
        assert s["defn_version"] == vm.DEFN_VERSION
        assert "premarket_low" in s["per_source"]

    def test_universe_dedupes_file_layer_against_tape(self, monkeypatch):
        """A snapshot level within $0.10 of the tape-derived PML must NOT double-count."""
        df = _the_0803_shape()
        monkeypatch.setattr(vm, "load_snapshot_levels",
                            lambda date: [{"price": 749.30, "source": "level_memory",
                                           "role": "support"}])
        uni = vm.build_universe(df, DATE)
        near = [u for u in uni if abs(u["price"] - 749.33) <= 0.10]
        assert len(near) == 1 and near[0]["source"] == "premarket_low"


class TestHistoryUpsert:
    def test_upsert_replaces_not_duplicates(self, tmp_path, monkeypatch):
        hist = tmp_path / "violin-history.jsonl"
        monkeypatch.setattr(vm, "HISTORY", hist)
        row = {"date": DATE, "coverage_pct": 50.0, "respected_total": 4, "covered_total": 2,
               "defn_version": vm.DEFN_VERSION, "engine_ticks_seen": 5,
               "per_source": {"premarket_low": {"coverage_pct": 50.0}}}
        vm.upsert_history([row])
        vm.upsert_history([dict(row, coverage_pct=75.0, covered_total=3)])
        lines = [json.loads(x) for x in hist.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 1
        assert lines[0]["coverage_pct"] == 75.0
        assert lines[0]["per_source_coverage"] == {"premarket_low": 50.0}
