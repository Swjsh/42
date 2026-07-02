"""WIRE-BOLLINGER guards (2026-07-02) — bollinger_squeeze wired at its VALIDATED cell.

Proposal: wire-2026-07-02-bollinger-squeeze (automation/state/conductor-proposals.jsonl).
Evidence: family-grind survivor (dir-null SURVIVES), fresh re-verify 2026-07-02 PASS —
analysis/recommendations/bollinger-squeeze-fresh-reverify.json (n=312, exp +$35.3/tr,
OOS +$44.0/tr, WF 1.443, stock-null + dir-null PASS).

Validated cell (ATM|stop-8): strike ATM (offset 0), isolated stop -0.08 / tp1 +0.30 /
tp1_qty_fraction 0.667 / chandelier trailing profit-lock 15%. SAFE PAPER ONLY.

Vary-and-assert (C14/L149): the _SETUP_EXIT_OVERRIDES entry and the new _xov
tq/plmode/trail extension are LOAD-BEARING — remove the entry and the registered
exit shape must fall back to the global (0.8 / "fixed") UNVALIDATED shape, which
these guards then catch RED.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_wire_bollinger_squeeze.py
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
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads((ROOT / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}
SETUP = "bollinger_squeeze"

VALIDATED_SHAPE = {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.30,
                   "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing",
                   "trail_pct": 0.15}


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


class _RegRecorder:
    """Captures exit_actuator.register_entry kwargs (the shape the exit_manager runs)."""

    def __init__(self):
        self.calls: list = []

    def register_entry(self, *a, **k):
        self.calls.append(k)
        return None


def _wire_execute(hc, monkeypatch, tmp_path, *, equity="25000.0",
                  now=dt.datetime(2026, 7, 2, 11, 0), reg: "_RegRecorder | None" = None):
    """_execute harness (mirrors test_trade_to_learn_2026_07_01._wire_execute)."""
    import fleet_broker as fb
    posts: list = []

    def fake_request(creds, endpoint, method="GET", data=None, timeout=15):
        posts.append({"endpoint": endpoint, "method": method, "data": data})
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
    # (_quality_lock_check monkeypatch removed -- lock DELETED 2026-07-02 per J directive)
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", True)
    monkeypatch.setitem(sys.modules, "exit_actuator",
                        reg if reg is not None
                        else types.SimpleNamespace(register_entry=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "strategies",
                        types.SimpleNamespace(by_name=lambda n: None))

    class _Resp:
        def read(self):
            return json.dumps({"equity": equity}).encode("utf-8")

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=10: _Resp())
    return posts


# =============================================================================
# Params pins — SAFE armed at the validated cell; Bold NOT armed
# =============================================================================
class TestParamsArming:
    def test_safe_enabled_and_armed(self, hc):
        assert SAFE_PARAMS["bollinger_squeeze_enabled"] is True
        assert SAFE_PARAMS["extra_setup_exec_armed"].get(SETUP) is True
        assert hc._extra_exec_armed(SAFE_PARAMS, SETUP) is True

    def test_bold_not_armed(self, hc):
        assert hc._extra_exec_armed(BOLD_PARAMS, SETUP) is False, \
            "SAFE PAPER ONLY — Bold/aggressive must NOT arm bollinger_squeeze"

    def test_validated_cell_keys_on_disk(self):
        assert SAFE_PARAMS["j_bollinger_squeeze_strike_override_enabled"] is True
        assert SAFE_PARAMS["j_bollinger_squeeze_strike_offset_safe"] == 0
        assert SAFE_PARAMS["j_bollinger_squeeze_premium_stop_pct"] == -0.08
        assert SAFE_PARAMS["j_bollinger_squeeze_tp1_pct"] == 0.30
        assert SAFE_PARAMS["j_bollinger_squeeze_tp1_qty_fraction"] == 0.667
        assert SAFE_PARAMS["j_bollinger_squeeze_profit_lock_mode"] == "trailing"
        assert SAFE_PARAMS["j_bollinger_squeeze_profit_lock_trail_pct"] == 0.15


# =============================================================================
# (a) Dispatcher wiring — the tuple is live, flag-gated, and reaches the method
# =============================================================================
class TestDispatcherWiring:
    def test_enabled_flag_reaches_dispatch_method(self):
        import setup_dispatch as sd
        d = sd.SetupDispatcher({"bollinger_squeeze_enabled": True}, {})
        results = d.run()
        names = [r.setup_name for r in results]
        assert SETUP in names, "dispatchers list must contain the bollinger_squeeze entry"
        row = results[names.index(SETUP)]
        assert row.fired is False
        assert str(row.skip_reason).startswith("SKIP_NO_FEED"), \
            "empty payload must route through _dispatch_bollinger_squeeze's feed guard"

    def test_flag_off_is_a_true_noop(self):
        import setup_dispatch as sd
        d = sd.SetupDispatcher({"bollinger_squeeze_enabled": False}, {})
        assert SETUP not in [r.setup_name for r in d.run()]

    def test_watcher_reexported(self):
        from backtest.lib.watchers import detect_bollinger_squeeze_setup  # noqa: F401


# =============================================================================
# (b)+(d) _execute — validated stop/TP1 pcts + ATM strike, both directions
# =============================================================================
class TestExecuteValidatedCell:
    @pytest.mark.parametrize("verdict_name,generic_strike", [
        ("ENTER_BULL", 618),   # call: generic Safe ITM-2 at $25K would be 618
        ("ENTER_BEAR", 622),   # put:  generic Safe ITM-2 at $25K would be 622
    ])
    def test_stop_tp_and_atm_strike(self, hc, monkeypatch, tmp_path, verdict_name,
                                    generic_strike):
        _wire_execute(hc, monkeypatch, tmp_path)
        verdict = {"verdict": verdict_name, "setup_name": SETUP, "triggers_fired": [SETUP]}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-02 10:55:00", "bar": {"close": 620.4}}}
        plan = hc._execute("safe", verdict, payload, SAFE_PARAMS, dry=True)
        assert plan["status"] == "WOULD_PLACE", plan
        # (b) validated pcts on mid=1.00 — NOT the -0.50 global catastrophe shape
        assert plan["stop"] == round(1.00 * (1 - 0.08), 2) == 0.92
        assert plan["tp"] == round(1.00 * (1 + 0.30), 2) == 1.30
        # (d) ATM offset 0 on Safe
        assert plan["strike"] == 620, "validated cell is ATM (offset 0)"
        # flag OFF -> generic tier (strike knob is LIVE, C14)
        off = dict(SAFE_PARAMS)
        off["j_bollinger_squeeze_strike_override_enabled"] = False
        plan_off = hc._execute("safe", verdict, payload, off, dry=True)
        assert plan_off["strike"] == generic_strike


# =============================================================================
# (c) Registered exit shape — the exact validated cell incl. tq/plmode/trail
# =============================================================================
class TestRegisteredExitShape:
    def _place(self, hc, monkeypatch, tmp_path, params):
        reg = _RegRecorder()
        _wire_execute(hc, monkeypatch, tmp_path, reg=reg)
        verdict = {"verdict": "ENTER_BULL", "setup_name": SETUP, "triggers_fired": [SETUP]}
        plan = hc._execute("safe", verdict, {"bar_ctx": {"timestamp_et": "2026-07-02 10:55:00", "bar": {"close": 620.4}}},
                           params, dry=False)
        assert plan["status"] == "PLACED", plan
        assert len(reg.calls) == 1, "register_entry must fire exactly once on PLACED"
        return reg.calls[0]

    def test_exit_shape_is_the_validated_cell(self, hc, monkeypatch, tmp_path):
        call = self._place(hc, monkeypatch, tmp_path, SAFE_PARAMS)
        assert call["exit_shape"] == VALIDATED_SHAPE
        assert call["strategy"] == SETUP

    # (e) non-vacuity: remove the override entry -> the shape DEGRADES to the
    # global (tq 0.8 on Safe / plmode "fixed" / stop -0.50) and the pin above
    # would go RED. Proves every new key is load-bearing (C14 vary-and-assert).
    def test_removing_override_entry_degrades_shape(self, hc, monkeypatch, tmp_path):
        monkeypatch.delitem(hc._SETUP_EXIT_OVERRIDES, SETUP)
        call = self._place(hc, monkeypatch, tmp_path, SAFE_PARAMS)
        shape = call["exit_shape"]
        assert shape != VALIDATED_SHAPE
        assert shape["profit_lock_mode"] == "fixed"
        assert shape["tp1_qty_fraction"] == float(SAFE_PARAMS.get("tp1_qty_fraction", 0.667))
        assert "trail_pct" not in shape
        assert shape["premium_stop_pct"] == -0.50

    def test_tq_plmode_trail_keys_are_live(self, hc, monkeypatch, tmp_path):
        """Vary the three new params keys -> the registered shape must follow."""
        varied = dict(SAFE_PARAMS)
        varied["j_bollinger_squeeze_tp1_qty_fraction"] = 0.5
        varied["j_bollinger_squeeze_profit_lock_mode"] = "fixed"
        varied["j_bollinger_squeeze_profit_lock_trail_pct"] = 0.25
        call = self._place(hc, monkeypatch, tmp_path, varied)
        shape = call["exit_shape"]
        assert shape["tp1_qty_fraction"] == 0.5
        assert shape["profit_lock_mode"] == "fixed"
        assert shape["trail_pct"] == 0.25
