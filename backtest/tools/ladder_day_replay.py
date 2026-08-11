#!/usr/bin/env python
"""ladder_day_replay.py -- replay a day's REAL broker fills through any exit shape.

J directive 2026-08-10: "show me the table of all the trades we did today, but putting it
through the new stop loss strategy engine, show me what we would have done today. Replay the
day with the engine with its new parameters."

WHAT THIS IS AND IS NOT
  IS:  the real entries (arm, symbol, qty, fill price, fill time -- from broker records) walked
       forward bar-by-bar on real OPRA 5-minute premium bars through the REAL exit_manager
       (`plan_exit_actions`), with a swappable ExitShape. Entry side is held FIXED; only the
       exit logic varies. That makes it a clean exit-only counterfactual.
  NOT: a signal replay. It cannot tell you what the engine would have ENTERED under different
       gates -- it takes the entries as given. For entry-side questions use
       backtest/tools/engine_fullhist_replay.py.

TWO DISCLOSURES THAT TRAVEL WITH EVERY NUMBER THIS PRINTS (do not strip them):
  1. FIVE-MINUTE GRANULARITY. Floors are tested against each bar's low, so an intra-bar dip
     through a floor exits at the floor, but the ORDER of the high and the low inside one bar
     is unknowable. Where a bar both makes a new HWM and breaches the resulting floor, this
     resolves optimistically (arm first, then exit at the floor). Sub-bar precision would need
     quote-level data we do not store.
  2. NO SPY FEED -> NO STRUCTURE EXITS. `plan_exit_actions` is fed premium only, so
     structure/ribbon exits cannot fire. Positions the live engine closed on structure instead
     ride to a premium floor or the catastrophe cap here. This makes the CONTROL arm
     PESSIMISTIC vs what actually happened (2026-08-10: control replays -$1,813 vs -$758
     actual). Ladder arms are unaffected in practice because their floors fire hours before the
     structure exit would -- but compare ladder-vs-ACTUAL, not ladder-vs-control, when quoting
     a dollar swing to J.

$0, no LLM, deterministic. Re-running with the same fills + cache is byte-identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import pandas as pd  # noqa: E402

import exit_manager as em  # noqa: E402
import strategies as st  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402


def _bars(symbol: str, cache: dict) -> pd.DataFrame:
    if symbol not in cache:
        cache[symbol] = load_contract_bars(symbol)
    return cache[symbol]


def replay_fill(fill: dict, shape: dict, cache: dict, *, trigger_level: float) -> dict:
    """Walk ONE real fill forward through the real exit manager under `shape`."""
    sym, qty, entry = fill["symbol"], int(fill["qty"]), float(fill["entry_premium"])
    df = _bars(sym, cache)
    ts = df["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    start = pd.Timestamp(f"{fill['date']} {fill['entry_time']}")
    sub = df.loc[(ts >= start).values]
    if sub.empty:
        return {**fill, "error": f"no OPRA bars at/after {start}"}

    state = em.ExitState.from_entry(
        symbol=sym, side=sym[-9], entry_premium=entry, qty=qty, exit_shape=shape,
        strategy=fill.get("strategy", "RIBBON"), trigger_level=trigger_level,
        structure_stop_enabled=True)

    hwm = entry
    exit_px = exit_time = None
    reason = "EOD_TIME_STOP"
    for _i, bar in sub.iterrows():
        hwm = max(hwm, float(bar["high"]))
        dec = em.plan_exit_actions(state, best_premium=hwm, worst_premium=float(bar["low"]),
                                   open_qty=qty, now_et=bar["timestamp_et"].time())
        state = dec.state
        if dec.actions:
            act = dec.actions[0]
            exit_px = getattr(act, "price", None) or state.runner_stop_premium
            exit_time = bar["timestamp_et"].strftime("%H:%M")
            reason = getattr(act, "reason", None) or act.kind
            break
    if exit_px is None:
        exit_px, exit_time = float(sub.iloc[-1]["close"]), "15:50"

    pnl = (float(exit_px) - entry) * qty * 100
    return {**fill, "replay_exit_time": exit_time, "replay_exit_premium": round(float(exit_px), 4),
            "replay_reason": str(reason), "replay_pnl": round(pnl, 2),
            "mfe_pct": round((hwm / entry - 1) * 100, 1), "hwm_premium": round(hwm, 4),
            "delta_vs_actual": round(pnl - float(fill["actual_pnl"]), 2)}


def replay_day(fills: list, shape: dict, *, trigger_level: float) -> dict:
    cache: dict = {}
    rows = [replay_fill(f, shape, cache, trigger_level=trigger_level) for f in fills]
    ok = [r for r in rows if "error" not in r]
    return {"rows": rows,
            "replay_total": round(sum(r["replay_pnl"] for r in ok), 2),
            "actual_total": round(sum(float(r["actual_pnl"]) for r in ok), 2),
            "n_priced": len(ok), "n_fills": len(rows)}


def print_table(res: dict) -> None:
    hdr = (f"{'#':>2} {'arm':8s} {'contract':8s} {'q':>3s} {'IN':>5s} {'entry':>6s} {'MFE':>5s} "
           f"{'OUT':>5s} {'px':>5s} {'reason':24s} {'NEW P&L':>9s} {'ACTUAL':>8s} {'delta':>9s}")
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(res["rows"], 1):
        if "error" in r:
            print(f"{i:>2} {r['arm']:8s} {r['symbol']:8s}  -- {r['error']}")
            continue
        sym = r["symbol"]
        cn = ("CALL" if sym[-9] == "C" else "PUT ") + str(int(sym[-8:-3]))
        print(f"{i:>2} {r['arm']:8s} {cn:8s} {r['qty']:>3d} {r['entry_time'][:5]:>5s} "
              f"{r['entry_premium']:6.2f} {r['mfe_pct']:4.0f}% {r['replay_exit_time']:>5s} "
              f"{r['replay_exit_premium']:5.2f} {r['replay_reason'][:24]:24s} "
              f"{r['replay_pnl']:+9.2f} {float(r['actual_pnl']):+8.2f} {r['delta_vs_actual']:+9.2f}")
    print("-" * len(hdr))
    print(f"{'':2} {'TOTAL':8s} {'':8s} {'':3s} {'':5s} {'':6s} {'':5s} {'':5s} {'':5s} {'':24s} "
          f"{res['replay_total']:+9.2f} {res['actual_total']:+8.2f} "
          f"{res['replay_total'] - res['actual_total']:+9.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fills", required=True, help="JSON file: list of real broker fills")
    ap.add_argument("--strategy", default="ribbon_ride", help="registry strategy for the base shape")
    ap.add_argument("--shape-override", default=None,
                    help='JSON dict merged over the registry ExitShape, e.g. \'{"pre_tp1_ladder":null}\'')
    ap.add_argument("--trigger-level", type=float, required=True,
                    help="the day's trigger level (structure stops need it; premium-only replay "
                         "cannot fire them but from_entry requires the field)")
    ap.add_argument("--out", default=None, help="write the full result JSON here")
    args = ap.parse_args()

    fills = json.loads(Path(args.fills).read_text(encoding="utf-8"))
    shape = st.by_name(args.strategy).exit.to_dict()
    if args.shape_override:
        shape.update(json.loads(args.shape_override))

    res = replay_day(fills, shape, trigger_level=args.trigger_level)
    res["shape"] = shape
    res["strategy"] = args.strategy
    res["disclosures"] = [
        "OPRA 5-minute bars: intra-bar high/low ORDER is unknowable; a bar that both sets a new "
        "HWM and breaches the resulting floor resolves optimistically (arm, then exit at floor).",
        "No SPY feed is wired in, so structure/ribbon exits CANNOT fire. This makes the no-ladder "
        "CONTROL arm pessimistic vs live. Quote ladder-vs-ACTUAL, never ladder-vs-control.",
        "Entries are held FIXED at the real broker fills. This is an exit-only counterfactual and "
        "says nothing about what different gates would have entered.",
    ]
    print_table(res)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
