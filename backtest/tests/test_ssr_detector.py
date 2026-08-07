"""Guards for backtest/futures/ssr/detector.py (Builder 2, SSR battery).

Six required cases per the ROLE contract:
  1. textbook short  -- sweep, close-back, post-sweep LH pivot shift, retest+reaction -> 1 signal.
  2. mirrored long    -- the exact same fixture reflected around a price axis.
  3. no-shift timeout -- sweep with no BOS/pivot/displacement within shift_window_bars -> no signal.
  4. no-retest timeout -- shift confirmed (displacement mode) but price never re-enters
     the zone band within retest_window_bars -> no signal.
  5. no-look-ahead mutation -- mutating bars strictly AFTER the signal bar never changes
     the signal(s) at or before that bar.
  6. entry-window filter -- an otherwise-perfect setup whose reaction-close lands at
     16:00 ET (outside the default [03:00, 15:00) window) is suppressed.

Fixtures are hand-built directly (no dependency on Builder 1's levels.py::build_levels
or its session/period helpers) -- only the LevelSnapshot dataclass SHAPE is reused, via
a try/except fallback stub with identical fields + sweepable_highs()/sweepable_lows()
methods so this file never breaks if levels.py is mid-edit in another worktree.

All fixtures were calibrated against the real wilder_atr()/SSRDetector.run() (not
hand-derived ATR) -- see the module-level constants' comments for the exact mechanics
each bar is engineered to trigger.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backtest.futures.ssr.detector import SSRDetector, SSRParams, SSRSignal  # noqa: E402
from backtest.futures.swing_sim import wilder_atr  # noqa: E402

try:
    from backtest.futures.ssr.levels import LevelSnapshot  # noqa: E402
except ImportError:  # pragma: no cover -- fallback if levels.py is mid-edit elsewhere
    @dataclass(frozen=True)
    class LevelSnapshot:  # minimal stub mirroring backtest/futures/ssr/levels.py verbatim
        prev_day_high: Optional[float] = None
        prev_day_low: Optional[float] = None
        prev_week_high: Optional[float] = None
        prev_week_low: Optional[float] = None
        prev_4h_high: Optional[float] = None
        prev_4h_low: Optional[float] = None
        asia_high: Optional[float] = None
        asia_low: Optional[float] = None
        london_high: Optional[float] = None
        london_low: Optional[float] = None
        ny_high: Optional[float] = None
        ny_low: Optional[float] = None
        day_open: Optional[float] = None
        h4_open: Optional[float] = None

        def sweepable_highs(self) -> list[tuple[str, float]]:
            pairs = (("PDH", self.prev_day_high), ("PWH", self.prev_week_high),
                     ("PREV_4H_HIGH", self.prev_4h_high), ("ASIA_HIGH", self.asia_high),
                     ("LONDON_HIGH", self.london_high), ("NY_HIGH", self.ny_high))
            return [(n, p) for n, p in pairs if p is not None]

        def sweepable_lows(self) -> list[tuple[str, float]]:
            pairs = (("PDL", self.prev_day_low), ("PWL", self.prev_week_low),
                     ("PREV_4H_LOW", self.prev_4h_low), ("ASIA_LOW", self.asia_low),
                     ("LONDON_LOW", self.london_low), ("NY_LOW", self.ny_low))
            return [(n, p) for n, p in pairs if p is not None]


ET = "America/New_York"
_SNAPSHOT_FIELDS = (
    "prev_day_high", "prev_day_low", "prev_week_high", "prev_week_low",
    "prev_4h_high", "prev_4h_low", "asia_high", "asia_low",
    "london_high", "london_low", "ny_high", "ny_low", "day_open", "h4_open",
)


def _snapshot(**kwargs) -> LevelSnapshot:
    base = {f: None for f in _SNAPSHOT_FIELDS}
    base.update(kwargs)
    return LevelSnapshot(**base)


def _make_snapshots(n: int, **kwargs) -> list:
    """One constant LevelSnapshot repeated for every bar -- the fixture windows are
    short enough that the level never rolls to a new value mid-fixture (frozen
    dataclass, safe to share the single instance across all n rows)."""
    snap = _snapshot(**kwargs)
    return [snap] * n


def _mkbars(rows: list[tuple[float, float, float, float]], start: pd.Timestamp) -> pd.DataFrame:
    out = []
    t = start
    for o, h, l, c in rows:
        out.append({"timestamp_et": t, "open": o, "high": h, "low": l, "close": c, "volume": 1000.0})
        t = t + pd.Timedelta(minutes=15)
    return pd.DataFrame(out)


def _mirror(rows: list[tuple[float, float, float, float]], axis: float = 200.0):
    """Reflect a bar sequence around `axis` (price -> axis - price), swapping
    high/low so the OHLC invariant (high >= low) still holds. Used to build the
    LONG fixture as an exact mirror of the SHORT one."""
    return [(axis - o, axis - l, axis - h, axis - c) for (o, h, l, c) in rows]


def _run(bars: pd.DataFrame, snapshots: list, params: SSRParams) -> list[SSRSignal]:
    atr = wilder_atr(bars, period=14)
    return SSRDetector(params).run(bars, snapshots, atr)


DEFAULT_PARAMS = SSRParams(zone_atr_mult=0.5, sweep_atr_mult=0.25,
                            shift_window_bars=16, retest_window_bars=16)

# 20 flat warmup bars (range 1.0, no gaps) seed Wilder-14 ATR at exactly 1.0 before
# anything interesting happens; flat/equal highs never register as swing points
# (find_swing_points' left-side check is strict `<`), so the warmup contributes
# nothing to the swing/structure read either.
_WARMUP = [(100.0, 100.5, 99.5, 100.0)] * 20

# The "textbook short" sequence (test 1): idx20 sweeps PDH=110 (pierce >0.25*ATR,
# closes back below same bar) -> SWEPT. idx23 prints a swing high at 109.9, LOWER
# than idx20's swing high (111.5) -> labeled "LH", confirmed at idx23+swing_window
# (2) = idx25 -> SHIFTED (shift_mode="pivot"; idx24 is deliberately kept under the
# displacement threshold so the pivot path is the ONLY thing that can fire first).
# idx26-28 continue down: no signal), then idx29-31 rally back up; idx32 touches
# back into the zone band [110-0.5*ATR, 110+0.5*ATR] and closes down -> SIGNAL.
_SHORT_ROWS = _WARMUP + [
    (108.0, 111.5, 107.5, 109.5),   # 20  SWEEP (pierce+close-back, same bar)
    (109.5, 109.6, 108.5, 109.0),   # 21
    (109.0, 109.2, 108.0, 108.3),   # 22
    (108.3, 109.9, 108.0, 109.5),   # 23  LH pivot candidate (109.9 < 111.5)
    (109.5, 109.6, 108.3, 107.8),   # 24  range 1.3 -- kept under displacement thresh
    (107.8, 108.0, 106.5, 106.8),   # 25  <- LH pivot CONFIRMS here (23+swing_window)
    (106.8, 107.0, 104.0, 104.5),   # 26
    (104.5, 105.0, 103.5, 104.0),   # 27
    (104.0, 105.0, 103.0, 103.5),   # 28
    (103.5, 106.0, 103.5, 105.5),   # 29  rally starts
    (105.5, 108.0, 105.5, 107.8),   # 30
    (107.8, 109.9, 107.8, 109.6),   # 31
    (109.6, 110.4, 109.2, 109.3),   # 32  retest touch + down reaction close -> SIGNAL
]
_SIGNAL_BAR_IDX = 32
_START = pd.Timestamp("2026-06-01 05:00", tz=ET)  # bar 32 lands at 13:00 ET (inside window)


class TestSSRDetectorTextbookCases:
    def test_textbook_short_sweep_shift_retest(self):
        bars = _mkbars(_SHORT_ROWS, _START)
        snaps = _make_snapshots(len(bars), prev_day_high=110.0)
        sigs = _run(bars, snaps, DEFAULT_PARAMS)

        assert len(sigs) == 1, sigs
        sig = sigs[0]
        assert sig.bar_index == _SIGNAL_BAR_IDX
        assert sig.direction == "short"
        assert sig.level_name == "PDH"
        assert sig.level_price == 110.0
        assert sig.sweep_extreme == 111.5           # the sweep bar's high (idx20)
        assert sig.entry_ref_close == pytest.approx(109.3)
        # stop = sweep_extreme + stop_atr_buffer(0.15) * ATR[signal_bar] -- must be
        # ABOVE the sweep extreme for a short (stop sits beyond the liquidity grab).
        assert sig.stop_price > sig.sweep_extreme
        assert sig.stop_price == pytest.approx(111.7728544276987)
        assert sig.state_trace == {"swept_at_index": 20, "shifted_at_index": 25,
                                    "shift_mode": "pivot"}

    def test_mirrored_long_sweep_shift_retest(self):
        """The exact short fixture reflected around price=200 -- a sell-side sweep
        of PDL=90, HL pivot shift, retest+up-reaction -> one long signal, mirror
        image of the short case in every field."""
        long_rows = _mirror(_SHORT_ROWS)
        bars = _mkbars(long_rows, _START)
        snaps = _make_snapshots(len(bars), prev_day_low=90.0)
        sigs = _run(bars, snaps, DEFAULT_PARAMS)

        assert len(sigs) == 1, sigs
        sig = sigs[0]
        assert sig.bar_index == _SIGNAL_BAR_IDX
        assert sig.direction == "long"
        assert sig.level_name == "PDL"
        assert sig.level_price == 90.0
        assert sig.sweep_extreme == 88.5             # 200 - 111.5, the mirrored sweep low
        assert sig.entry_ref_close == pytest.approx(200.0 - 109.3)
        # stop = sweep_extreme - stop_atr_buffer * ATR -- BELOW the sweep extreme for a long.
        assert sig.stop_price < sig.sweep_extreme
        assert sig.stop_price == pytest.approx(200.0 - 111.7728544276987)
        assert sig.state_trace == {"swept_at_index": 20, "shifted_at_index": 25,
                                    "shift_mode": "pivot"}

    def test_no_shift_timeout_produces_no_signal(self):
        """Sweep fires at idx20, then 20 flat/no-trend bars follow (no BOS, no
        confirmable pivot, no displacement) -- shift_window_bars=16 expires and the
        episode resets to IDLE without ever reaching SHIFTED."""
        rows = _SHORT_ROWS[:21] + [(108.0, 108.5, 107.5, 108.0)] * 20
        bars = _mkbars(rows, _START)
        snaps = _make_snapshots(len(bars), prev_day_high=110.0)
        sigs = _run(bars, snaps, DEFAULT_PARAMS)
        assert sigs == []

    def test_no_retest_timeout_produces_no_signal(self):
        """Sweep at idx20, an immediate oversized displacement bar at idx21 shifts
        the episode (mode='displacement'), then price drifts steadily AWAY from the
        zone band for 20 more bars -- retest_window_bars=16 expires with no
        retest+reaction ever occurring."""
        disp_rows = [
            (108.0, 111.5, 107.5, 109.5),   # 20 SWEEP
            (109.0, 109.2, 104.0, 104.5),   # 21 displacement (range 5.2 >> 1.5*ATR)
        ]
        far_away = [(104.5 - 0.3 * k, 104.8 - 0.3 * k, 104.0 - 0.3 * k, 104.3 - 0.3 * k)
                    for k in range(20)]
        rows = _SHORT_ROWS[:20] + disp_rows + far_away
        bars = _mkbars(rows, _START)
        snaps = _make_snapshots(len(bars), prev_day_high=110.0)
        sigs = _run(bars, snaps, DEFAULT_PARAMS)
        assert sigs == []

    def test_entry_window_filter_rejects_1600_et_signal(self):
        """Identical mechanics to the textbook short, just shifted so the signal
        bar's reaction close lands at 16:00 ET -- outside the default
        [03:00, 15:00) entry window -- so no signal is emitted even though the
        sweep/shift/retest sequence completes exactly as in test 1."""
        start_1600 = pd.Timestamp("2026-06-01 08:00", tz=ET)  # bar32 = 08:00 + 8h = 16:00
        bars = _mkbars(_SHORT_ROWS, start_1600)
        assert bars["timestamp_et"].iloc[_SIGNAL_BAR_IDX].time().strftime("%H:%M") == "16:00"
        snaps = _make_snapshots(len(bars), prev_day_high=110.0)
        sigs = _run(bars, snaps, DEFAULT_PARAMS)
        assert sigs == []

    def test_no_look_ahead_mutation(self):
        """Run the textbook short fixture, then mutate every bar strictly AFTER the
        signal bar into something wildly different (a second, much larger sweep)
        and re-run. Every signal at bar_index <= the original signal bar must be
        byte-identical across both runs -- proving the detector never used bars
        after the index it signals on (C6)."""
        tail_original = [
            (109.3, 109.4, 108.0, 108.2),
            (108.2, 112.0, 108.0, 111.5),
            (111.5, 111.6, 106.0, 106.5),
        ]
        tail_mutated = [
            (200.0, 205.0, 195.0, 201.0),
            (201.0, 250.0, 190.0, 240.0),
            (240.0, 245.0, 100.0, 105.0),
        ]
        rows_a = _SHORT_ROWS + tail_original
        rows_b = _SHORT_ROWS + tail_mutated
        assert rows_a[:_SIGNAL_BAR_IDX + 1] == rows_b[:_SIGNAL_BAR_IDX + 1]  # fixture sanity

        bars_a = _mkbars(rows_a, _START)
        bars_b = _mkbars(rows_b, _START)
        snaps_a = _make_snapshots(len(bars_a), prev_day_high=110.0)
        snaps_b = _make_snapshots(len(bars_b), prev_day_high=110.0)

        sigs_a = _run(bars_a, snaps_a, DEFAULT_PARAMS)
        sigs_b = _run(bars_b, snaps_b, DEFAULT_PARAMS)

        sigs_a_upto = [s for s in sigs_a if s.bar_index <= _SIGNAL_BAR_IDX]
        sigs_b_upto = [s for s in sigs_b if s.bar_index <= _SIGNAL_BAR_IDX]
        assert sigs_a_upto == sigs_b_upto
        assert len(sigs_a_upto) == 1  # sanity: the mutation test isn't vacuously true
