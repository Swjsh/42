"""SNIPER_LEVEL_BREAK per-combo evaluator.

Walks historical 5m bars day-by-day. Calls the sniper detector each bar.
On a signal, simulates the trade through Black-Scholes premium math
(reusing lib.pricing) until stop / TP1 / runner / time-stop fires.

Output dict matches overnight_grinder.evaluate_combo() schema so it slots
into the existing autoresearch pipeline (Stage 1-5 grinders, monitor,
scorecards) with zero downstream changes.

Per CLAUDE.md OP 16/19/20 every result row carries:
  - edge_capture (PRIMARY)
  - winners_capture, losers_added
  - top5_pct, quarter_pnl, positive_quarters, max_drawdown (default OP19)
  - passed_floors, regressions

Per OP 11/13: pure Python, no LLM in the loop. Uses pythonw.exe via
multiprocessing.set_executable so Pool workers don't flash console windows.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv  # noqa: E402
from lib.sniper_detector import (  # noqa: E402
    SniperParams,
    SniperSignal,
    compute_levels,
    detect_sniper_break,
)

logger = logging.getLogger(__name__)


# ---------- Anchor trades (per CLAUDE.md OP 16) ----------

J_WINNERS = [
    {"date": "2026-04-29", "j_pnl": 342, "side": "P", "strike": 710,
     "note": "711.4 rejection + ribbon flip"},
    {"date": "2026-05-01", "j_pnl": 470, "side": "P", "strike": 721,
     "note": "trendline rejection at 13:36 (leg #2 was real trigger)"},
    {"date": "2026-05-04", "j_pnl": 730, "side": "P", "strike": 721,
     "note": "premarket level + multi-day trendline + ribbon flip = CONFLUENCE"},
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

J_TOTAL_WINNERS = sum(t["j_pnl"] for t in J_WINNERS)  # 1542


# ---------- Combo schema ----------

@dataclass(frozen=True)
class SniperCombo:
    """All knobs for one SNIPER backtest run."""

    # Detector knobs (drive trigger fire rate)
    vol_mult: float = 1.5
    body_min_cents: float = 0.10
    min_stars: int = 2
    proximity_dollars: float = 1.50
    require_break_above_open: bool = True

    # Trade construction
    strike_offset: int = 0  # 0 = ATM; +2 = ITM-2 (puts: strike spot+2); -2 = OTM-2
    qty: int = 10  # J's actual size on 2026-05-11 + 2026-05-12 trades

    # Exit knobs
    premium_stop_pct: float = -0.10
    tp1_premium_pct: float = 0.30
    tp1_qty_fraction: float = 0.667
    runner_target_pct: float = 1.5  # +150% premium

    # Profit-lock (J's 2026-05-12 rule): once price hits +X%, stop moves to +Y%
    # so a winning trade can never go negative.
    profit_lock_threshold_pct: float = 0.10  # arm at +10% premium
    profit_lock_stop_offset_pct: float = 0.05  # set stop to entry + 5% (lock $5+ on each contract)

    # All-flat-by-EOD per CLAUDE.md hard rule
    time_stop_et_hour: int = 15
    time_stop_et_min: int = 50


# ---------- Trade simulation ----------

@dataclass
class SniperTrade:
    """Outcome of one sniper trade in the backtest."""

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
    level_label: str
    level_price: float
    vol_ratio: float
    body_dollars: float


def _strike_for(direction: str, spot: float, offset: int) -> int:
    """Compute strike given direction and offset.

    offset=0 → ATM (strike = round(spot))
    offset>0 → ITM (puts: strike higher than spot; calls: strike lower)
    offset<0 → OTM (puts: strike lower than spot; calls: strike higher)
    """
    if direction == "short":  # buying puts
        return round(spot) + offset
    else:  # buying calls
        return round(spot) - offset


def _premium(spot: float, strike: int, vix: float, now_et: dt.datetime, is_call: bool) -> float:
    """Black-Scholes premium for a fixed-strike option."""
    iv = vix_to_iv(vix)
    tte = time_to_expiry_years(now_et)
    price, _delta = black_scholes(spot, strike, iv, tte, is_call=is_call)
    return float(max(price, 0.01))  # broker-floor at $0.01


def _simulate_trade(
    signal: SniperSignal,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    vix_bars: pd.DataFrame,
    combo: SniperCombo,
) -> Optional[SniperTrade]:
    """Forward-walk bars from signal to exit. Apply stop / TP1 / runner / time-stop."""
    is_call = signal.direction == "long"
    entry_time = signal.bar_timestamp_et
    entry_spot = float(signal.entry_price)
    strike = _strike_for(signal.direction, entry_spot, combo.strike_offset)

    # Entry vix
    vix_at_entry = _vix_for(vix_bars, entry_time)
    if vix_at_entry is None:
        return None
    entry_premium = _premium(entry_spot, strike, vix_at_entry, entry_time, is_call)

    # Skip absurd premiums (data anomalies)
    if entry_premium < 0.05 or entry_premium > 20.0:
        return None

    # Position split
    tp1_qty = max(1, round(combo.qty * combo.tp1_qty_fraction))
    runner_qty = combo.qty - tp1_qty

    stop_premium = entry_premium * (1.0 + combo.premium_stop_pct)
    tp1_premium = entry_premium * (1.0 + combo.tp1_premium_pct)
    runner_target_premium = entry_premium * (1.0 + combo.runner_target_pct)
    time_stop = dt.time(combo.time_stop_et_hour, combo.time_stop_et_min)

    # Profit-lock per J 2026-05-12: once favor_premium hits entry+threshold,
    # raise the stop to entry+offset so a winning trade never goes negative.
    profit_lock_arm_premium = entry_premium * (1.0 + combo.profit_lock_threshold_pct)
    profit_lock_stop_premium = entry_premium * (1.0 + combo.profit_lock_stop_offset_pct)
    profit_lock_armed = False

    tp1_filled: Optional[float] = None
    tp1_filled_at: Optional[dt.datetime] = None

    # Walk forward bar-by-bar
    for fwd_idx in range(bar_idx + 1, len(spy_bars)):
        fwd = spy_bars.iloc[fwd_idx]
        fwd_time = fwd["timestamp_et"]
        if not hasattr(fwd_time, "date") or fwd_time.date() != entry_time.date():
            # Crossed midnight without exit (shouldn't happen) -> close at last-known
            break

        fwd_t = fwd_time.time()
        spot_close = float(fwd["close"])

        # Use bar's adverse-move spot to test stop (puts: bar.high adverse; calls: bar.low adverse)
        adverse_spot = float(fwd["high"]) if not is_call else float(fwd["low"])
        favor_spot = float(fwd["low"]) if not is_call else float(fwd["high"])

        vix = _vix_for(vix_bars, fwd_time) or vix_at_entry
        adverse_premium = _premium(adverse_spot, strike, vix, fwd_time, is_call)
        favor_premium = _premium(favor_spot, strike, vix, fwd_time, is_call)

        # Arm profit-lock if favor side hit the threshold this bar
        if not profit_lock_armed and favor_premium >= profit_lock_arm_premium:
            profit_lock_armed = True
            # Raise the stop floor to lock profit; never lowers below original stop
            if profit_lock_stop_premium > stop_premium:
                stop_premium = profit_lock_stop_premium

        # Stop fills first if both touched in same bar (per simulator.py convention)
        if adverse_premium <= stop_premium:
            # Stop on whatever's left (could be tp1_qty + runner_qty, or just runner_qty if TP1 already filled)
            remaining = (0 if tp1_filled is not None else tp1_qty) + runner_qty
            stop_pnl = (stop_premium - entry_premium) * 100 * remaining
            # If TP1 filled earlier, runner stop is at break-even per doctrine
            if tp1_filled is not None:
                # Runner stops at breakeven (entry_premium)
                runner_pnl = (entry_premium - entry_premium) * 100 * runner_qty
                tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
                total_pnl = tp1_pnl + runner_pnl
                exit_reason = "RUNNER_BE_STOP"
                runner_exit = entry_premium
            else:
                total_pnl = stop_pnl
                exit_reason = "STOP_ALL"
                runner_exit = stop_premium
            return SniperTrade(
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
                level_label=signal.level.label,
                level_price=signal.level.price,
                vol_ratio=signal.vol_ratio,
                body_dollars=signal.body_dollars,
            )

        # TP1 fills if favorable touched the target and TP1 not yet filled
        if tp1_filled is None and favor_premium >= tp1_premium:
            tp1_filled = tp1_premium
            tp1_filled_at = fwd_time
            # Don't exit; runner continues

        # Runner target fills?
        if tp1_filled is not None and favor_premium >= runner_target_premium:
            runner_pnl = (runner_target_premium - entry_premium) * 100 * runner_qty
            tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
            total_pnl = tp1_pnl + runner_pnl
            return SniperTrade(
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
                level_label=signal.level.label,
                level_price=signal.level.price,
                vol_ratio=signal.vol_ratio,
                body_dollars=signal.body_dollars,
            )

        # Time stop?
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
            return SniperTrade(
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
                level_label=signal.level.label,
                level_price=signal.level.price,
                vol_ratio=signal.vol_ratio,
                body_dollars=signal.body_dollars,
            )

    # End of data: close at last bar
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
    return SniperTrade(
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
        level_label=signal.level.label,
        level_price=signal.level.price,
        vol_ratio=signal.vol_ratio,
        body_dollars=signal.body_dollars,
    )


def _vix_for(vix_bars: pd.DataFrame, ts: dt.datetime) -> Optional[float]:
    """Look up VIX close at-or-before ts. Returns None if no data covers."""
    candidates = vix_bars[vix_bars["timestamp_et"] <= ts]
    if candidates.empty:
        return None
    return float(candidates["close"].iloc[-1])


# ---------- Per-day backtest ----------

def _signal_to_params(combo: SniperCombo) -> SniperParams:
    """Map combo to detector params. Time gate fixed at 09:30-15:50 per J 2026-05-12."""
    return SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=combo.require_break_above_open,
    )


def run_sniper_day(
    date_et: dt.date,
    spy_full: pd.DataFrame,
    vix_full: pd.DataFrame,
    combo: SniperCombo,
    max_trades_per_day: int = 1,
) -> list[SniperTrade]:
    """Run sniper detector across one trading day's RTH bars. Return trades."""
    params = _signal_to_params(combo)

    # Day's RTH bars + the prior history needed for level calc + vol baseline
    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    if day_bars.empty:
        return []

    # Compute levels once (using all history before the day)
    first_ts = day_bars["timestamp_et"].iloc[0]
    levels = compute_levels(spy_full, first_ts, params)
    if not levels:
        return []

    trades: list[SniperTrade] = []

    # Build a frame with at least 20 prior bars before the day for vol baseline
    pre_bars = spy_full[
        spy_full["timestamp_et"] < first_ts
    ].tail(40).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        bar = combined.iloc[bar_idx]
        signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
        if signal is None:
            continue

        trade = _simulate_trade(signal, bar_idx, combined, vix_full, combo)
        if trade is None:
            continue
        trades.append(trade)

        if len(trades) >= max_trades_per_day:
            break

    return trades


# ---------- Public evaluator (matches overnight_grinder schema) ----------

def evaluate_sniper_combo(combo_dict: dict) -> dict:
    """Run SNIPER over J anchor days + wide window. Return standard combo result.

    Output schema mirrors overnight_grinder.evaluate_combo so this slots into the
    existing autoresearch pipeline (Stage 2/3/4 grinders, monitor, scorecards).
    """
    try:
        combo = SniperCombo(**{k: combo_dict[k] for k in combo_dict if k in SniperCombo.__dataclass_fields__})
        from autoresearch import runner as _runner

        # ---- J anchor days ----
        min_d = dt.date.fromisoformat(min(t["date"] for t in J_WINNERS + J_LOSERS))
        max_d = dt.date.fromisoformat(max(t["date"] for t in J_WINNERS + J_LOSERS))
        spy_j, vix_j = _runner.load_data(min_d, max_d)
        spy_j["timestamp_et"] = pd.to_datetime(spy_j["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        vix_j["timestamp_et"] = pd.to_datetime(vix_j["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)

        by_day: dict[str, float] = {}
        all_anchor_trades: list[SniperTrade] = []
        for w in J_WINNERS + J_LOSERS:
            d = dt.date.fromisoformat(w["date"])
            trades = run_sniper_day(d, spy_j, vix_j, combo)
            day_pnl = round(sum(t.dollar_pnl for t in trades), 2)
            key = w["date"]
            if key in by_day:
                by_day[key + "_2"] = day_pnl
            else:
                by_day[key] = day_pnl
            all_anchor_trades.extend(trades)

        winners_capture = sum(by_day.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = 0.0
        for l in J_LOSERS:
            pnl = by_day.get(l["date"], 0.0)
            if pnl < 0:
                losers_added += -pnl
        edge_capture = winners_capture - losers_added

        pnl_4_29 = by_day.get("2026-04-29", 0.0)
        pnl_5_04 = by_day.get("2026-05-04", 0.0)

        # ---- Wide window: 2025-01-01 .. 2026-05-07 ----
        wide_start = dt.date(2025, 1, 1)
        wide_end = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22
        spy_w, vix_w = _runner.load_data(wide_start, wide_end)
        spy_w["timestamp_et"] = pd.to_datetime(spy_w["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        vix_w["timestamp_et"] = pd.to_datetime(vix_w["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)

        all_dates = sorted(set(spy_w["timestamp_et"].dt.date.unique()))
        wide_trades: list[SniperTrade] = []
        day_pnl_map: dict[dt.date, float] = defaultdict(float)
        quarter_pnl_map: dict[str, float] = defaultdict(float)

        for d in all_dates:
            if d < wide_start or d > wide_end:
                continue
            day_trades = run_sniper_day(d, spy_w, vix_w, combo)
            wide_trades.extend(day_trades)
            day_total = sum(t.dollar_pnl for t in day_trades)
            day_pnl_map[d] += day_total
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarter_pnl_map[q] += day_total

        wide_pnl = round(sum(day_pnl_map.values()), 2)
        wide_n = len(wide_trades)
        wide_winners = sum(1 for t in wide_trades if t.dollar_pnl > 0)
        wide_wr = round(wide_winners / wide_n, 3) if wide_n else 0.0

        # OP19 default metrics
        sorted_day_pnls = sorted(day_pnl_map.values(), reverse=True)
        top5_sum = sum(sorted_day_pnls[:5])
        top5_pct = round(top5_sum / wide_pnl, 3) if wide_pnl > 0 else 999.0
        positive_quarters = sum(1 for v in quarter_pnl_map.values() if v > 0)
        quarter_count = len(quarter_pnl_map)

        # Sequential drawdown
        cum = peak = max_dd = 0.0
        for d in sorted(day_pnl_map.keys()):
            cum += day_pnl_map[d]
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        # ---- Floors ----
        regressions = []
        # SNIPER floor: must NOT lose money on J's losing days; must win SOMETHING on J's winning days
        if pnl_4_29 < 0:
            regressions.append(f"4/29 ${pnl_4_29:.0f} negative on J winning day")
        if pnl_5_04 < 0:
            regressions.append(f"5/04 ${pnl_5_04:.0f} negative on J winning day")
        if losers_added > 100:
            regressions.append(f"losers_added ${losers_added:.0f} > $100 floor")
        if winners_capture < 200:
            # Must capture at least $200 of winning-day P&L (cap at 13% of J's $1542)
            regressions.append(f"winners_capture ${winners_capture:.0f} < $200 floor")

        return {
            "combo": combo_dict,
            "pnl_4_29": pnl_4_29,
            "pnl_5_04": pnl_5_04,
            "by_day": by_day,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": wide_wr,
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
