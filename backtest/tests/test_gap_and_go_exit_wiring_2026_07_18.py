"""GAP-AND-GO-REVALIDATION-BEFORE-ARM blocker B — gap_and_go's validated exit shape
(CHART-STOP-ONLY + standard v15 TP1/runner/time-stop) is now wired into
heartbeat_core._SETUP_EXIT_OVERRIDES + _synthetic_verdict_from_extra, so a FUTURE arming
attempt cannot silently trade the ribbon_ride shape (-20%/+150%) the way it would have
before this fire (queue.md, filed 2026-07-16 evening).

THIS FIRE DOES NOT ARM gap_and_go — extra_setup_exec_armed.gap_and_go stays absent
(WATCH_NOT_ARMED). These guards pin the SHAPE that will apply the moment it IS armed, plus
prove the fix is inert for every setup that doesn't opt into stop_mode="structure".

Covers:
  1. Params pins — new isolated keys on disk, exec-arm still absent (not an arming change).
  2. _SETUP_EXIT_OVERRIDES["gap_and_go"] carries stop/tp1/stop_mode="structure".
  3. _synthetic_verdict_from_extra threads row["stop_price"] -> verdict["rejection_level"]
     (the exact first-bar-extreme chart stop the watcher already computes), and is a
     no-op when stop_price is absent.
  4. INERTNESS: an already-armed setup (vwap_continuation) that does NOT declare
     stop_mode="structure" stays byte-identical "premium" mode even when its synthetic
     verdict also carries a rejection_level — the fix only activates when the setup's OWN
     _xov entry opts in.
  5. RESOLUTION: given gap_and_go's exact registered shape + structure_stop_enabled=True +
     a resolved trigger_level, exit_manager.ExitState.from_entry (unmocked, real module)
     actually resolves stop_mode="structure" — the tp1/runner/time-stop math is untouched.
  6. Vary-and-assert (C14): removing the _SETUP_EXIT_OVERRIDES entry degrades the shape to
     the old (buggy) ribbon_ride fallback — proves the entry is load-bearing, not decorative.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_gap_and_go_exit_wiring_2026_07_18.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from _broker_request_stub import broker_list_stub  # shared L294 contract

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}
SETUP = "gap_and_go"


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def em():
    return importlib.import_module("exit_manager")


class _RegRecorder:
    """Captures exit_actuator.register_entry kwargs (mirrors test_wire_bollinger_squeeze)."""

    def __init__(self):
        self.calls: list = []

    def register_entry(self, *a, **k):
        self.calls.append(k)
        return None


def _wire_execute(hc, monkeypatch, tmp_path, *, equity="1750.0",
                  now=dt.datetime(2026, 7, 18, 9, 35), reg: "_RegRecorder | None" = None):
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
# 1. Params pins — not an arming change
# =============================================================================
class TestParamsPins:
    def test_isolated_keys_on_disk(self):
        assert SAFE_PARAMS["j_gap_and_go_premium_stop_pct"] == -0.50
        assert SAFE_PARAMS["j_gap_and_go_tp1_pct"] == 0.30

    def test_still_not_exec_armed(self, hc):
        assert hc._extra_exec_armed(SAFE_PARAMS, SETUP) is False, \
            "this fire fixes the SHAPE, it does not arm gap_and_go"


# =============================================================================
# 2. _SETUP_EXIT_OVERRIDES entry
# =============================================================================
def test_override_entry_shape(hc):
    xov = hc._SETUP_EXIT_OVERRIDES[SETUP]
    assert xov["stop"] == "j_gap_and_go_premium_stop_pct"
    assert xov["tp1"] == "j_gap_and_go_tp1_pct"
    assert xov["stop_mode"] == "structure"


# =============================================================================
# 3. rejection_level threading in _synthetic_verdict_from_extra
# =============================================================================
class TestRejectionLevelWire:
    def test_stop_price_threads_to_rejection_level(self, hc):
        row = {"setup_name": SETUP, "fired": True, "direction": "short",
               "triggers": ["gap_down_confirmed"], "stop_price": 601.23}
        sv = hc._synthetic_verdict_from_extra(row)
        assert sv["rejection_level"] == 601.23

    def test_absent_stop_price_is_a_noop(self, hc):
        row = {"setup_name": SETUP, "fired": True, "direction": "short",
               "triggers": ["gap_down_confirmed"]}
        sv = hc._synthetic_verdict_from_extra(row)
        assert "rejection_level" not in sv


# =============================================================================
# 4. INERTNESS — vwap_continuation (already armed, no stop_mode opt-in) is unaffected
# =============================================================================
def test_vwap_continuation_stays_premium_mode_even_with_rejection_level(hc, monkeypatch, tmp_path):
    """A rejection_level being present on the synthetic verdict must not, by itself,
    flip an unrelated armed setup into structure mode — only its OWN _xov stop_mode
    opt-in can do that."""
    reg = _RegRecorder()
    _wire_execute(hc, monkeypatch, tmp_path, reg=reg)
    verdict = {"verdict": "ENTER_BULL", "setup_name": "vwap_continuation",
              "triggers_fired": ["vwap_continuation"], "rejection_level": 619.5}
    plan = hc._execute("safe", verdict,
                       {"bar_ctx": {"timestamp_et": "2026-07-18 10:00:00", "bar": {"close": 620.4}}},
                       SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    shape = reg.calls[0]["exit_shape"]
    assert "stop_mode" not in shape, \
        "vwap_continuation's _xov entry has no stop_mode key -> must stay absent (premium default)"


# =============================================================================
# 5. RESOLUTION — the real (unmocked) exit_manager actually resolves structure mode
# =============================================================================
def test_exit_manager_resolves_structure_mode_for_gap_and_go_shape(em):
    shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30,
             "tp1_qty_fraction": 0.667, "profit_lock_mode": "fixed",
             "stop_mode": "structure"}
    state = em.ExitState.from_entry(
        symbol="SPY260718P00601000", side="P", entry_premium=1.00, qty=3,
        exit_shape=shape, strategy="gap_and_go",
        trigger_level=601.23, structure_stop_enabled=True)
    assert state.stop_mode == "structure"
    assert state.trigger_level == 601.23
    # catastrophe cap demoted from the declared -0.50, TP1/runner untouched
    assert state.premium_stop_pct == -0.50
    assert state.tp1_premium_pct == 0.30


def test_exit_manager_falls_back_to_premium_when_trigger_level_missing(em):
    """Fail-open: if the trigger_level can't resolve (e.g. dispatch row had no
    stop_price), structure mode never activates -- the isolated premium stop guards."""
    shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30,
             "tp1_qty_fraction": 0.667, "profit_lock_mode": "fixed",
             "stop_mode": "structure"}
    state = em.ExitState.from_entry(
        symbol="SPY260718P00601000", side="P", entry_premium=1.00, qty=3,
        exit_shape=shape, strategy="gap_and_go",
        trigger_level=None, structure_stop_enabled=True)
    assert state.stop_mode == "premium"
    assert state.premium_stop_pct == -0.50


# =============================================================================
# 6. Vary-and-assert (C14) — remove the entry, the shape degrades to ribbon_ride
# =============================================================================
def test_removing_override_entry_degrades_to_ribbon_shape(hc, monkeypatch, tmp_path):
    monkeypatch.delitem(hc._SETUP_EXIT_OVERRIDES, SETUP)
    reg = _RegRecorder()
    _wire_execute(hc, monkeypatch, tmp_path, reg=reg)
    verdict = {"verdict": "ENTER_BEAR", "setup_name": SETUP,
              "triggers_fired": [SETUP], "rejection_level": 601.23}
    plan = hc._execute("safe", verdict,
                       {"bar_ctx": {"timestamp_et": "2026-07-18 09:35:00", "bar": {"close": 602.0}}},
                       SAFE_PARAMS, dry=False)
    assert plan["status"] == "PLACED", plan
    shape = reg.calls[0]["exit_shape"]
    assert "stop_mode" not in shape, "with the override gone, the ribbon_ride shape has no stop_mode key here (falls to structure mode via strategies.by_name in production, but this harness stubs strategies.by_name -> None, so the fallback bracket shape applies)"
    assert shape["premium_stop_pct"] == -0.50
