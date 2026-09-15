"""Tests for hq_market_correlate.py -- sample-row parsing and each mismatch
rule, all against synthetic fixture files under pytest's tmp_path (no real
state touched). Run: python -m pytest setup/scripts/test_hq_market_correlate.py -v
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

import hq_market_correlate as hmc


# ----------------------------------------------------------------------------
# read_beacon
# ----------------------------------------------------------------------------

def test_read_beacon_missing_file(tmp_path: Path):
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_beacon(now, tmp_path / "no-such-beacon.json")
    assert out["spy_last"] is None
    assert out["error"] == "beacon file not found"


def test_read_beacon_fresh(tmp_path: Path):
    beacon = tmp_path / "sight-beacon.json"
    beacon.write_text(json.dumps({
        "ok": True, "ts_et": "2026-09-15T09:59:30", "spy": 761.42, "last_bar": "2026-09-15T09:55:00-04:00",
    }), encoding="utf-8")
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_beacon(now, beacon)
    assert out["spy_last"] == 761.42
    assert out["bar_time"] == "2026-09-15T09:55:00-04:00"
    assert out["source_age_s"] == 30.0
    assert out["error"] is None


def test_read_beacon_malformed_json(tmp_path: Path):
    beacon = tmp_path / "sight-beacon.json"
    beacon.write_text("{not valid json", encoding="utf-8")
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_beacon(now, beacon)
    assert out["spy_last"] is None
    assert "JSONDecodeError" in out["error"]


# ----------------------------------------------------------------------------
# read_engine
# ----------------------------------------------------------------------------

def _ledger_row(account: str, ts_et: str, action: str = "HOLD", reason: str = "no setup") -> str:
    return json.dumps({
        "ts_et": ts_et, "account": account, "action": action, "verdict": action,
        "reason": reason, "spy": 761.5, "bear_score": 3, "bull_score": 4,
    })


def test_read_engine_missing_file(tmp_path: Path):
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_engine(now, tmp_path / "no-ledger.jsonl")
    assert out["error"] == "core-decisions.jsonl not found"
    assert out["per_account"]["safe-2"] is None


def test_read_engine_latest_per_account(tmp_path: Path):
    ledger = tmp_path / "core-decisions.jsonl"
    lines = [
        _ledger_row("safe", "2026-09-15T09:55:00", "HOLD"),
        _ledger_row("bold", "2026-09-15T09:55:01", "HOLD"),
        _ledger_row("safe", "2026-09-15T09:59:00", "ENTER", "trigger fired"),
    ]
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_engine(now, ledger)
    assert out["per_account"]["safe-2"]["action"] == "ENTER"
    assert out["per_account"]["safe-2"]["reason_short"] == "trigger fired"
    assert out["per_account"]["bold-2"]["action"] == "HOLD"
    assert out["last_tick_ts"] == "2026-09-15T09:59:00"
    assert out["last_tick_age_s"] == 60.0


def test_read_engine_malformed_line_skipped(tmp_path: Path):
    ledger = tmp_path / "core-decisions.jsonl"
    ledger.write_text("not json\n" + _ledger_row("safe", "2026-09-15T09:59:00") + "\n", encoding="utf-8")
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_engine(now, ledger)
    assert out["per_account"]["safe-2"]["action"] == "HOLD"
    assert out["error"] is None


def test_read_engine_missing_account_in_window(tmp_path: Path):
    ledger = tmp_path / "core-decisions.jsonl"
    ledger.write_text(_ledger_row("safe", "2026-09-15T09:59:00") + "\n", encoding="utf-8")
    now = datetime(2026, 9, 15, 10, 0, 0)
    out = hmc.read_engine(now, ledger)
    assert out["per_account"]["safe-2"]["action"] == "HOLD"
    assert out["per_account"]["bold-2"]["error"] == "no bold row in tail window"


# ----------------------------------------------------------------------------
# read_positions / read_breakers
# ----------------------------------------------------------------------------

def test_read_positions_missing_and_present(tmp_path: Path):
    safe_path = tmp_path / "current-position-safe.json"
    bold_path = tmp_path / "current-position-bold.json"
    safe_path.write_text(json.dumps({"status": "open", "symbol": "SPY260915C00760000", "qty": 3, "entry": 1.55}), encoding="utf-8")
    out = hmc.read_positions({"safe-2": safe_path, "bold-2": bold_path})
    assert out["safe-2"]["status"] == "open"
    assert out["safe-2"]["qty"] == 3
    assert out["bold-2"]["error"] == "position file not found"


def test_read_breakers(tmp_path: Path):
    safe_cb = tmp_path / "circuit-breaker.json"
    bold_cb = tmp_path / "agg-circuit-breaker.json"
    safe_cb.write_text(json.dumps({"tripped": False}), encoding="utf-8")
    bold_cb.write_text(json.dumps({"tripped": True}), encoding="utf-8")
    out = hmc.read_breakers({"safe-2": safe_cb, "bold-2": bold_cb})
    assert out["safe-2"]["tripped"] is False
    assert out["bold-2"]["tripped"] is True


# ----------------------------------------------------------------------------
# fetch_hq -- network failure fails open
# ----------------------------------------------------------------------------

def test_fetch_hq_connection_refused():
    # A port nothing is listening on -- must fail open, never raise.
    out = hmc.fetch_hq(url="http://127.0.0.1:1/api/hq", timeout=1.0)
    assert out["build_id"] is None
    assert out["error"] is not None


# ----------------------------------------------------------------------------
# build_row / append_row round-trip
# ----------------------------------------------------------------------------

def test_build_row_and_append(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    beacon = tmp_path / "sight-beacon.json"
    beacon.write_text(json.dumps({"ok": True, "ts_et": "2026-09-15T09:59:30", "spy": 761.0, "last_bar": "x"}), encoding="utf-8")
    ledger = tmp_path / "core-decisions.jsonl"
    ledger.write_text(_ledger_row("safe", "2026-09-15T09:59:00") + "\n", encoding="utf-8")

    now = datetime(2026, 9, 15, 10, 0, 0)
    row = hmc.build_row(
        now, beacon_path=beacon, ledger_path=ledger,
        position_paths={"safe-2": tmp_path / "missing-safe.json", "bold-2": tmp_path / "missing-bold.json"},
        breaker_paths={"safe-2": tmp_path / "missing-cb.json", "bold-2": tmp_path / "missing-cb2.json"},
        hq_url="http://127.0.0.1:1/api/hq",
    )
    assert row["ts_et"] == "2026-09-15T10:00:00"
    assert row["market"]["spy_last"] == 761.0
    assert row["engine"]["per_account"]["safe-2"]["action"] == "HOLD"
    assert row["hq"]["error"] is not None  # fail-open network path

    out_path = tmp_path / "market-correlation-2026-09-15.jsonl"
    hmc.append_row(row, out_path)
    hmc.append_row(row, out_path)
    loaded = hmc.load_rows(out_path)
    assert len(loaded) == 2
    assert loaded[0]["ts_et"] == "2026-09-15T10:00:00"


# ----------------------------------------------------------------------------
# mismatch rules
# ----------------------------------------------------------------------------

def _row(ts_et: str, spy: float | None, safe_action: str | None, bold_action: str | None,
         hq_safe_verdict: str | None = None, hq_bold_verdict: str | None = None,
         hq_safe_ts: str | None = None, hq_safe_spy: float | None = None,
         last_tick_ts: str | None = None) -> dict:
    return {
        "ts_et": ts_et,
        "market": {"spy_last": spy},
        "engine": {
            "last_tick_ts": last_tick_ts or ts_et,
            "per_account": {
                "safe-2": {"action": safe_action} if safe_action is not None else None,
                "bold-2": {"action": bold_action} if bold_action is not None else None,
            },
        },
        "hq": {
            "error": None,
            "market": {
                "safe": {"verdict": hq_safe_verdict, "tsEt": hq_safe_ts or ts_et, "spy": hq_safe_spy if hq_safe_spy is not None else spy},
                "bold": {"verdict": hq_bold_verdict, "tsEt": ts_et, "spy": spy},
            },
        },
    }


def test_check_action_not_reflected_flags_unreflected_enter():
    rows = [
        _row("2026-09-15T09:59:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD"),
        _row("2026-09-15T10:00:00", 761.2, "ENTER", "HOLD", "HOLD", "HOLD"),  # HQ never says ENTER
        _row("2026-09-15T10:01:00", 761.3, "ENTER", "HOLD", "HOLD", "HOLD"),
        _row("2026-09-15T10:02:00", 761.4, "ENTER", "HOLD", "HOLD", "HOLD"),
    ]
    mismatches = hmc.check_action_not_reflected(rows)
    assert any(m["rule"] == "a_action_not_reflected" and m["arm"] == "safe-2" for m in mismatches)


def test_check_action_not_reflected_ok_when_hq_catches_up():
    rows = [
        _row("2026-09-15T09:59:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD"),
        _row("2026-09-15T10:00:00", 761.2, "ENTER", "HOLD", "HOLD", "HOLD"),
        _row("2026-09-15T10:01:00", 761.3, "ENTER", "HOLD", "ENTER", "HOLD"),  # HQ reflects within window
    ]
    mismatches = hmc.check_action_not_reflected(rows)
    assert not any(m["arm"] == "safe-2" for m in mismatches)


def test_check_hq_stale_flags_during_rth():
    rows = [_row("2026-09-15T10:05:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD", hq_safe_ts="2026-09-15T09:55:00")]
    mismatches = hmc.check_hq_stale_or_mismatched(rows)
    assert any(m["rule"] == "b_hq_stale" for m in mismatches)


def test_check_hq_price_mismatch():
    rows = [_row("2026-09-15T10:05:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD", hq_safe_spy=765.0)]
    mismatches = hmc.check_hq_stale_or_mismatched(rows)
    assert any(m["rule"] == "b_price_mismatch" for m in mismatches)


def test_check_hq_stale_ignored_outside_rth():
    # 08:00 ET is before the 09:31 RTH window -- should not fire.
    rows = [_row("2026-09-15T08:00:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD", hq_safe_ts="2026-09-15T07:00:00")]
    mismatches = hmc.check_hq_stale_or_mismatched(rows)
    assert mismatches == []


def test_check_engine_tick_gap_flags_during_rth():
    rows = [_row("2026-09-15T10:05:00", 761.0, "HOLD", "HOLD", last_tick_ts="2026-09-15T10:00:00")]
    mismatches = hmc.check_engine_tick_gap(rows)
    assert any(m["rule"] == "c_engine_tick_gap" for m in mismatches)


def test_check_engine_tick_gap_ok_within_threshold():
    rows = [_row("2026-09-15T10:01:00", 761.0, "HOLD", "HOLD", last_tick_ts="2026-09-15T10:00:00")]
    mismatches = hmc.check_engine_tick_gap(rows)
    assert mismatches == []


def test_check_hq_activity_no_engine_flags():
    rows = [_row("2026-09-15T10:05:00", 761.0, "HOLD", "HOLD", hq_safe_verdict="ENTER", hq_bold_verdict="HOLD")]
    mismatches = hmc.check_hq_activity_no_engine(rows)
    assert any(m["rule"] == "d_hq_activity_no_engine" and m["arm"] == "safe-2" for m in mismatches)


def test_check_hq_activity_no_engine_ok_when_matching():
    rows = [_row("2026-09-15T10:05:00", 761.0, "ENTER", "HOLD", hq_safe_verdict="ENTER", hq_bold_verdict="HOLD")]
    mismatches = hmc.check_hq_activity_no_engine(rows)
    assert mismatches == []


# ----------------------------------------------------------------------------
# load_rows fail-open
# ----------------------------------------------------------------------------

def test_load_rows_missing_file(tmp_path: Path):
    assert hmc.load_rows(tmp_path / "missing.jsonl") == []


def test_load_rows_skips_malformed_lines(tmp_path: Path):
    p = tmp_path / "rows.jsonl"
    p.write_text('not json\n{"ts_et": "x"}\n', encoding="utf-8")
    rows = hmc.load_rows(p)
    assert len(rows) == 1
    assert rows[0]["ts_et"] == "x"
