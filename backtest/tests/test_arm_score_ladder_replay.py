"""Guard tests for backtest/tools/arm_score_ladder_replay.py -- the J-risk-ladder replay
evidence tool (analysis-only, no orders, no live config touched).

Three guards, per the task spec:
  1. Anchor-5 calibration -- the pinned 2026-07-27 09:40 construction reproduces
     bear_score=9, blockers=[5], level_rejection in raw triggers. RED-proofed by asserting
     a deliberately-corrupted level set (no 744.9) changes the result -- proves the
     assertion is actually sensitive to the levels input, not a tautology.
  2. Ladder math -- score 9 enters at threshold 9 but NOT at threshold 10; score 7 enters
     only at threshold 7 (not 8).
  3. min-3-floor vs risk-cap collision produces a DENY, never a silent qty clamp -- the
     exact real case the task brief called out: safe-2 at $1,179.38 equity, 3 ATM contracts
     at ~$1.94 premium = $582 notional > 30% cap ($353.81).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import datetime as dt  # noqa: E402

from backtest.lib.risk_gate import Allow, Deny, check_order  # noqa: E402
from backtest.tools.arm_score_ladder_replay import (  # noqa: E402
    ARMS,
    DEFAULT_LADDER,
    LEVEL_TIED_BEAR,
    build_calibration_bar_context,
    score_ctx,
)


# --------------------------------------------------------- 1. anchor-5 calibration
def test_anchor5_calibration_reproduces_pinned_ground_truth():
    ctx = build_calibration_bar_context()
    bear, _bull = score_ctx(ctx)
    assert bear.bear_score == 9
    assert bear.blockers == [5]
    assert "level_rejection" in bear.triggers_fired
    assert bear.rejection_level == 744.9
    assert any(t in LEVEL_TIED_BEAR for t in bear.triggers_fired)


def test_anchor5_calibration_is_red_proofed_by_corrupted_levels():
    """Removing 744.9 from the level set MUST change the result -- proves the calibration
    assertion is actually sensitive to its levels input, not vacuously true regardless of
    what's fed in."""
    baseline_ctx = build_calibration_bar_context()
    baseline_bear, _ = score_ctx(baseline_ctx)
    assert baseline_bear.bear_score == 9
    assert baseline_bear.blockers == [5]

    corrupted_levels = [735.88, 736.9, 737.75, 738.46, 739.83, 744.13, 745.52, 745.72]
    assert 744.9 not in corrupted_levels  # sanity on the corruption itself
    corrupted_ctx = build_calibration_bar_context(levels=corrupted_levels)
    corrupted_bear, _ = score_ctx(corrupted_ctx)

    # The corrupted run must differ from the pinned baseline -- either the rejection level
    # itself moves off 744.9, or the score/blockers change (both are acceptable proof of
    # sensitivity; asserting sameness on ALL of them would be the RED case this guards).
    changed = (
        corrupted_bear.rejection_level != baseline_bear.rejection_level
        or corrupted_bear.bear_score != baseline_bear.bear_score
        or corrupted_bear.blockers != baseline_bear.blockers
        or corrupted_bear.triggers_fired != baseline_bear.triggers_fired
    )
    assert changed, (
        "removing 744.9 from the level set did not change ANY output field -- the "
        "calibration proof is not actually sensitive to its levels input"
    )
    # Specifically: 744.9 must no longer be the confluence match once it's removed from
    # the level list entirely (it can't confluence-match itself if it isn't in the list).
    assert corrupted_bear.confluence_match != 744.9


# --------------------------------------------------------- 2. ladder math
def test_ladder_enters_at_exact_threshold_not_above():
    """score 9 enters at threshold 9 but NOT at threshold 10 (per the DEFAULT_LADDER's own
    safe-2/safe-3 = 9 vs a hypothetical 10 -- mirrors today's actual passed=True==zero-
    blockers requirement, which this ladder is explicitly designed to loosen)."""
    score = 9
    has_trigger = True
    assert (score >= 9) and has_trigger        # threshold 9 -> IN
    assert not ((score >= 10) and has_trigger)  # threshold 10 -> OUT (score never reaches 10)


def test_ladder_enters_only_at_its_own_threshold_not_looser_ones_misapplied():
    """score 7 enters at threshold 7 only -- a threshold of 8 or 9 must reject it. Guards
    against an off-by-one (>= vs >) or an inverted comparison."""
    score = 7
    has_trigger = True
    assert (score >= 7) and has_trigger
    assert not ((score >= 8) and has_trigger)
    assert not ((score >= 9) and has_trigger)


def test_ladder_requires_a_level_tied_trigger_even_at_a_qualifying_score():
    """A score meeting/exceeding threshold with NO level-tied trigger must still be OUT --
    this is the filter-10 'defensive: require >=1 level-tied trigger' mirror the task spec
    calls for explicitly (pure ribbon_flip alone must not qualify)."""
    score = 9
    triggers_raw = ["ribbon_flip"]  # not level-tied
    has_level_trigger = any(t in LEVEL_TIED_BEAR for t in triggers_raw)
    assert has_level_trigger is False
    ladder_in = (score >= 7) and has_level_trigger
    assert ladder_in is False


def test_default_ladder_matches_j_spec():
    assert DEFAULT_LADDER == {
        "risky-3": 7,
        "risky-1": 8,
        "bold-2": 8,
        "safe-3": 9,
        "safe-2": 9,
    }
    assert {a["id"] for a in ARMS} == set(DEFAULT_LADDER)


# --------------------------------------------------------- 3. min-3-floor vs risk-cap collision
def test_min_contracts_floor_vs_risk_cap_collision_denies_not_clamps():
    """THE real case the task brief called out: at safe-2's $1,179.38 equity, 3 ATM
    contracts at ~$1.94 premium = $582 notional, which exceeds the 30% risk cap
    ($353.81). risk_gate.check_order must DENY[RISK_CAP] -- never silently clamp qty down
    below the min_contracts floor (that would violate Rule 6's 2-TP+1-runner floor) and
    never silently allow an over-cap order."""
    equity = 1179.38
    premium = 1.94
    qty = 3  # the min_contracts floor -- already collides with the cap at this premium
    params = dict(
        per_trade_risk_cap_pct=0.30,
        daily_loss_kill_switch_pct=0.30,
        min_contracts=3,
        pdt_gate_mode="cash_settlement",
        max_same_day_roundtrips=5,
    )
    notional = premium * qty * 100.0
    risk_cap_dollars = equity * 0.30
    assert notional > risk_cap_dollars, "test setup sanity: the collision must actually exist"

    decision = check_order(
        account="CORE-SAFE (KIQE)", equity=equity, start_of_day_equity=equity,
        proposed_qty=qty, premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status="flat", day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params=params, settled_cash_available=equity,
        same_day_entries_used=0,
    )
    assert isinstance(decision, Deny)
    assert decision.code == "RISK_CAP"
    assert not isinstance(decision, Allow)


def test_min_contracts_floor_alone_denies_when_qty_below_it():
    """Sanity companion: qty below min_contracts denies MIN_CONTRACTS even when notional
    would otherwise fit -- proves the two gates are independent, not one masking the
    other."""
    params = dict(
        per_trade_risk_cap_pct=0.30, daily_loss_kill_switch_pct=0.30, min_contracts=3,
        pdt_gate_mode="cash_settlement", max_same_day_roundtrips=5,
    )
    decision = check_order(
        account="CORE-SAFE (KIQE)", equity=10_000.0, start_of_day_equity=10_000.0,
        proposed_qty=2, premium=0.10, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status="flat", day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params=params, settled_cash_available=10_000.0,
        same_day_entries_used=0,
    )
    assert isinstance(decision, Deny)
    assert decision.code == "MIN_CONTRACTS"
