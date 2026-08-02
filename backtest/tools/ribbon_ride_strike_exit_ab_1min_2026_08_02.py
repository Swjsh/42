"""ribbon_ride_strike_exit_ab_1min_2026_08_02.py -- STEP 2b of OPTION-BAR-RESOLUTION-BIAS-
2026-08-02: REPLICATION of ribbon_ride_strike_exit_ab.py's AXIS 1 (strike, SS-B fixed) and
AXIS 2 (exit shape, P5-CHALLENGER vs SS-B) at 1-MINUTE option-bar resolution, on the SAME
n=250 signal cohort, reproducing the ORIGINAL frozen cells (STRIKE_CELLS, shapes, the fill-bar
'>' convention) UNCHANGED -- no new hypotheses, no threshold sweeping, per task instruction.

WHY THIS MATTERS: the ORIGINAL study's headline finding -- "ATM strike beats OTM-2 by
$47.96/tr ... MAY SHIP per OP-11 auto-ratify" -- was computed ENTIRELY on 5-min cached OPRA
bars (lib.option_pricing_real.load_contract_bars, the exact defect function -- every cell of
BOTH axes, not just a fallback). ATM strikes carry a materially higher option delta than
OTM-2, so a stop that recovers inside a 5-min bar would be expected to matter MORE in dollar
terms at ATM than at OTM-2 -- i.e. the resolution bias (Step 1 of this investigation: 5-min
systematically FLATTERS P&L, 0 false positives the other way on the real-fills population)
could be inflating ATM's apparent edge over OTM-2 specifically, not just adding symmetric
noise. This script answers: does ATM still beat OTM-2 under SS-B at honest 1-minute
resolution, by a similar margin, clearing the same auto-ratify gates?

SCOPE REDUCTION (disclosed, not silent): the ORIGINAL study's random-entry null (20 seeds/
cell) and BH-FDR correction are NOT recomputed here -- they are NOT part of OP-11's
auto-ratify condition (oos_positive AND wf_ge_070 AND sub_window_stable AND
anchor_no_regression AND not unstable_on_toggle -- see ribbon_ride_strike_exit_ab.compare(),
which reads only `metrics` and `sensitivity_old_fillbar_convention`, never `null`/`p_null`/
`bh_fdr_survivor`), and re-running them at 1-min would need ~20x the network fetches (each null
seed draws NEW random dates/strikes outside the main cohort) for a check that does not gate
SHIP/WAIT. The auto-ratify-DECISIVE headline metrics (n/expectancy/wr/oos_total/oos_positive/
wf/wf_ge_070/edge_capture_rel/sub_window_stable) AND the fill-bar-convention sensitivity toggle
(also decision-relevant -- gates unstable_on_open_audit) ARE recomputed in full.

REUSE (OP-22): STRIKE_CELLS, SHAPES (SS-B / P5-CHALLENGER), load_cohort() (signal prep +
per-signal ss_time -- level/trigger recovery is independent of option-bar resolution),
t4_exit_matrix.battery(), rrse.top3_day_share()/both_halves()/compare()/verdict_flip()/
auto_ratify_flags(), and structure_stop_study.replay_structure_aware() (the certified SS-B/
P5-challenger replay engine) are all imported UNCHANGED. The ONLY new code is the bar loader
(1-min REST instead of 5-min disk cache).

ANALYSIS ONLY. Writes only to analysis/recommendations/. Never touches
ribbon_ride_strike_exit_ab.py, exit_manager.py, params.json, or any trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/ribbon_ride_strike_exit_ab_1min_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import structure_stop_study as sss                        # noqa: E402  (reused UNCHANGED -- SS-B replay engine)
import t4_exit_matrix as t4                                 # noqa: E402  (battery)
import ribbon_ride_strike_exit_ab as rrse                    # noqa: E402  (reused UNCHANGED -- shapes/cohort/compare)
from lib.option_pricing_real import option_symbol             # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached          # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "ribbon-ride-strike-exit-ab-1min-replication-2026-08-02.json"
OUT_MD = REPO / "analysis" / "recommendations" / "ribbon-ride-strike-exit-ab-1min-replication-2026-08-02.md"


def log(msg: str) -> None:
    print(f"[rrse-1min] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# BAR FETCH -- 1-minute equivalent of ribbon_ride_strike_exit_ab.fetch_entry_and_bars. SAME
# strike_for() convention, SAME '>' (exclude fill bar) / '>=' (old_semantics) toggle -- only the
# bar SOURCE changes (1-min REST/cache vs 5-min disk cache).
# ---------------------------------------------------------------------------------------------
def fetch_entry_and_bars_1min(entry_spot: float, side: str, date: dt.date, entry_ts: dt.datetime,
                              so: int, *, old_semantics: bool = False):
    strike = rrse.strike_for(entry_spot, side, so)
    symbol = option_symbol(date, strike, side)
    df, src = fetch_1min_cached(symbol, date.isoformat())
    if df is None or df.empty:
        return None
    ts = df["timestamp_et"]
    entry_ts_naive = entry_ts.replace(tzinfo=None) if entry_ts.tzinfo is not None else entry_ts
    entry_mask = (ts >= entry_ts_naive) & (ts.dt.date == date)
    entry_rows = df[entry_mask.values]
    if entry_rows.empty:
        return None
    entry_bar = entry_rows.iloc[0]
    entry_premium = float(entry_bar["open"])
    entry_bar_ts = entry_bar["timestamp_et"]
    walk_mask = ((ts >= entry_bar_ts) if old_semantics else (ts > entry_bar_ts)) & (ts.dt.date == date)
    walk = df[walk_mask.values]
    if walk.empty:
        return None
    norm_bars = []
    for _, r in walk.iterrows():
        t = r["timestamp_et"]
        norm_bars.append(sss.NormBar(t.to_pydatetime() if hasattr(t, "to_pydatetime") else t,
                                     float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return entry_premium, norm_bars, src


def replay_cell_1min(prepped: list[dict], so: int, shape: dict, use_structure: bool,
                     *, old_semantics: bool = False) -> tuple[list[dict], int, dict]:
    trades, n_no_bars, src_counts = [], 0, {}
    for s in prepped:
        fetched = fetch_entry_and_bars_1min(float(s["entry_spot"]), s["side"], s["date_obj"],
                                            s["entry_ts_obj"], so, old_semantics=old_semantics)
        if fetched is None:
            n_no_bars += 1
            continue
        entry_premium, norm_bars, src = fetched
        src_counts[src] = src_counts.get(src, 0) + 1
        ss_time = s["ss_time"] if use_structure else None
        r = sss.replay_structure_aware(entry_premium, s["side"], rrse.QTY, norm_bars, ss_time,
                                       shape, rrse.TIME_STOP_LAYER)
        trades.append({"date": s["date_obj"], "direction": s["direction"], "side": s["side"],
                       "pnl": r["pnl"], "structure_fired": r["structure_fired"]})
    return trades, n_no_bars, src_counts


def build_cell_1min(cell_id: str, so: int, strike_label: str, exit_label: str, shape: dict,
                    use_structure: bool, prepped: list[dict]) -> dict:
    t0 = _time_mod.time()
    trades, n_no_bars, src_counts = replay_cell_1min(prepped, so, shape, use_structure, old_semantics=False)
    b = t4.battery(trades)
    b["top3_day_share"] = rrse.top3_day_share(trades)
    bh = rrse.both_halves(trades)
    b["sub_window_stable"] = bh["both_positive"]
    b["both_halves"] = {"first": bh["first_half"], "second": bh["second_half"]}

    trades_old, n_no_bars_old, _src_old = replay_cell_1min(prepped, so, shape, use_structure,
                                                            old_semantics=True)
    b_old = t4.battery(trades_old)

    elapsed = round(_time_mod.time() - t0, 1)
    log(f"{cell_id}: n={b.get('n')} (dropped {n_no_bars} no-bars, sources={src_counts}) "
        f"exp=${b.get('expectancy')} OOS=${b.get('oos_total')} wf={b.get('wf')} "
        f"edge_capture_rel={b.get('edge_capture_rel')} "
        f"sensitivity(old)_exp=${b_old.get('expectancy')} ({elapsed}s)")

    return {
        "cell_id": cell_id, "strike_label": strike_label, "so_simulator_convention": so,
        "exit_label": exit_label, "n_no_local_bars": n_no_bars, "bar_sources": src_counts,
        "metrics": b,
        "sensitivity_old_fillbar_convention": {
            "n": b_old.get("n"), "n_no_local_bars": n_no_bars_old,
            "expectancy": b_old.get("expectancy"), "wr": b_old.get("wr"),
            "oos_total": b_old.get("oos_total"), "oos_positive": b_old.get("oos_positive"),
            "wf": b_old.get("wf"), "edge_capture_rel": b_old.get("edge_capture_rel"),
        },
        "null": None, "null_gate": None, "p_null": None,
        "scope_reduction_note": "null-baseline/BH-FDR NOT recomputed at 1-min -- see module "
                                 "docstring SCOPE REDUCTION; not part of OP-11 auto-ratify.",
    }


def main() -> int:
    t_start = _time_mod.time()
    log("loading signal cohort (ribbon_ride_strike_exit_ab.load_cohort, reused UNCHANGED)")
    prepped, _spy_full, _spy_by_date = rrse.load_cohort()
    log(f"cohort: {len(prepped)} signals")

    log("=== AXIS 1: strike (SS-B fixed), 1-minute resolution ===")
    axis1_cells = {}
    for label, so in rrse.STRIKE_CELLS:
        cell_id = f"{label}/SS-B"
        axis1_cells[label] = build_cell_1min(cell_id, so, label, "SS-B", rrse.SS_B_SHAPE, True, prepped)

    control = axis1_cells[rrse.CONTROL_STRIKE]
    candidates = {lbl: c for lbl, c in axis1_cells.items() if lbl != rrse.CONTROL_STRIKE}
    axis1_comparisons = {lbl: rrse.compare(c, control, f"{lbl} vs {rrse.CONTROL_STRIKE} (SS-B fixed, 1-min)")
                         for lbl, c in candidates.items()}
    winner_label = max(candidates,
                       key=lambda lbl: (candidates[lbl]["metrics"].get("oos_total") is not None,
                                        candidates[lbl]["metrics"].get("oos_total") or -1e18,
                                        candidates[lbl]["metrics"].get("expectancy") or -1e18))
    winner_so = dict(rrse.STRIKE_CELLS)[winner_label]
    log(f"AXIS 1 winner (by OOS total, tie-break full expectancy): {winner_label} "
        f"(OOS_total=${candidates[winner_label]['metrics'].get('oos_total')}, "
        f"beats control: {axis1_comparisons[winner_label]['candidate_beats_control']})")

    log("=== AXIS 2: exit shape (P5-CHALLENGER vs SS-B), at OTM-2 control + strike winner ===")
    axis2_strikes = {rrse.CONTROL_STRIKE: dict(rrse.STRIKE_CELLS)[rrse.CONTROL_STRIKE]}
    if winner_label != rrse.CONTROL_STRIKE:
        axis2_strikes[winner_label] = winner_so
    axis2_cells = {}
    for label, so in axis2_strikes.items():
        cell_id = f"{label}/P5-CHALLENGER"
        axis2_cells[label] = build_cell_1min(cell_id, so, label, "P5-CHALLENGER",
                                             rrse.P5_CHALLENGER_SHAPE, False, prepped)

    axis2_comparisons = {}
    for label in axis2_strikes:
        ss_b_cell = axis1_cells[label]
        p5_cell = axis2_cells[label]
        axis2_comparisons[label] = rrse.compare(p5_cell, ss_b_cell,
                                                f"P5-CHALLENGER vs SS-B (at {label}, 1-min)")

    ship = [v for v in list(axis1_comparisons.values()) + list(axis2_comparisons.values())
           if v["ship_or_wait"] == "SHIP"]
    wait_audit = [v for v in list(axis1_comparisons.values()) + list(axis2_comparisons.values())
                 if v["ship_or_wait"] == "WAIT_OPEN_AUDIT_CHIPS"]
    wait_evidence = [v for v in list(axis1_comparisons.values()) + list(axis2_comparisons.values())
                     if v["ship_or_wait"] == "WAIT_EVIDENCE"]

    original = json.loads((REPO / "analysis" / "recommendations" / "ribbon-ride-strike-exit-ab.json")
                          .read_text(encoding="utf-8"))
    orig_a1 = original["axis1_strike"]
    orig_a2 = original["axis2_exit"]

    log("=== SIDE-BY-SIDE: ORIGINAL (5-min) vs 1-MIN REPLICATION, AXIS 1 ===")
    for lbl in ["OTM-2", "OTM-1", "ATM", "ITM-2"]:
        o = orig_a1["cells"][lbl]["metrics"]
        n = axis1_cells[lbl]["metrics"]
        log(f"  {lbl}: original exp=${o.get('expectancy')} OOS=${o.get('oos_total')} "
            f"-> 1min exp=${n.get('expectancy')} OOS=${n.get('oos_total')}")
    log(f"  Original strike-axis verdict (from ribbon-ride-strike-exit-ab.md): ATM SHIPS "
        f"(+$47.96/tr over OTM-2). 1-min: winner={winner_label}, "
        f"ATM vs OTM-2 delta_exp=${axis1_comparisons.get('ATM', {}).get('delta_expectancy')}, "
        f"ship_or_wait={axis1_comparisons.get('ATM', {}).get('ship_or_wait')}")

    out = {
        "_doc": "STEP 2b of OPTION-BAR-RESOLUTION-BIAS-2026-08-02: ribbon_ride_strike_exit_ab."
                "py's AXIS 1 (strike) and AXIS 2 (exit shape) REPLICATED at 1-minute option-bar "
                "resolution, on the SAME n=250 signal cohort and the SAME frozen cells (no new "
                "hypotheses, no threshold sweeping). Null-baseline/BH-FDR scope-reduced (see "
                "module docstring) -- not part of the OP-11 auto-ratify decision.",
        "generated_at": dt.datetime.now().isoformat(),
        "original_scorecard": "analysis/recommendations/ribbon-ride-strike-exit-ab.json",
        "signal_cohort": {"source": "_signal_cache.load_or_build_signals() via rrse.load_cohort()",
                          "n_raw": len(prepped)},
        "axis1_strike": {"control": rrse.CONTROL_STRIKE, "winner": winner_label,
                         "cells": axis1_cells, "comparisons": axis1_comparisons},
        "axis1_strike_original_5min": orig_a1,
        "axis2_exit": {"strikes_tested": list(axis2_strikes.keys()), "cells": axis2_cells,
                      "comparisons": axis2_comparisons},
        "axis2_exit_original_5min": orig_a2,
        "ship_vs_wait": {
            "ship_per_op11_auto_ratify": ship,
            "wait_on_open_audit_chips": wait_audit,
            "wait_more_evidence": wait_evidence,
        },
        "runtime_seconds": round(_time_mod.time() - t_start, 1),
        "disclosures": [
            "Bar source is the ONLY variable changed vs the original study: "
            "lib.option_pricing_real.load_contract_bars (5-min disk cache) -> "
            "exit_shape_parity_study.fetch_option_bars (1-min live REST, shared helper "
            "_option_bars_1min_cache.fetch_1min_cached). Signal cohort, strike-offset "
            "convention (strike_for), fill-bar '>' convention (old_semantics=False primary, "
            "'>=' old_semantics=True sensitivity), shapes (SS-B/P5-CHALLENGER), trigger-level "
            "recovery, QTY=10, and TIME_STOP_LAYER (15:50 ET) are IDENTICAL to the original.",
            "SCOPE REDUCTION: random-entry null (20 seeds/cell) and BH-FDR are NOT recomputed "
            "at 1-min resolution -- see module docstring. null/p_null/bh_fdr_survivor fields "
            "are None in every cell here; SHIP/WAIT verdicts below do not depend on them "
            "(verified against ribbon_ride_strike_exit_ab.compare()'s own source, which reads "
            "only metrics + sensitivity_old_fillbar_convention).",
            "This is a REPLICATION, not a new search: STRIKE_CELLS, SHAPES, and the winner-"
            "selection rule are byte-identical to the original. Any verdict change traces ONLY "
            "to the resolution swap.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON} ({out['runtime_seconds']}s total)")
    log(f"SHIP: {len(ship)} | WAIT_OPEN_AUDIT_CHIPS: {len(wait_audit)} | WAIT_EVIDENCE: {len(wait_evidence)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
