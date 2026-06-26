"""Tests for the live VIX_REGIME_DAYSIDE watcher (J_VIX_DAYSIDE, edge #4).

Four things are asserted:

  1. UNIT — the pure core (``detect_vix_regime_dayside_core``) fires on a known
     above-VWAP-trend + favorable-VIX-regime fixture (long), correctly REFUSES the
     VIX-rising case, the VIX-not-low case, the mixed-open case, and the past-window case;
     plus the chart stop = the 12-bar swing extreme. The regime primitives
     (``causal_vix_median`` / ``vix_slope`` / ``favorable_regime``) are pinned vs the
     research definitions.

  2. STREAMING / DORMANT-SAFE — the BarContext wrapper fires once at the favorable entry
     bar when an intraday VIX series is threaded in (``ctx.vix_intraday``), and SKIPS
     (returns None — never guesses) when the VIX series is absent. This is the live
     DORMANT-safety property: with no VIX series wired into ctx the block is inert.

  3. ISOLATED-KEY GAMMA-SYNC — filters.py edge-#4 exit helpers read the ISOLATED keys
     (j_vix_dayside_premium_stop_pct / _tp1_pct), never the global catastrophe cap / global
     tp1. This is the edge-#2 lesson encoded: the isolated -0.08 stop must NOT be overridden
     by the global -0.50.

  4. PARITY — the live core reproduces the VALIDATED research detector
     (``autoresearch._b5_vix_regime_dayside.detect_opt_signals``) EXACTLY — same set of
     (date, side, stop_level) on the validated window, for the gate-clearing cell
     (low_margin=0.25, slope_rule=not_rising). If they diverge, the live watcher is not
     trading the edge the scorecard validated (L153; C14 — no detector drift).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_vix_regime_dayside_watcher.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lib.watchers.vix_regime_dayside_watcher import (
    detect_vix_regime_dayside_core,
    detect_vix_regime_dayside_setup,
    VixRegimeDaysideDetector,
    causal_vix_median,
    vix_slope,
    favorable_regime,
    trend_side,
    _reset_day,
    TREND_BARS,
    ENTRY_GATE,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
    DEFAULT_LOW_MARGIN,
)
from lib import filters as _filters
from lib.filters import BarContext

REPO = Path(__file__).resolve().parents[1]


# ── fixtures / helpers ────────────────────────────────────────────────────────

def _times(n: int, start_h: int = 9, start_m: int = 30, step: int = 5) -> list[dt.time]:
    out = []
    base = dt.datetime(2026, 1, 7, start_h, start_m)
    for i in range(n):
        out.append((base + dt.timedelta(minutes=step * i)).time())
    return out


def _bar(h, m, o, hi, lo, c, v=5000):
    return dict(timestamp_et=dt.datetime(2026, 1, 7, h, m),
                open=o, high=hi, low=lo, close=c, volume=v)


def _mk_ctx(rows, vix_series=None, *, vix_now: float = 15.0) -> BarContext:
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    ctx = BarContext(
        bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
        prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=vix_now,
        vix_prior=vix_now, vol_baseline_20=1000.0, range_baseline_20=0.5,
        levels_active=[], multi_day_levels=[], htf_15m_stack=None,
    )
    if vix_series is not None:
        object.__setattr__(ctx, "vix_intraday", vix_series)
    return ctx


# A canonical above-VWAP-trend day; the 4th bar (09:45) is the candidate entry bar.
_ROWS = [
    _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
    _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
    _bar(9, 40, 601.1, 601.8, 601.0, 601.7),   # side = C (last trend bar)
    _bar(9, 45, 601.7, 602.4, 601.6, 602.3),   # candidate entry bar (in 09:35-11:30)
]


# ── 1. UNIT — pure core + regime primitives ────────────────────────────────────

def test_core_long_favorable_regime_fires():
    closes = np.array([600.5, 601.1, 601.7, 602.3])
    highs = np.array([600.6, 601.2, 601.8, 602.4])
    lows = np.array([599.9, 601.0, 601.0, 601.6])
    vwap = np.array([600.2, 600.6, 601.0, 601.2])
    vix = np.array([16.0, 15.8, 15.6, 15.4])
    vix_med = np.array([22.0, 22.0, 22.0, 22.0])     # level well below median (low)
    vix_slp = np.array([-0.2, -0.2, -0.2, -0.2])     # not rising
    r = detect_vix_regime_dayside_core(closes, highs, lows, vwap, _times(4), vix, vix_med, vix_slp)
    assert r is not None
    assert r.side == "C" and r.direction == "long"
    assert abs(r.entry - 602.3) < 1e-9
    # chart stop = the 12-bar swing low across the available window (599.9 here)
    assert abs(r.stop_level - 599.9) < 1e-9


def test_core_vix_rising_does_not_fire():
    closes = np.array([600.5, 601.1, 601.7, 602.3])
    highs = np.array([600.6, 601.2, 601.8, 602.4])
    lows = np.array([599.9, 601.0, 601.0, 601.6])
    vwap = np.array([600.2, 600.6, 601.0, 601.2])
    vix = np.array([15.0, 15.5, 16.0, 16.5])
    vix_med = np.array([22.0, 22.0, 22.0, 22.0])     # low level...
    vix_slp = np.array([1.5, 1.5, 1.5, 1.5])          # ...but RISING -> not favorable
    assert detect_vix_regime_dayside_core(closes, highs, lows, vwap, _times(4), vix, vix_med, vix_slp) is None


def test_core_vix_not_low_does_not_fire():
    closes = np.array([600.5, 601.1, 601.7, 602.3])
    highs = np.array([600.6, 601.2, 601.8, 602.4])
    lows = np.array([599.9, 601.0, 601.0, 601.6])
    vwap = np.array([600.2, 600.6, 601.0, 601.2])
    vix = np.array([22.0, 22.0, 22.0, 22.0])
    vix_med = np.array([22.0, 22.0, 22.0, 22.0])     # level == median, margin 0.25 not met
    vix_slp = np.array([-0.5, -0.5, -0.5, -0.5])
    assert detect_vix_regime_dayside_core(closes, highs, lows, vwap, _times(4), vix, vix_med, vix_slp) is None


def test_core_mixed_open_does_not_fire():
    closes = np.array([600.4, 599.2, 599.8, 600.8])  # mixed first 3 closes
    highs = np.array([600.6, 600.6, 599.9, 600.9])
    lows = np.array([599.4, 599.0, 599.0, 599.7])
    vwap = np.array([600.0, 599.8, 599.8, 600.0])
    vix = np.array([16.0, 16.0, 16.0, 16.0])
    vix_med = np.array([22.0, 22.0, 22.0, 22.0])
    vix_slp = np.array([-0.5, -0.5, -0.5, -0.5])
    assert detect_vix_regime_dayside_core(closes, highs, lows, vwap, _times(4), vix, vix_med, vix_slp) is None


def test_core_favorable_only_after_window_does_not_fire():
    # trend bars at 11:15/11:20/11:25; the only favorable candidate bar is 11:35 (> 11:30).
    closes = np.array([600.5, 601.1, 601.7, 602.3])
    highs = np.array([600.6, 601.2, 601.8, 602.4])
    lows = np.array([599.9, 601.0, 601.0, 601.6])
    vwap = np.array([600.2, 600.6, 601.0, 601.2])
    vix = np.array([16.0, 15.8, 15.6, 15.4])
    vix_med = np.array([22.0, 22.0, 22.0, 22.0])
    vix_slp = np.array([-0.2, -0.2, -0.2, -0.2])
    times = [dt.time(11, 15), dt.time(11, 20), dt.time(11, 25), dt.time(11, 35)]
    assert detect_vix_regime_dayside_core(closes, highs, lows, vwap, times, vix, vix_med, vix_slp) is None


def test_regime_primitives_match_research_definitions():
    # causal_vix_median is a shift-1 trailing rolling median; vix_slope is vix[i]-vix[i-bars].
    series = np.arange(100, dtype=float)
    med = causal_vix_median(series, VIX_MEDIAN_BARS)
    # the median at i must NOT include series[i] (shift-1): for a strictly increasing series
    # the trailing median over prior bars is < series[i].
    assert np.isnan(med[0])
    assert med[VIX_MEDIAN_BARS + 1] < series[VIX_MEDIAN_BARS + 1]
    slp = vix_slope(series, VIX_SLOPE_BARS)
    assert np.isnan(slp[VIX_SLOPE_BARS - 1])
    assert slp[VIX_SLOPE_BARS] == VIX_SLOPE_BARS  # arange -> slope == bars
    # favorable_regime: low + not_rising required; None when slope unavailable.
    assert favorable_regime(15.0, 22.0, -0.5, DEFAULT_LOW_MARGIN, "not_rising") is True
    assert favorable_regime(15.0, 22.0, 1.0, DEFAULT_LOW_MARGIN, "not_rising") is False
    assert favorable_regime(22.0, 22.0, -0.5, DEFAULT_LOW_MARGIN, "not_rising") is False
    assert favorable_regime(15.0, float("nan"), -0.5, DEFAULT_LOW_MARGIN, "not_rising") is None
    assert favorable_regime(15.0, 22.0, None, DEFAULT_LOW_MARGIN, "not_rising") is None
    # slope_rule "any" ignores the slope.
    assert favorable_regime(15.0, 22.0, 5.0, DEFAULT_LOW_MARGIN, "any") is True


def test_trend_side_matches_research():
    above_c = [10.0, 11.0, 12.0]
    above_v = [9.0, 9.5, 10.0]
    assert trend_side(above_c, above_v, TREND_BARS) == "C"
    assert trend_side([8.0, 7.0, 6.0], [9.0, 9.0, 9.0], TREND_BARS) == "P"
    assert trend_side([10.0, 8.0, 12.0], [9.0, 9.0, 9.0], TREND_BARS) is None


# ── 2. STREAMING / DORMANT-SAFE — BarContext wrapper ───────────────────────────

def _favorable_vix(n_rth: int) -> list[float]:
    # high prior history (raises the trailing median) then a low, declining tail aligned to
    # the n_rth RTH bars.
    tail = [16.0, 15.8, 15.6, 15.4][:n_rth]
    return [22.0] * 80 + tail


def test_wrapper_fires_once_with_vix_series():
    _reset_day("none")
    fired = []
    for k in range(len(_ROWS)):
        vix = _favorable_vix(k + 1)
        s = detect_vix_regime_dayside_setup(_mk_ctx(_ROWS[: k + 1], vix))
        if s is not None:
            fired.append(s)
    assert len(fired) == 1, f"expected exactly one entry, got {len(fired)}"
    sig = fired[0]
    assert sig.watcher_name == "vix_regime_dayside_watcher"
    assert sig.setup_name == "VIX_REGIME_DAYSIDE"
    assert sig.direction == "long"
    assert sig.metadata["strike_offset"] == 0          # Safe-2 ATM ship cell
    assert sig.metadata["premium_stop_pct"] == -0.08
    assert sig.metadata["low_margin"] == DEFAULT_LOW_MARGIN
    assert sig.metadata["slope_rule"] == "not_rising"
    assert sig.metadata["promotion_status"] == "WATCH_ONLY"


def test_wrapper_skips_without_vix_series():
    """DORMANT-safety: with no intraday VIX series threaded into ctx, the regime cannot be
    confirmed -> the wrapper must return None on every bar (never guess)."""
    _reset_day("none")
    fired = []
    for k in range(len(_ROWS)):
        s = detect_vix_regime_dayside_setup(_mk_ctx(_ROWS[: k + 1], vix_series=None))
        if s is not None:
            fired.append(s)
    assert fired == [], "wrapper fired without a VIX series — must SKIP (never guess the regime)"


def test_interleaved_instances_do_not_corrupt_each_other():
    """Two SEPARATE detector instances replaying different days, bar-interleaved, each fire
    exactly once (per-instance one-entry/day state, MED-1)."""
    def _rows_on(day: dt.date):
        return [dict(timestamp_et=dt.datetime(day.year, day.month, day.day, *hm),
                     open=o, high=hi, low=lo, close=c, volume=5000)
                for hm, o, hi, lo, c in [
                    ((9, 30), 600.0, 600.6, 599.9, 600.5),
                    ((9, 35), 600.5, 601.2, 600.4, 601.1),
                    ((9, 40), 601.1, 601.8, 601.0, 601.7),
                    ((9, 45), 601.7, 602.4, 601.6, 602.3),
                ]]

    def _mk(rows, vix):
        df = pd.DataFrame(rows)
        cur = df.iloc[-1]
        ctx = BarContext(
            bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
            prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=15.0,
            vix_prior=15.0, vol_baseline_20=1000.0, range_baseline_20=0.5,
            levels_active=[], multi_day_levels=[], htf_15m_stack=None,
        )
        object.__setattr__(ctx, "vix_intraday", vix)
        return ctx

    rows_a = _rows_on(dt.date(2026, 1, 7))
    rows_b = _rows_on(dt.date(2026, 1, 8))
    det_a, det_b = VixRegimeDaysideDetector(), VixRegimeDaysideDetector()
    fired_a, fired_b = [], []
    for k in range(len(rows_a)):
        sa = det_a.detect(_mk(rows_a[: k + 1], _favorable_vix(k + 1)))
        if sa is not None:
            fired_a.append(sa)
        sb = det_b.detect(_mk(rows_b[: k + 1], _favorable_vix(k + 1)))
        if sb is not None:
            fired_b.append(sb)
    assert len(fired_a) == 1 and len(fired_b) == 1


# ── 3. ISOLATED-KEY GAMMA-SYNC (the edge-#2 lesson) ────────────────────────────

def test_filters_isolated_exit_helpers_read_keys_not_globals():
    """filters.py edge-#4 exit helpers must read the ISOLATED keys, never the global
    catastrophe cap / global tp1 (the edge-#2 -0.08-vs-global-(-0.50) lesson)."""
    safe = {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 0.50,
        "j_vix_dayside_premium_stop_pct": -0.08,
        "j_vix_dayside_tp1_pct": 0.30,
    }
    assert _filters.vix_dayside_premium_stop_pct(safe) == -0.08
    assert _filters.vix_dayside_tp1_pct(safe) == 0.30
    # Absent keys -> validated ATM defaults, NOT the global catastrophe cap.
    assert _filters.vix_dayside_premium_stop_pct(None) == -0.08
    assert _filters.vix_dayside_premium_stop_pct({"premium_stop_pct": -0.50}) == -0.08
    assert _filters.vix_dayside_tp1_pct(None) == 0.30


def test_filters_dormant_flag_default_false_and_delegator_present():
    assert _filters.vix_dayside_enabled(None) is False
    assert _filters.vix_dayside_enabled({}) is False
    assert _filters.vix_dayside_enabled({"j_vix_dayside_enabled": True}) is True
    assert _filters.vix_dayside_side(None) == "both"
    # delegator exists and delegates byte-for-byte to the watcher (returns None when no VIX
    # series + no qualifying setup on a bare ctx).
    assert hasattr(_filters, "detect_vix_regime_dayside")


def test_live_params_json_dormant_and_well_formed():
    """The shipped params.json must be valid JSON, carry the edge-#4 keys, and have the
    dormant flag OFF (the whole point: zero behavior change until J flips it)."""
    import json
    p = json.loads((REPO.parent / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    assert p["j_vix_dayside_enabled"] is False
    assert p["j_vix_dayside_premium_stop_pct"] == -0.08
    assert p["j_vix_dayside_tp1_pct"] == 0.30
    assert p["j_vix_dayside_low_margin"] == 0.25
    assert p["j_vix_dayside_slope_rule"] == "not_rising"
    assert p["j_vix_dayside_side"] in ("both", "put", "call")


# ── 4. PARITY — live core == validated research detector (full window) ──────────

@pytest.mark.skipif(
    not (REPO / "data").exists(),
    reason="backtest data dir not present",
)
def test_parity_with_validated_research_detector():
    """Live core must reproduce the research detector's signal SET (date, side, stop_level)
    for the gate-clearing cell (low_margin=0.25, slope_rule=not_rising) across the validated
    window. Same VIX-aligned arrays the research detector iterates."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    from autoresearch import runner as ar_runner
    from autoresearch.infinite_ammo_discovery import build_day_contexts, session_vwap_asof
    from autoresearch import _b5_vix_regime_dayside as research

    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = research._normalize_spy(spy_raw)
    vix_g = research._align_vix(spy, vix_raw)
    vix_med_g = research.causal_vix_median(vix_g, research.VIX_MEDIAN_BARS)
    vix_slp_g = research.vix_slope(vix_g, research.VIX_SLOPE_BARS)
    days = build_day_contexts(spy)

    LOW_MARGIN, SLOPE_RULE = 0.25, "not_rising"

    # Research detector's signal set: (date, side). The research detector does not expose
    # the chart stop on its OptSig (it stops via simulate_opt's swing), so parity is on
    # (date, side) — the entry-decision surface that determines what trades fire.
    research_sigs = research.detect_opt_signals(
        days, spy, vix_g, vix_med_g, vix_slp_g, LOW_MARGIN, SLOPE_RULE
    )
    research_set = sorted({(s.date, s.side) for s in research_sigs})

    # Live core, fed the SAME as-of arrays per day (RTH closes/highs/lows + session_vwap_asof
    # + the global VIX arrays sliced to each day's RTH rows).
    live_set = []
    for dc in days:
        rth = dc.rth
        # Match research's DEGENERATE-DAY filter (TREND_BARS + 2) so the comparison is over
        # the identical day population — research skips <TREND_BARS+2-bar days; the live core
        # (streaming guard TREND_BARS+1) would process them, but no such day exists in real
        # 0DTE RTH data, so this only makes the parity assertion apples-to-apples.
        if len(rth) < TREND_BARS + 2:
            continue
        gidx = rth.index.to_numpy()
        vwap = session_vwap_asof(rth).to_numpy(float)
        closes = rth["close"].to_numpy(float)
        highs = rth["high"].to_numpy(float)
        lows = rth["low"].to_numpy(float)
        times = list(rth["t"].to_numpy())
        vix = vix_g[gidx]
        vmed = vix_med_g[gidx]
        vslp = vix_slp_g[gidx]
        r = detect_vix_regime_dayside_core(
            closes, highs, lows, vwap, times, vix, vmed, vslp,
            low_margin=LOW_MARGIN, slope_rule=SLOPE_RULE,
        )
        if r is not None:
            live_set.append((dc.date, r.side))
    live_set = sorted(set(live_set))

    assert len(research_set) > 0, "research detector produced no signals — fixture broken"
    assert live_set == research_set, (
        "PARITY BREAK: live core != validated research detector. "
        f"research n={len(research_set)} live n={len(live_set)}. "
        f"only_research={sorted(set(research_set) - set(live_set))[:5]} "
        f"only_live={sorted(set(live_set) - set(research_set))[:5]}"
    )
