"""Guard: fleet_live threads params ``time_stop_et`` into exit_actuator.manage_tick.

D2 audit finding #5 (2026-07-09, markdown/audits/OVERNIGHT-READ-D2-2026-07-09.md, Fable
adjudication ACCEPTED-S): fleet_live.run()'s exit-management pass called ea.manage_tick
WITHOUT ``time_stop_et``, so exit_manager's hard-coded 15:50 default always won and the
6 fleet arms carried runner positions 10 minutes longer than the core accounts
(heartbeat_core threads the same params key at its _manage_exits call, heartbeat_core.py
~L761). Same dead-knob class as C14/L148 -- the params value existed, nothing consumed it
on this path.

RED-PROOF: drop the ``time_stop_et=params.get(...)`` kwarg from fleet_live.run()'s
ea.manage_tick call -> test_manage_tick_receives_params_time_stop REDs (captured kwarg
becomes absent/None while params say "15:40").

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_fleet_time_stop_threaded.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_FLEET = ROOT / "automation" / "state" / "fleet"
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(_FLEET), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}


@pytest.fixture()
def fl():
    return importlib.import_module("fleet_live")


def test_params_time_stop_is_1540():
    """Precondition pin: the live params value this guard asserts gets threaded."""
    assert SAFE_PARAMS["time_stop_et"] == "15:40"


def test_manage_tick_receives_params_time_stop(fl, monkeypatch, tmp_path):
    """Drive the REAL fleet_live.run() loop (broker faked, no orders possible: master_live
    False + no signal) and capture the kwargs ea.manage_tick is called with. Every processed
    arm's exit pass must carry ITS params' time_stop_et -- not the absent/None that lets the
    hard-coded 15:50 default win."""
    captured: list[dict] = []

    # STRUCTURE-STOP (2026-07-09) added a keyword-only last_closed_5m_close kwarg to the
    # REAL manage_tick -- this fake must accept it (a mock with a stale signature makes
    # fleet_live.run()'s try/except SILENTLY swallow the TypeError, which is exactly the
    # kind of false-green this guard exists to prevent; see run()'s exit-pass except block).
    def fake_manage_tick(arm_id, creds, *, live, ribbon_flip_back_fn=None, now_et=None,
                         broker=None, time_stop_et=None, last_closed_5m_close=None):
        captured.append({"arm_id": arm_id, "live": live, "time_stop_et": time_stop_et,
                         "last_closed_5m_close": last_closed_5m_close})
        return []

    # Broker: every processable arm gets creds + a clean flat account; nothing real is hit.
    processable = [a["id"] for a in json.loads((_FLEET / "accounts.json").read_text(encoding="utf-8"))
                   .get("arms", []) if fl._arm_is_processable(a)]
    monkeypatch.setattr(fl.fb, "load_creds", lambda: {arm: _CREDS for arm in processable})
    monkeypatch.setattr(fl.fb, "get_account", lambda c: {"equity": "2000.0", "daytrade_count": 0})
    monkeypatch.setattr(fl.fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fl.ea, "manage_tick", fake_manage_tick)
    monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)  # isolate breaker/lock/ledger writes

    results = fl.run(tmp_path / "no-such-signal.json", master_live=False)

    assert results, "run() processed no arms -- harness broke, not the feature"
    assert captured, "ea.manage_tick was never called -- the exit pass is severed"
    for call in captured:
        # Each arm's params come from fx._params_for(arm); every SPY arm's base params
        # (SAFE or BOLD) carry time_stop_et="15:40" -- absence here = the dead-knob regression.
        assert call["time_stop_et"] == "15:40", (
            f"{call['arm_id']}: manage_tick got time_stop_et={call['time_stop_et']!r} -- "
            "params time_stop_et is not threaded (fleet reverts to the hard-coded 15:50)")
        # STRUCTURE-STOP wiring (2026-07-09): this harness's signal path does not exist, so
        # usable_signal is None throughout -- last_closed_5m_close must be the fail-open
        # None (never a guess), proving the kwarg reaches manage_tick without crashing.
        assert call["last_closed_5m_close"] is None


def test_no_arm_is_live_in_this_harness(fl, monkeypatch, tmp_path):
    """Safety pin on the harness itself: master_live=False must mean every captured exit
    pass ran live=False (nothing in this guard can ever place)."""
    captured: list[dict] = []

    def fake_manage_tick(arm_id, creds, *, live, ribbon_flip_back_fn=None, now_et=None,
                         broker=None, time_stop_et=None, last_closed_5m_close=None):
        captured.append({"live": live})
        return []

    monkeypatch.setattr(fl.fb, "load_creds",
                        lambda: {a["id"]: _CREDS for a in
                                 json.loads((_FLEET / "accounts.json").read_text(encoding="utf-8"))
                                 .get("arms", [])})
    monkeypatch.setattr(fl.fb, "get_account", lambda c: {"equity": "2000.0", "daytrade_count": 0})
    monkeypatch.setattr(fl.fb, "is_flat_spy_options", lambda c: True)
    monkeypatch.setattr(fl.ea, "manage_tick", fake_manage_tick)
    monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)

    fl.run(tmp_path / "no-such-signal.json", master_live=False)
    assert captured and all(c["live"] is False for c in captured)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
