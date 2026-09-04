"""Order-lifecycle guards for multi/execute.py + multi/tickers_flatten.py -- the FIVE fixes
from the 2026-09-04 adversarial review (BLOCKER: unconfirmed/partial orders abandoned on the
book, nothing ever cancels).

FIX 1: finalize_order() -- poll, then cancel whatever did not fully fill, then re-read broker
       truth. Entry/exit loops record whatever ACTUALLY filled, clamp exit qty to broker
       truth, and split a partial SELL_ALL close across ticks.
FIX 2: startup reconciliation every tick -- stale BUY-side order sweep + orphan-position
       adoption, both run before core.tick() so an adopted position is managed THIS tick.
FIX 3: multi/lib/tickers_lock.py -- lane-vs-flatten file lock (Windows-safe, no fcntl).
FIX 4: (exercised in the lock test's neighbourhood) covered directly against the pure lock
       primitive; see test_tickers_paths_pinned_2026_09_04.py for FIX 5.

Same no-network discipline as test_tickers_execute_2026_09_04.py: every test monkeypatches
execute.mb.* / execute.mc.* / execute.core.tick and redirects execute.TICKERS_STATE_DIR /
execute.JOURNAL_DIR to a pytest tmp_path. Nothing here ever reaches a real broker.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from multi import execute  # noqa: E402
from multi import tickers_flatten as tf  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import exits as mex  # noqa: E402
from multi.lib import journal as mj  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402
from multi.lib import tickers_lock as tlock  # noqa: E402

FIXED_NOW = dt.datetime(2026, 9, 4, 10, 0, 0)
assert FIXED_NOW.weekday() == 4, "sanity: 2026-09-04 must be a weekday for these fixtures"

BASE_LANE_PARAMS = {
    "arm": "tickers",
    "shadow_only": False,
    "scorer": "production",
    "risk": {
        "max_contracts": 3, "min_contracts": 3, "max_concurrent_positions": 1,
        "daily_loss_kill_switch_pct": 0.01,
    },
    "exits": {"tp1_premium_pct": 45.0, "catastrophe_stop_pct": -50.0},
    "tick_cadence": {"minutes": 2, "first_tick_et": "09:35", "last_entry_et": "14:30"},
    "arms": {
        "tickers-1": {"key_source": "tickers-1", "account_number": "", "universe": ["NVDA", "AAPL", "AMZN"]},
        "tickers-2": {"key_source": "tickers-2", "account_number": "", "universe": ["TSLA", "META", "AVGO"]},
        "tickers-3": {"key_source": "tickers-3", "account_number": "", "universe": ["QQQ", "IWM", "GLD"]},
    },
}


def _lane_params(**overrides) -> dict:
    p = copy.deepcopy(BASE_LANE_PARAMS)
    p.update(overrides)
    return p


def _entry_row(contract: str, *, symbol="NVDA", side="C", qty=3, ask=1.50, mid=1.45,
               spot=500.0, expiry="2026-09-04", spread_pct=2.0) -> dict:
    return {"decision": "WOULD_PLACE", "contract": contract, "symbol": symbol, "side": side,
            "qty": qty, "ask": ask, "mid": mid, "spot": spot, "expiry": expiry,
            "spread_pct": spread_pct}


def _exit_row(contract: str, symbol: str, decision: str, *, qty_to_close=None,
              bid=1.0, ask=1.05, stage="theta_budget") -> dict:
    row = {"kind": "exit_eval", "contract": contract, "symbol": symbol, "decision": decision,
           "stage": stage, "bid": bid, "ask": ask}
    if qty_to_close is not None:
        row["qty_to_close"] = qty_to_close
    return row


def _seed_position(arm: str, contract: str, **kw) -> mps.PositionRecord:
    defaults = dict(symbol="NVDA", contract=contract, side="C", entry_premium=1.0,
                    entry_underlying_price=500.0, qty=3, entry_session_date="2026-09-04",
                    expiry="2026-09-04", hwm_premium=1.0, strategy="production_ribbon_ride")
    defaults.update(kw)
    rec = mps.PositionRecord(**defaults)
    state_path = execute.arm_state_path(arm)
    mps.ensure_initialized(path=state_path)
    mps.save_state({contract: rec}, path=state_path)
    return rec


def _write_secrets(state_dir: Path, arms=("tickers-1", "tickers-2", "tickers-3")) -> None:
    accounts = {}
    for i, a in enumerate(arms, start=1):
        accounts[a] = {"key": f"PKTEST{i}KEY", "secret": f"TESTSECRET{i}",
                       "base_url": "https://paper-api.alpaca.markets"}
    (state_dir / "secrets.json").write_text(json.dumps({"accounts": accounts}), encoding="utf-8")


def _read_ledger(arm: str) -> list[dict]:
    p = execute.arm_ledger_path(arm)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decisions(arm: str, decision: str) -> list[dict]:
    return [r for r in _read_ledger(arm) if r.get("decision") == decision]


def _stub_resolve(params: dict) -> mc.MultiCreds:
    acct = params.get("account") or {}
    return mc.MultiCreds(key="FAKEKEY", secret="FAKESECRET",
                         base_url="https://paper-api.alpaca.markets",
                         account_number=str(acct.get("account_number") or ""),
                         source=f"test:{acct.get('key_source')}")


def _stub_verify_account(resolved_number="PA_RESOLVED", equity=100000.0):
    def _fn(creds: mc.MultiCreds) -> dict:
        if creds.account_number and creds.account_number != resolved_number:
            raise mc.CredError(
                f"ACCOUNT MISMATCH: params.json says {creds.account_number} but the resolved "
                f"key authenticates as {resolved_number}. Refusing to proceed.")
        return {"account_number": resolved_number, "equity": equity, "buying_power": equity,
                "options_approved_level": 3, "status": "ACTIVE"}
    return _fn


def _recording_broker(monkeypatch: pytest.MonkeyPatch, *, held_qty: int = 999) -> dict:
    """Same fake surface as test_tickers_execute_2026_09_04.py's own helper (kept local --
    that file is a sibling test module, not a shared fixture library this suite imports from)."""
    calls = {"place_bracket": [], "market_sell": [], "cancel_order": []}

    def fake_place_bracket(creds, *, symbol, qty, limit_price, take_profit_price, stop_price,
                           armed=False, simple_fallback=False, params=None):
        calls["place_bracket"].append({"symbol": symbol, "qty": qty, "armed": armed})
        preview = execute.mb._gate_submission(armed, {"symbol": symbol, "qty": qty}, params=params)
        if preview is not None:
            return preview
        return {"id": "order-entry-1", "status": "accepted"}

    def fake_market_sell(creds, *, symbol, qty, armed=False, params=None):
        calls["market_sell"].append({"symbol": symbol, "qty": qty, "armed": armed})
        preview = execute.mb._gate_submission(armed, {"symbol": symbol, "qty": qty}, params=params)
        if preview is not None:
            return preview
        return {"id": "order-exit-1", "status": "accepted"}

    def fake_poll_fill(creds, order_id, *, attempts=3, sleep_sec=1.5):
        return {"filled": True, "status": "filled", "filled_qty": 3, "filled_avg_price": 1.60, "order": {}}

    def fake_equity_option_positions(creds, *, allowed_roots=None):
        return []

    def fake_get_orders(creds, *, status="open", symbol=None, side=None):
        return []

    def fake_get_order(creds, order_id):
        return {"id": order_id, "status": "filled", "filled_qty": 3, "filled_avg_price": 1.60}

    def fake_cancel_order(creds, order_id, *, armed=False, params=None):
        calls["cancel_order"].append({"order_id": order_id, "armed": armed})
        preview = execute.mb._gate_submission(armed, {"cancel_order_id": order_id}, params=params)
        if preview is not None:
            return preview
        return {"id": order_id, "status": "canceled"}

    def fake_get_position_qty(creds, symbol):
        return held_qty

    monkeypatch.setattr(execute.mb, "place_bracket", fake_place_bracket)
    monkeypatch.setattr(execute.mb, "market_sell", fake_market_sell)
    monkeypatch.setattr(execute.mb, "poll_fill", fake_poll_fill)
    monkeypatch.setattr(execute.mb, "equity_option_positions", fake_equity_option_positions)
    monkeypatch.setattr(execute.mb, "get_orders", fake_get_orders)
    monkeypatch.setattr(execute.mb, "get_order", fake_get_order)
    monkeypatch.setattr(execute.mb, "cancel_order", fake_cancel_order)
    monkeypatch.setattr(execute.mb, "get_position_qty", fake_get_position_qty)
    return calls


@pytest.fixture
def state_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "tickers"
    d.mkdir()
    monkeypatch.setattr(execute, "TICKERS_STATE_DIR", d)
    monkeypatch.setattr(execute, "JOURNAL_DIR", tmp_path / "journal")
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("## Known broken\n\n", encoding="utf-8")
    monkeypatch.setattr(execute, "STATUS_PATH", status_path)
    monkeypatch.setattr(execute, "now_et", lambda: FIXED_NOW)
    monkeypatch.setattr(execute.mc, "resolve", _stub_resolve)
    monkeypatch.setattr(execute.mc, "verify_account", _stub_verify_account())
    return d


def _deadline() -> float:
    return time.monotonic() + 60.0


# =============================================================================================
# 1. finalize_order -- direct unit tests, no run_arm needed
# =============================================================================================
def test_finalize_order_filled_immediately_no_cancel(monkeypatch):
    cancel_calls = []
    monkeypatch.setattr(execute.mb, "poll_fill", lambda creds, oid, *, attempts, sleep_sec: {
        "filled": True, "status": "filled", "filled_qty": 3, "filled_avg_price": 1.5, "order": {}})
    monkeypatch.setattr(execute.mb, "cancel_order",
                        lambda *a, **kw: cancel_calls.append(1) or {"status": "canceled"})
    monkeypatch.setattr(execute.mb, "get_order",
                        lambda *a, **kw: pytest.fail("get_order must not run on a clean full fill"))

    result = execute.finalize_order(None, "oid-1", requested_qty=3, shadow=False,
                                    arm_params={}, attempts=6, sleep_sec=2.0)

    assert result == {"status": "filled", "filled_qty": 3, "filled_avg_price": 1.5,
                      "canceled": False, "limbo": False}
    assert cancel_calls == []


def test_finalize_order_unfilled_gets_canceled(monkeypatch):
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": False, "status": "new", "filled_qty": 0, "filled_avg_price": None, "order": {}})
    cancel_calls = []

    def _cancel(creds, order_id, *, armed, params):
        cancel_calls.append({"order_id": order_id, "armed": armed})
        return {"id": order_id, "status": "canceled"}
    monkeypatch.setattr(execute.mb, "cancel_order", _cancel)
    monkeypatch.setattr(execute.mb, "get_order", lambda creds, oid: {
        "id": oid, "status": "canceled", "filled_qty": 0, "filled_avg_price": None})
    monkeypatch.setattr(execute.time, "sleep", lambda s: None)

    result = execute.finalize_order(None, "oid-2", requested_qty=3, shadow=False,
                                    arm_params={}, attempts=6, sleep_sec=2.0)

    assert result["filled_qty"] == 0
    assert result["canceled"] is True
    assert result["limbo"] is False
    assert len(cancel_calls) == 1
    assert cancel_calls[0]["armed"] is True  # shadow=False -> armed=(not shadow)=True


def test_finalize_order_partial_fill_remainder_canceled(monkeypatch):
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": True, "status": "partially_filled", "filled_qty": 1, "filled_avg_price": 1.55, "order": {}})
    monkeypatch.setattr(execute.mb, "cancel_order",
                        lambda creds, oid, *, armed, params: {"id": oid, "status": "canceled"})
    monkeypatch.setattr(execute.mb, "get_order", lambda creds, oid: {
        "id": oid, "status": "canceled", "filled_qty": 1, "filled_avg_price": 1.55})
    monkeypatch.setattr(execute.time, "sleep", lambda s: None)

    result = execute.finalize_order(None, "oid-3", requested_qty=3, shadow=False,
                                    arm_params={}, attempts=4, sleep_sec=2.0)

    assert result["filled_qty"] == 1
    assert result["filled_avg_price"] == 1.55
    assert result["canceled"] is True
    assert result["limbo"] is False


def test_finalize_order_cancel_races_a_fill_re_read_shows_filled(monkeypatch):
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": False, "status": "accepted", "filled_qty": 0, "filled_avg_price": None, "order": {}})

    def _cancel(creds, order_id, *, armed, params):
        raise execute.mb.BrokerAPIError("422 order already filled")
    monkeypatch.setattr(execute.mb, "cancel_order", _cancel)
    monkeypatch.setattr(execute.mb, "get_order", lambda creds, oid: {
        "id": oid, "status": "filled", "filled_qty": 3, "filled_avg_price": 1.62})
    monkeypatch.setattr(execute.time, "sleep", lambda s: None)

    result = execute.finalize_order(None, "oid-4", requested_qty=3, shadow=False,
                                    arm_params={}, attempts=6, sleep_sec=2.0)

    assert result["status"] == "filled"
    assert result["filled_qty"] == 3
    assert result["filled_avg_price"] == 1.62
    assert result["canceled"] is False
    assert result["limbo"] is False


def test_finalize_order_limbo_when_still_non_terminal_after_reads(monkeypatch):
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": False, "status": "accepted", "filled_qty": 0, "filled_avg_price": None, "order": {}})
    monkeypatch.setattr(execute.mb, "cancel_order", lambda *a, **kw: {"id": "x", "status": "pending_cancel"})
    monkeypatch.setattr(execute.mb, "get_order", lambda creds, oid: {
        "id": oid, "status": "pending_cancel", "filled_qty": 0, "filled_avg_price": None})
    monkeypatch.setattr(execute.time, "sleep", lambda s: None)

    result = execute.finalize_order(None, "oid-5", requested_qty=3, shadow=False,
                                    arm_params={}, attempts=6, sleep_sec=2.0)

    assert result["limbo"] is True
    assert result["filled_qty"] == 0


# =============================================================================================
# 2. entry loop: ENTRY_CANCELED places no record
# =============================================================================================
def test_entry_canceled_places_no_record(state_dir, monkeypatch):
    _recording_broker(monkeypatch)
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": False, "status": "new", "filled_qty": 0, "filled_avg_price": None, "order": {}})
    monkeypatch.setattr(execute.mb, "get_order", lambda creds, oid: {
        "id": oid, "status": "canceled", "filled_qty": 0, "filled_avg_price": None})
    monkeypatch.setattr(execute.time, "sleep", lambda s: None)
    contract = "NVDA260904C00500000"
    rows = [_entry_row(contract, symbol="NVDA", qty=3)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert summary["placed"] == 0
    assert len(_decisions("tickers-1", "ENTRY_CANCELED")) == 1
    assert _decisions("tickers-1", "ENTRY_FILLED") == []
    state = mps.load_state(path=execute.arm_state_path("tickers-1"))
    assert contract not in state


# =============================================================================================
# 3. exit SELL_ALL partial keeps the record; second tick (clamped to broker truth) finishes it
# =============================================================================================
def test_exit_sell_all_partial_keeps_record_second_tick_finishes(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch, held_qty=3)
    contract = "AAPL260904C00220000"
    _seed_position("tickers-1", contract, symbol="AAPL", entry_premium=1.0, hwm_premium=1.0, qty=3)
    rows = [_exit_row(contract, "AAPL", mex.ACTION_SELL_ALL, qty_to_close=3, bid=2.0, ask=2.05, stage="tp1")]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    # tick 1: only 1 of 3 fills; finalize_order cancels the remainder.
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": True, "status": "partially_filled", "filled_qty": 1, "filled_avg_price": 1.9, "order": {}})
    monkeypatch.setattr(execute.mb, "get_order", lambda creds, oid: {
        "id": oid, "status": "canceled", "filled_qty": 1, "filled_avg_price": 1.9})
    monkeypatch.setattr(execute.time, "sleep", lambda s: None)

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(_decisions("tickers-1", "EXIT_PARTIAL")) == 1
    assert _decisions("tickers-1", "EXIT_FILLED") == []
    state = mps.load_state(path=execute.arm_state_path("tickers-1"))
    assert contract in state, "a partial SELL_ALL must NOT pop the record"

    # tick 2: broker now holds only 2 (1 already sold last tick). core.py's row STILL says
    # qty_to_close=3 (it derives that from the record's ORIGINAL qty, which position_state.py
    # documents as never decremented) -- the belt-and-suspenders clamp must cut it to 2.
    monkeypatch.setattr(execute.mb, "get_position_qty", lambda creds, symbol: 2)
    monkeypatch.setattr(execute.mb, "poll_fill", lambda *a, **kw: {
        "filled": True, "status": "filled", "filled_qty": 2, "filled_avg_price": 2.1, "order": {}})

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert calls["market_sell"][-1]["qty"] == 2, "qty_to_close=3 must be clamped to held=2"
    filled = _decisions("tickers-1", "EXIT_FILLED")
    assert len(filled) == 1 and filled[0]["qty"] == 2
    # journal price is the qty-weighted average of BOTH fills: (1*1.9 + 2*2.1) / 3
    assert filled[0]["journal_price"] == round((1 * 1.9 + 2 * 2.1) / 3, 4)
    state2 = mps.load_state(path=execute.arm_state_path("tickers-1"))
    assert contract not in state2, "the fully-closed contract must now be popped"


def test_exit_qty_clamped_to_broker_held_qty(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch, held_qty=1)
    contract = "AMZN260904C00190000"
    _seed_position("tickers-1", contract, symbol="AMZN", entry_premium=1.0, hwm_premium=1.0, qty=3)
    rows = [_exit_row(contract, "AMZN", mex.ACTION_SELL_ALL, qty_to_close=3, bid=2.0, ask=2.05)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert calls["market_sell"] == [{"symbol": contract, "qty": 1, "armed": True}]


# =============================================================================================
# 4. STALE_STATE row + held==0 both drop the record; a broker read error never sells blind
# =============================================================================================
def test_stale_state_row_drops_record_no_sell(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    contract = "META260904C00700000"
    _seed_position("tickers-2", contract, symbol="META", entry_premium=1.0, hwm_premium=1.0)
    rows = [{"kind": "exit_eval", "contract": contract, "symbol": "META", "decision": "STALE_STATE",
            "gate": "broker_flat", "reason": "broker reports flat"}]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-2"])

    execute.run_arm("tickers-2", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(_decisions("tickers-2", "STATE_RECORD_DROPPED")) == 1
    assert calls["market_sell"] == []
    state = mps.load_state(path=execute.arm_state_path("tickers-2"))
    assert contract not in state


def test_exit_held_zero_pops_record(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch, held_qty=0)
    contract = "TSLA260904C00250000"
    _seed_position("tickers-2", contract, symbol="TSLA", entry_premium=1.0, hwm_premium=1.0)
    rows = [_exit_row(contract, "TSLA", mex.ACTION_SELL_ALL, qty_to_close=3, bid=2.0, ask=2.05)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-2"])

    execute.run_arm("tickers-2", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(_decisions("tickers-2", "EXIT_SKIPPED_FLAT")) == 1
    assert calls["market_sell"] == []
    state = mps.load_state(path=execute.arm_state_path("tickers-2"))
    assert contract not in state


def test_exit_qty_read_error_never_sells_blind(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)

    def _boom(creds, symbol):
        raise execute.mb.BrokerAPIError("simulated read failure")
    monkeypatch.setattr(execute.mb, "get_position_qty", _boom)
    contract = "IWM260904C00220000"
    _seed_position("tickers-3", contract, symbol="IWM", entry_premium=1.0, hwm_premium=1.0)
    rows = [_exit_row(contract, "IWM", mex.ACTION_SELL_ALL, qty_to_close=3, bid=2.0, ask=2.05)]
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: (rows, Counter()))
    _write_secrets(state_dir, arms=["tickers-3"])

    execute.run_arm("tickers-3", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(_decisions("tickers-3", "EXIT_QTY_READ_ERROR")) == 1
    assert calls["market_sell"] == []
    state = mps.load_state(path=execute.arm_state_path("tickers-3"))
    assert contract in state, "an UNKNOWN held qty must never drop or sell the record"


# =============================================================================================
# 5. stale-order sweep: universe BUY orders canceled; foreign roots and sell legs left alone
# =============================================================================================
def test_stale_order_sweep_cancels_buy_side_universe_orders_only(state_dir, monkeypatch):
    calls = _recording_broker(monkeypatch)
    open_orders = [
        {"id": "buy-ours", "symbol": "NVDA260904C00500000", "side": "buy", "qty": "3", "submitted_at": "t"},
        {"id": "sell-ours-protective", "symbol": "NVDA260904C00500000", "side": "sell", "qty": "3"},
        {"id": "buy-foreign", "symbol": "TSLA260904C00250000", "side": "buy", "qty": "3"},
    ]
    monkeypatch.setattr(execute.mb, "get_orders", lambda creds, **kw: open_orders)
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: ([], Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])  # universe NVDA/AAPL/AMZN -- TSLA is foreign

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(calls["cancel_order"]) == 1
    assert calls["cancel_order"][0]["order_id"] == "buy-ours"
    canceled = _decisions("tickers-1", "STALE_ORDER_CANCELED")
    assert len(canceled) == 1 and canceled[0]["order_id"] == "buy-ours"
    foreign = _decisions("tickers-1", "FOREIGN_OPEN_ORDER")
    assert len(foreign) == 1 and foreign[0]["order_id"] == "buy-foreign"
    assert all(row.get("order_id") != "sell-ours-protective" for row in _read_ledger("tickers-1")), (
        "a protective sell-side leg must never be touched OR even logged about")


def test_orders_read_error_logged_and_tick_continues(state_dir, monkeypatch):
    _recording_broker(monkeypatch)

    def _boom(creds, *, status="open", symbol=None, side=None):
        raise execute.mb.BrokerAPIError("simulated orders read failure")
    monkeypatch.setattr(execute.mb, "get_orders", _boom)
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: ([], Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    summary = execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert len(_decisions("tickers-1", "ORDERS_READ_ERROR")) == 1
    assert summary["creds"] == "ok"  # the tick was NOT aborted by the read failure


# =============================================================================================
# 6. orphan-position adoption
# =============================================================================================
def test_orphan_position_adopted_with_record_and_journal_row(state_dir, monkeypatch):
    _recording_broker(monkeypatch)
    contract = "AAPL260904C00220000"
    orphan_position = {"symbol": contract, "avg_entry_price": "1.85", "qty": "3", "current_price": "2.10"}
    monkeypatch.setattr(execute.mb, "equity_option_positions", lambda creds, allowed_roots=None: [orphan_position])
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: ([], Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    adopted = _decisions("tickers-1", "POSITION_ADOPTED")
    assert len(adopted) == 1
    assert adopted[0]["contract"] == contract
    assert adopted[0]["qty"] == 3
    assert adopted[0]["side"] == "C"

    state = mps.load_state(path=execute.arm_state_path("tickers-1"))
    assert contract in state
    rec = state[contract]
    assert rec.qty == 3
    assert rec.entry_premium == 1.85
    assert rec.symbol == "AAPL"

    journal_rows = mj.all_rows(path=execute.arm_journal_path("tickers-1"))
    entry_rows = [r for r in journal_rows if r.get("row_type") == "ENTRY"]
    assert len(entry_rows) == 1
    assert entry_rows[0]["contract"] == contract
    assert entry_rows[0]["trade_id"].startswith("adopted-tickers-1-")


def test_orphan_adoption_skipped_when_already_known(state_dir, monkeypatch):
    """A position already in state must never be re-adopted -- adoption would clobber real,
    live history (hwm_premium, tp1_filled) with a fresh, ignorant record."""
    _recording_broker(monkeypatch)
    contract = "AAPL260904C00220000"
    _seed_position("tickers-1", contract, symbol="AAPL", entry_premium=9.99, tp1_filled=True)
    orphan_position = {"symbol": contract, "avg_entry_price": "1.85", "qty": "3"}
    monkeypatch.setattr(execute.mb, "equity_option_positions", lambda creds, allowed_roots=None: [orphan_position])
    monkeypatch.setattr(execute.core, "tick", lambda *a, **kw: ([], Counter()))
    _write_secrets(state_dir, arms=["tickers-1"])

    execute.run_arm("tickers-1", _lane_params(), {}, {}, shadow=False, deadline=_deadline())

    assert _decisions("tickers-1", "POSITION_ADOPTED") == []
    state = mps.load_state(path=execute.arm_state_path("tickers-1"))
    assert state[contract].entry_premium == 9.99
    assert state[contract].tp1_filled is True


# =============================================================================================
# 7. weighted_exit_price -- pure function
# =============================================================================================
def test_weighted_exit_price_averages_closing_sells_only():
    contract = "NVDA260904C00500000"
    fills = [
        {"contract": contract, "side": "BUY", "qty": 3, "price": 1.0},
        {"contract": contract, "side": "SELL_PARTIAL", "qty": 1, "price": 5.0},  # TP1 -- excluded
        {"contract": contract, "side": "SELL_ALL_PARTIAL", "qty": 1, "price": 2.0},
        {"contract": "OTHER260904C00100000", "side": "SELL_ALL", "qty": 9, "price": 999.0},  # other contract
        {"contract": contract, "side": "SELL_ALL", "qty": 1, "price": 2.2},
    ]
    px = execute.weighted_exit_price(fills, contract)
    assert px == round((1 * 2.0 + 1 * 2.2) / 2, 4)


def test_weighted_exit_price_none_when_no_qualifying_fills():
    assert execute.weighted_exit_price([], "NVDA260904C00500000") is None
    assert execute.weighted_exit_price(
        [{"contract": "X", "side": "SELL_ALL", "qty": 1, "price": 1.0}], "NVDA260904C00500000") is None


# =============================================================================================
# 8. multi/lib/tickers_lock.py -- the pure primitive
# =============================================================================================
def test_lock_second_acquire_fails_while_held(tmp_path):
    lock_path = tmp_path / ".lane.lock"
    h1 = tlock.acquire(lock_path)
    assert h1 is not None
    assert lock_path.exists()

    h2 = tlock.acquire(lock_path)
    assert h2 is None

    tlock.release(h1)
    assert not lock_path.exists()


def test_lock_stale_lock_is_reclaimed(tmp_path):
    import os as _os
    lock_path = tmp_path / ".lane.lock"
    lock_path.write_text('{"pid": 999999, "acquired_at_et": "2020-01-01T00:00:00"}', encoding="utf-8")
    old = time.time() - 1000.0  # 1000s old, well past the 240s default staleness threshold
    _os.utime(lock_path, (old, old))

    handle = tlock.acquire(lock_path, stale_after_sec=240.0)

    assert handle is not None
    tlock.release(handle)


def test_lock_fresh_lock_is_not_reclaimed(tmp_path):
    lock_path = tmp_path / ".lane.lock"
    h1 = tlock.acquire(lock_path)
    assert h1 is not None

    handle = tlock.acquire(lock_path, stale_after_sec=240.0)  # fresh -- must NOT be reclaimed

    assert handle is None
    tlock.release(h1)


def test_lock_release_is_idempotent_and_none_safe(tmp_path):
    tlock.release(None)  # never held -- must not raise
    p = tmp_path / ".lock"
    h = tlock.acquire(p)
    tlock.release(h)
    tlock.release(h)  # already gone -- must not raise


# =============================================================================================
# 9. tickers_flatten.py's lock wait-then-force policy (FIX 3's caller-side half)
# =============================================================================================
def test_flatten_forces_past_a_held_lock_after_the_wait(tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "STATE_DIR", tmp_path)
    lock_path = tmp_path / ".lane.lock"
    other = tlock.acquire(lock_path)  # simulates another process holding it throughout
    assert other is not None

    monkeypatch.setattr(tf, "flatten_one", lambda lane_params, arm, *, shadow, ts: (True, f"{arm}:ok"))
    monkeypatch.setattr(tf.mc, "load_params", lambda path: _lane_params())

    monotonic_calls = {"n": 0}

    def _fake_monotonic():
        monotonic_calls["n"] += 1
        if monotonic_calls["n"] == 1:
            return 0.0          # initial wait_deadline computation
        if monotonic_calls["n"] <= 3:
            return 10.0         # two loop iterations still inside the window
        return 10_000.0         # then jump well past the deadline to end the loop
    monkeypatch.setattr(tf.time, "monotonic", _fake_monotonic)
    sleeps: list = []
    monkeypatch.setattr(tf.time, "sleep", lambda s: sleeps.append(s))

    rc = tf.flatten_all(tmp_path / "params.json", shadow=False)

    assert sleeps, "flatten_all must have polled for the lock at least once before forcing"
    assert rc == 0  # every arm's stubbed flatten_one reports ok
    tlock.release(other)


def test_flatten_acquires_immediately_when_lock_is_free(tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "STATE_DIR", tmp_path)
    monkeypatch.setattr(tf, "flatten_one", lambda lane_params, arm, *, shadow, ts: (True, f"{arm}:ok"))
    monkeypatch.setattr(tf.mc, "load_params", lambda path: _lane_params())
    sleeps: list = []
    monkeypatch.setattr(tf.time, "sleep", lambda s: sleeps.append(s))

    rc = tf.flatten_all(tmp_path / "params.json", shadow=False)

    assert sleeps == [], "an uncontended lock must never wait"
    assert rc == 0
    assert not (tmp_path / ".lane.lock").exists(), "the lock must be released after the pass"
