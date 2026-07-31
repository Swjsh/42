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
# PART 1 -- today's floor-colliding arms really do resolve to the OTM table.
# =============================================================================
@pytest.mark.parametrize("arm_id", ["risky-1", "risky-3", "safe-3"])
def test_floor_colliding_arms_resolve_to_bold_otm_tiers(fx, ss, arm_id):
    """risky-1/risky-3 (id-prefix default) and safe-3 (explicit params_patch override, for
    its own documented $600-notional-at-$2K-equity reason) all resolve to V15_BOLD_TIERS
    today -- the OTM-2/OTM-3 table, NOT the ATM-at-low-equity V15_BOLD_CORE_TIERS table core
    Bold uses. This is the mechanism, not the floor -- see this file's module docstring."""
    tiers = fx._tiers_for_arm(ARMS_BY_ID[arm_id])
    assert tiers is ss.V15_BOLD_TIERS, (
        f"{arm_id} no longer resolves to V15_BOLD_TIERS -- if this changed intentionally, "
        f"fold the outcome back into analysis/recommendations/min-entry-premium-2026-07-31"
        f".json (this was the pre-registered fix candidate, PROPOSED not armed)."
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
# pinning the PROPOSED (not armed) fix's expected effect at low equity.
# =============================================================================
def test_v15_bold_core_tiers_prices_nearer_atm_at_low_equity(ss):
    """V15_BOLD_CORE_TIERS (validated bold-strike-axis-2026-07-15.json, wired for core Bold
    2026-07-17 only) gives strike_offset=0 (ATM) at the $0-2K tier where V15_BOLD_TIERS gives
    -3 (OTM-3, the deepest/cheapest/most floor-colliding tier). This is the exact lever this
    session's provenance audit proposes extending to the fleet lane -- pinned here, NOT
    wired into fleet_executor._tiers_for_arm this session (safe-3 has an undocumented-until-
    now notional-cap trade-off that needs its own review first; see the scorecard)."""
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
