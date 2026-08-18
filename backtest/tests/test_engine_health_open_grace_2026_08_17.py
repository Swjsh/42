"""Guard: the 09:30:02 false-RED -- a session can only have been dark as long as it is OPEN.

THE INCIDENT (root-caused 2026-08-17; J: "I don't wanna wake up tomorrow and see a Discord
message of the engine being red"). The 15-min health beacon's 09:30 fire lands ~2 seconds
after the bell, BEFORE the 1-min heartbeat's first tick (~09:30:18+). check_engine_core then
measured staleness back to YESTERDAY'S 15:55:04 EOD tick and pinged J:

    "ENGINE STALE 1055.0m (>8m) during RTH -- last safe tick 1055.0m ago (15:55:04)"

three days running (08-11/12/13), each queued at 13:30:02Z sharp, each BYTE-IDENTICAL --
because 15:55:04 -> 09:30:02 is a CONSTANT 1055-minute gap, which is also why it read as a
"frozen value" to the spam investigation. Each RED was true for under 90 seconds and
self-cleared silently at the 09:45 beacon. An alarm that wakes J for nothing is an alarm
that gets ignored the day it is real.

WATCHER_OPEN_GRACE_MIN killed this exact class for watcher_feed in July; the fix never
landed on check_engine_core / check_sight_beacon (trap 5: land on ALL call sites).

THE CLAMP: effective RTH staleness = min(raw_age, minutes_since_open). Universally safe:
  * 09:30:02, last tick yesterday 15:55 -> eff 0.03m -> GREEN "awaiting first tick"
  * 09:39, STILL no tick (the real 2026-08-14 box-sleep dark open) -> eff 9m -> RED
  * 14:00, last tick 13:00 (mid-day death) -> eff 60m unchanged -> RED
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("engine_health", REPO / "setup" / "scripts" / "engine_health.py")
eh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eh)


def _write_core(tmp_path, ts_et: str, account: str = "safe"):
    p = tmp_path / "core-decisions.jsonl"
    p.write_text(json.dumps({"account": account, "ts_et": ts_et}) + "\n", encoding="utf-8")
    return p


def _et(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s)


# ---- the clamp itself -------------------------------------------------------

def test_clamp_is_a_property_of_session_open_not_of_the_data():
    et = _et(2026, 8, 18, 9, 30, 2)
    assert eh._rth_staleness_min(1055.0, et) < 0.1          # first seconds: ~0
    et2 = _et(2026, 8, 18, 9, 39, 0)
    assert eh._rth_staleness_min(1064.0, et2) == pytest.approx(9.0)   # dark open -> real
    et3 = _et(2026, 8, 18, 14, 0, 0)
    assert eh._rth_staleness_min(60.0, et3) == 60.0          # mid-day death untouched


# ---- check_engine_core ------------------------------------------------------

def test_0930_02_with_yesterdays_eod_tick_is_NOT_red(tmp_path, monkeypatch):
    """RED-PROOF of the exact 08-11/12/13 ping: last tick 15:55:04 yesterday, beacon fires
    09:30:02. Old code: RED 'ENGINE STALE 1055.0m'. New: GREEN awaiting first tick."""
    monkeypatch.setattr(eh, "STATE", tmp_path)
    _write_core(tmp_path, "2026-08-17T15:55:04")
    r = eh.check_engine_core("heartbeat_safe", "safe", True, _et(2026, 8, 18, 9, 30, 2))
    assert r["status"] == "GREEN", r
    assert "awaiting first tick" in r["detail"]


def test_dark_open_still_reds_once_budget_elapses(tmp_path, monkeypatch):
    """The 2026-08-14 box-sleep shape (first tick 09:46) MUST still alarm: by 09:39 the
    session has been open past the 8m budget with no tick -> RED. The grace must never
    become amnesty for a genuinely dark open."""
    monkeypatch.setattr(eh, "STATE", tmp_path)
    _write_core(tmp_path, "2026-08-13T15:55:04")
    r = eh.check_engine_core("heartbeat_safe", "safe", True, _et(2026, 8, 14, 9, 39, 0))
    assert r["status"] == "RED", r
    assert "ENGINE STALE" in r["detail"]


def test_midday_death_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    _write_core(tmp_path, "2026-08-18T13:00:03")
    r = eh.check_engine_core("heartbeat_safe", "safe", True, _et(2026, 8, 18, 14, 0, 0))
    assert r["status"] == "RED", r


def test_healthy_ticking_engine_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    _write_core(tmp_path, "2026-08-18T10:59:03")
    r = eh.check_engine_core("heartbeat_safe", "safe", True, _et(2026, 8, 18, 11, 0, 0))
    assert r["status"] == "GREEN", r


# ---- check_sight_beacon (the '+2 more' sibling in the same pings) -----------

def test_beacon_first_seconds_of_session_is_not_blind(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    yest = datetime(2026, 8, 17, 20, 0, 0, tzinfo=timezone.utc)   # 16:00 ET yesterday
    (tmp_path / "sight-beacon.json").write_text(
        json.dumps({"ok": True, "ts_utc": yest.isoformat(), "spy": 775.0,
                    "ribbon_stack": "BEAR", "data_source": "alpaca_rest_iex"}),
        encoding="utf-8")
    now_utc = datetime(2026, 8, 18, 13, 30, 2, tzinfo=timezone.utc)  # 09:30:02 ET
    r = eh.check_sight_beacon(True, now_utc)
    assert r["status"] == "GREEN", r
    assert "awaiting first beacon write" in r["detail"]


def test_beacon_dark_open_still_reds(tmp_path, monkeypatch):
    monkeypatch.setattr(eh, "STATE", tmp_path)
    yest = datetime(2026, 8, 17, 20, 0, 0, tzinfo=timezone.utc)
    (tmp_path / "sight-beacon.json").write_text(
        json.dumps({"ok": True, "ts_utc": yest.isoformat(), "spy": 775.0,
                    "ribbon_stack": "BEAR", "data_source": "alpaca_rest_iex"}),
        encoding="utf-8")
    now_utc = datetime(2026, 8, 18, 13, 39, 30, tzinfo=timezone.utc)  # 09:39:30 ET
    r = eh.check_sight_beacon(True, now_utc)
    assert r["status"] == "RED", r


def test_beacon_ok_false_is_still_immediately_red(tmp_path, monkeypatch):
    """The grace clamps STALENESS only. A beacon that says ok=False is a live fetch
    failure and must alarm instantly, open-grace or not."""
    monkeypatch.setattr(eh, "STATE", tmp_path)
    now_utc = datetime(2026, 8, 18, 13, 30, 10, tzinfo=timezone.utc)
    (tmp_path / "sight-beacon.json").write_text(
        json.dumps({"ok": False, "ts_utc": now_utc.isoformat(), "spy": None,
                    "ribbon_stack": "?", "data_source": "?"}), encoding="utf-8")
    r = eh.check_sight_beacon(True, now_utc)
    assert r["status"] == "RED", r


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
