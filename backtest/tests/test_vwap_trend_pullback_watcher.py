"""Parity + unit tests for the VWAP_TREND_PULLBACK (H4) live watcher.

THE LOAD-BEARING TEST (`test_parity_with_batch_detector`): the live streaming
detector must fire the SAME signals — same trigger bar, same side, same chart stop —
as the validated batch detector ``infinite_ammo_discovery.detect_vwap_pullback`` that
produced the ratified numbers (analysis/recommendations/vwap-trend-pullback-LIVE.json).
If they diverge, the live engine would NOT be trading the edge that was validated.

We replay real SPY 5m bars (the same CSV the discovery + ratify harness use) one bar
at a time through the watcher, building a BarContext whose ``prior_bars`` is the full
history up to and including the current bar (exactly what the ctx-only watchers get
live), and assert the emitted (bar_idx, side, stop) set equals the batch detector's.

Plus targeted unit tests: warmup safety, one-entry-per-day, no-clean-trend -> no fire,
day-state reset, and chart-stop direction.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]          # .../backtest
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO.parent))

from lib.filters import BarContext
import lib.watchers.vwap_trend_pullback_watcher as W
from lib.watchers.vwap_trend_pullback_watcher import detect_vwap_trend_pullback_setup
from autoresearch.infinite_ammo_discovery import (
    load_spy,
    build_day_contexts,
    detect_vwap_pullback,
)
from lib.ribbon import compute_ribbon

_SPY_CSV = _REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"


@pytest.fixture(scope="module")
def spy_df():
    return load_spy(str(_SPY_CSV))


def _reset_watcher_state():
    W._state_date = None
    W._trend_side = None
    W._trend_resolved = False
    W._fired_today = False


def _ctx_for(spy_df: pd.DataFrame, global_idx: int) -> BarContext:
    """Build a BarContext at spy_df row `global_idx` with full prior history.

    Mirrors what the ctx-only watchers receive live: prior_bars = all bars up to and
    including the trigger bar (the watcher filters to today's RTH itself).
    """
    bar = spy_df.iloc[global_idx]
    prior = spy_df.iloc[: global_idx + 1].copy()
    ts = bar["timestamp_et"]
    ts_py = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    return BarContext(
        bar_idx=global_idx,
        timestamp_et=ts_py,
        bar=bar,
        prior_bars=prior,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=17.0,
        vix_prior=17.0,
        vol_baseline_20=float(prior["volume"].tail(20).mean()),
        range_baseline_20=1.0,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
        level_states={},
    )


def _pick_signal_days(spy_df, n_days=6):
    """Find historical days where the batch detector fires (so parity has content)."""
    ribbon = compute_ribbon(pd.Series(spy_df["close"].values))
    days = build_day_contexts(spy_df)
    sigs = detect_vwap_pullback(spy_df, ribbon, None, days)
    # Map each signal to its date; return the first n_days distinct signal dates.
    seen = []
    for s in sigs:
        d = spy_df.iloc[s.bar_idx]["date"]
        if d not in seen:
            seen.append(d)
        if len(seen) >= n_days:
            break
    return sigs, seen


def test_parity_with_batch_detector(spy_df):
    """Live streaming detector == batch detector on real historical days.

    For each selected signal day, replay every RTH bar through the watcher and collect
    its emitted (global_bar_idx, side, round(stop,2)); compare to the batch detector's
    signals on those same days. Must be identical.
    """
    batch_sigs, signal_days = _pick_signal_days(spy_df, n_days=8)
    assert signal_days, "no batch signals found — fixture/data problem"

    # Batch expectation restricted to the selected days.
    batch_expect = {
        (s.bar_idx, s.side, round(s.stop_level or 0.0, 2))
        for s in batch_sigs
        if spy_df.iloc[s.bar_idx]["date"] in signal_days
    }

    # Stream the watcher across every bar of those days (chronological).
    live_got = set()
    day_set = set(signal_days)
    idxs = [i for i in range(len(spy_df)) if spy_df.iloc[i]["date"] in day_set]
    _reset_watcher_state()
    for gi in idxs:
        ctx = _ctx_for(spy_df, gi)
        sig = detect_vwap_trend_pullback_setup(ctx)
        if sig is not None:
            side = "C" if sig.direction == "long" else "P"
            live_got.add((gi, side, round(sig.stop_price, 2)))

    assert live_got == batch_expect, (
        "live watcher diverged from validated batch detector.\n"
        f"  only in batch: {sorted(batch_expect - live_got)}\n"
        f"  only in live : {sorted(live_got - batch_expect)}"
    )
    # And we actually exercised real signals (not a vacuous pass).
    assert len(batch_expect) >= 5, f"too few parity signals to be meaningful: {len(batch_expect)}"


def test_warmup_returns_none(spy_df):
    """Before TREND_BARS+1 RTH bars exist, the detector must not fire."""
    _reset_watcher_state()
    days = build_day_contexts(spy_df)
    dc = days[10]
    # First RTH bar of the day -> only 1 bar of session history.
    ctx = _ctx_for(spy_df, dc.idx0)
    assert detect_vwap_trend_pullback_setup(ctx) is None


def test_no_clean_trend_no_fire():
    """A choppy open (closes straddle VWAP in the first 6 bars) -> never fires."""
    _reset_watcher_state()
    base = dt.datetime(2026, 5, 20, 9, 30)
    rows = []
    # Alternate above/below so the first 6 closes are not all one side of VWAP.
    px = [540.0, 539.0, 540.5, 539.2, 540.4, 539.1, 540.6, 539.0, 540.7, 539.0]
    for i, c in enumerate(px):
        rows.append({
            "timestamp_et": pd.Timestamp(base + dt.timedelta(minutes=5 * i)),
            "open": c, "high": c + 0.4, "low": c - 0.4, "close": c, "volume": 300_000,
        })
    df = pd.DataFrame(rows)
    fired = False
    for gi in range(len(df)):
        bar = df.iloc[gi]
        ctx = BarContext(
            bar_idx=gi, timestamp_et=bar["timestamp_et"].to_pydatetime(), bar=bar,
            prior_bars=df.iloc[: gi + 1].copy(), ribbon_now=None, ribbon_history=[],
            vix_now=17.0, vix_prior=17.0, vol_baseline_20=300_000.0, range_baseline_20=1.0,
            levels_active=[], multi_day_levels=[], htf_15m_stack=None, level_states={},
        )
        if detect_vwap_trend_pullback_setup(ctx) is not None:
            fired = True
    assert not fired, "fired on a non-trending (chop) open"


def test_one_entry_per_day_and_stop_direction():
    """Clean uptrend then two VWAP tags -> exactly ONE call signal; stop below entry."""
    _reset_watcher_state()
    base = dt.datetime(2026, 5, 20, 9, 30)
    rows = []
    # 6 strong-up bars (each close well above a rising VWAP), then a dip that tags
    # VWAP and closes above it (entry), then another similar tag (must be suppressed).
    closes = [540.0, 540.6, 541.2, 541.8, 542.4, 543.0,   # trend window (rising)
              542.0,                                        # pullback tag #1 -> entry
              543.5, 542.2]                                 # later bars incl tag #2
    sig_count = 0
    first_sig = None
    df_rows = []
    for i, c in enumerate(closes):
        df_rows.append({
            "timestamp_et": pd.Timestamp(base + dt.timedelta(minutes=5 * i)),
            "open": c, "high": c + 0.5, "low": c - 0.8, "close": c, "volume": 300_000,
        })
    df = pd.DataFrame(df_rows)
    for gi in range(len(df)):
        bar = df.iloc[gi]
        ctx = BarContext(
            bar_idx=gi, timestamp_et=bar["timestamp_et"].to_pydatetime(), bar=bar,
            prior_bars=df.iloc[: gi + 1].copy(), ribbon_now=None, ribbon_history=[],
            vix_now=17.0, vix_prior=17.0, vol_baseline_20=300_000.0, range_baseline_20=1.0,
            levels_active=[], multi_day_levels=[], htf_15m_stack=None, level_states={},
        )
        s = detect_vwap_trend_pullback_setup(ctx)
        if s is not None:
            sig_count += 1
            if first_sig is None:
                first_sig = s
    assert sig_count == 1, f"expected exactly one entry/day, got {sig_count}"
    assert first_sig.direction == "long"
    assert first_sig.stop_price < first_sig.entry_price, "call chart-stop must be below entry"
    assert first_sig.setup_name == "VWAP_TREND_PULLBACK"
    assert first_sig.metadata["promotion_status"] == "WATCH_ONLY"


def test_day_state_resets():
    """A new date clears the fired flag (so day 2 can fire again)."""
    _reset_watcher_state()
    W._state_date = "2026-05-20"
    W._fired_today = True
    W._trend_resolved = True
    W._trend_side = "C"
    # A bar on a NEW date during warmup should reset state (and then return None for warmup).
    bar = pd.Series({
        "timestamp_et": pd.Timestamp("2026-05-21 09:30"),
        "open": 540.0, "high": 540.5, "low": 539.5, "close": 540.1, "volume": 300_000,
    })
    ctx = BarContext(
        bar_idx=0, timestamp_et=bar["timestamp_et"].to_pydatetime(), bar=bar,
        prior_bars=pd.DataFrame([bar]), ribbon_now=None, ribbon_history=[],
        vix_now=17.0, vix_prior=17.0, vol_baseline_20=300_000.0, range_baseline_20=1.0,
        levels_active=[], multi_day_levels=[], htf_15m_stack=None, level_states={},
    )
    detect_vwap_trend_pullback_setup(ctx)
    assert W._state_date == "2026-05-21"
    assert W._fired_today is False
