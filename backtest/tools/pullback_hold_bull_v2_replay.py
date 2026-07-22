"""backtest/tools/pullback_hold_bull_v2_replay.py -- PULLBACK-HOLD-BULL-TRIGGER v2 grid runner.

Frozen pre-reg: analysis/recommendations/pullback-hold-bull-prereg-v2-2026-07-22.json
Detector: backtest/tools/pullback_hold_bull_v2.py

REUSES (not re-derived) the v1 grid runner's infrastructure -- data loading conventions,
real-fills pricing (backtest.lib.exit_manager_walk / option_pricing_real / dojo.sim_executor),
significance stats, and ship-gate evaluation are imported directly from
backtest/tools/pullback_hold_bull_replay.py (v1 file, left UNTOUCHED). Only the grid
construction and the detector-frequency pass are NEW (they call the v2 detector +
impulse-leg feature, and add the EXTENDED (premarket-inclusive) bar load the impulse-leg
qualifier needs).

Rail-4 CLEAR: research tool + JSON/MD outputs; touches NO params/orders/filters/
heartbeat_core/strategies.py/CLAUDE.md. No broker import. No git operations.

USAGE:
    python -m backtest.tools.pullback_hold_bull_v2_replay
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date, datetime, time as dtime
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from tools.pullback_hold_bull_v2 import (  # noqa: E402
    ImpulseLegParams,
    PullbackHoldV2Params,
    detect_pullback_hold_bull_v2,
    impulse_leg_series,
)
# REUSED verbatim from v1 -- data-loading convention, stats, real-fills pricing, ship gates.
from tools.pullback_hold_bull_replay import (  # noqa: E402
    _bh_fdr,
    _day_slice,
    _in_window,
    _one_sample_p,
    check_sanity_anchors,
    evaluate_cell,
    run_real_fills,
)
from lib.watchers.level_memory import LevelMemory  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from autoresearch.rsi_extension_block_probe import _wilder_rsi  # noqa: E402  -- unused here but
# kept importable for parity with v1 (RSI is not part of the v2 grid -- confirmation was dropped).
from dojo import sim_executor as se  # noqa: E402

PREREG_PATH = _ROOT / "analysis" / "recommendations" / "pullback-hold-bull-prereg-v2-2026-07-22.json"
SCORECARD_PATH = _ROOT / "analysis" / "recommendations" / "pullback-hold-bull-v2-2026-07-22.json"
SPY_FULL_FILE = _ROOT / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-22.csv"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"

ARM_ID = "safe"          # dojo alias -> accounts.json "safe-2" (CORE-SAFE, ATM tiers)
STRATEGY_NAME = "ribbon_ride"
STRUCTURE_STOP_ENABLED = True  # FIXED per pre-reg (same for all cells, not read live)


# =====================================================================================
# Data loading -- TWO views of the same continuous frame: RTH-only (entry/hold scanning,
# unchanged from v1) and EXTENDED (premarket 04:00 ET onward, feeds ONLY the impulse-leg
# qualifier's lookback -- new in v2).
# =====================================================================================
def _load_spy(min_time: dtime) -> pd.DataFrame:
    df = pd.read_csv(SPY_FULL_FILE)
    ts = pd.to_datetime(df["timestamp_et"])
    ts = ts.dt.tz_localize("America/New_York") if ts.dt.tz is None else ts.dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts
    sliced = df[(ts.dt.time >= min_time) & (ts.dt.time < dtime(16, 0))].reset_index(drop=True)
    return sliced


def entries_per_day(n_signals: int, n_days: int) -> float:
    """Frequency disclosure helper -- pre-reg's explicit requirement given the selectivity
    axis is meant to cut entry frequency hard vs v1's any-level rule."""
    if n_days <= 0:
        return 0.0
    return round(n_signals / n_days, 3)


# =====================================================================================
# Grid enumeration -- read straight from the frozen pre-reg (never re-typed, never drifts).
# =====================================================================================
def build_grid(prereg: dict) -> list[PullbackHoldV2Params]:
    axes = prereg["detector_definition_space"]["grid_axes"]
    leg_param_map = prereg["detector_definition_space"]["grid_axes_impulse_leg_params"]
    cells = []
    for leg_mode in axes["impulse_leg_mode"]:
        leg_p = leg_param_map[leg_mode]
        for selectivity in axes["selectivity_mode"]:
            for band in axes["zone_band_cents"]:
                for n in axes["hold_bars_n"]:
                    cells.append(PullbackHoldV2Params(
                        impulse_leg_mode=leg_mode, k_bars=int(leg_p["k_bars"]),
                        min_leg_dollars=float(leg_p["min_leg_dollars"]),
                        max_retrace_pct=float(leg_p["max_retrace_pct"]),
                        selectivity_mode=selectivity, zone_band_cents=float(band),
                        hold_bars_n=int(n),
                    ))
    return cells


# =====================================================================================
# Detector-frequency pass -- FULL 44-day history, structural counts only, no $ claim.
# =====================================================================================
def run_detector_frequency(spy_rth: pd.DataFrame, spy_ext: pd.DataFrame, lm: LevelMemory,
                            full_days: list[str], grid: list[PullbackHoldV2Params]) -> dict:
    """Returns {cell_id: {"signals": [dict...], "n": int, "n_days_fired": int, "params": ...}}."""
    rth_day_map: dict[str, pd.DataFrame] = {}
    ext_day_map: dict[str, pd.DataFrame] = {}
    global_idx_of: dict[str, dict[int, int]] = {}
    for d in full_days:
        day = date.fromisoformat(d)
        rth_slice = _day_slice(spy_rth, day)
        rth_local = rth_slice.reset_index(drop=True)
        rth_day_map[d] = rth_local
        ext_day_map[d] = _day_slice(spy_ext, day).reset_index(drop=True)
        global_idx_of[d] = {i: int(orig) for i, orig in enumerate(rth_slice.index)}

    # impulse-leg cache: (impulse_leg_mode, day) -> list[ImpulseLegBar] -- computed ONCE per
    # (mode, day), reused across every cell sharing that mode (selectivity/band/N don't
    # affect the impulse-leg computation).
    leg_cache: dict[tuple[str, str], list] = {}

    out: dict[str, dict] = {}
    for params in grid:
        cid = params.cell_id()
        all_signals = []
        days_fired = set()
        for d in full_days:
            key = (params.impulse_leg_mode, d)
            if key not in leg_cache:
                leg_p = ImpulseLegParams(k_bars=params.k_bars, min_leg_dollars=params.min_leg_dollars,
                                          max_retrace_pct=params.max_retrace_pct)
                leg_cache[key] = impulse_leg_series(ext_day_map[d], rth_day_map[d], leg_p)
            leg_out = leg_cache[key]
            rth_local = rth_day_map[d]
            gmap = global_idx_of[d]

            def levels_at(i: int, _gmap=gmap) -> list[float]:
                g = _gmap[i]
                return [lv.price for lv in lm.levels_at(g)]

            sigs = detect_pullback_hold_bull_v2(
                rth_local, up_structure_ok=[b.ok for b in leg_out],
                leg_origin_lows=[b.leg_origin_low for b in leg_out],
                leg_highs=[b.leg_high for b in leg_out],
                retrace_pcts=[b.retrace_pct for b in leg_out],
                levels_at=levels_at, params=params, day_label=d)
            if sigs:
                days_fired.add(d)
            for s in sigs:
                row = asdict(s)
                row["pullback_ts"] = s.pullback_ts.isoformat()
                row["entry_ts"] = s.entry_ts.isoformat()
                all_signals.append(row)
        out[cid] = {"signals": all_signals, "n": len(all_signals), "n_days_fired": len(days_fired),
                     "entries_per_day_full_history": entries_per_day(len(all_signals), len(full_days)),
                     "params": asdict(params)}
    return out


# =====================================================================================
# main
# =====================================================================================
def main() -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    full_days = prereg["populations"]["full_history_days"]
    opra_days = set(prereg["populations"]["opra_covered_days"])
    held_out_days = set(prereg["populations"]["held_out_days"])
    anchors = prereg["sanity_anchors"]

    print("[load] SPY RTH + EXTENDED frames + LevelMemory + ribbon ...", file=sys.stderr)
    spy_rth = _load_spy(dtime(9, 30))
    spy_ext = _load_spy(dtime(4, 0))
    lm = LevelMemory(spy_rth)
    ribbon_df = compute_ribbon(spy_rth["close"].reset_index(drop=True))
    spy_rth_with_stack = spy_rth.reset_index(drop=True).copy()
    spy_rth_with_stack["stack"] = ribbon_df["stack"].values

    grid = build_grid(prereg)
    print(f"[grid] {len(grid)} cells", file=sys.stderr)

    print("[detector] full 44-day frequency pass ...", file=sys.stderr)
    freq_out = run_detector_frequency(spy_rth, spy_ext, lm, full_days, grid)

    safe_arm_cfg, _canonical = se._resolve_arm_cfg(ARM_ID)
    safe_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    time_stop = se._parse_hhmm(se._time_stop_et_for(safe_arm_cfg))

    print("[real-fills] pricing + exit-walking OPRA-covered signals ...", file=sys.stderr)
    priced_out = run_real_fills(spy_rth_with_stack, freq_out, opra_days, safe_arm_cfg,
                                 safe_params, time_stop)

    print("[gates] sanity anchors + ship-bar conditions 1-4 + BH-FDR ...", file=sys.stderr)
    cell_rows = []
    pvals = []
    for cell in grid:
        cid = cell.cell_id()
        anchor_check = check_sanity_anchors(freq_out[cid]["signals"], anchors)
        gate = evaluate_cell(priced_out[cid], held_out_days)
        # v1's evaluate_cell (reused verbatim) has a dormant key inconsistency: its n==0
        # early-return uses "p_value" instead of "p_value_raw" -- never hit in v1 because
        # v1's any-level rule always produced n>0 signals. v2's tighter selectivity can
        # legitimately produce n==0 real-fills cells, so normalize here rather than patch
        # the untouched v1 file.
        if "p_value_raw" not in gate:
            gate["p_value_raw"] = gate.get("p_value", 1.0)
        pvals.append(gate["p_value_raw"])
        cell_rows.append({
            "cell_id": cid, "params": asdict(cell),
            "full_history_n_signals": freq_out[cid]["n"],
            "full_history_n_days_fired": freq_out[cid]["n_days_fired"],
            "entries_per_day_full_history": freq_out[cid]["entries_per_day_full_history"],
            "anchor_check": anchor_check,
            "real_fills": gate,
        })
    bh_sig = _bh_fdr(pvals, q=0.10)
    for row, sig in zip(cell_rows, bh_sig):
        row["real_fills"]["condition_5_bh_fdr_significant_q10"] = bool(sig)
        row["clears_all_gates"] = bool(
            row["anchor_check"]["both_anchors_hit"]
            and row["real_fills"].get("condition_1_positive_aggregate")
            and row["real_fills"].get("condition_2_day_majority")
            and row["real_fills"].get("condition_3_survives_top_trade_drop")
            and row["real_fills"].get("condition_4_holds_on_held_out")
            and sig
        )

    shippable = [r for r in cell_rows if r["clears_all_gates"]]
    shippable.sort(key=lambda r: r["real_fills"].get("expectancy") or -1e9, reverse=True)
    ranked_all = sorted(
        cell_rows,
        key=lambda r: (r["clears_all_gates"], r["anchor_check"]["both_anchors_hit"],
                        r["real_fills"].get("expectancy") or -1e9),
        reverse=True,
    )

    verdict = "SHIP_CANDIDATE" if shippable else "NO_CELL_SHIPS"
    out = {
        "generated_at": datetime.now().isoformat(),
        "prereg_file": str(PREREG_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "grid_size": len(grid),
        "full_history_days_n": len(full_days),
        "opra_covered_days_n": len(opra_days),
        "held_out_days": sorted(held_out_days),
        "verdict": verdict,
        "n_shippable_cells": len(shippable),
        "top_5": ranked_all[:5],
        "all_cells": ranked_all,
    }
    SCORECARD_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[written] {SCORECARD_PATH}")
    print(f"[verdict] {verdict}  shippable={len(shippable)}/{len(grid)}")
    for r in ranked_all[:5]:
        rf = r["real_fills"]
        print(f"  {r['cell_id']:55s} clears={r['clears_all_gates']!s:5s} "
              f"anchors={r['anchor_check']['both_anchors_hit']!s:5s} "
              f"freq/day={r['entries_per_day_full_history']:.2f} "
              f"n={rf.get('n')} total=${rf.get('total_pnl')} exp=${rf.get('expectancy')}")
    return out


if __name__ == "__main__":
    main()
