"""EXTRA-SIGNAL-CHURN-COOLDOWN guard (queue.md, filed 2026-07-20 ~11:25 ET during RTH).

Live exhibit 2026-07-20 09:51-09:55 ET, safe account, extra_exec lane
vix_regime_dayside: THREE 3-lot 748C entries in 5 minutes (fills 1.13/0.79/0.76),
each stopped out in 40-60s, net -$87. The watchers' current-bar guards stop a
DUPLICATE signal within one bar, but nothing stopped a FRESH re-entry once the
account went flat again mid-bar (a stop-out) -- the nondeterministic free-model
veto blocked 2 of the 5 attempts, not a real gate.

Fix: exit_actuator.same_bar_cooldown_active/record_entry_bar (a per-arm, per-setup
"last trigger-bar attempted" ledger) + heartbeat_core._route_extra_setups now
refuses a new entry attempt for a setup on the SAME trigger bar it already
attempted one on. A stop-out no longer re-arms the setup until a genuinely NEW
5m bar closes. Scoped to the extra-setup lane only (out of scope: the primary
ribbon path, which already has its own one-position + gate discipline).

Pins:
  1. exit_actuator.same_bar_cooldown_active/record_entry_bar round-trip + fail-open
     on missing/corrupt state.
  2. _route_extra_setups: a 2nd attempt on the SAME bar for a setup that already
     attempted this bar is refused (SKIP_COOLDOWN_SAME_BAR), _execute never called.
  3. A DIFFERENT trigger bar for the SAME setup is NOT blocked (the whole point --
     a genuinely new signal must still trade).
  4. A cooldown-check exception never blocks a legitimate entry (fail-open).
  5. Recording only happens on an actual placement/would-place, not on a
     WATCH_NOT_ARMED / VETOED_BY_MODELS / SKIP_TICK_ENTRY_TAKEN row.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in (_SCRIPTS, _FLEET):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


@pytest.fixture()
def ea():
    return importlib.import_module("exit_actuator")


@pytest.fixture()
def cooldown_file(tmp_path, monkeypatch, ea):
    """Redirect exit_actuator's FLEET_DIR to a scratch dir so this test never touches
    the real automation/state/fleet/*/extra-setup-cooldown.json files."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    return tmp_path


def _payload(bar_ts: str) -> dict:
    return {"bar_ctx": {"timestamp_et": bar_ts}}


# --------------------------------------------------------------------------- #
# 1. exit_actuator primitives
# --------------------------------------------------------------------------- #
def test_load_last_entry_bars_empty_on_missing(cooldown_file, ea):
    assert ea.load_last_entry_bars("safe-2") == {}


def test_record_and_check_round_trip(cooldown_file, ea):
    assert ea.same_bar_cooldown_active("safe-2", "vix_regime_dayside", "2026-07-20T09:50:00") is False
    ea.record_entry_bar("safe-2", "vix_regime_dayside", "2026-07-20T09:50:00")
    assert ea.same_bar_cooldown_active("safe-2", "vix_regime_dayside", "2026-07-20T09:50:00") is True
    # a DIFFERENT bar for the same setup is not blocked
    assert ea.same_bar_cooldown_active("safe-2", "vix_regime_dayside", "2026-07-20T09:55:00") is False
    # a different setup on the same bar is not blocked
    assert ea.same_bar_cooldown_active("safe-2", "gap_and_go", "2026-07-20T09:50:00") is False


def test_load_last_entry_bars_fail_open_on_corrupt(cooldown_file, ea):
    d = cooldown_file / "safe-2"
    d.mkdir()
    (d / "extra-setup-cooldown.json").write_text("{not json", encoding="utf-8")
    assert ea.load_last_entry_bars("safe-2") == {}
    assert ea.same_bar_cooldown_active("safe-2", "x", "2026-07-20T09:50:00") is False


def test_same_bar_cooldown_active_fail_open_on_missing_inputs(cooldown_file, ea):
    assert ea.same_bar_cooldown_active("safe-2", None, "2026-07-20T09:50:00") is False
    assert ea.same_bar_cooldown_active("safe-2", "x", None) is False


def test_record_entry_bar_noop_on_missing_inputs(cooldown_file, ea):
    ea.record_entry_bar("safe-2", "", "2026-07-20T09:50:00")  # must not raise
    ea.record_entry_bar("safe-2", "x", "")  # must not raise
    assert ea.load_last_entry_bars("safe-2") == {}


# --------------------------------------------------------------------------- #
# 2/3. _route_extra_setups wiring
# --------------------------------------------------------------------------- #
def test_second_attempt_same_bar_is_blocked(hc, ea, cooldown_file, monkeypatch):
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE", "symbol": "SPY..C"})
    params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
    extra = [{"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
              "triggers": ["vix_dayside"]}]
    payload = _payload("2026-07-20T09:50:00")

    out1 = hc._route_extra_setups("safe", extra, payload, params)
    assert out1[0]["action"] == "WOULD_PLACE"

    # simulate the account going flat again (stop-out) and the SAME bar still current
    called = {"n": 0}
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: called.__setitem__("n", called["n"] + 1)
                         or {"status": "WOULD_PLACE"})
    out2 = hc._route_extra_setups("safe", extra, payload, params)
    assert out2[0]["action"] == "SKIP_COOLDOWN_SAME_BAR"
    assert called["n"] == 0, "_execute must NOT be called on a same-bar cooldown re-entry"


def test_new_bar_is_not_blocked(hc, ea, cooldown_file, monkeypatch):
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE", "symbol": "SPY..C"})
    params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
    extra = [{"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
              "triggers": ["vix_dayside"]}]

    out1 = hc._route_extra_setups("safe", extra, _payload("2026-07-20T09:50:00"), params)
    assert out1[0]["action"] == "WOULD_PLACE"

    called = {"n": 0}
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: called.__setitem__("n", called["n"] + 1)
                         or {"status": "WOULD_PLACE"})
    out2 = hc._route_extra_setups("safe", extra, _payload("2026-07-20T09:55:00"), params)
    assert out2[0]["action"] == "WOULD_PLACE", "a genuinely NEW trigger bar must still trade"
    assert called["n"] == 1


def test_cooldown_check_exception_fails_open(hc, monkeypatch):
    """Even if exit_actuator itself is broken, the route must still be able to place --
    fail-open, never fail-blocked (CLAUDE.md rail 2 spirit applied to a research-side guard:
    a broken cooldown file can never become a silent-forever trading halt)."""
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE", "symbol": "SPY..C"})

    import exit_actuator as broken_ea  # noqa: PLC0415
    monkeypatch.setattr(broken_ea, "same_bar_cooldown_active",
                         lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk error")))

    params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
    extra = [{"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
              "triggers": ["vix_dayside"]}]
    out = hc._route_extra_setups("safe", extra, _payload("2026-07-20T09:50:00"), params)
    assert out[0]["action"] == "WOULD_PLACE"


# --------------------------------------------------------------------------- #
# 5. Recording only happens on an actual placement
# --------------------------------------------------------------------------- #
def test_no_record_on_watch_not_armed(hc, ea, cooldown_file, monkeypatch):
    params = {}  # not exec-armed at all
    extra = [{"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
              "triggers": ["vix_dayside"]}]
    out = hc._route_extra_setups("safe", extra, _payload("2026-07-20T09:50:00"), params)
    assert out[0]["action"] == "WATCH_NOT_ARMED"
    assert ea.load_last_entry_bars("safe-2") == {}


def test_no_record_on_veto(hc, ea, cooldown_file, monkeypatch):
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": True, "reason": "no"})
    params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
    extra = [{"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
              "triggers": ["vix_dayside"]}]
    out = hc._route_extra_setups("safe", extra, _payload("2026-07-20T09:50:00"), params)
    assert out[0]["action"] == "VETOED_BY_MODELS"
    assert ea.load_last_entry_bars("safe-2") == {}
