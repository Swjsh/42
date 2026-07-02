"""Parity guard: bollinger_squeeze_watcher is a BYTE-FOR-BYTE port of the validated
autoresearch.family_detectors.detect_bollinger_squeeze (the grind's 316-signal funnel).

The make-or-break gate for WIRE-BOLLINGER (alpha-plan rank #2, 2026-07-02):
no parity, no wire. Three layers:

  FAST (per-edit):
    - engineered-fire frame: both detectors fire, identical signal dicts (non-vacuous)
    - random-walk frames: identical output (usually empty — shape parity)
    - swing-stop parity: watcher.swing_invalidation == null_baseline._swing_invalidation
    - ctx wrapper: fires ONLY when the last bar is the signal bar

  SLOW (nightly / on demand, needs the master CSV):
    - full-window 2025-01-01..2026-06-18 scan == the original detector, signal-for-signal,
      AND n_signals == 316 (the count recorded in family-grind-bollinger_squeeze.json).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bollinger_squeeze_watcher_parity.py -q
Slow: ... -m slow -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_BACKTEST = Path(__file__).resolve().parent.parent
if str(_BACKTEST) not in sys.path:
    sys.path.insert(0, str(_BACKTEST))

from autoresearch import family_detectors as fd  # noqa: E402
from autoresearch.null_baseline import _swing_invalidation  # noqa: E402
from lib.watchers import bollinger_squeeze_watcher as bw  # noqa: E402
from lib.filters import BarContext  # noqa: E402

MASTER_SPY = _BACKTEST / "data" / "spy_5m_2025-01-01_2026-06-18.csv"
GRIND_WINDOW = (dt.date(2025, 1, 1), dt.date(2026, 6, 18))
GRIND_N_SIGNALS = 316   # family-grind-bollinger_squeeze.json n_signals


# ── fixture builders ──────────────────────────────────────────────────────────
def _frame(closes, vols, date=dt.date(2025, 3, 3), wick=0.05, start=dt.time(9, 30)):
    n = len(closes)
    base = dt.datetime.combine(date, start)
    ts = [base + dt.timedelta(minutes=5 * i) for i in range(n)]
    o, h, l = [], [], []
    for i, cl in enumerate(closes):
        op = closes[i - 1] if i > 0 else cl
        o.append(op)
        h.append(max(op, cl) + wick)
        l.append(min(op, cl) - wick)
    return pd.DataFrame({"timestamp_et": pd.to_datetime(ts), "open": o, "high": h,
                         "low": l, "close": list(closes), "volume": list(vols)})


def _fire_frame():
    """45 flat bars (sd=0 -> bandwidth 0 -> squeeze) then a high-volume up-break."""
    closes = [600.0] * 45 + [601.0, 601.2]
    vols = [50_000] * 45 + [200_000, 60_000]
    return _frame(closes, vols)


def _sig_key(s: dict) -> tuple:
    return (str(s["date"]), s["time"], s["bar_idx"], s["side"],
            s["entry_spot"], s["rejection_level"])


# ── FAST: engineered fire — both detectors, identical, non-vacuous ────────────
def test_engineered_fire_parity_call():
    rth = fd.build_rth(_fire_frame())
    ref = fd.detect_bollinger_squeeze(rth)
    port = bw.detect_bollinger_squeeze_frame(rth)
    assert len(ref) >= 1, "engineered frame must fire (non-vacuous parity)"
    assert [_sig_key(s) for s in port] == [_sig_key(s) for s in ref]
    assert ref[0]["side"] == "C" and ref[0]["bar_idx"] == 45


def test_engineered_fire_parity_put():
    closes = [600.0] * 45 + [599.0, 598.8]
    vols = [50_000] * 45 + [200_000, 60_000]
    rth = fd.build_rth(_frame(closes, vols))
    ref = fd.detect_bollinger_squeeze(rth)
    port = bw.detect_bollinger_squeeze_frame(rth)
    assert len(ref) >= 1 and ref[0]["side"] == "P"
    assert [_sig_key(s) for s in port] == [_sig_key(s) for s in ref]


def test_no_volume_no_fire_parity():
    closes = [600.0] * 45 + [601.0]
    vols = [50_000] * 46                      # no volume expansion -> no fire
    rth = fd.build_rth(_frame(closes, vols))
    assert fd.detect_bollinger_squeeze(rth) == []
    assert bw.detect_bollinger_squeeze_frame(rth) == []


def test_random_walk_parity_multi_session():
    rng = np.random.default_rng(42)
    frames = []
    for d in (dt.date(2025, 4, 7), dt.date(2025, 4, 8)):
        closes = 600 + np.cumsum(rng.normal(0, 0.15, 78))
        vols = rng.integers(30_000, 150_000, 78)
        frames.append(_frame(list(closes), list(vols), date=d))
    rth = fd.build_rth(pd.concat(frames, ignore_index=True))
    ref = fd.detect_bollinger_squeeze(rth)
    port = bw.detect_bollinger_squeeze_frame(rth)
    assert [_sig_key(s) for s in port] == [_sig_key(s) for s in ref]


def test_swing_invalidation_verbatim_parity():
    rng = np.random.default_rng(7)
    closes = 600 + np.cumsum(rng.normal(0, 0.3, 78))
    vols = rng.integers(30_000, 150_000, 78)
    rth = fd.build_rth(_frame(list(closes), list(vols)))
    for idx in (5, 12, 40, 77):
        for side in ("C", "P"):
            assert bw.swing_invalidation(rth, idx, side, 12) == \
                _swing_invalidation(rth, idx, side, 12)


# ── FAST: ctx wrapper fires only on the live signal bar ──────────────────────
def _mk_ctx(df: pd.DataFrame) -> BarContext:
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1,
        timestamp_et=pd.Timestamp(cur["timestamp_et"]).to_pydatetime(),
        bar=cur,
        prior_bars=df,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=17.0,
        vix_prior=17.0,
        vol_baseline_20=50_000.0,
        range_baseline_20=0.5,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
    )


def test_ctx_wrapper_fires_on_signal_bar():
    full = _fire_frame()
    sig_frame = full.iloc[:46].reset_index(drop=True)   # last bar = the break bar (idx 45)
    sig = bw.detect_bollinger_squeeze_setup(_mk_ctx(sig_frame))
    assert sig is not None
    assert sig.direction == "long" and sig.setup_name == "BOLLINGER_SQUEEZE"
    # stop == the frame detector's rejection_level (same swing geometry)
    rth = fd.build_rth(sig_frame)
    ref = fd.detect_bollinger_squeeze(rth)
    assert sig.stop_price == ref[-1]["rejection_level"]
    assert sig.metadata["premium_stop_pct"] == -0.08
    assert sig.metadata["strike_offset"] == 0
    assert sig.metadata["tp1_premium_pct"] == 0.30
    assert sig.metadata["tp1_qty_fraction"] == 0.667
    assert sig.metadata["profit_lock_trail_pct"] == 0.15


def test_ctx_wrapper_silent_on_non_signal_bar():
    full = _fire_frame()
    pre_frame = full.iloc[:45].reset_index(drop=True)   # last bar = still in the squeeze
    assert bw.detect_bollinger_squeeze_setup(_mk_ctx(pre_frame)) is None


def test_ctx_wrapper_never_fires_historical_bar():
    """A frame whose signal bar is NOT the last bar must not fire (stale-frame guard)."""
    full = _fire_frame()                                # signal at idx 45, frame ends 46
    assert bw.detect_bollinger_squeeze_setup(_mk_ctx(full)) is None


# ── SLOW: the make-or-break full-window parity (no parity, no wire) ───────────
@pytest.mark.slow
@pytest.mark.skipif(not MASTER_SPY.exists(), reason="master SPY CSV not on disk")
def test_full_grind_window_parity_316_signals():
    from autoresearch import runner as ar
    spy, _vix = ar.load_data(*GRIND_WINDOW)
    rth = fd.build_rth(spy)
    ref = fd.detect_bollinger_squeeze(rth)
    port = bw.detect_bollinger_squeeze_frame(rth)
    assert len(ref) == GRIND_N_SIGNALS, (
        f"reference detector drifted: {len(ref)} != {GRIND_N_SIGNALS} recorded in "
        "family-grind-bollinger_squeeze.json (data or code changed)")
    assert len(port) == GRIND_N_SIGNALS
    mism = [(a, b) for a, b in zip(ref, port) if _sig_key(a) != _sig_key(b)]
    assert not mism, f"{len(mism)} signal mismatches; first: {mism[:3]}"
