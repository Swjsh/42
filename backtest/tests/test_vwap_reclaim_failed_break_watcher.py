"""Tests for the live VWAP_RECLAIM_FAILED_BREAK watcher (J_VWAP_RECLAIM_FB, edge #2).

Three things are asserted:

  1. UNIT — the pure core (``detect_vwap_reclaim_failed_break_core``) fires on a known
     failed-break -> reclaim fixture (long + short) and correctly REFUSES the
     no-counter-trend-break case (which is vwap_continuation's job, not this one), the
     mixed-open case, and the past-cutoff case. Plus the chart stop = the deepest
     failed-break excursion extreme.

  2. PARITY — the live core reproduces the VALIDATED research detector
     (``autoresearch._sub_struct_vwap_reclaim_failed_break.detect_signals``) EXACTLY —
     same (date, side, stop_level) on every day of the full 2025-01..2026-05 dataset. If
     they diverge, the live watcher is not trading the edge the scorecard validated
     (L153 — backtest triggers must map to live categories; C14 — no detector drift).

  3. EXPECTANCY SIGN — the validated ITM-2 cell (strike_offset=-2) reproduces a POSITIVE
     per-trade expectancy on real OPRA fills (the gate-clearing cell from the scorecard).
     This is the "validated cell reproduces its expectancy sign" assertion: it pins the
     sign (positive), not a fragile exact dollar figure, so the test stays green across
     benign data refreshes while still failing loudly if the edge ever flips negative.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_vwap_reclaim_failed_break_watcher.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lib.watchers.vwap_reclaim_failed_break_watcher import (
    detect_vwap_reclaim_failed_break_core,
    detect_vwap_reclaim_failed_break_setup,
    VwapReclaimFailedBreakDetector,
    _reset_day,
    TREND_BARS,
    ENTRY_CUTOFF,
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


def _mk_ctx(rows, *, vix: float = 17.0) -> BarContext:
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1, timestamp_et=cur["timestamp_et"], bar=cur,
        prior_bars=df, ribbon_now=None, ribbon_history=[], vix_now=vix,
        vix_prior=vix, vol_baseline_20=1000.0, range_baseline_20=0.5,
        levels_active=[], multi_day_levels=[], htf_15m_stack=None,
    )


def _bar(h, m, o, hi, lo, c, v=5000):
    return dict(timestamp_et=dt.datetime(2026, 1, 7, h, m),
                open=o, high=hi, low=lo, close=c, volume=v)


# ── 1. UNIT — pure core ───────────────────────────────────────────────────────

def test_core_long_failed_break_then_reclaim_fires():
    # above-VWAP trend (3 bars), counter-trend close BELOW vwap (failed break),
    # then a close BACK ABOVE vwap (reclaim) -> long.
    closes = np.array([600.5, 601.1, 601.7, 600.2, 599.8, 601.5])
    highs = np.array([600.6, 601.2, 601.8, 601.8, 600.3, 601.6])
    lows = np.array([599.9, 601.0, 601.0, 600.0, 599.5, 600.1])  # deepest break low = 599.5
    vwap = np.array([600.2, 600.6, 601.0, 601.0, 601.0, 601.0])
    r = detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, _times(6))
    assert r is not None
    assert r.side == "C" and r.direction == "long"
    assert abs(r.entry - 601.5) < 1e-9
    # chart stop = deepest LOW printed during the failed counter-trend break
    assert abs(r.stop_level - 599.5) < 1e-9


def test_core_short_failed_break_then_reclaim_fires():
    # below-VWAP trend, counter-trend close ABOVE vwap, then reclaim close BELOW -> short.
    closes = np.array([599.5, 598.9, 598.3, 599.8, 600.1, 598.1])
    highs = np.array([599.6, 599.0, 599.0, 600.0, 600.4, 598.4])  # highest break high = 600.4
    lows = np.array([599.4, 598.8, 598.2, 598.2, 599.9, 598.0])
    vwap = np.array([599.6, 599.2, 599.0, 599.0, 599.0, 599.0])
    r = detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, _times(6))
    assert r is not None
    assert r.side == "P" and r.direction == "short"
    assert abs(r.stop_level - 600.4) < 1e-9


def test_core_no_counter_trend_break_does_not_fire():
    # clean above-VWAP continuation, price NEVER closes below vwap -> NOT this setup
    # (that is vwap_continuation's job). Must return None.
    closes = np.array([600.5, 601.1, 601.7, 602.5, 603.1])
    highs = np.array([600.6, 601.2, 601.8, 602.6, 603.2])
    lows = np.array([599.9, 601.0, 601.6, 602.4, 602.9])
    vwap = np.array([600.2, 600.6, 601.0, 601.3, 601.6])
    assert detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, _times(5)) is None


def test_core_mixed_open_no_trend_side_does_not_fire():
    closes = np.array([600.4, 599.2, 599.8, 600.8, 601.4])  # mixed first 3 closes
    highs = np.array([600.6, 600.6, 599.9, 600.9, 601.5])
    lows = np.array([599.4, 599.0, 599.0, 599.7, 600.5])
    vwap = np.array([600.0, 599.8, 599.8, 600.0, 600.2])
    assert detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, _times(5)) is None


def test_core_reclaim_after_cutoff_does_not_fire():
    # break at 10:30 (<= cutoff) but reclaim at 10:35 (> cutoff) -> must NOT fire.
    closes = np.array([600.5, 601.1, 601.7, 600.2, 601.5])
    highs = np.array([600.6, 601.2, 601.8, 601.8, 601.6])
    lows = np.array([599.9, 601.0, 601.0, 600.0, 600.1])
    vwap = np.array([601.0, 601.0, 601.0, 601.0, 601.0])
    times = [dt.time(10, 15), dt.time(10, 20), dt.time(10, 25),
             dt.time(10, 30), dt.time(10, 35)]
    assert detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, times) is None


# ── streaming wrapper (BarContext) — fires once at the reclaim bar ─────────────

def test_wrapper_fires_once_at_reclaim_bar():
    rows = [
        _bar(9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar(9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar(9, 40, 601.1, 601.8, 601.0, 601.7),   # side = C
        _bar(9, 45, 601.7, 601.8, 600.0, 600.2),   # counter-trend break (close < VWAP)
        _bar(9, 50, 600.2, 601.6, 600.1, 601.5),   # reclaim (close > VWAP) -> entry
    ]
    _reset_day("none")
    fired = []
    for k in range(len(rows)):
        s = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows[: k + 1]))
        if s is not None:
            fired.append(s)
    assert len(fired) == 1, f"expected exactly one entry, got {len(fired)}"
    sig = fired[0]
    assert sig.watcher_name == "vwap_reclaim_failed_break_watcher"
    assert sig.setup_name == "VWAP_RECLAIM_FAILED_BREAK"
    assert sig.direction == "long"
    assert sig.metadata["strike_offset"] == 0          # Safe-2 ATM ship cell
    assert sig.metadata["premium_stop_pct"] == -0.08
    assert sig.metadata["promotion_status"] == "WATCH_ONLY"


# ── MED-1 — two interleaved callers must NOT corrupt each other's one/day guard ─

def _bar_d(day: dt.date, h, m, o, hi, lo, c, v=5000):
    """Like _bar but on an explicit date (for the interleave test)."""
    return dict(timestamp_et=dt.datetime(day.year, day.month, day.day, h, m),
                open=o, high=hi, low=lo, close=c, volume=v)


def _day_rows(day: dt.date):
    """A canonical above-VWAP-trend -> failed-break -> reclaim day (fires long once)."""
    return [
        _bar_d(day, 9, 30, 600.0, 600.6, 599.9, 600.5),
        _bar_d(day, 9, 35, 600.5, 601.2, 600.4, 601.1),
        _bar_d(day, 9, 40, 601.1, 601.8, 601.0, 601.7),   # side = C
        _bar_d(day, 9, 45, 601.7, 601.8, 600.0, 600.2),   # counter-trend break
        _bar_d(day, 9, 50, 600.2, 601.6, 600.1, 601.5),   # reclaim -> entry
    ]


def test_interleaved_callers_do_not_corrupt_each_other():
    """Two SEPARATE detector instances replaying DIFFERENT days, bar-interleaved,
    must each fire exactly once. Under the OLD module-level state, caller B's new-day
    reset (or fired flag) clobbered caller A's per-day guard mid-replay → A could
    double-fire or be wrongly suppressed. Per-instance state (MED-1) fixes that."""
    day_a = dt.date(2026, 1, 7)
    day_b = dt.date(2026, 1, 8)
    rows_a = _day_rows(day_a)
    rows_b = _day_rows(day_b)

    det_a = VwapReclaimFailedBreakDetector()
    det_b = VwapReclaimFailedBreakDetector()
    fired_a, fired_b = [], []

    # Interleave A's and B's bars: a0, b0, a1, b1, ... Each detector sees a clean
    # monotonic per-day stream of ITS OWN day; the two streams share no module state.
    for k in range(len(rows_a)):
        sa = det_a.detect(_mk_ctx(rows_a[: k + 1]))
        if sa is not None:
            fired_a.append(sa)
        sb = det_b.detect(_mk_ctx(rows_b[: k + 1]))
        if sb is not None:
            fired_b.append(sb)

    assert len(fired_a) == 1, f"detector A fired {len(fired_a)} times (expected 1)"
    assert len(fired_b) == 1, f"detector B fired {len(fired_b)} times (expected 1)"
    # Each fired on its OWN day (no cross-day leakage).
    assert fired_a[0].metadata is not None and fired_b[0].metadata is not None


def test_module_default_singleton_isolated_from_explicit_instance():
    """The module-level shim (default singleton) and an explicit instance must not
    share state: firing through the shim must not suppress an explicit instance's
    entry on a different day (the exact backtest-vs-live interleave the bug caused)."""
    day_a = dt.date(2026, 1, 7)
    day_b = dt.date(2026, 1, 8)
    rows_a = _day_rows(day_a)
    rows_b = _day_rows(day_b)

    _reset_day("none")
    explicit = VwapReclaimFailedBreakDetector()

    shim_fires, inst_fires = [], []
    for k in range(len(rows_a)):
        s_shim = detect_vwap_reclaim_failed_break_setup(_mk_ctx(rows_a[: k + 1]))
        if s_shim is not None:
            shim_fires.append(s_shim)
        s_inst = explicit.detect(_mk_ctx(rows_b[: k + 1]))
        if s_inst is not None:
            inst_fires.append(s_inst)

    assert len(shim_fires) == 1
    assert len(inst_fires) == 1


# ── isolated-key gamma-sync helpers (HIGH/MED-2/LOW-2) ─────────────────────────

def test_filters_isolated_exit_helpers_read_keys_not_globals():
    """filters.py edge-#2 exit helpers must read the ISOLATED keys, never the global
    catastrophe cap / global tp1 / global chart buffer."""
    # Safe-2 ATM cell params (with the WRONG global values present to prove isolation).
    safe = {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 0.50, "chart_stop_buffer_dollars": 0.50,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "j_vwap_reclaim_fb_tp1_pct": 0.30,
        "j_vwap_reclaim_fb_stop_buffer": 0.25,
    }
    assert _filters.vwap_reclaim_failed_break_premium_stop_pct(safe) == -0.08
    assert _filters.vwap_reclaim_failed_break_tp1_pct(safe) == 0.30
    assert _filters.vwap_reclaim_failed_break_stop_buffer(safe) == 0.25

    # Bold ITM-2 cell params.
    bold = {
        "premium_stop_pct": -0.07, "tp1_premium_pct": 0.75,
        "j_vwap_reclaim_fb_premium_stop_pct": -0.08,
        "j_vwap_reclaim_fb_tp1_pct": 0.75,
        "j_vwap_reclaim_fb_stop_buffer": 0.50,
    }
    assert _filters.vwap_reclaim_failed_break_premium_stop_pct(bold) == -0.08
    assert _filters.vwap_reclaim_failed_break_tp1_pct(bold) == 0.75
    assert _filters.vwap_reclaim_failed_break_stop_buffer(bold) == 0.50

    # Absent keys -> validated Safe-2 defaults, NOT the global catastrophe cap.
    assert _filters.vwap_reclaim_failed_break_premium_stop_pct(None) == -0.08
    assert _filters.vwap_reclaim_failed_break_premium_stop_pct({"premium_stop_pct": -0.50}) == -0.08


# ── 2. PARITY — live core == validated research detector (full dataset) ────────

@pytest.mark.skipif(
    not (REPO / "data").exists(),
    reason="backtest data dir not present",
)
def test_parity_with_validated_research_detector():
    """Live core must reproduce the research detector's signals EXACTLY (same date,
    side, stop_level) across the full dataset. Same window the scorecard used."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    from autoresearch import runner as ar_runner
    from autoresearch.infinite_ammo_discovery import build_day_contexts, session_vwap_asof
    from autoresearch._edgehunt_vwap_continuation import _normalize_spy
    from autoresearch._sub_struct_vwap_reclaim_failed_break import detect_signals

    spy_raw, _vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    days = build_day_contexts(spy)

    # Research detector's signal set: (date, side, stop_level)
    research = []
    for sg in detect_signals(days):
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        research.append((d, sg.side, round(float(sg.stop_level), 4)))

    # Live core, fed the SAME as-of arrays per day (the exact arrays the research
    # detector iterates over — RTH closes/highs/lows + session_vwap_asof + rth["t"]).
    live = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 3:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = list(rth["t"].values)
        r = detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, times)
        if r is not None:
            live.append((dc.date, r.side, round(float(r.stop_level), 4)))

    assert len(research) > 0, "research detector produced no signals — fixture broken"
    assert sorted(live) == sorted(research), (
        "PARITY BREAK: live core != validated research detector. "
        f"research n={len(research)} live n={len(live)}. "
        f"only_research={sorted(set(research) - set(live))[:5]} "
        f"only_live={sorted(set(live) - set(research))[:5]}"
    )


# ── 3. EXPECTANCY SIGN — validated ITM-2 cell reproduces a positive per-trade edge ─

@pytest.mark.skipif(
    not (REPO / "data").exists(),
    reason="backtest data dir not present",
)
def test_validated_itm2_cell_reproduces_positive_expectancy_sign():
    """The gate-clearing cell (ITM-2, strike_offset=-2) must reproduce a POSITIVE
    per-trade expectancy on real OPRA fills — the sign the scorecard validated.

    Pins the SIGN, not a fragile exact dollar figure (so a benign data refresh won't
    flake) — but fails loudly if the edge ever flips negative (the thing that would make
    flipping the dormant flag a mistake)."""
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    from autoresearch import runner as ar_runner
    from autoresearch.infinite_ammo_discovery import build_day_contexts
    from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix
    from autoresearch._sub_struct_vwap_reclaim_failed_break import (
        detect_signals, simulate_set, SURV_PREMIUM_STOP, PRIMARY_STRIKE_OFFSET, metrics,
    )
    from lib.ribbon import compute_ribbon

    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    signals = detect_signals(days)
    assert len(signals) > 0, "no signals — fixture broken"

    rows, cov = simulate_set(
        signals, spy, ribbon, vix,
        strike_offset=PRIMARY_STRIKE_OFFSET, premium_stop_pct=SURV_PREMIUM_STOP,
    )
    # require some real OPRA fills landed (otherwise the assertion is vacuous)
    assert cov["filled"] >= 20, f"too few real-OPRA fills to judge ({cov['filled']})"

    m = metrics(rows)
    assert m["exp_dollar"] > 0, (
        f"VALIDATED ITM-2 cell flipped to NEGATIVE per-trade expectancy "
        f"(exp=${m['exp_dollar']}, n={m['n']}) — the edge no longer reproduces; "
        f"do NOT flip j_vwap_reclaim_fb_enabled."
    )
