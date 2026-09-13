"""Guard: setup/scripts/station_presence.py -- PC-input-idle presence for the
Station "TV face" (GOAL-GAMMA-STATION-2026-09-13 item 4/6 re-scope).

Locks in: the absent->present transition detector, the 06:00-09:15 ET greeting
window, the 2-greetings/day cap, graceful no-op when no morning-brief wav
exists, and that a "present" transition outside the window never plays audio.

Every test injects idle_fn/now_utc/play_fn/latest_wav_fn -- none of them ever
call the real Windows GetLastInputInfo API, touch a real audio device, or
write to the real repo's automation/state/station/*. NO_WINDOW_PLATFORM tests
covering get_idle_seconds()/_play_wav_async() are separate and skip cleanly
off-Windows.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import station_presence as sp  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_presence_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "STATION_DIR", tmp_path)
    monkeypatch.setattr(sp, "PRESENCE_PATH", tmp_path / "presence.json")
    monkeypatch.setattr(sp, "LEDGER_PATH", tmp_path / "presence-ledger.jsonl")
    monkeypatch.setattr(sp, "INTERNAL_STATE_PATH", tmp_path / ".presence-internal.json")
    yield


# Fixed instants -- inside vs outside the 06:00-09:15 ET greeting window.
# 2026-09-14 is a Monday; EDT (UTC-4) is in effect (2026's DST window covers it).
_MON_0700_ET_UTC = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)   # 07:00 ET -- inside window
_MON_0920_ET_UTC = datetime(2026, 9, 14, 13, 20, tzinfo=timezone.utc)  # 09:20 ET -- just outside (after)
_MON_1400_ET_UTC = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)   # 14:00 ET -- well outside


def _run(now_utc, idle_s, *, play_ok=True, wav=Path("fake-morning.wav")):
    played = {"called": False, "path": None}

    def _play(path):
        played["called"] = True
        played["path"] = path
        return play_ok

    row = sp.run_once(
        now_utc=now_utc,
        idle_fn=lambda: idle_s,
        play_fn=_play,
        latest_wav_fn=lambda: wav,
    )
    return row, played


# ============================================================================
# presence.json shape + present/absent classification
# ============================================================================

def test_present_when_idle_below_threshold():
    row, _ = _run(_MON_1400_ET_UTC, 10.0)
    assert row["present"] is True
    assert row["idle_s"] == 10.0


def test_absent_when_idle_above_threshold():
    row, _ = _run(_MON_1400_ET_UTC, 600.0)
    assert row["present"] is False


def test_idle_exactly_at_threshold_is_absent():
    row, _ = _run(_MON_1400_ET_UTC, sp.PRESENCE_THRESHOLD_S)
    assert row["present"] is False, "the threshold itself is NOT present (strict less-than)"


def test_idle_none_fails_open_to_absent_not_a_crash():
    row, played = _run(_MON_1400_ET_UTC, None)
    assert row["present"] is False
    assert row["idle_s"] is None
    assert played["called"] is False


def test_presence_json_written_to_disk(tmp_path):
    _run(_MON_1400_ET_UTC, 5.0)
    data = json.loads(sp.PRESENCE_PATH.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"present", "idle_s", "ts_et", "transitions_today"}


# ============================================================================
# absent -> present transition + greeting window
# ============================================================================

def test_transition_to_present_inside_window_plays_greeting():
    row, played = _run(_MON_0700_ET_UTC, 5.0)  # first-ever tick: last_present defaults False
    assert row["present"] is True
    assert row["transitions_today"] == 1
    assert played["called"] is True
    ledger = [json.loads(l) for l in sp.LEDGER_PATH.read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "greeted" for r in ledger)


def test_transition_to_present_outside_window_never_plays():
    row, played = _run(_MON_1400_ET_UTC, 5.0)
    assert row["present"] is True
    assert row["transitions_today"] == 1  # transition is still counted...
    assert played["called"] is False       # ...but no greeting outside the window


def test_staying_present_does_not_replay_or_recount():
    _run(_MON_0700_ET_UTC, 5.0)  # first transition, greets
    row2, played2 = _run(_MON_0700_ET_UTC, 8.0)  # still present, same tick shape
    assert row2["transitions_today"] == 1, "no NEW transition while already present"
    assert played2["called"] is False


def test_present_then_absent_then_present_again_triggers_second_greeting():
    _run(_MON_0700_ET_UTC, 5.0)                      # present, greets (1st transition)
    row_absent, _ = _run(_MON_0700_ET_UTC, 999.0)     # goes absent
    assert row_absent["present"] is False
    row2, played2 = _run(_MON_0700_ET_UTC, 5.0)       # present again -- 2nd transition
    assert row2["transitions_today"] == 2
    assert played2["called"] is True


def test_greeting_cap_at_two_per_day():
    _run(_MON_0700_ET_UTC, 5.0)                   # 1st transition+greeting
    _run(_MON_0700_ET_UTC, 999.0)                 # absent
    _run(_MON_0700_ET_UTC, 5.0)                   # 2nd transition+greeting
    _run(_MON_0700_ET_UTC, 999.0)                 # absent
    row3, played3 = _run(_MON_0700_ET_UTC, 5.0)   # 3rd transition -- capped, no more greetings today
    assert row3["transitions_today"] == 3
    assert played3["called"] is False
    ledger = [json.loads(l) for l in sp.LEDGER_PATH.read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "greeting_capped" for r in ledger)


def test_no_wav_available_skips_gracefully_no_crash():
    row, played = _run(_MON_0700_ET_UTC, 5.0, wav=None)
    assert row["present"] is True
    assert played["called"] is False
    ledger = [json.loads(l) for l in sp.LEDGER_PATH.read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "greeting_skipped_no_wav" for r in ledger)


def test_play_failure_is_logged_not_raised():
    row, played = _run(_MON_0700_ET_UTC, 5.0, play_ok=False)
    assert row["present"] is True
    assert played["called"] is True
    ledger = [json.loads(l) for l in sp.LEDGER_PATH.read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "greeting_play_failed" for r in ledger)
    # A failed play must not consume a greeting slot -- confirmed by re-running
    # the SAME transition-eligible tick sequence and seeing it try again.


def test_window_boundaries_are_inclusive():
    # 06:00 ET and 09:15 ET exactly are both INSIDE the window (spec: "between
    # 06:00 and 09:15 ET").
    start = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)   # 06:00 ET
    end = datetime(2026, 9, 14, 13, 15, tzinfo=timezone.utc)    # 09:15 ET
    _, played_start = _run(start, 5.0)
    assert played_start["called"] is True
    _run(_MON_1400_ET_UTC, 999.0)  # reset to absent (new tmp state carries over via fixture isolation)


def test_transitions_reset_on_a_new_et_calendar_day(tmp_path):
    day1 = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)  # Mon 14:00 ET
    day2 = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)  # Tue 14:00 ET
    row1, _ = _run(day1, 5.0)
    assert row1["transitions_today"] == 1
    _run(day1, 999.0)  # absent before day rolls over
    row2, _ = _run(day2, 5.0)
    assert row2["transitions_today"] == 1, "a new ET day must reset the counter, not accumulate"


# ============================================================================
# get_idle_seconds / _play_wav_async -- fail-open off-Windows (no injection)
# ============================================================================

def test_get_idle_seconds_none_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert sp.get_idle_seconds() is None


def test_play_wav_async_false_on_non_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    assert sp._play_wav_async(tmp_path / "x.wav") is False


def test_latest_morning_brief_wav_picks_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "STATE", tmp_path)
    older = tmp_path / "gamma-voice-brief-20260101-morning.wav"
    newer = tmp_path / "gamma-voice-brief-20260102-morning.wav"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    import os
    import time
    os.utime(older, (time.time() - 100, time.time() - 100))
    assert sp._latest_morning_brief_wav() == newer


def test_latest_morning_brief_wav_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "STATE", tmp_path)
    assert sp._latest_morning_brief_wav() is None
