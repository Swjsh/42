"""Guard tests for FUTURES-NATIVE-OCO-DRY-RUN (filed 2026-09-03) -- the two new
`TastytradeBroker` helpers added to test the tastytrade SDK's native OTOCO complex-order
path (`ComplexOrderType.OTOCO`, `NewComplexOrder`, `Account.place_complex_order`) BEFORE
`place_bracket`'s routing is touched:

  - `place_otoco`          -- builds + places a trigger-order OTOCO (entry -> OCO TP/stop)
  - `cancel_complex_order` -- cancels the parent complex order by id

Neither helper is wired into `place_bracket` or any production path -- this file only pins
their own construction/response-handling behaviour. Every test uses a FAKE broker (mocked
`_account`/`_session`) -- no network, no real broker, no order placement.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backtest.futures import tastytrade_paper as tp  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state_files(monkeypatch, tmp_path):
    """Redirect WOULD_BE_FILE / BROKER_TRANSPORT_FILE to tmp paths so a watch-only test in
    this file never appends to the real automation/state/futures ledgers (same isolation
    pattern as test_tastytrade_paper_leg_failure_logging_2026_08_21.py)."""
    monkeypatch.setattr(tp, "WOULD_BE_FILE", tmp_path / "would-be-trades.jsonl")
    monkeypatch.setattr(tp, "BROKER_TRANSPORT_FILE", tmp_path / "broker-transport.jsonl")


class _FakeLeg:
    def __init__(self, order_type):
        self.order_type = order_type


class _FakePlacedOrder:
    def __init__(self, order_id, order_type):
        self.id = order_id
        self.order_type = order_type


class _FakeComplexOrder:
    def __init__(self, id, trigger_order=None, orders=None):
        self.id = id
        self.trigger_order = trigger_order
        self.orders = orders or []


class _FakeComplexResponse:
    def __init__(self, complex_order=None, errors=None, warnings=None):
        self.complex_order = complex_order
        self.errors = errors
        self.warnings = warnings


class _FakeContract:
    """Builds a REAL tastytrade.order.Leg -- NewOrder validates its legs via pydantic, so a
    stand-in dict fails leg construction and masks the actual behaviour under test."""
    def build_leg(self, qty, action):
        from tastytrade.instruments import InstrumentType
        from tastytrade.order import Leg
        return Leg(instrument_type=InstrumentType.FUTURE, symbol="MESZ9",
                   action=action, quantity=qty)


def _broker(watch_only=False):
    b = tp.TastytradeBroker(watch_only=watch_only)
    b._connected = True
    b._session = object()
    b._account = mock.Mock()
    b._front_month = lambda instrument: _FakeContract()
    return b


# ── place_otoco ──────────────────────────────────────────────────────────────────

def test_place_otoco_watch_only_logs_and_returns_none(tmp_path):
    broker = _broker(watch_only=True)
    out = broker.place_otoco("MES", "BUY", 1, 6000.0, 6010.0, 5990.0)
    assert out is None
    rows = tp.WOULD_BE_FILE.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert '"order_shape": "otoco"' in rows[0]


def test_place_otoco_success_extracts_labeled_ids():
    """A clean OTOCO response must map trigger/tp/stop ids by ORDER TYPE, not by list
    position -- the SDK gives no positional guarantee for `complex_order.orders`."""
    broker = _broker()
    tp_leg   = _FakePlacedOrder("tp-1", mock.Mock(value="Limit"))
    stop_leg = _FakePlacedOrder("stop-1", mock.Mock(value="Stop"))
    trigger  = _FakePlacedOrder("entry-1", mock.Mock(value="Limit"))
    co = _FakeComplexOrder(id=999, trigger_order=trigger, orders=[stop_leg, tp_leg])
    broker._account.place_complex_order = mock.AsyncMock(
        return_value=_FakeComplexResponse(complex_order=co))

    out = broker.place_otoco("MES", "BUY", 1, 6000.0, 6010.0, 5990.0)

    assert out == {
        "complex_order_id": 999, "trigger_order_id": "entry-1",
        "tp_order_id": "tp-1", "stop_order_id": "stop-1",
    }
    assert broker.last_failure_detail is None


def test_place_otoco_rejected_no_complex_order_returns_none_with_detail():
    """A rejected complex order (no id, or the dry-run default -1) must be treated as a
    failure -- not returned to the caller as if it were live -- and the exact broker-side
    detail must be captured, never swallowed."""
    broker = _broker()
    resp = _FakeComplexResponse(complex_order=None, errors=["futures_not_enabled"])
    broker._account.place_complex_order = mock.AsyncMock(return_value=resp)

    out = broker.place_otoco("MES", "BUY", 1, 6000.0, 6010.0, 5990.0)

    assert out is None
    assert broker.last_failure_detail is not None
    assert "futures_not_enabled" in broker.last_failure_detail["detail"]


def test_place_otoco_dry_run_default_id_treated_as_rejected():
    """PlacedComplexOrder.id defaults to -1 for a dry_run order per the SDK's own docstring
    -- if that ever leaks through (e.g. dry_run flips true unexpectedly upstream), it must
    NOT be reported as a real placed complex order id."""
    broker = _broker()
    co = _FakeComplexOrder(id=-1, trigger_order=None, orders=[])
    broker._account.place_complex_order = mock.AsyncMock(
        return_value=_FakeComplexResponse(complex_order=co))

    out = broker.place_otoco("MES", "BUY", 1, 6000.0, 6010.0, 5990.0)

    assert out is None


def test_place_otoco_transport_exception_never_raises():
    broker = _broker()
    broker._account.place_complex_order = mock.AsyncMock(
        side_effect=TimeoutError("ReadTimeout"))

    out = broker.place_otoco("MES", "SELL", 1, 6000.0, 5990.0, 6010.0)

    assert out is None
    assert broker.last_failure_detail["call"] == "place_otoco"
    assert broker.last_failure_detail["error_class"] == "TimeoutError"


def test_place_otoco_not_connected_returns_none():
    broker = tp.TastytradeBroker(watch_only=False)
    broker._connected = False
    out = broker.place_otoco("MES", "BUY", 1, 6000.0, 6010.0, 5990.0)
    assert out is None


# ── cancel_complex_order ─────────────────────────────────────────────────────────

def test_cancel_complex_order_watch_only_returns_true_no_network():
    broker = _broker(watch_only=True)
    assert broker.cancel_complex_order(999) is True
    broker._account.delete_complex_order.assert_not_called()


def test_cancel_complex_order_success():
    broker = _broker()
    broker._account.delete_complex_order = mock.AsyncMock(return_value=None)
    assert broker.cancel_complex_order(999) is True
    broker._account.delete_complex_order.assert_awaited_once_with(broker._session, 999)


def test_cancel_complex_order_failure_returns_false_never_raises():
    broker = _broker()
    broker._account.delete_complex_order = mock.AsyncMock(
        side_effect=RuntimeError("already terminal"))
    assert broker.cancel_complex_order(999) is False


def test_cancel_complex_order_not_connected_returns_false():
    broker = tp.TastytradeBroker(watch_only=False)
    broker._connected = False
    assert broker.cancel_complex_order(999) is False


# ── get_working_orders terminal-status bugfix (found live during this dry run) ────
#
# `get_live_orders` returns every order touching the account regardless of status --
# confirmed live 2026-09-03T04:46 ET: an unfiltered call returned 81 rows (mostly
# Filled/Rejected/Cancelled spanning 08-27..09-02) for an account that was actually flat.
# `get_working_orders` must exclude terminal statuses so a long-settled order never reads
# as "currently working" (this broke this dry run's own pre-check on the first live run).

class _FakeOrderRow:
    def __init__(self, order_id, status, symbol="/MESU6"):
        self.id = order_id
        self.status = status
        self.legs = [_FakeLegWithSymbol(symbol)]


class _FakeLegWithSymbol:
    def __init__(self, symbol):
        self.symbol = symbol


@pytest.mark.parametrize("status", ["Filled", "Cancelled", "Rejected", "Expired", "Removed"])
def test_get_working_orders_excludes_terminal_statuses(status):
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(
        return_value=[_FakeOrderRow(111, status)])
    out = broker.get_working_orders("MES")
    assert out == []


@pytest.mark.parametrize("status", ["Received", "Live", "Contingent", "Routed", "In Flight"])
def test_get_working_orders_includes_non_terminal_statuses(status):
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(
        return_value=[_FakeOrderRow(222, status)])
    out = broker.get_working_orders("MES")
    assert out == [{"order_id": 222, "symbol": "/MESU6", "status": status}]


def test_get_working_orders_mixed_batch_only_returns_non_terminal():
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(return_value=[
        _FakeOrderRow(1, "Filled"), _FakeOrderRow(2, "Live"),
        _FakeOrderRow(3, "Cancelled"), _FakeOrderRow(4, "Received"),
    ])
    out = broker.get_working_orders("MES")
    assert {row["order_id"] for row in out} == {2, 4}
