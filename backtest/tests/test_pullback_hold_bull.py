"""Guard tests for backtest/tools/pullback_hold_bull_detector.py.

Pre-reg: analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json
Queue item: PULLBACK-HOLD-BULL-TRIGGER.

RED-proofs: fires on synthetic fixtures shaped like BOTH of J's named 2026-07-21/07-22
exhibits, zone band is respected as a BAND (not a penny-exact compare), the N-bar hold
window is respected, confirmation gating (RSI-reset + green-close) works, and the detector
never uses information from a bar timestamped after the one it emits a signal for
(no-look-ahead, C6).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.pullback_hold_bull_detector import (  # noqa: E402
    PullbackHoldParams,
    detect_pullback_hold_bull,
    market_structure_up_ok,
    price_above_vwap_ok,
    session_vwap_series,
    up_structure_series,
)

ET = timezone(timedelta(hours=-4))  # fixture timestamps only need to be tz-aware + ordered


def _bars(rows: list[tuple], start=datetime(2026, 1, 5, 9, 30, tzinfo=ET)) -> pd.DataFrame:
    """rows: list of (open, high, low, close[, volume]) tuples, one per 5-min bar."""
    out = []
    for i, row in enumerate(rows):
        o, h, l, c = row[0], row[1], row[2], row[3]
        v = row[4] if len(row) > 4 else 1000.0
        out.append({
            "timestamp_et": start + timedelta(minutes=5 * i),
            "open": o, "high": h, "low": l, "close": c, "volume": v,
        })
    return pd.DataFrame(out)


def _const_levels(levels: list[float]):
    return lambda i: levels


def _params(**kw) -> PullbackHoldParams:
    base = dict(up_structure_mode="MARKET_STRUCTURE", zone_band_cents=0.25, hold_bars_n=2,
                confirm_mode="NONE")
    base.update(kw)
    return PullbackHoldParams(**base)


# =====================================================================================
# Core mechanics
# =====================================================================================
def test_basic_pullback_hold_fires():
    # bar0: low touches the zone (level=100.00, band=0.25 -> [99.75,100.25]); low=99.90
    # bar1: closes back above zone_top (100.25) -> entry at bar1
    df = _bars([
        (100.50, 100.60, 99.90, 100.00),   # bar0: pullback low 99.90
        (100.05, 100.60, 100.00, 100.40),  # bar1: closes 100.40 > zone_top 100.25 -> entry
    ])
    up_ok = [True, True]
    sigs = detect_pullback_hold_bull(
        df, up_structure_ok=up_ok, levels_at=_const_levels([100.0]),
        params=_params(hold_bars_n=1), day_label="2026-01-05")
    assert len(sigs) == 1
    s = sigs[0]
    assert s.pullback_bar_idx == 0
    assert s.entry_bar_idx == 1
    assert s.level_price == 100.0
    assert s.zone_low == pytest.approx(99.75)
    assert s.zone_top == pytest.approx(100.25)
    assert s.bars_to_hold == 1


def test_no_fire_without_up_structure():
    df = _bars([
        (100.50, 100.60, 99.90, 100.00),
        (100.05, 100.60, 100.00, 100.40),
    ])
    sigs = detect_pullback_hold_bull(
        df, up_structure_ok=[False, False], levels_at=_const_levels([100.0]),
        params=_params(hold_bars_n=1), day_label="d")
    assert sigs == []


def test_no_fire_when_low_never_enters_zone():
    # low=99.50 is 0.50 away from level=100.00 -- outside a 0.25 band
    df = _bars([
        (100.50, 100.60, 99.50, 99.55),
        (99.60, 100.60, 99.55, 100.40),
    ])
    sigs = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=_const_levels([100.0]),
        params=_params(zone_band_cents=0.25, hold_bars_n=1), day_label="d")
    assert sigs == []


def test_zone_is_a_band_not_penny_exact():
    """The SAME bars: fails at a tight band, fires at a wide band -- proves the compare is a
    band (range), never an exact-price match."""
    df = _bars([
        (100.50, 100.60, 99.74, 99.80),    # low 99.74 -> 0.26 below level 100.00
        (99.85, 100.60, 99.80, 100.60),    # closes well above any plausible zone_top
    ])
    tight = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=_const_levels([100.0]),
        params=_params(zone_band_cents=0.15, hold_bars_n=1), day_label="d")
    wide = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=_const_levels([100.0]),
        params=_params(zone_band_cents=0.40, hold_bars_n=1), day_label="d")
    assert tight == []
    assert len(wide) == 1


def test_hold_window_n_respected():
    # low touches zone at bar0; NOT reclaimed until bar2 (2 bars later). bar1's own low sits
    # OUTSIDE the zone (undershoots to 99.60 vs level 100.0, band 0.25) so it can never spawn
    # a second, independent candidate -- isolates the test to bar0's own N-bar window.
    df = _bars([
        (100.50, 100.60, 99.90, 100.00),   # bar0: pullback low, candidate
        (99.95, 100.00, 99.60, 99.90),     # bar1: low outside the zone band, no reclaim either
        (100.35, 100.60, 100.30, 100.40),  # bar2: low ALSO outside the band, closes 100.40 (reclaim)
    ])
    levels = _const_levels([100.0])
    n1 = detect_pullback_hold_bull(df, up_structure_ok=[True] * 3, levels_at=levels,
                                    params=_params(hold_bars_n=1), day_label="d")
    n2 = detect_pullback_hold_bull(df, up_structure_ok=[True] * 3, levels_at=levels,
                                    params=_params(hold_bars_n=2), day_label="d")
    assert n1 == []  # reclaim bar is 2 bars after the low -- N=1 window (bars 0..1) misses it
    assert len(n2) == 1
    assert n2[0].entry_bar_idx == 2
    assert n2[0].pullback_bar_idx == 0


def test_confirmation_both_gates_rsi_reset_and_green_close():
    df = _bars([
        (100.50, 100.60, 99.90, 100.00),   # bar0: pullback low
        (100.05, 100.60, 100.00, 100.40),  # bar1: reclaim, green close (100.40>100.05)
    ])
    levels = _const_levels([100.0])

    # RSI reset present (dips to 50 within lookback) -> passes
    rsi_ok = {0: 50.0, 1: 60.0}
    sigs_ok = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=levels,
        params=_params(hold_bars_n=1, confirm_mode="BOTH"), day_label="d",
        rsi_at=lambda i: rsi_ok.get(i))
    assert len(sigs_ok) == 1
    assert sigs_ok[0].passed_confirmation is True

    # No RSI reset (stays extended, never dips <=55) -> blocked
    rsi_bad = {0: 68.0, 1: 69.0}
    sigs_bad = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=levels,
        params=_params(hold_bars_n=1, confirm_mode="BOTH"), day_label="d",
        rsi_at=lambda i: rsi_bad.get(i))
    assert sigs_bad == []


def test_confirmation_both_blocks_red_close_even_with_rsi_reset():
    df = _bars([
        (100.50, 100.60, 99.90, 100.00),
        (100.50, 100.60, 100.00, 100.30),  # closes 100.30 > zone_top 100.25 but RED (open>close)
    ])
    levels = _const_levels([100.0])
    rsi_ok = {0: 50.0, 1: 60.0}
    sigs = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=levels,
        params=_params(hold_bars_n=1, confirm_mode="BOTH"), day_label="d",
        rsi_at=lambda i: rsi_ok.get(i))
    assert sigs == []


def test_no_candidate_reuse_after_consumed():
    """A pullback-low bar that fails to reclaim within N is not re-tested as a fresh
    candidate on the next bar (avoids duplicate/overlapping signals off one dip)."""
    df = _bars([
        (100.50, 100.60, 99.90, 100.00),   # bar0: pullback low, never reclaims (N=1)
        (100.00, 100.10, 99.95, 100.05),   # bar1: still low-ish, inside zone again
        (100.05, 100.60, 100.00, 100.40),  # bar2: reclaim
    ])
    sigs = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True, True], levels_at=_const_levels([100.0]),
        params=_params(hold_bars_n=1), day_label="d")
    # bar0's window (bars 0..1) never closes above zone_top -> candidate dropped, j advances
    # to 1; bar1's window (bars 1..2) DOES reclaim at bar2.
    assert len(sigs) == 1
    assert sigs[0].pullback_bar_idx == 1
    assert sigs[0].entry_bar_idx == 2


# =====================================================================================
# No-look-ahead (C6)
# =====================================================================================
def test_no_look_ahead_truncation():
    df_full = _bars([
        (100.50, 100.60, 99.90, 100.00),   # bar0: pullback low
        (100.05, 100.60, 100.00, 100.40),  # bar1: reclaim -> entry
        (100.40, 100.80, 100.30, 100.70),  # bar2: irrelevant future bar
        (100.70, 100.90, 100.60, 100.55),  # bar3: irrelevant future bar
    ])
    levels = _const_levels([100.0])
    params = _params(hold_bars_n=1)

    full = detect_pullback_hold_bull(df_full, up_structure_ok=[True] * 4, levels_at=levels,
                                      params=params, day_label="d")
    # Truncating to end exactly at the entry bar (idx 1) reproduces the SAME signal.
    truncated_after = detect_pullback_hold_bull(
        df_full.iloc[:2].reset_index(drop=True), up_structure_ok=[True, True],
        levels_at=levels, params=params, day_label="d")
    assert len(full) == 1
    assert len(truncated_after) == 1
    assert full[0].entry_bar_idx == truncated_after[0].entry_bar_idx == 1
    assert full[0].entry_close == truncated_after[0].entry_close

    # Truncating BEFORE the entry bar (only bar0 available) drops the signal entirely --
    # proves the detector needed bar1's own close to fire, never "knew" it in advance.
    truncated_before = detect_pullback_hold_bull(
        df_full.iloc[:1].reset_index(drop=True), up_structure_ok=[True],
        levels_at=levels, params=params, day_label="d")
    assert truncated_before == []


# =====================================================================================
# J's two named exhibits (synthetic fixtures shaped to match the key OHLC numbers from
# markdown/doctrine/DOJO-HARVEST-2026-07-21.md + automation/overnight/queue.md -- NOT the
# literal historical bars; real-data fidelity is separately checked by the replay tool's
# sanity_anchors gate against the actual cached SPY 5m series).
# =====================================================================================
def test_exhibit_2026_07_22_higher_low_over_level():
    """Pullback low 746.80, 26c above a level_memory level at 746.54; reclaims above zone
    top the following bar. Only a wide-enough band (>= ~0.30) can see this -- matches the
    pre-reg's own disclosure that band=0.15 is expected to fail this anchor."""
    df = _bars([
        (747.30, 747.45, 746.80, 746.85),   # 10:40 bar: pullback low 746.80
        (746.86, 747.10, 746.80, 747.00),   # 10:45 bar: reclaim close 747.00
    ], start=datetime(2026, 7, 22, 10, 40, tzinfo=ET))
    levels = _const_levels([746.54])
    band40 = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=levels,
        params=_params(zone_band_cents=0.40, hold_bars_n=1), day_label="2026-07-22")
    band15 = detect_pullback_hold_bull(
        df, up_structure_ok=[True, True], levels_at=levels,
        params=_params(zone_band_cents=0.15, hold_bars_n=1), day_label="2026-07-22")
    assert len(band40) == 1
    assert band40[0].pullback_low == pytest.approx(746.80)
    assert band15 == []  # disclosed in the pre-reg: tight band cannot see this anchor


def test_exhibit_2026_07_21_shelf_then_reclaim():
    """Three taps of a 745.77-745.85 shelf then an 11:15 close at 747.41 -- the reclaim is
    far above any plausible zone_top, so this anchor fires across every band width."""
    df = _bars([
        (746.30, 746.63, 745.77, 746.60),   # 10:40 tap
        (746.61, 747.26, 746.45, 746.91),   # 10:45
        (746.77, 746.89, 745.83, 746.00),   # 11:00 tap
        (746.00, 747.07, 745.85, 746.98),   # 11:05 tap
        (746.98, 747.52, 746.94, 747.21),   # 11:10
        (747.21, 747.55, 747.16, 747.41),   # 11:15 reclaim close 747.41
    ], start=datetime(2026, 7, 21, 10, 40, tzinfo=ET))
    levels = _const_levels([745.85])
    for band in (0.15, 0.25, 0.40):
        sigs = detect_pullback_hold_bull(
            df, up_structure_ok=[True] * len(df), levels_at=levels,
            params=_params(zone_band_cents=band, hold_bars_n=3), day_label="2026-07-21")
        assert len(sigs) >= 1, f"band={band} failed to see the 07-21 shelf exhibit"


# =====================================================================================
# cell_id formatting
# =====================================================================================
def test_cell_id_is_stable_and_readable():
    p = PullbackHoldParams(up_structure_mode="MARKET_STRUCTURE", zone_band_cents=0.25,
                            hold_bars_n=2, confirm_mode="BOTH")
    assert p.cell_id() == "MARKET_STRUCTURE_band25c_N2_BOTH"


# =====================================================================================
# Feature helpers (used by the replay harness -- sanity-checked here in isolation)
# =====================================================================================
def test_session_vwap_series_matches_cumulative_typical_price():
    df = _bars([(100.0, 100.2, 99.8, 100.0, 10.0), (100.0, 100.4, 99.9, 100.2, 10.0)])
    v = session_vwap_series(df)
    tp0 = (100.2 + 99.8 + 100.0) / 3.0
    assert v[0] == pytest.approx(tp0)
    tp1 = (100.4 + 99.9 + 100.2) / 3.0
    expected1 = (tp0 * 10.0 + tp1 * 10.0) / 20.0
    assert v[1] == pytest.approx(expected1)


def test_price_above_vwap_ok_basic():
    # bar0 close==vwap0 -> not strictly above; bar1 rallies well above cumulative vwap
    df = _bars([(100.0, 100.0, 100.0, 100.0, 10.0), (100.0, 105.0, 100.0, 105.0, 10.0)])
    ok = price_above_vwap_ok(df)
    assert ok[0] is False
    assert ok[1] is True


def test_market_structure_up_ok_detects_uptrend_and_flat():
    # A zigzag of higher-highs / higher-lows (legs: push up, small pullback, push up) should
    # read as uptrend once enough swing pivots exist; the opening bars (insufficient history)
    # must not.
    rows = []
    base = 100.0
    for _ in range(6):
        top = base + 1.0
        pullback_low = base + 0.6
        rows += [
            (base, base + 0.5, base - 0.1, base + 0.4),
            (base + 0.4, top, base + 0.3, top - 0.05),
            (top - 0.1, top, pullback_low, pullback_low + 0.05),
            (pullback_low + 0.1, pullback_low + 0.3, pullback_low - 0.05, pullback_low + 0.2),
        ]
        base = pullback_low + 0.2
    df = _bars(rows)
    ok = market_structure_up_ok(df, lookback_bars=60)
    assert any(ok), "a zigzag higher-high/higher-low uptrend must be detected at least once"
    assert ok[0] is False  # first bar can never have enough swing history
    assert ok[-1] is True  # by the end of a clean 6-leg uptrend it must read True


def test_up_structure_series_dispatch():
    df = _bars([(100.0, 100.2, 99.8, 100.0, 10.0), (100.0, 100.4, 99.9, 100.2, 10.0)])
    a = up_structure_series(df, "PRICE_VWAP")
    b = price_above_vwap_ok(df)
    assert a == b
    with pytest.raises(ValueError):
        up_structure_series(df, "NOT_A_MODE")  # type: ignore[arg-type]
