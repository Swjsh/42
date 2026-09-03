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


# =============================================================================
# EXTENSION (2026-07-15): events / prior_day / today_context / levels_context
# =============================================================================

# ----- fixture helpers -------------------------------------------------------
def _et_bars(day: str, times_et: list[str], *, base: float = 700.0, step: float = 0.1,
             volume: float = 1000.0) -> list[dict]:
    """[(HH:MM, ...)] on one ET calendar day -> raw UTC-timestamped OHLCV rows (matches
    _fetch_bars's DataFrame shape: tz-aware UTC `timestamp` column)."""
    rows = []
    for i, hhmm in enumerate(times_et):
        ts_et = pd.Timestamp(f"{day} {hhmm}:00", tz="America/New_York")
        c = round(base + step * i, 2)
        rows.append({"timestamp": ts_et.tz_convert("UTC"), "open": c, "high": c + 0.05,
                     "low": c - 0.05, "close": c, "volume": volume})
    return rows


def _rth_day_bars(day: str, *, base: float = 700.0, n: int = 78, vol: float = 1000.0) -> list[dict]:
    """A full synthetic RTH session (09:30-15:55, 5-min bars) for one ET calendar day."""
    times = []
    h, m = 9, 30
    for _ in range(n):
        times.append(f"{h:02d}:{m:02d}")
        m += 5
        if m >= 60:
            m -= 60
            h += 1
    return _et_bars(day, times, base=base, volume=vol)


def _daily_bars(dates: list[str], closes: list[float]) -> pd.DataFrame:
    rows = []
    for d, c in zip(dates, closes):
        ts = pd.Timestamp(f"{d} 20:00:00", tz="UTC")  # daily bar timestamp -- arbitrary UTC hour
        rows.append({"timestamp": ts, "open": c - 1.0, "high": c + 1.5, "low": c - 1.5,
                     "close": c, "volume": 5_000_000.0})
    return pd.DataFrame(rows)


# ----- compute_prior_day -----------------------------------------------------
def test_compute_prior_day_picks_the_row_strictly_before_today():
    daily = _daily_bars(["2026-07-13", "2026-07-14", "2026-07-15"], [700.0, 705.0, 710.0])
    result = cbp.compute_prior_day(daily, today_et_date="2026-07-15")
    assert result["prior_date"] == "2026-07-14"
    assert result["prior_close"] == 705.0
    assert result["prior_high"] == 706.5
    assert result["prior_low"] == 703.5
    assert result["prior_range"] == 3.0
    assert result["reason"] is None


def test_compute_prior_day_null_with_reason_on_empty_or_no_prior_row():
    empty_result = cbp.compute_prior_day(None, today_et_date="2026-07-15")
    assert empty_result["prior_close"] is None
    assert empty_result["reason"] == "no_daily_data"

    only_today = _daily_bars(["2026-07-15"], [710.0])
    no_prior_result = cbp.compute_prior_day(only_today, today_et_date="2026-07-15")
    assert no_prior_result["prior_close"] is None
    assert no_prior_result["reason"] == "no_prior_trading_day_in_window"


# ----- compute_today_context: gap / position / opening-range -----------------
def test_gap_pct_and_position_in_prior_range_computed_from_rth_bars():
    prior_day = {"prior_close": 700.0, "prior_high": 705.0, "prior_low": 695.0}
    today = pd.DataFrame(_rth_day_bars("2026-07-15", base=702.0))  # today opens +2 vs prior close
    now_et = datetime(2026, 7, 15, 9, 35)  # just after RTH open -- before 10:30 (OR not formed)
    ctx = cbp.compute_today_context(today, prior_day, now_et=now_et)
    assert ctx["today_open"] == pytest.approx(702.0, abs=0.01)
    assert ctx["gap_pct_at_open"] == pytest.approx((702.0 - 700.0) / 700.0 * 100, abs=0.01)
    assert ctx["gap_reason"] is None
    # position = (latest_close - prior_low) / (prior_high - prior_low); latest close is the
    # most recent bar in the `today` df as of 09:35 (a handful of 5-min bars in).
    assert 0.0 <= ctx["position_in_prior_range"] <= 1.5
    assert ctx["or_high"] is None and ctx["or_low"] is None
    assert ctx["or_reason"] == "before_10:30_et_opening_range_not_yet_formed"


def test_opening_range_populates_only_after_1030_and_uses_only_the_0930_1030_window():
    rows = _et_bars("2026-07-15", ["09:30", "09:45", "10:00", "10:15", "10:45", "11:00"],
                     base=700.0, step=0.0)  # flat base, override highs/lows per-row below
    rows[0]["high"], rows[0]["low"] = 701.0, 699.5   # inside OR window
    rows[3]["high"], rows[3]["low"] = 703.0, 698.0   # inside OR window -- the true OR H/L
    rows[4]["high"], rows[4]["low"] = 900.0, 1.0     # OUTSIDE the window (10:45) -- must be excluded
    today = pd.DataFrame(rows)
    now_et = datetime(2026, 7, 15, 10, 31)
    ctx = cbp.compute_today_context(today, {"prior_close": 700.0}, now_et=now_et)
    assert ctx["or_high"] == 703.0, "must ignore the 10:45 bar's 900.0 high (outside the 60-min OR window)"
    assert ctx["or_low"] == 698.0
    assert ctx["or_reason"] is None


def test_today_context_null_with_reason_when_no_rth_bars_yet():
    ctx = cbp.compute_today_context(None, {"prior_close": 700.0}, now_et=datetime(2026, 7, 15, 8, 0))
    assert ctx["today_open"] is None
    assert ctx["gap_reason"] == "no_rth_bars_for_today_yet"
    assert ctx["or_reason"] == "before_10:30_et_opening_range_not_yet_formed"
    assert ctx["rvol_reason"] == "no_intraday_data"


def test_position_in_prior_range_surfaces_stale_prior_session_fallback_explicitly():
    """GAP-REASON-SESSION-OPEN-FALLBACK (queue.md, closed 2026-09-03): confirmed live
    2026-07-20 ~09:34 ET -- a decision row carried spy=743.28 == prior-session-close
    with gap_reason='no_rth_bars_for_today_yet', but position_in_prior_range was
    SILENTLY computed against that same stale carryover price (reason=None). This test
    reproduces the exact shape: `five_min_df`'s newest row is still YESTERDAY's last
    bar (fetch hasn't landed today's first bar yet at 09:34 ET) -- the fallback must
    now be surfaced via position_reason, never a silent default."""
    prior_day = {"prior_close": 700.0, "prior_high": 705.0, "prior_low": 695.0}
    # Only yesterday's bars are present -- today's fetch hasn't landed yet.
    yesterday_only = pd.DataFrame(_rth_day_bars("2026-07-14", base=700.0))
    now_et = datetime(2026, 7, 15, 9, 34)
    ctx = cbp.compute_today_context(yesterday_only, prior_day, now_et=now_et)
    assert ctx["gap_reason"] == "no_rth_bars_for_today_yet"
    assert ctx["position_in_prior_range"] is None, (
        "must NOT silently compute a percentile against yesterday's stale close")
    assert ctx["position_reason"] == "latest_price_is_stale_prior_session_no_today_bars_yet"


def test_position_in_prior_range_still_computed_once_todays_bars_land():
    """Non-vacuous counterpart: once at least one TODAY bar is present, position must
    compute normally with reason=None (the fallback guard must not over-fire)."""
    prior_day = {"prior_close": 700.0, "prior_high": 705.0, "prior_low": 695.0}
    today = pd.DataFrame(_rth_day_bars("2026-07-15", base=702.0))
    now_et = datetime(2026, 7, 15, 9, 35)
    ctx = cbp.compute_today_context(today, prior_day, now_et=now_et)
    assert ctx["position_in_prior_range"] is not None
    assert ctx["position_reason"] is None


# ----- compute_rvol_session_so_far -------------------------------------------
def test_rvol_session_so_far_matches_hand_computed_ratio():
    """3 historical days at a KNOWN cumulative volume through 09:40 ET (2 bars/day: 09:30+09:35,
    100 each = 200 cum), median=200; today has 2 bars through 09:40 at 150 each = 300 cum.
    rvol = 300 / 200 = 1.5."""
    rows = []
    for day in ("2026-07-08", "2026-07-09", "2026-07-10"):
        rows += _et_bars(day, ["09:30", "09:35"], volume=100.0)
    rows += _et_bars("2026-07-13", ["09:30", "09:35"], volume=100.0)  # 4th day, same 200 cum
    rows += _et_bars("2026-07-14", ["09:30", "09:35"], volume=100.0)  # 5th day, same 200 cum
    rows += _et_bars("2026-07-15", ["09:30", "09:35"], volume=150.0)  # TODAY -- 300 cum
    df = pd.DataFrame(rows)
    now_et = datetime(2026, 7, 15, 9, 40)  # just past the 09:35 bar's close
    rvol, reason = cbp.compute_rvol_session_so_far(df, now_et=now_et, min_history_days=5)
    assert reason is None
    assert rvol == pytest.approx(1.5, abs=0.001)


def test_rvol_null_with_reason_below_min_history_days():
    rows = _et_bars("2026-07-14", ["09:30"], volume=100.0) + _et_bars("2026-07-15", ["09:30"], volume=100.0)
    df = pd.DataFrame(rows)
    rvol, reason = cbp.compute_rvol_session_so_far(df, now_et=datetime(2026, 7, 15, 9, 31),
                                                     min_history_days=5)
    assert rvol is None
    assert "insufficient_history" in reason


def test_rvol_only_sums_bars_up_to_the_cutoff_time_causal():
    """A historical day with volume AFTER the cutoff time-of-day must not inflate the median --
    the causal contract: only bars with et_time <= now's time-of-day count on any day."""
    rows = []
    for day in ("2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14"):
        rows += _et_bars(day, ["09:30"], volume=100.0)          # counts (<= cutoff)
        rows += _et_bars(day, ["09:45"], volume=10_000.0)        # must NOT count (> cutoff)
    rows += _et_bars("2026-07-15", ["09:30"], volume=100.0)     # today, matches historical median
    df = pd.DataFrame(rows)
    rvol, reason = cbp.compute_rvol_session_so_far(df, now_et=datetime(2026, 7, 15, 9, 31),
                                                     min_history_days=5)
    assert reason is None
    assert rvol == pytest.approx(1.0, abs=0.001), "the 09:45 10,000-volume bars must be excluded (future of the 09:31 cutoff)"


# ----- compute_events_context -------------------------------------------------
_RULES = {
    "cpi_release": {"block_starts_minutes_before": 5, "block_ends_minutes_after": 30},
    "ppi_release": {"block_starts_minutes_before": 5, "block_ends_minutes_after": 20},
}


def test_events_context_next_and_last_event_with_minutes():
    calendar = {
        "events_30d": [
            {"date": "2026-07-14", "time_et": "08:30", "event": "CPI", "type": "cpi_release", "severity": "high"},
            {"date": "2026-07-15", "time_et": "08:30", "event": "PPI", "type": "ppi_release", "severity": "med"},
        ],
        "no_trade_window_rules": _RULES,
    }
    now_et = datetime(2026, 7, 15, 1, 0)
    ctx = cbp.compute_events_context(calendar, {"freshness_stamp": "2026-07-14T07:45:00"}, now_et=now_et)
    assert ctx["next_event_name"] == "PPI"
    assert ctx["next_event_severity"] == "med"
    assert ctx["minutes_to_next_event"] == pytest.approx(450.0, abs=0.1)
    assert ctx["last_event_name"] == "CPI"
    assert ctx["minutes_since_last_event"] == pytest.approx(990.0, abs=0.1)
    assert ctx["no_trade_window_active"] is False
    assert ctx["todays_windows"] == [{"start_et": "08:25", "end_et": "08:50", "event": "PPI",
                                      "type": "ppi_release", "severity": "med"}]


def test_events_context_no_trade_window_active_true_inside_the_window():
    calendar = {"events_30d": [{"date": "2026-07-15", "time_et": "08:30", "event": "CPI",
                                "type": "cpi_release", "severity": "high"}],
                "no_trade_window_rules": _RULES}
    now_et = datetime(2026, 7, 15, 8, 27)  # inside 08:25-09:00 CPI window
    ctx = cbp.compute_events_context(calendar, {"freshness_stamp": now_et.isoformat()}, now_et=now_et)
    assert ctx["no_trade_window_active"] is True
    assert len(ctx["active_windows"]) == 1
    assert ctx["active_windows"][0]["event"] == "CPI"


def test_events_context_missing_calendar_is_null_with_reason():
    ctx = cbp.compute_events_context(None, None, now_et=datetime(2026, 7, 15, 1, 0))
    assert ctx["next_event_name"] is None
    assert ctx["last_event_name"] is None
    assert ctx["no_trade_window_active"] is False
    assert ctx["calendar_stale"] is True


# ----- _calendar_staleness ----------------------------------------------------
def test_calendar_staleness_fresh_before_todays_fire_uses_yesterdays_fire_as_anchor():
    # Wednesday 01:00 ET -- today's 07:45 fire hasn't happened; anchor = Tuesday 07:45.
    now_et = datetime(2026, 7, 15, 1, 0)  # Wednesday
    fresh_news = {"freshness_stamp": "2026-07-14T07:45:01"}  # Tuesday's fire
    stale, reason = cbp._calendar_staleness(fresh_news, now_et=now_et)
    assert stale is False
    assert reason is None


def test_calendar_staleness_true_when_stamp_predates_expected_fire():
    now_et = datetime(2026, 7, 15, 9, 0)  # Wednesday, well past today's 07:45 fire
    old_news = {"freshness_stamp": "2026-07-13T07:45:01"}  # 2 days stale
    stale, reason = cbp._calendar_staleness(old_news, now_et=now_et)
    assert stale is True
    assert "predates" in reason


def test_calendar_staleness_missing_news_is_always_stale():
    stale, reason = cbp._calendar_staleness(None, now_et=datetime(2026, 7, 15, 1, 0))
    assert stale is True
    assert "missing" in reason


# ----- compute_levels_context -------------------------------------------------
def test_levels_context_nearest_above_below_and_proximity_count():
    key_levels = {"levels": [
        {"price": 748.82, "label": "SUP_A", "source": "level_memory", "expires_at": "2026-07-15T16:00:00-04:00"},
        {"price": 753.09, "label": "RES_A", "source": "level_memory", "expires_at": "2026-07-15T16:00:00-04:00"},
        {"price": 700.00, "label": "FAR_SUP", "source": "reference", "expires_at": "2026-08-01T16:00:00-04:00"},
        {"price": 745.00, "label": "EXPIRED_SUP", "source": "level_memory", "expires_at": "2026-07-10T16:00:00-04:00"},
    ]}
    ctx = cbp.compute_levels_context(key_levels, latest_price=752.05, today_et_date="2026-07-15")
    assert ctx["nearest_level_above"] == {"price": 753.09, "distance": pytest.approx(1.04, abs=0.01), "source": "level_memory"}
    assert ctx["nearest_level_below"] == {"price": 748.82, "distance": pytest.approx(3.23, abs=0.01), "source": "level_memory"}
    assert ctx["n_levels_within_1pct"] == 2  # 748.82 + 753.09 both within 1% of 752.05; 700/745(expired) excluded
    assert ctx["reason"] is None


def test_levels_context_null_with_reason_missing_inputs():
    no_levels = cbp.compute_levels_context(None, latest_price=752.05, today_et_date="2026-07-15")
    assert no_levels["reason"] == "key-levels.json missing/malformed"
    no_price = cbp.compute_levels_context({"levels": []}, latest_price=None, today_et_date="2026-07-15")
    assert no_price["reason"] == "no_current_price_available"


# ----- _latest_close -----------------------------------------------------------
def test_latest_close_picks_the_max_timestamp_across_all_dfs():
    early = pd.DataFrame([{"timestamp": pd.Timestamp("2026-07-14 10:00", tz="UTC"), "close": 100.0}])
    late = pd.DataFrame([{"timestamp": pd.Timestamp("2026-07-15 01:00", tz="UTC"), "close": 200.0}])
    assert cbp._latest_close(early, late) == 200.0
    assert cbp._latest_close(None, late, None) == 200.0
    assert cbp._latest_close(None, None) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
