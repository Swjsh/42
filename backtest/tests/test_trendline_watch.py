"""Guards for the WS8 trendline visibility bridge (2026-08-01).

Pins the load-bearing contracts of backtest/autoresearch/trendline_watch.py +
its two wire points (trendline_engine.main hook, daily_brief morning line):

  1. ACTIVE means non-BROKEN: n_active + active_lines exclude BROKEN lines.
  2. nearest_active picks the minimum-distance ACTIVE line (never a BROKEN one),
     with correct side (above/below) and distance.
  3. detect_events mines status TRANSITIONS -- INTACT->BROKEN = "break",
     INTACT->TESTING = "retest"; a line FIRST SEEN already-BROKEN emits nothing
     (no stale re-announcements); last_break is the NEWEST break.
  4. ONE WRITER PER STATE FILE: refresh() writes trendline-watch.json and never
     creates/writes live-watch.json (WS7's file -- merge is READ-side, per the
     fleet write/read race lesson 2026-07-31).
  5. premarket_line always carries the as-of stamp (RTH-only producer -> the
     08:45 brief must never imply freshness) and degrades honestly on empty.
  6. The engine hook exists AND is fail-open: trendline_engine.main's call to
     trendline_watch.refresh is inside a try/except (AST-verified, not grepped).
  7. daily_brief._trendline_morning_line consumes payload["premarket_line"]
     verbatim when present and degrades to explicit no-data phrasing on a
     missing/garbled file; compose_morning_text includes the line.

RED-proof protocol: each contract was verified to FAIL against a deliberately
broken input/mutation before shipping (see WS8 session notes -- e.g. counting
BROKEN lines as active flips test 1; dropping the try/except flips test 6).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))

import trendline_watch as tw  # noqa: E402

_DB_PATH = REPO / "setup" / "scripts" / "daily_brief.py"
_spec = importlib.util.spec_from_file_location("daily_brief_under_tw_test", _DB_PATH)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


# ------------------------------------------------------------------ fixtures
def _live_state(lines):
    return {"date_et": "2026-07-31", "ts_et": "2026-07-31T16:00:03",
            "count": len(lines), "trendlines": lines}


def _line(kind="support", family="wick", status="INTACT", cv=746.71, last_close=746.79,
          tier="primary", respect=33):
    return {"kind": kind, "anchor_family": family, "tier": tier, "status": status,
            "current_value": cv, "break_level": cv, "respect_count": respect,
            "violations": 0, "slope_per_bar": 0.09, "last_close": last_close,
            "summary": f"{kind.upper()} [{family.upper()}] now {cv} | {status}"}


def _log_row(ts, kind="resistance", family="wick", status="INTACT", cv=746.37,
             a_et="07-31 13:35", b_et="07-31 14:20", tier="primary"):
    return {"date_et": ts[:10], "ts_et": ts, "kind": kind, "anchor_family": family,
            "tier": tier, "status": status, "current_value": cv,
            "a_et": a_et, "b_et": b_et, "summary": f"{kind} [{family}] {status} @ {cv}"}


# ------------------------------------------------------------------ 1. active
def test_active_excludes_broken():
    ls = _live_state([
        _line(status="INTACT", cv=746.71),
        _line(kind="resistance", status="BROKEN", cv=746.37),
        _line(family="body", status="TESTING", cv=746.79),
    ])
    p = tw.build_watch_payload(ls, [], "2026-08-01T12:00:00")
    assert p["n_total"] == 3
    assert p["n_active"] == 2, "BROKEN lines must not count as active"
    assert all(ln["status"] in ("INTACT", "TESTING") for ln in p["active_lines"])
    assert len(p["all_lines"]) == 3, "all_lines keeps the full picture incl. BROKEN"


# ------------------------------------------------------------------ 2. nearest
def test_nearest_active_min_distance_and_side_never_broken():
    ls = _live_state([
        _line(status="INTACT", cv=745.00, last_close=746.79),           # $1.79 below
        _line(kind="resistance", status="BROKEN", cv=746.80),           # $0.01 -- but BROKEN
        _line(kind="resistance", family="body", status="TESTING", cv=747.10),  # $0.31 above
    ])
    p = tw.build_watch_payload(ls, [], "2026-08-01T12:00:00")
    near = p["nearest_active"]
    assert near is not None
    assert near["current_value"] == 747.10, "BROKEN $0.01 line must never win nearest"
    assert near["side"] == "above"
    assert abs(near["distance_dollars"] - 0.31) < 1e-9
    # Caught live on first real run ("nearest None support"): _nearest_active reads
    # SLIMMED dicts, so it must read "flavor", not the pre-slim "anchor_family".
    assert near["flavor"] == "body", f"nearest flavor must survive slimming, got {near['flavor']!r}"


def test_nearest_none_when_no_close_or_no_active():
    assert tw.build_watch_payload(None, [], "x")["nearest_active"] is None
    only_broken = _live_state([_line(status="BROKEN")])
    assert tw.build_watch_payload(only_broken, [], "x")["nearest_active"] is None


# ------------------------------------------------------------------ 3. events
def test_detect_events_transitions_only():
    rows = [
        _log_row("2026-07-31T10:00:03", status="INTACT"),
        _log_row("2026-07-31T10:05:03", status="INTACT"),
        _log_row("2026-07-31T10:10:03", status="TESTING"),   # INTACT->TESTING = retest
        _log_row("2026-07-31T10:15:03", status="BROKEN"),    # TESTING->BROKEN = break
        _log_row("2026-07-31T10:20:03", status="BROKEN"),    # no duplicate
        # a DIFFERENT line first seen already-BROKEN -> NO event
        _log_row("2026-07-31T10:20:03", kind="support", family="body", status="BROKEN",
                 a_et="07-30 11:00", b_et="07-30 15:00"),
    ]
    evs = tw.detect_events(rows)
    assert [e["type"] for e in evs] == ["retest", "break"], evs
    assert evs[-1]["ts_et"] == "2026-07-31T10:15:03"
    p = tw.build_watch_payload(_live_state([]), rows, "2026-08-01T12:00:00")
    assert p["last_break"] and p["last_break"]["ts_et"] == "2026-07-31T10:15:03"
    assert p["last_retest"] and p["last_retest"]["ts_et"] == "2026-07-31T10:10:03"


def test_last_break_is_newest():
    rows = [
        _log_row("2026-07-30T11:00:03", status="INTACT"),
        _log_row("2026-07-30T11:05:03", status="BROKEN", cv=740.00),
        _log_row("2026-07-31T14:00:03", kind="support", status="INTACT", cv=745.5,
                 a_et="07-31 10:00", b_et="07-31 12:00"),
        _log_row("2026-07-31T14:05:03", kind="support", status="BROKEN", cv=745.5,
                 a_et="07-31 10:00", b_et="07-31 12:00"),
    ]
    p = tw.build_watch_payload(_live_state([]), rows, "x")
    assert p["last_break"]["ts_et"] == "2026-07-31T14:05:03"
    assert p["last_break"]["level"] == 745.5


# ------------------------------------------------------------------ 4. one writer
def test_refresh_writes_watch_and_never_live_watch(tmp_path, monkeypatch):
    monkeypatch.setattr(tw, "LIVE_STATE", tmp_path / "trendlines-live.json")
    monkeypatch.setattr(tw, "LOG", tmp_path / "trendline-log.jsonl")
    monkeypatch.setattr(tw, "WATCH", tmp_path / "trendline-watch.json")
    (tmp_path / "trendlines-live.json").write_text(
        json.dumps(_live_state([_line()])), encoding="utf-8")
    (tmp_path / "trendline-log.jsonl").write_text(
        json.dumps(_log_row("2026-07-31T10:00:03")) + "\n", encoding="utf-8")
    payload = tw.refresh(now_et_iso="2026-08-01T12:00:00")
    on_disk = json.loads((tmp_path / "trendline-watch.json").read_text(encoding="utf-8"))
    assert on_disk["n_active"] == payload["n_active"] == 1
    assert on_disk["premarket_line"] == payload["premarket_line"]
    assert not (tmp_path / "live-watch.json").exists(), \
        "one writer per file: trendline_watch must NEVER create WS7's live-watch.json"
    # merge point is documented in the payload itself for WS7 to find
    assert "live-watch.json" in on_disk["_merge_note"]


def test_refresh_fail_open_on_missing_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(tw, "LIVE_STATE", tmp_path / "absent-live.json")
    monkeypatch.setattr(tw, "LOG", tmp_path / "absent-log.jsonl")
    monkeypatch.setattr(tw, "WATCH", tmp_path / "trendline-watch.json")
    payload = tw.refresh(now_et_iso="2026-08-01T12:00:00")
    assert payload["n_total"] == 0 and payload["n_active"] == 0
    assert payload["premarket_line"] == "Trendlines: none on file yet."
    assert (tmp_path / "trendline-watch.json").exists()


# ------------------------------------------------------------------ 5. line
def test_premarket_line_carries_asof_and_nearest():
    ls = _live_state([_line(status="TESTING", cv=746.71, last_close=746.79)])
    p = tw.build_watch_payload(ls, [
        _log_row("2026-07-31T10:10:03", status="INTACT"),
        _log_row("2026-07-31T10:15:03", status="BROKEN", cv=746.37),
    ], "2026-08-01T12:00:00")
    line = p["premarket_line"]
    assert "1 active" in line
    assert "as of 07-31 16:00" in line, "RTH-only producer: as-of stamp is mandatory"
    assert "746.71" in line and "below close" in line
    assert "wick support" in line, "spoken line must carry the flavor (bodies-XOR-wicks rule)"
    assert "None" not in line, "a None leaking into the spoken line = slimming/field bug"
    assert "last break" in line and "746.37" in line
    assert len(line.split()) <= 40, "morning brief is word-capped at 140 total -- stay lean"


def test_premarket_line_empty_state():
    p = tw.build_watch_payload(None, [], "2026-08-01T12:00:00")
    assert p["premarket_line"] == "Trendlines: none on file yet."


# ------------------------------------------------------------------ 6. engine hook
def test_engine_hook_present_and_fail_open():
    """AST-verify trendline_engine.main calls trendline_watch.refresh INSIDE a
    try/except -- the visibility bridge must never be able to break the 5-min
    production fire. Grep-free: parses the actual tree."""
    import ast
    src = (REPO / "backtest" / "autoresearch" / "trendline_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    main_fn = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    hook_in_try = False
    for try_node in [n for n in ast.walk(main_fn) if isinstance(n, ast.Try)]:
        for call in [n for n in ast.walk(try_node) if isinstance(n, ast.Call)]:
            f = call.func
            if (isinstance(f, ast.Attribute) and f.attr == "refresh"
                    and isinstance(f.value, ast.Name) and f.value.id == "trendline_watch"):
                hook_in_try = True
    assert hook_in_try, ("trendline_engine.main must call trendline_watch.refresh() "
                         "inside a try/except (fail-open hook missing or unwrapped)")


# ------------------------------------------------------------------ 7. brief line
def test_daily_brief_consumes_premarket_line(tmp_path, monkeypatch):
    watch = tmp_path / "trendline-watch.json"
    watch.write_text(json.dumps({"premarket_line":
                                 "Trendlines: 2 active as of 07-31 16:00, nearest wick support at 746.71, 0.08 below close."}),
                     encoding="utf-8")
    monkeypatch.setattr(db, "TRENDLINE_WATCH_PATH", watch)
    line = db._trendline_morning_line()
    assert line.startswith("Trendlines: 2 active as of 07-31 16:00")


def test_daily_brief_line_fail_open(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "TRENDLINE_WATCH_PATH", tmp_path / "absent.json")
    assert db._trendline_morning_line() == "Trendlines: no watch surface on file yet."
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(db, "TRENDLINE_WATCH_PATH", bad)
    assert db._trendline_morning_line() == "Trendlines: no watch surface on file yet."


def test_compose_morning_includes_trendline_line(monkeypatch):
    monkeypatch.setattr(db, "_trendline_morning_line",
                        lambda: "Trendlines: 3 active as of 07-31 16:00.")
    facts = db.gather_morning_facts("2026-08-01")
    text = db.compose_morning_text(facts)
    assert "Trendlines: 3 active as of 07-31 16:00." in text
