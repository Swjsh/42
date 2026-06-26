"""exit_actuator -- the thin LIVE layer over exit_manager's pure core.

Per managed position, each tick this:
  1. reads the live open qty + the option quote (best=ask / worst=bid) from the broker,
  2. runs exit_manager.plan_exit_actions (the pure 5-stage walk),
  3. executes the resulting SELL_PARTIAL / SELL_ALL / RATCHET_STOP actions via fleet_broker,
  4. persists the new ExitState to the arm's exit-state ledger.

GATING (mirrors place_bracket / fleet_live discipline, fail-closed for trading):
  * WATCH (default, live=False): computes + persists the would-do actions, PLACES NOTHING.
  * LIVE (live=True): actually market-sells / replaces stops. Only the caller (heartbeat_core
    _execute or fleet_live, both already J-gated by ARMED / master-live + per-arm live) ever
    passes live=True.

State persistence: automation/state/fleet/{arm}/exit-state.json -- a dict keyed by option
symbol. The broker remains the source of truth for OPEN QTY (C11); this record only carries
the per-position exit-shape + evolving runner state (tp1_filled / runner_stop / hwm). A
missing/corrupt record is rebuilt from the entry on the next ENTRY, never guessed.

This module is import-safe (no side effects); fleet_broker is imported lazily so the pure
exit_manager core stays broker-free and unit-testable on its own.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import exit_manager as em

FLEET_DIR = Path(__file__).resolve().parent
ET = timezone(timedelta(hours=-4))


def _state_path(arm_id: str) -> Path:
    d = FLEET_DIR / arm_id
    d.mkdir(exist_ok=True)
    return d / "exit-state.json"


def load_states(arm_id: str) -> dict:
    """{symbol: ExitState} from the arm's exit-state ledger (empty on missing/corrupt)."""
    p = _state_path(arm_id)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict = {}
    for sym, d in (raw or {}).items():
        try:
            out[sym] = em.ExitState.from_dict(d)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def save_states(arm_id: str, states: dict) -> None:
    p = _state_path(arm_id)
    p.write_text(json.dumps({sym: st.to_dict() for sym, st in states.items()}, indent=2),
                 encoding="utf-8")


def register_entry(arm_id: str, *, symbol: str, side: str, entry_premium: float,
                   qty: int, exit_shape: dict, strategy: str = "") -> em.ExitState:
    """Persist a freshly-filled position's ExitState so the next tick can manage its
    scale-out. Called by the live actuator immediately after a bracket fill (the entry leg).
    Returns the new state (also written to the ledger)."""
    states = load_states(arm_id)
    st = em.ExitState.from_entry(symbol=symbol, side=side, entry_premium=entry_premium,
                                 qty=qty, exit_shape=exit_shape, strategy=strategy)
    states[symbol] = st
    save_states(arm_id, states)
    return st


def _now_et() -> datetime:
    return datetime.now(timezone.utc).astimezone(ET)


def manage_tick(arm_id: str, creds: dict, *, live: bool,
                ribbon_flip_back_fn=None, now_et: Optional[datetime] = None,
                broker=None) -> list[dict]:
    """Run ONE exit-management tick over EVERY managed position on this arm.

    For each persisted ExitState: read live qty + quote, plan the action, and (when live)
    execute. Returns a list of per-symbol result dicts (the WATCH/LIVE record). Prunes
    positions the broker shows flat (their lifecycle is done).

    `broker` is injectable for tests (defaults to the real fleet_broker). `ribbon_flip_back_fn`
    is an optional callable(symbol, side) -> bool that lets the caller feed the live
    ribbon-flip-back signal (heartbeat_core / fleet already compute the ribbon); when None
    the exit manager never force-exits on ribbon (premium/target/time stops still bind)."""
    if broker is None:
        import fleet_broker as broker  # lazy: keep the pure path broker-free
    now_dt = (now_et or _now_et())
    now_t = now_dt.time()
    states = load_states(arm_id)
    if not states:
        return []
    results: list[dict] = []
    changed = False
    for symbol, st in list(states.items()):
        open_qty = broker.get_position_qty(creds, symbol)
        if open_qty <= 0:
            # broker shows flat -> lifecycle complete, prune the record
            del states[symbol]
            changed = True
            results.append({"symbol": symbol, "open_qty": 0, "action": "FLAT_PRUNED"})
            continue
        hilo = broker.get_option_quote_hilo(creds, symbol)
        if hilo is None:
            results.append({"symbol": symbol, "open_qty": open_qty, "action": "HOLD",
                            "reason": "no_quote"})
            continue
        best_premium, worst_premium = hilo
        flip = bool(ribbon_flip_back_fn(symbol, st.side)) if ribbon_flip_back_fn else False
        dec = em.plan_exit_actions(st, best_premium=best_premium, worst_premium=worst_premium,
                                   open_qty=open_qty, now_et=now_t, ribbon_flip_back=flip)
        states[symbol] = dec.state
        changed = True
        executed = []
        for a in dec.actions:
            if a.kind in ("SELL_PARTIAL", "SELL_ALL"):
                res = (broker.market_sell(creds, symbol=symbol, qty=a.qty, live=live)
                       if live else {"_skipped": "WATCH"})
                executed.append({"kind": a.kind, "qty": a.qty, "stage": a.stage,
                                 "reason": a.reason, "placed": live and not res.get("_error")
                                 and not res.get("_refused") and not res.get("_skipped"),
                                 "broker": res})
            elif a.kind == "RATCHET_STOP":
                # The runner stop ratchet is realized lazily: we PERSIST the new stop level
                # in the ExitState and let the per-tick worst<=stop check enforce it (a
                # tick-managed stop, not a resting broker order), so no order_id plumbing is
                # required and a missed tick can't strand a stale resting stop. Recorded for
                # the ledger / observability.
                executed.append({"kind": "RATCHET_STOP", "stage": a.stage,
                                 "new_stop_premium": a.new_stop_premium, "reason": a.reason,
                                 "enforced": "tick_managed"})
        if dec.closes_position:
            del states[symbol]  # fully closed this tick -> prune
        results.append({"symbol": symbol, "open_qty": open_qty,
                        "best_premium": best_premium, "worst_premium": worst_premium,
                        "tp1_filled": dec.state.tp1_filled,
                        "runner_stop": dec.state.runner_stop_premium,
                        "actions": executed,
                        "mode": "LIVE" if live else "WATCH"})
    if changed:
        save_states(arm_id, states)
    return results
