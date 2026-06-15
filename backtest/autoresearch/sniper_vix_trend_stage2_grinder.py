"""SNIPER VIX-trend Stage 2 -- entry-condition sweep with IS/OOS WF split.

Stage 1 (sniper_vix_trend_grinder.py) fixed entry knobs and swept EXIT params.
OOS-confirmed best exit config for off=2 (from 2026-05-23 validation):
  strike_offset=2, premium_stop_pct=-0.10, tp1_premium_pct=0.50,
  runner_target_pct=1.25, profit_lock_threshold_pct=0.05,
  profit_lock_stop_offset_pct=0.08

This Stage 2 fixes those exit params and sweeps the ENTRY-SIDE knobs that
control how many signals fire and which days qualify:

  VIX_LOWER       : [17.0, 17.5, 18.0, 18.5]   (4)
  vol_mult        : [0.9, 1.0, 1.1, 1.3, 1.5]  (5)
  min_stars       : [2, 3]                       (2)
  proximity_dollars: [1.0, 1.5, 2.0]            (3)

= 4 × 5 × 2 × 3 = 120 combos

VIX_TREND_WINDOW stays at 5 (uniquely optimal from Stage 1 OOS analysis).
require_break_above_open=True, body_min_cents=0.02 (fixed).

Each combo is evaluated with a two-window IS/OOS split:
  IS:  2025-01-01 .. 2025-10-31  (10 months)
  OOS: 2025-11-01 .. 2026-05-22  (6.5 months)

Per-combo WF gate: OOS_Sharpe / IS_Sharpe >= 0.50.
A keeper must pass BOTH floor gates AND WF gate.

OUTPUT (under autoresearch/_state/sniper_vix_trend_stage2/):
  progress.json   results.jsonl   rejections.jsonl   keepers.jsonl
  runner.pid      grinder.log

CLI:
  python -m autoresearch.sniper_vix_trend_stage2_grinder --hours 4 --workers 4
  python -m autoresearch.sniper_vix_trend_stage2_grinder --reset --hours 4 --workers 4
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import logging
import math
import multiprocessing as mp
import os
import random
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# ---------- Fixed knobs from Stage 1 OOS-confirmed best (off=2) ----------
FIXED_EXIT = {
    "strike_offset": 2,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.50,
    "tp1_qty_fraction": 0.5,
    "runner_target_pct": 1.25,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.08,
    "qty": 10,
    "require_break_above_open": True,
    "body_min_cents": 0.02,
}

# Fixed VIX trend window (uniquely optimal from Stage 1 OOS analysis).
VIX_TREND_WINDOW: int = 5

# IS/OOS split
IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 10, 31)
OOS_START = dt.date(2025, 11, 1)
OOS_END = dt.date(2026, 5, 22)
FULL_START = IS_START
FULL_END = OOS_END

# J anchor trades (OP-16 edge gate — VIX-trend universe)
J_WINNERS = [
    {"date": "2026-05-04", "j_pnl": 730},
]
J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260},
    {"date": "2026-05-06", "j_pnl": -300},
    {"date": "2026-05-07", "j_pnl": -165},
]

OUT_DIR = REPO / "autoresearch" / "_state" / "sniper_vix_trend_stage2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _build_param_grid() -> list[dict]:
    """Build 120-combo entry-condition sweep. Exit params are fixed."""
    grid: list[dict] = []
    for vix_lower in [17.0, 17.5, 18.0, 18.5]:
        for vol_mult in [0.9, 1.0, 1.1, 1.3, 1.5]:
            for min_stars in [2, 3]:
                for proximity_dollars in [1.0, 1.5, 2.0]:
                    combo: dict = dict(FIXED_EXIT)
                    combo["vix_lower"] = vix_lower
                    combo["vix_trend_window"] = VIX_TREND_WINDOW
                    combo["vol_mult"] = vol_mult
                    combo["min_stars"] = min_stars
                    combo["proximity_dollars"] = proximity_dollars
                    grid.append(combo)
    return grid


def _build_vix_maps(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
    window: int = VIX_TREND_WINDOW,
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    """Return (prior_close_map, prior_Nd_avg_map) for all trade dates."""
    vix_by_date: dict[dt.date, float] = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    vix_sorted_vals = [vix_by_date[d] for d in sorted_vix_days]

    prior_close: dict[dt.date, float] = {}
    prior_nd_avg: dict[dt.date, float] = {}

    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        if idx < 0:
            prior_close[trade_date] = 15.0
            prior_nd_avg[trade_date] = 15.0
            continue
        prior_close[trade_date] = float(vix_sorted_vals[idx])
        start_idx = max(0, idx - window + 1)
        window_vals = vix_sorted_vals[start_idx: idx + 1]
        prior_nd_avg[trade_date] = float(mean(window_vals)) if window_vals else 15.0

    return prior_close, prior_nd_avg


def _sharpe(day_pnl_map: dict[dt.date, float]) -> float:
    """Annualized Sharpe from daily P&L dict."""
    vals = list(day_pnl_map.values())
    if len(vals) < 2:
        return 0.0
    mu = sum(vals) / len(vals)
    variance = sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mu / std) * math.sqrt(252)


def _window_stats(
    all_trades: list[dict],
    start: dt.date,
    end: dt.date,
    label: str,
) -> dict:
    """Compute stats for the trades within [start, end]."""
    trades = [t for t in all_trades if start <= dt.date.fromisoformat(t["date"]) <= end]
    day_pnl: dict[dt.date, float] = defaultdict(float)
    quarter_pnl: dict[str, float] = defaultdict(float)
    for t in trades:
        d = dt.date.fromisoformat(t["date"])
        day_pnl[d] += t["dollar_pnl"]
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        quarter_pnl[q] += t["dollar_pnl"]
    n = len(trades)
    winners = sum(1 for t in trades if t["dollar_pnl"] > 0)
    total_pnl = round(sum(day_pnl.values()), 2)
    wr = round(winners / n, 3) if n else 0.0
    sharpe = _sharpe(dict(day_pnl))
    pos_q = sum(1 for v in quarter_pnl.values() if v > 0)
    return {
        "window": label,
        "n_trades": n,
        "total_pnl": total_pnl,
        "wr": wr,
        "sharpe": round(sharpe, 3),
        "pos_q": pos_q,
        "quarter_count": len(quarter_pnl),
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl.items())},
    }


def evaluate_entry_combo(combo_dict: dict) -> dict:
    """Evaluate one SNIPER entry combo with VIX filter + IS/OOS split."""
    try:
        from autoresearch import runner as _runner
        from lib.ribbon import compute_ribbon
        from lib.simulator_real import simulate_trade_real
        from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

        vix_lower: float = combo_dict["vix_lower"]
        trend_window: int = combo_dict.get("vix_trend_window", VIX_TREND_WINDOW)

        spy_full, vix_full = _runner.load_data(FULL_START, FULL_END)
        for df in (spy_full, vix_full):
            df["timestamp_et"] = (
                pd.to_datetime(df["timestamp_et"], utc=True)
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )

        all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
        trade_dates = [d for d in all_dates if FULL_START <= d <= FULL_END]
        prior_close_map, prior_nd_avg_map = _build_vix_maps(vix_full, trade_dates, trend_window)

        params = SniperParams(
            vol_mult=combo_dict["vol_mult"],
            body_min_cents=combo_dict["body_min_cents"],
            min_stars=combo_dict["min_stars"],
            proximity_dollars=combo_dict["proximity_dollars"],
            no_trade_before=dt.time(9, 30),
            no_trade_after=dt.time(15, 50),
            require_break_above_open=combo_dict["require_break_above_open"],
        )

        all_trades: list[dict] = []
        day_pnl_full: dict[dt.date, float] = defaultdict(float)
        opra_missing = 0
        skipped_low = 0
        skipped_trend = 0

        for date_et in trade_dates:
            vix_prev = prior_close_map.get(date_et, 15.0)
            vix_nd = prior_nd_avg_map.get(date_et, 15.0)

            # Joint regime gate
            if vix_prev < vix_lower:
                skipped_low += 1
                continue
            if vix_prev < vix_nd:
                skipped_trend += 1
                continue

            day_bars = spy_full[
                (spy_full["timestamp_et"].dt.date == date_et)
                & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
            ].reset_index(drop=True)
            if day_bars.empty:
                continue

            first_ts = day_bars["timestamp_et"].iloc[0]
            levels = compute_levels(spy_full, first_ts, params)
            if not levels:
                continue

            pre_bars = (
                spy_full[spy_full["timestamp_et"] < first_ts]
                .tail(40)
                .reset_index(drop=True)
            )
            combined = pd.concat([pre_bars, day_bars], ignore_index=True)
            day_offset = len(pre_bars)
            ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

            fired_today = False
            for i in range(len(day_bars)):
                if fired_today:
                    break
                bar_idx = day_offset + i
                bar = combined.iloc[bar_idx]
                signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
                if signal is None or signal.direction != "short":
                    continue

                entry_spot = float(signal.entry_price)
                strike = round(entry_spot) + combo_dict["strike_offset"]

                fill = simulate_trade_real(
                    entry_bar_idx=bar_idx,
                    entry_bar=bar,
                    spy_df=combined,
                    ribbon_df=ribbon_df,
                    rejection_level=signal.level.price,
                    triggers_fired=["sniper_level_break"],
                    side="P",
                    qty=combo_dict["qty"],
                    setup="SNIPER_LEVEL_BREAK",
                    levels_active=[lv.price for lv in levels if lv.tier == "Active"],
                    levels_carry=[lv.price for lv in levels if lv.tier == "Carry"],
                    use_tiered_exits=True,
                    strike_override=int(strike),
                    premium_stop_pct=combo_dict["premium_stop_pct"],
                    profit_lock_threshold_pct=combo_dict["profit_lock_threshold_pct"],
                    profit_lock_stop_offset_pct=combo_dict["profit_lock_stop_offset_pct"],
                )

                if fill is None:
                    opra_missing += 1
                    break

                trade_rec = {
                    "date": date_et.isoformat(),
                    "side": "P",
                    "strike": int(strike),
                    "dollar_pnl": float(fill.dollar_pnl or 0.0),
                    "exit_reason": str(fill.exit_reason),
                    "entry_premium": float(fill.entry_premium or 0.0),
                    "vix_prev": round(vix_prev, 2),
                    "vix_nd_avg": round(vix_nd, 2),
                    "level_label": signal.level.label,
                }
                all_trades.append(trade_rec)
                day_pnl_full[date_et] += trade_rec["dollar_pnl"]
                fired_today = True

        # Window stats
        is_stats = _window_stats(all_trades, IS_START, IS_END, "IS")
        oos_stats = _window_stats(all_trades, OOS_START, OOS_END, "OOS")
        full_stats = _window_stats(all_trades, FULL_START, FULL_END, "FULL")

        # WF ratio
        wf_ratio = 0.0
        if is_stats["sharpe"] != 0:
            wf_ratio = round(oos_stats["sharpe"] / is_stats["sharpe"], 3)
        wf_pass = (
            wf_ratio >= 0.50
            and oos_stats["sharpe"] > 0
        )

        # OP-16 edge capture (full window)
        by_day_full = {
            t["date"]: round(day_pnl_full[dt.date.fromisoformat(t["date"])], 2)
            for t in all_trades
        }
        winners_capture = sum(by_day_full.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = sum(
            -by_day_full.get(lo["date"], 0.0)
            for lo in J_LOSERS
            if by_day_full.get(lo["date"], 0.0) < 0
        )
        edge_capture = round(winners_capture - losers_added, 2)

        # Floor gates (VIX-trend universe — use OOS as primary gate)
        regressions: list[str] = []
        if oos_stats["total_pnl"] <= 0:
            regressions.append(f"OOS P&L ${oos_stats['total_pnl']:.0f} <= 0")
        if oos_stats["n_trades"] < 5:
            regressions.append(f"OOS n={oos_stats['n_trades']} < 5 (too thin)")
        if oos_stats["n_trades"] > 0 and oos_stats["wr"] < 0.38:
            regressions.append(f"OOS wr={oos_stats['wr']:.3f} < 0.38")
        if oos_stats["pos_q"] < 2:
            regressions.append(f"OOS +q={oos_stats['pos_q']}/{oos_stats['quarter_count']} < 2")
        if not wf_pass:
            regressions.append(f"WF ratio {wf_ratio:.3f} fails gate (need >= 0.50 AND OOS sharpe > 0)")
        if full_stats["total_pnl"] < -600:
            regressions.append(f"full P&L ${full_stats['total_pnl']:.0f} < -$600")

        # Ratification-quality bar (above baseline OOS-confirmed $2,486)
        is_ratification_candidate = (
            oos_stats["total_pnl"] > 2_486
            and oos_stats["wr"] >= 0.55
            and wf_pass
        )

        return {
            "combo": combo_dict,
            "vix_lower": vix_lower,
            "vix_trend_window": trend_window,
            "skipped_low": skipped_low,
            "skipped_trend": skipped_trend,
            "opra_missing": opra_missing,
            "is_stats": is_stats,
            "oos_stats": oos_stats,
            "full_stats": full_stats,
            "wf_ratio": wf_ratio,
            "wf_pass": wf_pass,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": edge_capture,
            "is_ratification_candidate": is_ratification_candidate,
            "passed_floors": len(regressions) == 0,
            "regressions": regressions,
        }

    except Exception as exc:
        return {
            "combo": combo_dict,
            "error": repr(exc),
            "trace": traceback.format_exc(),
            "passed_floors": False,
            "regressions": ["execution_error"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SNIPER VIX-trend Stage 2 — entry-condition sweep with IS/OOS WF split"
    )
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    workers = min(args.workers, 4)
    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()

    _setup_logging()
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    grid = _build_param_grid()
    random.Random(2027).shuffle(grid)

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)

    state: dict = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "fixed_exit": FIXED_EXIT,
        "vix_trend_window": VIX_TREND_WINDOW,
        "is_window": f"{IS_START}..{IS_END}",
        "oos_window": f"{OOS_START}..{OOS_END}",
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "ratification_candidates": 0,
        "best_oos_pnl": None,
        "best_wf_ratio": 0.0,
        "best_edge_capture": 0.0,
        "current_pid": os.getpid(),
        "workers": workers,
        "last_update": started.isoformat(),
        "status": "running",
        "mode": "vix_trend_stage2_entry_sweep",
    }
    _write_progress(state)
    logging.info(
        "SNIPER VIX-trend Stage 2 started: %d combos, %d workers, deadline=%s",
        len(grid), workers, deadline,
    )
    print(f"SNIPER VIX-trend Stage 2: {len(grid)} combos | {workers} workers | deadline {deadline:%H:%M:%S}")
    print(f"IS: {IS_START}..{IS_END}  |  OOS: {OOS_START}..{OOS_END}  |  WF gate >= 0.50")
    print()

    completed = 0
    keepers_n = 0
    ratification_n = 0
    best_oos: float | None = None

    try:
        with mp.Pool(workers) as pool:
            for result in pool.imap_unordered(evaluate_entry_combo, grid, chunksize=1):
                completed += 1

                if dt.datetime.now() > deadline:
                    logging.info("Deadline reached; terminating pool")
                    state["status"] = "deadline_reached"
                    _write_progress(state)
                    pool.terminate()
                    break

                already_in_keepers = False
                if result.get("passed_floors"):
                    _append_jsonl(RESULTS, result)
                    state["passed_floors"] += 1

                    oos_pnl = result["oos_stats"]["total_pnl"]
                    wf = result["wf_ratio"]
                    ec = result["edge_capture"]

                    if best_oos is None or oos_pnl > best_oos:
                        best_oos = oos_pnl
                        state["best_oos_pnl"] = oos_pnl
                        keepers_n += 1
                        state["keepers"] = keepers_n
                        already_in_keepers = True
                        _append_jsonl(KEEPERS, result)
                        logging.info(
                            "KEEPER #%d: OOS_pnl=$%.0f OOS_wr=%.2f WF=%.3f ec=$%.0f "
                            "vix_lower=%.1f vol=%.2f stars=%d prox=%.1f",
                            keepers_n, oos_pnl,
                            result["oos_stats"]["wr"],
                            wf, ec,
                            result["vix_lower"], result["combo"]["vol_mult"],
                            result["combo"]["min_stars"],
                            result["combo"]["proximity_dollars"],
                        )

                    if wf > state["best_wf_ratio"]:
                        state["best_wf_ratio"] = wf
                    if ec > state["best_edge_capture"]:
                        state["best_edge_capture"] = ec

                    if result.get("is_ratification_candidate"):
                        ratification_n += 1
                        state["ratification_candidates"] = ratification_n
                        if not already_in_keepers:
                            _append_jsonl(KEEPERS, result)

                else:
                    _append_jsonl(REJECTIONS, result)
                    state["rejected"] += 1

                state["completed"] = completed
                state["last_update"] = dt.datetime.now().isoformat()

                if completed % 5 == 0:
                    _write_progress(state)
                    pct = 100 * completed / len(grid)
                    best_str = f"${best_oos:,.0f}" if best_oos is not None else "n/a"
                    print(
                        f"\r[{pct:5.1f}%] {completed}/{len(grid)} | "
                        f"passed={state['passed_floors']} | "
                        f"best_OOS={best_str} | "
                        f"best_WF={state['best_wf_ratio']:.3f} | "
                        f"ratif={ratification_n}",
                        end="", flush=True,
                    )

    except KeyboardInterrupt:
        state["status"] = "interrupted"
    else:
        if state.get("status") == "running":
            state["status"] = "completed"
            state["completed_at"] = dt.datetime.now().isoformat()

    state["completed"] = completed
    _write_progress(state)

    print(
        f"\nDone: {completed}/{len(grid)} "
        f"| passed={state['passed_floors']} "
        f"| keepers={keepers_n} "
        f"| ratif={ratification_n} "
        f"| best_OOS={state.get('best_oos_pnl')} "
        f"| best_WF={state['best_wf_ratio']:.3f}"
    )
    logging.info(
        "Grinder finished: completed=%d passed=%d keepers=%d ratif=%d status=%s",
        completed, state["passed_floors"], keepers_n, ratification_n, state["status"],
    )
    if PIDFILE.exists():
        PIDFILE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
