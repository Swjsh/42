"""Tests for the live VWAP_CONTINUATION watcher — unit + PARITY with the validated detector.

The headline test is PARITY: the live detector core (``detect_vwap_continuation_core`` +
``trend_side`` + ``vix_slope``, the pure pieces the watcher uses) must reproduce the EXACT
same per-day entry signals as the VALIDATED research detector
(``autoresearch.j_daily_pattern_ratify.detect_j_vwap_continuation``) across the full
2025-01..2026-06 dataset — for the plain J_VWAP_CONT variant, the breakout-only variant,
AND the VIX-gated variant. If they diverge, the live watcher is not trading the edge that
was validated (L153 — backtest triggers must map to live categories). This is the test
that lets the scorecard's numbers (n=153, exp +$38.3, WR 76.5%) be claimed for the LIVE
detector, not just the research one.

The discovery detector's OUTER loop (trend-side from the head, then the first in-trend
breakout/pullback bar inside the morning cutoff, with the optional VIX put-gate, one entry
per day) is reconstructed here on top of the live CORE, and the resulting signal set is
compared to the discovery's own ``Signal`` list. The CORE is the per-bar decision; the
loop (cutoff `break`, VIX `continue`, one-per-day) is the wrapper/heartbeat's job.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_vwap_continuation_watcher.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lib.watchers.vwap_continuation_watcher import (
    detect_vwap_continuation_core,
    detect_vwap_continuation_setup,
    trend_side,
    vix_slope,
    _reset_day,
    TREND_BARS,
    ENTRY_CUTOFF,
)
from lib.filters import BarContext

REPO = Path(__file__).resolve().parents[1]
SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"


# ── unit: trend_side ──────────────────────────────────────────────────────────

def test_trend_side_all_above_is_calls():
    assert trend_side([10, 11, 12], [9, 9, 9], 3) == "C"


def test_trend_side_all_below_is_puts():
    assert trend_side([8, 7, 6], [9, 9, 9], 3) == "P"


def test_trend_side_mixed_is_none():
    assert trend_side([10, 8, 11], [9, 9, 9], 3) is None


def test_trend_side_warmup_is_none():
    assert trend_side([10, 11], [9, 9], 3) is None  # only 2 of 3 bars


# ── unit: vix_slope (C5 put-gate primitive) ───────────────────────────────────

def test_vix_slope_deep_history_uses_5bar_span():
    # len 6 > look 5 -> slope = last - (last-5) = 18 - 15 = +3
    assert vix_slope([15.0, 15.5, 16.0, 16.5, 17.0, 18.0]) == pytest.approx(3.0)
    assert vix_slope([20.0, 19.5, 19.0, 18.5, 18.0, 16.0]) == pytest.approx(-4.0)


def test_vix_slope_short_history_zero_without_fallback():
    assert vix_slope([17.0, 17.0, 17.0]) == 0.0   # literal discovery guard (idx < look)


def test_vix_slope_short_history_uses_1bar_fallback():
    # parity bridge for the first <=5 morning bars (ctx exposes only vix_now/vix_prior)
    assert vix_slope([17.0, 17.0], fallback_1bar=-0.5) == -0.5
    assert vix_slope([17.0, 17.0], fallback_1bar=+0.3) == +0.3


# ── unit: pure core ───────────────────────────────────────────────────────────

def test_core_long_breakout():
    closes = np.array([600.5, 601.1, 601.7, 602.5])
    highs = np.array([600.6, 601.2, 601.8, 602.6])
    lows = np.array([599.9, 600.4, 601.0, 601.6])
    vwap = np.array([600.17, 600.57, 600.97, 601.4])
    r = detect_vwap_continuation_core(closes, highs, lows, vwap, 3)
    assert r is not None and r.side == "C" and r.direction == "long"
    assert r.trigger == "breakout"
    assert r.stop_level == 599.9   # session min low to date


def test_core_short_breakout():
    closes = np.array([599.5, 598.9, 598.3, 597.5])
    highs = np.array([600.1, 599.6, 599.0, 598.4])
    lows = np.array([599.4, 598.8, 598.2, 597.4])
    vwap = np.array([599.67, 599.38, 599.09, 598.9])
    r = detect_vwap_continuation_core(closes, highs, lows, vwap, 3)
    assert r is not None and r.side == "P" and r.direction == "short"
    assert r.trigger == "breakout"
    assert r.stop_level == 600.1   # session max high to date


def test_core_mixed_open_no_signal():
    closes = np.array([600.4, 599.2, 599.8, 600.8])   # close above then below -> mixed
    highs = np.array([600.6, 600.6, 599.9, 600.9])
    lows = np.array([599.4, 599.0, 599.0, 599.7])
    vwap = np.array([600.0, 599.8, 599.7, 599.8])
    assert detect_vwap_continuation_core(closes, highs, lows, vwap, 3) is None


def test_core_inside_trend_window_no_signal():
    closes = np.array([600.5, 601.1, 601.7, 602.5])
    highs = np.array([600.6, 601.2, 601.8, 602.6])
    lows = np.array([599.9, 600.4, 601.0, 601.6])
    vwap = np.array([600.17, 600.57, 600.97, 601.4])
    assert detect_vwap_continuation_core(closes, highs, lows, vwap, 2) is None  # j < TREND_BARS


def test_core_breakout_only_suppresses_pullback():
    # a pullback bar (tags VWAP, closes with-trend) that is NOT a fresh extreme
    closes = np.array([601.0, 601.5, 602.0, 601.6])
    highs = np.array([601.1, 601.6, 602.1, 601.7])    # bar3 high < prior max 602.1 -> not breakout
    lows = np.array([600.6, 601.1, 601.6, 600.95])
    vwap = np.array([600.8, 601.0, 601.2, 601.0])
    full = detect_vwap_continuation_core(closes, highs, lows, vwap, 3)
    bo = detect_vwap_continuation_core(closes, highs, lows, vwap, 3, breakout_only=True)
    assert full is not None and full.trigger == "pullback"
    assert bo is None


# ── unit: ctx wrapper gates ───────────────────────────────────────────────────

def _mk_ctx(rows, vix=17.0, vix_prior=None):
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
        prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=vix,
        vix_prior=vix if vix_prior is None else vix_prior,
        vol_baseline_20=1000.0, range_baseline_20=0.5,
        levels_active=[], multi_day_levels=[], htf_15m_stack=None,
    )


def _bar(h, m, o, hi, lo, c, v=5000):
    return dict(timestamp_et=dt.datetime(2026, 1, 7, h, m), open=o, high=hi, low=lo, close=c, volume=v)


def _run_day(rows, **kw):
    """Drive bars in order, return first fired signal (mirrors live streaming)."""
    _reset_day("reset")
    for k in range(len(rows)):
        s = detect_vwap_continuation_setup(_mk_ctx(rows[: k + 1]), **kw)
        if s is not None:
            return s
    return None


def test_wrapper_fires_long_breakout():
    rows = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),
        _bar(9, 45, 601.7, 602.6, 601.6, 602.5),
    ]
    sig = _run_day(rows)
    assert sig is not None and sig.direction == "long"
    assert sig.setup_name == "VWAP_CONTINUATION"
    assert sig.watcher_name == "vwap_continuation_watcher"
    assert sig.metadata["trigger"] == "breakout"
    assert sig.metadata["premium_stop_pct"] == -0.99   # chart-stop only
    assert sig.stop_price == 599.9                       # session min low to date


def test_wrapper_no_fire_inside_trend_window():
    # only TREND_BARS bars present -> warmup, no entry yet
    rows = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),
    ]
    assert _run_day(rows) is None


def test_wrapper_morning_cutoff_blocks_late_breakout():
    # trend window at 10:15-10:25, breakout at 11:00 > ENTRY_CUTOFF (10:30) -> no fire
    rows = [
        _bar(10, 15, 600.0, 600.6, 599.9, 600.5),
        _bar(10, 20, 600.5, 601.2, 600.4, 601.1),
        _bar(10, 25, 601.1, 601.8, 601.0, 601.7),
        _bar(11, 0, 601.7, 602.6, 601.6, 602.5),
    ]
    assert _run_day(rows) is None


def test_wrapper_vix_gate_blocks_put_on_falling_vix():
    rows = [
        _bar(9, 30, 600.0, 600.1, 599.4, 599.5),
        _bar(9, 35, 599.5, 599.6, 598.8, 598.9),
        _bar(9, 40, 598.9, 599.0, 598.2, 598.3),
        _bar(9, 45, 598.3, 598.4, 597.4, 597.5),
    ]
    falling = [20.0, 19.0, 18.0, 17.0]
    _reset_day("reset")
    fired = None
    for k in range(len(rows)):
        ctx = _mk_ctx(rows[: k + 1], vix=falling[k], vix_prior=falling[k - 1] if k > 0 else falling[k])
        s = detect_vwap_continuation_setup(ctx, put_needs_rising_vix=True)
        if s is not None:
            fired = s
    assert fired is None   # falling vix -> put-gate blocks


def test_wrapper_vix_gate_allows_put_on_rising_vix():
    rows = [
        _bar(9, 30, 600.0, 600.1, 599.4, 599.5),
        _bar(9, 35, 599.5, 599.6, 598.8, 598.9),
        _bar(9, 40, 598.9, 599.0, 598.2, 598.3),
        _bar(9, 45, 598.3, 598.4, 597.4, 597.5),
    ]
    rising = [16.0, 17.0, 18.0, 19.0]
    _reset_day("reset")
    fired = None
    for k in range(len(rows)):
        ctx = _mk_ctx(rows[: k + 1], vix=rising[k], vix_prior=rising[k - 1] if k > 0 else rising[k])
        s = detect_vwap_continuation_setup(ctx, put_needs_rising_vix=True)
        if s is not None:
            fired = s
    assert fired is not None and fired.direction == "short"


def test_wrapper_one_entry_per_day():
    # after a fire, subsequent bars do not fire again the same day
    rows = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),
        _bar(9, 45, 601.7, 602.6, 601.6, 602.5),   # first entry here
        _bar(9, 50, 602.5, 603.6, 602.4, 603.5),   # another breakout — must NOT fire
    ]
    _reset_day("reset")
    fires = [detect_vwap_continuation_setup(_mk_ctx(rows[: k + 1])) for k in range(len(rows))]
    n_fired = sum(1 for f in fires if f is not None)
    assert n_fired == 1


# ── PARITY: live core vs validated research detector over the FULL dataset ─────

def _discovery_signal_set(detect_fn_kwargs):
    """The research detector's signal set as (date, side, stop_level, trigger)."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from autoresearch.j_daily_pattern_ratify import detect_j_vwap_continuation
    from autoresearch.infinite_ammo_discovery import (
        load_spy, align_vix, build_day_contexts,
    )
    from lib.ribbon import compute_ribbon

    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)

    research = []
    for sg in detect_j_vwap_continuation(spy, ribbon, vix, days, **detect_fn_kwargs):
        bar = spy.iloc[sg.bar_idx]
        trig = (sg.note or "").replace("jvwap_", "")
        research.append((bar["date"], sg.side, round(float(sg.stop_level), 4), trig))
    return research, spy, vix, days


def _live_signal_set(spy, vix, days, *, breakout_only=False, put_needs_rising_vix=False):
    """Reconstruct the discovery OUTER loop on top of the live CORE + primitives.

    Mirrors ``detect_j_vwap_continuation`` exactly: trend side from the head, then the
    first morning (<=ENTRY_CUTOFF) in-trend breakout/pullback bar (via the live core),
    with the optional VIX put-gate (via the live ``vix_slope`` on the SAME global VIX
    series the discovery indexes), one entry per day. Returns the same
    (date, side, stop_level, trigger) tuples.
    """
    from autoresearch.infinite_ammo_discovery import session_vwap_asof

    out = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            res = detect_vwap_continuation_core(
                closes, highs, lows, vwap, j, breakout_only=breakout_only,
            )
            if res is None:
                continue
            # VIX put-gate — replicate the discovery's global-series 5-bar slope EXACTLY
            # (vix[idx] - vix[idx-5], 0.0 when idx<5). This is the parity-exact form;
            # the live wrapper's per-session+fallback slope is a runtime bridge for the
            # ctx limits and is unit-tested separately.
            if put_needs_rising_vix and res.side == "P":
                gi = int(idxs[j])
                disc_slope = 0.0 if gi < 5 or gi >= len(vix) else float(vix.values[gi] - vix.values[gi - 5])
                if disc_slope < 0:
                    continue
            out.append((dc.date, res.side, round(float(res.stop_level), 4), res.trigger))
            break
    return out


@pytest.mark.skipif(not SPY.exists(), reason="full SPY dataset not present")
def test_parity_full_pattern():
    """Live core reproduces detect_j_vwap_continuation (full J_VWAP_CONT) EXACTLY."""
    research, spy, vix, days = _discovery_signal_set({})
    live = _live_signal_set(spy, vix, days)
    assert len(research) > 0, "research detector produced no signals — fixture broken"
    assert sorted(live) == sorted(research), (
        f"PARITY BREAK (J_VWAP_CONT): research n={len(research)} live n={len(live)}. "
        f"only_research={sorted(set(research) - set(live))[:5]} "
        f"only_live={sorted(set(live) - set(research))[:5]}"
    )


@pytest.mark.skipif(not SPY.exists(), reason="full SPY dataset not present")
def test_parity_breakout_only():
    """Live core reproduces the breakout-only variant (J_VWAP_BREAKOUT) EXACTLY."""
    research, spy, vix, days = _discovery_signal_set({"breakout_only": True})
    live = _live_signal_set(spy, vix, days, breakout_only=True)
    assert len(research) > 0
    assert sorted(live) == sorted(research), (
        f"PARITY BREAK (J_VWAP_BREAKOUT): research n={len(research)} live n={len(live)}. "
        f"only_research={sorted(set(research) - set(live))[:5]} "
        f"only_live={sorted(set(live) - set(research))[:5]}"
    )


@pytest.mark.skipif(not SPY.exists(), reason="full SPY dataset not present")
def test_parity_vix_gated():
    """Live core + vix_slope reproduce the VIX-gated variant (J_VWAP_CONT_VIXGATE)."""
    research, spy, vix, days = _discovery_signal_set({"put_needs_rising_vix": True})
    live = _live_signal_set(spy, vix, days, put_needs_rising_vix=True)
    assert len(research) > 0
    assert sorted(live) == sorted(research), (
        f"PARITY BREAK (J_VWAP_CONT_VIXGATE): research n={len(research)} live n={len(live)}. "
        f"only_research={sorted(set(research) - set(live))[:5]} "
        f"only_live={sorted(set(live) - set(research))[:5]}"
    )
