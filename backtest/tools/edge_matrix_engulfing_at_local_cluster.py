"""backtest/tools/edge_matrix_engulfing_at_local_cluster.py -- EDGE-MATRIX family
runner: engulfing-at-local-cluster (ENGULFING-AT-STRUCTURE-TRIGGER Lane-A track's own
named next step, automation/overnight/queue.md).

Frozen pre-reg (written + zero-fork check run BEFORE any P&L replay): analysis/
recommendations/engulfing-at-local-cluster-prereg-2026-07-25.json -- 3 knobs x 16 cells:
    min_touches       in {3, 4}
    min_body_dollars  in {0.0, 0.40, 0.60, 0.80}
    tolerance         in {0.15, 0.20}
Direction (bearish-eng-at-high-cluster -> put / bullish-eng-at-low-cluster -> call) is
structural, evaluated together every cell -- not a 4th grid axis. The shipped registry
config (touch3|body0.40|tol0.20) is cell `touch3|body0.40|tol0.20`.

DETECTOR: backtest/tools/engulfing_at_local_cluster_detector.py -- a ZERO-FORK grid
adapter over the ALREADY-SHIPPED backtest/lib/patterns/registry.py::
engulfing_at_local_cluster predicate (commit 8aed997a). See that module's docstring +
backtest/tests/test_engulfing_at_local_cluster.py for the byte-identical-vs-registry
proof.

EXITS (identical for all 16 cells -- entry-side tuning ONLY): the LIVE RIBBON_RIDE shape
via dojo sim_executor._resolve_exit_shape(safe arm, "ribbon_ride", None), walked through
backtest/lib/exit_manager_walk.walk_exit_manager (the REAL production exit_manager core)
-- verbatim convention from edge_matrix_engulfing_at_structure.py (Lane-B).

DOLLARS: real OPRA fills only (option_pricing_real.load_contract_bars). NO BS-synthetic
anywhere -- uncached contracts are counted + disclosed as NO_OPRA skips, never priced.

SPY FRAME + TRUE-ET conversion: REUSES edge_matrix_bear_level_rejection.load_spy_frame /
_true_et verbatim (same frozen 386-day inventory) -- never re-derived, per C34 (one
implementation, not a fork).

Rail-4 CLEAR: research tool + JSON outputs. Touches NO params/orders/filters/
heartbeat_core/strategies.py/CLAUDE.md. No broker import. No git operations. No live
wiring -- engulfing_at_local_cluster remains registry.py discovery-only regardless of
this grid's verdict.

Run: backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_engulfing_at_local_cluster.py
     backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_engulfing_at_local_cluster.py --smoke 15
     backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_engulfing_at_local_cluster.py --anchors-only
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet", "backtest/tools"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from lib.ribbon import compute_ribbon  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol  # noqa: E402

import engulfing_at_local_cluster_detector as det  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from edge_matrix_bear_level_rejection import load_spy_frame, _true_et, regime_split  # noqa: E402
from pullback_hold_bull_replay import _one_sample_p  # noqa: E402  -- reused stat convention
from dojo import sim_executor as se  # noqa: E402
import fleet_executor as fx  # noqa: E402  -- reuse risk_gate.max_affordable_qty (broker-free, guard-tested)

PREREG_PATH = _ROOT / "analysis" / "recommendations" / "engulfing-at-local-cluster-prereg-2026-07-25.json"
INVENTORY_PATH = _ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
EPISODES_PATH = _ROOT / "analysis" / "recommendations" / "engulfing-at-local-cluster-episodes-2026-07-25.json"
RESULTS_PATH = _ROOT / "analysis" / "recommendations" / "engulfing-at-local-cluster-2026-07-25.json"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"
DATA_DIR = _ROOT / "backtest" / "data"

ENTRY_DELAY = timedelta(minutes=5)   # signal bar closes, entry fills in the NEXT 5m bar
STRATEGY_NAME = "ribbon_ride"
ARM_ID = "safe"

ANCHORS: tuple[dict, ...] = (
    {"date": "2026-07-23", "time_et": "10:40", "bias": "bearish",
     "note": "10:40 bearish engulfing at the 10:35/10:40 twin-high cluster -- SPY 738.86 -> 736.63"},
    {"date": "2026-07-21", "time_et": "11:05", "bias": "bullish",
     "note": "11:05 bullish engulfing at the 10:40/11:00/11:05 cluster -- SPY 746.77 -> 748.97"},
)


def log(msg: str) -> None:
    print(f"[edge-matrix-engulfing-at-local-cluster] {msg}", flush=True)


# =====================================================================================
# Anchor sanity check -- reads the FRESHEST cache directly (includes today), completely
# separate from the frozen 386-day inventory population (which ends 2026-07-22).
# =====================================================================================
def _find_freshest_spy_csv(data_dir: Path = DATA_DIR) -> Path:
    pattern = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_\w+)?\.csv$")
    candidates = []
    for p in data_dir.glob("spy_5m_*.csv"):
        m = pattern.match(p.name)
        if m:
            candidates.append((m.group(2), m.group(1), p))
    if not candidates:
        raise FileNotFoundError(f"no spy_5m_*.csv under {data_dir}")
    candidates.sort(key=lambda c: (c[0], c[1]))
    latest_end = candidates[-1][0]
    tied = sorted((c for c in candidates if c[0] == latest_end), key=lambda c: c[1])
    return tied[0][2]


def _load_freshest_rth(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, tuple[Bar, ...], str]:
    csv_path = _find_freshest_spy_csv(data_dir)
    df = pd.read_csv(csv_path)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(timestamp_et=ts, date=ts.dt.date, time_et=ts.dt.time)
    mask = (df["time_et"] >= dtime(9, 30)) & (df["time_et"] < dtime(16, 0))
    df = df.loc[mask].reset_index(drop=True)
    bars = tuple(
        Bar(open_time=r.timestamp_et.to_pydatetime(), open=float(r.open), high=float(r.high),
            low=float(r.low), close=float(r.close), volume=float(r.volume),
            granularity_seconds=300, source="alpaca_rest_iex")
        for r in df.itertuples(index=False)
    )
    return df, bars, csv_path.name


def check_anchors(grid: list[det.Cell]) -> dict:
    """Runs the REAL detector (not a hand re-derivation) against every grid cell at
    both anchor bar indices, on the freshest cache. Returns per-cell, per-anchor
    actual_fired/actual_bias, plus a both_anchors_fire flag per cell."""
    df, bars, csv_name = _load_freshest_rth()
    ctx = det.build_context(bars)

    idx_by_anchor: dict = {}
    for a in ANCHORS:
        d = date.fromisoformat(a["date"])
        t = dtime.fromisoformat(a["time_et"] + ":00")
        m = (df["date"] == d) & (df["time_et"] == t)
        hits = np.flatnonzero(m.to_numpy())
        idx_by_anchor[(a["date"], a["time_et"])] = int(hits[0]) if len(hits) == 1 else None

    per_anchor: list[dict] = []
    both_fire_by_cell: dict[str, bool] = {c.cell_id(): True for c in grid}
    for a in ANCHORS:
        idx = idx_by_anchor[(a["date"], a["time_et"])]
        cell_results = []
        for cell in grid:
            fired = False
            bias = None
            if idx is not None:
                hit = det.detect_bar(ctx, idx, cell)
                fired = hit is not None
                bias = hit["bias"] if hit else None
                if fired:
                    fired = bias == a["bias"]
            if not fired:
                both_fire_by_cell[cell.cell_id()] = False
            cell_results.append({"cell_id": cell.cell_id(), "fired": fired, "bias": bias})
        bar = ctx.bars[idx] if idx is not None else None
        per_anchor.append({
            "date": a["date"], "time_et": a["time_et"], "bias": a["bias"], "note": a["note"],
            "bar_found": idx is not None, "bar_index": idx,
            "bar_ohlc": (None if bar is None else {
                "open": round(bar.open, 2), "high": round(bar.high, 2),
                "low": round(bar.low, 2), "close": round(bar.close, 2),
            }),
            "cells": cell_results,
        })
    return {
        "source_csv": csv_name,
        "anchors": per_anchor,
        "both_anchors_fire_by_cell": both_fire_by_cell,
        "n_cells_both_anchors_fire": sum(1 for v in both_fire_by_cell.values() if v),
    }


# =====================================================================================
# Fill + exit walk (real OPRA only)
# =====================================================================================
def fill_and_walk_day(day_str: str, signals: list[dict], spy_ts: pd.Series,
                      spy_close: np.ndarray, day_slice_naive: pd.DataFrame,
                      arm_cfg: dict, safe_params: dict, exit_shape: dict,
                      structure_stop_enabled: bool, time_stop: dtime,
                      min_entry_premium: float, walk_cache: dict) -> list[dict]:
    out: list[dict] = []
    trade_date = date.fromisoformat(day_str)
    eod = datetime.combine(trade_date, dtime(16, 0))
    busy_until: Optional[pd.Timestamp] = None
    for s in signals:
        g = s["gidx"]
        sig_ts = pd.Timestamp(spy_ts.iloc[g])
        entry_ts = sig_ts + ENTRY_DELAY
        side = "P" if s["bias"] == "bearish" else "C"
        rec = {"day": day_str, "gidx": g, "bias": s["bias"], "side": side,
               "signal_ts": sig_ts.isoformat(), "entry_ts": entry_ts.isoformat(),
               "trigger_level": s["trigger_level"], "cluster_touch_count": s["cluster_touch_count"],
               "cluster_touch_spread": s["cluster_touch_spread"], "engulfed_body_dollars": s["engulfed_body_dollars"]}
        if busy_until is not None and entry_ts <= busy_until:
            rec["status"] = "SKIPPED_IN_POSITION"
            out.append(rec)
            continue
        spot = float(spy_close[g])
        strike = se._strike_for(arm_cfg, spot, side)
        symbol = option_symbol(trade_date, strike, side)
        rec.update({"strike": strike, "symbol": symbol, "spot_at_signal": round(spot, 2)})
        raw = load_contract_bars(symbol)
        if raw is None or raw.empty:
            rec["status"] = "NO_OPRA"
            out.append(rec)
            continue
        opt = raw.copy()
        opt["timestamp_et"] = _true_et(opt["timestamp_et"])
        opt = opt.sort_values("timestamp_et").reset_index(drop=True)
        fill = bar_at_or_after(opt, entry_ts)
        if fill is None:
            rec["status"] = "NO_FILL"
            out.append(rec)
            continue
        prem = round(float(fill.vwap), 4)
        rec["entry_premium"] = prem
        if prem < min_entry_premium:
            rec["status"] = "BELOW_MIN_PREMIUM"
            out.append(rec)
            continue
        base_qty = int(safe_params.get("min_contracts", 3))
        afford = fx.risk_gate.max_affordable_qty(
            equity=float(arm_cfg.get("starting_equity", 2000.0)), premium=prem, params=safe_params)
        qty = min(base_qty, afford) if afford else base_qty
        if qty < 1:
            rec["status"] = "UNAFFORDABLE"
            out.append(rec)
            continue
        key = (day_str, str(fill.timestamp_et), symbol, qty, round(s["trigger_level"], 2))
        res = walk_cache.get(key)
        if res is None:
            ribbon_tick_df = se._ribbon_aligned_to(day_slice_naive, opt)
            res = walk_exit_manager(
                symbol=symbol, side=side, entry_time_et=fill.timestamp_et, entry_premium=prem,
                qty=qty, exit_shape=exit_shape, structure_stop_enabled=structure_stop_enabled,
                trigger_level=float(s["trigger_level"]), strategy=STRATEGY_NAME, time_stop_et=time_stop,
                opt_df=opt, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=day_slice_naive)
            walk_cache[key] = res
        if res.exit_reason == "no_bars_after_entry":
            rec["status"] = "NO_BARS_AFTER_ENTRY"
            out.append(rec)
            busy_until = pd.Timestamp(eod)
            continue
        rec.update({"status": "FILLED", "qty": qty, "pnl": round(res.dollar_pnl, 2),
                    "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
                    "fill_ts": str(fill.timestamp_et)})
        out.append(rec)
        busy_until = pd.Timestamp(res.exit_time_et) if res.exit_time_et is not None else pd.Timestamp(eod)
    return out


# =====================================================================================
# Per-cell metrics + gates (same 4-gate convention as bear-level-rejection / Lane-B)
# =====================================================================================
def cell_metrics(cell: det.Cell, rows: list[dict], tuning_set: set[str], heldout_set: set[str],
                 vix_band_by_day: dict[str, str], both_anchors_fire: bool) -> dict:
    tun = [r for r in rows if r["day"] in tuning_set]
    held = [r for r in rows if r["day"] in heldout_set]
    n_signals = len(tun)
    fills = [r for r in tun if r["status"] == "FILLED"]
    pnls = [r["pnl"] for r in fills]
    n = len(fills)
    total = round(sum(pnls), 2)
    expectancy = round(total / n, 2) if n else 0.0

    by_day: dict[str, float] = {}
    for r in fills:
        by_day[r["day"]] = by_day.get(r["day"], 0.0) + r["pnl"]
    n_days = len(by_day)
    day_wins = sum(1 for v in by_day.values() if v > 0)
    day_wr = round(day_wins / n_days, 3) if n_days else 0.0

    desc = sorted(pnls, reverse=True)
    ex_top1 = round(total - sum(desc[:1]), 2) if n else 0.0
    ex_top3 = round(total - sum(desc[:3]), 2) if n else 0.0

    held_fills = [r for r in held if r["status"] == "FILLED"]
    held_total = round(sum(r["pnl"] for r in held_fills), 2)

    p_raw = round(_one_sample_p(pnls), 5) if n >= 2 else 1.0

    g1 = total > 0
    g2 = n_days > 0 and day_wins > (n_days / 2.0)
    g3 = n >= 1 and ex_top1 > 0
    g4 = len(held_fills) > 0 and held_total > 0

    n_bull = sum(1 for r in fills if r["bias"] == "bullish")
    n_bear = sum(1 for r in fills if r["bias"] == "bearish")

    def _count(status: str, pop: list[dict]) -> int:
        return sum(1 for r in pop if r["status"] == status)

    return {
        "cell_id": cell.cell_id(),
        "params": cell.to_dict(),
        "is_shipped_config": cell.is_shipped_config(),
        "n_signals": n_signals,
        "n_real_fills": n,
        "n_bullish_fills": n_bull,
        "n_bearish_fills": n_bear,
        "expectancy": expectancy,
        "total_pnl": total,
        "day_wr": day_wr,
        "n_days_covered": n_days,
        "n_day_wins": day_wins,
        "ex_top1_total": ex_top1,
        "ex_top3_total": ex_top3,
        "held_out_total": held_total,
        "n_heldout_fills": len(held_fills),
        "n_heldout_signals": len(held),
        "p_raw": p_raw,
        "gates": {"g1_positive_aggregate": g1, "g2_day_majority": g2,
                  "g3_survives_ex_top1": g3, "g4_held_out_positive": g4},
        "gates_passed": int(g1) + int(g2) + int(g3) + int(g4),
        "below_evidence_floor_n15": n < 15,
        "both_anchors_fire": both_anchors_fire,
        "skips_tuning": {
            "skipped_in_position": _count("SKIPPED_IN_POSITION", tun),
            "no_opra": _count("NO_OPRA", tun),
            "no_fill": _count("NO_FILL", tun),
            "below_min_premium": _count("BELOW_MIN_PREMIUM", tun),
            "unaffordable": _count("UNAFFORDABLE", tun),
            "no_bars_after_entry": _count("NO_BARS_AFTER_ENTRY", tun),
        },
        "regime_split": regime_split(fills, vix_band_by_day),
    }


def _bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg FDR, verbatim convention from
    backtest/tools/pullback_hold_bull_replay.py::_bh_fdr / edge_matrix_engulfing_at_structure.py
    -- a multi-cell PORTFOLIO correction across all cells' p_raw, not re-derived per cell."""
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
# main
# =====================================================================================
def main(smoke_days: int = 0, anchors_only: bool = False) -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"frozen pre-reg loaded: {PREREG_PATH.name} frozen_at={prereg['frozen_at']}")
    axes = prereg["grid"]["axes"]
    grid = det.build_grid(axes)
    assert len(grid) == prereg["grid"]["n_cells"] == 16
    log(f"grid: {len(grid)} cells")

    log("running anchor sanity check against the FRESHEST cache (includes today) ...")
    anchor_report = check_anchors(grid)
    for a in anchor_report["anchors"]:
        n_fire = sum(1 for c in a["cells"] if c["fired"])
        log(f"  anchor {a['date']} {a['time_et']} ({a['bias']}): bar_found={a['bar_found']} "
            f"fires on {n_fire}/{len(grid)} cells")
    log(f"  cells firing on BOTH anchors: {anchor_report['n_cells_both_anchors_fire']}/{len(grid)}")

    if anchors_only:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        out = {"mode": "anchors_only", "generated_at": datetime.now().isoformat(),
               "prereg_path": str(PREREG_PATH.relative_to(_ROOT)).replace("\\", "/"),
               "anchor_check": anchor_report}
        RESULTS_PATH.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        log(f"wrote {RESULTS_PATH} (anchors-only mode)")
        return out

    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    covered = {r["date"] for r in inv["days"]}
    opra = sorted(d for d in inv["opra_days"] if d in covered)
    heldout = [d for d in inv["heldout_days"] if d in covered]
    heldout_set = set(heldout)
    tuning = [d for d in opra if d not in heldout_set]
    tuning_set = set(tuning)
    signal_days = tuning + heldout
    vix_band_by_day = {r["date"]: r.get("vix_band") for r in inv["days"]}

    results_path = RESULTS_PATH
    episodes_path = EPISODES_PATH
    if smoke_days:
        signal_days = tuning[:smoke_days] + heldout[:max(1, smoke_days // 4)]
        import tempfile
        _scratch = Path(tempfile.gettempdir())
        results_path = _scratch / "edge_matrix_ealc_results.SMOKE.json"
        episodes_path = _scratch / "edge_matrix_ealc_episodes.SMOKE.json"
        log(f"SMOKE MODE: {len(signal_days)} days only -> {results_path.name}")
    log(f"days: covered={len(covered)} opra(signal)={len(signal_days)} "
        f"tuning={len(tuning)} heldout={len(heldout)} "
        f"(heldout honored: {heldout[0]}..{heldout[-1]})")

    log("building continuous RTH SPY frame from inventory per-day source files ...")
    spy = load_spy_frame(inv)
    log(f"  spy rows={len(spy)} range={spy['timestamp_et'].iloc[0]}..{spy['timestamp_et'].iloc[-1]}")

    ribbon_df = compute_ribbon(spy["close"].reset_index(drop=True))
    stacks = ribbon_df["stack"].values
    spy_with_stack = spy.copy()
    spy_with_stack["stack"] = stacks

    safe_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    arm_cfg, canonical = se._resolve_arm_cfg(ARM_ID)
    exit_shape = se._resolve_exit_shape(arm_cfg, STRATEGY_NAME, None)
    structure_stop_enabled = se._structure_stop_enabled()
    time_stop = se._parse_hhmm(se._time_stop_et_for(arm_cfg))
    min_entry_premium = float(safe_params.get("min_entry_premium", 0.3))
    ent_before = se._parse_hhmm(safe_params.get("entry_no_trade_before_et", "09:35"))
    ent_after = se._parse_hhmm(safe_params.get("entry_no_trade_after_et", "15:00"))
    log(f"arm={canonical} exit_shape={exit_shape} structure_stop={structure_stop_enabled} "
        f"time_stop={time_stop} entry_window=[{ent_before},{ent_after}) "
        f"min_premium={min_entry_premium}")

    # Build the PatternContext ONCE over the full continuous multi-day frame (same
    # convention pattern_prescreen.py/pattern_anchor_verify.py already use for every
    # registry rule -- see engulfing_at_local_cluster_detector.py's own docstring on
    # why this is the matched, not re-decided, convention). spy["timestamp_et"] is
    # TRUE-ET but NAIVE (edge_matrix_bear_level_rejection._true_et localizes to None
    # at the end) -- Bar requires tz-aware, so re-localize to America/New_York (DST-
    # aware) before building bars; this is a pure type-adaptation, not a new timestamp
    # computation (the wall-clock values are unchanged).
    ts_aware = spy["timestamp_et"].dt.tz_localize("America/New_York")
    bars = tuple(
        Bar(open_time=ts.to_pydatetime(), open=float(r.open), high=float(r.high),
            low=float(r.low), close=float(r.close), volume=0.0,
            granularity_seconds=300, source="frozen_inventory")
        for ts, r in zip(ts_aware, spy.itertuples(index=False))
    )
    ctx = det.build_context(bars)
    log(f"  PatternContext built over {len(ctx.bars)} bars")

    ts = spy["timestamp_et"]
    dates_str = ts.dt.date.astype(str).values
    day_gidx: dict[str, np.ndarray] = {}
    for d in signal_days:
        day_gidx[d] = np.flatnonzero(dates_str == d)
    spy_close = spy["close"].to_numpy()

    times = np.array([t.time() for t in ts], dtype=object)
    entry_lo = (datetime.combine(date(2000, 1, 1), ent_before) - ENTRY_DELAY).time()
    entry_hi = (datetime.combine(date(2000, 1, 1), ent_after) - ENTRY_DELAY).time()

    day_slices_naive: dict[str, pd.DataFrame] = {}
    for d in signal_days:
        day_slices_naive[d] = spy_with_stack.iloc[day_gidx[d]].reset_index(drop=True)

    walk_cache: dict = {}
    episodes: dict[str, list[dict]] = {}
    n_total_bars = 0
    for ci, cell in enumerate(grid):
        cid = cell.cell_id()
        rows: list[dict] = []
        for d in signal_days:
            gs = day_gidx[d]
            n_total_bars += len(gs) if ci == 0 else 0
            sigs = det.detect_cell_day(ctx, gs, cell)
            if not sigs:
                continue
            sigs = [s for s in sigs if entry_lo <= times[s["gidx"]] < entry_hi]
            if not sigs:
                continue
            rows.extend(fill_and_walk_day(
                d, sigs, ts, spy_close, day_slices_naive[d], arm_cfg, safe_params,
                exit_shape, structure_stop_enabled, time_stop, min_entry_premium, walk_cache))
        episodes[cid] = rows
        n_fill = sum(1 for r in rows if r["status"] == "FILLED")
        log(f"  cell {ci + 1}/{len(grid)} {cid}: signals={len(rows)} fills={n_fill}")

    log(f"n_bars_evaluated (per cell, one pass): {n_total_bars}")

    cells_out = [
        cell_metrics(cell, episodes[cell.cell_id()], tuning_set, heldout_set, vix_band_by_day,
                     both_anchors_fire=anchor_report["both_anchors_fire_by_cell"][cell.cell_id()])
        for cell in grid
    ]

    pvals = [c["p_raw"] for c in cells_out]
    bh_sig = _bh_fdr(pvals, q=0.10)
    for c, sig in zip(cells_out, bh_sig):
        c["bh_significant"] = bool(sig)
        c["ship_candidate"] = bool(
            c["gates_passed"] == 4 and c["bh_significant"] and c["both_anchors_fire"]
            and c["n_real_fills"] >= 15)

    results = {
        "family": prereg["family"],
        "generated_at": datetime.now().isoformat(),
        "prereg_path": str(PREREG_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "prereg_frozen_at": prereg["frozen_at"],
        "day_inventory": str(INVENTORY_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "n_tuning_days": len(tuning),
        "n_heldout_days": len(heldout),
        "n_bars_evaluated": n_total_bars,
        "exit_shape": exit_shape,
        "structure_stop_enabled": structure_stop_enabled,
        "time_stop_et": str(time_stop),
        "anchor_check": anchor_report,
        "cells": cells_out,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    log(f"wrote {results_path}")

    episodes_path.parent.mkdir(parents=True, exist_ok=True)
    episodes_path.write_text(json.dumps({
        "family": prereg["family"],
        "generated_at": results["generated_at"],
        "prereg_path": results["prereg_path"],
        "note": ("per-cell episode detail so verifiers can recompute every cell metric. "
                 "status=FILLED rows carry real-OPRA pnl; all other statuses are disclosed "
                 "skips (NEVER BS-synthetic-priced)."),
        "cells": episodes,
    }, indent=1, default=str), encoding="utf-8")
    log(f"wrote {episodes_path}")

    log("==== CELL TABLE (tuning population; held_out separate) ====")
    for c in sorted(cells_out, key=lambda r: (-int(r["ship_candidate"]), -r["gates_passed"], -r["expectancy"])):
        log(f"  {c['cell_id']:24s} n={c['n_real_fills']:4d} (bull={c['n_bullish_fills']:3d} "
            f"bear={c['n_bearish_fills']:3d}) exp=${c['expectancy']:+8.2f} total=${c['total_pnl']:+10.2f} "
            f"dayWR={c['day_wr']:.3f} held=${c['held_out_total']:+9.2f} p={c['p_raw']:.4f} "
            f"gates={c['gates_passed']}/4 bh={c['bh_significant']} anchors={c['both_anchors_fire']} "
            f"shipped={c['is_shipped_config']} SHIP={c['ship_candidate']}")
    n_ship = sum(1 for c in cells_out if c["ship_candidate"])
    log(f"ship candidates: {n_ship}/{len(cells_out)}")
    return results


if __name__ == "__main__":
    _smoke = 0
    _args = sys.argv[1:]
    _anchors_only = "--anchors-only" in _args
    _args = [a for a in _args if a != "--anchors-only"]
    if len(_args) >= 2 and _args[0] == "--smoke":
        _smoke = int(_args[1])
    main(smoke_days=_smoke, anchors_only=_anchors_only)
