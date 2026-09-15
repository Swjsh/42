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
    assert out["per_account"]["safe-2"]["spy"] == 761.5
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
    # HQ-POSITION-TRUTH (2026-09-15): exit-state.json is a dict keyed by
    # open option symbol (real safe-2 shape, trimmed) -- `{}` == flat.
    safe_path = tmp_path / "exit-state-safe.json"
    bold_path = tmp_path / "exit-state-bold.json"
    safe_path.write_text(json.dumps({
        "SPY260915C00760000": {"symbol": "SPY260915C00760000", "total_qty": 3, "entry_premium": 1.55},
    }), encoding="utf-8")
    out = hmc.read_positions({"safe-2": safe_path, "bold-2": bold_path})
    assert out["safe-2"]["status"] == "open"
    assert out["safe-2"]["qty"] == 3
    assert out["safe-2"]["open_count"] == 1
    assert out["bold-2"]["error"] == "exit-state file not found"


def test_read_positions_flat_empty_dict(tmp_path: Path):
    flat_path = tmp_path / "exit-state-flat.json"
    flat_path.write_text("{}", encoding="utf-8")
    out = hmc.read_positions({"safe-2": flat_path})
    assert out["safe-2"]["status"] == "flat"
    assert out["safe-2"]["open_count"] == 0
    assert out["safe-2"]["symbol"] is None


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
         last_tick_ts: str | None = None,
         hq_live_spy: float | None = None, hq_live_age_s: float | None = 10.0,
         safe_ledger_spy: float | None = None, hq_safe_engine_bar: float | None = None,
         safe_age_s: float | None = None) -> dict:
    # hq_safe_spy is kept as a back-compat alias feeding BOTH hq.market.safe.engineBarSpy
    # (rule b2's own field) and, when hq_live_spy is not given, hq.market_live.spy (rule
    # b1) -- callers that only cared about the OLD single price field keep working with
    # zero changes; callers exercising the NEW b1/b2 split pass the new params explicitly.
    live_spy = hq_live_spy if hq_live_spy is not None else (hq_safe_spy if hq_safe_spy is not None else spy)
    engine_bar = hq_safe_engine_bar if hq_safe_engine_bar is not None else (hq_safe_spy if hq_safe_spy is not None else spy)
    ledger_spy = safe_ledger_spy if safe_ledger_spy is not None else spy
    return {
        "ts_et": ts_et,
        "market": {"spy_last": spy},
        "engine": {
            "last_tick_ts": last_tick_ts or ts_et,
            "per_account": {
                "safe-2": {"action": safe_action, "spy": ledger_spy, "age_s": safe_age_s} if safe_action is not None else None,
                "bold-2": {"action": bold_action, "spy": spy} if bold_action is not None else None,
            },
        },
        "hq": {
            "error": None,
            "market": {
                "safe": {"verdict": hq_safe_verdict, "tsEt": hq_safe_ts or ts_et, "engineBarSpy": engine_bar},
                "bold": {"verdict": hq_bold_verdict, "tsEt": ts_et, "engineBarSpy": spy},
            },
            "market_live": {"spy": live_spy, "age_s": hq_live_age_s},
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


def test_check_hq_live_stale_flags_during_rth():
    rows = [_row("2026-09-15T10:05:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD", hq_live_age_s=200.0)]
    mismatches = hmc.check_hq_live_vs_beacon(rows)
    assert any(m["rule"] == "b1_stale" for m in mismatches)


def test_check_hq_live_price_mismatch():
    # beacon says 761.0, HQ's live field disagrees by well over the 0.05 tolerance --
    # a REAL bug in the dashboard's own live-quote read (not engine bar-lag, which
    # this rule no longer looks at).
    rows = [_row("2026-09-15T10:05:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD", hq_live_spy=765.0)]
    mismatches = hmc.check_hq_live_vs_beacon(rows)
    assert any(m["rule"] == "b1_price_mismatch" for m in mismatches)


def test_check_hq_live_ok_when_engine_bar_lags_live():
    # THE BUG THIS FIX CLOSES: engine bar (760.755) is genuinely behind the live
    # tape (758.925) by design (no look-ahead) -- rule b1 must NOT flag this, since
    # it only compares HQ's live field to the beacon, never to the engine bar.
    rows = [_row("2026-09-15T09:36:00", 758.925, "HOLD", "HOLD", "HOLD", "HOLD",
                  hq_live_spy=758.925, hq_safe_engine_bar=760.755, safe_ledger_spy=760.755)]
    mismatches = hmc.check_hq_live_vs_beacon(rows)
    assert mismatches == []


def test_check_hq_live_stale_ignored_outside_rth():
    # 08:00 ET is before the 09:31 RTH window -- should not fire.
    rows = [_row("2026-09-15T08:00:00", 761.0, "HOLD", "HOLD", "HOLD", "HOLD", hq_live_age_s=999.0)]
    mismatches = hmc.check_hq_live_vs_beacon(rows)
    assert mismatches == []


def test_check_hq_engine_bar_matches_ledger_ok():
    rows = [_row("2026-09-15T09:36:00", 758.925, "HOLD", "HOLD", "HOLD", "HOLD",
                  hq_safe_engine_bar=760.755, safe_ledger_spy=760.755)]
    mismatches = hmc.check_hq_engine_bar_vs_ledger(rows)
    assert mismatches == []


def test_check_hq_engine_bar_mismatch_flags():
    # HQ's engineBarSpy has drifted from the SAME ledger row's own spy -- a real
    # dashboard read/parse bug, not the expected engine-vs-live lag.
    rows = [_row("2026-09-15T09:36:00", 758.925, "HOLD", "HOLD", "HOLD", "HOLD",
                  hq_safe_engine_bar=760.755, safe_ledger_spy=760.90)]
    mismatches = hmc.check_hq_engine_bar_vs_ledger(rows)
    assert any(m["rule"] == "b2_engine_bar_mismatch" and m["arm"] == "safe-2" for m in mismatches)


def test_check_hq_engine_bar_ok_on_stale_ledger_row_sampling_race():
    # THE EXACT RACE from evidence 2026-09-15: sampled 15:41:02, this script's own
    # engine row is the 15:40:03 tick (spy=756.925, age_s=59.5 -- > B2_LEDGER_STALE_S)
    # while HQ's independent ledger read already picked up the 15:41:02 row
    # (engineBarSpy=756.66, written in the same second). HQ was correct; this
    # script's read was one tick stale -- must NOT fire.
    rows = [_row("2026-09-15T15:41:02", 756.925, "HOLD", "HOLD", "HOLD", "HOLD",
                  hq_safe_engine_bar=756.66, safe_ledger_spy=756.925, safe_age_s=59.5)]
    mismatches = hmc.check_hq_engine_bar_vs_ledger(rows)
    assert not any(m["rule"] == "b2_engine_bar_mismatch" for m in mismatches)


def test_check_hq_engine_bar_still_flags_genuine_mismatch_on_fresh_row():
    # Same price gap as the race case, but the ledger row is FRESH (age_s=5, well
    # under B2_LEDGER_STALE_S) -- this is a real dashboard read/parse drift, not a
    # tick-boundary race, and must still fire.
    rows = [_row("2026-09-15T15:41:02", 756.925, "HOLD", "HOLD", "HOLD", "HOLD",
                  hq_safe_engine_bar=756.66, safe_ledger_spy=756.925, safe_age_s=5.0)]
    mismatches = hmc.check_hq_engine_bar_vs_ledger(rows)
    assert any(m["rule"] == "b2_engine_bar_mismatch" and m["arm"] == "safe-2" for m in mismatches)


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
# check_position_hidden (p1) -- HQ-POSITION-TRUTH (2026-09-15)
# ----------------------------------------------------------------------------

def _row_with_positions(ts_et: str, safe_open: bool, hq_safe_open: list | None) -> dict:
    row = _row(ts_et, 761.0, "HOLD", "HOLD", hq_safe_verdict="HOLD", hq_bold_verdict="HOLD")
    row["positions"] = {
        "safe-2": {"status": "open" if safe_open else "flat", "symbol": "SPY260915P00757000", "qty": 3},
        "bold-2": {"status": "flat", "symbol": None, "qty": None},
    }
    row["hq"]["market"]["safe"]["position"] = {"open": hq_safe_open} if hq_safe_open is not None else None
    row["hq"]["market"]["bold"]["position"] = {"open": []}
    return row


def test_check_position_hidden_flags_the_exact_bug():
    # exit-state shows safe-2 OPEN (engine action already fell back to
    # HOLD -- the 2-min-later state this bug produced) but HQ's own
    # trading.position.safe.open is still empty.
    rows = [_row_with_positions("2026-09-15T10:42:00", safe_open=True, hq_safe_open=[])]
    mismatches = hmc.check_position_hidden(rows)
    assert any(m["rule"] == "p1_position_hidden" and m["arm"] == "safe-2" for m in mismatches)


def test_check_position_hidden_ok_when_hq_shows_it():
    rows = [_row_with_positions("2026-09-15T10:42:00", safe_open=True, hq_safe_open=[{"symbol": "SPY260915P00757000"}])]
    mismatches = hmc.check_position_hidden(rows)
    assert mismatches == []


def test_check_position_hidden_ok_when_flat():
    rows = [_row_with_positions("2026-09-15T10:42:00", safe_open=False, hq_safe_open=[])]
    mismatches = hmc.check_position_hidden(rows)
    assert mismatches == []


def test_check_position_hidden_flags_when_hq_position_field_missing_entirely():
    # An older /api/hq payload (predates this field) -- still a real
    # mismatch, not silently skipped, since the broker truth says OPEN.
    rows = [_row_with_positions("2026-09-15T10:42:00", safe_open=True, hq_safe_open=None)]
    mismatches = hmc.check_position_hidden(rows)
    assert any(m["rule"] == "p1_position_hidden" for m in mismatches)


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
