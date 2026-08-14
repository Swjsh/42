"""VISIBILITY (2026-07-09, OP-33c): heartbeat_core._execute's plan-log "stop" field must
show the TRUTH a position is actually managed under -- the known cosmetic bug (STATUS.md
2026-07-09 ~16:20 ET STOP-B ship-1 entry: "plan-log 'stop' shows the -20% fallback even in
structure mode"). Mirrors test_trade_to_learn_2026_07_01.py's _wire_execute harness.

Proves:
  * structure mode resolved (flag ON + a real trigger_level) -> plan["stop"]/
    plan["premium_stop_pct"] are corrected to the REAL catastrophe floor, and
    plan["stop_display"] renders 'STRUCTURE@<level> (cat -50%)'.
  * every existing isolated-setup pin (vwap_continuation etc., test_trade_to_learn_
    2026_07_01.py / test_money_path_2026_07_01.py) is untouched -- those setups never
    declare stop_mode="structure", so this build is a no-op for them (verified separately
    by re-running those suites unmodified).
  * render-only: the ONE broker POST (the actual order) never carries a stop/tp key.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from _broker_request_stub import broker_list_stub, order_posts  # shared L294 contract

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
SAFE_PARAMS = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


class _RealResolutionEa:
    """A register_entry fake that resolves a REAL ExitState via the frozen, unmocked
    exit_manager.ExitState.from_entry -- proves the plan-log reads a genuine resolution,
    not a stub -- while never touching disk (no FLEET_DIR redirect needed). Also exposes
    the REAL exit_actuator.describe_stop (captured before sys.modules is monkeypatched) so
    _execute's `_ea.describe_stop(...)` call -- `_ea` resolves to THIS fake once wired --
    still renders through the genuine, unmodified formatter."""

    def __init__(self):
        self.calls: list = []
        import exit_manager as em  # automation/state/fleet -- pure core, frozen, unmocked
        import exit_actuator as real_ea  # the REAL module, captured before any monkeypatch
        self._em = em
        self._describe_stop = real_ea.describe_stop

    def register_entry(self, arm_id, **kw):
        self.calls.append(kw)
        return self._em.ExitState.from_entry(
            symbol=kw["symbol"], side=kw["side"], entry_premium=kw["entry_premium"],
            qty=kw["qty"], exit_shape=kw["exit_shape"], strategy=kw.get("strategy", ""),
            trigger_level=kw.get("trigger_level"),
            structure_stop_enabled=kw.get("structure_stop_enabled", False))

    def load_states(self, arm):
        return {}

    def describe_stop(self, *a, **k):
        return self._describe_stop(*a, **k)


def _wire_execute(hc, monkeypatch, tmp_path, *, params, ea_fake,
                  now=dt.datetime(2026, 7, 9, 11, 0), strategies_mod=None):
    import fleet_broker as fb
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})

        _lst = broker_list_stub(endpoint, method)

        if _lst is not None:

            return _lst  # collection endpoints must be LIST-shaped
        return {"id": "ord-1", "status": "accepted"}

    monkeypatch.setattr(fb, "_request", fake_request)
    monkeypatch.setattr(fb, "load_creds", lambda: {"safe-2": _CREDS, "bold-2": _CREDS})
    monkeypatch.setattr(fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fb, "get_option_mid", lambda c, s: 1.00)
    monkeypatch.setattr(fb, "marketable_limit_price",
                        lambda c, s, side="buy", buffer=0.03: 1.08)
    monkeypatch.setattr(fb, "open_buy_orders", lambda c, s: [])
    monkeypatch.setattr(fb, "cancel_order", lambda *a, **k: {})
    monkeypatch.setattr(hc, "STATE", tmp_path)
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
    monkeypatch.setitem(sys.modules, "exit_actuator", ea_fake)
    if strategies_mod is not None:
        monkeypatch.setitem(sys.modules, "strategies", strategies_mod)

    class _Resp:
        def read(self):
            return json.dumps({"equity": params.get("_test_equity", "2000.0")}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return posts


def test_structure_mode_corrects_plan_stop_and_renders_display(hc, monkeypatch, tmp_path):
    """Generic ribbon setup, REAL production strategies.py (declares ribbon_ride's
    stop_mode="structure"), flag ON, verdict carries the EXACT trigger level -> structure
    mode resolves; plan["stop"]/plan["premium_stop_pct"] are corrected off the resolved
    ExitState (NOT the -50% flag-off fallback text), stop_display renders the chart-level
    truth, and the ONE order POST is untouched (render-only)."""
    import strategies as real_strat  # automation/state/fleet -- production module
    rr = real_strat.by_name("ribbon_ride")
    assert rr is not None and rr.exit.stop_mode == "structure", \
        "precondition: production ribbon_ride must declare stop_mode=structure"

    ea_fake = _RealResolutionEa()
    params = dict(SAFE_PARAMS)
    params["structure_stop_enabled"] = True
    posts = _wire_execute(hc, monkeypatch, tmp_path, params=params, ea_fake=ea_fake,
                          strategies_mod=real_strat)
    verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
               "triggers_fired": ["level_rejection"], "rejection_level": 620.9}
    payload = {"bar_ctx": {"timestamp_et": "2026-07-09 10:55:00", "bar": {"close": 620.4}}}

    plan = hc._execute("safe", verdict, payload, params, dry=False)

    assert plan["status"] == "PLACED", plan
    assert len(ea_fake.calls) == 1
    assert ea_fake.calls[0]["trigger_level"] == 620.9
    assert ea_fake.calls[0]["structure_stop_enabled"] is True

    assert plan["stop_mode"] == "structure"
    assert plan["trigger_level"] == 620.9
    assert plan["stop_display"] == "STRUCTURE@620.90 (cat -50%)"
    assert plan["premium_stop_pct"] == -0.50
    # the CORRECTED number: entry_px-anchored (1.08, the real marketable-limit fill price),
    # not the pre-resolution mid-anchored estimate (1.00 * (1-0.50) = 0.50) -- both are -50%
    # of a DIFFERENT base price, so the dollar figure itself changes even though the pct
    # doesn't. This is the actual bug fix (a truer number), not merely a new field.
    assert plan["stop"] == round(1.08 * (1 - 0.50), 2) == 0.54
    assert plan["stop"] != round(1.00 * (1 - 0.50), 2), \
        "must not still show the mid-anchored pre-resolution estimate"

    # RENDER-ONLY: the one broker POST is untouched -- no stop/tp key ever reaches the order
    assert len(order_posts(posts)) == 1
    data = order_posts(posts)[0]["data"]
    assert "stop" not in data and "stop_loss" not in data and "order_class" not in data


def test_structure_mode_flag_off_stays_premium_no_op(hc, monkeypatch, tmp_path):
    """structure_stop_enabled explicitly False -> byte-identical to today: plan["stop"]
    stays the flag-off fallback (-50% for a generic ribbon setup, per _stop_pct's existing
    else-branch), stop_mode reports 'premium'."""
    import strategies as real_strat
    ea_fake = _RealResolutionEa()
    params = dict(SAFE_PARAMS)
    params["structure_stop_enabled"] = False
    _wire_execute(hc, monkeypatch, tmp_path, params=params, ea_fake=ea_fake,
                 strategies_mod=real_strat)
    verdict = {"verdict": "ENTER_BEAR", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
               "triggers_fired": ["level_rejection"], "rejection_level": 620.9}
    payload = {"bar_ctx": {"timestamp_et": "2026-07-09 10:55:00", "bar": {"close": 620.4}}}

    plan = hc._execute("safe", verdict, payload, params, dry=False)

    assert plan["status"] == "PLACED", plan
    assert plan["stop_mode"] == "premium"
    assert plan["stop"] == round(1.00 * (1 - 0.50), 2)   # unchanged flag-off fallback
    assert plan["stop_display"] == "0.50 (-50%)"


def test_isolated_setup_unaffected_by_structure_flag(hc, monkeypatch, tmp_path):
    """An _SETUP_EXIT_OVERRIDES isolated setup (vwap_continuation) never declares
    stop_mode="structure" -- this build is a complete no-op for it, flag on or off
    (mirrors test_trade_to_learn_2026_07_01.py::test_vwap_continuation_trades_validated_
    isolated_cell's res["stop"]==0.94 pin, now also checking the new fields)."""
    ea_fake = _RealResolutionEa()
    params = dict(SAFE_PARAMS)
    params["structure_stop_enabled"] = True   # flag ON -- must still be a no-op
    _wire_execute(hc, monkeypatch, tmp_path, params=params, ea_fake=ea_fake,
                 strategies_mod=types.SimpleNamespace(by_name=lambda n: None))
    verdict = {"verdict": "ENTER_BEAR", "setup_name": "vwap_continuation",
               "triggers_fired": ["vwap_continuation"]}
    payload = {"bar_ctx": {"timestamp_et": "2026-07-09 10:55:00", "bar": {"close": 620.4}}}

    plan = hc._execute("safe", verdict, payload, params, dry=False)

    assert plan["status"] == "PLACED", plan
    assert plan["stop"] == 0.94  # mid 1.00 * (1 - 0.06), the ratified isolated stop, unchanged
    assert plan["stop_mode"] == "premium"
    assert plan["stop_display"] == "0.94 (-6%)"
