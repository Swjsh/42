"""RED-proof: GOAL-FUTURES-YELLOWS-2026-09-05 F1.

no_stray_exposure's window was `sorted(distinct anomaly-dates in the file)[-N:]` -- but
anomalies.jsonl is an append-only INCIDENT log (rows written only when something goes
wrong, never on a clean session). With only 2 distinct dates EVER written (the already-
fixed 2026-09-03 flatten cascade, whose real fill events happened 2026-09-01/09-02), that
window never rolled forward on its own: no new rows -> no new distinct dates -> the SAME 2
dates stay in `[-N:]` forever, regardless of how many calendar days pass. The check would
never age out and would stay RED indefinitely on a fixed, dormant defect.

This test fails on the pre-fix code (no calendar-day bound) and passes after
ANOMALY_MAX_AGE_DAYS is applied in check_no_stray_exposure (setup/scripts/futures_health.py).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import futures_health as fh  # noqa: E402

# The real 8-row cascade collapses (by fill event date) to 2 distinct dates: 2026-09-01 and
# 2026-09-02. Minimal repro uses one row per date.
_CASCADE_ROWS = [
    {"at_et": "2026-09-03T00:43:02", "event": "unattributed_closing_fill", "symbol": "MES",
     "fill": {"filled_at": "2026-09-01T08:08:47.540000+00:00"}},
    {"at_et": "2026-09-03T00:43:03", "event": "unattributed_closing_fill", "symbol": "MES",
     "fill": {"filled_at": "2026-09-02T20:00:07.533000+00:00"}},
]


def _write_rows(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_stray_exposure_still_red_within_the_age_window(tmp_path):
    """Sanity anchor: on 2026-09-05 (3-4 calendar days after the fill events), the cascade
    rows are still within ANOMALY_MAX_AGE_DAYS and must still read RED -- the fix must not
    silently clear a genuinely-recent incident."""
    p = tmp_path / "anomalies.jsonl"
    _write_rows(p, _CASCADE_ROWS)
    now = dt.datetime(2026, 9, 5, 6, 0, 0)
    result = fh.check_no_stray_exposure(now, anomalies_path=p)
    assert result["status"] == "RED"


def test_stray_exposure_ages_out_by_2026_09_08_no_new_rows_needed(tmp_path):
    """THE FIX: with zero new anomaly rows landing (the defect is already fixed upstream,
    so nothing new should ever be written), the check must still roll from RED to GREEN
    purely because enough calendar time passed -- never permanently RED on a dormant,
    already-fixed incident.

    Pre-fix code used `sorted(by_date)[-ANOMALY_LOOKBACK_SESSIONS:]` with no age bound: since
    by_date only ever has the same 2 keys (09-01, 09-02) here, that slice is IDENTICAL on
    2026-09-05 and 2026-09-08 -- this assertion FAILS on the pre-fix code (still RED on
    09-08) and PASSES after the ANOMALY_MAX_AGE_DAYS cutoff is applied.
    """
    p = tmp_path / "anomalies.jsonl"
    _write_rows(p, _CASCADE_ROWS)
    now = dt.datetime(2026, 9, 8, 6, 0, 0)
    result = fh.check_no_stray_exposure(now, anomalies_path=p)
    assert result["status"] == "GREEN", result["detail"]
    assert "aged out" in result["detail"]


def test_stray_exposure_ageout_cutoff_is_exactly_5_calendar_days(tmp_path):
    """Pins the exact cutoff so a future edit can't silently widen/narrow the window without
    a failing test: still RED the day before rollover (09-07), GREEN on/after 09-08."""
    p = tmp_path / "anomalies.jsonl"
    _write_rows(p, _CASCADE_ROWS)

    still_red = fh.check_no_stray_exposure(dt.datetime(2026, 9, 7, 6, 0, 0), anomalies_path=p)
    assert still_red["status"] == "RED"

    now_green = fh.check_no_stray_exposure(dt.datetime(2026, 9, 8, 6, 0, 0), anomalies_path=p)
    assert now_green["status"] == "GREEN"


def test_stray_exposure_new_recent_row_still_reds_after_old_rows_age_out(tmp_path):
    """A genuinely NEW incident must still RED even after the old cascade has aged out --
    the age-out bound must not accidentally suppress future real anomalies."""
    p = tmp_path / "anomalies.jsonl"
    _write_rows(p, _CASCADE_ROWS)
    _write_rows(p, [{"at_et": "2026-09-08T10:00:00", "event": "unattributed_closing_fill",
                     "symbol": "MES", "fill": {"filled_at": "2026-09-08T14:00:00+00:00"}}])
    now = dt.datetime(2026, 9, 8, 12, 0, 0)
    result = fh.check_no_stray_exposure(now, anomalies_path=p)
    assert result["status"] == "RED"
    assert "1 stray-exposure anomaly row(s)" in result["detail"]
