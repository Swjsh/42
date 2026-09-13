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
from datetime import datetime, timezone
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
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True)
    assert status == "yielded"
    assert "rth" in reason.lower()


def test_decide_action_yields_on_weekend_too():
    # Weekend is also "not RTH" for is_market_hours, but confirms the same code path holds
    # for the weekday-independent branch of the clock, not just the after-hours case.
    status, reason = sl.decide_action(_SAT_UTC, _cfg(), gpu_util_fn=lambda: 90,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True)
    # Saturday is not RTH, so this falls through to the GPU check (90% > 50% default) --
    # proving decide_action does NOT mistake a weekend for an RTH yield.
    assert status == "yielded"
    assert "gpu" in reason.lower()


def test_decide_action_ok_outside_rth_when_nothing_else_trips():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 10,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True)
    assert (status, reason) == ("ok", "")


def test_decide_action_yields_when_gpu_above_threshold():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(gpu_util_yield_pct=50),
                                       gpu_util_fn=lambda: 51, process_table_fn=lambda: {},
                                       ollama_reachable_fn=lambda u: True)
    assert status == "yielded"
    assert "gpu" in reason.lower()


def test_decide_action_ok_when_gpu_below_threshold():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(gpu_util_yield_pct=50),
                                       gpu_util_fn=lambda: 49, process_table_fn=lambda: {},
                                       ollama_reachable_fn=lambda u: True)
    assert status == "ok"


def test_decide_action_gpu_unmeasurable_fails_open():
    # nvidia-smi missing/erroring returns None -- that is "no signal," never a yield.
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: None,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: True)
    assert status == "ok"


def test_decide_action_yields_when_denylisted_process_present():
    cfg = _cfg(yield_processes=["steam.exe"])
    table = {1234: 'C:\\Program Files (x86)\\Steam\\steam.exe" -silent'}
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, cfg, gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: table, ollama_reachable_fn=lambda u: True)
    assert status == "yielded"
    assert "steam.exe" in reason


def test_decide_action_ok_when_no_denylisted_process():
    cfg = _cfg(yield_processes=["steam.exe"])
    table = {1234: "C:\\Windows\\explorer.exe"}
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, cfg, gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: table, ollama_reachable_fn=lambda u: True)
    assert status == "ok"


def test_decide_action_process_table_unreadable_fails_open():
    def _boom():
        raise OSError("no powershell")
    cfg = _cfg(yield_processes=["steam.exe"])
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, cfg, gpu_util_fn=lambda: 0,
                                       process_table_fn=_boom, ollama_reachable_fn=lambda u: True)
    assert status == "ok"


def test_decide_action_error_when_ollama_unreachable():
    status, reason = sl.decide_action(_TUE_AFTERHOURS_UTC, _cfg(), gpu_util_fn=lambda: 0,
                                       process_table_fn=lambda: {}, ollama_reachable_fn=lambda u: False)
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
