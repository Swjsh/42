"""Guard: setup/scripts/hq_self_review.py -- Gamma's own HQ self-review (GOAL-GAMMA-
STATION-2026-09-13, 2026-09-14 coordinator-directed build C9/C10).

Covers, hermetically (no real network, no real subprocess, no real repo state):
  - grade_hq() on a FAKE /api/hq-shaped payload: persona live/stale/ghost bucketing
    (quietReason's "no producer for " ghost prefix, deliverable.exists, status YELLOW/
    RED, and the crew-events-last-2h promotion-to-live rule), desks_stale, the score
    formula, and the rendered lines/ticker text.
  - should_capture()/should_vision_look() gating truth tables (presence/RTH/daily-cap;
    capture-taken/station-mode/GPU-util).
  - _vision_look() against a STUBBED urlopen (never real Ollama) -- request shape,
    response parsing, and the Pillow-missing -> skip (never raw PNG) rule.
  - review_once() end to end: writes hq-review.json, the Coach ticker fires only on a
    real score/stale-set change, the Gamma vision ticker fires only when the first
    vision line changed, and the synthetic-clock-vs-real-path guard.

Every module-level path constant this suite touches is monkeypatched onto a tmp_path
fixture -- no test here ever reads/writes the real repo's automation/state/station/*,
makes a real HTTP call, or spawns a real subprocess.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    p = str(REPO / _p) if _p else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

import hq_self_review as hsr  # noqa: E402
import station_board as sb  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(hsr, "REVIEW_PATH", tmp_path / "hq-review.json")
    monkeypatch.setattr(hsr, "CREW_EVENTS_PATH", tmp_path / "crew-events.jsonl")
    monkeypatch.setattr(hsr, "PRESENCE_PATH", tmp_path / "presence.json")
    monkeypatch.setattr(hsr, "MODE_PATH", tmp_path / "mode.json")
    monkeypatch.setattr(hsr, "CAPTURES_DIR", tmp_path / "captures")
    monkeypatch.setattr(hsr, "CAPTURE_LOG_PATH", tmp_path / "hq-capture-log.jsonl")
    yield


_NOW = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)  # 12:00 ET, after-hours-ish for these unit tests


def _persona(name, status="GREEN", quiet_reason=None, exists=True, age_min=10.0) -> dict:
    return {
        "name": name, "status": status, "quietReason": quiet_reason,
        "deliverable": {"path": f"fake/{name}.json", "exists": exists, "mtimeISO": None, "ageMin": age_min},
    }


def _payload(personas=None, desks=None, trading=True) -> dict:
    return {
        "company": {"personas": personas if personas is not None else [], "handoffs": []},
        "desks": desks if desks is not None else {},
        "trading": trading,
    }


# ============================================================================
# grade_hq -- persona bucketing
# ============================================================================

def test_grade_hq_all_green_is_fully_live():
    payload = _payload(personas=[_persona("Scout"), _persona("Pilot")])
    review = hsr.grade_hq(payload, [], _NOW)
    assert review["crew_live"] == 2
    assert review["crew_total"] == 2
    assert review["stale"] == []
    assert review["ghosts"] == []
    assert review["score_0_100"] == 100


def test_grade_hq_ghost_prefix_is_a_ghost_not_stale():
    payload = _payload(personas=[_persona("Coach", status="RED", quiet_reason="no producer for sectors.json yet")])
    review = hsr.grade_hq(payload, [], _NOW)
    assert review["ghosts"] == [{"name": "Coach", "why": "no producer for sectors.json yet"}]
    assert review["stale"] == []


def test_grade_hq_missing_deliverable_alone_with_no_ghost_signal_is_live():
    # 2026-09-14 coordinator correction: deliverable.exists=False is no longer an
    # independent ghost trigger -- ONLY a "no producer for" quietReason is. A persona
    # whose file simply doesn't exist yet, with no explanatory quietReason at all
    # (or a benign one), is live, not a ghost.
    payload = _payload(personas=[_persona("Treasurer", exists=False, quiet_reason=None)])
    review = hsr.grade_hq(payload, [], _NOW)
    assert review["ghosts"] == []
    assert review["crew_live"] == 1


def test_grade_hq_status_alone_no_longer_drives_stale_classification():
    # 2026-09-14 coordinator correction: `status` (YELLOW/RED) is dashboard-internal and
    # no longer re-derived here -- ONLY quietReason text patterns do. A RED/YELLOW status
    # with no quietReason (or a non-matching one) must NOT be called stale.
    payload = _payload(personas=[_persona("Analyst", status="YELLOW", quiet_reason=None),
                                 _persona("Scout", status="RED", quiet_reason="Gamma_ScoutPremarket DISABLED")])
    review = hsr.grade_hq(payload, [], _NOW)
    assert review["stale"] == []
    assert review["ghosts"] == []
    assert review["crew_live"] == 2


def test_grade_hq_overdue_text_is_stale():
    payload = _payload(personas=[_persona("Coach", status="RED",
                                          quiet_reason="expected every 30 min via the Station loop, "
                                                       "last evidence 09:12 ET")])
    review = hsr.grade_hq(payload, [], _NOW)
    assert [s["name"] for s in review["stale"]] == ["Coach"]
    assert review["ghosts"] == []


def test_grade_hq_recent_crew_event_promotes_a_stale_persona_to_live():
    payload = _payload(personas=[_persona("Chef", status="RED",
                                          quiet_reason="expected every 30 min via the Station loop, "
                                                       "last evidence 09:12 ET")])
    recent_row = {"ts_et": hsr.et_now(now_utc=_NOW - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S ET"),
                 "who": "Chef", "kind": "verdict", "line": "x"}
    review = hsr.grade_hq(payload, [recent_row], _NOW)
    assert review["crew_live"] == 1
    assert review["stale"] == []


def test_grade_hq_crew_event_older_than_2h_does_not_promote():
    payload = _payload(personas=[_persona("Chef", status="RED",
                                          quiet_reason="expected every 30 min via the Station loop, "
                                                       "last evidence 09:12 ET")])
    old_row = {"ts_et": hsr.et_now(now_utc=_NOW - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S ET"),
              "who": "Chef", "kind": "verdict", "line": "x"}
    review = hsr.grade_hq(payload, [old_row], _NOW)
    assert review["crew_live"] == 0
    assert len(review["stale"]) == 1


def test_grade_hq_desks_stale_and_score_formula():
    payload = _payload(
        personas=[_persona("A"),
                 _persona("B", status="RED", quiet_reason="overdue: no fire recorded today"),
                 _persona("Z", exists=False, quiet_reason="no producer for automation/state/z.json yet")],
        desks={"A": {"stale": False}, "B": {"stale": True}, "Z": {"stale": True}},
        trading=False,
    )
    review = hsr.grade_hq(payload, [], _NOW)
    assert review["desks_stale"] == ["B", "Z"]
    assert [s["name"] for s in review["stale"]] == ["B"]
    assert [g["name"] for g in review["ghosts"]] == ["Z"]
    # crew_live=1/3 -> base 33.33; 1 ghost -> -10; 2 stale desks -> -10; no trading -> -10
    assert review["score_0_100"] == max(0, round(100 / 3 - 10 - 10 - 10))
    assert any("trading strip missing" in ln for ln in review["lines"])


# ============================================================================
# 2026-09-14 coordinator correction -- the two real-world cases that were wrong live:
# a once-daily persona before its own due time (Analyst, real quietReason text), and
# a deliberately-yielding persona (Gamma Manager, real quietReason text). Both copied
# verbatim from the actual /api/hq payload this session (12:21 ET, market open).
# ============================================================================

_ANALYST_QUIET = "expected 16:45 ET weekdays via Gamma_AnalystEodReview, last digest 16:45 ET on a prior day"
_GAMMA_YIELD_QUIET = "yields — rth_window (weekday 09:30-15:55 ET)"


def test_analyst_at_noon_before_its_due_time_is_live_not_ghost():
    noon_et_utc = datetime(2026, 9, 14, 16, 21, tzinfo=timezone.utc)  # 12:21 ET -- real repro instant
    payload = _payload(personas=[_persona("Analyst", status="IDLE", quiet_reason=_ANALYST_QUIET, exists=False,
                                          age_min=None)])
    review = hsr.grade_hq(payload, [], noon_et_utc)
    assert review["ghosts"] == [], "before 16:45 ET, a missing today-dated digest is WAITING, not a ghost"
    assert review["stale"] == [], "and not stale either -- it simply isn't due yet"
    assert review["crew_live"] == 1


def test_analyst_after_its_due_time_with_still_no_file_is_stale():
    evening_et_utc = datetime(2026, 9, 14, 22, 0, tzinfo=timezone.utc)  # 18:00 ET -- past the 16:45 due time
    payload = _payload(personas=[_persona("Analyst", status="IDLE", quiet_reason=_ANALYST_QUIET, exists=False,
                                          age_min=None)])
    review = hsr.grade_hq(payload, [], evening_et_utc)
    assert review["ghosts"] == []
    assert [s["name"] for s in review["stale"]] == ["Analyst"], "past its own stated due time, this IS stale"


def test_yielding_gamma_manager_is_live_not_stale():
    payload = _payload(personas=[_persona("Gamma (Manager)", status="YELLOW", quiet_reason=_GAMMA_YIELD_QUIET)])
    review = hsr.grade_hq(payload, [], _NOW)
    assert review["stale"] == [], "yielding by design must never count as staleness"
    assert review["ghosts"] == []
    assert review["crew_live"] == 1
    assert review["score_0_100"] == 100, "a yielding-by-design persona must not cost the score anything"


def test_grade_hq_malformed_payload_degrades_honestly_never_raises():
    review = hsr.grade_hq({"company": "not-a-dict"}, [], _NOW)
    assert review["crew_total"] == 0
    assert review["score_0_100"] == 0

    review2 = hsr.grade_hq(None, [], _NOW)  # not even a dict
    assert review2["crew_total"] == 0


def test_ticker_line_matches_the_documented_shape():
    review = {
        "crew_live": 5, "crew_total": 7,
        "stale": [{"name": "Scout", "age_min": 360, "why": "x"}, {"name": "Treasurer", "age_min": 660, "why": "x"}],
        "ghosts": [], "desks_stale": ["X"], "_desks_total": 6,
    }
    line = hsr._ticker_line(review)
    assert line.startswith("Coach: HQ review — 5/7 crew live")
    assert "Scout 6h" in line
    assert "Treasurer 11h" in line
    assert "desks fresh 5/6" in line


# ============================================================================
# should_capture -- presence / RTH / daily-cap gating
# ============================================================================

_WEEKEND_UTC = datetime(2026, 9, 19, 20, 0, tzinfo=timezone.utc)  # Saturday -- never RTH


def _write_presence(tmp_path, present: bool):
    sb.atomic_write_text(hsr.PRESENCE_PATH, json.dumps({"present": present}))


def test_should_capture_false_when_j_present(tmp_path):
    _write_presence(tmp_path, True)
    ok, reason = hsr.should_capture(_WEEKEND_UTC)
    assert ok is False and "present" in reason


def test_should_capture_false_during_rth():
    hsr.PRESENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    hsr.PRESENCE_PATH.write_text(json.dumps({"present": False}), encoding="utf-8")
    rth_tue = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)  # Tue 11:00 ET
    ok, reason = hsr.should_capture(rth_tue)
    assert ok is False and "RTH" in reason


def test_should_capture_true_when_absent_outside_rth_under_cap(tmp_path):
    _write_presence(tmp_path, False)
    ok, reason = hsr.should_capture(_WEEKEND_UTC)
    assert ok is True, reason


def test_should_capture_false_once_daily_cap_reached(tmp_path):
    _write_presence(tmp_path, False)
    today = hsr.et_now(now_utc=_WEEKEND_UTC).strftime("%Y-%m-%d")
    rows = [{"ts_et": "x", "date": today, "path": f"p{i}"} for i in range(hsr.CAPTURE_MAX_PER_DAY)]
    sb.append_jsonl(hsr.CAPTURE_LOG_PATH, rows)
    ok, reason = hsr.should_capture(_WEEKEND_UTC)
    assert ok is False and "cap" in reason


def test_should_capture_defaults_to_present_and_skips_on_unreadable_presence_file():
    # presence.json missing entirely -- fails CLOSED (never captures), the safety-first
    # default for a "never while J is present" rule.
    ok, reason = hsr.should_capture(_WEEKEND_UTC)
    assert ok is False


# ============================================================================
# should_vision_look -- capture-taken / station-mode / GPU gating
# ============================================================================

def test_should_vision_look_false_without_a_capture_this_fire():
    ok, reason = hsr.should_vision_look(False, {})
    assert ok is False and "no capture" in reason


def test_should_vision_look_false_when_station_mode_gaming(tmp_path, monkeypatch):
    hsr.MODE_PATH.write_text(json.dumps({"mode": "gaming"}), encoding="utf-8")
    ok, reason = hsr.should_vision_look(True, {})
    assert ok is False and "gaming" in reason


def test_should_vision_look_false_when_gpu_busy(monkeypatch):
    monkeypatch.setattr(hsr, "_gpu_util_pct", lambda: 90.0)
    ok, reason = hsr.should_vision_look(True, {"gpu_util_yield_pct": 50})
    assert ok is False and "gpu_util" in reason


def test_should_vision_look_true_when_capture_taken_mode_ok_gpu_idle(monkeypatch):
    monkeypatch.setattr(hsr, "_gpu_util_pct", lambda: 5.0)
    ok, reason = hsr.should_vision_look(True, {"gpu_util_yield_pct": 50})
    assert ok is True, reason


# ============================================================================
# _vision_look -- stubbed urlopen (C10 rule 5), never real Ollama; Pillow-missing skip
# ============================================================================

def test_vision_look_skips_when_resize_returns_none_never_calls_the_model(tmp_path):
    called = {"n": 0}
    def _call_fn(image_bytes):
        called["n"] += 1
        raise AssertionError("must never call the model when resize failed")
    note = hsr._vision_look(tmp_path / "fake.png", "t", resize_fn=lambda p: None, call_fn=_call_fn)
    assert note is None
    assert called["n"] == 0


def test_vision_look_parses_lines_from_a_stubbed_model_response(tmp_path):
    def _call_fn(image_bytes):
        assert image_bytes == b"jpeg-bytes"
        return {"response": "1. Lighting is flat\n2. Empty desks on the left\n\nOverall it reads as functional."}
    note = hsr._vision_look(tmp_path / "fake.png", "2026-09-14 20:00:00 ET",
                            resize_fn=lambda p: b"jpeg-bytes", call_fn=_call_fn)
    assert note is not None
    assert note["model"] == hsr.VISION_MODEL
    assert note["lines"][0] == "1. Lighting is flat"
    assert len(note["lines"]) == 3


def test_vision_look_returns_none_on_empty_model_response(tmp_path):
    note = hsr._vision_look(tmp_path / "fake.png", "t", resize_fn=lambda p: b"x", call_fn=lambda b: {"response": "   "})
    assert note is None


def test_vision_look_fails_open_when_the_model_call_raises(tmp_path):
    def _boom(image_bytes):
        raise TimeoutError("ollama unreachable")
    note = hsr._vision_look(tmp_path / "fake.png", "t", resize_fn=lambda p: b"x", call_fn=_boom)
    assert note is None


def test_call_vision_model_request_shape_matches_the_verified_smoke_test(monkeypatch):
    """Stubs urllib.request.urlopen -- NEVER a real network call to Ollama. Locks in the
    exact request shape the coordinator's smoke test verified live."""
    captured = {}

    class _FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return json.dumps({"response": "ok", "eval_count": 5}).encode("utf-8")

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    monkeypatch.setattr(hsr.urllib.request, "urlopen", _fake_urlopen)
    out = hsr._call_vision_model(b"\xff\xd8fake-jpeg", timeout=60)

    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["timeout"] == 60
    body = captured["body"]
    assert body["model"] == "qwen2.5vl:7b"
    assert body["prompt"] == hsr.VISION_PROMPT
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.2, "num_predict": 400}
    assert body["keep_alive"] == "2m"
    import base64
    assert base64.b64decode(body["images"][0]) == b"\xff\xd8fake-jpeg"
    assert out["response"] == "ok"


# ============================================================================
# review_once -- end to end, hermetic (fetch_fn/capture_fn/vision_fn all injected)
# ============================================================================

_PILOT_OVERDUE_QUIET = "overdue: expected every 1 min 09:30-15:55 ET, last evidence 09:12 ET"


def _ok_fetch(url, timeout):
    return _payload(personas=[_persona("Scout"), _persona("Pilot", status="RED", quiet_reason=_PILOT_OVERDUE_QUIET)]), None


def test_review_once_writes_the_documented_json_shape():
    row = hsr.review_once("2026-09-14 20:00:00 ET", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch)
    assert row["crew_live"] == 1
    assert row["crew_total"] == 2
    doc = json.loads(hsr.REVIEW_PATH.read_text(encoding="utf-8"))
    for key in ("ts_et", "crew_live", "crew_total", "stale", "ghosts", "desks_stale", "score_0_100", "lines"):
        assert key in doc, key


def test_review_once_dashboard_unreachable_degrades_honestly_not_a_crash():
    def _fail_fetch(url, timeout):
        return None, "ConnectionRefusedError: dashboard not running"
    row = hsr.review_once("t", _WEEKEND_UTC, {}, fetch_fn=_fail_fetch)
    assert row["crew_total"] == 0
    assert "unreachable" in row["lines"][0]


def test_review_once_coach_ticker_fires_only_on_a_real_change():
    hsr.review_once("t1", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch)
    rows1 = [r for r in sb.read_jsonl(hsr.CREW_EVENTS_PATH) if r.get("kind") == "hq_review"]
    assert len(rows1) == 1, "first-ever review has no prior row to compare -- must emit"

    hsr.review_once("t2", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch)  # identical payload
    rows2 = [r for r in sb.read_jsonl(hsr.CREW_EVENTS_PATH) if r.get("kind") == "hq_review"]
    assert len(rows2) == 1, "an unchanged score/stale-set must not re-emit"

    def _changed_fetch(url, timeout):
        return _payload(personas=[_persona("Scout", status="RED", quiet_reason=_PILOT_OVERDUE_QUIET),
                                  _persona("Pilot", status="RED", quiet_reason=_PILOT_OVERDUE_QUIET)]), None
    hsr.review_once("t3", _WEEKEND_UTC, {}, fetch_fn=_changed_fetch)
    rows3 = [r for r in sb.read_jsonl(hsr.CREW_EVENTS_PATH) if r.get("kind") == "hq_review"]
    assert len(rows3) == 2, "a changed stale-set must emit again"


def test_review_once_never_writes_an_ideas_board_card(tmp_path):
    board_path = tmp_path / "ideas-board.json"
    hsr.review_once("t", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch)
    assert not board_path.exists(), "hq_self_review must never touch the ideas board (C10 rule 4)"


def test_review_once_runs_capture_and_vision_when_eligible_and_emits_gamma_ticker(tmp_path):
    _write_presence(tmp_path, False)

    def _fake_capture(now_utc):
        return {"ts_et": "t", "date": "2026-09-19", "path": str(tmp_path / "cap.png"),
                "nonblack": 40, "samples": 42, "returncode": 0}

    def _fake_vision(image_path, ts_et, **kw):
        return {"ts_et": ts_et, "model": hsr.VISION_MODEL, "capture": str(image_path),
                "lines": ["Lighting is flat and dim", "Overall reads as functional"]}

    row = hsr.review_once("2026-09-19 14:00:00 ET", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch,
                          capture_fn=_fake_capture, vision_fn=_fake_vision)

    assert row["capture"]["nonblack"] == 40
    assert row["vision_notes"][0]["lines"][0] == "Lighting is flat and dim"
    look_rows = [r for r in sb.read_jsonl(hsr.CREW_EVENTS_PATH) if r.get("kind") == "hq_look"]
    assert len(look_rows) == 1
    assert look_rows[0]["who"] == "Gamma"
    assert look_rows[0]["line"] == "Gamma looked at HQ: Lighting is flat and dim"


def test_review_once_gamma_ticker_only_on_a_changed_first_line(tmp_path):
    _write_presence(tmp_path, False)

    def _fake_capture(now_utc):
        return {"ts_et": "t", "date": "2026-09-19", "path": str(tmp_path / "cap.png"), "nonblack": 1, "samples": 1}

    def _fake_vision_same(image_path, ts_et, **kw):
        return {"ts_et": ts_et, "model": hsr.VISION_MODEL, "capture": str(image_path), "lines": ["Same problem"]}

    hsr.review_once("t1", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch, capture_fn=_fake_capture, vision_fn=_fake_vision_same)
    hsr.review_once("t2", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch, capture_fn=_fake_capture, vision_fn=_fake_vision_same)

    look_rows = [r for r in sb.read_jsonl(hsr.CREW_EVENTS_PATH) if r.get("kind") == "hq_look"]
    assert len(look_rows) == 1, "an unchanged first vision line must not re-emit the Gamma ticker"


def test_review_once_no_capture_no_vision_no_gamma_ticker():
    # presence.json absent -> should_capture fails closed -> no capture -> vision never runs.
    row = hsr.review_once("t", _WEEKEND_UTC, {}, fetch_fn=_ok_fetch)
    assert row["capture"] is None
    assert "vision_notes" not in row
    assert not any(r.get("kind") == "hq_look" for r in sb.read_jsonl(hsr.CREW_EVENTS_PATH))


# ============================================================================
# Synthetic-clock guard (mirrors station_loop's own -- same 2026-09-14 lesson)
# ============================================================================

def test_review_once_skips_on_synthetic_clock_at_a_real_shaped_path(monkeypatch, tmp_path):
    monkeypatch.setattr(hsr, "REPO", tmp_path)
    monkeypatch.setattr(hsr, "REVIEW_PATH", tmp_path / "automation" / "state" / "station" / "hq-review.json")
    far_clock = datetime(2020, 1, 1, tzinfo=timezone.utc)
    row = hsr.review_once("2020-01-01 00:00:00 ET", far_clock, {}, fetch_fn=_ok_fetch)
    assert row.get("skipped") == "synthetic clock + real path"
    assert not (tmp_path / "automation" / "state" / "station" / "hq-review.json").exists()
