"""Guard tests for setup/scripts/monday_verify.py -- WEEKEND-TWELVE Next-Twelve #6, the
mechanical Monday-verify sweep bundling WS7 live-watch, WS6 regime stamp, WS3 level
hysteresis, WS11 core recency, the theta cockpit, and the WS1 preview-vs-actuals diff into
ONE GREEN/YELLOW/RED/NOT_EXERCISED line per item.

Covers:
  1. Pure helpers: _combine severity ordering, _iter_concat_json (concatenated
     pretty-printed JSON docs, the level-refresh log's format, with resync-on-garbage),
     _level_flip_stats (hand-computed), _decode_bytes (UTF-16 BOM sniff -- a REAL bug this
     build caught: level-refresh-*.log is written UTF-16LE-with-BOM by PowerShell's `*>>`
     redirect, unlike every other log in this repo).
  2. Each of the six pure deciders (decide_ws7/ws6/ws3/ws11/theta/ws1): every reachable
     verdict, with an explicit RED-PROOF case per decider (the task's "feed it a fixture
     where an item fails and prove it reports RED" requirement) plus the C7 property that a
     healthy-cadence-but-unexercised claim combines to NOT_EXERCISED, never GREEN.
  3. The armed=True session-detection fix: a REAL bug found live during this build (6
     off-hours diagnostic rows on 2026-08-01, armed=False, would have been misread as a real
     RTH session) -- a dedicated regression test pins it.
  4. _scan_live_watch_log's backward day-boundary heuristic on a synthetic two-day log.
  5. End-to-end integration RED-PROOFS for the two log/ledger-parsing-heaviest checks (WS3,
     WS7) via monkeypatched module path constants + tmp_path fixtures -- proves the WRAPPER
     functions (not just the pure deciders) report RED on a failing fixture.
  6. STATUS.md plumbing: newly-red transition detection (no re-spam of a persisting RED),
     the prepended block's `## [` boundary format.
  7. A light real-repo smoke test: run_all() against the ACTUAL repo state (no
     monkeypatching) never raises and returns exactly 6 checks with a valid overall verdict
     -- this is also what proves the weekend dry-run is safe to run on demand.

Pure-logic + tmp_path/monkeypatch only -- no network, no live state touched except the one
real-repo smoke test, which is READ-ONLY (run_all never writes; only main()/write_outputs do).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _mv():
    return importlib.import_module("monday_verify")


# --------------------------------------------------------------------------- #
# 1. pure helpers
# --------------------------------------------------------------------------- #
def test_combine_severity_ordering():
    mv = _mv()
    assert mv._combine(mv.GREEN) == mv.GREEN
    assert mv._combine(mv.GREEN, mv.NOT_EXERCISED) == mv.NOT_EXERCISED
    assert mv._combine(mv.YELLOW, mv.NOT_EXERCISED) == mv.YELLOW
    assert mv._combine(mv.RED, mv.GREEN, mv.YELLOW, mv.NOT_EXERCISED) == mv.RED
    assert mv._combine(mv.NOT_EXERCISED, mv.NOT_EXERCISED) == mv.NOT_EXERCISED


def test_iter_concat_json_parses_multiple_pretty_docs():
    mv = _mv()
    doc1 = {"ok": True, "hysteresis_held": []}
    doc2 = {"ok": False, "error": "no bars"}
    doc3 = {"ok": True, "hysteresis_held": [{"label": "X", "price": 743.25}]}
    text = json.dumps(doc1, indent=2) + "\n" + json.dumps(doc2, indent=2) + "\n" + json.dumps(doc3, indent=2)
    out = mv._iter_concat_json(text)
    assert out == [doc1, doc2, doc3]


def test_iter_concat_json_resyncs_past_garbage():
    mv = _mv()
    doc1 = {"ok": True}
    doc2 = {"ok": True, "n": 2}
    text = json.dumps(doc1) + "\nnot json garbage {{{ \n" + json.dumps(doc2)
    out = mv._iter_concat_json(text)
    assert doc1 in out and doc2 in out


def test_iter_concat_json_empty_string():
    mv = _mv()
    assert mv._iter_concat_json("") == []
    assert mv._iter_concat_json("   \n\n  ") == []


def test_level_flip_stats_hand_computed():
    mv = _mv()
    # level 100.0 present at t1,t3 absent t2 (2 flips); level 200.0 present every tick (0 flips)
    ticks = [
        ("t1", [100.0, 200.0]),
        ("t2", [200.0]),
        ("t3", [100.0, 200.0]),
    ]
    stats = mv._level_flip_stats(ticks)
    assert stats["100.00"] == {"present": 2, "flips": 2}
    assert stats["200.00"] == {"present": 3, "flips": 0}


def test_decode_bytes_sniffs_utf16le_bom():
    """DISCOVERED BUILDING THIS SCRIPT: level-refresh-*.log is written UTF-16LE-with-BOM by
    PowerShell's `*>> $log`, not UTF-8 like every other log/ledger in this repo. This test
    pins the fix -- a bare .decode('utf-8') raised UnicodeDecodeError at byte 0 (0xFF) the
    first time this script ran against the REAL Saturday 2026-08-01 log."""
    mv = _mv()
    payload = {"ok": True, "hysteresis_held": []}
    text = json.dumps(payload)
    utf16_bytes = b"\xff\xfe" + text.encode("utf-16-le")
    assert mv._decode_bytes(utf16_bytes) == text
    utf8_bytes = text.encode("utf-8")
    assert mv._decode_bytes(utf8_bytes) == text


def test_decode_bytes_red_proof_without_sniff():
    """RED-PROOF: prove the bug is real -- a naive utf-8 decode of the SAME bytes raises."""
    payload_bytes = b"\xff\xfe" + json.dumps({"ok": True}).encode("utf-16-le")
    with pytest.raises(UnicodeDecodeError):
        payload_bytes.decode("utf-8")


def test_is_weekday():
    mv = _mv()
    assert mv._is_weekday("2026-08-03") is True   # Monday
    assert mv._is_weekday("2026-08-01") is False  # Saturday
    assert mv._is_weekday("2026-08-02") is False  # Sunday
    assert mv._is_weekday("not-a-date") is False


# --------------------------------------------------------------------------- #
# 2a. decide_ws7
# --------------------------------------------------------------------------- #
def test_decide_ws7_not_exercised_no_session():
    mv = _mv()
    assert mv.decide_ws7(has_session=False, n_rth_fires=0, expected_fires=405,
                         in_trade_ticks=0, n_entries=0) == mv.NOT_EXERCISED


def test_decide_ws7_red_proof_zero_fires_despite_session():
    mv = _mv()
    v = mv.decide_ws7(has_session=True, n_rth_fires=0, expected_fires=405,
                      in_trade_ticks=0, n_entries=0)
    assert v == mv.RED


def test_decide_ws7_red_proof_fill_but_never_seen_in_trade():
    mv = _mv()
    v = mv.decide_ws7(has_session=True, n_rth_fires=400, expected_fires=405,
                      in_trade_ticks=0, n_entries=1)
    assert v == mv.RED


def test_decide_ws7_healthy_cadence_no_fill_is_not_exercised_not_green():
    """C7: cadence is fine but the headline claim (field population on a real fill) never
    got exercised -- must combine to NOT_EXERCISED, never a bare GREEN pass."""
    mv = _mv()
    v = mv.decide_ws7(has_session=True, n_rth_fires=400, expected_fires=405,
                      in_trade_ticks=0, n_entries=0)
    assert v == mv.NOT_EXERCISED


def test_decide_ws7_degraded_cadence_no_fill_is_yellow_not_hidden():
    mv = _mv()
    v = mv.decide_ws7(has_session=True, n_rth_fires=100, expected_fires=405,
                      in_trade_ticks=0, n_entries=0)
    assert v == mv.YELLOW


def test_decide_ws7_green_full_path():
    mv = _mv()
    v = mv.decide_ws7(has_session=True, n_rth_fires=400, expected_fires=405,
                      in_trade_ticks=3, n_entries=1)
    assert v == mv.GREEN


def test_decide_ws7_yellow_degraded_cadence_with_fill():
    mv = _mv()
    v = mv.decide_ws7(has_session=True, n_rth_fires=100, expected_fires=405,
                      in_trade_ticks=3, n_entries=1)
    assert v == mv.YELLOW


# --------------------------------------------------------------------------- #
# 2b. decide_ws6
# --------------------------------------------------------------------------- #
def test_decide_ws6_not_exercised_weekend():
    mv = _mv()
    assert mv.decide_ws6(is_weekday=False, stamp_present=False, rc_present=False,
                         dates_match=False, gen_hhmm_in_window=None) == mv.NOT_EXERCISED


def test_decide_ws6_red_proof_missing_artifacts():
    mv = _mv()
    v = mv.decide_ws6(is_weekday=True, stamp_present=False, rc_present=False,
                      dates_match=False, gen_hhmm_in_window=None)
    assert v == mv.RED


def test_decide_ws6_red_proof_stale_date():
    mv = _mv()
    v = mv.decide_ws6(is_weekday=True, stamp_present=True, rc_present=True,
                      dates_match=False, gen_hhmm_in_window=None)
    assert v == mv.RED


def test_decide_ws6_yellow_no_timestamp():
    mv = _mv()
    v = mv.decide_ws6(is_weekday=True, stamp_present=True, rc_present=True,
                      dates_match=True, gen_hhmm_in_window=None)
    assert v == mv.YELLOW


def test_decide_ws6_yellow_outside_window():
    mv = _mv()
    v = mv.decide_ws6(is_weekday=True, stamp_present=True, rc_present=True,
                      dates_match=True, gen_hhmm_in_window=False)
    assert v == mv.YELLOW


def test_decide_ws6_green():
    mv = _mv()
    v = mv.decide_ws6(is_weekday=True, stamp_present=True, rc_present=True,
                      dates_match=True, gen_hhmm_in_window=True)
    assert v == mv.GREEN


# --------------------------------------------------------------------------- #
# 2c. decide_ws3
# --------------------------------------------------------------------------- #
def test_decide_ws3_not_exercised_no_session():
    mv = _mv()
    assert mv.decide_ws3(has_session=False, n_refresh_runs=0, worst_flips=None) == mv.NOT_EXERCISED


def test_decide_ws3_red_proof_zero_refresh_runs():
    mv = _mv()
    v = mv.decide_ws3(has_session=True, n_refresh_runs=0, worst_flips=None)
    assert v == mv.RED


def test_decide_ws3_red_proof_matches_friday_worst():
    """RED-PROOF using the EXACT documented Friday pathology (743.25: 14 flips) -- a level
    flickering >= Friday's pre-fix worst case must report RED, not a pass."""
    mv = _mv()
    v = mv.decide_ws3(has_session=True, n_refresh_runs=80,
                      worst_flips=mv.FRIDAY_WORST_FLIPS)
    assert v == mv.RED
    v2 = mv.decide_ws3(has_session=True, n_refresh_runs=80, worst_flips=20)
    assert v2 == mv.RED


def test_decide_ws3_yellow_mid():
    mv = _mv()
    v = mv.decide_ws3(has_session=True, n_refresh_runs=80, worst_flips=10)
    assert v == mv.YELLOW


def test_decide_ws3_green_low():
    mv = _mv()
    v = mv.decide_ws3(has_session=True, n_refresh_runs=80, worst_flips=1)
    assert v == mv.GREEN


def test_decide_ws3_yellow_no_measurable_levels():
    mv = _mv()
    v = mv.decide_ws3(has_session=True, n_refresh_runs=5, worst_flips=None)
    assert v == mv.YELLOW


# --------------------------------------------------------------------------- #
# 2d. decide_ws11
# --------------------------------------------------------------------------- #
def test_decide_ws11_not_exercised_when_window_static():
    mv = _mv()
    assert mv.decide_ws11(window_advanced=False) == mv.NOT_EXERCISED


def test_decide_ws11_green_when_advanced():
    mv = _mv()
    assert mv.decide_ws11(window_advanced=True) == mv.GREEN


# --------------------------------------------------------------------------- #
# 2e. decide_theta
# --------------------------------------------------------------------------- #
def test_decide_theta_not_exercised_no_session():
    mv = _mv()
    v = mv.decide_theta(has_session=False, snapshot_fresh=False, accounts_checked=False,
                        n_rows=0, n_usable_source_rows=0)
    assert v == mv.NOT_EXERCISED


def test_decide_theta_red_proof_stale_snapshot():
    mv = _mv()
    v = mv.decide_theta(has_session=True, snapshot_fresh=False, accounts_checked=True,
                        n_rows=0, n_usable_source_rows=0)
    assert v == mv.RED


def test_decide_theta_red_proof_no_accounts_checked():
    mv = _mv()
    v = mv.decide_theta(has_session=True, snapshot_fresh=True, accounts_checked=False,
                        n_rows=0, n_usable_source_rows=0)
    assert v == mv.RED


def test_decide_theta_not_exercised_zero_rows():
    mv = _mv()
    v = mv.decide_theta(has_session=True, snapshot_fresh=True, accounts_checked=True,
                        n_rows=0, n_usable_source_rows=0)
    assert v == mv.NOT_EXERCISED


def test_decide_theta_yellow_all_unavailable():
    mv = _mv()
    v = mv.decide_theta(has_session=True, snapshot_fresh=True, accounts_checked=True,
                        n_rows=5, n_usable_source_rows=0)
    assert v == mv.YELLOW


def test_decide_theta_green_usable():
    mv = _mv()
    v = mv.decide_theta(has_session=True, snapshot_fresh=True, accounts_checked=True,
                        n_rows=5, n_usable_source_rows=5)
    assert v == mv.GREEN


# --------------------------------------------------------------------------- #
# 2f. decide_ws1
# --------------------------------------------------------------------------- #
def test_decide_ws1_not_exercised_wrong_date():
    mv = _mv()
    v = mv.decide_ws1(date_matches_target=False, has_session=True, data_ok=True)
    assert v == mv.NOT_EXERCISED


def test_decide_ws1_not_exercised_no_session():
    mv = _mv()
    v = mv.decide_ws1(date_matches_target=True, has_session=False, data_ok=True)
    assert v == mv.NOT_EXERCISED


def test_decide_ws1_red_proof_data_not_gathered():
    mv = _mv()
    v = mv.decide_ws1(date_matches_target=True, has_session=True, data_ok=False)
    assert v == mv.RED


def test_decide_ws1_green():
    mv = _mv()
    v = mv.decide_ws1(date_matches_target=True, has_session=True, data_ok=True)
    assert v == mv.GREEN


# --------------------------------------------------------------------------- #
# 3. armed=True session-detection fix (REAL bug found live during this build)
# --------------------------------------------------------------------------- #
def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_load_core_rows_filters_out_unarmed_diagnostic_rows(tmp_path):
    """RED-PROOF of the exact live bug: 6 armed=False diagnostic rows on 2026-08-01 (found
    during this build) must NOT be read as a real RTH session."""
    mv = _mv()
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        {"ts_et": "2026-08-01T13:02:06", "account": "safe", "verdict": "HOLD", "armed": False},
        {"ts_et": "2026-08-01T14:23:18", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO", "armed": False},
    ])
    rows = mv._load_core_rows_for_date("2026-08-01", path=core)
    assert rows == [], "unarmed diagnostic rows must never be read as a real session"


def test_load_core_rows_keeps_armed_rows(tmp_path):
    mv = _mv()
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        {"ts_et": "2026-07-31T09:30:03", "account": "safe", "verdict": "HOLD", "armed": True},
        {"ts_et": "2026-07-31T09:31:03", "account": "safe", "verdict": "HOLD", "armed": False},
    ])
    rows = mv._load_core_rows_for_date("2026-07-31", path=core)
    assert len(rows) == 1
    assert rows[0]["armed"] is True


def test_entries_for_date_honors_monkeypatched_core_decisions(tmp_path, monkeypatch):
    """Proves the late-bound-default fix: _entries_for_date calls _load_core_rows_for_date
    WITHOUT an explicit path, so it must pick up a monkeypatched module-level CORE_DECISIONS
    (the exact gotcha a def-time-captured default would silently defeat)."""
    mv = _mv()
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        {"ts_et": "2026-08-03T11:44:02", "account": "safe", "verdict": "ENTER_BEAR",
         "armed": True, "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
    ])
    fleet_dir = tmp_path / "fleet"
    for arm in mv.FLEET_ARM_IDS:
        (fleet_dir / arm).mkdir(parents=True, exist_ok=True)
        (fleet_dir / arm / "decisions.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(mv, "CORE_DECISIONS", core)
    monkeypatch.setattr(mv, "FLEET_DIR", fleet_dir)
    entries, core_rows = mv._entries_for_date("2026-08-03")
    assert len(core_rows) == 1
    assert len(entries) == 1
    assert entries[0]["arm"] == "safe-2"
    assert entries[0]["side"] == "P"


# --------------------------------------------------------------------------- #
# 4. _scan_live_watch_log day-boundary heuristic
# --------------------------------------------------------------------------- #
def test_scan_live_watch_log_isolates_todays_contiguous_run(tmp_path, monkeypatch):
    mv = _mv()
    log = tmp_path / "live-watch.stdout.log"
    day1_lines = [f"[live_watch] {h:02d}:{m:02d} ET RTH snapshot written (in_trade=0, arms=5, errors=0)"
                  for h, m in [(15, 58), (15, 59), (16, 0)]]
    day2_lines = [f"[live_watch] {h:02d}:{m:02d} ET RTH snapshot written (in_trade=1, arms=5, errors=0)"
                  for h, m in [(9, 25), (9, 26), (9, 27)]]
    log.write_text("\n".join(day1_lines + day2_lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(mv, "_file_mtime_et_date", lambda p: "2026-08-03")
    scan = mv._scan_live_watch_log("2026-08-03", log_path=log)
    assert scan["available"] is True
    assert scan["n_rth_fires"] == 3
    assert scan["in_trade_ticks"] == 3
    assert scan["first_hhmm"] == "09:25"
    assert scan["last_hhmm"] == "09:27"


def test_scan_live_watch_log_not_available_when_mtime_mismatch(tmp_path, monkeypatch):
    mv = _mv()
    log = tmp_path / "live-watch.stdout.log"
    log.write_text("[live_watch] 12:55 ET closed; snapshot already CLOSED -- no write\n", encoding="utf-8")
    monkeypatch.setattr(mv, "_file_mtime_et_date", lambda p: "2026-08-01")
    scan = mv._scan_live_watch_log("2026-08-03", log_path=log)
    assert scan["available"] is False
    assert scan["n_rth_fires"] == 0


def test_scan_live_watch_log_closed_no_write_not_counted_as_rth_fire(tmp_path, monkeypatch):
    mv = _mv()
    log = tmp_path / "live-watch.stdout.log"
    log.write_text("[live_watch] 12:55 ET closed; snapshot already CLOSED -- no write\n", encoding="utf-8")
    monkeypatch.setattr(mv, "_file_mtime_et_date", lambda p: "2026-08-01")
    scan = mv._scan_live_watch_log("2026-08-01", log_path=log)
    assert scan["available"] is True
    assert scan["n_rth_fires"] == 0
    assert scan["in_trade_ticks"] == 0


# --------------------------------------------------------------------------- #
# 5. end-to-end integration RED-PROOFS (wrapper functions, not just deciders)
# --------------------------------------------------------------------------- #
def _synthetic_ws3_env(tmp_path, monkeypatch, mv, *, n_flips: int):
    """Synthetic core-decisions.jsonl where ONE level flickers exactly n_flips times across
    a handful of ticks (present/absent alternating), mirroring the real 743.25 pathology."""
    core = tmp_path / "core-decisions.jsonl"
    rows = []
    present = True
    minute = 30
    for i in range(n_flips + 2):
        levels = [743.25, 750.00] if present else [750.00]
        rows.append({"ts_et": f"2026-07-31T09:{minute:02d}:00", "account": "safe",
                     "verdict": "HOLD", "armed": True, "levels_active": levels})
        present = not present if i < n_flips else present
        minute += 1
    _write_jsonl(core, rows)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "level-refresh-2026-07-31.log"
    log_path.write_text(json.dumps({"ok": True, "hysteresis_held": []}), encoding="utf-8")
    monkeypatch.setattr(mv, "CORE_DECISIONS", core)
    monkeypatch.setattr(mv, "LOGS_DIR", logs_dir)
    fleet_dir = tmp_path / "fleet"
    for arm in mv.FLEET_ARM_IDS:
        (fleet_dir / arm).mkdir(parents=True, exist_ok=True)
        (fleet_dir / arm / "decisions.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(mv, "FLEET_DIR", fleet_dir)


def test_check_ws3_end_to_end_red_proof_on_friday_class_flicker(tmp_path, monkeypatch):
    """Feeds the WRAPPER (not the pure decider) a fixture whose worst level flickers exactly
    as many times as Friday's real 743.25 pathology (14) -- proves check_ws3_level_hysteresis
    reports RED end-to-end, not just that the isolated decider can."""
    mv = _mv()
    _synthetic_ws3_env(tmp_path, monkeypatch, mv, n_flips=mv.FRIDAY_WORST_FLIPS)
    result = mv.check_ws3_level_hysteresis("2026-07-31")
    assert result["verdict"] == mv.RED
    assert result["detail"]["worst_flips"] >= mv.FRIDAY_WORST_FLIPS
    assert "743.25" in result["observed"] or result["detail"]["worst_level"] == "743.25"


def test_check_ws3_end_to_end_green_on_stable_levels(tmp_path, monkeypatch):
    mv = _mv()
    _synthetic_ws3_env(tmp_path, monkeypatch, mv, n_flips=0)
    result = mv.check_ws3_level_hysteresis("2026-07-31")
    assert result["verdict"] == mv.GREEN


def test_check_ws3_not_exercised_when_no_ticks(tmp_path, monkeypatch):
    mv = _mv()
    core = tmp_path / "core-decisions.jsonl"
    core.write_text("", encoding="utf-8")
    monkeypatch.setattr(mv, "CORE_DECISIONS", core)
    result = mv.check_ws3_level_hysteresis("2026-08-01")
    assert result["verdict"] == mv.NOT_EXERCISED


def test_check_ws7_end_to_end_red_proof_fill_never_seen(tmp_path, monkeypatch):
    """A real armed ENTER fill exists for the date, but the live-watch log shows zero
    in_trade ticks all day -- the wrapper must report RED (the watcher missed a real
    position), not silently pass."""
    mv = _mv()
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        {"ts_et": "2026-08-03T10:15:00", "account": "safe", "verdict": "ENTER_BULL",
         "armed": True, "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON"},
    ])
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "live-watch.stdout.log"
    fires = [f"[live_watch] {h:02d}:{m:02d} ET RTH snapshot written (in_trade=0, arms=5, errors=0)"
             for h, m in [(10, 14), (10, 15), (10, 16), (10, 17)]]
    log_path.write_text("\n".join(fires) + "\n", encoding="utf-8")
    fleet_dir = tmp_path / "fleet"
    for arm in mv.FLEET_ARM_IDS:
        (fleet_dir / arm).mkdir(parents=True, exist_ok=True)
        (fleet_dir / arm / "decisions.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(mv, "CORE_DECISIONS", core)
    monkeypatch.setattr(mv, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(mv, "LIVE_WATCH_LOG", log_path)
    monkeypatch.setattr(mv, "LIVE_WATCH_JSON", tmp_path / "nonexistent-live-watch.json")
    monkeypatch.setattr(mv, "_file_mtime_et_date", lambda p: "2026-08-03")

    result = mv.check_ws7_live_watch("2026-08-03")
    assert result["verdict"] == mv.RED
    assert result["detail"]["n_entries"] == 1
    assert result["detail"]["log_scan"]["in_trade_ticks"] == 0


def test_check_ws7_end_to_end_green_full_path(tmp_path, monkeypatch):
    mv = _mv()
    core = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core, [
        {"ts_et": "2026-08-03T10:15:00", "account": "safe", "verdict": "ENTER_BULL",
         "armed": True, "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON"},
    ])
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "live-watch.stdout.log"
    fires = []
    for h, m in [(10, 14)]:
        fires.append(f"[live_watch] {h:02d}:{m:02d} ET RTH snapshot written (in_trade=0, arms=5, errors=0)")
    for h, m in [(10, 15), (10, 16), (10, 17)]:
        fires.append(f"[live_watch] {h:02d}:{m:02d} ET RTH snapshot written (in_trade=1, arms=5, errors=0)")
    log_path.write_text("\n".join(fires) + "\n", encoding="utf-8")
    fleet_dir = tmp_path / "fleet"
    for arm in mv.FLEET_ARM_IDS:
        (fleet_dir / arm).mkdir(parents=True, exist_ok=True)
        (fleet_dir / arm / "decisions.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(mv, "CORE_DECISIONS", core)
    monkeypatch.setattr(mv, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(mv, "LIVE_WATCH_LOG", log_path)
    monkeypatch.setattr(mv, "LIVE_WATCH_JSON", tmp_path / "nonexistent-live-watch.json")
    monkeypatch.setattr(mv, "_file_mtime_et_date", lambda p: "2026-08-03")

    result = mv.check_ws7_live_watch("2026-08-03")
    # cadence ratio here is 4/405 (far under 0.75) -- expect YELLOW, not GREEN; the point of
    # this test is in_trade_ticks > 0 with a real fill never returns RED.
    assert result["verdict"] in (mv.GREEN, mv.YELLOW)
    assert result["detail"]["log_scan"]["in_trade_ticks"] == 3


# --------------------------------------------------------------------------- #
# 6. STATUS.md plumbing
# --------------------------------------------------------------------------- #
def _fake_report(verdicts: dict) -> dict:
    checks = []
    for id_, v in verdicts.items():
        checks.append({"id": id_, "name": id_, "verdict": v, "expected": "exp", "observed": "obs",
                       "detail": {}})
    overall = max((c["verdict"] for c in checks), default="GREEN",
                  key=lambda x: {"RED": 3, "YELLOW": 2, "NOT_EXERCISED": 1, "GREEN": 0}[x])
    return {"schema_version": 1, "generated_at_et": "2026-08-03T16:15:00", "check_date": "2026-08-03",
            "overall": overall, "never_blocks_never_kills": True, "checks": checks}


def test_compute_newly_red_flags_new_but_not_persisting():
    mv = _mv()
    prior = _fake_report({"a": "RED", "b": "GREEN"})
    current = _fake_report({"a": "RED", "b": "RED"})
    newly = mv._compute_newly_red(current, prior)
    ids = {c["id"] for c in newly}
    assert ids == {"b"}, "a was already RED last run (no re-spam); b just went RED (flag it)"


def test_compute_newly_red_no_prior_report_flags_all_red():
    mv = _mv()
    current = _fake_report({"a": "RED", "b": "GREEN"})
    newly = mv._compute_newly_red(current, None)
    assert {c["id"] for c in newly} == {"a"}


def test_flag_known_broken_appends_under_marker(tmp_path):
    mv = _mv()
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n_marker doc_\n\n---\n\n## [older entry]\nbody\n",
                      encoding="utf-8")
    report = _fake_report({"ws3_level_hysteresis": "RED"})
    mv._flag_known_broken(report["checks"], "2026-08-03", status_md=status)
    text = status.read_text(encoding="utf-8")
    assert "MONDAY-VERIFY RED :: ws3_level_hysteresis" in text
    assert text.index("## Known broken") < text.index("MONDAY-VERIFY RED")


def test_flag_known_broken_noop_when_nothing_newly_red(tmp_path):
    mv = _mv()
    status = tmp_path / "STATUS.md"
    original = "## Known broken\n\n_marker doc_\n"
    status.write_text(original, encoding="utf-8")
    mv._flag_known_broken([], "2026-08-03", status_md=status)
    assert status.read_text(encoding="utf-8") == original


def test_prepend_status_block_is_newest_first(tmp_path):
    mv = _mv()
    status = tmp_path / "STATUS.md"
    status.write_text("## [old entry] OK\nold body\n", encoding="utf-8")
    report = _fake_report({"ws7_live_watch": "GREEN", "ws3_level_hysteresis": "NOT_EXERCISED"})
    mv._prepend_status_block(report, status_md=status)
    text = status.read_text(encoding="utf-8")
    assert text.startswith("## [")
    assert "monday_verify" in text.splitlines()[0]
    assert text.index("monday_verify") < text.index("old entry")
    assert "| Item | Verdict | Expected | Observed |" in text


def test_render_status_block_escapes_table_pipes():
    mv = _mv()
    report = _fake_report({"x": "GREEN"})
    report["checks"][0]["expected"] = "a | b"
    report["checks"][0]["observed"] = "c | d\nsecond line"
    block = mv._render_status_block(report)
    assert "a \\| b" in block
    assert "c \\| d" in block
    assert "second line" in block  # newline collapsed, content preserved


# --------------------------------------------------------------------------- #
# 7. real-repo smoke test (read-only; proves the weekend dry-run is safe)
# --------------------------------------------------------------------------- #
def test_run_all_against_real_repo_state_never_raises():
    mv = _mv()
    report = mv.run_all(mv.et_now().date().isoformat(), attempt_live_refresh=False)
    assert report["overall"] in (mv.GREEN, mv.YELLOW, mv.RED, mv.NOT_EXERCISED)
    assert len(report["checks"]) == 6
    ids = {c["id"] for c in report["checks"]}
    assert ids == {"ws7_live_watch", "ws6_regime_stamp", "ws3_level_hysteresis",
                   "ws11_core_recency", "theta_cockpit", "ws1_preview_diff"}
    for c in report["checks"]:
        assert c["verdict"] in (mv.GREEN, mv.YELLOW, mv.RED, mv.NOT_EXERCISED)
        assert isinstance(c["expected"], str) and c["expected"]
        assert isinstance(c["observed"], str) and c["observed"]


def test_run_all_friday_2026_07_31_matches_documented_flicker_numbers():
    """Cross-validates check_ws3's flip-counting logic against the REAL numbers published in
    LEVEL-FLICKER-FIX-2026-08-01.md (743.25: present 331/386, 14 flips) -- an independent
    re-derivation from the raw ledger, not a copy of the doc's own claim."""
    mv = _mv()
    result = mv.check_ws3_level_hysteresis("2026-07-31")
    detail = result["detail"]
    assert detail["n_ticks"] == 386
    row = detail["per_level"].get("743.25")
    assert row is not None, "743.25 must appear in Friday's real per-level stats"
    assert row["present"] == 331
    assert row["flips"] == 14
