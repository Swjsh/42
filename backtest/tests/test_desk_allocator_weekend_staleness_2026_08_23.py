"""Guard: a weekday-market-hours-only lane must not be flagged BROKEN purely because it is
the weekend.

WHY THIS EXISTS
  desk_allocator.py's `assess_futures` / `assess_multi_sector` used a raw
  `age_h(file) > STALE_H(24h)` staleness check on lanes that only tick during weekday RTH
  (futures shadow trader, multi-1's 15-min RTH shadow). Any Saturday or Sunday fire is
  GUARANTEED to see Friday's last write as >24h old -- the market being closed, not a real
  break. Caught 2026-08-23 in WEEKEND mode (runs every 2h, all weekend): this inflated the
  futures desk's score by +40 "BROKEN" points (falsely promoting it ahead of SPY 0DTE) and
  forced multi-sector's `dead_signal=True` ("do not polish a corpse") on EVERY weekend fire,
  even though multi-1 is a live, un-killed shadow lane -- just quiet outside trading days.

  Same false-positive CLASS as the 2026-08-21 armable_unarmed fix (a static/wall-clock signal
  misread as still-true) -- pinned here so this specific field can't regress the same way.

THE FIX
  Judge staleness against the most recently COMPLETED trading day (mirrors self_check.py's
  `_last_completed_trading_day` -- deliberately duplicated, not imported, to keep this script
  import-side-effect-free per its own "pure Python, $0" header). A lane is broken only if it
  failed to write during a trading session that has ALREADY closed -- a pure weekend/holiday
  gap can never trip it, but a lane that genuinely misses a real prior weekday session still
  does (this test also pins that the fix did not become a rubber stamp).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import desk_allocator as da                    # noqa: E402


def _touch_et(p: Path, et_iso: str) -> None:
    """Set p's mtime so its ET calendar date matches et_iso ('YYYY-MM-DDTHH:MM:SS')."""
    import os
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    naive = datetime.strptime(et_iso, "%Y-%m-%dT%H:%M:%S")
    utc = naive.replace(tzinfo=timezone.utc) - __import__("datetime").timedelta(
        hours=da._et_offset_hours(naive.replace(tzinfo=timezone.utc)))
    epoch = utc.timestamp()
    os.utime(p, (epoch, epoch))


def test_friday_lane_not_broken_on_sunday(tmp_path, monkeypatch):
    """The scar case: Friday close -> Sunday fire must read the lane as fine, not BROKEN."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    (tmp_path / "calendar.json").write_text('{"holidays": []}', encoding="utf-8")
    lane = tmp_path / "futures" / "shadow-progress.json"
    _touch_et(lane, "2026-08-21T15:15:00")   # Friday close

    monkeypatch.setattr(da, "_now_utc", lambda: datetime(2026, 8, 23, 4, 0, 0, tzinfo=timezone.utc))
    # 2026-08-23 04:00 UTC == 2026-08-23 00:00 ET, a Sunday
    assert da._lane_missed_trading_day(lane) is False


def test_lane_dark_since_thursday_still_flags_broken_on_sunday(tmp_path, monkeypatch):
    """The fix must not become a rubber stamp: a lane that missed Friday's REAL session
    (last wrote Thursday, market was open Friday) stays broken through the weekend."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    (tmp_path / "calendar.json").write_text('{"holidays": []}', encoding="utf-8")
    lane = tmp_path / "multi" / "shadow-ledger.jsonl"
    _touch_et(lane, "2026-08-20T19:32:00")   # Thursday -- Friday was a real open trading day

    monkeypatch.setattr(da, "_now_utc", lambda: datetime(2026, 8, 23, 4, 0, 0, tzinfo=timezone.utc))
    assert da._lane_missed_trading_day(lane) is True


def test_missing_lane_always_broken(tmp_path, monkeypatch):
    monkeypatch.setattr(da, "STATE", tmp_path)
    (tmp_path / "calendar.json").write_text('{"holidays": []}', encoding="utf-8")
    monkeypatch.setattr(da, "_now_utc", lambda: datetime(2026, 8, 23, 4, 0, 0, tzinfo=timezone.utc))
    assert da._lane_missed_trading_day(tmp_path / "futures" / "does-not-exist.json") is True


def test_weekday_morning_before_todays_session_not_flagged(tmp_path, monkeypatch):
    """Monday 08:00 ET, file last wrote Friday close -- today's session hasn't started yet,
    must not be broken."""
    monkeypatch.setattr(da, "STATE", tmp_path)
    (tmp_path / "calendar.json").write_text('{"holidays": []}', encoding="utf-8")
    lane = tmp_path / "futures" / "shadow-progress.json"
    _touch_et(lane, "2026-08-21T15:15:00")   # Friday close

    # 2026-08-24 12:00 UTC == 2026-08-24 08:00 ET, a Monday
    monkeypatch.setattr(da, "_now_utc", lambda: datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc))
    assert da._lane_missed_trading_day(lane) is False


def test_futures_desk_score_excludes_weekend_false_positive(tmp_path, monkeypatch):
    """End-to-end: assess_futures() must not carry the +40 BROKEN penalty for a Friday-close
    lane read on a Sunday."""
    import json as _json
    monkeypatch.setattr(da, "STATE", tmp_path)
    (tmp_path / "calendar.json").write_text('{"holidays": []}', encoding="utf-8")
    fut = tmp_path / "futures"
    fut.mkdir(parents=True)
    bar_doc = {"arming_bar": {"round_trips_needed": 20, "round_trips_have": 66,
                               "armable": True}}
    (fut / "shadow-progress.json").write_text(_json.dumps(bar_doc), encoding="utf-8")
    for lane in ("trader/heartbeat.json", "trader-broker/heartbeat.json",
                 "shadow-progress.json", "edge3-sim-progress.json", "ssr-shadow-progress.json"):
        _touch_et(fut / lane, "2026-08-21T15:15:00")
    (fut / "mirror-broker-orders.jsonl").write_text('{"ts_et": "x"}\n', encoding="utf-8")

    monkeypatch.setattr(da, "_now_utc", lambda: datetime(2026, 8, 23, 4, 0, 0, tzinfo=timezone.utc))
    a = da.assess_futures()
    assert a["broken"] == [], a["broken"]
    pts, why = da.score(a)
    assert not any("BROKEN" in w for w in why), why
