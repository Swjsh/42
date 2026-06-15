"""OPENING_DRIVE_FADE per-combo evaluator.

Walks historical 5m bars day-by-day. Calls the opening_drive_fade
detector each bar. On a signal, simulates the trade through
Black-Scholes premium math until stop / TP1 / runner / time-stop /
profit-lock fires.

Output dict schema matches overnight_grinder.evaluate_combo so it slots
into the existing Stage 1-5 autoresearch pipeline with zero downstream
changes (monitor, scorecard, keepers/rejections JSONL writers all work
unchanged).

Per CLAUDE.md OP 16/19/20 every result row carries:
  - edge_capture (PRIMARY)
  - winners_capture, losers_added
  - top5_pct, quarter_pnl, positive_quarters, max_drawdown
  - passed_floors, regressions

Floors per opening_drive_fade.md spec section 7:
  1. MUST catch 5/11 ATH-fade -> engine_pnl >= $0 on 2026-05-11
  2. MUST skip choppy days (no_drive mornings) -> 0 trades on those
  3. losers_added <= $50
  4. winners_capture >= $150 across J winners (4/29 + 5/01 + 5/04)
  5. edge_capture >= $100

Per OP 11/13: pure Python, no LLM in the loop. Uses pythonw.exe via
multiprocessing.set_executable in the grinder so Pool workers don't
flash console windows.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv  # noqa: E402
from lib.opening_drive_fade_detector import (  # noqa: E402
    OpeningDriveFadeParams,
    OpeningDriveFadeSignal,
    detect_opening_drive_fade,
    reset_state,
)

logger = logging.getLogger(__name__)


# ---------- Anchor trades (per CLAUDE.md OP 16) ----------
# Reused verbatim from sniper_evaluator so floor logic is consistent.

J_WINNERS = [
    {"date": "2026-04-29", "j_pnl": 342, "side": "P", "strike": 710,
     "note": "711.4 rejection + ribbon flip"},
    {"date": "2026-05-01", "j_pnl": 470, "side": "P", "strike": 721,
     "note": "trendline rejection at 13:36"},
    {"date": "2026-05-04", "j_pnl": 730, "side": "P", "strike": 721,
     "note": "premarket level + multi-day trendline + ribbon flip"},
]

J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260, "side": "P", "strike": 722,
     "note": "chop-trap manual entry, no real setup"},
    {"date": "2026-05-06", "j_pnl": -300, "side": "P", "strike": 730,
     "note": "held to zero, no stop"},
    {"date": "2026-05-07", "j_pnl": -45, "side": "C", "strike": 734,
     "note": "engine BULL into pre-FOMC bear sequence"},
    {"date": "2026-05-07", "j_pnl": -120, "side": "C", "strike": 737,
     "note": "manual bullish anticipation at session high"},
]

# 5/11 ATH-fade is the MUST-CATCH per spec section 7 floor #1
ATH_FADE_DATE = "2026-05-11"

# Choppy days where the detector MUST produce zero trades (per spec section 7
# floor #2). Identified by no_drive mornings: 09:35-10:30 range <= $1.00 OR
# no bar in that window with body >= $0.30. We compute this dynamically per
# day rather than hardcoding dates so the floor adapts as data extends.


# ---------- Combo schema ----------

@dataclass(frozen=True)
class OpeningDriveFadeCombo:
    """All knobs for one OPENING_DRIVE_FADE backtest run.

    Detector knobs match spec section 6 grid. Exit knobs locked to
    params.json v14 per spec section 5.
    """

    # --- Detector knobs (drive trigger fire rate) ---
    thrust_bar_min_dollars: float = 0.40
    stall_bars_required: int = 2
    stall_proximity_dollars: float = 0.20
    vol_decline_ratio: float = 0.70
    # time_window_end varies in the grid; start is locked at 09:35
    time_window_end_hour: int = 10
    time_window_end_min: int = 30
    # locked
    time_window_start_hour: int = 9
    time_window_start_min: int = 35
    entry_window_end_hour: int = 11
    entry_window_end_min: int = 0

    # --- Trade construction ---
    strike_offset: int = 2   # ITM-2 per spec section 4
    qty: int = 10            # matches sniper combo default for v14 sizing

    # --- Exit knobs (locked to params.json v14 per spec section 5) ---
    premium_stop_pct: float = -0.08
    tp1_premium_pct: float = 0.30
    tp1_qty_fraction: float = 0.667
    runner_target_pct: float = 1.5

    # --- Profit-lock per J 2026-05-12 rule (spec section 5) ---
    profit_lock_threshold_pct: float = 0.10
    profit_lock_stop_offset_pct: float = 0.05

    # --- All-flat-by-EOD (CLAUDE.md hard rule, params.json#time_stop_et) ---
    time_stop_et_hour: int = 15
    time_stop_et_min: int = 50


# ---------- Trade simulation ----------

@dataclass
class OpeningDriveFadeTrade:
    """Outcome of one opening_drive_fade trade in the backtest."""

    date_et: dt.date
    direction: str
    entry_time_et: dt.datetime
    entry_spot: float
    strike: int
    entry_premium: float
    qty: int
    tp1_qty: int
    runner_qty: int
    exit_premium_tp1: Optional[float]
    exit_premium_runner: Optional[float]
    exit_time_et: dt.datetime
    exit_reason: str
    dollar_pnl: float
    extreme_price: float
    stall_bar_count: int
    vol_ratio_thrust: float
    quality_tier: str


def _strike_for(direction: str, spot: float, offset: int) -> int:
    """ITM-2 strike picker. Mirrors sniper_evaluator._strike_for.

    offset=0 -> ATM
    offset>0 -> ITM (puts: strike higher than spot; calls: lower)
    """
    if direction == "short":  # puts
        return round(spot) + offset
    return round(spot) - offset


def _premium(spot: float, strike: int, vix: float, now_et: dt.datetime, is_call: bool) -> float:
    iv = vix_to_iv(vix)
    tte = time_to_expiry_years(now_et)
    price, _delta = black_scholes(spot, strike, iv, tte, is_call=is_call)
    return float(max(price, 0.01))


def _vix_for(vix_bars: pd.DataFrame, ts: dt.datetime) -> Optional[float]:
    candidates = vix_bars[vix_bars["timestamp_et"] <= ts]
    if candidates.empty:
        return None
    return float(candidates["close"].iloc[-1])


def _simulate_trade(
    signal: OpeningDriveFadeSignal,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    vix_bars: pd.DataFrame,
    combo: OpeningDriveFadeCombo,
) -> Optional[OpeningDriveFadeTrade]:
    """Forward-walk bars from signal to exit. Mirrors sniper_evaluator._simulate_trade."""
    is_call = signal.direction == "long"
    entry_time = signal.timestamp
    entry_spot = float(signal.entry_price)
    strike = _strike_for(signal.direction, entry_spot, combo.strike_offset)

    vix_at_entry = _vix_for(vix_bars, entry_time)
    if vix_at_entry is None:
        return None
    entry_premium = _premium(entry_spot, strike, vix_at_entry, entry_time, is_call)
    if entry_premium < 0.05 or entry_premium > 20.0:
        return None

    tp1_qty = max(1, round(combo.qty * combo.tp1_qty_fraction))
    runner_qty = combo.qty - tp1_qty

    stop_premium = entry_premium * (1.0 + combo.premium_stop_pct)
    tp1_premium = entry_premium * (1.0 + combo.tp1_premium_pct)
    runner_target_premium = entry_premium * (1.0 + combo.runner_target_pct)
    time_stop = dt.time(combo.time_stop_et_hour, combo.time_stop_et_min)

    profit_lock_arm_premium = entry_premium * (1.0 + combo.profit_lock_threshold_pct)
    profit_lock_stop_premium = entry_premium * (1.0 + combo.profit_lock_stop_offset_pct)
    profit_lock_armed = False

    tp1_filled: Optional[float] = None

    for fwd_idx in range(bar_idx + 1, len(spy_bars)):
        fwd = spy_bars.iloc[fwd_idx]
        fwd_time = fwd["timestamp_et"]
        if not hasattr(fwd_time, "date") or fwd_time.date() != entry_time.date():
            break
        fwd_t = fwd_time.time()
        spot_close = float(fwd["close"])

        adverse_spot = float(fwd["high"]) if not is_call else float(fwd["low"])
        favor_spot = float(fwd["low"]) if not is_call else float(fwd["high"])

        vix = _vix_for(vix_bars, fwd_time) or vix_at_entry
        adverse_premium = _premium(adverse_spot, strike, vix, fwd_time, is_call)
        favor_premium = _premium(favor_spot, strike, vix, fwd_time, is_call)

        if not profit_lock_armed and favor_premium >= profit_lock_arm_premium:
            profit_lock_armed = True
            if profit_lock_stop_premium > stop_premium:
                stop_premium = profit_lock_stop_premium

        # Stop fills first (simulator.py convention)
        if adverse_premium <= stop_premium:
            if tp1_filled is not None:
                # Runner stops at breakeven per doctrine
                runner_pnl = (entry_premium - entry_premium) * 100 * runner_qty
                tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
                total_pnl = tp1_pnl + runner_pnl
                exit_reason = "RUNNER_BE_STOP"
                runner_exit = entry_premium
            else:
                total_pnl = (stop_premium - entry_premium) * 100 * combo.qty
                exit_reason = "STOP_ALL"
                runner_exit = stop_premium
            return OpeningDriveFadeTrade(
                date_et=entry_time.date(),
                direction=signal.direction,
                entry_time_et=entry_time,
                entry_spot=entry_spot,
                strike=strike,
                entry_premium=entry_premium,
                qty=combo.qty,
                tp1_qty=tp1_qty,
                runner_qty=runner_qty,
                exit_premium_tp1=tp1_filled,
                exit_premium_runner=runner_exit,
                exit_time_et=fwd_time,
                exit_reason=exit_reason,
                dollar_pnl=round(total_pnl, 2),
                extreme_price=signal.extreme_price,
                stall_bar_count=signal.stall_bar_count,
                vol_ratio_thrust=signal.vol_ratio_thrust,
                quality_tier=signal.quality_tier,
            )

        if tp1_filled is None and favor_premium >= tp1_premium:
            tp1_filled = tp1_premium

        if tp1_filled is not None and favor_premium >= runner_target_premium:
            runner_pnl = (runner_target_premium - entry_premium) * 100 * runner_qty
            tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
            total_pnl = tp1_pnl + runner_pnl
            return OpeningDriveFadeTrade(
                date_et=entry_time.date(),
                direction=signal.direction,
                entry_time_et=entry_time,
                entry_spot=entry_spot,
                strike=strike,
                entry_premium=entry_premium,
                qty=combo.qty,
                tp1_qty=tp1_qty,
                runner_qty=runner_qty,
                exit_premium_tp1=tp1_filled,
                exit_premium_runner=runner_target_premium,
                exit_time_et=fwd_time,
                exit_reason="TP1_THEN_RUNNER_TARGET",
                dollar_pnl=round(total_pnl, 2),
                extreme_price=signal.extreme_price,
                stall_bar_count=signal.stall_bar_count,
                vol_ratio_thrust=signal.vol_ratio_thrust,
                quality_tier=signal.quality_tier,
            )

        if fwd_t >= time_stop:
            close_premium = _premium(spot_close, strike, vix, fwd_time, is_call)
            if tp1_filled is not None:
                tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
                runner_pnl = (close_premium - entry_premium) * 100 * runner_qty
                total_pnl = tp1_pnl + runner_pnl
                exit_reason = "TP1_THEN_TIME_STOP"
            else:
                total_pnl = (close_premium - entry_premium) * 100 * combo.qty
                exit_reason = "TIME_STOP_ALL"
            return OpeningDriveFadeTrade(
                date_et=entry_time.date(),
                direction=signal.direction,
                entry_time_et=entry_time,
                entry_spot=entry_spot,
                strike=strike,
                entry_premium=entry_premium,
                qty=combo.qty,
                tp1_qty=tp1_qty,
                runner_qty=runner_qty,
                exit_premium_tp1=tp1_filled,
                exit_premium_runner=close_premium,
                exit_time_et=fwd_time,
                exit_reason=exit_reason,
                dollar_pnl=round(total_pnl, 2),
                extreme_price=signal.extreme_price,
                stall_bar_count=signal.stall_bar_count,
                vol_ratio_thrust=signal.vol_ratio_thrust,
                quality_tier=signal.quality_tier,
            )

    # End-of-data fallback
    last = spy_bars.iloc[-1]
    last_time = last["timestamp_et"]
    last_spot = float(last["close"])
    last_vix = _vix_for(vix_bars, last_time) or vix_at_entry
    close_premium = _premium(last_spot, strike, last_vix, last_time, is_call)
    if tp1_filled is not None:
        tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
        runner_pnl = (close_premium - entry_premium) * 100 * runner_qty
        total_pnl = tp1_pnl + runner_pnl
        exit_reason = "TP1_THEN_EOD"
    else:
        total_pnl = (close_premium - entry_premium) * 100 * combo.qty
        exit_reason = "EOD_ALL"
    return OpeningDriveFadeTrade(
        date_et=entry_time.date(),
        direction=signal.direction,
        entry_time_et=entry_time,
        entry_spot=entry_spot,
        strike=strike,
        entry_premium=entry_premium,
        qty=combo.qty,
        tp1_qty=tp1_qty,
        runner_qty=runner_qty,
        exit_premium_tp1=tp1_filled,
        exit_premium_runner=close_premium,
        exit_time_et=last_time,
        exit_reason=exit_reason,
        dollar_pnl=round(total_pnl, 2),
        extreme_price=signal.extreme_price,
        stall_bar_count=signal.stall_bar_count,
        vol_ratio_thrust=signal.vol_ratio_thrust,
        quality_tier=signal.quality_tier,
    )


# ---------- Per-day backtest ----------

def _combo_to_params(combo: OpeningDriveFadeCombo) -> OpeningDriveFadeParams:
    return OpeningDriveFadeParams(
        thrust_bar_min_dollars=combo.thrust_bar_min_dollars,
        stall_bars_required=combo.stall_bars_required,
        stall_proximity_dollars=combo.stall_proximity_dollars,
        vol_decline_ratio=combo.vol_decline_ratio,
        time_window_start=dt.time(combo.time_window_start_hour, combo.time_window_start_min),
        time_window_end=dt.time(combo.time_window_end_hour, combo.time_window_end_min),
        entry_window_end=dt.time(combo.entry_window_end_hour, combo.entry_window_end_min),
    )


def _is_chop_day(day_bars: pd.DataFrame, params: OpeningDriveFadeParams) -> bool:
    """Per spec section 7 floor #2: no-drive day = 09:35-10:30 range <= $1.00
    OR no 5m bar in that window with body >= $0.30.
    """
    window = day_bars[
        (day_bars["timestamp_et"].dt.time >= params.time_window_start)
        & (day_bars["timestamp_et"].dt.time <= params.time_window_end)
    ]
    if window.empty:
        return True
    rng = float(window["high"].max()) - float(window["low"].min())
    if rng <= 1.00:
        return True
    has_thrust_body = ((window["close"] - window["open"]).abs() >= 0.30).any()
    if not has_thrust_body:
        return True
    return False


def run_opening_drive_fade_day(
    date_et: dt.date,
    spy_full: pd.DataFrame,
    vix_full: pd.DataFrame,
    combo: OpeningDriveFadeCombo,
) -> tuple[list[OpeningDriveFadeTrade], bool]:
    """Run detector across one trading day's RTH bars. Return (trades, was_chop_day).

    Resets per-day state at start so cross-day stale state never bleeds in.
    """
    params = _combo_to_params(combo)
    date_str = date_et.isoformat()
    reset_state(date_str)

    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    if day_bars.empty:
        return [], False

    is_chop = _is_chop_day(day_bars, params)

    # Build combined frame so bar_idx into `combined` works for forward-walk
    pre_bars = spy_full[spy_full["timestamp_et"] < day_bars["timestamp_et"].iloc[0]].tail(0).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    trades: list[OpeningDriveFadeTrade] = []
    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        bar = combined.iloc[bar_idx]
        signal = detect_opening_drive_fade(bar, bar_idx, combined, params)
        if signal is None:
            continue
        trade = _simulate_trade(signal, bar_idx, combined, vix_full, combo)
        if trade is None:
            continue
        trades.append(trade)
        # One-and-done per day per spec section 2 trigger #6 -- state machine
        # already prevents further fires but we break for clarity + speed.
        break

    return trades, is_chop


# ---------- Public evaluator (matches overnight_grinder schema) ----------

def evaluate_opening_drive_fade_combo(combo_dict: dict) -> dict:
    """Run OPENING_DRIVE_FADE over J anchor days + wide window. Return standard combo result.

    Output schema mirrors overnight_grinder.evaluate_combo so this slots into
    the existing autoresearch pipeline (Stage 2/3/4 grinders, monitor, scorecards).
    """
    try:
        valid_keys = OpeningDriveFadeCombo.__dataclass_fields__
        combo = OpeningDriveFadeCombo(**{k: combo_dict[k] for k in combo_dict if k in valid_keys})
        from autoresearch import runner as _runner

        # ---- J anchor days + ATH-fade day ----
        anchor_dates = sorted({t["date"] for t in J_WINNERS + J_LOSERS} | {ATH_FADE_DATE})
        min_d = dt.date.fromisoformat(min(anchor_dates))
        max_d = dt.date.fromisoformat(max(anchor_dates))
        spy_j, vix_j = _runner.load_data(min_d, max_d)
        spy_j["timestamp_et"] = pd.to_datetime(spy_j["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        vix_j["timestamp_et"] = pd.to_datetime(vix_j["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)

        by_day: dict[str, float] = {}
        chop_day_violations: list[str] = []  # dates where we fired on a chop day

        for d_str in anchor_dates:
            d = dt.date.fromisoformat(d_str)
            trades, is_chop = run_opening_drive_fade_day(d, spy_j, vix_j, combo)
            day_pnl = round(sum(t.dollar_pnl for t in trades), 2)
            by_day[d_str] = day_pnl
            if is_chop and trades:
                chop_day_violations.append(d_str)

        winners_capture = sum(by_day.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = 0.0
        for l in J_LOSERS:
            pnl = by_day.get(l["date"], 0.0)
            if pnl < 0:
                losers_added += -pnl
        edge_capture = winners_capture - losers_added

        pnl_4_29 = by_day.get("2026-04-29", 0.0)
        pnl_5_04 = by_day.get("2026-05-04", 0.0)
        pnl_5_11 = by_day.get(ATH_FADE_DATE, 0.0)

        # ---- Wide window: 2025-01-01 .. 2026-05-22 ----
        wide_start = dt.date(2025, 1, 1)
        wide_end = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22
        spy_w, vix_w = _runner.load_data(wide_start, wide_end)
        spy_w["timestamp_et"] = pd.to_datetime(spy_w["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        vix_w["timestamp_et"] = pd.to_datetime(vix_w["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)

        all_dates = sorted(set(spy_w["timestamp_et"].dt.date.unique()))
        wide_trades: list[OpeningDriveFadeTrade] = []
        day_pnl_map: dict[dt.date, float] = defaultdict(float)
        quarter_pnl_map: dict[str, float] = defaultdict(float)
        wide_chop_violations = 0

        for d in all_dates:
            if d < wide_start or d > wide_end:
                continue
            day_trades, is_chop = run_opening_drive_fade_day(d, spy_w, vix_w, combo)
            wide_trades.extend(day_trades)
            if is_chop and day_trades:
                wide_chop_violations += 1
            day_total = sum(t.dollar_pnl for t in day_trades)
            day_pnl_map[d] += day_total
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarter_pnl_map[q] += day_total

        wide_pnl = round(sum(day_pnl_map.values()), 2)
        wide_n = len(wide_trades)
        wide_winners = sum(1 for t in wide_trades if t.dollar_pnl > 0)
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

        # ---- Floors per spec section 7 ----
        regressions: list[str] = []
        # Floor 1: MUST catch 5/11 ATH-fade with engine_pnl >= $0
        if pnl_5_11 < 0:
            regressions.append(f"5/11 ATH-fade engine_pnl=${pnl_5_11:.0f} < $0 floor")
        # Floor 2: MUST skip chop days
        if chop_day_violations:
            regressions.append(f"fired on chop days: {chop_day_violations}")
        # Floor 3: losers_added <= $50
        if losers_added > 50.0:
            regressions.append(f"losers_added ${losers_added:.0f} > $50 floor")
        # Floor 4: winners_capture >= $150
        if winners_capture < 150.0:
            regressions.append(f"winners_capture ${winners_capture:.0f} < $150 floor")
        # Floor 5: edge_capture >= $100
        if edge_capture < 100.0:
            regressions.append(f"edge_capture ${edge_capture:.0f} < $100 floor")

        return {
            "combo": combo_dict,
            "pnl_4_29": pnl_4_29,
            "pnl_5_04": pnl_5_04,
            "pnl_5_11": pnl_5_11,
            "by_day": by_day,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": wide_wr,
            "wide_chop_violations": wide_chop_violations,
            "top5_pct": top5_pct,
            "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl_map.items()},
            "positive_quarters": positive_quarters,
            "quarter_count": quarter_count,
            "max_drawdown": round(max_dd, 2),
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
