"""j_intent_executor -- standing deterministic executor for J-called conditional
trades (automation/overnight/queue.md ## J-INTENT-EXECUTOR, J-called 2026-07-15
13:30 ET).

WHY: J: "you are too slow to decide then implement and making LLM calls for
logic." Today's J-called 752P took ~16 min to arm through a hand-written
one-off watcher (with a stale-bar bug), ~2 min trigger->fill, ~1 min
stop->flat -- every hop had an LLM wake inside it. This daemon removes every
LLM call from the hot path: Claude's ONLY role at trade time is to translate
J's sentence into an intent JSON in automation/state/j-intents.json (one turn,
<60s -- see `arm_intent_example` at the bottom of this file / the report this
build shipped with). This process polls that file every 15s and does
EVERYTHING else -- trigger/invalidation detection, sizing, risk-gating, entry,
TP1/catastrophe/chandelier/time-stop management, self-flatten, and journaling
-- with zero LLM calls, zero MCP round-trips, direct Alpaca REST only.

REUSE, NOT REBUILD (per the queue item's explicit instruction -- every one of
these is the SAME machinery the live heartbeat/fleet already trade with, so
this daemon can never drift from production behavior):
  * setup/scripts/j_intent_logic.py   -- trigger/invalidation/chart-stop pure
    evaluators + the ARMED_AT stale-bar guard (see that module's docstring).
  * automation/state/fleet/fleet_broker.py -- ALL broker I/O (account,
    positions, quotes, marketable-limit pricing, market_sell, poll_fill,
    close_all_spy_options). Same client the live fleet arms use today.
  * automation/state/fleet/exit_manager.py + exit_actuator.py -- the pure
    5-stage exit walk (TP1 partial / catastrophe / chandelier trail /
    structure chart-stop / time-stop) and its live per-tick actuator +
    state-ledger. A J-intent position is registered under its OWN arm_id
    namespace ("j_intent_safe" / "j_intent_bold" -> automation/state/fleet/
    j_intent_{account}/exit-state.json) so it can never collide with a core
    or fleet-arm position's persisted state.
  * backtest/lib/risk_gate.py -- check_order is the SAME single source of
    truth for kill-switch / settlement / sizing caps the live heartbeat uses.
  * setup/scripts/settlement_ledger.py -- the SAME Rule-7 cash-settlement
    pool the heartbeat and fast_path_executor already debit.
  * setup/scripts/spread_executor.py -- load_core_creds (.mcp.json reader,
    byte-identical pattern to fast_path_executor) + occ_symbol/parse_occ +
    the generic _request() REST client (also used for the SPY underlying-bar
    fetch, via its `host=` override).
  * setup/scripts/pdt_tracker.py -- fetch_day_trades_used_5d (kept only for
    legacy pdt_gate_mode="margin_pdt" / visibility parity with heartbeat_core;
    both core accounts run pdt_gate_mode="cash_settlement" today).
  * crypto/lib/strike_selection.py -- pick_strike (V15_SAFE_TIERS /
    V15_BOLD_TIERS), the SAME ATM/OTM ladder the live engine trades.
  * setup/scripts/et_clock.py -- the ONLY clock (never Bash TZ; this rig runs
    Mountain time, ET = local+2 -- see CLAUDE.md's TIME rule).

The ONLY genuinely new logic in this build is: the j-intents.json schema/
store, the trigger-driven entry decision (decide_entry), and the
journal/trades.csv + journal/YYYY-MM-DD.md writer (Rule 8). Everything else
above is imported, not reimplemented.

BAR-CLOSE CONVENTION: see j_intent_logic.py's module docstring. "The 13:15
bar" = the bar that STARTED 13:10 and CLOSED 13:15 -- every timestamp this
module logs against a bar is the CLOSE time.

FAIL-OPEN / FAIL-CLOSED CONTRACT (queue spec, restated precisely):
  * Feed errors (bar fetch, quote fetch) -> log + keep polling. Never crash
    the loop, never treat a feed gap as a trigger or an exit.
  * Order errors (entry POST fails, exit POST fails) -> fail CLOSED: alert
    once via automation/state/discord-outbox.jsonl (rate-limited, never
    spammed every 15s) and stop blindly retrying a failed ENTRY (an entry
    failure before any fill is safe to abandon -- the setup already printed,
    re-attempting blind risks a double-fire). An EXIT failure on an OPEN
    position is different: leaving a real position unmanaged is worse than a
    rate-limited alert, so exit attempts keep retrying every tick while the
    alert itself is throttled.

DEFAULT STATE = NO-OP: with an empty (or all-terminal) intents list this
process places NOTHING -- see `poll_once`'s first line and
test_j_intent_executor_replay.py::test_default_empty_intents_is_pure_noop.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time as _time
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Path wiring mirrors heartbeat_core.py EXACTLY (REPO / these dirs), so the
# exact same module objects (ribbon, exit_manager, risk_gate, ...) resolve --
# no parallel/near-duplicate import graph to drift from production.
sys.path.insert(0, str(Path(__file__).resolve().parent))  # this dir first
for _p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib"):
    sys.path.insert(0, str(PROJECT_ROOT / _p))

import j_intent_logic as jl  # noqa: E402
import j_intent_journal as jj  # noqa: E402  (append_journal_note, append_trade_row, build_entry_trade_row, alert_discord)
from et_clock import ET_TZ, et_now  # noqa: E402
import spread_executor as spx  # noqa: E402  (load_core_creds, occ_symbol, _request)
import fleet_broker as fb  # noqa: E402
import exit_manager as em  # noqa: E402
import exit_actuator as ea  # noqa: E402
import risk_gate as rg  # noqa: E402
import settlement_ledger as sl  # noqa: E402
import pdt_tracker as pdt  # noqa: E402
import strike_selection as ss  # noqa: E402

STATE = PROJECT_ROOT / "automation" / "state"
INTENTS_PATH = STATE / "j-intents.json"

POLL_SEC = 15
LOOP_IDLE_EXIT_SEC = 30 * 60  # self-exit when intents have been empty this long (09:25 refire covers the rest of RTH)

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ============================================================ intent store =
def _empty_store() -> dict:
    return {"intents": []}


def load_intents(path: Path = INTENTS_PATH) -> dict:
    """Fail-open on a missing/corrupt file -> an EMPTY store (never crashes
    the loop, never invents intents). A corrupt file is left on disk for a
    human to inspect rather than silently overwritten."""
    if not path.exists():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict) or not isinstance(data.get("intents"), list):
        return _empty_store()
    return data


def save_intents(data: dict, path: Path = INTENTS_PATH) -> None:
    """Atomic-ish write (temp file + replace) so a mid-write crash never
    truncates the live store a human might be reading."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_intent(data: dict, intent_id: str, **patch: Any) -> dict:
    """Return a NEW store dict with intent `intent_id` replaced by
    {**old, **patch} (coding-style immutability -- never mutate in place)."""
    new_intents = []
    for it in data.get("intents", []):
        if it.get("id") == intent_id:
            new_intents.append({**it, **patch})
        else:
            new_intents.append(it)
    return {**data, "intents": new_intents}


# ============================================================ params/creds =
def load_params(account: str) -> dict:
    """Account-overlay-merged params.json, byte-identical resolution order to
    fast_path_executor._load_params (base params.json <- params_{account}.json
    <- automation/state/aggressive/params.json for bold)."""
    base = STATE / "params.json"
    candidates = [STATE / f"params_{account}.json"]
    if account == "bold":
        candidates.append(STATE / "aggressive" / "params.json")
    merged: dict = {}
    if base.exists():
        try:
            merged = json.loads(base.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            merged = {}
    for p in candidates:
        if p.exists():
            try:
                merged = {**merged, **json.loads(p.read_text(encoding="utf-8"))}
            except (json.JSONDecodeError, OSError):
                pass
            break
    return merged


def load_creds(account: str) -> dict:
    """.mcp.json (gitignored) -> {key, secret, base_url}. Byte-identical
    source to fast_path_executor / spread_executor -- the ONLY credential
    store (CLAUDE.md secrets rule)."""
    return spx.load_core_creds(account)


# ============================================================ account context
def kill_switch_snapshot(account: str) -> dict:
    """{tripped, sod_equity} from circuit-breaker.json + the manual kill-
    switch sentinel file -- the EXACT same two-source check heartbeat_core._
    execute performs (bool(cb.get('tripped')) or (STATE/'kill-switch').exists()),
    so a J-intent can never trade past a kill-switch the core engine itself
    would have honored."""
    cb_path = (STATE / "aggressive" / "circuit-breaker.json") if account == "bold" else (STATE / "circuit-breaker.json")
    cb: dict = {}
    if cb_path.exists():
        try:
            cb = json.loads(cb_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cb = {}
    tripped = bool(cb.get("tripped")) or (STATE / "kill-switch").exists()
    sod_equity = cb.get("equity_start_of_day")
    if sod_equity is None:
        sod_equity = cb.get("starting_equity_today")
    return {"tripped": tripped, "sod_equity": sod_equity, "cb": cb}


def gather_entry_context(account: str, creds: dict) -> dict:
    """I/O ONLY: everything decide_entry needs that isn't specific to the
    triggering bar or the resolved option symbol. NEVER raises -- every
    sub-fetch degrades to a safe (deny-leaning) default on failure, matching
    the fail-closed-on-uncertainty contract risk_gate.check_order itself
    documents. Returns None fields are caught by risk_gate's own UNREADABLE_
    INPUT gate (fail-closed), never silently defaulted to a tradeable value.
    """
    acct = fb.get_account(creds)
    if not isinstance(acct, dict) or acct.get("_error"):
        return {"ok": False, "reason": f"account fetch failed: {acct}"}
    try:
        equity = float(acct.get("equity"))
    except (TypeError, ValueError):
        return {"ok": False, "reason": "equity unreadable"}
    ks = kill_switch_snapshot(account)
    sod_equity = ks["sod_equity"] if ks["sod_equity"] is not None else equity
    broker_flat = fb.is_flat_spy_options(creds)
    today_et = et_now().strftime("%Y-%m-%d")
    ledger_path = sl.ledger_path(STATE, account)
    settlement = sl.get_settlement_status(ledger_path, today_et, float(sod_equity))
    day_trades = pdt.fetch_day_trades_used_5d(creds)
    return {
        "ok": True,
        "equity": equity,
        "sod_equity": float(sod_equity),
        "broker_flat": broker_flat,
        "kill_switch_tripped": ks["tripped"],
        "settled_cash_available": settlement["settled_cash_remaining"],
        "same_day_entries_used": settlement["entries_used_today"],
        "day_trades_used_5d": day_trades,
        "ledger_path": ledger_path,
        "today_et": today_et,
    }


# ============================================================ sizing/decide
def resolve_qty(intent: dict, *, equity: float, premium: float, params: dict) -> int:
    """Explicit intent['sizing']['qty'] (int), or 'tier' -> risk_gate's own
    cap-aware max_affordable_qty (the SAME sizing math check_order enforces --
    L180 single source of truth), floored at params.min_contracts, capped at
    5 (matches fast_path_executor's $1K-tier cap). Never auto-reduces an
    EXPLICIT qty -- an explicit qty that doesn't fit is check_order's job to
    deny (mirrors production: 'the live gate does NOT auto-reduce')."""
    sizing = intent.get("sizing") or {}
    qty = sizing.get("qty", "tier")
    if qty == "tier":
        afford = rg.max_affordable_qty(equity=equity, premium=premium, params=params)
        min_contracts = int(params.get("min_contracts", 3))
        return max(min_contracts, min(afford, 5)) if afford else min_contracts
    try:
        return int(qty)
    except (TypeError, ValueError):
        return int(params.get("min_contracts", 3))


def decide_entry(intent: dict, *, ctx: dict, symbol: str, mid: float, params: dict) -> dict:
    """PURE decision (no I/O): broker-flat + risk_gate.check_order. Returns
    {'allow': bool, 'code': str, 'reason': str, 'qty': int, 'symbol': str}.
    `ctx` is the pre-fetched gather_entry_context() result -- this function
    never fetches anything itself, so 'kill-switch-tripped refusal' and
    'double-entry refusal when broker not flat' are directly unit-testable by
    constructing ctx by hand (backtest/tests/test_j_intent_executor_replay.py)."""
    if not ctx.get("ok"):
        return {"allow": False, "code": "CONTEXT_FETCH_FAILED", "reason": ctx.get("reason", "unknown"),
                "qty": 0, "symbol": symbol}
    qty = resolve_qty(intent, equity=ctx["equity"], premium=mid, params=params)
    setup_name = f"J_INTENT_{intent.get('id', 'unknown')}"
    current_position_status = "flat" if ctx["broker_flat"] else "open"
    decision = rg.check_order(
        intent["account"],
        equity=ctx["equity"],
        start_of_day_equity=ctx["sod_equity"],
        proposed_qty=qty,
        premium=mid,
        setup_name=setup_name,
        current_position_status=current_position_status,
        day_trades_used_5d=ctx["day_trades_used_5d"],
        kill_switch_tripped=ctx["kill_switch_tripped"],
        prior_stops_today=[],
        params=params,
        settled_cash_available=ctx["settled_cash_available"],
        same_day_entries_used=ctx["same_day_entries_used"],
    )
    return {
        "allow": bool(decision),
        "code": getattr(decision, "code", "UNKNOWN"),
        "reason": getattr(decision, "reason", ""),
        "qty": qty,
        "symbol": symbol,
    }


# ============================================================ symbol/strike
def resolve_symbol(intent: dict, spy_price: float, equity: float) -> str:
    """ATM/OTM strike via the SAME V15 tier ladder + pick_strike the live
    engine trades (crypto/lib/strike_selection.py) -- never a hand-picked
    strike. Expiry = today (0DTE, per CLAUDE.md 'The strategy')."""
    tiers = ss.V15_BOLD_TIERS if intent["account"] == "bold" else ss.V15_SAFE_TIERS
    strike = ss.pick_strike(spy_price, equity, intent["side"], tiers)
    expiry_yymmdd = et_now().strftime("%y%m%d")
    return spx.occ_symbol(intent["side"], strike, expiry_yymmdd, underlying="SPY")


# ============================================================ order placement
def place_entry(creds: dict, *, symbol: str, qty: int, live: bool = True) -> dict:
    """Cancel-replace any stale pending BUY on this exact symbol, then place
    ONE simple marketable limit BUY (Alpaca rejects bracket/oto for options
    100% of the time -- heartbeat_core._place_simple_entry precedent; TP/
    stop are engine-managed via exit_actuator, never a broker bracket).
    Polls to a terminal fill so the caller gets a REAL fill price/qty."""
    if not live:
        return {"_skipped": "live flag False (WATCH mode)"}
    for o in fb.open_buy_orders(creds, symbol):
        if o.get("id"):
            fb.cancel_order(creds, o["id"], live=True)
    entry_px = fb.marketable_limit_price(creds, symbol, side="buy")
    if not entry_px or entry_px <= 0:
        return {"_error": "no marketable quote (two-sided quote unavailable)"}
    order = {"symbol": symbol, "qty": str(int(qty)), "side": "buy", "type": "limit",
             "limit_price": str(round(float(entry_px), 2)), "time_in_force": "day"}
    res = fb._request(creds, "orders", method="POST", data=order)
    if not isinstance(res, dict):
        return {"_error": f"unexpected broker response: {res!r}"}
    if res.get("_error"):
        return res
    res["_simple_first"] = True
    res["_requested_limit_px"] = entry_px
    oid = res.get("id")
    if oid:
        res["_fill"] = fb.poll_fill(creds, oid, attempts=4, sleep_sec=1.5)
    return res


def register_position(intent: dict, *, symbol: str, entry_premium: float, qty: int) -> "em.ExitState":
    """Register the fill with exit_actuator under a J-intent-only arm
    namespace (automation/state/fleet/j_intent_{account}/exit-state.json) so
    it can never collide with a core or fleet-arm position. Builds the
    exit_shape straight from the intent's OWN exits block -- a J-called trade
    carries its complete exit contract in the intent, it does not fall back
    to any params.json default the way a core-engine setup does."""
    exits = intent.get("exits") or {}
    chandelier = exits.get("chandelier") or {}
    trigger_level = jl.chart_stop_trigger_level(intent)
    catastrophe_pct = float(exits.get("catastrophe_pct", -0.50))
    shape = {
        "premium_stop_pct": catastrophe_pct,
        "tp1_premium_pct": float(exits.get("tp1_pct", 0.30)),
        "tp1_qty_fraction": float(exits.get("tp1_fraction", 0.667)),
        "profit_lock_mode": "trailing" if chandelier else "fixed",
        # runner_target_mult maps DIRECTLY to exit_manager's runner_target_pct
        # (NOT mult-1.0) -- matches this codebase's own established convention:
        # exit_manager.DEFAULT_RUNNER_TARGET_PCT=2.5 is commented "CLAUDE.md:
        # runner target 2.5x", i.e. the doctrine multiplier IS the param value.
        "runner_target_pct": float(exits.get("runner_target_mult", em.DEFAULT_RUNNER_TARGET_PCT)),
        "trail_pct": float(chandelier.get("trail_pct", em.DEFAULT_TRAIL_PCT)),
        "profit_lock_arm_pct": float(chandelier.get("arm_pct", em.DEFAULT_PROFIT_LOCK_ARM_PCT)),
        "stop_mode": "structure" if trigger_level is not None else "premium",
        "catastrophe_stop_pct": catastrophe_pct,
    }
    return ea.register_entry(
        arm_id(intent["account"]), symbol=symbol, side=intent["side"],
        entry_premium=entry_premium, qty=qty, exit_shape=shape, strategy="J_INTENT",
        trigger_level=trigger_level, structure_stop_enabled=(trigger_level is not None),
    )


def arm_id(account: str) -> str:
    return f"j_intent_{account}"


# ============================================================ live bar feed
def fetch_latest_completed_bars(creds: dict, *, symbol: str = "SPY", limit: int = 5) -> list["jl.Bar"]:
    """Latest completed 5m SPY bars via direct Alpaca data REST (IEX feed --
    NEVER-BLIND: no MCP/TradingView dependency on the trigger hot path).
    Fail-open: any fetch/parse error returns [] and the caller simply holds
    (a feed gap must never read as 'no trigger forever' vs 'trigger now' --
    it reads as 'nothing new to evaluate this tick')."""
    end = et_now()
    start = end - timedelta(minutes=5 * (limit + 3))
    endpoint = (f"v2/stocks/{symbol}/bars?timeframe=5Min&limit={limit}"
                f"&start={start.strftime('%Y-%m-%dT%H:%M:%S')}Z"
                f"&end={end.strftime('%Y-%m-%dT%H:%M:%S')}Z&feed=iex")
    try:
        res = spx._request(creds, endpoint, host="https://data.alpaca.markets")
    except Exception:
        return []
    if not isinstance(res, dict) or res.get("_error"):
        return []
    bars_raw = res.get("bars") or []
    out = []
    for b in bars_raw:
        try:
            ts_utc = datetime.strptime(b["t"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            ts_et = et_now(now_utc=ts_utc)  # DST-aware UTC->ET (et_clock, never a hardcoded offset)
        except Exception:
            continue
        out.append(jl.Bar(start_et=ts_et, open=float(b["o"]), high=float(b["h"]),
                          low=float(b["l"]), close=float(b["c"]),
                          volume=float(b.get("v", 0) or 0)))
    out.sort(key=lambda x: x.start_et)
    return out


# ============================================================ main tick ===
def process_armed_intent(data: dict, intent: dict, *, now_et: datetime) -> dict:
    """One tick for ONE armed/triggered/filled intent. Returns the (possibly
    unchanged) store `data` with this intent's row updated. NEVER raises --
    every branch is wrapped so one bad intent can never take down the loop
    (fail-open on FEED errors, fail-closed/alert on ORDER errors, per module
    docstring)."""
    try:
        account = intent["account"]
        creds = load_creds(account)
        params = load_params(account)
        status = intent.get("status")

        if status == jl.STATUS_ARMED:
            bars = fetch_latest_completed_bars(creds)
            if not bars:
                return data  # feed gap -- fail-open, hold
            armed_at = jl.parse_et(intent["created_et"])
            expiry_et = None
            if intent.get("expiry_et"):
                expiry_et = jl.combine_today(now_et, intent["expiry_et"])
            trigger_spec = intent.get("trigger") or {}
            invalidation_spec = intent.get("invalidation") or {}

            if expiry_et is not None and now_et > expiry_et:
                return update_intent(data, intent["id"], status=jl.STATUS_EXPIRED,
                                     _resolved_at_et=now_et.strftime("%Y-%m-%dT%H:%M:%S"))

            for bar in bars:
                bclose = bar.close_et
                if jl.is_bar_stale(bclose, armed_at):
                    continue
                if intent.get("_last_bar_close_et") == bclose.strftime("%Y-%m-%dT%H:%M:%S"):
                    continue  # already evaluated this exact bar on a prior tick
                if jl.evaluate_invalidation(invalidation_spec, bar):
                    jj.append_journal_note(now_et, f"Intent {intent['id']} INVALIDATED at bar close "
                                                f"{bclose} (close={bar.close}).")
                    return update_intent(data, intent["id"], status=jl.STATUS_INVALIDATED,
                                         _last_bar_close_et=bclose.strftime("%Y-%m-%dT%H:%M:%S"))
                if jl.evaluate_trigger(trigger_spec, bar):
                    return _execute_trigger(data, intent, bar=bar, now_et=now_et,
                                            creds=creds, params=params)
                data = update_intent(data, intent["id"],
                                     _last_bar_close_et=bclose.strftime("%Y-%m-%dT%H:%M:%S"))
            return data

        if status in (jl.STATUS_TRIGGERED, jl.STATUS_FILLED):
            return _manage_open_position(data, intent, now_et=now_et, creds=creds)

        return data  # terminal status -- nothing to do
    except Exception as e:  # noqa: BLE001 -- one bad intent must never crash the loop
        jj.alert_discord(f"tick_error_{intent.get('id','?')}",
                      f"j_intent tick error on {intent.get('id','?')}: {type(e).__name__}: {e}",
                      now_et=now_et)
        return data


def _execute_trigger(data: dict, intent: dict, *, bar: "jl.Bar", now_et: datetime,
                     creds: dict, params: dict) -> dict:
    ctx = gather_entry_context(intent["account"], creds)
    if not ctx.get("ok"):
        jj.alert_discord(f"entry_ctx_{intent['id']}", f"j_intent {intent['id']}: entry context "
                                                    f"fetch failed ({ctx.get('reason')}) -- held, will retry.",
                      now_et=now_et)
        return data
    symbol = resolve_symbol(intent, bar.close, ctx["equity"])
    mid = fb.get_option_mid(creds, symbol)
    if not mid or mid <= 0:
        jj.alert_discord(f"entry_quote_{intent['id']}", f"j_intent {intent['id']}: no usable quote "
                                                      f"for {symbol} -- held, will retry.", now_et=now_et)
        return data
    decision = decide_entry(intent, ctx=ctx, symbol=symbol, mid=mid, params=params)
    if not decision["allow"]:
        jj.append_journal_note(now_et, f"Intent {intent['id']} trigger fired at bar close "
                                    f"{bar.close_et} but risk_gate DENIED "
                                    f"({decision['code']}: {decision['reason']}). Trade does not happen (Rule 10).")
        return update_intent(data, intent["id"], status=jl.STATUS_INVALIDATED,
                             _risk_gate_deny_code=decision["code"], _risk_gate_deny_reason=decision["reason"],
                             _resolved_at_et=now_et.strftime("%Y-%m-%dT%H:%M:%S"))
    res = place_entry(creds, symbol=symbol, qty=decision["qty"], live=True)
    if not isinstance(res, dict) or res.get("_error") or res.get("_refused") or res.get("_skipped"):
        jj.alert_discord(f"entry_place_{intent['id']}", f"j_intent {intent['id']}: ENTRY ORDER FAILED "
                                                      f"for {symbol} qty={decision['qty']}: {res}", now_et=now_et)
        return update_intent(data, intent["id"], status=jl.STATUS_TRIGGERED,
                             _entry_error=str(res)[:300], symbol=symbol, qty=decision["qty"])
    fill = res.get("_fill") or {}
    if not fill.get("filled"):
        # accepted but not yet confirmed filled -- stay TRIGGERED, next tick reconciles
        return update_intent(data, intent["id"], status=jl.STATUS_TRIGGERED, symbol=symbol,
                             qty=decision["qty"], _entry_order_id=res.get("id"))
    entry_px = float(fill.get("filled_avg_price") or 0)
    filled_qty = int(float(fill.get("filled_qty") or decision["qty"]))
    sl.record_entry(ctx["ledger_path"], ctx["today_et"], ctx["sod_equity"],
                    entry_px * filled_qty * 100.0, now_et.strftime("%Y-%m-%dT%H:%M:%S"))
    exit_state = register_position(intent, symbol=symbol, entry_premium=entry_px, qty=filled_qty)
    catastrophe_pct = float((intent.get("exits") or {}).get("catastrophe_pct", -0.50))
    stop_px = entry_px * (1 + catastrophe_pct)
    dollar_risk = (entry_px - stop_px) * filled_qty * 100.0
    row = jj.build_entry_trade_row(intent, symbol=symbol, qty=filled_qty, entry_px=entry_px,
                                equity_pre=ctx["equity"], now_et=now_et, stop_px=stop_px,
                                target_px=entry_px * (1 + float((intent.get("exits") or {}).get("tp1_pct", 0.30))),
                                dollar_risk=dollar_risk,
                                chart_stop_level=jl.chart_stop_trigger_level(intent))
    jj.append_trade_row(row, account=intent["account"])
    jj.append_journal_note(now_et, f"Intent {intent['id']} TRIGGERED + FILLED: BUY {filled_qty}x {symbol} "
                                f"@ ${entry_px:.2f} (order {res.get('id')}). Chart stop / catastrophe / "
                                f"chandelier / time-stop now engine-managed (exit_actuator, arm={arm_id(intent['account'])}).")
    return update_intent(data, intent["id"], status=jl.STATUS_FILLED, symbol=symbol, qty=filled_qty,
                         entry_px=entry_px, entry_order_id=res.get("id"),
                         triggered_bar_close_et=bar.close_et.strftime("%Y-%m-%dT%H:%M:%S"),
                         filled_at_et=now_et.strftime("%Y-%m-%dT%H:%M:%S"),
                         stop_mode=exit_state.stop_mode)


def _manage_open_position(data: dict, intent: dict, *, now_et: datetime, creds: dict) -> dict:
    symbol = intent.get("symbol")
    if not symbol:
        return data
    exits = intent.get("exits") or {}
    bars = fetch_latest_completed_bars(creds)
    last_closed_close = bars[-1].close if bars else None
    try:
        results = ea.manage_tick(arm_id(intent["account"]), creds, live=True,
                                 ribbon_flip_back_fn=None, now_et=now_et,
                                 time_stop_et=exits.get("time_stop_et"),
                                 last_closed_5m_close=last_closed_close)
    except Exception as e:  # noqa: BLE001 -- an exit-management error is CRITICAL (open position)
        jj.alert_discord(f"exit_tick_{intent['id']}", f"j_intent {intent['id']}: EXIT MANAGEMENT ERROR "
                                                    f"on OPEN position {symbol}: {type(e).__name__}: {e} -- "
                                                    f"position may be unmanaged, check the broker directly.",
                      now_et=now_et)
        return data
    row_for_symbol = next((r for r in results if r.get("symbol") == symbol), None)
    if row_for_symbol is None:
        return data
    if row_for_symbol.get("action") in ("FLAT_PRUNED",) or any(
        a.get("kind") == "SELL_ALL" and a.get("placed") for a in row_for_symbol.get("actions", [])
    ):
        jj.append_journal_note(now_et, f"Intent {intent['id']} EXITED: {symbol} flat "
                                    f"({row_for_symbol.get('action', row_for_symbol)}).")
        return update_intent(data, intent["id"], status=jl.STATUS_EXITED,
                             _resolved_at_et=now_et.strftime("%Y-%m-%dT%H:%M:%S"),
                             _exit_detail=str(row_for_symbol)[:500])
    for a in row_for_symbol.get("actions", []):
        if a.get("kind") in ("SELL_PARTIAL", "SELL_ALL") and not a.get("placed"):
            jj.alert_discord(f"exit_order_{intent['id']}", f"j_intent {intent['id']}: EXIT ORDER FAILED "
                                                         f"on OPEN position {symbol}: {a} -- retrying next tick.",
                          now_et=now_et)
    return data


def poll_once(*, now_et: Optional[datetime] = None, path: Path = INTENTS_PATH) -> dict:
    """ONE full pass over every non-terminal intent. Default state (empty or
    all-terminal intents) touches NOTHING (no broker call of any kind) --
    see test_default_empty_intents_is_pure_noop."""
    now_et = now_et or et_now()
    data = load_intents(path)
    active = [it for it in data.get("intents", []) if it.get("status") not in jl.TERMINAL_STATUSES]
    for intent in active:
        err = jl.validate_intent(intent)
        if err:
            data = update_intent(data, intent.get("id", "?"), status=jl.STATUS_INVALIDATED,
                                 _validation_error=err)
            continue
        data = process_armed_intent(data, intent, now_et=now_et)
    save_intents(data, path)
    return data


LOCK_PATH = STATE / "j-intent-executor.lock"
LOCK_STALE_SEC = 90  # > 2x POLL_SEC, so a healthy resident daemon's own heartbeat always looks fresh


def acquire_daemon_lock(now_et: datetime) -> bool:
    """True iff this process may proceed as the sole `--daemon` instance.

    Refuses (False) only when a lock file exists AND was touched within
    LOCK_STALE_SEC -- i.e. another instance is genuinely alive and ticking
    right now. A stale lock (crashed process, or simply no instance running)
    is silently reclaimed. This is belt-and-suspenders behind the scheduled
    task's own `MultipleInstances=IgnoreNew`: TWO resident daemons racing on
    the SAME j-intents.json could both observe status=='armed' on the same
    tick and both attempt entry -- exactly the double-order risk C11/Rule-4
    exist to prevent. Fail-open on a lock-write error (never let a filesystem
    hiccup block trading; the scheduler-level IgnoreNew is still the primary
    guard in that case)."""
    if LOCK_PATH.exists():
        try:
            age = (now_et - datetime.fromtimestamp(LOCK_PATH.stat().st_mtime)).total_seconds()
            if age < LOCK_STALE_SEC:
                return False
        except OSError:
            pass
    try:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_text(json.dumps({"pid": os.getpid(),
                                         "started_et": now_et.strftime("%Y-%m-%dT%H:%M:%S")}),
                             encoding="utf-8")
    except OSError:
        pass
    return True


def touch_daemon_lock(now_et: datetime) -> None:
    try:
        LOCK_PATH.write_text(json.dumps({"pid": os.getpid(),
                                         "touched_et": now_et.strftime("%Y-%m-%dT%H:%M:%S")}),
                             encoding="utf-8")
    except OSError:
        pass


def release_daemon_lock() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def run_daemon(path: Path = INTENTS_PATH) -> None:
    """15s poll loop -- the ONE resident process that actually ticks every
    15s. Self-exits at/after 16:00 ET, or after LOOP_IDLE_EXIT_SEC of an
    empty/all-terminal intents list. The scheduled task re-checks every 30min
    (see install-j-intent-executor.ps1) and relaunches if the prior instance
    already idled out -- so a newly-armed intent is always picked up within a
    30min worst case, while the process does not sit resident all day for
    nothing. Guarded by acquire_daemon_lock so two overlapping scheduled
    fires can never run concurrently against the same j-intents.json."""
    now_et = et_now()
    if not acquire_daemon_lock(now_et):
        print("j_intent_executor: another daemon instance is already alive (lock held) -- exiting.")
        return
    try:
        idle_since: Optional[datetime] = None
        while True:
            now_et = et_now()
            if now_et.time() >= dtime(16, 0):
                break
            touch_daemon_lock(now_et)
            data = poll_once(now_et=now_et, path=path)
            active = [it for it in data.get("intents", []) if it.get("status") not in jl.TERMINAL_STATUSES]
            if not active:
                idle_since = idle_since or now_et
                if (now_et - idle_since).total_seconds() >= LOOP_IDLE_EXIT_SEC:
                    break
            else:
                idle_since = None
            _time.sleep(POLL_SEC)
    finally:
        release_daemon_lock()


# ============================================================ CLI =========
def _self_test() -> int:
    """--self-test: prove the default no-op contract on THIS machine's real
    j-intents.json without placing anything (armed intents are skipped, only
    terminal/empty state is touched -- this never calls the broker)."""
    data = load_intents()
    active = [it for it in data.get("intents", []) if it.get("status") not in jl.TERMINAL_STATUSES]
    print(f"j-intents.json: {len(data.get('intents', []))} total, {len(active)} active")
    for it in active:
        print(f"  {it.get('id')}: status={it.get('status')} account={it.get('account')} side={it.get('side')}")
    if not active:
        print("No active intents -- next poll_once() would be a pure no-op (no broker calls).")
    return 0


def arm_intent_example(now_et: Optional[datetime] = None) -> dict:
    """Reference template for the ONLY thing Claude does at trade time:
    build one intent dict matching this shape, append it to
    automation/state/j-intents.json's "intents" list with status="armed",
    and save. No other action needed -- the resident daemon (already running
    from the 09:25 ET scheduled fire) picks it up on its next 15s tick. This
    function returns a REAL example (today's 2026-07-15 752P trade) purely
    for documentation/self-test; it does not write anything itself."""
    now_et = now_et or et_now()
    return {
        "id": jl.new_intent_id(now_et, slug="put"),
        "created_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "account": "safe",
        "side": "P",
        "trigger": {
            "type": "level_reject_confirmed_close",
            "tag_level": 752.00,
            "confirm_close_below": 751.94,
            "require_red_bar": True,
        },
        "invalidation": {"close_above": 752.45},
        "expiry_et": "15:00:00",
        "sizing": {"qty": 3},
        "exits": {
            "tp1_pct": 0.30,
            "tp1_fraction": 0.8,
            "chart_stop": {"close_above": 752.26},
            "catastrophe_pct": -0.50,
            "chandelier": {"arm_pct": 0.05, "trail_pct": 0.15},
            "runner_target_mult": 2.5,
            "time_stop_et": "15:40:00",
        },
        "status": jl.STATUS_ARMED,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run exactly one poll tick and exit")
    parser.add_argument("--daemon", action="store_true",
                        help="run the resident 15s poll loop until 16:00 ET / idle timeout "
                             "(what the scheduled task launches)")
    parser.add_argument("--self-test", action="store_true", help="print intents.json status, place nothing")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if args.daemon:
        run_daemon()
        return 0
    # default (including --once, and the bare no-arg case): exactly one poll
    # tick and exit. The scheduled task always passes --daemon; --once is for
    # manual/CI single-tick invocation (e.g. verifying a freshly-armed intent
    # is picked up without waiting on the resident loop).
    poll_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
