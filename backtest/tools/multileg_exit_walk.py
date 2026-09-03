#!/usr/bin/env python
"""multileg_exit_walk.py -- a replay that actually models SCALE-OUTS.

WHY THIS EXISTS (2026-08-11). `ladder_day_replay.replay_fill` breaks on the FIRST action and
returns one exit price for the whole position. That is fine for a pure stop question, and it is
WRONG for anything involving tranches: a TP1 partial gets scored as a full exit, so the runner's
upside vanishes. The tell that caught it was a tp1_qty_fraction sweep where 50% / 67% / 80% all
returned byte-identical totals -- impossible if partial sells were being modeled. Every number
that harness produced about TP1 level or sell fraction was meaningless and was thrown out.

WHAT THIS DOES DIFFERENTLY
  - carries open_qty across bars
  - SELL_PARTIAL reduces qty and the walk CONTINUES with the remainder
  - SELL_ALL closes the remainder and stops
  - accumulates realized P&L leg by leg, so TP1 + runner is priced as two legs, not one
  - reports the legs so a reader can see WHERE the money came from

This is also the harness J's N-tranche scale-out ("sell 5 to get the money back, 3 on the next
dump, hold 2, then 1 for a home run") has to be validated in before any engine change -- the
current exit_manager can only express TWO tranches (tp1_qty + runner_qty), so the study has to
come first and prove the shape is worth the build.

SAME DISCLOSURES as the sibling harness, they do not go away:
  1. OPRA 5-minute bars; intra-bar high/low ORDER is unknowable. A bar that both sets a new HWM
     and breaches the resulting floor resolves optimistically (arm, then exit at the floor).
  2. NO SPY FEED -> structure/ribbon exits cannot fire. Positions the live engine closed on
     structure ride to a premium floor here, so the CONTROL arm is pessimistic vs live. Compare
     cells to each other (paired), and quote cell-vs-ACTUAL only with that caveat attached.
  3. Entries are held FIXED at the real broker fills. Exit-only counterfactual.
  4. Fills are modeled at the trigger price with no slippage. Real market sells slip; treat
     every absolute total as optimistic and the RANKING as the trustworthy part.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pandas as pd  # noqa: E402

import exit_manager as em  # noqa: E402

# MARKET-STAGE FILL BUG (found + quantified 2026-09-03, WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY).
# `ExitAction` (automation/state/fleet/exit_manager.py) carries NO `price` field -- so
# `getattr(a, "price", None)` below is ALWAYS None, and every non-tp1 SELL leg falls back to
# `state.runner_stop_premium or worst_in`. `runner_stop_premium` is set at ExitState.from_entry
# to `entry_premium * (1 + stop_pct)` (exit_manager.py:290) and is NEVER None after entry -- so
# `worst_in` (the bar price `fill_mode` is supposed to control) is DEAD CODE for every stage
# except tp1: structure_stop, ribbon_flip, and time_stop -- market-style exits that should fill
# at whatever the option was actually trading at when the live event fired -- instead silently
# price at the STATIC catastrophe/premium-stop level, every time, regardless of what stage
# actually triggered them or what fill_mode the caller asked for.
#
# MEASURED (backtest/tools/walker_fidelity.py, 132-row safe-2/bold-2 anchor, 2026-09-03): on
# losing anchor rows the replayed loss % clusters within ~1pt of the static stop level
# (structure-mode rows: -50.7% to -51.9%, vs a real catastrophe_stop_pct of -50%; premium-mode
# rows: -20.6% to -21.3%, vs a real premium_stop_pct of -20%) while the ACTUAL realized loss %
# on the SAME rows ranges from -6% to -55% -- the walker is not modeling WHERE the live exit
# fired, only pricing every non-tp1 exit as if it were the theoretical worst case. This explains
# why toggling `fill_mode` (extreme/close/mixed) left the loser-side aggregate ratio BIT-
# IDENTICAL in that study (1.5900444748546014, every time) -- `worst_in` was never reached.
#
# FIX, behind a flag defaulting to OLD (buggy) behavior for every existing caller (same
# discipline as exit_manager_walk.py's `all_exits_market` kwarg -- a fix here moves every
# historical cell in every study that has ever called `walk()`, so it does not flip silently):
# `market_stage_fill_fix=True` prices _MARKET_STAGES legs at the bar's own worst-case price
# (`worst_in`, already resolved per `fill_mode`) instead of the static stop level.
#
# FINISHED 2026-09-03 (WALKER-MARKET-STAGE-FILL-ROOT-FIX, same-day follow-up).
#
# FIRST DRAFT OF THIS FOLLOW-UP tried extending _MARKET_STAGES to every non-tp1 SELL stage
# exit_manager.py emits (also premium_stop, profit_lock_floor, trail, be_stop, runner_target),
# reasoning that a live market SELL always crosses the bid. MEASURED, then REVERTED: on the
# 43-row PDT anchor this made aggregate_ratio WORSE (4.0922 -> 4.8773, not better) -- driven
# almost entirely by premium_stop (stage-level abs error $516.90 -> $930.00; structure_stop and
# trail moved the other way but by far less). ROOT REASON, found by re-reading this module's OWN
# disclosure #1 above ("intra-bar high/low ORDER is unknowable... resolves optimistically (arm,
# then exit at the floor)"): premium_stop/profit_lock_floor/trail/be_stop are NUMERIC-THRESHOLD
# crossings of `runner_stop_premium` -- the live engine polls a quote once a minute and fires the
# instant its poll shows a cross, so the true fill sits close to the THRESHOLD, not the coarse
# 5-min bar's full worst extreme (which can wick far past the threshold on a move the once-a-
# minute poll never actually observed). `state.runner_stop_premium` (the OLD/default fallback,
# UNCHANGED here) already IS that threshold -- these 4 stages were never the bug; they only
# LOOKED implicated because the same generic fallback also caught the genuinely-broken stages
# below. structure_stop / ribbon_flip are different in kind: neither has a premium THRESHOLD to
# fall back to at all (a chart-level break / a categorical stack flip), so `worst_in` (this bar's
# own price, already resolved per `fill_mode`) is the best available proxy -- unchanged from the
# original 2026-09-03 ship, already measured as an improvement there.
#
# THE ACTUAL FIX THIS SESSION: time_stop only. It was folded into the original _MARKET_STAGES
# (priced at worst_in) alongside structure_stop/ribbon_flip, but time_stop is a CLOCK event, not
# a price cross -- there is no "worst_premium at the instant it fired" to reuse, because nothing
# about the option's price caused it to fire. The queue item's own instruction: fills at the
# bar's CLOSE at the stop minute (the prevailing price when the clock event landed), not the
# bar's low and not the static stop level. Verified read-only against
# automation/state/fleet/fleet_broker.py#get_option_quote_hilo (best_premium=ASK,
# worst_premium=BID -- confirms every live exit is an unconditional MARKET order, never a
# resting limit, same fact the sibling backtest/lib/exit_manager_walk.py#FILL-PRICE-CONVENTION
# note already established) and exit_actuator.py#manage_tick (the sole call site for both core
# and fleet arms) -- neither file edited.
#
# "Fills at the cap level only if the bar actually crossed it" (the catastrophe/premium cap) is
# STRUCTURAL, not an extra condition to add: `exit_manager.plan_exit_actions`'s own
# `worst_premium <= runner_stop` check (fed this exact bar's `worst_in` as `worst_premium`) is
# what emits the ExitAction in the first place -- a premium_stop/profit_lock_floor leg can never
# exist unless that check already fired this bar, and its price (`state.runner_stop_premium`,
# unchanged) is the cap it is named after.
_MARKET_STAGES = frozenset({"structure_stop", "ribbon_flip", "time_stop"})
_TIME_STOP_STAGE = "time_stop"


def walk(fill: dict, shape: dict, bars, *, trigger_level: float = 0.0,
         fill_mode: str = "extreme", spy_closes=None, slippage: float = 0.0,
         market_stage_fill_fix: bool = False) -> dict:
    """Walk ONE real fill through the real exit_manager, honouring partial sells.

    Returns realized P&L across every leg plus the leg detail. `bars` is the contract's
    OPRA frame (already loaded by the caller so a population run loads each contract once).
    """
    entry = float(fill["entry_premium"])
    qty = int(fill["qty"])
    sym = fill["symbol"]

    ts = bars["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    sub = bars.loc[(ts >= pd.Timestamp(f"{fill['date']} {fill['entry_time']}")).values]
    if sub.empty:
        return {"error": "no bars at/after entry", "pnl": 0.0, "legs": []}

    state = em.ExitState.from_entry(
        symbol=sym, side=("P" if "P00" in sym else "C"), entry_premium=entry, qty=qty,
        exit_shape=shape, strategy=str(fill.get("strategy", "RIBBON")),
        trigger_level=trigger_level, structure_stop_enabled=bool(trigger_level))

    # SPY FEED (2026-08-11 harness fix #1). Without it, structure/ribbon exits CANNOT fire and
    # the walk holds a median 21 minutes longer than the live engine on 87/182 anchored
    # positions -- the single largest source of the +$5,949 fidelity bias, and fatal because
    # hold-time IS the variable under test in any exit A/B. `spy_closes` maps "HH:MM" -> the
    # CLOSED 5m SPY close, exactly what heartbeat_core/fleet_live thread into
    # plan_exit_actions as last_closed_5m_close. Absent -> old behaviour, disclosed.

    open_qty = qty
    hwm = entry
    pnl = 0.0
    legs: list = []

    # FILL MODE (2026-08-11 fidelity audit). The live engine polls a QUOTE once a minute; it
    # does not see a 5-minute bar's high or low unless the price is still there when it looks.
    # Feeding bar extremes into the planner triggers TP1 at highs and stops at lows the engine
    # never captured -- measured bias +$5,949 over 182 anchored positions, concentrated entirely
    # in ['tp1', ...] paths. Modes:
    #   "extreme" : bar high/low          (original -- documented optimistic, kept for A/B)
    #   "close"   : bar close for BOTH    (a price that demonstrably persisted to bar end)
    #   "mixed"   : close for the favourable side, low for the adverse side (conservative)
    for _i, bar in sub.iterrows():
        if open_qty <= 0:
            break
        _hi, _lo, _cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
        if fill_mode == "close":
            best_in, worst_in = _cl, _cl
        elif fill_mode == "mixed":
            best_in, worst_in = _cl, _lo
        else:
            best_in, worst_in = _hi, _lo
        hwm = max(hwm, best_in)
        _t = bar["timestamp_et"].strftime("%H:%M")
        _spy = (spy_closes or {}).get(_t)
        dec = em.plan_exit_actions(state, best_premium=hwm, worst_premium=worst_in,
                                   open_qty=open_qty, now_et=bar["timestamp_et"].time(),
                                   last_closed_5m_close=_spy)
        state = dec.state
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            # price the leg at whatever level triggered it
            px = getattr(a, "price", None)
            if px is None:
                if market_stage_fill_fix and a.stage == _TIME_STOP_STAGE:
                    # time_stop is a CLOCK event, not a price cross -- fills at this bar's
                    # CLOSE (the prevailing price at the stop minute), never an extreme and
                    # never the static stop level (see module-level note: this is the ONE
                    # stage this session's follow-up actually changed).
                    px = _cl
                elif market_stage_fill_fix and a.stage in _MARKET_STAGES:
                    # structure_stop / ribbon_flip (see module-level note): no premium
                    # threshold exists for either, so the bar's own worst-case price
                    # (`worst_in`, already resolved per `fill_mode`) is the best available
                    # proxy -- unchanged from the original 2026-09-03 ship.
                    px = worst_in
                else:
                    px = (entry * (1.0 + state.tp1_premium_pct) if a.stage == "tp1"
                          else state.runner_stop_premium or worst_in)
            n = min(int(a.qty or open_qty), open_qty)
            if n <= 0:
                continue
            # SLIPPAGE (harness fix #2). The engine market-sells; it does not get the trigger
            # price. Measured at +$60.5/position on the 20 fidelity positions whose exit TIMING
            # matched live exactly -- i.e. pure price error with timing held constant.
            px = max(0.01, float(px) - slippage)
            pnl += (float(px) - entry) * n * 100
            open_qty -= n
            legs.append({"t": bar["timestamp_et"].strftime("%H:%M"), "stage": a.stage,
                         "qty": n, "px": round(float(px), 4),
                         "pnl": round((float(px) - entry) * n * 100, 2)})
            if open_qty <= 0:
                break

    if open_qty > 0:   # never fully exited -> mark out at the last close (EOD flatten)
        px = float(sub.iloc[-1]["close"])
        pnl += (px - entry) * open_qty * 100
        legs.append({"t": "15:50", "stage": "eod", "qty": open_qty, "px": round(px, 4),
                     "pnl": round((px - entry) * open_qty * 100, 2)})
        open_qty = 0

    return {"pnl": round(pnl, 2), "legs": legs, "n_legs": len(legs),
            "mfe_pct": round((hwm / entry - 1) * 100, 1)}


def self_check() -> int:
    """Prove the walker models tranches -- the exact property the old harness lacked.
    A TP1 partial must produce TWO legs and the sell fraction must MOVE the total."""
    import strategies as st
    from ladder_population_killcheck import load_positions
    from lib.option_pricing_real import load_contract_bars

    pos = load_positions()
    base = st.by_name("ribbon_ride").exit.to_dict()
    picked = None
    for q in pos:
        try:
            df = load_contract_bars(q["symbol"])
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        r = walk(q, {**base, "tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.5}, df)
        if r.get("n_legs", 0) >= 2:
            picked = (q, df)
            break
    if picked is None:
        print("SELF-CHECK INCONCLUSIVE: no position produced a multi-leg exit")
        return 1
    q, df = picked
    print(f"self-check on {q['arm']} {q['symbol']} {q['date']} entry {q['entry_premium']} x{q['qty']}")
    outs = {}
    for frac in (0.5, 0.667, 0.8):
        r = walk(q, {**base, "tp1_premium_pct": 0.30, "tp1_qty_fraction": frac}, df)
        outs[frac] = r["pnl"]
        print(f"   sell {frac:.0%} -> pnl {r['pnl']:+.2f}  legs={r['legs']}")
    if len({round(v, 2) for v in outs.values()}) == 1:
        print("FAIL: sell fraction still has no effect -- tranches are NOT being modeled")
        return 1
    print("PASS: sell fraction moves the result -> partial sells are genuinely modeled")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_check())
