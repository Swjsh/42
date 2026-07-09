"""Tests for backtest/tools/pattern_prescreen.py — the C27 pre-screen tool.

Covers the 4th required guard category ("prescreen counts on a synthetic fixture with
known fire counts") plus the tool's other pure building blocks (verdict thresholds,
resampling, master-CSV picking) on tiny in-memory fixtures — none of these touch the
real master CSV or disk I/O other than a throwaway tmp_path.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_pattern_prescreen.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))

from crypto.lib.bar import Bar  # noqa: E402
from lib.patterns import PatternContext, PatternRule, evaluate_rule_over_range  # noqa: E402
from lib.patterns.predicates import volume_expansion  # noqa: E402

import tools.pattern_prescreen as prescreen  # noqa: E402


def _mk_bar(day: dt.date, minute_offset: int, o, h, l, c, v=1000.0) -> Bar:
    t0 = dt.datetime.combine(day, dt.time(9, 30), tzinfo=dt.timezone.utc)
    return Bar(open_time=t0 + dt.timedelta(minutes=5 * minute_offset),
               open=o, high=h, low=l, close=c, volume=v, granularity_seconds=300, source="test")


def _trading_days(n: int, base: dt.date = dt.date(2025, 1, 6)) -> list[dt.date]:
    out: list[dt.date] = []
    d = 0
    while len(out) < n:
        day = base + dt.timedelta(days=d)
        d += 1
        if day.weekday() < 5:
            out.append(day)
    return out


# ── 1. prescreen counts on a synthetic fixture with KNOWN fire counts ──────────

class TestSyntheticFireCounts:
    def _known_volume_spike_rule(self, mult: float = 2.0, lookback: int = 5) -> PatternRule:
        return PatternRule(
            name="_test_volume_spike", tier=1, timeframes=("5m",), direction="bullish",
            predicate=volume_expansion(lookback=lookback, mult=mult),
            citation="test-only", thresholds={"mult": mult, "lookback": lookback},
            description="test-only",
        )

    def test_known_fire_count_on_engineered_spikes(self):
        """3 trading days x 20 bars/day (60 bars). EXACTLY 2 bars per day are engineered
        to have volume >= 2x the trailing-5-bar average (all other volumes constant at
        1000, so the trailing average is always exactly 1000 once warmed up) -- so the
        rule must fire EXACTLY 6 times total (2/day x 3 days), 2 distinct days... no,
        EVERY day has a fire, so days_with_fire == 3."""
        bars: list[Bar] = []
        spike_offsets = {7, 14}   # 2 spike bars per day, well past the 5-bar warmup
        for day in _trading_days(3):
            for i in range(20):
                v = 5000.0 if i in spike_offsets else 1000.0
                bars.append(_mk_bar(day, i, 100.0, 100.5, 99.5, 100.0, v=v))
        ctx = PatternContext.build(tuple(bars))
        rule = self._known_volume_spike_rule(mult=2.0, lookback=5)
        hits = evaluate_rule_over_range(rule, ctx, timeframe="5m")

        assert len(hits) == 2 * 3   # 2 spikes/day x 3 days == 6, EXACTLY
        fired_bar_indices_within_day = sorted({h.bar_index % 20 for h in hits})
        assert fired_bar_indices_within_day == sorted(spike_offsets)

        stats = prescreen.compute_stats(hits, ctx.bars)
        assert stats["n_trading_days"] == 3
        assert stats["total_fires"] == 6
        assert stats["days_with_fire"] == 3
        assert stats["pct_days_fired"] == pytest.approx(100.0)
        assert stats["fires_per_day"] == pytest.approx(2.0)

    def test_zero_fires_on_flat_volume(self):
        bars = [_mk_bar(d, i, 100.0, 100.2, 99.8, 100.0, v=1000.0)
                for d in _trading_days(2) for i in range(10)]
        ctx = PatternContext.build(tuple(bars))
        rule = self._known_volume_spike_rule(mult=2.0, lookback=5)
        hits = evaluate_rule_over_range(rule, ctx, timeframe="5m")
        assert hits == []
        stats = prescreen.compute_stats(hits, ctx.bars)
        assert stats["total_fires"] == 0
        assert stats["pct_days_fired"] == 0.0
        assert stats["fires_per_month"] == 0.0

    def test_recent_window_split_narrows_denominator_and_hits(self):
        """5 trading days, a single spike on day 0 only. A recent-window that excludes
        day 0 must report zero fires and a shrunk n_trading_days -- proving
        compute_stats' window_start actually filters both the hit set AND the
        trading-day denominator, not just one of them."""
        days = _trading_days(5)
        bars: list[Bar] = []
        for di, day in enumerate(days):
            for i in range(10):
                v = 5000.0 if (di == 0 and i == 6) else 1000.0
                bars.append(_mk_bar(day, i, 100.0, 100.2, 99.8, 100.0, v=v))
        ctx = PatternContext.build(tuple(bars))
        rule = self._known_volume_spike_rule(mult=2.0, lookback=5)
        hits = evaluate_rule_over_range(rule, ctx, timeframe="5m")
        assert len(hits) == 1

        full = prescreen.compute_stats(hits, ctx.bars)
        assert full["n_trading_days"] == 5 and full["total_fires"] == 1

        recent = prescreen.compute_stats(hits, ctx.bars, window_start=days[1])
        assert recent["n_trading_days"] == 4
        assert recent["total_fires"] == 0


# ── 2. C27 verdict thresholds ───────────────────────────────────────────────────

class TestVerdictThresholds:
    @pytest.mark.parametrize("pct_days,fires_per_month,expected", [
        (81.0, 50.0, "NOISE-KILL"),     # over the 80% line -> NOISE-KILL regardless of frequency
        (80.0, 50.0, "TESTABLE"),       # exactly 80% is NOT > 80% -> falls through
        (10.0, 1.9, "TOO-RARE"),        # under the 2/month line
        (10.0, 2.0, "TESTABLE"),        # exactly 2.0 is NOT < 2 -> falls through
        (50.0, 10.0, "TESTABLE"),       # the healthy middle
        (90.0, 0.5, "NOISE-KILL"),      # NOISE-KILL is checked BEFORE too-rare
    ])
    def test_boundaries(self, pct_days, fires_per_month, expected):
        assert prescreen.classify_verdict(pct_days, fires_per_month) == expected


# ── 3. resampling ────────────────────────────────────────────────────────────────

class TestResample:
    def test_5m_to_15m_aggregation_is_correct(self):
        day = _trading_days(1)[0]
        t0 = dt.datetime.combine(day, dt.time(9, 30))
        rows = []
        # 3 5m bars -> should collapse into exactly ONE 15m bar: open=first open,
        # high=max high, low=min low, close=last close, volume=sum.
        for i, (o, h, l, c, v) in enumerate([
            (100.0, 100.5, 99.8, 100.2, 1000),
            (100.2, 101.0, 100.0, 100.8, 2000),
            (100.8, 100.9, 100.3, 100.5, 1500),
        ]):
            rows.append({"timestamp_et": t0 + dt.timedelta(minutes=5 * i), "date": day,
                         "open": o, "high": h, "low": l, "close": c, "volume": v})
        df = pd.DataFrame(rows)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize("America/New_York")
        out = prescreen.resample_timeframe(df, 15)
        assert len(out) == 1
        row = out.iloc[0]
        assert row["open"] == pytest.approx(100.0)
        assert row["high"] == pytest.approx(101.0)
        assert row["low"] == pytest.approx(99.8)
        assert row["close"] == pytest.approx(100.5)
        assert row["volume"] == pytest.approx(4500)

    def test_resample_never_bleeds_across_session_boundary(self):
        d1, d2 = _trading_days(2)
        t1 = dt.datetime.combine(d1, dt.time(15, 50))
        t2 = dt.datetime.combine(d2, dt.time(9, 30))
        rows = [
            {"timestamp_et": t1, "date": d1, "open": 100, "high": 100.5, "low": 99.5, "close": 100.3, "volume": 1000},
            {"timestamp_et": t2, "date": d2, "open": 200, "high": 200.5, "low": 199.5, "close": 200.3, "volume": 1000},
        ]
        df = pd.DataFrame(rows)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize("America/New_York")
        out = prescreen.resample_timeframe(df, 15)
        # two separate sessions -> two separate resampled bars, NEVER merged into one
        assert len(out) == 2
        assert set(out["date"]) == {d1, d2}
        assert out.loc[out["date"] == d1, "open"].iloc[0] == pytest.approx(100)
        assert out.loc[out["date"] == d2, "open"].iloc[0] == pytest.approx(200)

    def test_5m_passthrough_is_a_true_noop(self):
        day = _trading_days(1)[0]
        t0 = dt.datetime.combine(day, dt.time(9, 30))
        df = pd.DataFrame([{"timestamp_et": t0, "date": day, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize("America/New_York")
        assert prescreen.resample_timeframe(df, 5) is df


# ── 4. master-CSV picking (no real disk data touched -- tmp_path only) ─────────

class TestFindMasterCsv:
    def test_picks_widest_range_earliest_start_then_latest_end(self, tmp_path):
        for name in [
            "spy_5m_2025-06-01_2025-12-31.csv",
            "spy_5m_2025-01-01_2026-05-07.csv",
            "spy_5m_2025-01-01_2026-07-08.csv",   # widest: earliest start AND latest end
            "spy_5m_2026-05-19_2026-07-09.csv",
            "vix_5m_2025-01-01_2026-07-08.csv",   # must be ignored (vix, not spy)
        ]:
            (tmp_path / name).write_text("timestamp_et,open,high,low,close,volume\n")
        picked = prescreen.find_master_csv(tmp_path)
        assert picked.name == "spy_5m_2025-01-01_2026-07-08.csv"

    def test_raises_when_no_master_csv_present(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            prescreen.find_master_csv(tmp_path)


# ── 5. build_levels_by_date fails soft on thin data ─────────────────────────────

class TestBuildLevelsByDate:
    def test_thin_prior_history_yields_empty_levels_not_a_crash(self):
        day = _trading_days(1)[0]
        t0 = dt.datetime.combine(day, dt.time(9, 30))
        rows = [{"timestamp_et": t0 + dt.timedelta(minutes=5 * i), "date": day,
                 "open": 100, "high": 100.2, "low": 99.8, "close": 100, "volume": 1000}
                for i in range(5)]
        df = pd.DataFrame(rows)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize("America/New_York")
        out = prescreen.build_levels_by_date(df)
        assert out[day] == ()
