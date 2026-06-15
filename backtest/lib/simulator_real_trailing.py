"""Profit-lock variant wrapper around `simulate_trade_real`.

Adds support for three profit-lock modes WITHOUT modifying simulator_real.py:

    profit_lock_mode = "fixed"     — current behaviour (arm at threshold,
                                     floor stays at entry × (1 + offset))
    profit_lock_mode = "trailing"  — chandelier-style: once armed, floor
                                     re-computes each bar as max(arm_floor,
                                     HWM × (1 - trail_pct)). Floor never
                                     lowers, only steps up with HWM.
    profit_lock_mode = "stepped"   — discrete steps:
                                       HWM ≥ entry×1.20 → floor entry×1.10
                                       HWM ≥ entry×1.50 → floor entry×1.25
                                       HWM ≥ entry×2.00 → floor entry×1.50
                                       HWM ≥ entry×3.00 → floor entry×2.00

This is a TRUE wrapper — it copies the bar-walk logic from simulator_real
and ONLY swaps the profit-lock block. All other behaviour (TP1, runner
exits, level-stop, ribbon-flip, time-stop, slippage, MAE/MFE tracking) is
identical to simulator_real.simulate_trade_real.

The wrapper is intentionally a fork rather than a subclass so it can be
ratified and shipped without touching the production simulator. After J's
review, the winning mode can be folded back into simulator_real.

Source of truth: this file is a copy of simulator_real.py:simulate_trade_real
as of 2026-05-13 T44c (after T41 added FIXED profit-lock). If
simulator_real.py changes, this wrapper must be re-synced.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from .option_pricing_real import (
    bar_at_or_after,
    load_contract_bars,
    option_symbol,
    quote_at_index,
)
from .ribbon import RibbonState
from .simulator_real import (
    DEFAULT_ENTRY_SLIPPAGE,
    DEFAULT_EXIT_SLIPPAGE,
    _is_runner_exit_signal,
    _next_level_past_entry,
    _ribbon_at,
    _strike_from_spot,
)
from .simulator import (
    DEFAULT_QTY,
    TIME_STOP_ET,
    TP1_PREMIUM_PCT,
    TP1_QTY_FRACTION,
    RUNNER_MAX_PREMIUM_PCT,
    ExitReason,
    TradeFill,
)


# ── Stepped-mode rungs (HWM_multiple, floor_multiple), MUST be ascending ─────
STEPPED_RUNGS: tuple[tuple[float, float], ...] = (
    (1.20, 1.10),  # +20% HWM → lock +10%
    (1.50, 1.25),  # +50% HWM → lock +25%
    (2.00, 1.50),  # +100% HWM → lock +50%
    (3.00, 2.00),  # +200% HWM → lock +100%
)


def _stepped_floor(entry_premium: float, hwm: float) -> Optional[float]:
    """Return the highest applicable stepped floor, or None if HWM hasn't
    cleared the first rung."""
    if entry_premium <= 0 or hwm <= 0:
        return None
    ratio = hwm / entry_premium
    floor = None
    for rung_hwm, rung_floor in STEPPED_RUNGS:
        if ratio >= rung_hwm:
            floor = entry_premium * rung_floor
        else:
            break
    return floor


def simulate_trade_real_trailing(
    entry_bar_idx: int,
    entry_bar: pd.Series,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    rejection_level: Optional[float],
    triggers_fired: list[str],
    side: str = "P",
    qty: int = DEFAULT_QTY,
    setup: str = "BEARISH_REJECTION_RIDE_THE_RIBBON",
    entry_slippage: float = DEFAULT_ENTRY_SLIPPAGE,
    exit_slippage: float = DEFAULT_EXIT_SLIPPAGE,
    levels_active: Optional[list[float]] = None,
    levels_carry: Optional[list[float]] = None,
    use_tiered_exits: bool = True,
    strike_override: Optional[int] = None,
    premium_stop_pct: float = -0.08,
    strike_offset: int = -2,
    profit_lock_threshold_pct: float = 0.0,
    profit_lock_stop_offset_pct: float = 0.0,
    # ── NEW: profit-lock mode + trail ────────────────────────────────────────
    profit_lock_mode: str = "fixed",
    trail_pct: float = 0.30,
) -> Optional[TradeFill]:
    """Bracket simulation with selectable profit-lock mode.

    See module docstring for mode definitions.

    The function signature is otherwise IDENTICAL to
    `simulator_real.simulate_trade_real`, so it can be drop-in monkey-patched
    via `lib.orchestrator.simulate_trade_real = simulate_trade_real_trailing`.
    Unknown kwargs (`profit_lock_mode`, `trail_pct`) get ignored when the
    orchestrator calls with the standard signature — but the wrapper itself
    only uses these two extras when explicitly passed via a closure.
    """
    if profit_lock_mode not in ("fixed", "trailing", "stepped"):
        raise ValueError(
            f"profit_lock_mode must be 'fixed' | 'trailing' | 'stepped', "
            f"got {profit_lock_mode!r}"
        )

    entry_time = entry_bar["timestamp_et"]
    if hasattr(entry_time, "tz_localize"):
        if entry_time.tz is not None:
            entry_time = entry_time.tz_localize(None)
        entry_time = entry_time.to_pydatetime()
    elif hasattr(entry_time, "tzinfo") and entry_time.tzinfo is not None:
        entry_time = entry_time.replace(tzinfo=None)

    entry_spot = float(entry_bar["close"])
    if strike_override is not None:
        strike = strike_override
    else:
        atm = _strike_from_spot(entry_spot)
        if side == "P":
            strike = atm - strike_offset
        else:
            strike = atm + strike_offset
    symbol = option_symbol(entry_time.date(), strike, side)

    opt_df = load_contract_bars(symbol)
    if opt_df is None:
        return None

    opt_df = opt_df.copy()
    if opt_df["timestamp_et"].dt.tz is not None:
        opt_df["timestamp_et"] = opt_df["timestamp_et"].dt.tz_localize(None)

    next_bar_start = entry_time + dt.timedelta(minutes=5)
    entry_bar_opt = bar_at_or_after(opt_df, next_bar_start)
    if entry_bar_opt is None or entry_bar_opt.open <= 0:
        return None

    raw_open = entry_bar_opt.open
    entry_premium = raw_open + entry_slippage
    stop_premium = entry_premium * (1.0 + premium_stop_pct)
    tp1_premium_fallback = entry_premium * (1.0 + TP1_PREMIUM_PCT)
    runner_target_premium = entry_premium * (1.0 + RUNNER_MAX_PREMIUM_PCT)

    levels_active = list(levels_active or [])
    levels_carry = list(levels_carry or [])
    chart_tp1_level = _next_level_past_entry(
        entry_spot, levels_active + levels_carry, side
    )

    fill = TradeFill(
        setup=setup,
        entry_time_et=entry_time,
        entry_spot=entry_spot,
        strike=strike,
        qty=qty,
        entry_premium=entry_premium,
        entry_delta=0.0,
        entry_iv=0.0,
        entry_vix=0.0,
        rejection_level=rejection_level if rejection_level is not None else 0.0,
        triggers_fired=triggers_fired,
    )
    fill.max_adverse_premium = entry_premium
    fill.max_favorable_premium = entry_premium

    tp1_filled = False
    runner_stop_premium = stop_premium
    profit_lock_armed = False
    arm_floor: Optional[float] = None  # only meaningful for trailing mode

    tp1_qty = int(qty * TP1_QTY_FRACTION)
    runner_qty = qty - tp1_qty
    if use_tiered_exits and runner_qty >= 2:
        aggressive_remaining = runner_qty // 2
        conservative_remaining = runner_qty - aggressive_remaining
    else:
        conservative_remaining = runner_qty
        aggressive_remaining = 0

    cons_exit_premium: Optional[float] = None
    cons_exit_time = None
    aggr_exit_premium: Optional[float] = None
    aggr_exit_time = None

    entry_idx_opt = None
    for k in range(len(opt_df)):
        if opt_df.iloc[k]["timestamp_et"] == entry_bar_opt.timestamp_et:
            entry_idx_opt = k
            break
    if entry_idx_opt is None:
        return None

    spy_idx = entry_bar_idx + 2
    opt_idx = entry_idx_opt + 1
    fill.entry_time_et = entry_bar_opt.timestamp_et

    def _vol_baseline_at(idx: int) -> float:
        start = max(0, idx - 20)
        if start >= idx:
            return 0.0
        return float(spy_df.iloc[start:idx]["volume"].mean())

    while opt_idx < len(opt_df) and spy_idx < len(spy_df):
        spy_bar = spy_df.iloc[spy_idx]
        spy_time = spy_bar["timestamp_et"]
        if hasattr(spy_time, "tz_localize"):
            if spy_time.tz is not None:
                spy_time = spy_time.tz_localize(None)
            spy_time = spy_time.to_pydatetime()
        elif hasattr(spy_time, "tzinfo") and spy_time.tzinfo is not None:
            spy_time = spy_time.replace(tzinfo=None)
        opt_bar = quote_at_index(opt_df, opt_idx)
        if opt_bar is None:
            opt_idx += 1
            spy_idx += 1
            continue
        if spy_time.date() != entry_time.date():
            break

        if opt_bar.low < fill.max_adverse_premium:
            fill.max_adverse_premium = opt_bar.low
        if opt_bar.high > fill.max_favorable_premium:
            fill.max_favorable_premium = opt_bar.high

        worst_premium = opt_bar.low
        best_premium = opt_bar.high
        hwm = fill.max_favorable_premium  # already updated above

        # ── Profit-lock block (the ONLY behavioural divergence vs simulator_real) ──
        if profit_lock_threshold_pct > 0:
            arm_premium = entry_premium * (1.0 + profit_lock_threshold_pct)
            if not profit_lock_armed and best_premium >= arm_premium:
                profit_lock_armed = True
                arm_floor = entry_premium * (1.0 + profit_lock_stop_offset_pct)
                if arm_floor > runner_stop_premium:
                    runner_stop_premium = arm_floor

            if profit_lock_armed:
                if profit_lock_mode == "fixed":
                    pass  # arm_floor already applied above
                elif profit_lock_mode == "trailing":
                    trail_floor = hwm * (1.0 - trail_pct)
                    candidate = max(arm_floor or 0.0, trail_floor)
                    if candidate > runner_stop_premium:
                        runner_stop_premium = candidate
                elif profit_lock_mode == "stepped":
                    stepped = _stepped_floor(entry_premium, hwm)
                    if stepped is not None:
                        candidate = max(arm_floor or 0.0, stepped)
                        if candidate > runner_stop_premium:
                            runner_stop_premium = candidate
        elif profit_lock_mode in ("trailing", "stepped"):
            # Allow trailing/stepped without an explicit arm threshold — useful
            # for testing pure-trail variants. Arm immediately on first bar
            # where best_premium > entry_premium so the floor begins tracking.
            if not profit_lock_armed and best_premium > entry_premium:
                profit_lock_armed = True
                arm_floor = entry_premium  # break-even floor as anchor
            if profit_lock_armed:
                if profit_lock_mode == "trailing":
                    trail_floor = hwm * (1.0 - trail_pct)
                    candidate = max(arm_floor or 0.0, trail_floor)
                    if candidate > runner_stop_premium:
                        runner_stop_premium = candidate
                elif profit_lock_mode == "stepped":
                    stepped = _stepped_floor(entry_premium, hwm)
                    if stepped is not None and stepped > runner_stop_premium:
                        runner_stop_premium = stepped
        # ── /profit-lock block ──────────────────────────────────────────────────

        time_stop_now = spy_time.time() >= TIME_STOP_ET
        vol_baseline = _vol_baseline_at(spy_idx)

        # ── Pre-TP1 hard exits ───────────────────────────────────────────────
        if not tp1_filled:
            if worst_premium <= runner_stop_premium:
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = runner_stop_premium
                fill.exit_reason = ExitReason.EXIT_ALL_PREMIUM_STOP
                break

            if time_stop_now:
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = max(0.01, opt_bar.close - exit_slippage)
                fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP
                break

            ribbon_state = _ribbon_at(ribbon_df, spy_idx)
            opposite_stack = "BULL" if side == "P" else "BEAR"
            if (
                ribbon_state is not None
                and ribbon_state.stack == opposite_stack
                and ribbon_state.spread_cents >= 30.0
            ):
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = max(0.01, opt_bar.close - exit_slippage)
                fill.exit_reason = ExitReason.EXIT_ALL_RIBBON_FLIP_BACK
                break

            LEVEL_STOP_BUFFER = 0.50
            level_breached = (
                rejection_level is not None
                and rejection_level != 0.0
                and (
                    (side == "P" and float(spy_bar["close"]) > rejection_level + LEVEL_STOP_BUFFER)
                    or (side == "C" and float(spy_bar["close"]) < rejection_level - LEVEL_STOP_BUFFER)
                )
            )
            if level_breached:
                fill.runner_exit_time_et = spy_time
                fill.runner_exit_premium = max(0.01, opt_bar.close - exit_slippage)
                fill.exit_reason = ExitReason.EXIT_ALL_LEVEL_STOP
                break

            tp1_fire_reason = None
            tp1_fire_premium = None

            if chart_tp1_level is not None:
                hit_level = (
                    (side == "P" and float(spy_bar["low"]) <= chart_tp1_level + 0.30)
                    or (side == "C" and float(spy_bar["high"]) >= chart_tp1_level - 0.30)
                )
                if hit_level:
                    tp1_fire_reason = "chart_level"
                    tp1_fire_premium = max(0.01, opt_bar.close - exit_slippage)

            if tp1_fire_reason is None and best_premium >= tp1_premium_fallback:
                tp1_fire_reason = "premium_fallback"
                tp1_fire_premium = tp1_premium_fallback

            if tp1_fire_reason is not None:
                tp1_filled = True
                fill.tp1_time_et = spy_time
                fill.tp1_premium = tp1_fire_premium
                # BE stop on runners — but never LOWER an existing higher floor
                # set by a profit-lock floor (especially trailing/stepped).
                runner_stop_premium = max(runner_stop_premium, entry_premium)
                spy_idx += 1
                opt_idx += 1
                continue

            spy_idx += 1
            opt_idx += 1
            continue

        # ── Post-TP1: runner exits ───────────────────────────────────────────
        ribbon_state = _ribbon_at(ribbon_df, spy_idx)
        opposite_stack = "BULL" if side == "P" else "BEAR"
        ribbon_invalidated = (
            ribbon_state is not None
            and ribbon_state.stack == opposite_stack
            and ribbon_state.spread_cents >= 30.0
        )

        if conservative_remaining > 0:
            cons_exit_now = False
            cons_price = None
            if _is_runner_exit_signal(spy_bar, vol_baseline, levels_carry, levels_active,
                                       side, tier="conservative"):
                cons_exit_now = True
                cons_price = max(0.01, opt_bar.close - exit_slippage)
            elif ribbon_invalidated:
                cons_exit_now = True
                cons_price = max(0.01, opt_bar.close - exit_slippage)
            elif worst_premium <= runner_stop_premium:
                cons_exit_now = True
                cons_price = runner_stop_premium
            elif time_stop_now:
                cons_exit_now = True
                cons_price = max(0.01, opt_bar.close - exit_slippage)

            if cons_exit_now:
                cons_exit_premium = cons_price
                cons_exit_time = spy_time
                conservative_remaining = 0

        if aggressive_remaining > 0:
            aggr_exit_now = False
            aggr_price = None
            if _is_runner_exit_signal(spy_bar, vol_baseline, levels_carry, levels_active,
                                       side, tier="aggressive"):
                aggr_exit_now = True
                aggr_price = max(0.01, opt_bar.close - exit_slippage)
            elif ribbon_invalidated:
                aggr_exit_now = True
                aggr_price = max(0.01, opt_bar.close - exit_slippage)
            elif best_premium >= runner_target_premium:
                aggr_exit_now = True
                aggr_price = runner_target_premium
            elif worst_premium <= runner_stop_premium:
                aggr_exit_now = True
                aggr_price = runner_stop_premium
            elif time_stop_now:
                aggr_exit_now = True
                aggr_price = max(0.01, opt_bar.close - exit_slippage)

            if aggr_exit_now:
                aggr_exit_premium = aggr_price
                aggr_exit_time = spy_time
                aggressive_remaining = 0

        if conservative_remaining == 0 and aggressive_remaining == 0:
            if cons_exit_premium is not None and aggr_exit_premium is not None:
                fill.runner_exit_time_et = max(cons_exit_time, aggr_exit_time)
                cons_qty_n = max(1, runner_qty // 2 if use_tiered_exits and runner_qty >= 2 else runner_qty)
                aggr_qty_n = max(0, runner_qty - cons_qty_n)
                if aggr_qty_n > 0:
                    fill.runner_exit_premium = (
                        (cons_exit_premium * cons_qty_n + aggr_exit_premium * aggr_qty_n)
                        / (cons_qty_n + aggr_qty_n)
                    )
                else:
                    fill.runner_exit_premium = cons_exit_premium
            else:
                fill.runner_exit_time_et = cons_exit_time or aggr_exit_time
                fill.runner_exit_premium = cons_exit_premium or aggr_exit_premium
            if ribbon_invalidated:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_RIBBON
            elif time_stop_now:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TIME
            elif aggr_exit_premium is not None and aggr_exit_premium >= runner_target_premium - 0.01:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_TARGET
            else:
                fill.exit_reason = ExitReason.TP1_THEN_RUNNER_RIBBON
            break

        spy_idx += 1
        opt_idx += 1

    if fill.exit_reason is None:
        last_idx = min(opt_idx, len(opt_df) - 1)
        last_opt = quote_at_index(opt_df, last_idx)
        last_spy_idx = min(spy_idx, len(spy_df) - 1)
        last_spy_time = spy_df.iloc[last_spy_idx]["timestamp_et"]
        fill.runner_exit_time_et = last_spy_time
        fill.runner_exit_premium = (
            max(0.01, last_opt.close - exit_slippage) if last_opt
            else entry_premium * 0.5
        )
        fill.exit_reason = ExitReason.EXIT_ALL_TIME_STOP

    fill.dollar_pnl = _compute_pnl_local(fill, qty)
    fill.pct_return_on_premium = (
        fill.dollar_pnl / (entry_premium * qty * 100.0) if entry_premium > 0 else 0.0
    )
    if fill.runner_exit_time_et:
        delta_min = (fill.runner_exit_time_et - entry_time).total_seconds() / 60.0
        fill.hold_minutes = int(round(delta_min))
        fill.bars_held = int(round(delta_min / 5.0))
    return fill


def _compute_pnl_local(fill: TradeFill, qty: int) -> float:
    """Identical to simulator_real._compute_pnl — duplicated here so this
    module has zero post-import side effects on simulator_real."""
    if fill.runner_exit_premium is None:
        return 0.0
    if fill.tp1_filled():
        tp1_qty = int(qty * TP1_QTY_FRACTION)
        runner_qty = qty - tp1_qty
        tp1_pnl = (fill.tp1_premium - fill.entry_premium) * tp1_qty * 100.0
        runner_pnl = (fill.runner_exit_premium - fill.entry_premium) * runner_qty * 100.0
        return tp1_pnl + runner_pnl
    return (fill.runner_exit_premium - fill.entry_premium) * qty * 100.0
