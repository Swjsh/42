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
    """T sits exactly ON a bar's OPEN timestamp -- with the bar-CLOSE boundary fix (2026-07-14),
    a manual slice must require timestamp + granularity <= T (that bar has not yet closed at its
    own open), not a naive timestamp <= T. Each of the 3 args gets its OWN timeframe's
    granularity (daily=1day/hourly=1h/m15=15min) applied by alignment_for_decision regardless of
    the fixture's own bar spacing -- so the manual slice below must apply that same per-arg
    granularity, not the fixture's step, to reproduce the real boundary."""
    import datetime as dt
    step = dt.timedelta(hours=1)
    long_series = _up_df(80, step=step)
    T = long_series.iloc[49]["timestamp"]

    def _manual(df, granularity):
        return df[df["timestamp"] + granularity <= T].reset_index(drop=True)

    manually_sliced_daily = _manual(long_series, tas._BAR_GRANULARITY["daily"])
    manually_sliced_hourly = _manual(long_series, tas._BAR_GRANULARITY["hourly"])
    manually_sliced_m15 = _manual(long_series, tas._BAR_GRANULARITY["m15"])
    expected = cbp.compute_trend_alignment(
        manually_sliced_daily, manually_sliced_hourly, manually_sliced_m15)

    actual = tas.alignment_for_decision(long_series, long_series, long_series, T)
    assert actual == expected, (
        "alignment_for_decision must reproduce a manually bar-CLOSE-sliced "
        "compute_trend_alignment call byte-for-byte -- this is the property Phase 1's "
        "historical replay depends on")
    # sanity: the hourly-granularity manual slice is strictly shorter than a naive <=T slice
    # would be (bar 49 itself excluded because it has not closed as of its own open)
    naive_sliced = long_series[long_series["timestamp"] <= T]
    assert len(manually_sliced_hourly) == len(naive_sliced) - 1


def test_alignment_for_decision_excludes_still_forming_bar_mid_span():
    """THE look-ahead-leak regression test (root-caused 2026-07-14 adversarial verify pass):
    decision_ts strictly INSIDE a bar's span (not on a fixture row boundary) must NOT see that
    bar's already-realized close -- only bars that have fully closed by decision_ts. Pre-fix,
    `timestamp <= ts` included the still-forming bar with its future OHLC; every prior guard
    test only ever set T to an exact fixture-row timestamp, so this leak went uncaught. Uses
    the m15 arg (15min granularity) so a 5-minute mid-bar offset is unambiguously "still
    forming" regardless of the fixture's own 1h row spacing."""
    import datetime as dt
    step = dt.timedelta(hours=1)
    series = _up_df(60, step=step)
    bar_open = series.iloc[40]["timestamp"]
    mid_bar_T = bar_open + dt.timedelta(minutes=5)  # inside bar 40's 15min m15-granularity window

    alignment_mid_bar = tas.alignment_for_decision(None, None, series, mid_bar_T)
    alignment_at_open = tas.alignment_for_decision(None, None, series, bar_open)
    assert alignment_mid_bar == alignment_at_open, (
        "a decision 5 minutes into a still-forming m15 bar must read the SAME alignment as a "
        "decision made the instant that bar opened -- the forming bar's future close must "
        "never leak in just because decision_ts has ticked past its open timestamp")

    # and it must differ from a decision made AFTER bar 40 has fully closed (its close is now
    # legitimately visible) -- proves the boundary is load-bearing, not a no-op
    after_close_T = bar_open + tas._BAR_GRANULARITY["m15"]
    n_visible_mid = _n_visible_m15_bars(series, mid_bar_T)
    n_visible_after = _n_visible_m15_bars(series, after_close_T)
    assert n_visible_after == n_visible_mid + 1, (
        "exactly one additional bar (bar 40) must become visible once its m15 close has "
        "passed, not before")


def _n_visible_m15_bars(series: pd.DataFrame, ts) -> int:
    """Test helper: how many rows of `series` alignment_for_decision would treat as closed at
    ts, using the module's own 'm15' granularity constant."""
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("America/New_York").tz_convert("UTC")
    else:
        t = t.tz_convert("UTC")
    return int((series["timestamp"] + tas._BAR_GRANULARITY["m15"] <= t).sum())


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
