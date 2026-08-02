"""Guard: V15_BOLD_CORE_TIERS (2026-07-15 evening) -- the core-Bold-only ATM candidate
table for the $0-$2K tier, built from the bold-strike-axis-2026-07-15.json OOS study.

STATUS UPDATE 2026-07-18: WIRED. J gave explicit in-chat authorization ("Yes -- wire
Bold to ATM", 2026-07-17 night), ending the hold described below. Both live call sites
now read V15_BOLD_CORE_TIERS for the bold branch -- tests 5 (below) were flipped from
"not_yet_repointed" to "repointed_to_core_tiers" in the SAME commit as the
heartbeat_core.py / j_intent_executor.py edits. This ships as a PARTICIPATION fix
(OTM-3's structural floor-collision vs ATM's clean floor-clearance), NOT a claim that
the regime-parked P&L evidence below cleared OP-16's auto-ratify bar -- it did not, and
that is still honestly disclosed. Falsification rail: first n>=20 live Bold fills under
this tier get an expectancy check (automation/overnight/queue.md). Revert is one line
per call site, back to V15_BOLD_TIERS.

STATUS AS OF 2026-07-15 evening (historical, pre-wiring): this file guarded a table
that EXISTED but was DELIBERATELY NOT WIRED into any live call site yet. See
crypto/lib/strike_selection.py's V15_BOLD_CORE_TIERS docstring for the full record.
Short version: the evidence file's own near_miss_diagnostic labels this candidate
"WATCH -- NOT ship-ready" (fails wf_ge_070) and automation/overnight/queue.md's
WF-GATE-STRUCTURALLY-NULL entry (filed the same evening) says "re-adjudicate once the
WF redesign lands" / "Do NOT silently drop the gate." Per OP-16 (auto-ratify requires
ALL of OOS_positive AND WF>=0.70 AND sub_window_stable AND anchor_no_regression; "J is
NOT a ratification gate") and OP-32 (gate-provenance/redefinition questions route to
P2/Opus judgment, not mechanical Sonnet execution), this suite existed so the wiring
would be a reviewed one-line change whenever that re-adjudication landed -- superseded
2026-07-18 by J's direct authorization, which is a valid alternate path to shipping a
PARTICIPATION fix independent of the P&L auto-ratify gates (those remain unmet and are
disclosed as such above, not silently claimed).

WHAT THIS PROVES
-----------------
1. V15_BOLD_CORE_TIERS resolves ATM under $2K, and is IDENTICAL to V15_BOLD_TIERS at
   every tier above $2K (the task's "copy with ONLY the $0-2K tier changed" contract).
2. V15_BOLD_TIERS itself is BYTE-IDENTICAL / untouched under $2K (still OTM-3) --
   the critical regression guard: this is the exact assertion that would have RED'd
   the naive fix (directly editing V15_BOLD_TIERS in place) this file's history
   avoided shipping.
3. The two known SHARED consumers of V15_BOLD_TIERS -- automation/state/fleet/
   fleet_executor.py (_tiers_for_arm, arms safe-3/risky-1/risky-3) and
   setup/scripts/j_intent_executor.py (resolve_symbol, J-called conditional trades on
   the bold account) -- are UNCHANGED: both still resolve OTM-3 under $2K via the
   shared V15_BOLD_TIERS object, not the new table. j_intent_executor.py was NOT
   named as a consumer in the original naive-fix investigation; found here via a
   full-repo grep and pinned so it isn't silently forgotten by a future wiring pass.
4. Neither live call site (heartbeat_core.py's bold branch, j_intent_executor.py's
   bold branch) has been repointed at V15_BOLD_CORE_TIERS yet -- source-text pins
   that are EXPECTED to go RED and get updated the day a real wiring decision ships
   (C14 vary-and-assert: the pin must track true current behavior, not a wish).
5. crypto/validators/v20_strike_selection.py's T1/T2 pins (strike 743/737 for Bold
   $1K OTM-3) still match live pick_strike() output -- confirming they did NOT need
   updating, because V15_BOLD_TIERS was never touched.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bold_core_strike_tier_2026_07_15.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto.lib.strike_selection import (  # noqa: E402
    V15_BOLD_CORE_TIERS,
    V15_BOLD_TIERS,
    V15_SAFE_TIERS,
    pick_strike,
    pick_tier,
)

HEARTBEAT_CORE_SRC = (_SCRIPTS / "heartbeat_core.py").read_text(encoding="utf-8")
J_INTENT_EXECUTOR_SRC = (_SCRIPTS / "j_intent_executor.py").read_text(encoding="utf-8")
V20_VALIDATOR_SRC = (ROOT / "crypto" / "validators" / "v20_strike_selection.py").read_text(encoding="utf-8")

SPOT = 740.0  # matches v20_strike_selection.py's human-checkable convention


# =============================================================================
# 1. V15_BOLD_CORE_TIERS: new table resolves ATM under $2K, matches Bold above $2K
# =============================================================================

def test_core_tiers_resolve_atm_under_2k():
    for equity in (0.0, 1.0, 999.0, 1500.0, 1999.99):
        tier = pick_tier(equity, V15_BOLD_CORE_TIERS)
        assert tier.strike_offset == 0 and tier.label == "ATM", \
            f"equity={equity} should resolve ATM, got offset={tier.strike_offset} label={tier.label}"


def test_core_tiers_strike_math_atm_under_2k():
    call = pick_strike(SPOT, 1_000, "C", V15_BOLD_CORE_TIERS)
    put = pick_strike(SPOT, 1_000, "P", V15_BOLD_CORE_TIERS)
    assert call == 740, f"ATM bull call should be 740, got {call}"
    assert put == 740, f"ATM bear put should be 740, got {put}"


def test_core_tiers_match_bold_tiers_above_2k():
    """Only the $0-2K tier differs; every other bracket must be identical."""
    for equity in (2_000.0, 5_000.0, 9_999.0, 10_000.0, 24_999.0, 25_000.0, 100_000.0):
        core_tier = pick_tier(equity, V15_BOLD_CORE_TIERS)
        bold_tier = pick_tier(equity, V15_BOLD_TIERS)
        assert core_tier.strike_offset == bold_tier.strike_offset, (
            f"equity={equity}: core={core_tier.strike_offset} != bold={bold_tier.strike_offset}"
        )
        assert core_tier.label == bold_tier.label
        assert core_tier.equity_min == bold_tier.equity_min
        assert core_tier.equity_max == bold_tier.equity_max


# =============================================================================
# 2. CRITICAL REGRESSION GUARD: V15_BOLD_TIERS itself is untouched under $2K
# =============================================================================

def test_v15_bold_tiers_unchanged_under_2k_RED_PROOF():
    """This is the exact assertion the naive fix (editing V15_BOLD_TIERS in place)
    would have broken. If this ever REDs, someone edited the SHARED table instead of
    routing through V15_BOLD_CORE_TIERS -- fleet + j_intent_executor would silently
    change too."""
    for equity in (0.0, 1.0, 1000.0, 1999.99):
        tier = pick_tier(equity, V15_BOLD_TIERS)
        assert tier.strike_offset == -3 and tier.label == "OTM-3", \
            f"equity={equity}: V15_BOLD_TIERS must still be OTM-3, got {tier.label}"

    call = pick_strike(SPOT, 1_000, "C", V15_BOLD_TIERS)
    put = pick_strike(SPOT, 1_000, "P", V15_BOLD_TIERS)
    assert call == 743, f"V15_BOLD_TIERS bull call OTM-3 should be 743, got {call}"
    assert put == 737, f"V15_BOLD_TIERS bear put OTM-3 should be 737, got {put}"


def test_core_and_bold_tables_are_distinct_objects():
    assert V15_BOLD_CORE_TIERS is not V15_BOLD_TIERS
    assert V15_BOLD_CORE_TIERS != V15_BOLD_TIERS  # tuples compare by value too


# =============================================================================
# 3. FLEET ISOLATION -- safe-3 / risky-1 / risky-3 unaffected (fleet_executor.py)
# =============================================================================

def test_fleet_arms_resolve_otm3_under_2k_via_shared_table():
    """The task's critical regression guard, scoped to the ACTUAL <$2K/OTM-3 boundary
    this study concerns (test_fleet_arm_parity.py's own existing
    test_all_arms_bold_strike_tiers_at_2k checks equity==2000.0 exactly, which is
    already inside the OTM-2 bracket -- it does not cover this tier).

    UPDATED 2026-08-01 (FLEET-STRIKE-TIER-ATM-EXTENSION): risky-1/risky-3 were
    pre-registered + repointed to 'bold_core' (V15_BOLD_CORE_TIERS, ATM under $2K) --
    see analysis/recommendations/fleet-strike-tier-atm-extension-prereg-2026-08-01.json.

    UPDATED 2026-08-03 (FLEET-STRIKE-TIER-ATM-EXTENSION-SAFE3,
    analysis/deep-research/ARM-PARTICIPATION-AND-GROWTH-2026-08-03.md #1): safe-3 was
    ALSO repointed to 'bold_core' (see
    analysis/recommendations/fleet-strike-tier-atm-extension-safe3-prereg-2026-08-03.json)
    -- it is no longer a subject of this OTM-3 guard. The subject moved to safe-1
    (retired/inactive, but its accounts.json row still carries the explicit
    params_patch.strike_tier_table='bold' from the pre-2026-07-11 grid, untouched by
    either extension) so this guard still has a REAL, on-disk arm proving V15_BOLD_TIERS
    itself remains reachable/correct, byte-identical, through the shared _tiers_for_arm
    path -- not just via the raw-table-object check test_v15_bold_tiers_unchanged_under_
    2k_RED_PROOF already does below."""
    import fleet_executor as fx
    import json as _json

    accounts = _json.loads((_FLEET / "accounts.json").read_text(encoding="utf-8"))
    arm_map = {a["id"]: a for a in accounts["arms"]}

    # fleet_executor.py loads crypto/lib/strike_selection.py via its own _load_module shim
    # (synthetic module name "fleet_strike_selection", fleet_executor.py:49) -- a SEPARATE
    # module instance from this file's top-level `crypto.lib.strike_selection` import, even
    # though both load the same source. Identity checks against the shared table must
    # therefore go through fx.strike_selection.* (same convention test_fleet_arm_parity.py's
    # existing test_all_arms_bold_strike_tiers_at_2k already uses), not this file's import.
    arm = arm_map["safe-1"]
    assert arm.get("status") == "retired", (
        "safe-1 is expected to be the retired/inactive OTM-3 witness arm -- if it is "
        "active again, re-pick a different still-'bold' arm for this guard's subject"
    )
    tiers = fx._tiers_for_arm(arm)
    assert tiers is fx.strike_selection.V15_BOLD_TIERS, \
        "safe-1 must still resolve the SHARED V15_BOLD_TIERS object, got a different table"
    assert tiers is not fx.strike_selection.V15_BOLD_CORE_TIERS, \
        "safe-1 must NOT have been silently repointed at the new core-only table"

    tier = pick_tier(1_000.0, tiers)
    assert tier.strike_offset == -3 and tier.label == "OTM-3", (
        f"safe-1 at $1K equity must still resolve OTM-3, got {tier.label} "
        f"(offset={tier.strike_offset}) -- fleet sizing/affordability logic depends on this"
    )

    put_strike = fx.strike_selection.pick_strike(SPOT, 1_000.0, "P", tiers)
    assert put_strike == 737, f"safe-1 PUT strike at $1K should still be 737 (OTM-3), got {put_strike}"


def test_fleet_arms_safe3_risky_1_3_resolve_atm_under_2k_via_bold_core_table():
    """FLEET-STRIKE-TIER-ATM-EXTENSION (2026-08-01, risky-1/risky-3) + FLEET-STRIKE-TIER-
    ATM-EXTENSION-SAFE3 (2026-08-03, safe-3): all three ACTIVE fleet_rest arms now resolve
    V15_BOLD_CORE_TIERS (ATM under $2K) via params_patch.strike_tier_table='bold_core', NOT
    the shared V15_BOLD_TIERS object (that table's own live witness is now safe-1, retired
    -- see test_fleet_arms_resolve_otm3_under_2k_via_shared_table above). This is the exact
    change each pre-reg proposed -- pinned so a future silent revert (or an accidental drift
    back to the old default) is caught."""
    import fleet_executor as fx
    import json as _json

    accounts = _json.loads((_FLEET / "accounts.json").read_text(encoding="utf-8"))
    arm_map = {a["id"]: a for a in accounts["arms"]}

    for arm_id in ("safe-3", "risky-1", "risky-3"):
        arm = arm_map[arm_id]
        tiers = fx._tiers_for_arm(arm)
        assert tiers is fx.strike_selection.V15_BOLD_CORE_TIERS, \
            f"{arm_id} must resolve V15_BOLD_CORE_TIERS via 'bold_core', got a different table"
        assert tiers is not fx.strike_selection.V15_BOLD_TIERS, \
            f"{arm_id} must NOT still resolve the old shared OTM-3 table"

        tier = pick_tier(1_000.0, tiers)
        assert tier.strike_offset == 0 and tier.label == "ATM", (
            f"{arm_id} at $1K equity must resolve ATM, got {tier.label} (offset={tier.strike_offset})"
        )

        put_strike = fx.strike_selection.pick_strike(SPOT, 1_000.0, "P", tiers)
        assert put_strike == 740, f"{arm_id} PUT strike at $1K should be 740 (ATM), got {put_strike}"


# =============================================================================
# 4. SECOND CONSUMER -- j_intent_executor.py's bold branch (independently found,
#    NOT named in the original naive-fix investigation).
#    WIRED 2026-07-18 alongside heartbeat_core.py (dispatch: "both together so
#    automated and J-called Bold trades share one tier") -- this now asserts the
#    NEW ATM behavior, not the pre-wiring OTM-3 baseline. Was
#    'test_j_intent_executor_bold_resolves_otm3_under_2k' pre-wiring.
# =============================================================================

def test_j_intent_executor_bold_resolves_atm_under_2k():
    import j_intent_executor as jie

    # Call the real function directly -- resolve_symbol(intent, spy_price, equity) is pure
    # strike/OCC-symbol math (et_now() only affects the expiry date suffix, not the strike).
    occ = jie.resolve_symbol({"account": "bold", "side": "P"}, SPOT, 1_000.0)
    # OCC put symbol embeds the strike as an 8-digit (price*1000) field; 740 -> "00740000".
    assert "00740000" in occ, f"j_intent_executor bold PUT at $1K should embed strike 740 (ATM), got {occ}"


# =============================================================================
# 5. WIRED 2026-07-18 -- both live call sites now point at V15_BOLD_CORE_TIERS.
#    These pins were flipped IN THE SAME COMMIT as the heartbeat_core.py /
#    j_intent_executor.py edit (C14 vary-and-assert). They will go RED again if
#    either call site is reverted without updating this file to match.
# =============================================================================

def test_heartbeat_core_bold_branch_repointed_to_core_tiers():
    """WIRED 2026-07-18 (J explicit "Yes -- wire Bold to ATM" in-chat). Was
    'test_heartbeat_core_bold_branch_not_yet_repointed' pre-wiring (2026-07-15); flipped
    in the SAME commit as the heartbeat_core.py edit per C14 vary-and-assert."""
    assert "ss.V15_BOLD_CORE_TIERS if account == \"bold\" else ss.V15_SAFE_TIERS" in HEARTBEAT_CORE_SRC, (
        "heartbeat_core.py's bold strike call site should now read V15_BOLD_CORE_TIERS -- "
        "the live wiring shipped 2026-07-18. If this pin is red, either the wiring was "
        "reverted (update queue.md) or the call site shape changed for an unrelated reason."
    )
    assert "ss.V15_BOLD_TIERS if account == \"bold\"" not in HEARTBEAT_CORE_SRC, (
        "heartbeat_core.py still branches bold through V15_BOLD_TIERS -- the wiring did not "
        "actually ship despite this test file claiming it did."
    )


def test_j_intent_executor_bold_branch_repointed_to_core_tiers():
    """WIRED 2026-07-18 (J explicit "Yes -- wire Bold to ATM" in-chat). Was
    'test_j_intent_executor_bold_branch_not_yet_repointed' pre-wiring (2026-07-15); flipped
    in the SAME commit as the j_intent_executor.py edit per C14 vary-and-assert."""
    assert "ss.V15_BOLD_CORE_TIERS if intent[\"account\"] == \"bold\" else ss.V15_SAFE_TIERS" in J_INTENT_EXECUTOR_SRC, (
        "j_intent_executor.py's bold strike call site should now read V15_BOLD_CORE_TIERS -- "
        "the live wiring shipped 2026-07-18, keeping J's manual conditional bold trades on "
        "the same tier as the heartbeat path."
    )
    assert "ss.V15_BOLD_TIERS if intent[\"account\"] == \"bold\"" not in J_INTENT_EXECUTOR_SRC, (
        "j_intent_executor.py still branches bold through V15_BOLD_TIERS -- the wiring did "
        "not actually ship despite this test file claiming it did."
    )


# =============================================================================
# 6. VALIDATOR PINS -- v20_strike_selection.py's T1/T2 still match live behavior
#    (proves they did NOT need updating, because V15_BOLD_TIERS was never touched)
# =============================================================================

def test_v20_validator_pins_still_valid():
    assert "T1_bold_1k_bull_OTM3" in V20_VALIDATOR_SRC and "s == 743" in V20_VALIDATOR_SRC
    assert "T2_bold_1k_bear_OTM3" in V20_VALIDATOR_SRC and "s == 737" in V20_VALIDATOR_SRC
    # Live re-derivation, not just a text grep:
    assert pick_strike(SPOT, 1_000, "C", V15_BOLD_TIERS) == 743
    assert pick_strike(SPOT, 1_000, "P", V15_BOLD_TIERS) == 737


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
