"""Drift guard: feed_divergence_f10_f7's LOCAL filter mirrors must agree with
backtest/lib/filters.py (buyer_pressure_bar_v11 / _bullish_volume_divergence_failed)
on a synthetic bar battery. The tool keeps local copies so it never imports the
trading path; this test is the no-drift contract (OP #4). Runs unconditionally --
nothing here is staged."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
for _p in (str(BACKTEST),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import filters  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "feed_divergence_f10_f7", BACKTEST / "tools" / "feed_divergence_f10_f7.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def _mk(bars):
    """bars: list of (o, h, l, c, v)."""
    return [{"et": None, "o": o, "h": h, "l": l, "c": c, "v": v}
            for (o, h, l, c, v) in bars]


def _df(bars):
    return pd.DataFrame(
        [{"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
          "volume": b["v"]} for b in bars])


# 24-bar battery: flat warmup then a green surge, a green low-vol bar, a red bar,
# a green bar after a red high-vol recovery (f7 shape), boundary-equal volumes.
BATTERY = _mk(
    [(100, 101, 99, 100.5, 1000)] * 20
    + [
        (100.5, 102, 100.4, 101.8, 2500),   # green surge -> f10 pass
        (101.8, 102.0, 101.0, 101.2, 2600),  # red recovery vol>=breakout -> f7 fires
        (101.2, 101.9, 101.1, 101.5, 600),   # green low-vol -> f10 vol-block
        (101.5, 101.6, 101.4, 101.55, 700),  # green, vol 0.7x-boundary probe
    ])


class TestF10Mirror:
    @pytest.mark.parametrize("i", range(2, len(BATTERY)))
    def test_agrees_with_filters(self, i):
        df = _df(BATTERY)
        want = filters.buyer_pressure_bar_v11(
            df.iloc[i], filters.vol_baseline_20bar(df, i), vol_mult=0.7)
        got, _, _ = tool.f10_pass(BATTERY, i, vol_mult=0.7)
        assert got == want, f"bar {i}: tool={got} filters={want}"

    def test_boundary_vol_exactly_mult_times_baseline_passes(self):
        # filters: `vol < mult*base` blocks, so vol == mult*base passes -- pin >= not >
        bars = _mk([(100, 101, 99, 100.5, 1000)] * 20
                   + [(100.5, 101, 100.4, 100.9, 700)])  # exactly 0.7 * 1000
        got, _, _ = tool.f10_pass(bars, 20, vol_mult=0.7)
        df = _df(bars)
        want = filters.buyer_pressure_bar_v11(
            df.iloc[20], filters.vol_baseline_20bar(df, 20), vol_mult=0.7)
        assert got is True and want is True


class TestF7Mirror:
    @pytest.mark.parametrize("i", range(2, len(BATTERY)))
    def test_agrees_with_filters(self, i):
        df = _df(BATTERY)
        want = filters._bullish_volume_divergence_failed(df, i)
        got = tool.f7_fail(BATTERY, i)
        assert got == want, f"bar {i}: tool={got} filters={want}"

    def test_equal_volume_recovery_still_fires(self):
        # filters: `rec.volume >= bo.volume` -- equality fires; pin >= not >
        bars = _mk([(100, 101, 99, 100.5, 1000)] * 3
                   + [(100.5, 102, 100.4, 101.8, 2000),   # green breakout
                      (101.8, 101.9, 101.0, 101.1, 2000)])  # red, EQUAL vol
        df = _df(bars)
        assert tool.f7_fail(bars, 4) is True
        assert filters._bullish_volume_divergence_failed(df, 4) is True
