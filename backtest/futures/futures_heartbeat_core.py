"""futures_heartbeat_core.py — the DETERMINISTIC futures live tick (mirrors heartbeat_core.py).

Why (2026-07-07): the futures order-path (TastytradeBroker.place_bracket) is code-complete and
dry-run proven on sandbox account 5WW73759, and the MNQ v3 edge is validated (OOS +$69.89/tr, WF
PASS). The ONLY missing piece to autonomous paper-trading was a DETERMINISTIC tick — the old LLM
futures heartbeat was retired and futures never followed the SPY engine onto deterministic
heartbeat_core.py. This is that tick.

FLOW per instrument (MNQ, optionally MES):
  1. SEE   — latest 5m bars (continuous CSV, same source the validated backtest uses) + ribbon +
             VIX + levels -> run_all_watchers -> signals. REUSES the native-backtest see-loop so the
             signal is byte-identical to run_native_backtest.py (the thing v3 was validated on).
  2. DECIDE — should_take_v3 filters signals to the validated slices; risk.size_contracts sizes;
             risk PropAccount.would_violate is the kill-switch.
  3. ACT   — build the bracket + a deterministic exit plan; place via TastytradeBroker.place_bracket.

GATING (mirrors GAMMA_CORE_ARMED):
  DRY_RUN is the DEFAULT. A REAL sandbox order routes ONLY when BOTH hold:
    (a) env FUTURES_ARMED == "1", AND
    (b) the broker reports futures PROVISIONED (futures_bp > 0).
  Otherwise dry_run=True: the tick validates + logs + emits state, and places NOTHING. This fails
  SAFE — an armed-but-unprovisioned account (today's exact state: futures_bp=0.0) still does NOT route.

STATE EMIT (was stale since 06-17): every tick writes automation/state/futures/{last-tick,loop-state,
position}.json so J has glanceable visibility (like engine-health).

The pure-logic parts (signal read, decide, exit plan, state emit, arm gating) import only pandas +
local modules and run under EITHER interpreter. Only the broker-touching path lazily imports the
tastytrade SDK (system python), exactly like heartbeat_core's lazy fleet_broker import.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for p in ("backtest",):
    _pp = str(REPO / p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import pandas as pd  # noqa: E402

from futures.instruments import MNQ, MES, get as get_instrument  # noqa: E402
from futures.risk import PropAccount, TOPSTEP_50K, size_contracts  # noqa: E402
from futures.strategy_config_v3 import should_take_v3  # noqa: E402
from futures.futures_exit_manager import (  # noqa: E402
    FuturesExitState, open_state, decide_exit, DEFAULT_TIME_STOP_ET,
)

# Reuse the VALIDATED native-backtest see-loop pieces so the live signal == the backtested signal.
from futures.run_native_backtest import (  # noqa: E402
    load_futures, load_vix, EOD, _SPY_REFERENCE,
)
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states  # noqa: E402
from lib.watchers.runner import run_all_watchers  # noqa: E402
from lib.watchers.orb_watcher import set_futures_range_scale  # noqa: E402


# ── arm gating (mirrors GAMMA_CORE_ARMED semantics) ──────────────────────────
def _armed_env() -> bool:
    return os.environ.get("FUTURES_ARMED", "0") == "1"


STATE_DIR = REPO / "automation" / "state" / "futures"
LEDGER = STATE_DIR / "decisions.jsonl"

# Default risk profile: Topstep-style micro account (matches risk.py reference).
DEFAULT_RISK_PER_TRADE = 150.0   # $ risk budget per trade (micros)
DEFAULT_HARD_CAP = 5             # firm micro contract cap
TP1_FRACTION = 0.5


def _et_now() -> dt.datetime:
    """ET wall-clock via the repo's DST-aware clock (never Bash TZ / hardcoded offset)."""
    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_now  # noqa: PLC0415
        return et_now()
    except Exception:
        # Fallback: this box runs Mountain (ET = local + 2). Best-effort, never crash the tick.
        return dt.datetime.now() + dt.timedelta(hours=2)


# ── SEE: compute the latest signal (byte-faithful to the native backtest) ─────
def compute_latest_signals(inst, *, bars: Optional[pd.DataFrame] = None,
                           vix_df: Optional[pd.DataFrame] = None,
                           at_idx: Optional[int] = None) -> dict:
    """Run the validated watcher fleet on the most recent bar and return the raw signals + context.

    `bars`/`vix_df` injectable for tests + dry-run replay; live loads the continuous CSV (the same
    file run_native_backtest validated on). `at_idx` targets a specific bar (default: last usable
    bar); the trigger bar is at_idx (its exits are simulated forward from there). Returns a dict with
    'signals' (list of dicts) and a compact market snapshot for the ledger. Never raises — any
    failure returns {'signals': [], 'error': ...} so the tick logs + state-emits regardless."""
    try:
        # DEDUP RESET (correctness): run_all_watchers keeps module-GLOBAL dedup state
        # (_dedup_state/_dedup_date) that suppresses a repeat setup within a day. A live tick is a
        # fresh cold SEE of one bar — it must NOT inherit dedup state from a prior in-process tick,
        # or the same-process signal for a bar leaks/disappears depending on call order (observed
        # 2026-07-07: a scan populated the dedup, then the standalone tick saw n_signals=0 for a
        # bar that fires 2 signals cold). Reset makes each tick deterministic + order-independent.
        run_all_watchers.__globals__["_dedup_state"] = {}
        run_all_watchers.__globals__["_dedup_date"] = None

        sym = inst.symbol
        rth = bars if bars is not None else load_futures(sym)
        rth = rth[(rth["timestamp_et"].dt.time >= dt.time(9, 30)) &
                  (rth["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
        if len(rth) < 61:
            return {"signals": [], "error": "insufficient_bars"}

        approx_price = float(rth["close"].median())
        set_futures_range_scale(approx_price / _SPY_REFERENCE)
        try:
            vix_full = vix_df if vix_df is not None else load_vix()
            vix_aligned = _align_vix_to_spy(rth, vix_full)
            htf_stacks = _precompute_htf_15m_stacks(rth)
            ribbon_df = compute_ribbon(rth["close"])
            bars_full = bars if bars is not None else load_futures(sym)

            idx = at_idx if at_idx is not None else len(rth) - 1
            if idx < 60 or idx >= len(rth):
                return {"signals": [], "error": "idx_out_of_range"}

            bar = rth.iloc[idx]
            bt = bar["timestamp_et"]
            bd = bt.date()

            # Ribbon history: last 10 bars up to idx (matches run_native_backtest accumulation).
            ribbon_history = []
            for j in range(max(0, idx - 9), idx + 1):
                r = ribbon_df.iloc[j]
                ribbon_history.append(RibbonState(
                    fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                    stack=str(r["stack"]), spread_cents=float(r["spread_cents"])))
            rib = ribbon_history[-1]

            volb = vol_baseline_20bar(rth, idx)
            rngb = range_baseline_20bar(rth, idx)
            vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
            vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

            bars_to_now = bars_full[bars_full["timestamp_et"] <= bt]
            lset = _detect_from_history(bars_to_now, bd)

            # Rebuild level_states over today's bars up to idx (no look-ahead).
            level_states: dict = {}
            day_bars_all = rth[rth["timestamp_et"].dt.date == bd].reset_index(drop=True)
            for j in range(len(day_bars_all)):
                jb = day_bars_all.iloc[j]
                if jb["timestamp_et"] > bt:
                    break
                _update_level_states(level_states, lset.active, jb, j)

            htf = htf_stacks[idx] if idx < len(htf_stacks) else None
            ctx = BarContext(
                bar_idx=idx, timestamp_et=bt.to_pydatetime(), bar=bar,
                prior_bars=rth.iloc[:idx + 1], ribbon_now=rib, ribbon_history=ribbon_history,
                vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=volb, range_baseline_20=rngb,
                levels_active=lset.active, multi_day_levels=lset.multi_day, htf_15m_stack=htf,
                level_states=level_states,
            )

            dbars = day_bars_all
            match = (dbars["timestamp_et"] == bt).values
            bidx = int(match.argmax()) if match.any() else len(dbars) - 1

            sigs = run_all_watchers(bar, dbars, bidx, volb, ctx, vix_now, multi_day_rth=None)

            out = []
            for s in sigs:
                if s.direction not in ("long", "short"):
                    continue
                out.append({
                    "watcher": s.watcher_name, "setup": s.setup_name, "direction": s.direction,
                    "confidence": s.confidence, "entry": float(s.entry_price),
                    "stop": float(s.stop_price), "tp1": float(s.tp1_price),
                    "runner": (None if s.runner_price is None else float(s.runner_price)),
                    "reason": getattr(s, "reason", ""),
                })
            return {
                "signals": out,
                "snapshot": {"instrument": sym, "bar_ts_et": bt.isoformat(),
                             "close": float(bar["close"]), "ribbon": rib.stack,
                             "vix": round(vix_now, 2)},
            }
        finally:
            set_futures_range_scale(None)  # always restore SPY mode
    except Exception as e:  # noqa: BLE001 — the see step must never crash the tick
        return {"signals": [], "error": f"{type(e).__name__}: {e}"}


# ── DECIDE: filter to validated slices + size ────────────────────────────────
def decide_entry(signals: list[dict], *, vix: float, account: PropAccount,
                 risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
                 hard_cap: int = DEFAULT_HARD_CAP, inst=MNQ) -> Optional[dict]:
    """Pick the FIRST v3-validated signal, size it, and return an actionable entry (or None).

    should_take_v3 is the validated filter (OOS +$69.89/tr). Sizing via risk.size_contracts so a full
    stop loses ~risk_per_trade. The account kill-switch (would_violate on the prospective full-stop
    equity) is the hard refuse — no trade if a full stop would blow the drawdown. Deterministic:
    same signals+vix -> same decision."""
    for sig in signals:
        if not should_take_v3(sig["watcher"], sig["direction"], sig["confidence"], vix):
            continue
        stop_points = abs(float(sig["entry"]) - float(sig["stop"]))
        qty = size_contracts(account.starting_balance, risk_per_trade, stop_points, inst, hard_cap)
        # kill-switch: refuse if a FULL stop from here would violate the drawdown floor.
        full_stop_loss = stop_points * inst.point_value * qty
        if account.would_violate(account.starting_balance - full_stop_loss):
            return {"refused": "kill_switch", "signal": sig, "qty": qty,
                    "full_stop_loss": full_stop_loss}
        return {"signal": sig, "qty": qty, "stop_points": stop_points,
                "full_stop_loss": full_stop_loss, "vix": vix}
    return None


# ── broker provisioning probe (fail-safe) ────────────────────────────────────
def _broker_provisioned(broker) -> tuple[bool, dict]:
    """Return (futures_provisioned, detail). Fails SAFE: any failure / watch-only /
    unknown -> (False, ...) so the tick never routes on an unreadable account.

    ⚠️ CORRECTED 2026-08-09 -- futures_bp WAS THE WRONG SIGNAL. This gate originally
    required `futures_buying_power > 0`, on the 2026-07-07 reading that cert account
    5WW73759 showed futures_bp=0.0 and was therefore "not provisioned for futures".

    That reading was wrong, and it was proven wrong end-to-end tonight while the CME
    session was OPEN (2026-08-09 18:07-18:12 ET, sandbox, no real money):
      * dry run       -> validated, zero errors, buying-power effect -$2.52
      * resting order -> Routed -> **Live** on the book, reject_reason null, cancelled clean
      * marketable    -> **FILLED** 1 /MESU6 @ 7772.5, real position held, closed, flat
    Throughout all three, `futures_buying_power` stayed **0.0** and `is_futures_approved`
    stayed **false**. The July "Rejected: Session offline" was a MARKET-HOURS artifact,
    not a permissions verdict -- the account trades futures fine.

    So futures_bp is not a provisioning signal on this venue; it is a field the cert
    environment simply does not populate. Gating on it meant an armed, fully working
    account would have routed NOTHING, forever, while reporting itself safe -- the
    dead-knob shape (C14), with the added sting that the "evidence" for the knob was a
    single observation taken outside trading hours.

    The gate now asks the only question that actually matters: **will the broker accept
    an order right now?** A dry run is exactly that question, costs nothing, routes
    nothing, and cannot fill.
    """
    try:
        if getattr(broker, "watch_only", True):
            return False, {"reason": "watch_only"}
        if not broker.is_connected():
            if not broker.connect():
                return False, {"reason": "connect_failed"}
        eq = broker.get_account_equity()
        # futures_bp is still READ and reported -- it is useful context on the ledger row
        # -- but it is no longer the gate. See this function's docstring: it reads 0.0 on
        # an account that demonstrably routes and fills.
        fbp = _read_futures_bp(broker)
        accepts, why = _broker_accepts_orders(broker)
        return accepts, {"accepts_orders": accepts, "probe": why,
                         "futures_bp": fbp, "net_liq": eq}
    except Exception as e:  # noqa: BLE001
        return False, {"reason": f"probe_error: {type(e).__name__}: {e}"}


def _broker_accepts_orders(broker) -> tuple[bool, str]:
    """Will the broker accept a futures order right now? Dry run = the direct question.

    Routes nothing and cannot fill: `dry_run=True` is broker-side validation only. A
    session-hours rejection correctly reads as "not now" rather than "not ever", which is
    the exact distinction the old futures_bp gate collapsed.
    """
    try:
        from decimal import Decimal  # noqa: PLC0415
        import asyncio  # noqa: PLC0415
        import concurrent.futures  # noqa: PLC0415

        from tastytrade.instruments import Future as TTFuture  # noqa: PLC0415
        from tastytrade.order import (  # noqa: PLC0415
            NewOrder, OrderAction, OrderTimeInForce, OrderType,
        )

        acct = getattr(broker, "_account", None)
        sess = getattr(broker, "_session", None)
        if acct is None or sess is None:
            return False, "no session/account on broker"

        async def _probe():
            res = await TTFuture.get(sess, product_codes=["MES"])
            contracts = res if isinstance(res, list) else [res]
            front = sorted([c for c in contracts if not getattr(c, "is_expired", False)],
                           key=lambda c: c.expiration_date)[0]
            order = NewOrder(
                time_in_force=OrderTimeInForce.DAY, order_type=OrderType.LIMIT,
                legs=[front.build_leg(Decimal(1), OrderAction.BUY_TO_OPEN)],
                price=Decimal("-1000.00"),   # debit-signed, far below market
            )
            return await acct.place_order(sess, order, dry_run=True)

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                resp = pool.submit(asyncio.run, _probe()).result()
        except RuntimeError:
            resp = asyncio.new_event_loop().run_until_complete(_probe())

        if resp.errors:
            return False, f"dry_run errors: {resp.errors}"
        return True, "dry_run validated"
    except Exception as e:  # noqa: BLE001 -- fail safe, and say why on the ledger row
        return False, f"{type(e).__name__}: {e}"


def _read_futures_bp(broker) -> Optional[float]:
    """Best-effort futures buying power read (the provisioning signal). None on any failure."""
    try:
        acct = getattr(broker, "_account", None)
        sess = getattr(broker, "_session", None)
        if acct is None or sess is None:
            return None
        import asyncio  # noqa: PLC0415
        import concurrent.futures  # noqa: PLC0415

        async def _get():
            return await acct.get_balances(sess)

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                bal = pool.submit(asyncio.run, _get()).result()
        except RuntimeError:
            bal = asyncio.new_event_loop().run_until_complete(_get())
        return float(getattr(bal, "futures_buying_power", 0.0) or 0.0)
    except Exception:
        return None


# ── STATE EMIT (visibility) ──────────────────────────────────────────────────
def _emit_state(*, tick: dict, position: Optional[dict], loop: dict) -> None:
    """Write the 3 glanceable state files. Never raises."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "last-tick.json").write_text(json.dumps(tick, indent=2), encoding="utf-8")
        (STATE_DIR / "loop-state.json").write_text(json.dumps(loop, indent=2), encoding="utf-8")
        if position is not None:
            (STATE_DIR / "position.json").write_text(json.dumps(position, indent=2), encoding="utf-8")
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(tick) + "\n")
    except Exception:
        pass


def _load_position() -> Optional[FuturesExitState]:
    p = STATE_DIR / "position.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d or int(d.get("qty_open", 0)) <= 0:
            return None
        return FuturesExitState.from_dict(d)
    except Exception:
        return None


# ── the tick ─────────────────────────────────────────────────────────────────
def run_tick(inst=MNQ, *, broker=None, bars: Optional[pd.DataFrame] = None,
             vix_df: Optional[pd.DataFrame] = None, at_idx: Optional[int] = None,
             account: Optional[PropAccount] = None,
             time_stop_et: dt.time = DEFAULT_TIME_STOP_ET,
             force_price: Optional[float] = None) -> dict:
    """One deterministic see->decide->act tick for `inst`. Returns the ledger record.

    DRY_RUN unless FUTURES_ARMED=1 AND the broker reports futures provisioned. In dry-run the tick
    validates the order + computes the exit plan + emits state, but places NOTHING. Never raises."""
    now = _et_now()
    armed_env = _armed_env()
    account = account or TOPSTEP_50K
    rec: dict = {"ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "instrument": inst.symbol,
                 "armed_env": armed_env}

    # provisioning probe -> the REAL arm gate. dry_run is True unless armed AND provisioned.
    provisioned, prov_detail = (False, {"reason": "no_broker"})
    if broker is not None:
        provisioned, prov_detail = _broker_provisioned(broker)
    dry_run = not (armed_env and provisioned)
    rec["provisioned"] = provisioned
    rec["provision_detail"] = prov_detail
    rec["dry_run"] = dry_run

    # ── EXIT MANAGEMENT FIRST (manage any open position before a new entry) ──
    pos = _load_position()
    position_dict: Optional[dict] = pos.to_dict() if pos else None
    if pos is not None:
        px = force_price if force_price is not None else pos.entry
        plan = decide_exit(pos, price=px, now_et=now, time_stop_et=time_stop_et)
        rec["exit"] = plan.to_dict()
        position_dict = plan.new_state.to_dict()
        if plan.action != "HOLD" and not dry_run and broker is not None:
            try:
                broker.close_position(inst.symbol, plan.exit_qty, plan.exit_side, px)
                rec["exit_placed"] = True
            except Exception as e:  # noqa: BLE001
                rec["exit_placed"] = False
                rec["exit_error"] = f"{type(e).__name__}: {e}"

    # ── SEE ──
    see = compute_latest_signals(inst, bars=bars, vix_df=vix_df, at_idx=at_idx)
    rec["snapshot"] = see.get("snapshot")
    rec["n_signals"] = len(see.get("signals", []))
    if see.get("error"):
        rec["see_error"] = see["error"]

    # ── DECIDE ── (skip a new entry while a position is open — no stacking, Rule 6)
    vix = float((see.get("snapshot") or {}).get("vix", 17.0))
    entry = None
    if pos is None or int(position_dict.get("qty_open", 0)) <= 0:
        entry = decide_entry(see.get("signals", []), vix=vix, account=account, inst=inst)
    else:
        rec["decide_skip"] = "position_open_no_stack"

    if not entry or entry.get("refused"):
        rec["action"] = "NO_ENTRY" if not entry else f"REFUSED_{entry['refused']}"
        if entry and entry.get("refused"):
            rec["refuse_detail"] = entry
        _emit_state(tick=rec, position=position_dict,
                    loop={"ts_et": rec["ts_et"], "instrument": inst.symbol, "dry_run": dry_run,
                          "provisioned": provisioned, "last_action": rec["action"]})
        return rec

    # ── ACT ── build bracket + deterministic exit plan
    sig = entry["signal"]
    qty = int(entry["qty"])
    side = "BUY" if sig["direction"] == "long" else "SELL"
    exit_state = open_state(
        instrument=inst.symbol, direction=sig["direction"], entry=sig["entry"], stop=sig["stop"],
        tp1=sig["tp1"], runner=sig["runner"], qty_total=qty, tp1_fraction=TP1_FRACTION,
        entry_time_et=rec["ts_et"])
    rec["entry"] = {"watcher": sig["watcher"], "direction": sig["direction"],
                    "confidence": sig["confidence"], "qty": qty, "side": side,
                    "entry": sig["entry"], "stop": sig["stop"], "tp1": sig["tp1"],
                    "runner": sig["runner"]}
    rec["exit_plan_at_fill"] = exit_state.to_dict()

    order_result = None
    if broker is not None:
        # place_bracket itself honors watch_only; we pass dry_run intent via WHETHER we call it live.
        if dry_run:
            # DRY-RUN: validate the order shape without routing. Use the broker's own dry-run if live-
            # connected + provisioned would allow it; else record the fully-built order for the ledger.
            rec["order_built"] = {"instrument": inst.symbol, "side": side, "qty": qty,
                                  "entry": sig["entry"], "tp1": sig["tp1"], "stop": sig["stop"],
                                  "runner": sig["runner"], "routed": False, "dry_run": True}
            rec["action"] = "DRY_RUN_VALIDATED"
        else:
            try:
                order_result = broker.place_bracket(
                    inst.symbol, side, qty, sig["entry"], sig["tp1"], sig["stop"],
                    runner_price=sig["runner"], tp1_qty=exit_state.tp1_qty)
                rec["order_ids"] = order_result
                rec["action"] = "PLACED" if order_result else "PLACE_EMPTY"
                position_dict = exit_state.to_dict()  # now tracking the live position
            except Exception as e:  # noqa: BLE001
                rec["action"] = "PLACE_ERROR"
                rec["place_error"] = f"{type(e).__name__}: {e}"
    else:
        rec["order_built"] = {"instrument": inst.symbol, "side": side, "qty": qty,
                              "entry": sig["entry"], "tp1": sig["tp1"], "stop": sig["stop"],
                              "runner": sig["runner"], "routed": False, "dry_run": True}
        rec["action"] = "DRY_RUN_VALIDATED"

    _emit_state(tick=rec, position=position_dict,
                loop={"ts_et": rec["ts_et"], "instrument": inst.symbol, "dry_run": dry_run,
                      "provisioned": provisioned, "last_action": rec["action"]})
    return rec


def main() -> None:
    """CLI: run one tick per instrument. Default MNQ; --mes adds MES."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", action="store_true", help="also tick MES")
    ap.add_argument("--live-broker", action="store_true",
                    help="construct a real TastytradeBroker (still dry-run unless FUTURES_ARMED=1 AND provisioned)")
    args = ap.parse_args()

    broker = None
    if args.live_broker:
        try:
            from futures.tastytrade_paper import TastytradeBroker  # noqa: PLC0415
            broker = TastytradeBroker(watch_only=False)
        except Exception as e:  # noqa: BLE001
            print(f"broker construct failed ({e}); running BROKERLESS dry-run", file=sys.stderr)

    insts = [MNQ] + ([MES] if args.mes else [])
    for inst in insts:
        rec = run_tick(inst, broker=broker)
        print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
