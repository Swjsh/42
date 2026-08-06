"""stop_width_fullhist_sweep.py -- stop-width grid over the FULL-HISTORY (391-day) population.

Third leg of LENS 1 of the 2026-08-05 EOD audit. `stop_width_grid_20260805.py` answers the
n=1 question (the 776C death spiral) and `stop_width_population_grid.py` answers it over the
25-day real-fill book. Neither is enough to change a knob: a stop width that wins on those and
loses over 391 days is not a fix. This is the wide-population check, split by day-archetype.

DESIGN
    Reuses `engine_fullhist_replay.py` wholesale -- the SAME two-layer design that repo already
    trusts for full-history production-parity work:
      ENTRY layer  run_backtest(**SAFE_BASE_LIVE), the engine_cli-equivalent gate cascade.
                   Runs ONCE: entries do not depend on the exit stop, so re-running it per
                   cell would burn ~7 minutes each for a byte-identical trade list.
      EXIT layer   exit_manager_walk.walk_exit_manager driving the REAL
                   exit_manager.plan_exit_actions core, with the REAL ribbon_flip_back tick
                   frame (not disabled), re-walked ONCE PER STOP WIDTH.
    ONLY `premium_stop_pct` varies. Every other exit knob stays at the live
    strategies.py#RIBBON_RIDE shape. structure_stop_enabled=True, exactly as production.

    NOTE ON `stop_mode="structure"`: for entries carrying a trigger_level the live shape
    resolves to the structure stop and premium_stop_pct becomes the CATASTROPHE CAP. For
    entries with trigger_level=None it is the PRIMARY stop. The sweep therefore moves a
    different lever on different trades -- that is production's own behaviour, not a modelling
    choice, and the split is reported (`n_structure` / `n_premium`) rather than averaged away.

NO ORACLE COLUMNS. Every cell is a knob the engine could actually be set to tonight.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
for _p in (str(ROOT), str(REPO / "backtest" / "tools"), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import engine_fullhist_replay as efr  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
import engine_fullhist_replay as _efr  # noqa: E402

ARCHETYPES = REPO / "analysis" / "regime-library" / "day-archetypes.json"

STOP_WIDTHS = [-0.06, -0.10, -0.12, -0.15, -0.20, -0.25, -0.50]
TREND_LIKE = {"trend-up", "trend-down", "gap-go"}
CHOP_LIKE = {"range-chop", "pin-day", "gap-fade", "V-reversal", "inverted-V"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    t0 = time.time()

    arche = json.loads(ARCHETYPES.read_text(encoding="utf-8"))["days"]

    print("loading full-history SPY/VIX ...", flush=True)
    spy_df = pd.read_csv(efr.SPY_FILE)
    vix_df = pd.read_csv(efr.VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)

    print("ENTRY layer: run_backtest(**SAFE_BASE_LIVE) once ...", flush=True)
    r = run_backtest(spy_df, vix_df, start_date=efr.FULL_START, end_date=efr.FULL_END,
                     **efr.SAFE_BASE_LIVE)
    print(f"  {len(r.trades)} raw entries in {time.time()-t0:.0f}s", flush=True)

    base_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    print(f"  base exit shape: {base_shape}", flush=True)

    # pre-resolve per-trade inputs once (bars, ribbon frame, spy day) -- the expensive part
    prepared = []
    n_no_opra = n_no_spy = 0
    for t in r.trades:
        edate = efr.eb.entry_date(t)
        symbol = efr.option_symbol(edate, int(t.strike), t.side)
        opt_df = efr.load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy += 1
            continue
        prepared.append({
            "date": edate.isoformat(), "symbol": symbol, "side": t.side,
            "entry_time_et": efr.naive_dt(t.entry_time_et),
            "entry_premium": float(t.entry_premium),
            "trigger_level": float(t.rejection_level) if t.rejection_level else None,
            "qty": int(t.qty), "setup": t.setup,
            "opt_df": opt_df, "day_spy": day_spy,
            "rtd": efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            "archetype": (arche.get(edate.isoformat()) or {}).get("archetype", "unknown"),
        })
    print(f"  prepared {len(prepared)} trades "
          f"(dropped {n_no_opra} no-OPRA, {n_no_spy} no-SPY-day) "
          f"in {time.time()-t0:.0f}s", flush=True)

    report = {
        "population": {"raw_entries": len(r.trades), "replayed": len(prepared),
                       "dropped_no_opra": n_no_opra, "dropped_no_spy_day": n_no_spy,
                       "window": [str(efr.FULL_START), str(efr.FULL_END)],
                       "days": len(set(p["date"] for p in prepared))},
        "method": {"varied": "premium_stop_pct only", "base_shape": base_shape,
                   "structure_stop_enabled": True,
                   "core": "exit_manager.plan_exit_actions via exit_manager_walk",
                   "ribbon_flip_back": "modeled (real tick frame)"},
        "cells": {},
    }

    print(f"\n{'stop':>7s}{'total':>11s}{'trend':>10s}{'chop':>10s}"
          f"{'WR':>7s}{'n_struct':>9s}{'n_prem':>8s}", flush=True)
    for w in STOP_WIDTHS:
        shape = dict(base_shape, premium_stop_pct=w)
        rows = []
        for p in prepared:
            res = walk_exit_manager(
                symbol=p["symbol"], side=p["side"], entry_time_et=p["entry_time_et"],
                entry_premium=p["entry_premium"], qty=p["qty"], exit_shape=shape,
                structure_stop_enabled=True, trigger_level=p["trigger_level"],
                strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
                opt_df=p["opt_df"], ribbon_tick_df=p["rtd"], five_min_spy_df=p["day_spy"],
            )
            rows.append({"date": p["date"], "arche": p["archetype"],
                         "pnl": float(res.dollar_pnl), "mode": res.stop_mode,
                         "reason": res.exit_reason,
                         "entry_time_et": p["entry_time_et"].isoformat(),
                         "side": p["side"], "symbol": p["symbol"]})

        def tot(pred=None) -> float:
            return round(sum(x["pnl"] for x in rows if pred is None or pred(x)), 2)

        by_a = {}
        for a in sorted(set(x["arche"] for x in rows)):
            sel = [x for x in rows if x["arche"] == a]
            by_a[a] = {"n": len(sel), "pnl": round(sum(x["pnl"] for x in sel), 2),
                       "win_rate": round(sum(1 for x in sel if x["pnl"] > 0) / len(sel), 3)}
        n_struct = sum(1 for x in rows if x["mode"] == "structure")
        wr = round(sum(1 for x in rows if x["pnl"] > 0) / len(rows), 3) if rows else None
        reasons = defaultdict(int)
        for x in rows:
            reasons[x["reason"]] += 1
        lab = f"{w:.0%}"
        report["cells"][lab] = {
            "premium_stop_pct": w, "n_trades": len(rows), "total_pnl": tot(),
            "trend_like": tot(lambda x: x["arche"] in TREND_LIKE),
            "chop_like": tot(lambda x: x["arche"] in CHOP_LIKE),
            "win_rate": wr, "n_structure_mode": n_struct,
            "n_premium_mode": len(rows) - n_struct,
            "by_archetype": by_a, "exit_reasons": dict(reasons),
            "trades": rows,
        }
        c = report["cells"][lab]
        print(f"{lab:>7s}{c['total_pnl']:>+11.0f}{c['trend_like']:>+10.0f}"
              f"{c['chop_like']:>+10.0f}{wr:>7.2f}{n_struct:>9d}"
              f"{len(rows)-n_struct:>8d}", flush=True)

    Path(args.out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}  ({time.time()-t0:.0f}s total)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
