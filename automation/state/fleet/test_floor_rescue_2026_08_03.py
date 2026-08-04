"""test_floor_rescue_2026_08_03.py -- guards for the L246-class ORDERING FIX:
the full-send rescue lane must not be shadowed by the doomed plan it exists to rescue.

THE DEFECT (EOD-2026-08-03-FULL-REVIEW.md section 4.2): plan_all's full-send precondition
("no ENTER in plans") runs at PLAN time, but the $0.30 min_entry_premium floor that kills a
doomed OTM plan runs later, in finalize(), once a real premium exists. A cohort-vetoed tick
whose score clears the scoring peak produces a NORMAL-lane ENTER plan at the arm's own OTM
tier; that plan dies at the floor -- and the full-send lane, checked earlier, never fired.
Result: 0 full-send fires EVER vs 35 floor-blocks on 2026-08-03 alone.

THE FIX: fleet_live.decide_arm, on a SKIP_MIN_PREMIUM_FLOOR verdict for the selected plan,
asks fleet_executor.floor_rescue_plan for the full-send plan plan_all suppressed, prices the
rescue's OWN (ATM-class) strike via an injected rescue_premium_fetch, and finalizes THAT.
Every downstream risk guard (floor included) binds on the rescue verbatim -- the floor is
NEVER bypassed, only re-asked at a strike that can honestly clear it.

RED-PROOF (recorded): this file was written BEFORE the fix and run against the pre-fix code
-- the integration tests failed with the pre-fix HOLD/SKIP_MIN_PREMIUM_FLOOR verdicts, then
passed after the fix, unchanged.

$0, offline, pure unit tests. Run:
    backtest/.venv/Scripts/python.exe -m pytest automation/state/fleet/test_floor_rescue_2026_08_03.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

FLEET = Path(__file__).resolve().parent
REPO = FLEET.parents[2]
sys.path.insert(0, str(FLEET))
sys.path.insert(0, str(REPO / "backtest"))

import build_shared_signal as bss  # noqa: E402
import fleet_executor as fx  # noqa: E402
import fleet_live as fl  # noqa: E402

ACCOUNTS = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                         .read_text(encoding="utf-8"))
EQUITY = 5000.0  # today's real rebuilt-arm equity -- the exact tier where the defect bit
FULL_SEND_ARM_ID = "risky-1"
SUB_FLOOR = 0.11        # a real premium from today's 35 floor-kill rows
ATM_PREMIUM = 0.55      # a floor-clearing ATM premium (754C traded 0.37-0.38 at 09:42)


def _arm(arm_id: str) -> dict:
    for a in ACCOUNTS["arms"]:
        if a["id"] == arm_id:
            return a
    raise AssertionError(f"arm {arm_id} missing from accounts.json")


def _vetoed_core_row(verdict: str = "SKIP_ELITE_BULL_LEVEL_RECLAIM",
                     bull_score: int = 11) -> dict:
    """A cohort-vetoed core row at score 11 -- ABOVE the scoring peak (bull >= 9), so the
    producer's score-peak lane rescues it into the NORMAL strategies[] path. That is the
    2026-08-03 shape: a normal ENTER plan exists (and will floor-die at OTM premium) AND the
    full_send block is available on the SAME tick. bull_score=7 (below peak) is the
    OLD test_full_send_arm.py fixture where plan_all's own lane already worked."""
    return {
        "ts_et": "2026-08-03T13:23:02-04:00", "account": "bold", "spy": 744.10,
        "ribbon": "BULL", "spread_cents": 12, "vix": 15.9, "htf_15m": "BULL",
        "verdict": verdict, "action": verdict, "side": "C",
        "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "bear_score": 2, "bull_score": bull_score,
        "triggers": ["level_reclaim", "confluence"],
        "trigger_level_exact": 743.25,
        "bull_reclaim_level_raw": 743.25, "bear_rejection_level_raw": None,
    }


def _signal_from(row: dict) -> dict:
    import datetime as dt
    mapped = bss._map_core_row(row)
    now = dt.datetime(2026, 8, 3, 13, 23, tzinfo=bss.ET)
    return bss.build_from_rows(mapped, now, bold_row=mapped, probe_row=mapped,
                               run_vwap=False, write=False)


def _decide(arm_id: str = FULL_SEND_ARM_ID, *, sig=None, premium_override=SUB_FLOOR,
            fetch=lambda side, strike: ATM_PREMIUM, flat=True, killed=False,
            day_trades=0, params=None):
    sig = sig if sig is not None else _signal_from(_vetoed_core_row())
    return fl.decide_arm(_arm(arm_id), sig, equity=EQUITY, flat=flat,
                         day_trades=day_trades, killed=killed, sod_equity=EQUITY,
                         prior_stops=[], params=(params or BOLD_PARAMS),
                         premium_override=premium_override,
                         rescue_premium_fetch=fetch)


# --------------------------------------------------------------------------------------
# Fixture non-vacuity: the defect scenario must genuinely exist in this signal
# --------------------------------------------------------------------------------------
def test_fixture_reproduces_the_defect_shape():
    """The score-11 vetoed tick must yield BOTH a normal-lane ENTER plan (which the floor
    will kill) AND an available full_send block -- today's exact conjunction. If either half
    vanishes, every test below is vacuous."""
    sig = _signal_from(_vetoed_core_row())
    assert sig["full_send"]["bull"]["available"] is True, "full_send block must be available"
    plans = fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, BOLD_PARAMS)
    enters = [p for p in plans if p.action == "ENTER"]
    assert enters, "normal lane must produce an ENTER plan (score-peak rescued)"
    assert not str(enters[0].reason).startswith("FULL_SEND"), (
        "the ENTER must come from the NORMAL lane -- plan_all's own full-send lane firing "
        "here would mean the shadowing precondition changed shape; re-derive this fixture")


# --------------------------------------------------------------------------------------
# THE HEADLINE: floor-killed normal plan un-shadows the full-send rescue
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("verdict", ["SKIP_ELITE_BULL_LEVEL_RECLAIM",
                                     "SKIP_CONF_LVL_REC_AFTERNOON"])
def test_floor_killed_normal_plan_is_rescued_by_full_send(verdict):
    """PRE-FIX: HOLD/SKIP_MIN_PREMIUM_FLOOR (the 2026-08-03 row, 35x). POST-FIX: the rescue
    enters at the ATM strike with the ATM premium. Parametrized across two allowlisted
    cohorts -- the fix is the LANE's, not elite-specific."""
    sig = _signal_from(_vetoed_core_row(verdict))
    decision, exit_shape = _decide(sig=sig)
    assert decision.action == "ENTER_BULL", (
        f"expected the rescue ENTER, got {decision.action} risk_code={decision.risk_code} "
        f"reason={decision.reason!r} -- the pre-fix shadowing verdict")
    assert decision.risk_code == "ALLOW"
    assert str(decision.reason).startswith("FULL_SEND cohort="), "fill attribution tag"
    assert "floor_rescue" in str(decision.reason), "post-floor rescue must be audit-tagged"
    assert decision.premium == ATM_PREMIUM, "rescue must be risk-gated at ITS OWN premium"
    # strike is the ATM/PROBE table pick, not the arm's own OTM tier
    spot = float(sig["spot"])
    atm = fx.strike_selection.pick_strike(spot, EQUITY, "C", fx.PROBE_STRIKE_TIERS)
    own = fx.strike_selection.pick_strike(spot, EQUITY, "C",
                                          fx._tiers_for_arm(_arm(FULL_SEND_ARM_ID)))
    assert atm != own, "vacuous fixture: the two tables must differ at $5K"
    assert decision.strike == atm
    assert decision.qty == int(BOLD_PARAMS["min_contracts"]), "rescue is min-size, always"
    assert exit_shape is not None, "the rescue's own exit shape must ride to placement"


def test_vary_and_assert_non_full_send_arm_is_untouched():
    """C14: the identical floor-kill on an arm WITHOUT gate_override.full_send must keep the
    pre-fix verdict byte-for-byte (HOLD/SKIP_MIN_PREMIUM_FLOOR, no rescue annotation)."""
    decision, _ = _decide("risky-3")
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"
    assert "floor_rescue" not in str(decision.reason)
    assert "FULL_SEND" not in str(decision.reason)


def test_vary_and_assert_surviving_normal_plan_is_never_displaced():
    """A normal plan whose premium CLEARS the floor must place exactly as before -- the
    rescue only ever fires on a floor corpse, never beside a live plan (one-position rule)."""
    decision, _ = _decide(premium_override=0.55)
    assert decision.risk_code == "ALLOW"
    assert not str(decision.reason).startswith("FULL_SEND"), (
        "normal-lane ALLOW must stay the normal lane's")


# --------------------------------------------------------------------------------------
# THE FLOOR IS NEVER BYPASSED -- and every downstream risk guard binds on the rescue
# --------------------------------------------------------------------------------------
def test_rescue_priced_below_floor_is_killed_by_the_same_floor():
    """If even the ATM strike prices under $0.30, the rescue dies at the SAME floor and the
    original verdict stands (annotated). The floor is re-asked, never bypassed."""
    decision, _ = _decide(fetch=lambda side, strike: 0.12)
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"
    assert "floor_rescue denied" in str(decision.reason), "the attempt must be visible"


def test_rescue_fetch_failure_fails_closed():
    """No quote for the rescue strike -> premium None -> risk_gate UNREADABLE_INPUT deny ->
    original floor verdict stands. A rescue must never place on a guessed premium."""
    decision, _ = _decide(fetch=lambda side, strike: None)
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"
    assert "floor_rescue denied" in str(decision.reason)


def test_rescue_fetch_exception_fails_closed():
    def _boom(side, strike):
        raise RuntimeError("quote endpoint down")
    decision, _ = _decide(fetch=_boom)
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"


def test_no_fetcher_supplied_fails_closed_not_open():
    """Callers that don't inject a fetcher (older call sites, run_dry) get NO rescue ALLOW:
    premium None -> UNREADABLE_INPUT. The lane never trades blind."""
    decision, _ = _decide(fetch=None)
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"


def test_not_flat_still_blocks_the_rescue():
    """Rule 4: the floor check in finalize runs BEFORE check_order, so a sub-floor premium
    masks NOT_FLAT on the normal plan -- the rescue's own finalize must then catch it."""
    decision, _ = _decide(flat=False)
    assert decision.action == "HOLD"
    assert "floor_rescue denied: NOT_FLAT" in str(decision.reason)


def test_kill_switch_still_blocks_the_rescue():
    decision, _ = _decide(killed=True)
    assert decision.action == "HOLD"
    assert "floor_rescue denied: KILL_SWITCH" in str(decision.reason)


def test_pdt_still_blocks_the_rescue():
    decision, _ = _decide(day_trades=3)
    assert decision.action == "HOLD"
    assert "floor_rescue denied: PDT" in str(decision.reason)


# --------------------------------------------------------------------------------------
# The pure eligibility function
# --------------------------------------------------------------------------------------
def _floor_decision(plan):
    return fx.ArmDecision(plan.arm_id, "HOLD", plan.side, plan.setup_name, plan.strike,
                          plan.qty, SUB_FLOOR, plan.quality, "SKIP_MIN_PREMIUM_FLOOR",
                          f"premium {SUB_FLOOR} < min_entry_premium floor 0.3")


def test_floor_rescue_plan_returns_the_full_send_plan():
    sig = _signal_from(_vetoed_core_row())
    arm = _arm(FULL_SEND_ARM_ID)
    killed = [p for p in fx.plan_all(arm, sig, EQUITY, BOLD_PARAMS) if p.action == "ENTER"][0]
    rescue = fx.floor_rescue_plan(arm, sig, EQUITY, BOLD_PARAMS, killed, _floor_decision(killed))
    assert rescue is not None and rescue.action == "ENTER"
    assert str(rescue.reason).startswith("FULL_SEND cohort=")


def test_floor_rescue_never_rescues_a_rescue():
    """A floor-killed FULL_SEND/PROBE/SCORE_LADDER plan is terminal -- no self-rescue loop."""
    sig = _signal_from(_vetoed_core_row())
    arm = _arm(FULL_SEND_ARM_ID)
    for tag in ("FULL_SEND cohort=x", "PROBE_ARM cohort=y", "SCORE_LADDER floor=7 score=8"):
        fake = fx.EntryPlan("risky-1", "ENTER", "C", "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                            744, 5, "ELITE", tag, strategy="ribbon_ride")
        assert fx.floor_rescue_plan(arm, sig, EQUITY, BOLD_PARAMS, fake,
                                    _floor_decision(fake)) is None


def test_floor_rescue_requires_the_floor_verdict():
    """Any other deny code (RISK_CAP, NOT_FLAT, ...) is NOT this fix's business."""
    sig = _signal_from(_vetoed_core_row())
    arm = _arm(FULL_SEND_ARM_ID)
    killed = [p for p in fx.plan_all(arm, sig, EQUITY, BOLD_PARAMS) if p.action == "ENTER"][0]
    other = fx.ArmDecision(killed.arm_id, "HOLD", killed.side, killed.setup_name,
                           killed.strike, killed.qty, 2.0, killed.quality, "RISK_CAP",
                           "risk_gate denied: notional over cap")
    assert fx.floor_rescue_plan(arm, sig, EQUITY, BOLD_PARAMS, killed, other) is None


def test_floor_rescue_requires_full_send_opt_in():
    sig = _signal_from(_vetoed_core_row())
    for arm in ACCOUNTS["arms"]:
        if arm.get("status") != "active" or arm["id"] == FULL_SEND_ARM_ID:
            continue
        plans = [p for p in fx.plan_all(arm, sig, EQUITY, BOLD_PARAMS) if p.action == "ENTER"]
        if not plans:
            continue
        assert fx.floor_rescue_plan(arm, sig, EQUITY, BOLD_PARAMS, plans[0],
                                    _floor_decision(plans[0])) is None


def test_floor_rescue_requires_an_available_full_send_block():
    """Post-SHIP-B reality: a tick with no cohort veto emits an empty full_send block --
    nothing to rescue, original verdict stands."""
    sig = _signal_from(_vetoed_core_row())
    sig = {**sig, "full_send": {"bull": dict(bss._FULL_SEND_EMPTY),
                                "bear": dict(bss._FULL_SEND_EMPTY)}}
    arm = _arm(FULL_SEND_ARM_ID)
    killed = [p for p in fx.plan_all(arm, sig, EQUITY, BOLD_PARAMS) if p.action == "ENTER"][0]
    assert fx.floor_rescue_plan(arm, sig, EQUITY, BOLD_PARAMS, killed,
                                _floor_decision(killed)) is None
    decision, _ = _decide(sig=sig)
    assert decision.action == "HOLD" and decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"
