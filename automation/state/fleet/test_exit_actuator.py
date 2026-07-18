"""Tests for exit_actuator -- the live layer that turns plan_exit_actions into broker calls.

Uses a FAKE broker (no network) + a temp arm dir so the placed orders are captured and
asserted against the exit_shape's scale-out geometry. Proves:
  * WATCH (live=False) places NOTHING, LIVE (live=True) places the partial sells.
  * the TOTAL placed sells across the lifecycle == total_qty, split tp1_qty + runner_qty.
  * a broker-flat position is pruned from the persisted ledger.
"""
from __future__ import annotations

import json

import exit_actuator as ea
import exit_manager as em

RIBBON_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5,
                "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
SYM = "SPY260625P00600000"


class FakeBroker:
    """Injectable broker: scripted qty + quote per call, records every sell/replace."""
    def __init__(self, qty_seq, hilo_seq):
        self._qty = list(qty_seq)
        self._hilo = list(hilo_seq)
        self.sells = []
        self.replaces = []

    def get_position_qty(self, creds, symbol):
        return self._qty.pop(0) if self._qty else 0

    def get_option_quote_hilo(self, creds, symbol):
        return self._hilo.pop(0) if self._hilo else None

    def market_sell(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        return {"id": "fake", "status": "accepted"}

    def replace_stop_order(self, creds, *, order_id, stop_price, live):
        self.replaces.append({"order_id": order_id, "stop_price": stop_price})
        return {"id": "fake", "status": "accepted"}


def _arm(tmp_path, monkeypatch):
    """Point the actuator's FLEET_DIR at a temp dir so state writes are isolated."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    return "test-arm"


def test_register_entry_persists_state(tmp_path, monkeypatch):
    arm = _arm(tmp_path, monkeypatch)
    st = ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                           exit_shape=RIBBON_SHAPE, strategy="ribbon_ride")
    assert st.tp1_qty == 4 and st.runner_qty == 1
    loaded = ea.load_states(arm)
    assert SYM in loaded and loaded[SYM].entry_premium == 1.00


def test_watch_places_nothing(tmp_path, monkeypatch):
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = FakeBroker(qty_seq=[5], hilo_seq=[(2.55, 2.40)])  # TP1 would fire
    res = ea.manage_tick(arm, {}, live=False, broker=fb,
                         now_et=_dt(11, 0))
    # WATCH: the action is COMPUTED but no real sell placed (live flag false in the call)
    sells = [a for r in res for a in r.get("actions", []) if a["kind"] == "SELL_PARTIAL"]
    assert sells and sells[0]["qty"] == 4
    assert all(s["live"] is False for s in fb.sells)  # market_sell got live=False


def test_live_tp1_places_partial_sell(tmp_path, monkeypatch):
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = FakeBroker(qty_seq=[5], hilo_seq=[(2.55, 2.40)])
    ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0))
    assert len(fb.sells) == 1 and fb.sells[0]["qty"] == 4 and fb.sells[0]["live"] is True
    # state persisted: tp1_filled, runner stop -> BE
    st = ea.load_states(arm)[SYM]
    assert st.tp1_filled and st.runner_stop_premium == 1.00


def test_full_lifecycle_total_sold_equals_qty(tmp_path, monkeypatch):
    """Across TP1 (sell 4) + runner BE stop (sell 1) the total placed == 5 = total_qty."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    # tick 1: TP1 (qty5 open, premium spikes) -> sell 4
    fb1 = FakeBroker(qty_seq=[5], hilo_seq=[(2.55, 2.40)])
    ea.manage_tick(arm, {}, live=True, broker=fb1, now_et=_dt(11, 0))
    # tick 2: runner alone (qty1 open), drops to BE -> sell 1
    fb2 = FakeBroker(qty_seq=[1], hilo_seq=[(1.05, 0.99)])
    ea.manage_tick(arm, {}, live=True, broker=fb2, now_et=_dt(11, 5))
    total = sum(s["qty"] for s in fb1.sells) + sum(s["qty"] for s in fb2.sells)
    assert total == 5
    # runner fully closed -> pruned from the ledger
    assert SYM not in ea.load_states(arm)


def test_flat_position_pruned(tmp_path, monkeypatch):
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = FakeBroker(qty_seq=[0], hilo_seq=[])  # broker shows flat
    res = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0))
    assert res and res[0]["action"] == "FLAT_PRUNED"
    assert SYM not in ea.load_states(arm)


def test_no_quote_holds(tmp_path, monkeypatch):
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = FakeBroker(qty_seq=[5], hilo_seq=[None])  # quote unavailable
    res = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0))
    assert res[0]["action"] == "HOLD" and res[0]["reason"] == "no_quote"
    assert not fb.sells  # never force-exits on a missing quote


def test_ribbon_flip_fn_forces_exit(tmp_path, monkeypatch):
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = FakeBroker(qty_seq=[5], hilo_seq=[(1.10, 1.05)])  # no premium exit
    res = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0),
                         ribbon_flip_back_fn=lambda sym, side: True)
    assert fb.sells and fb.sells[0]["qty"] == 5  # exit ALL on flip
    assert SYM not in ea.load_states(arm)


# =============================================================================
# F7-EXIT-SELL-ALL-REFIRE (2026-07-18): duplicate-sell guard + failed-sell retry.
#
# Root cause traced this fire: BEFORE this fix, `if dec.closes_position: del
# states[symbol]` pruned the tracked position UNCONDITIONALLY the instant
# plan_exit_actions DECIDED to exit -- regardless of whether broker.market_sell
# actually succeeded. A failed/errored SELL_ALL (network timeout, API rejection)
# permanently orphaned the position from exit management (a silent forget, not a
# re-fire) until the 15:55 ET EOD-flatten backstop caught it. Separately, blindly
# retrying a "failed" sell is unsafe on its own: a urllib TimeoutError can fire
# AFTER Alpaca already accepted the POST, so a naive retry risks a genuine
# DUPLICATE real sell -- the literal risk F7 was filed to name. The fix threads
# BOTH: (a) don't prune on a failed/skipped sell -> next tick retries, (b) before
# retrying, check broker.open_sell_orders() for a still-resting order on this
# symbol and skip re-submitting if one exists.
# =============================================================================

class DupeGuardBroker(FakeBroker):
    """Extends FakeBroker with an injectable open_sell_orders() so these tests can
    exercise the F7 duplicate-guard path without touching the base fixture other
    tests in this file rely on (getattr-guarded in exit_actuator -- a broker WITHOUT
    this method, like the base FakeBroker, falls back to today's pre-guard behavior,
    proven unchanged by the 12 tests above)."""
    def __init__(self, qty_seq, hilo_seq, resting_seq=None, sell_results=None):
        super().__init__(qty_seq, hilo_seq)
        self._resting = list(resting_seq or [])
        self._sell_results = list(sell_results or [])
        self.open_sell_orders_calls = []

    def open_sell_orders(self, creds, symbol):
        self.open_sell_orders_calls.append(symbol)
        return self._resting.pop(0) if self._resting else []

    def market_sell(self, creds, *, symbol, qty, live):
        self.sells.append({"symbol": symbol, "qty": qty, "live": live})
        if self._sell_results:
            return self._sell_results.pop(0)
        return {"id": "fake", "status": "accepted"}


def test_duplicate_guard_skips_resubmit_when_order_already_resting(tmp_path, monkeypatch):
    """A prior tick's SELL_ALL is still resting broker-side -> this tick must NOT place a
    second market sell, and must NOT prune the ledger (position isn't confirmed flat yet)."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = DupeGuardBroker(qty_seq=[5], hilo_seq=[(0.10, 0.05)],   # premium stop hit -> SELL_ALL
                         resting_seq=[[{"id": "resting-1", "symbol": SYM, "side": "sell"}]])
    res = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0))
    assert not fb.sells, "must not place a duplicate market sell while one is already resting"
    assert fb.open_sell_orders_calls == [SYM]
    assert SYM in ea.load_states(arm), "position must stay tracked until confirmed flat"
    action = [a for r in res for a in r.get("actions", [])][0]
    assert action["kind"] == "SELL_ALL" and action["placed"] is False
    assert "duplicate guard" in action["broker"]["_skipped"]


def test_failed_sell_not_pruned_and_retries_next_tick(tmp_path, monkeypatch):
    """market_sell errors (e.g. network timeout) -> the position must stay tracked (NOT
    silently orphaned) so the NEXT tick retries; once it succeeds, the ledger prunes."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = DupeGuardBroker(qty_seq=[5, 5], hilo_seq=[(0.10, 0.05), (0.10, 0.05)],
                         resting_seq=[[], []],   # no resting order either tick
                         sell_results=[{"_error": "timeout"}, {"id": "ok", "status": "accepted"}])
    # tick 1: sell attempt fails -> must NOT prune
    res1 = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0))
    assert fb.sells and fb.sells[0]["qty"] == 5
    assert res1[0]["actions"][0]["placed"] is False
    assert SYM in ea.load_states(arm), "a failed sell must not orphan the position"
    # tick 2: retry succeeds -> now prune
    res2 = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 1))
    assert len(fb.sells) == 2 and fb.sells[1]["qty"] == 5
    assert res2[0]["actions"][0]["placed"] is True
    assert SYM not in ea.load_states(arm)


def test_watch_mode_unaffected_by_duplicate_guard(tmp_path, monkeypatch):
    """WATCH (live=False) never calls open_sell_orders or market_sell -- the guard is a
    LIVE-only concern; WATCH keeps previewing+pruning exactly as before this fix."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    fb = DupeGuardBroker(qty_seq=[5], hilo_seq=[(0.10, 0.05)],
                         resting_seq=[[{"id": "resting-1", "symbol": SYM, "side": "sell"}]])
    res = ea.manage_tick(arm, {}, live=False, broker=fb, now_et=_dt(11, 0))
    assert not fb.open_sell_orders_calls, "WATCH must not even query for resting orders"
    assert not fb.sells
    assert SYM not in ea.load_states(arm), "WATCH still previews+prunes (unchanged behavior)"


def test_base_fakebroker_without_dupe_guard_method_unaffected(tmp_path, monkeypatch):
    """A broker double that doesn't implement open_sell_orders (e.g. every OTHER test in
    this file's base FakeBroker) must fail OPEN to the exact pre-guard behavior -- proves
    the getattr guard, not just that the base test suite happens to still pass."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=RIBBON_SHAPE)
    assert not hasattr(FakeBroker, "open_sell_orders")
    fb = FakeBroker(qty_seq=[5], hilo_seq=[(0.10, 0.05)])
    res = ea.manage_tick(arm, {}, live=True, broker=fb, now_et=_dt(11, 0))
    assert fb.sells and fb.sells[0]["qty"] == 5
    assert res[0]["actions"][0]["placed"] is True
    assert SYM not in ea.load_states(arm)


# =============================================================================
# VISIBILITY (2026-07-09, OP-33c): stop_mode/trigger_level/last_closed_5m_close on every
# exit_pass row + describe_stop() -- the render-only fix for the known cosmetic bug
# (STATUS.md 2026-07-09 ~16:20 ET: "plan-log 'stop' shows the -20% fallback even in
# structure mode").
# =============================================================================
STRUCTURE_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
                   "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
                   "stop_mode": "structure", "catastrophe_stop_pct": -0.50}


def test_visibility_fields_are_additive_actions_unchanged(tmp_path, monkeypatch):
    """RENDER-ONLY PROOF (vary-and-assert): manage_tick's new stop_mode / trigger_level /
    last_closed_5m_close reporting fields can never change WHICH actions fire. Cross-checks
    the actuator's emitted actions against an INDEPENDENT direct call to the untouched pure
    core (exit_manager.plan_exit_actions, same inputs) -- if the reporting addition had
    leaked into the decision path, this diff would catch it. Also proves the fields
    themselves appear correctly on a fixture tick's row."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=STRUCTURE_SHAPE, strategy="ribbon_ride",
                      trigger_level=745.0, structure_stop_enabled=True)
    pre_state = ea.load_states(arm)[SYM]

    fb = FakeBroker(qty_seq=[5], hilo_seq=[(1.05, 1.00)])
    now = _dt(11, 0)
    res = ea.manage_tick(arm, {}, live=False, broker=fb, now_et=now, last_closed_5m_close=745.6)
    row = res[0]
    actuator_actions = [(a["kind"], a.get("qty"), a["stage"]) for a in row["actions"]]

    direct = em.plan_exit_actions(pre_state, best_premium=1.05, worst_premium=1.00,
                                  open_qty=5, now_et=now.time(), last_closed_5m_close=745.6)
    direct_actions = [(a.kind, a.qty, a.stage) for a in direct.actions]
    assert actuator_actions == direct_actions, \
        "visibility fields must never change WHICH actions fire"

    assert row["stop_mode"] == "structure"
    assert row["trigger_level"] == 745.0
    assert row["last_closed_5m_close"] == 745.6


def test_visibility_fields_survive_flat_pruned_and_hold_rows(tmp_path, monkeypatch):
    """The truth must not vanish on the tick a position closes (FLAT_PRUNED) or stalls
    (no-quote HOLD) -- both branches carry stop_mode/trigger_level too, not just the
    normal managed branch."""
    arm = _arm(tmp_path, monkeypatch)
    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=STRUCTURE_SHAPE, trigger_level=600.0,
                      structure_stop_enabled=True)
    fb_flat = FakeBroker(qty_seq=[0], hilo_seq=[])
    res = ea.manage_tick(arm, {}, live=True, broker=fb_flat, now_et=_dt(11, 0))
    assert res[0]["action"] == "FLAT_PRUNED"
    assert res[0]["stop_mode"] == "structure" and res[0]["trigger_level"] == 600.0

    ea.register_entry(arm, symbol=SYM, side="P", entry_premium=1.00, qty=5,
                      exit_shape=STRUCTURE_SHAPE, trigger_level=600.0,
                      structure_stop_enabled=True)
    fb_noquote = FakeBroker(qty_seq=[5], hilo_seq=[None])
    res2 = ea.manage_tick(arm, {}, live=True, broker=fb_noquote, now_et=_dt(11, 0))
    assert res2[0]["action"] == "HOLD"
    assert res2[0]["stop_mode"] == "structure" and res2[0]["trigger_level"] == 600.0


def test_describe_stop_structure_mode():
    st = em.ExitState.from_entry(
        symbol=SYM, side="P", entry_premium=1.00, qty=5, exit_shape=STRUCTURE_SHAPE,
        trigger_level=745.41, structure_stop_enabled=True)
    assert ea.describe_stop(st) == "STRUCTURE@745.41 (cat -50%)"


def test_describe_stop_premium_mode():
    """Premium mode ALWAYS renders the CALLER's own fallback text, never state.
    runner_stop_premium: the caller's numeric stop is mid-based (the pre-fill estimate),
    while ExitState.runner_stop_premium is entry_px-based (the real fill price) -- reading
    the state here would print a DIFFERENT number than the "stop" field returned alongside
    it. No fallback supplied -> honest 'n/a', never guesses."""
    st = em.ExitState.from_entry(symbol=SYM, side="P", entry_premium=1.00, qty=5,
                                 exit_shape=RIBBON_SHAPE)  # no stop_mode key -> "premium"
    assert st.stop_mode == "premium"
    assert ea.describe_stop(st, fallback_price=0.80, fallback_pct=-0.20) == "0.80 (-20%)"
    assert ea.describe_stop(st) == "n/a"


def test_describe_stop_none_state_falls_back_to_caller_text():
    """state=None (registration skipped/failed) -> the caller's own pre-resolution
    price/pct, byte-identical to every caller's text before this build; no info -> 'n/a'."""
    assert ea.describe_stop(None) == "n/a"
    assert ea.describe_stop(None, fallback_price=0.80, fallback_pct=-0.20) == "0.80 (-20%)"


def _dt(h, m):
    from datetime import datetime, timedelta, timezone
    return datetime(2026, 6, 25, h, m, tzinfo=timezone(timedelta(hours=-4)))


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    class _MP:
        def __init__(self):
            self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo = []

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        mp = _MP()
        try:
            with tempfile.TemporaryDirectory() as td:
                t(Path(td), mp)
            print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
