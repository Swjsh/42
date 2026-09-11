"""Guards for confluence_matrix.py — look-ahead safety + lens correctness + anchor.

These lock the load-bearing invariants of the confluence sweep so a future edit
cannot silently reintroduce a leak or mis-grade a lens:

  1. MTF agreement is CAUSAL — a planted-future pivot at a level must NOT be seen
     by _mtf_agreement at an earlier cutoff.
  2. _volume_usable correctly refuses thin IEX volume (OWED-PENDING-SIP guard).
  3. combo_passes is strict AND (every required lens must be true).
  4. _forward_excursion is direction-correct and only looks forward.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import confluence_matrix as cm  # noqa: E402


def _mk_5m_day(prices_hlc: list[tuple[float, float, float]], date="2026-05-04"):
    """Build a one-day 5m frame from (high, low, close) tuples starting 09:30 ET."""
    base = pd.Timestamp(f"{date} 09:30:00")
    rows = []
    for i, (h, l, c) in enumerate(prices_hlc):
        rows.append({"timestamp_et": base + pd.Timedelta(minutes=5 * i),
                     "high": h, "low": l, "close": c, "volume": 1000.0})
    return pd.DataFrame(rows)


class TestMtfCausal:
    def test_planted_future_pivot_invisible_at_earlier_cutoff(self):
        # Level = 700.0. First 6 bars sit far away (720). A pivot AT 700 is planted
        # at bar 10 (the future). At an early cutoff (bar 5), MTF must NOT see it.
        hlc = [(720.5, 720.0, 720.2)] * 6 + [(700.4, 699.8, 700.0)] * 6
        day = _mk_5m_day(hlc)
        early_cut = day["timestamp_et"].iloc[5]
        late_cut = day["timestamp_et"].iloc[11]
        agree_early = cm._mtf_agreement(day, early_cut, level=700.0)
        agree_late = cm._mtf_agreement(day, late_cut, level=700.0)
        assert agree_early == 0, "future pivot at 700 leaked into an earlier cutoff"
        assert agree_late >= 1, "the pivot at 700 should be visible once it has closed"

    def test_resample_causal_never_exceeds_cutoff(self):
        hlc = [(v, v - 0.5, v - 0.2) for v in np.linspace(700, 710, 20)]
        day = _mk_5m_day(hlc)
        cut = day["timestamp_et"].iloc[7]
        agg = cm._resample_causal(day, cut, 15)
        assert agg.index.max() <= cut, "resample bucket extends past the cutoff"


class TestVolumeGuard:
    def test_thin_iex_volume_refused(self):
        spy = pd.DataFrame({"volume": [1.4e4] * 500})
        usable, diag = cm._volume_usable(spy)
        assert usable is False
        assert "OWED-PENDING-SIP" in diag["verdict"]

    def test_full_sip_volume_accepted(self):
        spy = pd.DataFrame({"volume": [1.0e6] * 500})
        usable, diag = cm._volume_usable(spy)
        assert usable is True


class TestComboPasses:
    def _bar(self, lenses):
        return cm.LensBar(bar_idx=0, date=dt.date(2026, 5, 4), side="P",
                          rejection_level=720.0, lenses=lenses, mtf_count=2,
                          lm_mem=100.0, lm_flips=5, fwd_excursion=1.0, note="t")

    def test_strict_and(self):
        b = self._bar({"L_lm_reject": True, "L_day_tl": True, "L_level": False})
        assert cm.combo_passes(b, ("L_lm_reject", "L_day_tl")) is True
        assert cm.combo_passes(b, ("L_lm_reject", "L_level")) is False

    def test_empty_required_passes(self):
        b = self._bar({"L_lm_reject": True})
        assert cm.combo_passes(b, ()) is True


class TestForwardExcursion:
    def test_put_measures_downside(self):
        spy = pd.DataFrame({
            "close": [720.0, 719.0, 715.0, 718.0],
            "high": [720.5, 719.5, 716.0, 719.0],
            "low": [719.5, 718.0, 714.0, 717.0],
        })
        # entry at idx0 close 720; min low ahead = 714 -> excursion 6.0
        exc = cm._forward_excursion(spy, 0, "P", horizon=3)
        assert exc == pytest.approx(6.0, abs=0.01)

    def test_call_measures_upside(self):
        spy = pd.DataFrame({
            "close": [700.0, 701.0, 705.0, 703.0],
            "high": [700.5, 702.0, 706.0, 704.0],
            "low": [699.5, 700.5, 704.0, 702.0],
        })
        exc = cm._forward_excursion(spy, 0, "C", horizon=3)
        assert exc == pytest.approx(6.0, abs=0.01)  # 706 - 700

    def test_only_looks_forward(self):
        # a huge move BEFORE the entry bar must not affect excursion
        spy = pd.DataFrame({
            "close": [750.0, 720.0, 719.0, 718.0],
            "high": [760.0, 720.5, 719.5, 719.0],
            "low": [700.0, 719.0, 718.0, 717.0],
        })
        exc = cm._forward_excursion(spy, 1, "P", horizon=2)  # entry idx1 close 720
        assert exc == pytest.approx(3.0, abs=0.01)  # min(718,717)=717 -> 3.0, not 20
