"""Guard: setup/scripts/context_bundle_producer.py -- the TREND-ALIGNMENT math (Phase 0,
context-enrichment plan, 2026-07-14).

WHAT THIS PINS:
  1. `compute_trend_alignment` is the single source of truth Phase 1's correlation scorer
     will import -- it must return the RIGHT alignment_score sign+magnitude on aligned-up /
     aligned-down / mixed fixtures (using the SAME sawtooth-fixture technique
     test_structure_veto_classifier_live.py already validated: a monotonic series has NO
     interior swings and classifies 'unknown', so a real up/down read needs a sawtooth).
  2. A missing/insufficient timeframe degrades to `available: False` + contributes 0 to the
     score -- it never crashes, never fabricates a trend, never manufactures false alignment.
  3. `compute_trend_alignment` does NO I/O -- it is pure over the DataFrames it's handed, so
     Phase 1's walk-forward replay can call it directly on historical bars without touching
     disk/network (proven here by making file-open and network calls raise on the codepath).

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_context_bundle_producer.py -q
"""
from __future__ import annotations

import builtins
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(_SCRIPTS), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import context_bundle_producer as cbp  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixture: the SAME minimal-swing-producing sawtooth technique
# test_structure_veto_classifier_live.py::_sawtooth_bars uses -- a pure monotonic
# line has no interior swing points (classify_trend => 'unknown'), so a real
# up/down structure read needs genuine higher-highs/higher-lows (or mirror) swings.
# --------------------------------------------------------------------------- #
def _sawtooth_df(n: int, slope: float, base: float, *, step: timedelta) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        c = round(base + slope * i + 2.5 * math.sin(i * math.pi / 3), 2)
        rows.append({"timestamp": start + step * i, "open": c, "high": c + 0.6,
                     "low": c - 0.6, "close": c, "volume": 1000.0})
    return pd.DataFrame(rows)


def _up_df(n: int = 40, step: timedelta = timedelta(hours=1)) -> pd.DataFrame:
    return _sawtooth_df(n, slope=+0.35, base=100.0, step=step)


def _down_df(n: int = 40, step: timedelta = timedelta(hours=1)) -> pd.DataFrame:
    return _sawtooth_df(n, slope=-0.35, base=300.0, step=step)


# --------------------------------------------------------------------------- #
# 1. Aligned-up / aligned-down / mixed -- correct sign + magnitude
# --------------------------------------------------------------------------- #
def test_all_timeframes_aligned_up_scores_plus_three():
    up = _up_df()
    result = cbp.compute_trend_alignment(up, up, up)
    assert result["per_tf"]["daily"]["trend"] == "uptrend"
    assert result["per_tf"]["hourly"]["trend"] == "uptrend"
    assert result["per_tf"]["m15"]["trend"] == "uptrend"
    assert result["alignment_score"] == 3
    assert result["trend_alignment"]["bull"]["aligned"] is True
    assert result["trend_alignment"]["bull"]["agree_count"] == 3
    assert result["trend_alignment"]["bear"]["aligned"] is False
    assert result["trend_alignment"]["bear"]["agree_count"] == 0
    assert result["degraded"] is False


def test_all_timeframes_aligned_down_scores_minus_three():
    down = _down_df()
    result = cbp.compute_trend_alignment(down, down, down)
    assert result["per_tf"]["daily"]["trend"] == "downtrend"
    assert result["alignment_score"] == -3
    assert result["trend_alignment"]["bear"]["aligned"] is True
    assert result["trend_alignment"]["bear"]["agree_count"] == 3
    assert result["trend_alignment"]["bull"]["aligned"] is False
    assert result["degraded"] is False


def test_mixed_timeframes_score_is_the_net_not_the_max():
    """daily=up, hourly=down, m15=up -> net vote = +1 - 1 + 1 = +1 (NOT +3, NOT 'aligned' on
    either side -- the sign says 'weak bullish lean', the magnitude says 'not stacked')."""
    up, down = _up_df(), _down_df()
    result = cbp.compute_trend_alignment(up, down, up)
    assert result["per_tf"]["daily"]["trend"] == "uptrend"
    assert result["per_tf"]["hourly"]["trend"] == "downtrend"
    assert result["per_tf"]["m15"]["trend"] == "uptrend"
    assert result["alignment_score"] == 1
    assert result["trend_alignment"]["bull"]["aligned"] is False, (
        "2-of-3 must NOT read as full alignment")
    assert result["trend_alignment"]["bull"]["agree_count"] == 2
    assert result["trend_alignment"]["bear"]["agree_count"] == 1


def test_full_disagreement_nets_to_zero():
    """daily=up, hourly=down, m15=range(no swings) -> +1 - 1 + 0 = 0, no net lean either way."""
    up, down = _up_df(), _down_df()
    flat = pd.DataFrame([{"timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                          "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 1000.0}
                         for i in range(40)])
    result = cbp.compute_trend_alignment(up, down, flat)
    assert result["alignment_score"] == 0
    assert result["trend_alignment"]["bull"]["aligned"] is False
    assert result["trend_alignment"]["bear"]["aligned"] is False


# --------------------------------------------------------------------------- #
# 2. Degraded path -- a missing/insufficient timeframe never crashes, never
#    fabricates a trend, and is excluded from the agree/disagree count.
# --------------------------------------------------------------------------- #
def test_missing_timeframe_degrades_available_false_and_contributes_zero():
    up = _up_df()
    result = cbp.compute_trend_alignment(up, None, up)
    assert result["per_tf"]["hourly"]["available"] is False
    assert result["per_tf"]["hourly"]["trend"] == "unknown"
    assert result["per_tf"]["hourly"]["reason"] == "insufficient_bars"
    assert result["degraded"] is True
    assert "hourly: insufficient_bars" in result["degraded_reasons"]
    # excluded from BOTH counts, but the two REAL timeframes still fully agree bullish
    assert result["trend_alignment"]["bull"]["available_count"] == 2
    assert result["trend_alignment"]["bull"]["aligned"] is True
    assert result["alignment_score"] == 2  # 2 up votes, missing TF contributes 0 (not -1/+1)


def test_empty_dataframe_and_too_short_dataframe_both_degrade_gracefully():
    up = _up_df()
    empty = pd.DataFrame()
    too_short = _up_df(n=3)  # below MIN_BARS
    result_empty = cbp.compute_trend_alignment(up, empty, up)
    assert result_empty["per_tf"]["hourly"]["available"] is False
    result_short = cbp.compute_trend_alignment(up, too_short, up)
    assert result_short["per_tf"]["hourly"]["available"] is False
    assert result_short["per_tf"]["hourly"]["n_bars"] == 3


def test_all_timeframes_missing_never_raises_and_scores_zero():
    result = cbp.compute_trend_alignment(None, None, None)
    assert result["alignment_score"] == 0
    assert result["degraded"] is True
    assert result["trend_alignment"]["bull"]["aligned"] is False
    assert result["trend_alignment"]["bear"]["aligned"] is False
    for tf in ("daily", "hourly", "m15"):
        assert result["per_tf"][tf]["available"] is False


def test_malformed_rows_are_skipped_not_fatal():
    """NaN OHLC / bad timestamps in a few rows must be dropped, not crash the whole read."""
    df = _up_df(n=40)
    df = df.copy()
    df.loc[5, "close"] = float("nan")
    df.loc[10, "high"] = float("nan")
    result = cbp.compute_trend_alignment(df, df, df)
    assert result["per_tf"]["daily"]["n_bars"] == 38  # 2 rows dropped
    assert result["per_tf"]["daily"]["trend"] in ("uptrend", "range", "unknown")  # never raises


# --------------------------------------------------------------------------- #
# 2b. AS-OF-BOUNDED / NO-LOOK-AHEAD -- load-bearing for Phase 1 (2026-07-14
#    amendment): compute_trend_alignment must be a pure function of the ROWS its
#    DataFrames actually contain, never of anything beyond what the caller hands it.
# --------------------------------------------------------------------------- #
def test_compute_trend_alignment_is_as_of_bounded_no_lookahead():
    """Reconstructing alignment at a past decision timestamp T from bars[:T] must match a
    series that never had ANY bars past T at all -- this is exactly Phase 1's workflow
    (fetch daily/hourly/15m history once, slice to <=T per historical decision timestamp,
    call this SAME function -- never re-derive the math, never look past T). Two halves:

    1. RECONSTRUCTION IS STABLE: a <=T slice of a LONGER series (one that genuinely has
       bars after T) must produce the byte-identical result to an independently-built
       series that stops at T and never had any future rows -- the function must not be
       able to see beyond the DataFrame it was actually given.
    2. TRUNCATION IS NECESSARY: the SAME long series, sliced to <=T vs left un-truncated
       (bars past T included), must give a DIFFERENT read -- proving the function genuinely
       uses whatever it's handed rather than silently self-truncating. The no-look-ahead
       guarantee lives in the CALLER's slicing discipline (which Phase 1 must honor), not
       in any hidden magic inside this function.
    """
    long_series = _up_df(n=80, step=timedelta(hours=1))  # extends well past the cutoff below
    T = long_series.iloc[49]["timestamp"]

    sliced_from_long = long_series[long_series["timestamp"] <= T].reset_index(drop=True)
    cutoff_only = _up_df(n=50, step=timedelta(hours=1))  # independently built, zero future rows
    assert list(sliced_from_long["close"]) == list(cutoff_only["close"]), (
        "fixture sanity: both series must contain the identical rows up to T")

    result_from_long_sliced = cbp.compute_trend_alignment(sliced_from_long, sliced_from_long, sliced_from_long)
    result_cutoff_only = cbp.compute_trend_alignment(cutoff_only, cutoff_only, cutoff_only)
    assert result_from_long_sliced == result_cutoff_only, (
        "a <=T slice of a longer series must match a series that never had future bars at "
        "all -- the function must not see beyond T")

    result_full_unsliced = cbp.compute_trend_alignment(long_series, long_series, long_series)
    assert (result_full_unsliced["per_tf"]["daily"]["n_bars"]
            != result_from_long_sliced["per_tf"]["daily"]["n_bars"]), (
        "the un-truncated series must be read as MORE bars than the <=T slice -- if this "
        "doesn't hold, the fixture isn't actually exercising truncation")


def test_compute_trend_alignment_reconstruction_matches_at_multiple_cutoffs():
    """Same property as above, swept across several cutoffs -- the reconstruction must hold
    everywhere, not just at one lucky index."""
    long_series = _up_df(n=80, step=timedelta(hours=1))
    for cutoff_idx in (20, 35, 49, 65):
        T = long_series.iloc[cutoff_idx]["timestamp"]
        sliced = long_series[long_series["timestamp"] <= T].reset_index(drop=True)
        independent = _up_df(n=cutoff_idx + 1, step=timedelta(hours=1))
        assert cbp.compute_trend_alignment(sliced, sliced, sliced) == cbp.compute_trend_alignment(
            independent, independent, independent), f"reconstruction mismatch at cutoff_idx={cutoff_idx}"


# --------------------------------------------------------------------------- #
# 3. PURITY -- compute_trend_alignment does NO I/O. Phase 1's replay scorer must
#    be able to call it directly on historical DataFrames with zero side effects.
# --------------------------------------------------------------------------- #
def test_compute_trend_alignment_does_no_file_io(monkeypatch):
    def _forbidden_open(*a, **k):
        raise AssertionError("compute_trend_alignment must not open any file")
    monkeypatch.setattr(builtins, "open", _forbidden_open)
    up = _up_df()
    # must complete without ever touching the (now-forbidden) builtins.open
    result = cbp.compute_trend_alignment(up, up, up)
    assert result["alignment_score"] == 3


def test_compute_trend_alignment_does_no_network_io(monkeypatch):
    import urllib.request

    def _forbidden_urlopen(*a, **k):
        raise AssertionError("compute_trend_alignment must not make a network request")
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden_urlopen)
    up, down = _up_df(), _down_df()
    result = cbp.compute_trend_alignment(up, down, up)
    assert result["alignment_score"] == 1


# --------------------------------------------------------------------------- #
# 4. _df_to_bars -- the pure DataFrame -> Bar conversion helper
# --------------------------------------------------------------------------- #
def test_df_to_bars_sorts_oldest_first_and_is_tz_aware():
    df = _up_df(n=15)
    bars = cbp._df_to_bars(df, 3600, "test")
    assert len(bars) == 15
    assert all(b.open_time.tzinfo is not None for b in bars)
    assert bars == sorted(bars, key=lambda b: b.open_time)


def test_df_to_bars_empty_and_none_return_empty_list():
    assert cbp._df_to_bars(None, 3600, "test") == []
    assert cbp._df_to_bars(pd.DataFrame(), 3600, "test") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
