"""Guard for setup/scripts/spread_executor.py -- the DISARMED Alpaca mleg
vertical-debit-spread machinery (EDGE-2-DEBIT-SPREAD-AB build lane,
2026-07-14). No test here ever touches the network: the broker POST is
monkeypatched, and the never-armed guard asserts the broker is NOT called.

RED-PROOF CONTRACT (never-armed-by-default block): these tests go RED if
anyone (a) flips spread_execution_enabled in EITHER live params file, or
(b) weakens is_armed / the submit_spread gate, without coming through this
file. When the debit-spread A/B scorecard clears OP-11 and the key legitimately
flips, updating test_live_params_files_ship_disarmed WITH the scorecard
reference IS part of the arming diff -- that is the point of the guard.

Run: cd backtest && python -m pytest tests/test_spread_executor.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def sx():
    return importlib.import_module("spread_executor")


@pytest.fixture()
def sl():
    return importlib.import_module("settlement_ledger")


_EXP = "260715"


def _chain(sx, strikes, cp="C", expiry=_EXP):
    return [sx.occ_symbol(cp, s, expiry) for s in strikes]


def _both_chain(sx, strikes, expiry=_EXP):
    return _chain(sx, strikes, "C", expiry) + _chain(sx, strikes, "P", expiry)


_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.alpaca.markets"}
_ARMED = {"spread_execution_enabled": True}
_NOON = datetime(2026, 7, 15, 12, 0, 0)


def _no_broker(monkeypatch, sx):
    def _boom(*a, **k):
        raise AssertionError("broker _request was called -- gate failed to refuse")
    monkeypatch.setattr(sx, "_request", _boom)


def _capture_broker(monkeypatch, sx, response=None):
    calls: list[dict] = []

    def _fake(creds, endpoint, method="GET", data=None, timeout=15, host=None):
        calls.append({"endpoint": endpoint, "method": method, "data": data})
        return dict(response or {"id": "fake-order-id", "status": "accepted"})
    monkeypatch.setattr(sx, "_request", _fake)
    return calls


# ---- leg construction ---------------------------------------------------------

def test_call_spread_width_1_long_atm_short_otm_above(sx):
    legs = sx.build_debit_spread_legs("C", 625.30, _chain(sx, range(615, 636)), 1)
    assert sx.parse_occ(legs[0]["symbol"])["strike"] == 625.0   # long = ATM
    assert sx.parse_occ(legs[1]["symbol"])["strike"] == 626.0   # short = OTM above


def test_call_spread_width_5(sx):
    legs = sx.build_debit_spread_legs("C", 625.30, _chain(sx, range(615, 636)), 5)
    assert sx.parse_occ(legs[1]["symbol"])["strike"] == 630.0
    assert sx.spread_width(legs) == 5.0


def test_put_spread_width_1_long_atm_short_otm_below(sx):
    legs = sx.build_debit_spread_legs("P", 625.30, _chain(sx, range(615, 636), "P"), 1)
    assert sx.parse_occ(legs[0]["symbol"])["strike"] == 625.0
    assert sx.parse_occ(legs[1]["symbol"])["strike"] == 624.0   # short = OTM below


def test_put_spread_width_5(sx):
    legs = sx.build_debit_spread_legs("P", 624.61, _chain(sx, range(615, 636), "P"), 5)
    assert sx.parse_occ(legs[0]["symbol"])["strike"] == 625.0   # ATM = round(624.61)
    assert sx.parse_occ(legs[1]["symbol"])["strike"] == 620.0


def test_legs_carry_the_mleg_fields(sx):
    legs = sx.build_debit_spread_legs("C", 625.0, _chain(sx, range(615, 636)), 1)
    long_leg, short_leg = legs
    assert (long_leg["side"], long_leg["position_intent"], long_leg["ratio_qty"]) == \
        ("buy", "buy_to_open", "1")
    assert (short_leg["side"], short_leg["position_intent"], short_leg["ratio_qty"]) == \
        ("sell", "sell_to_open", "1")


def test_legs_select_only_matching_type_from_mixed_chain(sx):
    legs = sx.build_debit_spread_legs("P", 625.0, _both_chain(sx, range(615, 636)), 2)
    assert all(sx.parse_occ(leg["symbol"])["cp"] == "P" for leg in legs)


def test_chain_accepts_contract_dicts_and_symbol_keyed_dict(sx):
    dict_chain = [{"symbol": s} for s in _chain(sx, range(615, 636))]
    legs = sx.build_debit_spread_legs("C", 625.0, dict_chain, 1)
    assert sx.validate_spread_legs(legs) is None
    keyed = {s: {"greeks": {}} for s in _chain(sx, range(615, 636))}
    legs2 = sx.build_debit_spread_legs("C", 625.0, keyed, 1)
    assert [leg["symbol"] for leg in legs2] == [leg["symbol"] for leg in legs]


def test_multi_expiry_chain_prefers_earliest(sx):
    chain = _chain(sx, range(615, 636), "C", "260716") + _chain(sx, range(615, 636), "C", "260715")
    legs = sx.build_debit_spread_legs("C", 625.0, chain, 1)
    assert all(sx.parse_occ(leg["symbol"])["expiry"] == "260715" for leg in legs)


def test_missing_short_strike_raises(sx):
    with pytest.raises(ValueError, match="missing strikes"):
        sx.build_debit_spread_legs("C", 625.0, _chain(sx, [625]), 1)


def test_missing_long_strike_raises(sx):
    with pytest.raises(ValueError, match="missing strikes"):
        sx.build_debit_spread_legs("C", 625.0, _chain(sx, [626]), 1)


def test_invalid_side_and_width_raise(sx):
    chain = _chain(sx, range(615, 636))
    with pytest.raises(ValueError, match="side"):
        sx.build_debit_spread_legs("call", 625.0, chain, 1)
    with pytest.raises(ValueError, match="width"):
        sx.build_debit_spread_legs("C", 625.0, chain, 0)


def test_validate_refuses_credit_geometry(sx):
    legs = [
        {"symbol": sx.occ_symbol("C", 626, _EXP), "ratio_qty": "1",
         "side": "buy", "position_intent": "buy_to_open"},
        {"symbol": sx.occ_symbol("C", 625, _EXP), "ratio_qty": "1",
         "side": "sell", "position_intent": "sell_to_open"},
    ]
    assert "credit geometry refused" in sx.validate_spread_legs(legs)


def test_validate_refuses_mixed_expiry(sx):
    legs = [
        {"symbol": sx.occ_symbol("C", 625, "260715"), "ratio_qty": "1",
         "side": "buy", "position_intent": "buy_to_open"},
        {"symbol": sx.occ_symbol("C", 626, "260716"), "ratio_qty": "1",
         "side": "sell", "position_intent": "sell_to_open"},
    ]
    assert "expiry" in sx.validate_spread_legs(legs)


# ---- limit pricing from real quote fixtures -----------------------------------
# Fixture shapes = Alpaca v1beta1 latest-quotes (bp/ap), the same feed
# fleet_broker.get_option_mid prices the live single-leg parent from.

_LONG_Q = {"bp": 1.55, "ap": 1.61}    # ATM leg
_SHORT_Q = {"bp": 1.02, "ap": 1.08}   # OTM leg


def test_net_debit_mid(sx):
    # (1.58 mid) - (1.05 mid) = 0.53
    assert sx.net_debit_limit(_LONG_Q, _SHORT_Q, "mid") == 0.53


def test_net_debit_marketable(sx):
    # long ask 1.61 - short bid 1.02 = 0.59
    assert sx.net_debit_limit(_LONG_Q, _SHORT_Q, "marketable") == 0.59


def test_net_debit_floors_at_one_cent(sx):
    assert sx.net_debit_limit({"bp": 1.00, "ap": 1.02}, {"bp": 1.00, "ap": 1.02}, "mid") == 0.01


def test_net_debit_none_on_unusable_quote(sx):
    assert sx.net_debit_limit(None, _SHORT_Q, "mid") is None
    assert sx.net_debit_limit(_LONG_Q, {"bp": 0, "ap": 0}, "mid") is None


def test_close_credit_marketable(sx):
    # long bid 1.55 - short ask 1.08 = 0.47
    assert sx.close_credit_limit(_LONG_Q, _SHORT_Q) == 0.47


def test_close_credit_floors_and_none(sx):
    assert sx.close_credit_limit({"bp": 0.50, "ap": 0.52}, {"bp": 0.60, "ap": 0.70}) == 0.01
    assert sx.close_credit_limit(None, _SHORT_Q) is None


# ---- NEVER-ARMED-BY-DEFAULT (RED-proof) ----------------------------------------

def _good_legs(sx):
    return sx.build_debit_spread_legs("C", 625.0, _chain(sx, range(615, 636)), 1)


def test_is_armed_only_on_literal_bool_true(sx):
    for bad in ({}, {"spread_execution_enabled": False},
                {"spread_execution_enabled": None},
                {"spread_execution_enabled": "true"},
                {"spread_execution_enabled": 1}, None):
        assert sx.is_armed(bad) is False
    assert sx.is_armed({"spread_execution_enabled": True}) is True


def test_submit_refused_and_broker_untouched_when_disarmed(sx, monkeypatch):
    _no_broker(monkeypatch, sx)
    for params in ({}, {"spread_execution_enabled": False},
                   {"spread_execution_enabled": "true"}):
        res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53,
                               params=params, now_et=_NOON)
        assert res["_refused"] == "SPREAD_DISARMED"


def test_submit_places_mleg_when_armed(sx, monkeypatch):
    calls = _capture_broker(monkeypatch, sx)
    res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params=_ARMED, now_et=_NOON)
    assert res.get("id") == "fake-order-id"
    (call,) = calls
    assert call["endpoint"] == "orders" and call["method"] == "POST"
    order = call["data"]
    assert order["order_class"] == "mleg"
    assert order["qty"] == "3" and order["limit_price"] == "0.53"
    assert order["type"] == "limit" and order["time_in_force"] == "day"
    assert len(order["legs"]) == 2
    assert {leg["position_intent"] for leg in order["legs"]} == {"buy_to_open", "sell_to_open"}


def test_live_params_files_ship_disarmed(sx):
    """RED-PROOF: flipping spread_execution_enabled in EITHER live params file
    without coming through this test = RED. The arming diff (post debit-spread
    A/B scorecard, OP-11) updates THIS assertion with the scorecard reference."""
    for rel in ("automation/state/params.json", "automation/state/aggressive/params.json"):
        params = json.loads((_REPO / rel).read_text(encoding="utf-8"))
        assert "spread_execution_enabled" in params, f"{rel} lost the key"
        assert params["spread_execution_enabled"] is False, \
            f"{rel} armed without updating the guard -- see test docstring"
        assert not sx.is_armed(params)


def test_submit_refuses_bad_legs_qty_and_price_even_when_armed(sx, monkeypatch):
    _no_broker(monkeypatch, sx)
    legs = _good_legs(sx)
    assert "BAD_LEGS" in sx.submit_spread(_CREDS, legs[:1], 3, 0.53,
                                          params=_ARMED, now_et=_NOON)["_refused"]
    assert "qty" in sx.submit_spread(_CREDS, legs, 0, 0.53,
                                     params=_ARMED, now_et=_NOON)["_refused"]
    assert "limit_price" in sx.submit_spread(_CREDS, legs, 3, 0,
                                             params=_ARMED, now_et=_NOON)["_refused"]


def test_submit_refuses_debit_at_or_above_width(sx, monkeypatch):
    _no_broker(monkeypatch, sx)
    res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 1.00, params=_ARMED, now_et=_NOON)
    assert res["_refused"].startswith("DEBIT_GE_WIDTH")


# ---- settlement-ledger integration ---------------------------------------------

def test_placed_spread_debits_the_settled_pool(sx, sl, monkeypatch, tmp_path):
    _capture_broker(monkeypatch, sx)
    ctx = {"state_dir": tmp_path, "account": "safe", "sod_settled_cash": 1746.75}
    res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params=_ARMED,
                           now_et=_NOON, settlement_ctx=ctx)
    assert res["_settlement_recorded"] is True
    status = sl.get_settlement_status(sl.ledger_path(tmp_path, "safe"),
                                      _NOON.strftime("%Y-%m-%d"), 1746.75)
    assert status["entries_used_today"] == 1
    # net debit paid in full: 0.53 * 3 * 100 = 159.0 off the settled pool
    assert status["settled_cash_remaining"] == pytest.approx(1746.75 - 159.0)


def test_refused_spread_records_no_settlement(sx, sl, monkeypatch, tmp_path):
    _no_broker(monkeypatch, sx)
    ctx = {"state_dir": tmp_path, "account": "safe", "sod_settled_cash": 1746.75}
    sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params={},
                     now_et=_NOON, settlement_ctx=ctx)
    assert not sl.ledger_path(tmp_path, "safe").exists()


def test_failed_post_records_no_settlement(sx, sl, monkeypatch, tmp_path):
    _capture_broker(monkeypatch, sx, response={"_error": "HTTP 422", "_status": 422})
    ctx = {"state_dir": tmp_path, "account": "safe", "sod_settled_cash": 1746.75}
    res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params=_ARMED,
                           now_et=_NOON, settlement_ctx=ctx)
    assert res.get("_error")
    assert not sl.ledger_path(tmp_path, "safe").exists()


def test_bold_settlement_uses_aggressive_ledger_path(sx, sl, monkeypatch, tmp_path):
    _capture_broker(monkeypatch, sx)
    ctx = {"state_dir": tmp_path, "account": "bold", "sod_settled_cash": 1633.0}
    sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params=_ARMED,
                     now_et=_NOON, settlement_ctx=ctx)
    assert sl.ledger_path(tmp_path, "bold").exists()
    assert "aggressive" in str(sl.ledger_path(tmp_path, "bold"))


# ---- short-leg-never-into-the-close guard ---------------------------------------

def test_past_close_deadline_pure(sx):
    assert sx.past_close_deadline(datetime(2026, 7, 15, 15, 44, 59)) is False
    assert sx.past_close_deadline(datetime(2026, 7, 15, 15, 45, 0)) is True
    assert sx.past_close_deadline(datetime(2026, 7, 15, 15, 50, 0)) is True


def test_submit_refused_at_or_after_deadline_even_when_armed(sx, monkeypatch):
    _no_broker(monkeypatch, sx)
    res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params=_ARMED,
                           now_et=datetime(2026, 7, 15, 15, 45, 0))
    assert res["_refused"] == "SHORT_LEG_DEADLINE"


def test_submit_allowed_just_before_deadline(sx, monkeypatch):
    calls = _capture_broker(monkeypatch, sx)
    sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53, params=_ARMED,
                     now_et=datetime(2026, 7, 15, 15, 44, 59))
    assert len(calls) == 1


def test_deadline_overridable_via_params(sx, monkeypatch):
    _no_broker(monkeypatch, sx)
    res = sx.submit_spread(_CREDS, _good_legs(sx), 3, 0.53,
                           params={**_ARMED, "spread_close_deadline_et": "12:00"},
                           now_et=_NOON)
    assert res["_refused"] == "SHORT_LEG_DEADLINE"


# ---- close_spread ---------------------------------------------------------------

def _position(sx):
    return {"long_symbol": sx.occ_symbol("C", 625, _EXP),
            "short_symbol": sx.occ_symbol("C", 626, _EXP), "qty": 3}


def test_close_spread_builds_both_to_close_legs(sx, monkeypatch):
    calls = _capture_broker(monkeypatch, sx)
    sx.close_spread(_CREDS, _position(sx), min_credit=0.47)
    order = calls[0]["data"]
    assert order["order_class"] == "mleg" and order["qty"] == "3"
    long_leg, short_leg = order["legs"]
    assert (long_leg["side"], long_leg["position_intent"]) == ("sell", "sell_to_close")
    assert (short_leg["side"], short_leg["position_intent"]) == ("buy", "buy_to_close")


def test_close_spread_limit_is_negative_credit_per_alpaca_convention(sx, monkeypatch):
    calls = _capture_broker(monkeypatch, sx)
    sx.close_spread(_CREDS, _position(sx), min_credit=0.47)
    assert calls[0]["data"]["limit_price"] == "-0.47"


def test_close_spread_never_gated_by_disarm_or_deadline(sx, monkeypatch):
    """An exit must NEVER be blocked by a config flag (OP-25 fail-open): the
    signature takes no params/now_et at all -- prove the POST fires with the
    live repo params disarmed and the wall clock irrelevant."""
    calls = _capture_broker(monkeypatch, sx)
    res = sx.close_spread(_CREDS, _position(sx), min_credit=0.01)
    assert len(calls) == 1 and res.get("id")


def test_close_spread_validates_position(sx, monkeypatch):
    _no_broker(monkeypatch, sx)
    assert "_refused" in sx.close_spread(_CREDS, {"long_symbol": "garbage",
                                                  "short_symbol": "x", "qty": 3},
                                         min_credit=0.4)
    assert "_refused" in sx.close_spread(_CREDS, {**_position(sx), "qty": 0}, min_credit=0.4)
    assert "_refused" in sx.close_spread(_CREDS, _position(sx), min_credit=0)
