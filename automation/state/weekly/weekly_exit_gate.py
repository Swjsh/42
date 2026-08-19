"""weekly_exit_gate -- the CALLER-SIDE wrapper that adds what exit_manager has no concept
of: multi-day theta budget, a days-to-live counter, the CORRECTED Friday-only flatten
schedule, and the paired shadow clock. This module NEVER forks exit_manager's validated
walk (`em.plan_exit_actions`) -- it wraps it, exactly like exit_actuator.py wraps it for
the live SPY book. It NEVER places, cancels, or modifies an order: every function here is
pure (no I/O) except `emit_shadow_row`, whose only side effect is an APPEND to the shadow
ledger (never a broker call).

THE THETA-TIMER BUG THIS EXISTS TO PREVENT (the highest-consequence correctness bug in
this workstream, see also the flatten-schedule section below for the highest-consequence
SAFETY bug). exit_manager's -50% catastrophe cap was validated on 0DTE SPY, where a
position that decays 50% intraday genuinely IS a stopped-out loss -- there is no "tomorrow"
for a same-day contract to recover in. A weekly position is different: params.json records
verified decay of -18/-19%/day at 3DTE, so a FLAT (thesis-neutral, price hasn't moved)
position decays ~46-56% by day 3-4 on THETA ALONE. Feeding that position through the
unmodified catastrophe cap would silently relabel ordinary decay as "premium_stop" /
"structure_stop" -- the cap becomes an accidental theta timer, and every exit reason in the
ledger lies about why the trade closed. The fix is ORDERING, not a bigger/smaller
threshold: theta budget MUST be evaluated, and MUST have the chance to fire, BEFORE
exit_manager's own catastrophe/structure check ever runs. See `plan_weekly_exit_actions`
for where that ordering is enforced.

THE FLATTEN-SCHEDULE BUG (the highest-consequence SAFETY bug this workstream found). The
frozen v1 design (program doc §4, pre-correction) said "close by Friday 15:30 ET". Verified
2026-08-18: Alpaca REJECTS option orders after 3:15pm ET on expiration day for every pilot
name except SPY/QQQ, and the do-not-exercise submission cutoff is 3:00pm ET. A 15:30 ET
close attempt would have missed BOTH cutoffs. A LONG OPTION LEFT TO AUTO-EXERCISE ON A
$5,000 ACCOUNT DELIVERS SHARES THE ACCOUNT CANNOT AFFORD (100 shares of GLD/QQQ/NVDA/TSLA
at even a modest strike is a multi-thousand-dollar obligation the account cannot margin).
params.json's flatten_schedule_et is the CORRECTED ladder: 14:45 ET soft time-stop, 14:50
ET hard backstop, 14:55 ET last-resort do-not-exercise sweep -- all comfortably ahead of
both real cutoffs. This module resolves and journals which rung has been crossed; it never
places the DNE submission itself (Stage A is shadow-only, see module docstring above).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, time as _time, timedelta
from pathlib import Path
from typing import Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet"))
import exit_manager as em  # noqa: E402
import weekly_strategies as ws  # noqa: E402

WEEKLY_DIR = Path(__file__).resolve().parent
SHADOW_LEDGER_PATH = WEEKLY_DIR / "shadow-ledger.jsonl"  # WEEKLY-OPTIONS-PROGRAM.md §9

# Weekly holds are multi-day BY DESIGN (the entire point of the lane, program doc §1). The
# SPY-style same-day 15:50 ET time_stop_et that exit_manager.plan_exit_actions defaults to
# must NEVER independently force-close a weekly position -- this lane's own Friday flatten
# schedule + days-to-live budget (below) are the ONLY time-based forced exits. Passing this
# sentinel to the delegated em.plan_exit_actions call guarantees its internal `now_et >=
# time_stop_et` check can never fire inside a trading session (23:59:59 > any RTH time).
_NEVER_TIME_STOP_SENTINEL = _time(23, 59, 59)

_FRIDAY_WEEKDAY = 4  # datetime.weekday(): Mon=0 .. Sun=6


# --- weekly-lane inputs exit_manager has no concept of -----------------------------------
@dataclass(frozen=True)
class WeeklyExitContext:
    """Everything this wrapper needs beyond em.ExitState/em.plan_exit_actions' own
    arguments. Immutable, built once per position at entry time (mirrors ExitState.
    from_entry's "resolved once, never flaps mid-trade" contract) except
    underlying_move_in_direction, which is naturally fresh every tick (the caller re-reads
    the live underlying each call, same as best_premium/worst_premium)."""
    entry_session_date: date
    days_to_live: int
    zone_width: float                              # entry-time zone width (ATR-derived; see
                                                     # params.json signal.ZONE_WIDTH_ATR_MULT)
    underlying_move_in_direction: float             # SIGNED by the CALLER so + == favorable
                                                     # to this trade's side (a put's move is
                                                     # -1 * (current - entry); this module
                                                     # never re-derives the sign itself)
    max_premium_bleed_pct_without_progress: float   # fraction, e.g. 0.30
    flatten_schedule_et: Mapping[str, str]          # params.json's flatten_schedule_et block

    @staticmethod
    def from_params(*, entry_session_date: date, zone_width: float,
                    underlying_move_in_direction: float,
                    params: Optional[dict] = None) -> "WeeklyExitContext":
        """Build straight from automation/state/weekly/params.json (re-read fresh, see
        weekly_strategies.load_params) so no caller hand-copies a number this file already
        owns."""
        p = params if params is not None else ws.load_params()
        exits = p.get("exits")
        if not isinstance(exits, dict):
            raise ValueError("weekly params.json missing/malformed 'exits' block")
        flatten = p.get("flatten_schedule_et")
        if not isinstance(flatten, dict):
            raise ValueError("weekly params.json missing/malformed 'flatten_schedule_et' block")
        tb = ws.theta_budget_config(p)
        return WeeklyExitContext(
            entry_session_date=entry_session_date,
            days_to_live=int(exits["days_to_live"]),
            zone_width=float(zone_width),
            underlying_move_in_direction=float(underlying_move_in_direction),
            max_premium_bleed_pct_without_progress=tb["max_premium_bleed_pct_without_progress"],
            flatten_schedule_et=flatten,
        )


# --- days-to-live -------------------------------------------------------------------------
def trading_sessions_held(entry_session_date: date, today_session_date: date) -> int:
    """Weekday-counted (Mon-Fri) trading sessions from entry through today, INCLUSIVE of the
    entry day itself (entry day == 1 session held). NOT holiday-aware: automation/state/
    calendar.json carries the real holiday list but is owned by a different workstream and
    can go stale silently; coupling this counter to its freshness would trade one silent-
    failure risk for another. Treating every calendar weekday as a session is the SAFE
    direction -- a real market holiday inside the window makes this OVERCOUNT sessions,
    which can only make days_to_live expire EARLIER than the true trading-session count. An
    early flatten is the safe failure mode here; a late one (missing the real cutoff) is
    not. NEEDS_J / future work: wire calendar.json's holiday list if exact session-day
    accounting becomes load-bearing (e.g. once the promotion gate is measuring session
    counts precisely rather than as a coarse budget).

    Raises on a weekend endpoint -- weekly-1 must never be evaluated on a non-trading day
    (weekend holds are FORBIDDEN, params.risk.weekend_holds=false; see
    plan_weekly_exit_actions' own weekend guard, which this mirrors for direct callers)."""
    if today_session_date < entry_session_date:
        raise ValueError(f"trading_sessions_held: today {today_session_date} precedes "
                         f"entry {entry_session_date}")
    if entry_session_date.weekday() >= 5 or today_session_date.weekday() >= 5:
        raise ValueError("trading_sessions_held: entry/today must both be weekdays -- "
                         "weekend holds are FORBIDDEN (params.risk.weekend_holds=false)")
    sessions = 0
    d = entry_session_date
    while d <= today_session_date:
        if d.weekday() < 5:
            sessions += 1
        d += timedelta(days=1)
    return sessions


# --- Friday-only flatten schedule (weekend_holds=false) -----------------------------------
@dataclass(frozen=True)
class FlattenSchedule:
    soft: _time
    hard: _time
    last_resort: _time


def _parse_hhmm(value: str) -> _time:
    parts = str(value).strip().split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    return _time(hh, mm)


def resolve_flatten_schedule(now_et: datetime,
                             flatten_schedule_et: Mapping[str, str]) -> Optional[FlattenSchedule]:
    """Weekday-vs-Friday time-stop selection (program doc §4 rule 5 + risk.weekend_holds=
    false: a weekly-1 position may NEVER carry a weekend gap). The CORRECTED 14:45/14:50/
    14:55 ET ladder from params.json's flatten_schedule_et applies ONLY on Friday -- see
    this module's docstring for the full 15:30-was-dangerous provenance. Any other weekday
    returns None: the days-to-live budget + theta budget + exit_manager's own
    premium/structure/TP1/runner walk are this lane's ONLY other exits Mon-Thu; multi-day
    holds are the entire point of the weekly lane, so there is deliberately no same-day
    forced close on a non-Friday session."""
    if now_et.weekday() != _FRIDAY_WEEKDAY:
        return None
    return FlattenSchedule(
        soft=_parse_hhmm(flatten_schedule_et["soft_time_stop"]),
        hard=_parse_hhmm(flatten_schedule_et["hard_backstop"]),
        last_resort=_parse_hhmm(flatten_schedule_et["last_resort_dne_sweep"]),
    )


def flatten_stage(now_et: datetime, schedule: FlattenSchedule) -> Optional[str]:
    """Which rung of the Friday ladder THIS tick has crossed, most-urgent first (a tick that
    somehow lands past 14:55 must never report the softer 14:45 label). None before 14:45
    ET (schedule.soft) -- the position is still inside its normal Friday session."""
    t = now_et.time()
    if t >= schedule.last_resort:
        return "flatten_last_resort_dne_sweep"
    if t >= schedule.hard:
        return "flatten_hard_backstop"
    if t >= schedule.soft:
        return "flatten_soft_time_stop"
    return None


# --- theta budget (must fire BEFORE exit_manager's catastrophe/structure cap) -------------
def thesis_has_progressed(underlying_move_in_direction: float, zone_width: float) -> bool:
    """params.json exits.theta_budget.thesis_progress_definition, implemented verbatim:
    "underlying has moved >= 0.5 * ZONE_WIDTH in the trade's direction from entry".
    `underlying_move_in_direction` must already be SIGNED by the caller so positive ==
    favorable to this trade's side -- this pure function has no notion of side."""
    return float(underlying_move_in_direction) >= 0.5 * float(zone_width)


def theta_budget_action(state: em.ExitState, *, worst_premium: float, open_qty: int,
                        underlying_move_in_direction: float, zone_width: float,
                        max_premium_bleed_pct_without_progress: float
                        ) -> Optional[em.ExitAction]:
    """LOAD-BEARING ORDERING (module docstring): the caller MUST consult this BEFORE
    exit_manager's catastrophe/structure cap on the same tick. Returns a SELL_ALL
    ExitAction (stage="theta_budget") once premium has bled
    >= max_premium_bleed_pct_without_progress of entry AND the underlying has NOT cleared
    the thesis-progress bar; None otherwise (the caller proceeds to exit_manager, whose own
    checks still protect an intrabar disaster that theta alone would not explain)."""
    if thesis_has_progressed(underlying_move_in_direction, zone_width):
        return None
    if state.entry_premium <= 0:
        raise ValueError("theta_budget_action: entry_premium must be positive")
    bleed = (state.entry_premium - float(worst_premium)) / state.entry_premium
    if bleed >= max_premium_bleed_pct_without_progress:
        reason = (f"theta_budget: premium bled {bleed:.1%} of entry with thesis "
                 f"unprogressed (underlying_move={underlying_move_in_direction:.4f} < "
                 f"0.5*zone_width={0.5 * zone_width:.4f})")
        return em.ExitAction("SELL_ALL", qty=open_qty, reason=reason, stage="theta_budget")
    return None


# --- overnight-trim multiplier: ONE-TIME entry-sizing interpretation ---------------------
def overnight_trim_qty(base_qty: int, overnight_size_multiplier: float,
                       held_overnight: bool) -> int:
    """ONE-TIME entry-sizing interpretation of params.risk.overnight_size_multiplier
    (0.5 at v1). Applies the multiplier ONCE, at entry, to the qty a position opens with
    when the entry decision anticipates carrying it overnight (Mon-Thu; a Friday entry
    would already be subject to the flatten schedule above the same session, so it is never
    "held overnight" in this sense). Does NOT re-apply the multiplier on subsequent nights.

    NEEDS_J (params.json's own label on risk._overnight_semantics, verbatim): whether this
    ONE-TIME cut or a NIGHTLY-COMPOUNDING halving (the multiplier re-applied every night
    held, i.e. base_qty * multiplier**nights_held) is the intended semantics is an OPEN
    DECISION -- params.json states this explicitly, it is not this function's call to make.
    This function implements the ONE-TIME interpretation ONLY, per this workstream's brief;
    the compounding alternative is NOT built here and would produce a materially smaller
    size on any hold beyond one night (mult**2=0.25, mult**3=0.125, ... vs this function's
    constant 0.5). Whichever J rules, this is a SIZING decision applied once, at entry,
    before any order exists -- it never resizes an already-open position, so it lives here
    (beside the exit gate's entry-time context) rather than inside any per-tick walk."""
    if base_qty <= 0:
        raise ValueError("overnight_trim_qty: base_qty must be positive")
    if not held_overnight:
        return int(base_qty)
    return max(int(base_qty * float(overnight_size_multiplier)), 0)


# --- the composed per-tick decision --------------------------------------------------------
def plan_weekly_exit_actions(state: em.ExitState, ctx: WeeklyExitContext, *,
                             best_premium: float, worst_premium: float, open_qty: int,
                             now_et: datetime, ribbon_flip_back: bool = False,
                             last_closed_5m_close: Optional[float] = None) -> em.ExitDecision:
    """ONE weekly-lane exit tick. Ordering is load-bearing (see module docstring for why):

      1. weekend guard -- weekly-1 must structurally never be evaluated on Sat/Sun.
      2. THETA BUDGET -- must precede #5's delegated catastrophe/structure cap.
      3. Friday-only flatten schedule (14:45/50/55 ET) -- risk.weekend_holds=false.
      4. days-to-live expiry.
      5. delegate to exit_manager.plan_exit_actions for everything else (catastrophe/
         structure stop, TP1, runner, ribbon-flip) -- NEVER forked, only wrapped. The
         delegated call is given a sentinel time_stop_et so exit_manager's own same-day
         15:50 SPY time-stop can never independently fire on a multi-day hold.

    Returns an em.ExitDecision -- the SAME type exit_manager itself returns, so any caller
    that already knows how to execute an ExitDecision (see exit_actuator.py) needs zero new
    plumbing. Never places an order: this function only returns/journals the intended
    action, exactly like exit_manager.plan_exit_actions' own pure-core contract.
    """
    if now_et.weekday() >= 5:
        raise ValueError(
            f"plan_weekly_exit_actions: called on {now_et.date()} (weekday="
            f"{now_et.weekday()}) -- weekend holds are FORBIDDEN "
            f"(params.risk.weekend_holds=false); a weekly-1 position must never still be "
            f"open past Friday's flatten schedule")
    if open_qty <= 0:
        return em.ExitDecision(state=state, actions=())

    if not state.theta_budget_hit:
        theta_action = theta_budget_action(
            state, worst_premium=worst_premium, open_qty=open_qty,
            underlying_move_in_direction=ctx.underlying_move_in_direction,
            zone_width=ctx.zone_width,
            max_premium_bleed_pct_without_progress=ctx.max_premium_bleed_pct_without_progress)
        if theta_action is not None:
            new_hwm = max(state.hwm_premium if state.hwm_premium is not None
                         else state.entry_premium, best_premium)
            new_state = replace(state, theta_budget_hit=True,
                                theta_budget_reason=theta_action.reason, hwm_premium=new_hwm)
            return em.ExitDecision(new_state, (theta_action,))

    schedule = resolve_flatten_schedule(now_et, ctx.flatten_schedule_et)
    if schedule is not None:
        stage = flatten_stage(now_et, schedule)
        if stage is not None:
            reason = f"{stage} @ {now_et.strftime('%H:%M')} ET Friday (no weekend holds)"
            return em.ExitDecision(
                state, (em.ExitAction("SELL_ALL", qty=open_qty, reason=reason, stage=stage),))

    sessions = trading_sessions_held(ctx.entry_session_date, now_et.date())
    if sessions >= ctx.days_to_live:
        reason = f"days_to_live expired ({sessions}/{ctx.days_to_live} sessions held)"
        return em.ExitDecision(
            state, (em.ExitAction("SELL_ALL", qty=open_qty, reason=reason,
                                  stage="days_to_live"),))

    return em.plan_exit_actions(
        state, best_premium=best_premium, worst_premium=worst_premium, open_qty=open_qty,
        now_et=now_et.time(), ribbon_flip_back=ribbon_flip_back,
        time_stop_et=_NEVER_TIME_STOP_SENTINEL, last_closed_5m_close=last_closed_5m_close)


# --- PAIRED SHADOW CLOCK -------------------------------------------------------------------
def _decision_to_dict(dec: em.ExitDecision) -> dict:
    return {
        "actions": [
            {"kind": a.kind, "qty": a.qty, "reason": a.reason, "stage": a.stage,
             "new_stop_premium": a.new_stop_premium}
            for a in dec.actions
        ],
        "closes_position": dec.closes_position,
        "tp1_filled": dec.state.tp1_filled,
        "runner_stop_premium": dec.state.runner_stop_premium,
    }


def paired_shadow_clock(state: em.ExitState, ctx: WeeklyExitContext, *,
                        best_premium: float, worst_premium: float, open_qty: int,
                        now_et: datetime, ribbon_flip_back: bool = False,
                        last_closed_5m_close: Optional[float] = None) -> dict:
    """For EVERY exit tick, computes BOTH:
      - "weekly": the REAL decision from plan_weekly_exit_actions (theta budget +
        days-to-live + Friday-only flatten schedule + exit_manager's own walk).
      - "naive_0dte": what an UNMODIFIED 0DTE exit_manager call would have decided on the
        IDENTICAL position this same tick -- em.plan_exit_actions with its own default
        same-day 15:50 ET time_stop_et, no theta budget, no days-to-live, no Friday-only
        gating. This is "what would have happened if this weekly position were simply run
        through the SPY exit machine unmodified" -- the naive-porting failure mode this
        whole workstream exists to correct (module docstring: same-day flatten of a
        multi-day thesis, or an unmodified -50% cap mislabeling theta decay as a stop-out).

    DECIDES NOTHING on the naive shape: it is computed and returned for the shadow ledger
    ONLY, never executed, never allowed to influence the "weekly" decision above (the two
    calls below are independent -- neither passes its result to the other). This is how the
    UNVALIDATED_STARTING_DEFAULT weekly shape earns validation later (program doc §8):
    without a same-tick naive comparison from the FIRST signal, there is no forward evidence
    that the weekly-specific corrections (theta budget, multi-day hold, Friday-only flatten)
    actually outperform naively porting the SPY machine as-is.

    Pure -- no I/O. Returns a plain dict shaped for JSON (see emit_shadow_row for the
    append-only writer)."""
    weekly_decision = plan_weekly_exit_actions(
        state, ctx, best_premium=best_premium, worst_premium=worst_premium,
        open_qty=open_qty, now_et=now_et, ribbon_flip_back=ribbon_flip_back,
        last_closed_5m_close=last_closed_5m_close)
    naive_decision = em.plan_exit_actions(
        state, best_premium=best_premium, worst_premium=worst_premium, open_qty=open_qty,
        now_et=now_et.time(), ribbon_flip_back=ribbon_flip_back,
        time_stop_et=em.TIME_STOP_ET, last_closed_5m_close=last_closed_5m_close)
    return {
        "ts_et": now_et.isoformat(),
        "symbol": state.symbol,
        "side": state.side,
        "entry_premium": state.entry_premium,
        "best_premium": best_premium,
        "worst_premium": worst_premium,
        "weekly": _decision_to_dict(weekly_decision),
        "naive_0dte": _decision_to_dict(naive_decision),
    }


def emit_shadow_row(row: dict, *, path: Optional[Path] = None) -> None:
    """Append ONE paired-shadow-clock row to the shadow ledger. Append-only ('a', no
    read-modify-write -- matches exit_actuator.py's own prune-log.jsonl race-free pattern)
    so concurrent weekly-lane ticks can never corrupt each other's rows.

    NO SILENT FALLBACK: a write failure is RE-RAISED, unlike some of this codebase's
    best-effort status notes (e.g. exit_actuator._note_flat_prune_status swallows OSError
    because a lost STATUS.md line is recoverable from prune-log.jsonl). This ledger has no
    such backstop -- it is program doc §8's ONLY evidence trail for the shadow -> paper
    promotion gate -- so a swallowed write error here would be exactly the "exits 0 while
    writing nothing" failure class (C7) this codebase has repeatedly been burned by.

    `path` defaults to the real shadow-ledger.jsonl; tests MUST pass an explicit tmp path
    so unit tests never write into the shared, gitignored, live ledger file."""
    target = path if path is not None else SHADOW_LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
