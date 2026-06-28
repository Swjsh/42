"""FIX1 tests — one-position plan selection + the live bracket built from the SELECTED
strategy's own ExitShape (not a hardcoded -50% / params tp).

Covers:
  * select_plan: REGISTRY-priority among ENTER plans; HOLD fallback; None on empty.
  * decide_arm returns (decision, exit_shape) and the exit_shape is the fired strategy's.
  * _place_live builds stop/TP from the exit shape: stop = mid*(1+premium_stop_pct),
    tp = mid*(1+tp1_premium_pct); invalid/zero stop -> -50% catastrophe cap.
  * pre_plan prefetch + decide_arm pick the SAME (side, strategy, strike) (deterministic).
"""
from __future__ import annotations

import fleet_executor as fx
import fleet_live as fl


# --- fixtures (a multi-strategy signal: one ribbon side + one VWAP side) -------
SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 8}]
PARAMS = {"position_sizing_tiers": SIZING, "per_trade_risk_cap_pct": 0.5,
          "daily_loss_kill_switch_pct": 0.5, "min_contracts": 3,
          "v15_max_premium_pct_of_account": [{"equity_min": 0, "equity_max": 1e9, "max_pct": 0.9}]}
ARM = {"id": "risky-loose", "gate_override": {}}


def _strat_entry(name, side, setup, triggers=("t1", "t2"), quality="BASE", spot=600.0):
    return {"name": name, "side": side, "setup": setup, "triggers": list(triggers),
            "quality": quality, "est_premium": None, "spot": spot}


def _multi_signal():
    """Both strategies fire: ribbon_ride (bull/C) AND vwap_continuation (bear/P)."""
    return {"spot": 600.0, "strategies": [
        _strat_entry("vwap_continuation", "P", "VWAP_CONTINUATION",
                     triggers=["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_PULLBACK"]),
        _strat_entry("ribbon_ride", "C", "BULLISH_RECLAIM_RIDE_THE_RIBBON"),
    ]}


# --- select_plan -------------------------------------------------------------
def test_select_plan_prefers_registry_order():
    """Among ENTER plans, ribbon_ride (REGISTRY[0]) wins over vwap_continuation (REGISTRY[1])."""
    plans = fx.plan_all(ARM, _multi_signal(), 2000.0, PARAMS)
    enters = [p for p in plans if p.action == "ENTER"]
    assert {p.strategy for p in enters} == {"ribbon_ride", "vwap_continuation"}
    sel = fx.select_plan(plans)
    assert sel.action == "ENTER" and sel.strategy == "ribbon_ride"


def test_select_plan_falls_back_to_hold():
    """No ENTER plans (tight gate holds all) -> select_plan returns a HOLD plan (faithful log)."""
    tight = {"id": "tight", "gate_override": {"min_triggers": 99}}
    plans = fx.plan_all(tight, _multi_signal(), 2000.0, PARAMS)
    assert plans and all(p.action == "HOLD" for p in plans)
    sel = fx.select_plan(plans)
    assert sel is not None and sel.action == "HOLD"


def test_select_plan_none_on_empty():
    assert fx.select_plan([]) is None


def test_fleet_live_select_is_the_canonical_one():
    assert fl._select_plan is fx.select_plan


# --- decide_arm returns (decision, exit_shape) -------------------------------
def test_decide_arm_returns_selected_exit_shape():
    decision, exit_shape = fl.decide_arm(
        ARM, _multi_signal(), equity=2000.0, flat=True, day_trades=0, killed=False,
        sod_equity=2000.0, prior_stops=[], params=PARAMS, premium_override=0.40)
    assert decision.action == "ENTER_BULL"  # ribbon_ride C selected
    # ribbon_ride's grind-winner exit shape flows through:
    assert exit_shape["premium_stop_pct"] == -0.20
    assert exit_shape["tp1_premium_pct"] == 1.5
    assert exit_shape["tp1_qty_fraction"] == 0.8
    assert exit_shape["profit_lock_mode"] == "fixed"


def test_decide_arm_vwap_exit_when_only_vwap_fires():
    """Only VWAP fires -> decide_arm selects it and returns the -8% tight-stop exit shape."""
    sig = {"spot": 600.0, "strategies": [
        _strat_entry("vwap_continuation", "C", "VWAP_CONTINUATION",
                     triggers=["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_BREAKOUT"])]}
    decision, exit_shape = fl.decide_arm(
        ARM, sig, equity=2000.0, flat=True, day_trades=0, killed=False,
        sod_equity=2000.0, prior_stops=[], params=PARAMS, premium_override=0.40)
    assert decision.action == "ENTER_BULL"
    assert exit_shape["premium_stop_pct"] == -0.08
    assert exit_shape["tp1_premium_pct"] == 0.3
    assert exit_shape["profit_lock_mode"] == "trailing"


def test_decide_arm_no_signal_returns_tuple():
    decision, exit_shape = fl.decide_arm(
        ARM, None, equity=2000.0, flat=True, day_trades=0, killed=False,
        sod_equity=2000.0, prior_stops=[], params=PARAMS)
    assert decision.action == "HOLD" and exit_shape is None


# --- _place_live builds the bracket from the exit shape ----------------------
class _FakeBroker:
    """Stub broker: returns a fixed mid + records the bracket levels (NO real order)."""
    def __init__(self, mid):
        self.mid = mid
        self.captured = None

    def get_option_mid(self, creds, symbol):
        return self.mid

    def place_bracket(self, creds, *, symbol, qty, limit_price, take_profit_price,
                      stop_price, live, simple_fallback=False):
        self.captured = {"symbol": symbol, "qty": qty, "limit_price": limit_price,
                         "take_profit_price": take_profit_price, "stop_price": stop_price,
                         "live": live, "simple_fallback": simple_fallback}
        return {"id": "fake-order", "status": "accepted"}


def _place_with(monkeypatch, exit_shape, mid=1.00):
    fake = _FakeBroker(mid)
    monkeypatch.setattr(fl.fb, "get_option_mid", fake.get_option_mid)
    monkeypatch.setattr(fl.fb, "place_bracket", fake.place_bracket)
    # Isolate the exit_manager state write _place_live now does on a fill (don't pollute the
    # real fleet dir): redirect the actuator's state root to a throwaway tmp dir for this call.
    import tempfile
    from pathlib import Path
    monkeypatch.setattr(fl.ea, "FLEET_DIR", Path(tempfile.mkdtemp()))
    decision = fx.ArmDecision("risky-loose", "ENTER_BULL", "C", "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                              600, 5, mid, "BASE", "ALLOW", "test")
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 6, 26, 11, 0, tzinfo=timezone(timedelta(hours=-4)))
    res = fl._place_live({}, ARM, decision, exit_shape, {}, PARAMS, now)
    return res, fake


def test_place_live_bracket_matches_ribbon_exit_shape(monkeypatch):
    """stop = mid*(1+premium_stop_pct), tp = mid*(1+tp1_premium_pct), from the exit shape."""
    ribbon_exit = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5,
                   "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
    res, fake = _place_with(monkeypatch, ribbon_exit, mid=1.00)
    assert fake.captured["stop_price"] == 0.80   # 1.00 * (1 - 0.20)
    assert fake.captured["take_profit_price"] == 2.50  # 1.00 * (1 + 1.5)
    # the placement record echoes the strategy's fractions/lock for the EOD layer
    assert res["tp1_qty_fraction"] == 0.8 and res["profit_lock_mode"] == "fixed"
    assert res["placed"] is True


def test_place_live_bracket_matches_vwap_exit_shape(monkeypatch):
    """VWAP's -8% tight stop / +30% TP1 flows through distinctly from ribbon's."""
    vwap_exit = {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.3,
                 "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing"}
    res, fake = _place_with(monkeypatch, vwap_exit, mid=1.00)
    assert fake.captured["stop_price"] == 0.92   # 1.00 * (1 - 0.08)
    assert fake.captured["take_profit_price"] == 1.30  # 1.00 * (1 + 0.30)
    assert res["profit_lock_mode"] == "trailing"


def test_place_live_invalid_stop_falls_back_to_catastrophe_cap(monkeypatch):
    """A zero/None premium_stop_pct -> -50% catastrophe cap, not a too-tight/invalid stop."""
    bad_exit = {"premium_stop_pct": 0, "tp1_premium_pct": 1.5,
                "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
    res, fake = _place_with(monkeypatch, bad_exit, mid=1.00)
    assert fake.captured["stop_price"] == 0.50   # -50% catastrophe cap
    assert res["premium_stop_pct"] == -0.50


def test_place_live_none_exit_shape_uses_catastrophe_cap(monkeypatch):
    """exit_shape None (defensive) -> catastrophe cap stop + params/30% TP fallback."""
    res, fake = _place_with(monkeypatch, None, mid=1.00)
    assert fake.captured["stop_price"] == 0.50


# --- pre_plan prefetch determinism (same selection as decide_arm) ------------
def test_pre_plan_and_decide_arm_pick_same_plan():
    """select_plan is deterministic: the runner's pre_plan prefetch and decide_arm's
    internal selection choose the SAME (side, strategy, strike)."""
    sig = _multi_signal()
    pre = fx.select_plan(fx.plan_all(ARM, sig, 2000.0, PARAMS))
    decision, _ = fl.decide_arm(ARM, sig, equity=2000.0, flat=True, day_trades=0,
                                killed=False, sod_equity=2000.0, prior_stops=[],
                                params=PARAMS, premium_override=0.40)
    assert pre.side == decision.side
    assert pre.strike == decision.strike
    assert pre.strategy == "ribbon_ride"


if __name__ == "__main__":
    import sys
    import types
    # minimal monkeypatch shim for standalone run
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
            if "monkeypatch" in t.__code__.co_varnames[: t.__code__.co_argcount]:
                t(mp)
            else:
                t()
            print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
