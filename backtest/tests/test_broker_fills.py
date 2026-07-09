"""Guard tests for setup/scripts/broker_fills.py (HANDOFF-2026-07-09-TRUTH-AND-EXITS, T1).

Pure-logic tests only -- no network. Locks in: attribution rule (fleet_rest=engine,
core-arms=engine-only-if-matched, crypto=always manual), FIFO round-trip pnl math
(100x option multiplier), dedup-by-activity-id idempotency, and per-account/per-day
statement aggregation.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "broker_fills", REPO / "setup" / "scripts" / "broker_fills.py")
bf = importlib.util.module_from_spec(_SPEC)
sys.modules["broker_fills"] = bf
_SPEC.loader.exec_module(bf)


def _activity(activity_id, symbol, side, qty, price, ts, order_id=None) -> dict:
    return {"id": activity_id, "activity_type": "FILL", "symbol": symbol, "side": side,
            "qty": str(qty), "price": str(price), "transaction_time": ts,
            "order_id": order_id or f"order-{activity_id}"}


# --- normalize_fill: attribution rule -----------------------------------------------------

def test_fleet_rest_arm_option_is_engine():
    a = _activity("1", "SPY260708P00741000", "buy", 3, 0.96, "2026-07-08T13:52:05Z")
    norm = bf.normalize_fill(a, "safe-1")
    assert norm["attribution"] == "engine"
    assert norm["multiplier"] == 100
    assert norm["is_option"] is True
    assert norm["date_et"] == "2026-07-08"  # 13:52Z = 09:52 ET, same calendar date


def test_fleet_rest_arm_crypto_is_manual():
    a = _activity("2", "BTC/USD", "buy", 0.001, 65000, "2026-07-08T05:00:00Z")
    norm = bf.normalize_fill(a, "safe-3")
    assert norm["attribution"] == "manual"
    assert norm["is_crypto"] is True
    assert norm["multiplier"] == 1


def test_core_arm_matched_order_is_engine():
    a = _activity("3", "SPY260626P00732000", "buy", 5, 0.50, "2026-06-26T14:53:02Z",
                   order_id="a4b95ed1-43cb-4d49-9066-f14142d430cd")
    norm = bf.normalize_fill(a, "safe-2", engine_ids={"a4b95ed1-43cb-4d49-9066-f14142d430cd"})
    assert norm["attribution"] == "engine"


def test_core_arm_unmatched_order_is_manual():
    a = _activity("4", "SPY260626P00732000", "buy", 5, 0.50, "2026-06-26T14:53:02Z",
                   order_id="some-manual-order-id")
    norm = bf.normalize_fill(a, "safe-2", engine_ids={"a4b95ed1-43cb-4d49-9066-f14142d430cd"})
    assert norm["attribution"] == "manual"


def test_malformed_activity_returns_none():
    assert bf.normalize_fill({}, "safe-1") is None
    assert bf.normalize_fill({"id": "x", "symbol": "SPY..P", "side": "buy",
                              "transaction_time": "2026-07-08T00:00:00Z",
                              "price": "0", "qty": "1"}, "safe-1") is None  # zero price


# --- fifo_round_trips: pnl math ------------------------------------------------------------

def test_option_round_trip_pnl_uses_100x_multiplier():
    buy = bf.normalize_fill(
        _activity("e1", "SPY260708P00741000", "buy", 3, 0.96, "2026-07-08T13:52:05Z"), "safe-1")
    sell = bf.normalize_fill(
        _activity("e2", "SPY260708P00741000", "sell", 3, 0.65, "2026-07-08T14:01:05Z"), "safe-1")
    round_trips, open_lots = bf.fifo_round_trips([buy, sell])
    assert open_lots == []
    assert len(round_trips) == 1
    rt = round_trips[0]
    # (0.65 - 0.96) * 3 * 100 = -93.0
    assert rt["pnl"] == -93.0
    assert rt["qty"] == 3


def test_partial_exit_leaves_open_lot():
    buy = bf.normalize_fill(
        _activity("e3", "SPY260708C00745000", "buy", 8, 0.17, "2026-07-08T14:49:03Z"), "safe-3")
    sell = bf.normalize_fill(
        _activity("e4", "SPY260708C00745000", "sell", 5, 0.28, "2026-07-08T14:52:00Z"), "safe-3")
    round_trips, open_lots = bf.fifo_round_trips([buy, sell])
    assert len(round_trips) == 1
    assert round_trips[0]["qty"] == 5
    assert len(open_lots) == 1
    assert open_lots[0]["qty"] == 3  # 8 bought, 5 matched -> 3 still open


def test_different_symbols_never_cross_match():
    buy_a = bf.normalize_fill(
        _activity("e5", "SPY260708C00745000", "buy", 3, 0.20, "2026-07-08T14:00:00Z"), "safe-1")
    sell_b = bf.normalize_fill(
        _activity("e6", "SPY260708P00741000", "sell", 3, 0.20, "2026-07-08T14:01:00Z"), "safe-1")
    round_trips, open_lots = bf.fifo_round_trips([buy_a, sell_b])
    assert round_trips == []
    assert len(open_lots) == 2


# --- build_statement: aggregation -----------------------------------------------------------

def test_statement_aggregates_per_account_and_attribution():
    round_trips = [
        {"arm": "safe-1", "date_et": "2026-07-08", "attribution": "engine", "pnl": -93.0,
         "symbol": "X", "entry_activity_id": "1", "exit_activity_id": "2",
         "entry_price": 1, "exit_price": 1, "qty": 1, "entry_ts_et": "t", "exit_ts_et": "t"},
        {"arm": "safe-2", "date_et": "2026-07-08", "attribution": "manual", "pnl": 40.0,
         "symbol": "X", "entry_activity_id": "3", "exit_activity_id": "4",
         "entry_price": 1, "exit_price": 1, "qty": 1, "entry_ts_et": "t", "exit_ts_et": "t"},
    ]
    stmt = bf.build_statement(round_trips, [])
    assert stmt["per_account"]["safe-1"]["engine_pnl"] == -93.0
    assert stmt["per_account"]["safe-2"]["manual_pnl"] == 40.0
    assert stmt["total_engine_pnl"] == -93.0
    assert stmt["total_manual_pnl"] == 40.0
    assert stmt["total_realized_pnl"] == -53.0
    assert stmt["per_day"]["2026-07-08"]["safe-1"]["realized_pnl"] == -93.0


# --- ledger dedup / idempotency --------------------------------------------------------------

def test_ledger_dedup_by_activity_id(tmp_path):
    ledger = tmp_path / "fills-ledger.jsonl"
    fill1 = bf.normalize_fill(
        _activity("dup1", "SPY260708P00741000", "buy", 3, 0.96, "2026-07-08T13:52:05Z"), "safe-1")
    bf.append_new_fills([fill1], ledger_path=ledger)
    rows, ids = bf.load_existing_ledger(ledger_path=ledger)
    assert len(rows) == 1
    assert "dup1" in ids

    # Simulate a re-run: the same activity id must not be appended twice.
    already_seen = {"dup1"} | ids
    new_fills = [f for f in [fill1] if f["activity_id"] not in already_seen]
    bf.append_new_fills(new_fills, ledger_path=ledger)
    rows2, _ = bf.load_existing_ledger(ledger_path=ledger)
    assert len(rows2) == 1  # still just one row -- no duplicate appended
