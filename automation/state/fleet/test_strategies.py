"""Unit tests for the shared strategy registry."""
import strategies as S


def _block(setup, triggers=("t1",), passed=True):
    return {"setup_name": setup, "triggers_fired": list(triggers), "passed": passed}


def test_ribbon_ride_fires_on_its_setups():
    assert S.RIBBON_RIDE in S.fired(_block("BEARISH_REJECTION_RIDE_THE_RIBBON"))
    assert S.RIBBON_RIDE in S.fired(_block("BULLISH_RECLAIM_RIDE_THE_RIBBON"))


def test_vwap_fires_on_its_setup():
    got = S.fired(_block("VWAP_CONTINUATION"))
    assert S.VWAP_CONTINUATION in got


def test_no_fire_when_not_passed():
    assert S.fired(_block("BEARISH_REJECTION_RIDE_THE_RIBBON", passed=False)) == []


def test_no_fire_without_triggers():
    assert S.fired(_block("BEARISH_REJECTION_RIDE_THE_RIBBON", triggers=())) == []


def test_unknown_setup_fires_nothing():
    assert S.fired(_block("SOME_RANDOM_SETUP")) == []


def test_exit_shape_is_grind_winner():
    e = S.RIBBON_RIDE.exit
    assert e.premium_stop_pct == -0.20
    assert e.tp1_premium_pct == 1.5
    assert e.tp1_qty_fraction == 0.8
    assert e.profit_lock_mode == "fixed"


def test_strategies_are_direction_agnostic():
    # No strategy carries a direction lock — that was the bug we removed.
    for s in S.REGISTRY:
        assert not hasattr(s, "direction_lock")


def test_by_name():
    assert S.by_name("ribbon_ride") is S.RIBBON_RIDE
    assert S.by_name("nope") is None
