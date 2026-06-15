"""SNIPER VIX-trend regime grinder — VIX>=18 AND VIX>5d_avg joint filter.

WHY (L73):
  The VIX>=18 grinder passed full-window gates ($3,297, WR=56.2%, +q=4/5)
  but FAILED OOS walk-forward (WF ratio=-0.224, OOS=-$833).

  Root cause: VIX level (>=18) alone is insufficient — VIX CHARACTER
  (trending/escalating vs spike-and-revert) is the true discriminator.

  VIX-trend diagnostic (_sniper_vix_trend_filter.py, 2026-05-24) confirmed:
    - Escalating VIX (VIX > 5d avg): n=39, pnl=+$4,738, WR=66.7%
    - Declining VIX  (VIX <= 5d avg): n=34, pnl=-$1,440, WR=44.1%
    - Joint filter OOS (VIX>=18 AND escalating): $+1,108, WR=55%, Sharpe=1.901
      (vs baseline OOS -$833, WR=46%, Sharpe=-0.820 — major improvement)

  The full 432-combo grinder with joint filter finds the BEST combo within
  the escalating VIX universe. The single-combo diagnostic used primary
  candidate (off=1); the optimal combo within the joint-filter universe may
  differ.

FILTER:
  Skip trade day if EITHER:
    prior_day_VIX_close < VIX_THRESHOLD (18)      [VIX too quiet]
    OR
    prior_day_VIX_close < prior_5d_avg_VIX_close   [VIX declining]

  Only trade when VIX >= 18 AND VIX is above its 5-day rolling average
  (regime is ESCALATING, not just elevated).

GRID: Same 432-combo grid as sniper_vix18_grinder.py.

GATES:
  Ratification gates: pnl > $2,000 AND WR >= 45% AND +quarters >= 4.
  WF gate: build `_oos_sniper_vix_trend.py` after this run completes.

OUTPUT (under autoresearch/_state/sniper_vix_trend_stage1/):
  progress.json  results.jsonl  rejections.jsonl  keepers.jsonl  runner.pid  grinder.log

CLI:
  python.exe -m autoresearch.sniper_vix_trend_grinder --hours 6 --workers 4
  python.exe -m autoresearch.sniper_vix_trend_grinder --reset --hours 6 --workers 4
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import logging
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

VIX_THRESHOLD: int = 18
VIX_TREND_WINDOW: int = 5  # rolling prior days for VIX average

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

OUT_DIR = REPO / "autoresearch" / "_state" / "sniper_vix_trend_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

J_WINNERS = [
    {"date": "2026-05-04", "j_pnl": 730},
]
J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260},
    {"date": "2026-05-06", "j_pnl": -300},
    {"date": "2026-05-07", "j_pnl": -165},
]


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
    grid: list[dict] = []
    for strike_offset in [1, 2, 3]:
        for premium_stop_pct in [-0.10, -0.15, -0.20, -0.25]:
            for profit_lock_threshold_pct in [0.0, 0.05, 0.10]:
                for profit_lock_stop_offset_pct in [0.05, 0.08]:
                    for tp1_premium_pct in [0.30, 0.40, 0.50]:
                        for runner_target_pct in [1.25, 2.0]:
                            grid.append({
                                "vol_mult": 1.1,
                                "body_min_cents": 0.02,
                                "min_stars": 2,
                                "strike_offset": strike_offset,
                                "premium_stop_pct": premium_stop_pct,
                                "tp1_premium_pct": tp1_premium_pct,
                                "tp1_qty_fraction": 0.5,
                                "runner_target_pct": runner_target_pct,
                                "profit_lock_threshold_pct": profit_lock_threshold_pct,
                                "profit_lock_stop_offset_pct": profit_lock_stop_offset_pct,
                                "qty": 10,
                                "proximity_dollars": 1.5,
                                "require_break_above_open": True,
                            })
    return grid


def _build_vix_maps(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
) -> tuple[dict[dt.date, float], dict[dt.date, float]]:
    """Return (prior_close_map, prior_5d_avg_map) for all trade dates."""
    vix_by_date: dict[dt.date, float] = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    vix_sorted_vals = [vix_by_date[d] for d in sorted_vix_days]

    prior_close: dict[dt.date, float] = {}
    prior_5d_avg: dict[dt.date, float] = {}

    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        if idx < 0:
            prior_close[trade_date] = 15.0
            prior_5d_avg[trade_date] = 15.0
            continue
        prior_close[trade_date] = float(vix_sorted_vals[idx])
        start_idx = max(0, idx - VIX_TREND_WINDOW + 1)
        window_vals = vix_sorted_vals[start_idx:idx + 1]
        prior_5d_avg[trade_date] = float(mean(window_vals)) if window_vals else 15.0

    return prior_close, prior_5d_avg


def evaluate_vix_trend_combo(combo_dict: dict) -> dict:
    """Evaluate one SNIPER combo with joint VIX filter (VIX>=18 AND VIX>5d_avg)."""
    try:
        from autoresearch import runner as _runner
        from autoresearch.sniper_evaluator import SniperCombo
        from lib.ribbon import compute_ribbon
        from lib.simulator_real import simulate_trade_real
        from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

        spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
        for df in (spy_full, vix_full):
            df["timestamp_et"] = (
                pd.to_datetime(df["timestamp_et"], utc=True)
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )

        all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
        trade_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
        prior_close_map, prior_5d_avg_map = _build_vix_maps(vix_full, trade_dates)

        combo = SniperCombo(**{
            k: combo_dict[k] for k in combo_dict
            if k in SniperCombo.__dataclass_fields__
        })
        params = SniperParams(
            vol_mult=combo.vol_mult,
            body_min_cents=combo.body_min_cents,
            min_stars=combo.min_stars,
            proximity_dollars=combo.proximity_dollars,
            no_trade_before=dt.time(9, 30),
            no_trade_after=dt.time(15, 50),
            require_break_above_open=combo.require_break_above_open,
        )

        by_day: dict[str, float] = {}
        all_trades: list[dict] = []
        opra_missing_count = 0
        skipped_low = 0
        skipped_trend = 0
        day_pnl_map: dict[dt.date, float] = defaultdict(float)
        quarter_pnl_map: dict[str, float] = defaultdict(float)

        for date_et in trade_dates:
            vix_prev = prior_close_map.get(date_et, 15.0)
            vix_5d = prior_5d_avg_map.get(date_et, 15.0)

            # JOINT REGIME GATE: VIX >= 18 AND VIX escalating (above 5d avg)
            if vix_prev < VIX_THRESHOLD:
                skipped_low += 1
                continue
            if vix_prev < vix_5d:
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

            for i in range(len(day_bars)):
                bar_idx = day_offset + i
                bar = combined.iloc[bar_idx]
                signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
                if signal is None:
                    continue
                if signal.direction != "short":
                    continue

                entry_spot = float(signal.entry_price)
                strike = round(entry_spot) + combo.strike_offset

                fill = simulate_trade_real(
                    entry_bar_idx=bar_idx,
                    entry_bar=bar,
                    spy_df=combined,
                    ribbon_df=ribbon_df,
                    rejection_level=signal.level.price,
                    triggers_fired=["sniper_level_break"],
                    side="P",
                    qty=combo.qty,
                    setup="SNIPER_LEVEL_BREAK",
                    levels_active=[L.price for L in levels if L.tier == "Active"],
                    levels_carry=[L.price for L in levels if L.tier == "Carry"],
                    use_tiered_exits=True,
                    strike_override=int(strike),
                    premium_stop_pct=combo.premium_stop_pct,
                    profit_lock_threshold_pct=combo.profit_lock_threshold_pct,
                    profit_lock_stop_offset_pct=combo.profit_lock_stop_offset_pct,
                )

                if fill is None:
                    opra_missing_count += 1
                    break

                trade_rec = {
                    "date": date_et.isoformat(),
                    "side": "P",
                    "strike": int(strike),
                    "dollar_pnl": float(fill.dollar_pnl or 0.0),
                    "exit_reason": str(fill.exit_reason),
                    "entry_premium": float(fill.entry_premium or 0.0),
                    "vix_prev": round(vix_prev, 2),
                    "vix_5d_avg": round(vix_5d, 2),
                }
                all_trades.append(trade_rec)
                day_pnl_map[date_et] += trade_rec["dollar_pnl"]
                q = f"{date_et.year}-Q{(date_et.month - 1) // 3 + 1}"
                quarter_pnl_map[q] += trade_rec["dollar_pnl"]
                by_day[date_et.isoformat()] = round(day_pnl_map[date_et], 2)
                break

        winners_capture = sum(by_day.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = sum(
            -by_day.get(lo["date"], 0.0)
            for lo in J_LOSERS
            if by_day.get(lo["date"], 0.0) < 0
        )
        edge_capture = winners_capture - losers_added

        wide_pnl = round(sum(day_pnl_map.values()), 2)
        wide_n = len(all_trades)
        wide_winners = sum(1 for t in all_trades if t["dollar_pnl"] > 0)
        wide_wr = round(wide_winners / wide_n, 3) if wide_n else 0.0

        sorted_day_pnls = sorted(day_pnl_map.values(), reverse=True)
        top5_sum = sum(sorted_day_pnls[:5])
        top5_pct = round(top5_sum / wide_pnl, 3) if wide_pnl > 0 else 999.0

        positive_quarters = sum(1 for v in quarter_pnl_map.values() if v > 0)
        quarter_count = len(quarter_pnl_map)

        cum = peak = max_dd = 0.0
        for d in sorted(day_pnl_map.keys()):
            cum += day_pnl_map[d]
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        # Floors (VIX-trend universe — ~40 trades, looser floors than baseline)
        regressions: list[str] = []
        if wide_pnl < -600:
            regressions.append(f"wide_pnl ${wide_pnl:.0f} < -$600 floor")
        if wide_n < 10:
            regressions.append(f"wide_n {wide_n} < 10 (too thin)")
        if wide_n > 0 and wide_wr < 0.38:
            regressions.append(f"wide_wr {wide_wr:.3f} < 0.38")
        if positive_quarters < 2:
            regressions.append(f"+q {positive_quarters}/{quarter_count} < 2")
        if edge_capture < -400:
            regressions.append(f"edge_capture ${edge_capture:.0f} < -$400")

        pnl_5_04 = by_day.get("2026-05-04", 0.0)
        if pnl_5_04 < -500:
            regressions.append(f"5/04 ${pnl_5_04:.0f} < -$500 (J winner day)")

        is_ratification_candidate = (
            wide_pnl > 2_000 and wide_wr >= 0.45 and positive_quarters >= 4
        )

        return {
            "combo": combo_dict,
            "vix_threshold": VIX_THRESHOLD,
            "vix_trend_window": VIX_TREND_WINDOW,
            "skipped_low": skipped_low,
            "skipped_trend": skipped_trend,
            "pnl_5_04": pnl_5_04,
            "pnl_5_05": by_day.get("2026-05-05", 0.0),
            "pnl_5_06": by_day.get("2026-05-06", 0.0),
            "pnl_5_07": by_day.get("2026-05-07", 0.0),
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": wide_wr,
            "top5_pct": top5_pct,
            "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl_map.items())},
            "positive_quarters": positive_quarters,
            "quarter_count": quarter_count,
            "max_drawdown": round(max_dd, 2),
            "opra_missing_days": opra_missing_count,
            "is_ratification_candidate": is_ratification_candidate,
            "passed_floors": len(regressions) == 0,
            "regressions": regressions,
            "by_day": by_day,
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
        description="SNIPER VIX-trend real-fills grinder — 432 combos, VIX>=18 AND VIX>5d_avg"
    )
    parser.add_argument("--hours", type=float, default=6.0)
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

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)
    grid = _build_param_grid()
    random.Random(2026).shuffle(grid)

    state: dict = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "vix_threshold": VIX_THRESHOLD,
        "vix_trend_window": VIX_TREND_WINDOW,
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "ratification_candidates": 0,
        "best_wide_pnl": None,
        "best_edge_capture": 0.0,
        "current_pid": os.getpid(),
        "workers": workers,
        "last_update": started.isoformat(),
        "status": "running",
        "mode": "real_fills_vix_trend",
    }
    _write_progress(state)
    logging.info(
        "SNIPER VIX-trend grinder started: %d combos, %d workers, deadline=%s",
        len(grid), workers, deadline,
    )

    completed = 0
    keepers_n = 0
    ratification_n = 0
    best_wide: tuple[float, dict] | None = None

    try:
        with mp.Pool(workers) as pool:
            for result in pool.imap_unordered(evaluate_vix_trend_combo, grid, chunksize=1):
                completed += 1

                if dt.datetime.now() > deadline:
                    logging.info("Deadline reached; terminating pool")
                    state["status"] = "deadline_reached"
                    _write_progress(state)
                    pool.terminate()
                    break

                if result.get("passed_floors"):
                    _append_jsonl(RESULTS, result)
                    state["passed_floors"] += 1

                    wp = result.get("wide_pnl")
                    already_in_keepers = False
                    if wp is not None and (best_wide is None or wp > best_wide[0]):
                        best_wide = (wp, result["combo"])
                        state["best_wide_pnl"] = wp
                        keepers_n += 1
                        state["keepers"] = keepers_n
                        already_in_keepers = True
                        _append_jsonl(KEEPERS, result)
                        logging.info(
                            "KEEPER #%d: pnl=$%.0f edge=$%.0f wr=%.2f +q=%d/%d n=%d ratif=%s",
                            keepers_n, wp, result["edge_capture"],
                            result["wide_wr"],
                            result["positive_quarters"], result["quarter_count"],
                            result["wide_n_trades"],
                            "YES" if result.get("is_ratification_candidate") else "no",
                        )

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
                    if best_wide:
                        state["best_wide_pnl"] = best_wide[0]
                    _write_progress(state)
                    pct = 100 * completed / len(grid)
                    print(
                        f"\r[{pct:5.1f}%] {completed}/{len(grid)} done | "
                        f"best=${state.get('best_wide_pnl', 'n/a')} | "
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
    print(f"\nDone: {completed}/{len(grid)} | ratif={ratification_n} | best=${state.get('best_wide_pnl')}")
    logging.info("Grinder finished: completed=%d ratif=%d status=%s", completed, ratification_n, state["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
