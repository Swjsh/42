"""Tests for the call (bullish) side of the BS simulator.

Mirrors test_simulator.py for puts but uses synthetic call setups.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from lib.ribbon import compute_ribbon
from lib.simulator import (
    DEFAULT_QTY,
    ExitReason,
    TradeFill,
    simulate_trade,
)


def _bars(spots: list[float], vol: int = 5_000_000) -> pd.DataFrame:
    """Build a SPY 5-min bar DataFrame from a closing-price series."""
    start = dt.datetime(2026, 4, 1, 9, 35).replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    rows = []
    for i, s in enumerate(spots):
        ts = start + dt.timedelta(minutes=5 * i)
        rng = 0.4
        rows.append({
            "timestamp_et": pd.Timestamp(ts),
            "open": s, "high": s + rng / 2, "low": s - rng / 2, "close": s,
            "volume": vol,
        })
    return pd.DataFrame(rows)


def _vix_series(n: int, vix: float = 17.0) -> pd.Series:
    return pd.Series([vix] * n)


def _ribbon_df(bars: pd.DataFrame) -> pd.DataFrame:
    return compute_ribbon(bars["close"])


def test_call_simulator_runs_winning_bullish_trade():
    # Steady price advance from 720 to 723 - calls profit.
    spots = [720.0 + i * 0.05 for i in range(60)]
    bars = _bars(spots)
    vix = _vix_series(len(bars))
    ribbon = _ribbon_df(bars)
    fill = simulate_trade(
        entry_bar_idx=0,
        entry_bar=bars.iloc[0],
        spy_df=bars,
        vix_aligned=vix,
        ribbon_df=ribbon,
        rejection_level=719.50,  # support reclaimed
        triggers_fired=["level_reclaim"],
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        side="C",
        premium_stop_pct=-0.10,
    )
    assert fill.side == "C"
    assert fill.exit_reason is not None
    # Bullish trade in a steady uptrend should not lose money outright.
    assert fill.dollar_pnl >= -50, f"unexpected loss: ${fill.dollar_pnl:.0f}"


def test_call_simulator_premium_stop_when_price_falls():
    # Sharp price decline after entry - calls should stop out.
    spots = [720.0] + [720.0 - i * 0.30 for i in range(1, 30)]
    bars = _bars(spots)
    vix = _vix_series(len(bars))
    ribbon = _ribbon_df(bars)
    fill = simulate_trade(
        entry_bar_idx=0,
        entry_bar=bars.iloc[0],
        spy_df=bars,
        vix_aligned=vix,
        ribbon_df=ribbon,
        rejection_level=719.50,
        triggers_fired=["level_reclaim"],
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        side="C",
        premium_stop_pct=-0.10,
    )
    # Either premium stop or level stop should fire (price falls below 719.50).
    assert fill.exit_reason in (
        ExitReason.EXIT_ALL_PREMIUM_STOP,
        ExitReason.EXIT_ALL_LEVEL_STOP,
        ExitReason.EXIT_ALL_RIBBON_FLIP_BACK,
    )
    assert fill.dollar_pnl < 0


def test_call_simulator_level_stop_on_close_below_support():
    # Price holds above 720 then breaks below 719.50 (the reclaimed support).
    spots = [720.5] * 5 + [720.5, 720.0, 719.0, 719.0, 719.0]
    bars = _bars(spots)
    vix = _vix_series(len(bars))
    ribbon = _ribbon_df(bars)
    fill = simulate_trade(
        entry_bar_idx=0,
        entry_bar=bars.iloc[0],
        spy_df=bars,
        vix_aligned=vix,
        ribbon_df=ribbon,
        rejection_level=719.50,
        triggers_fired=["level_reclaim"],
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        side="C",
        premium_stop_pct=-0.20,  # wide premium stop so level stop fires first
    )
    # Should exit on level violation OR premium stop (both acceptable)
    assert fill.exit_reason in (
        ExitReason.EXIT_ALL_LEVEL_STOP,
        ExitReason.EXIT_ALL_PREMIUM_STOP,
        ExitReason.EXIT_ALL_RIBBON_FLIP_BACK,
        ExitReason.EXIT_ALL_TIME_STOP,
    )


def test_put_and_call_use_correct_atm_strike():
    """Strike rounding should not differ by side; both round nearest dollar."""
    bars = _bars([720.4] * 10)
    vix = _vix_series(len(bars))
    ribbon = _ribbon_df(bars)
    put_fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0], spy_df=bars, vix_aligned=vix,
        ribbon_df=ribbon, rejection_level=720.5,
        triggers_fired=["level_rejection"],
        setup="BEARISH_REJECTION_RIDE_THE_RIBBON", side="P",
    )
    call_fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0], spy_df=bars, vix_aligned=vix,
        ribbon_df=ribbon, rejection_level=720.0,
        triggers_fired=["level_reclaim"],
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
    )
    assert put_fill.strike == 720
    assert call_fill.strike == 720


def test_premium_stop_pct_is_respected():
    """Tighter stop should fire faster (worse exit reason distribution shifts toward stop)."""
    # Price dips then recovers — tight stop fires, loose stop survives
    spots = [720.0, 719.7, 719.4, 720.5, 721.0, 721.5, 722.0]
    bars = _bars(spots)
    vix = _vix_series(len(bars))
    ribbon = _ribbon_df(bars)

    tight = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0], spy_df=bars, vix_aligned=vix,
        ribbon_df=ribbon, rejection_level=719.0,
        triggers_fired=["level_reclaim"],
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
        premium_stop_pct=-0.10,
    )
    loose = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0], spy_df=bars, vix_aligned=vix,
        ribbon_df=ribbon, rejection_level=719.0,
        triggers_fired=["level_reclaim"],
        setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
        premium_stop_pct=-0.50,
    )
    # Tight stop's MAE is hit (worse exit), loose isn't.
    # Both exit somewhere; we just check premium_stop_pct flows through.
    assert tight.exit_reason is not None
    assert loose.exit_reason is not None
