"""G4 guard — extra-setup execution routing in heartbeat_core.

Pins the SAFETY CONTRACT of the G4 wiring (route fired validated-detector signals to the
live _execute path):

  1. DEFAULT-OFF: with no `extra_setup_exec_armed` key (or a non-dict / non-True value),
     a fired extra-setup row NEVER reaches _execute — it logs WATCH_NOT_ARMED. This is the
     byte-identical no-op that makes the wiring safe to ship disarmed.
  2. ENABLE != ARM (the crux): the detector-enable flags (j_vwap_cont_enabled / gap_and_go_
     enabled) are ALREADY true in params, but routing to a live order requires the SEPARATE
     extra_setup_exec_armed[setup]=True. A detector being enabled (WATCH) must not place.
  3. CORRECT MAPPING: long->ENTER_BULL, short->ENTER_BEAR; neutral / not-fired / malformed
     -> no trade (fail-closed).
  4. ARMED path routes through _execute with the mapped synthetic verdict + the free-model
     veto, and a veto blocks placement.
  5. FAIL-OPEN: an exception inside the route never propagates out of the tick.

These are graduated guards (OP-25): the "validated in sim, never placed live" + dead-knob
classes (L47/L70/C11/C14) become impossible to reintroduce silently — a future edit that
makes the exec-arm default ON, or gates execution on the detector-enable flag, REDs here.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def hc():
    """Import heartbeat_core fresh (it lives in setup/scripts)."""
    mod = importlib.import_module("heartbeat_core")
    return mod


# --------------------------------------------------------------------------- #
# 1. DEFAULT-OFF
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("params", [
    {},                                            # key absent entirely
    {"extra_setup_exec_armed": {}},                # present but empty
    {"extra_setup_exec_armed": None},              # wrong type
    {"extra_setup_exec_armed": ["vwap_continuation"]},  # list, not dict
    {"extra_setup_exec_armed": {"vwap_continuation": False}},   # explicit False
    {"extra_setup_exec_armed": {"vwap_continuation": 1}},       # truthy-but-not-True
    {"extra_setup_exec_armed": {"vwap_continuation": "true"}},  # string, not bool True
])
def test_exec_arm_defaults_off(hc, params):
    assert hc._extra_exec_armed(params, "vwap_continuation") is False


def test_exec_arm_requires_exact_true(hc):
    assert hc._extra_exec_armed({"extra_setup_exec_armed": {"vwap_continuation": True}},
                                "vwap_continuation") is True
    # a different setup stays off
    assert hc._extra_exec_armed({"extra_setup_exec_armed": {"vwap_continuation": True}},
                                "gap_and_go") is False


def test_exec_arm_none_setup(hc):
    assert hc._extra_exec_armed({"extra_setup_exec_armed": {"x": True}}, None) is False


# --------------------------------------------------------------------------- #
# 2/5. ENABLE != ARM, and detector-enabled params do NOT place
# --------------------------------------------------------------------------- #
def test_detector_enabled_but_not_exec_armed_is_watch_only(hc, monkeypatch):
    """The real-world shipped state: detectors enabled (WATCH), exec-arm absent."""
    called = {"n": 0}
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    params = {"j_vwap_cont_enabled": True, "gap_and_go_enabled": True}  # enabled, NOT exec-armed
    extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "long",
              "triggers": ["vwap_reclaim"]}]
    out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, params)
    assert called["n"] == 0, "_execute must NOT be called when only enabled, not exec-armed"
    assert out == [{"setup": "vwap_continuation", "action": "WATCH_NOT_ARMED"}]


# --------------------------------------------------------------------------- #
# 3. MAPPING
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("direction,expected", [
    ("long", "ENTER_BULL"),
    ("short", "ENTER_BEAR"),
    ("LONG", "ENTER_BULL"),
    ("Short", "ENTER_BEAR"),
])
def test_synthetic_verdict_mapping(hc, direction, expected):
    row = {"setup_name": "vwap_continuation", "fired": True, "direction": direction,
           "triggers": ["t1", "t2"]}
    sv = hc._synthetic_verdict_from_extra(row)
    assert sv["verdict"] == expected
    assert sv["setup_name"] == "vwap_continuation"
    assert sv["triggers_fired"] == ["t1", "t2"]


@pytest.mark.parametrize("row", [
    {"setup_name": "x", "fired": False, "direction": "long"},   # not fired
    {"setup_name": "x", "fired": True, "direction": "neutral"}, # neutral -> no trade
    {"setup_name": "x", "fired": True, "direction": "sideways"},# unknown -> no trade
    {"setup_name": "x", "fired": True},                          # no direction
    {"error": "dispatch_crashed: boom"},                        # error row
    "not-a-dict",                                                # malformed
])
def test_synthetic_verdict_fail_closed(hc, row):
    assert hc._synthetic_verdict_from_extra(row) is None


# --------------------------------------------------------------------------- #
# 4. ARMED path routes through _execute + honors the veto
# --------------------------------------------------------------------------- #
def test_armed_routes_through_execute_with_mapped_verdict(hc, monkeypatch):
    captured = {}

    def fake_execute(account, verdict, payload, params, *, dry):
        captured["account"] = account
        captured["verdict"] = verdict
        captured["dry"] = dry
        return {"status": "WOULD_PLACE", "symbol": "SPY..P"}

    monkeypatch.setattr(hc, "_execute", fake_execute)
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)

    params = {"extra_setup_exec_armed": {"vwap_continuation": True}}
    extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "short",
              "triggers": ["vwap_loss"]}]
    out = hc._route_extra_setups("bold", extra, {"bar_ctx": {}}, params)

    assert captured["account"] == "bold"
    assert captured["verdict"]["verdict"] == "ENTER_BEAR"
    assert captured["verdict"]["setup_name"] == "vwap_continuation"
    assert out[0]["setup"] == "vwap_continuation"
    assert out[0]["action"] == "WOULD_PLACE"


def test_armed_but_vetoed_does_not_place(hc, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {"status": "X"})
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": True, "reason": "model said no"})
    params = {"extra_setup_exec_armed": {"vwap_continuation": True}}
    extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "long", "triggers": []}]
    out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, params)
    assert called["n"] == 0
    assert out[0]["action"] == "VETOED_BY_MODELS"


# --------------------------------------------------------------------------- #
# 5. FAIL-OPEN
# --------------------------------------------------------------------------- #
def test_route_never_raises(hc, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("broker exploded")
    monkeypatch.setattr(hc, "_execute", boom)
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    params = {"extra_setup_exec_armed": {"vwap_continuation": True}}
    extra = [{"setup_name": "vwap_continuation", "fired": True, "direction": "long", "triggers": []}]
    out = hc._route_extra_setups("safe", extra, {"bar_ctx": {}}, params)  # must not raise
    assert out[0]["action"] == "EXTRA_EXEC_ERROR"
    assert "broker exploded" in out[0]["err"]


def test_empty_extra_is_noop(hc):
    assert hc._route_extra_setups("safe", [], {}, {}) == []
    assert hc._route_extra_setups("safe", None, {}, {}) == []
