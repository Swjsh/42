"""test_full_send_arm.py -- guards for the FULL-SEND learning arm (2026-07-31).

TWO JOBS, and the SECOND is the one that matters:

  (i)  PROOF OF EFFECT -- the full-send arm ENTERS on a cohort-vetoed tick where every gated
       arm is blocked. RED-proof: revert `gate_override.full_send` (or the producer allowlist)
       and these tests fail.

  (ii) PROOF OF SAFETY -- every RISK guard still binds on this arm. The whole design is
       "loose on SELECTION, never loose on RISK", so each of the kill switch, the per-trade
       risk cap, PDT, no-add/one-position, the min_entry_premium floor, and EOD-flatten scope
       is asserted to still BLOCK a full-send plan. If anyone ever routes this lane around
       finalize()/risk_gate, these fail.

$0, offline, pure unit tests. Run:
    backtest/.venv/Scripts/python.exe -m pytest automation/state/fleet/test_full_send_arm.py -q
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

ACCOUNTS = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                         .read_text(encoding="utf-8"))
EQUITY = 2000.0


def _arm(arm_id: str) -> dict:
    for a in ACCOUNTS["arms"]:
        if a["id"] == arm_id:
            return a
    raise AssertionError(f"arm {arm_id} missing from accounts.json")


FULL_SEND_ARM_ID = "risky-1"


def _vetoed_core_row(verdict: str = "SKIP_ELITE_BULL_LEVEL_RECLAIM",
                     bull_score: int = 7) -> dict:
    """A REAL-SHAPED core-decisions row: the engine NAMED a bull reclaim setup, a level-tied
    entry trigger fired, it had an exact level -- and a COHORT gate refused it.

    SCORE MATTERS, and this default is deliberate. The fleet's EXISTING scoring-peak lane
    (build_shared_signal._score_peak_check) already rescues a cohort-vetoed tick whose score
    clears the peak (bull >= 9 / bear >= 8) -- that is exactly how safe-3 and risky-3 entered
    on 2026-07-31 at bull_score 11. Measured over the 28-day bold ledger: of 206 cohort-vetoed
    named-setup ticks carrying a level, 189 (92%) were ALREADY rescued that way and only 17
    were marginal to this lane. So a score-11 fixture would prove nothing about full_send --
    it would pass on the pre-existing path. bull_score=7 is BELOW the peak, which is the
    population where this lane is the ONLY thing that can take the trade."""
    return {
        "ts_et": "2026-07-31T12:15:02-04:00", "account": "bold", "spy": 744.10,
        "ribbon": "BULL", "spread_cents": 12, "vix": 16.4, "htf_15m": "BULL",
        "verdict": verdict, "action": verdict, "side": "C",
        "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "bear_score": 2, "bull_score": bull_score,
        "triggers": ["level_reclaim", "confluence"],
        "trigger_level_exact": 743.25,
        "bull_reclaim_level_raw": 743.25, "bear_rejection_level_raw": None,
    }


def _signal_from(row: dict) -> dict:
    """Build the live-shaped shared signal from a core row via the REAL producer (mapped the
    same way _latest_today_core would), with the network VWAP pass off so tests stay offline."""
    import datetime as dt
    mapped = bss._map_core_row(row)
    now = dt.datetime(2026, 7, 31, 12, 15, tzinfo=bss.ET)
    return bss.build_from_rows(mapped, now, bold_row=mapped, probe_row=mapped,
                              run_vwap=False, write=False)


# --------------------------------------------------------------------------------------
# (i) PROOF OF EFFECT
# --------------------------------------------------------------------------------------
def test_producer_emits_full_send_on_a_cohort_vetoed_named_setup():
    sig = _signal_from(_vetoed_core_row())
    blk = sig["full_send"]["bull"]
    assert blk["available"] is True
    assert blk["blocked_verdict"] == "SKIP_ELITE_BULL_LEVEL_RECLAIM"
    assert blk["level"] == 743.25
    assert blk["setup_name"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON"


def test_full_send_arm_enters_where_the_gated_arms_are_blocked():
    """THE headline guard. Same tick, same signal: the gated arms produce no ENTER; the
    full-send arm does. RED-proof: revert risky-1's gate_override and this fails."""
    sig = _signal_from(_vetoed_core_row())

    fs_plans = fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, BOLD_PARAMS)
    fs_enters = [p for p in fs_plans if p.action == "ENTER"]
    assert fs_enters, "full-send arm must ENTER on a cohort-vetoed named setup"
    assert fs_enters[0].reason.startswith("FULL_SEND cohort=elite_bull_level_reclaim")
    assert fs_enters[0].trigger_level == 743.25

    for gated_id in ("safe-3", "risky-3"):
        arm = _arm(gated_id)
        plans = fx.plan_all(arm, sig, EQUITY, BOLD_PARAMS,
                            probe_cfg=ACCOUNTS.get("probe_arm"))
        assert not [p for p in plans if p.action == "ENTER"], (
            f"{gated_id} must NOT enter on this cohort-vetoed tick -- if it does, the "
            "full-send lane is leaking into arms that never opted in")


def test_full_send_is_min_size_and_never_the_arms_normal_sizing():
    sig = _signal_from(_vetoed_core_row())
    plan = [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, BOLD_PARAMS)
            if p.action == "ENTER"][0]
    assert plan.qty == int(BOLD_PARAMS["min_contracts"])
    normal_qty = fx._qty_for(BOLD_PARAMS.get("position_sizing_tiers"), EQUITY, True)
    if normal_qty is not None:
        assert plan.qty <= normal_qty, "full-send must never size ABOVE the arm's normal qty"


def test_min_size_clamp_applies_to_NORMAL_entries_too_not_just_rescued_ones():
    """The "never loose on RISK" half. A high-score tick routes through the arm's NORMAL lane
    (scoring-peak already passed it), and the clamp must STILL bind there -- otherwise a
    full-send arm would take MORE trades at FULL bold size, the exact inversion of intent.

    NON-VACUITY (this test was VACUOUS on first write and the RED-proof caught it): the
    UNRELATED recency clamp (_apply_recency_min_sizing) is currently RED and independently
    clamps 12 -> min_contracts, so with live params the assertion passed even with the
    full-send clamp deleted. `recency_min_size_enabled: False` disables that path so the ONLY
    thing that can produce min size here is the full-send clamp. RED-proof (verified): delete
    the _apply_full_send_min_sizing call in _plan_from_strategies and this fails."""
    params = {**BOLD_PARAMS, "recency_min_size_enabled": False}
    unclamped = fx._qty_for(params.get("position_sizing_tiers"), EQUITY, True)
    assert unclamped and unclamped > int(params["min_contracts"]), (
        "fixture broken: normal sizing must exceed min_contracts or this test is vacuous")

    sig = _signal_from(_vetoed_core_row(bull_score=11))
    plan = [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, params)
            if p.action == "ENTER"][0]
    assert not str(plan.reason).startswith("FULL_SEND"), "fixture must exercise the NORMAL lane"
    assert plan.qty == int(params["min_contracts"])
    assert "FULL_SEND min size" in str(plan.reason)

    # vary-and-assert: a NON-full-send arm on the identical signal keeps its FULL sizing
    other = [p for p in fx.plan_all(_arm("risky-3"), sig, EQUITY, params) if p.action == "ENTER"]
    assert other and other[0].qty == unclamped, (
        "the clamp must be scoped to full-send arms only, never global")


def test_full_send_prices_ATM_via_PROBE_STRIKE_TIERS_not_the_arms_normal_tier():
    """PINS THE TRUE SHIPPED BEHAVIOR: the full-send lane prices ATM.

    HISTORY -- READ BEFORE CHANGING. This guard previously asserted the OPPOSITE ("full-send
    must price the SAME strike as its sizing-peer arm"), claiming to pin a REVERTED ATM
    override. It was VACUOUS: its fixture used bull_score=11, which the PRE-EXISTING
    scoring-peak lane already rescues, so `_full_send_plan` never ran in it and the assertion
    only ever compared two NORMAL-lane plans. It stayed green while the override was live.
    The revert had in fact only been applied to `_tiers_for_arm`, which the full-send lane
    never calls (`_full_send_plan` -> `PROBE_STRIKE_TIERS` directly, fleet_executor ~L849).

    DECISION (2026-07-31 evening): KEEP ATM. It is precisely what clears the UNTOUCHED $0.30
    min_entry_premium floor that refused risky-1 on 15 of its 16 named-setup ticks on
    2026-07-31 -- the entire reason the arm exists. So this guard now pins the behavior that
    actually ships, rather than asserting a revert that never happened.

    THE HONEST LABEL THAT GOES WITH IT: the A/B's headline full_send cell was measured at
    strike_offset=2 (OTM-2). Production trades offset=0. That cell DOES NOT APPLY to this lane
    (OP-16 sim-accuracy) -- the incremental trades this arm adds are UNMEASURED AT THEIR ACTUAL
    STRIKE, and every surface (accounts.json full_send_doc, the scorecard JSON + MD) says so.

    NON-VACUITY is asserted explicitly below: the plan under test must carry a FULL_SEND
    reason, and the normal lane must price a DIFFERENT strike, or the test fails loudly.
    RED-proof (verified): point `_full_send_plan` at `_tiers_for_arm(arm)` and this fails."""
    # bull_score=7 -- BELOW the scoring peak, so the full-send lane is the ONLY thing that can
    # take this trade. (At 11 the scoring-peak lane rescues it and this lane never runs.)
    sig = _signal_from(_vetoed_core_row(bull_score=7))
    spot = float(sig["spot"])
    fs = [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, BOLD_PARAMS)
          if p.action == "ENTER"][0]

    # --- NON-VACUITY: this must be the full-send lane, not some other lane's plan ----------
    assert str(fs.reason).startswith("FULL_SEND cohort="), (
        f"fixture broken -- this test must exercise _full_send_plan, got reason={fs.reason!r}. "
        "A score at/above the peak makes this test vacuous (that was the original defect).")

    # --- the shipped strike IS the ATM/PROBE table ----------------------------------------
    expected_atm = fx.strike_selection.pick_strike(spot, EQUITY, fs.side, fx.PROBE_STRIKE_TIERS)
    assert fs.strike == expected_atm, "full-send must price PROBE_STRIKE_TIERS (ATM at $2K)"
    assert fs.strike == 744, f"canary: spot {spot} ATM call strike should be 744, got {fs.strike}"

    # --- vary-and-assert: the lane reads PROBE's table, never _tiers_for_arm ---------------
    # AMENDED 2026-08-04 (chain-walk lane): ATM-TIER-EXTENSION-2K-10K (1fbde442, prereg
    # 625c6a80) repointed bold_core's $2K-10K row OTM-2 -> ATM, so at the original $2K
    # fixture the two tables now AGREE and the old hard `fs.strike != arm_tier_strike`
    # assertion went vacuous-by-cure (it asserted the DEFECT's exhibit, not the mechanism).
    # The mechanism claim ("full-send prices PROBE, never the arm's table") keeps its teeth
    # at the first equity where the tables still DIVERGE on the committed tables --
    # $10K-25K: bold_core OTM-1 vs PROBE ITM-1. _full_send_plan never consults
    # position_sizing_tiers (min_contracts hard clamp), so the lane fires at this equity
    # regardless of sizing-tier coverage. RED-proof unchanged: point _full_send_plan at
    # _tiers_for_arm(arm) and the diverging-equity assertions fail.
    arm_tier_strike = fx.strike_selection.pick_strike(spot, EQUITY, fs.side,
                                                     fx._tiers_for_arm(_arm(FULL_SEND_ARM_ID)))
    DIVERGE_EQUITY = 12_000.0
    probe_12k = fx.strike_selection.pick_strike(spot, DIVERGE_EQUITY, fs.side,
                                                fx.PROBE_STRIKE_TIERS)
    arm_12k = fx.strike_selection.pick_strike(spot, DIVERGE_EQUITY, fs.side,
                                              fx._tiers_for_arm(_arm(FULL_SEND_ARM_ID)))
    assert probe_12k != arm_12k, (
        "fixture broken: the two tables must still diverge SOMEWHERE (currently $10K-25K: "
        f"bold_core OTM-1 vs PROBE ITM-1) -- got {arm_12k} vs {probe_12k}")
    fs_12k = [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, DIVERGE_EQUITY, BOLD_PARAMS)
              if p.action == "ENTER" and str(p.reason).startswith("FULL_SEND cohort=")]
    assert fs_12k, "full-send lane must fire at the diverging equity too (sizing-tier-free)"
    assert fs_12k[0].strike == probe_12k, (
        "full-send must price PROBE's table at an equity where the arm's own table differs "
        f"(got {fs_12k[0].strike}, PROBE says {probe_12k}, arm table says {arm_12k})")

    # --- and the arm's NORMAL lane is untouched: it still prices the arm's own table -------
    normal_sig = _signal_from(_vetoed_core_row(bull_score=11))
    normal = [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), normal_sig, EQUITY, BOLD_PARAMS)
              if p.action == "ENTER"][0]
    assert not str(normal.reason).startswith("FULL_SEND cohort="), (
        "fixture broken -- the score-11 tick must route through the NORMAL lane")
    assert normal.strike == arm_tier_strike, (
        "the normal lane must price the arm's own tier table (post-ATM-extension the two "
        "tables agree at $2K, so this is a same-value check here; the $12K divergence block "
        "above carries the discriminating assertion)")
    assert fx._tiers_for_arm(_arm(FULL_SEND_ARM_ID)) is not fx.PROBE_STRIKE_TIERS, (
        "the arm's own tier table must never BE the probe table -- that half of the revert "
        "is real and stays")


def test_lane_is_inert_for_every_arm_that_did_not_opt_in():
    """Producer emits the block unconditionally; ONLY gate_override.full_send consumes it."""
    sig = _signal_from(_vetoed_core_row())
    for arm in ACCOUNTS["arms"]:
        if arm.get("status") != "active" or arm["id"] == FULL_SEND_ARM_ID:
            continue
        assert fx._full_send_plan(arm, sig, EQUITY, BOLD_PARAMS, arm["id"], sig.get("spot")) is None


# --------------------------------------------------------------------------------------
# (i-b) SELECTION IS ALLOWLISTED -- it must NOT rescue anything outside the measured package
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("verdict", [
    "SKIP_NO_LEVELS",            # SIGHT failure -- blindness, no tier trades through it
    "SKIP_EARLY_ENTRY",          # time gate
    "SKIP_LATE_ENTRY",           # time gate
    "SKIP_STALE_TRIGGER",        # time gate
    "SKIP_STRUCTURE_VETO",       # structural
    "SKIP_BAD_INPUT",            # data integrity
    "SKIP_RIBBON_MOMENTUM_GATE", # a real cohort gate, but NOT in the measured package
    "SKIP_DOJI_ENTRY_BAR",       # ditto
    "HOLD",                      # plain scoring hold -- ladder's turf, not this lane's
])
def test_non_allowlisted_verdicts_never_produce_a_full_send_entry(verdict):
    sig = _signal_from(_vetoed_core_row(verdict))
    assert sig["full_send"]["bull"]["available"] is False
    assert not [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, BOLD_PARAMS)
                if p.action == "ENTER" and str(p.reason).startswith("FULL_SEND")]


def test_no_level_means_no_trade():
    """A full-send entry is never stop-less."""
    row = _vetoed_core_row()
    row["trigger_level_exact"] = None
    row["bull_reclaim_level_raw"] = None
    sig = _signal_from(row)
    assert sig["full_send"]["bull"]["available"] is False


def test_allowlist_is_exactly_the_measured_package():
    """Drift guard: the shipped allowlist must equal the 5 cohort gates the pre-registered A/B
    actually measured. Adding a 6th without a new A/B is the multiple-comparisons trap."""
    assert bss.FULL_SEND_ALLOWED_VERDICTS == frozenset({
        "SKIP_ELITE_BULL_LEVEL_RECLAIM", "SKIP_BULL_1100_1200",
        "SKIP_CONF_LVL_REC_AFTERNOON", "SKIP_LEVEL_REJECTION_GATE",
        "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY",
    })


# --------------------------------------------------------------------------------------
# (ii) PROOF OF SAFETY -- THE GUARD THAT MATTERS
# --------------------------------------------------------------------------------------
def _fs_plan():
    sig = _signal_from(_vetoed_core_row())
    plans = [p for p in fx.plan_all(_arm(FULL_SEND_ARM_ID), sig, EQUITY, BOLD_PARAMS)
             if p.action == "ENTER"]
    assert plans, "fixture broken: expected a full-send ENTER plan"
    return plans[0]


def _finalize(plan, **over):
    kw = dict(equity=EQUITY, start_of_day_equity=EQUITY, premium=1.20,
              current_position_status=None, day_trades_used_5d=0,
              kill_switch_tripped=False, prior_stops_today=[],
              params=BOLD_PARAMS, account_label="PA3W17FD8G19")
    kw.update(over)
    return fx.finalize(plan, **kw)


def test_baseline_full_send_plan_is_allowed_when_nothing_is_wrong():
    """Control for the blocking tests below -- without it, a lane that ALWAYS blocked would
    pass every safety test vacuously."""
    d = _finalize(_fs_plan())
    assert d.risk_code == "ALLOW" and d.action == "ENTER_BULL"


def test_kill_switch_still_blocks_a_full_send_entry():
    d = _finalize(_fs_plan(), kill_switch_tripped=True)
    assert d.action == "HOLD" and d.risk_code == "KILL_SWITCH"


def test_no_add_one_position_rule_still_blocks_a_full_send_entry():
    """Rule 4 -- broker says a position is already open."""
    d = _finalize(_fs_plan(), current_position_status="open")
    assert d.action == "HOLD" and d.risk_code == "NOT_FLAT"


def test_per_trade_risk_cap_still_blocks_a_full_send_entry():
    """Rule 6 -- min-size does not exempt the notional cap."""
    d = _finalize(_fs_plan(), premium=9.99)
    assert d.action == "HOLD" and d.risk_code == "RISK_CAP"


def test_pdt_rule_still_blocks_a_full_send_entry():
    d = _finalize(_fs_plan(), day_trades_used_5d=3, equity=2000.0)
    assert d.action == "HOLD" and d.risk_code == "PDT"


def test_min_entry_premium_floor_still_blocks_a_full_send_entry():
    """The anti-spread-noise floor is NEVER bypassed for this lane."""
    d = _finalize(_fs_plan(), premium=0.05)
    assert d.action == "HOLD" and d.risk_code == "SKIP_MIN_PREMIUM_FLOOR"


def test_full_send_plans_go_through_finalize_not_around_it():
    """Structural: plan_all only ever emits PLANS. The single risk authority is finalize(),
    and a plan is never an order until it passes. Proven by the fact that a raw ENTER plan
    carries no risk_code at all -- only an ArmDecision does."""
    plan = _fs_plan()
    assert plan.action == "ENTER"
    assert not hasattr(plan, "risk_code")


def test_eod_flatten_covers_the_full_send_arm():
    """The 15:55 flatten iterates ACTIVE fleet_rest arms -- arming full-send must not have
    removed this arm from that scope."""
    arm = _arm(FULL_SEND_ARM_ID)
    assert arm["status"] == "active" and arm["execution"] == "fleet_rest" and arm["live"] is True


def test_full_send_arm_is_still_a_risk_profile_not_a_strategy():
    """Doctrine guard (memory: arms are RISK PROFILES, not strategies). The lane may only
    ever produce ribbon_ride's own validated setups -- never a new strategy or setup name."""
    plan = _fs_plan()
    assert plan.strategy == "ribbon_ride"
    assert plan.setup_name.upper() in fx.PROBE_RIBBON_SETUPS


# =============================================================================
# SELECTIVITY-GATE REGRESSION GUARD (2026-08-12)
# =============================================================================
# Commit e28d210c (2026-07-31 16:21) intended to ADD the full-send producer lane. It
# SWAPPED risky-1's whole gate_override dict instead:
#     -{"min_triggers": 2, "require_confluence_or_sequence": true}
#     +{"full_send": true}
# The two key families are ORTHOGONAL in source -- _gate_check reads only min_triggers /
# require_confluence_or_sequence / min_setup_quality and never sees full_send; _is_full_send
# reads only full_send -- so the swap DELETED the arm's entry gate and bought nothing.
# accounts.json's own map_doc recorded the accident on 2026-08-02; nothing repaired it for
# 12 days. On 2026-08-12 risky-1 took 16 of the book's 38 positions while its live twin
# safe-3, running these exact keys, blocked 49 of the 83 identical signal-ticks.
# THESE TESTS WOULD HAVE GONE RED ON e28d210c. That is the whole point of them.


def test_risky1_selectivity_gate_survives_full_send():
    """THE REGRESSION GUARD: arming/adjusting full_send must never remove the entry gate."""
    go = _arm(FULL_SEND_ARM_ID).get("gate_override") or {}
    assert go.get("min_triggers", 0) >= 2, (
        f"risky-1 lost its min_triggers gate -- this is the e28d210c regression. gate_override={go}")
    assert go.get("require_confluence_or_sequence") is True, (
        f"risky-1 lost require_confluence_or_sequence -- e28d210c regression. gate_override={go}")


def test_full_send_and_selectivity_keys_coexist():
    """They are orthogonal key families: restoring the gate must NOT de-arm full-send,
    and arming full-send must NOT clear the gate. Both must read True off the same dict."""
    arm = _arm(FULL_SEND_ARM_ID)
    go = arm.get("gate_override") or {}
    assert go.get("full_send") is True, "full_send was dropped while restoring the gate"
    assert fx._is_full_send(arm) is True, "_is_full_send no longer recognises the arm"
    assert {"min_triggers", "require_confluence_or_sequence"} <= set(go), (
        "gate keys missing from the same dict that carries full_send")


def test_risky1_gate_matches_its_live_twin_safe3():
    """safe-3 is risky-1's gate twin (same selectivity, different sizing). They diverged
    only because of the accidental deletion -- pin them back together so a future edit to
    one is a visible, deliberate divergence rather than a silent one."""
    r1 = (_arm(FULL_SEND_ARM_ID).get("gate_override") or {})
    s3 = (_arm("safe-3").get("gate_override") or {})
    for k in ("min_triggers", "require_confluence_or_sequence"):
        assert r1.get(k) == s3.get(k), (
            f"risky-1 and safe-3 disagree on {k}: {r1.get(k)!r} vs {s3.get(k)!r}. "
            "If this divergence is intentional, update this guard with the reason.")
