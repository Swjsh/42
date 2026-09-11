"""Guards for dynamic_stop_ab.py — prove the dynamic stop is CAUSAL, BINDS differently
than static, and is not a re-optimization. Fast unit tests (no OPRA load)."""
from __future__ import annotations

import sys
from pathlib import Path

_BT = Path(__file__).resolve().parents[1]
_REPO = _BT.parent
for p in (str(_BT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from autoresearch import dynamic_stop_ab as D  # noqa: E402


class _Sig:
    def __init__(self, side="P", stop_level=591.0, bar_idx=10):
        self.side = side
        self.stop_level = stop_level
        self.bar_idx = bar_idx
        self.note = "t"


def test_static_ignores_features():
    r = D.make_static(-0.06)
    # static must return the SAME pct regardless of atr/vix/structure
    a = r(_Sig(), 1.35, 0.5, 15.0, 17.0, 587.0, 0.5)
    b = r(_Sig(), 2.10, 3.0, 40.0, 17.0, 610.0, 0.65)
    assert a == b == -0.06


def test_atr_scaled_widens_with_atr():
    r = D.make_atr(1.5)
    lo_vol = r(_Sig(), 1.35, 0.5, 17.0, 17.0, 587.0, 0.65)   # small ATR
    hi_vol = r(_Sig(), 1.35, 2.0, 17.0, 17.0, 587.0, 0.65)   # big ATR
    assert lo_vol is not None and hi_vol is not None
    # a bigger ATR must produce a WIDER (more negative) stop pct
    assert hi_vol < lo_vol, (lo_vol, hi_vol)


def test_iv_scaled_widens_with_vix():
    r = D.make_iv(-0.06)
    calm = r(_Sig(), 1.35, 0.8, 14.0, 17.0, 587.0, 0.5)
    panic = r(_Sig(), 1.35, 0.8, 34.0, 17.0, 587.0, 0.5)
    assert panic < calm, (calm, panic)   # high VIX => wider stop
    # sanity: at VIX == median the scaler equals base
    at_med = r(_Sig(), 1.35, 0.8, 17.0, 17.0, 587.0, 0.5)
    assert abs(at_med - (-0.06)) < 1e-9


def test_structure_stop_scales_with_distance():
    r = D.make_structure(0.50)
    near = r(_Sig(stop_level=588.0), 1.35, 0.8, 17.0, 17.0, 587.0, 0.65)  # 1pt away
    far = r(_Sig(stop_level=592.0), 1.35, 0.8, 17.0, 17.0, 587.0, 0.65)   # 5pt away
    assert far < near, (near, far)   # farther chart level => wider premium stop


def test_clamp_bounds():
    # a tiny entry premium with a big distance must clamp, not invent a -900% stop
    r = D.make_atr(2.0)
    pct = r(_Sig(), 0.05, 3.0, 17.0, 17.0, 587.0, 0.65)
    assert D.STOP_CLAMP[0] <= pct <= D.STOP_CLAMP[1]
    assert pct == D.STOP_CLAMP[0]   # hits the -0.99 floor


def test_bh_fdr_planted():
    # 4 clearly-significant (p=.001) + 6 null (p=.8). BH q=0.10 must keep the 4, drop the 6.
    pvals = [0.001, 0.001, 0.001, 0.001, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]
    rej = D.bh_fdr(pvals, q=0.10)
    assert rej[:4] == [True, True, True, True]
    assert not any(rej[4:])


def test_bh_fdr_all_null():
    # all p=0.5 -> nothing survives (guards against a bug that always accepts)
    assert not any(D.bh_fdr([0.5] * 8, q=0.10))


def test_atr_causal_only_looks_back():
    # atr_at must only read bars <= i (no look-ahead). Build a frame where a HUGE
    # range appears AFTER i; the ATR at i must be unaffected by it.
    import pandas as pd
    n = 40
    df = pd.DataFrame({
        "high": [100.5] * n, "low": [99.5] * n, "close": [100.0] * n,
    })
    df.loc[30, ["high", "low"]] = [200.0, 50.0]   # giant bar AFTER i=20
    atr20 = D.atr_at(df, 20)
    # with only ~1pt ranges up to bar 20, ATR must be ~1.0, NOT blown out by bar 30
    assert atr20 < 2.0, atr20
