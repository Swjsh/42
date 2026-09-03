"""Guard tests for setup/scripts/futures_health.py (built 2026-08-29) -- the futures-lane
liveness instrument that closes the "self_check.py has ZERO futures awareness" gap found
during the go-live audit. Pure filesystem/time logic; the scheduled-task PowerShell query is
always monkeypatched (a fake `query=` callable) -- no real Get-ScheduledTask call, no real
process/task mutation, no network.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import futures_health as fh  # noqa: E402
import self_check as sc  # noqa: E402

NOW = dt.datetime(2026, 8, 29, 12, 0, 0)          # a Saturday -- CME closed all day
NOW_WEEKDAY_RTH = dt.datetime(2026, 8, 28, 13, 0, 0)  # a Friday, 13:00 ET -- CME open (RTH)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        path.write_text(obj, encoding="utf-8")
    else:
        path.write_text(json.dumps(obj), encoding="utf-8")


def _append_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# 1. ghost pending_entry signature -> RED with the age in the reason
# ---------------------------------------------------------------------------
def test_ghost_pending_entry_is_red_with_age_in_reason(tmp_path):
    p = tmp_path / "fillsim-positions.json"
    placed = (NOW - dt.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S")
    _write(p, {"MES": {"status": "pending_entry", "placed_time_et": placed}})
    result = fh.check_can_enter(NOW, positions_path=p)
    assert result["status"] == "RED"
    assert "45.0" in result["detail"] or "45." in result["detail"]
    assert "GHOST-ORDER DEADLOCK" in result["detail"]


def test_fresh_pending_entry_is_not_red(tmp_path):
    p = tmp_path / "fillsim-positions.json"
    placed = (NOW - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
    _write(p, {"MES": {"status": "pending_entry", "placed_time_et": placed}})
    result = fh.check_can_enter(NOW, positions_path=p)
    assert result["status"] == "GREEN"


def test_flat_positions_file_is_green(tmp_path):
    p = tmp_path / "fillsim-positions.json"
    _write(p, {})
    assert fh.check_can_enter(NOW, positions_path=p)["status"] == "GREEN"


def test_open_position_is_not_a_deadlock(tmp_path):
    """status=open is a legitimately held position, not the pending_entry deadlock."""
    p = tmp_path / "fillsim-positions.json"
    _write(p, {"MES": {"status": "open", "order_id": "x"}})
    assert fh.check_can_enter(NOW, positions_path=p)["status"] == "GREEN"


# ---------------------------------------------------------------------------
# 2. quiet day, zero signals, zero fills -> stays GREEN (never flagged)
# ---------------------------------------------------------------------------
def test_quiet_day_zero_signals_stays_green(tmp_path):
    p = tmp_path / "decisions.jsonl"
    rows = []
    base = NOW - dt.timedelta(days=10)
    for i in range(10):
        d = (base + dt.timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append({"ts_et": f"{d}T12:00:00", "action": "HOLD", "reason": "no_signal"})
    _append_jsonl(p, rows)
    result = fh.check_fills_recency(NOW, decisions_path=p)
    assert result["status"] == "GREEN"
    assert "quiet day" in result["detail"] or "not a failure" in result["detail"]


def test_can_enter_and_fills_recency_both_green_on_a_quiet_day(tmp_path):
    """Integration-shaped: the doctrine case ('sitting out is a valid day') must never
    flag EITHER of the two checks most likely to over-fire on a quiet market."""
    pos = tmp_path / "fillsim-positions.json"
    _write(pos, {})
    dec = tmp_path / "decisions.jsonl"
    _append_jsonl(dec, [{"ts_et": "2026-08-24T12:00:00", "action": "HOLD", "reason": "no_signal"}])
    assert fh.check_can_enter(NOW, positions_path=pos)["status"] == "GREEN"
    assert fh.check_fills_recency(NOW, decisions_path=dec)["status"] == "GREEN"


# ---------------------------------------------------------------------------
# 3. signals-seen + repeated ENTER_REFUSED across sessions -> RED
# ---------------------------------------------------------------------------
def test_repeated_enter_refused_across_sessions_is_red(tmp_path):
    p = tmp_path / "decisions.jsonl"
    rows = []
    dates = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
    for d in dates[:-2]:
        rows.append({"ts_et": f"{d}T12:00:00", "action": "HOLD", "reason": "no_signal"})
    for d in dates[-2:]:
        rows.append({"ts_et": f"{d}T13:00:01", "action": "ENTER_REFUSED",
                     "reason": "ERL_IRL_SWEEP_FVG", "n_signals": 1})
    _append_jsonl(p, rows)
    result = fh.check_fills_recency(NOW, decisions_path=p)
    assert result["status"] == "RED"
    assert "ENTER_REFUSED" in result["detail"]
    assert "SIGNALS SEEN BUT ENTRY REFUSED" in result["detail"]


def test_single_session_enter_refused_is_only_yellow(tmp_path):
    """One isolated refusal is not yet 'repeatedly' -- below the RED threshold."""
    p = tmp_path / "decisions.jsonl"
    rows = [
        {"ts_et": "2026-08-27T12:00:00", "action": "HOLD", "reason": "no_signal"},
        {"ts_et": "2026-08-28T13:00:01", "action": "ENTER_REFUSED", "reason": "x"},
    ]
    _append_jsonl(p, rows)
    result = fh.check_fills_recency(NOW, decisions_path=p)
    assert result["status"] == "YELLOW"


# ---------------------------------------------------------------------------
# 4. Disabled AND in quiet-mode-restore.json -> QUIESCED-BY-DESIGN, not RED
# ---------------------------------------------------------------------------
def test_disabled_task_in_restore_list_is_quiesced_not_outage(tmp_path):
    restore = tmp_path / "quiet-mode-restore.json"
    _write(restore, {"restore_to_ready": ["Gamma_FuturesTrader", "Gamma_FuturesMirror"]})

    def fake_query(names):
        return [
            {"TaskName": "Gamma_FuturesTrader", "State": "Disabled",
             "LastRunTime": "2026-08-29T10:00:00", "LastTaskResult": 0, "Error": None},
        ]

    result = fh.check_task_liveness(task_names=("Gamma_FuturesTrader",),
                                    quiet_restore_path=restore, query=fake_query)
    assert result["status"] == "GREEN"
    assert "QUIESCED-BY-DESIGN" in result["detail"]


# ---------------------------------------------------------------------------
# 5. Disabled and NOT in that list -> IS an outage
# ---------------------------------------------------------------------------
def test_disabled_task_not_in_restore_list_is_an_outage(tmp_path):
    restore = tmp_path / "quiet-mode-restore.json"
    _write(restore, {"restore_to_ready": ["Gamma_FuturesMirror"]})  # Trader NOT listed

    def fake_query(names):
        return [
            {"TaskName": "Gamma_FuturesTrader", "State": "Disabled",
             "LastRunTime": "2026-08-29T10:00:00", "LastTaskResult": 1, "Error": None},
        ]

    result = fh.check_task_liveness(task_names=("Gamma_FuturesTrader",),
                                    quiet_restore_path=restore, query=fake_query)
    assert result["status"] == "RED"
    assert "OUTAGE" in result["detail"]
    assert "Gamma_FuturesTrader" in result["detail"]


def test_enabled_ready_task_is_green(tmp_path):
    restore = tmp_path / "quiet-mode-restore.json"
    _write(restore, {"restore_to_ready": []})

    def fake_query(names):
        return [{"TaskName": "Gamma_FuturesTrader", "State": "Ready",
                 "LastRunTime": "2026-08-29T10:00:00", "LastTaskResult": 0, "Error": None}]

    result = fh.check_task_liveness(task_names=("Gamma_FuturesTrader",),
                                    quiet_restore_path=restore, query=fake_query)
    assert result["status"] == "GREEN"


# ---------------------------------------------------------------------------
# 6. every input file missing -> producer runs cleanly, UNKNOWN sub-verdicts
# ---------------------------------------------------------------------------
def test_every_input_missing_is_fail_open_unknown(tmp_path):
    missing_positions = tmp_path / "no-positions.json"
    missing_decisions = tmp_path / "no-decisions.jsonl"
    missing_transport = tmp_path / "no-transport.jsonl"
    missing_probe = tmp_path / "no-probe.jsonl"
    missing_freshness = tmp_path / "no-freshness.json"
    missing_restore = tmp_path / "no-restore.json"

    can_enter = fh.check_can_enter(NOW, positions_path=missing_positions)
    fills = fh.check_fills_recency(NOW, decisions_path=missing_decisions)
    transport = fh.check_broker_transport(NOW, transport_path=missing_transport,
                                          probe_path=missing_probe)
    freshness = fh.check_data_freshness(freshness_path=missing_freshness)
    tasks = fh.check_task_liveness(quiet_restore_path=missing_restore,
                                   query=lambda names: None)

    for result in (can_enter, fills, transport, freshness, tasks):
        assert result["status"] == "UNKNOWN", result

    # Fusion must not crash and must degrade to YELLOW (never a fabricated GREEN or RED)
    # when every check is UNKNOWN.
    worst = max(fh._SEVERITY[c["status"]]
               for c in (can_enter, fills, transport, freshness, tasks))
    assert fh._VERDICT_FOR_SEVERITY[worst] == "YELLOW"


def test_build_report_end_to_end_with_everything_missing(tmp_path, monkeypatch):
    """Full build_report() through a monkeypatched STATE with nothing on disk and an
    unavailable task query -- must run to completion, never raise, and the top-level
    verdict must be exactly one of GREEN/YELLOW/RED (never the string 'UNKNOWN')."""
    monkeypatch.setattr(fh, "STATE", tmp_path)
    monkeypatch.setattr(fh, "_default_query_tasks", lambda names: None)
    report = fh.build_report(now_et=NOW)
    assert report["verdict"] in ("GREEN", "YELLOW", "RED")
    assert report["verdict"] == "YELLOW"
    # 6, not 5: broker_exit_pairing (FUTURES-BROKER-LANE-NEVER-LOGS-EXITS, 2026-09-03) added
    # a 6th check. It degrades to UNKNOWN here for the same reason every other check does --
    # STATE is monkeypatched to an empty tmp_path, so trader-broker/decisions.jsonl is missing.
    assert len(report["checks"]) == 6
    assert all(c["status"] == "UNKNOWN" for c in report["checks"])
    assert len(report["reasons"]) == 6


# ---------------------------------------------------------------------------
# 7. SESSION_NOT_ACTIVE outside CME hours does not produce RED
# ---------------------------------------------------------------------------
def test_session_not_active_outside_cme_hours_is_not_red(tmp_path):
    probe = tmp_path / "broker-probe.jsonl"
    _append_jsonl(probe, [
        {"at_et": "2026-08-29T10:00:00", "session_phase": "WEEKEND", "session_open": False,
         "dry_run_ok": False, "error": "TastytradeError: tif.futures_session_not_active",
         "verdict": "SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)"},
        {"at_et": "2026-08-29T11:00:00", "session_phase": "WEEKEND", "session_open": False,
         "dry_run_ok": False, "error": "TastytradeError: tif.futures_session_not_active",
         "verdict": "SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)"},
    ])
    # NOW is a Saturday -- CME closed all day, matching the scenario.
    result = fh.check_broker_transport(NOW, transport_path=tmp_path / "no-transport.jsonl",
                                       probe_path=probe)
    assert result["status"] != "RED"
    assert result["status"] == "GREEN"


def test_real_transport_errors_during_open_session_is_red(tmp_path):
    """Contrast case for #7: the SAME error shape, but during an open CME session and
    NOT self-reported as session-closed -- outage #2's actual signature -- must RED."""
    probe = tmp_path / "broker-probe.jsonl"
    _append_jsonl(probe, [
        {"at_et": "2026-08-27T23:05:06", "dry_run_ok": False, "error": "ReadTimeout: ",
         "verdict": "H1_PERMISSIONS"},
        {"at_et": "2026-08-27T23:10:06", "dry_run_ok": False, "error": "ReadTimeout: ",
         "verdict": "H1_PERMISSIONS"},
        {"at_et": "2026-08-27T23:15:06", "dry_run_ok": False, "error": "ReadTimeout: ",
         "verdict": "H1_PERMISSIONS"},
    ])
    result = fh.check_broker_transport(NOW_WEEKDAY_RTH,
                                       transport_path=tmp_path / "no-transport.jsonl",
                                       probe_path=probe)
    assert result["status"] == "RED"
    assert "3/3" in result["detail"]


def test_probe_row_class_distinguishes_mislabeled_h1_permissions():
    """The core discovery documented in the module docstring: verdict=H1_PERMISSIONS is
    overloaded and can mean either a confirmed permission rejection (healthy transport) or
    a raw transport exception (ReadTimeout) mislabeled by the probe script. dry_run_ok is
    the only reliable discriminator."""
    confirmed_permission_reject = {"verdict": "H1_PERMISSIONS", "dry_run_ok": True,
                                   "errors": ["not permitted"]}
    mislabeled_timeout = {"verdict": "H1_PERMISSIONS", "dry_run_ok": False,
                          "error": "ReadTimeout: "}
    assert fh._probe_row_class(confirmed_permission_reject) == "healthy"
    assert fh._probe_row_class(mislabeled_timeout) == "error"


# ---------------------------------------------------------------------------
# data_freshness passthrough
# ---------------------------------------------------------------------------
def test_data_freshness_folds_existing_verdict_verbatim(tmp_path):
    p = tmp_path / "data-freshness.json"
    _write(p, {"verdict": "RED", "written_at_et": "2026-08-28T16:00:03",
              "feeds": {"MES": {"verdict": "RED", "age_minutes": 45.0}}})
    result = fh.check_data_freshness(freshness_path=p)
    assert result["status"] == "RED"
    assert "RED" in result["detail"]


def test_data_freshness_missing_is_unknown(tmp_path):
    result = fh.check_data_freshness(freshness_path=tmp_path / "nope.json")
    assert result["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# wiring / registration
# ---------------------------------------------------------------------------
def test_out_file_target_is_the_documented_path():
    assert fh.OUT_FILE == fh.STATE / "futures" / "health.json"


def test_main_never_raises_and_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(fh, "STATE", tmp_path)
    monkeypatch.setattr(fh, "OUT_FILE", tmp_path / "futures" / "health.json")
    monkeypatch.setattr(fh, "_default_query_tasks", lambda names: None)
    rc = fh.main()
    assert rc == 0
    assert (tmp_path / "futures" / "health.json").exists()
    written = json.loads((tmp_path / "futures" / "health.json").read_text(encoding="utf-8"))
    assert written["verdict"] in ("GREEN", "YELLOW", "RED")


# ---------------------------------------------------------------------------
# self_check.py fold-in (TASK 2): thin passthrough of futures_health.json's own verdict
# ---------------------------------------------------------------------------
def test_self_check_futures_missing_artifact_is_silent(tmp_path):
    """SILENT UNTIL DEPLOYED: futures_health.py never having fired must never look like a
    problem -- an UNKNOWN/missing futures artifact must never turn an otherwise-GREEN
    self_check RED (per the task spec)."""
    assert sc.check_futures_health(NOW, path=tmp_path / "no-health.json") == []


def test_self_check_futures_green_is_silent(tmp_path):
    p = tmp_path / "health.json"
    _write(p, {"verdict": "GREEN", "checks": [], "reasons": []})
    assert sc.check_futures_health(NOW, path=p) == []


def test_self_check_futures_red_reaches_problems_and_classifies_broken(tmp_path):
    p = tmp_path / "health.json"
    _write(p, {"verdict": "RED",
              "reasons": ["[RED] can_enter: MES pending_entry STUCK 21735.2m -- GHOST-ORDER "
                         "DEADLOCK signature"]})
    problems = sc.check_futures_health(NOW, path=p)
    assert len(problems) == 1
    assert "FUTURES-HEALTH RED" in problems[0]
    assert sc._problem_is_broken(problems[0]) is True


def test_self_check_futures_yellow_is_degraded_not_broken(tmp_path):
    p = tmp_path / "health.json"
    _write(p, {"verdict": "YELLOW", "reasons": ["[YELLOW] broker_transport: elevated error rate"]})
    problems = sc.check_futures_health(NOW, path=p)
    assert len(problems) == 1
    assert "FUTURES-HEALTH DEGRADED" in problems[0]
    assert sc._problem_is_broken(problems[0]) is False


def test_self_check_futures_corrupt_artifact_is_silent_not_a_crash(tmp_path):
    p = tmp_path / "health.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert sc.check_futures_health(NOW, path=p) == []


def test_self_check_registered_in_main_aggregator():
    """Wiring check: run() must actually call check_futures_health (matches the existing
    test_registered_in_main_aggregator pattern for check_quote_recorder_alive)."""
    src = (REPO / "setup" / "scripts" / "self_check.py").read_text(encoding="utf-8")
    assert "problems.extend(check_futures_health(now))" in src


if __name__ == "__main__":  # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
