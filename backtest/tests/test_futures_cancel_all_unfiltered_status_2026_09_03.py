"""Guard tests for FUTURES-CANCEL-ALL-UNFILTERED-STATUS (filed 2026-09-03, off the
FUTURES-NATIVE-OCO-DRY-RUN close).

`TastytradeBroker.cancel_all` used to iterate the UNFILTERED `get_live_orders` result
(terminal Filled/Rejected/Cancelled orders included -- confirmed live: 81 phantom rows on a
flat account) with the delete_order call for every order wrapped in ONE try/except around the
whole async loop. One order raising on re-cancel aborted the sweep for every order still
queued behind it -- `_cancel_and_confirm_clear` (futures_trader_core.py) would then log
`flatten_cancel_incomplete` and close the position anyway, exposing any STILL-WORKING sibling
order that never even got a cancel attempt.

Fix: skip terminal-status orders, wrap each individual cancel in its own try/except, return
`{attempted, cancelled, failed}` instead of a bare bool. These tests pin: the terminal-status
filter, per-order isolation (one raise doesn't stop the rest), and the new return shape. Every
test uses a FAKE broker (mocked `_account`/`_session`) -- no network, no real broker.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backtest.futures import tastytrade_paper as tp  # noqa: E402

for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures import futures_trader_core as core  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state_files(monkeypatch, tmp_path):
    """Same isolation pattern as test_futures_native_otoco_dry_run_2026_09_03.py -- redirect
    WOULD_BE_FILE / BROKER_TRANSPORT_FILE so a watch-only or transport-error test in this file
    never appends to the real automation/state/futures ledgers."""
    monkeypatch.setattr(tp, "WOULD_BE_FILE", tmp_path / "would-be-trades.jsonl")
    monkeypatch.setattr(tp, "BROKER_TRANSPORT_FILE", tmp_path / "broker-transport.jsonl")


class _FakeLegWithSymbol:
    def __init__(self, symbol):
        self.symbol = symbol


class _FakeOrderRow:
    def __init__(self, order_id, status, symbol="/MESU6"):
        self.id = order_id
        self.status = status
        self.legs = [_FakeLegWithSymbol(symbol)]


def _broker(watch_only=False):
    b = tp.TastytradeBroker(watch_only=watch_only)
    b._connected = True
    b._session = object()
    b._account = mock.Mock()
    return b


# ── watch-only / not-connected: no network, zero-dict ────────────────────────────

def test_cancel_all_watch_only_returns_zero_dict_no_network():
    broker = _broker(watch_only=True)
    out = broker.cancel_all("MES")
    assert out == {"attempted": 0, "cancelled": 0, "failed": []}
    broker._account.get_live_orders.assert_not_called()


def test_cancel_all_not_connected_returns_zero_dict():
    broker = tp.TastytradeBroker(watch_only=False)
    broker._connected = False
    out = broker.cancel_all("MES")
    assert out == {"attempted": 0, "cancelled": 0, "failed": []}


# ── terminal-status filter ────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["Filled", "Cancelled", "Rejected", "Expired", "Removed"])
def test_cancel_all_skips_terminal_status_orders(status):
    """A terminal-status order must never even reach delete_order -- it's not 'attempted'."""
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(
        return_value=[_FakeOrderRow(111, status)])
    broker._account.delete_order = mock.AsyncMock(return_value=None)

    out = broker.cancel_all("MES")

    assert out == {"attempted": 0, "cancelled": 0, "failed": []}
    broker._account.delete_order.assert_not_awaited()


def test_cancel_all_mixed_batch_only_targets_working_orders():
    """The exact bug shape: a batch with terminal orders mixed in among working ones must
    cancel ONLY the working ones."""
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(return_value=[
        _FakeOrderRow(1, "Filled"),
        _FakeOrderRow(2, "Live"),
        _FakeOrderRow(3, "Cancelled"),
        _FakeOrderRow(4, "Received"),
    ])
    broker._account.delete_order = mock.AsyncMock(return_value=None)

    out = broker.cancel_all("MES")

    assert out == {"attempted": 2, "cancelled": 2, "failed": []}
    cancelled_ids = {c.args[1] for c in broker._account.delete_order.await_args_list}
    assert cancelled_ids == {2, 4}


# ── per-order isolation: one raise must not abort the rest ───────────────────────

def test_cancel_all_one_order_raising_does_not_stop_the_others():
    """THE regression this queue item exists for: order 2's delete_order raises -- orders 1
    and 3 (queued on either side of it) must still get their cancel attempted and confirmed,
    and order 2 must land in `failed`, never silently drop the whole sweep."""
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(return_value=[
        _FakeOrderRow(1, "Live"),
        _FakeOrderRow(2, "Live"),
        _FakeOrderRow(3, "Live"),
    ])

    async def _delete(session, order_id):
        if order_id == 2:
            raise RuntimeError("already terminal")
        return None

    broker._account.delete_order = mock.AsyncMock(side_effect=_delete)

    out = broker.cancel_all("MES")

    assert out["attempted"] == 3
    assert out["cancelled"] == 2
    assert out["failed"] == [2]
    # both non-raising orders were still awaited despite order 2 blowing up between them
    cancelled_ids = {c.args[1] for c in broker._account.delete_order.await_args_list}
    assert cancelled_ids == {1, 2, 3}


def test_cancel_all_all_orders_raise_returns_all_failed_never_raises():
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(return_value=[
        _FakeOrderRow(1, "Live"), _FakeOrderRow(2, "Contingent"),
    ])
    broker._account.delete_order = mock.AsyncMock(side_effect=RuntimeError("boom"))

    out = broker.cancel_all("MES")  # must not raise

    assert out["attempted"] == 2
    assert out["cancelled"] == 0
    assert set(out["failed"]) == {1, 2}


def test_cancel_all_clean_sweep_all_cancelled():
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(return_value=[
        _FakeOrderRow(10, "Live"), _FakeOrderRow(11, "Received"),
    ])
    broker._account.delete_order = mock.AsyncMock(return_value=None)

    out = broker.cancel_all("MES")

    assert out == {"attempted": 2, "cancelled": 2, "failed": []}


def test_cancel_all_get_live_orders_transport_failure_returns_dict_never_raises():
    """The OUTER get_live_orders call itself failing (network down) must still return the
    dict shape, not raise into the caller -- same fail-open contract as before."""
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(side_effect=TimeoutError("ReadTimeout"))

    out = broker.cancel_all("MES")

    assert out["attempted"] == 0
    assert out["cancelled"] == 0
    assert out["failed"] == []
    assert "error" in out


def test_cancel_all_only_matches_orders_for_the_given_instrument():
    broker = _broker()
    broker._account.get_live_orders = mock.AsyncMock(return_value=[
        _FakeOrderRow(1, "Live", symbol="/MESU6"),
        _FakeOrderRow(2, "Live", symbol="/MNQU6"),
    ])
    broker._account.delete_order = mock.AsyncMock(return_value=None)

    out = broker.cancel_all("MES")

    assert out == {"attempted": 1, "cancelled": 1, "failed": []}


# ── _cancel_and_confirm_clear (futures_trader_core.py) tolerates the new dict return ──
#
# `_cancel_and_confirm_clear` calls `broker.cancel_all(symbol)` and never inspects its
# return value (it confirms clearance via `get_working_orders` instead) -- this pins that
# the new {attempted, cancelled, failed} dict shape from TastytradeBroker.cancel_all does
# not change that path's behaviour at all: the FLATTEN sweep still confirms clear and
# reports True exactly as it did when cancel_all returned a bare bool.

class _DictReturningCancelBroker:
    """Mimics the real TastytradeBroker.cancel_all's new dict return shape."""

    def __init__(self):
        self.call_log: list[str] = []

    def cancel_all(self, symbol):
        self.call_log.append("cancel_all")
        return {"attempted": 2, "cancelled": 2, "failed": []}

    def get_working_orders(self, symbol):
        self.call_log.append("get_working_orders")
        return []


def test_cancel_and_confirm_clear_ignores_dict_return_value_and_still_confirms(tmp_path):
    import datetime as dt
    broker = _DictReturningCancelBroker()
    paths = {"dir": tmp_path, "ledger": tmp_path / "decisions.jsonl",
             "last_tick": tmp_path / "last-tick.json",
             "loop_state": tmp_path / "loop-state.json",
             "heartbeat": tmp_path / "heartbeat.json"}
    out = core._cancel_and_confirm_clear(broker, "MES", dt.datetime(2026, 8, 12, 11, 0), paths)
    assert out is True
    assert broker.call_log == ["cancel_all", "get_working_orders"]
