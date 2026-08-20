#!/usr/bin/env python
"""winners_exit_target_report_2026_08_19.py -- scores the raw exit-shape grid and writes the
markdown matrix + the JSON verdict.

Reads  : backtest/data/winners-exit-target-matrix-2026-08-19.raw.json (gitignored, 32 MB)
Writes : analysis/deep-research/WINNERS-EXIT-TARGET-MATRIX-2026-08-19.json (scored cells)
         analysis/deep-research/WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md (sections A-E)

PRIMARY ACCOUNTING = market-style exit fills at exit_fill_realism's 0.13-of-bar-range
("mr"). Justification is measured, not assumed: replaying the live production shape over the
whole book reconciles to the realised gross book to +$341 on 303 trades (+$1.13/trade) under
that model, versus +$3,392 under the repo's legacy limit-fill convention and -$790 under a
flat 2c market slip. All three are reported for every cell; none are blended.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "backtest", REPO / "backtest" / "lib", REPO / "backtest" / "tools",
          REPO / "setup" / "scripts", REPO / "automation" / "state" / "fleet"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import winners_exit_target_matrix_2026_08_19 as W  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager, DEFAULT_EXIT_SLIPPAGE  # noqa: E402

RAW = REPO / "backtest" / "data" / "winners-exit-target-matrix-2026-08-19.raw.json"
OUT_MD = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.md"
OUT_JSON = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.json"

MODELS = ["pnl_market_range", "pnl_market", "pnl_limit"]
PRIMARY = "pnl_market_range"
N_EFFECTIVE = 84         # 60-min signal clusters within (date x side); see report section 2


# ─────────────────────────────────────────────────────── production reference walk ──
def run_production():
    doc = json.loads(W.MATRIX.read_text(encoding="utf-8"))
    rows = doc["rows"]
    spy = W.load_spy()
    rl = W.csb.build_ribbon_lookup(spy)
    out = []
    for r in rows:
        opt = W.load_1m(r["symbol"], r["date"])
        if opt is None or opt.empty:
            continue
        setup = r.get("setup") or ""
        if setup not in W.SETUP_TO_SHAPE:
            continue
        strat, shape = W.SETUP_TO_SHAPE[setup]
        d = dt.date.fromisoformat(r["date"])
        day_spy = spy.loc[spy["timestamp_et"].dt.date == d].reset_index(drop=True)
        rtd = W.csb.ribbon_tick_df_for(opt, rl)
        struct = bool(W.STRUCTURE_STOP_ENABLED and shape.get("stop_mode") == "structure"
                      and r.get("trigger_level") is not None)
        res = walk_exit_manager(
            symbol=r["symbol"], side=r["side"],
            entry_time_et=dt.datetime.fromisoformat(r["entry_ts_et"]).replace(microsecond=0),
            entry_premium=r["entry_premium"], qty=int(r["qty"]), exit_shape=shape,
            structure_stop_enabled=struct, trigger_level=r.get("trigger_level"),
            strategy=strat, time_stop_et=W.TIME_STOP_ET, opt_df=opt,
            ribbon_tick_df=rtd, five_min_spy_df=day_spy)
        bar_at = {pd.Timestamp(t): (c, h, lo) for t, c, h, lo
                  in zip(opt["timestamp_et"], opt["close"], opt["high"], opt["low"])}
        ep = float(r["entry_premium"])
        mk = rg = 0.0
        legs = [{"qty": lg.qty, "price": lg.fill_price, "stage": lg.stage, "ts": lg.ts_et}
                for lg in res.legs]
        legs_mk = []
        ok = True
        for lg in legs:
            b = bar_at.get(pd.Timestamp(lg["ts"]))
            if b is None:
                ok = False
                break
            cl, hi, lo = b
            pc = max(0.01, cl - DEFAULT_EXIT_SLIPPAGE)
            pr = max(0.01, cl - W.RANGE_REALISM_FRAC * (hi - lo))
            mk += (pc - ep) * lg["qty"] * 100.0
            rg += (pr - ep) * lg["qty"] * 100.0
            legs_mk.append({"qty": lg["qty"], "price": pc})
        out.append({
            "arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "qty": int(r["qty"]),
            "entry_premium": ep, "entry_ts": r["entry_ts_et"], "side": r["side"],
            "pnl_limit": res.dollar_pnl,
            "pnl_market": round(mk, 2) if ok else None,
            "pnl_market_range": round(rg, 2) if ok else None,
            "fees_limit": W.fees_for(int(r["qty"]), legs),
            "fees_market": W.fees_for(int(r["qty"]), legs_mk) if ok else None,
            "n_legs": len(legs), "exit_reason": res.exit_reason,
            "stages": [lg["stage"] for lg in legs],
            "leg_prices": [lg["price"] for lg in legs],
            "reached_tp1": any(lg["stage"] == "tp1" for lg in legs),
            "tp1_price": next((lg["price"] for lg in legs if lg["stage"] == "tp1"), None),
            "runner_price": next((lg["price"] for lg in legs if lg["stage"] != "tp1"), None),
            "real_pnl_gross": r["real_pnl_gross"], "real_pnl_net": r["real_pnl_net"],
        })
    return out


# ───────────────────────────────────────────────────────────────────── cell scoring ──
def score(trades, model=PRIMARY):
    vals = [t[model] for t in trades if t[model] is not None]
    fee_key = "fees_limit" if model == "pnl_limit" else "fees_market"
    fees = sum(t[fee_key] for t in trades if t[fee_key] is not None)
    gross = sum(vals)
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    ordered = sorted([t for t in trades if t[model] is not None], key=lambda t: t["entry_ts"])
    cum = peak = 0.0
    mdd = 0.0
    for t in ordered:
        cum += t[model]
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return {
        "gross": round(gross, 2), "fees": round(fees, 2), "net": round(gross - fees, 2),
        "n": len(vals), "wins": len(wins),
        "win_rate": round(len(wins) / len(vals), 4) if vals else None,
        "avg_win": round(st.mean(wins), 2) if wins else 0.0,
        "avg_loss": round(st.mean(losses), 2) if losses else 0.0,
        "max_drawdown": round(mdd, 2),
        "avg_legs": round(st.mean([t["n_legs"] for t in trades]), 2),
    }


def concentration(cell_trades, prod_by_key, model=PRIMARY):
    """Top-day and top-trade share of the cell-vs-production DELTA."""
    per_trade, per_day = [], defaultdict(float)
    for t in cell_trades:
        k = (t["arm"], t["symbol"], t["entry_ts"])
        p = prod_by_key.get(k)
        if p is None or t[model] is None or p[model] is None:
            continue
        d = t[model] - p[model]
        per_trade.append((d, t["date"], t["arm"], t["symbol"]))
        per_day[t["date"]] += d
    total = sum(x[0] for x in per_trade)
    if abs(total) < 1e-9 or not per_trade:
        return {"total_delta": round(total, 2), "top_day_share": None,
                "top_trade_share": None, "top_day": None, "top_trade": None,
                "n_delta_nonzero": sum(1 for x in per_trade if abs(x[0]) > 0.005)}
    td = max(per_day.items(), key=lambda kv: abs(kv[1]))
    tt = max(per_trade, key=lambda x: abs(x[0]))
    return {"total_delta": round(total, 2),
            "top_day_share": round(td[1] / total, 4), "top_day": [td[0], round(td[1], 2)],
            "top_trade_share": round(tt[0] / total, 4),
            "top_trade": [tt[1], tt[2], tt[3], round(tt[0], 2)],
            "n_delta_nonzero": sum(1 for x in per_trade if abs(x[0]) > 0.005)}


def runner_beats_tp1(trades):
    """Among 2+ leg exits that reached TP1: did the RUNNER leg fill ABOVE the TP1 leg?
    This is the 2026-08-19 exhibit (+$299 winner, runner $1.82 vs TP1 $1.65) generalised.
    Reported as a rate + the mean/median premium edge per contract, both signed."""
    diffs = []
    for t in trades:
        if not t["reached_tp1"] or t["n_legs"] < 2 or t["tp1_price"] is None:
            continue
        diffs.append(t["leg_prices"][-1] - t["tp1_price"])
    if not diffs:
        return {"n_two_leg_tp1": 0, "n_runner_above_tp1": 0, "rate": None,
                "mean_premium_edge": None, "median_premium_edge": None}
    beat = sum(1 for d in diffs if d > 0)
    return {"n_two_leg_tp1": len(diffs), "n_runner_above_tp1": beat,
            "rate": round(beat / len(diffs), 4),
            "mean_premium_edge": round(st.mean(diffs), 4),
            "median_premium_edge": round(st.median(diffs), 4)}


TABLES = REPO / "analysis" / "deep-research" / "WINNERS-EXIT-TARGET-MATRIX-2026-08-19.tables.md"


def write_tables(payload, prod, prod_by_key, per_trade, cells):
    """Emit the machine-generated table block that the human report embeds verbatim."""
    P = PRIMARY
    key = P + "_delta_net"
    rows = payload["cells"]
    by_id = {r["cell_id"]: r for r in rows}
    pnet = payload["production_cell"]["scores"][P]["net"]
    L = []

    def cell(frac, tp1, run, tr):
        return by_id.get("f%s_t%s_r%s_x%s" % (frac, tp1, run, tr))

    def canon_id(frac, tp1, run, tr):
        if frac == 0.0:
            return cell(0.0, 0.30, 1.0, 0.10)
        if frac == 1.0:
            return cell(1.0, tp1, 1.0, 0.10)
        return cell(frac, tp1, run, tr)

    L.append("### A. Headline grid — TP1 fraction x TP1 trigger")
    L.append("")
    L.append("Each cell shows the BEST (runner_target, trail) combination for that "
             "(fraction, trigger) pair, primary accounting `%s`, net of fees. "
             "`delta` is versus the production shape (net %+0.0f)." % (P, pnet))
    L.append("")
    L.append("| TP1 frac | " + " | ".join("TP1 +%d%%" % int(t * 100) for t in W.TP1S) + " |")
    L.append("|---|" + "---|" * len(W.TP1S))
    for frac in W.FRACS:
        cs = []
        for tp1 in W.TP1S:
            best = None
            for run in W.RUNNERS:
                for tr in W.TRAILS:
                    r = canon_id(frac, tp1, run, tr)
                    if r is None:
                        continue
                    if best is None or r[key] > best[key]:
                        best = r
            if best is None:
                cs.append("n/a")
                continue
            mark = " **<-PROD**" if (frac == 0.667 and tp1 == 1.00) else ""
            cs.append("net %+0.0f<br>d %+0.0f<br>WR %.0f%%%s"
                      % (best[P]["net"], best[key], 100 * (best[P]["win_rate"] or 0), mark))
        L.append("| **%s** | " % frac + " | ".join(cs) + " |")
    L.append("")

    L.append("### B. Full ranking — every unique cell, primary accounting")
    L.append("")
    L.append("| rank | cell | frac | TP1 | runner | trail | net | delta | WR | avg win | "
             "avg loss | maxDD | legs | topDay% | topTrade% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        c = r["conc"]
        s = r[P]
        L.append("| %d | `%s` | %s | +%d%% | %s | %s | %+0.0f | %+0.0f | %.0f%% | %+0.0f | "
                 "%+0.0f | %0.0f | %.2f | %s | %s |"
                 % (i, r["cell_id"], r["tp1_qty_fraction"], int(r["tp1_trigger_pct"] * 100),
                    ("none" if r["runner_target_pct"] == 99.0 else "+%d%%" % int(r["runner_target_pct"] * 100)),
                    r["trail_pct"], s["net"], r[key], 100 * (s["win_rate"] or 0),
                    s["avg_win"], s["avg_loss"], s["max_drawdown"], s["avg_legs"],
                    ("%.0f%%" % (100 * c["top_day_share"])) if c["top_day_share"] is not None else "-",
                    ("%.0f%%" % (100 * c["top_trade_share"])) if c["top_trade_share"] is not None else "-"))
    L.append("")

    L.append("### C. Same cells under the other two fill models (sensitivity)")
    L.append("")
    L.append("| cell | net (range-realism, PRIMARY) | net (flat 2c market) | net (legacy limit) |")
    L.append("|---|---|---|---|")
    for r in rows[:15] + rows[-5:]:
        L.append("| `%s` | %+0.0f | %+0.0f | %+0.0f |"
                 % (r["cell_id"], r["pnl_market_range"]["net"], r["pnl_market"]["net"],
                    r["pnl_limit"]["net"]))
    L.append("| **PRODUCTION** | %+0.0f | %+0.0f | %+0.0f |"
             % (payload["production_cell"]["scores"]["pnl_market_range"]["net"],
                payload["production_cell"]["scores"]["pnl_market"]["net"],
                payload["production_cell"]["scores"]["pnl_limit"]["net"]))
    L.append("")

    L.append("### D. One-axis marginals (all other axes held at production)")
    L.append("")
    L.append("| axis | value | net | delta vs prod |")
    L.append("|---|---|---|---|")
    for tp1 in W.TP1S:
        r = canon_id(0.667, tp1, 99.0, 0.15)
        if r:
            L.append("| TP1 trigger | +%d%% | %+0.0f | %+0.0f |"
                     % (int(tp1 * 100), r[P]["net"], r[key]))
    for frac in W.FRACS:
        r = canon_id(frac, 1.00, 99.0, 0.15)
        if r:
            L.append("| TP1 fraction | %s | %+0.0f | %+0.0f |" % (frac, r[P]["net"], r[key]))
    for run in W.RUNNERS:
        r = canon_id(0.667, 1.00, run, 0.15)
        if r:
            L.append("| runner target | %s | %+0.0f | %+0.0f |"
                     % ("none (99.0)" if run == 99.0 else "+%d%%" % int(run * 100),
                        r[P]["net"], r[key]))
    for tr in W.TRAILS:
        r = canon_id(0.667, 1.00, 99.0, tr)
        if r:
            L.append("| trail width | %s | %+0.0f | %+0.0f |" % (tr, r[P]["net"], r[key]))
    L.append("")

    L.append("### E. Runner-vs-TP1 (does the 2026-08-19 exhibit generalise?)")
    L.append("")
    L.append("| cell | 2-leg exits reaching TP1 | runner filled ABOVE TP1 | rate | "
             "mean premium edge | median |")
    L.append("|---|---|---|---|---|---|")
    for r in ([by_id.get("f0.667_t1.0_r99.0_x0.15")] + rows[:6]):
        if r is None:
            continue
        v = r["runner_vs_tp1"]
        L.append("| `%s` | %d | %d | %s | %s | %s |"
                 % (r["cell_id"], v["n_two_leg_tp1"], v["n_runner_above_tp1"],
                    ("%.0f%%" % (100 * v["rate"])) if v["rate"] is not None else "-",
                    v["mean_premium_edge"], v["median_premium_edge"]))
    L.append("")
    TABLES.write_text("\n".join(L), encoding="utf-8")
    print("wrote", TABLES)


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    cells = {c["cell_id"]: c for c in raw["cells"]}
    per_trade = raw["per_trade"]
    prod = run_production()
    prod_by_key = {(t["arm"], t["symbol"], t["entry_ts"]): t for t in prod}

    prod_scores = {m: score(prod, m) for m in MODELS}
    real_gross = sum(t["real_pnl_gross"] for t in prod)
    real_net = sum(t["real_pnl_net"] for t in prod)

    rows_out = []
    for cid, trades in per_trade.items():
        c = cells[cid]
        rec = {"cell_id": cid, "tp1_qty_fraction": c["frac"], "tp1_trigger_pct": c["tp1"],
               "runner_target_pct": c["runner"], "trail_pct": c["trail"],
               "inert_axes": ([] if c["frac"] not in (0.0, 1.0)
                              else (["tp1_trigger", "runner_target", "trail"] if c["frac"] == 0.0
                                    else ["runner_target", "trail"]))}
        for m in MODELS:
            s = score(trades, m)
            rec[m] = s
            rec[m + "_delta_net"] = round(s["net"] - prod_scores[m]["net"], 2)
        rec["conc"] = concentration(trades, prod_by_key, PRIMARY)
        rec["runner_vs_tp1"] = runner_beats_tp1(trades)
        rows_out.append(rec)

    key = PRIMARY + "_delta_net"
    rows_out.sort(key=lambda r: -r[key])

    payload = {
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "population": {"n_trades": raw["n_trades"], "skipped": raw["skipped"],
                       "n_effective": N_EFFECTIVE},
        "fidelity": {
            "real_book_gross": round(real_gross, 2), "real_book_net_fees": round(real_net, 2),
            "production_shape_replay": {m: prod_scores[m] for m in MODELS},
            "gap_vs_real_gross": {m: round(prod_scores[m]["gross"] - real_gross, 2)
                                  for m in MODELS},
        },
        "production_cell": {
            "definition": "per-row LIVE ExitShape from automation/state/fleet/strategies.py "
                          "(ribbon_ride TP1 +100% / sell 66.7% / trail 15% / runner_target 99.0 "
                          "== none; vwap_* TP1 +40%/+30% sell 80% fixed-lock)",
            "scores": prod_scores,
        },
        "nominal_cell_count": raw["nominal_cell_count"],
        "unique_cell_count": len(rows_out),
        "primary_model": PRIMARY,
        "cells": rows_out,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    write_tables(payload, prod, prod_by_key, per_trade, cells)
    print("wrote", OUT_JSON)
    print("PRODUCTION replay net (%s): %+.2f  | real book gross %+.2f net %+.2f"
          % (PRIMARY, prod_scores[PRIMARY]["net"], real_gross, real_net))
    print("\nTOP 12 cells by delta-vs-production (%s, net of fees):" % PRIMARY)
    for r in rows_out[:12]:
        c = r["conc"]
        print("  %-28s frac=%-5s tp1=%-4s run=%-4s trail=%-4s  net %+8.0f  delta %+7.0f  "
              "WR %.0f%%  MDD %6.0f  topday %s topTrade %s"
              % (r["cell_id"], r["tp1_qty_fraction"], r["tp1_trigger_pct"],
                 r["runner_target_pct"], r["trail_pct"], r[PRIMARY]["net"], r[key],
                 100 * (r[PRIMARY]["win_rate"] or 0), r[PRIMARY]["max_drawdown"],
                 c["top_day_share"], c["top_trade_share"]))
    print("\nBOTTOM 5:")
    for r in rows_out[-5:]:
        print("  %-28s net %+8.0f delta %+7.0f" % (r["cell_id"], r[PRIMARY]["net"], r[key]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
