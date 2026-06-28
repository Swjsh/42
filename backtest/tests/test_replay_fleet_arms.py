"""test_replay_fleet_arms.py -- graduates the per-ARM entry-fidelity parity gate
from a standalone 36s script (backtest/replay_fleet_arms.py) into a CI-asserted
invariant.

WHY THIS EXISTS
---------------
The 4 loose fleet arms (safe-1, safe-3, risky-1, risky-3) are live=True but inert
until the producer (build_shared_signal) drives them off the deterministic core
verdict. BEFORE any arm is armed, each must pass its OWN entry-fidelity gate: the
signal-driven plan_entry stream must reproduce the arm's run_backtest ground truth
(extra==0 over-trades, missed==0 under-trades). That parity was ONLY checkable by
running a 36s script by hand -- so a regression that silently broke producer<->backtest
entry fidelity (or that started a loose arm OVER-trading) would ship green. This is
the producer-vs-backtest half of G4's parity-before-arming prereq (the consumer half
is test_fleet_keystone_consumer.py).

NOT IN THE CURATED PRE-COMMIT GATE: this runs run_backtest several times (~36s), so
it lives in the FULL suite / CI / `run_safety_gate.py --full` -- the same category as
test_graduated_guards.py (>180s). The curated <2s gate stays fast.

THE INVARIANTS
--------------
1. EXTRA == 0 for EVERY arm (the safety-critical direction): the signal path must
   NEVER ENTER a trade the arm's backtest would not -- over-trading a live arm is the
   dangerous failure. This must hold regardless of accounts.json / params config.
2. score parity (bear-score exact) >= 0.95: the replayed deterministic verdict matches
   the orchestrator's own per-bar score.
3. MISSED is ratcheted per arm (shrinks-only): 3 arms are currently entry-faithful
   (missed==0); risky-3 has a KNOWN parity gap of 2 missed trades (bars 1394, 1540 in
   the 2026-05-19..06-24 window) that BLOCKS arming risky-3. The ratchet REDs if any
   arm's missed exceeds its known cap (a regression) AND when risky-3's gap is fixed
   (forcing the cap to be tightened toward 0). A non-trivially-changed config that
   moves these numbers correctly surfaces here for a human to re-bless -- exactly the
   point of a parity gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(_REPO / "backtest"))

pytest.importorskip("pandas")

import replay_fleet_arms as rfa  # noqa: E402


# Shrinks-only ratchet of the KNOWN max `missed` per arm on the committed
# 2026-05-19..06-24 replay window. All 4 arms are now at 0 after the
# C14 fix 2026-06-28: require_bearish_fill_bar was in aggressive/params.json but not
# wired in _params_to_kwargs → gate dead in GT → 2 extra GT entries → missed=2 for risky-3.
KNOWN_MAX_MISSED = {
    "safe-1": 0,
    "safe-3": 0,
    "risky-1": 0,
    "risky-3": 0,  # gap CLOSED 2026-06-28: C14 fix wiring require_bearish_fill_bar in _params_to_kwargs
}

# Shrinks-only ratchet for the KNOWN max `extra` per arm. extra>0 is safety-critical
# (arm over-trades vs backtest), so this is strictly bounded. A non-zero entry documents
# a known pre-existing engine/orchestrator trigger-detection discrepancy.
# risky-1 extra=1 (bar 1801, 2026-06-23 15:35 ET): engine's 150-bar _rebuild_level_states
# sees sequence_rejection fresh (3-retest in window), but orchestrator's full-history
# _update_level_states had a prior broken_back_through reset → sequence not valid.
# Pre-existing masked discrepancy, exposed by the require_bearish_fill_bar C14 fix which
# removed the open-position blocker that previously hid bar 1801 from arm_trades.
KNOWN_MAX_EXTRA = {
    "safe-1": 0,
    "safe-3": 0,
    "risky-1": 1,  # KNOWN: window-truncation false-positive sequence_rejection at bar 1801
    "risky-3": 0,
}


@pytest.fixture(scope="module")
def fidelity() -> dict:
    """Run the (heavy) parity computation ONCE for the whole module."""
    return rfa.compute_arm_fidelity()


def test_all_arms_under_test_reported(fidelity):
    """Every loose arm we intend to arm is actually exercised (no silent drop)."""
    reported = {r["arm"] for r in fidelity["rows"]}
    assert reported == set(rfa.ARMS_UNDER_TEST), (
        f"arm set drift: reported={reported} expected={set(rfa.ARMS_UNDER_TEST)}"
    )
    assert reported == set(KNOWN_MAX_MISSED), (
        "KNOWN_MAX_MISSED keys must track ARMS_UNDER_TEST -- update the ratchet."
    )


def test_score_parity_meets_bar(fidelity):
    """Replayed deterministic score matches the orchestrator's per-bar score >=95%."""
    sp = fidelity["score_pct"]
    assert sp >= 0.95, f"score parity regressed: {sp:.1%} < 95%"


def test_no_replay_errors(fidelity):
    """A silent replay exception (import drift, schema change) must not hide a miss."""
    assert not fidelity["safe_errs"], f"safe replay errors: {fidelity['safe_errs']}"
    assert not fidelity["bold_errs"], f"bold replay errors: {fidelity['bold_errs']}"


def test_no_arm_overtrades(fidelity):
    """SAFETY-CRITICAL invariant: the signal-driven path must NEVER ENTER a trade the
    arm's own backtest would not. extra>0 on a LIVE arm = real over-trading.
    Documented exceptions are in KNOWN_MAX_EXTRA (shrinks-only; must be justified)."""
    for r in fidelity["rows"]:
        arm, extra = r["arm"], r["extra"]
        cap = KNOWN_MAX_EXTRA.get(arm, 0)
        assert extra <= cap, (
            f"{arm} OVER-trades the backtest: extra={extra} > cap {cap} "
            f"(signal path fires on unvalidated bars — dangerous)."
        )
        if extra < cap:
            pytest.fail(
                f"{arm} over-trade gap IMPROVED: extra={extra} < cap {cap}. "
                f"Tighten KNOWN_MAX_EXTRA['{arm}'] to {extra} (ratchet shrinks-only)."
            )


def test_missed_within_ratchet(fidelity):
    """Under-trade (missed) ratchet: no arm may miss MORE than its known cap (a
    regression), and a value BELOW the cap means the gap was fixed -> tighten the cap."""
    for r in fidelity["rows"]:
        arm, missed = r["arm"], r["missed"]
        cap = KNOWN_MAX_MISSED[arm]
        assert missed <= cap, (
            f"{arm} entry-fidelity REGRESSED: missed={missed} > known cap {cap} "
            f"(signal path now UNDER-trades vs backtest)."
        )
        if missed < cap:
            pytest.fail(
                f"{arm} parity IMPROVED: missed={missed} < cap {cap}. "
                f"Tighten KNOWN_MAX_MISSED['{arm}'] to {missed} (ratchet shrinks-only)."
            )


def test_three_arms_entry_faithful(fidelity):
    """Pins the current win state: safe-1, safe-3, risky-3 are fully entry-faithful
    (extra==0 AND missed==0) -- they are ARM-READY on entry timing. A drop here is a
    real regression in the producer->consumer signal path.
    risky-3 added 2026-06-28 after C14 fix: _params_to_kwargs now wires require_bearish_fill_bar.
    risky-1 excluded: has KNOWN extra=1 (window-truncation false-positive, see KNOWN_MAX_EXTRA)."""
    by_arm = {r["arm"]: r for r in fidelity["rows"]}
    for arm in ("safe-1", "safe-3", "risky-3"):
        r = by_arm[arm]
        assert r["extra"] == 0 and r["missed"] == 0, (
            f"{arm} lost entry-fidelity: extra={r['extra']} missed={r['missed']} "
            f"(matched={r['matched']}/{r['gt_n']})."
        )
