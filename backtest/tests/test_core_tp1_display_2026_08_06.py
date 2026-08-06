"""D4 guard -- CORE-TP1-DISPLAY-DIVERGENCE (2026-08-06).

THE DEFECT: heartbeat_core._execute computed the journaled `tp` from params.json's
tp1_premium_pct (~L2052), but the exit engine registration below (~L2224-2230) arms the
STRATEGY REGISTRY's ExitShape for non-isolated setups (ribbon_ride: tp1_premium_pct=1.0 vs
params' 0.5) -- and the post-registration back-correction (~L2250-2257) fixed the stop
fields but never `tp`. Every journaled core entry therefore promised a TP1 the exit engine
would never take (0.5x logged, 1.0x armed).

THE FIX (render-only, same class as the existing stop back-correction): after
register_entry, `plan["tp"]` and `plan["tp1_premium_pct"]` are recomputed from the
ExitState that was ACTUALLY registered (entry_premium * (1 + state.tp1_premium_pct)).

Harness mirrors test_money_path_2026_07_01._wire_execute (full real _execute, fake broker
REST), with exit_actuator stubbed to return a REAL exit_manager.ExitState built from a
registry-style shape -- so the assertion runs the genuine back-correction branch.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_core_tp1_display_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "backtest"), str(ROOT), str(ROOT / "setup" / "scripts"),
           str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}

# The registry-vs-params divergence this guard pins: a shape whose tp1_premium_pct (1.0)
# differs from params.json's (0.5 today; assert inequality below, never assume).
REGISTRY_STYLE_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.0,
                        "tp1_qty_fraction": 0.8, "profit_lock_mode": "trailing"}


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


def _wire(hc, monkeypatch, tmp_path, *, now=dt.datetime(2026, 8, 6, 11, 0)):
    """test_money_path_2026_07_01._wire_execute pattern, except exit_actuator returns a REAL
    ExitState (so the D4 back-correction branch actually executes)."""
    import fleet_broker as fb
    import exit_manager as em

    monkeypatch.setattr(fb, "_request",
                        lambda creds, endpoint, method="GET", data=None, timeout=15:
                        {"id": "ord-1", "status": "accepted"})
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "get_option_mid", lambda c, s: 1.00)
    monkeypatch.setattr(fb, "marketable_limit_price", lambda c, s, side="buy", buffer=0.03: 1.08)
    monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
    monkeypatch.setattr(fb, "open_buy_orders_checked", lambda c, s: ([], True))
    monkeypatch.setattr(fb, "symbol_position_qty_checked", lambda c, s: (0, True))
    monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
    monkeypatch.setattr(hc, "STATE", tmp_path)
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
    monkeypatch.setattr(hc, "_capture_greeks", lambda *a, **k: {})

    registered = {}

    def fake_register_entry(arm_id, *, symbol, side, entry_premium, qty, exit_shape,
                            strategy="", trigger_level=None, structure_stop_enabled=False):
        st = em.ExitState.from_entry(symbol=symbol, side=side, entry_premium=entry_premium,
                                     qty=qty, exit_shape=exit_shape, strategy=strategy,
                                     trigger_level=trigger_level,
                                     structure_stop_enabled=structure_stop_enabled)
        registered["state"] = st
        registered["shape"] = exit_shape
        return st

    monkeypatch.setitem(sys.modules, "exit_actuator", types.SimpleNamespace(
        register_entry=fake_register_entry,
        describe_stop=lambda *a, **k: "stub"))
    monkeypatch.setitem(sys.modules, "strategies", types.SimpleNamespace(
        by_name=lambda n: types.SimpleNamespace(
            exit=types.SimpleNamespace(to_dict=lambda: dict(REGISTRY_STYLE_SHAPE)))))

    class _Resp:
        def read(self):
            return json.dumps({"equity": "2000.0"}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return registered


def _enter_bear_plan(hc, monkeypatch, tmp_path):
    registered = _wire(hc, monkeypatch, tmp_path)
    verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
               "triggers_fired": ["level_rejection"]}
    payload = {"bar_ctx": {"timestamp_et": "2026-08-06 10:55:00", "bar": {"close": 768.0},
                            "levels_active": [768.5]}}
    plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=False)
    return plan, registered


def test_precondition_registry_tp1_differs_from_params():
    """Non-vacuity: the divergence this guard exists for must actually exist between the
    fixture shape and live params. If params ever move to 1.0 this test flags that the
    fixture needs a new divergent value rather than letting the suite go vacuous."""
    assert float(SAFE_PARAMS.get("tp1_premium_pct", 0.30)) != REGISTRY_STYLE_SHAPE["tp1_premium_pct"]


def test_journaled_tp_matches_the_armed_shape_not_params(hc, monkeypatch, tmp_path):
    """THE D4 PIN: plan['tp'] must equal entry_premium * (1 + ARMED tp1_premium_pct)."""
    plan, registered = _enter_bear_plan(hc, monkeypatch, tmp_path)
    assert plan["status"] == "PLACED", plan
    st = registered["state"]
    assert st.tp1_premium_pct == REGISTRY_STYLE_SHAPE["tp1_premium_pct"]  # armed 1.0
    armed_tp = round(st.entry_premium * (1.0 + st.tp1_premium_pct), 2)   # 1.08 * 2.0 = 2.16
    assert plan["tp"] == armed_tp, (
        f"journaled tp {plan['tp']} != armed TP1 level {armed_tp} -- the D4 display "
        "divergence is back (tp computed from params, shape armed from the registry)")
    assert plan["tp1_premium_pct"] == st.tp1_premium_pct


def test_journaled_tp_does_not_carry_the_params_value(hc, monkeypatch, tmp_path):
    """Other direction (non-vacuous): the OLD wrong value (mid * (1+params tp1)) must be
    absent whenever it differs from the armed value."""
    plan, registered = _enter_bear_plan(hc, monkeypatch, tmp_path)
    params_tp1 = float(SAFE_PARAMS.get("tp1_premium_pct", 0.30))
    old_wrong_tp = round(1.00 * (1.0 + params_tp1), 2)  # mid-based params render
    st = registered["state"]
    armed_tp = round(st.entry_premium * (1.0 + st.tp1_premium_pct), 2)
    assert old_wrong_tp != armed_tp  # fixture sanity: the two renders genuinely differ
    assert plan["tp"] != old_wrong_tp


def test_exit_unmanaged_keeps_legacy_tp_render(hc, monkeypatch, tmp_path):
    """When no exit registration happens (dry preview), the pre-existing mid-based render
    stays byte-identical -- the fix is scoped to the registered-entry branch only."""
    _wire(hc, monkeypatch, tmp_path)
    verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
               "triggers_fired": ["level_rejection"]}
    payload = {"bar_ctx": {"timestamp_et": "2026-08-06 10:55:00", "bar": {"close": 768.0}}}
    plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=True)
    params_tp1 = float(SAFE_PARAMS.get("tp1_premium_pct", 0.30))
    assert plan["tp"] == round(1.00 * (1.0 + params_tp1), 2)
