"""Confirmatory A/B for prereg STOP-MODE-STRUCTURE-VS-PREMIUM-2026-08-09 (commit 2a36724a).

Pre-registered BEFORE this file existed. The hypothesis, mechanism, gates, kill criteria and the
"will not ship on this run" rule all live in that frozen JSON -- this runner only executes it.

Three arms, differing from the shipped ribbon_ride exit shape in ONE field each (except the third,
which is deliberately two, to separate a cap effect from the mode effect):

  CONTROL           exactly fleet_strategies.by_name("ribbon_ride").exit
  PREMIUM_20        stop_mode: structure -> premium. Nothing else. Because BASE_EXIT already
                    carries premium_stop_pct=-0.20, this is precisely "turn the structure stop
                    off and use the flat -20% premium stop that is already configured".
  PREMIUM_20_CAP60  as PREMIUM_20 plus catastrophe_stop_pct -0.50 -> -0.60.

Both populations, every pre-registered entry row, full canonical battery per cell, BH-FDR across
every cell this study tests. Every cell reported including failures.
"""

from __future__ import annotations

import json
import sys
import time as _time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "automation" / "state" / "fleet"),
           str(ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import entry_exit_matrix_2026_08_09 as eem  # noqa: E402
import score_ladder_replay_2026_08_07 as sl  # noqa: E402
import engine_fullhist_replay as efr  # noqa: E402

PREREG = ROOT / "analysis" / "recommendations" / "prereg-stop-mode-structure-vs-premium-2026-08-09.json"
OUT = ROOT / "analysis" / "recommendations" / "stop-mode-structure-vs-premium-2026-08-09.json"


def _arm(**over) -> dict:
    d = dict(eem.BASE_EXIT)
    d.update(over)
    return d


ARMS = {
    "CONTROL": _arm(),
    "PREMIUM_20": _arm(stop_mode="premium"),
    "PREMIUM_20_CAP60": _arm(stop_mode="premium", catastrophe_stop_pct=-0.60),
}


def log(m: str) -> None:
    print(f"[stop-mode] {m}", flush=True)


def main() -> int:
    t0 = _time.time()
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    log(f"prereg {prereg['prereg_id']} frozen {prereg['frozen_at_et']}")
    for name, shape in ARMS.items():
        log(f"  arm {name}: stop_mode={shape['stop_mode']} "
            f"premium_stop_pct={shape['premium_stop_pct']} cat={shape['catastrophe_stop_pct']}")

    spy_raw, vix_df = eem.load_extended_data()
    spy_rth = sl.build_rth_frame(spy_raw)
    r, bear_by_idx, bull_by_idx = sl.run_backtest_with_full_capture(
        spy_raw, vix_df, start_date=eem.FULL_START, end_date=eem.FULL_END, **sl.SAFE_BASE_LIVE_NOW)
    ribbon_lookup = efr.build_ribbon_lookup(spy_raw)
    log(f"population loaded ({_time.time()-t0:.0f}s)")

    cells: dict[str, dict] = {}

    rows_a = eem.build_rows_pop_a(r.trades, bear_by_idx, bull_by_idx, spy_rth)
    for rid in eem.ROW_ORDER:
        blk = rows_a[rid]
        for aname, shape in ARMS.items():
            t1 = _time.time()
            lane = eem.walk_lane_dynamic_shape(blk["rung"], blk["candidates"], blk["binary"],
                                               spy_rth, ribbon_lookup, eem._static_col(shape))
            b = eem.battery(lane["trades"])
            b["n_excluded"] = len(lane["excluded"])
            b["suppressed_binary"] = lane["suppressed_binary"]
            cells[f"A|{rid}|{aname}"] = b
            log(f"A {rid:9s} {aname:17s} n={b['n']:5d} exp=${b['expectancy'] or 0:>8.2f} "
                f"p={b['bootstrap_p_mean_gt0']} ({_time.time()-t1:.0f}s)")

    events, meta = eem.load_ledger_events()
    rows_b = eem.build_rows_pop_b(events)
    for rid in ["CONTROL", "STRUCT8", "VD1", "MAX3"]:
        for aname, shape in ARMS.items():
            lane = eem.walk_events_sequential(rows_b[rid], eem._static_col(shape),
                                              spy_rth, ribbon_lookup)
            b = eem.battery(lane["trades"])
            b["n_excluded"] = len(lane["excluded"])
            b["suppressed_binary"] = lane["suppressed_binary"]
            cells[f"B|{rid}|{aname}"] = b
            log(f"B {rid:9s} {aname:17s} n={b['n']:5d} exp=${b['expectancy'] or 0:>8.2f} "
                f"p={b['bootstrap_p_mean_gt0']}")

    # ---- BH across every cell this study tested
    pvals = {k: v.get("bootstrap_p_mean_gt0") for k, v in cells.items() if v.get("n", 0) >= 5}
    bh = sl.benjamini_hochberg(pvals, q=0.10)

    # ---- pre-registered deltas + mechanism signature
    deltas = {}
    for pop, rlist in (("A", eem.ROW_ORDER), ("B", ["CONTROL", "STRUCT8", "VD1", "MAX3"])):
        for rid in rlist:
            c = cells.get(f"{pop}|{rid}|CONTROL", {})
            for aname in ("PREMIUM_20", "PREMIUM_20_CAP60"):
                a = cells.get(f"{pop}|{rid}|{aname}", {})
                if not c.get("n") or not a.get("n"):
                    continue
                d_exp = round((a["expectancy"] or 0) - (c["expectancy"] or 0), 2)
                d_wr = round((a["wr"] or 0) - (c["wr"] or 0), 4)
                deltas[f"{pop}|{rid}|{aname}"] = {
                    "delta_expectancy": d_exp, "delta_wr": d_wr,
                    "delta_total": round((a["total"] or 0) - (c["total"] or 0), 2),
                    "mechanism_signature_holds": bool(d_exp > 0 and d_wr < 0),
                    "arm_drop_best_day_exp": a.get("drop_best_day_expectancy"),
                    "arm_sub_window_stable": a.get("sub_window_stable"),
                    "arm_tuesday_total": a.get("tuesday_0804_total"),
                    "arm_tuesday_n": a.get("tuesday_0804_n"),
                }

    prem = [v for k, v in deltas.items() if k.endswith("PREMIUM_20")]
    a_pos = [v for k, v in deltas.items() if k.startswith("A|") and k.endswith("PREMIUM_20")
             and v["delta_expectancy"] > 0]
    b_pos = [v for k, v in deltas.items() if k.startswith("B|") and k.endswith("PREMIUM_20")
             and v["delta_expectancy"] > 0]
    a_all = [v for k, v in deltas.items() if k.startswith("A|") and k.endswith("PREMIUM_20")]
    b_all = [v for k, v in deltas.items() if k.startswith("B|") and k.endswith("PREMIUM_20")]
    tue_eval = [v for v in prem if (v["arm_tuesday_n"] or 0) > 0]

    verdict = {
        "populations_agree_in_sign": bool(a_pos and b_pos and len(a_pos) == len(a_all)
                                          and len(b_pos) == len(b_all)),
        "pop_a_rows_positive": f"{len(a_pos)}/{len(a_all)}",
        "pop_b_rows_positive": f"{len(b_pos)}/{len(b_all)}",
        "mechanism_signature_rows": f"{sum(1 for v in prem if v['mechanism_signature_holds'])}/{len(prem)}",
        "tuesday_gate_evaluable_cells": len(tue_eval),
        "bh_survivors": sorted([k for k, v in bh.items() if v]),
        "ships_tonight": False,
        "ship_block_reason": prereg["ship_rule"]["why"],
    }

    OUT.write_text(json.dumps({
        "prereg_id": prereg["prereg_id"], "prereg_commit": "2a36724a",
        "generated_at_et": prereg["frozen_at_et"] + " (runner executed same session)",
        "arms": {k: v for k, v in ARMS.items()},
        "cells": cells, "deltas": deltas, "bh_pass_q010": bh, "verdict": verdict,
        "runtime_seconds": round(_time.time() - t0, 1),
    }, indent=1, default=str), encoding="utf-8")
    log(f"\n{json.dumps(verdict, indent=1)}")
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
