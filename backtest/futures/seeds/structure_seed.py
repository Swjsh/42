"""Seed C -- BOS/CHoCH market structure as a STANDALONE tradeable signal, MES
4h-of-RTH bars. Per FUTURES-REVIVAL-PLAN section 2c seed 3: "Structure/level
reads: market_structure.py BOS/CHoCH... at daily/4h scale... trade in the
break direction."

Reuses `crypto.lib.market_structure` verbatim (`find_swing_points` +
`walk_structure`) -- the SAME primitive already used elsewhere in this repo
as a daily FILTER on other signals (`backtest/futures/analysis/
PHASE1-swing-battery/swing_battery.py::build_daily_context`, 2026-07-02).
THIS seed is genuinely new: structure fires here are the ENTRY TRIGGER
itself (trade in the break direction), not a confirmation filter on a
different signal -- that combination was never tested by the prior battery
(its "Seed C" used daily structure only to gate seeds A/B; see that battery's
RESULTS.md finding #4: only 39 daily structure events in 18mo, never
independently traded).

No-look-ahead: `walk_structure`'s confirmation-delay design means a swing at
bar_index only becomes a usable BREAK REFERENCE starting at bar_index+window,
so any StructureEvent's `break_index` never depends on bars after itself --
safe to run over the full historical array once (see
`backtest/tests/test_swing_seeds.py::TestStructureSeedNoLookahead` for the
regression proof: mutating bars strictly after index k never changes any
event with break_index <= k).

Grid (6 combos): window (fractal pivot bars-per-side) in {2, 3} x
trade_on in {"BOS", "CHoCH", "BOTH"}. Direction = the event's own
bullish/bearish read (both directions reported).
"""
from __future__ import annotations

import sys
from datetime import timezone
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import walk_structure  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

WINDOWS = (2, 3)
TRADE_ON = ("BOS", "CHoCH", "BOTH")
BAR_GRANULARITY_SECONDS = 4 * 3600  # nominal; not used by walk_structure's logic


def bars_df_to_bar_objects(bars: pd.DataFrame) -> list[Bar]:
    """4h-of-RTH (or daily) OHLCV frame -> immutable crypto.lib.bar.Bar objects,
    tz-aware UTC (Bar's invariant)."""
    out = []
    for row in bars.itertuples(index=False):
        ts = row.timestamp_et
        ts_utc = ts.tz_convert(timezone.utc) if ts.tzinfo is not None else ts.tz_localize(timezone.utc)
        out.append(Bar(open_time=ts_utc, open=float(row.open), high=float(row.high),
                        low=float(row.low), close=float(row.close),
                        volume=float(getattr(row, "volume", 0) or 0),
                        granularity_seconds=BAR_GRANULARITY_SECONDS, source="mes_4h_rth"))
    return out


def build_grid() -> list[dict]:
    grid = []
    for w in WINDOWS:
        for t in TRADE_ON:
            grid.append({"window": w, "trade_on": t})
    assert len(grid) == 6
    return grid


def generate_signals(bars: pd.DataFrame, grid: list[dict] | None = None) -> pd.DataFrame:
    """bars: 4h-of-RTH (or daily) OHLCV frame, RangeIndex 0..n-1. Signal fires
    at `break_index` (the bar whose CLOSE confirmed the break); entry is
    break_index + 1's open (next-bar convention, consistent with the other
    seeds)."""
    if grid is None:
        grid = build_grid()
    bar_objs = bars_df_to_bar_objects(bars)
    events_by_window: dict[int, tuple] = {}
    rows = []
    for combo in grid:
        w = combo["window"]
        if w not in events_by_window:
            swings = find_swing_points(bar_objs, window=w, inclusive_right=True)
            _, events = walk_structure(bar_objs, swings, w)
            events_by_window[w] = events
        trade_on = combo["trade_on"]
        combo_id = f"structure_w{w}_{trade_on}"
        for ev in events_by_window[w]:
            if trade_on != "BOTH" and ev.kind != trade_on:
                continue
            rows.append({
                "combo_id": combo_id, "window": w, "trade_on": trade_on,
                "signal_bar_idx": ev.break_index,
                "direction": "long" if ev.direction == "bullish" else "short",
                "event_kind": ev.kind, "broken_price": ev.broken_price,
                "swing_index": ev.swing_index,
            })
    return pd.DataFrame(rows, columns=["combo_id", "window", "trade_on", "signal_bar_idx",
                                        "direction", "event_kind", "broken_price", "swing_index"])


__all__ = ["build_grid", "generate_signals", "bars_df_to_bar_objects"]
