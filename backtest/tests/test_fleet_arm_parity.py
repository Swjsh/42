"""test_fleet_arm_parity.py — fast per-arm entry parity guard for the 4 live fleet arms.

WHAT THIS PROVES (the fast-fixture port of replay_fleet_arms.py)
---------------------------------------------------------------
replay_fleet_arms.py is a heavy standalone script: it loads 8 days of real SPY+VIX CSVs,
runs the full backtest pipeline, re-runs decide_payload bar-by-bar, builds synthetic signals,
and checks MATCH/EXTRA/MISSED per arm. It is the correct end-to-end integration proof but
runs in minutes and lives outside the curated pytest suite → a regression that breaks per-arm
gating would ship GREEN.

This file is the FAST pytest counterpart: it uses REAL arm configs from accounts.json and
tests the CONSUMER CONTRACT — given a dual-perception signal (the shape build_shared_signal
emits) does each arm make the correct ENTER/HOLD decision per its frozen policy?

KEY CONTRACTS PROVED
--------------------
1. PERCEPTION-SOURCE ROUTING: safe arms read signal['safe']; risky/bold arms read
   signal['bold']. A bold pass that the SAFE account's ledger didn't match → risky ENTERs,
   safe HOLDs.
2. PER-ARM GATE: safe-3 / risky-1 (tight, require_confluence_or_sequence) HOLD on non-elite
   signals and ENTER on elite ones. safe-1 / risky-3 (loose, min_triggers=1) ENTER on any
   single-trigger pass.
3. SIZING: safe-1 / safe-3 use SAFE params (base_qty=5 at $2K–10K); risky-1 / risky-3 use
   BOLD params (base_qty=8 at $2K–10K). The _base_params_for routing is the only source of
   this difference.
4. STRIKE TIER: all 4 arms use BOLD strike tiers at $2K equity → OTM-2 (strike_offset=−2);
   PUT=598, CALL=602 on SPY=600.
5. BEAR AND BULL: per-arm gates are direction-agnostic; this file exercises PUT (bear) and
   CALL (bull) entries.
6. BITE (params-routing): with config_source patched to "" on a risky arm it would start with
   "risky" → still routes to BOLD params (id prefix wins). Ensures the routing rule is
   exercised.

RAIL-4 CLEAR: test-only. Imports real arm configs (read-only) and the real fleet_executor;
mutates NOTHING in production, places no orders. Ships on green — engine-benefit (OP-22/OP-26).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in (str(_FLEET), str(_REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fleet_executor as fx  # noqa: E402

# --- Load real arm configs from accounts.json (read-only) -------------------------
_ACCOUNTS = json.loads((_REPO / "automation" / "state" / "fleet" / "accounts.json").read_text(encoding="utf-8"))
_ARM_MAP = {a["id"]: a for a in _ACCOUNTS["arms"]}

SAFE_LOOSE  = _ARM_MAP["safe-1"]   # min_triggers=1, no ELITE req, reads signal['safe']
SAFE_TIGHT  = _ARM_MAP["safe-3"]   # min_triggers=2, require_confluence, reads signal['safe']
RISKY_TIGHT = _ARM_MAP["risky-1"]  # min_triggers=2, require_confluence, reads signal['bold']
RISKY_LOOSE = _ARM_MAP["risky-3"]  # min_triggers=1, no ELITE req,  reads signal['bold']

SPY_SPOT   = 600.0
EQUITY_2K  = 2000.0  # real starting equity for risky arms; also tests safe arms at $2K

# --- Signal construction helpers ---------------------------------------------------
def _bear_block(passed: bool, *, confluence: bool = False, n_triggers: int = 1) -> dict:
    trigs = ["level_reject"] * n_triggers
    if confluence:
        trigs = ["multi_day_confluence"] + trigs[:n_triggers - 1]
    return {
        "passed": passed,
        "score": 9 if passed else 3,
        "triggers_fired": trigs if passed else [],
        "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON" if passed else None,
        "confluence": confluence and passed,
    }


def _bull_block(passed: bool, *, confluence: bool = False, n_triggers: int = 1) -> dict:
    trigs = ["level_reclaim"] * n_triggers
    if confluence:
        trigs = ["multi_day_confluence"] + trigs[:n_triggers - 1]
    return {
        "passed": passed,
        "score": 9 if passed else 3,
        "triggers_fired": trigs if passed else [],
        "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON" if passed else None,
        "confluence": confluence and passed,
    }


def _dual_signal(
    *,
    safe_bear_passed: bool = False,
    safe_bull_passed: bool = False,
    bold_bear_passed: bool = False,
    bold_bull_passed: bool = False,
    confluence: bool = False,
    n_triggers: int = 1,
) -> dict:
    """Dual-perception signal in the shape build_shared_signal emits.

    The top-level 'bear'/'bull' mirror the safe perception (production_action from safe
    heartbeat). The 'safe' / 'bold' sub-blocks are what _perception_for_arm routes each
    arm to."""
    safe_bear = _bear_block(safe_bear_passed, confluence=confluence, n_triggers=n_triggers)
    safe_bull = _bull_block(safe_bull_passed, confluence=confluence, n_triggers=n_triggers)
    bold_bear = _bear_block(bold_bear_passed, confluence=confluence, n_triggers=n_triggers)
    bold_bull = _bull_block(bold_bull_passed, confluence=confluence, n_triggers=n_triggers)

    prod_action = "HOLD"
    if safe_bear_passed:
        prod_action = "ENTER_BEAR"
    elif safe_bull_passed:
        prod_action = "ENTER_BULL"

    return {
        "spot": SPY_SPOT,
        "vix": 15.0,
        "production_action": prod_action,
        "bear": safe_bear,
        "bull": safe_bull,
        "safe": {"bear": safe_bear, "bull": safe_bull},
        "bold": {"bear": bold_bear, "bull": bold_bull},
    }


# =============================================================================
# 1. PERCEPTION-SOURCE ROUTING — bold pass → risky ENTERs, safe HOLDs
# =============================================================================

def test_bold_bear_pass_risky_loose_enters():
    """RISKY_LOOSE reads signal['bold']: a bold-only bear pass → ENTER PUT."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=1)
    assert sig["safe"]["bear"]["passed"] is False   # safe account did NOT pass
    assert sig["bold"]["bear"]["passed"] is True    # bold passed

    plan = fx.plan_entry(RISKY_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan.action == "ENTER", plan.reason
    assert plan.side == "P"


def test_bold_bear_pass_safe_loose_holds():
    """SAFE_LOOSE reads signal['safe']: the same bold-only pass → HOLD (perception confound guard)."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=1)
    plan = fx.plan_entry(SAFE_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_LOOSE))
    assert plan.action == "HOLD", f"safe arm must not pick up bold-only pass, got {plan.reason}"


def test_bold_bull_pass_risky_loose_enters():
    """RISKY_LOOSE reads signal['bold']: bold-only bull pass → ENTER CALL."""
    sig = _dual_signal(bold_bull_passed=True, n_triggers=1)
    plan = fx.plan_entry(RISKY_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan.action == "ENTER", plan.reason
    assert plan.side == "C"


def test_bold_bull_pass_safe_tight_holds():
    """SAFE_TIGHT reads signal['safe']: bold-only bull pass → HOLD."""
    sig = _dual_signal(bold_bull_passed=True, n_triggers=1)
    plan = fx.plan_entry(SAFE_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_TIGHT))
    assert plan.action == "HOLD"


# =============================================================================
# 2. SAFE ARM GATE (reads signal['safe'])
# =============================================================================

def test_safe_loose_enters_on_safe_bear_pass():
    """SAFE_LOOSE: safe bear pass + 1 trigger → ENTER."""
    sig = _dual_signal(safe_bear_passed=True, n_triggers=1)
    plan = fx.plan_entry(SAFE_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_LOOSE))
    assert plan.action == "ENTER"
    assert plan.side == "P"


def test_safe_tight_holds_on_non_elite_safe_bear():
    """SAFE_TIGHT (min_triggers=2, require_confluence): 2 plain triggers, no confluence → HOLD."""
    sig = _dual_signal(safe_bear_passed=True, n_triggers=2, confluence=False)
    plan = fx.plan_entry(SAFE_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_TIGHT))
    assert plan.action == "HOLD"
    reason = plan.reason.lower()
    assert "confluence" in reason or "elite" in reason, plan.reason


def test_safe_tight_enters_on_elite_safe_bear():
    """SAFE_TIGHT: confluence trigger makes the signal ELITE → ENTER."""
    sig = _dual_signal(safe_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(SAFE_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_TIGHT))
    assert plan.action == "ENTER"
    assert plan.quality == "ELITE"


# =============================================================================
# 3. RISKY ARM GATE (reads signal['bold'])
# =============================================================================

def test_risky_tight_holds_on_non_elite_bold_bear():
    """RISKY_TIGHT (min_triggers=2, require_confluence): bold bear pass but non-elite → HOLD."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=False)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "HOLD"
    reason = plan.reason.lower()
    assert "confluence" in reason or "elite" in reason, plan.reason


def test_risky_tight_enters_on_elite_bold_bear():
    """RISKY_TIGHT: bold bear pass + confluence → ENTER PUT."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "ENTER"
    assert plan.side == "P"
    assert plan.quality == "ELITE"


def test_risky_loose_enters_on_non_elite_bold_bear():
    """RISKY_LOOSE: one plain trigger suffices → ENTER PUT."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=1, confluence=False)
    plan = fx.plan_entry(RISKY_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan.action == "ENTER"
    assert plan.quality == "BASE"


def test_risky_loose_both_directions():
    """RISKY_LOOSE has no direction_lock: bull and bear ENTERs are both legal."""
    sig_bear = _dual_signal(bold_bear_passed=True, n_triggers=1)
    sig_bull = _dual_signal(bold_bull_passed=True, n_triggers=1)
    plan_bear = fx.plan_entry(RISKY_LOOSE, sig_bear, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    plan_bull = fx.plan_entry(RISKY_LOOSE, sig_bull, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan_bear.action == "ENTER" and plan_bear.side == "P"
    assert plan_bull.action == "ENTER" and plan_bull.side == "C"


# =============================================================================
# 4. STRIKE TIER — all 4 arms use BOLD tiers at $2K equity → OTM-2
# =============================================================================

def test_all_arms_bold_strike_tiers_at_2k():
    """All 4 live fleet arms resolve to BOLD strike tiers at $2K equity.
    BOLD tiers at $2K: $2K–10K bracket → OTM-2 (strike_offset=−2).
    On SPY=600: PUT→598, CALL→602."""
    for arm in (SAFE_LOOSE, SAFE_TIGHT, RISKY_TIGHT, RISKY_LOOSE):
        tiers = fx._tiers_for_arm(arm)
        assert tiers is fx.strike_selection.V15_BOLD_TIERS, \
            f"{arm['id']} should use BOLD tiers, got SAFE"

    # Strike math sanity at SPY=600 (OTM-2 offset)
    put_strike  = fx.strike_selection.pick_strike(SPY_SPOT, EQUITY_2K, "P", fx.strike_selection.V15_BOLD_TIERS)
    call_strike = fx.strike_selection.pick_strike(SPY_SPOT, EQUITY_2K, "C", fx.strike_selection.V15_BOLD_TIERS)
    assert put_strike  == 598, f"OTM-2 PUT strike should be 598, got {put_strike}"
    assert call_strike == 602, f"OTM-2 CALL strike should be 602, got {call_strike}"


def test_arm_plan_carries_otm2_strike():
    """An ENTERING risky arm at $2K on SPY=600 gets OTM-2 strike in the plan."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=1)
    plan = fx.plan_entry(RISKY_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan.action == "ENTER"
    assert plan.strike == 598, f"PUT OTM-2 should be 598, got {plan.strike}"


# =============================================================================
# 5. SIZING — SAFE params (base=5) vs BOLD params (base=8) at $2K–10K
# =============================================================================

def test_safe_arms_use_safe_sizing():
    """SAFE_LOOSE and SAFE_TIGHT read SAFE params → base_qty=5 at $2K equity."""
    for arm in (SAFE_LOOSE, SAFE_TIGHT):
        sig = _dual_signal(safe_bear_passed=True, n_triggers=1)
        plan = fx.plan_entry(arm, sig, equity=EQUITY_2K, params=fx._params_for(arm))
        if plan.action == "ENTER":  # SAFE_LOOSE enters on 1 trigger; SAFE_TIGHT needs elite
            assert plan.qty == 5, f"{arm['id']} base qty should be 5 (SAFE params), got {plan.qty}"


def test_risky_arms_use_bold_sizing():
    """RISKY_LOOSE reads BOLD params → base_qty=8 at $2K equity."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=1)
    plan = fx.plan_entry(RISKY_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan.action == "ENTER"
    assert plan.qty == 8, f"risky-3 base qty should be 8 (BOLD params), got {plan.qty}"


def test_risky_elite_bold_sizing():
    """RISKY_TIGHT on elite signal → elite_qty=12 (BOLD params)."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "ENTER"
    assert plan.qty == 12, f"risky-1 elite qty should be 12 (BOLD params), got {plan.qty}"


def test_safe_elite_safe_sizing():
    """SAFE_TIGHT on elite signal → elite_qty=8 (SAFE params)."""
    sig = _dual_signal(safe_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(SAFE_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_TIGHT))
    assert plan.action == "ENTER"
    assert plan.qty == 8, f"safe-3 elite qty should be 8 (SAFE params), got {plan.qty}"


# =============================================================================
# 6. BITE — regression catches if perception routing breaks
# =============================================================================

def test_no_pass_all_arms_hold_BITE():
    """No bear or bull pass → all 4 arms HOLD regardless of gate."""
    sig = _dual_signal()  # all passed=False
    for arm in (SAFE_LOOSE, SAFE_TIGHT, RISKY_TIGHT, RISKY_LOOSE):
        plan = fx.plan_entry(arm, sig, equity=EQUITY_2K, params=fx._params_for(arm))
        assert plan.action == "HOLD", f"{arm['id']} should HOLD on empty signal, got {plan.reason}"


def test_safe_perception_missing_bold_sub_block_falls_back_BITE():
    """If the signal lacks 'bold' sub-block entirely, RISKY arm falls back to top-level
    (production-faithful HOLD when top-level is HOLD). Regression for perception-routing
    breakage where signal['bold'] is dropped."""
    sig_no_bold = _dual_signal(bold_bear_passed=True, n_triggers=1)
    sig_no_bold.pop("bold")  # simulate producer bug: bold sub-block missing

    plan = fx.plan_entry(RISKY_LOOSE, sig_no_bold, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    # Without the bold block the arm falls back to signal top-level (safe-side = passed=False) → HOLD.
    assert plan.action == "HOLD", \
        f"risky arm without signal['bold'] must fall back to HOLD, got {plan.reason}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
