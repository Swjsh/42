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


_select_plan = fx.select_plan  # canonical one-position selection (REGISTRY-priority), shared


def decide_arm(arm: dict, signal: dict | None, *, equity: float, flat: bool,
               day_trades: int, killed: bool, sod_equity: float,
               prior_stops: list[str], params: dict, premium_override: float | None = None):
    """Multi-strategy decision: every fired strategy is gated+sized by plan_all, ONE is
    selected (REGISTRY priority, one-position rule), then the shared risk gate runs. No
    I/O, no placement. Returns (ArmDecision, exit_shape) so the caller can build the
    bracket from THIS strategy's proven exit shape (the grind-winner edge IS its exit).

    premium_override (when set) is the REAL option mid for the planned strike (fetched
    by the caller via the broker), so the WATCH risk-gate decision is faithful, not a
    signal estimate. Falls back to the side-block / signal est_premium when not supplied.
    """
    if signal is None:
        return (fx.ArmDecision(arm["id"], "HOLD", None, None, None, None, None, None,
                               None, "no live signal"), None)
    plans = fx.plan_all(arm, signal, equity, params)
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
    mid = fb.get_option_mid(creds, symbol)
    # MARKETABLE-LIMIT (#15): a limit @ mid rarely crosses on 0DTE -> the "zero fills ever" bug.
    # Price the ENTRY at ask+buffer so it actually fills; mid stays the base for the TP/stop pct
    # math (unchanged). No two-sided quote -> HOLD (never blind-price).
    entry_px = fb.marketable_limit_price(creds, symbol, side="buy",
                                         buffer=float(params.get("entry_cross_buffer", 0.03)))
    if mid is None or mid <= 0 or entry_px is None or entry_px <= 0:
        return {"mode": "LIVE", "placed": False, "reason": f"no quote for {symbol}"}
    # CANCEL-REPLACE (#15): clear any stale never-crossed BUY limit on this symbol from a prior
    # tick before placing a fresh marketable one (prevents a pile of dead pendings).
    for _o in fb.open_buy_orders(creds, symbol):
        if _o.get("id"):
            fb.cancel_order(creds, _o["id"], live=True)

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
    res = fb._request(creds, "orders", method="POST", data=_order)
    if not isinstance(res, dict):
        res = {"_error": f"unexpected broker response: {res!r}"}
    if not res.get("_error"):
        res["_simple_first"] = True
        res["_note"] = ("simple marketable limit placed directly (options: no broker bracket); "
                        "TP/stop engine-managed (exit_manager)")
    placed = not res.get("_error") and not res.get("_refused")
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
            "entry_px": entry_px, "broker": res, "placed": placed}


def run(signal_path: Path, master_live: bool) -> list[dict]:
    now = _now_et()
    creds_all = fb.load_creds()
    accounts = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    signal, sig_err = _load_signal(signal_path, now)
    usable_signal = signal if (signal is not None and sig_err is None) else None
    results: list[dict] = []

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
        day_trades = int(acct.get("daytrade_count", 0) or 0)
        flat = fb.is_flat_spy_options(creds)
        params = fx._params_for(arm)
        limit_pct = _limit_pct_for(arm)
        breaker = _load_or_arm_breaker(arm_id, equity, now, limit_pct)
        killed = bool(breaker.get("tripped"))
        sod = float(breaker.get("starting_equity_today", equity))
        prior_stops = _load_prior_stops(arm_id, now)

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
            exit_pass = ea.manage_tick(arm_id, creds, live=bool(master_live) and bool(arm.get("live"))
                                       and not bool(breaker.get("tripped")), now_et=now,
                                       ribbon_flip_back_fn=_flip,
                                       time_stop_et=params.get("time_stop_et"),
                                       last_closed_5m_close=_closed_5m_close)
        except Exception as e:  # noqa: BLE001
            exit_pass = [{"error": f"exit_manage: {type(e).__name__}: {e}"}]

        # Faithful WATCH: fetch the REAL option mid for the planned strike (read-only)
        # so the risk-gate decision uses the true premium, not the signal estimate.
        # SAME select-one logic as decide_arm so the prefetched strike matches the strike
        # that will actually be traded (deterministic -> identical (side, strategy, strike)).
        premium_override = None
        if usable_signal is not None:
            pre_plan = _select_plan(fx.plan_all(arm, usable_signal, equity, params))
            if pre_plan is not None and pre_plan.action == "ENTER" and pre_plan.strike \
                    and pre_plan.side and not arm.get("structure_override"):
                premium_override = fb.get_option_mid(creds, _occ_symbol(pre_plan.side, pre_plan.strike, now))

        decision, exit_shape = decide_arm(arm, usable_signal, equity=equity, flat=flat,
                                          day_trades=day_trades, killed=killed, sod_equity=sod,
                                          prior_stops=prior_stops, params=params,
                                          premium_override=premium_override)

        arm_live = bool(master_live) and bool(arm.get("live")) and not killed
        if arm_live and decision.action in ("ENTER_BEAR", "ENTER_BULL") and flat and usable_signal:
            placement = _place_live(creds, arm, decision, exit_shape, usable_signal, params, now)
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
