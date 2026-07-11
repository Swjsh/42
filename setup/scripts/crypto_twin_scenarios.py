"""crypto_twin_scenarios.py -- B1b: the SCENARIO SCHEDULER (the path-coverage battery).

markdown/planning/TWIN-PROGRAM.md value stream #1: "Force every exit lifecycle branch
through REAL paper fills daily ... A HOLD-all-day twin validates nothing -- coverage-
oriented by design, opposite of production selectivity." This module is that forcing
function. It does NOT reimplement SEE/DECIDE/gate/ACT/manage -- it is a thin scheduling
layer ON TOP of crypto_twin_core.run_tick() (REUSE, never fork, the same hard rail
crypto_twin_core.py's own docstring states): each 5-min tick, it decides whether to (a)
let the tick run organically (the default -- most ticks), or (b) FORCE one lifecycle
branch by handing run_tick a scenario-scoped TwinConfig (built via dataclasses.replace,
never mutating/persisting into the caller's cfg -- the param-freeze rule) plus
force_entry="bull" (Alpaca crypto is long-only, so every LIVE branch here is bull-side --
see BRANCH_REGISTRY's SIM-tier entries for the bear-side plan) and a scenario_tag.

BRANCH REGISTRY (the six LIVE branches this build forces/observes, plus three SIM-tier
placeholders queued for TWIN-B1.5 -- coordinator schema amendment 2026-07-11, "define
those three branch names now with status NOT_YET_COVERED / tier SIM so the scoreboard
renders the full picture honestly from day one"):

  LIVE (real Alpaca paper fills, forced by this scheduler):
    ENTRY_TP1_TRAIL        -- TP1 fires, runner rides, trailing floor exits the remainder.
    ENTRY_STRUCTURE_STOP   -- a closed 5m bar crosses a trigger_level planted just above spot.
    ENTRY_CAT_CAP          -- tight premium-mode fallback stop (no trigger_level).
    ENTRY_MAX_HOLD         -- max_hold_hours elapses before any exit_manager stage fires.
    RESTART_OPEN_POSITION  -- a FRESH TwinConfig/process still correctly finds + manages
                              an already-open position (every real 5-min tick already IS a
                              fresh pythonw process -- see crypto_twin_health.py's module
                              docstring -- so this branch's job is to make that property
                              EXPLICITLY, deterministically observed, not just incidental).
    ORGANIC_SIGNAL          -- NEVER forced: counted passively the moment a natural
                              (unforced) ribbon+level verdict places a real entry.

  SIM (queued, TWIN-B1.5, NOT exercised by this build -- Alpaca crypto cannot short, so
       these can never be forced via a REAL fill; B1.5 will simulate fills against live
       BTC quotes, mirroring backtest/futures/fill_sim_broker.py's own-fill-sim machinery
       for the futures swing lane -- that module is referenced here BY NAME ONLY, never
       imported, since building the SIM lane is explicitly out of THIS build's scope):
    ENTRY_TP1_TRAIL_BEAR, ENTRY_STRUCTURE_STOP_BEAR, ENTRY_CAT_CAP_BEAR

MECHANISM-FORCING, not an edge claim (same standing doctrine as crypto_twin_core.py's own
exit_shape): every override below is tuned so the branch is REACHABLE QUICKLY on live BTC
noise, never to make a trading claim -- see TWIN-PROGRAM.md's "Design decisions": "twin
signal/exit params change only for COVERAGE reasons, never chasing twin P&L."

GRADING: a branch is GREEN when its lifecycle closes via the EXPECTED exit stage, OR via
"ribbon_flip"/"time_stop" -- both are genuinely LIVE, independent exit conditions (ribbon
state is 100% external to this module's overrides; time_stop is a real wall-clock fact,
see crypto_twin_core's 2026-07-11 ET-conversion bugfix) that may legitimately preempt any
scenario's designed stage without that being a mechanism bug. Any OTHER mismatch is an
INCIDENT, logged loud to incidents.jsonl (the ROI ledger: "mechanism_bugs_caught").

STATE (all under automation/state/crypto-twin/, the twin's own namespace):
  path-coverage.json   -- the public scoreboard (per-branch tier/status/count_today/
                          last_exercised_utc/last_result), day-rollover on UTC date change.
  scenario-state.json  -- private scheduler bookkeeping: which branch (if any) is
                          currently in flight, since when.
  incidents.jsonl       -- append-only, one row per INCIDENT, full context.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace as _replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
for _p in ("automation/state/fleet", "backtest/lib"):
    _full = REPO / _p
    if str(_full) not in sys.path:
        sys.path.insert(0, str(_full))

import crypto_twin_core as ctc  # noqa: E402

# --- the branch registry (single source of truth for tier + expected stage) ------------
BRANCH_REGISTRY: dict[str, dict] = {
    # --- LIVE tier: built THIS session (B1b), forced via real Alpaca paper fills -------
    "ENTRY_TP1_TRAIL": {
        "tier": "LIVE", "expected_stage": "trail",
        "description": "TP1 fires, runner rides, trailing floor exits the remainder.",
    },
    "ENTRY_STRUCTURE_STOP": {
        "tier": "LIVE", "expected_stage": "structure_stop",
        "description": "Chart-level stop: a closed 5m bar crosses the planted trigger level.",
    },
    "ENTRY_CAT_CAP": {
        "tier": "LIVE", "expected_stage": "premium_stop",
        "description": "Tight premium-mode fallback stop (no trigger_level -> catastrophe-style cap).",
    },
    "ENTRY_MAX_HOLD": {
        "tier": "LIVE", "expected_stage": "MAX_HOLD_FLATTEN",
        "description": "max_hold_hours elapses before any exit_manager stage fires.",
    },
    "RESTART_OPEN_POSITION": {
        "tier": "LIVE", "expected_stage": "ANY",
        "description": "A fresh TwinConfig/process correctly rediscovers + manages an open position.",
    },
    "ORGANIC_SIGNAL": {
        "tier": "LIVE", "expected_stage": None,  # never forced -- counted passively at entry time
        "description": "A natural (unforced) ribbon+level verdict places a real entry.",
    },
    # --- SIM tier: QUEUED for TWIN-B1.5 (bear/P-side lifecycles). Alpaca crypto is
    #     long-only so these can never be forced via a REAL fill -- B1.5 will simulate
    #     fills against live BTC quotes via backtest/futures/fill_sim_broker.py's
    #     machinery (named here for the future build, never imported by this one).
    #     Coordinator schema amendment 2026-07-11: defined now so the scoreboard renders
    #     the full picture honestly from day one ("5/6 LIVE green, bear branches pending
    #     SIM lane").
    "ENTRY_TP1_TRAIL_BEAR": {
        "tier": "SIM", "expected_stage": "trail",
        "description": "BEAR-side mirror of ENTRY_TP1_TRAIL. QUEUED: TWIN-B1.5.",
    },
    "ENTRY_STRUCTURE_STOP_BEAR": {
        "tier": "SIM", "expected_stage": "structure_stop",
        "description": "BEAR-side mirror of ENTRY_STRUCTURE_STOP. QUEUED: TWIN-B1.5.",
    },
    "ENTRY_CAT_CAP_BEAR": {
        "tier": "SIM", "expected_stage": "premium_stop",
        "description": "BEAR-side mirror of ENTRY_CAT_CAP. QUEUED: TWIN-B1.5.",
    },
}

# The branches THIS scheduler ever forces (excludes ORGANIC_SIGNAL, which is passive-only,
# and every SIM-tier branch, which cannot be forced via a real long-only fill).
FORCED_LIVE_BRANCHES: list[str] = [
    name for name, meta in BRANCH_REGISTRY.items()
    if meta["tier"] == "LIVE" and name != "ORGANIC_SIGNAL"
]

MAX_SCENARIO_ENTRIES_PER_DAY = 6  # global cap across all FORCED_LIVE_BRANCHES, UTC-day
SCENARIO_STALE_HOURS = 3.0  # defensive backstop only -- every branch's OWN override
                            # resolves in minutes; this just frees the one-at-a-time slot
                            # if a position somehow never closes (the position itself
                            # stays protected by its real max_hold/catastrophe stop).

# Terminal stages that are genuinely LIVE, independent exit conditions -- may legitimately
# preempt ANY scenario's designed stage without that being a mechanism bug (see module
# docstring's GRADING section).
_ALWAYS_ACCEPTABLE_STAGES = frozenset({"ribbon_flip", "time_stop"})


# --- per-branch scenario-scoped overrides (param-freeze: dataclasses.replace only) -----
def _build_scenario_cfg(branch: str, base_cfg: ctc.TwinConfig) -> tuple[ctc.TwinConfig, Optional[float]]:
    """Returns (scenario_cfg, trigger_level_offset_pct) for a FORCED branch. Every
    override is SCENARIO-SCOPED -- built fresh via dataclasses.replace on base_cfg, never
    mutates or persists into the caller's TwinConfig (param-freeze rule, TWIN-PROGRAM.md
    "Design decisions"). Numbers are chosen to make the branch REACHABLE QUICKLY on live
    BTC noise -- mechanism-forcing, never a trading-edge claim (see module docstring)."""
    shape = dict(base_cfg.exit_shape)
    offset: Optional[float] = None

    if branch == "ENTRY_TP1_TRAIL":
        # tp1 tight (+0.15%) and reachable; runner_target far away (20%, effectively
        # unreachable in a short scenario window) so the runner is FORCED to resolve via
        # the tight trailing floor, not by rocketing to target. premium_stop loose (-2%)
        # so it doesn't preempt tp1/trail on ordinary noise.
        shape.update(stop_mode="premium", premium_stop_pct=-0.02, tp1_premium_pct=0.0015,
                    tp1_qty_fraction=0.667, profit_lock_mode="trailing", trail_pct=0.0015,
                    profit_lock_arm_pct=0.0005, runner_target_pct=0.20)
        cfg = _replace(base_cfg, exit_shape=shape)
    elif branch == "ENTRY_STRUCTURE_STOP":
        # trigger_level planted just ABOVE spot (offset computed by run_tick from ITS OWN
        # just-fetched price, see trigger_level_offset_pct) -- side "C" structure-stop
        # exits when a closed 5m bar's close < trigger_level, so the position is already
        # at/near that condition from the moment it's entered ("a close-through happens
        # soon", per TWIN-PROGRAM.md). premium_stop_pct is the structure-mode catastrophe
        # fallback (kept loose so the DEDICATED structure branch gets first crack).
        shape.update(stop_mode="structure", premium_stop_pct=-0.02)
        offset = 0.0004
        cfg = _replace(base_cfg, exit_shape=shape)
    elif branch == "ENTRY_CAT_CAP":
        # NO trigger_level -> from_entry demotes to premium mode (the "no level nearby"
        # fallback). premium_stop_pct tight (-0.25%) so ordinary BTC 5m noise crosses it
        # within a few ticks; tp1 set far away (20%) so TP1 cannot preempt the cap.
        shape.update(stop_mode="premium", premium_stop_pct=-0.0025, tp1_premium_pct=0.20)
        cfg = _replace(base_cfg, exit_shape=shape)
    elif branch == "ENTRY_MAX_HOLD":
        # tp1/premium_stop both far away so the ONLY realistic exit is the duration guard
        # itself, tightened to ~20 minutes (manage_positions' own guard, checked BEFORE
        # plan_exit_actions -- see crypto_twin_core.manage_positions).
        shape.update(stop_mode="premium", premium_stop_pct=-0.05, tp1_premium_pct=0.05)
        cfg = _replace(base_cfg, exit_shape=shape, max_hold_hours=20.0 / 60.0)
    elif branch == "RESTART_OPEN_POSITION":
        # Reuses ENTRY_CAT_CAP's tight, deterministic shape so the position resolves
        # quickly regardless -- the property under test is "does a freshly-constructed
        # TwinConfig/process still find + correctly manage this position" (see
        # run_scenario_tick's per-tick reload-from-disk design), not which stage fires.
        shape.update(stop_mode="premium", premium_stop_pct=-0.0025, tp1_premium_pct=0.20)
        cfg = _replace(base_cfg, exit_shape=shape)
    else:
        raise ValueError(f"crypto_twin_scenarios: no scenario overrides defined for branch {branch!r}")
    return cfg, offset


# --- path-coverage.json (the public scoreboard) -----------------------------------------
def _default_branch_record(meta: dict) -> dict:
    return {"tier": meta["tier"],
           "status": "NOT_YET_COVERED" if meta["tier"] == "SIM" else "PENDING",
           "count_today": 0, "last_exercised_utc": None, "last_result": None}


def _fresh_coverage(now_utc: datetime) -> dict:
    return {"date_utc": now_utc.strftime("%Y-%m-%d"),
           "branches": {name: _default_branch_record(meta) for name, meta in BRANCH_REGISTRY.items()}}


def _load_coverage(path: Path, *, now_utc: datetime) -> dict:
    """Load-or-roll today's path-coverage.json (mirrors crypto_twin_core.load_breaker's
    UTC-day rollover pattern). On a new UTC day, count_today resets to 0 for every branch
    but last_exercised_utc/last_result are RETAINED as history -- the scoreboard's memory
    of "did this branch EVER go green" should never be erased by a day boundary, only
    "did it run TODAY" (status resets to PENDING/NOT_YET_COVERED)."""
    today = now_utc.strftime("%Y-%m-%d")
    if not path.exists():
        return _fresh_coverage(now_utc)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _fresh_coverage(now_utc)
    if not isinstance(doc, dict) or doc.get("date_utc") != today:
        prev_branches = doc.get("branches", {}) if isinstance(doc, dict) else {}
        branches = {}
        for name, meta in BRANCH_REGISTRY.items():
            prev = prev_branches.get(name, {}) if isinstance(prev_branches.get(name), dict) else {}
            rec = _default_branch_record(meta)
            rec["last_exercised_utc"] = prev.get("last_exercised_utc")
            rec["last_result"] = prev.get("last_result")
            branches[name] = rec
        return {"date_utc": today, "branches": branches}
    branches = dict(doc.get("branches", {}))
    for name, meta in BRANCH_REGISTRY.items():
        if name not in branches or not isinstance(branches[name], dict):
            branches[name] = _default_branch_record(meta)
    return {"date_utc": today, "branches": branches}


def _save_coverage(path: Path, coverage: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(coverage, indent=2), encoding="utf-8")


def _mark_exercise_touch(coverage: dict, branch: str, now_utc: datetime) -> dict:
    """A scenario just STARTED (entry placed) -- IN_PROGRESS, not yet graded."""
    branches = dict(coverage.get("branches", {}))
    rec = dict(branches.get(branch, _default_branch_record(BRANCH_REGISTRY[branch])))
    rec["status"] = "IN_PROGRESS"
    rec["last_exercised_utc"] = now_utc.isoformat()
    branches[branch] = rec
    return {**coverage, "branches": branches}


def _mark_exercise_result(coverage: dict, branch: str, now_utc: datetime, verdict: str, detail: str) -> dict:
    """A scenario just COMPLETED (closed, or timed out) -- the graded, terminal update."""
    branches = dict(coverage.get("branches", {}))
    rec = dict(branches.get(branch, _default_branch_record(BRANCH_REGISTRY[branch])))
    rec["status"] = verdict
    rec["last_exercised_utc"] = now_utc.isoformat()
    rec["last_result"] = "GREEN" if verdict == "GREEN" else detail
    rec["count_today"] = int(rec.get("count_today", 0)) + 1
    branches[branch] = rec
    return {**coverage, "branches": branches}


# --- scenario-state.json (private scheduler bookkeeping) --------------------------------
def _load_scenario_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_scenario_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _scenario_stale(scenario_state: dict, now_utc: datetime) -> bool:
    started = scenario_state.get("started_utc")
    if not started:
        return False
    try:
        started_dt = datetime.fromisoformat(started)
    except (ValueError, TypeError):
        return True  # malformed timestamp -- treat as stale rather than wedge the slot forever
    return (now_utc - started_dt).total_seconds() / 3600.0 >= SCENARIO_STALE_HOURS


# --- branch selection --------------------------------------------------------------------
def _pick_next_branch(coverage: dict, *, today: str) -> Optional[str]:
    """Pick the next LIVE forced branch to exercise, or None when nothing should be
    forced this tick (daily cap reached, or everything's already GREEN today). Priority:
    INCIDENT-today branches first (retry the failure), then least-covered-today, then
    oldest-last_exercised_utc (never-exercised sorts first via the empty-string default).
    """
    branches = coverage.get("branches", {})
    total_today = sum(int(branches.get(b, {}).get("count_today", 0)) for b in FORCED_LIVE_BRANCHES)
    if total_today >= MAX_SCENARIO_ENTRIES_PER_DAY:
        return None
    candidates = [b for b in FORCED_LIVE_BRANCHES if branches.get(b, {}).get("status") != "GREEN"]
    if not candidates:
        return None  # everything's green today -- don't burn the spare rep needlessly

    def _key(b: str):
        rec = branches.get(b, {})
        is_incident = 0 if rec.get("status") == "INCIDENT" else 1
        count = int(rec.get("count_today", 0))
        last = rec.get("last_exercised_utc") or ""
        return (is_incident, count, last)

    candidates.sort(key=_key)
    return candidates[0]


# --- outcome extraction + grading --------------------------------------------------------
def _extract_terminal_stage(exit_pass: list, symbol: str) -> tuple[bool, Optional[str]]:
    """From a manage_positions() results list (as embedded in a decisions.jsonl row's
    exit_pass), determine whether `symbol` closed THIS tick and, if so, via which real
    stage/action. Returns (closed_this_tick, stage_or_action)."""
    for r in exit_pass or []:
        if not isinstance(r, dict) or r.get("symbol") != symbol:
            continue
        action = r.get("action")
        if action == "MAX_HOLD_FLATTEN":
            return True, "MAX_HOLD_FLATTEN"
        if action == "FLAT_PRUNED":
            return True, "FLAT_PRUNED_UNEXPECTED"
        for a in r.get("actions", []) or []:
            if isinstance(a, dict) and a.get("kind") == "SELL_ALL":
                return True, a.get("stage") or "UNKNOWN_STAGE"
        return False, None
    return False, None


def _grade(branch: str, stage: str) -> tuple[str, str]:
    expected = BRANCH_REGISTRY.get(branch, {}).get("expected_stage")
    if stage in _ALWAYS_ACCEPTABLE_STAGES:
        return "GREEN", (f"{branch}: closed via {stage} (independent live exit condition "
                         f"preempted the designed stage {expected!r} -- not a mechanism bug)")
    if expected == "ANY":
        if stage == "FLAT_PRUNED_UNEXPECTED":
            return "INCIDENT", f"{branch}: position vanished without a recognized exit stage"
        return "GREEN", f"{branch}: resumed + closed via {stage!r} after simulated restart"
    if stage == expected:
        return "GREEN", f"{branch}: closed via expected stage {stage!r}"
    return "INCIDENT", f"{branch}: expected stage {expected!r}, got {stage!r}"


# --- incidents.jsonl (the ROI ledger) -----------------------------------------------------
def _log_incident(cfg: ctc.TwinConfig, *, branch: str, detail: str, row: dict) -> None:
    p = cfg.state_dir / "incidents.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "detail": detail,
        "decision_row_action": row.get("action"),
        "price": row.get("price"),
        "exit_pass": row.get("exit_pass"),
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# --- the scenario-wrapped tick (crypto_twin_health.py's new entrypoint) -----------------
def run_scenario_tick(cfg: ctc.TwinConfig = ctc.TwinConfig(), *, live: bool = False,
                      now_utc: Optional[datetime] = None,
                      raw_bars: Optional[list[dict]] = None,
                      coverage_path: Optional[Path] = None,
                      scenario_state_path: Optional[Path] = None,
                      force_branch: Optional[str] = None) -> dict:
    """ONE tick, scenario-scheduler-wrapped. Decides whether to force a branch (network-
    free scheduling -- only local-disk reads: path-coverage.json, scenario-state.json,
    get_open_position, read_breaker_tripped), then ALWAYS calls crypto_twin_core.run_tick
    exactly once (organic or forced) -- the single network-touching call stays exactly
    where it always was, unwrapped, so a genuine run_tick failure propagates to the
    caller (crypto_twin_health.run_tick_with_health) exactly as before. Bookkeeping AFTER
    that call (coverage/scenario-state/incident writes) is wrapped separately so a
    bookkeeping hiccup can never mask an otherwise-successful tick or produce a duplicate
    error row.

    `raw_bars`/`now_utc` mirror run_tick's own injectable-clock/bars pattern -- fully
    testable without the network or real time.

    `force_branch` (MANUAL/VERIFICATION ONLY -- mirrors crypto_twin_core.run_tick's own
    force_entry test flag): when given, SKIPS _pick_next_branch's selection and forces
    exactly this branch. Still subject to every OTHER safety gate (one-scenario-at-a-
    time, breaker-tripped, organic-position-open, daily cap) -- it only overrides WHICH
    branch gets picked, never WHETHER forcing is safe right now. Reachable via this
    module's own `--force-branch` CLI flag; the scheduled-task caller
    (crypto_twin_health.py) never passes it, so production ticks are unaffected.
    """
    now = now_utc or datetime.now(timezone.utc)
    coverage_path = coverage_path or (cfg.state_dir / "path-coverage.json")
    scenario_state_path = scenario_state_path or (cfg.state_dir / "scenario-state.json")

    entry_cfg, force_entry, trigger_offset, scenario_tag = cfg, None, None, None
    scheduler_decision: dict = {"forced_branch": None, "reason_no_force": None}
    try:
        coverage = _load_coverage(coverage_path, now_utc=now)
        scenario_state = _load_scenario_state(scenario_state_path)
        existing_position = ctc.get_open_position(cfg)
        breaker_tripped = ctc.read_breaker_tripped(cfg)

        if scenario_state.get("active_branch"):
            active_branch_in_flight = scenario_state["active_branch"]
            # Re-apply the SAME scenario-scoped override on every MANAGING tick, not
            # just the entry tick -- exit_shape fields are frozen into ExitState at
            # entry (manage_positions reads the PERSISTED ExitState thereafter, so
            # those stay correct regardless of which cfg later ticks pass in), but
            # max_hold_hours is a TOP-LEVEL TwinConfig field manage_positions re-reads
            # from cfg EVERY tick -- without this, ENTRY_MAX_HOLD's tightened window
            # would only apply on tick 1 and the position would silently ride the
            # caller's real max_hold_hours (6h) instead, defeating the branch. A
            # corrupted/unknown branch name here raises inside _build_scenario_cfg,
            # caught by this block's own except below -> falls back to fully organic
            # (never gets stuck half-applying a bogus override).
            entry_cfg, _reapplied_offset = _build_scenario_cfg(active_branch_in_flight, cfg)
            scheduler_decision["reason_no_force"] = (
                f"scenario {active_branch_in_flight} already in flight")
        elif existing_position is not None:
            scheduler_decision["reason_no_force"] = "a position is already open"
        elif breaker_tripped:
            scheduler_decision["reason_no_force"] = "breaker tripped"
        else:
            branch = force_branch if force_branch is not None else \
                _pick_next_branch(coverage, today=now.strftime("%Y-%m-%d"))
            if branch is None:
                scheduler_decision["reason_no_force"] = "daily cap reached or all LIVE branches green today"
            else:
                entry_cfg, trigger_offset = _build_scenario_cfg(branch, cfg)
                force_entry = "bull"
                scenario_tag = branch
                scheduler_decision["forced_branch"] = branch
    except Exception as e:  # noqa: BLE001 -- a scheduling hiccup degrades to "run organically", never blocks the tick.
        entry_cfg, force_entry, trigger_offset, scenario_tag = cfg, None, None, None
        scheduler_decision = {"forced_branch": None,
                              "reason_no_force": f"scheduler error: {type(e).__name__}: {e}"}

    row = ctc.run_tick(entry_cfg, live=live, force_entry=force_entry, now_utc=now,
                       raw_bars=raw_bars, trigger_level_offset_pct=trigger_offset,
                       scenario_tag=scenario_tag)

    bookkeeping_error: Optional[str] = None
    try:
        coverage = _load_coverage(coverage_path, now_utc=now)
        scenario_state = _load_scenario_state(scenario_state_path)

        if scenario_tag is not None and row.get("action") == "ENTERED":
            scenario_state = {"active_branch": scenario_tag, "started_utc": now.isoformat()}
            _save_scenario_state(scenario_state_path, scenario_state)
            coverage = _mark_exercise_touch(coverage, scenario_tag, now)

        active_branch = scenario_state.get("active_branch")
        if active_branch:
            closed, stage = _extract_terminal_stage(row.get("exit_pass") or [], cfg.symbol)
            if closed:
                verdict_str, detail = _grade(active_branch, stage)
                coverage = _mark_exercise_result(coverage, active_branch, now, verdict_str, detail)
                _save_scenario_state(scenario_state_path, {})
                if verdict_str == "INCIDENT":
                    _log_incident(cfg, branch=active_branch, detail=detail, row=row)
            elif _scenario_stale(scenario_state, now):
                detail = (f"{active_branch}: scenario timed out without closing "
                         f"(started {scenario_state.get('started_utc')})")
                coverage = _mark_exercise_result(coverage, active_branch, now, "INCIDENT", detail)
                _save_scenario_state(scenario_state_path, {})
                _log_incident(cfg, branch=active_branch, detail=detail, row=row)

        if force_entry is None and row.get("action") == "ENTERED":
            coverage = _mark_exercise_touch(coverage, "ORGANIC_SIGNAL", now)
            coverage = _mark_exercise_result(coverage, "ORGANIC_SIGNAL", now, "GREEN",
                                             "ORGANIC_SIGNAL: natural signal-driven entry placed")

        _save_coverage(coverage_path, coverage)
    except Exception as e:  # noqa: BLE001 -- bookkeeping must never mask a successful tick.
        bookkeeping_error = f"{type(e).__name__}: {e}"

    return {"row": row, "scheduler_decision": scheduler_decision, "bookkeeping_error": bookkeeping_error}


# --- CLI ------------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Crypto Twin scenario-scheduled tick -- forces path-coverage branches on live BTC")
    parser.add_argument("--live", action="store_true", help="place real paper orders (default WATCH)")
    parser.add_argument("--ticks", type=int, default=1, help="number of ticks to run")
    parser.add_argument("--force-branch", choices=sorted(FORCED_LIVE_BRANCHES), default=None,
                        help="MANUAL/VERIFICATION ONLY: force this specific branch this tick "
                             "(still subject to every other safety gate)")
    args = parser.parse_args(argv)

    for _ in range(max(1, args.ticks)):
        result = run_scenario_tick(live=args.live, force_branch=args.force_branch)
        print(json.dumps({
            "action": (result["row"] or {}).get("action"),
            "scenario": (result["row"] or {}).get("scenario"),
            "scheduler_decision": result["scheduler_decision"],
            "bookkeeping_error": result["bookkeeping_error"],
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
