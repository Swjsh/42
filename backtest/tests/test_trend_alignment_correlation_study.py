"""Guard: backtest/tools/trend_alignment_correlation_study.py -- Phase 1 build step
(context-enrichment plan, 2026-07-14).

WHAT THIS PINS:
  1. `alignment_for_decision` (this module's ONE slicing boundary) reproduces a manually
     <=T-sliced call to context_bundle_producer.compute_trend_alignment EXACTLY -- the
     no-look-ahead reconstruction property, one level up from Phase 0's own pure-function
     guard (test_context_bundle_producer.py::
     test_compute_trend_alignment_is_as_of_bounded_no_lookahead). This is the property Phase
     1's actual correlation run depends on for every historical decision it scores.
  2. `alignment_for_decision` treats bars strictly AFTER the decision timestamp as invisible --
     appending future rows to the input DataFrame must not change the result for a fixed T.
  3. `compute_trend_alignment` is imported, not reimplemented -- pinned via identity check so a
     future edit can't silently fork the math into two copies.
  4. `alignment_vs_side` correctly flips sign for bear vs bull and reports aligned/fighting from
     the SAME raw alignment bundle (no re-derivation of the vote logic).
  5. The three population loaders (P1/P2/P3) return non-empty, schema-sane lists using ONLY
     already-cached / local files -- no network calls in this test file (P1 reads the committed
     signal-set.json cache, P2 reads the local fills-ledger.jsonl, P3 is a Python literal).

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_trend_alignment_correlation_study.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "setup" / "scripts", ROOT / "backtest", ROOT / "backtest" / "tools", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import context_bundle_producer as cbp                    # noqa: E402
import trend_alignment_correlation_study as tas           # noqa: E402


def _up_df(n: int, *, step) -> pd.DataFrame:
    """Sawtooth-uptrend fixture -- the SAME technique test_context_bundle_producer.py's
    _sawtooth_df uses (a pure monotonic line has no interior swing points and classifies
    'unknown'; a real up/down structure read needs genuine higher-highs/higher-lows swings).
    Slicing-behavior tests below don't need a specific trend, but the sign-convention test
    (test_alignment_vs_side_flips_sign_for_bear) needs a real, non-zero directional read."""
    import math
    import datetime as dt
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    rows = []
    for i in range(n):
        c = round(100.0 + 0.35 * i + 2.5 * math.sin(i * math.pi / 3), 2)
        rows.append({"timestamp": start + step * i, "open": c, "high": c + 0.6,
                      "low": c - 0.6, "close": c, "volume": 1000.0})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------- #
# 1/2. No-look-ahead reconstruction at THIS module's slicing boundary
# ------------------------------------------------------------------------------------------- #
def test_alignment_for_decision_matches_cutoff_only_series():
    import datetime as dt
    long_series = _up_df(80, step=dt.timedelta(hours=1))
    T = long_series.iloc[49]["timestamp"]

    manually_sliced = long_series[long_series["timestamp"] <= T].reset_index(drop=True)
    expected = cbp.compute_trend_alignment(manually_sliced, manually_sliced, manually_sliced)

    actual = tas.alignment_for_decision(long_series, long_series, long_series, T)
    assert actual == expected, (
        "alignment_for_decision must reproduce a manually <=T-sliced compute_trend_alignment "
        "call byte-for-byte -- this is the property Phase 1's historical replay depends on")


def test_alignment_for_decision_ignores_future_rows():
    import datetime as dt
    short_series = _up_df(50, step=dt.timedelta(hours=1))
    T = short_series.iloc[49]["timestamp"]
    long_series = _up_df(80, step=dt.timedelta(hours=1))  # same first 50 rows + 30 MORE (future)

    a_short = tas.alignment_for_decision(short_series, short_series, short_series, T)
    a_long = tas.alignment_for_decision(long_series, long_series, long_series, T)
    assert a_short == a_long, (
        "appending bars AFTER T to the input DataFrame must not change the T-decision's "
        "alignment read -- future rows must be invisible")


def test_alignment_for_decision_accepts_naive_et_timestamp():
    """Every real signal source in this study (ribbon_ride entry_ts, fills-ledger, J_ANCHOR_
    TRADES entry_time_et) records naive ET, not UTC -- the decision_ts normalization must not
    silently misinterpret that as UTC (which would shift every read by 4-5 hours)."""
    import datetime as dt
    series = _up_df(60, step=dt.timedelta(hours=1))
    T_utc = series.iloc[29]["timestamp"]
    # naive ET wall-clock equivalent (winter/summer offset irrelevant to this identity check --
    # we just confirm the naive path produces the SAME bucket as the already-tz-aware UTC path
    # when constructed from the matching UTC instant).
    T_et_naive = T_utc.tz_convert("America/New_York").tz_localize(None)

    a_from_utc = tas.alignment_for_decision(series, series, series, T_utc)
    a_from_naive_et = tas.alignment_for_decision(series, series, series, T_et_naive)
    assert a_from_utc == a_from_naive_et, (
        "a naive timestamp must be interpreted as ET and normalized to the SAME UTC instant, "
        "not misread as already-UTC")


# ------------------------------------------------------------------------------------------- #
# 3. Single source of truth -- no forked math
# ------------------------------------------------------------------------------------------- #
def test_compute_trend_alignment_is_the_same_object():
    assert tas.compute_trend_alignment is cbp.compute_trend_alignment, (
        "trend_alignment_correlation_study must import compute_trend_alignment UNMODIFIED -- "
        "identity check pins against a future silent fork/reimplementation")


# ------------------------------------------------------------------------------------------- #
# 4. alignment_vs_side sign convention
# ------------------------------------------------------------------------------------------- #
def test_alignment_vs_side_flips_sign_for_bear():
    import datetime as dt
    up = _up_df(60, step=dt.timedelta(hours=1))
    T = up.iloc[59]["timestamp"]
    alignment = tas.alignment_for_decision(up, up, up, T)
    assert alignment["alignment_score"] > 0, "fixture sanity: monotonic-up must score positive"

    bull_view = tas.alignment_vs_side(alignment, "bull")
    bear_view = tas.alignment_vs_side(alignment, "bear")
    assert bull_view["signed_score"] == alignment["alignment_score"]
    assert bear_view["signed_score"] == -alignment["alignment_score"]
    assert bull_view["aligned"] is True and bull_view["fighting"] is False
    assert bear_view["aligned"] is False and bear_view["fighting"] is True


def test_alignment_vs_side_rejects_bad_side():
    import datetime as dt
    up = _up_df(60, step=dt.timedelta(hours=1))
    alignment = tas.alignment_for_decision(up, up, up, up.iloc[59]["timestamp"])
    with pytest.raises(ValueError):
        tas.alignment_vs_side(alignment, "up")


def test_side_from_option_char():
    assert tas.side_from_option_char("C") == "bull"
    assert tas.side_from_option_char("P") == "bear"
    assert tas.side_from_option_char("call") == "bull"
    assert tas.side_from_option_char("put") == "bear"
    with pytest.raises(ValueError):
        tas.side_from_option_char("X")


# ------------------------------------------------------------------------------------------- #
# 5. Population loaders -- local/cached files only, no network in this test file
# ------------------------------------------------------------------------------------------- #
def test_load_p1_population_schema():
    sigs = tas.load_p1_population()
    assert len(sigs) > 0
    s = sigs[0]
    for key in ("date", "entry_ts", "side", "entry_spot", "direction"):
        assert key in s
    assert all(s["direction"] in ("bull", "bear") for s in sigs)


def test_load_p2_population_schema():
    positions = tas.load_p2_population()
    assert len(positions) > 0
    p = positions[0]
    for key in ("arm", "symbol", "entry_ts_utc", "actual_exit_pnl"):
        assert key in p


def test_load_p3_population_is_the_op16_anchor_set():
    trades = tas.load_p3_population()
    assert len(trades) == 7
    assert sum(1 for t in trades if t["role"] == "winner") == 3
    assert sum(1 for t in trades if t["role"] == "loser") == 4
    winner_sum = round(sum(t["j_pnl"] for t in trades if t["role"] == "winner"), 2)
    assert winner_sum == 1542.0, "must match CLAUDE.md OP-16 max ($1,542) -- transcription check"
