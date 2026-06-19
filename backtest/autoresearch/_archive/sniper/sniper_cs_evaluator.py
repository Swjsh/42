"""SNIPER_LEVEL_BREAK chart-stop evaluator (CS variant).

Same signal detection as sniper_evaluator.py (vol-spike level break via
sniper_detector.py).  Exit mechanics replace premium-% stops with SPY-price
chart stops (per CLAUDE.md L100 + L51/L55 root-cause fix):

  BEAR entry (puts):
    chart_stop_spy  = level_price + chart_stop_buffer   (adverse: spy goes UP)
    risk_spy        = chart_stop_spy - entry_spot        (> 0)
    tp1_spy_target  = entry_spot - risk_spy * tp1_r
    runner_spy_target = entry_spot - risk_spy * runner_r

  BULL entry (calls):
    chart_stop_spy  = level_price - chart_stop_buffer   (adverse: spy goes DOWN)
    risk_spy        = entry_spot - chart_stop_spy        (> 0)
    tp1_spy_target  = entry_spot + risk_spy * tp1_r
    runner_spy_target = entry_spot + risk_spy * runner_r

Premium at each SPY-price exit is computed via Black-Scholes so P&L is option
dollars, not SPY dollars.  This separates signal quality from premium-stop
misfire (L51/L55: VIX spike inflates premium at entry, shrinks stop budget).

Per L100: all premium-exit SNIPER variants are ARTIFACT-INVALIDATED.
This is the only remaining unvalidated design path.
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
class SniperCSCombo:
    """All knobs for one chart-stop SNIPER backtest run."""

    # Detector knobs (same as SniperCombo)
    vol_mult: float = 1.5
    body_min_cents: float = 0.10
    min_stars: int = 2
    proximity_dollars: float = 1.50
    require_break_above_open: bool = True

    # Trade construction
    strike_offset: int = 0   # 0=ATM; +2=ITM-2
    qty: int = 10
    tp1_qty_fraction: float = 0.667

    # Chart-stop knobs (replaces premium_stop_pct entirely)
    chart_stop_buffer: float = 0.50  # SPY points beyond level (L51/L55 fix)
    tp1_r: float = 2.0               # TP1 at risk × tp1_r SPY points favorable
    runner_r: float = 3.0            # Runner at risk × runner_r SPY points favorable

    # VIX regime filter (L73: VIX character matters for level-break setups)
    # 0.0 = no filter (original behavior); 15.0 or 18.0 = minimum VIX at entry
    vix_min: float = 0.0
    # True = require prior_day_VIX > prior_5d_avg_VIX (VIX escalating regime, L73 OOS-confirmed)
    vix_trending: bool = False

    # All-flat-by-EOD (hard rule)
    time_stop_et_hour: int = 15
    time_stop_et_min: int = 50


# ---------- Trade result ----------

@dataclass
class SniperTrade:
    """Outcome of one chart-stop SNIPER trade."""

    date_et: dt.date
    direction: str
    entry_time_et: dt.datetime
    entry_spot: float
    strike: int
    entry_premium: float
    qty: int
    tp1_qty: int
    runner_qty: int
    chart_stop_spy: float        # the SPY-price hard stop used
    risk_spy: float              # SPY distance to chart stop at entry
    exit_premium_tp1: Optional[float]
    exit_premium_runner: Optional[float]
    exit_time_et: dt.datetime
    exit_reason: str
    dollar_pnl: float
    level_label: str
    level_price: float
    vol_ratio: float
    body_dollars: float


# ---------- Pricing helpers (identical to sniper_evaluator.py) ----------

def _strike_for(direction: str, spot: float, offset: int) -> int:
    if direction == "short":   # buying puts
        return round(spot) + offset
    else:                       # buying calls
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


# ---------- Chart-stop trade simulation ----------

def _simulate_cs_trade(
    signal: SniperSignal,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    vix_bars: pd.DataFrame,
    combo: SniperCSCombo,
) -> Optional[SniperTrade]:
    """Simulate one SNIPER trade using SPY-price chart stop (CS variant).

    Stop is placed at level_price ± chart_stop_buffer in SPY space.
    TP1 / runner are R-multiples of that risk distance.
    Premium at each exit computed via BS so P&L is in option dollars.
    """
    bar = spy_bars.iloc[bar_idx]
    entry_time = bar["timestamp_et"]
    entry_spot = float(bar["close"])
    vix_at_entry = _vix_for(vix_bars, entry_time) or 18.0

    # L73 VIX regime gate: skip entry if VIX is below the minimum threshold
    if combo.vix_min > 0 and vix_at_entry < combo.vix_min:
        return None

    # L73 VIX-trending gate: skip entry if prior_day_VIX <= prior_5d_avg_VIX
    # (VIX must be escalating, not declining — level gate alone is IS-overfit, L104)
    if combo.vix_trending:
        entry_date = entry_time.date()
        prior_vix = vix_bars[vix_bars["timestamp_et"].dt.date < entry_date]
        if not prior_vix.empty:
            daily_close = (
                prior_vix.groupby(prior_vix["timestamp_et"].dt.date)["close"]
                .last()
                .sort_index()
            )
            if len(daily_close) >= 5:
                window = daily_close.iloc[-5:]
                prior_close_val = float(window.iloc[-1])
                prior_5d_avg_val = float(window.mean())
                if prior_close_val <= prior_5d_avg_val:
                    return None
            else:
                return None  # insufficient VIX history for trend check
        else:
            return None

    is_call = signal.direction == "long"
    strike = _strike_for(signal.direction, entry_spot, combo.strike_offset)
    entry_premium = _premium(entry_spot, strike, vix_at_entry, entry_time, is_call)

    # Chart stop in SPY price space
    if not is_call:  # puts (bear): adverse = SPY going UP
        chart_stop_spy = signal.level.price + combo.chart_stop_buffer
        risk_spy = chart_stop_spy - entry_spot
    else:            # calls (bull): adverse = SPY going DOWN
        chart_stop_spy = signal.level.price - combo.chart_stop_buffer
        risk_spy = entry_spot - chart_stop_spy

    if risk_spy <= 0:
        return None  # degenerate: entry already beyond chart stop

    # R-multiple SPY-price targets
    if not is_call:  # puts profit when SPY goes DOWN
        tp1_spy_target = entry_spot - risk_spy * combo.tp1_r
        runner_spy_target = entry_spot - risk_spy * combo.runner_r
    else:            # calls profit when SPY goes UP
        tp1_spy_target = entry_spot + risk_spy * combo.tp1_r
        runner_spy_target = entry_spot + risk_spy * combo.runner_r

    tp1_qty = max(1, round(combo.qty * combo.tp1_qty_fraction))
    runner_qty = combo.qty - tp1_qty
    time_stop = dt.time(combo.time_stop_et_hour, combo.time_stop_et_min)

    tp1_filled: Optional[float] = None
    tp1_filled_at: Optional[dt.datetime] = None

    for fwd_idx in range(bar_idx + 1, len(spy_bars)):
        fwd = spy_bars.iloc[fwd_idx]
        fwd_time = fwd["timestamp_et"]
        if not hasattr(fwd_time, "date") or fwd_time.date() != entry_time.date():
            break

        fwd_t = fwd_time.time()
        spot_close = float(fwd["close"])
        vix = _vix_for(vix_bars, fwd_time) or vix_at_entry

        # Adverse and favorable SPY prices this bar
        # puts: high is adverse (spy going up hurts); calls: low is adverse
        if not is_call:
            adverse_spy = float(fwd["high"])
            favor_spy = float(fwd["low"])
        else:
            adverse_spy = float(fwd["low"])
            favor_spy = float(fwd["high"])

        # 1. Chart stop (fires before TP1 per simulator.py convention)
        chart_stop_hit = (not is_call and adverse_spy >= chart_stop_spy) or (
            is_call and adverse_spy <= chart_stop_spy
        )
        if chart_stop_hit:
            stop_exit_premium = _premium(chart_stop_spy, strike, vix, fwd_time, is_call)
            if tp1_filled is not None:
                tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
                runner_pnl = (stop_exit_premium - entry_premium) * 100 * runner_qty
                total_pnl = tp1_pnl + runner_pnl
                exit_reason = "RUNNER_CHART_STOP"
            else:
                total_pnl = (stop_exit_premium - entry_premium) * 100 * combo.qty
                exit_reason = "CHART_STOP_ALL"
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
                chart_stop_spy=chart_stop_spy,
                risk_spy=round(risk_spy, 3),
                exit_premium_tp1=tp1_filled,
                exit_premium_runner=stop_exit_premium,
                exit_time_et=fwd_time,
                exit_reason=exit_reason,
                dollar_pnl=round(total_pnl, 2),
                level_label=signal.level.label,
                level_price=signal.level.price,
                vol_ratio=signal.vol_ratio,
                body_dollars=signal.body_dollars,
            )

        # 2. TP1 check
        tp1_hit = (not is_call and favor_spy <= tp1_spy_target) or (
            is_call and favor_spy >= tp1_spy_target
        )
        if tp1_filled is None and tp1_hit:
            tp1_exit_premium = _premium(tp1_spy_target, strike, vix, fwd_time, is_call)
            tp1_filled = tp1_exit_premium
            tp1_filled_at = fwd_time

        # 3. Runner target
        runner_hit = (not is_call and favor_spy <= runner_spy_target) or (
            is_call and favor_spy >= runner_spy_target
        )
        if tp1_filled is not None and runner_hit:
            runner_exit_premium = _premium(runner_spy_target, strike, vix, fwd_time, is_call)
            tp1_pnl = (tp1_filled - entry_premium) * 100 * tp1_qty
            runner_pnl = (runner_exit_premium - entry_premium) * 100 * runner_qty
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
                chart_stop_spy=chart_stop_spy,
                risk_spy=round(risk_spy, 3),
                exit_premium_tp1=tp1_filled,
                exit_premium_runner=runner_exit_premium,
                exit_time_et=fwd_time,
                exit_reason="TP1_THEN_RUNNER_TARGET",
                dollar_pnl=round(tp1_pnl + runner_pnl, 2),
                level_label=signal.level.label,
                level_price=signal.level.price,
                vol_ratio=signal.vol_ratio,
                body_dollars=signal.body_dollars,
            )

        # 4. Time stop
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
                chart_stop_spy=chart_stop_spy,
                risk_spy=round(risk_spy, 3),
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

    # EOD fallback: close at last bar
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
        chart_stop_spy=chart_stop_spy,
        risk_spy=round(risk_spy, 3),
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


# ---------- Per-day backtest ----------

def _signal_to_params(combo: SniperCSCombo) -> SniperParams:
    return SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=combo.require_break_above_open,
    )


def run_sniper_cs_day(
    date_et: dt.date,
    spy_full: pd.DataFrame,
    vix_full: pd.DataFrame,
    combo: SniperCSCombo,
    max_trades_per_day: int = 1,
) -> list[SniperTrade]:
    """Run chart-stop SNIPER across one trading day's RTH bars."""
    params = _signal_to_params(combo)

    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    if day_bars.empty:
        return []

    first_ts = day_bars["timestamp_et"].iloc[0]
    levels = compute_levels(spy_full, first_ts, params)
    if not levels:
        return []

    pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(40).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    trades: list[SniperTrade] = []
    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        bar = combined.iloc[bar_idx]
        signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
        if signal is None:
            continue
        trade = _simulate_cs_trade(signal, bar_idx, combined, vix_full, combo)
        if trade is None:
            continue
        trades.append(trade)
        if len(trades) >= max_trades_per_day:
            break

    return trades


# ---------- Public evaluator (matches overnight_grinder schema) ----------

def evaluate_sniper_cs_combo(combo_dict: dict) -> dict:
    """Run chart-stop SNIPER over J anchor days + wide window.

    Output schema mirrors overnight_grinder.evaluate_combo so this slots into
    the existing autoresearch pipeline (Stage 2/3/4 grinders, scorecards).
    """
    try:
        valid_fields = SniperCSCombo.__dataclass_fields__
        combo = SniperCSCombo(**{k: combo_dict[k] for k in combo_dict if k in valid_fields})
        from autoresearch import runner as _runner

        # ---- J anchor days ----
        min_d = dt.date.fromisoformat(min(t["date"] for t in J_WINNERS + J_LOSERS))
        max_d = dt.date.fromisoformat(max(t["date"] for t in J_WINNERS + J_LOSERS))
        spy_j, vix_j = _runner.load_data(min_d, max_d)
        spy_j["timestamp_et"] = (
            pd.to_datetime(spy_j["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )
        vix_j["timestamp_et"] = (
            pd.to_datetime(vix_j["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )

        by_day: dict[str, float] = {}
        all_anchor_trades: list[SniperTrade] = []
        for w in J_WINNERS + J_LOSERS:
            d = dt.date.fromisoformat(w["date"])
            trades = run_sniper_cs_day(d, spy_j, vix_j, combo)
            day_pnl = round(sum(t.dollar_pnl for t in trades), 2)
            key = w["date"]
            by_day[key] = day_pnl
            all_anchor_trades.extend(trades)

        winners_capture = sum(by_day.get(w["date"], 0.0) for w in J_WINNERS)
        losers_added = 0.0
        for lsr in J_LOSERS:
            pnl = by_day.get(lsr["date"], 0.0)
            if pnl < 0:
                losers_added += -pnl
        edge_capture = winners_capture - losers_added

        pnl_4_29 = by_day.get("2026-04-29", 0.0)
        pnl_5_04 = by_day.get("2026-05-04", 0.0)

        # ---- Wide window: 2025-01-01 .. 2026-05-22 ----
        wide_start = dt.date(2025, 1, 1)
        wide_end = dt.date(2026, 5, 22)
        spy_w, vix_w = _runner.load_data(wide_start, wide_end)
        spy_w["timestamp_et"] = (
            pd.to_datetime(spy_w["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )
        vix_w["timestamp_et"] = (
            pd.to_datetime(vix_w["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )

        all_dates = sorted(set(spy_w["timestamp_et"].dt.date.unique()))
        wide_trades: list[SniperTrade] = []
        day_pnl_map: dict[dt.date, float] = defaultdict(float)
        quarter_pnl_map: dict[str, float] = defaultdict(float)

        for d in all_dates:
            day_trades = run_sniper_cs_day(d, spy_w, vix_w, combo)
            wide_trades.extend(day_trades)
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

        regressions = []
        if pnl_4_29 < 0:
            regressions.append(f"4/29 ${pnl_4_29:.0f} negative on J winning day")
        if pnl_5_04 < 0:
            regressions.append(f"5/04 ${pnl_5_04:.0f} negative on J winning day")
        if losers_added > 100:
            regressions.append(f"losers_added ${losers_added:.0f} > $100 floor")
        if winners_capture < 200:
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
