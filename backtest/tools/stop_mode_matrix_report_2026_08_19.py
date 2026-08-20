#!/usr/bin/env python
"""Reporting driver for stop_mode_matrix_2026_08_19.

Emits analysis/deep-research/LOSSES-STOP-MODE-MATRIX-2026-08-19.json:
  * every cell x every upside shape x three populations
  * the realized book on each population (ground truth, never a simulated stand-in)
  * concentration of each cell's DELTA vs the production cell (top day / top trade share)
  * what each cell did to the WINNERS, not just the losers
  * the observed live stop_mode split (structure vs premium as actually traded)
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stop_mode_matrix_2026_08_19 as S  # noqa: E402

PROD_CELL = "STRUCTURE+cap50"          # structure_stop_enabled=True, premium_stop_pct=-0.50
NO_STOP = "NO_STOP (15:40 time stop only)"


def realized_trades(rows, idxs):
    out = []
    for i in idxs:
        r = rows[i]
        out.append({"key": i, "arm": r["arm"], "date": r["date"],
                    "exit_ts": r["exit_ts_et"], "pnl_gross": r["real_pnl_gross"],
                    "fee": r["fee_total_ex_cat"],
                    "slip": r["qty"] * S.EXIT_SLIP_PREMIUM * 100.0,
                    "hold_min": r["hold_minutes"], "tp1_done": r["exit_stage"] == "tp1",
                    "reason": r.get("exit_stage"), "qty": r["qty"]})
    return out


def n_effective(rows, idxs):
    """Independent DECISIONS, not fills. The 5 arms fire the same signal within seconds."""
    sig = set()
    for i in idxs:
        r = rows[i]
        t = dt.datetime.fromisoformat(r["entry_ts_et"])
        bucket = t.replace(second=0, microsecond=0)
        bucket = bucket - dt.timedelta(minutes=bucket.minute % 5)
        sig.add((r["date"], r["side"], bucket.isoformat(), r["setup"].upper()))
    return len(sig)


def main():
    m, rows, results, per_trade, uncomputable, no_bars = S.main()
    cells = S.build_cells()
    labels = [c[2] for c in cells]

    # populations -------------------------------------------------------
    struct_ok = set(S.results_index_ok(results, "STRUCTURE+cap50")) if hasattr(S, "results_index_ok") else None
    keys_by_cell = {}
    for shape in S.UPSIDE:
        for lab in labels:
            keys_by_cell[(shape, lab)] = set(t["key"] for t in results[(shape, lab)])

    all_idx = set(range(len(rows)))
    pop = {
        "FULL": sorted(all_idx),
        "ATRABLE": sorted(keys_by_cell[("RIBBON", "ATR_2x")]),
        "STRUCTABLE": sorted(keys_by_cell[("RIBBON", PROD_CELL)]),
    }

    report = {
        "_doc": ("FULL stop-mode counterfactual matrix over the entire real-fills book. "
                 "Built by backtest/tools/stop_mode_matrix_2026_08_19.py + this driver."),
        "_independence_warning": m["_independence_warning"],
        "_lookahead": ("Entry bar EXCLUDED from every decision. Every stop level is decidable "
                       "at entry: fixed %-of-entry-premium, ATR from PRE-entry option bars only, "
                       "a clock, a trail seeded at entry, or the SPY trigger level recorded on "
                       "the decision row that produced the order. Bars walked forward to the "
                       "15:40 ET hard time stop from the full-day OPRA cache."),
        "_cost_note": ("gross = simulated P&L. net_fees subtracts OCC/ORF/TAF/SEC via "
                       "setup/scripts/cost_model.py. net_fees_slip additionally subtracts the "
                       "MEASURED exit-fill optimism of $0.0103/contract "
                       "(COST-REALISM-2026-08-18.md), i.e. $1.03 per contract sold."),
        "_optimism_disclosure": ("Stops fill AT the stop level unless the bar OPENS through it "
                                 "(then at the open). Real stops slip further. Every cell "
                                 "carries this same optimism, so cell-to-cell deltas are fairer "
                                 "than absolute levels; tighter stops fire more often and so "
                                 "collect MORE of this unmodelled optimism -- the matrix is "
                                 "biased IN FAVOUR of tight stops, not against them."),
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "production_cell": PROD_CELL,
        "production_cell_provenance": ("automation/state/params.json: structure_stop_enabled=True "
                                       "(SS-B chart-stop-primary, STOP-B 2026-07-09), "
                                       "premium_stop_pct=-0.50 / premium_stop_pct_bear=-0.50 "
                                       "(catastrophe cap, chart-stop-primary 2026-06-18)."),
        "populations": {k: {"n": len(v), "n_effective": n_effective(rows, v),
                            "n_days": len(set(rows[i]["date"] for i in v))}
                        for k, v in pop.items()},
        "uncomputable": {k: len(set(v)) for k, v in uncomputable.items()},
        "uncomputable_note": ("Never defaulted to zero and never silently dropped: an ATR cell "
                              "is UNCOMPUTABLE when fewer than 15 pre-entry 1-min option bars "
                              "exist (open-bell entries); a STRUCTURE cell is UNCOMPUTABLE when "
                              "the decision row carries no trigger_level. Cells are compared "
                              "only within a population where every compared cell is computable."),
        "realized_book": {},
        "matrix": {},
        "observed_live_split": {},
        "harness_fidelity": {},
    }

    for pname, idxs in pop.items():
        rt = realized_trades(rows, idxs)
        report["realized_book"][pname] = S.summarize(rt, "REALIZED (as traded)")

    # matrix ------------------------------------------------------------
    for pname, idxs in pop.items():
        iset = set(idxs)
        for shape in S.UPSIDE:
            base = [t for t in results[(shape, PROD_CELL)] if t["key"] in iset]
            if len(base) != len(idxs):
                # the production cell is not computable across this whole population,
                # so no delta can be quoted here -- levels only.
                base = None
            for lab in labels:
                tr = [t for t in results[(shape, lab)] if t["key"] in iset]
                if not tr:
                    continue
                if len(tr) != len(idxs):
                    # cell not computable on this whole population -> SKIP.
                    # Never partial-compare: a 183-row cell scored against a 303-row
                    # population is a different experiment wearing the same label.
                    continue
                s = S.summarize(tr, lab, baseline=base if base else None)
                s["shape"] = shape
                s["population"] = pname
                s["is_production"] = (lab == PROD_CELL)
                report["matrix"].setdefault(pname, {}).setdefault(shape, []).append(s)

    # observed live split (real fills, no simulation) --------------------
    for mode in ("structure", "premium", None):
        sub = [r for r in rows if r.get("stop_mode") == mode]
        if not sub:
            continue
        g = sum(r["real_pnl_gross"] for r in sub)
        w = [r for r in sub if r["real_pnl_gross"] > 0]
        l = [r for r in sub if r["real_pnl_gross"] < 0]
        byd = defaultdict(float)
        for r in sub:
            byd[r["date"]] += r["real_pnl_gross"]
        report["observed_live_split"][str(mode)] = {
            "n": len(sub), "n_effective": n_effective(rows, [rows.index(r) for r in sub]),
            "gross": round(g, 2),
            "net_fees": round(g - sum(r["fee_total_ex_cat"] for r in sub), 2),
            "win_rate": round(len(w) / len(sub), 4),
            "avg_loss": round(statistics.mean([r["real_pnl_gross"] for r in l]), 2) if l else 0.0,
            "worst_loss": round(min([r["real_pnl_gross"] for r in l]), 2) if l else 0.0,
            "winner_dollars": round(sum(r["real_pnl_gross"] for r in w), 2),
            "date_span": [min(r["date"] for r in sub), max(r["date"] for r in sub)],
            "n_days": len(byd),
            "top_day": max(byd.items(), key=lambda kv: abs(kv[1])),
            "arms": sorted(set(r["arm"] for r in sub)),
        }

    # harness fidelity ---------------------------------------------------
    fid = {}
    for pname, idxs in pop.items():
        rz = report["realized_book"][pname]
        for shape in S.UPSIDE:
            cellrows = report["matrix"].get(pname, {}).get(shape, [])
            prod = next((c for c in cellrows if c["cell"] == PROD_CELL), None)
            if prod:
                fid[pname + "|" + shape] = {
                    "realized_gross": rz["gross"], "sim_production_gross": prod["gross"],
                    "gap": round(prod["gross"] - rz["gross"], 2),
                    "realized_wr": rz["win_rate"], "sim_production_wr": prod["win_rate"],
                }
    report["harness_fidelity"] = fid
    report["harness_fidelity_note"] = (
        "The simulated production cell is NOT expected to reproduce the realized book: the book "
        "was traded across three stop_mode eras and five arm configs with differing tp1/trail "
        "shapes, whereas every simulated cell is forced onto ONE common upside rule so the "
        "downside is the only moving part. The gap is reported, not hidden. Cell-to-cell deltas "
        "inside one shape x one population are the finding; absolute levels are not.")

    S.OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("wrote", S.OUT)
    return report


if __name__ == "__main__":
    rep = main()
    for pname in ("STRUCTABLE", "FULL"):
        print("\n===== POPULATION", pname, rep["populations"][pname])
        print("REALIZED:", json.dumps({k: rep["realized_book"][pname][k] for k in
              ("n", "gross", "net_fees_slip", "win_rate", "avg_loss", "worst_loss",
               "max_drawdown", "winner_dollars")}))
        for shape in ("RIBBON", "SAFE"):
            print("-- shape", shape)
            cs = sorted(rep["matrix"][pname][shape], key=lambda c: -c["gross"])
            for c in cs:
                print(f"  {c['cell']:26s} n={c['n']:3d} gross={c['gross']:9.0f} "
                      f"netfs={c['net_fees_slip']:9.0f} wr={c['win_rate']:.3f} "
                      f"avgL={c['avg_loss']:8.0f} worstL={c['worst_loss']:8.0f} "
                      f"mdd={c['max_drawdown']:9.0f} winD={c['winner_dollars']:8.0f} "
                      f"d={c.get('delta_vs_baseline')}")
