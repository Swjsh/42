"""Seed A -- RIBBON_REJECTION_WICK re-expressed on MES daily bars (swing horizon).

Reuses the SPY-validated detector verbatim:
`backtest/lib/watchers/ribbon_rejection_wick_detector.py::detect_both()`.
Per FUTURES-REVIVAL-PLAN-2026-07-02.md section 2c seed 1: "re-express
ribbon_rejection_wick short signals on MES at swing horizon... adapt price
scale, MES points not SPY dollars."

PRICE-SCALE ADAPTATION (disclosed):
  The detector's structural logic (ribbon band, wick fraction, structural
  break, stack filter) is entirely RELATIVE/scale-free -- it operates on
  whatever OHLC units it's given, so feeding it raw MES index points (not
  converted through spy_to_index) is correct and requires no math, only
  parameter rescaling for the two ABSOLUTE-unit knobs:
    close_margin_dollars: 0.01 (SPY cents) -> 0.25 (MES 1 tick)
    min_bar_range_dollars: 0.10 (SPY)      -> 5.00 (MES, ~few ticks; at daily
        scale this is a near-no-op filter -- daily ranges run 20-150+ points --
        kept only to reject degenerate zero-range bars, e.g. halt days)

NOT PORTABLE -- disclosed and disabled, not faked:
  `vol_mult_min` (break-bar volume >= K x TODAY'S PRIOR RTH-bar median) has no
  meaning at daily granularity -- there is exactly ONE bar per day, so "prior
  bars today" is always empty and the internal ratio always returns 0.0 (see
  detector's `_break_bar_vol_ratio`, `len(today_prior) < vol_median_min_bars`
  guard). Grid fixes vol_mult_min=0.0 for every combo (filter off) rather than
  emitting zero signals under a K>0 label that would misrepresent the test.

Grid (8 combos, matches the SPY battery's BH-FDR-survivor knob RANGE, not its
exact values -- lookback/above-lookback are rescaled from 5m-bar counts to
daily-bar counts, a genuinely different unit):
  wick_frac_min in {0.35, 0.5} (scale-free ratio, portable as-is)
  break_lookback_bars in {5, 10} daily bars (~1-2 weeks; SPY's 6/12 5m-bars = 30/60min)
  stack_filter in {"not_flipped", "any"}
Both bear (short) and bull (long) mirrors run for every combo -- battery
discipline mandates both directions reported, not just the short cohort.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(_REPO / "backtest"))

from lib.watchers.ribbon_rejection_wick_detector import detect_both, RRWParams  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

WICK_FRAC_MIN = (0.35, 0.5)
BREAK_LOOKBACK_BARS = (5, 10)
STACK_FILTER = ("not_flipped", "any")
ABOVE_LOOKBACK_BARS = 40          # fixed, disclosed (~8wk at daily) -- not gridded
CLOSE_MARGIN_PTS = 0.25           # 1 MES tick
MIN_BAR_RANGE_PTS = 5.0           # a few ticks; near-no-op at daily scale (disclosed)


def build_grid() -> list[dict]:
    grid = []
    for wfm in WICK_FRAC_MIN:
        for lb in BREAK_LOOKBACK_BARS:
            for sf in STACK_FILTER:
                grid.append({"wick_frac_min": wfm, "break_lookback_bars": lb,
                             "stack_filter": sf})
    assert len(grid) == 8
    return grid


def _params_for(combo: dict) -> RRWParams:
    return RRWParams(
        wick_frac_min=combo["wick_frac_min"],
        break_lookback_bars=combo["break_lookback_bars"],
        vol_mult_min=0.0,  # disabled -- see module docstring, NOT portable to daily bars
        require_stack_not_flipped=(combo["stack_filter"] == "not_flipped"),
        close_margin_dollars=CLOSE_MARGIN_PTS,
        above_lookback_bars=ABOVE_LOOKBACK_BARS,
        min_bar_range_dollars=MIN_BAR_RANGE_PTS,
        vol_median_min_bars=3,
    )


def generate_signals(bars: pd.DataFrame, grid: list[dict] | None = None) -> pd.DataFrame:
    """bars: daily (or 4h-of-RTH) OHLCV frame, RangeIndex, columns timestamp_et/
    open/high/low/close/volume (the exact schema `data.resample_daily` emits).
    Returns one row per (combo, direction, fired bar)."""
    if grid is None:
        grid = build_grid()
    if len(bars) == 0:
        return pd.DataFrame(columns=["combo_id", "wick_frac_min", "break_lookback_bars",
                                      "stack_filter", "signal_bar_idx", "direction",
                                      "wick_frac", "bars_since_break", "stack_at_signal"])
    ribbon_df = compute_ribbon(bars["close"])
    rows = []
    for combo in grid:
        combo_id = (f"rrw_w{combo['wick_frac_min']}_lb{combo['break_lookback_bars']}"
                    f"_{combo['stack_filter']}")
        params = _params_for(combo)
        for idx in range(2, len(bars)):
            for sig in detect_both(bars, idx, params, ribbon_df=ribbon_df):
                rows.append({
                    "combo_id": combo_id, **combo,
                    "signal_bar_idx": idx,
                    "direction": "short" if sig["direction"] == "bearish" else "long",
                    "wick_frac": sig["wick_frac"],
                    "bars_since_break": sig["bars_since_break"],
                    "stack_at_signal": sig["stack_at_signal"],
                })
    return pd.DataFrame(rows, columns=["combo_id", "wick_frac_min", "break_lookback_bars",
                                        "stack_filter", "signal_bar_idx", "direction",
                                        "wick_frac", "bars_since_break", "stack_at_signal"])


__all__ = ["build_grid", "generate_signals", "CLOSE_MARGIN_PTS", "MIN_BAR_RANGE_PTS"]
