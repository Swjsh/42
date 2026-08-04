"""test_risky1_lane_composition_check.py -- guards for setup/scripts/
risky1_lane_composition_check.py and the composition claims it proves.

WHY THIS EXISTS: the 2026-08-02 day+1 audit (analysis/recommendations/
fleet-strike-tier-atm-2026-08-02.md) mischaracterized risky-1's normal lane as
"tight-gated (min_triggers=2 + confluence/sequence required)". That claim is FALSE on the
current accounts.json (commit e28d210c REPLACED, not merged, that gate_override with
{"full_send": true}) -- already independently caught the same night by
FLEET-PARITY-TESTS-READ-LIVE-STATE (commit dea5b2e2). These tests pin the CORRECTED,
empirically-verified composition so it cannot silently drift back to the wrong story, and
RED-proof the specific claims risky1_lane_composition_check.py's docstring makes.

Run: backtest/.venv/Scripts/python.exe -m pytest automation/state/fleet/test_risky1_lane_composition_check.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parent
REPO = FLEET.parents[2]
sys.path.insert(0, str(FLEET))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import fleet_executor as fx  # noqa: E402
import risky1_lane_composition_check as lcc  # noqa: E402

ACCOUNTS = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
BOLD_PARAMS = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                         .read_text(encoding="utf-8"))


def _arm(arm_id: str) -> dict:
    for a in ACCOUNTS["arms"]:
        if a["id"] == arm_id:
            return a
    raise AssertionError(f"arm {arm_id} missing from accounts.json")


# --------------------------------------------------------------------------------------
# 1. THE CORRECTED FACT: risky-1's gate_override carries no trigger-count/confluence gate.
# --------------------------------------------------------------------------------------
def test_risky1_gate_override_is_full_send_only_not_tight():
    """DRIFT GUARD + CORRECTION-OF-RECORD pin: the 2026-08-02 audit's premise
    ("min_triggers=2 + confluence/sequence required") requires these keys to be present.
    They are not -- e28d210c replaced the whole dict. If this ever fails because the keys
    reappeared, the composition conclusion in this module's docstring must be re-derived,
    not assumed."""
    g = _arm("risky-1").get("gate_override") or {}
    assert g == {"full_send": True}, (
        f"risky-1.gate_override changed to {g!r} -- re-derive the lane composition proof, "
        "the 'normal lane is ungated' finding no longer holds as stated")
    assert "min_triggers" not in g
    assert "require_confluence_or_sequence" not in g


def test_risky1_gate_check_passes_with_zero_selectivity_demands():
    """RED-proof: fx._gate_check(risky-1, ...) must return None (pass) for a block with
    only ONE trigger and no confluence -- if a future edit reinstates min_triggers/
    require_confluence_or_sequence, this fails, proving the test actually discriminates."""
    arm = _arm("risky-1")
    blk = {"triggers_fired": ["level_rejection"], "confluence": False}
    assert fx._gate_check(arm, blk, {}) is None
    # vary-and-assert: an arm that DOES carry those keys must still be gated (proves the
    # None result above is because risky-1's config lacks the gate, not because
    # _gate_check itself is broken/inert).
    tight_arm = dict(arm)
    tight_arm["gate_override"] = {"min_triggers": 2, "require_confluence_or_sequence": True}
    assert fx._gate_check(tight_arm, blk, {}) is not None


def test_grid_map_metadata_matches_the_arms_own_cell_field():
    """The stale-doc bug this session found and fixed: grid.map is display-only metadata
    that must not contradict the arm's own live `cell` field. RED-proofed by construction --
    this failed before the accounts.json fix in the same commit as this test."""
    grid_map = (ACCOUNTS.get("grid") or {}).get("map", {})
    arm = _arm("risky-1")
    assert grid_map.get("risky-1") == arm.get("cell"), (
        f"grid.map['risky-1']={grid_map.get('risky-1')!r} disagrees with the arm's own "
        f"cell={arm.get('cell')!r} -- this exact drift is what produced the 2026-08-02 "
        "audit's 'tight-gated' error")


# --------------------------------------------------------------------------------------
# 2. Normal lane fires ungated (proves point 1 behaviorally, not just via config read).
# --------------------------------------------------------------------------------------
def test_normal_lane_enters_on_a_single_base_trigger_no_elite_needed():
    sig = lcc._signal(lcc.SCENARIOS["1_NORMAL_PASS"])
    enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
    assert enters, "risky-1 must enter on a plain single-trigger BASE-quality pass"
    assert lcc._lane(enters[0].reason) == "normal"
    assert enters[0].quality == "BASE"


# --------------------------------------------------------------------------------------
# 3. Strike-table agreement is equity-contingent -- vary equity, watch the verdict flip.
# --------------------------------------------------------------------------------------
def test_strike_tables_agree_below_10k_and_diverge_at_and_above_10k():
    """THE central vary-and-assert of this correction: same two tables, same helper, only
    the equity input changes, and the agreement verdict flips. If either strike table is
    ever edited such that this stops flipping, the 'coincidence, not guarantee' framing in
    risky1_lane_composition_check.py's docstring is stale and must be revisited.

    BOUNDARY MOVED 2026-08-04 (amended by the chain-walk lane when this pin went stale):
    ATM-TIER-EXTENSION-2K-10K (commit 1fbde442, prereg 625c6a80) repointed bold_core's
    $2K-10K row OTM-2 -> ATM, so agreement now extends through $10K and the first
    divergence bracket is $10K-25K (bold_core OTM-1 vs PROBE ITM-1). The 'coincidence,
    not guarantee' framing HOLDS -- only the boundary moved. Revert of the extension
    (restore -2 on the $2K-10K row) must flip this test back, which is exactly the
    stale-pin alarm this guard exists to raise."""
    for eq in (1_999.99, 2_000.0, 9_999.0):
        core = fx.strike_selection.pick_tier(eq, fx.strike_selection.V15_BOLD_CORE_TIERS)
        probe = fx.strike_selection.pick_tier(eq, fx.PROBE_STRIKE_TIERS)
        assert core.strike_offset == probe.strike_offset == 0, (
            f"at ${eq:,.2f} both tables must be ATM post-extension "
            f"(core={core.strike_offset}, probe={probe.strike_offset})")

    at_or_above = fx.strike_selection.pick_tier(10_000.0, fx.strike_selection.V15_BOLD_CORE_TIERS)
    at_or_above_probe = fx.strike_selection.pick_tier(10_000.0, fx.PROBE_STRIKE_TIERS)
    assert at_or_above.strike_offset != at_or_above_probe.strike_offset
    assert at_or_above.strike_offset == -1       # OTM-1
    assert at_or_above_probe.strike_offset == +1  # Slight ITM


def test_full_send_lane_strike_is_never_derived_from_tiers_for_arm():
    """Mechanical proof that bold_core is INERT on the full-send lane specifically: run the
    cohort-veto scenario at an equity where the two tables DIVERGE (>=$2K) and confirm the
    fill still prices ATM (PROBE_STRIKE_TIERS), never OTM-2 (what _tiers_for_arm/bold_core
    would give the normal lane at this same equity)."""
    sig = lcc._signal(lcc.SCENARIOS["2_COHORT_VETO_BELOW_PEAK"])
    enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.ABOVE_2K_EQUITY, BOLD_PARAMS)
    assert enters and lcc._lane(enters[0].reason) == "FULL_SEND"
    # side is 'C' (bull/call) at spot 745.0: ATM strike == round(spot) == 745.
    assert enters[0].strike == 745, (
        f"full-send strike={enters[0].strike} -- expected ATM (745), unaffected by bold_core "
        "even though this equity sits in the bracket where bold_core would price OTM-2")


# --------------------------------------------------------------------------------------
# 4. Attribution survives: every full-send fill is tagged and distinguishable from normal.
# --------------------------------------------------------------------------------------
def test_full_send_entries_always_carry_the_full_send_reason_prefix():
    for name in ("2_COHORT_VETO_BELOW_PEAK", "3_HARD_SKIP_FILL_BAR_ABOVE_PEAK"):
        sig = lcc._signal(lcc.SCENARIOS[name])
        enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
        assert enters, f"{name}: expected a full-send rescue entry"
        assert enters[0].reason.startswith("FULL_SEND"), (
            f"{name}: reason={enters[0].reason!r} does not carry the FULL_SEND tag -- "
            "full_send_vs_gated.py's _lane() would misclassify this fill as 'normal'")

    sig = lcc._signal(lcc.SCENARIOS["1_NORMAL_PASS"])
    enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
    assert enters and not enters[0].reason.startswith("FULL_SEND"), (
        "a normally-passing tick must NOT carry the FULL_SEND tag")


# --------------------------------------------------------------------------------------
# 5. ADDITIONAL FINDING (flagged as a follow-up, not fixed here): risky-3's own hard-skip
#    opt-out is dead on the live path. Documented as a pinned CURRENT-BEHAVIOR test so a
#    future fix to build_shared_signal/_strategies_block shows up here as an intentional
#    change, not a silent one.
# --------------------------------------------------------------------------------------
def test_risky3_hard_skip_override_is_currently_not_consulted_by_plan_all():
    """Pins a SURPRISING, currently-live gap found while proving risky-1's composition:
    risky-3's gate_params.hard_skip_verdicts=[] (GATE-TIERS-IMPLEMENT, 2026-07-23, built
    specifically to let risky-3 trade through require_bearish_fill_bar) is NEVER consulted
    by fleet_live.py's actual call path (plan_all -> _plan_from_strategies, which reads
    signal['strategies'] -- built ONCE, uniformly, upstream of any per-arm rescue;
    _effective_passed, the function that reads hard_skip_verdicts, is only ever called from
    plan_entry, which production does not call). This means risky-1's FULL_SEND lane is
    currently the ONLY fleet mechanism that can trade a SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY
    tick, on ANY arm -- risky-3's parallel mechanism is dead code on the live path.
    NOT fixed here (out of this session's two assigned problems, touches shared
    signal-construction code) -- flagged via spawn_task. If a future fix wires
    _effective_passed into _plan_from_strategies, THIS test should start failing (risky-3
    would then ENTER), and should be updated deliberately, not silently."""
    sig = lcc._signal(lcc.SCENARIOS["3_HARD_SKIP_FILL_BAR_ABOVE_PEAK"])
    r3_enters, _ = lcc.enter_plans(ACCOUNTS, "risky-3", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
    assert not r3_enters, (
        "risky-3 entered on a hard-skip fill-bar tick -- its hard_skip_verdicts=[] override "
        "is now being consulted by the live path; update this test deliberately and correct "
        "the 'risky-1's full-send lane is uniquely irreplaceable' claim in "
        "risky1_lane_composition_check.py's docstring")
    # control: risky-1's full-send lane DOES take this same tick (the arm this session is
    # actually about is not similarly dead).
    r1_enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
    assert r1_enters and lcc._lane(r1_enters[0].reason) == "FULL_SEND"


# --------------------------------------------------------------------------------------
# 6. The script's pure run() stays callable and internally consistent (regression guard
#    for the tool itself, not just the config it reads).
# --------------------------------------------------------------------------------------
def test_run_produces_the_expected_shape():
    r = lcc.run()
    assert r["risky1_gate_override"] == {"full_send": True}
    assert set(r["scenarios"]) == {
        f"{name}@{eq}" for name in lcc.SCENARIOS
        for eq in ("live_lt_2k", "above_2k")
    }
    diverging = [row for row in r["strike_table_agreement_by_equity"] if not row["agree"]]
    agreeing = [row for row in r["strike_table_agreement_by_equity"] if row["agree"]]
    assert diverging and agreeing, "equity sweep must exercise BOTH the agreeing and diverging brackets"
