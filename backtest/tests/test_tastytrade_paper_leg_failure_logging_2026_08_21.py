"""Guard: a rejected order leg must LOG why, not silently return an empty id list.

WHY THIS EXISTS
  The MES mirror's first-ever real armed order attempt (2026-08-21T11:10 ET, Tastytrade
  sandbox, MIRROR_ARMED=1) came back placed=False, order_ids=[] -- and the ONLY trace in
  automation/state/logs/futures-mirror-shadow.stderr.log was two unrelated lines with an
  EMPTY exception message ("get_positions failed: ", "get_account_equity failed: "). Nothing
  in place_bracket's own `if r.order: ids.append(...)` branch ever logged what the SDK
  response actually carried when r.order was falsy -- a leg can be rejected with ZERO
  diagnostic trail. This pins two independent fixes:
    1. place_bracket logs a WARNING with the SDK response's own errors/warnings (or a repr
       fallback) for every leg that comes back with no order id.
    2. get_positions/get_account_equity always include the exception TYPE in their log line,
       so an empty str(e) is no longer a dead end.
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
def _isolate_broker_transport_file(monkeypatch, tmp_path):
    """2026-08-29: this file's leg-rejection tests exercise place_bracket's REAL
    _log_broker_transport() call (test_rejected_leg_* below), which appends to
    tastytrade_paper.BROKER_TRANSPORT_FILE unconditionally -- an unpatched run of this test
    file wrote fake rows into the real automation/state/futures/broker-transport.jsonl ledger.
    Redirect it to a tmp path for every test in this module, same isolation shape used
    throughout this repo's other broker/state guard files."""
    monkeypatch.setattr(tp, "BROKER_TRANSPORT_FILE", tmp_path / "broker-transport.jsonl")


class _FakeOrder:
    def __init__(self, order_id):
        self.id = order_id


class _FakeResponse:
    """Mimics the tastytrade SDK's place_order() response shape."""
    def __init__(self, order=None, errors=None, warnings=None):
        self.order = order
        self.errors = errors
        self.warnings = warnings


class _FakeContract:
    """Builds a REAL tastytrade.order.Leg (not a bare dict) -- NewOrder validates its
    legs via pydantic, so a stand-in dict fails leg construction itself and masks the
    actual behavior under test (place_bracket's own r.order-falsy branch)."""
    def build_leg(self, qty, action):
        from tastytrade.instruments import InstrumentType
        from tastytrade.order import Leg
        return Leg(instrument_type=InstrumentType.FUTURE, symbol="MESZ9",
                   action=action, quantity=qty)


def _broker():
    b = tp.TastytradeBroker(watch_only=False)
    b._connected = True
    b._session = object()
    b._account = mock.Mock()
    b._front_month = lambda instrument: _FakeContract()
    return b


def test_rejected_leg_logs_a_warning_with_sdk_error_detail(caplog):
    """Every leg that comes back with r.order falsy must log a WARNING carrying whatever
    the SDK attached (errors/warnings), so a future rejection is diagnosable."""
    broker = _broker()
    # Entry leg rejected with an explicit SDK error; the other 3 legs "succeed".
    responses = [
        _FakeResponse(order=None, errors=["insufficient_buying_power"]),
        _FakeResponse(order=_FakeOrder("tp1-1")),
        _FakeResponse(order=_FakeOrder("stop-1")),
    ]
    broker._account.place_order = mock.AsyncMock(side_effect=responses)

    with caplog.at_level("WARNING"):
        ids = broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

    assert ids == ["tp1-1", "stop-1"]   # entry leg silently dropped, as before -- BUT:
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("entry leg rejected" in w and "insufficient_buying_power" in w
               for w in warnings), warnings


def test_all_legs_succeed_logs_no_rejection_warning(caplog):
    """Happy path must stay silent -- no new noise on the common case."""
    broker = _broker()
    responses = [
        _FakeResponse(order=_FakeOrder("entry-1")),
        _FakeResponse(order=_FakeOrder("tp1-1")),
        _FakeResponse(order=_FakeOrder("stop-1")),
    ]
    broker._account.place_order = mock.AsyncMock(side_effect=responses)

    with caplog.at_level("WARNING"):
        ids = broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

    assert ids == ["entry-1", "tp1-1", "stop-1"]
    assert not [r for r in caplog.records if "rejected" in r.message]


def test_rejected_leg_with_no_sdk_error_field_falls_back_to_repr(caplog):
    """Even when the SDK response carries nothing named errors/error/warnings, the warning
    must still fire (with a repr fallback) rather than silently dropping the leg."""
    broker = _broker()
    responses = [
        _FakeResponse(order=None),  # no errors/warnings attrs populated
        _FakeResponse(order=_FakeOrder("tp1-1")),
        _FakeResponse(order=_FakeOrder("stop-1")),
    ]
    broker._account.place_order = mock.AsyncMock(side_effect=responses)

    with caplog.at_level("WARNING"):
        broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("entry leg rejected" in w for w in warnings), warnings


def test_get_positions_failure_logs_exception_type_even_when_message_is_empty(caplog):
    """Live incident: str(e) was empty ("get_positions failed: "). The exception TYPE must
    always be present in the log line so a blank message is no longer a dead end."""
    broker = _broker()

    class _BlankError(Exception):
        def __str__(self):
            return ""

    def _boom():
        raise _BlankError()

    broker._account.get_positions = mock.AsyncMock(side_effect=_BlankError())

    with caplog.at_level("ERROR"):
        result = broker.get_positions()

    assert result == []
    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert any("_BlankError" in e for e in errors), errors


def test_get_account_equity_failure_logs_exception_type_even_when_message_is_empty(caplog):
    broker = _broker()

    class _BlankError(Exception):
        def __str__(self):
            return ""

    broker._account.get_balances = mock.AsyncMock(side_effect=_BlankError())

    with caplog.at_level("ERROR"):
        result = broker.get_account_equity()

    assert result is None
    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert any("_BlankError" in e for e in errors), errors
