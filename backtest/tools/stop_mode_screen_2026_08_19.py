#!/usr/bin/env python
"""Final screen: which stop-mode cell, if any, survives the honesty gates.

Two reference points, both stated, never blended:
  * REALIZED  -- the book as actually traded. Ground truth. External reference.
  * NO_STOP   -- the same harness, same upside rule, ZERO downside management. Internal
                 reference. A cell's delta vs NO_STOP is the pure stop-lever effect, free of
                 the harness's upside-rule difference.

The simulated STRUCTURE cell is NOT used as the production baseline: it is a
re-implementation, and it misses the realized book by thousands of dollars on the identical
rows (reported as harness_fidelity). Quoting deltas against it would credit every alternative
with the re-implementation's own error.

GATES (a cell must pass ALL to be called anything but noise):
  G1 beats REALIZED after fees + measured exit slippage, on its population
  G2 positive delta vs NO_STOP under BOTH upside shapes (no shape flip)
  G3 delta vs NO_STOP survives dropping its single best day
  G4 chronological halves agree in sign
  G5 top single day is < 50% of the summed |delta|
  G6 holds on BOTH populations (recent-era STRUCTABLE and FULL)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stop_mode_matrix_2026_08_19 as S  # noqa: E402

OUT = S.REPO / "analysis" / "deep-research" / "LOSSES-STOP-MODE-SCREEN-2026-08-19.json"
REF = "NO_STOP (15:40 time stop only)"
PROD_SIM = "STRUCTURE+cap50"


def concentration(d, rows):
    byday = defaultdict(float)
    for k, v in d.items():
        byday[rows[k]["date"]] += v
    absum = sum(abs(v) for v in d.values())
    if not absum:
        # the reference cell against itself -- an exact zero, not a missing value
        return {"delta": 0.0, "top_day": None, "top_day_value": 0.0, "top_day_share": 0.0,
                "top_trade_share": 0.0, "drop_best_day": 0.0, "days_positive": 0,
                "days_total": len(set(rows[k]["date"] for k in d))}
    bd = sorted(byday.items(), key=lambda kv: -abs(kv[1]))
    tot = sum(d.values())
    return {
        "delta": round(tot, 2),
        "top_day": bd[0][0], "top_day_value": round(bd[0][1], 2),
        "top_day_share": round(abs(bd[0][1]) / absum, 4),
        "top_trade_share": round(max(abs(v) for v in d.values()) / absum, 4),
        "drop_best_day": round(tot - bd[0][1], 2),
        "days_positive": sum(1 for v in byday.values() if v > 0),
        "days_total": len(byday),
    }


def main():
    m, rows, results, per_trade, uncomputable, no_bars = S.main()
    labels = [c[2] for c in S.build_cells()]
    struct_keys = sorted(set(t["key"] for t in results[("RIBBON", PROD_SIM)]))
    pops = {"STRUCTABLE": struct_keys, "FULL": list(range(len(rows)))}

    def realized_net(keys):
        g = sum(rows[i]["real_pnl_gross"] for i in keys)
        fee = sum(rows[i]["fee_total_ex_cat"] for i in keys)
        slip = sum(rows[i]["qty"] * S.EXIT_SLIP_PREMIUM * 100.0 for i in keys)
        return g, g - fee, g - fee - slip

    rep = {"generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
           "gates": {"G1": "beats REALIZED after fees+slippage",
                     "G2": "delta vs NO_STOP positive under BOTH upside shapes",
                     "G3": "delta vs NO_STOP survives dropping its best day",
                     "G4": "chronological halves agree in sign",
                     "G5": "top day < 50% of summed |delta|",
                     "G6": "passes on BOTH populations"},
           "reference_note": ("NO_STOP = identical harness, identical upside rule, zero "
                              "downside management. Delta vs NO_STOP is the pure stop lever."),
           "harness_fidelity": {}, "realized": {}, "cells": {}}

    for pname, keys in pops.items():
        g, nf, nfs = realized_net(keys)
        rep["realized"][pname] = {"n": len(keys), "gross": round(g, 2),
                                  "net_fees": round(nf, 2), "net_fees_slip": round(nfs, 2)}
        kset = set(keys)
        for shape in S.UPSIDE:
            sim_prod = [t for t in results[(shape, PROD_SIM)] if t["key"] in kset]
            if len(sim_prod) == len(keys):
                sp = sum(t["pnl_gross"] for t in sim_prod)
                rep["harness_fidelity"][pname + "|" + shape] = {
                    "realized_gross": round(g, 2), "sim_STRUCTURE_gross": round(sp, 2),
                    "gap": round(sp - g, 2),
                    "reading": ("the simulated structure stop is a RE-IMPLEMENTATION and does "
                                "not reproduce the traded book; it is therefore NOT used as the "
                                "delta baseline")}

    for pname, keys in pops.items():
        kset = set(keys)
        g, nf, nfs = realized_net(keys)
        for lab in labels:
            per_shape = {}
            ok = True
            for shape in S.UPSIDE:
                tr = {t["key"]: t for t in results[(shape, lab)] if t["key"] in kset}
                ref = {t["key"]: t for t in results[(shape, REF)] if t["key"] in kset}
                if len(tr) != len(keys) or len(ref) != len(keys):
                    ok = False
                    break
                gross = sum(t["pnl_gross"] for t in tr.values())
                fees = sum(t["fee"] for t in tr.values())
                slip = sum(t["slip"] for t in tr.values())
                wins = [t for t in tr.values() if t["pnl_gross"] > 0]
                losses = [t for t in tr.values() if t["pnl_gross"] < 0]
                chrono = sorted(tr.values(), key=lambda t: t["exit_ts"])
                peak = cum = mdd = 0.0
                for t in chrono:
                    cum += t["pnl_gross"]
                    peak = max(peak, cum)
                    mdd = min(mdd, cum - peak)
                d = {k: tr[k]["pnl_gross"] - ref[k]["pnl_gross"] for k in keys}
                con = concentration(d, rows)
                order = sorted(keys, key=lambda k: rows[k]["entry_ts_et"])
                h1 = sum(d[k] for k in order[:len(order) // 2])
                h2 = sum(d[k] for k in order[len(order) // 2:])
                per_shape[shape] = {
                    "gross": round(gross, 2),
                    "net_fees": round(gross - fees, 2),
                    "net_fees_slip": round(gross - fees - slip, 2),
                    "win_rate": round(len(wins) / len(tr), 4),
                    "avg_loss": round(sum(t["pnl_gross"] for t in losses) / len(losses), 2)
                    if losses else 0.0,
                    "worst_loss": round(min([t["pnl_gross"] for t in losses]), 2) if losses else 0.0,
                    "max_drawdown": round(mdd, 2),
                    "winner_dollars": round(sum(t["pnl_gross"] for t in wins), 2),
                    "loser_dollars": round(sum(t["pnl_gross"] for t in losses), 2),
                    "vs_realized_gross": round(gross - g, 2),
                    "vs_realized_net_fees_slip": round((gross - fees - slip) - nfs, 2),
                    "vs_NO_STOP": con,
                    "half1": round(h1, 2), "half2": round(h2, 2),
                    "halves_agree": (h1 > 0) == (h2 > 0),
                    "stop_fill_share": round(sum(
                        1 for t in tr.values() if t["reason"] in
                        ("premium_stop", "trail_stop", "catastrophe_cap",
                         "structure_stop", "spy_move_stop")) / len(tr), 4),
                }
            if not ok:
                continue
            r, s = per_shape["RIBBON"], per_shape["SAFE"]
            gates = {
                "G1": r["vs_realized_net_fees_slip"] > 0 and s["vs_realized_net_fees_slip"] > 0,
                "G2": r["vs_NO_STOP"]["delta"] > 0 and s["vs_NO_STOP"]["delta"] > 0,
                "G3": r["vs_NO_STOP"]["drop_best_day"] > 0 and s["vs_NO_STOP"]["drop_best_day"] > 0,
                "G4": r["halves_agree"] and s["halves_agree"],
                "G5": r["vs_NO_STOP"]["top_day_share"] < 0.50
                and s["vs_NO_STOP"]["top_day_share"] < 0.50,
            }
            rep["cells"].setdefault(pname, {})[lab] = {"shapes": per_shape, "gates": gates,
                                                       "gates_passed": sum(gates.values())}

    # G6: cross-population
    for lab in labels:
        a = rep["cells"].get("STRUCTABLE", {}).get(lab)
        b = rep["cells"].get("FULL", {}).get(lab)
        g6 = bool(a and b and all(a["gates"].values()) and all(b["gates"].values()))
        for e in (a, b):
            if e:
                e["gates"]["G6"] = g6
                e["gates_passed"] = sum(e["gates"].values())
                e["SURVIVES_ALL"] = all(e["gates"].values())
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("wrote", OUT)
    return rep, rows


if __name__ == "__main__":
    rep, rows = main()
    for pname in ("STRUCTABLE", "FULL"):
        print("\n########", pname, "realized:", rep["realized"][pname])
        cs = rep["cells"][pname]
        for lab, e in sorted(cs.items(), key=lambda kv: -kv[1]["shapes"]["RIBBON"]["gross"]):
            r, s = e["shapes"]["RIBBON"], e["shapes"]["SAFE"]
            print(f"{lab:26s} R:{r['gross']:8.0f}/{r['net_fees_slip']:8.0f} "
                  f"S:{s['gross']:8.0f}/{s['net_fees_slip']:8.0f} "
                  f"dNS R{r['vs_NO_STOP']['delta']:8.0f} S{s['vs_NO_STOP']['delta']:8.0f} "
                  f"tdShr {r['vs_NO_STOP']['top_day_share']:.2f}/{s['vs_NO_STOP']['top_day_share']:.2f} "
                  f"gates={''.join(k for k, v in e['gates'].items() if v) or '-'} "
                  f"{'SURVIVES' if e.get('SURVIVES_ALL') else ''}")
