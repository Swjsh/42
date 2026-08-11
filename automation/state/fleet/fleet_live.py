"""fleet_live -- the live/WATCH fleet runner (one perception -> N policies).

Reads the heartbeat's `shared-signal.json` once per tick and fans it to every active
`fleet_rest` arm (safe-3 / risky-1 / risky-3). Each arm applies its FROZEN policy via
the pure, unit-tested core in fleet_executor.py (direction_lock, gate_override, sizing)
then the SAME risk_gate.check_order the live heartbeat + backtest use, against the arm's
REAL broker state (equity / flat / day-trades pulled live via fleet_broker).

TWO MODES (per-arm, default WATCH):
  * WATCH (default): computes + LOGS each arm's decision to {arm}/decisions.jsonl.
    Places NOTHING. This is "sniper eyes watching a plethora of strategies for all
    accounts" -- real per-arm decisions against the live signal, $0 risk.
  * LIVE: only when the master flag AND the arm's own `live:true` are both set AND the
    arm is broker-verified flat AND its kill-switch is not tripped. Places a bracket via
    fleet_broker.place_bracket (never-null stop, oto fallback).

safe-1 + bold-2 are NOT processed here (execution="mcp_heartbeat" -- they trade via
their own Gamma_Heartbeat* MCP path; placing them here too would double-fill).

The LIVE placement path is built but GATED OFF (master --live + per-arm live flags both
default false) until a controlled Monday-RTH test order validates it -- live option
order placement cannot be validated while the market is closed.

CLI:
    python fleet_live.py                 # WATCH all active fleet_rest arms (default)
    python fleet_live.py --signal PATH   # use a specific signal file (testing)
    python fleet_live.py --live          # master-enable LIVE (still needs per-arm live:true)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any

FLEET_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FLEET_DIR))
sys.path.insert(0, str(FLEET_DIR.parents[2] / "setup" / "scripts"))
import fleet_broker as fb  # noqa: E402
import fleet_executor as fx  # noqa: E402
import exit_actuator as ea  # noqa: E402  (the tick-managed scale-out engine)
from et_clock import ET_TZ as ET  # noqa: E402 — DST-aware ET (TZ-SYSTEMIC fix: was timezone(timedelta(hours=-4)))
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
DEFAULT_SIGNAL = FLEET_DIR / "shared-signal.json"
SIGNAL_MAX_AGE_SEC = 420  # 7 min -- a heartbeat tick is every 3 min

# 6-ACCOUNT UNIFICATION LEVER (2026-06-25, reversible) — which arms this runner processes.
# DEFAULT (False) = TODAY'S EXACT BEHAVIOR: only the 4 fleet_rest arms (safe-1/3, risky-1/3);
# safe-2/bold-2 (execution="mcp_heartbeat") are placed by their own heartbeat_core path, so
# processing them here too would DOUBLE-FILL. When FLEET_OWNS_ALL_6=True (the Path-B migration,
# paired with heartbeat_core GAMMA_CORE_PLACES=0 so the brain stops placing safe-2/bold-2),
# this runner ALSO processes the mcp_heartbeat arms — making the fleet the ONE executor for all
# 6 grid cells off the ONE brain. NEVER flip this without flipping GAMMA_CORE_PLACES=0 first
# (the no-double-fill invariant). Reversible: set back to False for today's split execution.
import os  # noqa: E402
FLEET_OWNS_ALL_6 = os.environ.get("GAMMA_FLEET_OWNS_ALL_6", "0") == "1"


def _arm_is_processable(arm: dict) -> bool:
    """Should fleet_live process this arm? Always the 4 fleet_rest arms; ALSO the 2
    mcp_heartbeat controls when FLEET_OWNS_ALL_6 (the unification migration). Excludes
    futures/pending arms (no SPY 0DTE option path here)."""
    if arm.get("status") != "active":
        return False
    ex = arm.get("execution")
    if ex == "fleet_rest":
        return True
    if ex == "mcp_heartbeat" and FLEET_OWNS_ALL_6:
        return True
    return False


def _now_et() -> datetime:
    return datetime.now(timezone.utc).astimezone(ET)


def _signal_age_sec(sig: dict, now: datetime) -> float | None:
    wa = sig.get("written_at")
    if not isinstance(wa, str):
        return None
    try:
        dt = datetime.fromisoformat(wa)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ET)
        return (now - dt).total_seconds()
    except ValueError:
        return None


def _load_signal(path: Path, now: datetime) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "no_signal_file"
    try:
        sig = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return None, f"signal_unreadable: {e}"
    age = _signal_age_sec(sig, now)
    if age is not None and age > SIGNAL_MAX_AGE_SEC:
        return sig, f"signal_stale_{int(age)}s"
    return sig, None


def _limit_pct_for(arm: dict) -> float:
    src = str(arm.get("config_source", "")) + str(arm.get("id", ""))
    return 0.30 if str(arm.get("id", "")).startswith("safe") and "bold" not in src else 0.50


# FLEET-PDT-PARITY (2026-08-06): the TRUE trailing-5-business-day day-trade count, computed
# from the broker's own FILL history exactly the way heartbeat_core.py:1909 already does for
# the core accounts (pdt_tracker.fetch_day_trades_used_5d). See the long comment at the call
# site in run() for WHY the fleet lane never got this and why enforcement is flag-gated.
#
# TTL memo: the fetch pulls ~10 calendar days of activities (measured 150-200 ms/arm on
# 2026-08-06) and run() walks every arm serially INSIDE the placement path, so an uncached
# call would add ~0.5 s of latency to each 60 s tick for a number that can only change when a
# round trip COMPLETES. 90 s is under one tick plus slack, so a completed round trip is
# reflected on the next tick at worst, while a retry/duplicate call within a tick is free.
_PDT_TTL_SEC = 90.0
_pdt_memo: dict[str, tuple[float, int]] = {}


def _true_day_trades_5d(arm_id: str, creds: dict, acct: dict,
                        now_mono: float | None = None) -> tuple[int, str]:
    """(count, source) for this arm. FAIL-OPEN in the SAME direction pdt_tracker documents:
    any failure degrades to the broker's own daytrade_count field, then 0 -- i.e. to exactly
    today's pre-fix value, so a fetch outage can never invent a new block. `source` is
    recorded in the ledger so a reader can always tell a real count from a fallback."""
    import time as _time  # noqa: PLC0415
    mono = now_mono if now_mono is not None else _time.monotonic()
    hit = _pdt_memo.get(arm_id)
    if hit and (mono - hit[0]) < _PDT_TTL_SEC:
        return hit[1], "pdt_tracker_cached"
    try:
        import sys as _sys  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415
        _scripts = str(_Path(__file__).resolve().parents[2] / "setup" / "scripts")
        if _scripts not in _sys.path:
            _sys.path.insert(0, _scripts)
        import pdt_tracker as _pdt  # noqa: PLC0415
        n = int(_pdt.fetch_day_trades_used_5d(creds))
    except Exception:  # noqa: BLE001 -- visibility must never break the tick (C7 fail-open)
        return int((acct or {}).get("daytrade_count") or 0), "broker_field_fallback"
    _pdt_memo[arm_id] = (mono, n)
    return n, "pdt_tracker"


def _load_or_arm_breaker(arm_id: str, equity: float, now: datetime, limit_pct: float) -> dict:
    """Per-arm daily kill-switch. Armed from live equity at first run each day."""
    d = FLEET_DIR / arm_id
    d.mkdir(exist_ok=True)
    path = d / "circuit-breaker.json"
    today = now.strftime("%Y-%m-%d")
    if path.exists():
        try:
            b = json.loads(path.read_text(encoding="utf-8"))
            if str(b.get("last_reset", ""))[:10] == today:
                return b
        except (json.JSONDecodeError, OSError):
            pass
    # arm fresh for today
    b = {
        "tripped": False, "tripped_at": None, "tripped_reason": None,
        "starting_equity_today": round(equity, 2), "current_equity": round(equity, 2),
        "daily_loss_limit_pct": limit_pct, "max_drawdown_today_pct": 0.0,
        "last_reset": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "_note": f"fleet arm {arm_id} daily kill-switch (-{int(limit_pct*100)}% of SoD).",
    }
    path.write_text(json.dumps(b, indent=2), encoding="utf-8")
    return b


# --- PROBE ARM daily-cap counter (2026-07-10 ship) ----------------------------------------
# Per-day count of ALLOWED probe entries (risk_gate-cleared, PROBE_ARM-tagged), persisted the
# SAME way as _load_or_arm_breaker's daily kill-switch (last_reset date match -> fresh 0 on
# rollover). fleet_executor.plan_all/_probe_plan are pure (no I/O) -- the count is read here,
# passed in as probe_entries_today, and incremented here (via _record_probe_entry) ONLY after
# finalize() actually ALLOWs a PROBE_ARM-tagged ENTER, never on a HOLD/deny.
def _load_probe_count(arm_id: str, now: datetime) -> dict:
    d = FLEET_DIR / arm_id
    d.mkdir(exist_ok=True)
    path = d / "probe-count.json"
    today = now.strftime("%Y-%m-%d")
    if path.exists():
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
            if str(c.get("date", "")) == today:
                return c
        except (json.JSONDecodeError, OSError):
            pass
    return {"date": today, "count": 0}


def _record_probe_entry(arm_id: str, now: datetime) -> None:
    c = _load_probe_count(arm_id, now)
    c["count"] = int(c.get("count", 0)) + 1
    c["last_entry_et"] = now.isoformat()
    path = FLEET_DIR / arm_id / "probe-count.json"
    path.write_text(json.dumps(c, indent=2), encoding="utf-8")


def _load_prior_stops(arm_id: str, now: datetime) -> list[str]:
    path = FLEET_DIR / arm_id / "first-entry-lock.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    today = now.strftime("%Y-%m-%d")
    return [r.get("setup_name") for r in data
            if str(r.get("exited_at_et", ""))[:10] == today
            and r.get("exit_reason") in ("premium_stop", "chart_stop", "ribbon_flip_back", "stop_market")]


# --- ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02) -------------------------------------------
# Closes the gap documented in analysis/deep-research/FLEET-RACE-AND-LATENCY-2026-08-01.md
# section 3: the ONLY guard against a double-entry was run()'s POSITIONS-only `flat` check
# (fb.is_flat_spy_options), which cannot see a still-WORKING order, and _place_live's old
# stale-order cancel loop placed a fresh order unconditionally even when its own cancel
# raced a fill at the broker. This is the LOCAL half of the fix (a short-TTL per-(arm,
# symbol) claim file, consulted inline in _place_live below); the AUTHORITATIVE half (a
# live broker open-orders query, fail-CLOSED on any query error) is
# fleet_broker.open_buy_orders_checked / symbol_position_qty_checked. Deliberately mirrors
# exit_actuator.same_bar_cooldown_active's claim-file shape/contract (same per-arm-file
# pattern, same fail-OPEN-on-read-error contract -- a claim-file problem must never itself
# block a legitimate entry; the broker query is what fails CLOSED). Guard:
# test_entry_idempotency_guard.py.
# FLEET-SAME-BAR-COOLDOWN (2026-08-06) -- core-parity wiring of the 2026-07-20
# EXTRA-SIGNAL-CHURN-COOLDOWN, NOT a new edge. The mechanism (exit_actuator.
# same_bar_cooldown_active / record_entry_bar, per-(arm, setup) "last trigger-bar
# attempted" ledger in <arm>/extra-setup-cooldown.json) has protected the CORE extra-setup
# lane since 2026-07-20; the fleet placement path never consulted it (LEVER-ENTRY-COUNT-
# 2026-08-06.md section 2d measured the gap: Wed 08-05 +$202, Tue 08-04 +$144, 0/26 days
# harmed, blocks exactly 3 churn re-entries week-wide while preserving the 09:57 +$524
# rescue whose trigger bar was genuinely new). Rule: the closed 5m trigger bar (signal
# "trigger_bar_et", threaded from core-decisions by build_shared_signal) must ADVANCE
# before the SAME (arm, setup) re-enters -- no numeric knob exists, structural.
# Frozen forward prereg (committed BEFORE this wiring, git-provable):
# analysis/recommendations/fleet-same-bar-cooldown-prereg-2026-08-06.json (55880b45).
# FAIL-OPEN: missing/None trigger_bar_et, unreadable cooldown file, or ANY consult
# exception must never block an entry; a stamp failure never aborts a placed entry.
# Guard: test_fleet_same_bar_cooldown.py.
#
# *** DISARMED AT SHIP (2026-08-06 evening) -- DO-NOT-ARM verdict. *** The ship-gate
# replay through the PRODUCTION trigger-bar identity (each fleet row's own core_tick_id
# -> core-decisions trigger_bar_et, i.e. exactly what this consult keys on live) FAILED
# to reproduce the study: on Wed 08-05 every re-entry's trigger bar ADVANCED
# (09:58->09:50, 10:06->09:55, 10:10->10:00, 10:14->10:05, 10:18->10:10) so it blocks
# NOTHING (study claimed +$202); on Tue 08-04 the only same-bar pair is risky-3
# 09:54/09:57 (both bar 09:45) -- so it blocks the 09:57 763C leg, which is the +$524
# REAL-FILLS WINNER the study said it preserves (EOD-2026-08-04-ENGINE.md:464). The
# study keyed entries to WALL-CLOCK last-closed bars; the engine's trigger_bar_et lags
# tick-phase-dependently (bar-cache append + trig_idx=n-2), so bar-equality relations
# do not transfer (L251 class). Net on the motivating tape: -$524, and the prereg's own
# kill criterion (blocks a winner > +$150) is met on day-0 replay. Outcome record:
# analysis/recommendations/fleet-same-bar-cooldown-OUTCOME-2026-08-06.json.
# ARM (only after an honest forward re-measure keyed to trigger_bar_et clears the
# prereg gates): FLEET_SAME_BAR_COOLDOWN = True.
FLEET_SAME_BAR_COOLDOWN = False

ENTRY_CLAIM_TTL_SEC = 180  # >= one full tick at today's 3-min cadence, several at the 1-min
                           # candidate cadence; real fills resolve in ~0.1-0.2s (measured,
                           # see the 2026-08-01 latency instrument) so this only needs to
                           # bridge broker propagation lag, never a legitimate re-entry
                           # minutes later (which requires an exit + a fresh trigger bar).


def _claim_path(arm_id: str) -> Path:
    d = FLEET_DIR / arm_id
    d.mkdir(exist_ok=True)
    return d / "entry-claim.json"


def _claim_active(arm_id: str, symbol: str, now: datetime,
                  ttl_sec: float = ENTRY_CLAIM_TTL_SEC) -> bool:
    """True iff an unexpired entry claim already exists for this EXACT (arm, symbol) --
    the FAST, local, broker-independent half of the idempotency guard (covers two ticks
    landing inside one short signal window without waiting on broker propagation). Fail-
    OPEN (False) on any missing/corrupt file or unparseable timestamp -- a claim-file
    problem must never itself block a legitimate entry; the broker-side query in
    _place_live is the fail-CLOSED authority."""
    path = _claim_path(arm_id)
    if not path.exists():
        return False
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        if str(rec.get("symbol")) != symbol:
            return False
        claimed_at = datetime.fromisoformat(str(rec["claimed_at_et"]))
        if claimed_at.tzinfo is None:
            claimed_at = claimed_at.replace(tzinfo=ET)
        age = (now - claimed_at).total_seconds()
        return 0 <= age < ttl_sec
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return False


def _write_claim(arm_id: str, symbol: str, now: datetime) -> None:
    """Reserve the entry claim BEFORE the broker POST. Best-effort/fail-safe: a write
    error here must never abort an otherwise-clean entry -- the broker-side open-orders
    check on the NEXT tick remains the backstop if this local marker is lost."""
    try:
        _claim_path(arm_id).write_text(
            json.dumps({"symbol": symbol, "claimed_at_et": now.isoformat()}),
            encoding="utf-8")
    except OSError:
        pass


_select_plan = fx.select_plan  # canonical one-position selection (REGISTRY-priority), shared


def decide_arm(arm: dict, signal: dict | None, *, equity: float, flat: bool,
               day_trades: int, killed: bool, sod_equity: float,
               prior_stops: list[str], params: dict, premium_override: float | None = None,
               probe_cfg: dict | None = None, probe_entries_today: int = 0,
               rescue_premium_fetch=None):
    """Multi-strategy decision: every fired strategy is gated+sized by plan_all, ONE is
    selected (REGISTRY priority, one-position rule), then the shared risk gate runs. No
    I/O, no placement. Returns (ArmDecision, exit_shape) so the caller can build the
    bracket from THIS strategy's proven exit shape (the grind-winner edge IS its exit).

    premium_override (when set) is the REAL option mid for the planned strike (fetched
    by the caller via the broker), so the WATCH risk-gate decision is faithful, not a
    signal estimate. Falls back to the side-block / signal est_premium when not supplied.

    probe_cfg/probe_entries_today (2026-07-10, PROBE ARM): pass-through to fx.plan_all --
    default None/0 is an inert no-op for every arm except the one probe_cfg names (see
    fleet_executor._is_probe_active). This function stays I/O-free; the caller (run()) owns
    reading accounts.json's probe_arm block and the persisted daily counter.

    rescue_premium_fetch (2026-08-03, L246 ORDERING FIX): optional (side, strike) -> mid
    callback used ONLY when the selected plan dies at the min_entry_premium floor and
    fleet_executor.floor_rescue_plan finds a full-send plan that plan_all's "no ENTER in
    plans" precondition shadowed (the 0-fires-EVER defect: the doomed OTM plan blocked the
    lane built to rescue it). The rescue is re-finalized at ITS OWN (ATM-class) strike's
    real premium -- so the floor and every downstream risk guard bind on it verbatim. None
    (every pre-existing caller) => the rescue finalizes with premium=None and risk_gate
    fails CLOSED (UNREADABLE_INPUT): the lane never trades blind. I/O stays in the caller.
    """
    if signal is None:
        return (fx.ArmDecision(arm["id"], "HOLD", None, None, None, None, None, None,
                               None, "no live signal"), None)
    plans = fx.plan_all(arm, signal, equity, params,
                        probe_cfg=probe_cfg, probe_entries_today=probe_entries_today)
    plan = _select_plan(plans)
    if plan is None:
        return (fx.ArmDecision(arm["id"], "HOLD", None, None, None, None, None, None,
                               None, "no qualifying setup (no strategy fired)"), None)
    exit_shape = plan.exit_shape  # the selected strategy's proven bracket (or None on HOLD)
    premium = premium_override
    if premium is None:
        premium = signal.get("est_premium")
        # FIX2 path: prefer the SELECTED strategy entry's est_premium; else fall back to the
        # SELECTED plan's side-block (not _chosen_side's single pick) so the premium matches
        # the strategy actually being traded.
        for e in signal.get("strategies") or []:
            if e.get("name") == plan.strategy and e.get("side") == plan.side \
                    and e.get("est_premium") is not None:
                premium = e.get("est_premium")
                break
        else:
            src = fx._perception_for_arm(signal, arm)
            side_blk = (src.get("bull") if plan.side == "C" else src.get("bear")) or {}
            if isinstance(side_blk, dict) and side_blk.get("est_premium") is not None:
                premium = side_blk.get("est_premium")
    # CAP-AWARE SIZING (fix: safe-3 qty8 > $600 cap). The shared risk gate DENIES an
    # over-cap qty with NO auto-reduce (L180/C11), so reduce the PROPOSED qty to the
    # affordable max — an A+ ELITE qty8 then places a cap-fitting order instead of being
    # silently BLOCK[RISK_CAP]'d (why safe-3 generated zero fills). afford==0 (even
    # min_contracts won't fit) -> leave qty so the gate correctly denies.
    if getattr(plan, "action", None) == "ENTER" and premium and getattr(plan, "qty", 0):
        afford = fx.risk_gate.max_affordable_qty(equity=equity, premium=premium, params=params)
        if afford and plan.qty > afford:
            plan = replace(plan, qty=afford,
                           reason=f"{plan.reason} [cap-reduced {plan.qty}->{afford}]")
    decision = fx.finalize(
        plan, equity=equity, start_of_day_equity=sod_equity, premium=premium,
        current_position_status=(None if flat else "open"),
        day_trades_used_5d=day_trades, kill_switch_tripped=killed,
        prior_stops_today=prior_stops, params=params,
        account_label=str(arm.get("account_number") or arm["id"]),
    )
    # L246 ORDERING FIX (2026-08-03): when the floor kills the selected plan, the full-send
    # rescue lane that plan_all's "no ENTER in plans" precondition shadowed gets its turn --
    # re-finalized at ITS OWN (ATM-class) strike's real premium, so the floor and every
    # downstream risk guard (NOT_FLAT / KILL_SWITCH / PDT / RISK_CAP / the floor itself)
    # bind on the rescue verbatim. Fires ONLY on SKIP_MIN_PREMIUM_FLOOR (see
    # fx.floor_rescue_plan's fail-closed eligibility). A denied rescue keeps the original
    # floor verdict, annotated for the audit trail. Guard: test_floor_rescue_2026_08_03.py.
    if decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR":
        rescue = fx.floor_rescue_plan(arm, signal, equity, params, plan, decision)
        if rescue is not None:
            r_premium = None
            if rescue_premium_fetch is not None and rescue.side and rescue.strike:
                try:
                    r_premium = rescue_premium_fetch(rescue.side, int(rescue.strike))
                except Exception:  # noqa: BLE001 -- a quote failure fails CLOSED below
                    r_premium = None
            r_decision = fx.finalize(
                rescue, equity=equity, start_of_day_equity=sod_equity, premium=r_premium,
                current_position_status=(None if flat else "open"),
                day_trades_used_5d=day_trades, kill_switch_tripped=killed,
                prior_stops_today=prior_stops, params=params,
                account_label=str(arm.get("account_number") or arm["id"]),
            )
            if r_decision.risk_code == "ALLOW" and r_decision.action in ("ENTER_BEAR",
                                                                         "ENTER_BULL"):
                r_decision = replace(
                    r_decision,
                    reason=(f"{r_decision.reason}; floor_rescue after "
                            f"SKIP_MIN_PREMIUM_FLOOR (normal plan strike={plan.strike} "
                            f"prem={premium})"))
                return (r_decision, rescue.exit_shape)
            decision = replace(
                decision,
                reason=(f"{decision.reason}; FULL_SEND floor_rescue denied: "
                        f"{r_decision.risk_code}"))
    return (decision, exit_shape)


def _occ_symbol(side: str, strike: int, expiry: datetime) -> str:
    cp = "C" if side == "C" else "P"
    return f"SPY{expiry.strftime('%y%m%d')}{cp}{int(round(strike * 1000)):08d}"


def _past_entry_ceiling(params: dict, now_et: datetime) -> bool:
    """FIX1 (2026-07-01): hard entry-time ceiling (mirror of heartbeat_core._past_entry_ceiling).
    safe-1/risky-3 hit the same 2026-06-30 failure: ENTER at 15:52 -> Alpaca rejected the order
    ('expires soon'). True => now_et is AT/AFTER params entry_no_trade_after_et => _place_live
    returns a SKIP_LATE_ENTRY row instead of attempting an order. Missing/malformed key fails
    CLOSED to the 15:00 doctrine default (v15.1 [09:35,15:00) entry window)."""
    raw = params.get("entry_no_trade_after_et") if isinstance(params, dict) else None
    ceiling = dt_time(15, 0)
    if raw:
        try:
            parts = str(raw).split(":")
            ceiling = dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (TypeError, ValueError, IndexError):
            ceiling = dt_time(15, 0)
    return now_et.time() >= ceiling


def _before_entry_floor(params: dict, now_et: datetime) -> bool:
    """FIX (2026-07-02): wall-clock entry-time floor (mirror of heartbeat_core).
    Fleet had a ceiling mirror but NO floor — safe-1 entered 09:31:01 on 2026-07-02 off
    the core's stale 09:30:03 verdict. Fails CLOSED to the 09:35 doctrine default.
    Guard: test_entry_floor_2026_07_02.py::TestFleetFloorMirror."""
    raw = params.get("entry_no_trade_before_et") if isinstance(params, dict) else None
    floor = dt_time(9, 35)
    if raw:
        try:
            parts = str(raw).split(":")
            floor = dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (TypeError, ValueError, IndexError):
            floor = dt_time(9, 35)
    return now_et.time() < floor


def _place_live(creds: dict, arm: dict, decision, exit_shape: dict | None,
                signal: dict, params: dict, now: datetime) -> dict:
    """LIVE bracket placement (gated). Built for the Monday flip; never runs in WATCH.

    The bracket levels come from the SELECTED strategy's own ExitShape (the grind-winner
    edge IS its exit): stop = mid*(1+premium_stop_pct) (premium_stop_pct is NEGATIVE, e.g.
    -0.20 -> mid*0.80), TP1 = mid*(1+tp1_premium_pct). tp1_qty_fraction + profit_lock_mode
    are threaded into the placement record for the EOD/management layer (place_bracket is a
    single TP1+stop bracket; scale-out/trail is a flagged FIX1 follow-up, NOT redesigned here).
    A malformed/zero/None premium_stop_pct (or a computed stop >= mid / <= 0) falls back to
    the -50% catastrophe cap rather than placing a too-tight/invalid stop (C2 null-stop guard).

    VISIBILITY (2026-07-09, STOP-B): "stop"/"premium_stop_pct" on the returned dict reflect
    the position's ACTUALLY-RESOLVED mode -- corrected to the catastrophe floor when
    exit_manager resolved STRUCTURE mode, unchanged (premium/mid-based) otherwise. New keys
    "stop_mode" ("structure"|"premium"), "trigger_level", and "stop_display" (the human-
    readable 'STRUCTURE@<level> (cat -50%)' / '<price> (<pct>)' text) make the truth
    glanceable in decisions.jsonl without decoding the pct fields. See exit_actuator.
    describe_stop for the render-only formatting contract.
    """
    if arm.get("structure_override"):
        return {"mode": "LIVE", "placed": False,
                "reason": "structure_override (e.g. 1DTE/vertical) not implemented -- held"}
    # FIX1 (2026-07-01): entry-time ceiling — a late ENTER is a logged SKIP row, never an
    # order attempt (2026-06-30: safe-1/risky-3 fired 15:52, Alpaca rejected 'expires soon').
    if _past_entry_ceiling(params, now):
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_LATE_ENTRY",
                "entry_ceiling_et": str(params.get("entry_no_trade_after_et") or "15:00")}
    # FIX (2026-07-02): wall-clock floor mirror — the fleet consumes the core verdict
    # via shared-signal (passed derives from VERDICT, not action), so it needs its own gate.
    if _before_entry_floor(params, now):
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_EARLY_ENTRY",
                "entry_floor_et": str(params.get("entry_no_trade_before_et") or "09:35")}
    side = decision.side
    strike = decision.strike
    qty = decision.qty
    expiry = now  # 0DTE
    symbol = _occ_symbol(side, strike, expiry)
    arm_id = str(arm.get("id") or "unknown")
    # FLEET-SAME-BAR-COOLDOWN consult (see module comment at FLEET_SAME_BAR_COOLDOWN):
    # refuse a re-entry for a (arm, setup) that already attempted an entry on THIS exact
    # closed 5m trigger bar. Mirrors heartbeat_core._route_extra_setups' consult contract
    # exactly (same key shape, same string-equality bar comparison, same fail-open
    # try/except -- a cooldown-check error must never block an entry). Placed BEFORE any
    # broker/quote call: the refusal is local and free.
    if FLEET_SAME_BAR_COOLDOWN:
        _cd_bar = str((signal or {}).get("trigger_bar_et") or "") or None
        try:
            if ea.same_bar_cooldown_active(arm_id, str(decision.setup_name or "") or None,
                                           _cd_bar):
                return {"mode": "LIVE", "placed": False, "reason": "SKIP_COOLDOWN_SAME_BAR",
                        "trigger_bar_et": _cd_bar}
        except Exception:  # noqa: BLE001 -- fail-open: a cooldown-check error never blocks
            pass
    mid = fb.get_option_mid(creds, symbol)
    # MARKETABLE-LIMIT (#15): a limit @ mid rarely crosses on 0DTE -> the "zero fills ever" bug.
    # Price the ENTRY at ask+buffer so it actually fills; mid stays the base for the TP/stop pct
    # math (unchanged). No two-sided quote -> HOLD (never blind-price).
    entry_px = fb.marketable_limit_price(creds, symbol, side="buy",
                                         buffer=float(params.get("entry_cross_buffer", 0.03)))
    if mid is None or mid <= 0 or entry_px is None or entry_px <= 0:
        return {"mode": "LIVE", "placed": False, "reason": f"no quote for {symbol}"}

    # ORDER-LEVEL IDEMPOTENCY GUARD (2026-08-02, closes the gap in FLEET-RACE-AND-LATENCY-
    # 2026-08-01.md section 3). run()'s `flat` gate (fb.is_flat_spy_options, POSITIONS-only)
    # was read once, earlier, BEFORE this arm's exit-management pass / premium pre-fetch /
    # decide_arm -- real wall-clock time elapses between that read and this POST, and a
    # still-WORKING order from a prior tick is invisible to a positions-only query anyway.
    # Two layers, EITHER refusing is sufficient (fail CLOSED for placement -- a missed entry
    # is cheap, a double entry is not). This function is ENTRY-only: every return below is a
    # WATCH/SKIP row, never touches exits or the kill-switch (those are gated upstream in
    # run(), untouched by this block).
    #   LAYER 1 -- claim file (local, no network): an unexpired claim for this EXACT (arm,
    #     symbol) refuses outright before ever reaching the broker.
    if _claim_active(arm_id, symbol, now):
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_DUPLICATE_CLAIM",
                "detail": f"entry claim already active for {symbol}"}
    #   LAYER 2 -- broker open-orders query (authoritative). A query FAILURE refuses too
    #     (uncertain state -> no placement). open_buy_orders_checked / symbol_position_qty_
    #     checked are DISTINCT from open_buy_orders / is_flat_spy_options (which fail OPEN to
    #     []/True -- correct for their original read-only/maintenance uses, wrong for a
    #     placement gate) specifically so this guard can tell "confirmed empty" apart from
    #     "broker didn't answer".
    pending, ok = fb.open_buy_orders_checked(creds, symbol)
    if not ok:
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_ORDER_QUERY_ERROR",
                "detail": f"could not confirm no pending BUY order for {symbol}"}
    if pending:
        # CANCEL-REPLACE (#15, hardened 2026-08-02): clear stale never-crossed BUY limit(s)
        # on this symbol, but RE-VERIFY before proceeding -- a blind cancel-then-place was
        # the exact cancel-vs-fill race this guard exists to close (a cancel that raced a
        # fill must refuse here, never stack a second order on top of the fill).
        for _o in pending:
            if _o.get("id"):
                fb.cancel_order(creds, _o["id"], live=True)
        still_open, ok2 = fb.open_buy_orders_checked(creds, symbol)
        if not ok2:
            return {"mode": "LIVE", "placed": False, "reason": "SKIP_POST_CANCEL_QUERY_ERROR",
                    "detail": f"could not re-verify {symbol} after cancel"}
        if still_open:
            return {"mode": "LIVE", "placed": False, "reason": "SKIP_ORDER_STILL_OPEN_AFTER_CANCEL",
                    "detail": f"{len(still_open)} BUY order(s) survived the cancel attempt"}
        held_qty, ok3 = fb.symbol_position_qty_checked(creds, symbol)
        if not ok3:
            return {"mode": "LIVE", "placed": False, "reason": "SKIP_POST_CANCEL_POSITION_QUERY_ERROR",
                    "detail": f"could not confirm flat on {symbol} after cancel"}
        if held_qty > 0:
            return {"mode": "LIVE", "placed": False, "reason": "SKIP_CANCEL_RACED_FILL",
                    "detail": f"{symbol} shows {held_qty} filled contract(s) -- cancel raced a fill"}
    # Reserve the claim BEFORE the broker POST (defense in depth, independent of the
    # broker's own propagation timing -- see LAYER 1 above).
    _write_claim(arm_id, symbol, now)

    ex = exit_shape or {}
    # TP1 from the strategy's exit shape (positive pct); fall back to params, then +30%.
    tp_pct = ex.get("tp1_premium_pct")
    if tp_pct is None:
        tp_pct = float(params.get("tp1_premium_pct", params.get("tp1_pct", 0.30)))
    tp_price = round(mid * (1 + float(tp_pct)), 2)

    # Stop from the strategy's exit shape (negative pct -> mid*(1+pct)); guard invalid.
    CATASTROPHE_STOP = -0.50  # -50% catastrophe cap (CHART-STOP-PRIMARY)
    stop_pct = ex.get("premium_stop_pct")
    stop_pct = float(stop_pct) if stop_pct not in (None, 0) else CATASTROPHE_STOP
    stop_price = round(mid * (1 + stop_pct), 2)
    if stop_price >= mid or stop_price <= 0:  # too-tight/invalid -> catastrophe cap
        stop_pct = CATASTROPHE_STOP
        stop_price = round(mid * (1 + stop_pct), 2)

    # FIX2 (2026-07-01, supersedes the 2026-06-28 simple_fallback ladder): Alpaca NEVER
    # accepts bracket/oto for options (42210000) — the old place_bracket(simple_fallback=True)
    # path ate 2 guaranteed 422s (bracket_err + oto_err) before EVERY simple attempt
    # (2026-06-30 exec.broker rows). Place the marketable simple limit DIRECTLY; TP/stop stay
    # engine-managed (register_entry below + ea.manage_tick runs FIRST each cycle, enforcing
    # premium/target/time stops via the per-tick worst<=stop check — the exact C2 condition).
    if qty is None or int(qty) < 1:
        return {"mode": "LIVE", "placed": False, "reason": f"invalid qty {qty}"}
    _order = {"symbol": symbol, "qty": str(int(qty)), "side": "buy", "type": "limit",
              "limit_price": str(round(float(entry_px), 2)), "time_in_force": "day"}
    # LATENCY INSTRUMENT (2026-08-01, WEEKEND-TWELVE #5): our OWN wall-clock right before the
    # broker POST -- distinct from the broker's own created_at/submitted_at already riding
    # inside `res` below (that is Alpaca's clock; this is ours, so the gap between the two is
    # a real network-latency measurement, not just a duplicate). Logging only.
    submit_ts = _now_et().isoformat()
    res = fb._request(creds, "orders", method="POST", data=_order)
    if not isinstance(res, dict):
        res = {"_error": f"unexpected broker response: {res!r}"}
    if not res.get("_error"):
        res["_simple_first"] = True
        res["_note"] = ("simple marketable limit placed directly (options: no broker bracket); "
                        "TP/stop engine-managed (exit_manager)")
    placed = not res.get("_error") and not res.get("_refused")
    # FLEET-SAME-BAR-COOLDOWN stamp: record (arm, setup) -> trigger-bar ONLY on an actual
    # placement (mirrors core's _TAKEN contract -- every refusal above returned before this
    # line and never stamps). record_entry_bar itself no-ops on empty setup/bar and swallows
    # write errors (never aborts an already-placed entry).
    if FLEET_SAME_BAR_COOLDOWN and placed:
        try:
            ea.record_entry_bar(arm_id, str(decision.setup_name or ""),
                                str((signal or {}).get("trigger_bar_et") or ""))
        except Exception:  # noqa: BLE001 -- never abort an already-placed entry
            pass
    # EXIT ENGINE WIRING (FIX1 follow-up, 2026-06-25): the bracket above is only the
    # entry leg + a catastrophe-floor stop. Register the position with the exit_manager so
    # the tick-managed scale-out (partial TP1 at tp1_qty_fraction + runner + profit-lock per
    # profit_lock_mode) is realized on subsequent ticks via exit_actuator.manage_tick. This
    # is the validated 5-stage exit shape the single full-qty bracket cannot express. Only
    # registered on a real fill (placed) so a rejected order leaves no orphan exit state.
    _exit_state = None
    if placed:
        try:
            # STRUCTURE-STOP (2026-07-09): trigger_level rides on `decision` (threaded from
            # the selected EntryPlan by fleet_executor.finalize); structure_stop_enabled is
            # read straight from this arm's params (default False/absent -> "premium" mode,
            # byte-identical -- see exit_manager.ExitState.from_entry for the resolution).
            _exit_state = ea.register_entry(
                arm["id"], symbol=symbol, side=side, entry_premium=entry_px,
                qty=qty, exit_shape=ex, strategy=str(decision.setup_name or ""),
                trigger_level=getattr(decision, "trigger_level", None),
                structure_stop_enabled=bool(params.get("structure_stop_enabled", False)))
        except Exception:  # never let exit-state bookkeeping fail an accepted entry
            _exit_state = None
    # ENTRY-ANCHOR-TO-FILL FIX (2026-08-03): register_entry above necessarily seeds
    # entry_premium from entry_px (the PRE-FILL marketable-limit price) -- fleet_live had
    # NO fill-poll anywhere on the entry path before this fix (confirmed: 0 of 240 broker
    # sub-objects across every fleet arm's decisions.jsonl history ever recorded a non-null
    # filled_avg_price). Poll now, bounded (mirrors heartbeat_core._reconcile_fill's own
    # cap so a slow poll can never stall the per-minute tick materially), and re-anchor the
    # just-registered ExitState to the TRUE fill via exit_actuator.reanchor_entry -- see
    # that function's docstring for the full mechanism + the conservative refuse-and-log
    # cases (fill unknown, or a real tick already advanced the position past this poll).
    # Guard: backtest/tests/test_entry_anchor_to_fill_2026_08_03.py.
    if placed and _exit_state is not None:
        _fill_info = None
        try:
            _order_id = res.get("id") if isinstance(res, dict) else None
            if _order_id:
                _fill_info = fb.poll_fill(creds, _order_id, attempts=4, sleep_sec=0.6)
        except Exception as _e:  # noqa: BLE001 -- a poll failure must never abort the entry
            print(f"[reanchor] poll_fill FAILED for {symbol}: {type(_e).__name__}: {_e}",
                 file=sys.stderr)
            _fill_info = None
        _true_fill = (_fill_info.get("filled_avg_price")
                     if isinstance(_fill_info, dict) and _fill_info.get("filled") else None)
        if _true_fill is not None:
            try:
                _reanchored = ea.reanchor_entry(arm["id"], symbol=symbol,
                                                true_entry_premium=_true_fill)
                if _reanchored is not None:
                    _exit_state = _reanchored
                else:
                    print(f"[reanchor] SKIPPED {symbol}: no eligible ExitState to re-anchor "
                         f"(already tp1_filled/profit_lock_armed, or registration missing) "
                         f"-- riding out on the limit anchor {entry_px}", file=sys.stderr)
            except Exception as _e:  # noqa: BLE001 -- never let reanchoring break the tick
                print(f"[reanchor] FAILED for {symbol}: {type(_e).__name__}: {_e} "
                     f"-- riding out on the limit anchor {entry_px}", file=sys.stderr)
        else:
            print(f"[reanchor] fill unknown for {symbol} after poll (fill_info={_fill_info}) "
                 f"-- keeping the limit anchor {entry_px}, never guessing", file=sys.stderr)
    # VISIBILITY (2026-07-09, render-only; OP-33c/STOP-B ship-1 known-cosmetic-bug fix): the
    # plan-log "stop" text must show the TRUTH this position is actually managed under. When
    # register_entry above resolved STRUCTURE mode, the premium-mode stop_price/stop_pct
    # computed at line ~299 (from the strategy's flag-OFF-fallback premium_stop_pct, e.g.
    # ribbon_ride's -20%) is NOT what protects this trade -- exit_manager enforces the chart-
    # level + the catastrophe cap instead, and BOTH numeric fields are corrected here to match
    # (they were already log-only -- see the _order dict above, which carries no stop/tp key
    # at all; neither field is ever sent to the broker, so this cannot change what gets
    # placed). Premium-mode positions are byte-identical to before this change (untouched).
    # stop_display always carries the human-readable form either way.
    if _exit_state is not None and _exit_state.stop_mode == "structure":
        stop_pct = _exit_state.catastrophe_stop_pct
        stop_price = _exit_state.runner_stop_premium
    stop_display = ea.describe_stop(_exit_state, fallback_price=stop_price, fallback_pct=stop_pct)
    return {"mode": "LIVE", "symbol": symbol, "mid": mid, "tp": tp_price,
            "tp1_premium_pct": tp_pct, "stop": stop_price, "premium_stop_pct": stop_pct,
            "stop_display": stop_display,
            "stop_mode": (_exit_state.stop_mode if _exit_state is not None else "premium"),
            "trigger_level": (_exit_state.trigger_level if _exit_state is not None else None),
            "strategy": decision.setup_name,
            # the FULL exit shape, now ENFORCED by the exit_manager (registered above):
            "tp1_qty_fraction": ex.get("tp1_qty_fraction"),
            "profit_lock_mode": ex.get("profit_lock_mode"),
            "exit_managed": placed,
            "entry_px": entry_px, "broker": res, "placed": placed,
            "submit_ts": submit_ts}


def run(signal_path: Path, master_live: bool) -> list[dict]:
    now = _now_et()
    creds_all = fb.load_creds()
    accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    # Eager exit_patch validation (2026-07-20 exit-diversity overlay): a typo'd knob must
    # kill the tick loudly at config load, not silently no-op at entry time (C14/L201).
    fx.validate_accounts_exit_patches(accounts)
    signal, sig_err = _load_signal(signal_path, now)
    usable_signal = signal if (signal is not None and sig_err is None) else None
    results: list[dict] = []
    # PROBE ARM (2026-07-10): single top-level accounts.json read; None/enabled=False is a
    # byte-identical no-op for every arm (fx._is_probe_active short-circuits False).
    probe_cfg = accounts.get("probe_arm")

    for arm in accounts.get("arms", []):
        # Process the 4 fleet_rest arms always; ALSO the 2 mcp_heartbeat controls when the
        # FLEET_OWNS_ALL_6 unification lever is set (paired with GAMMA_CORE_PLACES=0 upstream,
        # the no-double-fill invariant). DEFAULT: fleet_rest only = today's split execution.
        if not _arm_is_processable(arm):
            continue
        arm_id = arm["id"]
        creds = creds_all.get(arm_id)
        row: dict[str, Any] = {
            "tick_id": (signal or {}).get("tick_id"),
            # LATENCY INSTRUMENT (2026-08-01, WEEKEND-TWELVE #5, additive/logging-only):
            # core_tick_id + signal_written_at let a later join (setup/scripts/
            # fill_latency.py) walk core_verdict_ts (core-decisions.jsonl, via core_tick_id)
            # -> signal_written_ts (this signal's own written_at, captured here since
            # shared-signal.json itself is overwritten every tick and not archived) ->
            # plan_ts/submit_ts below -> fill_ts (broker). ts_et (unchanged) IS this tick's
            # read/plan-start timestamp -- documented here so a reader never has to
            # rediscover that mapping.
            "core_tick_id": (signal or {}).get("core_tick_id"),
            "signal_written_at": (signal or {}).get("written_at"),
            "ts_et": now.isoformat(), "arm_id": arm_id,
            "signal_status": sig_err or "ok",
        }
        if not creds:
            row.update(action="ERROR", reason="no creds in secrets.json")
            results.append(_log(arm_id, row)); continue
        acct = fb.get_account(creds)
        if acct.get("_error"):
            row.update(action="ERROR", reason=f"account fetch: {acct.get('_status')}")
            results.append(_log(arm_id, row)); continue

        equity = float(acct.get("equity", 0) or 0)
        # FLEET-PDT-PARITY (2026-08-06, EOD-2026-08-05-SILENT-ARMS). This line read
        # `acct.get("daytrade_count")`, which Alpaca PAPER returns as **null** for every
        # arm -> int(None or 0) == 0 FOREVER. fleet_executor.py:1125 pins these arms to
        # pdt_gate_mode="margin_pdt", so the margin-PDT branch of the risk gate has been
        # fed a hardcoded 0 since the fleet shipped: `0 >= 3` is never true, Rule 7 was
        # structurally unenforceable on every fleet arm, and the decision ledger recorded
        # `day_trades: 0` as if that were broker truth. This is the SAME defect
        # heartbeat_core.py fixed for the core accounts on 2026-07-06 (its comment: "a
        # hardcoded 0 that no component ever incremented"); the fleet lane never got the
        # sibling fix. Broker-verified 2026-08-06 pre-dawn -- TRUE trailing-5bd counts
        # were safe-3=6, risky-1=7, risky-3=8 while all three logged 0.
        #
        # TWO SEPARATE HALVES, deliberately:
        #   VISIBILITY (always on, zero behavior change) -- the TRUE count is computed and
        #     logged every tick as day_trades_true/day_trades_source, so the ledger stops
        #     lying and "why didn't this arm trade" is answerable from the row itself.
        #   ENFORCEMENT (params.fleet_pdt_enforce, DEFAULT FALSE) -- what the risk gate
        #     actually binds on. Left OFF because flipping it blind would instantly jail
        #     all three arms (6/7/8 >= 3) on a constraint the PAPER broker does not
        #     enforce, and doctrine has ALREADY once ruled exactly this kind of inherited
        #     margin-PDT block "a fictional constraint, not a real one" (params.json
        #     #_pdt_gate_mode_doc, 2026-07-14, after it silently killed 4 real core
        #     entries). Enforcement also needs the account-type question settled first:
        #     all five arms now read multiplier=4 / shorting_enabled=true (MARGIN), which
        #     CONTRADICTS core params.json's pinned "multiplier=1 ... CASH account"
        #     provenance -- that doc also names PA3DHPT7KIQE, an account safe-2 no longer
        #     points at. Resolve that, then flip this one key.
        # Revert / arm: set params.fleet_pdt_enforce true (arm) or delete it (today's
        # behavior). Guard: backtest/tests/test_fleet_pdt_parity.py (vary-and-assert, C14).
        params = fx._params_for(arm)
        day_trades_legacy = int(acct.get("daytrade_count", 0) or 0)
        day_trades_true, day_trades_source = _true_day_trades_5d(arm_id, creds, acct)
        enforce_true = bool(params.get("fleet_pdt_enforce")) and bool(arm.get("live"))
        day_trades = day_trades_true if enforce_true else day_trades_legacy
        row.update(day_trades_true=day_trades_true, day_trades_source=day_trades_source,
                   pdt_enforced=enforce_true)
        flat = fb.is_flat_spy_options(creds)
        limit_pct = _limit_pct_for(arm)
        breaker = _load_or_arm_breaker(arm_id, equity, now, limit_pct)
        killed = bool(breaker.get("tripped"))
        sod = float(breaker.get("starting_equity_today", equity))
        prior_stops = _load_prior_stops(arm_id, now)
        # PROBE ARM: only the named arm reads/writes probe-count.json (no stray per-arm
        # files for the other 3 -- guard on _is_probe_active, not just "does probe_cfg exist").
        probe_entries_today = (_load_probe_count(arm_id, now).get("count", 0)
                               if fx._is_probe_active(arm, probe_cfg) else 0)

        # EXIT-MANAGEMENT PASS (runs FIRST each tick, before any new entry): manage every
        # open position's scale-out per its registered exit shape (partial TP1 + runner +
        # profit-lock + time stop). WATCH arms compute-but-place-nothing (live=arm_live);
        # only a live, non-killed arm actually scales out. Fail-safe: bookkeeping errors
        # never abort the entry pass below.
        exit_pass = []
        try:
            # G14 (2026-07-01): fleet arms get the same v15.3 ribbon-flip-back PRIMARY
            # invalidation as the core accounts. Stale/absent signal -> None (fail-open;
            # catastrophe cap / targets / time stops still run inside manage_tick).
            _flip = ea.make_ribbon_flip_fn((usable_signal or {}).get("ribbon_stack"))
            # D2 #5 (2026-07-09): thread the arm's params time_stop_et ("15:40") through --
            # previously ABSENT, so exit_manager's hard-coded 15:50 default always won and
            # fleet arms carried runners 10 min longer than the core accounts (heartbeat_core
            # threads the same key at its _manage_exits call). Fail-safe inside manage_tick:
            # missing/malformed parses to 15:50, never widens past close. Guard:
            # test_fleet_time_stop_threaded.py. Revert: drop this kwarg.
            # STRUCTURE-STOP (2026-07-09): shared-signal.json's 'spot' is the closed 5m SPY
            # bar's close (heartbeat_core._build_payload's trig_idx = n-2 -- there is always
            # a MORE RECENT confirmation bar past it, so it is never the forming bar) and
            # `usable_signal` is already None whenever _load_signal found the file missing OR
            # older than SIGNAL_MAX_AGE_SEC (420s = 7min) -- reusing that existing staleness
            # gate (the same one _flip's ribbon_stack read already relies on) gives the
            # structure-stop check a fail-open closed-bar feed for free, no new plumbing.
            # Only consulted by a position whose stop_mode resolved to "structure" at entry
            # (exit_manager.plan_exit_actions); every other position ignores it.
            _closed_5m_close = (usable_signal or {}).get("spot")
            # ORPHAN-POSITION SAFETY NET (2026-08-10 night audit): adopt any open broker
            # position this arm is NOT tracking, so a lost/corrupt exit-state can never leave
            # a live position unmanaged until the 15:55 flatten -- the shape of today's
            # risky-1 -$440. Until tonight fleet arms (safe-3/risky-1/risky-3) had no
            # equivalent of heartbeat_core's _adopt_untracked_positions at all. Done INSIDE
            # manage_tick (not as a separate call here) so it uses the same injectable broker
            # the tick already resolved -- a standalone call imported the real fleet_broker
            # and fired an out-of-band `positions` GET that existing test doubles could not
            # intercept. `registry_shape` lets an ENGINE-PLACED orphan get its full ladder
            # back rather than a cap-only downgrade; unknown provenance stays cap-only.
            try:
                import strategies as _strategies  # noqa: PLC0415
                _adopt_shape = fx._exit_shape_dict(_strategies.by_name("ribbon_ride"), arm)
            except Exception:  # noqa: BLE001 -- no shape -> adoption still runs, cap-only
                _adopt_shape = None
            # KILL-SWITCH MUST NOT FREEZE EXITS (2026-08-10 night audit -- fleet-only defect).
            # This gate used to include `and not breaker.tripped`, which set live=False on a
            # tripped arm and turned the whole exit pass into WATCH: planned but PLACED
            # NOTHING. Proven empirically -- a 3-lot at entry 1.16 quoted 0.45 (61% down, way
            # through the -50% catastrophe cap) placed 1 sell with the breaker OK and ZERO
            # sells with it tripped. The stop-loss stopped working at exactly the moment the
            # account was losing the most, and the position rode to the 15:55 flatten.
            #
            # Rule 5 ("day closed for that account, no revenge trades") is an ENTRY rule.
            # Exiting an existing position is risk REDUCTION, never a revenge trade, and
            # freezing it converts a bounded loss into an unbounded one.
            #
            # heartbeat_core._manage_exits has ALWAYS been correct here (`live=ARMED`, no
            # breaker term), so this is fleet_live diverging from the reference path -- the
            # same 3 arms (safe-3/risky-1/risky-3) that also lacked the orphan safety net.
            # Entries remain fully blocked when tripped, by two INDEPENDENT gates that this
            # change does not touch: `arm_live` (below) and risk_gate's kill_switch_tripped.
            # Revert: re-add `and not bool(breaker.get("tripped"))` to this live= expression.
            exit_pass = ea.manage_tick(arm_id, creds,
                                       live=bool(master_live) and bool(arm.get("live")),
                                       now_et=now,
                                       ribbon_flip_back_fn=_flip,
                                       time_stop_et=params.get("time_stop_et"),
                                       last_closed_5m_close=_closed_5m_close,
                                       adopt_untracked=True, registry_shape=_adopt_shape)
        except Exception as e:  # noqa: BLE001
            exit_pass = [{"error": f"exit_manage: {type(e).__name__}: {e}"}]

        # Faithful WATCH: fetch the REAL option mid for the planned strike (read-only)
        # so the risk-gate decision uses the true premium, not the signal estimate.
        # SAME select-one logic as decide_arm so the prefetched strike matches the strike
        # that will actually be traded (deterministic -> identical (side, strategy, strike)).
        premium_override = None
        if usable_signal is not None:
            pre_plan = _select_plan(fx.plan_all(arm, usable_signal, equity, params,
                                                probe_cfg=probe_cfg,
                                                probe_entries_today=probe_entries_today))
            if pre_plan is not None and pre_plan.action == "ENTER" and pre_plan.strike \
                    and pre_plan.side and not arm.get("structure_override"):
                premium_override = fb.get_option_mid(creds, _occ_symbol(pre_plan.side, pre_plan.strike, now))

        decision, exit_shape = decide_arm(arm, usable_signal, equity=equity, flat=flat,
                                          day_trades=day_trades, killed=killed, sod_equity=sod,
                                          prior_stops=prior_stops, params=params,
                                          premium_override=premium_override,
                                          probe_cfg=probe_cfg,
                                          probe_entries_today=probe_entries_today,
                                          # L246 ORDERING FIX: real-quote pricing for a
                                          # floor-rescue's OWN strike (read-only GET; only
                                          # consulted on a SKIP_MIN_PREMIUM_FLOOR verdict).
                                          rescue_premium_fetch=(
                                              lambda side, strike:
                                              fb.get_option_mid(creds, _occ_symbol(side, strike, now))))

        # PROBE ARM: the cap counts DECIDED (risk_gate-ALLOWED) probe entries, not merely
        # attempted plans -- increments regardless of WATCH/LIVE mode (a WATCH-mode "would
        # have entered" still consumes a slot; today's accounts.json already has this arm
        # live=true + the scheduled task passes --live, so WATCH-only is not the operative
        # case, but the counter must not depend on that to stay correct if it ever changes).
        if (decision.risk_code == "ALLOW" and decision.action in ("ENTER_BEAR", "ENTER_BULL")
                and str(decision.reason or "").startswith("PROBE_ARM")):
            _record_probe_entry(arm_id, now)

        arm_live = bool(master_live) and bool(arm.get("live")) and not killed
        if arm_live and decision.action in ("ENTER_BEAR", "ENTER_BULL") and flat and usable_signal:
            # LATENCY INSTRUMENT (2026-08-01, WEEKEND-TWELVE #5): plan_ts is THIS arm's own
            # "about to act" instant -- more precise than the shared per-tick `now` above
            # (row["ts_et"]), which is captured once before ANY per-arm work (account fetch,
            # exit-management pass, premium pre-fetch) and can trail plan_ts by real time on
            # a slow tick. Logging only -- _place_live's decision/pricing/placement logic is
            # unchanged; this just timestamps the moment right before it runs.
            plan_ts = _now_et()
            placement = _place_live(creds, arm, decision, exit_shape, usable_signal, params, now)
            placement["plan_ts"] = plan_ts.isoformat()
        else:
            placement = {"mode": "WATCH" if not arm_live else "LIVE",
                         "placed": False,
                         "reason": ("watch_mode" if not arm_live else
                                    ("not_enter" if decision.action not in ("ENTER_BEAR", "ENTER_BULL")
                                     else "not_flat" if not flat else "no_signal"))}

        row.update(equity=round(equity, 2), flat=flat, day_trades=day_trades,
                   killed=killed, **asdict(decision), placement=placement,
                   exit_pass=exit_pass)
        results.append(_log(arm_id, row))
    return results


def _log(arm_id: str, row: dict) -> dict:
    d = FLEET_DIR / arm_id
    d.mkdir(exist_ok=True)
    with (d / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Fleet live/WATCH runner (one perception -> N policies).")
    ap.add_argument("--signal", default=str(DEFAULT_SIGNAL))
    ap.add_argument("--live", action="store_true", help="master-enable LIVE (still needs per-arm live:true)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        results = run(Path(args.signal), args.live)
    except Exception as e:  # never crash the scheduled wrapper
        print(json.dumps({"error": str(e)}))
        return 0
    if not args.quiet:
        for r in results:
            print(f"{r['arm_id']:9} {r.get('action',''):11} "
                  f"{str(r.get('reason',''))[:50]:50} place={r.get('placement',{}).get('mode','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
