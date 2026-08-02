"""SHRINK-NOT-DENY (2026-08-03 ship) -- guards for fleet_executor._shrink_qty_to_affordable
and its wiring into finalize(), immediately before risk_gate.check_order.

WHY THIS EXISTS: SIZING-SCALING-DECISION-2026-08-03.md proved fleet_executor's
position_sizing_tiers mechanism is DENY-not-shrink -- a tiered qty too big for the per-trade
cap gets refused WHOLESALE instead of sized down to the largest legal amount, and this costs
96% of a controlled population's total P&L right at the $2,000 equity boundary (Safe:
$207.90 scaled vs $4,820.40 baseline). ARM-PARTICIPATION-AND-GROWTH-2026-08-03.md #2 found
this is not hypothetical: fleet_executor's tiers have been LIVE for safe-3/risky-1/risky-3
since inception, and risky-3's own equity has round-tripped the $2,000 line at least twice
this month (currently $2,121.61, live-verified -- see test_deny_before_shrink_after below,
which constructs the REAL deadlock case at that exact equity).

THIS IS A DEFECT FIX, NOT AN ARMING OF NEW SCALING. position_sizing_tiers already drives
every fleet_rest order today (safe-3/risky-1/risky-3) -- this only changes what happens when
a tiered qty doesn't fit the cap (shrink to the largest legal size, per Rule 6's own floor,
instead of denying the trade outright). Whether to EVER wire CORE (safe-2/bold-2) onto
position_sizing_tiers at all remains untouched and is explicitly J's call
(SIZING-SCALING-DECISION-2026-08-03.md's own recommendation #2: do not arm scaled sizing
until a shrink-semantics re-run like this one confirms the deadlock is closed -- this file
IS that re-run, scoped to the fleet lane where the tiers are already live).

REVERT (one line, byte-identical): in finalize(), change
    _qty, _shrink_note = _shrink_qty_to_affordable(plan.qty, equity, premium, _fleet_params)
back to
    _qty, _shrink_note = plan.qty, None
(or delete the call and revert proposed_qty=_qty / plan.qty, _binding's proposed_qty=_qty /
plan.qty, and the ArmDecision qty/reason fields back to plan.qty/plan.reason). No accounts.json
or params.json change is required to revert -- this is pure code, and _shrink_qty_to_affordable
staying defined-but-uncalled is itself inert.

FORWARD KILL CRITERION (pre-committed): over the first n>=10 real fleet fills that trigger a
shrink (shrink_note present in the decisions.jsonl reason field) OR 10 trading sessions post-
ship, whichever comes first, if the shrunk-qty cohort's realized net P&L reads negative,
revert per the one-line instruction above and re-open SIZING-SCALING-DECISION-2026-08-03.md's
open question (§8 #2: shrink-semantics was specified/code-grounded but UNMEASURED on real
fills at ship time -- this guard suite is the unit/integration proof, not a live-P&L proof).

Runs under pytest OR standalone (`python test_shrink_not_deny_2026_08_03.py`), mirroring
test_recency_min_sizing.py's tmp_path-free, pure-function-first shape (no I/O needed here --
_shrink_qty_to_affordable takes params as a plain dict).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # automation/state/fleet/<this file> -> repo root
FLEET = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(FLEET))

import fleet_executor as fx  # noqa: E402

BOLD_PARAMS = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                         .read_text(encoding="utf-8"))
SAFE_PARAMS = json.loads((REPO / "automation" / "state" / "params.json")
                         .read_text(encoding="utf-8"))

# risky-3's LIVE equity, fetched fresh this session via fleet_broker.get_account (read-only
# GET /v2/account) -- matches accounts.json's own account_number PA31WIU8X15Q, and matches
# ARM-PARTICIPATION-AND-GROWTH-2026-08-03.md's independently-fetched figure to the penny.
RISKY3_LIVE_EQUITY = 2121.61

# Bold's position_sizing_tiers at $2,121.61 (the [2000, 10000) bracket): base_qty=8,
# elite_qty=12 -- pinned directly from automation/state/aggressive/params.json so this file
# fails loudly (not silently) if that table is ever retuned.
BOLD_TIER_BASE_QTY = 8
BOLD_TIER_ELITE_QTY = 12


def _final(plan, premium, equity, params, account_label="TEST"):
    return fx.finalize(plan, equity=equity, start_of_day_equity=equity, premium=premium,
                       current_position_status=None, day_trades_used_5d=0,
                       kill_switch_tripped=False, prior_stops_today=[], params=params,
                       account_label=account_label)


# =============================================================================================
# 1. PURE UNIT TESTS -- _shrink_qty_to_affordable in isolation
# =============================================================================================

def test_qty_none_passes_through():
    qty, note = fx._shrink_qty_to_affordable(None, 2000.0, 1.50, BOLD_PARAMS)
    assert qty is None and note is None


def test_premium_none_passes_through():
    qty, note = fx._shrink_qty_to_affordable(8, 2000.0, None, BOLD_PARAMS)
    assert qty == 8 and note is None


def test_affordable_qty_passes_through_unchanged():
    """A qty that already fits the cap is byte-identical -- the shrink is a NO-OP whenever
    check_order would have allowed it anyway."""
    # qty=5 @ premium=1.00 -> notional $500, well under Bold's $1,060.805 cap @ this equity.
    qty, note = fx._shrink_qty_to_affordable(5, RISKY3_LIVE_EQUITY, 1.00, BOLD_PARAMS)
    assert qty == 5 and note is None


def test_oversize_qty_shrinks_to_max_affordable():
    qty, note = fx._shrink_qty_to_affordable(BOLD_TIER_BASE_QTY, RISKY3_LIVE_EQUITY, 1.50, BOLD_PARAMS)
    assert qty == 7, f"expected shrink to 7 (largest affordable at $1.50), got {qty}"
    assert note is not None and "shrunk 8->7" in note


def test_genuine_deadlock_passes_through_unshrunk():
    """When even min_contracts doesn't fit (max_affordable_qty==0), there is no legal size to
    shrink to -- qty passes through UNCHANGED so the caller's existing check_order call denies
    it exactly as it did before this fix. No regression versus baseline."""
    qty, note = fx._shrink_qty_to_affordable(BOLD_TIER_ELITE_QTY, RISKY3_LIVE_EQUITY, 3.00, BOLD_PARAMS)
    assert qty == BOLD_TIER_ELITE_QTY, "a genuine deadlock must not shrink the qty at all"
    assert note is None


def test_never_shrinks_below_min_contracts_property():
    """Property check across a wide premium sweep: whenever a shrink happens, the result is
    NEVER below params['min_contracts'] (Rule 6's immovable floor) -- this is guaranteed by
    risk_gate.max_affordable_qty's own contract (0 or >= min_contracts, never between), but
    pinned here directly against the real function, not just re-asserted from its docstring."""
    min_contracts = int(BOLD_PARAMS["min_contracts"])
    for cents in range(10, 500, 7):  # premiums $0.10 .. $4.93 in irregular steps
        premium = cents / 100.0
        for qty in (BOLD_TIER_BASE_QTY, BOLD_TIER_ELITE_QTY):
            shrunk, _ = fx._shrink_qty_to_affordable(qty, RISKY3_LIVE_EQUITY, premium, BOLD_PARAMS)
            assert shrunk is None or shrunk == 0 or shrunk >= min_contracts, (
                f"premium={premium} qty={qty} shrunk to {shrunk} -- below Rule 6's floor "
                f"of {min_contracts}"
            )


def test_malformed_params_fails_open_to_original_qty():
    """Unreadable params must never turn a shrink-attempt into a NEW way to lose an order --
    fails open to the untouched qty, leaving check_order (called next by the real caller) as
    the one true decision-maker, exactly as before this fix existed."""
    qty, note = fx._shrink_qty_to_affordable(8, RISKY3_LIVE_EQUITY, 1.50, {"min_contracts": "not-a-number"})
    assert qty == 8 and note is None


# =============================================================================================
# 2. EXECUTION PROOF -- the REAL risky-3 deadlock, at risky-3's REAL live equity, quoting
#    both the pre-fix DENY and the post-fix shrink-ALLOW (task's own explicit ask).
# =============================================================================================

def test_deny_before_shrink_after_at_risky3_real_equity():
    """Constructs the exact scenario ARM-PARTICIPATION-AND-GROWTH-2026-08-03.md #2 flagged:
    risky-3 at its OWN live equity ($2,121.61, fetched fresh this session), Bold's REAL
    position_sizing_tiers (qty 8 @ this equity, non-elite), and a plausible real ATM 0DTE
    premium ($1.50 -- SIZING-SCALING-DECISION-2026-08-03.md's own §5 cites 'real ATM 0DTE
    premiums routinely run $1-3').

    BEFORE (quoted): finalize()'s pre-2026-08-03 shape called risk_gate.check_order directly
    on plan.qty with no affordability pre-check -- reproduced here by calling check_order
    directly with the UNSHRUNK tiered qty, which is byte-identical to what finalize() used to
    send. This must DENY (RISK_CAP): notional $1,200.00 > cap $1,060.805 (50% of $2,121.61).

    AFTER (quoted): the REAL, current fleet_executor.finalize() (not a mock, not a
    reimplementation) on the identical inputs. This must ALLOW at the shrunk qty=7: notional
    $1,050.00 <= cap $1,060.805.
    """
    equity = RISKY3_LIVE_EQUITY
    premium = 1.50
    tiered_qty = fx._qty_for(BOLD_PARAMS["position_sizing_tiers"], equity, elite=False)
    assert tiered_qty == BOLD_TIER_BASE_QTY, (
        f"Bold's own tier table at ${equity} should resolve base_qty={BOLD_TIER_BASE_QTY}, "
        f"got {tiered_qty} -- re-derive the scenario numbers if the tier table changed"
    )

    # --- BEFORE: what finalize() used to do (call check_order on the raw tiered qty) -------
    _fleet_params = dict(BOLD_PARAMS)
    _fleet_params["pdt_gate_mode"] = "margin_pdt"
    before_decision = fx.risk_gate.check_order(
        "risky-3-TEST", equity=equity, start_of_day_equity=equity,
        proposed_qty=tiered_qty, premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params=_fleet_params,
    )
    print(f"[shrink-not-deny proof] BEFORE (unshrunk qty={tiered_qty} @ ${premium}): "
          f"allowed={before_decision.allowed} code={getattr(before_decision, 'code', None)} "
          f"reason={before_decision.reason!r}")
    assert before_decision.allowed is False, "pre-fix semantics must DENY this exact order"
    assert before_decision.code == "RISK_CAP", (
        f"expected RISK_CAP, got {before_decision.code} -- re-derive the scenario if params "
        f"or risk_gate's own cap math changed"
    )

    # --- AFTER: the REAL, current finalize() (this repo's actual shipped code) -------------
    plan = fx.EntryPlan(
        arm_id="risky-3", action="ENTER", side="P",
        setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", strike=None, qty=tiered_qty,
        quality="BASE", reason="clean P entry (BASE)",
    )
    after_decision = _final(plan, premium, equity, BOLD_PARAMS, account_label="risky-3-TEST")
    print(f"[shrink-not-deny proof] AFTER  (shrunk qty={after_decision.qty} @ ${premium}): "
          f"action={after_decision.action} risk_code={after_decision.risk_code} "
          f"reason={after_decision.reason!r}")
    assert after_decision.action == "ENTER_BEAR", (
        f"post-fix finalize() must ALLOW the shrunk order, got action={after_decision.action} "
        f"risk_code={after_decision.risk_code} reason={after_decision.reason}"
    )
    assert after_decision.risk_code == "ALLOW"
    assert after_decision.qty == 7, f"expected shrunk qty=7, got {after_decision.qty}"
    assert "shrunk 8->7" in after_decision.reason

    # --- Cross-check: the shrunk order really is legal (never below Rule 6's floor, and its
    #     own notional really does clear the cap it was denied against above) -------------
    assert after_decision.qty >= int(BOLD_PARAMS["min_contracts"])
    shrunk_notional = premium * after_decision.qty * 100
    cap_dollars = equity * BOLD_PARAMS["per_trade_risk_cap_pct"]
    assert shrunk_notional <= cap_dollars, (
        f"shrunk notional ${shrunk_notional:.2f} must clear the ${cap_dollars:.2f} cap "
        f"it was sized down to fit"
    )


def test_genuine_deadlock_still_denies_both_before_and_after():
    """Regression-safety twin of the test above: at a premium so high even min_contracts (5)
    doesn't fit risky-3's cap, BOTH the pre-fix call shape (check_order on the raw elite qty)
    AND the post-fix finalize() must DENY -- a true deadlock is not something shrink-not-deny
    can or should rescue (that would mean placing an order below Rule 6's floor, or above the
    cap -- both forbidden). Proves the fix narrows outcomes, it does not loosen risk."""
    equity = RISKY3_LIVE_EQUITY
    premium = 3.00
    tiered_qty = fx._qty_for(BOLD_PARAMS["position_sizing_tiers"], equity, elite=True)
    assert tiered_qty == BOLD_TIER_ELITE_QTY

    _fleet_params = dict(BOLD_PARAMS)
    _fleet_params["pdt_gate_mode"] = "margin_pdt"
    before_decision = fx.risk_gate.check_order(
        "risky-3-TEST", equity=equity, start_of_day_equity=equity,
        proposed_qty=tiered_qty, premium=premium, setup_name="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params=_fleet_params,
    )
    assert before_decision.allowed is False

    plan = fx.EntryPlan(
        arm_id="risky-3", action="ENTER", side="C",
        setup_name="BULLISH_RECLAIM_RIDE_THE_RIBBON", strike=None, qty=tiered_qty,
        quality="ELITE", reason="clean C entry (ELITE)",
    )
    after_decision = _final(plan, premium, equity, BOLD_PARAMS, account_label="risky-3-TEST")
    print(f"[shrink-not-deny deadlock proof] qty={tiered_qty} @ ${premium}: "
          f"action={after_decision.action} risk_code={after_decision.risk_code}")
    assert after_decision.action == "HOLD", "a genuine deadlock must still HOLD after this fix"
    assert after_decision.risk_code in ("RISK_CAP", "MAX_PREMIUM_TIER")
    assert after_decision.qty == tiered_qty, "a denied deadlock must report the ORIGINAL (unshrunk) qty"


# =============================================================================================
# 3. VARY-AND-ASSERT (C14) -- the shrink is genuinely wired into finalize()'s real call path,
#    not a dead knob that only fires when called directly.
# =============================================================================================

def test_shrink_note_appears_in_the_real_finalize_reason_string():
    """The decisions.jsonl reason field is what J's REVOKE surface and every downstream
    monitor actually reads -- confirm the shrink is VISIBLE there, not just internally
    tracked."""
    plan = fx.EntryPlan(
        arm_id="risky-3", action="ENTER", side="P",
        setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", strike=746, qty=BOLD_TIER_BASE_QTY,
        quality="BASE", reason="clean P entry (BASE)",
    )
    d = _final(plan, 1.50, RISKY3_LIVE_EQUITY, BOLD_PARAMS, account_label="risky-3-TEST")
    assert "shrunk" in d.reason and "RISK_CAP shrink-not-deny" in d.reason


def test_safe_arm_at_2k_boundary_also_shrinks_not_denies():
    """SIZING-SCALING-DECISION-2026-08-03.md's own headline number was Safe at $2,000
    ($207.90 scaled vs $4,820.40 baseline, deny-semantics). This is the SAFE-side twin of the
    risky-3 proof above -- different account, same mechanism, same fix, proving the change
    isn't accidentally Bold-only."""
    equity = 2_000.0  # Safe's own tier boundary -- resolves base_qty=5 (SAFE_PARAMS)
    premium = 1.30     # notional @ qty5 = $650 > Safe's $600 cap (30% of $2,000) -> would deny
    tiered_qty = fx._qty_for(SAFE_PARAMS["position_sizing_tiers"], equity, elite=False)
    assert tiered_qty == 5

    _fleet_params = dict(SAFE_PARAMS)
    _fleet_params["pdt_gate_mode"] = "margin_pdt"
    before_decision = fx.risk_gate.check_order(
        "safe-3-TEST", equity=equity, start_of_day_equity=equity,
        proposed_qty=tiered_qty, premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=0, kill_switch_tripped=False,
        prior_stops_today=[], params=_fleet_params,
    )
    assert before_decision.allowed is False, (
        f"expected a deny to set up this proof, got allowed=True ({before_decision.reason}) "
        f"-- re-derive the premium if Safe's params changed"
    )

    plan = fx.EntryPlan(
        arm_id="safe-3", action="ENTER", side="P",
        setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON", strike=None, qty=tiered_qty,
        quality="BASE", reason="clean P entry (BASE)",
    )
    after_decision = _final(plan, premium, equity, SAFE_PARAMS, account_label="safe-3-TEST")
    assert after_decision.action == "ENTER_BEAR", (
        f"expected the SAFE-side shrink to also rescue this order, got "
        f"action={after_decision.action} risk_code={after_decision.risk_code}"
    )
    assert after_decision.qty < tiered_qty
    assert after_decision.qty >= int(SAFE_PARAMS["min_contracts"])


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
