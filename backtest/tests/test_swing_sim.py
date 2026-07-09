"""Guards for swing_sim.py (Phase-1 futures multiday swing simulator).

Covers: gap-aware fills (the load-bearing behavior -- a naive "always fill at
the nominal stop/target price" implementation must RED here), Wilder ATR math,
max-hold-days exit, DATA_END, and P&L point math vs CONTRACT-SPECS.md ($5/pt
MES, $2/pt MNQ). Run: pytest backtest/tests/test_swing_sim.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.swing_sim import wilder_atr, simulate_swing, simulate_buy_and_hold  # noqa: E402
from futures.instruments import MES, MNQ  # noqa: E402


def make_bars(ohlc: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """rows of (open, high, low, close); RangeIndex 0..n-1."""
    return pd.DataFrame(ohlc, columns=["open", "high", "low", "close"])


# ─── Gap-aware fills (the core behavior this module exists for) ───────────────

class TestGapAwareFills:
    def test_gap_through_stop_long_fills_at_open_not_stop_price(self):
        # Long entry 5900, stop_mult=1.5 * atr=20 -> stop = 5900 - 30 = 5870.
        # Bar 1 GAPS below the stop: opens at 5820 (no intrabar approach from above).
        bars = make_bars([
            (5900, 5910, 5895, 5905),   # entry bar
            (5820, 5825, 5810, 5815),   # gapped bar: open 5820 <= stop 5870
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=None, max_hold_bars=5)
        assert r.reason == "STOP"
        assert r.gapped is True
        assert r.exit_px == pytest.approx(5820.0), "must fill at the OPEN, not the nominal stop 5870"
        assert r.exit_px != pytest.approx(5870.0), "must NOT fill at the nominal stop price"
        # The gap fill is WORSE than the nominal stop would have been.
        assert r.exit_px < 5870.0

    def test_gap_through_stop_short_fills_at_open_not_stop_price(self):
        # Short entry 5900, stop = 5900 + 30 = 5930. Bar 1 gaps ABOVE the stop.
        bars = make_bars([
            (5900, 5905, 5890, 5895),
            (5980, 5985, 5975, 5978),   # gapped bar: open 5980 >= stop 5930
        ])
        r = simulate_swing("short", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=None, max_hold_bars=5)
        assert r.reason == "STOP"
        assert r.gapped is True
        assert r.exit_px == pytest.approx(5980.0)
        assert r.exit_px > 5930.0, "gap fill must be WORSE than the nominal stop for a short"

    def test_wrong_gap_implementation_would_red(self):
        """Non-vacuous per the build spec: a naive sim that always fills at the
        nominal stop price (ignoring the gap) would compute a DIFFERENT --
        and wrong -- dollar P&L than the correct gap-aware fill. This test
        pins the CORRECT number and proves the two are not equal."""
        bars = make_bars([
            (5900, 5910, 5895, 5905),
            (5820, 5825, 5810, 5815),  # 50pt gap below the 5870 nominal stop
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=None, max_hold_bars=5, qty=1,
                            cost_per_side_usd=2.50)
        correct_pts = 5820.0 - 5900.0        # -80
        wrong_pts_if_naive_stop_fill = 5870.0 - 5900.0  # -30 (what a buggy sim would report)
        assert r.pnl_pts == pytest.approx(correct_pts)
        assert r.pnl_pts != pytest.approx(wrong_pts_if_naive_stop_fill)
        correct_usd = correct_pts * MES.point_value - 2 * 2.50
        assert r.pnl_usd == pytest.approx(correct_usd)

    def test_gap_through_target_long_fills_at_open_better_than_target(self):
        # Long entry 5900, target = 5900 + 60 (target_mult=3.0*atr=20) = 5960.
        # Bar 1 gaps ABOVE target: opens at 6000.
        bars = make_bars([
            (5900, 5910, 5895, 5905),
            (6000, 6010, 5995, 6005),
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=5)
        assert r.reason == "TARGET"
        assert r.gapped is True
        assert r.exit_px == pytest.approx(6000.0)
        assert r.exit_px > 5960.0, "gap fill must be BETTER than the nominal target for a long"

    def test_no_gap_intrabar_stop_fills_at_exact_stop_price(self):
        # Stop = 5870. Bar 1 opens ABOVE the stop (5895) but its LOW touches 5865
        # intrabar -- no gap, so the fill must be at the exact stop level.
        bars = make_bars([
            (5900, 5910, 5895, 5905),
            (5895, 5898, 5865, 5880),
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=None, max_hold_bars=5)
        assert r.reason == "STOP"
        assert r.gapped is False
        assert r.exit_px == pytest.approx(5870.0)

    def test_entry_bar_itself_can_stop_out_same_bar(self):
        # Entry bar's own range takes out the stop (no separate "gap" bar needed).
        bars = make_bars([(5900, 5905, 5860, 5870)])  # low 5860 < stop 5870
        r = simulate_swing("long", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=None, max_hold_bars=5)
        assert r.reason == "STOP"
        assert r.gapped is False
        assert r.hold_bars == 0

    def test_stop_checked_before_target_same_bar(self):
        # Both stop (5870) and target (5960) inside one bar's range -- conservative: stop wins.
        bars = make_bars([
            (5900, 5910, 5895, 5905),
            (5900, 5970, 5860, 5900),
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=20.0, instrument=MES,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=5)
        assert r.reason == "STOP"


# ─── Wilder ATR ─────────────────────────────────────────────────────────────

class TestWilderATR:
    def test_matches_hand_calculation(self):
        # 5 bars, period=3. TR = [h-l, h-l, h-l, h-l, h-l] since no big gaps here.
        bars = make_bars([
            (100, 110, 90, 100),   # TR0 = 20
            (100, 108, 98, 105),   # TR1 = max(10, |108-100|=8, |98-100|=2) = 10
            (105, 115, 100, 110),  # TR2 = max(15, |115-105|=10, |100-105|=5) = 15
            (110, 112, 104, 108),  # TR3 = max(8, |112-110|=2, |104-110|=6) = 8
            (108, 120, 106, 115),  # TR4 = max(14, |120-108|=12, |106-108|=2) = 14
        ])
        atr = wilder_atr(bars, period=3)
        assert pd.isna(atr.iloc[0]) and pd.isna(atr.iloc[1])
        seed = (20 + 10 + 15) / 3.0
        assert atr.iloc[2] == pytest.approx(seed)
        atr3 = (seed * 2 + 8) / 3.0
        assert atr.iloc[3] == pytest.approx(atr3)
        atr4 = (atr3 * 2 + 14) / 3.0
        assert atr.iloc[4] == pytest.approx(atr4)

    def test_atr_positive_after_warmup(self):
        bars = make_bars([(100 + i, 105 + i, 95 + i, 100 + i) for i in range(20)])
        atr = wilder_atr(bars, period=14)
        assert (atr.iloc[13:] > 0).all()

    def test_atr_empty_bars(self):
        assert len(wilder_atr(make_bars([]), period=14)) == 0

    def test_atr_used_as_stop_produces_expected_distance(self):
        bars = make_bars([(100 + i, 105 + i, 95 + i, 100 + i) for i in range(20)])
        atr = wilder_atr(bars, period=14)
        entry_idx = 15
        a = float(atr.iloc[entry_idx - 1])
        long_bars = bars.iloc[entry_idx:entry_idx + 6].reset_index(drop=True)
        r = simulate_swing("long", 0, long_bars, atr_at_entry=a, instrument=MES,
                            stop_mult=1.5, target_mult=None, max_hold_bars=5)
        expected_stop = long_bars["open"].iloc[0] - 1.5 * a
        assert r.stop_px == pytest.approx(expected_stop)


# ─── Max-hold / DATA_END ───────────────────────────────────────────────────

class TestHoldHorizon:
    def test_max_hold_exit_at_time_when_nothing_hit(self):
        # Stop/target both far away; nothing fires in 3 bars -> TIME exit at bar 3's close.
        bars = make_bars([
            (5900, 5905, 5895, 5900),
            (5900, 5905, 5895, 5901),
            (5901, 5906, 5896, 5902),
            (5902, 5907, 5897, 5903),
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=3)
        assert r.reason == "TIME"
        assert r.hold_bars == 3
        assert r.exit_px == pytest.approx(5903.0)

    def test_data_end_when_bars_run_out_before_max_hold(self):
        bars = make_bars([
            (5900, 5905, 5895, 5900),
            (5900, 5905, 5895, 5901),
        ])
        r = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=5)
        assert r.reason == "DATA_END"
        assert r.exit_idx == 1
        assert r.exit_px == pytest.approx(5901.0)

    def test_zero_max_hold_exits_same_bar_close(self):
        bars = make_bars([(5900, 5905, 5895, 5903)])
        r = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=0)
        assert r.hold_bars == 0
        assert r.exit_px == pytest.approx(5903.0)

    def test_invalid_direction_raises(self):
        bars = make_bars([(100, 105, 95, 100)])
        with pytest.raises(ValueError):
            simulate_swing("sideways", 0, bars, atr_at_entry=10.0, instrument=MES)

    def test_invalid_atr_raises(self):
        bars = make_bars([(100, 105, 95, 100)])
        with pytest.raises(ValueError):
            simulate_swing("long", 0, bars, atr_at_entry=0.0, instrument=MES)
        with pytest.raises(ValueError):
            simulate_swing("long", 0, bars, atr_at_entry=float("nan"), instrument=MES)

    def test_entry_idx_out_of_range_raises(self):
        bars = make_bars([(100, 105, 95, 100)])
        with pytest.raises(ValueError):
            simulate_swing("long", 5, bars, atr_at_entry=10.0, instrument=MES)


# ─── P&L point math vs CONTRACT-SPECS.md ───────────────────────────────────

class TestPointMath:
    def test_mes_five_dollars_per_point(self):
        # 10pt long win on MES, 1 contract, no stop/target hit -> TIME at +10pts.
        bars = make_bars([(5900, 5901, 5899, 5900), (5900, 5911, 5899, 5910)])
        r = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=1,
                            cost_per_side_usd=0.0)
        assert r.pnl_pts == pytest.approx(10.0)
        assert r.pnl_usd == pytest.approx(10.0 * 5.0)  # $5/pt MES

    def test_mnq_two_dollars_per_point(self):
        bars = make_bars([(21000, 21001, 20999, 21000), (21000, 21030, 20999, 21020)])
        r = simulate_swing("long", 0, bars, atr_at_entry=200.0, instrument=MNQ,
                            stop_mult=1.5, target_mult=3.0, max_hold_bars=1,
                            cost_per_side_usd=0.0)
        assert r.pnl_pts == pytest.approx(20.0)
        assert r.pnl_usd == pytest.approx(20.0 * 2.0)  # $2/pt MNQ

    def test_qty_scales_linearly(self):
        bars = make_bars([(5900, 5901, 5899, 5900), (5900, 5911, 5899, 5910)])
        r1 = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                             max_hold_bars=1, qty=1, cost_per_side_usd=0.0)
        r3 = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                             max_hold_bars=1, qty=3, cost_per_side_usd=0.0)
        assert r3.pnl_usd == pytest.approx(r1.pnl_usd * 3)

    def test_commission_deducted_both_sides(self):
        bars = make_bars([(5900, 5901, 5899, 5900), (5900, 5911, 5899, 5910)])
        free = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                               max_hold_bars=1, qty=2, cost_per_side_usd=0.0)
        costed = simulate_swing("long", 0, bars, atr_at_entry=100.0, instrument=MES,
                                 max_hold_bars=1, qty=2, cost_per_side_usd=2.50)
        # 2 sides * $2.50 * 2 contracts = $10 round-turn cost.
        assert free.pnl_usd - costed.pnl_usd == pytest.approx(10.0)

    def test_short_direction_pnl_sign(self):
        bars = make_bars([(5900, 5901, 5899, 5900), (5900, 5901, 5889, 5890)])
        r = simulate_swing("short", 0, bars, atr_at_entry=100.0, instrument=MES,
                            max_hold_bars=1, cost_per_side_usd=0.0)
        assert r.pnl_pts == pytest.approx(10.0)  # short profits when price falls
        assert r.pnl_usd > 0


# ─── Buy-and-hold null helper ──────────────────────────────────────────────

class TestBuyAndHold:
    def test_long_hold_matches_open_to_close_delta(self):
        bars = make_bars([(5900, 5905, 5895, 5901), (5901, 5920, 5900, 5915),
                           (5915, 5918, 5910, 5912)])
        r = simulate_buy_and_hold("long", 0, bars, MES, hold_bars=2, cost_per_side_usd=0.0)
        assert r.pnl_pts == pytest.approx(5912.0 - 5900.0)
        assert r.reason == "TIME"

    def test_data_end_flag(self):
        bars = make_bars([(5900, 5905, 5895, 5901), (5901, 5920, 5900, 5915)])
        r = simulate_buy_and_hold("long", 0, bars, MES, hold_bars=10, cost_per_side_usd=0.0)
        assert r.reason == "DATA_END"
        assert r.exit_idx == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
