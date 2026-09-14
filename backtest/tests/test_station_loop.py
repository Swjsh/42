"""Guard: setup/scripts/station_loop.py + station_board.py + station_facts.py -- the
Station loop v1 (GOAL-GAMMA-STATION-2026-09-13 item (4)).

Locks in: the yield-rule truth table (RTH / GPU-busy / denylisted-process / Ollama-down),
each check independently injectable so no test here shells out or touches the network;
schema validation of the model's structured-output response (malformed output becomes a
logged "error" ledger row, never a crash or a fabricated card); title dedupe (exact-
normalized AND difflib-similar); the board cap (oldest killed/proposed rows drop first,
never the newest); the ledger row's field shape; and that an unreachable Ollama produces an
"error"/"ollama_down" row while `main()` still exits 0 (never a scheduler alarm). A couple of
station_facts.py tests lock the SAFE-vs-BOLD circuit-breaker key-vocabulary divergence
(documented in each breaker file's own _schema_note) since that mapping is the single
easiest thing in this module to get quietly backwards.

Every module-level Path constant this suite touches (IDEAS_BOARD_PATH, LEDGER_PATH,
BRIEF_PATH, CONFIG_PATH, STATION_PROMPT_PATH, LOG_DIR) is monkeypatched onto a tmp_path
fixture -- no test here ever reads or writes real repo state, and none makes a real HTTP or
subprocess call (call_ollama_chat / _ollama_reachable / _gpu_util_pct / process-table are
monkeypatched at their call sites).
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

import station_loop as sl  # noqa: E402
import station_board as sb  # noqa: E402
import station_facts as sf  # noqa: E402

# Captured at collection time, BEFORE the autouse fixture below stubs sl._task_health_snapshot
# on every test -- a few tests want the REAL enumeration logic (with a fake registered_tasks_fn
# injected) rather than the fast fixed-dict stub every other test gets by default.
_REAL_TASK_HEALTH_SNAPSHOT = sl._task_health_snapshot


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _isolate_station_paths(monkeypatch, tmp_path):
    """Every station_loop output/input path is redirected under tmp_path so no test
    touches the real repo's automation/state/station/ or E:\\Gamma\\logs\\."""
    monkeypatch.setattr(sl, "STATION_DIR", tmp_path)
    monkeypatch.setattr(sl, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(sl, "IDEAS_BOARD_PATH", tmp_path / "ideas-board.json")
    monkeypatch.setattr(sl, "BRIEF_PATH", tmp_path / "station-brief.md")
    monkeypatch.setattr(sl, "LEDGER_PATH", tmp_path / "loop-ledger.jsonl")
    monkeypatch.setattr(sl, "STATION_PROMPT_PATH", tmp_path / "station.md")
    monkeypatch.setattr(sl, "LOG_DIR", tmp_path / "logs")
    # GAMMA-STATION item 12 (2026-09-13): isolate the closed-loop scorer's own paths too, and
    # stub conductor_outcome.record so no test in this file appends a real row to the repo's
    # automation/state/conductor-outcomes.jsonl as a side effect of calling run_once()/main()
    # (same class of bug conftest.py's _crypto_twin_pid_file_untouched_by_tests guards against
    # for a different file -- a bound-default/unpatched dependency writing to live state).
    monkeypatch.setattr(sl, "AUTOPSY_DIR", tmp_path / "autopsies")
    monkeypatch.setattr(sl, "VERDICTS_LEDGER_PATH", tmp_path / "station-verdicts.jsonl")
    monkeypatch.setattr(sl, "SETTLED_HYP_PATH", tmp_path / "hypotheses-settled.json")
    monkeypatch.setattr(sl.conductor_outcome, "record", lambda **kw: None)
    # 2026-09-14 company-roster re-point (C1-C3): sectors.json + crew-events.jsonl paths,
    # isolated exactly like every other Station output above. sector_rows.build_sector_rows
    # is stubbed to an empty list by default (it is a real, read-only function over live
    # repo files -- safe to call for real, but this file's own docstring promises "no test
    # here ever reads... real repo state", so tests that care about sector-row content
    # override this stub locally). _task_health_snapshot is stubbed to avoid a real
    # PowerShell/Task Scheduler subprocess call on every one of this suite's ~30 run_once()
    # calls; tests targeting _task_health_snapshot itself override it back per-test.
    monkeypatch.setattr(sl, "SECTORS_PATH", tmp_path / "sectors.json")
    monkeypatch.setattr(sl, "CREW_EVENTS_PATH", tmp_path / "crew-events.jsonl")
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [])
    monkeypatch.setattr(sl, "_task_health_snapshot", lambda now_utc, **kw: {
        "ts_et": "2026-09-14 00:00:00 ET", "disabled": [], "failed_last_run": [],
        "total": 0, "source": "test-stub (autouse fixture)",
    })
    # 2026-09-14 C9/C10 (coordinator-directed): hq_self_review.review_once makes a real
    # HTTP call (to the dashboard) and can spawn a real PowerShell capture -- stubbed
    # wholesale here, exactly the lesson learned from the test_station_yield_unload.py
    # leak this same session (a test with an injected clock must never touch live state,
    # or in this case, a real network/subprocess call). Tests targeting hq_self_review
    # itself live in test_hq_self_review.py with their own proper isolation.
    monkeypatch.setattr(sl.hq_self_review, "review_once", lambda *a, **kw: {"stubbed": True})
    yield


# Fixed, known-weekday UTC instants (EDT, UTC-4, is in effect both days -- 2026's DST
# window is 2nd-Sun-March .. 1st-Sun-Nov, and September sits well inside it).
_TUE_RTH_UTC = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)      # Tue 11:00 ET -- inside RTH
_TUE_AFTERHOURS_UTC = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)  # Tue 18:00 ET -- after hours
_SAT_UTC = datetime(2026, 9, 19, 15, 0, tzinfo=timezone.utc)          # Sat 11:00 ET -- weekend


def _cfg(**overrides) -> dict:
    cfg = dict(sl.DEFAULT_CONFIG)
    cfg.update(overrides)
    return cfg


# ============================================================================
# decide_action -- yield-rule truth table (clock always injected, every I/O check stubbed)
# ============================================================================

def test_decide_action_yields_during_rth_weekday():
    status, reason = sl.decide_action(_TUE_RTH_UTC, _cfg(), gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "yielded"
    assert "rth" in reason.lower()


def test_decide_action_yields_on_weekend_too():
    # Weekend is also "not RTH" for is_market_hours, but confirms the same code path holds
    # for the weekday-independent branch of the clock, not just the after-hours case.
    status, reason = sl.decide_action(_SAT_UTC, _cfg(), gpu_util_fn=lambda: 90,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    # Saturday is not RTH, so this falls through to the GPU check (90% > 50% default) --
    # proving decide_action does NOT mistake a weekend for an RTH yield.
    assert status == "yielded"
    assert "gpu" in reason.lower()


def test_decide_action_ok_outside_rth_when_nothing_else_trips():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 10,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert (status, reason) == ("ok", "")


def test_decide_action_yields_when_gpu_above_threshold():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(gpu_util_yield_pct=50),
                                       gpu_util_fn=lambda: 51, process_table_fn=lambda: {},
                                       ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "yielded"
    assert "gpu" in reason.lower()


def test_decide_action_ok_when_gpu_below_threshold():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(gpu_util_yield_pct=50),
                                       gpu_util_fn=lambda: 49, process_table_fn=lambda: {},
                                       ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "ok"


def test_decide_action_gpu_unmeasurable_fails_open():
    # nvidia-smi missing/erroring returns None -- that is "no signal," never a yield.
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: None,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "ok"


def test_decide_action_yields_when_denylisted_process_present():
    cfg = _cfg(yield_processes=["steam.exe"])
    table = {1234: 'C:\\Program Files (x86)\\Steam\\steam.exe" -silent'}
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, cfg, gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: table, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "yielded"
    assert "steam.exe" in reason


def test_decide_action_ok_when_no_denylisted_process():
    cfg = _cfg(yield_processes=["steam.exe"])
    table = {1234: "C:\\Windows\\explorer.exe"}
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, cfg, gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: table, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "ok"


def test_decide_action_process_table_unreadable_fails_open():
    def _boom():
        raise OSError("no powershell")
    cfg = _cfg(yield_processes=["steam.exe"])
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, cfg, gpu_util_fn=lambda: 0,
                                       process_table_fn=_boom, ollama_reachable_fn=lambda u: True,
                                       station_mode_fn=lambda: "work")
    assert status == "ok"


def test_decide_action_error_when_ollama_unreachable():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: False,
                                       station_mode_fn=lambda: "work")
    assert (status, reason) == ("error", "ollama_down")


def test_decide_action_force_skips_rth_gpu_denylist_but_not_ollama():
    # force=True during RTH, with GPU pegged and a denylisted process present, still
    # reaches "ok" as long as Ollama answers -- but still refuses when Ollama is down.
    cfg = _cfg(yield_processes=["steam.exe"])
    status_ok, _ = sl.decide_action(_TUE_RTH_UTC, cfg, force=True, gpu_util_fn=lambda: 99,
                                    process_table_fn=lambda: {1: "steam.exe"},
                                    ollama_reachable_fn=lambda u: True)
    assert status_ok == "ok"

    status_err, reason_err = sl.decide_action(_TUE_RTH_UTC, cfg, force=True, gpu_util_fn=lambda: 99,
                                              process_table_fn=lambda: {1: "steam.exe"},
                                              ollama_reachable_fn=lambda u: False)
    assert (status_err, reason_err) == ("error", "ollama_down")


# ============================================================================
# parse_model_output -- structured-response schema validation
# ============================================================================

def _fake_ollama_response(brief="Quiet fire, nothing new.", cards=None, wants=None,
                          prompt_tokens=1234, gen_tokens=56) -> dict:
    content = json.dumps({"brief": brief, "cards": cards or [], "wants": wants or []})
    return {"message": {"role": "assistant", "content": content},
            "prompt_eval_count": prompt_tokens, "eval_count": gen_tokens}


def test_parse_model_output_valid_schema_roundtrips():
    card = {"title": "T", "mechanism": "M", "evidence": ["E1"],
            "proposed_shadow_test": "S", "cost_line": "$0", "confidence": "low"}
    raw = _fake_ollama_response(cards=[card])
    parsed = sl.parse_model_output(raw)
    assert parsed["brief"] == "Quiet fire, nothing new."
    assert parsed["cards"] == [card]
    assert parsed["wants"] == []


def test_parse_model_output_missing_required_key_raises():
    raw = {"message": {"content": json.dumps({"brief": "x", "cards": []})}}  # no "wants"
    with pytest.raises(ValueError):
        sl.parse_model_output(raw)


# ============================================================================
# test_spec on cards (GOAL-GAMMA-STATION item 12) -- schema accepts a valid spec and null,
# rejects a bad type
# ============================================================================

def _card(**overrides) -> dict:
    base = {"title": "T", "mechanism": "M", "evidence": ["E1"], "proposed_shadow_test": "S",
            "cost_line": "$0", "confidence": "low"}
    base.update(overrides)
    return base


def test_parse_model_output_accepts_valid_test_spec():
    card = _card(test_spec={"type": "size_cap", "params": {"cap": 3}})
    raw = _fake_ollama_response(cards=[card])
    parsed = sl.parse_model_output(raw)
    assert parsed["cards"][0]["test_spec"] == {"type": "size_cap", "params": {"cap": 3}}


def test_parse_model_output_accepts_null_test_spec():
    card = _card(test_spec=None)
    raw = _fake_ollama_response(cards=[card])
    parsed = sl.parse_model_output(raw)
    assert parsed["cards"][0]["test_spec"] is None


def test_parse_model_output_accepts_card_with_no_test_spec_key_at_all():
    # Most fires won't set it -- absence must be exactly as valid as an explicit null.
    card = _card()
    raw = _fake_ollama_response(cards=[card])
    parsed = sl.parse_model_output(raw)
    assert "test_spec" not in parsed["cards"][0]


def test_parse_model_output_rejects_bad_test_spec_type():
    card = _card(test_spec={"type": "not_a_real_type", "params": {}})
    raw = _fake_ollama_response(cards=[card])
    with pytest.raises(ValueError):
        sl.parse_model_output(raw)


def test_parse_model_output_rejects_test_spec_with_non_dict_params():
    card = _card(test_spec={"type": "size_cap", "params": "cap=3"})
    raw = _fake_ollama_response(cards=[card])
    with pytest.raises(ValueError):
        sl.parse_model_output(raw)


def test_parse_model_output_rejects_test_spec_that_is_not_an_object_or_null():
    card = _card(test_spec="size_cap")
    raw = _fake_ollama_response(cards=[card])
    with pytest.raises(ValueError):
        sl.parse_model_output(raw)


def test_parse_model_output_cards_not_a_list_raises():
    raw = {"message": {"content": json.dumps({"brief": "x", "cards": "nope", "wants": []})}}
    with pytest.raises(ValueError):
        sl.parse_model_output(raw)


def test_parse_model_output_non_json_content_raises():
    raw = {"message": {"content": "not json at all"}}
    with pytest.raises(json.JSONDecodeError):
        sl.parse_model_output(raw)


# ============================================================================
# station_board -- dedupe (exact + similarity) and cap
# ============================================================================

def test_merge_new_cards_adds_a_genuinely_new_card():
    existing = []
    new = [{"title": "Fade the noon fake breakout", "mechanism": "m", "evidence": [],
            "proposed_shadow_test": "t", "cost_line": "$0", "confidence": "low"}]
    board, added = sb.merge_new_cards(existing, new, ts_et="2026-09-13 12:00:00 ET",
                                      model="gamma-planner", similarity_threshold=0.8,
                                      max_new=2, cap=50)
    assert added == 1
    assert board[0]["title"] == "Fade the noon fake breakout"
    assert board[0]["status"] == "proposed"
    assert board[0]["prompted_by"] == "station-loop"
    assert board[0]["id"]  # short hash, non-empty


def test_merge_new_cards_drops_exact_duplicate_title_case_insensitive():
    existing = [{"title": "Fade the noon fake breakout", "status": "proposed"}]
    new = [{"title": "  fade the NOON fake breakout  ", "mechanism": "m", "evidence": [],
            "proposed_shadow_test": "t", "cost_line": "$0", "confidence": "low"}]
    board, added = sb.merge_new_cards(existing, new, ts_et="t", model="m",
                                      similarity_threshold=0.8, max_new=2, cap=50)
    assert added == 0
    assert len(board) == 1


def test_merge_new_cards_drops_near_duplicate_by_similarity():
    existing = [{"title": "Fade the noon fake breakout on low volume", "status": "proposed"}]
    new = [{"title": "Fade the noon fake breakout on light volume", "mechanism": "m",
            "evidence": [], "proposed_shadow_test": "t", "cost_line": "$0", "confidence": "low"}]
    board, added = sb.merge_new_cards(existing, new, ts_et="t", model="m",
                                      similarity_threshold=0.8, max_new=2, cap=50)
    assert added == 0, "a one-word rewording should read as a near-duplicate"


def test_merge_new_cards_keeps_a_genuinely_different_title():
    existing = [{"title": "Fade the noon fake breakout", "status": "proposed"}]
    new = [{"title": "TP1 fires late on low-ATR mornings", "mechanism": "m", "evidence": [],
            "proposed_shadow_test": "t", "cost_line": "$0", "confidence": "low"}]
    board, added = sb.merge_new_cards(existing, new, ts_et="t", model="m",
                                      similarity_threshold=0.8, max_new=2, cap=50)
    assert added == 1
    assert len(board) == 2


_FIVE_DISTINCT_TITLES = [
    "Fade the noon fake breakout",
    "TP1 fires late on low-ATR mornings",
    "Runner target rarely hit on Tuesdays",
    "Entry slippage spikes after FOMC prints",
    "Safe breaker rearms an hour late on Mondays",
]  # pairwise difflib ratio < 0.5 -- deliberately NOT near-duplicates of each other


def test_merge_new_cards_respects_max_new_per_fire():
    new = [
        {"title": t, "mechanism": "m", "evidence": [], "proposed_shadow_test": "t",
         "cost_line": "$0", "confidence": "low"}
        for t in _FIVE_DISTINCT_TITLES
    ]
    board, added = sb.merge_new_cards([], new, ts_et="t", model="m",
                                      similarity_threshold=0.8, max_new=2, cap=50)
    assert added == 2
    assert len(board) == 2


def test_apply_cap_drops_oldest_proposed_before_newest():
    # 50 rows, all "proposed" (droppable), cap=48 -> over=2 -> the 2 OLDEST (lowest-index,
    # i.e. "Old 0"/"Old 1") drop; both "Kept newer" rows (added later, higher index) survive.
    board = [{"title": f"Old {i}", "status": "proposed"} for i in range(48)]
    board += [{"title": "Kept newer 1", "status": "proposed"},
              {"title": "Kept newer 2", "status": "proposed"}]
    capped = sb._apply_cap(board, 48)
    assert len(capped) == 48
    titles = {c["title"] for c in capped}
    assert titles == {"Kept newer 1", "Kept newer 2"} | {f"Old {i}" for i in range(2, 48)}
    assert "Old 0" not in titles
    assert "Old 1" not in titles


def test_apply_cap_protects_non_droppable_status_when_possible():
    # A "shipped" card should survive the cap ahead of "proposed"/"killed" rows.
    board = [{"title": "shipped", "status": "shipped"}]
    board += [{"title": f"p{i}", "status": "proposed"} for i in range(50)]
    capped = sb._apply_cap(board, 50)
    assert len(capped) == 50
    assert any(c["title"] == "shipped" for c in capped)


def test_merge_new_cards_enforces_board_cap_end_to_end():
    existing = [{"title": f"Old {i}", "status": "proposed"} for i in range(49)]
    new = [{"title": "Brand new idea", "mechanism": "m", "evidence": [],
            "proposed_shadow_test": "t", "cost_line": "$0", "confidence": "low"}]
    board, added = sb.merge_new_cards(existing, new, ts_et="t", model="m",
                                      similarity_threshold=0.8, max_new=2, cap=49)
    assert added == 1
    assert len(board) == 49
    assert any(c["title"] == "Brand new idea" for c in board)
    assert not any(c["title"] == "Old 0" for c in board), "oldest proposed row should drop first"


# ============================================================================
# run_once -- full fire, ledger row shape, ollama_down -> error + exit 0
# ============================================================================

def _stub_ok_decision(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("ok", ""))


def test_run_once_ok_writes_board_brief_and_ledger_row(monkeypatch, tmp_path):
    _stub_ok_decision(monkeypatch)
    card = {"title": "A fresh idea", "mechanism": "m", "evidence": ["e1"],
            "proposed_shadow_test": "s", "cost_line": "$0", "confidence": "med"}
    fake_raw = _fake_ollama_response(brief="Looked at the ladder, one idea.", cards=[card])
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: fake_raw)

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["status"] == "ok"
    assert row["cards_added"] == 1
    assert row["board_size"] == 1
    assert row["prompt_tokens"] == 1234
    assert row["gen_tokens"] == 56
    assert set(row.keys()) == {
        "ts_et", "model", "status", "reason", "duration_s",
        "prompt_tokens", "gen_tokens", "cards_added", "board_size",
    }

    board = json.loads(sl.IDEAS_BOARD_PATH.read_text(encoding="utf-8"))
    assert board[0]["title"] == "A fresh idea"
    brief_text = sl.BRIEF_PATH.read_text(encoding="utf-8")
    assert "Looked at the ladder, one idea." in brief_text
    assert "1 cards on the board" in brief_text

    ledger_lines = sl.LEDGER_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) == 1
    logged = json.loads(ledger_lines[0])
    assert logged == row


def test_run_once_yield_writes_ledger_row_only_no_board_write(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))
    called = {"n": 0}
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: called.__setitem__("n", called["n"] + 1))

    row = sl.run_once(now_utc=_TUE_RTH_UTC)

    assert row["status"] == "yielded"
    assert row["reason"].startswith("rth_window")
    assert row["cards_added"] == 0
    assert called["n"] == 0, "the model must never be called on a yielded fire"
    assert not sl.IDEAS_BOARD_PATH.exists()


def test_run_once_ollama_down_logs_error_row_and_main_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(sl, "_ollama_reachable", lambda base_url: False)

    exit_code = sl.main(["--once", "--force"])

    assert exit_code == 0
    ledger_lines = sl.LEDGER_PATH.read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(ledger_lines[-1])
    assert row["status"] == "error"
    assert row["reason"] == "ollama_down"
    printed = json.loads(capsys.readouterr().out.strip())
    assert printed["status"] == "error"


def test_run_once_bad_model_output_logs_error_row_not_a_crash(monkeypatch):
    _stub_ok_decision(monkeypatch)
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: {"message": {"content": "not json"}})

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["status"] == "error"
    assert "model_call_failed" in row["reason"]
    assert not sl.IDEAS_BOARD_PATH.exists()


def test_run_once_clears_pending_notes_after_a_successful_fire(monkeypatch):
    _stub_ok_decision(monkeypatch)
    sl.PENDING_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    sl.PENDING_NOTES_PATH.write_text(json.dumps([{"card_id": "x", "action": "test", "note": "n"}]),
                                     encoding="utf-8")
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: _fake_ollama_response())

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["status"] == "ok"
    assert json.loads(sl.PENDING_NOTES_PATH.read_text(encoding="utf-8")) == []


def test_run_once_leaves_pending_notes_untouched_on_a_failed_fire(monkeypatch):
    _stub_ok_decision(monkeypatch)
    sl.PENDING_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    original = [{"card_id": "x", "action": "test", "note": "n"}]
    sl.PENDING_NOTES_PATH.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: {"message": {"content": "not json"}})

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["status"] == "error", "a failed model call never read/delivered the notes"
    assert json.loads(sl.PENDING_NOTES_PATH.read_text(encoding="utf-8")) == original


def test_run_once_leaves_pending_notes_untouched_on_a_yielded_fire(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))
    sl.PENDING_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    original = [{"card_id": "x", "action": "test", "note": "n"}]
    sl.PENDING_NOTES_PATH.write_text(json.dumps(original), encoding="utf-8")

    row = sl.run_once(now_utc=_TUE_RTH_UTC)

    assert row["status"] == "yielded"
    assert json.loads(sl.PENDING_NOTES_PATH.read_text(encoding="utf-8")) == original


def test_run_once_never_exceeds_max_new_cards_per_fire(monkeypatch):
    _stub_ok_decision(monkeypatch)
    cards = [
        {"title": t, "mechanism": "m", "evidence": [], "proposed_shadow_test": "t",
         "cost_line": "$0", "confidence": "low"}
        for t in _FIVE_DISTINCT_TITLES
    ]
    fake_raw = _fake_ollama_response(cards=cards)
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: fake_raw)

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["cards_added"] == sl.DEFAULT_CONFIG["max_new_cards_per_fire"] == 2


# ============================================================================
# GOAL-GAMMA-STATION item 12 -- the closed idea loop wiring in run_once()
# ============================================================================

def test_run_once_records_conductor_outcome_with_station_source_on_ok_fire(monkeypatch):
    _stub_ok_decision(monkeypatch)
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: _fake_ollama_response())
    calls = []
    monkeypatch.setattr(sl.conductor_outcome, "record", lambda **kw: calls.append(kw))

    sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert len(calls) == 1
    assert calls[0]["source"] == "station"
    assert calls[0]["task_id"] == "Gamma_Station"
    assert calls[0]["items_added"] == 0   # a quiet fire (no cards) still records a row
    assert calls[0]["items_drained"] == 0


def test_run_once_records_conductor_outcome_on_a_yielded_fire_too(monkeypatch):
    calls = []
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))
    monkeypatch.setattr(sl.conductor_outcome, "record", lambda **kw: calls.append(kw))

    row = sl.run_once(now_utc=_TUE_RTH_UTC)

    assert row["status"] == "yielded"
    assert len(calls) == 1
    assert calls[0]["source"] == "station"


def test_run_once_calls_score_testing_cards_after_drain_inbox_even_when_yielded(monkeypatch):
    order = []
    monkeypatch.setattr(sl, "drain_inbox", lambda: order.append("drain_inbox") or 0)
    monkeypatch.setattr(sl.station_board, "score_testing_cards",
                        lambda *a, **kw: order.append("score_testing_cards") or {"testing_cards": 0})
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))

    row = sl.run_once(now_utc=_TUE_RTH_UTC)

    assert row["status"] == "yielded", "the model must never be called on a yielded fire"
    assert order == ["drain_inbox", "score_testing_cards"], (
        "scoring needs no model -- it must run right after the inbox drain on every fire, "
        "yielded or not")


def test_score_testing_cards_flips_status_to_supported_once_n_post_meets_min_n(tmp_path):
    board_path = tmp_path / "ideas-board.json"
    autopsy_dir = tmp_path / "autopsies"
    verdicts_path = tmp_path / "station-verdicts.jsonl"
    settled_path = tmp_path / "hypotheses-settled.json"
    autopsy_dir.mkdir()

    card = {"id": "c1", "ts_et": "2026-09-01 12:00:00 ET", "status": "testing",
            "title": "cap size", "test_spec": {"type": "size_cap", "params": {"cap": 3}}}
    board_path.write_text(json.dumps([card]), encoding="utf-8")

    rows = (
        [{"date": "2026-08-25", "qty": 5, "actual_pnl": -100.0}] * 2       # pre-registration, ignored
        + [{"date": "2026-09-05", "qty": 5, "actual_pnl": -100.0}] * 3     # post: cap=3 helps every row
    )
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    summary = sb.score_testing_cards(board_path, autopsy_dir=autopsy_dir, verdicts_path=verdicts_path,
                                     settled_path=settled_path, min_n=3,
                                     now_et=datetime(2026, 9, 10))

    assert summary["scored"] == 1
    assert summary["supported"] == 1
    new_board = json.loads(board_path.read_text(encoding="utf-8"))
    assert new_board[0]["status"] == "supported"
    assert new_board[0]["verdict"] == "supported"
    assert new_board[0]["verdict_n_pre"] == 2
    assert new_board[0]["verdict_n_post"] == 3
    ledger_lines = verdicts_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) == 1
    assert json.loads(ledger_lines[0])["card_id"] == "c1"


def test_score_testing_cards_stays_testing_below_min_n(tmp_path):
    board_path = tmp_path / "ideas-board.json"
    autopsy_dir = tmp_path / "autopsies"
    autopsy_dir.mkdir()

    card = {"id": "c1", "ts_et": "2026-09-01 12:00:00 ET", "status": "testing",
            "title": "cap size", "test_spec": {"type": "size_cap", "params": {"cap": 3}}}
    board_path.write_text(json.dumps([card]), encoding="utf-8")
    rows = [{"date": "2026-09-05", "qty": 5, "actual_pnl": -100.0}] * 2  # only 2 post rows
    (autopsy_dir / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    summary = sb.score_testing_cards(board_path, autopsy_dir=autopsy_dir,
                                     verdicts_path=tmp_path / "v.jsonl",
                                     settled_path=tmp_path / "s.json", min_n=3,
                                     now_et=datetime(2026, 9, 10))

    assert summary["pending"] == 1
    new_board = json.loads(board_path.read_text(encoding="utf-8"))
    assert new_board[0]["status"] == "testing", "must not flip status below min_n"
    assert new_board[0]["verdict"] == "pending"


def test_score_testing_cards_is_a_cheap_noop_with_no_testing_cards(tmp_path):
    board_path = tmp_path / "ideas-board.json"
    board_path.write_text(json.dumps([{"id": "c1", "status": "proposed", "title": "x"}]), encoding="utf-8")
    verdicts_path = tmp_path / "station-verdicts.jsonl"

    summary = sb.score_testing_cards(board_path, autopsy_dir=tmp_path / "nonexistent",
                                     verdicts_path=verdicts_path, settled_path=tmp_path / "s.json")

    assert summary["testing_cards"] == 0
    assert not verdicts_path.exists(), "no testing cards -> zero writes, not even an empty ledger file"


# ============================================================================
# station_facts -- SAFE vs BOLD circuit-breaker key-vocabulary divergence
# ============================================================================

def test_gather_account_breaker_safe_computes_day_pnl(tmp_path):
    p = tmp_path / "circuit-breaker.json"
    p.write_text(json.dumps({
        "tripped": False, "tripped_reason": None,
        "starting_equity_today": 5000.0, "current_equity": 5123.45,
    }), encoding="utf-8")
    fact = sf.gather_account_breaker(p, "safe")
    assert fact["available"] is True
    assert fact["equity"] == 5123.45
    assert fact["day_pnl"] == pytest.approx(123.45)
    assert fact["tripped"] is False


def test_gather_account_breaker_bold_uses_its_own_key_names(tmp_path):
    p = tmp_path / "circuit-breaker.json"
    p.write_text(json.dumps({
        "tripped": True, "trip_reason": "daily_loss_kill_switch",
        "equity_start_of_day": 5000.0, "equity_current": 4700.0,
    }), encoding="utf-8")
    fact = sf.gather_account_breaker(p, "bold")
    assert fact["available"] is True
    assert fact["equity"] == 4700.0
    assert fact["day_pnl"] == pytest.approx(-300.0)
    assert fact["tripped"] is True
    assert fact["tripped_reason"] == "daily_loss_kill_switch"


def test_gather_account_breaker_missing_file_is_unavailable_not_zero(tmp_path):
    fact = sf.gather_account_breaker(tmp_path / "does-not-exist.json", "safe")
    assert fact["available"] is False
    assert "equity" not in fact  # never fabricates a 0 in place of a real reading


# ============================================================================
# decide_action -- station_mode_fn (GOAL-GAMMA-STATION-2026-09-13 item 6):
# "gaming"/"off" yield, "work" passes, all injected -- no real mode.json read.
# ============================================================================

def test_decide_action_yields_for_gaming_mode():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 0,
                                      process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                      station_mode_fn=lambda: "gaming")
    assert status == "yielded"
    assert "gaming" in reason.lower()


def test_decide_action_yields_for_off_mode():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 0,
                                      process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                      station_mode_fn=lambda: "off")
    assert status == "yielded"
    assert "off" in reason.lower()


def test_decide_action_ok_for_work_mode():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 0,
                                      process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                      station_mode_fn=lambda: "work")
    assert (status, reason) == ("ok", "")


def test_decide_action_force_still_bypasses_station_mode():
    # force=True (a manual run) skips the mode/RTH/GPU/denylist checks entirely --
    # confirms station_mode_fn is read inside the `if not force:` branch, not before it.
    status, _ = sl.decide_action(_TUE_RTH_UTC, _cfg(), force=True, gpu_util_fn=lambda: 0,
                                 process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True,
                                 station_mode_fn=lambda: "gaming")
    assert status == "ok"


# ============================================================================
# station_board -- dashboard-inbox consumption (Test/Kill/Ask interactivity,
# 2026-09-13 amendment 3): apply_inbox_actions, render_pending_notes_text,
# read_jsonl/append_jsonl.
# ============================================================================

def test_apply_inbox_actions_kill_sets_status_no_note():
    board = [{"id": "c1", "title": "Idea one", "status": "proposed"}]
    inbox = [{"card_id": "c1", "action": "kill", "note": ""}]
    new_board, notes = sb.apply_inbox_actions(board, inbox)
    assert new_board[0]["status"] == "killed"
    assert notes == []


def test_apply_inbox_actions_test_sets_status_and_queues_note():
    board = [{"id": "c1", "title": "Idea one", "status": "proposed",
             "proposed_shadow_test": "Replay the trades with a 5min stop."}]
    inbox = [{"card_id": "c1", "action": "test", "note": "make it fast"}]
    new_board, notes = sb.apply_inbox_actions(board, inbox)
    assert new_board[0]["status"] == "testing"
    assert len(notes) == 1
    assert notes[0]["action"] == "test"
    assert notes[0]["proposed_shadow_test"] == "Replay the trades with a 5min stop."
    assert notes[0]["note"] == "make it fast"


def test_apply_inbox_actions_ask_queues_note_no_status_change():
    board = [{"id": "c1", "title": "Idea one", "status": "proposed"}]
    inbox = [{"card_id": "c1", "action": "ask", "note": "why does this matter?"}]
    new_board, notes = sb.apply_inbox_actions(board, inbox)
    assert new_board[0]["status"] == "proposed"  # unchanged
    assert len(notes) == 1
    assert notes[0]["action"] == "ask"
    assert notes[0]["note"] == "why does this matter?"


def test_apply_inbox_actions_unknown_card_id_is_skipped_not_raised():
    board = [{"id": "c1", "title": "Idea one", "status": "proposed"}]
    inbox = [{"card_id": "does-not-exist", "action": "kill", "note": ""}]
    new_board, notes = sb.apply_inbox_actions(board, inbox)
    assert new_board == board
    assert notes == []


def test_apply_inbox_actions_never_mutates_caller_board_in_place():
    board = [{"id": "c1", "title": "Idea one", "status": "proposed"}]
    inbox = [{"card_id": "c1", "action": "kill", "note": ""}]
    sb.apply_inbox_actions(board, inbox)
    assert board[0]["status"] == "proposed", "caller's original board/card dict must not be mutated"


def test_render_pending_notes_text_empty_list_is_empty_string():
    assert sb.render_pending_notes_text([]) == ""


def test_render_pending_notes_text_includes_test_and_ask_notes():
    notes = [
        {"card_id": "c1", "action": "test", "title": "Idea one", "proposed_shadow_test": "Do X", "note": ""},
        {"card_id": "c2", "action": "ask", "title": "Idea two", "note": "explain the mechanism"},
    ]
    text = sb.render_pending_notes_text(notes)
    assert "Idea one" in text and "Do X" in text
    assert "Idea two" in text and "explain the mechanism" in text


def test_read_jsonl_skips_malformed_lines(tmp_path):
    p = tmp_path / "inbox.jsonl"
    p.write_text('{"a": 1}\nNOT JSON\n{"a": 2}\n', encoding="utf-8")
    rows = sb.read_jsonl(p)
    assert rows == [{"a": 1}, {"a": 2}]


def test_read_jsonl_missing_file_returns_empty_list(tmp_path):
    assert sb.read_jsonl(tmp_path / "does-not-exist.jsonl") == []


def test_append_jsonl_appends_without_clobbering(tmp_path):
    p = tmp_path / "inbox.jsonl"
    sb.append_jsonl(p, [{"a": 1}])
    sb.append_jsonl(p, [{"a": 2}, {"a": 3}])
    assert sb.read_jsonl(p) == [{"a": 1}, {"a": 2}, {"a": 3}]


def test_append_jsonl_empty_list_is_a_no_op(tmp_path):
    p = tmp_path / "inbox.jsonl"
    sb.append_jsonl(p, [])
    assert not p.exists()


# ============================================================================
# station_loop.drain_inbox -- full file-level round trip (own tmp_path paths,
# never the real repo's automation/state/station/*).
# ============================================================================

@pytest.fixture()
def _inbox_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "INBOX_PATH", tmp_path / "station-inbox.jsonl")
    monkeypatch.setattr(sl, "INBOX_PROCESSED_PATH", tmp_path / "station-inbox-processed.jsonl")
    monkeypatch.setattr(sl, "PENDING_NOTES_PATH", tmp_path / "station-pending-notes.json")
    return tmp_path


def test_drain_inbox_no_file_is_a_no_op(_inbox_paths):
    assert sl.drain_inbox() == 0
    assert not sl.IDEAS_BOARD_PATH.exists()


def test_drain_inbox_applies_kill_and_archives_row(_inbox_paths):
    sl.IDEAS_BOARD_PATH.write_text(
        json.dumps([{"id": "c1", "title": "Idea one", "status": "proposed"}]), encoding="utf-8")
    sl.INBOX_PATH.write_text(json.dumps({"card_id": "c1", "action": "kill", "note": ""}) + "\n", encoding="utf-8")

    drained = sl.drain_inbox()

    assert drained == 1
    board = json.loads(sl.IDEAS_BOARD_PATH.read_text(encoding="utf-8"))
    assert board[0]["status"] == "killed"
    assert sl.INBOX_PATH.read_text(encoding="utf-8").strip() == "", "inbox must be drained to empty"
    processed = sb.read_jsonl(sl.INBOX_PROCESSED_PATH)
    assert len(processed) == 1 and processed[0]["card_id"] == "c1"


def test_drain_inbox_ask_action_persists_pending_note_across_fires(_inbox_paths):
    sl.IDEAS_BOARD_PATH.write_text(
        json.dumps([{"id": "c1", "title": "Idea one", "status": "proposed"}]), encoding="utf-8")
    sl.INBOX_PATH.write_text(
        json.dumps({"card_id": "c1", "action": "ask", "note": "explain this"}) + "\n", encoding="utf-8")

    sl.drain_inbox()

    pending = json.loads(sl.PENDING_NOTES_PATH.read_text(encoding="utf-8"))
    assert len(pending) == 1
    assert pending[0]["note"] == "explain this"

    # A second, empty-inbox fire must not lose or duplicate the pending note.
    drained_again = sl.drain_inbox()
    assert drained_again == 0
    pending_after = json.loads(sl.PENDING_NOTES_PATH.read_text(encoding="utf-8"))
    assert pending_after == pending


def test_run_once_folds_pending_notes_into_prompt(monkeypatch, _inbox_paths):
    """Verifies the FOLD half of the pending-notes contract: a note queued by
    drain_inbox() (from a dashboard Ask/Test action) reaches the model's
    prompt text on the next actual model-calling fire.

    NOT asserted here: clearing station-pending-notes.json after a successful
    fire delivers the note. Reading the current run_once() shows it reads and
    folds pending notes into facts_text but never clears PENDING_NOTES_PATH
    afterward -- so today a delivered note is folded into every subsequent
    fire's prompt too, not just the next one. station_loop.py is outside this
    session's edit ownership (Fable owns it this build); flagged in the final
    report rather than fixed here or asserted as correct behavior in this test."""
    sl.PENDING_NOTES_PATH.write_text(
        json.dumps([{"card_id": "c1", "action": "ask", "title": "Idea one", "note": "explain this"}]),
        encoding="utf-8")
    _stub_ok_decision(monkeypatch)
    captured = {}

    def _fake_call(model, system_text, user_text, base_url, num_ctx, timeout=300):
        captured["user_text"] = user_text
        return _fake_ollama_response(brief="ok")

    monkeypatch.setattr(sl, "call_ollama_chat", _fake_call)

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["status"] == "ok"
    assert "explain this" in captured["user_text"]
    assert "J's direct requests" in captured["user_text"]


def test_run_once_keeps_pending_notes_on_model_call_failure(monkeypatch, _inbox_paths):
    sl.PENDING_NOTES_PATH.write_text(
        json.dumps([{"card_id": "c1", "action": "ask", "title": "Idea one", "note": "explain this"}]),
        encoding="utf-8")
    _stub_ok_decision(monkeypatch)
    monkeypatch.setattr(sl, "call_ollama_chat", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))

    row = sl.run_once(now_utc=_TUE_AFTERHOURS_UTC)

    assert row["status"] == "error"
    pending_after = json.loads(sl.PENDING_NOTES_PATH.read_text(encoding="utf-8"))
    assert len(pending_after) == 1, "a failed model call must never lose J's queued note"


# ============================================================================
# 2026-09-14 company-roster re-point (C1-C3): sectors.json + crew-events.jsonl.
# Chef's verdict-scoring pass and Coach's sectors/task-health pass already ran every
# fire before this build -- nothing wrote down that either had done anything (J's
# 2026-09-14 verdict: "'quiet since 09:05' for Chef -- okay, why?"). These tests lock
# in: sectors.json/crew-events.jsonl are written on a YIELDED fire (never gated on the
# LLM branch); the Chef verdict ticker only fires on a REAL change (hypothesis_scorer
# re-scores every testing card every fire even when nothing moved -- verified live
# 2026-09-14 via three byte-identical n_post=0 ledger rows 30 minutes apart); the Coach
# sectors row respects the change-or-heartbeat rule; task_health deltas fire on a
# Disabled-state flip; and crew_events/sector_rows failures degrade the Station fire,
# never crash it.
# ============================================================================

def test_run_once_writes_sectors_json_on_a_yielded_fire(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [
        {"lane": "SPY 0DTE core", "state": "armed-paper", "arm_or_acct_alias": "safe-2",
         "last_evidence_et": "2026-09-14 11:00:00 ET", "evidence": "e", "window_pnl": 1.0,
         "health": "green", "doc": "CLAUDE.md"},
    ])

    row = sl.run_once(now_utc=_TUE_RTH_UTC)

    assert row["status"] == "yielded", "the model must never be called on a yielded fire"
    assert sl.SECTORS_PATH.exists(), "sectors.json must be written even when the fire yields"
    doc = json.loads(sl.SECTORS_PATH.read_text(encoding="utf-8"))
    assert doc["rows"][0]["lane"] == "SPY 0DTE core"
    assert doc["summary_line"].startswith("1 lanes")
    assert set(doc.keys()) == {"ts_et", "rows", "summary_line", "task_health"}
    assert set(doc["task_health"].keys()) == {"ts_et", "disabled", "failed_last_run", "total", "source"}


def test_run_once_writes_crew_events_on_a_yielded_fire(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))

    sl.run_once(now_utc=_TUE_RTH_UTC)

    assert sl.CREW_EVENTS_PATH.exists(), "crew-events.jsonl must be written even when the fire yields"
    rows = sb.read_jsonl(sl.CREW_EVENTS_PATH)
    assert any(r.get("who") == "Coach" and r.get("kind") == "sectors" for r in rows)


def test_run_once_survives_a_totally_broken_sectors_crew_events_call(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))
    monkeypatch.setattr(sl, "_write_sectors_and_crew_events",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("everything is on fire")))

    row = sl.run_once(now_utc=_TUE_RTH_UTC)  # must not raise

    assert row["status"] == "yielded"


def test_write_sectors_and_crew_events_fails_open_when_build_sector_rows_raises(monkeypatch):
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("disk on fire")))

    sl._write_sectors_and_crew_events("2026-09-14 12:00:00 ET", _TUE_AFTERHOURS_UTC, dict(sl.DEFAULT_CONFIG))

    doc = json.loads(sl.SECTORS_PATH.read_text(encoding="utf-8"))
    assert doc["rows"] == []
    assert doc["summary_line"].startswith("0 lanes")


def test_sectors_summary_line_counts_green_red_frozen_and_names_first_red_lane():
    rows = [
        {"lane": "A", "health": "green"},
        {"lane": "B", "health": "red", "evidence": "broker down"},
        {"lane": "C", "health": "red", "evidence": "also broken"},
        {"lane": "D", "health": "frozen"},
        {"lane": "E", "health": "amber"},
    ]
    line = sl._sectors_summary_line(rows)
    assert line.startswith("5 lanes")
    assert "1 GREEN" in line
    assert "2 RED" in line
    assert "B: broker down" in line
    assert "1 frozen" in line


def test_sectors_summary_line_no_red_lanes_has_no_parenthetical():
    line = sl._sectors_summary_line([{"lane": "A", "health": "green"}])
    assert "0 RED" in line
    assert "(" not in line


def test_write_sectors_and_crew_events_sectors_row_only_on_change_or_heartbeat(monkeypatch):
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [{"lane": "A", "health": "green"}])
    cfg = dict(sl.DEFAULT_CONFIG)

    def _fire(now_utc):
        sl._write_sectors_and_crew_events(sl.et_now(now_utc=now_utc).strftime("%Y-%m-%d %H:%M:%S ET"), now_utc, cfg)

    _fire(_TUE_AFTERHOURS_UTC)
    rows1 = [r for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "sectors"]
    assert len(rows1) == 1, "the first-ever sectors write has no prior row to compare -- must emit"

    # Same summary line, 5 min later (well inside the 3h heartbeat) -> no new row.
    _fire(_TUE_AFTERHOURS_UTC + timedelta(minutes=5))
    rows2 = [r for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "sectors"]
    assert len(rows2) == 1, "an unchanged summary inside the heartbeat window must not re-emit"

    # Same summary line, past the 3h heartbeat -> re-emits as a keepalive.
    _fire(_TUE_AFTERHOURS_UTC + timedelta(hours=3, minutes=5))
    rows3 = [r for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "sectors"]
    assert len(rows3) == 2, "an unchanged summary past the heartbeat window must re-emit (the ~3h keepalive)"

    # A changed summary -> emits regardless of timing.
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows",
                        lambda *a, **kw: [{"lane": "A", "health": "red", "evidence": "down"}])
    _fire(_TUE_AFTERHOURS_UTC + timedelta(hours=3, minutes=6))
    rows4 = [r for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "sectors"]
    assert len(rows4) == 3, "a changed summary must always emit, regardless of timing"


def test_write_sectors_and_crew_events_task_health_delta_emits_went_disabled_and_came_back(monkeypatch):
    calls = {"n": 0}

    def _fake_health(now_utc, **kw):
        calls["n"] += 1
        disabled = ["Gamma_Foo"] if calls["n"] == 2 else []
        return {"ts_et": f"t{calls['n']}", "disabled": disabled, "failed_last_run": [], "total": 2, "source": "fake"}

    monkeypatch.setattr(sl, "_task_health_snapshot", _fake_health)
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [])
    cfg = dict(sl.DEFAULT_CONFIG)

    sl._write_sectors_and_crew_events("t1", _TUE_AFTERHOURS_UTC, cfg)                      # baseline: nothing disabled
    sl._write_sectors_and_crew_events("t2", _TUE_AFTERHOURS_UTC + timedelta(minutes=1), cfg)  # Gamma_Foo flips Disabled
    sl._write_sectors_and_crew_events("t3", _TUE_AFTERHOURS_UTC + timedelta(minutes=2), cfg)  # Gamma_Foo flips back

    lines = [r["line"] for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "task_health"]
    assert "Coach: Gamma_Foo went Disabled" in lines
    assert "Coach: Gamma_Foo came back Ready" in lines


def test_emit_chef_verdict_events_only_fires_on_a_real_change(monkeypatch):
    monkeypatch.setattr(sl, "decide_action", lambda now_utc, config, **kw: ("yielded", "rth_window (weekday 09:30-15:55 ET)"))
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [])

    card = {"id": "c1", "ts_et": "2026-09-01 12:00:00 ET", "status": "testing", "title": "cap size",
            "test_spec": {"type": "size_cap", "params": {"cap": 3, "strategy": "RIDE_THE_RIBBON"}}}
    sl.IDEAS_BOARD_PATH.write_text(json.dumps([card]), encoding="utf-8")
    sl.AUTOPSY_DIR.mkdir(parents=True, exist_ok=True)
    # Both rows pre-date the card's own ts_et -> pre-registration only, n_post stays 0 on
    # every rescore (identical to the real station-verdicts.jsonl rows this test mirrors).
    rows = [{"date": "2026-08-25", "qty": 5, "actual_pnl": -100.0}] * 2
    (sl.AUTOPSY_DIR / "all.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    sl.run_once(now_utc=_TUE_RTH_UTC)  # fire 1: no prior verdict on the card -> "first verdict" -> must emit
    events_1 = [r for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "verdict"]
    assert len(events_1) == 1
    assert events_1[0]["who"] == "Chef"
    assert events_1[0]["ref"] == "c1"
    assert "size_cap(3)" in events_1[0]["line"]
    assert "RIDE_THE_RIBBON" in events_1[0]["line"]

    sl.run_once(now_utc=_TUE_RTH_UTC)  # fire 2: identical autopsy data -> n_post/status unchanged
    events_2 = [r for r in sb.read_jsonl(sl.CREW_EVENTS_PATH) if r.get("kind") == "verdict"]
    assert len(events_2) == 1, "an unchanged re-score must not spam a duplicate Chef ticker line"


def test_format_chef_verdict_line_matches_the_real_bullish_reclaim_shape():
    spec = {"type": "size_cap", "params": {"cap": 3, "strategy": "BULLISH_RECLAIM_RIDE_THE_RIBBON"}}
    result = {"effect_pre": 1236.6, "n_pre": 148, "effect_post": None, "n_post": 0}
    line = sl._format_chef_verdict_line({"id": "f5deabe978", "title": "x"}, spec, result, "testing", 10)
    assert line == ("Chef: size_cap(3) on BULLISH_RECLAIM_RIDE_THE_RIBBON — pre +$1,237 (n 148) "
                    "· post n 0/10 → testing")


def test_format_chef_verdict_line_falls_back_to_title_when_no_strategy_or_arm():
    spec = {"type": "metric_correlation", "params": {"x": "entry_slippage"}}
    result = {"effect_pre": 0.42, "n_pre": 30, "effect_post": None, "n_post": 12}
    line = sl._format_chef_verdict_line({"id": "abc", "title": "Slippage vs entry delay"}, spec, result, "supported", 10)
    assert "metric_correlation(entry_slippage~actual_pnl)" in line
    assert "Slippage vs entry delay" in line, "no strategy/arm in params -- must fall back to the card title"
    assert "r=+0.420" in line, "metric_correlation's effect_pre must format as a correlation, not a dollar amount"
    assert "post n 12/10" in line
    assert line.endswith("supported")


def test_task_health_snapshot_real_logic_lists_disabled_gamma_tasks_only():
    fake_tasks = [
        {"name": "Gamma_Foo", "state": "Ready"},
        {"name": "Gamma_Bar", "state": "Disabled"},
        {"name": "Gamma_Baz", "state": "Disabled"},
        {"name": "NotGamma_Qux", "state": "Disabled"},  # excluded -- not a Gamma_* task
    ]
    result = _REAL_TASK_HEALTH_SNAPSHOT(_TUE_AFTERHOURS_UTC, registered_tasks_fn=lambda: fake_tasks)
    assert result["disabled"] == ["Gamma_Bar", "Gamma_Baz"]
    assert result["total"] == 3
    assert result["failed_last_run"] == []
    assert "LastTaskResult" in result["source"]


def test_task_health_snapshot_fails_open_on_enumeration_error():
    def _boom():
        raise RuntimeError("Get-ScheduledTask unavailable")
    result = _REAL_TASK_HEALTH_SNAPSHOT(_TUE_AFTERHOURS_UTC, registered_tasks_fn=_boom)
    assert result["disabled"] == []
    assert result["total"] == 0
    assert "unavailable" in result["source"]


# ============================================================================
# 2026-09-14 bug fix: synthetic-clock-vs-real-path guard in
# _write_sectors_and_crew_events. Found live -- test_station_yield_unload.py's
# pre-existing fixture called run_once(now_utc=SUNDAY_EVENING_UTC) twice without
# isolating SECTORS_PATH/CREW_EVENTS_PATH, writing real rows stamped
# '2026-09-13 18:00:00 ET' into the real repo. The fixture is now fixed (the
# correct, preferred fix); this guard is defense in depth so ANY future caller
# with the same mistake degrades to a no-op instead of corrupting live state.
# REPO itself is redirected to tmp_path here (never the real absolute path) so
# this test can prove the guard's real-path branch without ever risking a write
# to the actual repo.
# ============================================================================

def test_write_sectors_and_crew_events_skips_on_synthetic_clock_at_a_real_shaped_path(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "REPO", tmp_path)
    real_sectors = tmp_path / "automation" / "state" / "station" / "sectors.json"
    real_crew_events = tmp_path / "automation" / "state" / "station" / "crew-events.jsonl"
    monkeypatch.setattr(sl, "SECTORS_PATH", real_sectors)
    monkeypatch.setattr(sl, "CREW_EVENTS_PATH", real_crew_events)
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [{"lane": "A", "health": "green"}])
    monkeypatch.setattr(sl, "_task_health_snapshot", lambda now_utc, **kw: {
        "ts_et": "x", "disabled": [], "failed_last_run": [], "total": 0, "source": "stub"})

    far_clock = datetime(2020, 1, 1, tzinfo=timezone.utc)  # decades of drift -- unambiguous
    sl._write_sectors_and_crew_events("2020-01-01 00:00:00 ET", far_clock, dict(sl.DEFAULT_CONFIG))

    assert not real_sectors.exists(), "a synthetic clock at a real-shaped path must skip the write entirely"
    assert not real_crew_events.exists()


def test_write_sectors_and_crew_events_proceeds_on_a_fresh_clock_at_the_same_path(monkeypatch, tmp_path):
    # Same "real"-shaped path as above -- proves the guard keys off clock drift, not the
    # path alone, so a genuine production fire (now_utc always close to wall-clock time)
    # is never blocked just because it happens to write to the real location.
    monkeypatch.setattr(sl, "REPO", tmp_path)
    real_sectors = tmp_path / "automation" / "state" / "station" / "sectors.json"
    real_crew_events = tmp_path / "automation" / "state" / "station" / "crew-events.jsonl"
    monkeypatch.setattr(sl, "SECTORS_PATH", real_sectors)
    monkeypatch.setattr(sl, "CREW_EVENTS_PATH", real_crew_events)
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [{"lane": "A", "health": "green"}])
    monkeypatch.setattr(sl, "_task_health_snapshot", lambda now_utc, **kw: {
        "ts_et": "x", "disabled": [], "failed_last_run": [], "total": 0, "source": "stub"})

    fresh_clock = datetime.now(timezone.utc)
    sl._write_sectors_and_crew_events(sl.et_now(now_utc=fresh_clock).strftime("%Y-%m-%d %H:%M:%S ET"),
                                      fresh_clock, dict(sl.DEFAULT_CONFIG))

    assert real_sectors.exists(), "a fresh (real-fire) clock must proceed even at a real-shaped path"


def test_write_sectors_and_crew_events_guard_respects_the_15_minute_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "REPO", tmp_path)
    real_sectors = tmp_path / "automation" / "state" / "station" / "sectors.json"
    monkeypatch.setattr(sl, "SECTORS_PATH", real_sectors)
    monkeypatch.setattr(sl, "CREW_EVENTS_PATH", tmp_path / "automation" / "state" / "station" / "crew-events.jsonl")
    monkeypatch.setattr(sl.sector_rows, "build_sector_rows", lambda *a, **kw: [])
    monkeypatch.setattr(sl, "_task_health_snapshot", lambda now_utc, **kw: {
        "ts_et": "x", "disabled": [], "failed_last_run": [], "total": 0, "source": "stub"})

    just_inside = datetime.now(timezone.utc) - timedelta(minutes=10)  # < 15m -- must proceed
    sl._write_sectors_and_crew_events("t", just_inside, dict(sl.DEFAULT_CONFIG))
    assert real_sectors.exists(), "10 minutes of drift is well inside the 15-minute guard threshold"
