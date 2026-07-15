"""Guard for setup/scripts/settlement_ledger.py -- Rule 7 cash-settlement gate
feed (2026-07-14, replaces the margin-PDT day-trade counter for both core cash
accounts). See backtest/lib/risk_gate.py CODE_SETTLEMENT docs +
markdown/research/CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md.

Run: cd backtest && python -m pytest tests/test_settlement_ledger.py -q
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def sl():
    return importlib.import_module("settlement_ledger")


# ---- compute_settled_cash_remaining (PURE) -----------------------------------

def test_settled_cash_remaining_with_no_entries_is_full_pool(sl):
    assert sl.compute_settled_cash_remaining(1746.63, []) == 1746.63
    assert sl.compute_settled_cash_remaining(1746.63, None) == 1746.63


def test_settled_cash_remaining_debits_each_entry(sl):
    remaining = sl.compute_settled_cash_remaining(1000.0, [300.0, 200.0])
    assert remaining == 500.0


def test_settled_cash_remaining_clips_at_zero_not_negative(sl):
    remaining = sl.compute_settled_cash_remaining(100.0, [80.0, 80.0])
    assert remaining == 0.0


def test_settled_cash_remaining_ignores_unparseable_entries(sl):
    # Defensive: a malformed entry in the notionals list should not crash the
    # gate feed -- skip it rather than raise (fail-open per module contract).
    remaining = sl.compute_settled_cash_remaining(1000.0, [300.0, "bad", None])
    assert remaining == 700.0


# ---- load_ledger / save_ledger / record_entry (I/O) ---------------------------

def test_load_ledger_fresh_when_file_missing(sl, tmp_path):
    path = tmp_path / "settlement-ledger.json"
    ledger = sl.load_ledger(path, "2026-07-14", 1746.63)
    assert ledger == {"date": "2026-07-14", "sod_settled_cash": 1746.63, "entries": []}


def test_load_ledger_resets_on_new_trading_day(sl, tmp_path):
    path = tmp_path / "settlement-ledger.json"
    sl.record_entry(path, "2026-07-13", 1746.63, 300.0, "2026-07-13T10:38:00")
    # New day -> fresh ledger, even though yesterday's file has entries.
    ledger = sl.load_ledger(path, "2026-07-14", 1800.0)
    assert ledger["date"] == "2026-07-14"
    assert ledger["entries"] == []
    assert ledger["sod_settled_cash"] == 1800.0


def test_load_ledger_fail_open_on_corrupt_file(sl, tmp_path):
    path = tmp_path / "settlement-ledger.json"
    path.write_text("not json at all", encoding="utf-8")
    ledger = sl.load_ledger(path, "2026-07-14", 1746.63)
    assert ledger == {"date": "2026-07-14", "sod_settled_cash": 1746.63, "entries": []}


def test_record_entry_appends_and_persists(sl, tmp_path):
    path = tmp_path / "settlement-ledger.json"
    sl.record_entry(path, "2026-07-14", 1746.63, 357.0, "2026-07-14T10:38:00")
    sl.record_entry(path, "2026-07-14", 1746.63, 222.0, "2026-07-14T13:36:00")
    status = sl.get_settlement_status(path, "2026-07-14", 1746.63)
    assert status["entries_used_today"] == 2
    assert status["settled_cash_remaining"] == pytest.approx(1746.63 - 357.0 - 222.0)
    assert status["sod_settled_cash"] == 1746.63


def test_get_settlement_status_is_read_only(sl, tmp_path):
    path = tmp_path / "settlement-ledger.json"
    before = sl.get_settlement_status(path, "2026-07-14", 1746.63)
    after = sl.get_settlement_status(path, "2026-07-14", 1746.63)
    assert before == after
    assert not path.exists(), "get_settlement_status must never write (read-only)"


def test_get_settlement_status_fail_open_on_corrupt_file(sl, tmp_path):
    path = tmp_path / "settlement-ledger.json"
    path.write_text("{{{not json", encoding="utf-8")
    status = sl.get_settlement_status(path, "2026-07-14", 1746.63)
    assert status["entries_used_today"] == 0
    assert status["settled_cash_remaining"] == 1746.63


def test_save_ledger_fail_open_returns_false_on_write_error(sl, tmp_path):
    # Point the path at a location that cannot be created as a directory
    # (a file where a directory is expected) to force a write error.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad_path = blocker / "settlement-ledger.json"  # blocker is a FILE, not a dir
    ok = sl.save_ledger(bad_path, {"date": "2026-07-14", "sod_settled_cash": 1.0, "entries": []})
    assert ok is False


# ---- ledger_path convention ---------------------------------------------------

def test_ledger_path_safe_vs_bold(sl, tmp_path):
    safe_path = sl.ledger_path(tmp_path, "safe")
    bold_path = sl.ledger_path(tmp_path, "bold")
    assert safe_path == tmp_path / "settlement-ledger.json"
    assert bold_path == tmp_path / "aggressive" / "settlement-ledger.json"
    assert safe_path != bold_path


# ---- end-to-end: mirrors the real 2026-07-14 same-day sequence ---------------

def test_end_to_end_matches_todays_real_blocked_sequence(sl, tmp_path):
    """The exact 4 entries core Safe's OLD margin-PDT gate blocked today
    (core-decisions.jsonl RISK_DENY_PDT @10:38/13:36/13:37/13:38), replayed
    through the ledger the way heartbeat_core._execute actually calls it."""
    path = tmp_path / "settlement-ledger.json"
    sod = 1746.63
    today = "2026-07-14"
    trades = [(3, 1.19), (3, 0.74), (3, 0.70), (3, 0.69)]
    for qty, premium in trades:
        status = sl.get_settlement_status(path, today, sod)
        notional = qty * premium * 100.0
        assert notional <= status["settled_cash_remaining"], (
            f"qty={qty} premium={premium} notional=${notional} would have been "
            f"denied with only ${status['settled_cash_remaining']} settled remaining"
        )
        sl.record_entry(path, today, sod, notional, f"{today}T00:00:00")
    final = sl.get_settlement_status(path, today, sod)
    assert final["entries_used_today"] == 4
    total = sum(q * p * 100.0 for q, p in trades)
    assert final["settled_cash_remaining"] == pytest.approx(sod - total)
    assert final["settled_cash_remaining"] > 0, "today's 4 real trades never exhausted the settled pool"
