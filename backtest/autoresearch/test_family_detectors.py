"""TDD for family_detectors — correctness + the look-ahead (causality) guard (C6).

Anti-pattern 2.3 (BACKTESTING-PLAYBOOK): write the detector test FIRST with hand-built
fixtures, before trusting it on real data. The load-bearing test here is CAUSALITY:
truncating the frame after bar T must not change any signal at bar_idx < T (the decision
at bar i uses only bars <= i). A detector that fails this has a future leak (L14/34/57/61).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/autoresearch/test_family_detectors.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from autoresearch import family_detectors as fd  # noqa: E402


# ── fixture builders ─────────────────────────────────────────────────────────
def _frame(closes, date=dt.date(2025, 3, 3), vols=None, wick=0.05, start=dt.time(9, 30)):
    """Build a raw spy-like frame (timestamp_et, ohlcv) from a close path.
    open = prior close (first bar open=close), high/low = body extremes +/- wick."""
    n = len(closes)
    base = dt.datetime.combine(date, start)
    ts = [base + dt.timedelta(minutes=5 * i) for i in range(n)]
    o, h, l, c, v = [], [], [], [], []
    for i, cl in enumerate(closes):
        op = closes[i - 1] if i > 0 else cl
        o.append(op); c.append(cl)
        h.append(max(op, cl) + wick); l.append(min(op, cl) - wick)
        v.append(vols[i] if vols is not None else 50_000)
    return pd.DataFrame({"timestamp_et": pd.to_datetime(ts), "open": o, "high": h,
                         "low": l, "close": c, "volume": v})


def _rth(closes, **kw):
    return fd.build_rth(_frame(closes, **kw))


# ── indicator correctness ────────────────────────────────────────────────────
def test_adx_high_in_trend_low_in_chop():
    trend = list(np.arange(100, 130, 0.5))                 # 60 bars, steady up
    h = np.array([x + 0.05 for x in trend]); l = np.array([x - 0.05 for x in trend])
    c = np.array(trend)
    adx, pdi, mdi = fd.adx_session(h, l, c, 14)
    assert np.nanmax(adx) > 25, "ADX should exceed 25 in a strong trend"
    assert pdi[-1] > mdi[-1], "+DI should dominate in an uptrend"

    chop = [100 + (0.3 if i % 2 else -0.3) for i in range(60)]
    h2 = np.array([x + 0.05 for x in chop]); l2 = np.array([x - 0.05 for x in chop])
    adx2, _, _ = fd.adx_session(h2, l2, np.array(chop), 14)
    assert np.nanmax(adx2) < 25, "ADX should stay below 25 in chop"


def test_adx_always_returns_triple():
    # warmup early-exit branch must still return a 3-tuple (per_session ncols=3 contract)
    out = fd.adx_session(np.arange(5.0), np.arange(5.0), np.arange(5.0), 14)
    assert isinstance(out, tuple) and len(out) == 3


def test_atr_wilder_sane():
    closes = list(np.arange(100, 120, 1.0))                # 20 bars
    r = _rth(closes)
    atr = fd.per_session(r, lambda h, l, c: fd.atr_session(h, l, c, 14))
    assert np.isnan(atr[0])
    assert atr[-1] > 0 and atr[-1] < 5, "ATR should be a small positive on $1 steps"


def test_bollinger_bandwidth_widens_on_expansion():
    tight = [100 + 0.05 * (i % 2) for i in range(25)]      # very tight
    wide = tight + [100, 103, 99, 104, 98]                 # expansion
    r = _rth(wide)
    _, _, _, bw = fd.bollinger_session(r, 20, 2.0)
    assert bw[24] < bw[-1], "bandwidth should widen once range expands"


# ── causality guard (THE critical test) ──────────────────────────────────────
@pytest.mark.parametrize("name", list(fd.FAMILIES))
def test_no_lookahead_truncation_invariance(name):
    """Truncating the frame after bar T must not change any signal at bar_idx < T.
    A future leak in any indicator / squeeze-quantile / coarse-SMA would break this."""
    rng = np.random.RandomState(7)
    # a path with trend, reversal, squeeze and expansion so every detector has a chance
    seg = ([100 + 0.6 * i for i in range(25)]              # up-trend
           + [115 - 0.6 * i for i in range(25)]            # down-trend (reversal)
           + [100 + 0.04 * (i % 2) for i in range(20)]     # squeeze
           + [100, 102.5, 99, 103.5, 98, 104])             # expansion
    closes = [round(x + rng.normal(0, 0.05), 2) for x in seg]
    vols = [50_000 + (40_000 if i >= len(seg) - 6 else 0) for i in range(len(seg))]
    detect = fd.FAMILIES[name]
    full = detect(_rth(closes, vols=vols))
    for T in (45, 60, 75):
        if T >= len(closes):
            continue
        trunc = detect(_rth(closes[:T], vols=vols[:T]))
        full_lt = [(s["bar_idx"], s["side"]) for s in full if s["bar_idx"] < T]
        got = [(s["bar_idx"], s["side"]) for s in trunc if s["bar_idx"] < T]
        assert got == full_lt, (
            f"{name}: signals before bar {T} changed when future bars were truncated "
            f"(LOOK-AHEAD). full={full_lt} trunc={got}")


# ── per-detector: fires on a crafted positive, skips the negative ─────────────
def test_ema_adx_fires_on_trend_skips_chop():
    # steep down (build ADX, EMA9<EMA21) then steep up -> bullish cross while ADX still > 25
    path = [100 - 1.0 * i for i in range(30)] + [70 + 1.2 * i for i in range(25)]
    sigs = fd.detect_ema_adx(_rth(path))
    assert any(s["side"] == "C" for s in sigs), "expected a bullish EMA cross with ADX>25"
    assert all(s["meta"]["adx"] > 25 for s in sigs), "every signal must clear the ADX gate"

    # honest chop = mean-reverting NOISE around 100 (two-sided directional movement ->
    # low ADX). A perfectly periodic sawtooth is NOT chop in DI terms (one-sided DM).
    rng = np.random.RandomState(3)
    chop = [round(100 + rng.uniform(-0.4, 0.4), 2) for _ in range(70)]
    r = _rth(chop)
    adx, _, _ = fd.per_session(r, lambda h, l, c: fd.adx_session(h, l, c, 14), ncols=3)
    assert np.nanmax(adx) < 25, "ADX must stay below the trend floor on no-trend noise"
    assert fd.detect_ema_adx(r) == [], "ADX gate must reject chop (no trend)"


def test_supply_demand_fires_on_impulse_retest():
    # 15 quiet bars (small ATR) -> big green impulse -> pull back into demand zone -> reclaim
    quiet = [100 + 0.1 * (i % 2) for i in range(15)]
    impulse = [102.0]                                       # +~2 body green impulse
    pullback = [101.0, 100.05, 100.6]                       # dip into [open=100.1, low] then reclaim
    sigs = fd.detect_supply_demand_zone(_rth(quiet + impulse + pullback))
    assert any(s["side"] == "C" and s["meta"]["zone_kind"] == "demand" for s in sigs), \
        "expected a demand-zone reclaim long"


def test_bollinger_squeeze_fires_on_expansion_breakout():
    tight = [100 + 0.06 * (i % 2) for i in range(44)]       # long squeeze (low bandwidth)
    breakout = [102.5]                                      # close jumps past upper band
    vols = [50_000] * 44 + [200_000]                        # breakout volume confirm
    sigs = fd.detect_bollinger_squeeze(_rth(tight + breakout, vols=vols))
    assert any(s["side"] == "C" for s in sigs), "expected an up-side squeeze breakout"


def test_three_ducks_runs_without_error():
    # smoke: a long uptrend session; must run + emit only causal, gated signals (>=0)
    path = [100 + 0.2 * i for i in range(60)]
    sigs = fd.detect_three_ducks(_rth(path))
    assert isinstance(sigs, list)
    for s in sigs:
        assert s["side"] in ("C", "P") and s["family"] == "three_ducks"
