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
    assert cth.account_status() == "LIVE"


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
                     "account_status", "n_orders_lifetime", "last_error"}
    assert set(health.keys()) == expected_keys
    assert health["last_action"] == "HOLD"
    assert health["last_error"] is None
    assert health["account_status"] == "BLOCKED_NO_ACCOUNT"
    assert health["last_tick_et"] == now_et.isoformat()


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
