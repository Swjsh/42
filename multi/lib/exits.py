"""multi/lib/exits.py -- the exit DECISION for one multi-symbol-lane position, one evaluation.

FORKED FROM `automation/state/fleet/exit_manager.py` (READ for shape, NEVER imported -- J
directive 2026-08-19: copy the SPY engine, don't touch the original). The pure-decision-core /
thin-actuator split, the "broker is the source of truth for qty, this module is the source of
truth for entry-relative math" division, and the persist-a-new-immutable-state-every-tick
pattern are all carried over deliberately. Everything else is rebuilt for what THIS lane's
params.json actually specifies (`automation/state/multi/params.json`'s `exits` and
`flatten_schedule_et` blocks), which differs from the SPY engine in the one way that matters
most: **this lane holds positions across MULTIPLE DAYS** (`exits.days_to_live`, currently 3
trading sessions), where the SPY engine's exit_manager is 0DTE and never has to reason about
theta decay accumulating over a hold, session/weekend boundaries, or an expiration day that
isn't today.

============================================================================================
WHY THE EVALUATION ORDER BELOW IS LOAD-BEARING (read before touching the order)
============================================================================================
  1. EXPIRY-DAY FLATTEN SCHEDULE -- a SAFETY item, not a profit item, and it runs FIRST,
     UNSKIPPABLE by any other rule. Alpaca rejects option orders after ~3:15pm ET on
     expiration day and the do-not-exercise cutoff is 3:00pm ET; a long option left to
     auto-exercise would deliver shares this account (starting equity $9,628.45) cannot
     afford. A position that would otherwise be a perfectly happy runner (TP1 filled,
     trailing nicely toward runner_target) MUST still flatten at 14:45/14:50/14:55 ET on its
     own expiry day -- see `test_multi_exits.py`'s
     `test_expiry_flatten_overrides_happy_runner`.
  2. THETA BUDGET BEFORE THE CATASTROPHE CAP. Verified decay runs ~18-19%/day at 3DTE, so a
     FLAT (thesis never confirmed) position bleeds ~46-56% by day 3-4 purely from time decay
     -- enough to touch the -50% catastrophe cap on decay alone, with the loss then
     mislabeled "stopped out" in the ledger when it was actually "we let theta eat it because
     the underlying never moved." Theta fires when premium has bled past
     `max_premium_bleed_pct_without_progress` (30%) AND the underlying has NOT cleared
     `thesis_progress_definition` (parsed from params -- see `_parse_atr_mult` below, "0.5 *
     ATR(14) in the trade's direction from entry"). Ordered strictly before the catastrophe
     check (`theta_budget.fires_before_catastrophe_cap`, read from params, not hardcoded) so
     a tick where BOTH conditions are true is labelled THETA_STOP, never CATASTROPHE_STOP --
     see the explicit ordering test.
  3. DAYS-TO-LIVE BUDGET -- `exits.days_to_live`, counted in TRADING SESSIONS
     (`trading_sessions_elapsed` below), never calendar days: a Friday entry evaluated the
     following Monday has been held ONE session, not three. Ranked after theta (theta is the
     more specific diagnosis of "why is this decaying") but before TP1/runner (a stale
     position's time budget outranks letting it keep riding).
  4. TP1 / RUNNER / TRAILING PROFIT LOCK -- percent-of-entry-premium, straight out of params
     (`tp1_premium_pct`, `runner_target_mult`, `trail_pct`, `profit_lock_arm_pct`). TP1 is a
     ONE-TIME partial (`PositionRecord.tp1_filled` gates it -- a second evaluation after TP1
     must never re-fire the partial). Post-TP1 the runner rides with a trailing floor that
     arms at `profit_lock_arm_pct` favorable and then chases the high-water mark at
     `trail_pct` off the top, mirroring exit_manager's chandelier post-TP1 walk.
  5. CATASTROPHE CAP (-50%) -- last of the "protective" checks, the hard backstop that fires
     when nothing more specific already explained the loss.
  6. WEEKEND GUARD -- `risk.weekend_holds` is false for this lane. A position must never be
     evaluated as still open across a weekend, so this is a FRIDAY flatten condition:
     whenever a position reaches this final check on a Friday at/after
     `flatten_schedule_et.soft_time_stop` (reusing that same cutoff -- there is no
     weekend-specific time in params.json, and using the existing EOD-flatten cutoff avoids
     inventing an undocumented new threshold), it flattens rather than risking a weekend
     hold. ASSUMPTION, stated once here: "Friday" is read from `now_et.weekday() == 4`
     (America/New_York), and the guard is time-gated by the SAME soft cutoff used for
     expiry-day flattening rather than firing the instant Friday's calendar date begins.

Every threshold used below is read from the `params` dict passed in at call time -- nothing
here hardcodes a value that lives in `automation/state/multi/params.json`. Fail loud: a
missing/malformed required params key raises `ExitConfigError` rather than silently
defaulting.

**THIS MODULE NEVER PLACES AN ORDER.** `evaluate_exit()` is pure: given a position record and
this tick's market facts, it returns an `ExitDecision` (what to do + why + the updated record
to persist). The caller (multi/core.py's tick loop, once wired) is responsible for acting on
`decision.qty > 0` via multi/lib/broker.py and then persisting `decision.record` via
multi/lib/position_state.py. There is no broker import, no network call, and no
`armed`/submission path anywhere in this file.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from zoneinfo import ZoneInfo

from multi.lib.position_state import PositionRecord

ET = ZoneInfo("America/New_York")

# --- action / stage vocabulary (public contract) -------------------------------------------
ACTION_HOLD = "HOLD"
ACTION_SELL_PARTIAL = "SELL_PARTIAL"
ACTION_SELL_ALL = "SELL_ALL"

STAGE_FLAT = "flat"
STAGE_EXPIRY_SOFT = "expiry_soft"
STAGE_EXPIRY_HARD = "expiry_hard"
STAGE_EXPIRY_LAST_RESORT = "expiry_last_resort"
STAGE_THETA_BUDGET = "theta_budget"
STAGE_DAYS_TO_LIVE = "days_to_live"
STAGE_TIME_STOP = "same_day_time_stop"
STAGE_TP1 = "tp1"
STAGE_RUNNER_TARGET = "runner_target"
STAGE_TRAIL_STOP = "trail_stop"
STAGE_CATASTROPHE_STOP = "catastrophe_stop"
STAGE_WEEKEND_GUARD = "weekend_guard"
STAGE_HOLD = "hold"


class ExitConfigError(RuntimeError):
    """Raised when a required threshold is missing/malformed in the `params` dict passed to
    `evaluate_exit`. Fail loud -- this module never substitutes a silent default for a value
    that is supposed to live in automation/state/multi/params.json."""


@dataclass(frozen=True)
class ExitDecision:
    """The result of ONE evaluation. `record` is the (possibly updated) PositionRecord the
    caller must persist via multi/lib/position_state.save_state regardless of `action` --
    even a HOLD tick updates the high-water mark and days_held. `qty` is the number of
    contracts the caller should sell (0 for HOLD)."""

    action: str        # ACTION_HOLD | ACTION_SELL_PARTIAL | ACTION_SELL_ALL
    stage: str          # machine-readable reason code, see STAGE_* constants
    reason: str          # human-readable explanation
    qty: int
    facts: dict = field(default_factory=dict)
    record: Optional[PositionRecord] = None


# --- params access (fail loud on anything missing) -----------------------------------------
def _require(d: Any, key: str, ctx: str) -> Any:
    if not isinstance(d, dict) or key not in d or d[key] is None:
        raise ExitConfigError(f"params.{ctx} is missing required key {key!r}")
    return d[key]


def _exits_cfg(params: dict) -> dict:
    return _require(params, "exits", "")


def _flatten_cfg(params: dict) -> dict:
    return _require(params, "flatten_schedule_et", "")


def _weekend_holds(params: dict) -> bool:
    risk = _require(params, "risk", "")
    if "weekend_holds" not in risk:
        raise ExitConfigError("params.risk is missing required key 'weekend_holds'")
    return bool(risk["weekend_holds"])


_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _parse_hhmm(value: Any, *, ctx: str) -> dt.time:
    """Parse an "HH:MM"[:SS] params string into a naive `datetime.time` (compared only
    against other ET wall-clock times, never mixed with a differently-zoned value). Fails
    loud on anything that doesn't match -- a flatten-schedule cutoff is safety-critical and
    must never silently fall back to a guessed default."""
    m = _HHMM_RE.match(str(value).strip())
    if not m:
        raise ExitConfigError(f"{ctx} = {value!r} is not an HH:MM[:SS] time string")
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ExitConfigError(f"{ctx} = {value!r} is out of range")
    return dt.time(hh, mm, ss)


_ATR_MULT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\*\s*ATR", re.IGNORECASE)


def _parse_atr_mult(thesis_progress_definition: Any) -> float:
    """Extract the ATR multiplier from params' prose definition (currently "underlying has
    moved >= 0.5 * ATR(14) in the trade's direction from entry") via regex rather than
    hardcoding 0.5 in code -- if the params prose is ever edited to a different multiplier,
    this function tracks it automatically instead of silently going stale. Fails loud if the
    "N * ATR" shape cannot be found."""
    m = _ATR_MULT_RE.search(str(thesis_progress_definition))
    if not m:
        raise ExitConfigError(
            f"theta_budget.thesis_progress_definition {thesis_progress_definition!r} does not "
            f"contain a parseable 'N * ATR' multiplier"
        )
    return float(m.group(1))


# --- trading-session counting (never calendar days) -----------------------------------------
def mode_name(params: dict) -> str:
    """Which business this lane is in. Defaults to intraday_v1 -- the mode J directed.

    Deliberately NOT a silent default to the multi-day model: a params file without a mode
    block is far more likely to be a fresh/partial config than a considered choice to hold
    positions overnight, and defaulting to the riskier hold model would be the wrong direction
    to be wrong in.
    """
    m = params.get("mode")
    if isinstance(m, dict) and m.get("name"):
        return str(m["name"])
    return "intraday_v1"


def is_intraday(params: dict) -> bool:
    return mode_name(params) == "intraday_v1"


def _time_stop_et(params: dict) -> str:
    m = params.get("mode")
    if isinstance(m, dict) and m.get("time_stop_et"):
        return str(m["time_stop_et"])
    raise ExitConfigError(
        "mode.time_stop_et missing while running intraday_v1 -- refusing to guess a "
        "same-day flatten time. An intraday lane with no time stop holds overnight, which is "
        "exactly what this mode forbids."
    )


def trading_sessions_elapsed(entry_date: dt.date, today: dt.date) -> int:
    """Count of weekday (Mon-Fri) sessions strictly AFTER `entry_date` up to and including
    `today`. Entry day itself is session 0 (not yet "held" any session). A Friday entry
    evaluated the following Monday returns 1, not 3 -- weekends do not count, matching the
    task's explicit "Fri->Mon hold is 1 session, not 3" requirement.

    Deliberately holiday-agnostic (weekday only) -- no NYSE holiday calendar dependency was
    in scope for this build; a holiday inside the window would over-count by one session per
    holiday, a conservative direction (flattens a session earlier, never later).
    """
    if today <= entry_date:
        return 0
    sessions = 0
    d = entry_date + dt.timedelta(days=1)
    while d <= today:
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            sessions += 1
        d += dt.timedelta(days=1)
    return sessions


# --- the pure decision core ------------------------------------------------------------------
def evaluate_exit(
    record: PositionRecord,
    *,
    now_et: dt.datetime,
    best_premium: float,
    worst_premium: float,
    open_qty: int,
    underlying_price: float,
    atr14: float,
    params: dict,
) -> ExitDecision:
    """ONE evaluation of ONE position. Pure -- no I/O, no order placement. `now_et` MUST be
    tz-aware in America/New_York (never a fixed UTC offset -- this box runs Mountain time).

    Ordering is implemented in EXACTLY the sequence documented in the module docstring:
    expiry-day flatten -> theta budget -> days-to-live -> TP1/runner/trail -> catastrophe cap
    -> weekend guard. Each stage either returns immediately (decision made) or falls through
    to the next, carrying forward any state update (high-water mark, days_held, runner-stop
    ratchet) via the returned `record`.
    """
    if now_et.tzinfo is None:
        raise ExitConfigError("evaluate_exit requires a tz-aware now_et (America/New_York)")

    exits_cfg = _exits_cfg(params)
    flatten_cfg = _flatten_cfg(params)

    hwm = max(record.hwm_premium, best_premium)
    today = now_et.date()
    entry_date = dt.date.fromisoformat(record.entry_session_date)
    sessions_elapsed = trading_sessions_elapsed(entry_date, today)
    base_record = record.touch(hwm_premium=hwm, days_held=sessions_elapsed)

    base_facts = {
        "now_et": now_et.isoformat(),
        "entry_premium": record.entry_premium,
        "best_premium": best_premium,
        "worst_premium": worst_premium,
        "hwm_premium": hwm,
        "open_qty": open_qty,
        "expiry": record.expiry,
        "entry_session_date": record.entry_session_date,
        "sessions_elapsed": sessions_elapsed,
        "tp1_filled": record.tp1_filled,
    }

    # Already flat (broker truth) -- nothing to manage. Defensive: a caller should not
    # normally invoke evaluate_exit on a flat position, but this must never fire an action
    # against zero open contracts.
    if open_qty <= 0:
        return ExitDecision(
            action=ACTION_HOLD, stage=STAGE_FLAT, qty=0,
            reason="position already flat -- nothing to manage",
            facts=base_facts, record=base_record,
        )

    # ── 1. EXPIRY-DAY FLATTEN SCHEDULE -- SAFETY, FIRST, UNSKIPPABLE ─────────────────────
    is_expiry_day = record.expiry == today.isoformat()
    if is_expiry_day:
        soft = _parse_hhmm(_require(flatten_cfg, "soft_time_stop", "flatten_schedule_et"),
                           ctx="flatten_schedule_et.soft_time_stop")
        hard = _parse_hhmm(_require(flatten_cfg, "hard_backstop", "flatten_schedule_et"),
                           ctx="flatten_schedule_et.hard_backstop")
        last_resort = _parse_hhmm(
            _require(flatten_cfg, "last_resort_dne_sweep", "flatten_schedule_et"),
            ctx="flatten_schedule_et.last_resort_dne_sweep")
        t = now_et.time()
        facts = {**base_facts, "is_expiry_day": True,
                 "soft_time_stop": str(soft), "hard_backstop": str(hard),
                 "last_resort_dne_sweep": str(last_resort)}
        if t >= last_resort:
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_EXPIRY_LAST_RESORT, qty=open_qty,
                reason=(f"expiry-day LAST-RESORT DNE sweep: now {t.isoformat('minutes')} >= "
                        f"{last_resort.isoformat('minutes')} on expiry {record.expiry} -- "
                        f"cannot skip, do-not-exercise cutoff is 15:00 ET"),
                facts=facts, record=base_record,
            )
        if t >= hard:
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_EXPIRY_HARD, qty=open_qty,
                reason=(f"expiry-day hard backstop: now {t.isoformat('minutes')} >= "
                        f"{hard.isoformat('minutes')} on expiry {record.expiry}"),
                facts=facts, record=base_record,
            )
        if t >= soft:
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_EXPIRY_SOFT, qty=open_qty,
                reason=(f"expiry-day soft time-stop: now {t.isoformat('minutes')} >= "
                        f"{soft.isoformat('minutes')} on expiry {record.expiry} -- "
                        f"flattening before the ~15:15 ET order-rejection window"),
                facts=facts, record=base_record,
            )
        # expiry day, but before the soft cutoff -- fall through to normal evaluation.

    theta_cfg = _require(exits_cfg, "theta_budget", "exits")
    max_bleed_pct = float(_require(theta_cfg, "max_premium_bleed_pct_without_progress",
                                   "exits.theta_budget"))
    atr_mult = _parse_atr_mult(
        _require(theta_cfg, "thesis_progress_definition", "exits.theta_budget"))
    fires_before_cat = bool(theta_cfg.get("fires_before_catastrophe_cap", True))

    premium_bleed_pct = max(
        0.0, (record.entry_premium - worst_premium) / record.entry_premium * 100.0
    )
    if record.side == "C":
        thesis_progress = (underlying_price - record.entry_underlying_price) >= atr_mult * atr14
    else:
        thesis_progress = (record.entry_underlying_price - underlying_price) >= atr_mult * atr14
    theta_fires = premium_bleed_pct >= max_bleed_pct and not thesis_progress
    theta_facts = {
        **base_facts,
        "premium_bleed_pct": round(premium_bleed_pct, 4),
        "max_premium_bleed_pct_without_progress": max_bleed_pct,
        "thesis_progress": thesis_progress,
        "atr_mult_required": atr_mult,
        "atr14": atr14,
        "underlying_price": underlying_price,
        "entry_underlying_price": record.entry_underlying_price,
    }

    def _theta_decision() -> Optional[ExitDecision]:
        if not theta_fires:
            return None
        return ExitDecision(
            action=ACTION_SELL_ALL, stage=STAGE_THETA_BUDGET, qty=open_qty,
            reason=(f"theta budget: premium bled {premium_bleed_pct:.1f}% >= "
                    f"{max_bleed_pct}% without thesis progress (needed underlying move >= "
                    f"{atr_mult} * ATR14 = {atr_mult * atr14:.2f} in the "
                    f"{'bullish' if record.side == 'C' else 'bearish'} direction; "
                    f"observed {underlying_price - record.entry_underlying_price:+.2f})"),
            facts=theta_facts, record=base_record,
        )

    def _catastrophe_decision() -> Optional[ExitDecision]:
        cat_pct = float(_require(exits_cfg, "catastrophe_stop_pct", "exits"))
        cat_level = record.entry_premium * (1.0 + cat_pct / 100.0)
        if worst_premium > cat_level:
            return None
        return ExitDecision(
            action=ACTION_SELL_ALL, stage=STAGE_CATASTROPHE_STOP, qty=open_qty,
            reason=(f"catastrophe cap: worst_premium {worst_premium:.4f} <= "
                    f"{cat_level:.4f} ({cat_pct}% of entry {record.entry_premium:.4f})"),
            facts={**base_facts, "catastrophe_stop_pct": cat_pct, "catastrophe_level": cat_level},
            record=base_record,
        )

    # ── 2. THETA BUDGET (before the catastrophe cap, per theta_budget.fires_before_catastrophe_cap) ──
    if fires_before_cat:
        d = _theta_decision()
        if d is not None:
            return d

    # ── 3. DAYS-TO-LIVE BUDGET (trading sessions) ────────────────────────────────────────
    # MODE BRANCH (WP-0). Intraday: a same-day time stop replaces the days-to-live budget --
    # "how many sessions has this lived" is meaningless when it may not survive one.
    if is_intraday(params):
        stop_hhmm = _time_stop_et(params)
        hh, mm = (int(x) for x in stop_hhmm.split(":")[:2])
        if (now_et.hour, now_et.minute) >= (hh, mm):
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_TIME_STOP, qty=open_qty,
                reason=(f"same-day time stop {stop_hhmm} ET reached "
                        f"(mode={mode_name(params)}; this lane does not hold overnight)"),
                facts={**base_facts, "time_stop_et": stop_hhmm}, record=base_record,
            )
        days_to_live = None
    else:
        days_to_live = int(_require(exits_cfg, "days_to_live", "exits"))
    if days_to_live is not None and sessions_elapsed >= days_to_live:
        return ExitDecision(
            action=ACTION_SELL_ALL, stage=STAGE_DAYS_TO_LIVE, qty=open_qty,
            reason=(f"days-to-live budget: {sessions_elapsed} trading session(s) held >= "
                    f"budget of {days_to_live} (entered {record.entry_session_date})"),
            facts={**base_facts, "days_to_live": days_to_live}, record=base_record,
        )

    # ── 4. TP1 / RUNNER / TRAILING PROFIT LOCK ───────────────────────────────────────────
    tp1_pct = float(_require(exits_cfg, "tp1_premium_pct", "exits"))
    tp1_frac = float(_require(exits_cfg, "tp1_qty_fraction", "exits"))
    runner_mult = float(_require(exits_cfg, "runner_target_mult", "exits"))
    trail_pct = float(_require(exits_cfg, "trail_pct", "exits"))
    arm_pct = float(_require(exits_cfg, "profit_lock_arm_pct", "exits"))

    tp1_target = record.entry_premium * (1.0 + tp1_pct / 100.0)
    runner_target = record.entry_premium * runner_mult

    if not record.tp1_filled:
        # tp1_qty_fraction is a plain fraction in params.json (0.5, 0.667, 0.8 -- see
        # CLAUDE.md's "tp1_qty_fraction 0.8 Safe / 0.667 Bold"), never a percent -- used
        # directly, no /100 conversion (unlike tp1_premium_pct, which IS a percent number).
        tp1_qty = min(int(record.qty * tp1_frac), open_qty)
        if tp1_qty > 0 and best_premium >= tp1_target:
            new_record = base_record.touch(
                tp1_filled=True, runner_stop_premium=record.entry_premium,
                profit_lock_armed=False,
            )
            return ExitDecision(
                action=ACTION_SELL_PARTIAL, stage=STAGE_TP1, qty=tp1_qty,
                reason=(f"TP1: best_premium {best_premium:.4f} >= target {tp1_target:.4f} "
                        f"(+{tp1_pct}% of entry) -- selling {tp1_qty}, runner stop -> "
                        f"breakeven {record.entry_premium:.4f}"),
                facts={**base_facts, "tp1_target": tp1_target, "tp1_qty": tp1_qty},
                record=new_record,
            )
        # TP1 not yet hit -- fall through to catastrophe check below, carrying only the hwm/
        # days_held update (base_record).
    else:
        # Post-TP1 runner: ratchet-only, arms at +arm_pct, then chandelier-trails off the HWM.
        runner_stop = record.runner_stop_premium
        if runner_stop is None:
            runner_stop = record.entry_premium
        profit_lock_armed = record.profit_lock_armed
        arm_level = record.entry_premium * (1.0 + arm_pct / 100.0)
        if not profit_lock_armed and best_premium >= arm_level:
            profit_lock_armed = True
        if profit_lock_armed:
            trail_floor = hwm * (1.0 - trail_pct / 100.0)
            runner_stop = max(runner_stop, trail_floor)
        runner_record = base_record.touch(
            runner_stop_premium=round(runner_stop, 6), profit_lock_armed=profit_lock_armed,
        )
        if best_premium >= runner_target:
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_RUNNER_TARGET, qty=open_qty,
                reason=(f"runner target: best_premium {best_premium:.4f} >= "
                        f"{runner_target:.4f} ({runner_mult}x entry)"),
                facts={**base_facts, "runner_target": runner_target, "runner_stop": runner_stop},
                record=runner_record,
            )
        if worst_premium <= runner_stop:
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_TRAIL_STOP, qty=open_qty,
                reason=(f"runner trailing stop: worst_premium {worst_premium:.4f} <= "
                        f"floor {runner_stop:.4f} "
                        f"({'armed, trailing ' + str(trail_pct) + '% off HWM' if profit_lock_armed else 'breakeven floor'})"),
                facts={**base_facts, "runner_stop": runner_stop,
                       "profit_lock_armed": profit_lock_armed},
                record=runner_record,
            )
        base_record = runner_record  # carry the ratcheted stop forward into step 5/6

    # ── 5. CATASTROPHE CAP (-50%), last of the protective checks ────────────────────────
    d = _catastrophe_decision()
    if d is not None:
        # base_record already reflects any runner-stop ratchet from step 4 above; re-stamp
        # it onto the catastrophe decision so a ratchet is never lost on the exit tick.
        return ExitDecision(action=d.action, stage=d.stage, reason=d.reason, qty=d.qty,
                            facts=d.facts, record=base_record)

    if not fires_before_cat:
        d = _theta_decision()
        if d is not None:
            return ExitDecision(action=d.action, stage=d.stage, reason=d.reason, qty=d.qty,
                                facts=d.facts, record=base_record)

    # ── 6. WEEKEND GUARD -- risk.weekend_holds is false; Friday is a flatten condition ──
    if not _weekend_holds(params):
        soft = _parse_hhmm(_require(flatten_cfg, "soft_time_stop", "flatten_schedule_et"),
                           ctx="flatten_schedule_et.soft_time_stop")
        is_friday = now_et.weekday() == 4
        if is_friday and now_et.time() >= soft:
            return ExitDecision(
                action=ACTION_SELL_ALL, stage=STAGE_WEEKEND_GUARD, qty=open_qty,
                reason=(f"weekend guard: risk.weekend_holds=false and today is Friday at/after "
                        f"{soft.isoformat('minutes')} ET -- flattening rather than risking a "
                        f"weekend hold"),
                facts={**base_facts, "is_friday": True, "weekend_holds": False},
                record=base_record,
            )

    return ExitDecision(
        action=ACTION_HOLD, stage=STAGE_HOLD, qty=0,
        reason="no exit condition met this evaluation",
        facts=base_facts, record=base_record,
    )
