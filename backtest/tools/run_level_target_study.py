"""run_level_target_study.py -- driver for level_target_exit_study.py. Builds the full
real-fills population, runs the incumbent baseline + all 144 frozen cells, evaluates gates
G1-G8, applies BH-FDR, and writes the deliverable JSON per the frozen prereg's
`deliverables_when_run` spec.

Run (backtest venv): backtest/.venv/Scripts/python.exe backtest/tools/run_level_target_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import level_target_exit_study as lts  # noqa: E402

BH_Q = 0.10
MIN_N = 30


# ---------------------------------------------------------------------------------------------
# stats helpers -- house convention (see backtest/tools/shelf_hold_reclaim_study.py's
# one_sample_p / bh_fdr; copied per this codebase's established per-study pattern rather than
# cross-importing another study's module as a dependency).
# ---------------------------------------------------------------------------------------------

def one_sample_p(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 1.0
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0 if mean == 0 else 0.0
    t = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))))


def bh_fdr(pvals: list[float], q: float = BH_Q) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= (rank + 1) / m * q:
            max_k = rank
    sig = [False] * m
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


def wf_norm(is_delta_total: float, n_is: int, oos_delta_total: float, n_oos: int) -> float:
    """Project-standard per-trade normalized WF ratio (backtest/autoresearch/
    vwap_pullback_ratify.py:_wf_norm, 'rolling_walk_forward.py L93'), applied here to the
    CELL's per-position DELTA vs incumbent (not raw pnl) so it answers 'does this cell's
    advantage persist OOS', exactly what G5 asks."""
    if n_is == 0 or n_oos == 0 or is_delta_total == 0:
        return 0.0
    return (oos_delta_total / n_oos) / (is_delta_total / n_is)


def load_runner_trail_cohort_keys() -> set:
    """(arm, symbol) pairs whose REAL production exit included a stage=='trail' leg --
    reuses setup/scripts/sampling_gap_ledger.py's already-built, already-verified join of
    decisions.jsonl/core-decisions.jsonl exit_pass rows to real fills (sub-problem A of this
    same investigation), rather than re-deriving it."""
    if not lts.SAMPLING_GAP_PATH.exists():
        return set()
    d = json.loads(lts.SAMPLING_GAP_PATH.read_text(encoding="utf-8"))
    return {(r["arm_or_account"], r["symbol"]) for r in d.get("all_scored_events", [])
           if r.get("stage") == "trail"}


def main() -> dict:
    t0 = _time_mod.time()
    positions, excl_pop = lts.build_population()
    daily_bars, spy5 = lts.load_spy_bars()

    prepared, excl_data = [], {"no_opt_bars": 0, "no_spot": 0, "level_reconstruction_failed": 0}
    resolution_counts: dict = {}
    for pos in positions:
        entry_dt_utc = dt.datetime.fromisoformat(pos["entry_ts_utc"].replace("Z", "+00:00"))
        entry_et = entry_dt_utc.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
        pos["_entry_ts_et_naive"] = entry_et
        opt_df, opt_resolution = lts.load_option_bars(pos["symbol"], date_et=pos["date_et"])
        if opt_df is None or opt_df.empty:
            excl_data["no_opt_bars"] += 1
            continue
        resolution_counts[opt_resolution] = resolution_counts.get(opt_resolution, 0) + 1
        pos["_opt_resolution"] = opt_resolution
        spot = lts.spot_at(spy5, entry_et)
        if spot is None:
            excl_data["no_spot"] += 1
            continue
        recon = lts.rla.reconstruct_levels(as_of_et=entry_et, daily_bars=daily_bars,
                                           five_min_df=spy5, spot=spot)
        if not recon.get("ok"):
            excl_data["level_reconstruction_failed"] += 1
            continue
        pos["_opt_df"] = opt_df
        pos["_spot_at_entry"] = spot
        pos["_levels"] = recon["levels"]
        prepared.append(pos)

    print(f"[t={_time_mod.time()-t0:.1f}s] population prepared: {len(prepared)} positions "
         f"(pop excl {excl_pop}, data excl {excl_data}, option-bar resolution {resolution_counts})")

    for pos in prepared:
        inc = lts.walk_position_incumbent(pos, pos["_opt_df"], spy5)
        pos["_incumbent_pnl"] = inc["pnl"]

    parity_harness_total = round(sum(p["_incumbent_pnl"] for p in prepared), 2)
    parity_actual_total = round(sum(p["actual_exit_pnl"] for p in prepared), 2)
    parity_gap_dollars = round(parity_harness_total - parity_actual_total, 2)
    parity_gap_pct = (round(parity_gap_dollars / parity_actual_total, 4)
                      if parity_actual_total else None)
    print(f"[t={_time_mod.time()-t0:.1f}s] harness parity: harness={parity_harness_total} "
         f"actual={parity_actual_total} gap={parity_gap_dollars} ({parity_gap_pct})")

    runner_cohort_keys = load_runner_trail_cohort_keys()
    for pos in prepared:
        pos["_is_runner_trail"] = (pos["arm"], pos["symbol"]) in runner_cohort_keys
    n_runner_cohort = sum(1 for p in prepared if p["_is_runner_trail"])
    print(f"[t={_time_mod.time()-t0:.1f}s] runner-trail cohort: {n_runner_cohort} positions "
         f"(source: {len(runner_cohort_keys)} (arm,symbol) keys from sampling-gap.json)")

    # ---- 144 cells --------------------------------------------------------------------------
    trading_days = sorted({p["date_et"] for p in prepared})
    n_days = len(trading_days)
    split_idx = max(1, int(round(n_days * 0.60)))
    is_days = set(trading_days[:split_idx])
    oos_days = set(trading_days[split_idx:])

    cells_raw = []
    n_walks = 0
    for rule in lts.TARGET_RULES:
        for reach in lts.MAX_REACH_SWEEP:
            key = f"_target_{rule}_{reach}"
            for pos in prepared:
                elig = lts.eligible_levels(pos["_levels"], pos["side"], pos["_spot_at_entry"],
                                           pos["trigger_level"], reach)
                pos[key] = lts.pick_target(elig, pos["_spot_at_entry"], rule)
            for band in lts.BAND_SWEEP:
                for form in lts.TRIGGER_FORMS:
                    for action in lts.ACTIONS:
                        rows = []
                        for pos in prepared:
                            tgt = pos[key]
                            if tgt is None:
                                rows.append({"pos": pos, "cell_pnl": pos["_incumbent_pnl"],
                                            "level_fired": False, "has_target": False})
                                continue
                            res = lts.walk_position_level_target(
                                pos, pos["_opt_df"], spy5, tgt["price"], band, form, action)
                            n_walks += 1
                            rows.append({"pos": pos, "cell_pnl": res["pnl"],
                                        "level_fired": res["level_fired"], "has_target": True})
                        cells_raw.append({
                            "target_rule": rule, "max_reach": reach, "band": band,
                            "trigger_form": form, "action": action, "rows": rows,
                        })
    print(f"[t={_time_mod.time()-t0:.1f}s] {len(cells_raw)} cells x {len(prepared)} positions "
         f"walked ({n_walks} level-target walks executed)")

    # ---- evaluate gates per cell --------------------------------------------------------------
    cells = []
    for c in cells_raw:
        rows = c["rows"]
        n_with_target = sum(1 for r in rows if r["has_target"])
        n_level_fired = sum(1 for r in rows if r["level_fired"])
        level_fired_rate = round(n_level_fired / len(rows), 4) if rows else 0.0

        deltas = [r["cell_pnl"] - r["pos"]["_incumbent_pnl"] for r in rows]
        cell_total = round(sum(r["cell_pnl"] for r in rows), 2)
        incumbent_total = round(sum(r["pos"]["_incumbent_pnl"] for r in rows), 2)
        aggregate_delta = round(cell_total - incumbent_total, 2)

        by_day: dict = {}
        for r, d in zip(rows, deltas):
            by_day.setdefault(r["pos"]["date_et"], []).append(d)
        day_deltas = {day: sum(v) for day, v in by_day.items()}
        n_days_flat_or_better = sum(1 for v in day_deltas.values() if v >= 0)
        day_majority_frac = (round(n_days_flat_or_better / len(day_deltas), 4)
                             if day_deltas else 0.0)

        total_delta = sum(deltas)
        best_day_delta = max(day_deltas.values()) if day_deltas else 0.0
        drop_best_day_delta = round(total_delta - best_day_delta, 2)
        best_trade_delta = max(deltas) if deltas else 0.0
        drop_best_trade_delta = round(total_delta - best_trade_delta, 2)

        cohort_rows = [r for r in rows if r["pos"]["_is_runner_trail"]]
        cohort_cell_total = round(sum(r["cell_pnl"] for r in cohort_rows), 2)
        cohort_incumbent_total = round(sum(r["pos"]["_incumbent_pnl"] for r in cohort_rows), 2)

        is_deltas = [d for r, d in zip(rows, deltas) if r["pos"]["date_et"] in is_days]
        oos_deltas = [d for r, d in zip(rows, deltas) if r["pos"]["date_et"] in oos_days]
        is_total, oos_total = sum(is_deltas), sum(oos_deltas)
        wf = wf_norm(is_total, len(is_deltas), oos_total, len(oos_deltas))

        pval = one_sample_p(deltas)

        G1 = aggregate_delta > 0
        G2 = day_majority_frac > 0.50
        G3 = (drop_best_day_delta > 0) and (drop_best_trade_delta > 0)
        G4 = cohort_cell_total >= cohort_incumbent_total
        G5 = (oos_total > 0) and (wf >= 0.70)
        G7 = level_fired_rate >= 0.50
        G8 = aggregate_delta > abs(parity_gap_dollars)

        underpowered = n_with_target < MIN_N
        cells.append({
            "target_rule": c["target_rule"], "max_reach": c["max_reach"], "band": c["band"],
            "trigger_form": c["trigger_form"], "action": c["action"],
            "n_positions_considered": len(rows), "n_with_target": n_with_target,
            "n_level_fired": n_level_fired, "level_fired_rate": level_fired_rate,
            "cell_total_pnl": cell_total, "incumbent_total_pnl": incumbent_total,
            "aggregate_delta": aggregate_delta, "p_value": round(pval, 6),
            "day_majority_frac": day_majority_frac,
            "drop_best_day_delta": drop_best_day_delta,
            "drop_best_trade_delta": drop_best_trade_delta,
            "runner_cohort_n": len(cohort_rows), "runner_cohort_cell_total": cohort_cell_total,
            "runner_cohort_incumbent_total": cohort_incumbent_total,
            "is_oos_split": {"n_is": len(is_deltas), "n_oos": len(oos_deltas),
                             "is_delta_total": round(is_total, 2),
                             "oos_delta_total": round(oos_total, 2), "wf_norm": round(wf, 4)},
            "underpowered": underpowered,
            "gates": {"G1_aggregate": G1, "G2_day_majority": G2, "G3_drop_best": G3,
                     "G4_runner_cohort_no_regression": G4, "G5_oos": G5, "G7_level_fired_rate": G7,
                     "G8_parity": G8},
        })

    pvals = [c["p_value"] for c in cells]
    sig = bh_fdr(pvals, q=BH_Q)
    for c, s in zip(cells, sig):
        c["gates"]["G6_bh_fdr"] = bool(s)
        gates = c["gates"]
        all_pass = all(gates.values())
        if c["underpowered"]:
            c["verdict"] = "INCONCLUSIVE_UNDERPOWERED"
        elif all_pass:
            c["verdict"] = "SHIP"
        else:
            c["verdict"] = "KILL"

    n_underpowered = sum(1 for c in cells if c["underpowered"])
    n_ship = sum(1 for c in cells if c["verdict"] == "SHIP")
    n_kill = sum(1 for c in cells if c["verdict"] == "KILL" and not c["underpowered"])
    overall_verdict = "SHIP" if n_ship > 0 else (
        "KILL" if n_underpowered < len(cells) else "INCONCLUSIVE_UNDERPOWERED")
    # kill_criterion per prereg: "No cell passes G1-G8, OR fewer than 30 positions resolve a
    # target on the primary cohort and Path A is not admissible." Path A IS admissible
    # (proven separately); so kill fires only on the first clause.
    if n_ship == 0:
        overall_verdict = "KILL"

    graveyard_flags = []
    for c in cells:
        if (c["action"] == "ARM_FULL" and c["trigger_form"] == "ARM_T_touch"
                and c["band"] == 0.0 and c["verdict"] == "SHIP"):
            graveyard_flags.append(
                f"{c['target_rule']}|reach{c['max_reach']}|band0.0|touch|FULL is the "
                f"exit-all-at-touch REFERENCE ARM per graveyard_check -- if this is the sole "
                f"or dominant winner, treat as a graveyard contradiction, not a ship.")

    result = {
        "rule_id": "level-target-exit",
        "run_at_et": dt.datetime.now().isoformat(),
        "prereg": str(lts.PREREG_PATH.relative_to(REPO)).replace("\\", "/"),
        "prereg_frozen_git_sha": "a965c8499efacf38fed741c9d7c96abce24eb721",
        "path_a_admissibility": {
            "verdict": "ADMISSIBLE",
            "proof": "backtest/lib/reconstruct_levels_asof.py + "
                     "backtest/tests/test_reconstruct_levels_asof.py (6/6 green)",
            "reconstruction_scope": lts.rla.RECONSTRUCTION_SCOPE,
        },
        "band_interpretation_note": lts.BAND_INTERPRETATION_NOTE,
        "resolution_disclosure": "Option bars fetched at 1-MINUTE resolution per position via "
                                 "live REST (exit_shape_parity_study.fetch_option_bars), NOT "
                                 "the population-wide 5-minute CSV cache -- found + fixed this "
                                 "session: a 5-min bar's point-sampled open missed intra-bar "
                                 "stops a real engine tick caught (verified exactly on "
                                 "SPY260709C00750000/risky-3, a $475 phantom-gain artifact), "
                                 "producing a huge sign-flipped harness-vs-live parity gap on "
                                 "the first run. See option_bar_resolution_counts for how many "
                                 "positions actually got 1min_rest vs the 5min_cache_fallback. "
                                 "SPY bars deliberately STAY 5-minute (structure_stop is "
                                 "5-min-NATIVE by v15.3 design, not an approximation).",
        "population": {
            "universe": "fills-ledger.jsonl, ALL_LIVE_ARMS (all 6 arms), FIFO-paired via "
                        "exit_shape_parity_study.reconstruct_positions",
            "n_raw_positions": len(positions) + sum(excl_pop.values()),
            "n_after_population_filters": len(positions),
            "excluded_population_stage": excl_pop,
            "n_after_data_availability": len(prepared),
            "excluded_data_stage": excl_data,
            "n_final": len(prepared),
            "option_bar_resolution_counts": resolution_counts,
            "n_distinct_days": n_days,
            "is_days": sorted(is_days), "oos_days": sorted(oos_days),
            "n_runner_trail_cohort": n_runner_cohort,
        },
        "harness_vs_live_parity": {
            "harness_incumbent_total": parity_harness_total,
            "actual_real_fills_total": parity_actual_total,
            "gap_dollars": parity_gap_dollars, "gap_pct_of_actual": parity_gap_pct,
        },
        "gates_all_must_pass": ["G1_aggregate", "G2_day_majority", "G3_drop_best",
                               "G4_runner_cohort_no_regression", "G5_oos", "G6_bh_fdr",
                               "G7_level_fired_rate", "G8_parity"],
        "total_cells": len(cells),
        "n_ship": n_ship, "n_kill": n_kill, "n_inconclusive_underpowered": n_underpowered,
        "overall_verdict": overall_verdict,
        "graveyard_flags": graveyard_flags,
        "cells": cells,
        "runtime_seconds": round(_time_mod.time() - t0, 1),
    }
    lts.OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lts.OUT_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[t={_time_mod.time()-t0:.1f}s] wrote {lts.OUT_PATH}")
    print(f"VERDICT: {overall_verdict}  (ship={n_ship} kill={n_kill} "
         f"underpowered={n_underpowered} / {len(cells)} cells)")
    return result


if __name__ == "__main__":
    main()
