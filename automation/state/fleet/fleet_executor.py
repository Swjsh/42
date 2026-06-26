"""Fleet executor — one perception, many policies.

Reads ONE shared signal per heartbeat tick (the single chart-read / scoring pass)
and fans it out to every active arm in `accounts.json`. Each arm applies its own
FROZEN policy (direction lock, A+ gate override, sizing) on top of the shared
signal, then the SAME `risk_gate.check_order` that the live heartbeat and backtest
use decides whether the order may be placed. See markdown/specs/FLEET-DESIGN.md.

Cost stays ~flat regardless of arm count: the expensive perception happens once
(upstream, in the heartbeat); this module is pure deterministic policy + the pure
risk gate. No LLM calls here.

SAFETY: default mode is DRY-RUN — it computes and logs each arm's decision and
places NOTHING. Live REST order placement (Milestone 2) is a separate, explicitly
guarded path (`place_bracket_rest`) that refuses to run without an enable flag and
an open market. This file never touches a human session (OP-32 invariant).

Reuses (pure, stdlib-only — loaded by absolute path, anchored to repo root, C9):
  - backtest/lib/risk_gate.py    :: check_order  (the single risk authority)
  - crypto/lib/strike_selection.py :: pick_strike (v15 per-tier OTM/ITM math)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# --- locate repo root + load the pure reusable engine pieces (C9) -------------
FLEET_DIR = Path(__file__).resolve().parent
REPO_ROOT = FLEET_DIR.parents[2]  # automation/state/fleet -> repo root


def _load_module(modname: str, relpath: str):
    path = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError(f"cannot load {modname} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod  # register before exec so dataclasses resolve forward refs
    spec.loader.exec_module(mod)
    return mod


risk_gate = _load_module("fleet_risk_gate", "backtest/lib/risk_gate.py")
strike_selection = _load_module("fleet_strike_selection", "crypto/lib/strike_selection.py")
strategies = _load_module("fleet_strategies", "automation/state/fleet/strategies.py")

ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
SECRETS_PATH = FLEET_DIR / "secrets.json"
DECISIONS_DIR = FLEET_DIR / "decisions"
PARAMS_SAFE = REPO_ROOT / "automation/state/params.json"
PARAMS_BOLD = REPO_ROOT / "automation/state/aggressive/params.json"


# --- value types -------------------------------------------------------------
@dataclass(frozen=True)
class EntryPlan:
    """Result of the pure gating pass (before the risk gate)."""

    arm_id: str
    action: str  # "ENTER" | "HOLD"
    side: Optional[str]  # "P" | "C" | None
    setup_name: Optional[str]
    strike: Optional[int]
    qty: Optional[int]
    quality: Optional[str]  # "ELITE" | "BASE" | None
    reason: str
    # Multi-strategy fields (default None → existing 8-positional construction unchanged):
    strategy: Optional[str] = None        # which shared-set strategy this plan trades
    exit_shape: Optional[dict] = None     # the strategy's proven bracket (stop/tp1/lock)


@dataclass(frozen=True)
class ArmDecision:
    """Final per-arm decision after the risk gate."""

    arm_id: str
    action: str  # "ENTER_BEAR" | "ENTER_BULL" | "HOLD"
    side: Optional[str]
    setup_name: Optional[str]
    strike: Optional[int]
    qty: Optional[int]
    premium: Optional[float]
    quality: Optional[str]
    risk_code: Optional[str]
    reason: str


# --- pure helpers ------------------------------------------------------------
def _perception_for_arm(signal: Mapping[str, Any], arm: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Pick the per-arm perception block from the signal (dual-perception routing).

    When the signal carries 'safe'/'bold' sub-blocks (the flagged dual-perception build),
    a safe arm reads signal['safe'] and a bold/risky/loose arm reads signal['bold'] -- so a
    bold arm is judged on the BOLD ledger's perception, not the SAFE one (perception-source
    confound fix). Falls back to the top-level signal (production-faithful) when the sub-block
    is absent OR no arm is given (backward-compat: the v1 single-perception signal is unchanged)."""
    if arm is None:
        return signal
    role = "safe" if str(arm.get("id", "")).startswith("safe") else "bold"
    block = signal.get(role)
    if isinstance(block, Mapping) and ("bull" in block or "bear" in block):
        return block
    return signal


def _chosen_side(signal: Mapping[str, Any], arm: Optional[Mapping[str, Any]] = None):
    """Pick the candidate side from the shared signal: (side, side_block, setup).

    If `arm` is supplied and the signal carries dual-perception sub-blocks, the arm's
    role-appropriate block is used; otherwise the top-level bear/bull is read (v1 behavior)."""
    src = _perception_for_arm(signal, arm)
    bear = src.get("bear") or {}
    bull = src.get("bull") or {}
    bear_go = bear.get("passed") is True
    bull_go = bull.get("passed") is True
    if bear_go and bull_go:
        if (signal.get("production_action") or "").upper() == "ENTER_BULL":
            return "C", bull, bull.get("setup_name", "BULLISH_RECLAIM_RIDE_THE_RIBBON")
        return "P", bear, bear.get("setup_name", "BEARISH_REJECTION_RIDE_THE_RIBBON")
    if bear_go:
        return "P", bear, bear.get("setup_name", "BEARISH_REJECTION_RIDE_THE_RIBBON")
    if bull_go:
        return "C", bull, bull.get("setup_name", "BULLISH_RECLAIM_RIDE_THE_RIBBON")
    return None, {}, None


def _is_elite(side_block: Mapping[str, Any]) -> bool:
    """ELITE (v13b) = trigger set includes confluence OR a sequence_* trigger."""
    if side_block.get("confluence") is True:
        return True
    return any("sequence" in str(t).lower() for t in side_block.get("triggers_fired", []) or [])


def _tiers_for_arm(arm: Mapping[str, Any]):
    """Pick the strike-offset table (SAFE=ATM / BOLD=OTM) for this arm.

    strike_tier_table may be set as a TOP-LEVEL arm key OR inside the arm's params_patch
    (the design files some arms' table under params_patch). The explicit value wins; absent
    one, default by side-class from the arm id. .lower() is applied defensively.
    """
    patch = arm.get("params_patch") or {}
    table = arm.get("strike_tier_table") or (patch.get("strike_tier_table") if isinstance(patch, Mapping) else None)
    if not table:
        table = "safe" if str(arm["id"]).startswith("safe") else "bold"
    table = str(table).lower()
    return strike_selection.V15_SAFE_TIERS if table == "safe" else strike_selection.V15_BOLD_TIERS


def _qty_for(tiers: Any, equity: float, elite: bool) -> Optional[int]:
    if not isinstance(tiers, list):
        return None
    for tier in tiers:
        lo, hi = tier.get("equity_min"), tier.get("equity_max")
        if lo is None or hi is None:
            continue
        if float(lo) <= equity < float(hi):
            return int(tier.get("elite_qty" if elite else "base_qty"))
    return None


def _hold(arm_id, side, setup, reason, strike=None, qty=None, quality=None) -> EntryPlan:
    return EntryPlan(arm_id, "HOLD", side, setup, strike, qty, quality, reason)


def select_plan(plans: Sequence[EntryPlan]) -> Optional[EntryPlan]:
    """One-position rule: among ENTER plans, the highest-priority by REGISTRY order
    (RIBBON_RIDE before VWAP_CONTINUATION). Falls back to the first HOLD plan (faithful
    logging) when none ENTER. None if the list is empty. Deterministic — the same plan is
    selected here and in the live runner's pre_plan prefetch (so the prefetched premium
    matches the traded strike)."""
    if not plans:
        return None
    order = {s.name: i for i, s in enumerate(strategies.REGISTRY)}
    enters = [p for p in plans if p.action == "ENTER"]
    if enters:
        return min(enters, key=lambda p: order.get(p.strategy, 999))
    return plans[0]


# --- phase A: pure gating (fully unit-testable, no I/O, no risk gate) ---------
def plan_entry(
    arm: Mapping[str, Any],
    signal: Mapping[str, Any],
    equity: float,
    params: Mapping[str, Any],
) -> EntryPlan:
    """Apply this arm's frozen policy to the shared signal. No risk gate yet."""
    arm_id = str(arm["id"])
    side, blk, setup = _chosen_side(signal, arm)
    if side is None:
        return _hold(arm_id, None, None, "no qualifying setup (neither side passed)")

    # direction lock (e.g. risky-1 = PUT_ONLY)
    dl = arm.get("direction_lock")
    if dl == "PUT_ONLY" and side != "P":
        return _hold(arm_id, side, setup, "direction_lock=PUT_ONLY skips a CALL signal")
    if dl == "CALL_ONLY" and side != "C":
        return _hold(arm_id, side, setup, "direction_lock=CALL_ONLY skips a PUT signal")

    # A+ gate override (e.g. safe-3)
    g = arm.get("gate_override") or {}
    conf = blk.get("confidence", signal.get("confidence"))
    min_conf = g.get("min_confidence")
    if min_conf is not None:
        if conf is None:
            return _hold(arm_id, side, setup, f"A+ gate: confidence missing, need >= {min_conf}")
        if float(conf) < float(min_conf):
            return _hold(arm_id, side, setup, f"A+ gate: confidence {conf} < {min_conf}")
    triggers = blk.get("triggers_fired", []) or []
    min_trig = g.get("min_triggers")
    if min_trig is not None and len(triggers) < int(min_trig):
        return _hold(arm_id, side, setup, f"A+ gate: {len(triggers)} triggers < {min_trig}")
    elite = _is_elite(blk)
    if g.get("require_confluence_or_sequence") and not elite:
        return _hold(arm_id, side, setup, "A+ gate: requires confluence/sequence (not EXCELLENT)")
    if str(g.get("min_setup_quality", "")).upper() == "EXCELLENT" and not elite:
        return _hold(arm_id, side, setup, "A+ gate: setup not EXCELLENT")

    # strike + qty (reuse v15 math)
    spot = signal.get("spot")
    if spot is None:
        return _hold(arm_id, side, setup, "no spot in signal")
    strike = strike_selection.pick_strike(float(spot), float(equity), side, _tiers_for_arm(arm))
    quality = "ELITE" if elite else "BASE"
    qty = _qty_for(params.get("position_sizing_tiers"), float(equity), elite)
    if qty is None:
        return _hold(arm_id, side, setup, "no sizing tier covers equity", strike=strike, quality=quality)
    return EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality, f"clean {side} entry ({quality})")


def _gate_check(arm: Mapping[str, Any], blk: Mapping[str, Any], signal: Mapping[str, Any]) -> Optional[str]:
    """The arm's SELECTIVITY gate (confidence / triggers / quality). Returns None to pass,
    else a short reason. This is the account's ONLY job besides sizing — it adds strictness,
    never a direction lock or a strategy choice."""
    g = arm.get("gate_override") or {}
    conf = blk.get("confidence", signal.get("confidence"))
    min_conf = g.get("min_confidence")
    if min_conf is not None:
        if conf is None:
            return f"confidence missing, need >= {min_conf}"
        if float(conf) < float(min_conf):
            return f"confidence {conf} < {min_conf}"
    min_trig = g.get("min_triggers")
    triggers = blk.get("triggers_fired", []) or []
    if min_trig is not None and len(triggers) < int(min_trig):
        return f"{len(triggers)} triggers < {min_trig}"
    elite = _is_elite(blk)
    if g.get("require_confluence_or_sequence") and not elite:
        return "requires confluence/sequence"
    if str(g.get("min_setup_quality", "")).upper() == "EXCELLENT" and not elite:
        return "setup not EXCELLENT"
    return None


def _exit_shape_dict(strat) -> dict:
    """The full exit shape threaded into the EntryPlan -> live exit_manager. Uses the
    ExitShape.to_dict() canonical form (includes runner_target_pct / trail_pct /
    profit_lock_arm_pct) so the live runner ride is fully described by the strategy."""
    ex = strat.exit
    if hasattr(ex, "to_dict"):
        return ex.to_dict()
    return {  # defensive fallback (older ExitShape without to_dict)
        "premium_stop_pct": ex.premium_stop_pct,
        "tp1_premium_pct": ex.tp1_premium_pct,
        "tp1_qty_fraction": ex.tp1_qty_fraction,
        "profit_lock_mode": ex.profit_lock_mode,
    }


def _gate_block_for_entry(entry: Mapping[str, Any]) -> dict:
    """Synthesize the side-block _gate_check / _is_elite read for a strategies[] entry,
    so the arm's selectivity gate + ELITE classification work uniformly on the FIX2 set."""
    trigs = list(entry.get("triggers") or [])
    return {
        "passed": True,
        "triggers_fired": trigs,
        "confluence": str(entry.get("quality", "")).upper() == "ELITE" or any(
            "confluence" in str(t).lower() for t in trigs),
        "confidence": entry.get("confidence"),
    }


def _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot) -> list[EntryPlan]:
    """FIX2 path: build one EntryPlan per entry in signal['strategies'] (each entry already
    carries name/side/setup/triggers/quality, evaluated independently by the producer). The
    arm applies ONLY its gate (selectivity) + sizing; the exit shape comes from the REGISTRY."""
    plans: list[EntryPlan] = []
    for entry in signal.get("strategies") or []:
        strat = strategies.by_name(str(entry.get("name")))
        if strat is None:
            continue  # unknown strategy name -> skip (forward-compat)
        side = entry.get("side")
        if side not in ("P", "C"):
            continue
        setup = str(entry.get("setup") or strat.name)
        blk = _gate_block_for_entry(entry)
        elite = _is_elite(blk)
        quality = entry.get("quality") or ("ELITE" if elite else "BASE")
        gate_reason = _gate_check(arm, blk, signal)
        e_spot = entry.get("spot", spot)
        if gate_reason is not None:
            plans.append(EntryPlan(arm_id, "HOLD", side, setup, None, None, quality,
                                   f"gate: {gate_reason}", strategy=strat.name))
            continue
        if e_spot is None:
            plans.append(EntryPlan(arm_id, "HOLD", side, setup, None, None, quality,
                                   "no spot in signal", strategy=strat.name))
            continue
        strike = strike_selection.pick_strike(float(e_spot), float(equity), side, tiers)
        qty = _qty_for(params.get("position_sizing_tiers"), float(equity), elite)
        if qty is None:
            plans.append(EntryPlan(arm_id, "HOLD", side, setup, strike, None, quality,
                                   "no sizing tier covers equity", strategy=strat.name))
            continue
        plans.append(EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality,
                               f"{strat.name} {side} ({quality})",
                               strategy=strat.name, exit_shape=_exit_shape_dict(strat)))
    return plans


def plan_all(
    arm: Mapping[str, Any],
    signal: Mapping[str, Any],
    equity: float,
    params: Mapping[str, Any],
) -> list[EntryPlan]:
    """Multi-strategy successor to plan_entry: EVERY validated strategy that fired this tick,
    gated + sized by THIS arm. The account contributes ONLY selectivity (_gate_check) and
    sizing (strike tier + qty); each strategy brings its own proven exit. No direction lock,
    no per-account strategy silo — that was the bug. One EntryPlan per (side, strategy).

    FIX2: when the signal carries the producer's `strategies[]` set (every registered edge
    evaluated independently), plan it directly so VWAP_CONTINUATION (and any future strategy)
    fires as its own plan, not just the ribbon read. When `strategies[]` is ABSENT, fall back
    to the side-block setup-name match (backward-compat with the v1 signal + all existing tests)."""
    arm_id = str(arm["id"])
    spot = signal.get("spot")
    tiers = _tiers_for_arm(arm)
    if signal.get("strategies") is not None:
        return _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)

    src = _perception_for_arm(signal, arm)
    plans: list[EntryPlan] = []
    for side, blk in (("P", src.get("bear") or {}), ("C", src.get("bull") or {})):
        fired = strategies.fired(blk)
        if not fired:
            continue
        elite = _is_elite(blk)
        quality = "ELITE" if elite else "BASE"
        gate_reason = _gate_check(arm, blk, signal)
        for strat in fired:
            setup = str(blk.get("setup_name") or strat.name)
            if gate_reason is not None:
                plans.append(EntryPlan(arm_id, "HOLD", side, setup, None, None, quality,
                                       f"gate: {gate_reason}", strategy=strat.name))
                continue
            if spot is None:
                plans.append(EntryPlan(arm_id, "HOLD", side, setup, None, None, quality,
                                       "no spot in signal", strategy=strat.name))
                continue
            strike = strike_selection.pick_strike(float(spot), float(equity), side, tiers)
            qty = _qty_for(params.get("position_sizing_tiers"), float(equity), elite)
            if qty is None:
                plans.append(EntryPlan(arm_id, "HOLD", side, setup, strike, None, quality,
                                       "no sizing tier covers equity", strategy=strat.name))
                continue
            plans.append(EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality,
                                   f"{strat.name} {side} ({quality})",
                                   strategy=strat.name, exit_shape=_exit_shape_dict(strat)))
    return plans


# --- phase B: risk gate (reuses the single authority) ------------------------
def finalize(
    plan: EntryPlan,
    *,
    equity: float,
    start_of_day_equity: float,
    premium: Optional[float],
    current_position_status: Any,
    day_trades_used_5d: int,
    kill_switch_tripped: bool,
    prior_stops_today: Sequence[str],
    params: Mapping[str, Any],
    account_label: str,
) -> ArmDecision:
    """Run the shared risk gate over an ENTER plan; HOLD plans pass through."""
    if plan.action == "HOLD":
        return ArmDecision(plan.arm_id, "HOLD", plan.side, plan.setup_name, plan.strike,
                           plan.qty, None, plan.quality, None, plan.reason)
    decision = risk_gate.check_order(
        account_label,
        equity=equity,
        start_of_day_equity=start_of_day_equity,
        proposed_qty=plan.qty,
        premium=premium,
        setup_name=plan.setup_name,
        current_position_status=current_position_status,
        day_trades_used_5d=day_trades_used_5d,
        kill_switch_tripped=kill_switch_tripped,
        prior_stops_today=prior_stops_today,
        params=params,
    )
    if not decision.allowed:
        return ArmDecision(plan.arm_id, "HOLD", plan.side, plan.setup_name, plan.strike,
                           plan.qty, premium, plan.quality, decision.code,
                           f"risk_gate denied: {decision.reason}")
    action = "ENTER_BEAR" if plan.side == "P" else "ENTER_BULL"
    return ArmDecision(plan.arm_id, action, plan.side, plan.setup_name, plan.strike,
                       plan.qty, premium, plan.quality, "ALLOW", plan.reason)


# --- runner (DRY-RUN by default) ---------------------------------------------
def _base_params_for(arm: Mapping[str, Any]) -> dict:
    """The unpatched base params for this arm — SAFE or BOLD params.json verbatim.

    Side-class routing is unchanged: bold/risky arms (or a config_source naming the
    aggressive params) read PARAMS_BOLD; everything else reads PARAMS_SAFE.
    """
    src = str(arm.get("config_source", ""))
    if "aggressive" in src or str(arm["id"]).startswith(("bold", "risky")):
        return json.loads(PARAMS_BOLD.read_text(encoding="utf-8"))
    return json.loads(PARAMS_SAFE.read_text(encoding="utf-8"))


def _params_for(arm: Mapping[str, Any]) -> dict:
    """Per-arm params = base SAFE/BOLD params with the arm's `params_patch` shallow-merged on top.

    This is the ONE sizing lever that makes per-arm differentiation real (the gates only ADD
    selectivity; sizing comes from params.position_sizing_tiers in plan_entry, and strike depth
    from strike_tier_table read by _tiers_for_arm). PARITY INVARIANT (tested): an arm with NO
    params_patch returns a dict byte-identical to the base SAFE/BOLD params — so safe-1/safe-3/
    risky-1 (no patch) behave exactly as before this change. A patch shallow-overwrites only the
    top-level keys it names (e.g. position_sizing_tiers, strike_tier_table); it never deep-merges.
    """
    base = _base_params_for(arm)
    patch = arm.get("params_patch")
    if isinstance(patch, Mapping) and patch:
        base.update(patch)
    return base


def run_dry(signal: Mapping[str, Any], accounts: Mapping[str, Any]) -> list[tuple[ArmDecision, Optional[EntryPlan]]]:
    """Evaluate every active arm against the signal. Places NO orders.

    Returns (decision, selected_plan) pairs so the dry-run can surface which strategy
    fired and the exit shape it would have used. selected_plan is None when no strategy
    fired at all (a pure no-setup HOLD)."""
    out: list[tuple[ArmDecision, Optional[EntryPlan]]] = []
    for arm in accounts.get("arms", []):
        if arm.get("status") != "active":
            continue
        params = _params_for(arm)
        equity = float(arm.get("starting_equity") or 0.0)
        # MULTI-STRATEGY: every fired strategy gated+sized by this arm, ONE selected by
        # REGISTRY priority (one-position rule). Each plan carries its strategy's exit shape.
        plan = select_plan(plan_all(arm, signal, equity, params))
        if plan is None:
            out.append((ArmDecision(str(arm["id"]), "HOLD", None, None, None, None, None,
                                    None, None, "no qualifying setup (no strategy fired)"), None))
            continue
        # premium for the SELECTED plan's side (faithful WATCH risk-gate input).
        # FIX2 path: prefer the chosen strategy entry's est_premium; else the side-block's.
        premium = None
        for e in signal.get("strategies") or []:
            if e.get("name") == plan.strategy and e.get("side") == plan.side:
                premium = e.get("est_premium")
                break
        if premium is None:
            src = _perception_for_arm(signal, arm)
            side_blk = (src.get("bull") if plan.side == "C" else src.get("bear")) or {}
            premium = side_blk.get("est_premium", signal.get("est_premium"))
        decision = finalize(
            plan,
            equity=equity,
            start_of_day_equity=equity,
            premium=premium,
            current_position_status=None,  # dry-run assumes flat; live fetches broker
            day_trades_used_5d=0,
            kill_switch_tripped=False,
            prior_stops_today=[],
            params=params,
            account_label=str(arm.get("account_number") or arm["id"]),
        )
        out.append((decision, plan))
    return out


def place_bracket_rest(*_args, **_kwargs):  # pragma: no cover - Milestone 2
    """LIVE order placement. Intentionally not implemented in Milestone 1.

    Guard contract for Milestone 2: refuse unless an explicit enable flag exists
    AND the market is open AND the account is broker-verified flat. Never places
    from this dry-run milestone.
    """
    raise NotImplementedError(
        "Live placement is Milestone 2 — gated behind enable-flag + market-open + flat-verify."
    )


def _exit_str(plan: Optional[EntryPlan]) -> str:
    """Compact exit-shape summary for the dry-run table (stop/tp1/frac/lock)."""
    ex = getattr(plan, "exit_shape", None) if plan else None
    if not ex:
        return ""
    return (f"stop{ex.get('premium_stop_pct')}/tp{ex.get('tp1_premium_pct')}/"
            f"f{ex.get('tp1_qty_fraction')}/{ex.get('profit_lock_mode')}")


def _print_table(rows: Sequence[tuple[ArmDecision, Optional[EntryPlan]]]) -> None:
    print(f"{'arm':10} {'action':12} {'side':4} {'strike':>7} {'qty':>4} {'prem':>6} "
          f"{'quality':8} {'strategy':16} {'exit':34} reason")
    print("-" * 140)
    for d, plan in rows:
        strat = (plan.strategy if plan and plan.strategy else "") or ""
        print(f"{d.arm_id:10} {d.action:12} {str(d.side or ''):4} "
              f"{str(d.strike or ''):>7} {str(d.qty or ''):>4} {str(d.premium or ''):>6} "
              f"{str(d.quality or ''):8} {strat:16} {_exit_str(plan):34} {d.reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fleet executor (dry-run).")
    ap.add_argument("--signal", required=True, help="path to a shared-signal.json")
    args = ap.parse_args()
    signal = json.loads(Path(args.signal).read_text(encoding="utf-8"))
    accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    rows = run_dry(signal, accounts)
    _print_table(rows)
    DECISIONS_DIR.mkdir(exist_ok=True)
    for d, plan in rows:
        line = json.dumps({"tick_id": signal.get("tick_id"), "time_et": signal.get("time_et"),
                           "mode": "DRY_RUN",
                           "strategy": (plan.strategy if plan else None),
                           "exit_shape": (plan.exit_shape if plan else None),
                           **asdict(d)})
        (DECISIONS_DIR / f"{d.arm_id}.jsonl").open("a", encoding="utf-8").write(line + "\n")


if __name__ == "__main__":
    main()
