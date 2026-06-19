"""SNIPER_LEVEL_BREAK VIX>=18 Stage 1 grinder — real fills + VIX regime pre-filter.

WHY:
  Plain SNIPER real-fills grinder found best combo at wide_pnl = -$90.8
  (150 trades, 50% WR, 2/6 +quarters).  Dead on aggregate.

  VIX regime filter test (_sniper_vix_regime_filter.py, 2026-05-23) showed that
  applying a VIX>=18 gate on the SAME best combo gives:
    wide_pnl = +$1,472  (70 trades, 54.3% WR, 3/5 +quarters)
  Passes WR gate but fails P&L gate ($2,000) and +quarters gate (4/6).

  Hypothesis: the unfiltered grinder's best combo is NOT the best combo when the
  regime filter is applied.  A wider stop (-0.20 to -0.25) or different profit-lock
  may clear the $2,000 P&L gate inside the VIX>=18 universe.

WHAT:
  Same 432-combo grid as sniper_real_fills_grinder.py:
    locked: vol_mult=1.1, body_min_cents=0.02, min_stars=2, qty=10,
            proximity_dollars=1.5, require_break_above_open=True, tp1_qty_fraction=0.5
    sweep:  strike_offset {1,2,3}
            × premium_stop_pct {-0.10,-0.15,-0.20,-0.25}
            × profit_lock_threshold_pct {0.0, 0.05, 0.10}
            × profit_lock_stop_offset_pct {0.05, 0.08}
            × tp1_premium_pct {0.30, 0.40, 0.50}
            × runner_target_pct {1.25, 2.0}
    Total: 3 × 4 × 3 × 2 × 3 × 2 = 432 combos.

  VIX gate: skip any trade date where prior_day_VIX_close < VIX_THRESHOLD (18).
  This eliminates the choppy 2025-Q2 / 2025-Q3 environment and keeps only
  genuinely trending / high-volatility days where level-break follow-through occurs.

RATIFICATION GATES (all 3 required for a combo to be RATIFICATION_READY):
  wide_pnl  > $2,000
  WR        >= 45%
  positive_quarters >= 4/6

OUTPUT (under autoresearch/_state/sniper_vix18_stage1/):
  progress.json        live progress meter (atomic write every 5 combos)
  results.jsonl        every combo that passed floors
  rejections.jsonl     every combo that failed floors
  keepers.jsonl        combos that set a new best wide_pnl
  runner.pid           current process PID
  grinder.log          structured log

CLI:
  python.exe -m autoresearch.sniper_vix18_grinder --hours 8 --workers 4
  python.exe -m autoresearch.sniper_vix18_grinder --reset --hours 8 --workers 4

CLAUDE.md compliance:
  - OP 16: edge_capture is PRIMARY; aggregate is secondary tiebreaker
  - OP 19: every result row carries top5_pct, quarter_pnl, positive_quarters,
    max_drawdown by default
  - OP 20: real fills (not BS); concentration disclosure (top5_pct);
    VIX threshold documented as survival-selection caveat
  - OP 25: atomic progress writes, silent-failure prevention, all foot-guns noted
  - Grinder NEVER modifies heartbeat.md / params*.json / CLAUDE.md (Rule 9)
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

import pandas as pd

# ── Win32: spawn workers from the real Python313 executable, not the venv stub ──
# (L41 / L72 foot-gun: venv pythonw.exe re-execs as console python.exe)
if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# ── Constants ─────────────────────────────────────────────────────────────────

VIX_THRESHOLD: int = 18  # skip day if prior_day_VIX_close < this value

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

OUT_DIR = REPO / "autoresearch" / "_state" / "sniper_vix18_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

# ── J anchors (mirrors sniper_real_fills_grinder.py — bearish only) ───────────
# 5/04 only: confirmed SNIPER setup (level break that holds, J +$730).
# 4/29 excluded: J's profit came from riding full-day open→close trend, not from
# a level-break signal.  SNIPER fires at 12:30 on a false breakout on 4/29.
J_WINNERS = [
    {"date": "2026-05-04", "j_pnl": 730},
]
J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260},
    {"date": "2026-05-06", "j_pnl": -300},
    {"date": "2026-05-07", "j_pnl": -165},  # -$45 + -$120 combined
]


# ── Utilities ──────────────────────────────────────────────────────────────────


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    """Atomic JSON progress write (tmp → rename to avoid torn reads)."""
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


# ── Param grid (same 432 combos as sniper_real_fills_grinder) ─────────────────


def _build_param_grid() -> list[dict]:
    """Return the 432-combo SNIPER real-fills parameter grid.

    Locked: vol_mult=1.1, body_min_cents=0.02 (sniper-v1 winners).
    Locked: min_stars=2, qty=10, proximity_dollars=1.5,
            require_break_above_open=True, tp1_qty_fraction=0.5.
    Sweep dimensions (wider-stop + profit-lock frontier):
      strike_offset:             {1, 2, 3}
      premium_stop_pct:          {-0.10, -0.15, -0.20, -0.25}
      profit_lock_threshold_pct: {0.0,  0.05,  0.10}
      profit_lock_stop_offset:   {0.05, 0.08}
      tp1_premium_pct:           {0.30, 0.40, 0.50}
      runner_target_pct:         {1.25, 2.0}
    """
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


# ── VIX prior-close map ───────────────────────────────────────────────────────


def _build_vix_prev_map(
    vix_df: pd.DataFrame,
    trade_dates: list[dt.date],
) -> dict[dt.date, float]:
    """Return {trade_date: prior_day_vix_close} for all trade dates.

    Uses the last VIX bar of each calendar day as that day's closing value.
    Falls back to 15.0 (below any tested threshold) if no prior VIX history.
    O(n log n) via bisect — fast even on 350-day lookups.
    """
    vix_by_date: dict[dt.date, float] = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())

    result: dict[dt.date, float] = {}
    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        result[trade_date] = float(vix_by_date[sorted_vix_days[idx]]) if idx >= 0 else 15.0
    return result


# ── Per-combo evaluator (multiprocess-safe top-level fn) ──────────────────────


def evaluate_vix18_combo(combo_dict: dict) -> dict:
    """Evaluate one SNIPER combo across the wide window with VIX>=18 pre-filter.

    Skips any trade date where prior_day_VIX_close < VIX_THRESHOLD.
    Uses real OPRA fills via simulate_trade_real.
    Returns a result dict matching the sniper_real_fills_grinder schema so
    downstream tooling (Stage 2/3/4, monitor, scorecards) works unchanged.
    """
    try:
        from autoresearch import runner as _runner
        from autoresearch.sniper_evaluator import SniperCombo
        from lib.ribbon import compute_ribbon
        from lib.simulator_real import simulate_trade_real
        from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

        # ── Load + normalize timestamps (OP-25 foot-gun: pandas MultiIndex + tz) ──
        spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
        for df in (spy_full, vix_full):
            df["timestamp_et"] = (
                pd.to_datetime(df["timestamp_et"], utc=True)
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )

        # ── Build VIX prior-close map for regime filter ──
        all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
        trade_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
        vix_prev_map = _build_vix_prev_map(vix_full, trade_dates)

        # ── Build SNIPER combo + detector params ──
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

        # ── Per-date loop ──
        by_day: dict[str, float] = {}
        all_trades: list[dict] = []
        opra_missing_count = 0
        skipped_days = 0
        day_pnl_map: dict[dt.date, float] = defaultdict(float)
        quarter_pnl_map: dict[str, float] = defaultdict(float)

        for date_et in trade_dates:
            # VIX REGIME GATE
            vix_prev = vix_prev_map.get(date_et, 15.0)
            if vix_prev < VIX_THRESHOLD:
                skipped_days += 1
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
                # Scope lock: BEARISH only (BULLISH_RECLAIM stays DRAFT per OP-16)
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
                    break  # one attempt per day

                trade_rec = {
                    "date": date_et.isoformat(),
                    "side": "P",
                    "strike": int(strike),
                    "dollar_pnl": float(fill.dollar_pnl or 0.0),
                    "exit_reason": str(fill.exit_reason),
                    "entry_premium": float(fill.entry_premium or 0.0),
                    "vix_prev": round(vix_prev, 2),
                }
                all_trades.append(trade_rec)
                day_pnl_map[date_et] += trade_rec["dollar_pnl"]
                q = f"{date_et.year}-Q{(date_et.month - 1) // 3 + 1}"
                quarter_pnl_map[q] += trade_rec["dollar_pnl"]
                by_day[date_et.isoformat()] = round(day_pnl_map[date_et], 2)
                break  # one trade per day

        # ── J anchor metrics (OP-16: edge_capture is PRIMARY) ──
        winners_capture = sum(by_day.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = 0.0
        for loser in J_LOSERS:
            pnl = by_day.get(loser["date"], 0.0)
            if pnl < 0:
                losers_added += -pnl
        edge_capture = winners_capture - losers_added

        # ── Wide window aggregate metrics ──
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

        # ── Floor checks (VIX-filtered universe) ──
        # With VIX>=18 we expect ~70 qualifying trades (down from 150).
        # Known baseline (best unfiltered combo with VIX>=18 applied post-hoc):
        #   wide_pnl = $1,472 / WR = 54.3% / +q = 3/5
        # Floors: reject clearly broken combos, keep anything with positive signal.
        regressions: list[str] = []
        if wide_pnl < -800:
            regressions.append(f"wide_pnl ${wide_pnl:.0f} < -$800 floor")
        if wide_n < 15:
            regressions.append(f"wide_n {wide_n} < 15 (too thin to evaluate)")
        if wide_n > 0 and wide_wr < 0.38:
            regressions.append(f"wide_wr {wide_wr:.3f} < 0.38 floor")
        if positive_quarters < 2:
            regressions.append(
                f"positive_quarters {positive_quarters}/{quarter_count} < 2 floor"
            )
        if edge_capture < -400:
            regressions.append(f"edge_capture ${edge_capture:.0f} < -$400 floor")

        # 5/04 is a confirmed SNIPER setup in high-VIX (VIX was ~25 that day)
        pnl_5_04 = by_day.get("2026-05-04", 0.0)
        if pnl_5_04 < -500:
            regressions.append(
                f"5/04 ${pnl_5_04:.0f} < -$500 floor (J winning day, confirmed SNIPER)"
            )

        # ── Ratification assessment ──
        is_ratification_candidate = (
            wide_pnl > 2_000
            and wide_wr >= 0.45
            and positive_quarters >= 4
        )

        return {
            "combo": combo_dict,
            "vix_threshold": VIX_THRESHOLD,
            "skipped_days": skipped_days,
            # J anchors
            "pnl_5_04": pnl_5_04,
            "pnl_5_05": by_day.get("2026-05-05", 0.0),
            "pnl_5_06": by_day.get("2026-05-06", 0.0),
            "pnl_5_07": by_day.get("2026-05-07", 0.0),
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            # Wide window
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": wide_wr,
            "top5_pct": top5_pct,
            "quarter_pnl": {k: round(v, 2) for k, v in sorted(quarter_pnl_map.items())},
            "positive_quarters": positive_quarters,
            "quarter_count": quarter_count,
            "max_drawdown": round(max_dd, 2),
            "opra_missing_days": opra_missing_count,
            # Ratification
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


# ── Main pool driver ───────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SNIPER VIX>=18 real-fills grinder — 432 combos with regime pre-filter"
    )
    parser.add_argument("--hours", type=float, default=6.0,
                        help="Run for N hours then stop gracefully (default: 6)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers, cap=4 per CLAUDE.md OP-15 (default: 4)")
    parser.add_argument("--reset", action="store_true",
                        help="Delete prior run files before starting")
    args = parser.parse_args()

    workers = min(args.workers, 4)
    if args.reset:
        # Reset BEFORE _setup_logging so LOGFILE isn't locked (L72 foot-gun)
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
        "mode": "real_fills_vix18",
    }
    _write_progress(state)
    logging.info(
        "SNIPER VIX>=%d grinder started: %d combos, %d workers, deadline=%s",
        VIX_THRESHOLD, len(grid), workers, deadline,
    )

    completed = 0
    keepers_n = 0
    ratification_n = 0
    best_wide: tuple[float, dict] | None = None

    try:
        with mp.Pool(workers) as pool:
            for result in pool.imap_unordered(evaluate_vix18_combo, grid, chunksize=1):
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
                            "KEEPER #%d: pnl=$%.0f edge=$%.0f wr=%.2f "
                            "+q=%d/%d n=%d ratif=%s combo=%s",
                            keepers_n, wp, result["edge_capture"],
                            result["wide_wr"],
                            result["positive_quarters"], result["quarter_count"],
                            result["wide_n_trades"],
                            "YES" if result.get("is_ratification_candidate") else "no",
                            result["combo"],
                        )

                    if result.get("is_ratification_candidate"):
                        ratification_n += 1
                        state["ratification_candidates"] = ratification_n
                        if not already_in_keepers:
                            # Log non-best ratification candidates separately
                            _append_jsonl(KEEPERS, result)
                        logging.info(
                            "RATIFICATION CANDIDATE: pnl=$%.0f wr=%.2f +q=%d/%d "
                            "n=%d skip=%d combo=%s",
                            result["wide_pnl"], result["wide_wr"],
                            result["positive_quarters"], result["quarter_count"],
                            result["wide_n_trades"], result.get("skipped_days", 0),
                            result["combo"],
                        )

                    ec = result.get("edge_capture", 0.0)
                    if ec > state["best_edge_capture"]:
                        state["best_edge_capture"] = ec

                else:
                    _append_jsonl(REJECTIONS, result)
                    state["rejected"] += 1

                state["completed"] = completed
                state["last_update"] = dt.datetime.now().isoformat()
                if completed % 5 == 0:
                    _write_progress(state)
                    logging.info(
                        "progress: %d/%d passed=%d keepers=%d ratif=%d best_pnl=%s",
                        completed, len(grid),
                        state["passed_floors"], keepers_n, ratification_n,
                        state.get("best_wide_pnl"),
                    )

    except Exception:
        # OP-25 silent-failure prevention: never die quietly
        logging.exception("FATAL: parent pool loop crashed")
        state["status"] = "crashed"
        state["completed"] = completed
        state["last_update"] = dt.datetime.now().isoformat()
        _write_progress(state)
        if PIDFILE.exists():
            PIDFILE.unlink()
        return 2

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)
    if PIDFILE.exists():
        PIDFILE.unlink()

    summary = (
        f"SNIPER VIX>={VIX_THRESHOLD} grinder done: "
        f"{completed}/{len(grid)} combos, "
        f"passed={state['passed_floors']}, "
        f"keepers={keepers_n}, "
        f"ratification_candidates={ratification_n}"
    )
    if best_wide:
        summary += f", best_wide_pnl=${best_wide[0]:.0f}"
    logging.info(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
