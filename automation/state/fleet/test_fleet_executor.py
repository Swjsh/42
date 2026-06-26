"""Tests for the fleet executor policy fan-out.

Proves each arm's frozen policy behaves on synthetic signals: controls take clean
signals, the A+ arm abstains on marginal setups and takes EXCELLENT ones, the
puts-only arm skips calls, and the shared risk gate blocks oversized orders.

Runs under pytest OR standalone (`python test_fleet_executor.py`) so it can be
verified without the backtest venv (the executor + risk_gate + strike_selection
are all stdlib-only).
"""
from __future__ import annotations

import json

import fleet_executor as fx

# --- arm fixtures (mirror accounts.json semantics) ---------------------------
SAFE_CONTROL = {"id": "safe-1", "status": "active", "strike_tier_table": "safe"}
APLUS = {
    "id": "safe-3", "status": "active", "strike_tier_table": "safe",
    "gate_override": {"min_confidence": 0.65, "min_setup_quality": "EXCELLENT",
                      "min_triggers": 2, "require_confluence_or_sequence": True},
}
PUTS_ONLY = {"id": "risky-1", "status": "active", "strike_tier_table": "bold",
             "direction_lock": "PUT_ONLY"}

# --- 6-account differentiation fixtures (the DESIGN arms) ---------------------
# safe-loose: forced OTM (bold table) + qty-raising patch; min_triggers:1 only.
SAFE_LOOSE = {
    "id": "safe-loose", "status": "active",
    "gate_override": {"min_triggers": 1},
    "params_patch": {
        "strike_tier_table": "bold",
        "position_sizing_tiers": [
            {"equity_min": 0, "equity_max": 2000, "base_qty": 5, "elite_qty": 5},
            {"equity_min": 2000, "equity_max": 10000, "base_qty": 6, "elite_qty": 8},
            {"equity_min": 10000, "equity_max": 999999999, "base_qty": 10, "elite_qty": 15}],
    },
}
# risky-1 recast: PUT_ONLY + a MEDIUM quality gate (no min_confidence -> not frozen today).
BOLD_MEDIUM = {
    "id": "risky-1", "status": "active", "direction_lock": "PUT_ONLY",
    "gate_override": {"min_triggers": 2, "require_confluence_or_sequence": True},
}
# risky-3 recast: thinnest gate, SAFE/ATM table for cheap fills, both directions.
BOLD_LOOSE = {
    "id": "risky-3", "status": "active",
    "gate_override": {"min_triggers": 1},
    "params_patch": {
        "strike_tier_table": "safe",
        "position_sizing_tiers": [
            {"equity_min": 0, "equity_max": 2000, "base_qty": 5, "elite_qty": 5},
            {"equity_min": 2000, "equity_max": 10000, "base_qty": 8, "elite_qty": 10},
            {"equity_min": 10000, "equity_max": 999999999, "base_qty": 12, "elite_qty": 15}],
    },
}

SAFE_PARAMS = {
    "per_trade_risk_cap_pct": 0.3, "daily_loss_kill_switch_pct": 0.3, "min_contracts": 3,
    "first_entry_after_stop_blocked": True,
    "position_sizing_tiers": [
        {"equity_min": 0, "equity_max": 2000, "base_qty": 3, "elite_qty": 3},
        {"equity_min": 2000, "equity_max": 10000, "base_qty": 5, "elite_qty": 8},
        {"equity_min": 10000, "equity_max": 999999999, "base_qty": 10, "elite_qty": 15}],
    "v15_max_premium_pct_of_account": [
        {"equity_min": 0, "equity_max": 2000, "max_pct": 0.4},
        {"equity_min": 2000, "equity_max": 10000, "max_pct": 0.3},
        {"equity_min": 10000, "equity_max": 25000, "max_pct": 0.25},
        {"equity_min": 25000, "equity_max": 999999999, "max_pct": 0.2}],
}
BOLD_PARAMS = {**SAFE_PARAMS, "per_trade_risk_cap_pct": 0.5}

# --- signal fixtures ---------------------------------------------------------
BEAR_APLUS = {"spot": 748.5, "production_action": "ENTER_BEAR",
              "bear": {"passed": True, "score": 8, "triggers_fired": ["level_reject", "confluence"],
                       "confluence": True, "confidence": 0.72,
                       "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
              "bull": {"passed": False}}
BEAR_MARGINAL = {"spot": 748.5, "production_action": "ENTER_BEAR",
                 "bear": {"passed": True, "score": 6, "triggers_fired": ["ribbon_flip"],
                          "confluence": False, "confidence": 0.55,
                          "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
                 "bull": {"passed": False}}
BULL_APLUS = {"spot": 748.5, "production_action": "ENTER_BULL",
              "bear": {"passed": False},
              "bull": {"passed": True, "score": 9, "triggers_fired": ["confluence", "level_reclaim"],
                       "confluence": True, "confidence": 0.70,
                       "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON"}}
NO_SETUP = {"spot": 748.5, "bear": {"passed": False}, "bull": {"passed": False}}


def _final(plan, premium, equity, params):
    return fx.finalize(plan, equity=equity, start_of_day_equity=equity, premium=premium,
                       current_position_status=None, day_trades_used_5d=0,
                       kill_switch_tripped=False, prior_stops_today=[], params=params,
                       account_label="TEST")


def test_control_takes_clean_bear():
    plan = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 2000.0, SAFE_PARAMS)
    assert plan.action == "ENTER" and plan.side == "P"
    d = _final(plan, 0.40, 2000.0, SAFE_PARAMS)
    assert d.action == "ENTER_BEAR" and d.risk_code == "ALLOW"


def test_aplus_holds_marginal():
    plan = fx.plan_entry(APLUS, BEAR_MARGINAL, 2000.0, SAFE_PARAMS)
    assert plan.action == "HOLD" and "confidence" in plan.reason


def test_aplus_takes_excellent():
    plan = fx.plan_entry(APLUS, BEAR_APLUS, 2000.0, SAFE_PARAMS)
    assert plan.action == "ENTER" and plan.quality == "ELITE"
    d = _final(plan, 0.40, 2000.0, SAFE_PARAMS)
    assert d.action == "ENTER_BEAR"


def test_putsonly_skips_call():
    plan = fx.plan_entry(PUTS_ONLY, BULL_APLUS, 2000.0, BOLD_PARAMS)
    assert plan.action == "HOLD" and "PUT_ONLY" in plan.reason


def test_putsonly_takes_put():
    plan = fx.plan_entry(PUTS_ONLY, BEAR_APLUS, 2000.0, BOLD_PARAMS)
    assert plan.action == "ENTER" and plan.side == "P"


def test_risk_cap_blocks_oversize():
    plan = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 2000.0, SAFE_PARAMS)
    d = _final(plan, 5.00, 2000.0, SAFE_PARAMS)  # 5.00 * 8 * 100 = $4000 >> $600 cap
    assert d.action == "HOLD" and d.risk_code in ("RISK_CAP", "MAX_PREMIUM_TIER")


def test_strike_tables_differ():
    safe_plan = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 5000.0, SAFE_PARAMS)
    bold_plan = fx.plan_entry(PUTS_ONLY, BEAR_APLUS, 5000.0, BOLD_PARAMS)
    assert safe_plan.strike == 748  # SAFE tier offset 0 (ATM)
    assert bold_plan.strike == 746  # BOLD tier offset -2 (OTM-2 put)


def test_no_setup_holds():
    plan = fx.plan_entry(SAFE_CONTROL, NO_SETUP, 2000.0, SAFE_PARAMS)
    assert plan.action == "HOLD" and "no qualifying setup" in plan.reason


# --- A single fired-trigger BUT-NOT-EXCELLENT bear signal (the discriminator) ---
# One real entry-trigger fired, no confluence/sequence, no confidence carried. The
# loose arms (min_triggers:1) take it; the medium/tight arms (>=2 triggers OR
# EXCELLENT OR min_confidence) hold. This is the "scoring-peak reclaim the tight gates
# blocked" shape that the looseness tiers exist to discriminate.
BEAR_ONE_TRIGGER = {
    "spot": 735.0, "production_action": "ENTER_BEAR",
    "bear": {"passed": True, "score": 8, "triggers_fired": ["level_rejection"],
             "confluence": False,
             "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
    "bull": {"passed": False}}


# --- STEP 1: per-arm params override path (_params_for) -----------------------
def test_params_parity_unpatched_is_byte_identical():
    """PARITY INVARIANT: an arm with NO params_patch yields a dict byte-identical to
    the base SAFE/BOLD params -- proves safe-1/safe-3/risky-1 (no patch) are unchanged."""
    # safe arm (no patch) == raw SAFE params.json
    base_safe = json.loads(fx.PARAMS_SAFE.read_text(encoding="utf-8"))
    got_safe = fx._params_for({"id": "safe-1"})
    assert json.dumps(got_safe, sort_keys=True) == json.dumps(base_safe, sort_keys=True)
    # bold arm (no patch) == raw BOLD params.json
    base_bold = json.loads(fx.PARAMS_BOLD.read_text(encoding="utf-8"))
    got_bold = fx._params_for({"id": "risky-1"})
    assert json.dumps(got_bold, sort_keys=True) == json.dumps(base_bold, sort_keys=True)
    # empty-dict patch is also a no-op (parity holds)
    got_empty = fx._params_for({"id": "safe-3", "params_patch": {}})
    assert json.dumps(got_empty, sort_keys=True) == json.dumps(base_safe, sort_keys=True)


def test_params_patch_changes_sizing_tiers():
    """A params_patch with position_sizing_tiers shallow-overwrites that key only."""
    merged = fx._params_for(SAFE_LOOSE)
    assert merged["position_sizing_tiers"] == SAFE_LOOSE["params_patch"]["position_sizing_tiers"]
    # other keys untouched (still the base SAFE values)
    base_safe = json.loads(fx.PARAMS_SAFE.read_text(encoding="utf-8"))
    assert merged["per_trade_risk_cap_pct"] == base_safe["per_trade_risk_cap_pct"]
    assert merged.get("v15_max_premium_pct_of_account") == base_safe.get("v15_max_premium_pct_of_account")


def test_params_patch_qty_drives_plan_qty():
    """The patched tiers (not min_contracts) drive the qty plan_entry returns."""
    base_plan = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 2000.0, SAFE_PARAMS)
    # SAFE_PARAMS [2000,10000) base_qty=5 -> control gets 5 (ELITE here -> elite_qty=8)
    assert base_plan.qty == 8
    # safe-loose patched tiers: [2000,10000) base 6 / elite 8 -> ELITE bear -> 8; change base via a BASE signal
    patched = fx._params_for(SAFE_LOOSE)
    base_signal = {"spot": 735.0, "production_action": "ENTER_BEAR",
                   "bear": {"passed": True, "score": 8, "triggers_fired": ["level_rejection"],
                            "confluence": False, "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
                   "bull": {"passed": False}}
    p = fx.plan_entry(SAFE_LOOSE, base_signal, 2000.0, patched)
    assert p.action == "ENTER" and p.quality == "BASE" and p.qty == 6  # patched base_qty=6


def test_strike_tier_table_in_patch_flips_depth():
    """strike_tier_table inside params_patch flips SAFE(ATM)<->BOLD(OTM) strike depth."""
    # safe-loose forces the BOLD (OTM) table via params_patch -> OTM-2 put at $5K
    plan = fx.plan_entry(SAFE_LOOSE, BEAR_APLUS, 5000.0, fx._params_for(SAFE_LOOSE))
    assert plan.strike == 746  # round(748.5)=748 + (-2) OTM-2 put == 746 (BOLD table)
    # a plain safe arm (SAFE/ATM table) at the same spot -> ATM 748
    plain = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 5000.0, SAFE_PARAMS)
    assert plain.strike == 748


# --- STEP 4: each arm's DISTINCT gating on the one-trigger discriminator ------
def test_safe_loose_takes_one_trigger():
    plan = fx.plan_entry(SAFE_LOOSE, BEAR_ONE_TRIGGER, 2000.0, fx._params_for(SAFE_LOOSE))
    assert plan.action == "ENTER" and plan.side == "P"


def test_safe3_tight_holds_one_trigger():
    """safe-3 needs >=2 triggers AND EXCELLENT AND confidence -> holds the 1-trigger setup."""
    plan = fx.plan_entry(APLUS, BEAR_ONE_TRIGGER, 2000.0, SAFE_PARAMS)
    assert plan.action == "HOLD"


def test_bold_medium_holds_one_trigger_but_takes_aplus_put():
    """risky-1 medium: >=2 triggers + confluence -> holds 1-trigger, takes the A+ put."""
    held = fx.plan_entry(BOLD_MEDIUM, BEAR_ONE_TRIGGER, 2000.0, BOLD_PARAMS)
    assert held.action == "HOLD"
    took = fx.plan_entry(BOLD_MEDIUM, BEAR_APLUS, 2000.0, BOLD_PARAMS)
    assert took.action == "ENTER" and took.side == "P"


def test_bold_medium_still_skips_call():
    """risky-1 keeps PUT_ONLY -> never takes a CALL even when it is A+."""
    plan = fx.plan_entry(BOLD_MEDIUM, BULL_APLUS, 2000.0, BOLD_PARAMS)
    assert plan.action == "HOLD" and "PUT_ONLY" in plan.reason


def test_bold_loose_takes_one_trigger_both_directions():
    """bold-loose: thinnest gate, both directions, takes the 1-trigger bear AND a bull."""
    bear = fx.plan_entry(BOLD_LOOSE, BEAR_ONE_TRIGGER, 2000.0, fx._params_for(BOLD_LOOSE))
    assert bear.action == "ENTER" and bear.side == "P"
    bull_sig = {"spot": 735.0, "production_action": "ENTER_BULL", "bear": {"passed": False},
                "bull": {"passed": True, "score": 9, "triggers_fired": ["level_reclaim"],
                         "confluence": False, "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON"}}
    bull = fx.plan_entry(BOLD_LOOSE, bull_sig, 2000.0, fx._params_for(BOLD_LOOSE))
    assert bull.action == "ENTER" and bull.side == "C"


# --- the loose arm PLACES at its equity (qty within the risk cap) -------------
def test_bold_loose_places_at_equity_within_cap():
    """bold-loose at $2K: SAFE/ATM table, patched qty8, ATM put ~$0.70 -> $560 < $1000 cap -> ALLOW."""
    patched = fx._params_for(BOLD_LOOSE)
    plan = fx.plan_entry(BOLD_LOOSE, BEAR_ONE_TRIGGER, 2000.0, patched)
    assert plan.action == "ENTER" and plan.qty == 8  # patched [2000,10000) base 8 (BASE setup)
    d = _final(plan, 0.70, 2000.0, patched)  # 0.70*8*100 = $560 < $1000 (bold) cap
    assert d.action == "ENTER_BEAR" and d.risk_code == "ALLOW"


def test_safe_loose_places_at_equity_within_cap():
    """safe-loose at $2K: BOLD/OTM table, patched qty6, OTM-2 put ~$0.30 -> $180 < $600 cap -> ALLOW."""
    patched = fx._params_for(SAFE_LOOSE)
    plan = fx.plan_entry(SAFE_LOOSE, BEAR_ONE_TRIGGER, 2000.0, patched)
    assert plan.action == "ENTER" and plan.qty == 6
    d = _final(plan, 0.30, 2000.0, patched)  # 0.30*6*100 = $180 < $600 (safe) cap
    assert d.action == "ENTER_BEAR" and d.risk_code == "ALLOW"


# --- min_contracts is NOT the sizing lever (the INERT-knob guard) -------------
def test_min_contracts_is_not_the_sizing_lever():
    """Changing min_contracts (3 vs 5) leaves finalize's action/qty IDENTICAL at $2K.
    qty comes from position_sizing_tiers, NOT min_contracts -- min_contracts only sets a
    FLOOR (a deny below it), never the chosen qty."""
    p3 = {**SAFE_PARAMS, "min_contracts": 3}
    p5 = {**SAFE_PARAMS, "min_contracts": 5}
    plan3 = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 2000.0, p3)
    plan5 = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 2000.0, p5)
    assert plan3.qty == plan5.qty == 8  # tier elite_qty, unaffected by min_contracts
    d3 = _final(plan3, 0.40, 2000.0, p3)
    d5 = _final(plan5, 0.40, 2000.0, p5)
    assert d3.action == d5.action == "ENTER_BEAR"
    assert d3.qty == d5.qty == 8  # identical -> min_contracts did NOT move sizing


# --- STEP 3: dual-perception routing (perception-source confound fix) ----------
def test_dual_perception_routes_safe_vs_bold_blocks():
    """When the signal carries 'safe'/'bold' sub-blocks that DISAGREE, a safe arm and a
    bold arm pick different side-blocks (safe -> signal['safe'], bold -> signal['bold'])."""
    dual = {
        "spot": 735.0, "production_action": "HOLD",
        # top-level (backward-compat): nothing passes
        "bear": {"passed": False}, "bull": {"passed": False},
        # SAFE perception: still HOLD (production-faithful)
        "safe": {"bear": {"passed": False}, "bull": {"passed": False}},
        # BOLD perception (scoring-peak): a bear passed off the bold ledger
        "bold": {"bear": {"passed": True, "score": 8, "triggers_fired": ["level_rejection"],
                          "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
                 "bull": {"passed": False}},
    }
    safe_side = fx._chosen_side(dual, SAFE_CONTROL)[0]
    bold_side = fx._chosen_side(dual, BOLD_LOOSE)[0]
    assert safe_side is None        # safe arm reads SAFE block -> nothing
    assert bold_side == "P"         # bold arm reads BOLD block -> bear passed
    # and a bold arm with NO dual block falls back to top-level (backward-compat)
    flat_sig = {"spot": 735.0, "production_action": "HOLD",
                "bear": {"passed": False}, "bull": {"passed": False}}
    assert fx._chosen_side(flat_sig, BOLD_LOOSE)[0] is None


def test_chosen_side_no_arm_is_v1_top_level():
    """_chosen_side(signal) with no arm reads top-level bear/bull (v1 byte-identical)."""
    assert fx._chosen_side(BEAR_APLUS)[0] == "P"
    assert fx._chosen_side(NO_SETUP)[0] is None


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
