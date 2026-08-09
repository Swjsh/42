"""Guard tests for backtest/lib/trendline_detector.py (new 2026-08-09).

Covers the invariants named in the build brief:
  1. anchor_mode wick/body is NEVER mixed within one line (structural, RED-proofed).
  2. Zero look-ahead: as_of_index truncates BEFORE any computation.
  3. Touch counting respects min_touches / min_bars_between_touches / min_span_bars.
  4. max_slope_pct_per_bar caps candidate slope.
  5. line_id is stable across bars (same physical line keeps its id as it accrues touches).
  6. status transitions (intact -> testing -> broken) and just_broken fire correctly.
  7. bars_from_dataframe round-trips a backtest-shaped DataFrame.
  8. Immutability: annotate_decisions_with_trendline_state never mutates its inputs.

Run: cd backtest && python -m pytest tests/test_trendline_detector.py -v
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))

from crypto.lib.bar import Bar  # noqa: E402
from lib import trendline_detector as td  # noqa: E402


def _mk(i: int, low: float, high: float, close: float | None = None, open_: float | None = None) -> Bar:
    c = close if close is not None else (low + high) / 2
    o = open_ if open_ is not None else c
    return Bar(
        open_time=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5 * i),
        open=o, high=high, low=low, close=c, volume=1000.0, granularity_seconds=300, source="test",
    )


def _ascending_support_bars(n: int = 40, pivots: frozenset[int] = frozenset({2, 10, 18})) -> tuple[Bar, ...]:
    """3 clean pivot lows at the given bar indices (>=6 apart), everything else well above
    the line so only the pivots themselves are touches."""
    base, slope = 500.0, 0.05
    bars = []
    for i in range(n):
        lv = base + slope * i
        if i in pivots:
            bars.append(_mk(i, low=lv, high=lv + 1.5))
        else:
            bars.append(_mk(i, low=lv + 0.5, high=lv + 2.0))
    return tuple(bars)


def _descending_resistance_bars(n: int = 40, pivots: frozenset[int] = frozenset({2, 10, 18})) -> tuple[Bar, ...]:
    base, slope = 500.0, -0.05
    bars = []
    for i in range(n):
        lv = base + slope * i
        if i in pivots:
            bars.append(_mk(i, low=lv - 1.5, high=lv))
        else:
            bars.append(_mk(i, low=lv - 2.0, high=lv - 0.5))
    return tuple(bars)


# ---------------------------------------------------------------------------
# 1. anchor_mode wick/body structural no-mixing guard
# ---------------------------------------------------------------------------

def test_wick_mode_uses_raw_wick_never_body() -> None:
    """The stock ascending-support fixture's pivot bars have open==close==(low+high)/2 by
    construction (`_mk`'s default) -- i.e. every pivot's body-bottom (the body-mode anchor
    value) is ALREADY, structurally, a different number from its wick low (the wick-mode
    anchor value): low=lv vs body-bottom=lv+0.75 (since high=lv+1.5). This is the cleanest
    possible proof that the two modes read different accessors: no hand-engineered single-
    bar special case needed, just the natural fixture."""
    bars = _ascending_support_bars()
    lines_wick = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                       min_bars_between_touches=6, anchor_mode="wick")
    lines_body = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                       min_bars_between_touches=6, anchor_mode="body")
    assert lines_wick, "expected a wick-mode support line"
    assert lines_body, "expected a body-mode support line"

    wick_anchor2 = next(a for a in lines_wick[0].anchors if a.bar_index == 2)
    body_anchor2 = next(a for a in lines_body[0].anchors if a.bar_index == 2)
    assert wick_anchor2.price == bars[2].low, "wick mode must anchor bar 2 at its raw LOW"
    assert body_anchor2.price == min(bars[2].open, bars[2].close), (
        "body mode must anchor bar 2 at min(open,close)"
    )
    assert wick_anchor2.price != body_anchor2.price, (
        "wick and body anchors at the SAME bar must read different accessors, not collapse "
        "to the same value"
    )


def test_anchor_mode_never_mixed_within_one_line() -> None:
    """Every anchor of every returned line must come from the SAME accessor as the
    line's own anchor_mode -- direct structural check, both modes."""
    bars = _ascending_support_bars()
    for mode in ("wick", "body"):
        lines = td.detect_trendlines(bars, kinds=("support",), anchor_mode=mode,
                                      min_touches=3, min_span_bars=6, min_bars_between_touches=6)
        for ln in lines:
            assert ln.anchor_mode == mode
            for a in ln.anchors:
                bar = bars[a.bar_index]
                wick_val = bar.low
                body_val = min(bar.open, bar.close)
                if mode == "wick":
                    assert a.price == wick_val, "wick-mode anchor must equal the raw low"
                else:
                    assert a.price == body_val, "body-mode anchor must equal min(open,close)"


def test_invalid_anchor_mode_raises() -> None:
    bars = _ascending_support_bars()
    with pytest.raises(ValueError):
        td.detect_trendlines(bars, anchor_mode="wick_and_body")  # type: ignore[arg-type]


def test_red_proof_mixed_accessor_would_be_caught() -> None:
    """RED-PROOF: manually build a _Candidate-shaped scenario where body mode's own bar-view
    swap is bypassed (simulate the bug this guard exists to catch) and confirm the assertion
    inside detect_trendlines actually fires. We do this by monkeypatching _view_for_mode to
    return the WICK view while anchor_mode='body' is requested -- the exact failure mode the
    structural guard must reject."""
    bars = _ascending_support_bars()
    original = td._view_for_mode
    try:
        td._view_for_mode = lambda b, mode: tuple(b)  # always return the unmodified (wick) view
        with pytest.raises(AssertionError):
            td.detect_trendlines(bars, kinds=("support",), anchor_mode="body",
                                  min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    finally:
        td._view_for_mode = original


# ---------------------------------------------------------------------------
# 2. Zero look-ahead
# ---------------------------------------------------------------------------

def test_as_of_index_truncates_before_any_computation() -> None:
    """A line detected with as_of_index=K must be BYTE-IDENTICAL to calling
    detect_trendlines on bars[:K+1] directly -- as_of_index must never let a later
    bar leak into the fit."""
    bars = _ascending_support_bars(n=40)
    k = 25
    truncated_call = td.detect_trendlines(bars[: k + 1], kinds=("support",),
                                           min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    as_of_call = td.detect_trendlines(bars, as_of_index=k, kinds=("support",),
                                       min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    assert [ln.to_dict() for ln in truncated_call] == [ln.to_dict() for ln in as_of_call]


def test_future_bars_never_change_a_past_snapshot() -> None:
    """Detecting as-of bar 25 must give the SAME line whether or not bars 26-39 exist in
    the array passed in -- proof that nothing beyond as_of_index is read."""
    bars_full = _ascending_support_bars(n=40)
    bars_short = bars_full[:26]
    full_asof = td.detect_trendlines(bars_full, as_of_index=25, kinds=("support",),
                                      min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    short_direct = td.detect_trendlines(bars_short, kinds=("support",),
                                         min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    assert [ln.to_dict() for ln in full_asof] == [ln.to_dict() for ln in short_direct]


# ---------------------------------------------------------------------------
# 3. touch / span / spacing grammar
# ---------------------------------------------------------------------------

def test_min_touches_enforced() -> None:
    """Only 2 clean pivots (below the wall-clock min_touches=3 default) -> no line."""
    bars = _ascending_support_bars(n=20, pivots=frozenset({2, 10}))
    lines = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                  min_bars_between_touches=6)
    assert lines == (), "2 pivots must not satisfy min_touches=3"


def test_min_touches_relaxed_finds_the_same_line() -> None:
    bars = _ascending_support_bars(n=20, pivots=frozenset({2, 10}))
    lines = td.detect_trendlines(bars, kinds=("support",), min_touches=2, min_span_bars=6,
                                  min_bars_between_touches=6)
    assert lines, "2 pivots must satisfy a relaxed min_touches=2"


def test_min_span_bars_rejects_close_anchors() -> None:
    """A 2-pivot candidate whose ONLY possible anchor pair spans 3 bars must be rejected
    once min_span_bars=6 (relaxing min_touches to 2 so the only knob under test is span --
    a 3rd, farther-apart pivot would let a different, longer-spanning pair win instead,
    which is correct behavior but not what this test isolates)."""
    bars = _ascending_support_bars(n=20, pivots=frozenset({2, 5}))
    lines = td.detect_trendlines(bars, kinds=("support",), min_touches=2, min_span_bars=6,
                                  min_bars_between_touches=2)
    assert lines == (), "the only anchor pair spans 3 bars (< 6) and must be rejected"

    # Sanity: the SAME pivots, with min_span_bars relaxed to <= 3, DO form a line -- proves
    # the rejection above is the span gate, not some other silent filter.
    lines_relaxed = td.detect_trendlines(bars, kinds=("support",), min_touches=2, min_span_bars=3,
                                          min_bars_between_touches=2)
    assert lines_relaxed, "relaxing min_span_bars to 3 must recover the line"


def test_min_bars_between_touches_dedupes_clustered_touches() -> None:
    """Two touches 1 bar apart count as ONE touch once min_bars_between_touches=6 -- a
    cluster of adjacent touches is one reaction, not independent tests (Tori-method
    convergence, see module docstring)."""
    base, slope = 500.0, 0.05
    bars = []
    # pivots at 2,3 (adjacent -- one reaction), then 20, 38 -- all "on the line" within tol.
    pivot_idxs = {2, 3, 20, 38}
    for i in range(40):
        lv = base + slope * i
        if i in pivot_idxs:
            bars.append(_mk(i, low=lv, high=lv + 1.5))
        else:
            bars.append(_mk(i, low=lv + 0.5, high=lv + 2.0))
    lines_spaced = td.detect_trendlines(tuple(bars), kinds=("support",), min_touches=3,
                                         min_span_bars=6, min_bars_between_touches=6,
                                         touch_tolerance_dollars=0.05)
    # With spacing enforced, bars 2 and 3 can't BOTH count -- only one of them plus 20/38
    # can reach 3. Confirm no line double-counts adjacent bars 2 AND 3 as distinct touches.
    for ln in lines_spaced:
        touched = {a.bar_index for a in ln.anchors}
        assert not ({2, 3} <= touched), "adjacent bars 2 and 3 must not both be counted as anchors"


# ---------------------------------------------------------------------------
# 4. slope cap
# ---------------------------------------------------------------------------

def test_max_slope_pct_per_bar_caps_steep_lines() -> None:
    """A steep line (large slope) must be excluded once max_slope_pct_per_bar is tight.

    Uses a FIXED, generous pivot dip (independent of slope) rather than the gentle
    ascending-support helper's small +0.5 offset: at steep_slope=2.0/bar, a +0.5 offset is
    swamped by the trend's own per-bar drift within one fractal window (2 bars * 2.0 =
    4.0 > 0.5), so a pivot bar can stop being a LOCAL extreme at all. A dip of 10.0 keeps
    every pivot a clean local minimum regardless of the trend slope under test.
    """
    base = 500.0
    bars = []
    pivots = {2, 10, 18}
    steep_slope = 2.0  # ~0.4%/bar at base=500 -- far steeper than the 0.05%/bar cap below
    dip = 10.0
    for i in range(30):
        lv = base + steep_slope * i
        if i in pivots:
            bars.append(_mk(i, low=lv - dip, high=lv - dip + 1.5))
        else:
            bars.append(_mk(i, low=lv, high=lv + 1.5))
    bars = tuple(bars)
    uncapped = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                     min_bars_between_touches=6)
    capped = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                   min_bars_between_touches=6, max_slope_pct_per_bar=0.0005)
    assert uncapped, "sanity: the steep line must be detectable when uncapped"
    assert capped == (), "a 0.4%/bar line must be rejected by a 0.05%/bar cap"


# ---------------------------------------------------------------------------
# 5. line_id stability
# ---------------------------------------------------------------------------

def test_line_id_stable_as_more_touches_accrue() -> None:
    """The SAME physical line (same first anchor) must keep the SAME line_id when
    detected from a longer bar window that adds a 4th touch."""
    bars40 = _ascending_support_bars(n=40, pivots=frozenset({2, 10, 18}))
    bars60 = _ascending_support_bars(n=60, pivots=frozenset({2, 10, 18, 34}))
    lines_a = td.detect_trendlines(bars40, kinds=("support",), min_touches=3, min_span_bars=6,
                                    min_bars_between_touches=6)
    lines_b = td.detect_trendlines(bars60, kinds=("support",), min_touches=3, min_span_bars=6,
                                    min_bars_between_touches=6)
    assert lines_a and lines_b
    assert lines_a[0].line_id == lines_b[0].line_id, (
        "line_id must be stable across re-detection with more history/touches"
    )
    assert lines_b[0].touch_count >= lines_a[0].touch_count


def test_line_id_encodes_direction_and_family() -> None:
    lines = td.detect_trendlines(_ascending_support_bars(), kinds=("support",), anchor_mode="wick",
                                  min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    assert lines
    assert lines[0].line_id.startswith("TL-SPY-5m-SUP-W-")

    lines_body = td.detect_trendlines(_ascending_support_bars(), kinds=("support",), anchor_mode="body",
                                       min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    assert lines_body
    assert lines_body[0].line_id.startswith("TL-SPY-5m-SUP-B-")

    lines_res = td.detect_trendlines(_descending_resistance_bars(), kinds=("resistance",),
                                      min_touches=3, min_span_bars=6, min_bars_between_touches=6)
    assert lines_res
    assert lines_res[0].line_id.startswith("TL-SPY-5m-RES-W-")


# ---------------------------------------------------------------------------
# 6. status transitions
# ---------------------------------------------------------------------------

def test_status_intact_when_price_stays_above_support() -> None:
    bars = _ascending_support_bars()
    lines = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                  min_bars_between_touches=6)
    assert lines and lines[0].status == "intact"
    assert not lines[0].just_broken


def test_status_broken_and_just_broken_on_the_break_bar() -> None:
    """Extend the ascending-support fixture with a hard close BELOW the line on the final
    bar -- status must read 'broken' and just_broken must be True (first-ever violation on
    the query bar)."""
    bars = list(_ascending_support_bars(n=40))
    base, slope = 500.0, 0.05
    last_i = 39
    line_val_at_last = base + slope * last_i  # approx, anchors are at 2/10/18 but slope matches
    # Force a clean break: close well below the support projection.
    bars[last_i] = _mk(last_i, low=line_val_at_last - 3.0, high=line_val_at_last + 0.2,
                        close=line_val_at_last - 2.0)
    lines = td.detect_trendlines(tuple(bars), kinds=("support",), min_touches=3, min_span_bars=6,
                                  min_bars_between_touches=6, touch_tolerance_dollars=0.20)
    assert lines, "line must still be detectable through the break bar"
    ln = lines[0]
    assert ln.status == "broken", ln
    assert ln.just_broken is True, ln


def test_just_broken_false_on_the_bar_after_the_break() -> None:
    """One bar AFTER the break, status is still broken (or the line may no longer win a
    slot) but just_broken for THIS query bar must be False -- the break already happened
    on the prior bar, not this one."""
    bars = list(_ascending_support_bars(n=41))
    base, slope = 500.0, 0.05
    break_i = 39
    line_val = base + slope * break_i
    bars[break_i] = _mk(break_i, low=line_val - 3.0, high=line_val + 0.2, close=line_val - 2.0)
    # bar 40: also below the line (still broken), but NOT the first violation.
    line_val_40 = base + slope * 40
    bars[40] = _mk(40, low=line_val_40 - 3.0, high=line_val_40 - 1.0, close=line_val_40 - 2.0)
    lines = td.detect_trendlines(tuple(bars), kinds=("support",), min_touches=3, min_span_bars=6,
                                  min_bars_between_touches=6, touch_tolerance_dollars=0.20)
    assert lines
    assert lines[0].status == "broken"
    assert lines[0].just_broken is False, "the break already happened one bar earlier"


# ---------------------------------------------------------------------------
# 7. DataFrame adapter
# ---------------------------------------------------------------------------

def test_bars_from_dataframe_round_trips_backtest_shape() -> None:
    import pandas as pd

    rows = []
    for i in range(10):
        ts = pd.Timestamp("2026-01-02 09:30:00", tz="America/New_York") + pd.Timedelta(minutes=5 * i)
        rows.append({"timestamp_et": ts, "open": 500 + i, "high": 500.5 + i,
                      "low": 499.5 + i, "close": 500.2 + i, "volume": 1000})
    df = pd.DataFrame(rows)
    bars = td.bars_from_dataframe(df)
    assert len(bars) == 10
    assert bars[0].open == 500.0
    assert bars[0].high == 500.5
    assert bars[-1].close == 509.2
    # chronological order preserved
    assert all(bars[i].open_time < bars[i + 1].open_time for i in range(len(bars) - 1))


def test_bars_from_dataframe_handles_missing_volume() -> None:
    import pandas as pd

    rows = []
    for i in range(6):
        ts = pd.Timestamp("2026-01-02 09:30:00", tz="America/New_York") + pd.Timedelta(minutes=5 * i)
        rows.append({"timestamp_et": ts, "open": 500 + i, "high": 500.5 + i,
                      "low": 499.5 + i, "close": 500.2 + i})
    df = pd.DataFrame(rows)
    bars = td.bars_from_dataframe(df)
    assert len(bars) == 6
    assert bars[0].volume == 0.0


def test_bars_from_dataframe_empty_returns_empty_tuple() -> None:
    import pandas as pd

    df = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    assert td.bars_from_dataframe(df) == ()


# ---------------------------------------------------------------------------
# 8. Immutability / engine-awareness plumbing
# ---------------------------------------------------------------------------

def test_annotate_decisions_never_mutates_input() -> None:
    import pandas as pd

    rows = []
    for i in range(60):
        ts = pd.Timestamp("2026-01-02 09:30:00", tz="America/New_York") + pd.Timedelta(minutes=5 * i)
        rows.append({"timestamp_et": ts, "open": 500 + i * 0.05, "high": 500.5 + i * 0.05,
                      "low": 499.5 + i * 0.05, "close": 500.2 + i * 0.05, "volume": 1000})
    spy_df = pd.DataFrame(rows)

    decisions = [
        {"bar_idx": 30, "action": "HOLD", "triggers_fired": []},
        {"bar_idx": 45, "action": "ENTER_BEAR", "triggers_fired": ["trendline_rejection"]},
    ]
    import copy
    decisions_copy = copy.deepcopy(decisions)

    out = td.annotate_decisions_with_trendline_state(decisions, spy_df, min_touches=2,
                                                       min_span_bars=4, min_bars_between_touches=2,
                                                       lookback_bars=40)
    assert decisions == decisions_copy, "input decisions list/dicts must never be mutated"
    assert len(out) == len(decisions)
    for row in out:
        assert "trendline_state" in row
    # Original keys survive untouched (additive-only).
    assert out[0]["action"] == "HOLD"
    assert out[1]["triggers_fired"] == ["trendline_rejection"]


def test_annotate_decisions_handles_missing_bar_idx_gracefully() -> None:
    import pandas as pd

    spy_df = pd.DataFrame({
        "timestamp_et": [pd.Timestamp("2026-01-02 09:30:00", tz="America/New_York")],
        "open": [500.0], "high": [500.5], "low": [499.5], "close": [500.2], "volume": [1000],
    })
    decisions = [{"action": "HOLD"}, {"bar_idx": None, "action": "SKIP"}, {"bar_idx": 9999, "action": "HOLD"}]
    out = td.annotate_decisions_with_trendline_state(decisions, spy_df)
    assert len(out) == 3
    for row in out:
        assert row["trendline_state"] == {}


def test_trendline_state_for_decision_row_empty_when_no_lines() -> None:
    assert td.trendline_state_for_decision_row(()) == {}
    assert td.trendline_state_for_decision_row([]) == {}


def test_trendline_state_for_decision_row_shape() -> None:
    bars = _ascending_support_bars()
    lines = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                  min_bars_between_touches=6)
    row = td.trendline_state_for_decision_row(lines)
    assert row["n_lines"] == len(lines)
    assert "nearest_line_id" in row
    assert row["support"] is not None
    assert row["resistance"] is None  # only support lines were requested/found


# ---------------------------------------------------------------------------
# 9. TrendlineState is frozen (immutability)
# ---------------------------------------------------------------------------

def test_trendline_state_is_frozen() -> None:
    bars = _ascending_support_bars()
    lines = td.detect_trendlines(bars, kinds=("support",), min_touches=3, min_span_bars=6,
                                  min_bars_between_touches=6)
    assert lines
    with pytest.raises(Exception):
        lines[0].touch_count = 999  # type: ignore[misc]


def test_no_lines_returns_empty_tuple_not_none() -> None:
    """Too few bars -- must return () and never raise or return None."""
    bars = _ascending_support_bars(n=6)
    lines = td.detect_trendlines(bars)
    assert lines == ()
