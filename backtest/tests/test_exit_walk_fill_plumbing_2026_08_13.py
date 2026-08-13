"""Guard: the fill-model plumbing is INERT by default (prereg FILL-MODEL-UNIFICATION-2026-08-13).

WHAT WAS ADDED. walk_exit_manager and _fill_price gained two parameters:
    exit_slippage    (default DEFAULT_EXIT_SLIPPAGE = 0.02)
    all_exits_market (default False)

WHY. The frozen prereg's STEP 1 is "fix the fill model with the slippage constants UNCHANGED, and
publish the A-only delta". That was UN-RUNNABLE: DEFAULT_EXIT_SLIPPAGE was a module constant and
there was no switch for the market-vs-limit split, so neither arm could be expressed. The prereg
named this as the blocker in as many words. This is that plumbing.

THE INVARIANT THIS FILE EXISTS TO HOLD: adding the ability to run the treatment arm must not, by
itself, move a single historical number. ~95 files call walk_exit_manager; if the defaults drifted,
every one of their cells would shift in the same commit that introduced the switch -- which is
exactly the laundering the prereg forbids ("A SIGN FLIP IS NOT A RESURRECTION").

So the default arm is pinned by VALUE, not by inspection. If someone flips the default to close the
optimism gap, this file goes RED and forces that flip to happen in the prereg'd commit that also
carries the re-baseline and the fee model -- together, in the mandated order, or not at all.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WALK_PATH = REPO / "backtest" / "lib" / "exit_manager_walk.py"


@pytest.fixture(scope="module")
def emw():
    sys.path.insert(0, str(REPO / "backtest" / "lib"))
    spec = importlib.util.spec_from_file_location("_emw_plumbing_probe", WALK_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_emw_plumbing_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------- the default must not move


@pytest.mark.parametrize("stage,level,close,expected", [
    # limit-style stages: fill EXACTLY at the level, no slippage (today's behaviour)
    ("tp1", 1.30, 1.10, 1.30),
    ("runner_target", 2.50, 1.10, 2.50),
    ("premium_stop", 0.50, 1.10, 0.50),
    ("profit_lock_floor", 0.80, 1.10, 0.80),
    ("trail", 0.90, 1.10, 0.90),
    ("be_stop", 1.00, 1.10, 1.00),
    # market-style stages: close minus the 0.02 default
    ("time_stop", None, 1.10, 1.08),
    ("ribbon_flip", None, 1.10, 1.08),
    ("structure_stop", None, 1.10, 1.08),
])
def test_default_arm_is_byte_identical_to_pre_plumbing(emw, stage, level, close, expected):
    """THE REGRESSION. Every one of the 9 stages, pinned by value. A drift here means ~95 calling
    files' historical cells moved without a prereg."""
    got = emw._fill_price(stage, level, close)
    assert got == pytest.approx(expected, abs=1e-9), (
        f"{stage} default fill changed to {got}, expected {expected}. If this was the intentional "
        "fill-model fix, it must land in the prereg'd commit WITH the slippage re-baseline and "
        "the fee model, in the mandated order -- not as a default flip.")


def test_the_six_zero_slippage_stages_are_still_six(emw):
    """Pins the size of the gap so a partial fix is visible as partial."""
    stages = {"tp1": 1.30, "runner_target": 2.50, "premium_stop": 0.50,
              "profit_lock_floor": 0.80, "trail": 0.90, "be_stop": 1.00}
    exact = [s for s, lvl in stages.items() if emw._fill_price(s, lvl, 1.10) == lvl]
    assert len(exact) == 6, f"expected 6 zero-slippage stages, found {len(exact)}: {exact}"


# --------------------------------------------------------------- both arms are expressible


def test_the_STEP1_treatment_arm_can_actually_be_run(emw):
    """all_exits_market=True is the A-arm: every stage market-fills, which is what live does."""
    assert emw._fill_price("tp1", 1.30, 1.10, all_exits_market=True) == pytest.approx(1.08)
    assert emw._fill_price("premium_stop", 0.50, 1.10, all_exits_market=True) == pytest.approx(1.08)
    assert emw._fill_price("time_stop", None, 1.10, all_exits_market=True) == pytest.approx(1.08)


def test_the_slippage_constant_is_now_overridable(emw):
    """STEP 2 needs this; without it the re-baseline could only be done by editing a module
    constant, which is un-A/B-able."""
    assert emw._fill_price("time_stop", None, 1.10, exit_slippage=0.01) == pytest.approx(1.09)
    assert emw._fill_price("time_stop", None, 1.10, exit_slippage=0.00) == pytest.approx(1.10)


def test_walk_exit_manager_exposes_both_parameters(emw):
    """The resolver alone is not enough -- the public entry point ~95 files call must accept them,
    or the arms still cannot be run end to end."""
    params = inspect.signature(emw.walk_exit_manager).parameters
    for name, default in (("exit_slippage", emw.DEFAULT_EXIT_SLIPPAGE),
                          ("all_exits_market", False)):
        assert name in params, f"walk_exit_manager does not accept {name}"
        assert params[name].default == default, (
            f"walk_exit_manager's {name} default is {params[name].default}, expected {default} -- "
            "a changed default moves every caller's numbers silently")


def test_the_positive_price_floor_survives_both_arms(emw):
    """A deep stop minus slippage must never produce a non-positive fill."""
    assert emw._fill_price("time_stop", None, 0.01) >= 0.01
    assert emw._fill_price("tp1", 0.01, 0.01, all_exits_market=True) >= 0.01
    assert emw._fill_price("time_stop", None, 1.00, exit_slippage=5.0) >= 0.01


def test_the_prereg_that_authorises_this_exists(emw):
    """Plumbing without its prereg is just an unexplained switch. If the prereg is deleted, the
    justification for these parameters is gone and they should be too."""
    prereg = REPO / "analysis" / "recommendations" / "prereg-fill-model-unification-2026-08-13.json"
    assert prereg.exists(), "the prereg authorising this plumbing is missing"
    assert "FILL-MODEL-UNIFICATION-2026-08-13" in WALK_PATH.read_text(encoding="utf-8"), (
        "the module no longer cites the prereg that authorises these parameters")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
