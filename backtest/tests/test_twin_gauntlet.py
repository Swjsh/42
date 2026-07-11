"""Tests for setup/scripts/twin_gauntlet.py -- B2a (TWIN-PROGRAM.md value stream #2).

Covers: the gauntlet-queue.jsonl REQUEST-row schema round-trip, path-coverage.json
read/write helpers (pending_requests/record_path_result -- "the one-line hook"),
poll_results' TWO independent evidence sources (path-coverage.json AND journal.jsonl
fallback) + its honest timeout (never a silent pass), and --dry mode's full
pass/fail behavior INCLUDING the bite: every one of the 6 paths' "wrong-stage"
fixture must FAIL, proving the check is not vacuous (a --dry mode that always says
PASS would be worse than no gate at all).

All state-writing tests use an injected tmp_path -- never the real
automation/state/crypto-twin/ ledgers.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "automation/state/fleet", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import twin_gauntlet as tg  # noqa: E402


# ============================================================================
# Queue contract -- REQUEST row schema round-trip
# ============================================================================

_REQUEST_ROW_KEYS = {"request_id", "path", "n", "requested_at_utc", "requested_at_et",
                     "timeout_min", "status", "source"}


def test_request_paths_writes_append_only_schema_complete_rows(tmp_path):
    queue_path = tmp_path / "gauntlet-queue.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    rows = tg.request_paths(["tp1_trail", "structure_stop"], n=2, timeout_min=45,
                            queue_path=queue_path, now_utc=now)
    assert len(rows) == 2
    for r in rows:
        assert _REQUEST_ROW_KEYS <= set(r.keys())
        assert r["status"] == "REQUESTED"
        assert r["source"] == "twin_gauntlet"
        assert r["n"] == 2
        assert r["timeout_min"] == 45
        assert r["request_id"].startswith("gauntlet-")
        # round-trips through json (append-only jsonl contract)
        assert json.loads(json.dumps(r)) == r
    on_disk = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert on_disk == rows


def test_request_paths_never_rewrites_prior_rows(tmp_path):
    """APPEND-ONLY: a second call must not touch the first call's rows (mirrors the
    established decisions.jsonl/journal.jsonl convention in crypto_twin_core.py)."""
    queue_path = tmp_path / "gauntlet-queue.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    first = tg.request_paths(["tp1_trail"], n=1, timeout_min=45, queue_path=queue_path, now_utc=now)
    tg.request_paths(["structure_stop"], n=1, timeout_min=45, queue_path=queue_path,
                     now_utc=now + timedelta(minutes=1))
    on_disk = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert len(on_disk) == 2
    assert on_disk[0] == first[0]  # byte-identical, unchanged by the second call


def test_unique_request_ids_across_paths_and_calls(tmp_path):
    queue_path = tmp_path / "gauntlet-queue.jsonl"
    rows = tg.request_paths(["tp1_trail", "tp1_trail"], n=1, timeout_min=45, queue_path=queue_path)
    assert rows[0]["request_id"] != rows[1]["request_id"]


# ============================================================================
# path-coverage.json helpers -- "the one-line hook" (pending_requests / record_path_result)
# ============================================================================

def test_pending_requests_lists_unserviced_requested_rows(tmp_path):
    queue_path = tmp_path / "gauntlet-queue.jsonl"
    coverage_path = tmp_path / "path-coverage.json"
    rows = tg.request_paths(["tp1_trail", "structure_stop"], n=1, timeout_min=45,
                            queue_path=queue_path)
    pending = tg.pending_requests(queue_path=queue_path, coverage_path=coverage_path)
    assert {p["path"] for p in pending} == {"tp1_trail", "structure_stop"}


def test_pending_requests_drops_a_request_once_recorded(tmp_path):
    queue_path = tmp_path / "gauntlet-queue.jsonl"
    coverage_path = tmp_path / "path-coverage.json"
    rows = tg.request_paths(["tp1_trail", "structure_stop"], n=1, timeout_min=45,
                            queue_path=queue_path)
    tg.record_path_result("tp1_trail", status="green", request_id=rows[0]["request_id"],
                          coverage_path=coverage_path)
    pending = tg.pending_requests(queue_path=queue_path, coverage_path=coverage_path)
    assert [p["path"] for p in pending] == ["structure_stop"]


def test_record_path_result_schema_and_running_totals(tmp_path):
    coverage_path = tmp_path / "path-coverage.json"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    tg.record_path_result("tp1_trail", status="green", request_id="req-1",
                          coverage_path=coverage_path, now_utc=now)
    rec = tg.record_path_result("tp1_trail", status="red", request_id="req-2",
                                incident="premium fallback fired instead of structure stop",
                                coverage_path=coverage_path, now_utc=now + timedelta(minutes=5))
    assert rec["status"] == "red"
    assert rec["last_request_id"] == "req-2"
    assert rec["n_total_today"] == 2
    assert rec["n_green_today"] == 1          # only the first call was green
    assert rec["last_incident"] == "premium fallback fired instead of structure stop"
    data = tg.load_coverage(coverage_path)
    assert "tp1_trail" in data["paths"]
    assert "updated_at_utc" in data


def test_load_coverage_missing_file_is_fail_open(tmp_path):
    assert tg.load_coverage(tmp_path / "nope.json") == {}


def test_load_coverage_corrupt_file_is_fail_open(tmp_path):
    p = tmp_path / "path-coverage.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert tg.load_coverage(p) == {}


# ============================================================================
# poll_results -- two independent evidence sources + honest timeout
# ============================================================================

def _clock(start):
    """Returns (now_fn, sleep_fn) sharing one mutable cursor -- deterministic,
    no real waiting, mirrors trade_autopsy.py's injectable sleep_fn pattern."""
    cursor = [start]

    def now_fn():
        return cursor[0]

    def sleep_fn(seconds):
        cursor[0] += timedelta(seconds=seconds)
    return now_fn, sleep_fn


def test_poll_results_resolves_via_path_coverage_green(tmp_path):
    coverage_path = tmp_path / "path-coverage.json"
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    req = tg._new_request_row("tp1_trail", 1, 45, now_utc=now)
    tg.record_path_result("tp1_trail", status="green", request_id=req["request_id"],
                          coverage_path=coverage_path, now_utc=now)
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req], timeout_min=1, poll_interval_sec=5, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["overall"] == "PASS"
    assert report["results"]["tp1_trail"]["status"] == "PASS"
    assert report["results"]["tp1_trail"]["source"] == "path-coverage.json"


def test_poll_results_resolves_via_path_coverage_red_is_fail(tmp_path):
    coverage_path = tmp_path / "path-coverage.json"
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    req = tg._new_request_row("structure_stop", 1, 45, now_utc=now)
    tg.record_path_result("structure_stop", status="red", request_id=req["request_id"],
                          incident="wrong stage observed", coverage_path=coverage_path, now_utc=now)
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req], timeout_min=1, poll_interval_sec=5, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["overall"] == "FAIL"
    assert report["results"]["structure_stop"]["status"] == "FAIL"
    assert "wrong stage" in report["results"]["structure_stop"]["detail"]


def test_poll_results_ignores_a_result_for_a_different_request_id(tmp_path):
    """A stale/unrelated prior green for this path must NOT satisfy a NEW request
    -- only a matching request_id counts (otherwise a gauntlet could rubber-stamp
    off yesterday's coverage)."""
    coverage_path = tmp_path / "path-coverage.json"
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    tg.record_path_result("tp1_trail", status="green", request_id="some-other-request",
                          coverage_path=coverage_path, now_utc=now)
    req = tg._new_request_row("tp1_trail", 1, 1, now_utc=now)  # a DIFFERENT, fresh request
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req], timeout_min=1, poll_interval_sec=30, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["results"]["tp1_trail"]["status"] == "FAIL"
    assert report["results"]["tp1_trail"]["source"] == "timeout"


def test_poll_results_resolves_via_journal_fallback_when_no_coverage(tmp_path):
    """Even before path-coverage.json is wired by the scenario scheduler, a
    matching CLOSED row in the twin's own journal.jsonl is authoritative evidence."""
    coverage_path = tmp_path / "path-coverage.json"   # never written
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    req = tg._new_request_row("structure_stop", 1, 45, now_utc=now)
    journal_path.write_text(json.dumps({
        "ts_utc": (now + timedelta(minutes=2)).isoformat(), "event": "CLOSED",
        "stage": "structure_stop", "symbol": "BTC/USD",
    }) + "\n", encoding="utf-8")
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req], timeout_min=1, poll_interval_sec=5, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["results"]["structure_stop"]["status"] == "PASS"
    assert report["results"]["structure_stop"]["source"] == "journal.jsonl"


def test_poll_results_ignores_journal_rows_before_the_request(tmp_path):
    """A journal row that closed BEFORE this request was made (stale evidence from
    an earlier, unrelated lifecycle) must not satisfy a fresh request."""
    coverage_path = tmp_path / "path-coverage.json"
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    journal_path.write_text(json.dumps({
        "ts_utc": (now - timedelta(minutes=5)).isoformat(), "event": "CLOSED",
        "stage": "structure_stop", "symbol": "BTC/USD",
    }) + "\n", encoding="utf-8")
    req = tg._new_request_row("structure_stop", 1, 1, now_utc=now)
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req], timeout_min=1, poll_interval_sec=30, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["results"]["structure_stop"]["status"] == "FAIL"
    assert report["results"]["structure_stop"]["source"] == "timeout"


def test_poll_results_honest_timeout_never_silently_passes(tmp_path):
    coverage_path = tmp_path / "path-coverage.json"
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    req = tg._new_request_row("catastrophe_cap", 1, 1, now_utc=now)
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req], timeout_min=1, poll_interval_sec=20, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["overall"] == "FAIL"
    r = report["results"]["catastrophe_cap"]
    assert r["status"] == "FAIL"
    assert r["source"] == "timeout"
    assert "honest timeout" in r["detail"]
    assert "not a proven mechanism failure" in r["detail"]


def test_poll_results_multiple_paths_mixed_outcome(tmp_path):
    coverage_path = tmp_path / "path-coverage.json"
    journal_path = tmp_path / "journal.jsonl"
    now = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)
    req_a = tg._new_request_row("tp1_trail", 1, 1, now_utc=now)
    req_b = tg._new_request_row("max_hold", 1, 1, now_utc=now)
    tg.record_path_result("tp1_trail", status="green", request_id=req_a["request_id"],
                          coverage_path=coverage_path, now_utc=now)
    now_fn, sleep_fn = _clock(now)
    report = tg.poll_results([req_a, req_b], timeout_min=1, poll_interval_sec=20, sleep_fn=sleep_fn,
                             now_fn=now_fn, coverage_path=coverage_path, journal_path=journal_path)
    assert report["overall"] == "FAIL"                 # one FAIL sinks the overall verdict
    assert report["results"]["tp1_trail"]["status"] == "PASS"
    assert report["results"]["max_hold"]["status"] == "FAIL"


# ============================================================================
# --dry mode: default fixtures PASS
# ============================================================================

ALL_PATHS = list(tg.PATH_REGISTRY)


def test_dry_mode_all_six_paths_pass_by_default():
    """Integration: every path's default fixture, driven through the REAL
    crypto_twin_core.place_entry/manage_positions (imported read-only), hits its
    documented expected mechanism. If this reds, either a scenario's numbers drifted
    from exit_manager's real behavior or exit_manager itself changed shape."""
    report = tg.run_dry(ALL_PATHS, n=1)
    assert report.get("import_error") is None, report.get("import_error")
    assert report["overall"] == "PASS", report["results"]
    for path in ALL_PATHS:
        assert report["results"][path]["status"] == "PASS", report["results"][path]


def test_dry_mode_n_repeats_each_scenario():
    report = tg.run_dry(["structure_stop"], n=3)
    assert report["results"]["structure_stop"]["n"] == 3
    assert report["overall"] == "PASS"


# ============================================================================
# --dry mode: THE BITE -- a wrong-stage fixture must FAIL (not vacuous)
# ============================================================================

_WRONG_STAGE_OVERRIDES = {
    "tp1_trail": {"quotes": ((64100.0, 64050.0), (64100.0, 64050.0), (64100.0, 64050.0))},
    "structure_stop": {"last_closed_close": 63900.0},           # never breaks the trigger
    "catastrophe_cap": {"adverse_quote": (63900.0, 63850.0)},   # stays inside the -3% band
    "max_hold": {"elapsed_hours": 1.0},                          # well under the 6h threshold
    "restart_open_position": {"corrupt_state": True},            # state lost across "restart"
    "entry": {"order_error": "simulated broker rejection"},
}


@pytest.mark.parametrize("path", ALL_PATHS)
def test_dry_mode_wrong_stage_fixture_fails(path):
    """THE bite test VERIFY calls for: a fixture engineered to NOT hit the expected
    mechanism must report FAIL, per path. A --dry mode that reports PASS regardless
    of what actually happened would be worse than no gate -- this proves it isn't."""
    override = _WRONG_STAGE_OVERRIDES[path]
    report = tg.run_dry([path], n=1, overrides={path: override})
    assert report["overall"] == "FAIL"
    assert report["results"][path]["status"] == "FAIL"


def test_dry_mode_overall_fails_if_any_single_path_fails():
    overrides = {"structure_stop": _WRONG_STAGE_OVERRIDES["structure_stop"]}
    report = tg.run_dry(["tp1_trail", "structure_stop"], n=1, overrides=overrides)
    assert report["results"]["tp1_trail"]["status"] == "PASS"
    assert report["results"]["structure_stop"]["status"] == "FAIL"
    assert report["overall"] == "FAIL"


def test_dry_mode_import_failure_reports_cleanly_never_raises(monkeypatch):
    """Defensive requirement (module docstring): crypto_twin_core.py is being
    edited by a parallel crew this same session -- a transient import break must
    degrade to a clean FAIL report, never an uncaught traceback."""
    def _boom():
        raise ImportError("simulated: crypto_twin_core mid-edit syntax error")
    monkeypatch.setattr(tg, "_import_crypto_twin_core", _boom)
    report = tg.run_dry(["tp1_trail"], n=1)
    assert report["overall"] == "FAIL"
    assert "crypto_twin_core import failed" in report["import_error"]
    assert report["results"]["tp1_trail"]["status"] == "FAIL"


# ============================================================================
# CLI
# ============================================================================

def test_cli_unknown_path_exits_2(capsys):
    rc = tg.main(["--paths", "not_a_real_path", "--dry"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "unknown path" in captured.err


def test_cli_dry_all_pass_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tg, "LAST_RESULT_PATH", tmp_path / "gauntlet-last.json")
    rc = tg.main(["--paths", "tp1_trail,entry", "--dry"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[DRY]" in out
    assert "overall: PASS" in out


def test_write_last_result_snapshot_shape(tmp_path):
    last_path = tmp_path / "gauntlet-last.json"
    report = {"mode": "DRY", "overall": "PASS",
             "results": {"tp1_trail": {"status": "PASS"}, "structure_stop": {"status": "FAIL"}}}
    tg._write_last_result(report, path=last_path)
    data = json.loads(last_path.read_text(encoding="utf-8"))
    assert data["mode"] == "DRY"
    assert data["overall"] == "PASS"
    assert data["paths"] == {"tp1_trail": "PASS", "structure_stop": "FAIL"}
    assert "ts_et" in data


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
