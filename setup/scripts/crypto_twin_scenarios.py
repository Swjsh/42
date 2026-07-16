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

  SIM (TWIN-B1.5, built 2026-07-14, WIRED into the production 5-min loop 2026-07-16 --
       Alpaca crypto cannot short, so these can never be forced via a REAL fill; simulates
       fills against the SAME live BTC quotes the LIVE lane reads, reusing
       backtest/futures/fill_sim_broker.py's gap-aware stop-fill machinery verbatim
       (imported, not forked) for the futures swing lane's own fill-sim approach.
       run_scenario_tick() below now calls run_sim_bear_tick() on EVERY tick, immediately
       after the LIVE row's own bookkeeping save -- see the "TWIN-B1.5-WIRE" comment there):
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
for _p in ("automation/state/fleet", "backtest/lib", "backtest"):
    _full = REPO / _p
    if str(_full) not in sys.path:
        sys.path.insert(0, str(_full))

import crypto_twin_core as ctc  # noqa: E402

# --- TWIN-B1.5 additions (2026-07-14): the SIM-tier bear lane's own dependencies. Every
# name below is REUSED verbatim (never forked) -- see the big docstring block ahead of
# run_sim_bear_tick() for exactly how each is used. crypto_twin_core.py / crypto_twin_
# broker.py (the LIVE entry path + broker code) are READ from below (fetch_closed_bars,
# get_crypto_quote_hilo -- both already read-only) and NEVER edited or monkey-patched by
# this module.
import crypto_twin_broker as broker  # noqa: E402
import crypto_twin_levels as tl  # noqa: E402
import crypto_twin_signal as sig  # noqa: E402
import exit_manager as em  # noqa: E402
from et_clock import et_now  # noqa: E402
from futures.fill_sim_broker import gap_aware_stop_fill  # noqa: E402

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

# TWIN-B1.5 (2026-07-14): the three SIM-tier bear branches, forced via crypto_twin_sim_
# bear's own lane below (never via ctc.run_tick/place_entry -- Alpaca crypto is
# long-only, so these positions are never real broker orders).
SIM_BEAR_BRANCHES: list[str] = [name for name, meta in BRANCH_REGISTRY.items() if meta["tier"] == "SIM"]

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

    # TWIN-B1.5-WIRE (2026-07-16, SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN.md ship-list #4):
    # every production tick ALSO ticks the SIM-tier bear lane, run strictly AFTER the LIVE
    # coverage save above so the two never race on the shared path-coverage.json (sequential
    # read-modify-write, single-threaded tick -- the SIM tick's own _load_coverage picks up
    # whatever the LIVE bookkeeping block just wrote, then only mutates its own 3 SIM branch
    # entries). This is the fix for the 43/43 ENTER_BEAR -> SKIP_NO_SHORT_CRYPTO waste (Alpaca
    # crypto is cash/long-only -- see ctc.run_tick's `action = "SKIP_NO_SHORT_CRYPTO"` branch):
    # instead of an organic bear verdict recording nothing but a skip, the SAME cadence now
    # also exercises run_sim_bear_tick's own independent branch scheduler (its own one-at-a-
    # time gate + daily cap, mirrors the LIVE bull branches being FORCED every tick regardless
    # of an organic trigger) against the SAME real BTC quotes -- never a real broker order, own
    # private ledger (sim-bear-positions.json / sim-bear-scenario-state.json / sim-bear-
    # journal.jsonl, never exit-state.json/journal.jsonl). Wrapped in its own try/except so a
    # bug in the SIM lane can NEVER turn an otherwise-successful LIVE row into a TICK_ERROR --
    # same "a hiccup here must never mask a successful tick" discipline as bookkeeping_error
    # above. Falsification rail (queue.md / the redesign doc's honesty rail): if the first 10
    # bear-SIM fills show >55% loss rate, pull this call -- ENTER_BEAR falls straight back to
    # SKIP_NO_SHORT_CRYPTO, current behavior, by deleting this block. Twin P&L (SIM or LIVE) is
    # mechanism-validation only, never SPY evidence, per standing project doctrine.
    sim_bear_result: Optional[dict] = None
    sim_bear_error: Optional[str] = None
    try:
        sim_bear_result = run_sim_bear_tick(cfg, now_utc=now, raw_bars=raw_bars)
    except Exception as e:  # noqa: BLE001 -- the SIM lane must never mask the LIVE row's own tick.
        sim_bear_error = f"{type(e).__name__}: {e}"

    return {"row": row, "scheduler_decision": scheduler_decision, "bookkeeping_error": bookkeeping_error,
            "sim_bear": sim_bear_result, "sim_bear_error": sim_bear_error}


# ==========================================================================================
# TWIN-B1.5 (2026-07-14): the SIM-tier BEAR lane -- ENTRY_TP1_TRAIL_BEAR,
# ENTRY_STRUCTURE_STOP_BEAR, ENTRY_CAT_CAP_BEAR.
#
# WHY THIS EXISTS: Alpaca crypto is cash/long-only (see crypto_twin_core.place_entry's own
# docstring) -- there is no real broker order that expresses a bear (P/put-mirrored)
# position, so the bear-side halves of the exit lifecycle (structure-stop close-ABOVE-
# trigger, the tight catastrophe cap, TP1->trail) can NEVER be forced through
# run_scenario_tick/ctc.run_tick the way the six LIVE branches are. Leaving them
# fixture-only (TWIN-PROGRAM.md's original "Long-only limitation" note) means the bear
# mechanism only gets unit-test coverage, never a rep against genuinely live, noisy BTC
# quotes. This section closes that gap the MIDDLE way (queue.md TWIN-B1.5): real live
# quotes in, REAL exit_manager.plan_exit_actions deciding, SIMULATED (never broker) fills
# out -- strictly better evidence than a fixture, honestly short of a real fill.
#
# WHAT IS REUSED, NEVER FORKED:
#   * exit_manager.ExitState / plan_exit_actions -- the IDENTICAL decision core every LIVE
#     branch runs (imported as `em` above). A bear position is built with side="P", exactly
#     like a real production put would be -- this module changes NO exit_manager code.
#   * crypto_twin_core.fetch_closed_bars -- the SAME closed-bar SEE stage the LIVE tick
#     uses (read-only; never places an order). crypto_twin_broker.get_crypto_quote_hilo --
#     the SAME live bid/ask read the LIVE manage_positions loop uses (read-only).
#   * backtest/futures/fill_sim_broker.gap_aware_stop_fill -- the exact pure gap-aware fill
#     convention named in the queue ticket ("gaps fill at the open beyond the stop, never
#     at the stop"), imported verbatim (never reimplemented) to price simulated stop fills.
#   * This module's OWN _load_coverage/_save_coverage/_mark_exercise_touch/
#     _mark_exercise_result/_extract_terminal_stage/_grade/_scenario_stale/_log_incident --
#     the path-coverage.json schema + grading rules are branch-name-agnostic already (see
#     each function's own signature), so the SIM lane reuses them UNCHANGED. A bear branch
#     grades exactly like a LIVE one: expected-stage match (or ribbon_flip/time_stop) ->
#     GREEN, anything else -> INCIDENT logged to the SAME incidents.jsonl via the UNCHANGED
#     _log_incident (its row shape is fixed -- ts_utc/branch/detail/decision_row_action/
#     price/exit_pass -- no separate literal "tier" field is added; a SIM-lane incident is
#     unambiguous from `branch` alone, since only the 3 SIM branches end in "_BEAR").
#
# THE ONE THING THAT MUST BE INVENTED: real option premium ALREADY moves the right way for
# a put (up when spot falls) -- that is ordinary option economics, not special-cased
# anywhere in exit_manager. Spot BTC has no such instrument, so this module manufactures a
# SYNTHETIC "mirror premium" that reproduces the same economics: mirror_premium() reflects
# the raw price around the entry price (2*entry - price), so it rises when spot falls and
# falls when spot rises -- exactly the shape exit_manager's best_premium/worst_premium
# checks already assume, regardless of side. This is the ONLY new decision-relevant
# arithmetic in this whole lane; everything else is composition of existing, tested pieces.
#
# NEVER BLENDED WITH LIVE: SIM bear positions are NEVER written to exit-state.json,
# decisions.jsonl, or journal.jsonl (the LIVE ledgers) -- they get their own private state
# (sim-bear-positions.json, sim-bear-scenario-state.json) and their own append-only journal
# (sim-bear-journal.jsonl), every row explicitly carrying "tier": "SIM". path-coverage.json
# IS shared (by design -- it is the one honest scoreboard for BOTH tiers, per
# TWIN-PROGRAM.md's schema), but every bear branch's `tier` field there already reads "SIM"
# (see BRANCH_REGISTRY) and _mark_exercise_result never touches that field.
#
# WIRED INTO THE 24/7 SCHEDULER 2026-07-16 (TWIN-B1.5-WIRE, SIX-ACCOUNT-DAILY-HYPOTHESIS-
# REDESIGN.md ship-list #4): run_scenario_tick() above now calls run_sim_bear_tick() on
# EVERY production tick (crypto_twin_health.py's run_tick_with_health -- the Gamma_CryptoTwin
# scheduled-task entrypoint -- calls run_scenario_tick() unchanged; no edit to
# crypto_twin_health.py or crypto_twin_core.py was needed, both remain untouched by this
# wiring per their own "thin wrapper, never edited" conventions). This lane is ALSO still
# directly reachable via `python -m crypto_twin_scenarios --sim-bear [--force-sim-branch ...]`
# for manual/verification runs -- both paths call the exact same run_sim_bear_tick().
# ==========================================================================================

SIM_BEAR_STATE_FILENAME = "sim-bear-scenario-state.json"     # private one-at-a-time slot bookkeeping
SIM_BEAR_POSITIONS_FILENAME = "sim-bear-positions.json"      # the ONE open SIM bear position, if any
SIM_BEAR_JOURNAL_FILENAME = "sim-bear-journal.jsonl"          # NEVER journal.jsonl -- see docstring above

MAX_SIM_BEAR_ENTRIES_PER_DAY = 3  # own cap, independent of MAX_SCENARIO_ENTRIES_PER_DAY --
                                   # one rep per bear branch per UTC day by default.


# --- the synthetic put-mirror (the one genuinely new piece of arithmetic) ---------------
def mirror_premium(entry_price: float, raw_price: float) -> float:
    """Synthetic PUT-mirror 'premium' for a spot instrument that has no real put: reflects
    `raw_price` around `entry_price` (2*entry - raw), so it RISES when raw_price FALLS
    (bear-favorable) and FALLS when raw_price RISES (bear-adverse) -- reproducing the same
    shape real option premium already has for a put (production never needs this function;
    a real put's premium already moves this way). Pure, symmetric: mirror_premium(e, e) ==
    e, i.e. a position's synthetic premium starts equal to its raw entry price, exactly
    mirroring how crypto_twin_core's bull entries set entry_premium=entry raw price."""
    return 2.0 * entry_price - raw_price


def mirror_price_from_premium(entry_price: float, premium: float) -> float:
    """Inverse of mirror_premium: recovers the raw BTC price a given synthetic premium
    level corresponds to. Used to translate an exit_manager premium-space stop/target level
    back into a raw price for gap-aware fill pricing / structure-level construction."""
    return 2.0 * entry_price - premium


def _bear_hilo_premiums(entry_price: float, ask: float, bid: float) -> tuple[float, float]:
    """(best_premium, worst_premium) for a bear (put-mirrored) position from a raw
    (ask, bid) quote pair -- crypto_twin_broker.get_crypto_quote_hilo's own return shape.
    DIRECTION-INVERTED from the bull convention (crypto_twin_core.manage_positions:
    best=ask, worst=bid): the LOWEST raw price (bid) is most favorable for a bear -> HIGHEST
    synthetic premium; the HIGHEST raw price (ask) is least favorable -> LOWEST synthetic
    premium."""
    best = mirror_premium(entry_price, bid)
    worst = mirror_premium(entry_price, ask)
    return best, worst


# --- per-branch SIM overrides (mirrors _build_scenario_cfg's philosophy: mechanism-
# forcing, never an edge claim -- these numbers are copied verbatim from the LIVE bull
# equivalents (ENTRY_TP1_TRAIL / ENTRY_STRUCTURE_STOP / ENTRY_CAT_CAP), since the mirror
# transform above makes the SAME percentages reachable-quickly in synthetic-premium space
# exactly like they are in real premium space) -------------------------------------------
def _build_sim_bear_shape(branch: str, base_exit_shape: dict) -> tuple[dict, Optional[float]]:
    """Returns (exit_shape, trigger_level_offset_pct) for a SIM bear branch. Scoped to a
    plain exit_shape dict (never a TwinConfig/dataclasses.replace) -- a SIM bear position
    is never built via ctc.place_entry (no real broker order exists to attach a TwinConfig
    to); see _place_sim_bear_entry for how the ExitState is constructed directly."""
    shape = dict(base_exit_shape)
    if branch == "ENTRY_TP1_TRAIL_BEAR":
        shape.update(stop_mode="premium", premium_stop_pct=-0.02, tp1_premium_pct=0.0015,
                    tp1_qty_fraction=0.667, profit_lock_mode="trailing", trail_pct=0.0015,
                    profit_lock_arm_pct=0.0005, runner_target_pct=0.20)
        return shape, None
    if branch == "ENTRY_STRUCTURE_STOP_BEAR":
        # trigger planted just BELOW spot (negative offset) -- bear's structure-stop fires
        # when a closed 5m bar's close > trigger_level (side="P" semantics, see
        # exit_manager._structure_stop_hit), so ordinary noise is very likely to close
        # above a trigger planted just under entry.
        shape.update(stop_mode="structure", premium_stop_pct=-0.02)
        return shape, -0.0004
    if branch == "ENTRY_CAT_CAP_BEAR":
        shape.update(stop_mode="premium", premium_stop_pct=-0.0025, tp1_premium_pct=0.20)
        return shape, None
    raise ValueError(f"crypto_twin_scenarios: no SIM bear overrides defined for branch {branch!r}")


# --- branch selection (mirrors _pick_next_branch, scoped to SIM_BEAR_BRANCHES + its own cap) --
def _pick_next_sim_branch(coverage: dict, *, today: str) -> Optional[str]:
    branches = coverage.get("branches", {})
    total_today = sum(int(branches.get(b, {}).get("count_today", 0)) for b in SIM_BEAR_BRANCHES)
    if total_today >= MAX_SIM_BEAR_ENTRIES_PER_DAY:
        return None
    candidates = [b for b in SIM_BEAR_BRANCHES if branches.get(b, {}).get("status") != "GREEN"]
    if not candidates:
        return None

    def _key(b: str):
        rec = branches.get(b, {})
        is_incident = 0 if rec.get("status") == "INCIDENT" else 1
        count = int(rec.get("count_today", 0))
        last = rec.get("last_exercised_utc") or ""
        return (is_incident, count, last)

    candidates.sort(key=_key)
    return candidates[0]


# --- sim-bear-positions.json (private -- NEVER exit-state.json) -------------------------
def _load_sim_bear_position(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) and doc else None


def _save_sim_bear_position(path: Path, position: Optional[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(position or {}, indent=2), encoding="utf-8")


# --- sim-bear-journal.jsonl (private -- NEVER journal.jsonl) ----------------------------
def _journal_sim_bear(journal_path: Path, event: str, **fields) -> None:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, "twin": True,
          "tier": "SIM", **fields}
    with journal_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# --- ribbon read (best-effort, reuses crypto_twin_signal.evaluate's own ribbon math -- NEVER
# reimplemented) for the ribbon-flip-back input plan_exit_actions expects ----------------
def _closed_ribbon_stack(bars: list, now: datetime) -> Optional[str]:
    """Best-effort ribbon stack (BULL/BEAR/MIXED) off the SAME closed bars this tick
    already fetched. Reuses crypto_twin_signal.evaluate purely for its `.ribbon_stack`
    field -- the SIM bear lane's entries are always FORCED (never organic), so evaluate's
    own ENTER/HOLD verdict is deliberately ignored here. None on any failure (fail-open --
    a missing ribbon read degrades to "never flip", never a spurious close)."""
    try:
        levels = tl.build_level_set(bars, now)
        return sig.evaluate(bars, levels).ribbon_stack
    except Exception:  # noqa: BLE001
        return None


# --- simulated fill pricing (the ONE place fill_sim_broker.gap_aware_stop_fill is used) --
def _bear_sim_fill_raw_price(action: em.ExitAction, *, entry_premium: float,
                             pre_state: em.ExitState, post_state: em.ExitState,
                             price: float, bar_open: Optional[float]) -> float:
    """Simulated fill price, in RAW BTC terms, for one exit_manager action on a SIM bear
    position. INFORMATIONAL/journal-only (never fed back into exit_manager's own state --
    the decision core already decided the action off the synthetic premium; this only
    answers 'what would the broker plausibly have filled at').

    A bear position mirrors a SHORT in raw-price terms (its stop is breached when raw price
    rises ABOVE the stop level) -- direction="short" for gap_aware_stop_fill's convention:
    'gaps fill at the open beyond the stop, never at the stop' (task requirement, verbatim
    from backtest/futures/fill_sim_broker.py, imported not reimplemented). TP1/runner-
    target favorable touches fill AT the level (fill_sim_broker's own target-leg
    convention -- no gap modeling on a favorable touch)."""
    stage = action.stage
    try:
        if stage == "structure_stop":
            stop_raw = pre_state.trigger_level if pre_state.trigger_level is not None else price
            return round(gap_aware_stop_fill("short", stop_raw, price, bar_open), 2)
        if stage == "premium_stop":
            stop_premium = (post_state.runner_stop_premium if post_state.runner_stop_premium is not None
                            else pre_state.runner_stop_premium)
            stop_raw = (mirror_price_from_premium(entry_premium, stop_premium)
                       if stop_premium is not None else price)
            return round(gap_aware_stop_fill("short", stop_raw, price, bar_open), 2)
        if stage == "tp1":
            level_premium = entry_premium * (1.0 + pre_state.tp1_premium_pct)
            return round(mirror_price_from_premium(entry_premium, level_premium), 2)
        if stage == "runner_target":
            level_premium = entry_premium * (1.0 + pre_state.runner_target_pct)
            return round(mirror_price_from_premium(entry_premium, level_premium), 2)
        if stage in ("trail", "be_stop"):
            stop_premium = (post_state.runner_stop_premium if post_state.runner_stop_premium is not None
                            else pre_state.runner_stop_premium)
            stop_raw = (mirror_price_from_premium(entry_premium, stop_premium)
                       if stop_premium is not None else price)
            return round(gap_aware_stop_fill("short", stop_raw, price, bar_open), 2)
    except (TypeError, ValueError):
        pass
    return round(price, 2)  # ribbon_flip / time_stop / any unmodeled stage -- market exit


# --- entry + management (the SIM analogs of place_entry / manage_positions -- NEVER call
# crypto_twin_broker's order-placing functions: place_crypto_order/market_sell_crypto/
# close_all_crypto are never imported by name here beyond get_crypto_quote_hilo, which is
# read-only) --------------------------------------------------------------------------
def _place_sim_bear_entry(cfg: ctc.TwinConfig, *, branch: str, now: datetime, price: float,
                          journal_path: Path) -> dict:
    shape, offset = _build_sim_bear_shape(branch, cfg.exit_shape)
    trigger_level = round(price * (1.0 + offset), 2) if offset is not None else None
    st = em.ExitState.from_entry(symbol=cfg.symbol, side="P", entry_premium=price,
                                 qty=cfg.units_per_entry, exit_shape=shape,
                                 strategy="crypto_twin_sim_bear", trigger_level=trigger_level,
                                 structure_stop_enabled=True)
    position = {"exit_state": st.to_dict(), "entered_at_utc": now.isoformat(), "branch": branch}
    _journal_sim_bear(journal_path, "SIM_PLACED", symbol=cfg.symbol, branch=branch, side="bear",
                      entry_price_raw=price, trigger_level=trigger_level, units=cfg.units_per_entry,
                      exit_shape=shape)
    return position


def _manage_sim_bear_position(cfg: ctc.TwinConfig, *, position: dict, branch: str, now: datetime,
                              price: float, bar_open: Optional[float], ribbon_stack: Optional[str],
                              journal_path: Path) -> tuple[list, str, Optional[dict]]:
    """Returns (exit_pass, action, new_position_or_None) -- exit_pass is shaped EXACTLY
    like manage_positions()'s own per-symbol result dict so _extract_terminal_stage/_grade
    (both branch-name-agnostic already) apply UNCHANGED."""
    st = em.ExitState.from_dict(position["exit_state"])
    entered_at = datetime.fromisoformat(position["entered_at_utc"])
    elapsed_h = (now - entered_at).total_seconds() / 3600.0

    if elapsed_h >= cfg.max_hold_hours:
        _journal_sim_bear(journal_path, "SIM_CLOSED", symbol=cfg.symbol, branch=branch,
                          reason="max_hold_flatten", elapsed_hours=round(elapsed_h, 2))
        return ([{"symbol": cfg.symbol, "action": "MAX_HOLD_FLATTEN",
                 "elapsed_hours": round(elapsed_h, 2)}], "MAX_HOLD_FLATTEN", None)

    hilo = broker.get_crypto_quote_hilo(cfg.symbol)
    if hilo is None:
        return [{"symbol": cfg.symbol, "action": "HOLD", "reason": "no_quote"}], "HOLD_NO_QUOTE", position

    ask, bid = hilo
    best, worst = _bear_hilo_premiums(st.entry_premium, ask, bid)
    flip = ribbon_stack == "BULL"  # side="P" flips on BULL ribbon -- mirrors
                                   # crypto_twin_core._make_ribbon_flip_fn's own rule
    now_et_time = et_now(now_utc=now).time()
    dec = em.plan_exit_actions(st, best_premium=best, worst_premium=worst,
                               open_qty=cfg.units_per_entry, now_et=now_et_time,
                               ribbon_flip_back=flip, last_closed_5m_close=price)

    executed = []
    for a in dec.actions:
        if a.kind in ("SELL_PARTIAL", "SELL_ALL"):
            fill_raw = _bear_sim_fill_raw_price(a, entry_premium=st.entry_premium, pre_state=st,
                                                post_state=dec.state, price=price, bar_open=bar_open)
            executed.append({"kind": a.kind, "units": a.qty, "stage": a.stage, "reason": a.reason,
                             "sim_fill_raw_price": fill_raw})
            _journal_sim_bear(journal_path, "SIM_MANAGED" if a.kind == "SELL_PARTIAL" else "SIM_CLOSED",
                              symbol=cfg.symbol, branch=branch, kind=a.kind, units=a.qty,
                              stage=a.stage, reason=a.reason, sim_fill_raw_price=fill_raw)
        elif a.kind == "RATCHET_STOP":
            executed.append({"kind": "RATCHET_STOP", "stage": a.stage,
                             "new_stop_premium": a.new_stop_premium, "reason": a.reason})

    if dec.closes_position:
        return [{"symbol": cfg.symbol, "actions": executed}], "SIM_CLOSED", None

    new_position = {"exit_state": dec.state.to_dict(), "entered_at_utc": position["entered_at_utc"],
                    "branch": branch}
    return [{"symbol": cfg.symbol, "actions": executed}], "SIM_MANAGED", new_position


# --- the SIM-wrapped tick (crypto_twin_scenarios' own new public entrypoint) -------------
def run_sim_bear_tick(cfg: ctc.TwinConfig = ctc.TwinConfig(), *,
                      now_utc: Optional[datetime] = None,
                      raw_bars: Optional[list[dict]] = None,
                      coverage_path: Optional[Path] = None,
                      sim_state_path: Optional[Path] = None,
                      position_path: Optional[Path] = None,
                      journal_path: Optional[Path] = None,
                      force_branch: Optional[str] = None) -> dict:
    """ONE tick of the SIM-tier bear lane (TWIN-B1.5). Mirrors run_scenario_tick's overall
    shape (scheduling decision -> real quote-driven tick -> bookkeeping) but NEVER touches
    a real broker order: entries/exits are SIMULATED against the SAME live quote feed the
    LIVE lane reads (crypto_twin_core.fetch_closed_bars / crypto_twin_broker.
    get_crypto_quote_hilo -- both read-only), decided by the REAL exit_manager core.

    `force_branch` (MANUAL/VERIFICATION ONLY, mirrors run_scenario_tick's own flag): skips
    _pick_next_sim_branch's selection and forces exactly this SIM branch. Still subject to
    the one-scenario-at-a-time gate.
    """
    now = now_utc or datetime.now(timezone.utc)
    coverage_path = coverage_path or (cfg.state_dir / "path-coverage.json")
    sim_state_path = sim_state_path or (cfg.state_dir / SIM_BEAR_STATE_FILENAME)
    position_path = position_path or (cfg.state_dir / SIM_BEAR_POSITIONS_FILENAME)
    journal_path = journal_path or (cfg.state_dir / SIM_BEAR_JOURNAL_FILENAME)

    scheduler_decision: dict = {"forced_branch": None, "reason_no_force": None}

    bars, bar_meta = ctc.fetch_closed_bars(cfg, now_utc=now, raw_bars=raw_bars)
    if not bars or bar_meta["verdict"] != "ok":
        scheduler_decision["reason_no_force"] = f"bar feed not ok: {bar_meta.get('verdict')}"
        return {"action": "HOLD_BAD_BARS", "bar_meta": bar_meta, "price": None, "exit_pass": [],
               "scheduler_decision": scheduler_decision, "bookkeeping_error": None}
    price = bars[-1].close
    bar_open = bars[-1].open

    scenario_state = _load_scenario_state(sim_state_path)
    position = _load_sim_bear_position(position_path)
    action = "HOLD"
    exit_pass: list = []
    branch: Optional[str] = None

    if scenario_state.get("active_branch") and position is not None:
        branch = scenario_state["active_branch"]
        scheduler_decision["reason_no_force"] = f"SIM scenario {branch} already in flight"
        ribbon_stack = _closed_ribbon_stack(bars, now)
        exit_pass, action, position = _manage_sim_bear_position(
            cfg, position=position, branch=branch, now=now, price=price, bar_open=bar_open,
            ribbon_stack=ribbon_stack, journal_path=journal_path)
    else:
        coverage_peek = _load_coverage(coverage_path, now_utc=now)
        branch = force_branch if force_branch is not None else \
            _pick_next_sim_branch(coverage_peek, today=now.strftime("%Y-%m-%d"))
        if branch is None:
            scheduler_decision["reason_no_force"] = "daily cap reached or all SIM branches green today"
        else:
            position = _place_sim_bear_entry(cfg, branch=branch, now=now, price=price,
                                             journal_path=journal_path)
            scenario_state = {"active_branch": branch, "started_utc": now.isoformat()}
            scheduler_decision["forced_branch"] = branch
            action = "SIM_ENTERED"

    bookkeeping_error: Optional[str] = None
    try:
        coverage = _load_coverage(coverage_path, now_utc=now)

        if scheduler_decision["forced_branch"] is not None:
            _save_scenario_state(sim_state_path, scenario_state)
            _save_sim_bear_position(position_path, position)
            coverage = _mark_exercise_touch(coverage, branch, now)
        elif action in ("SIM_MANAGED", "SIM_CLOSED", "MAX_HOLD_FLATTEN"):
            _save_sim_bear_position(position_path, position)

        active_branch = scenario_state.get("active_branch") if scenario_state else None
        if active_branch:
            closed, stage = _extract_terminal_stage(exit_pass, cfg.symbol)
            if closed:
                verdict_str, detail = _grade(active_branch, stage)
                coverage = _mark_exercise_result(coverage, active_branch, now, verdict_str, detail)
                _save_scenario_state(sim_state_path, {})
                _save_sim_bear_position(position_path, None)
                if verdict_str == "INCIDENT":
                    _log_incident(cfg, branch=active_branch, detail=detail,
                                  row={"action": action, "exit_pass": exit_pass, "tier": "SIM"})
            elif _scenario_stale(scenario_state, now):
                detail = (f"{active_branch}: SIM scenario timed out without closing "
                         f"(started {scenario_state.get('started_utc')})")
                coverage = _mark_exercise_result(coverage, active_branch, now, "INCIDENT", detail)
                _save_scenario_state(sim_state_path, {})
                _save_sim_bear_position(position_path, None)
                _log_incident(cfg, branch=active_branch, detail=detail,
                              row={"action": action, "exit_pass": exit_pass, "tier": "SIM"})

        _save_coverage(coverage_path, coverage)
    except Exception as e:  # noqa: BLE001 -- bookkeeping must never mask a successful tick.
        bookkeeping_error = f"{type(e).__name__}: {e}"

    return {"action": action, "price": price, "exit_pass": exit_pass,
           "scheduler_decision": scheduler_decision, "bookkeeping_error": bookkeeping_error}


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
    # TWIN-B1.5 (2026-07-14): purely additive -- omitting --sim-bear runs the exact
    # pre-existing LIVE scheduler tick above, byte-identical to before this flag existed.
    parser.add_argument("--sim-bear", action="store_true",
                        help="run the SIM-tier bear lane tick instead of the LIVE scheduler tick "
                             "(never places a broker order -- simulated fills only)")
    parser.add_argument("--force-sim-branch", choices=sorted(SIM_BEAR_BRANCHES), default=None,
                        help="MANUAL/VERIFICATION ONLY (--sim-bear mode): force this specific "
                             "SIM branch this tick (still subject to the one-at-a-time gate)")
    args = parser.parse_args(argv)

    for _ in range(max(1, args.ticks)):
        if args.sim_bear:
            sim_result = run_sim_bear_tick(force_branch=args.force_sim_branch)
            print(json.dumps(sim_result, indent=2, default=str))
            continue
        result = run_scenario_tick(live=args.live, force_branch=args.force_branch)
        print(json.dumps({
            "action": (result["row"] or {}).get("action"),
            "scenario": (result["row"] or {}).get("scenario"),
            "scheduler_decision": result["scheduler_decision"],
            "bookkeeping_error": result["bookkeeping_error"],
            # TWIN-B1.5-WIRE (2026-07-16): the SIM-tier bear lane now ticks every production
            # cycle alongside the LIVE row above -- surfaced here so a manual CLI run shows it.
            "sim_bear_action": (result.get("sim_bear") or {}).get("action"),
            "sim_bear_error": result.get("sim_bear_error"),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
