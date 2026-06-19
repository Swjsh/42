"""Tests for the live GAP_AND_GO watcher — unit + PARITY with the validated detector.

The headline test is PARITY: the live detector (detect_gap_and_go_core, the pure core
the watcher uses) must produce the EXACT same (date, side, stop_level) signals as the
VALIDATED research detector (autoresearch.infinite_ammo_discovery.detect_gap_and_go)
across the full 2025-01..2026-06 dataset. If they diverge, the live watcher is not
trading the edge that was validated (L153 — backtest triggers must map to live
categories). This is the test that lets the scorecard's numbers be claimed for the
LIVE detector, not just the research one.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_gap_and_go_watcher.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from lib.watchers.gap_and_go_watcher import (
    detect_gap_and_go_core,
    detect_gap_and_go_setup,
    MIN_GAP,
    MAX_GAP,
)
from lib.filters import BarContext

REPO = Path(__file__).resolve().parents[1]
SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"


# ── unit: pure core ──────────────────────────────────────────────────────────

def test_core_gap_up_green_is_calls():
    r = detect_gap_and_go_core(600.0, 603.0, 604.2, 602.8, 604.0)
    assert r is not None and r.side == "C" and r.direction == "long"
    assert r.stop_level == 602.8  # first-bar low


def test_core_gap_down_red_is_puts():
    r = detect_gap_and_go_core(600.0, 597.0, 597.2, 595.8, 596.0)
    assert r is not None and r.side == "P" and r.direction == "short"
    assert r.stop_level == 597.2  # first-bar high


def test_core_gap_up_red_does_not_fire():
    # gap up but first bar red = a fade setup, NOT gap-and-go
    assert detect_gap_and_go_core(600.0, 603.0, 603.2, 601.5, 602.0) is None


def test_core_gap_down_green_does_not_fire():
    assert detect_gap_and_go_core(600.0, 597.0, 598.5, 596.9, 598.0) is None


def test_core_gap_too_small():
    # +0.10% < 0.25% min
    assert detect_gap_and_go_core(600.0, 600.6, 601.0, 600.4, 601.0) is None


def test_core_gap_too_large():
    # +2.0% > 1.5% max
    assert detect_gap_and_go_core(600.0, 612.0, 613.0, 611.5, 612.8) is None


def test_core_bad_prior_close():
    assert detect_gap_and_go_core(0.0, 603.0, 604.0, 602.0, 603.5) is None
    assert detect_gap_and_go_core(-1.0, 603.0, 604.0, 602.0, 603.5) is None


def test_core_boundary_min_gap_just_above():
    # just ABOVE +0.25% with a green bar -> fires (inclusive boundary, matches
    # discovery). Use a small epsilon over MIN_GAP to avoid float-equality on the
    # exact boundary (600*(1+0.0025) lands a hair BELOW 0.0025 in float, correctly
    # not firing — which the parity test already confirms matches the research code).
    prior = 600.0
    first_open = prior * (1 + MIN_GAP + 1e-4)
    r = detect_gap_and_go_core(prior, first_open, first_open + 1, first_open - 0.1,
                               first_open + 0.5)
    assert r is not None and r.side == "C"


# ── unit: ctx wrapper gates ──────────────────────────────────────────────────

def _mk_ctx(rows, vix=17.0):
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
        prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=vix,
        vix_prior=vix, vol_baseline_20=1000.0, range_baseline_20=0.5,
        levels_active=[], multi_day_levels=[], htf_15m_stack=None,
    )


def test_wrapper_only_fires_on_open_bar():
    rows = [
        dict(timestamp_et=dt.datetime(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=dt.datetime(2026, 1, 7, 9, 35), open=603.0, high=604.2, low=602.8, close=604.0, volume=5000),
    ]
    assert detect_gap_and_go_setup(_mk_ctx(rows)) is None  # 09:35, not the open bar


def test_wrapper_derives_prior_close_from_multiday():
    rows = [
        dict(timestamp_et=dt.datetime(2026, 1, 6, 15, 55), open=600.5, high=600.8, low=599.8, close=600.0, volume=1000),
        dict(timestamp_et=dt.datetime(2026, 1, 7, 9, 30), open=603.0, high=604.2, low=602.8, close=604.0, volume=5000),
    ]
    sig = detect_gap_and_go_setup(_mk_ctx(rows))
    assert sig is not None and sig.direction == "long"
    assert sig.stop_price == 602.8
    assert sig.metadata["prior_rth_close"] == 600.0
    assert sig.metadata["premium_stop_pct"] == -0.99  # chart-stop only


def test_wrapper_explicit_prior_close_single_day():
    rows = [dict(timestamp_et=dt.datetime(2026, 1, 7, 9, 30), open=597.0, high=597.2, low=595.8, close=596.0, volume=5000)]
    sig = detect_gap_and_go_setup(_mk_ctx(rows), prior_rth_close=600.0)
    assert sig is not None and sig.direction == "short" and sig.stop_price == 597.2


def test_wrapper_no_prior_close_returns_none():
    rows = [dict(timestamp_et=dt.datetime(2026, 1, 7, 9, 30), open=603.0, high=604.2, low=602.8, close=604.0, volume=5000)]
    assert detect_gap_and_go_setup(_mk_ctx(rows)) is None  # single-day frame, no explicit close


# ── PARITY: live core vs validated research detector over the FULL dataset ────

@pytest.mark.skipif(not SPY.exists(), reason="full SPY dataset not present")
def test_parity_with_validated_discovery_detector():
    """Live detect_gap_and_go_core must reproduce the research detector's signals
    EXACTLY (same date, side, stop_level) across all 363 days."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from autoresearch.infinite_ammo_discovery import (
        load_spy, align_vix, build_day_contexts, detect_gap_and_go, _gap_setup,
    )
    from lib.ribbon import compute_ribbon

    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)

    # Research detector's signal set: (date, side, stop_level)
    research = []
    for sg in detect_gap_and_go(spy, ribbon, vix, days):
        bar = spy.iloc[sg.bar_idx]
        research.append((bar["date"], sg.side, round(float(sg.stop_level), 4)))

    # Live core, fed the SAME inputs (prior close + first RTH bar) via _gap_setup,
    # which yields (dc, gap, first_idx, first_bar) for every gapped day.
    live = []
    for dc, gap, fidx, fbar in _gap_setup(days):
        r = detect_gap_and_go_core(
            dc.prior_close, float(fbar["open"]), float(fbar["high"]),
            float(fbar["low"]), float(fbar["close"]),
        )
        if r is not None:
            live.append((dc.date, r.side, round(float(r.stop_level), 4)))

    assert len(research) > 0, "research detector produced no signals — fixture broken"
    assert sorted(live) == sorted(research), (
        f"PARITY BREAK: live core != validated detector. "
        f"research n={len(research)} live n={len(live)}. "
        f"only_research={sorted(set(research) - set(live))[:5]} "
        f"only_live={sorted(set(live) - set(research))[:5]}"
    )
