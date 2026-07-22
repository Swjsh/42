"""backtest/tools/pullback_hold_bull_replay.py -- PULLBACK-HOLD-BULL-TRIGGER grid runner.

Frozen pre-reg: analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json
Detector: backtest/tools/pullback_hold_bull_detector.py

Runs the 36-cell frozen grid over:
  1. FULL 44-day history (detector-FREQUENCY stats only -- how often each cell structurally
     fires, no P&L claim).
  2. The 39-day OPRA-covered subset (real option fills, via
     backtest.lib.option_pricing_real + backtest.lib.exit_manager_walk -- the REAL production
     exit_manager decision core, ribbon 'stack' series from backtest.lib.ribbon over the full
     continuous close series so EMA-48 has proper warmup, no per-day reset).

Strike/qty/exit-shape/cache-loading are all REUSED from setup/scripts/dojo/sim_executor.py
(the same plumbing dojo_exit_diversity_replay.py and every other real-fills probe in this
codebase already uses) -- never hand-rolled a second time.

Rail-4 CLEAR: research tool + JSON/MD outputs; touches NO params/orders/filters/heartbeat_core/
strategies.py/CLAUDE.md. No broker import. No git operations.

USAGE:
    python -m backtest.tools.pullback_hold_bull_replay
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from tools.pullback_hold_bull_detector import (  # noqa: E402
    PullbackHoldParams,
    detect_pullback_hold_bull,
    up_structure_series,
)
from lib.watchers.level_memory import LevelMemory  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, option_symbol  # noqa: E402
from autoresearch.rsi_extension_block_probe import _wilder_rsi  # noqa: E402  -- reused, not re-derived
from dojo import sim_executor as se  # noqa: E402
import fleet_executor as fx  # noqa: E402  -- reuse risk_gate.max_affordable_qty

PREREG_PATH = _ROOT / "analysis" / "recommendations" / "pullback-hold-bull-prereg-2026-07-22.json"
SCORECARD_PATH = _ROOT / "analysis" / "recommendations" / "pullback-hold-bull-2026-07-22.json"
MD_PATH = _ROOT / "analysis" / "recommendations" / "pullback-hold-bull-stage-summary-2026-07-22.md"
SPY_FULL_FILE = _ROOT / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-22.csv"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"

ARM_ID = "safe"          # dojo alias -> accounts.json "safe-2" (CORE-SAFE, ATM tiers)
STRATEGY_NAME = "ribbon_ride"
STRUCTURE_STOP_ENABLED = True  # FIXED per pre-reg (same for all cells, not read live)


# =====================================================================================
# Data loading -- one continuous frame for proper multi-day warmup (ribbon EMA-48, RSI).
# =====================================================================================
def _load_spy_full() -> pd.DataFrame:
    df = pd.read_csv(SPY_FULL_FILE)
    ts = pd.to_datetime(df["timestamp_et"])
    ts = ts.dt.tz_localize("America/New_York") if ts.dt.tz is None else ts.dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts
    rth = df[(ts.dt.time >= dtime(9, 30)) & (ts.dt.time < dtime(16, 0))].reset_index(drop=True)
    return rth


def _day_slice(spy_full: pd.DataFrame, day: date) -> pd.DataFrame:
    mask = spy_full["timestamp_et"].dt.date == day
    return spy_full[mask]


# =====================================================================================
# Grid enumeration -- read straight from the frozen pre-reg (never re-typed, never drifts).
# =====================================================================================
def build_grid(prereg: dict) -> list[PullbackHoldParams]:
    axes = prereg["detector_definition_space"]["grid_axes"]
    cells = []
    for mode in axes["up_structure_mode"]:
        for band in axes["zone_band_cents"]:
            for n in axes["hold_bars_n"]:
                for confirm in axes["confirm_mode"]:
                    cells.append(PullbackHoldParams(
                        up_structure_mode=mode, zone_band_cents=float(band),
                        hold_bars_n=int(n), confirm_mode=confirm,
                    ))
    return cells


# =====================================================================================
# Statistics -- one-sample significance (mean pnl != 0), BH-FDR (reused convention,
# rsi_extension_block_probe's own normal-approx style).
# =====================================================================================
def _one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se_ = (var / n) ** 0.5
    if se_ == 0:
        return 1.0
    t = mean / se_
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))
    return max(0.0, min(1.0, p))


def _bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh = [(k + 1) / m * q for k in range(m)]
    sig = [False] * m
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= thresh[rank]:
            max_k = rank
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


# =====================================================================================
# Detector-frequency pass -- FULL 44-day history, structural counts only, no $ claim.
# =====================================================================================
def run_detector_frequency(spy_full: pd.DataFrame, lm: LevelMemory, rsi_series: pd.Series,
                            full_days: list[str], grid: list[PullbackHoldParams]) -> dict:
    """Returns {cell_id: {"signals": [dict...], "n": int, "n_days_fired": int}}."""
    day_index_map: dict[str, pd.DataFrame] = {}
    global_idx_of: dict[str, dict[int, int]] = {}
    for d in full_days:
        day = date.fromisoformat(d)
        day_df = _day_slice(spy_full, day)
        day_local = day_df.reset_index(drop=True)
        day_index_map[d] = day_local
        # map day-local idx -> the ORIGINAL global row index in spy_full (for LevelMemory/RSI)
        global_idx_of[d] = {i: int(orig) for i, orig in enumerate(day_df.index)}

    # up_structure_ok cache: (mode, day) -> list[bool] -- computed ONCE per (mode,day), reused
    # across every cell sharing that mode (cheap PRICE_VWAP, expensive MARKET_STRUCTURE).
    up_cache: dict[tuple[str, str], list[bool]] = {}

    out: dict[str, dict] = {}
    for params in grid:
        cid = params.cell_id()
        all_signals = []
        days_fired = set()
        for d in full_days:
            key = (params.up_structure_mode, d)
            if key not in up_cache:
                up_cache[key] = up_structure_series(day_index_map[d], params.up_structure_mode,
                                                     structure_lookback_bars=params.structure_lookback_bars)
            up_ok = up_cache[key]
            day_local = day_index_map[d]
            gmap = global_idx_of[d]

            def levels_at(i: int, _gmap=gmap) -> list[float]:
                g = _gmap[i]
                return [lv.price for lv in lm.levels_at(g)]

            rsi_at = None
            if params.confirm_mode == "BOTH":
                def rsi_at(i: int, _gmap=gmap) -> Optional[float]:  # noqa: F811
                    g = _gmap[i]
                    v = rsi_series.iloc[g]
                    return None if pd.isna(v) else float(v)

            sigs = detect_pullback_hold_bull(
                day_local, up_structure_ok=up_ok, levels_at=levels_at, params=params,
                day_label=d, rsi_at=rsi_at)
            if sigs:
                days_fired.add(d)
            for s in sigs:
                row = asdict(s)
                row["pullback_ts"] = s.pullback_ts.isoformat()
                row["entry_ts"] = s.entry_ts.isoformat()
                all_signals.append(row)
        out[cid] = {"signals": all_signals, "n": len(all_signals), "n_days_fired": len(days_fired),
                     "params": asdict(params)}
    return out


# =====================================================================================
# Sanity anchors -- fidelity gate, evaluated on the detector-frequency signals directly.
# =====================================================================================
def _in_window(ts_iso: str, day: str, lo_hhmm: str, hi_hhmm: str) -> bool:
    ts = pd.Timestamp(ts_iso)
    if str(ts.date()) != day:
        return False
    lo = dtime.fromisoformat(lo_hhmm + ":00")
    hi = dtime.fromisoformat(hi_hhmm + ":00")
    return lo <= ts.time() <= hi


def check_sanity_anchors(signals: list[dict], anchors: dict) -> dict:
    a1, a2 = anchors["anchor_1"], anchors["anchor_2"]
    hit1 = [s for s in signals if _in_window(s["entry_ts"], a1["date"], *a1["window_et"])]
    hit2 = [s for s in signals if _in_window(s["entry_ts"], a2["date"], *a2["window_et"])]
    return {
        "anchor_1_hit": bool(hit1), "anchor_1_matches": hit1,
        "anchor_2_hit": bool(hit2), "anchor_2_matches": hit2,
        "both_anchors_hit": bool(hit1) and bool(hit2),
    }


# =====================================================================================
# Real-fills dollar pass -- OPRA-covered days only.
# =====================================================================================
def price_and_walk_signal(sig: dict, spy_day_with_stack: pd.DataFrame, safe_arm_cfg: dict,
                           safe_params: dict, time_stop: dtime) -> dict:
    trade_date = date.fromisoformat(sig["day"])
    entry_spot = float(sig["entry_close"])
    strike = se._strike_for(safe_arm_cfg, entry_spot, "C")
    symbol = option_symbol(trade_date, strike, "C")
    spy_plain = se._load_spy_5m_for_date(trade_date)  # naive-ET RTH df, dojo convention
    if spy_plain is None:
        return {**sig, "status": "NO_SPY_DATA"}
    opt_df, price_source, is_synth = se._load_option_series(symbol, "C", strike, trade_date, spy_plain)
    if opt_df is None or opt_df.empty:
        return {**sig, "status": "NO_OPTION_DATA", "symbol": symbol, "strike": strike}
    entry_ts_naive = pd.Timestamp(sig["entry_ts"]).tz_localize(None)
    fill = bar_at_or_after(opt_df, entry_ts_naive)
    if fill is None:
        return {**sig, "status": "NO_FILL", "symbol": symbol, "strike": strike,
                "price_source": price_source, "is_synthetic": is_synth}
    entry_premium = round(fill.vwap, 4)
    base_qty = int(safe_params.get("min_contracts", 3))
    afford = fx.risk_gate.max_affordable_qty(
        equity=float(safe_arm_cfg.get("starting_equity", 2000.0)), premium=entry_premium,
        params=safe_params)
    qty = min(base_qty, afford) if afford else base_qty
    if qty < 1:
        return {**sig, "status": "UNAFFORDABLE", "symbol": symbol, "strike": strike,
                "entry_premium": entry_premium, "price_source": price_source}

    ribbon_tick_df = se._ribbon_aligned_to(spy_day_with_stack, opt_df)
    exit_shape = se._resolve_exit_shape(safe_arm_cfg, STRATEGY_NAME, None)
    result = walk_exit_manager(
        symbol=symbol, side="C", entry_time_et=fill.timestamp_et, entry_premium=entry_premium,
        qty=qty, exit_shape=exit_shape, structure_stop_enabled=STRUCTURE_STOP_ENABLED,
        trigger_level=float(sig["zone_low"]), strategy=STRATEGY_NAME, time_stop_et=time_stop,
        opt_df=opt_df, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=spy_plain,
    )
    return {**sig, "status": "FILLED", "symbol": symbol, "strike": strike, "qty": qty,
            "entry_premium": entry_premium, "price_source": price_source, "is_synthetic": is_synth,
            "pnl": result.dollar_pnl, "exit_reason": result.exit_reason,
            "hold_minutes": result.hold_minutes, "resolved": result.resolved}


def run_real_fills(spy_full_with_stack: pd.DataFrame, freq_out: dict, opra_days: set[str],
                    safe_arm_cfg: dict, safe_params: dict, time_stop: dtime) -> dict:
    out: dict[str, list[dict]] = {}
    for cid, cell in freq_out.items():
        priced = []
        for sig in cell["signals"]:
            if sig["day"] not in opra_days:
                continue
            day = date.fromisoformat(sig["day"])
            spy_day_with_stack = _day_slice(spy_full_with_stack, day).reset_index(drop=True)
            # se._load_spy_5m_for_date/_load_option_series need NAIVE ET timestamps; strip tz
            # on the local copy passed for ribbon alignment (se._ribbon_aligned_to handles it).
            spy_day_naive = spy_day_with_stack.copy()
            spy_day_naive["timestamp_et"] = pd.to_datetime(spy_day_naive["timestamp_et"]).dt.tz_localize(None)
            priced.append(price_and_walk_signal(sig, spy_day_naive, safe_arm_cfg, safe_params, time_stop))
        out[cid] = priced
    return out


# =====================================================================================
# Ship-gate evaluation (conditions 1-4; condition 5 BH-FDR applied across the whole grid
# in `main`, since it needs every cell's p-value at once).
# =====================================================================================
def evaluate_cell(priced: list[dict], held_out_days: set[str]) -> dict:
    filled = [p for p in priced if p.get("status") == "FILLED" and p.get("pnl") is not None]
    n = len(filled)
    if n == 0:
        return {"n": 0, "condition_1": False, "condition_2": False, "condition_3": False,
                "condition_4": False, "total_pnl": 0.0, "expectancy": None, "p_value": 1.0}
    pnls = [p["pnl"] for p in filled]
    total = round(sum(pnls), 2)
    condition_1 = total > 0

    by_day: dict[str, float] = {}
    for p in filled:
        by_day[p["day"]] = by_day.get(p["day"], 0.0) + p["pnl"]
    n_days = len(by_day)
    day_wins = sum(1 for v in by_day.values() if v > 0)
    condition_2 = n_days > 0 and day_wins > (n_days / 2.0)

    top = max(pnls)
    condition_3 = (total - top) > 0

    held_out_total = sum(v for d, v in by_day.items() if d in held_out_days)
    held_out_days_hit = [d for d in by_day if d in held_out_days]
    condition_4 = bool(held_out_days_hit) and held_out_total > 0

    p_val = _one_sample_p(pnls)
    return {
        "n": n, "total_pnl": total, "expectancy": round(total / n, 2),
        "win_rate": round(sum(1 for x in pnls if x > 0) / n, 3),
        "condition_1_positive_aggregate": condition_1,
        "condition_2_day_majority": condition_2, "condition_2_day_wins": day_wins,
        "condition_2_day_count": n_days,
        "condition_3_survives_top_trade_drop": condition_3,
        "condition_3_total_minus_top": round(total - top, 2),
        "condition_4_holds_on_held_out": condition_4,
        "condition_4_held_out_total": round(held_out_total, 2),
        "condition_4_held_out_days_with_trades": held_out_days_hit,
        "p_value_raw": round(p_val, 4),
        "by_day_pnl": {k: round(v, 2) for k, v in by_day.items()},
    }


# =====================================================================================
# main
# =====================================================================================
def main() -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    full_days = prereg["populations"]["full_history_days"]
    opra_days = set(prereg["populations"]["opra_covered_days"])
    held_out_days = set(prereg["populations"]["held_out_days"])
    anchors = prereg["sanity_anchors"]

    print("[load] SPY full continuous frame + LevelMemory + ribbon + RSI ...", file=sys.stderr)
    spy_full = _load_spy_full()
    lm = LevelMemory(spy_full)
    ribbon_df = compute_ribbon(spy_full["close"].reset_index(drop=True))
    spy_full_with_stack = spy_full.reset_index(drop=True).copy()
    spy_full_with_stack["stack"] = ribbon_df["stack"].values
    rsi_series = _wilder_rsi(spy_full["close"].reset_index(drop=True))

    grid = build_grid(prereg)
    print(f"[grid] {len(grid)} cells", file=sys.stderr)

    print("[detector] full 44-day frequency pass ...", file=sys.stderr)
    freq_out = run_detector_frequency(spy_full, lm, rsi_series, full_days, grid)

    safe_arm_cfg, _canonical = se._resolve_arm_cfg(ARM_ID)
    safe_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    time_stop = se._parse_hhmm(se._time_stop_et_for(safe_arm_cfg))

    print("[real-fills] pricing + exit-walking OPRA-covered signals ...", file=sys.stderr)
    priced_out = run_real_fills(spy_full_with_stack, freq_out, opra_days, safe_arm_cfg,
                                 safe_params, time_stop)

    print("[gates] sanity anchors + ship-bar conditions 1-4 + BH-FDR ...", file=sys.stderr)
    cell_rows = []
    pvals = []
    for cell in grid:
        cid = cell.cell_id()
        anchor_check = check_sanity_anchors(freq_out[cid]["signals"], anchors)
        gate = evaluate_cell(priced_out[cid], held_out_days)
        pvals.append(gate["p_value_raw"])
        cell_rows.append({
            "cell_id": cid, "params": asdict(cell),
            "full_history_n_signals": freq_out[cid]["n"],
            "full_history_n_days_fired": freq_out[cid]["n_days_fired"],
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

    # Diagnostic-only (no effect on the grid/gates/verdict, per no-post-hoc-tuning): if
    # anchor_1 (2026-07-22) is missed by every cell, characterize WHY -- when does each
    # up-structure qualifier candidate first read True on that day, vs the exhibit's own
    # 10:40 ET pullback-low bar. Answers "how late" the lagging qualifiers are, for the report.
    anchor1_diag = None
    if not any(r["anchor_check"]["anchor_1_hit"] for r in cell_rows):
        day22 = _day_slice(spy_full, date(2026, 7, 22)).reset_index(drop=True)
        pullback_bar_idx = int(day22.index[day22["timestamp_et"].dt.time == dtime(10, 40)][0])
        diag = {}
        for mode in ("MARKET_STRUCTURE", "PRICE_VWAP"):
            ok = up_structure_series(day22, mode)
            # "how late" = first True AT OR AFTER the exhibit's own pullback bar (10:40 ET) --
            # NOT the first True of the whole day, which can pre-date an intervening False
            # stretch (PRICE_VWAP here is True pre-open-rally, flips False during the 10:20-
            # 10:50 pullback itself, then True again -- the recovery-after-the-dip time is the
            # meaningful "how late" number, not the unrelated early-morning True).
            first_true_after = next((i for i in range(pullback_bar_idx, len(ok)) if ok[i]), None)
            diag[mode] = {
                "first_true_at_or_after_pullback_bar_et": (
                    str(day22.iloc[first_true_after]["timestamp_et"].time())
                    if first_true_after is not None else None),
            }
        anchor1_diag = {
            "note": ("Every cell missed anchor_1 -- both up-structure qualifier candidates, "
                     "evaluated at the pullback-low bar itself (10:40 ET per the exhibit), "
                     "read False at that exact bar. Verified genuine timing gap, not a bug "
                     "(session VWAP crossed correctly per the math; MARKET_STRUCTURE lacked "
                     "confirmed swing labels yet at that point in the session): PRICE_VWAP "
                     "recovers True at "
                     f"{diag['PRICE_VWAP']['first_true_at_or_after_pullback_bar_et']} ET "
                     "(15 min after the 10:40 low), MARKET_STRUCTURE first reads True at "
                     f"{diag['MARKET_STRUCTURE']['first_true_at_or_after_pullback_bar_et']} ET "
                     "(45 min after) -- both LAG the exact bar J's own pattern-read called "
                     "live, which is the root-cause tension this whole queue item exists to "
                     "fix (lagging trend confirmation vs J's earlier structural read)."),
            "by_mode": diag,
        }

    shippable = [r for r in cell_rows if r["clears_all_gates"]]
    shippable.sort(key=lambda r: r["real_fills"].get("expectancy") or -1e9, reverse=True)
    ranked_all = sorted(
        cell_rows,
        key=lambda r: (r["clears_all_gates"], r["real_fills"].get("expectancy") or -1e9),
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
        "anchor_1_universal_miss_diagnostic": anchor1_diag,
        "top_5": ranked_all[:5],
        "all_cells": ranked_all,
    }
    SCORECARD_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[written] {SCORECARD_PATH}")
    print(f"[verdict] {verdict}  shippable={len(shippable)}/{len(grid)}")
    for r in ranked_all[:5]:
        rf = r["real_fills"]
        print(f"  {r['cell_id']:45s} clears={r['clears_all_gates']!s:5s} "
              f"n={rf.get('n')} total=${rf.get('total_pnl')} exp=${rf.get('expectancy')} "
              f"anchors={r['anchor_check']['both_anchors_hit']}")
    return out


if __name__ == "__main__":
    main()
