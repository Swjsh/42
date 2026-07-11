"""Tests for setup/scripts/broker_canary.py -- the BROKER CANARY (TWIN-PROGRAM.md).

Coverage per the build spec:
  * rolling cap (record_observation / _enforce_rolling_cap)
  * assess() verdict rules against FIXTURE observations, one bite per RED/YELLOW rule
  * probe() piggyback behavior (unauthenticated bars leg, gated authenticated account
    leg, fail-open on either leg, the "one-line hookup" end-to-end write of both stores)
  * fail-open: assess() must never raise on malformed rows

No live network calls -- every probe() test monkeypatches broker_canary.ctb's own
functions (mirrors test_crypto_twin_broker.py / test_crypto_twin_health.py's exact
convention: patch the SIBLING module's imported reference, not urllib directly).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import broker_canary as bc  # noqa: E402

_NOW = datetime(2026, 7, 11, 9, 0, 0)  # naive ET, matches et_now()'s convention
_NOW_UTC = datetime(2026, 7, 11, 13, 0, 0, tzinfo=timezone.utc)


def _row(kind: str, minutes_ago: float, ok: bool, latency_ms: float = 100.0, now: datetime = _NOW) -> dict:
    ts = (now - timedelta(minutes=minutes_ago)).isoformat()
    return {"ts_et": ts, "ts_utc": ts, "kind": kind, "latency_ms": latency_ms, "ok": ok, "detail": "fixture"}


def _raise(exc: Exception):
    def _f(*a, **k):
        raise exc
    return _f


# ============================================================================
# section 1: canary collection -- record_observation / rolling cap
# ============================================================================

def test_record_observation_appends_and_returns_row(tmp_path):
    p = tmp_path / "canary.jsonl"
    row = bc.record_observation(bc.KIND_BARS, 12.3, True, "2 bars", now_et=_NOW, now_utc=_NOW_UTC, path=p)
    assert row["kind"] == bc.KIND_BARS
    assert row["ok"] is True
    assert row["latency_ms"] == 12.3
    assert row["ts_et"] == _NOW.isoformat()
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == row


def test_record_observation_detail_is_length_capped(tmp_path):
    p = tmp_path / "canary.jsonl"
    huge = "x" * 5000
    row = bc.record_observation(bc.KIND_BARS, 1.0, False, huge, now_et=_NOW, now_utc=_NOW_UTC, path=p)
    assert len(row["detail"]) == bc._MAX_DETAIL_LEN


def test_rolling_cap_trims_to_last_n(tmp_path):
    p = tmp_path / "canary.jsonl"
    cap = 10
    total = cap + 25
    for i in range(total):
        bc.record_observation(bc.KIND_BARS, float(i), True, f"row {i}",
                              now_et=_NOW, now_utc=_NOW_UTC, path=p, cap=cap)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == cap
    kept = [json.loads(l)["detail"] for l in lines]
    assert kept == [f"row {i}" for i in range(total - cap, total)]  # oldest trimmed, order preserved


def test_rolling_cap_exact_boundary_no_trim(tmp_path):
    p = tmp_path / "canary.jsonl"
    cap = 8
    for i in range(cap):
        bc.record_observation(bc.KIND_BARS, float(i), True, f"row {i}",
                              now_et=_NOW, now_utc=_NOW_UTC, path=p, cap=cap)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == cap  # exactly at cap -- must NOT trim
    kept = [json.loads(l)["detail"] for l in lines]
    assert kept == [f"row {i}" for i in range(cap)]


def test_rolling_cap_no_trim_when_under_cap(tmp_path):
    p = tmp_path / "canary.jsonl"
    for i in range(5):
        bc.record_observation(bc.KIND_BARS, float(i), True, f"row {i}",
                              now_et=_NOW, now_utc=_NOW_UTC, path=p, cap=100)
    assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 5


def test_read_rolling_fail_open_on_missing_file(tmp_path):
    assert bc._read_rolling(tmp_path / "does-not-exist.jsonl") == []


def test_read_rolling_skips_malformed_lines(tmp_path):
    p = tmp_path / "canary.jsonl"
    p.write_text('{"ok": true}\nNOT JSON AT ALL\n{"ok": false}\n', encoding="utf-8")
    rows = bc._read_rolling(p)
    assert rows == [{"ok": True}, {"ok": False}]


# ============================================================================
# section 1: probe() -- piggyback behavior, mocked network
# ============================================================================

_ONE_BAR = [{"t": "2026-07-11T09:00:00Z", "o": 64000.0, "h": 64010.0, "l": 63990.0, "c": 64005.0, "v": 1.2}]


def test_probe_bars_leg_forces_unauthenticated_creds_and_lightweight_limit(tmp_path, monkeypatch):
    captured = {}

    def _fake_fetch(symbol, *, granularity_seconds, limit, creds):
        captured.update(symbol=symbol, granularity_seconds=granularity_seconds, limit=limit, creds=creds)
        return _ONE_BAR

    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", _fake_fetch)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", _raise(FileNotFoundError("no acct")))
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=tmp_path / "roll.jsonl",
                      canary_json_path=tmp_path / "glance.json")
    # the HARD RULE: genuinely unauthenticated (creds={} -> no auth header) + lightweight (limit=1)
    assert captured["creds"] == {}
    assert captured["limit"] == bc.PROBE_BAR_LIMIT == 1
    assert result["bars"]["ok"] is True
    assert result["bars"]["kind"] == bc.KIND_BARS


def test_probe_bars_leg_fail_open_on_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", _raise(TimeoutError("no route to host")))
    monkeypatch.setattr(bc.ctb, "get_twin_creds", _raise(FileNotFoundError("no acct")))
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=tmp_path / "roll.jsonl",
                      canary_json_path=tmp_path / "glance.json")  # must NOT raise
    assert result["bars"]["ok"] is False
    assert "TimeoutError" in result["bars"]["detail"]


def test_probe_skips_auth_leg_when_no_twin_account_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", lambda *a, **k: _ONE_BAR)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", _raise(FileNotFoundError("no acct")))
    roll = tmp_path / "roll.jsonl"
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=roll, canary_json_path=tmp_path / "glance.json")
    assert result["account"] is None
    # only the bars leg was recorded -- no phantom auth row for an unconfigured account
    assert len(roll.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_probe_auth_leg_records_success_when_account_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", lambda *a, **k: _ONE_BAR)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", lambda **k: {"key": "K", "secret": "S", "base_url": "https://x"})
    monkeypatch.setattr(bc.ctb, "get_account", lambda creds: {"status": "ACTIVE"})
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=tmp_path / "roll.jsonl",
                      canary_json_path=tmp_path / "glance.json")
    assert result["account"]["ok"] is True
    assert result["account"]["kind"] == bc.KIND_AUTH
    assert "ACTIVE" in result["account"]["detail"]


def test_probe_auth_leg_records_failure_on_broker_error_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", lambda *a, **k: _ONE_BAR)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", lambda **k: {"key": "K", "secret": "S", "base_url": "https://x"})
    monkeypatch.setattr(bc.ctb, "get_account", lambda creds: {"_error": "401 unauthorized", "_status": 401})
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=tmp_path / "roll.jsonl",
                      canary_json_path=tmp_path / "glance.json")
    assert result["account"]["ok"] is False
    assert "401" in result["account"]["detail"]


def test_probe_auth_leg_fail_open_on_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", lambda *a, **k: _ONE_BAR)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", lambda **k: {"key": "K", "secret": "S", "base_url": "https://x"})
    monkeypatch.setattr(bc.ctb, "get_account", _raise(ConnectionError("reset by peer")))
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=tmp_path / "roll.jsonl",
                      canary_json_path=tmp_path / "glance.json")  # must NOT raise
    assert result["account"]["ok"] is False
    assert "ConnectionError" in result["account"]["detail"]


def test_probe_does_not_double_call_account_for_crypto_status(tmp_path, monkeypatch):
    """The 'one lightweight probe' hard rail: get_twin_creds must be called with
    verify_crypto_status=False (a pure local file read) so probe() makes EXACTLY one
    authenticated network call (its own explicit get_account), not two."""
    calls = {"get_twin_creds_kwargs": None}

    def _fake_get_twin_creds(**kwargs):
        calls["get_twin_creds_kwargs"] = kwargs
        return {"key": "K", "secret": "S", "base_url": "https://x"}

    account_calls = []
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", lambda *a, **k: _ONE_BAR)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", _fake_get_twin_creds)
    monkeypatch.setattr(bc.ctb, "get_account", lambda creds: account_calls.append(creds) or {"status": "ACTIVE"})

    bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=tmp_path / "roll.jsonl",
             canary_json_path=tmp_path / "glance.json")
    assert calls["get_twin_creds_kwargs"] == {"verify_crypto_status": False}
    assert len(account_calls) == 1  # exactly ONE authenticated call, not two


def test_probe_is_the_one_line_hookup_writes_both_stores(tmp_path, monkeypatch):
    """The end-to-end payoff: calling probe() ALONE (its production call signature takes
    zero required args) both appends to the rolling jsonl AND refreshes the glance json
    -- this is the exact one-liner queue.md asks the sentinel/twin tick to add."""
    monkeypatch.setattr(bc.ctb, "fetch_crypto_bars", lambda *a, **k: _ONE_BAR)
    monkeypatch.setattr(bc.ctb, "get_twin_creds", _raise(FileNotFoundError("no acct")))
    roll = tmp_path / "roll.jsonl"
    glance = tmp_path / "glance.json"
    result = bc.probe(now_et=_NOW, now_utc=_NOW_UTC, rolling_path=roll, canary_json_path=glance)

    assert roll.exists() and glance.exists()
    on_disk = json.loads(glance.read_text(encoding="utf-8"))
    assert on_disk["verdict"] == result["assess"]["verdict"] == "GREEN"
    assert on_disk["assessed_at_et"] == _NOW.isoformat()


# ============================================================================
# section 2: assess() verdict rules -- fixture observations, one bite per rule
# ============================================================================

def test_assess_green_on_no_observations():
    result = bc.assess(rows=[], now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"
    assert result["detail"] == "no observations recorded yet"
    assert result["auth_ok"] is None
    assert result["last_ok_et"] is None
    assert result["p50_latency_ms"] == 0.0
    assert result["error_rate_1h"] == 0.0
    assert result["n_observations"] == 0


def test_assess_green_on_all_healthy():
    rows = [_row(bc.KIND_BARS, 10, True), _row(bc.KIND_AUTH, 5, True)]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"
    assert result["detail"] == "nominal"


# ---- YELLOW rule 1: p50 > 2x trailing-24h baseline median ----

def test_assess_yellow_on_latency_spike_vs_trailing_baseline():
    rows = [
        _row(bc.KIND_BARS, 300, True, latency_ms=100.0),   # 5h ago -> baseline window
        _row(bc.KIND_BARS, 200, True, latency_ms=100.0),   # baseline window
        _row(bc.KIND_BARS, 30, True, latency_ms=500.0),    # recent (last 1h): 5x the baseline
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "YELLOW"
    assert "p50" in result["detail"]
    assert result["p50_latency_ms"] == 500.0


def test_assess_not_yellow_when_no_trailing_baseline_exists():
    # Huge absolute latency but NO history older than 1h -- the rule is RELATIVE to a
    # trailing baseline (per spec: "p50 > 2x trailing-24h median"), so it must not fire
    # on insufficient history (cold-start must never manufacture a false alarm).
    rows = [_row(bc.KIND_BARS, 30, True, latency_ms=5000.0)]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"


# ---- YELLOW rule 2: any auth failure in the last hour ----

def test_assess_yellow_on_auth_failure_within_last_hour():
    rows = [_row(bc.KIND_BARS, 10, True), _row(bc.KIND_AUTH, 5, False)]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "YELLOW"
    assert "auth failure within last hour" in result["detail"]


def test_assess_not_yellow_when_auth_failure_older_than_an_hour():
    # A single auth failure from 2 hours ago -- outside the RECENT_WINDOW_MINUTES=60
    # window -- must not trip the "failure in last hour" rule (recency-scoped by design).
    rows = [_row(bc.KIND_AUTH, 120, False), _row(bc.KIND_AUTH, 10, True)]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"


# ---- RED rule 1: >= 3 consecutive failures ----

def test_assess_red_on_three_consecutive_failures():
    rows = [
        _row(bc.KIND_BARS, 10, True),
        _row(bc.KIND_BARS, 8, False),
        _row(bc.KIND_BARS, 6, False),
        _row(bc.KIND_BARS, 4, False),
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "RED"
    assert "3 consecutive probe failures" in result["detail"]


def test_assess_not_red_on_only_two_consecutive_failures():
    # Boundary bite: exactly 2 trailing failures must NOT cross the >=3 threshold.
    rows = [
        _row(bc.KIND_BARS, 10, True),
        _row(bc.KIND_BARS, 8, True),
        _row(bc.KIND_BARS, 6, False),
        _row(bc.KIND_BARS, 4, False),
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"


def test_assess_consecutive_failure_streak_resets_on_a_recovery():
    # 3 failures THEN a recovery -- the trailing streak is 0, must not be RED.
    rows = [
        _row(bc.KIND_BARS, 20, False),
        _row(bc.KIND_BARS, 15, False),
        _row(bc.KIND_BARS, 10, False),
        _row(bc.KIND_BARS, 5, True),
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"


# ---- RED rule 2: auth dead > 15 minutes ----

def test_assess_red_on_auth_dead_over_15_minutes():
    rows = [
        _row(bc.KIND_AUTH, 30, True),   # last known-good auth
        _row(bc.KIND_AUTH, 2, False),   # still failing now -- dead 30m
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "RED"
    assert "auth dead" in result["detail"]


def test_assess_not_red_when_auth_dead_under_15_minutes():
    rows = [
        _row(bc.KIND_AUTH, 10, True),
        _row(bc.KIND_AUTH, 2, False),   # dead only 10m -- below the 15m RED threshold
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "YELLOW"  # escalation ladder: still within-the-hour YELLOW, not yet RED


def test_assess_auth_dead_none_when_never_configured():
    # No auth observations at all (twin account not configured yet) must never
    # manufacture a RED/YELLOW out of pure absence.
    rows = [_row(bc.KIND_BARS, 10, True)]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"
    assert result["auth_ok"] is None


def test_assess_red_overrides_yellow_and_both_reasons_are_disclosed():
    rows = [
        _row(bc.KIND_BARS, 300, True, latency_ms=100.0),
        _row(bc.KIND_BARS, 200, True, latency_ms=100.0),
        _row(bc.KIND_BARS, 30, False, latency_ms=500.0),
        _row(bc.KIND_BARS, 20, False, latency_ms=500.0),
        _row(bc.KIND_BARS, 10, False, latency_ms=500.0),
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["verdict"] == "RED"
    assert "p50" in result["detail"]
    assert "3 consecutive probe failures" in result["detail"]


# ---- field-level bites ----

def test_assess_auth_ok_reflects_most_recent_auth_observation():
    rows = [_row(bc.KIND_AUTH, 30, True), _row(bc.KIND_AUTH, 5, False)]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["auth_ok"] is False


def test_assess_error_rate_1h_is_a_fraction_of_recent_observations():
    rows = [
        _row(bc.KIND_BARS, 50, True),
        _row(bc.KIND_BARS, 40, True),
        _row(bc.KIND_BARS, 30, False),
        _row(bc.KIND_BARS, 20, True),
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["error_rate_1h"] == 0.25
    assert result["verdict"] == "GREEN"  # a single non-consecutive miss alone doesn't degrade the verdict


def test_assess_last_ok_et_is_the_last_successful_row_not_the_last_row():
    rows = [
        _row(bc.KIND_BARS, 30, True),
        _row(bc.KIND_AUTH, 20, True),   # the true last SUCCESS
        _row(bc.KIND_BARS, 10, False),  # most recent overall, but failed
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)
    assert result["last_ok_et"] == (_NOW - timedelta(minutes=20)).isoformat()


def test_assess_rows_override_bypasses_the_real_file(monkeypatch):
    # Explicit rows=[] (falsy but NOT None) must short-circuit the file read entirely.
    monkeypatch.setattr(bc, "_read_rolling", _raise(AssertionError("must not read the file when rows is given")))
    result = bc.assess(rows=[], now_et=_NOW, write=False)
    assert result["verdict"] == "GREEN"


def test_assess_never_raises_on_malformed_rows():
    rows = [
        {"garbage": True},  # no ts_et at all -- dropped by _parse_rows
        {"ts_et": _NOW.isoformat(), "kind": bc.KIND_AUTH},  # auth row missing "ok" AND "latency_ms"
        {"ts_et": (_NOW - timedelta(minutes=1)).isoformat(), "kind": bc.KIND_BARS, "ok": True},  # missing latency_ms
    ]
    result = bc.assess(rows=rows, now_et=_NOW, write=False)  # must not raise
    assert result["verdict"] in ("GREEN", "YELLOW", "RED")


# ---- write behavior ----

def test_assess_writes_glance_json(tmp_path):
    out = tmp_path / "broker-canary.json"
    result = bc.assess(rows=[_row(bc.KIND_BARS, 5, True)], now_et=_NOW, write=True, out_path=out)
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == result


def test_assess_write_false_does_not_touch_disk(tmp_path):
    out = tmp_path / "broker-canary.json"
    bc.assess(rows=[_row(bc.KIND_BARS, 5, True)], now_et=_NOW, write=False, out_path=out)
    assert not out.exists()


def test_assess_assessed_at_et_field_matches_injected_now():
    result = bc.assess(rows=[], now_et=_NOW, write=False)
    assert result["assessed_at_et"] == _NOW.isoformat()


# ============================================================================
# CLI
# ============================================================================

def test_cli_assess_only_never_calls_probe(monkeypatch, capsys):
    monkeypatch.setattr(bc, "probe", _raise(AssertionError("probe() must not run with --assess-only")))
    monkeypatch.setattr(bc, "assess", lambda: {"verdict": "GREEN", "detail": "nominal"})
    rc = bc.main(["--assess-only"])
    assert rc == 0
    assert "GREEN" in capsys.readouterr().out


def test_cli_default_calls_probe(monkeypatch, capsys):
    monkeypatch.setattr(bc, "probe", lambda: {"bars": {"ok": True}, "account": None, "assess": {"verdict": "GREEN"}})
    rc = bc.main([])
    assert rc == 0
    assert "GREEN" in capsys.readouterr().out
