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

AMENDED 2026-08-12 -- THESE PINS WERE PINNING AN ACCIDENT. The "normal lane is ungated"
composition locked in here was never designed; it was the side effect of e28d210c swapping
risky-1's gate_override dict instead of merging into it. On 2026-08-12 risky-1 took 16 of the
book's 38 positions while its gate twin safe-3 -- running the exact keys e28d210c deleted --
blocked 49 of the 83 identical signal-ticks. The gate was restored that night and every
affected pin was RE-DERIVED (not deleted), per the instruction the original gate_override pin
wrote into its own docstring. Each amended test carries its reason inline. Discriminating
power is preserved: every vary-and-assert still runs, expectation inverted rather than
removed. Evidence: analysis/deep-research/2026-08-12-churn/.

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
def test_risky1_gate_override_is_full_send_PLUS_the_restored_gate():
    """AMENDED 2026-08-12 -- the re-derivation this pin's own docstring demanded.

    The original asserted gate_override == {"full_send": True} and said: "If this ever fails
    because the keys reappeared, the composition conclusion must be RE-DERIVED, not assumed."
    They reappeared DELIBERATELY. Here is the re-derivation.

    WHAT CHANGED: e28d210c (2026-07-31) intended to ADD the full-send producer lane; it
    SWAPPED the whole dict and silently deleted risky-1's entry gate. accounts.json's own
    map_doc recorded that accident on 2026-08-02 -- and these tests then pinned the ACCIDENT
    as though it were the design. On 2026-08-12 risky-1 took 16 of the book's 38 positions
    while its gate twin safe-3, running these exact keys, blocked 49 of the 83 identical
    signal-ticks. Gate restored that night (churn teardown, 15-agent workflow).

    WHY 'UNGATED NORMAL LANE' NO LONGER HOLDS: it was never a design property, only the
    observable consequence of a dict swap. The key families are ORTHOGONAL in source
    (_gate_check reads min_triggers / require_confluence_or_sequence / min_setup_quality and
    never sees full_send; _is_full_send reads only full_send), so both coexist."""
    g = _arm("risky-1").get("gate_override") or {}
    assert g.get("full_send") is True, f"full_send lost from risky-1.gate_override: {g!r}"
    assert g.get("min_triggers") == 2, (
        f"risky-1 lost its restored min_triggers gate: {g!r} -- if deliberate, re-derive the "
        "lane composition proof again and amend this pin with the reason")
    assert g.get("require_confluence_or_sequence") is True, (
        f"risky-1 lost require_confluence_or_sequence: {g!r}")


def test_risky1_gate_check_now_BLOCKS_a_single_trigger_no_confluence_tick():
    """AMENDED 2026-08-12 (gate restored). Same discriminating structure, expectation
    inverted: risky-1 must now REFUSE the thin tick it used to take. The vary-and-assert
    runs in BOTH directions, so this still proves _gate_check is live rather than inert --
    it is the behavioural assertion that would have caught e28d210c."""
    arm = _arm("risky-1")
    blk = {"triggers_fired": ["level_rejection"], "confluence": False}
    assert fx._gate_check(arm, blk, {}) is not None, (
        "risky-1 took a 1-trigger no-confluence tick -- its restored gate is not binding")
    # other direction: strip the gate keys and the SAME block must pass, proving the refusal
    # comes from the config and not from a broken/always-deny gate.
    ungated = dict(arm)
    ungated["gate_override"] = {"full_send": True}
    assert fx._gate_check(ungated, blk, {}) is None, (
        "_gate_check refuses even without selectivity keys -- it is not discriminating")
    assert fx._is_full_send(arm) is True  # orthogonal families both live


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
def test_normal_lane_NO_LONGER_enters_on_a_single_base_trigger():
    """AMENDED 2026-08-12 (gate restored) -- behavioural counterpart of the config pin, and
    the entire point of the restoration. 1_NORMAL_PASS is a plain single-trigger BASE tick:
    exactly the cohort that produced risky-1's 16-of-38 entry share on 2026-08-12. With
    min_triggers=2 + confluence/sequence required it must be refused on the normal lane."""
    sig = lcc._signal(lcc.SCENARIOS["1_NORMAL_PASS"])
    enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
    normal = [e for e in enters if lcc._lane(e.reason) == "normal"]
    assert not normal, (
        "risky-1's normal lane still enters on a single-trigger BASE tick: "
        f"{[e.reason for e in normal]!r} -- restored gate is not binding on the plan path")


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

    # AMENDED 2026-08-12: with the gate restored, 1_NORMAL_PASS (single-trigger BASE) no
    # longer yields a NORMAL entry. Whatever it yields must be nothing, or a correctly-tagged
    # FULL_SEND rescue -- never an untagged fill, which is the misclassification
    # full_send_vs_gated.py._lane() exists to prevent.
    sig = lcc._signal(lcc.SCENARIOS["1_NORMAL_PASS"])
    enters, _ = lcc.enter_plans(ACCOUNTS, "risky-1", sig, lcc.RISKY1_LIVE_EQUITY, BOLD_PARAMS)
    for e in enters:
        assert e.reason.startswith("FULL_SEND"), (
            f"post-gate-restore a single-trigger BASE tick produced untagged entry {e.reason!r} "
            "-- it would be misattributed to the normal lane")


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
    # AMENDED 2026-08-12: gate restored alongside full_send (orthogonal key families).
    assert r["risky1_gate_override"] == {
        "full_send": True, "min_triggers": 2, "require_confluence_or_sequence": True}
    assert set(r["scenarios"]) == {
        f"{name}@{eq}" for name in lcc.SCENARIOS
        for eq in ("live_lt_2k", "above_2k")
    }
    diverging = [row for row in r["strike_table_agreement_by_equity"] if not row["agree"]]
    agreeing = [row for row in r["strike_table_agreement_by_equity"] if row["agree"]]
    assert diverging and agreeing, "equity sweep must exercise BOTH the agreeing and diverging brackets"
