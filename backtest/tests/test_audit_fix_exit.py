"""GUARD (FIX #5, 2026-07-07): the params.json ``time_stop_et`` knob must be LIVE on the
exit behavior path, not a dead knob shadowed by the hard-coded 15:50.

Root cause it red-proofs: exit_actuator.manage_tick called exit_manager.plan_exit_actions
WITHOUT passing time_stop_et, so the pure core defaulted to TIME_STOP_ET (15:50) and any
value in params.json (e.g. "15:40") never changed the live force-close time.

The fix: manage_tick now accepts time_stop_et (the params value), parses it via
exit_manager.parse_time_stop_et (fail-safe to 15:50 on missing/malformed -- never widens
past close), and forwards it to plan_exit_actions.

RED-PROOF (what fails without the production fix):
  * revert exit_actuator.manage_tick's `time_stop_et=` forward -> the core defaults to 15:50
    -> at 15:41 with time_stop_et="15:40" NO SELL_ALL fires (position held past its stop) ->
    test_manage_tick_honors_earlier_time_stop FAILS on `assert time_stops` (empty).
  * revert exit_manager.parse_time_stop_et -> ImportError on the direct-parse asserts.

The fleet dir is on sys.path via conftest? -- exit_manager/exit_actuator live in
automation/state/fleet, so we add that dir explicitly (mirrors how the fleet's own
test_exit_actuator.py imports them by bare name)."""
from __future__ import annotations

import sys
from datetime import datetime, time as _time, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FLEET = _ROOT / "automation" / "state" / "fleet"
_SCRIPTS = _ROOT / "setup" / "scripts"  # exit_actuator imports et_clock from here
for _p in (_FLEET, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_actuator as ea  # noqa: E402
import exit_manager as em  # noqa: E402

SYM = "SPY260707P00600000"
# An exit shape that will NOT trigger a premium stop / TP1 at the test quote, so the ONLY
# thing that can produce a SELL is the time stop -- isolating the knob under test.
QUIET_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.5,
               "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
# quote sits just above entry: no premium-stop (worst > entry*(1-0.50)), no TP1 (best <
# entry*(1+1.5)). Pure hold absent a time stop.
HILO = (1.05, 0.99)
ENTRY = 1.00


class _FakeBroker:
    """Records sells; scripted qty + quote. Mirrors fleet/test_exit_actuator.FakeBroker."""
    def __init__(self, qty, hilo):
        self._qty = [qty]
        self._hilo = [hilo]
        self.sells = []

    def get_position_qty(self, creds, symbol):
        return self._qty.pop(0) if self._qty else 0

    def get_option_quote_hilo(self, creds, symbol):
        return self._hilo.pop(0) if self._hilo else None

    def market_sell(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        return {"id": "fake", "status": "accepted"}


def _dt(h, m):
    return datetime(2026, 7, 7, h, m, tzinfo=timezone(timedelta(hours=-4)))


def _arm(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    return "test-arm"


# ── 1. parse helper: fail-SAFE + honest parse ────────────────────────────────────────────
def test_parse_time_stop_et_reads_hhmm():
    assert em.parse_time_stop_et("15:40") == _time(15, 40)


def test_parse_time_stop_et_failsafe_default():
    # missing / malformed -> the doctrine default 15:50, never a widened stop.
    assert em.parse_time_stop_et(None) == _time(15, 50)
    assert em.parse_time_stop_et("garbage") == _time(15, 50)
    assert em.parse_time_stop_et("25:99") == _time(15, 50)


# ── 2. pure core already honored the kwarg -- this pins that contract ─────────────────────
def test_plan_exit_actions_uses_passed_time_stop():
    st = em.ExitState.from_entry(symbol=SYM, side="P", entry_premium=ENTRY, qty=5,
                                 exit_shape=QUIET_SHAPE)
    early = em.plan_exit_actions(st, best_premium=HILO[0], worst_premium=HILO[1],
                                 open_qty=5, now_et=_time(15, 39),
                                 time_stop_et=_time(15, 40))
    assert not any(a.stage == "time_stop" for a in early.actions), "15:39 must NOT time-stop"
    late = em.plan_exit_actions(st, best_premium=HILO[0], worst_premium=HILO[1],
                                open_qty=5, now_et=_time(15, 41),
                                time_stop_et=_time(15, 40))
    assert any(a.kind == "SELL_ALL" and a.stage == "time_stop" for a in late.actions), \
        "15:41 must time-stop at 15:40"


# ── 3. BEHAVIOR PATH: manage_tick must forward the params knob (this is the dead-knob RED) ─
def test_manage_tick_honors_earlier_time_stop(tmp_path, monkeypatch):
    """With time_stop_et='15:40' a tick at 15:41 force-closes; a tick at 15:39 does not.
    If manage_tick fails to forward the knob, the core defaults to 15:50 and 15:41 HOLDS ->
    `time_stops` is empty -> this assert FAILS (the red-proof)."""
    # 15:39 -> no time stop (below the earlier knob)
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=ENTRY, qty=5,
                      exit_shape=QUIET_SHAPE)
    fb_early = _FakeBroker(qty=5, hilo=HILO)
    ea.manage_tick(arm, {}, live=True, broker=fb_early, now_et=_dt(15, 39),
                   time_stop_et="15:40")
    assert not fb_early.sells, "15:39 tick must NOT sell (before the 15:40 knob)"

    # 15:41 -> time stop fires because the params knob (15:40) is now honored, not 15:50
    fb_late = _FakeBroker(qty=5, hilo=HILO)
    res = ea.manage_tick(arm, {}, live=True, broker=fb_late, now_et=_dt(15, 41),
                         time_stop_et="15:40")
    time_stops = [a for r in res for a in r.get("actions", [])
                  if a.get("stage") == "time_stop"]
    assert time_stops, "15:41 tick MUST time-stop under time_stop_et='15:40' (dead-knob RED)"
    assert fb_late.sells and fb_late.sells[0]["qty"] == 5, "time stop sells ALL open units"


def test_manage_tick_default_still_1550(tmp_path, monkeypatch):
    """Absent a param (None), the behavior path still fails SAFE to 15:50: a 15:41 tick with
    NO time_stop_et supplied must NOT time-stop (guards against the fix widening/narrowing the
    default)."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=ENTRY, qty=5,
                      exit_shape=QUIET_SHAPE)
    fb = _FakeBroker(qty=5, hilo=HILO)
    ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(15, 41))  # no time_stop_et
    assert not fb.sells, "15:41 with default knob (15:50) must NOT time-stop"
