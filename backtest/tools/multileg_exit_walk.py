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


def walk(fill: dict, shape: dict, bars, *, trigger_level: float = 0.0) -> dict:
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
        trigger_level=trigger_level, structure_stop_enabled=True)

    open_qty = qty
    hwm = entry
    pnl = 0.0
    legs: list = []

    for _i, bar in sub.iterrows():
        if open_qty <= 0:
            break
        hwm = max(hwm, float(bar["high"]))
        dec = em.plan_exit_actions(state, best_premium=hwm, worst_premium=float(bar["low"]),
                                   open_qty=open_qty, now_et=bar["timestamp_et"].time())
        state = dec.state
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            # price the leg at whatever level triggered it
            px = getattr(a, "price", None)
            if px is None:
                px = (entry * (1.0 + state.tp1_premium_pct) if a.stage == "tp1"
                      else state.runner_stop_premium or float(bar["low"]))
            n = min(int(a.qty or open_qty), open_qty)
            if n <= 0:
                continue
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
