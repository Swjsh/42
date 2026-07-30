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


# --------------------------------------------------------------------------- #
# 6. structure_veto blocks the extra-setup route too (FIX 2026-07-06)
# --------------------------------------------------------------------------- #
# Regression: 2026-07-06 live session had 7 extra-setup (bollinger_squeeze) fires
# route to _execute while the PRIMARY verdict was SKIP_STRUCTURE_VETO or HOLD,
# including one that bought the EXACT direction structure_veto had just blocked on
# the same tick (structure_veto exists specifically to prevent this class of loss --
# built after the 2026-06-26 -$237 wrong-way entry). Net -$33 on that cluster.
# structure_veto's premise ("this tick's structure makes a directional entry
# dangerous") must block every execution path on the account, not just the primary
# ribbon path.
def _payload_stub():
    # RETARGETED 2026-07-30 (BLINDNESS BLOCK / SKIP_NO_LEVELS): `levels_active` added.
    # This stub previously omitted the key entirely, which the new blind-entry rail reads
    # (fail-closed) as "the engine cannot see" -- so test_non_veto_hold_still_routes_extra_
    # setup below correctly went RED: on a blind tick the G4 extra-setup route is now
    # suppressed too (setup_dispatch.py:344 builds those detectors' BarContext from this
    # SAME levels_active list, so they are blind in the literal sense as well).
    # The guard was RIGHT to fire; the FIXTURE was wrong. These tests are about G4 ROUTING
    # semantics on a normal sighted tick, and production is always sighted here --
    # heartbeat_core._build_payload writes `"levels_active": active` unconditionally, so a
    # payload with no such key never occurs live. Modelling a populated level set makes the
    # fixture faithful to production and keeps these tests testing what they were written to
    # test. Blind-tick G4 behavior has its own dedicated coverage:
    # test_blind_no_levels_2026_07_30.py::test_blind_also_blocks_the_extra_setup_side_channel.
    return {"bar_ctx": {"bar": {"close": 751.0},
                        "ribbon_now": {"stack": "BULL", "spread_cents": 10},
                        "htf_15m_stack": "BULL", "vix_now": 16.0,
                        "levels_active": [749.5, 751.2]}}


def test_structure_veto_blocks_extra_setup_route(hc, monkeypatch):
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: object())
    monkeypatch.setattr(hc, "_build_payload", lambda df, params: _payload_stub())
    monkeypatch.setattr(hc, "_engine_verdict", lambda payload: {
        "verdict": "SKIP_STRUCTURE_VETO",
        "reason": "structure-veto: C entry blocked -- price structure is 'downtrend' (wrong-way entry)",
        "side": None, "setup_name": None, "bear_score": 5, "bull_score": 11, "triggers_fired": [],
    })
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(
        "setup_dispatch.dispatch_extra_setups",
        lambda *a, **k: [{"setup_name": "bollinger_squeeze", "fired": True,
                           "direction": "long", "triggers": ["squeeze_break"]}],
    )
    routed = {"n": 0}
    monkeypatch.setattr(
        hc, "_route_extra_setups",
        lambda *a, **k: (routed.__setitem__("n", routed["n"] + 1),
                          [{"setup": "bollinger_squeeze", "action": "PLACED"}])[1],
    )

    rec = hc.run_account("safe")

    assert rec["verdict"] == "SKIP_STRUCTURE_VETO"
    assert routed["n"] == 0, "_route_extra_setups must NOT be called on SKIP_STRUCTURE_VETO"
    assert "extra_exec" not in rec
    assert rec.get("extra_exec_blocked_by") == "structure_veto"


def test_non_veto_hold_still_routes_extra_setup(hc, monkeypatch):
    """Sibling case: an ordinary HOLD (no setup, NOT a structure veto) must still
    route a fired+armed extra-setup exactly as before -- this fix narrows ONLY the
    SKIP_STRUCTURE_VETO case; it must not silently defeat the G4 route on plain HOLDs."""
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: object())
    monkeypatch.setattr(hc, "_build_payload", lambda df, params: _payload_stub())
    monkeypatch.setattr(hc, "_engine_verdict", lambda payload: {
        "verdict": "HOLD", "reason": "no setup passed scoring (neither bear nor bull)",
        "side": None, "setup_name": None, "bear_score": 5, "bull_score": 5, "triggers_fired": [],
    })
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(
        "setup_dispatch.dispatch_extra_setups",
        lambda *a, **k: [{"setup_name": "bollinger_squeeze", "fired": True,
                           "direction": "long", "triggers": ["squeeze_break"]}],
    )
    routed = {"n": 0}
    monkeypatch.setattr(
        hc, "_route_extra_setups",
        lambda *a, **k: (routed.__setitem__("n", routed["n"] + 1),
                          [{"setup": "bollinger_squeeze", "action": "PLACED"}])[1],
    )

    rec = hc.run_account("safe")

    assert rec["verdict"] == "HOLD"
    assert routed["n"] == 1, "_route_extra_setups must still fire on a plain HOLD"
    assert rec.get("extra_exec") == [{"setup": "bollinger_squeeze", "action": "PLACED"}]
