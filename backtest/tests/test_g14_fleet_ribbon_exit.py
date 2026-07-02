"""G14 fleet coverage: the v15.3 ribbon-flip-back PRIMARY invalidation must reach
FLEET positions, not just the core accounts (2026-07-01).

History: the conductor fix f76ac48 revived heartbeat_core._ribbon_flip_fn (BULL/BEAR
literal mismatch), but fleet_live.manage_tick was still called WITHOUT a
ribbon_flip_back_fn -- so the fleet arms (the only accounts with engine round trips
as of 07-01) had no primary exit. Single source is now exit_actuator.make_ribbon_flip_fn,
consumed by BOTH paths. These guards RED if either wiring or parity regresses.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(FLEET))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import exit_actuator as ea  # noqa: E402

# Producer literals per backtest/lib/ribbon.py -- the ONLY values ribbon_stack takes.
PRODUCER_LITERALS = ("BULL", "BEAR", "MIXED", "WARMUP", "UNKNOWN")


def test_make_ribbon_flip_fn_matrix() -> None:
    """PUT exits on BULL, CALL exits on BEAR; MIXED/WARMUP/UNKNOWN never flip."""
    expected = {
        ("BULL", "P"): True, ("BULL", "C"): False,
        ("BEAR", "P"): False, ("BEAR", "C"): True,
    }
    for stack in PRODUCER_LITERALS:
        fn = ea.make_ribbon_flip_fn(stack)
        assert fn is not None
        for side in ("P", "C"):
            want = expected.get((stack, side), False)
            assert fn("SPY260701P00745000", side) is want, (stack, side)


def test_make_ribbon_flip_fn_absent_stack_fails_open() -> None:
    assert ea.make_ribbon_flip_fn(None) is None
    assert ea.make_ribbon_flip_fn("") is None


def test_core_and_fleet_implementations_agree() -> None:
    """Parity: heartbeat_core._ribbon_flip_fn must behave identically to the shared
    exit_actuator.make_ribbon_flip_fn for every producer literal x side (C14 drift guard)."""
    import heartbeat_core as hc

    for stack in PRODUCER_LITERALS:
        core_fn = hc._ribbon_flip_fn(stack)
        shared_fn = ea.make_ribbon_flip_fn(stack)
        for side in ("P", "C"):
            assert core_fn("X", side) == shared_fn("X", side), (stack, side)


def test_fleet_live_passes_flip_fn_to_manage_tick() -> None:
    """Wiring guard: fleet_live's exit pass must build the flip fn from the shared
    signal's ribbon_stack and pass it into manage_tick (REDs if the kwarg is dropped)."""
    src = (FLEET / "fleet_live.py").read_text(encoding="utf-8")
    assert "make_ribbon_flip_fn" in src, "fleet_live must build the shared ribbon flip fn"
    assert 'ribbon_flip_back_fn=_flip' in src, "fleet_live must pass the flip fn to manage_tick"
    assert '.get("ribbon_stack")' in src, "flip fn must derive from the shared signal's ribbon_stack"
