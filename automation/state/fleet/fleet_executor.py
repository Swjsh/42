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
    # STRUCTURE-STOP (2026-07-09, additive/default-None): the chart level this ENTRY's
    # signal reacted to (build_shared_signal.py's nearest_active_level derivation), threaded
    # end-to-end into ExitState so a flag-gated structure-mode position knows its level.
    trigger_level: Optional[float] = None


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
    # STRUCTURE-STOP (2026-07-09, additive/default-None): carries the ENTER plan's
    # trigger_level through to the placement layer (_place_live reads decision.trigger_level).
    trigger_level: Optional[float] = None
    # SIZING-DEADLOCK TELEMETRY (2026-07-30, additive/default-None): on a per-order sizing
    # refusal, risk_gate.explain_block's dict — says whether the deny was "size down" or
    # "NO legal qty exists at this premium" (deadlock). Rides into the arm's decisions.jsonl
    # via fleet_live's `**asdict(decision)`. Populated ONLY on a deny; None everywhere else,
    # so every ALLOW row is byte-identical to before.
    binding: Optional[dict] = None


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


def _effective_passed(block: Mapping[str, Any], arm: Optional[Mapping[str, Any]]) -> bool:
    """Per-arm hard-skip override (GATE-TIERS-IMPLEMENT, 2026-07-23, audit rank #3:
    markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md section 4 -- 'require_bearish_
    fill_bar ... not inherited via _HARD_SKIP' for RISKY-tier arms).

    Default (arm has no `gate_params.hard_skip_verdicts` key) reads block['passed']
    EXACTLY as today -- byte-identical for every arm that doesn't opt in. An arm whose
    accounts.json carries `gate_params: {"hard_skip_verdicts": [...]}` instead honors
    ONLY the verdicts named in that list as hard blocks; a verdict in
    build_shared_signal.py's GLOBAL _HARD_SKIP_VERDICTS but absent from the arm's own
    list is RESCUED via the block's score_peak_passed (the quality check computed
    ignoring the hard-skip filter). An empty list means the arm ignores every global
    hard-skip gate (the RISKY/minimum-viable tier)."""
    gate_params = (arm or {}).get("gate_params") or {}
    if "hard_skip_verdicts" not in gate_params:
        return block.get("passed") is True
    allowed_hard_skips = set(gate_params.get("hard_skip_verdicts") or [])
    hard_skip_reason = block.get("hard_skip_action")
    if hard_skip_reason and hard_skip_reason in allowed_hard_skips:
        return False  # this arm still honors this specific hard-skip verdict
    return block.get("score_peak_passed") is True


def _chosen_side(signal: Mapping[str, Any], arm: Optional[Mapping[str, Any]] = None):
    """Pick the candidate side from the shared signal: (side, side_block, setup).

    If `arm` is supplied and the signal carries dual-perception sub-blocks, the arm's
    role-appropriate block is used; otherwise the top-level bear/bull is read (v1 behavior)."""
    src = _perception_for_arm(signal, arm)
    bear = src.get("bear") or {}
    bull = src.get("bull") or {}
    bear_go = _effective_passed(bear, arm)
    bull_go = _effective_passed(bull, arm)
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


def _is_full_send(arm: Optional[Mapping[str, Any]]) -> bool:
    """True iff this arm carries gate_override.full_send (the FULL-SEND risk profile)."""
    return bool(((arm or {}).get("gate_override") or {}).get("full_send"))


def _tiers_for_arm(arm: Mapping[str, Any]):
    """Pick the strike-offset table (SAFE=ATM / BOLD=OTM) for this arm.

    strike_tier_table may be set as a TOP-LEVEL arm key OR inside the arm's params_patch
    (the design files some arms' table under params_patch). The explicit value wins; absent
    one, default by side-class from the arm id. .lower() is applied defensively.

    FULL-SEND ARMS ARE **NOT** SPECIAL-CASED HERE -- and that is a MEASURED decision, not an
    oversight (2026-07-31). An ATM override for the full-send arm was built, then REVERTED the
    same session when its own A/B cell came back: over 387 sessions of real OPRA fills, moving
    the full-send profile from OTM-2 to ATM changed total P&L from +$3,430 to -$5,110 (min-size
    scaled: +$1,951 -> -$4,036) while changing trade count by less than 2% (332 -> 327). The
    intended benefit -- clearing the $0.30 min_entry_premium floor that killed 15 of risky-1's
    16 named-setup ticks on 2026-07-31 -- is NOT observable in this harness at all, because
    that floor lives in fleet_executor.finalize(), not in the orchestrator. So the change had a
    measured cost and an unmeasurable benefit; shipping it would have been exactly the
    "tune a knob before the cause is known" anti-pattern. The arm's premium-floor problem is a
    FLOOR/strike-tier question and is owned by the min_entry_premium provenance audit, not by
    the full-send lane. See analysis/recommendations/full-send-arm-2026-07-31.md.
    """
    patch = arm.get("params_patch") or {}
    table = arm.get("strike_tier_table") or (patch.get("strike_tier_table") if isinstance(patch, Mapping) else None)
    if not table:
        table = "safe" if str(arm["id"]).startswith("safe") else "bold"
    table = str(table).lower()
    if table == "safe":
        return strike_selection.V15_SAFE_TIERS
    if table == "bold_core":
        # FLEET-STRIKE-TIER-ATM-EXTENSION (2026-08-01, pre-registered): risky-1/risky-3 only
        # (never safe-3 -- its OTM choice is documented-deliberate for the $600 notional cap
        # at $2K equity). Repoints the $0-2K bracket from OTM-3 to ATM, the SAME table core
        # Bold was wired to 2026-07-17-18 (V15_BOLD_CORE_TIERS is a validated, guard-tested,
        # already-live table -- see crypto/lib/strike_selection.py). Falsification rail +
        # pre-registered gates: analysis/recommendations/fleet-strike-tier-atm-extension-
        # prereg-2026-08-01.json, frozen BEFORE this arming.
        return strike_selection.V15_BOLD_CORE_TIERS
    return strike_selection.V15_BOLD_TIERS


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


# SHRINK-NOT-DENY (2026-08-03, SIZING-SCALING-DECISION-2026-08-03.md + ARM-PARTICIPATION-
# AND-GROWTH-2026-08-03.md #2): _qty_for itself CANNOT do the shrink -- it is a phase-A pure
# gating function (see the "phase A: pure gating" banner below) called from plan_entry /
# _plan_from_strategies / plan_all BEFORE any live premium is resolved, and the shrink math
# needs premium (notional = premium * qty * 100). The earliest point in this file's own call
# chain where a tiered qty and a resolved premium both exist is finalize() (phase B, the risk
# gate wrapper) -- see _shrink_qty_to_affordable below and its call site inside finalize().


# --- recency-conditioned min-sizing (2026-07-10 ship, A/B: analysis/recommendations/ -------
# recency-sizing-ab.json -- policy_dominates=true on 8 real fleet-fill days, -$1,274 ->
# -$793, worst day -$388 -> -$297. Staged mechanism: analysis/recommendations/
# recency-sizing-proposal.json. Flag-gated (recency_min_size_enabled, default False ->
# byte-identical). Scope: ribbon_ride ONLY (the A/B's population, C29) -- every other
# strategy (vwap_continuation included) is untouched even when the flag is on.
RECENCY_CONFIRMATION_PATH = REPO_ROOT / "automation" / "state" / "recency-confirmation.json"
RECENCY_MIN_SIZE_STRATEGY = strategies.RIBBON_RIDE.name  # "ribbon_ride"


def _recency_verdict(path: Optional[Path] = None) -> str:
    """Tri-state RED/YELLOW/GREEN read of recency-confirmation.json's `headline` block --
    the SAME field the capital gates already read (contender_oos_check.assess_recency_gate
    / autonomy_actuator._recency_gate_clears / task_scorer._recency_explicitly_red all key
    off headline.edges_confirmed_on_recent / headline.any_red; test_task_scorer_recency.py
    pins the two-reader field-parity contract). Mirrors recency_check.append_status's own
    STATUS.md state derivation (RED-BLOCKED / CONFIRMED / YELLOW):
        RED    = headline.any_red is True
        GREEN  = headline.edges_confirmed_on_recent is True (and not RED)
        YELLOW = everything else (not-yet-confirmed / small-n / no fills)
    DISCLOSURE: this headline is produced by recency_check.py, which scores THREE edges
    (vwap_continuation / vwap_reclaim_failed_break / vix_regime_dayside) -- NOT ribbon_ride
    (recency-sizing-ab.json's own disclosure). It is reused here as the standing, already-
    wired "is the shop in a confirmed cold stretch" signal (the identical field 3 existing
    capital gates already key off) rather than standing up a second per-strategy verdict
    producer -- ribbon_ride's OWN point-in-time A/B (recency_sizing_ab.py) independently
    verdicted RED on all 8 real fleet-fill days in the same window, so the two signals agree
    on the evidence in hand.
    FAIL-OPEN: missing/unreadable/malformed file or headline -> "YELLOW". This gate only
    ever NARROWS an already risk_gate-allowed qty, never blocks a trade outright, so
    uncertainty must default to normal sizing, not a clamp -- the opposite fail-direction
    from the ship-path gates (which fail CLOSED because they block capital moves, not just
    shrink one).
    """
    p = path or RECENCY_CONFIRMATION_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "YELLOW"
    if not isinstance(data, dict):
        return "YELLOW"
    headline = data.get("headline")
    if not isinstance(headline, dict):
        return "YELLOW"
    if headline.get("any_red") is True:
        return "RED"
    if headline.get("edges_confirmed_on_recent") is True:
        return "GREEN"
    return "YELLOW"


def _apply_full_send_min_sizing(
    qty: Optional[int], arm: Optional[Mapping[str, Any]], params: Mapping[str, Any],
) -> "tuple[Optional[int], Optional[str]]":
    """FULL-SEND (2026-07-31): clamp qty DOWN to params.min_contracts on EVERY entry a
    full-send arm makes -- the "never loose on RISK" half of the profile. J's design is
    "get in more, at minimum size"; without this the arm would take MORE trades at its normal
    BOLD qty, which is the opposite of the intent and the one way this lane could actually
    hurt. Non-full-send arms pass through byte-identical (vary-and-assert, C14). min() is a
    ceiling, never a floor-raise: a qty already at/below min_contracts is left alone.
    Returns (qty, clamp_note); clamp_note is None unless the clamp actually fired."""
    if qty is None or not _is_full_send(arm):
        return qty, None
    try:
        min_qty = int(params.get("min_contracts", 3))
    except (TypeError, ValueError):
        min_qty = 3
    clamped = min(int(qty), min_qty)
    if clamped == qty:
        return qty, None
    return clamped, f"qty clamped {qty}->{clamped}: FULL_SEND min size"


def _apply_recency_min_sizing(
    qty: Optional[int], strategy_name: Optional[str], params: Mapping[str, Any],
) -> "tuple[Optional[int], Optional[str]]":
    """Clamp qty DOWN to the account's min_contracts floor (Rule 6) when ribbon_ride's
    CURRENT recency verdict is RED. YELLOW/GREEN/unreadable-state/flag-off/wrong-strategy
    all pass qty through byte-identical (vary-and-assert, C14). ONLY the RED branch ships:
    the A/B's own ALL_RED_CAVEAT discloses every one of its 8 real-fill days verdicted RED,
    so the staged proposal's YELLOW->0.5x tier is UNPROVEN on real data and deliberately
    NOT implemented here -- RED-floor only, the one mechanism the evidence actually covers.
    Uses min() (a ceiling, never a floor-raise): a qty already at/below min_contracts is
    left alone -- this only stops an elite/tier UPSIZE above the floor, matching the
    proposal's own min_contracts_consistency note (red_qty already equals min_contracts).
    Returns (qty, clamp_note) -- clamp_note is the placement-log line when the clamp
    actually fired (qty strictly decreased), else None.
    """
    if qty is None or not bool(params.get("recency_min_size_enabled", False)):
        return qty, None
    if strategy_name != RECENCY_MIN_SIZE_STRATEGY:
        return qty, None
    if _recency_verdict() != "RED":
        return qty, None
    try:
        min_qty = int(params.get("min_contracts", 3))
    except (TypeError, ValueError):
        min_qty = 3
    clamped = min(int(qty), min_qty)
    if clamped == qty:
        return qty, None
    note = f"qty clamped {qty}->{clamped}: recency RED"
    print(f"[fleet_executor] {note} (strategy={strategy_name})", flush=True)
    return clamped, note


# SHRINK-NOT-DENY (2026-08-03 ship, DEFECT FIX -- not an arming of new scaling).
# SIZING-SCALING-DECISION-2026-08-03.md proved fleet_executor's position_sizing_tiers
# mechanism (_qty_for, already LIVE for safe-3/risky-1/risky-3 since inception -- see
# accounts.json grid.sizing_profiles) is DENY-not-shrink: finalize() historically passed the
# full tiered qty straight to risk_gate.check_order with no affordability pre-check, so a
# qty that doesn't fit the per-trade cap gets refused WHOLESALE instead of sized down. That
# document measured this costs 96% of a controlled Safe-equivalent population's total P&L
# right at the $2,000 tier boundary ($207.90 vs a $4,820.40 baseline) -- because the tier's
# own qty jump (e.g. 5->8 for Bold) TIGHTENS the per-contract premium ceiling under the SAME
# fixed dollar cap, pricing itself out of most of its own opportunity set. ARM-PARTICIPATION-
# AND-GROWTH-2026-08-03.md #2 confirmed this is not hypothetical for the fleet: risky-3's own
# equity has round-tripped the $2,000 line at least twice this month and sits at $2,121.61
# (live-verified) as of this ship -- inside the affected band right now.
#
# THE FIX mirrors setup/scripts/heartbeat_core.py's OWN already-proven clamp shape
# (heartbeat_core.py:1964-1967 -- read-only reference, that file is out of scope for this
# change and was NOT edited): shrink a too-big qty DOWN to the largest size risk_gate will
# actually allow, using risk_gate.max_affordable_qty -- the EXACT SAME cap math check_order
# itself uses (C14: no re-typed literals, the two can never silently diverge). This is a
# DEFECT FIX to a sizing mechanism that is ALREADY ARMED AND LIVE on the fleet, not a new
# arming decision -- unlike core (which has never been wired to position_sizing_tiers at
# all, per SIZING-SCALING-DECISION's own §5), the fleet's tiers already drive every fleet_rest
# order today. Whether to EVER arm scaled sizing on CORE is explicitly J's call and untouched
# here.
#
# THE FLOOR IS IMMOVABLE: max_affordable_qty's own contract (backtest/lib/risk_gate.py:613-
# 641) guarantees its return value is always EITHER 0 (a genuine deadlock -- not even
# min_contracts, Rule 6's floor, fits under the cap) OR >= min_contracts. This function can
# therefore never shrink a qty below Rule 6's floor -- it can only pick a legal size in
# [min_contracts, original_qty), or leave a genuine deadlock exactly as denied as before.
def _shrink_qty_to_affordable(
    qty: Optional[int], equity: float, premium: Optional[float], params: Mapping[str, Any],
) -> "tuple[Optional[int], Optional[str]]":
    """Shrink a too-big tiered qty DOWN to risk_gate's own max_affordable_qty when doing so
    would turn a would-be RISK_CAP/MAX_PREMIUM_TIER deny into a legal, smaller ALLOW.

    qty=None (no sizing tier covered equity) or premium=None (not yet resolved -- e.g. a
    caller that hasn't priced the option yet) pass through byte-identical -- this only ever
    fires once a real qty AND a real premium both exist. A deadlock (max_affordable_qty==0,
    i.e. not even min_contracts is affordable) also passes through unchanged -- there is no
    legal size to shrink to, so the caller's existing risk_gate.check_order call denies it
    exactly as it did before this fix (no regression versus baseline). Any exception from the
    affordability math (malformed params, etc.) fails OPEN to the ORIGINAL qty -- this
    function only ever narrows an outcome that check_order would otherwise decide; it must
    never itself become a new reason a legal order fails to place.

    Returns (qty, shrink_note) -- shrink_note is the placement-log line when the shrink
    actually fired (qty strictly decreased), else None. Matches the existing
    _apply_recency_min_sizing / _apply_full_send_min_sizing note contract.
    """
    if qty is None or premium is None:
        return qty, None
    try:
        afford = risk_gate.max_affordable_qty(equity=equity, premium=premium, params=params)
    except Exception:  # noqa: BLE001 -- telemetry-adjacent math must never block a legal order
        return qty, None
    qty_i = int(qty)
    if not afford or afford >= qty_i:
        return qty, None
    return afford, f"qty shrunk {qty_i}->{afford}: RISK_CAP shrink-not-deny (was DENY pre-2026-08-03)"


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
    # SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX (2026-07-11): a `min_confidence` check used to
    # live here (see git history / accounts.json.bak-2026-06-25-pre-grid) comparing
    # against blk.get("confidence", signal.get("confidence")) -- but build_shared_signal.py
    # has NEVER populated a "confidence" field on any signal it emits (see its own
    # "FAITHFULNESS NOTE (v1)" docstring: "confidence/confluence/est_premium" are
    # explicitly omitted pending "the pre-LIVE step" that was never built). Any arm
    # with min_confidence set would therefore ALWAYS read conf=None and ALWAYS HOLD --
    # a permanent, silent always-block, not real selectivity. GATE-PROVENANCE-AUDIT-
    # 2026-07-02 finding E5/F6: 4 rows in that window, safe-3 down to 1 trade/30d.
    # DELETED rather than "fixed forward" because populating a genuine confidence
    # score would mean inventing/validating a new scoring model tonight (out of scope
    # for a surgical bug fix) -- and the 2026-06-25 grid rebuild had ALREADY dropped
    # min_confidence from every live accounts.json arm (confirmed: replay_fleet_arms.py
    # independently notes this is "moot now"), so removing the dead code changes NO
    # current trading behavior. Guard: test_min_confidence_gate_removed_and_inert
    # (test_fleet_executor.py) -- proves even a stale/reintroduced min_confidence key
    # in gate_override can never again silently starve an arm.
    g = arm.get("gate_override") or {}
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
    # plan_entry is the pre-FIX2 single-strategy path: `setup` only ever carries a ribbon
    # setup name here (_chosen_side's only defaults), so scope by entry_setups membership
    # rather than assuming -- this stays correct even if a caller injects a non-ribbon
    # setup_name into the v1 bear/bull block.
    _strat_for_sizing = (RECENCY_MIN_SIZE_STRATEGY
                         if str(setup or "").upper() in {s.upper() for s in strategies.RIBBON_RIDE.entry_setups}
                         else None)
    qty, _clamp_note = _apply_recency_min_sizing(qty, _strat_for_sizing, params)
    reason = f"clean {side} entry ({quality})"
    if _clamp_note:
        reason += f"; {_clamp_note}"
    return EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality, reason)


def _gate_check(arm: Mapping[str, Any], blk: Mapping[str, Any], signal: Mapping[str, Any]) -> Optional[str]:
    """The arm's SELECTIVITY gate (triggers / quality). Returns None to pass,
    else a short reason. This is the account's ONLY job besides sizing — it adds strictness,
    never a direction lock or a strategy choice.

    SAFE3-CONFIDENCE-ALWAYS-BLOCK-FIX (2026-07-11): a `min_confidence` check used to
    live here too -- removed for the same reason as plan_entry's (see the comment
    there): build_shared_signal.py never populates "confidence" on any signal, so the
    check could only ever always-HOLD, never genuinely gate. `signal` is kept as a
    parameter (now otherwise unused) to avoid touching its two call sites for a
    behavior-preserving cleanup that isn't part of this bug fix.
    """
    g = arm.get("gate_override") or {}
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


def _exit_shape_dict(strat, arm: Optional[Mapping[str, Any]] = None) -> dict:
    """The full exit shape threaded into the EntryPlan -> live exit_manager. Uses the
    ExitShape.to_dict() canonical form (includes runner_target_pct / trail_pct /
    profit_lock_arm_pct) so the live runner ride is fully described by the strategy.

    EXIT-PARAMETER A/B OVERLAY (2026-07-20, J directive: "every fleet arm takes the SAME
    engine signals but with DIFFERENT exit/risk parameters"): when `arm` is given and its
    accounts.json `params_patch.exit_patch` is non-empty, the patch is shallow-merged OVER
    this dict (patch keys win) -- so two arms trading the IDENTICAL entry signal can carry
    DIFFERENT stops/targets/trails, turning daily real fills into a live exit-parameter A/B.
    This intentionally BREAKS the pre-2026-07-20 "exit is a property of the strategy, not
    the account" invariant (test_six_account_exit_shapes.py updated same-session) -- that
    was correct doctrine for "no accidental per-account exit drift"; this is a deliberate,
    disclosed, schema-validated overlay, not drift. arm=None (every pre-existing caller
    that never passes it) stays byte-identical -- opt-in only.
    """
    ex = strat.exit
    base = ex.to_dict() if hasattr(ex, "to_dict") else {  # defensive fallback (no to_dict)
        "premium_stop_pct": ex.premium_stop_pct,
        "tp1_premium_pct": ex.tp1_premium_pct,
        "tp1_qty_fraction": ex.tp1_qty_fraction,
        "profit_lock_mode": ex.profit_lock_mode,
    }
    if arm is not None:
        patch = _exit_patch_for_arm(arm)
        if patch:
            base = {**base, **patch}
    return base


# EXIT_PATCH schema = exactly strategies.ExitShape's dataclass fields -- the SAME keys
# ExitShape.to_dict() emits and exit_manager.ExitState.from_entry reads (verified against
# that function's exit_shape.get(...) call sites, 2026-07-20). Never hand-maintained as a
# separate list -- deriving it from the dataclass means a future ExitShape field addition
# is automatically a valid exit_patch key with no second edit required.
EXIT_PATCH_ALLOWED_KEYS: frozenset = frozenset(
    getattr(strategies.ExitShape, "__dataclass_fields__", {}).keys()
)


def _validate_exit_patch(arm_id: str, patch: Any) -> dict:
    """Validate an arm's params_patch.exit_patch against the REAL ExitShape schema.

    None/absent -> {} (byte-identical no-op, the overwhelming default). A non-dict value
    or ANY key outside EXIT_PATCH_ALLOWED_KEYS raises ValueError immediately -- fail loud,
    never silently ignored (C14/L201: a translated-but-unapplied knob is this repo's #1
    recurring failure class). Called both eagerly (validate_accounts_exit_patches, at
    accounts.json load) and at every merge site (_exit_shape_dict), so a typo'd key can
    never survive to production regardless of whether this arm's strategies happen to
    fire on a given tick.
    """
    if patch is None:
        return {}
    if not isinstance(patch, Mapping):
        raise ValueError(
            f"arm {arm_id!r}: params_patch.exit_patch must be a dict, got "
            f"{type(patch).__name__}"
        )
    unknown = set(patch) - EXIT_PATCH_ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"arm {arm_id!r}: params_patch.exit_patch has unknown key(s) "
            f"{sorted(unknown)} -- valid keys are {sorted(EXIT_PATCH_ALLOWED_KEYS)} "
            f"(strategies.ExitShape schema; do not invent keys the exit manager can't read)"
        )
    return dict(patch)


def _exit_patch_for_arm(arm: Mapping[str, Any]) -> dict:
    """This arm's validated exit_patch dict (see _validate_exit_patch), or {} when absent."""
    arm_patch = arm.get("params_patch")
    raw = arm_patch.get("exit_patch") if isinstance(arm_patch, Mapping) else None
    return _validate_exit_patch(str(arm.get("id", "?")), raw)


def validate_accounts_exit_patches(accounts: Mapping[str, Any]) -> None:
    """Fail loud AT CONFIG-LOAD TIME: validate every arm's exit_patch up front, independent
    of whether any strategy fires for that arm on a given signal (a per-tick-only check
    could leave a typo'd patch silently unvalidated for an inactive/quiet arm). Call once
    per accounts.json read. Raises ValueError on the first offending arm."""
    for arm in accounts.get("arms", []):
        _exit_patch_for_arm(arm)


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
        qty, _clamp_note = _apply_recency_min_sizing(qty, strat.name, params)
        qty, _fs_note = _apply_full_send_min_sizing(qty, arm, params)
        _clamp_note = _fs_note or _clamp_note
        # LEVEL PROVENANCE (G12, 2026-07-09 night): prefer the EXACT trigger level the entry
        # signal fired against (build_shared_signal's trigger_level_exact -- ground truth,
        # sourced verbatim from filters.detect_level_rejection/detect_level_reclaim via
        # core-decisions.jsonl) over the proximity-guess trigger_level (nearest_active_level
        # heuristic). Falls back to the heuristic only when the exact value is absent (e.g.
        # a TRENDLINE-tier entry with no level-tied trigger, or an older shared-signal.json
        # pre-dating this field) -- never guesses when BOTH are absent (stays None).
        _tl_exact = entry.get("trigger_level_exact")
        _tl = _tl_exact if _tl_exact is not None else entry.get("trigger_level")
        _reason = f"{strat.name} {side} ({quality})"
        if _clamp_note:
            _reason += f"; {_clamp_note}"
        plans.append(EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality,
                               _reason,
                               strategy=strat.name, exit_shape=_exit_shape_dict(strat, arm),
                               trigger_level=(float(_tl) if _tl is not None else None)))
    return plans


# --- PROBE ARM (2026-07-10 ship, amended same-session per participation-cascade evidence) --
# J directive 2026-07-10: "6 arms and nothing took a trade... why isn't 1 arm set to take
# riskier trades? we have 3 risky and 3 bold." DIAGNOSIS: every arm's ONLY job is _gate_check
# (selectivity) + sizing -- it can only ADD restriction on top of an already passed=True
# tick; nothing here can ever RESCUE a passed=False tick, however loose gate_override is. So
# the cohort/tier gates baked into the shared signal's passed-derivation (build_shared_signal
# mirrors heartbeat_core.py's GATE_KEYS: block_elite_bull, block_bull_1100_1200, block_conf_
# lvl_rec_afternoon, block_level_rejection, ...) apply UNIFORMLY to every arm. Fix: ONE
# designated arm (accounts.json top-level "probe_arm": risky-3 by default -- already the
# fleet's loosest-gate + riskiest-sizing fleet_rest cell) trades the cohorts those gates
# blocked, at min_contracts, via the separate signal['probe'] block build_shared_signal.py
# emits (_probe_passed_blocks -- see there for the full bypass rationale). Scope: ribbon_ride
# ONLY (the family the diagnosis covers) and ONLY when this arm's NORMAL pass (above) produced
# no ENTER this tick -- never a second, redundant entry alongside a normal one.
#
# AMENDMENT (same session, automation/state/participation-cascade.json evidence): the
# cohort/tier gates are real but are NOT the #1 blocker in practice -- min_entry_premium is
# (18 arm-events on 07-10 alone, ~2x every other blocker combined), because the fleet's own
# far-OTM/bold sizing tiers price their natural 0DTE contracts under the $0.30 floor. The
# floor's anti-spread-noise evidence is real and STAYS FULLY INTACT -- it is never bypassed,
# weakened, or special-cased for probe. Instead PROBE_STRIKE_TIERS gives probe's OWN contracts
# a NEARER (ATM-class) strike than the arm's normal bold/OTM table, so they clear the SAME
# floor on their own merits. block_bull_ribbon_flip (a GATE_KEYS name that looked plausible as
# another cohort gate) was checked and confirmed ABSENT from both params.json files -- no
# bypass needed for a gate that isn't armed.
#
# Every other gate (kill-switch/PDT/min_entry_premium floor/entry-time floor-ceiling/
# one-position/per-trade risk cap) still runs downstream in finalize()/risk_gate.check_order/
# fleet_live._place_live, completely untouched. Instant de-arm: accounts.json
# probe_arm.enabled=false. Guard: test_probe_arm.py.
PROBE_RIBBON_SETUPS = {s.upper() for s in strategies.RIBBON_RIDE.entry_setups}

# PROBE ARM STRIKE OVERRIDE: probe entries price a NEARER strike than the arm's own (bold/
# OTM) sizing table -- see the module comment above. A STANDALONE table (values happen to
# match strike_selection.V15_SAFE_TIERS today, but this is deliberately NOT a reference to
# it) so a future SAFE-arm-specific tier retune can never silently also change probe's
# strike selection -- low coupling over a few duplicated lines.
PROBE_STRIKE_TIERS: tuple = (
    strike_selection.StrikeTier(0.0, 2_000.0, 0, "ATM"),
    strike_selection.StrikeTier(2_000.0, 10_000.0, 0, "ATM"),
    strike_selection.StrikeTier(10_000.0, 25_000.0, 1, "Slight ITM"),
    strike_selection.StrikeTier(25_000.0, 999_999_999.0, 2, "ITM-2"),
)


def _is_probe_active(arm: Mapping[str, Any], probe_cfg: Optional[Mapping[str, Any]]) -> bool:
    """True iff probe_cfg (accounts.json's top-level "probe_arm" block) is enabled AND names
    THIS arm. probe_cfg=None (the default on every existing call site) or enabled=False is a
    byte-identical no-op -- this is the ONE gate the whole mechanism hangs off."""
    if not isinstance(probe_cfg, Mapping) or not probe_cfg.get("enabled"):
        return False
    return str(arm.get("id", "")) == str(probe_cfg.get("arm_id", ""))


def _cohort_tag(blocked_verdict: Any) -> str:
    """'SKIP_ELITE_BULL_LEVEL_RECLAIM' -> 'elite_bull_level_reclaim' (mechanical, always
    derivable -- the original verdict is one grep away from the tag)."""
    v = str(blocked_verdict or "UNKNOWN")
    v = v[5:] if v.startswith("SKIP_") else v
    return v.lower()


def _probe_plan(
    arm: Mapping[str, Any], signal: Mapping[str, Any], equity: float, params: Mapping[str, Any],
    arm_id: str, spot: Any, daily_cap: int, probe_entries_today: int,
) -> Optional[EntryPlan]:
    """Synthesize a min-size ribbon_ride EntryPlan from signal['probe'] (the cohort-bypass
    block) when THIS tick's cohort was blocked. Returns None when signal['probe'] carries no
    passed side at all (nothing to probe -- caller's normal HOLD reasoning stands unmodified).
    qty is HARD-CLAMPED to params.min_contracts -- never calls _qty_for or
    _apply_recency_min_sizing (already at floor, C29 N/A). Strike uses PROBE_STRIKE_TIERS
    (nearer than the arm's own bold/OTM table -- see module comment) NOT the arm's normal
    _tiers_for_arm result, so the probe's own contract naturally prices to clear the
    UNTOUCHED min_entry_premium floor instead of colliding with it like the arm's usual
    far-OTM strikes do."""
    probe = signal.get("probe")
    if not isinstance(probe, Mapping):
        return None
    for side, key in (("P", "bear"), ("C", "bull")):
        blk = probe.get(key)
        if not isinstance(blk, Mapping) or blk.get("passed") is not True:
            continue
        setup = str(blk.get("setup_name") or "")
        if setup.upper() not in PROBE_RIBBON_SETUPS:
            continue  # scope = ribbon_ride only (see module comment)
        cohort = _cohort_tag(blk.get("blocked_verdict"))
        if probe_entries_today >= daily_cap:
            return _hold(arm_id, side, setup,
                        f"PROBE_ARM cohort={cohort} blocked: daily cap reached "
                        f"({probe_entries_today}/{daily_cap})")
        if spot is None:
            return _hold(arm_id, side, setup, f"PROBE_ARM cohort={cohort} blocked: no spot in signal")
        strike = strike_selection.pick_strike(float(spot), float(equity), side, PROBE_STRIKE_TIERS)
        try:
            qty = int(params.get("min_contracts", 3))
        except (TypeError, ValueError):
            qty = 3
        trigs = list(blk.get("triggers_fired") or [])
        elite = _is_elite({"confluence": any("confluence" in str(t).lower() for t in trigs),
                           "triggers_fired": trigs})
        quality = "ELITE" if elite else "BASE"
        _tl = blk.get("trigger_level_exact")
        return EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality,
                         f"PROBE_ARM cohort={cohort}",
                         strategy=strategies.RIBBON_RIDE.name,
                         exit_shape=_exit_shape_dict(strategies.RIBBON_RIDE, arm),
                         trigger_level=(float(_tl) if _tl is not None else None))
    return None


def plan_all(
    arm: Mapping[str, Any],
    signal: Mapping[str, Any],
    equity: float,
    params: Mapping[str, Any],
    probe_cfg: Optional[Mapping[str, Any]] = None,
    probe_entries_today: int = 0,
) -> list[EntryPlan]:
    """Multi-strategy successor to plan_entry: EVERY validated strategy that fired this tick,
    gated + sized by THIS arm. The account contributes ONLY selectivity (_gate_check) and
    sizing (strike tier + qty); each strategy brings its own proven exit. No direction lock,
    no per-account strategy silo — that was the bug. One EntryPlan per (side, strategy).

    FIX2: when the signal carries the producer's `strategies[]` set (every registered edge
    evaluated independently), plan it directly so VWAP_CONTINUATION (and any future strategy)
    fires as its own plan, not just the ribbon read. When `strategies[]` is ABSENT, fall back
    to the side-block setup-name match (backward-compat with the v1 signal + all existing tests).

    PROBE ARM: probe_cfg/probe_entries_today default to an inert no-op (every existing call
    site is byte-identical). When probe_cfg names THIS arm and enabled=True, AND the pass
    above produced no ENTER, a min-size cohort-bypass plan is appended (see _probe_plan)."""
    arm_id = str(arm["id"])
    spot = signal.get("spot")
    tiers = _tiers_for_arm(arm)
    if signal.get("strategies") is not None:
        plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
    else:
        src = _perception_for_arm(signal, arm)
        plans = []
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
                qty, _clamp_note = _apply_recency_min_sizing(qty, strat.name, params)
                qty, _fs_note = _apply_full_send_min_sizing(qty, arm, params)
                _clamp_note = _fs_note or _clamp_note
                # LEVEL PROVENANCE: same exact-over-heuristic preference as _plan_from_strategies
                # (see comment there) -- the side-block fallback path mirrors it for parity.
                _tl_exact = blk.get("trigger_level_exact")
                _tl = _tl_exact if _tl_exact is not None else blk.get("trigger_level")
                _reason = f"{strat.name} {side} ({quality})"
                if _clamp_note:
                    _reason += f"; {_clamp_note}"
                plans.append(EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality,
                                       _reason,
                                       strategy=strat.name, exit_shape=_exit_shape_dict(strat, arm),
                                       trigger_level=(float(_tl) if _tl is not None else None)))

    if _is_probe_active(arm, probe_cfg) and not any(p.action == "ENTER" for p in plans):
        cap = int((probe_cfg or {}).get("daily_cap", 3))
        probe_plan = _probe_plan(arm, signal, equity, params, arm_id, spot,
                                 cap, probe_entries_today)
        if probe_plan is not None:
            plans.append(probe_plan)
    # SCORE LADDER (2026-07-27, J's graduated-arm design -- "the riskiest arm can hop in at
    # a seven out of ten"): the probe's sibling lane for SCORING-failed ticks. The :549
    # invariant ("nothing here can ever RESCUE a passed=False tick") is deliberately and
    # EXPLICITLY amended by this lane -- rescue is its entire purpose, so it is a separately
    # named mechanism behind its own per-arm config key, never a loosening of gate_override's
    # tighten-only semantics. Fires ONLY when: this arm sets gate_override.score_ladder_floor
    # (only risky-3 at ship, floor 7), no ENTER and no probe plan exists this tick, and the
    # signal's ladder block (build_shared_signal._ladder_block, fail-closed producer) carries
    # an available bear setup at/above the floor. Instant de-arm: delete the config key.
    if not any(p.action == "ENTER" for p in plans):
        ladder_plan = _ladder_plan(arm, signal, equity, params, arm_id, spot)
        if ladder_plan is not None:
            plans.append(ladder_plan)
    # FULL-SEND (2026-07-31, J directive: "we should just be getting in shit and seeing if it
    # works"). Third and loosest rescue lane, same shape/contract as probe + ladder: fires ONLY
    # for an arm carrying gate_override.full_send, ONLY when no other lane produced an ENTER,
    # and ONLY off the producer's explicitly-allowlisted COHORT-veto block. Min size, real
    # level as the chart stop, every risk guard downstream untouched.
    if not any(p.action == "ENTER" for p in plans):
        fs_plan = _full_send_plan(arm, signal, equity, params, arm_id, spot)
        if fs_plan is not None:
            plans.append(fs_plan)
    return plans


# --- FULL-SEND lane (2026-07-31) ----------------------------------------------------------
# Consumer half of build_shared_signal.py's `full_send` block -- read that module comment for
# the full rationale, the allowlist, and the pre-registered A/B behind it.
#
# THE ARCHITECTURAL FINDING THIS EXISTS TO FIX: an arm's gate_override can only ever ADD
# selectivity. Measured across ALL fleet history, gate_override blocked 45/3479 ticks on
# safe-3, 45/3479 on risky-1, 0/3479 on risky-3 -- and 0 of 128 on 2026-07-31, the day J called
# three entries the fleet did not take. Entry ADMISSION is decided upstream in the producer,
# which emits ONE strategies[] list every arm shares, so no accounts.json edit can express
# "this arm inherits fewer vetoes". This lane is the minimum change that makes it expressible.
#
# LOOSE ON SELECTION, NEVER LOOSE ON RISK. Dropped: cohort/tier vetoes (allowlist upstream).
# Fully retained and untouched downstream: the daily kill switch, risk_gate.check_order
# (per-trade cap Rule 6, PDT Rule 7, NOT_FLAT/no-add Rule 4), the min_entry_premium floor,
# entry-time floor/ceiling, EOD flatten, and broker-flat verification in fleet_live._place_live.
# Guard: test_full_send_arm.py (both directions -- it enters where gated arms are blocked, AND
# every risk guard provably still binds on it).
def _full_send_plan(
    arm: Mapping[str, Any], signal: Mapping[str, Any], equity: float,
    params: Mapping[str, Any], arm_id: str, spot: Any,
) -> Optional[EntryPlan]:
    """Min-size ribbon_ride entry off signal['full_send'] for an arm with
    gate_override.full_send. Returns None whenever the arm is not armed for this lane or the
    producer emitted nothing to rescue -- the caller's normal HOLD reasoning then stands
    unmodified. qty is HARD-CLAMPED to params.min_contracts (never _qty_for, never
    _apply_recency_min_sizing -- already at the floor). Strike uses PROBE_STRIKE_TIERS for the
    same reason the probe lane does: a nearer, ATM-class contract clears the UNTOUCHED
    min_entry_premium floor on its own merits instead of colliding with the arm's far-OTM
    table (the #1 practical blocker, 15 of risky-1's 16 named-setup ticks on 2026-07-31)."""
    g = arm.get("gate_override") or {}
    if not g.get("full_send"):
        return None
    fs = signal.get("full_send")
    if not isinstance(fs, Mapping):
        return None
    for side, key in (("P", "bear"), ("C", "bull")):
        blk = fs.get(key)
        if not isinstance(blk, Mapping) or blk.get("available") is not True:
            continue
        setup = str(blk.get("setup_name") or "")
        if setup.upper() not in PROBE_RIBBON_SETUPS:
            continue  # scope = ribbon_ride's validated setups only -- never a new strategy
        level = blk.get("level")
        if not isinstance(level, (int, float)):
            continue  # no chart-stop anchor -> no trade (a full-send entry is never stop-less)
        cohort = _cohort_tag(blk.get("blocked_verdict"))
        if spot is None:
            return _hold(arm_id, side, setup, f"FULL_SEND cohort={cohort} blocked: no spot in signal")
        strike = strike_selection.pick_strike(float(spot), float(equity), side, PROBE_STRIKE_TIERS)
        try:
            qty = int(params.get("min_contracts", 3))
        except (TypeError, ValueError):
            qty = 3
        trigs = list(blk.get("triggers_fired") or [])
        quality = "ELITE" if _is_elite({"triggers_fired": trigs}) else "BASE"
        return EntryPlan(arm_id, "ENTER", side, setup, strike, qty, quality,
                         f"FULL_SEND cohort={cohort} trig={'+'.join(trigs)}",
                         strategy=strategies.RIBBON_RIDE.name,
                         exit_shape=_exit_shape_dict(strategies.RIBBON_RIDE, arm),
                         trigger_level=float(level))
    return None


def _ladder_plan(
    arm: Mapping[str, Any], signal: Mapping[str, Any], equity: float,
    params: Mapping[str, Any], arm_id: str, spot: Any,
) -> Optional[EntryPlan]:
    """Min-size ribbon_ride entry off signal['ladder']['bear'] when this arm's score floor
    admits it. Mirrors _probe_plan's shape deliberately: min_contracts hard clamp (never
    _qty_for), PROBE_STRIKE_TIERS (same premium-floor reasoning), risk_gate/finalize()
    downstream completely untouched. BEAR ONLY at ship -- the bull mirror waits for its own
    pre-registered evidence (2026-07-27's bull-9 fired mid-fade and would have lost).

    The raw detection's own level (bear_rejection_level_raw upstream) rides as
    trigger_level, so the entry gets the standard chart-stop anchor -- a ladder entry is
    never stop-less."""
    g = arm.get("gate_override") or {}
    floor = g.get("score_ladder_floor")
    if floor is None:
        return None
    # SCOPE FENCE (caught by test_ladder_never_doubles_a_normal_enter's first RED): the lane
    # rescues SCORING-FAILED ticks only. If the shared signal's bear block PASSED and this
    # arm still produced no ENTER (sizing hole, gate_check, spot missing), that is a
    # different failure with its own remedies -- the ladder must not become a general-purpose
    # fallback that papers over sizing/config problems at min-size.
    if (signal.get("bear") or {}).get("passed") is True:
        return None
    ladder = signal.get("ladder")
    if not isinstance(ladder, Mapping):
        return None
    blk = ladder.get("bear")
    if not isinstance(blk, Mapping) or blk.get("available") is not True:
        return None
    try:
        floor_i = int(floor)
    except (TypeError, ValueError):
        return None
    score = int(blk.get("score") or 0)
    level = blk.get("level")
    if score < floor_i or not isinstance(level, (int, float)):
        return None
    if spot is None:
        return _hold(arm_id, "P", "SCORE_LADDER", "score-ladder: no spot in signal")
    strike = strike_selection.pick_strike(float(spot), float(equity), "P", PROBE_STRIKE_TIERS)
    try:
        qty = int(params.get("min_contracts", 3))
    except (TypeError, ValueError):
        qty = 3
    trigs = list(blk.get("triggers_raw") or [])
    quality = "ELITE" if any("confluence" in str(t).lower() for t in trigs) else "BASE"
    return EntryPlan(arm_id, "ENTER", "P", "BEARISH_REJECTION_RIDE_THE_RIBBON", strike, qty,
                     quality,
                     f"SCORE_LADDER floor={floor_i} score={score} "
                     f"blockers={blk.get('blockers')} trig={'+'.join(trigs)}",
                     strategy=strategies.RIBBON_RIDE.name,
                     exit_shape=_exit_shape_dict(strategies.RIBBON_RIDE, arm),
                     trigger_level=float(level))


# --- FLOOR-RESCUE eligibility (2026-08-03, L246-class ORDERING FIX) -----------------------
# THE DEFECT (EOD-2026-08-03-FULL-REVIEW.md section 4.2, "0 fires EVER vs 35 floor-blocks
# today"): plan_all's full-send precondition ("no ENTER in plans") runs at PLAN time, but the
# min_entry_premium floor that kills a doomed OTM plan runs LATER, in finalize(), once a real
# premium exists. On a cohort-vetoed tick whose score clears the scoring peak, the NORMAL lane
# produces an ENTER plan at the arm's own OTM tier; that plan dies at the $0.30 floor -- and
# the full-send lane, checked earlier, is shadowed by the corpse. This function is the PURE
# eligibility half of the fix; the caller (fleet_live.decide_arm) re-finalizes the rescue at
# its OWN strike's REAL premium, so every risk guard -- the floor included -- binds verbatim.
# The floor is re-asked at an ATM-class strike that can honestly clear it, never bypassed.
def floor_rescue_plan(
    arm: Mapping[str, Any],
    signal: Mapping[str, Any],
    equity: float,
    params: Mapping[str, Any],
    killed_plan: Optional[EntryPlan],
    decision: "Optional[ArmDecision]",
) -> Optional[EntryPlan]:
    """The full-send plan plan_all suppressed, iff the selected plan just died at the
    min_entry_premium floor. None in every other case -- the caller's verdict then stands.

    Eligibility (ALL required, fail-closed):
      * decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR" -- ONLY the floor un-shadows the
        rescue. Any other deny (NOT_FLAT/KILL_SWITCH/PDT/RISK_CAP/...) is a real risk
        refusal that would bind on the rescue identically; re-planning it would be noise.
      * the killed plan was a NORMAL-lane ENTER -- a floor-killed FULL_SEND/PROBE_ARM/
        SCORE_LADDER plan is terminal (no self-rescue loop; those lanes already price the
        ATM/PROBE table, so a floor kill there means the tick is genuinely untradeable).
      * the arm carries gate_override.full_send (risky-1 only at ship).
      * _full_send_plan finds an available, allowlisted, level-anchored block to rescue.
    Guard: test_floor_rescue_2026_08_03.py (RED-proofed against the pre-fix code)."""
    if decision is None or decision.risk_code != "SKIP_MIN_PREMIUM_FLOOR":
        return None
    if killed_plan is None or killed_plan.action != "ENTER":
        return None
    if str(killed_plan.reason or "").startswith(("FULL_SEND", "PROBE_ARM", "SCORE_LADDER")):
        return None
    if not _is_full_send(arm):
        return None
    rescue = _full_send_plan(arm, signal, equity, params, str(arm.get("id", "?")),
                             signal.get("spot"))
    if rescue is None or rescue.action != "ENTER":
        return None
    return rescue


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
    # ENTRY-1 PREMIUM FLOOR (2026-07-09 ship, STOP-B disposition) -- the SAME plan-time
    # admission as heartbeat_core._execute (setup/scripts/heartbeat_core.py, post-NO_PREMIUM),
    # applied HERE (not in plan_all/_plan_from_strategies, which build EntryPlans before any
    # live premium is resolved -- see D2 audit finding #3) so it fires at the exact point the
    # plan finally carries a resolved premium, for EVERY caller of finalize() -- fleet_live.py's
    # decide_arm() (the live path) and run_dry() (the dry-run/CLI/replay path) alike -- with no
    # duplicated logic in a second file. Every arm inherits the floor via its base SAFE/BOLD
    # params.json (params_patch never overrides it unless an arm explicitly sets its own).
    # NOT a risk_gate rule -- runs BEFORE check_order. 0/absent = OFF (byte-identical).
    # Guard: backtest/tests/test_min_entry_premium_floor.py. Revert: delete/zero the params key.
    try:
        _min_prem = float(params.get("min_entry_premium") or 0.0)
    except (TypeError, ValueError):
        _min_prem = 0.0
    if _min_prem > 0 and premium is not None:
        try:
            _prem_val = float(premium)
        except (TypeError, ValueError):
            _prem_val = None
        if _prem_val is not None and _prem_val < _min_prem:
            return ArmDecision(plan.arm_id, "HOLD", plan.side, plan.setup_name, plan.strike,
                               plan.qty, premium, plan.quality, "SKIP_MIN_PREMIUM_FLOOR",
                               f"premium {premium} < min_entry_premium floor {_min_prem}")
    # BLAST-RADIUS GUARD (2026-07-14): _base_params_for reads the SAME on-disk
    # automation/state/params.json / aggressive/params.json that core Safe/Bold
    # now opt into pdt_gate_mode="cash_settlement" (see those files + backtest/
    # lib/risk_gate.py CODE_SETTLEMENT). fleet_executor never computes/passes
    # settled_cash_available/same_day_entries_used -- if it inherited
    # cash_settlement mode from the shared file, check_order would fail-closed
    # to UNREADABLE_INPUT on EVERY fleet order (a strict regression from
    # today's near-always-ALLOW margin_pdt behavior, for arms outside this
    # task's scope). Force fleet arms onto the legacy path explicitly,
    # independent of whatever the shared file says, until/unless fleet gets
    # its own settlement-ledger wiring (queued, not part of this change).
    _fleet_params = dict(params)
    _fleet_params["pdt_gate_mode"] = "margin_pdt"
    # SHRINK-NOT-DENY (2026-08-03) -- see _shrink_qty_to_affordable's own module comment for
    # the full mechanism/evidence. Fires here, immediately before check_order, because this
    # is the first point in the call chain where plan.qty (phase A, tiered) and premium
    # (resolved by the caller just above) both exist. A no-op (qty unchanged) on every plan
    # that already fits, on every HOLD (returned above before this line), and whenever
    # max_affordable_qty reports a genuine deadlock (0) -- those still deny exactly as before.
    #
    # CHEAP-CONTRACT QTY BOOST (SHIP C, 2026-08-03, J verbatim: "if it's under point five o
    # for a contract, let's buy ten of them... let's just do that for risky three").
    # Params-driven, per-arm: fires ONLY when the arm's params_patch carries
    # cheap_contract_qty_boost = {"premium_below": <x>, "qty": <n>} AND the resolved premium
    # is strictly below the threshold AND the boost RAISES qty (never shrinks a larger plan).
    # Placement is deliberate: AFTER the min-premium floor (a floor-refused plan never gets
    # here) and BEFORE _shrink_qty_to_affordable + risk_gate.check_order, so Rule 6 remains
    # fully authoritative over the boosted size -- shrink can cut it back down and the risk
    # gate can still HOLD it. Absent key / malformed values = byte-identical no-op (C14:
    # guarded by a vary-and-assert in test_cheap_contract_qty_boost_2026_08_03.py).
    # TRADE-TO-LEARN single-arm A/B (risky-3 only via accounts.json params_patch); kill
    # criterion n>=10 boosted fills or 10 sessions, net<0 -> revert (delete the patch key).
    _boosted_qty = plan.qty
    _boost_cfg = params.get("cheap_contract_qty_boost")
    if isinstance(_boost_cfg, Mapping) and premium is not None:
        try:
            _b_below = float(_boost_cfg.get("premium_below"))
            _b_qty = int(_boost_cfg.get("qty"))
            _prem_f = float(premium)
        except (TypeError, ValueError):
            _b_below, _b_qty, _prem_f = None, None, None
        if (_b_below is not None and _b_qty is not None and _prem_f is not None
                and _prem_f < _b_below and _b_qty > _boosted_qty):
            _boosted_qty = _b_qty
    _qty, _shrink_note = _shrink_qty_to_affordable(_boosted_qty, equity, premium, _fleet_params)
    decision = risk_gate.check_order(
        account_label,
        equity=equity,
        start_of_day_equity=start_of_day_equity,
        proposed_qty=_qty,
        premium=premium,
        setup_name=plan.setup_name,
        current_position_status=current_position_status,
        day_trades_used_5d=day_trades_used_5d,
        kill_switch_tripped=kill_switch_tripped,
        prior_stops_today=prior_stops_today,
        params=_fleet_params,
    )
    if not decision.allowed:
        # BINDING-CONSTRAINT TELEMETRY (2026-07-30 incident) — see ArmDecision.binding and
        # risk_gate.explain_block. Distinguishes a sizing miss from a structural deadlock
        # (no legal qty at this premium). FAILS OPEN: telemetry never breaks a decision.
        try:
            _binding = risk_gate.explain_block(equity=equity, premium=premium,
                                               params=_fleet_params, proposed_qty=_qty)
        except Exception:  # noqa: BLE001
            _binding = None
        return ArmDecision(plan.arm_id, "HOLD", plan.side, plan.setup_name, plan.strike,
                           _qty, premium, plan.quality, decision.code,
                           f"risk_gate denied: {decision.reason}", binding=_binding)
    action = "ENTER_BEAR" if plan.side == "P" else "ENTER_BULL"
    _reason = plan.reason if not _shrink_note else f"{plan.reason}; {_shrink_note}"
    return ArmDecision(plan.arm_id, action, plan.side, plan.setup_name, plan.strike,
                       _qty, premium, plan.quality, "ALLOW", _reason,
                       trigger_level=plan.trigger_level)


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
    validate_accounts_exit_patches(accounts)  # fail loud on a bad exit_patch, before any tick
    out: list[tuple[ArmDecision, Optional[EntryPlan]]] = []
    for arm in accounts.get("arms", []):
        if arm.get("status") != "active":
            continue
        params = _params_for(arm)
        equity = float(arm.get("starting_equity") or 0.0)
        # MULTI-STRATEGY: every fired strategy gated+sized by this arm, ONE selected by
        # REGISTRY priority (one-position rule). Each plan carries its strategy's exit shape.
        # PROBE ARM: run_dry is a one-shot CLI/demo evaluation (no cross-tick state), so the
        # daily counter always reads 0 here -- the live per-tick count lives in fleet_live.py.
        plan = select_plan(plan_all(arm, signal, equity, params,
                                    probe_cfg=accounts.get("probe_arm")))
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
