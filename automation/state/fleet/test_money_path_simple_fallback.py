"""Guard: the fleet live order path MUST pass simple_fallback=True to place_bracket.

THE 2026-06-28 MONEY-PATH FIX. Alpaca rejects BOTH bracket and oto for options (error
42210000). Without simple_fallback, every fleet ENTER returned _error -> placed=False ->
no fill -> the exit_manager was never registered: the 4 live fleet arms placed ZERO option
orders from 2026-06-22 onward (the "nothing is working" root cause uncovered by the
2026-06-28 full audit).

This RED-on-regression test pins the kwarg so the zero-fills bug can never silently return.
It is SAFE to place a stopless-broker simple limit because the fleet registers each fill with
the ticking exit_manager (fleet_live._place_live register_entry + ea.manage_tick runs FIRST
each cycle, enforcing premium/target/time stops via the per-tick worst<=stop check) -- the
exact C2 condition place_bracket's own docstring requires.
"""
from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

import fleet_live as fl


def test_place_live_passes_simple_fallback(monkeypatch):
    """The load-bearing assertion: _place_live calls place_bracket with simple_fallback=True,
    and an accepted fill registers with the exit_manager (no orphan, no stopless naked long)."""
    captured: dict = {}

    def fake_place_bracket(creds, **kw):
        captured.update(kw)
        # mimic the real simple-fallback success path: not _error / not _refused -> placed=True
        return {"id": "fake-order", "_simple_fallback": True}

    registered: dict = {}

    def fake_register_entry(arm_id, **kw):
        registered["arm_id"] = arm_id
        registered.update(kw)

    monkeypatch.setattr(fl.fb, "get_option_mid", lambda creds, symbol: 1.00)
    monkeypatch.setattr(fl.fb, "place_bracket", fake_place_bracket)
    monkeypatch.setattr(fl.ea, "register_entry", fake_register_entry)

    decision = SimpleNamespace(side="P", strike=600, qty=3, setup_name="VWAP_CONTINUATION")
    arm = {"id": "risky-test"}
    exit_shape = {"tp1_premium_pct": 0.30, "premium_stop_pct": -0.08,
                  "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing"}
    now = _dt.datetime(2026, 6, 29, 10, 0)

    res = fl._place_live({"k": "v"}, arm, decision, exit_shape, {"tick_id": 1}, {}, now)

    assert captured.get("simple_fallback") is True, \
        "fleet _place_live MUST pass simple_fallback=True (else Alpaca 42210000 -> zero fills)"
    assert res["placed"] is True
    assert registered.get("arm_id") == "risky-test", \
        "an accepted fill MUST register with the exit_manager (C2: tick-managed stop)"


def test_simple_fallback_off_strands_orders(monkeypatch):
    """Characterize the bug being prevented: if place_bracket returns _error (the options
    complex-order rejection, which is what happened pre-fix), placed=False and register_entry
    is NEVER called -- the zero-fills + no-exit-state failure mode."""
    monkeypatch.setattr(fl.fb, "get_option_mid", lambda creds, symbol: 1.00)
    monkeypatch.setattr(fl.fb, "place_bracket",
                        lambda creds, **kw: {"_error": "both bracket and oto rejected"})
    called = {"n": 0}
    monkeypatch.setattr(fl.ea, "register_entry",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    decision = SimpleNamespace(side="P", strike=600, qty=3, setup_name="VWAP_CONTINUATION")
    now = _dt.datetime(2026, 6, 29, 10, 0)
    res = fl._place_live({"k": "v"}, {"id": "x"}, decision, {}, {"tick_id": 1}, {}, now)

    assert res["placed"] is False
    assert called["n"] == 0  # no fill -> no exit registration (the zero-fills bug)
