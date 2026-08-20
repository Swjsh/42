#!/usr/bin/env python
"""/fable-too-good artifact hunt for the stop-mode matrix.

Almost every simulated cell beats the simulated production cell. When 30 of 32 alternatives
beat the incumbent, the usual cause is the HARNESS, not the lever. This module hunts:
  1. selection bias in the STRUCTABLE sub-population
  2. day-concentration of every delta (top day / top trade share, days-positive)
  3. shape-flip fragility (does the cell win under BOTH upside rules?)
  4. chronological-half sign stability
  5. what each cell does to the RIGHT TAIL (the top-5 realized winners)
  6. stop-fill optimism exposure (how many stop fills each cell collects)
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

OUT = S.REPO / "analysis" / "deep-research" / "LOSSES-STOP-MODE-HUNT-2026-08-19.json"
PROD = "STRUCTURE+cap50"


def main():
    m, rows, results, per_trade, uncomputable, no_bars = S.main()
    labels = [c[2] for c in S.build_cells()]
    struct_keys = sorted(set(t["key"] for t in results[("RIBBON", PROD)]))
    sk = set(struct_keys)
    full_keys = list(range(len(rows)))

    rep = {"generated_at_et": dt.datetime.now().isoformat(timespec="seconds")}

    # ---- 1. selection bias in STRUCTABLE -------------------------------
    def book(idxs):
        g = sum(rows[i]["real_pnl_gross"] for i in idxs)
        w = [i for i in idxs if rows[i]["real_pnl_gross"] > 0]
        return {"n": len(idxs), "gross": round(g, 2), "wins": len(w),
                "wr": round(len(w) / len(idxs), 4) if idxs else None,
                "winner_dollars": round(sum(rows[i]["real_pnl_gross"] for i in w), 2),
                "n_days": len(set(rows[i]["date"] for i in idxs)),
                "date_span": [min(rows[i]["date"] for i in idxs),
                              max(rows[i]["date"] for i in idxs)] if idxs else None,
                "setups": sorted({rows[i]["setup"] for i in idxs}),
                "arms": sorted({rows[i]["arm"] for i in idxs})}
    rep["selection_bias"] = {
        "STRUCTABLE (trigger_level present)": book(struct_keys),
        "EXCLUDED (no trigger_level)": book([i for i in full_keys if i not in sk]),
        "FULL": book(full_keys),
        "verdict_note": ("If the two halves differ materially in realized P&L or date span, "
                         "the STRUCTABLE matrix is scored on a non-representative slice and "
                         "its levels do not generalise to the book."),
    }

    # ---- 2..6 per cell --------------------------------------------------
    realized_by_key = {i: rows[i]["real_pnl_gross"] for i in full_keys}
    top5 = sorted(full_keys, key=lambda i: -realized_by_key[i])[:5]

    cells = {}
    for pop_name, keys in (("STRUCTABLE", struct_keys), ("FULL", full_keys)):
        kset = set(keys)
        for shape in S.UPSIDE:
            base_tr = {t["key"]: t for t in results[(shape, PROD)] if t["key"] in kset}
            have_base = len(base_tr) == len(keys)
            for lab in labels:
                tr = {t["key"]: t for t in results[(shape, lab)] if t["key"] in kset}
                if len(tr) != len(keys):
                    continue
                ent = cells.setdefault((pop_name, lab), {})
                pnl = {k: v["pnl_gross"] for k, v in tr.items()}
                g = sum(pnl.values())
                ent[shape] = {
                    "gross": round(g, 2),
                    "vs_realized": round(g - sum(realized_by_key[k] for k in keys), 2),
                    "stop_fills": sum(1 for v in tr.values()
                                      if v["reason"] in ("premium_stop", "trail_stop",
                                                         "catastrophe_cap", "structure_stop",
                                                         "spy_move_stop")),
                }
                if have_base:
                    d = {k: pnl[k] - base_tr[k]["pnl_gross"] for k in keys}
                    byday = defaultdict(float)
                    for k, v in d.items():
                        byday[rows[k]["date"]] += v
                    absum = sum(abs(v) for v in d.values())
                    tot = sum(d.values())
                    halves = sorted(keys, key=lambda k: rows[k]["entry_ts_et"])
                    h1 = sum(d[k] for k in halves[:len(halves) // 2])
                    h2 = sum(d[k] for k in halves[len(halves) // 2:])
                    bd = sorted(byday.items(), key=lambda kv: -abs(kv[1]))
                    ent[shape].update({
                        "delta_vs_prod": round(tot, 2),
                        "delta_top_day": bd[0][0] if bd else None,
                        "delta_top_day_value": round(bd[0][1], 2) if bd else None,
                        "delta_top_day_share": round(abs(bd[0][1]) / absum, 4) if absum else None,
                        "delta_top_trade_share": round(max(abs(v) for v in d.values()) / absum, 4)
                        if absum else None,
                        "delta_days_positive": sum(1 for v in byday.values() if v > 0),
                        "delta_days_total": len(byday),
                        "delta_drop_best_day": round(tot - bd[0][1], 2) if bd else None,
                        "half1": round(h1, 2), "half2": round(h2, 2),
                        "halves_agree_sign": (h1 > 0) == (h2 > 0),
                    })
                # right tail: what did this cell do to the 5 biggest REALIZED winners
                tt = [k for k in top5 if k in tr]
                if tt:
                    ent[shape]["top5_realized_winner_dollars"] = round(
                        sum(realized_by_key[k] for k in tt), 2)
                    ent[shape]["top5_in_this_cell"] = round(sum(pnl[k] for k in tt), 2)
                    ent[shape]["top5_kept_frac"] = round(
                        sum(pnl[k] for k in tt) / sum(realized_by_key[k] for k in tt), 4)

    out = {}
    for (pop_name, lab), ent in cells.items():
        if "RIBBON" not in ent or "SAFE" not in ent:
            continue
        r, s = ent["RIBBON"], ent["SAFE"]
        ent["shape_flip_fragile"] = (r["gross"] > 0) != (s["gross"] > 0)
        if "delta_vs_prod" in r and "delta_vs_prod" in s:
            ent["delta_sign_agrees_across_shapes"] = (
                (r["delta_vs_prod"] > 0) == (s["delta_vs_prod"] > 0))
        out.setdefault(pop_name, {})[lab] = ent
    rep["cells"] = out

    # ---- day-level view of the whole book -------------------------------
    byday = defaultdict(float)
    for i in full_keys:
        byday[rows[i]["date"]] += realized_by_key[i]
    ordered = sorted(byday.items(), key=lambda kv: -abs(kv[1]))
    rep["realized_day_concentration"] = {
        "n_days": len(byday), "total": round(sum(byday.values()), 2),
        "top5_days": [(d, round(v, 2)) for d, v in ordered[:5]],
        "top_day_share_of_abs": round(abs(ordered[0][1]) / sum(abs(v) for v in byday.values()), 4),
        "days_positive": sum(1 for v in byday.values() if v > 0),
    }
    # right tail of the realized book
    srt = sorted(full_keys, key=lambda i: -realized_by_key[i])
    wins = [i for i in srt if realized_by_key[i] > 0]
    wd = sum(realized_by_key[i] for i in wins)
    rep["realized_right_tail"] = {
        "winner_dollars": round(wd, 2),
        "top5_share_of_winner_dollars": round(
            sum(realized_by_key[i] for i in srt[:5]) / wd, 4),
        "top5": [{"date": rows[i]["date"], "arm": rows[i]["arm"], "symbol": rows[i]["symbol"],
                  "pnl": realized_by_key[i], "exit_stage": rows[i]["exit_stage"],
                  "mfe_pct": rows[i].get("mfe_pct")} for i in srt[:5]],
    }
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("wrote", OUT)
    return rep


if __name__ == "__main__":
    rep = main()
    print(json.dumps(rep["selection_bias"], indent=1))
    print(json.dumps(rep["realized_day_concentration"], indent=1))
    print(json.dumps(rep["realized_right_tail"], indent=1))
