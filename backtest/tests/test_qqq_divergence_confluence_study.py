"""Guards for qqq_divergence_confluence_study.py (chef-inbox 2026-07-11 first-pass study).

C6 no-look-ahead is the load-bearing property here: the QQQ reclaim/failure label at a
signal's entry_ts must be derived ONLY from QQQ bars strictly before entry_ts (the rolling
window) plus the single entry bar itself -- never a bar that closes after the label exists.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from qqq_divergence_confluence_study import (  # noqa: E402
    qqq_label_for_signal,
    spy_forward_return,
    realized_vol_for_signal,
    confound_check_by_volatility,
    LEVEL_WINDOW_BARS,
)


def _bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """rows: (timestamp_et_str, open, high, low, close)."""
    return pd.DataFrame(
        [{"timestamp_et": dt.datetime.fromisoformat(t), "open": o, "high": h,
          "low": lo, "close": c, "volume": 1000} for t, o, h, lo, c in rows]
    )


def _flat_prior(base_ts: dt.datetime, n: int, price: float) -> list[tuple]:
    return [((base_ts - dt.timedelta(minutes=5 * (n - i))).isoformat(), price, price, price, price)
            for i in range(n)]


class TestNoLookAhead:
    def test_reclaim_uses_only_prior_bars_for_the_level(self):
        """A future bar with an extreme high/low must NOT affect the level computed
        as-of entry_ts -- prove by mutating a bar AFTER entry_ts and confirming the
        label is unchanged."""
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, LEVEL_WINDOW_BARS, price=100.0)
        entry_bar = (entry_ts.isoformat(), 100.0, 100.0, 99.5, 100.6)  # closes above prior high
        future_extreme = ((entry_ts + dt.timedelta(minutes=5)).isoformat(), 100.6, 500.0, 0.1, 100.6)
        df = _bars(prior + [entry_bar, future_extreme])
        result = qqq_label_for_signal(df, entry_ts, "bull")
        assert result["label"] == "reclaimed"
        assert result["level"] == pytest.approx(100.0)

        # Now blow up the future bar even further -- label must be byte-identical.
        future_bigger = ((entry_ts + dt.timedelta(minutes=5)).isoformat(), 100.6, 99999.0, -99999.0, 100.6)
        df2 = _bars(prior + [entry_bar, future_bigger])
        result2 = qqq_label_for_signal(df2, entry_ts, "bull")
        assert result2 == result

    def test_bear_reclaim_mirrors_bull(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, LEVEL_WINDOW_BARS, price=100.0)
        entry_bar = (entry_ts.isoformat(), 100.0, 100.2, 99.0, 99.4)  # closes below prior low
        df = _bars(prior + [entry_bar])
        result = qqq_label_for_signal(df, entry_ts, "bear")
        assert result["label"] == "reclaimed"

    def test_failed_when_touch_but_no_close_through(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, LEVEL_WINDOW_BARS, price=100.0)
        entry_bar = (entry_ts.isoformat(), 100.0, 100.3, 99.8, 99.9)  # touches high, closes back under
        df = _bars(prior + [entry_bar])
        result = qqq_label_for_signal(df, entry_ts, "bull")
        assert result["label"] == "failed"

    def test_none_when_neither_touched(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, LEVEL_WINDOW_BARS, price=100.0)
        entry_bar = (entry_ts.isoformat(), 99.9, 99.95, 99.85, 99.9)  # never reaches the 100.0 level
        df = _bars(prior + [entry_bar])
        result = qqq_label_for_signal(df, entry_ts, "bull")
        assert result["label"] == "none"

    def test_insufficient_prior_bars_is_no_data(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, 2, price=100.0)  # far fewer than window//4 floor
        entry_bar = (entry_ts.isoformat(), 100.0, 101.0, 99.0, 100.5)
        df = _bars(prior + [entry_bar])
        result = qqq_label_for_signal(df, entry_ts, "bull")
        assert result["label"] == "no_data"

    def test_no_bars_at_or_after_entry_is_no_data(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, LEVEL_WINDOW_BARS, price=100.0)
        df = _bars(prior)  # nothing at/after entry_ts
        result = qqq_label_for_signal(df, entry_ts, "bull")
        assert result["label"] == "no_data"


class TestForwardReturnProxy:
    def test_aligned_return_positive_when_signal_direction_confirmed(self):
        date_obj = dt.date(2026, 1, 6)
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        rows = [
            (entry_ts.isoformat(), 500.0, 500.0, 500.0, 500.0),
            ((entry_ts + dt.timedelta(minutes=30)).isoformat(), 501.0, 501.5, 500.5, 501.2),
        ]
        df = _bars(rows)
        df["date"] = df["timestamp_et"].dt.date
        by_date = {date_obj: df}
        ret = spy_forward_return(by_date, date_obj, entry_ts, 500.0, "bull")
        assert ret == pytest.approx(1.2)
        ret_bear = spy_forward_return(by_date, date_obj, entry_ts, 500.0, "bear")
        assert ret_bear == pytest.approx(-1.2)

    def test_missing_day_returns_none(self):
        ret = spy_forward_return({}, dt.date(2026, 1, 6), dt.datetime(2026, 1, 6, 14, 45),
                                  500.0, "bull")
        assert ret is None

    def test_empty_window_returns_none(self):
        date_obj = dt.date(2026, 1, 6)
        entry_ts = dt.datetime(2026, 1, 6, 15, 55)  # after all bars in the day
        rows = [(dt.datetime(2026, 1, 6, 9, 30).isoformat(), 500.0, 500.0, 500.0, 500.0)]
        df = _bars(rows)
        df["date"] = df["timestamp_et"].dt.date
        ret = spy_forward_return({date_obj: df}, date_obj, entry_ts, 500.0, "bull")
        assert ret is None


class TestRealizedVolNoLookAhead:
    """realized_vol_for_signal is the confound-control input (disclosure #3 follow-up) --
    it must use the SAME no-look-ahead convention as qqq_label_for_signal: bars strictly
    BEFORE entry_ts only."""

    def test_future_bars_do_not_affect_realized_vol(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, LEVEL_WINDOW_BARS, price=100.0)
        df = _bars(prior)
        vol_before = realized_vol_for_signal(df, entry_ts)
        assert vol_before == pytest.approx(0.0)  # flat prior -> zero realized vol

        # A wild future bar must not change the computed vol at all (it's excluded by the
        # strict '<' filter, same as qqq_label_for_signal's own look-ahead guard).
        future_wild = ((entry_ts + dt.timedelta(minutes=5)).isoformat(), 100.0, 999.0, 1.0, 500.0)
        df2 = _bars(prior + [future_wild])
        vol_after = realized_vol_for_signal(df2, entry_ts)
        assert vol_after == pytest.approx(vol_before)

    def test_nonzero_vol_on_moving_prior(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = [((entry_ts - dt.timedelta(minutes=5 * (LEVEL_WINDOW_BARS - i))).isoformat(),
                  100.0 + i * 0.1, 100.0 + i * 0.1, 100.0 + i * 0.1, 100.0 + i * 0.1)
                 for i in range(LEVEL_WINDOW_BARS)]
        df = _bars(prior)
        vol = realized_vol_for_signal(df, entry_ts)
        assert vol is not None
        assert vol > 0.0

    def test_insufficient_prior_bars_returns_none(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        prior = _flat_prior(entry_ts, 2, price=100.0)  # below the max(5, window//4) floor
        df = _bars(prior)
        assert realized_vol_for_signal(df, entry_ts) is None

    def test_no_prior_bars_returns_none(self):
        entry_ts = dt.datetime(2026, 1, 6, 14, 45)
        df = _bars([((entry_ts + dt.timedelta(minutes=5)).isoformat(), 100.0, 100.0, 100.0, 100.0)])
        assert realized_vol_for_signal(df, entry_ts) is None


class TestConfoundCheckByVolatility:
    """confound_check_by_volatility answers disclosure #3: does the reclaimed-vs-none
    spread survive a realized-volatility control, or does it collapse (meaning the pooled
    result was likely a trend-day/volatility proxy, not QQQ-specific confirmation)?"""

    @staticmethod
    def _row(label: str, ret: float, vol: float) -> dict:
        return {"qqq_label": label, "spy_forward_return_aligned": ret, "realized_vol": vol}

    def test_insufficient_n_below_floor(self):
        rows = [self._row("reclaimed", 1.0, 0.001) for _ in range(5)]
        out = confound_check_by_volatility(rows)
        assert out["status"] == "INSUFFICIENT_N_FOR_VOL_CONTROL"

    def test_spread_survives_in_both_halves(self):
        # 10 low-vol + 10 high-vol rows (distinct vol values per row -- no median tie);
        # reclaimed clearly beats none in BOTH halves.
        rows = []
        for i in range(10):
            rows.append(self._row("reclaimed", 2.0, 0.0010 + i * 0.00001))   # low vol
            rows.append(self._row("none", 0.5, 0.0010 + i * 0.00001))        # low vol
            rows.append(self._row("reclaimed", 2.0, 0.0200 + i * 0.00001))   # high vol
            rows.append(self._row("none", 0.5, 0.0200 + i * 0.00001))        # high vol
        out = confound_check_by_volatility(rows)
        assert out["status"] == "OK"
        assert out["verdict"] == "SPREAD_SURVIVES_VOL_CONTROL"
        assert out["halves"]["low_vol"]["reclaimed_vs_none_spread"] > 0
        assert out["halves"]["high_vol"]["reclaimed_vs_none_spread"] > 0

    def test_spread_collapses_in_one_half(self):
        rows = []
        for i in range(10):
            rows.append(self._row("reclaimed", 2.0, 0.0010 + i * 0.00001))   # low vol: reclaimed beats none
            rows.append(self._row("none", 0.5, 0.0010 + i * 0.00001))
            rows.append(self._row("reclaimed", 0.5, 0.0200 + i * 0.00001))   # high vol: NO advantage (collapses)
            rows.append(self._row("none", 0.6, 0.0200 + i * 0.00001))
        out = confound_check_by_volatility(rows)
        assert out["verdict"] == "SPREAD_COLLAPSES_IN_AT_LEAST_ONE_VOL_HALF"

    def test_rows_missing_realized_vol_are_excluded(self):
        rows = [self._row("reclaimed", 2.0, 0.001) for _ in range(3)]
        rows += [{"qqq_label": "none", "spy_forward_return_aligned": 0.5, "realized_vol": None}
                 for _ in range(3)]
        out = confound_check_by_volatility(rows)
        # only 3 rows carry a real realized_vol -> below the n>=20 floor
        assert out["status"] == "INSUFFICIENT_N_FOR_VOL_CONTROL"
        assert out["n_with_vol"] == 3
