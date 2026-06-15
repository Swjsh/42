"""Tests for atomic_bracket_guard -- naked-position + orphan-parent detection.

Run: pytest -v setup/scripts/test_atomic_bracket_guard.py

These tests monkey-patch `_request` so we never hit the real Alpaca API.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

# Direct import (script is in setup/scripts, not a package)
_spec = importlib.util.spec_from_file_location(
    "abg",
    Path(__file__).parent / "atomic_bracket_guard.py",
)
abg = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(abg)  # type: ignore[union-attr]


def _fake_request_factory(positions: list, orders: list):
    """Build a mock _request that returns positions then orders."""
    def _fake(endpoint, key, secret, method="GET", data=None, timeout=10):
        if "positions" in endpoint:
            return positions
        if "orders" in endpoint and method == "GET":
            return orders
        if "orders" in endpoint and method == "DELETE":
            return {}  # successful cancel
        return None
    return _fake


def test_is_spy_option_recognizes_call() -> None:
    assert abg._is_spy_option("SPY260518C00740000") is True


def test_is_spy_option_recognizes_put() -> None:
    assert abg._is_spy_option("SPY260518P00734000") is True


def test_is_spy_option_rejects_underlying() -> None:
    assert abg._is_spy_option("SPY") is False


def test_is_spy_option_rejects_other_ticker() -> None:
    assert abg._is_spy_option("QQQ260518C00500000") is False


def test_option_direction_long_call() -> None:
    assert abg._option_direction("SPY260518C00740000") == "long_call"


def test_option_direction_long_put() -> None:
    assert abg._option_direction("SPY260518P00734000") == "long_put"


def test_clean_account_no_positions_no_orders() -> None:
    with patch.object(abg, "_request", side_effect=_fake_request_factory([], [])):
        report = abg.audit_account("safe", dry_run=True)
    assert report["ok"] is True
    assert report["positions_checked"] == 0
    assert report["open_orders_checked"] == 0
    assert report["naked_positions"] == []
    assert report["orphan_parents"] == []


def test_naked_filled_position_detected() -> None:
    """Position exists, no stop orders open -> RED naked detection."""
    positions = [{
        "symbol": "SPY260518C00740000",
        "qty": "3",
        "side": "long",
        "avg_entry_price": "1.84",
        "current_price": "1.51",
        "unrealized_pl": "-99",
    }]
    orders = []  # NO stop orders open
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("bold", dry_run=True)
    assert report["ok"] is True
    assert len(report["naked_positions"]) == 1
    nk = report["naked_positions"][0]
    assert nk["symbol"] == "SPY260518C00740000"
    assert nk["qty"] == 3
    assert nk["severity"] == "RED"
    assert "Rule 3" in nk["reason"]


def test_protected_position_not_flagged() -> None:
    """Position with matching stop order -> no flag."""
    positions = [{
        "symbol": "SPY260518C00740000",
        "qty": "3",
        "side": "long",
        "avg_entry_price": "1.84",
    }]
    orders = [{
        "id": "abc-stop-leg",
        "symbol": "SPY260518C00740000",
        "order_type": "stop",
        "type": "stop",
        "stop_price": "1.50",
        "side": "sell",
        "qty": "3",
        "status": "open",
    }]
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("safe", dry_run=True)
    assert report["naked_positions"] == []


def test_orphan_parent_buy_no_stop_leg_detected_and_canceled() -> None:
    """Unfilled parent buy with no stop leg -> AMBER + cancel."""
    positions = []
    orders = [{
        "id": "orphan-parent-id",
        "symbol": "SPY260518C00740000",
        "side": "buy",
        "qty": "3",
        "status": "new",
        "order_class": "simple",  # fell back from bracket
        "submitted_at": "2026-05-18T13:48:00Z",
        "limit_price": "1.84",
        "legs": [],  # no stop leg
    }]
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("bold", dry_run=False)
    assert len(report["orphan_parents"]) == 1
    op = report["orphan_parents"][0]
    assert op["order_id"] == "orphan-parent-id"
    assert op["severity"] == "AMBER"
    assert op["canceled"] is True
    assert len(report["orphan_parents_canceled"]) == 1


def test_orphan_parent_dry_run_does_not_cancel() -> None:
    """Dry-run: detected but NOT canceled."""
    positions = []
    orders = [{
        "id": "orphan-x",
        "symbol": "SPY260518P00734000",
        "side": "buy",
        "qty": "3",
        "status": "new",
        "order_class": "simple",
        "legs": [],
    }]
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("safe", dry_run=True)
    assert len(report["orphan_parents"]) == 1
    assert report["orphan_parents"][0].get("canceled") is None
    assert report["orphan_parents_canceled"] == []


def test_bracket_parent_with_stop_leg_not_flagged() -> None:
    """Proper bracket: parent + take_profit leg + stop_loss leg -> no flag."""
    positions = []
    orders = [{
        "id": "good-parent",
        "symbol": "SPY260518C00740000",
        "side": "buy",
        "qty": "3",
        "status": "new",
        "order_class": "bracket",
        "legs": [
            {
                "id": "leg-tp",
                "order_type": "limit",
                "type": "limit",
                "side": "sell",
                "limit_price": "2.50",
            },
            {
                "id": "leg-stop",
                "order_type": "stop",
                "type": "stop",
                "stop_price": "1.40",
                "side": "sell",
            },
        ],
    }]
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("safe", dry_run=False)
    assert report["orphan_parents"] == []


def test_filled_position_with_orphan_unfilled_stop_protected() -> None:
    """Position filled + open stop targeting same symbol = protected."""
    positions = [{
        "symbol": "SPY260518C00740000",
        "qty": "3",
        "side": "long",
        "avg_entry_price": "1.84",
    }]
    # Stop order at top level (not a leg)
    orders = [{
        "id": "standalone-stop",
        "symbol": "SPY260518C00740000",
        "order_type": "stop",
        "type": "stop",
        "stop_price": "1.40",
        "side": "sell",
        "qty": "3",
        "status": "open",
    }]
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("safe", dry_run=True)
    assert report["naked_positions"] == []


def test_ignores_non_spy_options() -> None:
    """QQQ option position = not in scope, doesn't trigger flag."""
    positions = [{
        "symbol": "QQQ260518C00500000",
        "qty": "5",
        "side": "long",
        "avg_entry_price": "1.50",
    }]
    orders = []
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        report = abg.audit_account("safe", dry_run=True)
    assert report["positions_checked"] == 0
    assert report["naked_positions"] == []


def test_api_error_returned_in_report() -> None:
    """If Alpaca returns an error, audit fails gracefully."""
    def _err(endpoint, key, secret, method="GET", data=None, timeout=10):
        return {"_error": "503 Service Unavailable"}
    with patch.object(abg, "_request", side_effect=_err):
        report = abg.audit_account("safe", dry_run=True)
    assert report["ok"] is False
    assert "503" in report["error"]


def test_exit_code_red_when_naked() -> None:
    """Main returns 1 when a naked position is found."""
    import sys
    positions = [{"symbol": "SPY260518C00740000", "qty": "3", "side": "long",
                  "avg_entry_price": "1.84"}]
    orders = []
    with patch.object(abg, "_request", side_effect=_fake_request_factory(positions, orders)):
        with patch.object(sys, "argv", ["abg.py", "--account", "safe", "--dry-run", "--silent"]):
            rc = abg.main()
    assert rc == 1


def test_exit_code_clean() -> None:
    """Main returns 0 when no naked positions."""
    import sys
    with patch.object(abg, "_request", side_effect=_fake_request_factory([], [])):
        with patch.object(sys, "argv", ["abg.py", "--account", "safe", "--silent"]):
            rc = abg.main()
    assert rc == 0
