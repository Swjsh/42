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
    # SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX (2026-07-11): min_confidence:0.65 REMOVED from
    # this fixture -- fleet_executor.py's confidence check was deleted (build_shared_
    # signal.py never populated "confidence", so it could only ever always-HOLD; see
    # the fix comment in plan_entry/_gate_check). min_triggers + require_confluence_
    # or_sequence + min_setup_quality still make this arm the tight/selective one.
    "gate_override": {"min_setup_quality": "EXCELLENT",
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
    # SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX: BEAR_MARGINAL is marginal on triggers (1) AND
    # confluence (False) AND the now-unused confidence field (0.55) -- the arm still
    # correctly HOLDs, now via the triggers criterion (was via confidence pre-fix).
    plan = fx.plan_entry(APLUS, BEAR_MARGINAL, 2000.0, SAFE_PARAMS)
    assert plan.action == "HOLD" and "triggers" in plan.reason


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
    # This test targets the tier-PATCH axis only -- _params_for reads the LIVE params.json
    # (now shipping recency_min_size_enabled=true, 2026-07-10), so neutralize that axis here
    # so this assertion never rides the live recency-confirmation.json's real-world state
    # (which is expected to keep changing weekly). Recency-clamp coverage lives in its own
    # dedicated automation/state/fleet/test_recency_min_sizing.py.
    patched = {**patched, "recency_min_size_enabled": False}
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
    """safe-3 needs >=2 triggers AND EXCELLENT -> holds the 1-trigger setup."""
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
    # neutralize the recency-clamp axis (see test_params_patch_qty_drives_plan_qty comment) --
    # this test targets the risk-cap admission path, not recency sizing.
    patched = {**fx._params_for(BOLD_LOOSE), "recency_min_size_enabled": False}
    plan = fx.plan_entry(BOLD_LOOSE, BEAR_ONE_TRIGGER, 2000.0, patched)
    assert plan.action == "ENTER" and plan.qty == 8  # patched [2000,10000) base 8 (BASE setup)
    d = _final(plan, 0.70, 2000.0, patched)  # 0.70*8*100 = $560 < $1000 (bold) cap
    assert d.action == "ENTER_BEAR" and d.risk_code == "ALLOW"


def test_safe_loose_places_at_equity_within_cap():
    """safe-loose at $2K: BOLD/OTM table, patched qty6, OTM-2 put ~$0.30 -> $180 < $600 cap -> ALLOW."""
    # neutralize the recency-clamp axis (see test_params_patch_qty_drives_plan_qty comment) --
    # this test targets the risk-cap admission path, not recency sizing.
    patched = {**fx._params_for(SAFE_LOOSE), "recency_min_size_enabled": False}
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


# --- GATE-TIERS-IMPLEMENT (2026-07-23): per-arm hard-skip override ------------
# Audit rank #3 (markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md section 4):
# require_bearish_fill_bar's global hard-skip should NOT be inherited by the RISKY/
# minimum-viable-gate tier. An arm opts in via accounts.json `gate_params.hard_skip_
# verdicts` (empty list = ignore every global hard-skip gate); absence of the key is
# byte-identical to pre-change behavior.
RISKY_TIER_NO_HARD_SKIP = {
    "id": "risky-3", "status": "active",
    "gate_override": {"min_triggers": 1},
    "gate_params": {"hard_skip_verdicts": []},
}
_HARD_SKIP_BLOCKED_BLOCK = {
    "passed": False, "score": 8, "score_peak_passed": True,
    "hard_skip_action": "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY",
    "triggers_fired": ["level_rejection"],
    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
}


def test_effective_passed_default_is_byte_identical():
    """An arm with NO gate_params.hard_skip_verdicts key reads block['passed'] verbatim --
    the exact pre-change behavior -- even though score_peak_passed/hard_skip_action are
    now present on the block."""
    assert fx._effective_passed(_HARD_SKIP_BLOCKED_BLOCK, BOLD_LOOSE) is False
    assert fx._effective_passed(_HARD_SKIP_BLOCKED_BLOCK, None) is False
    passing_block = {"passed": True, "score_peak_passed": True, "hard_skip_action": None}
    assert fx._effective_passed(passing_block, BOLD_LOOSE) is True


def test_effective_passed_rescues_for_opted_out_arm():
    """An arm whose gate_params.hard_skip_verdicts is [] (ignore-all) is RESCUED by
    score_peak_passed even though the block's baked-in 'passed' is False."""
    assert fx._effective_passed(_HARD_SKIP_BLOCKED_BLOCK, RISKY_TIER_NO_HARD_SKIP) is True


def test_effective_passed_still_honors_named_hard_skip():
    """An arm that explicitly names the SAME verdict in its own hard_skip_verdicts list
    still treats it as a hard block (opt-out is per-verdict, not blanket)."""
    arm = {"id": "risky-3", "gate_params":
           {"hard_skip_verdicts": ["SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"]}}
    assert fx._effective_passed(_HARD_SKIP_BLOCKED_BLOCK, arm) is False


def test_effective_passed_no_hard_skip_present_unaffected():
    """A normally-passing block (no hard_skip_action) is unaffected by an arm's opt-out --
    opting out only matters when a hard-skip verdict actually fired."""
    block = {"passed": True, "score_peak_passed": True, "hard_skip_action": None,
             "triggers_fired": ["level_reclaim"], "setup_name": "X"}
    assert fx._effective_passed(block, RISKY_TIER_NO_HARD_SKIP) is True


def test_chosen_side_hard_skip_rescue_end_to_end():
    """Integration: _chosen_side rescues a hard-skip-blocked BOLD-role signal for the
    opted-out RISKY-tier arm, but a control arm reading the SAME block stays blocked."""
    dual = {
        "spot": 735.0, "production_action": "HOLD",
        "bear": {"passed": False}, "bull": {"passed": False},
        "safe": {"bear": {"passed": False}, "bull": {"passed": False}},
        "bold": {"bear": dict(_HARD_SKIP_BLOCKED_BLOCK), "bull": {"passed": False}},
    }
    control_side = fx._chosen_side(dual, BOLD_LOOSE)[0]       # no gate_params key
    rescued_side = fx._chosen_side(dual, RISKY_TIER_NO_HARD_SKIP)[0]
    assert control_side is None      # unchanged: still honors the global hard-skip
    assert rescued_side == "P"       # opted-out arm sees the rescued bear


# --- LANE-5 ORPHAN CLOSE (2026-08-04): is the hard-skip override actually LIVE-WIRED? -------
# QUEUE ITEM ("fleet_executor._effective_passed... dead knob... since 2026-07-23, only
# reachable from backtest/replay_fleet_arms.py") investigated fresh this session. Root cause,
# stated precisely: the mechanism is NOT code-dead -- it is CONFIG-INERT. accounts.json's
# risky-3 entry genuinely carries `gate_params: {"hard_skip_verdicts": []}` on disk (verified
# this session), _chosen_side/_effective_passed correctly consume it (proven above by
# test_effective_passed_rescues_for_opted_out_arm / test_chosen_side_hard_skip_rescue_end_to_end
# already in this file), and build_shared_signal.py's dual-perception 'bold' block DOES carry
# score_peak_passed/hard_skip_action when SCORING_PEAK_LIVE=True (confirmed True on disk) and a
# real (non-blind) row exists. The reason it never visibly FIRES on the live ledger: build_
# shared_signal._HARD_SKIP_VERDICTS has exactly ONE member, SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY
# (tied to the require_bearish_fill_bar gate) -- and per markdown/deep-research/WEEK-ORDER-
# 2026-08-03.md's gate table, require_bearish_fill_bar is "prereg frozen, NOT armed" as a
# deliberate evidence-based decision. An unarmed gate never writes that verdict string, so
# hard_skip_action is always None on today's real rows and the rescue branch always resolves
# to the SAME answer score_peak_passed alone would give -- functionally invisible, by config,
# not by a wiring bug. The tests above already prove the ISOLATED logic; this test closes the
# gap to "live-path" by loading the REAL accounts.json (not a hand-copied literal that could
# silently drift from disk) and driving the mechanism through fleet_executor.plan_entry -- the
# actual live entry point -- end to end. No production code changed; this is a diagnostic +
# regression guard proving the mechanism is correctly wired and ready for the day
# require_bearish_fill_bar (or any future _HARD_SKIP_VERDICTS member) arms.
def _real_arm(arm_id: str) -> dict:
    import pathlib
    accounts_path = pathlib.Path(__file__).resolve().parent / "accounts.json"
    accounts = json.loads(accounts_path.read_text(encoding="utf-8"))
    for a in accounts["arms"]:
        if a["id"] == arm_id:
            return a
    raise KeyError(f"{arm_id} not found in real accounts.json arms list")


def test_real_accounts_json_risky3_has_the_opt_out_configured():
    """RED-PROOF anchor: if a future accounts.json edit ever drops risky-3's opt-out (or
    changes it to a non-empty list that re-includes the fill-bar verdict), this fails loud
    before the end-to-end test below can silently start passing for the wrong reason."""
    risky3 = _real_arm("risky-3")
    assert risky3.get("gate_params") == {"hard_skip_verdicts": []}
    risky1 = _real_arm("risky-1")
    assert risky1.get("gate_params") is None, "risky-1 is the control -- must have NO override"


def test_real_accounts_json_wiring_rescues_risky3_not_risky1():
    """Vary-and-assert against the REAL on-disk accounts.json (not a synthetic fixture):
    the SAME hard-skip-blocked BOLD-perception signal is rescued for the real risky-3 arm
    object and stays blocked for the real risky-1 arm object, via _chosen_side -- the exact
    function plan_entry calls first on every live tick."""
    risky3 = _real_arm("risky-3")
    risky1 = _real_arm("risky-1")
    dual = {
        "spot": 735.0, "production_action": "HOLD",
        "bear": {"passed": False}, "bull": {"passed": False},
        "safe": {"bear": {"passed": False}, "bull": {"passed": False}},
        "bold": {"bear": dict(_HARD_SKIP_BLOCKED_BLOCK), "bull": {"passed": False}},
    }
    assert fx._chosen_side(dual, risky1)[0] is None, "control must still honor the hard-skip"
    assert fx._chosen_side(dual, risky3)[0] == "P", "real disk risky-3 config must rescue it"


def test_real_accounts_json_wiring_through_plan_entry_end_to_end():
    """Full live entry point (plan_entry, not just the pure _chosen_side helper) with the
    REAL risky-3/risky-1 arm dicts and BOLD_PARAMS -- proves the override changes the actual
    ENTER/HOLD decision, not just an internal side-selection helper."""
    risky3 = _real_arm("risky-3")
    risky1 = _real_arm("risky-1")
    dual = {
        "spot": 735.0, "production_action": "HOLD",
        "bear": {"passed": False}, "bull": {"passed": False},
        "safe": {"bear": {"passed": False}, "bull": {"passed": False}},
        "bold": {"bear": dict(_HARD_SKIP_BLOCKED_BLOCK), "bull": {"passed": False}},
    }
    control_plan = fx.plan_entry(risky1, dual, 5000.0, BOLD_PARAMS)
    rescued_plan = fx.plan_entry(risky3, dual, 5000.0, BOLD_PARAMS)
    assert control_plan.action == "HOLD", control_plan.reason
    assert rescued_plan.action == "ENTER" and rescued_plan.side == "P", rescued_plan.reason


# --- SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX guard (GATE-PROVENANCE-AUDIT-2026-07-02 E5/F6) ---
def test_min_confidence_gate_removed_and_inert():
    """build_shared_signal.py has NEVER populated a "confidence" field on any signal it
    emits (its own FAITHFULNESS NOTE docstring says so explicitly). A min_confidence
    gate could therefore only ever read conf=None and always-HOLD -- not real
    selectivity, a silent permanent starve (safe-3 was down to 1 trade/30d). The check
    was DELETED from plan_entry and _gate_check rather than "fixed forward" (populating
    a genuine confidence score needs a validated model, out of scope for a surgical
    fix). This guard proves a stale/reintroduced min_confidence key (e.g. restored from
    accounts.json.bak-2026-06-25-pre-grid, which DOES still carry it) can never again
    silently starve an arm, AND that the mechanism is structurally gone, not just
    coincidentally unreachable."""
    stale_gate_arm = {
        "id": "safe-3", "status": "active", "strike_tier_table": "safe",
        "gate_override": {"min_confidence": 0.65, "min_triggers": 2,
                          "require_confluence_or_sequence": True},
    }
    # A signal shaped exactly like build_shared_signal.py's real output: every OTHER
    # A+ criterion (triggers, confluence) satisfied, but NO "confidence" key anywhere
    # (top-level or side-block) -- the true production shape, not a hostile fixture.
    confidence_free_signal = json.loads(json.dumps(BEAR_APLUS))  # deep copy
    del confidence_free_signal["bear"]["confidence"]
    assert "confidence" not in confidence_free_signal["bear"]
    assert "confidence" not in confidence_free_signal
    plan = fx.plan_entry(stale_gate_arm, confidence_free_signal, 2000.0, SAFE_PARAMS)
    assert plan.action == "ENTER", (
        f"REGRESSION: a stale min_confidence key starved the arm again (reason: {plan.reason!r})"
    )
    # same proof against the multi-strategy gate path (_gate_check, feeds plan_all)
    reason = fx._gate_check(stale_gate_arm, confidence_free_signal["bear"], confidence_free_signal)
    assert reason is None, f"REGRESSION: _gate_check still blocks on confidence (reason: {reason!r})"
    # structural belt-and-suspenders: the read is gone from the source, not merely
    # unreachable today -- a future edit can't quietly resurrect it in a form this
    # black-box behavioral check wouldn't happen to exercise.
    import inspect
    assert 'g.get("min_confidence")' not in inspect.getsource(fx.plan_entry)
    assert 'g.get("min_confidence")' not in inspect.getsource(fx._gate_check)


# --- BLAST-RADIUS GUARD (2026-07-14): fleet arms pinned off the cash-settlement gate ---
def test_finalize_pins_pdt_gate_mode_to_margin_pdt_regardless_of_params():
    """automation/state/params.json / aggressive/params.json (the SAME files
    _base_params_for reads) now default to pdt_gate_mode="cash_settlement" for
    core Safe/Bold (backtest/lib/risk_gate.py CODE_SETTLEMENT). fleet_executor
    never computes settled_cash_available/same_day_entries_used -- if finalize()
    ever inherited cash_settlement mode from a params dict, check_order would
    fail-closed to UNREADABLE_INPUT on EVERY fleet order (a real regression
    for arms outside the Rule-7-rewrite's scope). This proves finalize()
    overrides pdt_gate_mode back to "margin_pdt" even when the CALLER'S params
    dict explicitly requests cash_settlement -- fleet arms cannot silently
    inherit this mode from the shared config file."""
    hostile_params = dict(SAFE_PARAMS, pdt_gate_mode="cash_settlement")
    plan = fx.plan_entry(SAFE_CONTROL, BEAR_APLUS, 2000.0, hostile_params)
    assert plan.action == "ENTER"
    decision = _final(plan, 0.40, 2000.0, hostile_params)
    assert decision.action == "ENTER_BEAR" and decision.risk_code == "ALLOW", (
        f"REGRESSION: fleet arm denied under cash_settlement mode leaking from "
        f"shared params (action={decision.action!r}, risk_code={decision.risk_code!r}, "
        f"reason={decision.reason!r}) -- finalize() must pin pdt_gate_mode='margin_pdt' "
        f"regardless of params."
    )


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
