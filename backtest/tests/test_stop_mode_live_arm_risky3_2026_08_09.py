"""Guards for the risky-3 stop_mode live A/B (armed 2026-08-09, paper only).

Prereg: analysis/recommendations/prereg-stop-mode-live-arm-risky3-2026-08-09.json (commit
a2d7c3e4, frozen BEFORE the accounts.json edit).

WHAT THESE PIN, and why each one earns its place:

1. VARY-AND-ASSERT (C14/L201). A knob that is declared but not resolved is this codebase's
   single most repeated defect class. It is not enough that accounts.json CONTAINS
   stop_mode=premium -- the shape that reaches the live exit_manager must actually carry it,
   resolved through the REAL fleet_executor._exit_shape_dict merge, not a re-implementation.

2. BLAST RADIUS. The whole experiment is "one arm differs". If a later edit spreads premium
   mode to a sibling, the A/B silently loses its control and nobody would notice from P&L
   alone. Every other arm is pinned to structure.

3. ONE VARIABLE. risky-3 must differ from the ribbon_ride registry in stop_mode and NOTHING
   else. The outgoing patch also carried trail_pct 0.20; if a future edit reintroduces a
   second differing field, this stops being a one-variable test (the exact defect the parent
   matrix's ATR_STOP column had -- it bundled a dynamic width with a mode change and a
   look-ahead).

4. THE AND-GATE. exit_manager resolves structure stops as (shape_mode=='structure' AND
   caller structure_stop_enabled). This experiment de-arms structure for one arm via the
   SHAPE side only. If someone "fixes" it by flipping the global params.structure_stop_enabled
   instead, every arm loses its structure stop at once -- a fleet-wide change disguised as a
   one-arm experiment. Both halves are pinned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
ACCOUNTS = FLEET / "accounts.json"
PREREG = REPO / "analysis" / "recommendations" / "prereg-stop-mode-live-arm-risky3-2026-08-09.json"

ARM = "risky-3"


def _load():
    if str(FLEET) not in sys.path:
        sys.path.insert(0, str(FLEET))
    import fleet_executor as fx
    import strategies as st
    accounts = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    return fx, st, accounts


def _arm(accounts: dict, arm_id: str) -> dict:
    for a in accounts["arms"]:
        if a["id"] == arm_id:
            return a
    raise AssertionError(f"arm {arm_id} not found")


def _resolved(arm_id: str) -> dict:
    fx, st, accounts = _load()
    return fx._exit_shape_dict(st.by_name("ribbon_ride"), _arm(accounts, arm_id))


def test_prereg_exists_and_is_paper_only():
    assert PREREG.exists(), "frozen prereg missing"
    d = json.loads(PREREG.read_text(encoding="utf-8"))
    assert d["frozen_before_any_config_change"] is True
    assert "PAPER ONLY" in d["money"]


def test_risky3_resolves_premium_through_the_real_executor():
    """VARY-AND-ASSERT: the shape that reaches the live exit_manager, not the raw JSON."""
    shape = _resolved(ARM)
    assert shape["stop_mode"] == "premium", (
        f"{ARM} did not resolve premium mode through _exit_shape_dict: {shape['stop_mode']}")
    # premium mode makes the registry's already-configured -20% the OPERATIVE stop
    assert shape["premium_stop_pct"] == pytest.approx(-0.20)


def test_risky3_differs_from_registry_in_stop_mode_ONLY():
    """ONE VARIABLE. A second differing field turns this into a bundle."""
    _fx, st, _a = _load()
    registry = dict(st.by_name("ribbon_ride").exit.to_dict())
    shape = _resolved(ARM)
    diffs = {k for k in set(registry) | set(shape) if registry.get(k) != shape.get(k)}
    assert diffs == {"stop_mode"}, f"{ARM} differs from registry in more than stop_mode: {diffs}"


def test_every_other_arm_still_resolves_structure():
    """BLAST RADIUS: exactly one arm may be premium."""
    fx, st, accounts = _load()
    strat = st.by_name("ribbon_ride")
    premium_arms = []
    for a in accounts["arms"]:
        mode = fx._exit_shape_dict(strat, a)["stop_mode"]
        if mode == "premium":
            premium_arms.append(a["id"])
    assert premium_arms == [ARM], (
        f"expected ONLY {ARM} in premium mode, got {premium_arms} -- the A/B has lost its "
        f"control or premium mode has spread")


def test_global_structure_stop_flag_untouched():
    """THE AND-GATE: this is a one-arm SHAPE change. Flipping the global flag instead would
    de-arm structure stops fleet-wide while looking like a one-arm experiment."""
    for rel in ("automation/state/params.json", "automation/state/aggressive/params.json"):
        p = json.loads((REPO / rel).read_text(encoding="utf-8"))
        assert p.get("structure_stop_enabled") is True, (
            f"{rel} structure_stop_enabled is no longer True -- that is a FLEET-WIDE change, "
            f"not the one-arm experiment this prereg authorized")


def test_exit_patch_schema_still_validates():
    """Fail-loud contract: unknown exit_patch keys must raise at load."""
    fx, _st, accounts = _load()
    fx.validate_accounts_exit_patches(accounts)   # must not raise


def test_revert_path_is_documented_verbatim():
    """A revert nobody can find is not a revert."""
    arm = _arm(json.loads(ACCOUNTS.read_text(encoding="utf-8")), ARM)
    # The doc lives INSIDE params_patch, matching this file's own convention for sibling
    # knobs (_cheap_contract_qty_boost_doc sits there too), not on the arm root.
    doc = arm["params_patch"].get("_exit_patch_doc", "")
    assert "REVERT" in doc
    assert '"stop_mode": "structure"' in doc and "trail_pct" in doc, (
        "the byte-exact restore value is not in the revert instructions")
    assert arm.get("exit_profile") == "PREMIUM-STOP"


def test_control_attribution_is_the_corrected_one():
    """risky-1 is NOT a control (tp1 0.5 since 2026-07-29). Pin the correction so the stale
    2026-07-20 note cannot re-infect a future reader."""
    fx, st, accounts = _load()
    strat = st.by_name("ribbon_ride")
    registry = dict(strat.exit.to_dict())
    r1 = fx._exit_shape_dict(strat, _arm(accounts, "risky-1"))
    assert r1["tp1_premium_pct"] != registry["tp1_premium_pct"], (
        "risky-1 now matches the registry -- if that is intentional, update the prereg's "
        "corrected control design instead of letting the stale 'risky-1 is the control' "
        "claim quietly become true again")
    d = json.loads(PREREG.read_text(encoding="utf-8"))
    assert d.get("_corrections"), "prereg lost its control-attribution correction"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
