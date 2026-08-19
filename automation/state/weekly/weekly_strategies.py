"""weekly_strategies -- the weekly lane's OWN exit-shape registry (arm weekly-1).

WHY A SEPARATE REGISTRY (per this workstream's brief, WEEKLY-OPTIONS-PROGRAM.md §1/§4):
`automation/state/fleet/strategies.py`'s REGISTRY is the SPY-validated edge set -- every
entry there earned its shape on real SPY 0DTE fills (ribbon_ride's SS-B cell, vwap_
continuation's T-W6 port, etc.). The weekly lane has ZERO fills of its own yet (program
doc §5: "Zero backtest history exists for any new symbol"). Appending an unvalidated
weekly shape to that file would silently blend an argued starting point into the SPY
book's proven set -- so this module NEVER imports strategies.REGISTRY and NEVER appends
to it. It DOES reuse the ExitShape/Strategy dataclasses themselves (proven, symbol-generic
containers -- the crypto twin already imports them verbatim per project_crypto_twin
precedent), because the containers are just typed data, not validated numbers.

Every value here is sourced LIVE from automation/state/weekly/params.json's "exits" block
(re-read every call -- another workstream owns that file and may edit it between ticks;
this module never caches a stale copy) and is labeled UNVALIDATED_STARTING_DEFAULT,
matching params.json's own "_label" on that block verbatim. Nothing here is armed, live,
or fitted to a single weekly fill -- see WEEKLY-OPTIONS-PROGRAM.md §8 for the shadow ->
paper promotion gate these values must clear before they mean anything.

UNIT CONVERSION (load-bearing, easy to get backwards): params.json's exits.* block uses
PERCENT units (tp1_premium_pct=45.0 means +45%), matching how a human reads the program
doc's tables. exit_manager.ExitShape uses FRACTIONS (tp1_premium_pct=0.45 means the exact
same +45%, but as the multiplier exit_manager's `entry * (1 + tp1_premium_pct)` formula
expects). Every percent-unit field below is divided by 100 exactly once, here, so no
caller has to remember the convention twice. `runner_target_mult` is the ONE exception:
it is already a TOTAL multiple of entry (1.75 == exit at 1.75x entry), so converting to
exit_manager's ADDITIVE `runner_target_pct` needs `mult - 1.0`, not `/100`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet"))
from strategies import ExitShape, Strategy  # noqa: E402 -- reused containers only, NOT the SPY registry

WEEKLY_DIR = Path(__file__).resolve().parent
PARAMS_PATH = WEEKLY_DIR / "params.json"

# Matches params.json's own "_label" on the exits block verbatim -- do not drift the string.
UNVALIDATED_STARTING_DEFAULT = "UNVALIDATED_STARTING_DEFAULT"


def load_params() -> dict:
    """Read automation/state/weekly/params.json fresh every call -- no module-level cache,
    because another workstream owns this file and may edit it between ticks (a cached copy
    would silently trade on a stale config). Raises loudly on missing/corrupt: a weekly-lane
    module silently falling back to a plausible-looking default here is exactly the shop's
    #1 documented failure class (C7, "silent success is failure")."""
    if not PARAMS_PATH.exists():
        raise FileNotFoundError(f"weekly params missing: {PARAMS_PATH}")
    try:
        raw = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"weekly params.json is corrupt: {PARAMS_PATH} ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"weekly params.json did not parse to an object: {PARAMS_PATH}")
    return raw


def _exits_block(params: Optional[dict] = None) -> dict:
    p = params if params is not None else load_params()
    exits = p.get("exits")
    if not isinstance(exits, dict):
        raise ValueError("weekly params.json missing/malformed 'exits' block")
    return exits


def theta_budget_config(params: Optional[dict] = None) -> dict:
    """The exits.theta_budget sub-block, fraction-converted, for weekly_exit_gate. Kept
    here (not duplicated in weekly_exit_gate.py) so there is exactly one params-reading
    path for the exits block, matching this module's single-source-of-truth contract."""
    e = _exits_block(params)
    tb = e.get("theta_budget")
    if not isinstance(tb, dict):
        raise ValueError("weekly params.json missing/malformed 'exits.theta_budget' block")
    return {
        "fires_before_catastrophe_cap": bool(tb.get("fires_before_catastrophe_cap", True)),
        "max_premium_bleed_pct_without_progress":
            float(tb["max_premium_bleed_pct_without_progress"]) / 100.0,
        "thesis_progress_definition": str(tb.get("thesis_progress_definition", "")),
    }


def weekly_exit_shape(params: Optional[dict] = None) -> ExitShape:
    """The UNVALIDATED_STARTING_DEFAULT weekly exit shape, built fresh from params.json's
    exits.* block every call (params.json is the single source of truth -- this function
    never hardcodes a number that lives there).

    ASSUMPTIONS stated per judgment-guards (params.json does not spell these out, so this
    function picks the most reasonable reading and records it rather than stalling):

    1. premium_stop_pct == catastrophe_stop_pct. v1 rule 8 (program doc §4) keeps the -50%
       catastrophe cap as the ONLY premium-based stop for weeklies -- there is no separate
       tighter validated premium stop the way ribbon_ride's -20% flag-off fallback exists
       for SPY. So the flag-OFF premium fallback IS the catastrophe cap itself; there is
       nothing else to fall back to.
    2. stop_mode="structure". Program doc §4 rule 1 explicitly "Keeps" chart-structure
       stops for weeklies (same level-interaction edge thesis as SPY's ribbon_ride SS-B
       cell). This declaration is BEHAVIORALLY INERT on its own -- exactly like ribbon_ride's
       own stop_mode="structure" declaration -- until the caller ALSO passes
       structure_stop_enabled=True and a trigger_level at entry (see exit_manager.
       ExitState.from_entry). Absent either, positions fall back to mode="premium" using
       assumption #1's cap.
    3. profit_lock_mode="trailing". params.json's exits block sets both trail_pct (20.0)
       and profit_lock_arm_pct (15.0) but never states profit_lock_mode explicitly. A
       trailing chandelier is the only mode where trail_pct is ever consulted (a "fixed"
       mode ignores it entirely, per exit_manager's runner walk) -- and it mirrors the
       validated SS-B ribbon_ride cell shape these starting values were argued from
       (program doc §4 row 9: "Shapes inherited as STARTING values"). NEEDS_J if a fixed
       BE-floor runner was actually intended instead -- this is a real fork, not a detail.
    """
    e = _exits_block(params)
    cat_pct = float(e["catastrophe_stop_pct"]) / 100.0
    return ExitShape(
        premium_stop_pct=cat_pct,                          # assumption 1
        tp1_premium_pct=float(e["tp1_premium_pct"]) / 100.0,
        tp1_qty_fraction=float(e["tp1_qty_fraction"]),
        profit_lock_mode="trailing",                        # assumption 3, NEEDS_J
        runner_target_pct=float(e["runner_target_mult"]) - 1.0,
        trail_pct=float(e["trail_pct"]) / 100.0,
        profit_lock_arm_pct=float(e["profit_lock_arm_pct"]) / 100.0,
        stop_mode="structure",                               # assumption 2
        catastrophe_stop_pct=cat_pct,
    )


def weekly_exit_shape_note(params: Optional[dict] = None) -> str:
    """The Strategy.note string -- kept as a function (not a literal) so it always reflects
    the LIVE params.json values it describes rather than a copy that can drift."""
    e = _exits_block(params)
    tb = theta_budget_config(params)
    return (
        f"{UNVALIDATED_STARTING_DEFAULT} (params.json's own label, matched verbatim -- "
        f"NOT fitted to a single weekly fill). Sourced live from automation/state/weekly/"
        f"params.json exits.*: catastrophe/premium stop {e['catastrophe_stop_pct']:+.0f}%, "
        f"TP1 +{e['tp1_premium_pct']:.0f}% sell {e['tp1_qty_fraction']:.0%}, runner target "
        f"{e['runner_target_mult']:.2f}x, trail {e['trail_pct']:.0f}% off HWM (assumed "
        f"trailing mode -- see weekly_exit_shape docstring assumption 3, NEEDS_J), theta "
        f"budget fires at {tb['max_premium_bleed_pct_without_progress']:.0%} unprogressed "
        f"bleed BEFORE the catastrophe cap (weekly_exit_gate.py owns that ordering -- this "
        f"registry only carries the exit SHAPE, not the theta/days-to-live/flatten-schedule "
        f"wrapper logic). Validated only via the paired shadow-clock A/B against the naive "
        f"ported-0DTE shape (program doc §5, weekly_exit_gate.paired_shadow_clock)."
    )


# --- The weekly-lane's OWN set (deliberately separate from strategies.REGISTRY) ---------
# entry_setups are PLACEHOLDER names pending the weekly_core signal producer (program doc
# §5, a DIFFERENT workstream's module -- not built by this one). They name the level-
# interaction edge thesis this program is built on (program doc §1: "rejection, reclaim,
# S/R flip+retest"). fired() below matches on these exactly like strategies.fired() does;
# if weekly_core ships different setup_name strings, only THIS tuple needs to change.
WEEKLY_LEVEL_INTERACTION_SETUPS = (
    "WEEKLY_LEVEL_REJECT",
    "WEEKLY_LEVEL_RECLAIM",
    "WEEKLY_SR_FLIP_RETEST",
)


def weekly_level_interaction() -> Strategy:
    """Build fresh (not a module-level constant) so every call reflects the current
    params.json -- a Strategy built once at import time would freeze a stale ExitShape for
    the life of the process, silently ignoring a same-session params.json edit."""
    return Strategy(
        name="weekly_level_interaction",
        entry_setups=WEEKLY_LEVEL_INTERACTION_SETUPS,
        exit=weekly_exit_shape(),
        note=weekly_exit_shape_note(),
    )


def by_name(name: str) -> Optional[Strategy]:
    """Weekly-lane lookup, mirroring strategies.by_name's shape. Only one strategy exists
    at v1 (program doc §4: the level-interaction edge is the ONLY weekly thesis) -- this
    stays a function (not a REGISTRY tuple scan) because there is exactly one entry to date
    and adding a second is the moment to promote it to a tuple, not before.
    """
    strat = weekly_level_interaction()
    return strat if name == strat.name else None
