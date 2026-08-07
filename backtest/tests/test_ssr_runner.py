"""Guards for backtest/futures/ssr/backtest_runner.py (SSR battery trade runner).

Synthetic bars + stub signal/snapshot objects only -- NO dependence on
detector.py/levels.py internals (those are sibling, parallel-built modules;
this file exercises backtest_runner.py's own contract in isolation).

Covers: entry-at-next-bar-open, the same-bar stop/tp1 tie-break inherited
from futures_sim.simulate_futures (stop checked first), 16:55 ET truncation,
the one-open-position-per-instrument rule, and runner-target selection
(nearest opposing level beyond tp1, else 3R fallback).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ssr_runner.py -v
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
_BACKTEST_DIR = _REPO / "backtest"
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))

from futures.ssr import backtest_runner  # noqa: E402
from futures.ssr.backtest_runner import run_trades, future_bars_through_flat  # noqa: E402
from futures.instruments import MES  # noqa: E402

TZ = "America/New_York"


@dataclass
class StubSignal:
    """Duck-types detector.SSRSignal's fields (ts_et, bar_index, direction,
    level_name, level_price, sweep_extreme, stop_price, entry_ref_close,
    state_trace) without importing detector.py."""
    ts_et: pd.Timestamp
    bar_index: int
    direction: str
    level_name: str
    level_price: float
    sweep_extreme: float
    stop_price: float
    entry_ref_close: float
    state_trace: dict = field(default_factory=dict)


@dataclass
class StubSnapshot:
    """Duck-types levels.LevelSnapshot's all_levels() -> list[(name, price)]."""
    levels: list

    def all_levels(self):
        return self.levels


def make_flat_bars(start_et: str = "2026-08-05 09:00", n: int = 10,
                    freq_minutes: int = 15, price: float = 100.0) -> pd.DataFrame:
    """Chronological RangeIndex 0..n-1 bars, tight range (never touches a
    TP1/runner that's several R away) so trades resolve to time_exit unless
    a test deliberately overrides specific rows."""
    ts = pd.date_range(start=pd.Timestamp(start_et, tz=TZ), periods=n, freq=f"{freq_minutes}min")
    return pd.DataFrame({
        "timestamp_et": ts,
        "open": [price] * n, "high": [price + 0.5] * n,
        "low": [price - 0.5] * n, "close": [price] * n,
        "volume": [1000] * n,
    })


def make_signal(bars: pd.DataFrame, bar_index: int, direction: str = "long",
                 stop_price: float = 95.0, level_name: str = "PDL") -> StubSignal:
    return StubSignal(
        ts_et=bars["timestamp_et"].iloc[bar_index], bar_index=bar_index, direction=direction,
        level_name=level_name, level_price=stop_price, sweep_extreme=stop_price - 1.0,
        stop_price=stop_price, entry_ref_close=float(bars["close"].iloc[bar_index]),
        state_trace={"shift_mode": "BOS"},
    )


# --- 1. entry-at-next-bar-open -------------------------------------------

def test_entry_is_next_bar_open():
    bars = make_flat_bars(n=10)
    sig = make_signal(bars, bar_index=2, stop_price=95.0)
    snapshots = [None] * len(bars)
    trades = run_trades(bars, snapshots, [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert len(trades) == 1
    assert trades[0]["entry"] == pytest.approx(float(bars["open"].iloc[3]))
    assert trades[0]["ts_entry_et"] == bars["timestamp_et"].iloc[3]


def test_signal_on_last_bar_has_no_next_bar_is_skipped():
    bars = make_flat_bars(n=5)
    sig = make_signal(bars, bar_index=4, stop_price=95.0)  # last bar -- no next open
    stats = {}
    trades = run_trades(bars, [None] * len(bars), [sig], MES, atr=pd.Series([1.0] * len(bars)), stats=stats)
    assert trades == []
    assert stats["skipped_no_next_bar"] == 1


# --- 2. same-bar stop-and-tp1 conflict: futures_sim checks STOP first -----

def test_same_bar_stop_and_tp1_conflict_resolves_stop_first():
    bars = make_flat_bars(n=5)
    # Entry bar (index 1) spans both the stop (95) and tp1 (100 + 1.5*5 = 107.5).
    bars.loc[1, ["open", "high", "low", "close"]] = [100.0, 110.0, 90.0, 100.0]
    sig = make_signal(bars, bar_index=0, stop_price=95.0)
    trades = run_trades(bars, [None] * len(bars), [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert len(trades) == 1
    # futures_sim.simulate_futures checks `lo <= stop` BEFORE `hi >= tp1` for
    # longs -- a bar that satisfies both resolves as a full stop-out, not tp1.
    assert trades[0]["outcome"] == "stopped"
    assert trades[0]["net"] < 0


def test_same_bar_stop_and_tp1_conflict_short_resolves_stop_first():
    bars = make_flat_bars(n=5)
    # Short: entry 100, stop 105 (R=5, tp1 = 100 - 7.5 = 92.5). Entry bar
    # spans both: high 108 (>= stop 105) and low 85 (<= tp1 92.5).
    bars.loc[1, ["open", "high", "low", "close"]] = [100.0, 108.0, 85.0, 100.0]
    sig = make_signal(bars, bar_index=0, direction="short", stop_price=105.0)
    trades = run_trades(bars, [None] * len(bars), [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert len(trades) == 1
    assert trades[0]["outcome"] == "stopped"
    assert trades[0]["net"] < 0


# --- 3. truncation: no bar after 16:55 ET reaches the sim ------------------

def test_future_bars_through_flat_excludes_bars_after_1655_et():
    ts = pd.date_range(start=pd.Timestamp("2026-08-05 16:30", tz=TZ), periods=6, freq="15min")
    bars = pd.DataFrame({"timestamp_et": ts, "open": [100.0] * 6, "high": [100.5] * 6,
                          "low": [99.5] * 6, "close": [100.0] * 6, "volume": [1] * 6})
    fb = future_bars_through_flat(bars, entry_idx=0, ts_et=ts[0])
    assert len(fb) == 2  # 16:30, 16:45 only -- 17:00 exceeds the 16:55 cutoff
    assert (fb["timestamp_et"] <= pd.Timestamp("2026-08-05 16:55", tz=TZ)).all()


def test_run_trades_end_to_end_truncates_at_1655_et():
    ts = pd.date_range(start=pd.Timestamp("2026-08-05 16:15", tz=TZ), periods=6, freq="15min")
    bars = pd.DataFrame({"timestamp_et": ts, "open": [100.0] * 6, "high": [100.5] * 6,
                          "low": [99.5] * 6, "close": [100.0] * 6, "volume": [1] * 6})
    sig = make_signal(bars, bar_index=0, stop_price=95.0)  # entry bar idx1 (16:30)
    trades = run_trades(bars, [None] * len(bars), [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert len(trades) == 1
    # Bars <=16:55 from entry(idx1) are idx1(16:30) and idx2(16:45) -> 2 rows,
    # never triggers stop/tp1 (flat range) -> time_exit at the last in-window
    # bar -> bars_held == 1 (0-based offset within the 2-row future_bars).
    assert trades[0]["bars_held"] == 1
    assert trades[0]["ts_entry_et"] == ts[1]


# --- 4. one-open-position-per-instrument rule -------------------------------

def test_overlapping_signal_skipped_while_position_open():
    bars = make_flat_bars(n=10)
    sig1 = make_signal(bars, bar_index=0, stop_price=95.0)   # entry idx1, flat bars -> time_exit at idx9
    sig2 = make_signal(bars, bar_index=1, stop_price=96.0)   # entry idx2, while sig1's position is open
    stats = {}
    trades = run_trades(bars, [None] * len(bars), [sig1, sig2], MES,
                         atr=pd.Series([1.0] * len(bars)), stats=stats)
    assert len(trades) == 1
    assert stats["skipped_while_open"] == 1


def test_signal_after_prior_exit_is_taken():
    bars = make_flat_bars(n=6)
    # sig1 stops out on its OWN entry bar (idx1) so the position closes immediately.
    bars.loc[1, ["open", "high", "low", "close"]] = [100.0, 100.5, 90.0, 100.0]
    sig1 = make_signal(bars, bar_index=0, stop_price=95.0)
    sig2 = make_signal(bars, bar_index=2, stop_price=95.0)   # entry idx3, well after sig1's exit at idx1
    stats = {}
    trades = run_trades(bars, [None] * len(bars), [sig1, sig2], MES,
                         atr=pd.Series([1.0] * len(bars)), stats=stats)
    assert len(trades) == 2
    assert stats["skipped_while_open"] == 0


# --- 5. runner: nearest opposing level beyond tp1, else 3R fallback --------

def test_runner_is_nearest_level_beyond_tp1():
    bars = make_flat_bars(n=5)
    sig = make_signal(bars, bar_index=0, stop_price=95.0)
    # entry = bars.open[1] = 100.0, R=5, tp1 = 107.5. Levels: one below tp1
    # (excluded), one just beyond (nearest), one far beyond (not nearest).
    snapshots = [StubSnapshot(levels=[("PDH", 103.0), ("NY_HIGH", 109.0), ("PWH", 120.0)])] + [None] * 4
    trades = run_trades(bars, snapshots, [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert trades[0]["runner"] == pytest.approx(109.0)
    assert trades[0]["runner_source"] == "level"


def test_runner_falls_back_to_3r_when_no_level_beyond_tp1():
    bars = make_flat_bars(n=5)
    sig = make_signal(bars, bar_index=0, stop_price=95.0)
    # tp1 = 107.5; both levels sit below it -> no candidate -> 3R fallback.
    snapshots = [StubSnapshot(levels=[("PDH", 101.0), ("NY_HIGH", 103.0)])] + [None] * 4
    trades = run_trades(bars, snapshots, [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert trades[0]["runner"] == pytest.approx(100.0 + 3.0 * 5.0)
    assert trades[0]["runner_source"] == "fallback_3r"


def test_runner_capped_at_5r_even_with_a_far_level():
    bars = make_flat_bars(n=5)
    sig = make_signal(bars, bar_index=0, stop_price=95.0)
    # entry=100, R=5, tp1=107.5, 5R cap = 125.0. Nearest-beyond-tp1 level is 200 (>> cap).
    snapshots = [StubSnapshot(levels=[("PWH", 200.0)])] + [None] * 4
    trades = run_trades(bars, snapshots, [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert trades[0]["runner"] == pytest.approx(100.0 + 5.0 * 5.0)
    assert trades[0]["runner_source"] == "capped_5r"


def test_short_runner_is_nearest_level_beyond_tp1():
    bars = make_flat_bars(n=5)
    sig = make_signal(bars, bar_index=0, direction="short", stop_price=105.0)
    # entry=100, R=5, tp1 = 100 - 7.5 = 92.5. Nearest level below tp1 -> 90.
    snapshots = [StubSnapshot(levels=[("PDL", 90.0), ("NY_LOW", 80.0), ("PWL", 95.0)])] + [None] * 4
    trades = run_trades(bars, snapshots, [sig], MES, atr=pd.Series([1.0] * len(bars)))
    assert trades[0]["runner"] == pytest.approx(90.0)
    assert trades[0]["runner_source"] == "level"


# --- degenerate-R guard (bonus coverage for the skip contract) -------------

def test_degenerate_r_below_one_tick_is_skipped_and_counted():
    bars = make_flat_bars(n=5)
    entry_next_open = float(bars["open"].iloc[1])
    sig = make_signal(bars, bar_index=0, stop_price=entry_next_open - (MES.tick_size / 2.0))
    stats = {}
    trades = run_trades(bars, [None] * len(bars), [sig], MES, atr=pd.Series([1.0] * len(bars)), stats=stats)
    assert trades == []
    assert stats["skipped_degenerate"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
