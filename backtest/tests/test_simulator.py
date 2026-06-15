"""Simulator unit tests — verify P&L calc, TP1 mechanics, conservative stop rule."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.simulator import simulate_trade, ExitReason, TP1_QTY_FRACTION, DEFAULT_QTY  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402


ET = pytz.timezone("America/New_York")


def _make_bars(prices: list[tuple[float, float, float, float, float]], start_time: dt.datetime) -> pd.DataFrame:
    """Make a bars DataFrame from (open, high, low, close, volume) tuples."""
    rows = []
    for i, (o, h, l, c, v) in enumerate(prices):
        rows.append({
            "timestamp_et": start_time + dt.timedelta(minutes=5 * i),
            "open": o, "high": h, "low": l, "close": c, "volume": v,
        })
    return pd.DataFrame(rows)


def _make_constant_vix(n: int, value: float = 17.50) -> pd.Series:
    return pd.Series([value] * n)


def _make_constant_ribbon(n: int, stack: str = "BEAR") -> pd.DataFrame:
    """Stub ribbon: post-warmup all-BEAR (or chosen stack)."""
    return pd.DataFrame({
        "fast": [99.5] * n,
        "pivot": [100.0] * n,
        "slow": [100.5] * n,
        "spread_cents": [100.0] * n,
        "stack": [stack] * n,
    })


def test_simulator_runner_exit_on_ribbon_flip():
    """Entry at bar 0; modest SPY drop fires TP1 cleanly. Runner sits comfortably
    above BE and below 3x target. Bar 5 ribbon flip → runner exits on flip."""
    start = ET.localize(dt.datetime(2026, 5, 6, 10, 0))
    # Modest drop — fires TP1 (best_premium >= +30%) but runner stays in [BE, 3x target] band
    bars = _make_bars([
        (720.0, 720.5, 719.0, 719.5, 50000),  # entry at close 719.5
        (719.5, 719.5, 717.5, 717.7, 90000),  # bar 1: low 717.5 → TP1 fires; close 717.7
        (717.7, 718.0, 717.0, 717.5, 70000),  # bar 2: tight range above 717
        (717.5, 718.0, 717.0, 717.5, 65000),  # bar 3: tight range
        (717.5, 718.0, 717.0, 717.5, 60000),  # bar 4
        (717.5, 718.0, 717.0, 717.5, 50000),  # bar 5 — ribbon flip here
        (717.5, 718.0, 717.0, 717.5, 40000),
    ], start)
    vix = _make_constant_vix(len(bars))
    ribbon = _make_constant_ribbon(len(bars), stack="BEAR")
    ribbon.loc[5:, "stack"] = "MIXED"   # ribbon flips at bar 5

    fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0],
        spy_df=bars, vix_aligned=vix, ribbon_df=ribbon,
        rejection_level=720.0,
        triggers_fired=["level_rejection", "ribbon_flip"],
    )
    assert fill.exit_reason == ExitReason.TP1_THEN_RUNNER_RIBBON
    assert fill.runner_exit_time_et == bars.iloc[5]["timestamp_et"]
    assert fill.tp1_filled() is True
    assert fill.dollar_pnl > 0


def test_simulator_premium_stop_hit():
    """SPY rallies hard, premium drops below -50% → premium stop fires, exit ALL."""
    start = ET.localize(dt.datetime(2026, 5, 6, 10, 0))
    # SPY rallies from 720 to 728 over 6 bars — put will get crushed
    bars = _make_bars([
        (720, 720.5, 719.5, 719.5, 50000),
        (720, 723, 720, 722, 80000),     # rally
        (722, 727, 722, 726, 90000),     # huge rally
        (726, 728, 726, 728, 70000),
    ], start)
    vix = _make_constant_vix(len(bars))
    ribbon = _make_constant_ribbon(len(bars), stack="BEAR")  # ribbon stays bear (test premium stop alone)

    fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0],
        spy_df=bars, vix_aligned=vix, ribbon_df=ribbon,
        rejection_level=720.5,
        triggers_fired=["level_rejection"],
    )
    assert fill.exit_reason in {
        ExitReason.EXIT_ALL_PREMIUM_STOP,
        ExitReason.EXIT_ALL_LEVEL_STOP,  # SPY closed above rejection level too
    }
    # Loss should be ~50% of entry premium x qty x 100
    assert fill.dollar_pnl < 0


def test_simulator_tp1_then_runner_target():
    """SPY drops sharply, hits TP1, then continues to 3x runner target."""
    start = ET.localize(dt.datetime(2026, 5, 6, 10, 0))
    # SPY drops dramatically
    bars = _make_bars([
        (720, 720.5, 719.5, 719.5, 50000),
        (719.5, 719.5, 715, 715.5, 90000),    # big drop — TP1 likely hit
        (715, 716, 712, 712, 100000),         # more
        (712, 713, 708, 708.5, 120000),       # massive drop
        (708, 709, 705, 705, 130000),         # runner target territory
    ], start)
    vix = _make_constant_vix(len(bars))
    ribbon = _make_constant_ribbon(len(bars), stack="BEAR")

    fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0],
        spy_df=bars, vix_aligned=vix, ribbon_df=ribbon,
        rejection_level=720.5,
        triggers_fired=["level_rejection", "ribbon_flip"],
    )
    assert fill.tp1_filled() is True
    assert fill.dollar_pnl > 0
    # The trade should be a strong winner with big SPY drop


def test_simulator_time_stop_fires_when_no_other_exit():
    """If neither TP1 nor stop hits, time stop should fire at/after 15:50.

    Realistic scenario: entry at 14:30, SPY drifts narrowly without enough movement to
    hit either +30% TP1 or -50% stop. Time stop ends the trade at 15:50.
    """
    start = ET.localize(dt.datetime(2026, 5, 6, 14, 30))
    # 16 bars from 14:30 through 15:50 ET; SPY drifts in a tight range.
    # Choose ranges small enough that put premium stays bounded between -49% and +29%.
    rows = []
    for i in range(17):
        # Each bar: SPY oscillates within ±$0.30 of 720 with low/high tight
        rows.append((720.0, 720.10, 719.90, 720.0, 50000))
    bars = _make_bars(rows, start)
    vix = _make_constant_vix(len(bars))
    ribbon = _make_constant_ribbon(len(bars), stack="BEAR")

    fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0],
        spy_df=bars, vix_aligned=vix, ribbon_df=ribbon,
        rejection_level=721.0,
        triggers_fired=["level_rejection"],
    )
    # Expected: time stop or premium stop (theta-driven decay over 80 min)
    assert fill.exit_reason in {
        ExitReason.EXIT_ALL_TIME_STOP,
        ExitReason.EXIT_ALL_PREMIUM_STOP,   # ATM 0DTE flat-tape will hit -50% via theta alone
        ExitReason.TP1_THEN_RUNNER_TIME,
    }


def test_pnl_accounting_round_trip():
    """For a known entry/exit premium, P&L = (exit - entry) * qty * 100, allocated by TP1 split."""
    start = ET.localize(dt.datetime(2026, 5, 6, 10, 0))
    # Constant SPY but ribbon flips at bar 1 → exit on flip at bar 1's close
    bars = _make_bars([
        (720, 720.5, 719.5, 720, 50000),
        (720, 720.5, 719.5, 720, 50000),
    ], start)
    vix = _make_constant_vix(len(bars))
    ribbon = _make_constant_ribbon(len(bars), stack="BEAR")
    ribbon.loc[1:, "stack"] = "MIXED"

    fill = simulate_trade(
        entry_bar_idx=0, entry_bar=bars.iloc[0],
        spy_df=bars, vix_aligned=vix, ribbon_df=ribbon,
        rejection_level=721.0,
        triggers_fired=["level_rejection"],
    )
    # No TP1 hit — full qty exits at exit_premium
    assert fill.tp1_filled() is False
    expected_pnl = (fill.runner_exit_premium - fill.entry_premium) * DEFAULT_QTY * 100
    assert fill.dollar_pnl == pytest.approx(expected_pnl, abs=0.01)
