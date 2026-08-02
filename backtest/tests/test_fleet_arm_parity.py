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
2. PER-ARM GATE: safe-3 (tight, require_confluence_or_sequence) HOLDs on non-elite signals
   and ENTERs on elite ones. safe-1 / risky-3 (loose, min_triggers=1) ENTER on any
   single-trigger pass. risky-1 (RISKY_TIGHT below — name predates the 2026-07-31 FULL-SEND
   conversion, commit e28d210c) no longer carries min_triggers/require_confluence at all
   (gate_override is now {"full_send": true}) — its NORMAL lane is therefore UNGATED, same as
   risky-3, and ENTERs on any single-trigger pass at normal (not min) sizing; the separate
   full-send MIN-SIZE rescue lane (_full_send_plan, only for producer-cohort-vetoed ticks) is
   a plan_all-level concern covered by test_full_send_arm.py, not by this fast plan_entry file.
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

import pytest

_REPO = Path(__file__).resolve().parents[2]
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in (str(_FLEET), str(_REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fleet_executor as fx  # noqa: E402


# --- FLEET-PARITY-TESTS-READ-LIVE-STATE (filed 2026-07-27, fixed 2026-08-01) -------
# _apply_recency_min_sizing (called inside plan_entry) reads the LIVE
# recency-confirmation.json verdict via fx._recency_verdict(). Every test in this file
# EXCEPT the ones in section 7 below is testing perception-routing/gating/sizing/strike
# logic, NOT the recency-clamp feature — so they must run against a FIXED, non-live
# verdict, or they silently start failing/passing depending on the rig's live P&L state
# (a guard whose verdict depends on live state is not a guard, C7/C14). Default here is
# "GREEN" (byte-identical passthrough, matching _apply_recency_min_sizing's own YELLOW/
# GREEN no-op branches) so every OTHER test in this file exercises un-clamped qty math,
# same as before the 2026-07-10 recency-sizing feature ever shipped. Section 7 overrides
# this per-test via monkeypatch to exercise BOTH the RED-clamped and GREEN-unclamped
# branches explicitly (vary-and-assert, C14) instead of relying on whatever the live file
# happens to say tonight.
@pytest.fixture(autouse=True)
def _fixed_recency_verdict(monkeypatch):
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "GREEN")

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
# NOTE (FLEET-PARITY-TESTS-READ-LIVE-STATE, fixed 2026-08-01): build_shared_signal.py's
# GATE-TIERS-IMPLEMENT (2026-07-23) made "score_peak_passed"/"hard_skip_action" ride
# ALONGSIDE the unchanged "passed" field (see build_shared_signal.py:383-388) so
# fleet_executor._effective_passed() can rescue a hard-skip-only block for an arm whose
# gate_params.hard_skip_verdicts opts out (risky-3/RISKY_LOOSE, the only arm with an
# empty hard_skip_verdicts list today). score_peak_passed is a SUPERSET of passed (true
# whenever passed is true, plus hard-skip-only cases); these synthetic fixtures never
# simulate a hard-skip scenario, so score_peak_passed mirrors passed exactly and
# hard_skip_action is always None. Without this field these blocks were a STALE fixture
# against the real producer contract — RISKY_LOOSE could never pass _effective_passed's
# score_peak_passed branch and every RISKY_LOOSE test silently HELD regardless of the
# signal shape (a producer/consumer contract drift, C7/C14 — caught while fixing the
# separate live-recency-state issue in the same suite).
def _bear_block(passed: bool, *, confluence: bool = False, n_triggers: int = 1) -> dict:
    trigs = ["level_reject"] * n_triggers
    if confluence:
        trigs = ["multi_day_confluence"] + trigs[:n_triggers - 1]
    return {
        "passed": passed,
        "score": 9 if passed else 3,
        "score_peak_passed": passed,
        "hard_skip_action": None,
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
        "score_peak_passed": passed,
        "hard_skip_action": None,
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

def test_risky_tight_enters_on_non_elite_bold_bear_since_fullsend_conversion():
    """RISKY_TIGHT (risky-1) lost its min_triggers/require_confluence gate on 2026-07-31
    (FULL-SEND conversion, commit e28d210c: gate_override -> {"full_send": true}). Its
    NORMAL lane (this test calls plan_entry directly, not the plan_all rescue lane) is now
    UNGATED — a non-elite bold bear pass ENTERs at BASE quality, same shape as RISKY_LOOSE.
    This is a DELIBERATE behavior change, not a bug — pinned here so a future accounts.json
    edit that silently re-tightens (or a revert per the commit's own REVOKE line) is visible
    as an intentional test change, not a mystery regression."""
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=False)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "ENTER", plan.reason
    assert plan.quality == "BASE"


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
# 4. STRIKE TIER — safe-1 (retired) uses BOLD(OTM) tiers; safe-3/risky-1/risky-3 use
#    BOLD_CORE (ATM) tiers at $2K equity (FLEET-STRIKE-TIER-ATM-EXTENSION, 2026-08-01,
#    pre-registered: analysis/recommendations/fleet-strike-tier-atm-extension-prereg-
#    2026-08-01.json, for risky-1/risky-3; FLEET-STRIKE-TIER-ATM-EXTENSION-SAFE3,
#    2026-08-03, analysis/recommendations/fleet-strike-tier-atm-extension-safe3-prereg-
#    2026-08-03.json, for safe-3). safe-1 UNCHANGED (retired, predates either extension).
# =============================================================================

def test_safe_loose_uses_bold_otm_strike_tiers_at_2k():
    """safe-1 (retired fixture) keeps the OTM V15_BOLD_TIERS table, unchanged by either
    ATM extension -- it is inactive and was never in scope for them. BOLD tiers at $2K:
    $2K-10K bracket -> OTM-2 (offset=-2). On SPY=600: PUT->598, CALL->602. Was
    test_safe_arms_use_bold_otm_strike_tiers_at_2k (looped safe-1 AND safe-3) before
    2026-08-03: safe-3 moved to the bold_core bucket that session -- see
    test_safe3_risky_arms_use_bold_core_atm_strike_tiers_at_2k below."""
    tiers = fx._tiers_for_arm(SAFE_LOOSE)
    assert tiers is fx.strike_selection.V15_BOLD_TIERS, \
        f"{SAFE_LOOSE['id']} should use BOLD(OTM) tiers, got a different table"

    put_strike  = fx.strike_selection.pick_strike(SPY_SPOT, EQUITY_2K, "P", fx.strike_selection.V15_BOLD_TIERS)
    call_strike = fx.strike_selection.pick_strike(SPY_SPOT, EQUITY_2K, "C", fx.strike_selection.V15_BOLD_TIERS)
    assert put_strike  == 598, f"OTM-2 PUT strike should be 598, got {put_strike}"
    assert call_strike == 602, f"OTM-2 CALL strike should be 602, got {call_strike}"


def test_safe3_risky_arms_use_bold_core_atm_strike_tiers_at_2k():
    """safe-3/risky-1/risky-3 all resolve V15_BOLD_CORE_TIERS (ATM at $2K-10K, unchanged
    above $2K) via params_patch.strike_tier_table='bold_core' -- the 2026-08-01 extension
    (risky-1/risky-3) plus its 2026-08-03 safe-3 follow-on, both repointing to the table
    core Bold already used since 2026-07-17/18. At $2K-10K: strike_offset=-2 (same as
    before, this bracket is untouched -- ONLY the $0-2K bracket differs, and
    EQUITY_2K==2000.0 sits exactly at the $2K-10K boundary, so this test still reads OTM-2
    math, matching the safe-1 test above by design; the ATM behavior lives at equity <
    2000, covered by test_fleet_strike_tier_floor_collision_2026_07_31.py and
    test_bold_core_strike_tier_2026_07_15.py)."""
    for arm in (SAFE_TIGHT, RISKY_TIGHT, RISKY_LOOSE):
        tiers = fx._tiers_for_arm(arm)
        assert tiers is fx.strike_selection.V15_BOLD_CORE_TIERS, \
            f"{arm['id']} should use BOLD_CORE tiers, got a different table"
        assert tiers is not fx.strike_selection.V15_BOLD_TIERS, \
            f"{arm['id']} must not still resolve the old shared OTM table"

    put_strike  = fx.strike_selection.pick_strike(SPY_SPOT, EQUITY_2K, "P", fx.strike_selection.V15_BOLD_CORE_TIERS)
    call_strike = fx.strike_selection.pick_strike(SPY_SPOT, EQUITY_2K, "C", fx.strike_selection.V15_BOLD_CORE_TIERS)
    assert put_strike  == 598, f"OTM-2 PUT strike at $2K should still be 598, got {put_strike}"
    assert call_strike == 602, f"OTM-2 CALL strike at $2K should still be 602, got {call_strike}"


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


# =============================================================================
# 7. RECENCY-CONDITIONED MIN-SIZING — both branches exercised explicitly against a
#    MOCKED verdict (never the live recency-confirmation.json), per FLEET-PARITY-
#    TESTS-READ-LIVE-STATE (filed 2026-07-27). ribbon_ride ONLY (C29 scope); RED clamps
#    qty down to min_contracts, GREEN/YELLOW pass through byte-identical.
# =============================================================================

def test_recency_red_clamps_risky_elite_qty(monkeypatch):
    """RED verdict clamps risky-1's elite ribbon_ride qty 12->min_contracts (5)."""
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "RED")
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "ENTER"
    assert plan.qty == 5, f"RED verdict should clamp risky-1 elite qty to min_contracts, got {plan.qty}"
    assert "recency red" in plan.reason.lower(), plan.reason


def test_recency_red_clamps_safe_elite_qty(monkeypatch):
    """RED verdict clamps safe-3's elite ribbon_ride qty 8->min_contracts (3)."""
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "RED")
    sig = _dual_signal(safe_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(SAFE_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(SAFE_TIGHT))
    assert plan.action == "ENTER"
    assert plan.qty == 3, f"RED verdict should clamp safe-3 elite qty to min_contracts, got {plan.qty}"
    assert "recency red" in plan.reason.lower(), plan.reason


def test_recency_green_does_not_clamp_risky_elite_qty(monkeypatch):
    """GREEN verdict is a no-op: risky-1 elite qty stays at the full 12 (unclamped branch,
    explicit — not just relying on the autouse fixture default)."""
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "GREEN")
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "ENTER"
    assert plan.qty == 12, f"GREEN verdict must not clamp risky-1 elite qty, got {plan.qty}"
    assert "recency" not in plan.reason.lower(), plan.reason


def test_recency_yellow_does_not_clamp_risky_elite_qty(monkeypatch):
    """YELLOW (not-yet-confirmed) is also a no-op per the shipped design — only RED clamps."""
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "YELLOW")
    sig = _dual_signal(bold_bear_passed=True, n_triggers=2, confluence=True)
    plan = fx.plan_entry(RISKY_TIGHT, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_TIGHT))
    assert plan.action == "ENTER"
    assert plan.qty == 12, f"YELLOW verdict must not clamp risky-1 elite qty, got {plan.qty}"


def test_recency_red_clamps_base_tier_ribbon_ride_too(monkeypatch):
    """RED clamps by STRATEGY (ribbon_ride, C29), not by quality tier — RISKY_LOOSE's
    non-elite BASE-tier entry is the same strategy and gets clamped too: base qty 8 ->
    min_contracts 5 (risky-3's floor). Confirms the clamp scope is strategy-wide, not
    elite-only."""
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "RED")
    sig = _dual_signal(bold_bear_passed=True, n_triggers=1, confluence=False)
    plan = fx.plan_entry(RISKY_LOOSE, sig, equity=EQUITY_2K, params=fx._params_for(RISKY_LOOSE))
    assert plan.action == "ENTER"
    assert plan.qty == 5, f"base qty (8) should clamp to risky-3's min_contracts (5), got {plan.qty}"
    assert "recency red" in plan.reason.lower(), plan.reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
