"""Tests for setup/scripts/crypto_twin_health.py -- T3 visibility instruments for the
CRYPTO TWIN (OP-33c): twin-health.json schema + fail-open behavior, soak-log.jsonl
hourly-rollup watermarking, and the outermost error-capture wrapper
(run_tick_with_health) that must NEVER itself raise, even when the wrapped
crypto_twin_core.run_tick() does.

Mirrors test_crypto_twin_core.py's _twin_cfg(tmp_path) isolation convention exactly
so every test runs fully isolated from the real automation/state/crypto-twin/ ledger
-- and additionally isolates automation/state/twin-health.json (a TOP-LEVEL file,
outside cfg.state_dir by design) via the explicit health_path= override every writer
function accepts.
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

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_health as cth  # noqa: E402


def _twin_cfg(tmp_path: Path, **overrides) -> ctc.TwinConfig:
    state_dir = tmp_path / "automation" / "state" / "crypto-twin"
    return ctc.TwinConfig(state_dir=state_dir, **overrides)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ============================================================================
# Path identity -- HEALTH_PATH is TOP-LEVEL, soak paths are cfg-scoped
# ============================================================================
def test_health_path_is_top_level_glance_file():
    """automation/state/twin-health.json -- a sibling of engine-health.json /
    self-check-last.json, deliberately OUTSIDE the crypto-twin/ namespace (per the
    task spec: J glances at automation/state/*.json directly)."""
    assert cth.HEALTH_PATH == REPO / "automation" / "state" / "twin-health.json"
    assert "crypto-twin" not in str(cth.HEALTH_PATH.relative_to(REPO / "automation" / "state"))


def test_soak_paths_live_under_the_cfg_state_dir(tmp_path):
    """Soak-log/watermark ARE inside the twin's own namespace (cfg.state_dir), unlike
    HEALTH_PATH -- so they inherit cfg's test isolation automatically."""
    cfg = _twin_cfg(tmp_path)
    assert cth._soak_log_path(cfg) == cfg.state_dir / "soak-log.jsonl"
    assert cth._soak_watermark_path(cfg) == cfg.state_dir / "soak-watermark.json"
    assert str(cfg.state_dir) in str(cth._soak_log_path(cfg))


# ============================================================================
# count_ticks_today / count_orders_lifetime -- fail-open, re-derived from ledgers
# ============================================================================
def test_count_ticks_today_missing_file_is_zero(tmp_path):
    assert cth.count_ticks_today(tmp_path / "nope.jsonl", "2026-07-10") == 0


def test_count_ticks_today_filters_by_date(tmp_path):
    p = tmp_path / "decisions.jsonl"
    _write_jsonl(p, [
        {"ts_et": "2026-07-09T23:55:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T00:05:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T12:00:00", "action": "ENTERED"},
        {"ts_et": "2026-07-11T00:01:00", "action": "HOLD"},
    ])
    assert cth.count_ticks_today(p, "2026-07-10") == 2


def test_count_ticks_today_skips_malformed_lines(tmp_path):
    p = tmp_path / "decisions.jsonl"
    p.write_text('{"ts_et": "2026-07-10T00:00:00", "action": "HOLD"}\n'
                "not valid json\n"
                '{"ts_et": "2026-07-10T00:05:00", "action": "HOLD"}\n', encoding="utf-8")
    assert cth.count_ticks_today(p, "2026-07-10") == 2


def test_count_orders_lifetime_missing_file_is_zero(tmp_path):
    assert cth.count_orders_lifetime(tmp_path / "nope.jsonl") == 0


def test_count_orders_lifetime_counts_only_accepted_placed_events(tmp_path):
    p = tmp_path / "journal.jsonl"
    _write_jsonl(p, [
        {"event": "PLACED", "order": {"id": "abc123", "status": "accepted"}},
        {"event": "PLACED", "order": {"_refused": "invalid side"}},
        {"event": "PLACED", "order": {"_error": "500"}},
        {"event": "PLACED", "order": {"_skipped": "WATCH mode"}},
        {"event": "FILLED", "order_id": "abc123"},
        {"event": "PLACED", "order": {"id": "def456", "status": "accepted"}},
    ])
    assert cth.count_orders_lifetime(p) == 2


def test_count_orders_lifetime_zero_when_never_placed(tmp_path):
    """The current BLOCKED_NO_ACCOUNT reality: place_entry is never reached, so an
    empty/absent journal.jsonl must honestly read 0, not crash."""
    assert cth.count_orders_lifetime(tmp_path / "journal.jsonl") == 0


# ============================================================================
# account_status -- LIVE vs BLOCKED_NO_ACCOUNT
# ============================================================================
def test_account_status_blocked_when_no_secrets_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "secrets.json")
    assert cth.account_status() == "BLOCKED_NO_ACCOUNT"


def test_account_status_live_when_twin_creds_present(monkeypatch, tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {"twin": {"key": "K", "secret": "S"}}}))
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", p)
    monkeypatch.setattr(cth.broker, "get_account", lambda creds: {"crypto_status": "ACTIVE"})
    assert cth.account_status() == "LIVE"


def test_account_status_blocked_when_crypto_not_approved(monkeypatch, tmp_path):
    """2026-07-11: crypto shares an account's EXISTING approval state (confirmed via Alpaca's
    docs + live account reads) rather than needing a dedicated account type -- so a configured
    account can still be blocked if Alpaca hasn't activated crypto_status on it. Must surface
    as its OWN distinct status, not get conflated with 'no account configured yet'."""
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {"twin": {"key": "K", "secret": "S"}}}))
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", p)
    monkeypatch.setattr(cth.broker, "get_account", lambda creds: {"crypto_status": "INACTIVE"})
    assert cth.account_status() == "BLOCKED_CRYPTO_NOT_APPROVED"


def test_account_status_blocked_when_secrets_exist_but_no_twin_entry(monkeypatch, tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"accounts": {"someone_else": {"key": "K", "secret": "S"}}}))
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", p)
    assert cth.account_status() == "BLOCKED_NO_ACCOUNT"


# ============================================================================
# write_twin_health -- schema + fail-open
# ============================================================================
def test_write_twin_health_schema_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"
    now_et = datetime(2026, 7, 10, 21, 30, 0)
    row = {"action": "HOLD"}
    health = cth.write_twin_health(cfg, row=row, error=None, now_et=now_et, health_path=health_path)

    expected_keys = {"last_tick_et", "ticks_today", "last_action", "breaker_tripped",
                     "account_status", "n_orders_lifetime", "last_error",
                     "path_coverage", "branches_green_today", "incidents_today"}
    assert set(health.keys()) == expected_keys
    assert health["last_action"] == "HOLD"
    assert health["last_error"] is None
    assert health["account_status"] == "BLOCKED_NO_ACCOUNT"
    assert health["last_tick_et"] == now_et.isoformat()
    # B1c fail-open: no path-coverage.json anywhere yet -> empty scoreboard, zero counts,
    # never a crash (same discipline as every other fact in this file).
    assert health["path_coverage"] == {}
    assert health["branches_green_today"] == 0
    assert health["incidents_today"] == 0


def test_write_twin_health_writes_real_file_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"
    assert not health_path.exists()
    cth.write_twin_health(cfg, row={"action": "MANAGED"}, error=None,
                          now_et=datetime(2026, 7, 10, 22, 0, 0), health_path=health_path)
    assert health_path.exists()
    on_disk = json.loads(health_path.read_text(encoding="utf-8"))
    assert on_disk["last_action"] == "MANAGED"


def test_write_twin_health_fail_open_on_missing_ledgers(tmp_path, monkeypatch):
    """No decisions.jsonl, no journal.jsonl, no breaker.json anywhere -- must still
    produce a complete, valid health dict (0 ticks, 0 orders, breaker_tripped=None),
    never raise."""
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"
    health = cth.write_twin_health(cfg, row=None, error=None,
                                   now_et=datetime(2026, 7, 10, 21, 0, 0), health_path=health_path)
    assert health["ticks_today"] == 0
    assert health["n_orders_lifetime"] == 0
    assert health["breaker_tripped"] is None
    assert health["last_action"] is None


def test_write_twin_health_reflects_current_tick_error_only(tmp_path, monkeypatch):
    """last_error is the CURRENT tick's error, not a sticky historical flag -- a
    clean tick after a prior error must clear it back to None."""
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"
    cth.write_twin_health(cfg, row=None, error="URLError: timed out",
                          now_et=datetime(2026, 7, 10, 21, 0, 0), health_path=health_path)
    h2 = cth.write_twin_health(cfg, row={"action": "HOLD"}, error=None,
                               now_et=datetime(2026, 7, 10, 21, 5, 0), health_path=health_path)
    assert h2["last_error"] is None


def test_write_twin_health_reads_breaker_tripped(tmp_path, monkeypatch):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "breaker.json").write_text(json.dumps({"tripped": True}), encoding="utf-8")
    health_path = tmp_path / "twin-health.json"
    health = cth.write_twin_health(cfg, row=None, error=None,
                                   now_et=datetime(2026, 7, 10, 21, 0, 0), health_path=health_path)
    assert health["breaker_tripped"] is True


# ============================================================================
# B1c: path-coverage scoreboard summary (RE-DERIVED every call, never a second
# source of truth) -- summarize_path_coverage() + write_twin_health()'s wiring of it
# ============================================================================
def test_summarize_path_coverage_empty_doc_is_fail_open():
    summary = cth.summarize_path_coverage({})
    assert summary == {"path_coverage": {}, "branches_green_today": 0, "incidents_today": 0}


def test_summarize_path_coverage_malformed_doc_is_fail_open():
    assert cth.summarize_path_coverage("not a dict") == \
        {"path_coverage": {}, "branches_green_today": 0, "incidents_today": 0}
    assert cth.summarize_path_coverage(None) == \
        {"path_coverage": {}, "branches_green_today": 0, "incidents_today": 0}


def test_summarize_path_coverage_counts_green_and_incident_and_carries_tier():
    doc = {
        "date_utc": "2026-07-11",
        "branches": {
            "ENTRY_TP1_TRAIL": {"tier": "LIVE", "status": "GREEN", "count_today": 1,
                                "last_exercised_utc": "t1", "last_result": "GREEN"},
            "ENTRY_STRUCTURE_STOP": {"tier": "LIVE", "status": "GREEN", "count_today": 1,
                                     "last_exercised_utc": "t2", "last_result": "GREEN"},
            "ENTRY_CAT_CAP": {"tier": "LIVE", "status": "INCIDENT", "count_today": 1,
                              "last_exercised_utc": "t3", "last_result": "expected mismatch"},
            "ENTRY_MAX_HOLD": {"tier": "LIVE", "status": "PENDING", "count_today": 0,
                               "last_exercised_utc": None, "last_result": None},
            "RESTART_OPEN_POSITION": {"tier": "LIVE", "status": "PENDING", "count_today": 0,
                                      "last_exercised_utc": None, "last_result": None},
            "ORGANIC_SIGNAL": {"tier": "LIVE", "status": "PENDING", "count_today": 0,
                               "last_exercised_utc": None, "last_result": None},
            "ENTRY_TP1_TRAIL_BEAR": {"tier": "SIM", "status": "NOT_YET_COVERED", "count_today": 0,
                                     "last_exercised_utc": None, "last_result": None},
        },
    }
    summary = cth.summarize_path_coverage(doc)
    assert summary["branches_green_today"] == 2
    assert summary["incidents_today"] == 1
    assert summary["path_coverage"]["ENTRY_TP1_TRAIL"]["tier"] == "LIVE"
    assert summary["path_coverage"]["ENTRY_TP1_TRAIL_BEAR"]["tier"] == "SIM"
    assert summary["path_coverage"]["ENTRY_TP1_TRAIL_BEAR"]["status"] == "NOT_YET_COVERED"
    assert len(summary["path_coverage"]) == 7


def test_write_twin_health_reflects_real_path_coverage_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    coverage_doc = {
        "date_utc": "2026-07-10",
        "branches": {
            "ENTRY_MAX_HOLD": {"tier": "LIVE", "status": "GREEN", "count_today": 1,
                               "last_exercised_utc": "2026-07-10T21:00:00", "last_result": "GREEN"},
        },
    }
    (cfg.state_dir / "path-coverage.json").write_text(json.dumps(coverage_doc), encoding="utf-8")
    health_path = tmp_path / "twin-health.json"
    health = cth.write_twin_health(cfg, row=None, error=None,
                                   now_et=datetime(2026, 7, 10, 21, 0, 0), health_path=health_path)
    assert health["branches_green_today"] == 1
    assert health["incidents_today"] == 0
    assert health["path_coverage"]["ENTRY_MAX_HOLD"]["status"] == "GREEN"
    on_disk = json.loads(health_path.read_text(encoding="utf-8"))
    assert on_disk["path_coverage"]["ENTRY_MAX_HOLD"]["tier"] == "LIVE"


def test_write_twin_health_fail_open_on_malformed_path_coverage_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "path-coverage.json").write_text("not valid json{{{", encoding="utf-8")
    health_path = tmp_path / "twin-health.json"
    health = cth.write_twin_health(cfg, row=None, error=None,
                                   now_et=datetime(2026, 7, 10, 21, 0, 0), health_path=health_path)
    assert health["path_coverage"] == {}
    assert health["branches_green_today"] == 0


# ============================================================================
# append_soak_row_if_due -- hourly rollup, watermarked, never duplicates
# ============================================================================
def test_soak_row_written_on_first_call(tmp_path):
    cfg = _twin_cfg(tmp_path)
    _write_jsonl(cfg.state_dir / "decisions.jsonl", [
        {"ts_et": "2026-07-10T20:05:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T20:35:00", "action": "MANAGED"},
    ])
    now_et = datetime(2026, 7, 10, 21, 0, 5)  # just crossed the 21:00 hour floor
    row = cth.append_soak_row_if_due(cfg, now_et=now_et)
    assert row is not None
    assert row["n_ticks"] == 2
    assert row["action_distribution"] == {"HOLD": 1, "MANAGED": 1}
    assert row["n_errors"] == 0
    assert (cfg.state_dir / "soak-log.jsonl").exists()


def test_soak_row_not_duplicated_within_same_hour(tmp_path):
    cfg = _twin_cfg(tmp_path)
    _write_jsonl(cfg.state_dir / "decisions.jsonl", [{"ts_et": "2026-07-10T20:05:00", "action": "HOLD"}])
    first = cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 21, 0, 5))
    assert first is not None
    # A second tick 5 minutes later, still within the 21:xx hour -- must be a no-op.
    second = cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 21, 5, 0))
    assert second is None
    lines = (cfg.state_dir / "soak-log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_soak_row_written_again_after_next_hour_boundary(tmp_path):
    cfg = _twin_cfg(tmp_path)
    _write_jsonl(cfg.state_dir / "decisions.jsonl", [
        {"ts_et": "2026-07-10T20:55:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T21:10:00", "action": "HOLD"},
    ])
    r1 = cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 21, 0, 0))
    assert r1 is not None
    r2 = cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 22, 0, 0))
    assert r2 is not None
    lines = (cfg.state_dir / "soak-log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    # Second row's window starts exactly where the first left off (watermarked).
    assert r2["period_start_et"] == r1["period_end_et"]


def test_soak_row_survives_restart_via_persisted_watermark(tmp_path):
    """A FRESH cfg object (simulating a new process after a task restart) must still
    respect the on-disk watermark and not double-roll-up the same hour."""
    cfg = _twin_cfg(tmp_path)
    _write_jsonl(cfg.state_dir / "decisions.jsonl", [{"ts_et": "2026-07-10T20:05:00", "action": "HOLD"}])
    cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 21, 0, 0))
    cfg2 = _twin_cfg(tmp_path)  # fresh object, same on-disk state_dir
    again = cth.append_soak_row_if_due(cfg2, now_et=datetime(2026, 7, 10, 21, 3, 0))
    assert again is None


def test_soak_row_counts_tick_errors(tmp_path):
    cfg = _twin_cfg(tmp_path)
    _write_jsonl(cfg.state_dir / "decisions.jsonl", [
        {"ts_et": "2026-07-10T20:05:00", "action": "HOLD"},
        {"ts_et": "2026-07-10T20:10:00", "action": "TICK_ERROR"},
        {"ts_et": "2026-07-10T20:15:00", "action": "TICK_ERROR"},
    ])
    row = cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 21, 0, 0))
    assert row["n_errors"] == 2
    assert row["action_distribution"]["TICK_ERROR"] == 2


def test_soak_row_after_multi_hour_gap_is_one_honest_row_not_a_backfill_loop(tmp_path):
    """A multi-hour gap (box off overnight) must not loop trying to backfill one row
    per skipped hour -- exactly one row, spanning the true gap."""
    cfg = _twin_cfg(tmp_path)
    _write_jsonl(cfg.state_dir / "decisions.jsonl", [{"ts_et": "2026-07-10T20:05:00", "action": "HOLD"}])
    cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 10, 21, 0, 0))
    # jump 5 hours ahead in one call (simulates a long outage)
    row = cth.append_soak_row_if_due(cfg, now_et=datetime(2026, 7, 11, 2, 0, 0))
    assert row is not None
    lines = (cfg.state_dir / "soak-log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # not 5 -- one honest row for the whole gap


# ============================================================================
# run_tick_with_health -- the outermost wrapper NEVER raises
# ============================================================================
def test_run_tick_with_health_success_path_writes_health(tmp_path, monkeypatch):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    result = cth.run_tick_with_health(cfg, live=False, now_utc=now,
                                      now_et=datetime(2026, 7, 10, 8, 0, 0),
                                      raw_bars=[], health_path=health_path)
    assert result["error"] is None
    assert result["row"]["action"] == "HOLD_BAD_BARS"  # empty raw_bars -> bad-bars path, still a clean tick
    assert health_path.exists()
    assert result["health"]["last_error"] is None


# --- B1b wiring: run_tick_with_health now drives crypto_twin_scenarios.run_scenario_tick,
# not crypto_twin_core.run_tick directly -- prove a forced branch surfaces end-to-end in
# the health snapshot's path_coverage (not just via the lower-level unit tests in
# test_crypto_twin_scenarios.py). Local minimal broker stub -- this file otherwise never
# needs one (every other test here stays at BLOCKED_NO_ACCOUNT).
class _StubBroker:
    def __init__(self):
        self.orders = []

    def place_crypto_order(self, creds, *, symbol, side, notional=None, qty=None,
                           order_type="market", limit_price=None, live):
        self.orders.append({"symbol": symbol, "qty": qty})
        return {"id": "stub-order-1", "status": "accepted"}

    def poll_fill(self, creds, order_id, attempts=4, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_avg_price": 64000.0, "order": {}}

    def get_crypto_position_qty(self, creds, symbol="BTC/USD"):
        return 0.0024

    def get_crypto_quote_hilo(self, symbol="BTC/USD", creds=None):
        return (64010.0, 64000.0)  # inert


def test_run_tick_with_health_surfaces_a_forced_scenario_branch_in_path_coverage(tmp_path, monkeypatch):
    stub = _StubBroker()
    monkeypatch.setattr(cth.ctc.broker, "get_twin_creds", lambda verify_crypto_status=True:
                        {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"})
    monkeypatch.setattr(cth.ctc.broker, "get_account", lambda creds: {"equity": 10000.0})
    monkeypatch.setattr(cth.ctc.broker, "place_crypto_order", stub.place_crypto_order)
    monkeypatch.setattr(cth.ctc.broker, "poll_fill", stub.poll_fill)
    monkeypatch.setattr(cth.ctc.broker, "get_crypto_position_qty", stub.get_crypto_position_qty)
    monkeypatch.setattr(cth.ctc.broker, "get_crypto_quote_hilo", stub.get_crypto_quote_hilo)
    monkeypatch.setattr(cth.cts, "_pick_next_branch", lambda coverage, *, today: "ENTRY_MAX_HOLD")

    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = [{"t": (now - timedelta(minutes=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "o": 64000, "h": 64001, "l": 63999, "c": 64000, "v": 1.0} for i in range(80, 0, -1)]
    result = cth.run_tick_with_health(cfg, live=True, now_utc=now,
                                      now_et=datetime(2026, 7, 10, 8, 0, 0),
                                      raw_bars=bars, health_path=health_path)
    assert result["error"] is None
    assert result["row"]["action"] == "ENTERED"
    assert result["row"]["scenario"] == "ENTRY_MAX_HOLD"
    assert result["health"]["path_coverage"]["ENTRY_MAX_HOLD"]["status"] == "IN_PROGRESS"
    on_disk = json.loads(health_path.read_text(encoding="utf-8"))
    assert on_disk["path_coverage"]["ENTRY_MAX_HOLD"]["status"] == "IN_PROGRESS"
    assert stub.orders  # a REAL order was placed via the health-wrapper's own entrypoint


def test_run_tick_with_health_exception_path_never_raises(tmp_path, monkeypatch):
    """The core assertion: if crypto_twin_core.run_tick() raises (e.g. a genuine
    network failure), run_tick_with_health must catch it, log a TICK_ERROR decision
    row, write twin-health.json with last_error set, and return normally -- NOT
    propagate the exception."""
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"

    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network outage")

    monkeypatch.setattr(cth.ctc, "run_tick", _boom)

    result = cth.run_tick_with_health(cfg, live=True, now_utc=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
                                      now_et=datetime(2026, 7, 10, 8, 0, 0), health_path=health_path)
    assert result["error"] is not None
    assert "ConnectionError" in result["error"]
    assert result["row"]["action"] == "TICK_ERROR"
    assert health_path.exists()
    on_disk = json.loads(health_path.read_text(encoding="utf-8"))
    assert on_disk["last_error"] is not None
    assert on_disk["last_action"] == "TICK_ERROR"
    # the error row was actually journaled to decisions.jsonl, not just returned
    decisions = (cfg.state_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(decisions) == 1
    assert json.loads(decisions[0])["action"] == "TICK_ERROR"


def test_run_tick_with_health_error_gets_counted_in_a_later_soak_rollup(tmp_path, monkeypatch):
    """A tick's own TICK_ERROR can never appear in the rollup computed by that SAME
    call -- append_soak_row_if_due's window is always [watermark, this-hour-floor),
    and a tick's own ts_et is by construction >= this-hour-floor (that's WHY it
    triggers the rollup at all). So the correct assertion is: tick 1 errors inside
    hour A; tick 2 (any outcome) crosses into hour B and its rollup -- which covers
    hour A -- captures tick 1's error."""
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    cfg = _twin_cfg(tmp_path)
    health_path = tmp_path / "twin-health.json"

    def _boom(*args, **kwargs):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(cth.ctc, "run_tick", _boom)

    cth.run_tick_with_health(cfg, live=False, now_utc=datetime(2026, 7, 10, 20, 10, tzinfo=timezone.utc),
                             now_et=datetime(2026, 7, 10, 20, 10, 0), health_path=health_path)
    r2 = cth.run_tick_with_health(cfg, live=False, now_utc=datetime(2026, 7, 10, 21, 0, tzinfo=timezone.utc),
                                  now_et=datetime(2026, 7, 10, 21, 0, 0), health_path=health_path)
    assert r2["soak_row"] is not None
    assert r2["soak_row"]["n_errors"] == 1


# ============================================================================
# BROKER-CANARY-SENTINEL-HOOKUP (queue.md 2026-07-11) -- main() now piggybacks
# broker_canary.probe() on every scheduled tick. Never touches run_tick_with_health
# itself (zero risk to the 40+ tests above); lives entirely in the CLI entrypoint.
# ============================================================================
def test_main_calls_broker_canary_probe(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    monkeypatch.setattr(cth, "HEALTH_PATH", tmp_path / "twin-health.json")
    monkeypatch.setattr(cth, "run_tick_with_health",
                        lambda live=False: {"row": {"action": "HOLD_BAD_BARS"}, "error": None,
                                            "health": {}, "soak_row": None})
    calls = []

    def _fake_probe():
        calls.append(1)
        return {"assess": {"verdict": "GREEN"}}

    monkeypatch.setattr(cth.bc, "probe", _fake_probe)
    rc = cth.main([])
    assert rc == 0
    assert calls == [1]  # probe() was actually invoked, not just imported
    out = json.loads(capsys.readouterr().out)
    assert out["broker_canary"] == "GREEN"


def test_main_survives_a_broker_canary_exception(tmp_path, monkeypatch, capsys):
    """The canary must never break the twin's own tick -- even if probe() itself
    somehow raised (belt-and-suspenders on top of probe()'s own internal fail-open),
    main() still returns the tick's own exit code and prints its own result."""
    monkeypatch.setattr(cth.broker, "TWIN_SECRETS_PATH", tmp_path / "no-secrets.json")
    monkeypatch.setattr(cth, "HEALTH_PATH", tmp_path / "twin-health.json")
    monkeypatch.setattr(cth, "run_tick_with_health",
                        lambda live=False: {"row": {"action": "HOLD_BAD_BARS"}, "error": None,
                                            "health": {}, "soak_row": None})

    def _boom():
        raise ConnectionError("simulated canary network outage")

    monkeypatch.setattr(cth.bc, "probe", _boom)
    rc = cth.main([])
    assert rc == 0  # tick itself had no error -- the canary blowing up must not change that
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "HOLD_BAD_BARS"
    assert out["broker_canary"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
