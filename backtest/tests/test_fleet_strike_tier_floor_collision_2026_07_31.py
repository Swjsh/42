"""Guard: fleet strike-tier / min_entry_premium floor-collision provenance pin.

2026-07-31 gate-provenance audit (J: 11/11 bull setup at 743.25 taken by risky-3 @ $0.33,
WON; safe-3/risky-1 refused because their OWN strike priced at $0.15 -- below the
min_entry_premium=0.30 floor; risky-1 alone logged 15/16 named-setup ticks today dying on
this floor). Full writeup + blocked-trade replay (n=25, total -$145.20, exp/tr -$5.81,
drop-best -$9.59 -- a mild NEGATIVE for the exact cohort the floor excludes, reinforcing
rather than undermining the floor's 2026-07-09 T2/T3/T5 provenance):
analysis/recommendations/min-entry-premium-2026-07-31.json

VERDICT: the floor itself is KEPT unchanged (real provenance, guard already exists at
test_min_entry_premium_floor.py). This file pins the SEPARATE, already-existing mechanism
that makes risky-1/risky-3/safe-3 collide with that floor so often: fleet_executor.
_tiers_for_arm defaults every non-'safe'-prefixed arm id (and safe-3 explicitly via
params_patch.strike_tier_table='bold') to strike_selection.V15_BOLD_TIERS (OTM-2/OTM-3),
NOT the ATM-at-low-equity V15_BOLD_CORE_TIERS table core Bold was repointed to on
2026-07-17. This was already diagnosed 2026-07-10 (accounts.json probe_arm._doc AMENDMENT 1)
and quantified 2026-07-15 (analysis/recommendations/bold-strike-axis-2026-07-15.json: OTM-3
clears the floor 33.76% of afternoon signals vs ATM's 96.88%) -- STILL true today, three
weeks later, for the fleet lane specifically.

UPDATE 2026-08-01 (FLEET-STRIKE-TIER-ATM-EXTENSION, queue item this file's own docstring
named as the proposed fix candidate): risky-1/risky-3 are now REPOINTED to 'bold_core'
(V15_BOLD_CORE_TIERS) after a pre-registration frozen BEFORE arming
(analysis/recommendations/fleet-strike-tier-atm-extension-prereg-2026-08-01.json, n>=20-fill
gates). safe-3 was UNCHANGED at that time (own documented notional-cap reason, out of scope
for THAT extension specifically). Part 1's parametrization below now reflects that split,
not the pre-fix state.

UPDATE 2026-08-03 (FLEET-STRIKE-TIER-ATM-EXTENSION-SAFE3,
analysis/deep-research/ARM-PARTICIPATION-AND-GROWTH-2026-08-03.md #1): safe-3 is now ALSO
REPOINTED to 'bold_core', after its own separate pre-registration
(analysis/recommendations/fleet-strike-tier-atm-extension-safe3-prereg-2026-08-03.json).
The $600-notional-cap concern that excluded it from the 2026-08-01 extension was NOT
resolved by new evidence -- it is disclosed as an untested, carried-forward risk in that
prereg's own notional_cap_caveat -- this is a scope extension of the same machinery, not a
claim the earlier caveat stopped applying. safe-1 (retired/inactive) is now the file's only
still-OTM/'bold' witness. Part 1 below is updated again to reflect all THREE active
fleet_rest arms on 'bold_core'.

WHY THIS GUARD EXISTS (not a code change -- a documentation pin): C14 doctrine says a
diagnosed-but-unfixed mechanism is exactly the kind of thing that silently rots. This test
RED-PROOFS the finding two ways: (1) proves TODAY's fleet arms really do resolve to the OTM
table (the thing costing floor-clearance), and (2) proves the ALREADY-VALIDATED alternative
table (V15_BOLD_CORE_TIERS) really would price nearer-the-money for the SAME arms, so a
future session extending the fix has a pinned, tested starting point instead of re-deriving
it. If accounts.json or fleet_executor.py's default ever silently changes (e.g., someone
"fixes" this by flipping the default without reading this file's provenance chain), this
test will fail and point back here.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_fleet_strike_tier_floor_collision_2026_07_31.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ACCOUNTS_PATH = ROOT / "automation" / "state" / "fleet" / "accounts.json"
ACCOUNTS = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
ARMS_BY_ID = {a["id"]: a for a in ACCOUNTS["arms"]}


@pytest.fixture()
def fx():
    return importlib.import_module("fleet_executor")


@pytest.fixture()
def ss(fx):
    """strike_selection is loaded by fleet_executor via _load_module (anchored to repo root,
    module name 'fleet_strike_selection', C9 doctrine) -- reuse ITS already-loaded instance
    rather than a second import under a name that isn't on sys.path."""
    return fx.strike_selection


# =============================================================================
# PART 1 -- safe-1 (retired) is the last arm still resolving the OTM table;
# safe-3/risky-1/risky-3 all now resolve the ATM-at-low-equity table (2026-08-01 fix for
# risky-1/risky-3, 2026-08-03 fix for safe-3, both armed).
# =============================================================================
def test_safe1_still_resolves_to_bold_otm_tiers(fx, ss):
    """safe-1 (retired/inactive, explicit params_patch override predating either ATM
    extension) still resolves V15_BOLD_TIERS -- the OTM-2/OTM-3 table, NOT the
    ATM-at-low-equity V15_BOLD_CORE_TIERS table core Bold/risky-1/risky-3/safe-3 use.
    Was test_safe3_still_resolves_to_bold_otm_tiers before 2026-08-03: safe-3 moved to the
    'now resolves bold_core' bucket that session (see test_risky_and_safe3_arms_now_resolve_
    to_bold_core_atm_tiers below) -- safe-1 is the file's remaining live OTM witness."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID["safe-1"])
    assert tiers is ss.V15_BOLD_TIERS, (
        "safe-1 no longer resolves to V15_BOLD_TIERS -- if this changed intentionally, "
        "fold the outcome back into analysis/recommendations/min-entry-premium-2026-07-31.json "
        "and re-pick a live OTM witness arm for this guard."
    )


@pytest.mark.parametrize("arm_id", ["safe-3", "risky-1"])
def test_risky_and_safe3_arms_now_resolve_to_bold_core_atm_tiers(fx, ss, arm_id):
    """FLEET-STRIKE-TIER-ATM-EXTENSION (2026-08-01, pre-registered before arming --
    analysis/recommendations/fleet-strike-tier-atm-extension-prereg-2026-08-01.json) for
    risky-1, extended to safe-3 2026-08-03 (analysis/recommendations/
    fleet-strike-tier-atm-extension-safe3-prereg-2026-08-03.json): both resolve
    V15_BOLD_CORE_TIERS via params_patch.strike_tier_table='bold_core', clearing the
    min_entry_premium floor far more often at low equity (the mechanism this file's module
    docstring names). risky-3 LEFT this cohort 2026-08-06 (pre-registered per-arm KILL of
    the 2K-10K ATM extension, n=14/-$653) -- its own pin lives in
    test_atm_tier_extension_risky3_kill_2026_08_06.py."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID[arm_id])
    assert tiers is ss.V15_BOLD_CORE_TIERS, (
        f"{arm_id} no longer resolves to V15_BOLD_CORE_TIERS -- if this changed intentionally, "
        f"fold the outcome back into the arm's own prereg json."
    )
    assert tiers is not ss.V15_BOLD_TIERS, f"{arm_id} must not have reverted to the old OTM table"


def test_risky3_resolves_pre_ext_table_after_2026_08_06_kill(fx, ss):
    """ATM-TIER-EXTENSION-2K-10K per-arm kill (2026-08-06): risky-3 resolves
    V15_BOLD_CORE_PRE_EXT_TIERS ($0-2K still ATM per the 2026-08-01 extension; $2K-10K
    back to OTM-2). Full vary-and-assert coverage:
    test_atm_tier_extension_risky3_kill_2026_08_06.py."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID["risky-3"])
    assert tiers is ss.V15_BOLD_CORE_PRE_EXT_TIERS, (
        "risky-3 no longer resolves the pre-extension table -- if the kill was deliberately "
        "un-done, fold the new evidence into atm-tier-extension-2k10k-prereg-2026-08-03.json."
    )


def test_core_bold_arms_are_NOT_in_this_collision(fx, ss):
    """Sanity control: bold-2 (CORE-BOLD, mcp_heartbeat execution) is not a fleet_rest arm at
    all -- it doesn't route through fleet_executor._tiers_for_arm, and heartbeat_core.py's own
    bold branch was already repointed to V15_BOLD_CORE_TIERS on 2026-07-17. 0 SKIP_MIN_PREMIUM
    _FLOOR fires were found on the core lane in the 2026-07-28..07-31 replay window."""
    assert ARMS_BY_ID["bold-2"]["execution"] == "mcp_heartbeat"
    assert "risky-1" not in ("bold-2",)  # trivially documents the two are distinct arms


# =============================================================================
# PART 2 -- the already-validated alternative table really does clear nearer-the-money,
# pinning the fix's expected effect at low equity (WIRED 2026-08-01 for risky-1/risky-3;
# see PART 1 above for the live-wiring pins).
# =============================================================================
def test_v15_bold_core_tiers_prices_nearer_atm_at_low_equity(ss):
    """V15_BOLD_CORE_TIERS (validated bold-strike-axis-2026-07-15.json, wired for core Bold
    2026-07-17, extended to fleet risky-1/risky-3 2026-08-01, extended to safe-3 2026-08-03)
    gives strike_offset=0 (ATM) at the $0-2K tier where V15_BOLD_TIERS gives -3 (OTM-3, the
    deepest/cheapest/most floor-colliding tier). Only safe-1 (retired/inactive) still
    resolves V15_BOLD_TIERS live -- its own documented notional-cap trade-off is now carried
    forward as a disclosed, untested risk in safe-3's own prereg rather than a reason to
    exclude safe-3 entirely; see that prereg's notional_cap_caveat."""
    otm_tier = ss.pick_tier(1_750.0, ss.V15_BOLD_TIERS)
    atm_tier = ss.pick_tier(1_750.0, ss.V15_BOLD_CORE_TIERS)
    assert otm_tier.strike_offset == -3
    assert atm_tier.strike_offset == 0
    spot = 748.0
    otm_strike = ss.pick_strike(spot, 1_750.0, "C", ss.V15_BOLD_TIERS)
    atm_strike = ss.pick_strike(spot, 1_750.0, "C", ss.V15_BOLD_CORE_TIERS)
    assert otm_strike == 751  # 3 further OTM -> cheaper -> more likely to collide with 0.30
    assert atm_strike == 748  # ATM -> pricier -> clears the floor more often


def test_min_entry_premium_floor_unchanged_by_this_session(fx):
    """This session's disposition was KEEP -- confirm the floor value itself was not touched
    (duplicates test_min_entry_premium_floor.py's own pin as a belt-and-suspenders check
    local to this investigation's guard file)."""
    safe = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    bold = json.loads((ROOT / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    assert safe["min_entry_premium"] == 0.30
    assert bold["min_entry_premium"] == 0.30


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
