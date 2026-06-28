"""Graduated guard — DOUBLE_BOTTOM_BASE_QUIET dispatch wiring (2026-06-28).

Mirrors the G4 guard (test_g4_extra_setup_routing.py) for the double_bottom_base_quiet
detector. Pins the safety contract so a future edit that accidentally defaults the exec-arm
ON, or wires the detector to the wrong enable flag, REDs here immediately.

SAFETY CONTRACT (all must hold):
  1. DEFAULT-OFF:  'db_base_quiet_enabled' flag absent or False → NOT dispatched (no row
                   at all in SetupDispatcher.run() results).
  2. ENABLE != ARM: flag True (WATCH mode) → dispatches signal, but heartbeat_core routes
                   to WATCH_NOT_ARMED when extra_setup_exec_armed key is absent/False.
  3. EXEC-ARM:     extra_setup_exec_armed["double_bottom_base_quiet"]=True is the ONLY key
                   that gates live order placement — not the detector enable flag.
  4. CORRECT MAPPING: direction="long" (double bottom is bullish) → ENTER_BULL via
                   _synthetic_verdict_from_extra().
  5. SETUP NAME:   must be "double_bottom_base_quiet" (exact string), not any alias.
  6. FLAG NAME:    enable flag must be "db_base_quiet_enabled" (not j_db_* or db_quiet_*).

These are C14/L47 class guards: "validated in sim, never placed live" must be impossible
to reintroduce silently by a future parameter rename or flag misalignment.

Source evidence (CLAUDE.md OP-16 bar and real OPRA fills, C1):
  edgehunt-double_bottom_base_quiet.json (run 2026-06-20):
    4 cells clear full bar — OOS>0, posQ>=4/6, top5<200, N>=20 all hold.
    Best: strike+0_stop-0.99 N=122 WR=63.9% OOS_avg=+$26.3/trade.
  Cleared: OOS-positive expectancy + anchor-no-regression (OP-16 source-of-truth
    days are bearish entries; double_bottom is bullish — no regression to test).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture()
def sd_mod():
    """Import setup_dispatch fresh each test (avoids cross-test state leakage)."""
    if "setup_dispatch" in sys.modules:
        del sys.modules["setup_dispatch"]
    return importlib.import_module("setup_dispatch")


@pytest.fixture()
def hc_mod():
    """Import heartbeat_core fresh (for _extra_exec_armed)."""
    return importlib.import_module("heartbeat_core")


# ---------------------------------------------------------------------------
# 1. DEFAULT-OFF: flag absent → setup NOT dispatched (no row in results)
# ---------------------------------------------------------------------------

def test_db_base_quiet_not_dispatched_when_flag_absent(sd_mod):
    """When db_base_quiet_enabled is absent from params, the detector produces NO row."""
    params = {}   # flag absent entirely
    payload = {}  # empty payload — _build_ctx returns None → SKIP path never reached
    disp = sd_mod.SetupDispatcher(params, payload)
    results = disp.run()
    setup_names = [r.setup_name for r in results]
    assert "double_bottom_base_quiet" not in setup_names, (
        "double_bottom_base_quiet must NOT appear in results when flag is absent"
    )


def test_db_base_quiet_not_dispatched_when_flag_false(sd_mod):
    """When db_base_quiet_enabled=False, the detector produces NO row."""
    params = {"db_base_quiet_enabled": False}
    disp = sd_mod.SetupDispatcher(params, {})
    results = disp.run()
    assert all(r.setup_name != "double_bottom_base_quiet" for r in results)


# ---------------------------------------------------------------------------
# 2. ENABLE != ARM — enabled (WATCH) but no exec-arm key → WATCH_NOT_ARMED
# ---------------------------------------------------------------------------

def test_db_base_quiet_enabled_but_not_exec_armed_is_watch_only(hc_mod, monkeypatch):
    """With only db_base_quiet_enabled=True (no exec-arm key), _execute is never called."""
    called = {"n": 0}
    monkeypatch.setattr(hc_mod, "_execute",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    params = {"db_base_quiet_enabled": True}   # enabled (WATCH) but NOT exec-armed
    extra = [{
        "setup_name": "double_bottom_base_quiet",
        "fired": True,
        "direction": "long",
        "triggers": ["double_bottom_detector", "conf_low_gate", "low_vol_vix"],
    }]
    out = hc_mod._route_extra_setups("safe", extra, {"bar_ctx": {}}, params)
    assert called["n"] == 0, "_execute must NOT be called when only enabled, not exec-armed"
    assert out == [{"setup": "double_bottom_base_quiet", "action": "WATCH_NOT_ARMED"}]


# ---------------------------------------------------------------------------
# 3. EXEC-ARM KEY — exact spelling and exact True value required
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("params", [
    {},                                                              # key absent
    {"extra_setup_exec_armed": {}},                                  # empty dict
    {"extra_setup_exec_armed": {"double_bottom_base_quiet": False}}, # explicit False
    {"extra_setup_exec_armed": {"double_bottom_base_quiet": 1}},     # truthy-not-True
    {"extra_setup_exec_armed": {"double_bottom_base_quiet": "true"}},# string, not bool
    {"extra_setup_exec_armed": {"db_base_quiet": True}},             # wrong key name
])
def test_exec_arm_defaults_off(hc_mod, params):
    """All non-True and alias keys must return False from _extra_exec_armed."""
    assert hc_mod._extra_exec_armed(params, "double_bottom_base_quiet") is False


def test_exec_arm_requires_exact_true(hc_mod):
    """Only exact bool True arms the setup; a different setup stays off."""
    armed_params = {"extra_setup_exec_armed": {"double_bottom_base_quiet": True}}
    assert hc_mod._extra_exec_armed(armed_params, "double_bottom_base_quiet") is True
    # arming double_bottom must not arm gap_and_go or vwap_continuation
    assert hc_mod._extra_exec_armed(armed_params, "gap_and_go") is False
    assert hc_mod._extra_exec_armed(armed_params, "vwap_continuation") is False


# ---------------------------------------------------------------------------
# 4. CORRECT MAPPING: direction="long" → ENTER_BULL
# ---------------------------------------------------------------------------

def test_db_base_quiet_long_maps_to_enter_bull(hc_mod):
    """double_bottom is a bullish reversal — direction='long' must map to ENTER_BULL."""
    row = {
        "setup_name": "double_bottom_base_quiet",
        "fired": True,
        "direction": "long",
        "triggers": ["double_bottom_detector", "conf_low_gate"],
    }
    sv = hc_mod._synthetic_verdict_from_extra(row)
    assert sv is not None, "_synthetic_verdict_from_extra must not return None for fired=long"
    assert sv["verdict"] == "ENTER_BULL"
    assert sv["setup_name"] == "double_bottom_base_quiet"


def test_db_base_quiet_short_maps_to_enter_bear(hc_mod):
    """If a double_bottom watcher somehow emits short (shouldn't happen), map correctly."""
    row = {
        "setup_name": "double_bottom_base_quiet",
        "fired": True,
        "direction": "short",
        "triggers": ["double_bottom_detector"],
    }
    sv = hc_mod._synthetic_verdict_from_extra(row)
    assert sv is not None
    assert sv["verdict"] == "ENTER_BEAR"


# ---------------------------------------------------------------------------
# 5. FLAG NAME guard — the enable flag must be "db_base_quiet_enabled"
#    (not "j_db_base_quiet_enabled", "db_quiet_enabled", etc.)
# ---------------------------------------------------------------------------

def test_enable_flag_name_is_db_base_quiet_enabled(sd_mod):
    """The enable flag literal 'db_base_quiet_enabled' triggers dispatch when True.

    This test patches _build_ctx to return None (so the detector call itself is skipped)
    and verifies that setting db_base_quiet_enabled=True causes a row to appear in results
    (with SKIP_NO_FEED), while any other plausible alias does NOT.
    """
    with patch.object(sd_mod.SetupDispatcher, "_build_ctx", return_value=None):
        # Correct flag name → a result row appears (SKIP_NO_FEED, not absent)
        disp_on = sd_mod.SetupDispatcher({"db_base_quiet_enabled": True}, {})
        results_on = disp_on.run()
        assert any(r.setup_name == "double_bottom_base_quiet" for r in results_on), (
            "db_base_quiet_enabled=True must trigger dispatch (even if SKIP_NO_FEED)"
        )

        # Wrong alias → no row
        for bad_flag in ("j_db_base_quiet_enabled", "db_quiet_enabled", "double_bottom_base_quiet_enabled"):
            disp_bad = sd_mod.SetupDispatcher({bad_flag: True}, {})
            results_bad = disp_bad.run()
            assert all(r.setup_name != "double_bottom_base_quiet" for r in results_bad), (
                f"Alias '{bad_flag}' must NOT trigger dispatch — only 'db_base_quiet_enabled' is valid"
            )


# ---------------------------------------------------------------------------
# 6. SETUP NAME integrity — exact string "double_bottom_base_quiet"
# ---------------------------------------------------------------------------

def test_setup_name_exact_string(sd_mod):
    """When the flag is on and ctx is missing, the DispatchResult carries the exact setup name."""
    with patch.object(sd_mod.SetupDispatcher, "_build_ctx", return_value=None):
        disp = sd_mod.SetupDispatcher({"db_base_quiet_enabled": True}, {})
        results = disp.run()
        db_results = [r for r in results if r.setup_name == "double_bottom_base_quiet"]
        assert len(db_results) == 1
        assert db_results[0].fired is False
        assert db_results[0].skip_reason is not None
