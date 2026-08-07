"""f10_f7_population_battery_2026_08_07.py -- LANE 2 parts 2-4: execute the FROZEN
bull-f10 buyer-pressure prereg (queued since 08-03, never run) + the freshly-frozen
bull-f7 volume-divergence prereg + joint cells, on the full 391-day real-OPRA population.

PREREGS (both committed BEFORE this file existed -- git-provable):
  F10: analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json
       cells f10_vol_mult {0.7 baseline, 0.5, 0.35, 0.0}; gates: added-cohort OOS-positive,
       WF>=0.70 or disclosed-null, no month >50% of added P&L, anchor no-regression,
       drop-best, decision floor n>=20. BH family = the 3 relax cells.
  F7:  analysis/recommendations/bull-f7-volume-divergence-prereg-2026-08-07.json
       (committed 94157aa6 BEFORE this runner) cells {f7_off, joint_relax35, joint_off};
       same gates; separate BH family; joint cells are sequential replays through the
       orchestrator, never sums of single-relax cells.

MACHINERY: imports bull_gate_f5class_requal_2026_08_01 (the battery template both preregs
cite) and reuses its data loading (et-v2 C6 discipline), added-cohort diff, walk_exit_manager
re-walk (real production exit core, RIBBON_RIDE registry shape), cell stats, drop-best and
BH-FDR verbatim -- no re-derivation.

SHARED-KWARG CONFOUND (frozen handling, per the F7 prereg's disclosure block): the
orchestrator's disable_filters and f9_vol_mult are shared bear+bull knobs. Every cell
therefore also reports BEAR-side drift vs baseline; the PRIMARY gate-bearing added-bull
cohort is restricted to days with ZERO bear-side drift ("clean days"); the full added
cohort is a sensitivity slice. backtest/lib is read-only during market hours (Rule 9) so a
bull-only kwarg cannot be added before 15:55 ET; the evening package may add one and re-run.

ANCHOR RULE (exact, stated here so no judgment is left in the verdict): baseline bull
trades MISSING from a relax run (crowded out by the one-position constraint) are re-walked
at baseline config; anchor_no_regression PASSES iff their aggregate walked P&L (the
forfeit) is <= 0 -- i.e. the relax may only crowd out aggregate losers.

Rail-4 CLEAR: analysis only. No live network reads (real OPRA cache only; missing contracts
dropped and counted, never imputed -- C7).

Run: backtest/.venv/Scripts/python.exe backtest/tools/f10_f7_population_battery_2026_08_07.py
     [--smoke]   last 10 sessions only (mechanism check) -> .smoke.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bull_gate_f5class_requal_2026_08_01 as f5t  # noqa: E402  -- the battery template
from lib.orchestrator import run_backtest  # noqa: E402

PREREG_F10 = ROOT / "analysis" / "recommendations" / "bull-f10-buyer-pressure-prereg-2026-08-04.json"
PREREG_F7 = ROOT / "analysis" / "recommendations" / "bull-f7-volume-divergence-prereg-2026-08-07.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "f10-f7-population-battery-2026-08-07.json"
SMOKE_JSON = ROOT / "analysis" / "recommendations" / "f10-f7-population-battery-2026-08-07.smoke.json"

# (cell_name, f9_vol_mult, disable_filters, bh_family)
CELLS = [
    ("f10_relax_50", 0.5, None, "f10"),
    ("f10_relax_35", 0.35, None, "f10"),
    ("f10_off", 0.0, None, "f10"),
    ("f7_off", 0.7, [7], "f7"),
    ("joint_relax35", 0.35, [7], "f7"),
    ("joint_off", 0.0, [7], "f7"),
]


def log(m: str) -> None:
    print(f"[f10-f7-battery] {m}", flush=True)


def cfg(f9: float, disable: list[int] | None) -> dict:
    c = dict(f5t.SAFE_BASE_LIVE, f9_vol_mult=f9)
    if disable:
        c["disable_filters"] = list(disable)
    return c


def trade_key(t) -> tuple:
    return (f5t._et_naive(t.entry_time_et), t.side, round(float(t.strike), 2))


def bear_drift(base, variant) -> dict:
    bk = {trade_key(t) for t in base.trades if t.side == "P"}
    vk = {trade_key(t) for t in variant.trades if t.side == "P"}
    added = sorted(vk - bk)
    removed = sorted(bk - vk)
    dirty_days = sorted({k[0].date().isoformat() for k in (vk ^ bk)})
    return {"bear_added_n": len(added), "bear_removed_n": len(removed),
            "dirty_days": dirty_days}


def missing_baseline_bulls(base, variant) -> list:
    vk = {trade_key(t) for t in variant.trades}
    return [t for t in base.trades if t.side == "C" and trade_key(t) not in vk]


def month_shares(trades: list[dict]) -> dict:
    by_month: dict[str, float] = {}
    for t in trades:
        by_month[t["date"][:7]] = round(by_month.get(t["date"][:7], 0.0) + t["pnl"], 2)
    total = sum(by_month.values())
    max_share = (round(max(by_month.values()) / total, 3)
                 if total > 0 and by_month else None)
    return {"by_month": by_month, "max_month_share": max_share,
            "stable": (max_share is not None and max_share <= 0.5) if total > 0 else False}


def gate_cell(clean: dict, anchor_forfeit: float, months: dict) -> dict:
    n = clean["n"]
    floor_ok = n >= f5t.N_FLOOR
    oos_ok = clean["recent_25"]["total_pnl"] > 0
    sub_ok = bool(months["stable"])
    anchor_ok = anchor_forfeit <= 0
    drop_ok = bool(clean["drop_best"]["still_positive"])
    verdict = "NO_VERDICT_BELOW_FLOOR" if not floor_ok else (
        "PASS_ALL_GATES" if (oos_ok and sub_ok and anchor_ok and drop_ok
                             and clean["total_pnl"] > 0) else "FAIL")
    return {"decision_floor_n20": floor_ok, "oos_positive_recent25": oos_ok,
            "wf": "disclosed-null (no WF harness in this battery -- standing escape hatch)",
            "sub_window_stable": sub_ok,
            "anchor_no_regression": anchor_ok,
            "anchor_forfeit_dollars": round(anchor_forfeit, 2),
            "drop_best": drop_ok, "aggregate_positive": clean["total_pnl"] > 0,
            "verdict": verdict}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    for p in (PREREG_F10, PREREG_F7):
        j = json.loads(p.read_text(encoding="utf-8"))
        log(f"prereg loaded: {p.name} (frozen {j.get('frozen_at_et')})")

    log("loading SPY/VIX merged frames (et-v2, template lineage)")
    spy_raw = f5t.load_merged(f5t.OLD_SPY, f5t.NEW_SPY)
    vix_raw = f5t.load_merged(f5t.OLD_VIX, f5t.NEW_VIX)
    spy_rth = f5t.build_rth(spy_raw)
    all_days = [d for d in sorted(spy_rth["timestamp_et"].dt.date.unique())
                if f5t.FULL_START <= d <= f5t.FULL_END and d not in f5t.HALF_DAYS]
    log(f"population: {len(all_days)} sessions (expected {f5t.EXPECTED_DAYS})")
    if len(all_days) != f5t.EXPECTED_DAYS:
        log("FATAL: population mismatch")
        return 1
    recent_start = all_days[-25].isoformat()

    if args.smoke:
        run_start, run_end = all_days[-10], all_days[-1]
        log(f"SMOKE: {run_start}..{run_end}")
    else:
        run_start, run_end = f5t.FULL_START, f5t.FULL_END

    ribbon_lookup = f5t.build_ribbon_lookup(spy_rth)
    day_frames = f5t.build_day_frames(spy_rth)

    log("running BASELINE (production SAFE_BASE_LIVE, f10_vol_mult=0.7, all filters on)")
    base = run_backtest(spy_raw, vix_raw, start_date=run_start, end_date=run_end,
                        **cfg(0.7, None))
    log(f"baseline trades n={len(base.trades)}")

    cells_out, grades, pvals_by_family = {}, {}, {"f10": [], "f7": []}
    family_keys = {"f10": [], "f7": []}

    for cell_name, f9, disable, family in CELLS:
        log(f"running cell {cell_name} (f9_vol_mult={f9}, disable={disable})")
        variant = run_backtest(spy_raw, vix_raw, start_date=run_start, end_date=run_end,
                               **cfg(f9, disable))
        added = f5t.added_bull_cohort(base, variant)
        drift = bear_drift(base, variant)
        missing = missing_baseline_bulls(base, variant)
        log(f"  added={len(added)} bear_drift +{drift['bear_added_n']}/-{drift['bear_removed_n']} "
            f"dirty_days={len(drift['dirty_days'])} missing_baseline_bulls={len(missing)}")

        replays, n_missing = [], 0
        for t in added:
            r = f5t.requalify_trade(t, ribbon_lookup, day_frames)
            if r is None:
                n_missing += 1
            else:
                replays.append(r)
        dirty = set(drift["dirty_days"])
        clean_replays = [r for r in replays if r["date"] not in dirty]

        forfeit_replays, forfeit_missing = [], 0
        for t in missing:
            r = f5t.requalify_trade(t, ribbon_lookup, day_frames)
            if r is None:
                forfeit_missing += 1
            else:
                forfeit_replays.append(r)
        anchor_forfeit = sum(r["pnl"] for r in forfeit_replays)

        clean_stats = f5t.cell_stats(clean_replays, n_missing, recent_start)
        full_stats = f5t.cell_stats(replays, n_missing, recent_start)
        months = month_shares(clean_replays)
        per_unit = ([r["pnl"] / max(1, r["qty"]) for r in clean_replays])
        qty10_naive = round(sum(per_unit) * 10.0 / max(1, 1), 2) if per_unit else 0.0

        grade = gate_cell(clean_stats, anchor_forfeit, months)
        cells_out[cell_name] = {
            "config": {"f10_vol_mult": f9, "disable_filters": disable},
            "added_raw_n": len(added), "n_missing_opra": n_missing,
            "bear_drift": drift,
            "clean_day_added_cohort_PRIMARY": clean_stats,
            "full_added_cohort_sensitivity": full_stats,
            "month_shares_clean": months,
            "anchor": {"missing_baseline_bulls_n": len(missing),
                       "forfeit_walked_pnl": round(anchor_forfeit, 2),
                       "forfeit_unpriceable_n": forfeit_missing},
            "bold_qty10_naive_scale_clean_total": qty10_naive,
        }
        grades[cell_name] = grade
        pvals_by_family[family].append(clean_stats["p_value_raw"])
        family_keys[family].append(cell_name)
        log(f"  {cell_name}: clean n={clean_stats['n']} total=${clean_stats['total_pnl']} "
            f"verdict={grade['verdict']}")

    for fam in ("f10", "f7"):
        sig = f5t.bh_fdr(pvals_by_family[fam], q=0.10)
        for k, s in zip(family_keys[fam], sig):
            cells_out[k]["bh_fdr_significant_q10"] = bool(s)

    out = {
        "_doc": "Frozen-prereg execution: bull F10 buyer-pressure grid + bull F7 "
                "volume-divergence + joint cells, full 391-day real-OPRA battery. "
                "PRIMARY cohort = clean days (zero bear-side drift). ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregs": [str(PREREG_F10.relative_to(ROOT)).replace("\\", "/"),
                    str(PREREG_F7.relative_to(ROOT)).replace("\\", "/")],
        "smoke": bool(args.smoke),
        "window": [run_start.isoformat(), run_end.isoformat()],
        "recent_25_start": recent_start,
        "baseline_trade_count": len(base.trades),
        "baseline_bull_count": sum(1 for t in base.trades if t.side == "C"),
        "n_floor": f5t.N_FLOOR,
        "bh_families": family_keys,
        "anchor_rule": "PASS iff aggregate walked P&L of baseline bulls crowded out by the "
                       "relax is <= 0 (the relax may only crowd out aggregate losers)",
        "cells": cells_out,
        "grades": grades,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    dest = SMOKE_JSON if args.smoke else OUT_JSON
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {dest}")
    for k, g in grades.items():
        log(f"  {k}: {g['verdict']}")
    log(f"runtime {out['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
