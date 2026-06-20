"""REGIME_SWITCHER pre-pass cache builder.

Per spec markdown/0dte/regime_switcher.md Section 10:
  - The switcher's combo grid (1,296 combos) varies ONLY the regime
    classifier knobs. Sub-strategy internal knobs are locked.
  - So the per-strategy daily P&L is independent of the switcher combo.
  - Pre-compute each strategy's daily P&L over the full backfill ONCE.
  - Then every per-combo eval becomes O(N_days) lookups (~5 seconds).

Output: backtest/autoresearch/_state/regime_switcher_stage1/
  - strategy_pnl_matrix.json   { strategy_id: { "YYYY-MM-DD": pnl } }
  - regime_inputs.json         { "YYYY-MM-DD": {gap_abs, prior_range, vix_spot, vix_change_1d, macro_proximity_hr, is_event_macro} }
  - prepass.log
  - prepass.pid

Wall-clock estimate: ~3.5 hours total (4 strategies x ~50 min each, plus
regime inputs computation ~10 min).

Per CLAUDE.md:
  - OP 11/13: pure Python, no LLM in loop.
  - OP 15: NOT thread-pool; we use sequential single-strategy passes here
    because each evaluator already does its own multiprocessing internally
    via the run_*_day functions (vectorized). Keeping the pre-pass single-
    process avoids the runner._patched_filter_constants thread-safety
    issue documented in OP 15.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "autoresearch" / "_state" / "regime_switcher_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MATRIX_PATH = OUT_DIR / "strategy_pnl_matrix.json"
INPUTS_PATH = OUT_DIR / "regime_inputs.json"
PROGRESS_PATH = OUT_DIR / "prepass_progress.json"
PIDFILE = OUT_DIR / "prepass.pid"
LOGFILE = OUT_DIR / "prepass.log"

MACRO_CAL_PATH = REPO.parent / "automation" / "state" / "macro-calendar.json"

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22

# Locked sub-strategy best-known combos (per spec Section 7).
# These match each strategy's last known good combo as of 2026-05-13.
SNIPER_BEST_COMBO = {
    "vol_mult": 1.3,
    "body_min_cents": 0.05,
    "min_stars": 2,
    "strike_offset": 2,
    "premium_stop_pct": -0.08,
    "tp1_premium_pct": 0.40,
    "runner_target_pct": 1.5,
    "profit_lock_threshold_pct": 0.0,
    "profit_lock_stop_offset_pct": 0.05,
    "tp1_qty_fraction": 0.667,
    "qty": 3,  # paper account binding per spec Section 7
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}

# UPDATED 2026-05-13 evening: GOOD T44b winner combo (3/3 PASS + T44c walk-forward 2.67x)
# + T50b trailing profit-lock kwargs. Calls orchestrator with use_real_fills=True
# (NOT BS sim) — matches production simulator_real.
V14E_BEST_COMBO = {
    "strike_offset_bear": 0,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.50,
    "no_trade_before": "09:35",
    "tp1_premium_pct": 0.30,
    "runner_target_premium_pct": 2.5,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.10,
    "profit_lock_mode": "trailing",
    "profit_lock_trail_pct": 0.20,
}

VWAP_BEST_COMBO = {
    "vol_mult": 1.3,
    "proximity_dollars": 0.10,
    "lookback_bars": 2,
    "body_min_cents": 0.08,
    "require_ribbon_agreement": True,
    "ribbon_min_spread_cents": 30.0,
    "strike_offset": 2,
    "qty": 3,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.30,
    "tp1_qty_fraction": 0.667,
    "runner_target_pct": 1.5,
    "profit_lock_threshold_pct": 0.10,
    "profit_lock_stop_offset_pct": 0.05,
}

ODF_BEST_COMBO: dict[str, Any] = {
    "thrust_bar_min_dollars": 0.40,
    "stall_bars_required": 2,
    "stall_proximity_dollars": 0.20,
    "vol_decline_ratio": 0.70,
    "time_window_end_hour": 10,
    "time_window_end_min": 30,
    "strike_offset": 2,
    "qty": 3,
    "premium_stop_pct": -0.08,
    "tp1_premium_pct": 0.30,
    "tp1_qty_fraction": 0.667,
    "runner_target_pct": 1.5,
    "profit_lock_threshold_pct": 0.10,
    "profit_lock_stop_offset_pct": 0.05,
}


# ---------- Utilities ----------

def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    tmp = PROGRESS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS_PATH)


def _load_data():
    """Load SPY + VIX over the wide window with timezone normalization."""
    from autoresearch import runner as _runner

    spy_df, vix_df = _runner.load_data(WIDE_START, WIDE_END)
    spy_df["timestamp_et"] = (
        pd.to_datetime(spy_df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    vix_df["timestamp_et"] = (
        pd.to_datetime(vix_df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    return spy_df, vix_df


# ---------- Regime input computation (lookahead-safe) ----------

_MACRO_HIGH_TYPES = {
    "fomc_decision",
    "cpi_release",
    "nfp_release",
}


def _load_macro_events() -> list[dict]:
    """Read macro-calendar.json and return high-severity FOMC/CPI/NFP events."""
    if not MACRO_CAL_PATH.exists():
        logging.warning(f"macro-calendar.json missing at {MACRO_CAL_PATH}; macro veto disabled")
        return []
    try:
        cal = json.loads(MACRO_CAL_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning(f"failed to parse macro-calendar.json: {exc}; macro veto disabled")
        return []

    events = []
    for ev in cal.get("events_30d", []):
        if ev.get("severity") == "high" and ev.get("type") in _MACRO_HIGH_TYPES:
            try:
                ev_date = dt.date.fromisoformat(ev["date"])
                ev_time = dt.time.fromisoformat(ev.get("time_et", "08:30"))
                events.append({
                    "date": ev_date,
                    "time_et": ev_time,
                    "type": ev["type"],
                })
            except Exception:
                continue
    # Sort ascending for binary lookup
    events.sort(key=lambda e: (e["date"], e["time_et"]))
    return events


_IS_MACRO_WINDOW_HR = 48.0  # max hours away for is_event_macro=True in prepass output
# BUG FIX 2026-05-16 (FUTURE-IMPROVEMENTS #16 cosmetic): previously is_event_macro was True
# for ALL 338 days because the prepass picked the closest event regardless of distance —
# every calendar day has some FOMC/CPI/NFP within hundreds of hours. The regime classifier
# already applies a separate distance gate (macro_proximity_hr <= knobs.macro_proximity_hr,
# default 24h), so the evaluator was never wrong. But the prepass JSON was misleading.
# Fix: cap is_event_macro=True to events within _IS_MACRO_WINDOW_HR (48h), covering all
# reasonable knob values (default 24h; grinders rarely sweep beyond 48h for this knob).


def _macro_proximity(date_et: dt.date, events: list[dict]) -> tuple[Optional[float], bool]:
    """Compute hours-to-next-or-from-last FOMC/CPI/NFP event.

    Per spec: macro_proximity_hr is the absolute hour distance to the closest
    high-severity event. is_event_macro is True if the closest event is FOMC,
    CPI, or NFP AND within _IS_MACRO_WINDOW_HR hours (48h cap).

    All computed at 09:30 ET of date_et.
    """
    if not events:
        return None, False

    now = dt.datetime.combine(date_et, dt.time(9, 30))
    closest_hr = None
    closest_type = None
    for ev in events:
        ev_dt = dt.datetime.combine(ev["date"], ev["time_et"])
        delta_hr = abs((ev_dt - now).total_seconds()) / 3600.0
        if closest_hr is None or delta_hr < closest_hr:
            closest_hr = delta_hr
            closest_type = ev["type"]

    # is_event_macro: event must be FOMC/CPI/NFP AND within 48h proximity cap.
    # The regime classifier applies a tighter distance check (knobs.macro_proximity_hr,
    # default 24h). This 48h cap just prevents misleading True values for events
    # that are days away and would never trigger MACRO_VETO under any knob setting.
    is_macro = (
        closest_type in _MACRO_HIGH_TYPES
        and closest_hr is not None
        and closest_hr <= _IS_MACRO_WINDOW_HR
    )
    return closest_hr, is_macro


def compute_regime_inputs(
    date_et: dt.date,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    macro_events: list[dict],
) -> Optional[dict[str, Any]]:
    """Compute the 5 lookahead-safe regime inputs for one trading day.

    Returns None if data is insufficient (first day or missing bars).

    All inputs frozen at 09:30:00 ET. Uses prior-session bars + 09:30 quote.
    """
    # Today's bars
    today_bars = spy_df[
        (spy_df["timestamp_et"].dt.date == date_et)
        & (spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    if today_bars.empty:
        return None

    # Today's open = first 09:30 bar's open
    spy_open = float(today_bars.iloc[0]["open"])

    # Prior session's bars (RTH)
    prior_bars = spy_df[
        (spy_df["timestamp_et"].dt.date < date_et)
        & (spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if prior_bars.empty:
        return None

    last_prior_date = prior_bars["timestamp_et"].dt.date.max()
    prior_day_bars = prior_bars[prior_bars["timestamp_et"].dt.date == last_prior_date]
    if prior_day_bars.empty:
        return None

    prior_close = float(prior_day_bars.iloc[-1]["close"])
    prior_high = float(prior_day_bars["high"].max())
    prior_low = float(prior_day_bars["low"].min())

    gap_signed = spy_open - prior_close
    gap_abs = abs(gap_signed)
    prior_range = prior_high - prior_low

    # VIX spot at 09:30:00 ET (use the 09:30 5m bar's close or the latest at-or-before 09:30)
    vix_at_open = vix_df[
        (vix_df["timestamp_et"].dt.date == date_et)
        & (vix_df["timestamp_et"].dt.time >= dt.time(9, 30))
    ]
    if vix_at_open.empty:
        # Fallback: use prior session close
        vix_prior = vix_df[vix_df["timestamp_et"].dt.date < date_et]
        if vix_prior.empty:
            return None
        vix_spot = float(vix_prior.iloc[-1]["close"])
    else:
        vix_spot = float(vix_at_open.iloc[0]["close"])

    # Prior VIX close
    vix_prior_session = vix_df[vix_df["timestamp_et"].dt.date < date_et]
    if vix_prior_session.empty:
        vix_change_1d = 0.0
    else:
        vix_prior_close = float(vix_prior_session.iloc[-1]["close"])
        vix_change_1d = vix_spot - vix_prior_close

    # Macro proximity
    macro_hr, is_macro = _macro_proximity(date_et, macro_events)

    return {
        "gap_abs": round(gap_abs, 4),
        "gap_signed": round(gap_signed, 4),
        "prior_range": round(prior_range, 4),
        "vix_spot": round(vix_spot, 3),
        "vix_change_1d": round(vix_change_1d, 3),
        "macro_proximity_hr": (round(macro_hr, 2) if macro_hr is not None else None),
        "is_event_macro": bool(is_macro),
    }


# ---------- Per-strategy daily P&L (sequential, single-process) ----------

def build_strategy_pnl(
    strategy_id: str,
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    all_dates: list[dt.date],
) -> dict[str, float]:
    """Run one strategy over every day. Return {YYYY-MM-DD: pnl}."""
    pnl_by_day: dict[str, float] = {}

    if strategy_id == "SNIPER":
        from autoresearch.sniper_evaluator import SniperCombo, run_sniper_day

        combo = SniperCombo(**{
            k: SNIPER_BEST_COMBO[k] for k in SNIPER_BEST_COMBO
            if k in SniperCombo.__dataclass_fields__
        })
        for i, d in enumerate(all_dates):
            try:
                trades = run_sniper_day(d, spy_df, vix_df, combo)
                pnl_by_day[d.isoformat()] = round(sum(t.dollar_pnl for t in trades), 2)
            except Exception as exc:
                logging.warning(f"SNIPER {d}: {exc}")
                pnl_by_day[d.isoformat()] = 0.0
            if (i + 1) % 20 == 0:
                logging.info(f"SNIPER progress: {i + 1}/{len(all_dates)}")

    elif strategy_id == "VWAP":
        from autoresearch.vwap_evaluator import VwapCombo, run_vwap_day

        combo = VwapCombo(**{
            k: VWAP_BEST_COMBO[k] for k in VWAP_BEST_COMBO
            if k in VwapCombo.__dataclass_fields__
        })
        for i, d in enumerate(all_dates):
            try:
                trades = run_vwap_day(d, spy_df, vix_df, combo)
                pnl_by_day[d.isoformat()] = round(sum(t.dollar_pnl for t in trades), 2)
            except Exception as exc:
                logging.warning(f"VWAP {d}: {exc}")
                pnl_by_day[d.isoformat()] = 0.0
            if (i + 1) % 20 == 0:
                logging.info(f"VWAP progress: {i + 1}/{len(all_dates)}")

    elif strategy_id == "ODF":
        from autoresearch.opening_drive_fade_evaluator import (
            OpeningDriveFadeCombo,
            run_opening_drive_fade_day,
        )

        combo = OpeningDriveFadeCombo(**{
            k: ODF_BEST_COMBO[k] for k in ODF_BEST_COMBO
            if k in OpeningDriveFadeCombo.__dataclass_fields__
        })
        for i, d in enumerate(all_dates):
            try:
                trades, _ = run_opening_drive_fade_day(d, spy_df, vix_df, combo)
                pnl_by_day[d.isoformat()] = round(sum(t.dollar_pnl for t in trades), 2)
            except Exception as exc:
                logging.warning(f"ODF {d}: {exc}")
                pnl_by_day[d.isoformat()] = 0.0
            if (i + 1) % 20 == 0:
                logging.info(f"ODF progress: {i + 1}/{len(all_dates)}")

    elif strategy_id == "v14_enhanced":
        # UPDATED 2026-05-13 evening: call orchestrator.run_backtest directly with
        # use_real_fills=True. We can't use runner.run_with_params because it doesn't
        # pass through the new T50b kwargs (profit_lock_mode, profit_lock_trail_pct)
        # and hard-codes use_real_fills=False. Per CLAUDE.md OP 20 + T50b: production
        # uses simulator_real (OPRA bars), not BS sim.
        from lib.orchestrator import run_backtest as _run_backtest
        from autoresearch import config as _config

        try:
            kwargs = {
                "start_date": all_dates[0],
                "end_date": all_dates[-1],
                "use_real_fills": True,  # T50b doctrine: real OPRA fills only
                # GOOD T44b winner combo
                "strike_offset_bear": V14E_BEST_COMBO["strike_offset_bear"],
                "premium_stop_pct_bear": V14E_BEST_COMBO["premium_stop_pct_bear"],
                "tp1_qty_fraction": V14E_BEST_COMBO["tp1_qty_fraction"],
                "tp1_premium_pct": V14E_BEST_COMBO["tp1_premium_pct"],
                "runner_target_premium_pct": V14E_BEST_COMBO["runner_target_premium_pct"],
                # T50b trailing profit-lock
                "profit_lock_threshold_pct": V14E_BEST_COMBO["profit_lock_threshold_pct"],
                "profit_lock_stop_offset_pct": V14E_BEST_COMBO["profit_lock_stop_offset_pct"],
                "profit_lock_mode": V14E_BEST_COMBO["profit_lock_mode"],
                "profit_lock_trail_pct": V14E_BEST_COMBO["profit_lock_trail_pct"],
                "no_trade_before": _config.parse_time(V14E_BEST_COMBO["no_trade_before"]),
            }
            res = _run_backtest(spy_df, vix_df, **kwargs)
            bucket: dict[str, float] = defaultdict(float)
            for t in res.trades:
                bucket[t.entry_time_et.date().isoformat()] += t.dollar_pnl
            for d in all_dates:
                pnl_by_day[d.isoformat()] = round(bucket.get(d.isoformat(), 0.0), 2)
            logging.info(f"v14_enhanced REAL-FILLS done: {len(res.trades)} trades, total=${sum(t.dollar_pnl for t in res.trades):.0f}")
        except Exception as exc:
            logging.error(f"v14_enhanced run_backtest failed: {exc}\n{traceback.format_exc()}")
            for d in all_dates:
                pnl_by_day[d.isoformat()] = 0.0

    else:
        raise ValueError(f"unknown strategy_id: {strategy_id}")

    return pnl_by_day


# ---------- Main ----------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategies",
        type=str,
        # 2026-05-13 evening: SNIPER excluded (T42-full real-fills 0/432 keepers).
        # Default rebuilds v14e (with new GOOD T44b combo + trailing T50b kwargs)
        # and re-uses cached VWAP/ODF if present.
        default="v14_enhanced,VWAP,ODF",
        help="Comma-separated subset to recompute. SNIPER is excluded by default.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Discard existing cache and rebuild from scratch.",
    )
    args = parser.parse_args()

    _setup_logging()
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    started = dt.datetime.now()
    logging.info(f"regime_switcher pre-pass started PID={os.getpid()} at {started}")

    state: dict[str, Any] = {
        "started_at": started.isoformat(),
        "current_strategy": None,
        "completed_strategies": [],
        "status": "running",
        "current_pid": os.getpid(),
    }
    _write_progress(state)

    try:
        logging.info(f"loading SPY + VIX data {WIDE_START} .. {WIDE_END}")
        spy_df, vix_df = _load_data()
        all_dates = sorted(set(spy_df["timestamp_et"].dt.date.unique()))
        all_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
        logging.info(f"loaded {len(spy_df)} SPY bars, {len(vix_df)} VIX bars, {len(all_dates)} trading days")

        # Build regime inputs first (cheap, ~10 min)
        if args.reset or not INPUTS_PATH.exists():
            logging.info("computing regime inputs (lookahead-safe; gap, prior_range, vix, macro_proximity)")
            macro_events = _load_macro_events()
            logging.info(f"loaded {len(macro_events)} high-severity macro events")

            regime_inputs: dict[str, Any] = {}
            for i, d in enumerate(all_dates):
                inputs = compute_regime_inputs(d, spy_df, vix_df, macro_events)
                if inputs is not None:
                    regime_inputs[d.isoformat()] = inputs
                if (i + 1) % 50 == 0:
                    logging.info(f"regime_inputs progress: {i + 1}/{len(all_dates)}")
                    state["current_strategy"] = "regime_inputs"
                    state["regime_inputs_completed"] = i + 1
                    state["regime_inputs_total"] = len(all_dates)
                    _write_progress(state)

            INPUTS_PATH.write_text(json.dumps(regime_inputs, indent=2), encoding="utf-8")
            logging.info(f"wrote {len(regime_inputs)} regime input rows to {INPUTS_PATH}")
        else:
            logging.info(f"regime_inputs cache exists at {INPUTS_PATH}; skipping (use --reset to rebuild)")

        # Build per-strategy daily P&L matrix
        if args.reset or not MATRIX_PATH.exists():
            matrix: dict[str, dict[str, float]] = {}
        else:
            matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
            logging.info(f"loaded existing matrix with strategies: {list(matrix.keys())}")

        strategies_to_run = [s.strip() for s in args.strategies.split(",") if s.strip()]

        for strategy_id in strategies_to_run:
            if strategy_id in matrix and not args.reset:
                logging.info(f"{strategy_id} already cached ({len(matrix[strategy_id])} days); skipping")
                state["completed_strategies"].append(strategy_id)
                _write_progress(state)
                continue

            logging.info(f"=== Building daily P&L for {strategy_id} ===")
            state["current_strategy"] = strategy_id
            state["last_update"] = dt.datetime.now().isoformat()
            _write_progress(state)

            t0 = time.time()
            pnl_map = build_strategy_pnl(strategy_id, spy_df, vix_df, all_dates)
            elapsed = time.time() - t0
            logging.info(
                f"{strategy_id} done in {elapsed:.0f}s. "
                f"days={len(pnl_map)} total_pnl={sum(pnl_map.values()):.2f}"
            )

            matrix[strategy_id] = pnl_map
            # Write after each strategy so a crash doesn't lose work
            MATRIX_PATH.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
            state["completed_strategies"].append(strategy_id)
            state["last_update"] = dt.datetime.now().isoformat()
            _write_progress(state)

        state["status"] = "completed"
        state["completed_at"] = dt.datetime.now().isoformat()
        _write_progress(state)

        elapsed_total = (dt.datetime.now() - started).total_seconds()
        logging.info(f"pre-pass complete in {elapsed_total:.0f}s. matrix at {MATRIX_PATH}")
        return 0

    except Exception as exc:
        logging.error(f"pre-pass FAILED: {exc}\n{traceback.format_exc()}")
        state["status"] = "failed"
        state["error"] = repr(exc)
        _write_progress(state)
        return 1

    finally:
        if PIDFILE.exists():
            try:
                PIDFILE.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
