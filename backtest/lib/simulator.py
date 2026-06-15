"""Bracket-order fill simulation for the BEARISH and BULLISH setups.

Given an entry signal at bar N, walks subsequent bars and decides when to exit.

Bracket structure (per playbook v1.0, mirrored for bull):
  BEARISH (puts):
    - Entry: BUY qty ATM 0DTE puts at trigger bar's close
    - TP1 (sell ~2/3): premium >= entry * (1 + TP1_PREMIUM_PCT)
    - Runner (~1/3): after TP1, stop moves to breakeven; exit on
        (a) ribbon flips back to non-BEAR
        (b) premium >= entry * (1 + RUNNER_MAX_PREMIUM_PCT)
        (c) time stop 15:50 ET
    - Stop-all triggers: premium <= entry * (1 + premium_stop_pct),
      bar close ABOVE rejection_level, ribbon flips, time stop.
  BULLISH (calls): mirror — close BELOW reclaim_level is the chart stop,
    ribbon must stay BULL, etc.

Conservative simulation:
  - If a bar's high+low range touches BOTH stop and TP1: stop fills first.
  - During a bar: max-adverse premium computed at the side's worst spot
    (for puts: bar.high; for calls: bar.low).
  - During a bar: max-favorable at the side's best spot
    (for puts: bar.low; for calls: bar.high).
  - No look-ahead.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from .pricing import (
    OptionQuote,
    black_scholes,
    price_atm_call,
    price_atm_put,
    time_to_expiry_years,
    vix_to_iv,
)
from .ribbon import RibbonState


def _price_existing_option(
    strike: int, spot: float, vix: float, now_et: dt.datetime, is_call: bool
) -> OptionQuote:
    """Price a fixed-strike option (call or put) at the given spot/vix/time.

    Used to track premium evolution AFTER entry — the strike is locked in.
    """
    iv = vix_to_iv(vix)
    tte = time_to_expiry_years(now_et)
    premium, delta = black_scholes(spot, strike, iv, tte, is_call=is_call)
    return OptionQuote(
        spot=spot, strike=strike, iv=iv, time_to_expiry_years=tte,
        is_call=is_call, premium=premium, delta=delta,
    )


# Backwards-compatible alias used by tests + diagnostic tools.
def _price_existing_put(strike: int, spot: float, vix: float, now_et: dt.datetime) -> OptionQuote:
    return _price_existing_option(strike, spot, vix, now_et, is_call=False)


# ----- params (sourced from automation/state/params.json conceptually) -----

PREMIUM_STOP_PCT = -0.50    # legacy default; tests expect this. Production v14 uses -0.08.
TP1_PREMIUM_PCT = 0.30
RUNNER_MAX_PREMIUM_PCT = 3.00
TP1_QTY_FRACTION = 2.0 / 3.0
TIME_STOP_ET = dt.time(15, 50)
DEFAULT_QTY = 3
DEFAULT_LEVEL_STOP_BUFFER = 0.0  # extra dollars past rejection_level before chart stop fires


class ExitReason(str, Enum):
    TP1_THEN_RUNNER_TARGET = "TP1_THEN_RUNNER_TARGET"
    TP1_THEN_RUNNER_RIBBON = "TP1_THEN_RUNNER_RIBBON"
    TP1_THEN_RUNNER_TIME = "TP1_THEN_RUNNER_TIME"
    TP1_THEN_RUNNER_BE_STOP = "TP1_THEN_RUNNER_BE_STOP"
    EXIT_ALL_PREMIUM_STOP = "EXIT_ALL_PREMIUM_STOP"
    EXIT_ALL_LEVEL_STOP = "EXIT_ALL_LEVEL_STOP"
    EXIT_ALL_RIBBON_FLIP_BACK = "EXIT_ALL_RIBBON_FLIP_BACK"
    EXIT_ALL_RUNNER_SIGNAL_BEFORE_TP1 = "EXIT_ALL_RUNNER_SIGNAL_BEFORE_TP1"
    EXIT_ALL_TIME_STOP = "EXIT_ALL_TIME_STOP"


@dataclass
class TradeFill:
    """Output of the simulator — one trade row."""
    setup: str
    entry_time_et: dt.datetime
    entry_spot: float
    strike: int
    qty: int
    entry_premium: float
    entry_delta: float
    entry_iv: float
    entry_vix: float
    rejection_level: float        # alias for "level" — bear=resistance, bull=support
    triggers_fired: list[str]
    side: str = "P"               # "P" (puts/bear) | "C" (calls/bull)
    tp1_time_et: Optional[dt.datetime] = None
    tp1_premium: Optional[float] = None
    runner_exit_time_et: Optional[dt.datetime] = None
    runner_exit_premium: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    dollar_pnl: float = 0.0
    pct_return_on_premium: float = 0.0
    hold_minutes: int = 0
    bars_held: int = 0
    max_adverse_premium: float = 0.0
    max_favorable_premium: float = 0.0


def simulate_trade(
    entry_bar_idx: int,
    entry_bar: pd.Series,
    spy_df: pd.DataFrame,
    vix_aligned: pd.Series,
    ribbon_df: pd.DataFrame,
    rejection_level: float,
    triggers_fired: list[str],
    qty: int = DEFAULT_QTY,
    setup: str = "BEARISH_REJECTION_RIDE_THE_RIBBON",
    side: str = "P",
    premium_stop_pct: float = PREMIUM_STOP_PCT,
    tp1_premium_pct: float = TP1_PREMIUM_PCT,
    runner_target_premium_pct: float = RUNNER_MAX_PREMIUM_PCT,
    tp1_qty_fraction: float = TP1_QTY_FRACTION,
    time_stop_et: dt.time = TIME_STOP_ET,
    level_stop_buffer_dollars: float = DEFAULT_LEVEL_STOP_BUFFER,
    strike_offset: int = 0,  # NEW 2026-05-09 evening: 0=ATM, +N=N OTM, -N=N ITM (matches simulator_real semantics)
    profit_lock_threshold_pct: float = 0.0,  # NEW 2026-05-13 v14_enhanced: 0=off; e.g. 0.10 = arm at +10% favorable
    profit_lock_stop_offset_pct: float = 0.0,  # NEW 2026-05-13 v14_enhanced: where to raise stop when armed (e.g. 0.05 = +5% above entry)
) -> TradeFill:
    """Simulate the bracket from entry through exit.

    All exit knobs are now parameterised so autoresearch can tune them.

    Args:
        side: "P" (puts/bearish) or "C" (calls/bullish). Mirrors the
            level-stop and ribbon-flip exit logic.
        premium_stop_pct: negative (e.g. -0.10 for -10% stop).
        tp1_premium_pct: positive (e.g. 0.30 for +30% take profit).
        runner_target_premium_pct: positive (e.g. 3.00 for +300% runner cap).
        tp1_qty_fraction: 0.0 to 1.0 — fraction of qty sold at TP1.
        time_stop_et: latest entry time before forced flat (e.g. dt.time(15, 50)).
        level_stop_buffer_dollars: extra $ past rejection_level before chart stop.
        profit_lock_threshold_pct: 0.0 = off; otherwise positive % (e.g. 0.10 = arm at +10%
            favorable premium). Once armed, raises runner_stop_premium to
            entry_premium * (1 + profit_lock_stop_offset_pct) so the trade
            cannot go negative. Per J 2026-05-12 winners-never-negative rule.
        profit_lock_stop_offset_pct: where to set the stop floor when profit-lock
            arms (e.g. 0.05 = entry+5%, 0.0 = BE). Never lowers an existing higher floor.
    """
    is_call = side == "C"
    expected_ribbon = "BULL" if is_call else "BEAR"
    entry_time = entry_bar["timestamp_et"]
    entry_spot = float(entry_bar["close"])
    entry_vix = float(vix_aligned.iloc[entry_bar_idx])

    entry_quote = (
        price_atm_call(entry_spot, entry_vix, entry_time)
        if is_call else price_atm_put(entry_spot, entry_vix, entry_time)
    )
    # Multi-Agent Gamma 2.0: support OTM/ITM strike offset (matches simulator_real semantics).
    # For puts:  strike = atm - strike_offset.  +1 = 1-OTM (strike below spot), -1 = 1-ITM (above spot).
    # For calls: strike = atm + strike_offset.  +1 = 1-OTM (strike above spot), -1 = 1-ITM (below spot).
    if strike_offset != 0:
        atm = entry_quote.strike
        target_strike = (atm + strike_offset) if is_call else (atm - strike_offset)
        # Re-price at the offset strike using same vol/time
        from .pricing import black_scholes
        new_premium, new_delta = black_scholes(entry_spot, target_strike,
                                                 entry_quote.iv, entry_quote.time_to_expiry_years,
                                                 is_call=is_call)
        entry_premium = float(new_premium)
        strike = target_strike
        entry_delta = float(new_delta)
    else:
        entry_premium = entry_quote.premium
        strike = entry_quote.strike
        entry_delta = entry_quote.delta

    stop_premium = entry_premium * (1.0 + premium_stop_pct)
    tp1_premium = entry_premium * (1.0 + tp1_premium_pct)
    runner_target_premium = entry_premium * (1.0 + runner_target_premium_pct)

    fill = TradeFill(
        setup=setup,
        entry_time_et=entry_time,
        entry_spot=entry_spot,
        strike=strike,
        qty=qty,
        entry_premium=entry_premium,
        entry_delta=entry_delta,
        entry_iv=entry_quote.iv,
        entry_vix=entry_vix,
        rejection_level=rejection_level if rejection_level is not None else 0.0,
        triggers_fired=triggers_fired,
        side=side,
    )

    tp1_filled = False
    runner_stop_premium = stop_premium
    profit_lock_armed = False  # v14_enhanced: arms when favorable premium hits threshold
    fill.max_adverse_premium = entry_premium
    fill.max_favorable_premium = entry_premium

    for i in range(entry_bar_idx + 1, len(spy_df)):
        bar = spy_df.iloc[i]
        bar_time = bar["timestamp_et"]
        if bar_time.date() != entry_time.date():
            break

        bar_vix = float(vix_aligned.iloc[i])
        # For puts: spot UP = premium DOWN (adverse). For calls: spot DOWN = premium DOWN.
        adverse_spot = float(bar["high"]) if not is_call else float(bar["low"])
        favorable_spot = float(bar["low"]) if not is_call else float(bar["high"])
        worst_quote = _price_existing_option(strike, adverse_spot, bar_vix, bar_time, is_call=is_call)
        best_quote = _price_existing_option(strike, favorable_spot, bar_vix, bar_time, is_call=is_call)
        worst_premium = worst_quote.premium
        best_premium = best_quote.premium

        if worst_premium < fill.max_adverse_premium:
            fill.max_adverse_premium = worst_premium
        if best_premium > fill.max_favorable_premium:
            fill.max_favorable_premium = best_premium

        # v14_enhanced profit-lock: once favorable premium reaches the threshold,
        # raise the stop floor so a winning trade cannot go negative.
        # Never LOWERS an existing higher floor.
        if profit_lock_threshold_pct > 0 and not profit_lock_armed:
            arm_premium = entry_premium * (1.0 + profit_lock_threshold_pct)
            if best_premium >= arm_premium:
                profit_lock_armed = True
                new_floor = entry_premium * (1.0 + profit_lock_stop_offset_pct)
                if new_floor > runner_stop_premium:
                    runner_stop_premium = new_floor

        stop_touched_this_bar = worst_premium <= runner_stop_premium
        tp1_touched_this_bar = (not tp1_filled) and best_premium >= tp1_premium
        time_stop_now = bar_time.time() >= time_stop_et

        if stop_touched_this_bar and not tp1_filled:
            fill.runner_exit_time_et = bar_time
            fill.runner_exit_premium = runner_stop_premium
            fill.exit_reason = ExitReason.EXIT_ALL_PREMIUM_STOP
            break

        if time_stop_now and not tp1_filled:
            close_quote = _price_existing_option(
                strike, float(bar["close"]), bar_vix, bar_time, is_call=is_call
            )
            fill.runner_exit_time_et = bar_time
            fill.runner_exit_premium = close_quote.premium
            fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP
            break

        # Ribbon flips back AWAY from setup direction → exit all.
        ribbon_state = _get_ribbon_at(ribbon_df, i)
        if ribbon_state is not None and ribbon_state.stack != expected_ribbon:
            close_quote = _price_existing_option(
                strike, float(bar["close"]), bar_vix, bar_time, is_call=is_call
            )
            fill.runner_exit_time_et = bar_time
            fill.runner_exit_premium = close_quote.premium
            fill.exit_reason = (
                ExitReason.EXIT_ALL_RIBBON_FLIP_BACK if not tp1_filled
                else ExitReason.TP1_THEN_RUNNER_RIBBON
            )
            break

        # Bar closes against the level → chart stop (with optional buffer).
        # For puts (bear): close ABOVE rejected resistance + buffer = stop
        # For calls (bull): close BELOW reclaimed support - buffer = stop
        if rejection_level is not None and not tp1_filled:
            level_threshold = (
                rejection_level + level_stop_buffer_dollars if not is_call
                else rejection_level - level_stop_buffer_dollars
            )
            level_violated = (
                bar["close"] > level_threshold if not is_call
                else bar["close"] < level_threshold
            )
            if level_violated:
                close_quote = _price_existing_option(
                    strike, float(bar["close"]), bar_vix, bar_time, is_call=is_call
                )
                fill.runner_exit_time_et = bar_time
                fill.runner_exit_premium = close_quote.premium
                fill.exit_reason = ExitReason.EXIT_ALL_LEVEL_STOP
                break

        if tp1_touched_this_bar:
            tp1_filled = True
            fill.tp1_time_et = bar_time
            fill.tp1_premium = tp1_premium
            # Move to breakeven, but PRESERVE profit-lock floor if it's higher
            runner_stop_premium = max(entry_premium, runner_stop_premium)
            continue

        if tp1_filled:
            if best_premium >= runner_target_premium:
                fill.runner_exit_time_et = bar_time
                fill.runner_exit_premium = runner_target_premium
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TARGET
                break
            if worst_premium <= runner_stop_premium:
                fill.runner_exit_time_et = bar_time
                fill.runner_exit_premium = runner_stop_premium
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_BE_STOP
                break
            if time_stop_now:
                close_quote = _price_existing_option(
                    strike, float(bar["close"]), bar_vix, bar_time, is_call=is_call
                )
                fill.runner_exit_time_et = bar_time
                fill.runner_exit_premium = close_quote.premium
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TIME
                break

    if fill.exit_reason is None:
        last_idx = min(entry_bar_idx + 78, len(spy_df) - 1)
        last_bar = spy_df.iloc[last_idx]
        last_vix = float(vix_aligned.iloc[last_idx])
        last_quote = _price_existing_option(
            strike, float(last_bar["close"]), last_vix, last_bar["timestamp_et"], is_call=is_call
        )
        fill.runner_exit_time_et = last_bar["timestamp_et"]
        fill.runner_exit_premium = last_quote.premium
        fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP

    fill.dollar_pnl = _compute_pnl(fill, qty, tp1_qty_fraction=tp1_qty_fraction)
    fill.pct_return_on_premium = (
        fill.dollar_pnl / (entry_premium * qty * 100.0) if entry_premium > 0 else 0.0
    )
    if fill.runner_exit_time_et:
        delta_min = (fill.runner_exit_time_et - entry_time).total_seconds() / 60.0
        fill.hold_minutes = int(round(delta_min))
        fill.bars_held = int(round(delta_min / 5.0))
    return fill


def _get_ribbon_at(ribbon_df: pd.DataFrame, idx: int) -> Optional[RibbonState]:
    if idx < 0 or idx >= len(ribbon_df):
        return None
    row = ribbon_df.iloc[idx]
    if row["stack"] == "WARMUP" or pd.isna(row["fast"]):
        return None
    return RibbonState(
        fast=float(row["fast"]),
        pivot=float(row["pivot"]),
        slow=float(row["slow"]),
        spread_cents=float(row["spread_cents"]),
        stack=str(row["stack"]),
    )


def _compute_pnl(fill: TradeFill, qty: int, tp1_qty_fraction: float = TP1_QTY_FRACTION) -> float:
    """P&L identical for puts and calls: long the option, P&L = (exit - entry) * qty * 100.

    `tp1_qty_fraction` controls how many contracts get sold at TP1 (0.667 = 2/3,
    0.50 = half, 1.0 = all-out at TP1 with no runner).
    """
    if fill.runner_exit_premium is None:
        return 0.0
    if fill.tp1_filled():
        tp1_qty = int(round(qty * tp1_qty_fraction))
        # Edge case: tp1_qty_fraction=1.0 means everything sold at TP1, no runner.
        tp1_qty = min(tp1_qty, qty)
        runner_qty = qty - tp1_qty
        tp1_pnl = (fill.tp1_premium - fill.entry_premium) * tp1_qty * 100.0
        runner_pnl = (fill.runner_exit_premium - fill.entry_premium) * runner_qty * 100.0
        return tp1_pnl + runner_pnl
    return (fill.runner_exit_premium - fill.entry_premium) * qty * 100.0


def _tp1_filled_method(self) -> bool:
    return self.tp1_time_et is not None


TradeFill.tp1_filled = _tp1_filled_method
