"""Tests for the multi-strategy executor pass (plan_all): all strategies on all accounts,
account = gate x sizing only."""
import fleet_executor as fe


def _signal(bull=None, bear=None, spot=598.0):
    return {"spot": spot, "bull": bull or {}, "bear": bear or {}}


def _block(setup, triggers=("t1", "t2"), passed=True, **extra):
    return {"setup_name": setup, "triggers_fired": list(triggers), "passed": passed, **extra}


SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 8}]


def _arm(arm_id="safe-base", gate=None, table=None):
    a = {"id": arm_id, "gate_override": gate or {}}
    if table:
        a["params_patch"] = {"strike_tier_table": table}
    return a


def test_both_strategies_fire_on_one_side():
    # A bull block whose setup is the ribbon reclaim → ribbon_ride fires.
    sig = _signal(bull=_block("BULLISH_RECLAIM_RIDE_THE_RIBBON"))
    plans = fe.plan_all(_arm(), sig, 2000.0, {"position_sizing_tiers": SIZING})
    enters = [p for p in plans if p.action == "ENTER"]
    assert any(p.strategy == "ribbon_ride" and p.side == "C" for p in enters)


def test_strategy_carries_its_own_exit():
    sig = _signal(bear=_block("BEARISH_REJECTION_RIDE_THE_RIBBON"))
    plans = fe.plan_all(_arm(), sig, 2000.0, {"position_sizing_tiers": SIZING})
    p = next(p for p in plans if p.action == "ENTER" and p.strategy == "ribbon_ride")
    assert p.exit_shape["premium_stop_pct"] == -0.20
    assert p.exit_shape["tp1_premium_pct"] == 1.5
    assert p.exit_shape["tp1_qty_fraction"] == 0.8


def test_tight_gate_holds_when_too_few_triggers():
    # tight arm needs >=2 triggers; give it 1 → HOLD, not ENTER.
    sig = _signal(bear=_block("BEARISH_REJECTION_RIDE_THE_RIBBON", triggers=("t1",)))
    plans = fe.plan_all(_arm("safe-tight", gate={"min_triggers": 2}), sig, 2000.0,
                        {"position_sizing_tiers": SIZING})
    assert all(p.action == "HOLD" for p in plans)
    assert any("triggers <" in p.reason for p in plans)


def test_loose_gate_enters_same_signal():
    # same 1-trigger signal, loose arm (no min) → ENTER.
    sig = _signal(bear=_block("BEARISH_REJECTION_RIDE_THE_RIBBON", triggers=("t1",)))
    plans = fe.plan_all(_arm("safe-loose"), sig, 2000.0, {"position_sizing_tiers": SIZING})
    assert any(p.action == "ENTER" for p in plans)


def test_sizing_axis_safe_vs_risky_strike():
    sig = _signal(bull=_block("BULLISH_RECLAIM_RIDE_THE_RIBBON"))
    safe = fe.plan_all(_arm("safe-base", table="safe"), sig, 2000.0, {"position_sizing_tiers": SIZING})
    risky = fe.plan_all(_arm("risky-base", table="bold"), sig, 2000.0, {"position_sizing_tiers": SIZING})
    s = next(p for p in safe if p.action == "ENTER")
    r = next(p for p in risky if p.action == "ENTER")
    # bold/OTM strike for a CALL sits ABOVE the safe/ATM strike (further from spot).
    assert r.strike >= s.strike


def test_no_direction_lock_anywhere():
    # A CALL signal is never silently dropped for a "PUT_ONLY" reason — that concept is gone.
    sig = _signal(bull=_block("BULLISH_RECLAIM_RIDE_THE_RIBBON"))
    plans = fe.plan_all(_arm("risky-loose"), sig, 2000.0, {"position_sizing_tiers": SIZING})
    assert any(p.action == "ENTER" and p.side == "C" for p in plans)


def test_no_fire_when_nothing_passed():
    sig = _signal()  # empty blocks
    assert fe.plan_all(_arm(), sig, 2000.0, {"position_sizing_tiers": SIZING}) == []
