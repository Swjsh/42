#!/usr/bin/env python
"""winners_exit_target_matrix_2026_08_19.py -- THE BIGGER-WINNERS lane: a FULL exit-shape
matrix over every closed round trip in the real-fills book.

LEVER: exit target / TP1 shape. Grid = tp1_qty_fraction x tp1_premium_pct (TP1 trigger)
x runner_target_pct x trail_pct. Everything else (stop level, stop_mode, pre-TP1 ladder,
pre-TP1 trail, profit-lock mode/arm, catastrophe cap, time stop) is HELD at the row's live
production shape so exactly one axis family moves.

POPULATION: analysis/recommendations/trade-matrix.json -- 303 closed round trips, 5 arms,
35 trading days. NOT 303 independent decisions (one shared signal, r=0.846) -- n_effective
is computed and reported.

HARNESS: the REAL live exit core (automation/state/fleet/exit_manager.plan_exit_actions)
ticked by backtest/lib/exit_manager_walk.walk_exit_manager over full-day 1-minute OPRA bars
from backtest/data/opra_1m_cache. Point-sampled at each bar's OPEN (the live NBBO-snapshot
analog) -- NO intrabar look-ahead, no peeking at a future high.

FILL MODELS (both reported, never blended):
  A. limit    -- the repo's historical convention: limit-style stages fill AT the trigger
                 level, market-style stages (time_stop/ribbon_flip/structure_stop) pay
                 DEFAULT_EXIT_SLIPPAGE. Documented as OPTIMISTIC vs live.
  B. market   -- every stage fills at that bar's close minus slippage. This is what live
                 actually does (fleet_broker.market_sell has no limit_price on any exit).
                 Reported at 2c/contract and at exit_fill_realism's 0.13-of-range.
Fill price never feeds back into the decision path, so B is recomputed exactly from A's
legs -- one walk, two (three) accountings.

FEES: setup/scripts/cost_model.py primitives, recomputed PER CELL (a cell with more exit
legs pays more per-execution OCC/ORF/TAF ceilings).

SCOPE: analysis only. Arms nothing, writes no params.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "backtest", REPO / "backtest" / "lib", REPO / "backtest" / "tools",
          REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.exit_manager_walk import walk_exit_manager, DEFAULT_EXIT_SLIPPAGE  # noqa: E402
import catastrophe_stop_shakeout_ab as csb  # noqa: E402
import cost_model as cm  # noqa: E402

MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"
OPRA_1M = REPO / "backtest" / "data" / "opra_1m_cache"
SPY_5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-19.csv"
# 32 MB of per-trade x per-cell detail -> backtest/data/ (gitignored), not the analysis tree.
OUT_JSON = REPO / "backtest" / "data" / "winners-exit-target-matrix-2026-08-19.raw.json"

TIME_STOP_ET = dt.time(15, 40)          # automation/state/params.json time_stop_et
STRUCTURE_STOP_ENABLED = True           # automation/state/params.json structure_stop_enabled
RANGE_REALISM_FRAC = 0.13               # setup/scripts/exit_fill_realism.py

# -- production exit shapes, verbatim from automation/state/fleet/strategies.py + params.json
RIBBON_RIDE = dict(premium_stop_pct=-0.20, tp1_premium_pct=1.0, tp1_qty_fraction=0.667,
                   pre_tp1_ladder=[[0.50, 0.30], [0.75, 0.60]],
                   pre_tp1_trail_arm_pct=0.75, pre_tp1_trail_pct=0.20,
                   profit_lock_mode="trailing", runner_target_pct=99.0, trail_pct=0.15,
                   stop_mode="structure", catastrophe_stop_pct=-0.50)
VWAP_CONT = dict(premium_stop_pct=-0.06, tp1_premium_pct=0.40, tp1_qty_fraction=0.8,
                 profit_lock_mode="fixed")
VWAP_RFB = dict(premium_stop_pct=-0.08, tp1_premium_pct=0.30, tp1_qty_fraction=0.8,
                profit_lock_mode="fixed")
BOLLINGER = dict(premium_stop_pct=-0.08, tp1_premium_pct=0.30, tp1_qty_fraction=0.667,
                 profit_lock_mode="fixed")
VIX_DAYSIDE = dict(premium_stop_pct=-0.08, tp1_premium_pct=0.30, tp1_qty_fraction=0.8,
                   profit_lock_mode="fixed")

SETUP_TO_SHAPE = {
    "BEARISH_REJECTION_RIDE_THE_RIBBON": ("ribbon_ride", RIBBON_RIDE),
    "BULLISH_RECLAIM_RIDE_THE_RIBBON":   ("ribbon_ride", RIBBON_RIDE),
    "VWAP_CONTINUATION":                 ("vwap_continuation", VWAP_CONT),
    "vwap_continuation":                 ("vwap_continuation", VWAP_CONT),
    "VWAP_RECLAIM_FAILED_BREAK":         ("vwap_reclaim_failed_break", VWAP_RFB),
    "vwap_reclaim_failed_break":         ("vwap_reclaim_failed_break", VWAP_RFB),
    "bollinger_squeeze":                 ("bollinger_squeeze", BOLLINGER),
    "vix_regime_dayside":                ("vix_regime_dayside", VIX_DAYSIDE),
}

# -- the assigned grid
FRACS = [0.0, 0.333, 0.5, 0.667, 0.8, 1.0]
TP1S = [0.30, 0.50, 0.75, 1.00, 1.50]
RUNNERS = [1.0, 2.5, 99.0]          # 99.0 == "no runner target" (today's live value)
TRAILS = [0.10, 0.15, 0.25, 0.40]


def load_1m(symbol: str, date: str):
    p = OPRA_1M / f"{symbol}_{date}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    ts = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    out = pd.DataFrame({"timestamp_et": ts, "open": df["o"].astype(float),
                        "high": df["h"].astype(float), "low": df["l"].astype(float),
                        "close": df["c"].astype(float)})
    return out.sort_values("timestamp_et").reset_index(drop=True)


def load_spy():
    df = pd.read_csv(SPY_5M)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True) \
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    return df.sort_values("timestamp_et").reset_index(drop=True)


def fees_for(qty, legs) -> float:
    """Entry (1 execution) + one execution per exit leg, cost_model primitives."""
    f = cm.occ_fee(qty) + cm.orf_fee(qty)
    for lg in legs:
        f += cm.occ_fee(lg["qty"]) + cm.orf_fee(lg["qty"]) + cm.taf_fee(lg["qty"])
        f += cm.sec_fee(lg["price"] * lg["qty"] * 100.0)
    return round(f, 4)


def main() -> int:
    limit_cells = None
    if "--cells" in sys.argv:
        limit_cells = int(sys.argv[sys.argv.index("--cells") + 1])
    start_cell = 0
    if "--start" in sys.argv:
        start_cell = int(sys.argv[sys.argv.index("--start") + 1])
    out_path = OUT_JSON
    if "--out" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("--out") + 1])
    sample = "--sample" in sys.argv

    doc = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = doc["rows"]
    if sample:
        rows = rows[:25]

    spy = load_spy()
    ribbon_lookup = csb.build_ribbon_lookup(spy)

    prepared, skipped = [], []
    opt_cache, rtd_cache, spy_day_cache, bar_at_cache = {}, {}, {}, {}
    for r in rows:
        key = (r["symbol"], r["date"])
        if key not in opt_cache:
            opt_cache[key] = load_1m(*key)
        opt = opt_cache[key]
        if opt is None or opt.empty:
            skipped.append({"arm": r["arm"], "date": r["date"], "symbol": r["symbol"],
                            "why": "no cached 1-min OPRA bars"})
            continue
        if key not in rtd_cache:
            rtd_cache[key] = csb.ribbon_tick_df_for(opt, ribbon_lookup)
            bar_at_cache[key] = {pd.Timestamp(t): (c, h, lo)
                                 for t, c, h, lo in zip(opt["timestamp_et"], opt["close"],
                                                        opt["high"], opt["low"])}
        d = dt.date.fromisoformat(r["date"])
        if d not in spy_day_cache:
            spy_day_cache[d] = spy.loc[spy["timestamp_et"].dt.date == d].reset_index(drop=True)
        setup = r.get("setup") or ""
        if setup not in SETUP_TO_SHAPE:
            skipped.append({"arm": r["arm"], "date": r["date"], "symbol": r["symbol"],
                            "why": "no production exit shape for setup " + repr(setup)})
            continue
        strat, base_shape = SETUP_TO_SHAPE[setup]
        prepared.append({
            "row": r, "strategy": strat, "base_shape": base_shape,
            "entry_ts": dt.datetime.fromisoformat(r["entry_ts_et"]).replace(microsecond=0),
            "opt": opt, "rtd": rtd_cache[key], "spy_day": spy_day_cache[d],
            "bar_at": bar_at_cache[key],
            "struct": bool(STRUCTURE_STOP_ENABLED and base_shape.get("stop_mode") == "structure"
                           and r.get("trigger_level") is not None),
        })

    cells, seen = [], {}
    for frac in FRACS:
        for tp1 in TP1S:
            for run in RUNNERS:
                for tr in TRAILS:
                    if frac == 0.0:
                        canon = ("frac0",)
                    elif frac == 1.0:
                        canon = ("frac1", tp1)
                    else:
                        canon = (frac, tp1, run, tr)
                    cid = "f%s_t%s_r%s_x%s" % (frac, tp1, run, tr)
                    ck = "|".join(map(str, canon))
                    cells.append({"cell_id": cid, "frac": frac, "tp1": tp1, "runner": run,
                                  "trail": tr, "canon": ck})
                    seen.setdefault(ck, cid)
    uniq = {}
    for c in cells:
        if seen[c["canon"]] == c["cell_id"]:
            uniq[c["canon"]] = c
    unique_cells = list(uniq.values())[start_cell:]
    if limit_cells:
        unique_cells = unique_cells[:limit_cells]

    t0 = dt.datetime.now()
    results = {}
    for c in unique_cells:
        per_trade = []
        for pr in prepared:
            r = pr["row"]
            shape = dict(pr["base_shape"])
            shape["tp1_qty_fraction"] = c["frac"]
            shape["tp1_premium_pct"] = c["tp1"]
            if c["frac"] not in (0.0, 1.0):
                shape["runner_target_pct"] = c["runner"]
                shape["trail_pct"] = c["trail"]
            res = walk_exit_manager(
                symbol=r["symbol"], side=r["side"], entry_time_et=pr["entry_ts"],
                entry_premium=r["entry_premium"], qty=int(r["qty"]), exit_shape=shape,
                structure_stop_enabled=pr["struct"], trigger_level=r.get("trigger_level"),
                strategy=pr["strategy"], time_stop_et=TIME_STOP_ET,
                opt_df=pr["opt"], ribbon_tick_df=pr["rtd"], five_min_spy_df=pr["spy_day"])
            ep = float(r["entry_premium"])
            legs_limit = [{"qty": lg.qty, "price": lg.fill_price, "stage": lg.stage,
                           "ts": lg.ts_et} for lg in res.legs]
            pnl_mk = 0.0
            pnl_rg = 0.0
            legs_mk = []
            ok = True
            for lg in legs_limit:
                bar = pr["bar_at"].get(pd.Timestamp(lg["ts"]))
                if bar is None:
                    ok = False
                    break
                cl, hi, lo = bar
                px_c = max(0.01, cl - DEFAULT_EXIT_SLIPPAGE)
                px_r = max(0.01, cl - RANGE_REALISM_FRAC * (hi - lo))
                pnl_mk += (px_c - ep) * lg["qty"] * 100.0
                pnl_rg += (px_r - ep) * lg["qty"] * 100.0
                legs_mk.append({"qty": lg["qty"], "price": px_c})
            per_trade.append({
                "arm": r["arm"], "date": r["date"], "symbol": r["symbol"],
                "qty": int(r["qty"]), "entry_premium": ep,
                "entry_ts": r["entry_ts_et"], "side": r["side"],
                "pnl_limit": res.dollar_pnl,
                "pnl_market": round(pnl_mk, 2) if ok else None,
                "pnl_market_range": round(pnl_rg, 2) if ok else None,
                "fees_limit": fees_for(int(r["qty"]), legs_limit),
                "fees_market": fees_for(int(r["qty"]), legs_mk) if ok else None,
                "n_legs": len(legs_limit), "exit_reason": res.exit_reason,
                "stages": [lg["stage"] for lg in legs_limit],
                "leg_prices": [lg["price"] for lg in legs_limit],
                "reached_tp1": any(lg["stage"] == "tp1" for lg in legs_limit),
                "tp1_price": next((lg["price"] for lg in legs_limit
                                   if lg["stage"] == "tp1"), None),
                "runner_price": next((lg["price"] for lg in legs_limit
                                      if lg["stage"] != "tp1"), None),
            })
        results[c["cell_id"]] = per_trade
        el = (dt.datetime.now() - t0).total_seconds()
        print("[%d/%d] %s gross=%+.0f  %.0fs" % (len(results), len(unique_cells), c["cell_id"],
                                                 sum(t["pnl_limit"] for t in per_trade), el),
              flush=True)

    payload = {"cells": unique_cells, "nominal_cell_count": len(cells),
               "unique_cell_count_total": len(uniq), "n_trades": len(prepared),
               "skipped": skipped, "per_trade": results,
               "elapsed_s": round((dt.datetime.now() - t0).total_seconds(), 1)}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    print("wrote", out_path, "elapsed", payload["elapsed_s"], "s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
