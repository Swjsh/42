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
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "setup" / "scripts"))
from et_clock import ET_TZ as ET  # DST-aware ET (TZ-SYSTEMIC fix: was timezone(timedelta(hours=-4)))
import exit_manager as em

FLEET_DIR = Path(__file__).resolve().parent


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


def _cooldown_path(arm_id: str) -> Path:
    d = FLEET_DIR / arm_id
    d.mkdir(exist_ok=True)
    return d / "extra-setup-cooldown.json"


def load_last_entry_bars(arm_id: str) -> dict:
    """{setup_name: trigger_bar_et_iso} -- the LAST trigger-bar timestamp an extra-setup
    ATTEMPTED (armed placement, dry or live -- see _TAKEN in heartbeat_core.py) an entry on,
    per setup. Read by heartbeat_core._route_extra_setups (EXTRA-SIGNAL-CHURN-COOLDOWN,
    2026-07-20) to refuse a SAME-BAR re-entry after a stop-out reopens the account to flat:
    the churn exhibit (09:51/09:54/09:55 ET 3x 748C entries, one stopped-out trigger bar,
    net -$87) fired repeatedly within a SINGLE closed 5m bar once the free-model veto let
    one tick through -- a same-bar re-entry, not a genuinely new signal. Requiring the trigger
    bar to ADVANCE before the SAME setup can re-enter is a structural fix with no numeric
    knob to hand-pick (the "requires-new-trigger-bar" option named in the queue item, chosen
    over "min N bars" specifically because there is no existing trade population to
    pre-register a duration against -- this is a brand-new mechanism, not a re-tunable
    parameter). Empty on missing/corrupt (fail-open -- an unreadable cooldown file can never
    block a legitimate entry, only ever fail toward "no cooldown recorded")."""
    p = _cooldown_path(arm_id)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def record_entry_bar(arm_id: str, setup_name: str, trigger_bar_et: str) -> None:
    """Persist the trigger-bar timestamp `setup_name` just attempted an entry on (see
    load_last_entry_bars for the full rationale). Fail-safe: any write error is swallowed --
    this is a churn-prevention side-record, never allowed to abort an entry that already
    placed/would-place."""
    if not setup_name or not trigger_bar_et:
        return
    try:
        states = load_last_entry_bars(arm_id)
        states[str(setup_name)] = str(trigger_bar_et)
        _cooldown_path(arm_id).write_text(json.dumps(states, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- never abort the caller's already-placed entry
        pass


def same_bar_cooldown_active(arm_id: str, setup_name: "str | None",
                             trigger_bar_et: "str | None") -> bool:
    """True iff `setup_name` already attempted an entry on THIS exact trigger bar for this
    arm (per load_last_entry_bars) -- the SAME-BAR re-entry guard. False (never blocks) on
    any missing input or read error -- fail-open by construction."""
    if not setup_name or not trigger_bar_et:
        return False
    try:
        last = load_last_entry_bars(arm_id)
    except Exception:  # noqa: BLE001
        return False
    return str(last.get(str(setup_name), "")) == str(trigger_bar_et)


def register_entry(arm_id: str, *, symbol: str, side: str, entry_premium: float,
                   qty: int, exit_shape: dict, strategy: str = "",
                   trigger_level: Optional[float] = None,
                   structure_stop_enabled: bool = False) -> em.ExitState:
    """Persist a freshly-filled position's ExitState so the next tick can manage its
    scale-out. Called by the live actuator immediately after a bracket fill (the entry leg).
    Returns the new state (also written to the ledger).

    trigger_level / structure_stop_enabled (2026-07-09, additive, both default to today's
    exact behavior): forwarded straight to ExitState.from_entry, which resolves stop_mode
    ONCE here at registration -- see exit_manager.py for the flag-gated resolution rule."""
    states = load_states(arm_id)
    st = em.ExitState.from_entry(symbol=symbol, side=side, entry_premium=entry_premium,
                                 qty=qty, exit_shape=exit_shape, strategy=strategy,
                                 trigger_level=trigger_level,
                                 structure_stop_enabled=structure_stop_enabled)
    states[symbol] = st
    save_states(arm_id, states)
    return st


def reanchor_entry(arm_id: str, *, symbol: str, true_entry_premium: Optional[float],
                   reason: str = "fill_reconcile") -> "Optional[em.ExitState]":
    """ENTRY-ANCHOR-TO-FILL FIX (2026-08-03). register_entry (above) necessarily seeds
    entry_premium from the PRE-FILL marketable-limit price (entry_px = ask + buffer,
    fleet_broker.marketable_limit_price) -- the true fill is not known until the broker
    confirms it, which happens strictly AFTER registration in both live callers
    (fleet_live.py#_place_live places the order then registers synchronously; heartbeat_
    core.py#_execute registers synchronously, then the CALLER polls via _reconcile_exec).
    Whenever the fill prices BETTER than the limit -- the common case, confirmed against
    real broker fills 2026-08-03 (safe-3 limit 0.42/fill 0.37, risky-1 limit 0.41/fill
    0.37) and against the 105-fill population in
    analysis/recommendations/entry-execution-cost-2026-08-02.json (98.1% of real fills,
    avg 4.11c/contract) -- every threshold DERIVED from entry_premium is anchored HIGH:
    TP1 needs MORE favorable movement than it should before the partial take-profit (and
    the post-TP1 profit-lock arm, profit_lock_arm_scope="post_tp1") engages, leaving MORE
    size exposed to the catastrophe stop for LONGER than the validated exit shape intends.
    This is the exact mechanism behind J's stated #1 fear ("when it crashes, we end up
    selling the trade and not making any money") -- see analysis/staged/
    entry-anchor-fix-2026-08-03.diff's cover doc for the live worked example
    (safe-3, 2026-08-03: TP1 sat at $0.84 instead of the true $0.74 while price traded
    above $0.74 for several minutes with zero trail armed).

    This function re-anchors ONCE, immediately after the fill is confirmed, correcting
    entry_premium plus every price DERIVED from it via the EXACT SAME formula
    ExitState.from_entry already uses (`runner_stop_premium = entry_premium * (1 +
    premium_stop_pct)`) -- it never re-resolves stop_mode/trigger_level/premium_stop_pct
    themselves (those stay frozen-once per from_entry's own "never flaps mid-trade"
    contract; only the PRICE they are anchored to moves).

    CONSERVATIVE BY DESIGN -- returns None (caller logs loudly, keeps the limit anchor)
    whenever:
      * no persisted ExitState exists for `symbol` under `arm_id` (registration itself
        failed/raced -- nothing to re-anchor)
      * true_entry_premium is None or <= 0 (fill unknown/unparseable after polling --
        NEVER guess; the limit-anchored state from register_entry stands as-is, which is
        exactly today's pre-fix behavior, not a regression)
      * st.tp1_filled is already True, OR st.profit_lock_armed is already True -- a REAL
        tick already took a scale-out/lock action against the old anchor; retroactively
        moving entry_premium underneath an already-executed partial sell would desync the
        broker's actual proceeds from this ledger's bookkeeping. The trade rides out under
        its original (limit) anchor rather than risk corrupting an in-flight managed
        position. In practice this is a non-issue: re-anchoring happens within the same
        tick / immediately after the fill poll, long before either could plausibly have
        advanced (manage_tick only runs at the START of the NEXT tick -- see fleet_live.
        run()'s exit-management-pass-runs-first ordering).

    hwm_premium (the high-water mark used to arm the profit lock) is raised/lowered to
    true_entry_premium ONLY when it has not yet moved past the OLD (wrong) entry_premium
    -- i.e. no real tick has advanced it since registration. If a real tick already
    pushed hwm_premium above the old anchor, it is left untouched (never regressed --
    lowering an already-achieved high-water mark could incorrectly un-arm a legitimately
    armed profit lock).

    Immutable per coding-style: builds a NEW ExitState via dataclasses.replace, never
    mutates `st` in place.
    Guard: backtest/tests/test_entry_anchor_to_fill_2026_08_03.py.
    """
    if true_entry_premium is None:
        return None
    try:
        true_entry_premium = float(true_entry_premium)
    except (TypeError, ValueError):
        return None
    if true_entry_premium <= 0:
        return None
    states = load_states(arm_id)
    st = states.get(symbol)
    if st is None:
        return None
    if st.tp1_filled or st.profit_lock_armed:
        return None
    old_entry = st.entry_premium
    new_hwm = (true_entry_premium if (st.hwm_premium is None or st.hwm_premium <= old_entry)
              else st.hwm_premium)
    new_runner_stop = round(true_entry_premium * (1.0 + st.premium_stop_pct), 4)
    new_st = replace(st, entry_premium=true_entry_premium,
                     runner_stop_premium=new_runner_stop, hwm_premium=new_hwm)
    states[symbol] = new_st
    save_states(arm_id, states)
    return new_st


def _now_et() -> datetime:
    return datetime.now(timezone.utc).astimezone(ET)


def describe_stop(state: Optional[em.ExitState], *,
                  fallback_price: Optional[float] = None,
                  fallback_pct: Optional[float] = None) -> str:
    """RENDER-ONLY (2026-07-09 visibility build, OP-33c): the plan/placement log's human-
    readable stop TRUTH -- fixes the known cosmetic bug (STATUS.md 2026-07-09 ~16:20 ET:
    "plan-log 'stop' shows the -20% fallback even in structure mode"). Reads the ALREADY-
    RESOLVED ExitState (stop_mode/trigger_level/catastrophe_stop_pct are resolved ONCE, at
    entry, by the FROZEN exit_manager.ExitState.from_entry) -- this function never re-derives
    the structure/premium resolution itself, so the rendered text can never drift from the
    real decision; it only formats what from_entry already decided.

    Structure mode -> 'STRUCTURE@<level> (cat <pct>)', read straight off the resolved state
    (the ONLY case this function needs the state for). Premium mode -- including state=None,
    i.e. registration was skipped/failed (a broker error before any fill) or a caller
    previewing before a real entry exists -- ALWAYS renders the CALLER's own pre-resolution
    price/pct, never state.runner_stop_premium: the caller's numeric "stop"/"premium_stop_pct"
    fields are mid-based (the pre-fill estimate logged alongside this string), while
    ExitState.runner_stop_premium is entry_px-based (the real fill price) -- deliberately
    DIFFERENT numbers for a different purpose (C11's broker-is-truth reconciliation happens
    tick-to-tick, not at this log line). Using the caller's own number keeps this string
    internally consistent with the "stop"/"premium_stop_pct" fields returned alongside it
    (never two different numbers claiming to be the same stop), and is byte-identical to
    every caller's pre-visibility-build rendering. Pure formatting; never read by any
    decision path."""
    if state is not None and state.stop_mode == "structure":
        lvl = state.trigger_level
        lvl_s = f"{float(lvl):.2f}" if lvl is not None else "?"
        return f"STRUCTURE@{lvl_s} (cat {state.catastrophe_stop_pct:+.0%})"
    if fallback_price is not None and fallback_pct is not None:
        try:
            return f"{float(fallback_price):.2f} ({float(fallback_pct):+.0%})"
        except (TypeError, ValueError):
            return str(fallback_price)
    return "n/a"


def make_ribbon_flip_fn(ribbon_stack: Optional[str]):
    """Single source for the v15.3 chart-stop-PRIMARY ribbon-flip-back invalidation (G14).

    The producer (backtest/lib/ribbon.py) emits stack == 'BULL'|'BEAR'|'MIXED'|'WARMUP'|
    'UNKNOWN'. A PUT position exits when the stack turns BULL; a CALL when it turns BEAR;
    MIXED/WARMUP/UNKNOWN never flip (loss-of-stack is not an opposite-direction reversal).
    Returns None when the stack is unknown/absent (fail-open: the -50% catastrophe cap,
    targets and time stops still run). Shared by heartbeat_core (core accounts) AND
    fleet_live (fleet arms) so the two exit paths cannot drift (C14/G14 parity)."""
    if not ribbon_stack:
        return None

    def fn(symbol: str, side: str) -> bool:  # noqa: ANN001
        return ribbon_stack == ("BULL" if side == "P" else "BEAR")
    return fn


def manage_tick(arm_id: str, creds: dict, *, live: bool,
                ribbon_flip_back_fn=None, now_et: Optional[datetime] = None,
                broker=None, time_stop_et=None,
                last_closed_5m_close: Optional[float] = None) -> list[dict]:
    """Run ONE exit-management tick over EVERY managed position on this arm.

    For each persisted ExitState: read live qty + quote, plan the action, and (when live)
    execute. Returns a list of per-symbol result dicts (the WATCH/LIVE record). Prunes
    positions the broker shows flat (their lifecycle is done).

    `broker` is injectable for tests (defaults to the real fleet_broker). `ribbon_flip_back_fn`
    is an optional callable(symbol, side) -> bool that lets the caller feed the live
    ribbon-flip-back signal (heartbeat_core / fleet already compute the ribbon); when None
    the exit manager never force-exits on ribbon (premium/target/time stops still bind).

    `time_stop_et` is the params.json ``time_stop_et`` value (an "HH:MM" str / datetime.time /
    None). FIX (2026-07-07): previously the call to plan_exit_actions passed NO time_stop_et
    so the hard-coded 15:50 always won and the params key was DEAD. Now the caller's param is
    parsed (fail-safe to 15:50 on missing/malformed -- never widens past close) and forwarded
    to the pure core so the knob is live. Guard: test_audit_fix_exit.py.

    `last_closed_5m_close` (2026-07-09, STRUCTURE-STOP) is the latest CLOSED 5m SPY bar's
    close, or None when the caller's own feed is missing/stale -- forwarded verbatim to
    plan_exit_actions, which only consults it for a position whose stop_mode resolved to
    "structure" at entry (every other position ignores it, so omitting this kwarg is a
    no-op -- existing callers are unaffected)."""
    if broker is None:
        import fleet_broker as broker  # lazy: keep the pure path broker-free
    stop_t = em.parse_time_stop_et(time_stop_et)
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
            # VISIBILITY (2026-07-09, additive/render-only, OP-33c): carry the pruned
            # position's resolved stop_mode/trigger_level into the log row even though the
            # ledger entry is gone -- a reader scanning decisions.jsonl for "how was this
            # position managed" must not lose that fact the tick it closes.
            results.append({"symbol": symbol, "open_qty": 0, "action": "FLAT_PRUNED",
                            "stop_mode": st.stop_mode, "trigger_level": st.trigger_level})
            continue
        hilo = broker.get_option_quote_hilo(creds, symbol)
        if hilo is None:
            results.append({"symbol": symbol, "open_qty": open_qty, "action": "HOLD",
                            "reason": "no_quote",
                            "stop_mode": st.stop_mode, "trigger_level": st.trigger_level})
            continue
        best_premium, worst_premium = hilo
        # D2 (2026-07-07): adopted MANUAL positions are cap-only — the engine does NOT impose
        # a ribbon-flip (strategy) exit on a trade J originated; only the -50% cap + 15:50
        # flatten manage it. J drives the exit. Everything else keeps the v15.3 ribbon-flip.
        flip = (bool(ribbon_flip_back_fn(symbol, st.side))
                if (ribbon_flip_back_fn and st.strategy != "adopted_manual") else False)
        dec = em.plan_exit_actions(st, best_premium=best_premium, worst_premium=worst_premium,
                                   open_qty=open_qty, now_et=now_t, ribbon_flip_back=flip,
                                   time_stop_et=stop_t, last_closed_5m_close=last_closed_5m_close)
        states[symbol] = dec.state
        changed = True
        executed = []
        sell_placed_ok = True   # tracks whether EVERY sell action this tick was actually
                                 # accepted (or we're in WATCH/preview) -- gates whether a
                                 # closes_position tick is safe to prune below (F7 fix).
        for a in dec.actions:
            if a.kind in ("SELL_PARTIAL", "SELL_ALL"):
                # F7-EXIT-SELL-ALL-REFIRE (2026-07-18): before submitting a REAL sell,
                # check whether a prior tick's sell order for this symbol is still
                # resting/open on the broker -- a slow fill, or a network timeout AFTER
                # Alpaca actually accepted the order, would otherwise cause this tick to
                # stack a DUPLICATE market sell on top of one that already landed.
                # getattr-guarded: a broker double that doesn't implement the check (e.g.
                # existing test fakes) fails OPEN to today's exact pre-guard behavior.
                dupe_check = getattr(broker, "open_sell_orders", None)
                resting = (dupe_check(creds, symbol) if (live and dupe_check) else [])
                if resting:
                    res = {"_skipped": f"duplicate guard: {len(resting)} sell order(s) "
                                        f"already resting for {symbol}"}
                    placed = False
                else:
                    res = (broker.market_sell(creds, symbol=symbol, qty=a.qty, live=live)
                           if live else {"_skipped": "WATCH"})
                    placed = live and not res.get("_error") and not res.get("_refused") \
                        and not res.get("_skipped")
                if live and not placed:
                    sell_placed_ok = False
                executed.append({"kind": a.kind, "qty": a.qty, "stage": a.stage,
                                 "reason": a.reason, "placed": placed,
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
        # F7 fix: only prune the tracked position when the close is either a WATCH-mode
        # preview (nothing was actually placed, so nothing to reconcile) or every SELL_ALL
        # this tick was genuinely accepted broker-side. A skipped-as-duplicate or failed
        # sell must NOT drop tracking -- plan_exit_actions is idempotent-on-a-missed-tick
        # by design (its own docstring), so leaving the state in place lets the NEXT tick
        # re-derive the same close decision and either retry (real failure) or defer to the
        # resting order (duplicate) -- see the dupe-guard above. Before this fix, ANY
        # closes_position tick pruned unconditionally, so a failed/errored SELL_ALL
        # permanently orphaned the position from exit management (worse than a re-fire --
        # a silent forget) until the 15:55 ET EOD flatten backstop caught it.
        if dec.closes_position and (not live or sell_placed_ok):
            del states[symbol]  # fully closed (or WATCH preview) this tick -> prune
        results.append({"symbol": symbol, "open_qty": open_qty,
                        "best_premium": best_premium, "worst_premium": worst_premium,
                        "tp1_filled": dec.state.tp1_filled,
                        "runner_stop": dec.state.runner_stop_premium,
                        "actions": executed,
                        "mode": "LIVE" if live else "WATCH",
                        # VISIBILITY (2026-07-09, additive/render-only, OP-33c): the TRUTH
                        # this position is actually managed under. stop_mode/trigger_level
                        # are frozen at entry (exit_manager.ExitState.from_entry resolves
                        # them ONCE, never re-derived here) so they cannot drift from the
                        # real decision; last_closed_5m_close is the tick-level feed value
                        # THIS call received (None whenever the caller's own feed was
                        # stale/absent -- see exit_manager._structure_stop_hit's fail-open).
                        # Purely additive reporting -- `actions` above is computed from
                        # `dec` BEFORE this dict exists, so these keys can never change
                        # which actions fire (vary-and-assert: test_exit_actuator.py
                        # test_visibility_fields_are_additive_actions_unchanged).
                        "stop_mode": dec.state.stop_mode,
                        "trigger_level": dec.state.trigger_level,
                        "last_closed_5m_close": last_closed_5m_close})
    if changed:
        save_states(arm_id, states)
    return results
