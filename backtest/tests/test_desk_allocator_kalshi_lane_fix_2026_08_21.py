"""Guard: assess_prediction_markets() must judge liveness off the LIVE kalshi lane.

WHY THIS EXISTS
  kalshi_tick.py (SPY-directional lane) was superseded the SAME DAY it shipped
  (2026-08-09) by kalshi_auto.py (the weather lane, Gamma_KalshiAuto, 18:10 ET
  daily -- the only Kalshi task actually registered in Task Scheduler). The old
  assess_prediction_markets() read kalshi_tick.py's `last-tick.json` /
  `shadow-ledger.jsonl` for its liveness + progress signal. Those files have sat
  frozen since 2026-08-09 BY DESIGN (retired, not broken) -- so the desk
  permanently reported BROKEN/0-progress against a dead sibling while the real
  weather lane (weather-predictions.jsonl) ran clean the entire time. Same bug
  CLASS the 2026-08-20 fix caught once already on assess_multi_sector's two lanes.

  These tests pin: (a) a fresh weather lane + a permanently-stale last-tick.json
  must NOT report broken; (b) a genuinely stale weather lane still reports
  broken (the liveness check itself still works, just against the right file);
  (c) progress reflects the per-city scorecard's best `n`, not a dead row count.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import desk_allocator as da                    # noqa: E402


def _write_predictions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_stale_dead_lane_sibling_no_longer_marks_desk_broken(tmp_path, monkeypatch):
    """The regression this fire fixes: last-tick.json frozen since 2026-08-09 by
    design must NOT poison the desk's liveness verdict any more."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    k = tmp_path / "kalshi"
    _write_predictions(k / "weather-predictions.jsonl", [
        {"series": "KXHIGHNY", "observed": 74.0, "pick_won": True, "abs_err": 0.4},
    ])
    # the dead sibling: present, but ancient -- must be irrelevant to this check
    (k / "last-tick.json").write_text("{}", encoding="utf-8")
    old = time.time() - 86400 * 400
    import os
    os.utime(k / "last-tick.json", (old, old))

    a = da.assess_prediction_markets()
    assert a["broken"] == [], a["broken"]
    assert a["dead_signal"] is False


def test_genuinely_stale_weather_lane_still_reports_broken(tmp_path, monkeypatch):
    """The liveness check must still fire for REAL staleness -- just against the
    correct (live) producer file, not the retired one."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    k = tmp_path / "kalshi"
    _write_predictions(k / "weather-predictions.jsonl", [
        {"series": "KXHIGHNY", "observed": 74.0, "pick_won": True, "abs_err": 0.4},
    ])
    import os
    old = time.time() - 3600 * 200   # >48h stale
    os.utime(k / "weather-predictions.jsonl", (old, old))

    a = da.assess_prediction_markets()
    assert a["broken"], "genuinely stale weather lane must still be flagged"
    assert "weather-predictions" in a["broken"][0]


def test_missing_weather_predictions_file_reports_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(da, "STATE", tmp_path)
    a = da.assess_prediction_markets()
    assert a["broken"] and "MISSING" in a["broken"][0]
    assert a["progress"] == 0.0


def test_progress_reflects_best_city_scorecard_not_dead_row_count(tmp_path, monkeypatch):
    """Progress must track the live scorecard's best-city `n`, not shadow-ledger
    row count from the retired lane (which could be anything, including stale
    numbers unrelated to actual weather-lane progress)."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    k = tmp_path / "kalshi"
    rows = [{"series": "KXHIGHNY", "observed": 70.0 + i, "pick_won": i % 2 == 0,
             "abs_err": 1.0} for i in range(12)]
    _write_predictions(k / "weather-predictions.jsonl", rows)
    # a huge, unrelated row count in the dead sibling must NOT influence progress
    (k / "shadow-ledger.jsonl").write_text("\n".join(["{}"] * 500), encoding="utf-8")

    a = da.assess_prediction_markets()
    assert abs(a["progress"] - 12 / 20.0) < 1e-9, a["progress"]


def test_city_earning_the_bar_is_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(da, "STATE", tmp_path)
    k = tmp_path / "kalshi"
    rows = [{"series": "KXHIGHNY", "observed": 70.0 + i, "pick_won": True,
             "abs_err": 0.5} for i in range(25)]
    _write_predictions(k / "weather-predictions.jsonl", rows)

    a = da.assess_prediction_markets()
    assert "1 earned" in a["headline"], a["headline"]


def test_live_kalshi_state_currently_healthy():
    """Live-state canary against the REAL repo state (no monkeypatch): the
    production kalshi lane is known-live as of 2026-08-21 (weather-predictions.jsonl
    written 2026-08-20T22:10 UTC). If this ever goes broken it should be because
    the lane genuinely stopped, not because of the last-tick.json defect."""
    a = da.assess_prediction_markets()
    assert a["broken"] == [], (
        "prediction-markets desk reports broken against LIVE repo state: %r — "
        "either the weather lane genuinely stopped, or the fix regressed" % a["broken"]
    )
