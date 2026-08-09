"""Guards for the trendline swing seed (backtest/futures/trendline_geometry.py +
backtest/futures/seeds/trendline_swing_seed.py). Covers: grid shape, validity-rule
rejection (spacing/span), bounce/break/break_retest firing on hand-built synthetic bars,
safety-line construction, no-look-ahead (the load-bearing correctness property, per this
repo's C6 lesson category), and a real-data smoke test (skipped if the CSV is absent).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures import trendline_geometry as tg  # noqa: E402
from futures.seeds import trendline_swing_seed as tls  # noqa: E402
from futures.swing_sim import wilder_atr  # noqa: E402
from futures.instruments import MES  # noqa: E402


def make_h4_bars(rows: list[tuple], start: dt.date = dt.date(2025, 1, 2)) -> pd.DataFrame:
    """rows: (open, high, low, close, volume). Two bars per synthetic trading day (matches
    `data.resample_4h_rth`'s 2-bars/session shape) -- only bar ORDER and the `date` grouping
    matter for these unit tests, not real calendar weekends."""
    out = []
    for i, (o, h, l, c, v) in enumerate(rows):
        day_offset = i // 2
        bucket = i % 2
        d = start + dt.timedelta(days=day_offset)
        t = dt.time(9, 30) if bucket == 0 else dt.time(13, 30)
        out.append({"timestamp_et": pd.Timestamp.combine(d, t).tz_localize("America/New_York"),
                     "date": d, "bucket": bucket, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(out)


def make_daily_bars(rows: list[tuple], start: dt.date = dt.date(2025, 1, 2)) -> pd.DataFrame:
    out = []
    for i, (o, h, l, c, v) in enumerate(rows):
        d = start + dt.timedelta(days=i)
        out.append({"timestamp_et": pd.Timestamp.combine(d, dt.time(9, 30)).tz_localize("America/New_York"),
                     "date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(out)


def _baseline_bar(low_baseline=6010.0, close_baseline=6010.0):
    return (6010.0, 6015.0, low_baseline, close_baseline, 100)


def _build_ascending_support_bars(n_total: int = 45) -> pd.DataFrame:
    """3 EXACTLY colinear swing lows on line y = 6000 + 0.05*x at bar_index 2, 18, 34
    (spacing 16/16 >= 6, span 32 >= 30) -- every other bar is a high-baseline filler bar
    that can't compete as a touch of this line. window=2 fractal: each touch bar's
    neighbors (i-2..i-1, i+1..i+2) sit well above it."""
    rows = [list(_baseline_bar()) for _ in range(n_total)]
    for idx in (2, 18, 34):
        price = 6000.0 + 0.05 * idx
        rows[idx] = [price + 0.5, price + 1.0, price, price + 0.3, 100]
    return make_h4_bars([tuple(r) for r in rows])


class TestGrid:
    def test_build_grid_has_12_combos(self):
        grid = tls.build_grid()
        assert len(grid) == 12
        assert {c["window"] for c in grid} == {2, 3}
        assert {c["entry_trigger"] for c in grid} == {"bounce", "break", "break_retest"}
        assert {c["stop_shape"] for c in grid} == {"atr", "safety_line"}


class TestSwingGeometry:
    def test_finds_ascending_support_line_with_3_touches(self):
        bars = _build_ascending_support_bars()
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        support_lines = [l for l in lines if l.kind == "support"]
        assert len(support_lines) >= 1
        best = max(support_lines, key=lambda l: len(l.touch_indices))
        assert len(best.touch_indices) >= 3
        assert best.last_touch_idx - best.first_touch_idx >= 30

    def test_touches_too_close_together_rejected(self):
        # 3 colinear points but spacing 3/3 < min_spacing_bars=6 -- must NOT qualify.
        rows = [list(_baseline_bar()) for _ in range(40)]
        for idx in (10, 13, 16):
            price = 6000.0 + 0.05 * idx
            rows[idx] = [price + 0.5, price + 1.0, price, price + 0.3, 100]
        bars = make_h4_bars([tuple(r) for r in rows])
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        # No support line should span exactly these 3 tightly-spaced points.
        bad = [l for l in lines if l.kind == "support" and set(l.touch_indices) >= {10, 13, 16}]
        assert bad == []

    def test_span_too_short_rejected(self):
        # 3 colinear points, spacing 6/6 = OK, but span 12 < min_span_bars=30.
        rows = [list(_baseline_bar()) for _ in range(30)]
        for idx in (4, 10, 16):
            price = 6000.0 + 0.05 * idx
            rows[idx] = [price + 0.5, price + 1.0, price, price + 0.3, 100]
        bars = make_h4_bars([tuple(r) for r in rows])
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        bad = [l for l in lines if l.kind == "support" and set(l.touch_indices) >= {4, 10, 16}]
        assert bad == []


class TestEntryTriggers:
    def test_bounce_fires_long_off_ascending_support(self):
        bars = _build_ascending_support_bars(n_total=45)
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        support = max((l for l in lines if l.kind == "support"), key=lambda l: len(l.touch_indices))
        # bar 37 (> confirmed_idx=34+2=36): low dips near the line, closes well back above.
        lp = support.price_at(37)
        bars.loc[37, ["low", "close", "open", "high"]] = [lp - 0.5, lp + 8.0, lp + 7.0, lp + 8.5]
        events = tls._walk_line_events(support, bars, tg.TOUCH_TOLERANCE_PCT)
        bounces = [e for e in events if e["event_type"] == "bounce" and e["bar_idx"] == 37]
        assert len(bounces) == 1
        assert bounces[0]["direction"] == "long"

    def test_break_fires_short_and_retest_is_found(self):
        bars = _build_ascending_support_bars(n_total=48)
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        support = max((l for l in lines if l.kind == "support"), key=lambda l: len(l.touch_indices))
        lp37 = support.price_at(37)
        # Bar 37 closes CLEARLY below the line -> break-short.
        bars.loc[37, ["low", "close", "open", "high"]] = [lp37 - 10.0, lp37 - 8.0, lp37 - 1.0, lp37 - 0.5]
        # Bar 39: price returns UP to retest the (now-resistance) line, closes back down
        # (comfortably past the ~0.10% tolerance band on both checks, not edge-of-tolerance).
        lp39 = support.price_at(39)
        bars.loc[39, ["low", "close", "open", "high"]] = [lp39 - 11.0, lp39 - 10.0, lp39 - 8.0, lp39]
        events = tls._walk_line_events(support, bars, tg.TOUCH_TOLERANCE_PCT)
        breaks = [e for e in events if e["event_type"] == "break"]
        retests = [e for e in events if e["event_type"] == "break_retest"]
        assert len(breaks) == 1 and breaks[0]["bar_idx"] == 37 and breaks[0]["direction"] == "short"
        assert len(retests) == 1 and retests[0]["direction"] == "short"
        # Line stops producing events after its own break (see module docstring).
        assert all(e["bar_idx"] <= retests[0]["bar_idx"] for e in events)


class TestSafetyLine:
    def test_bounce_safety_distance_is_distance_to_action_line(self):
        bars = _build_ascending_support_bars(n_total=45)
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        support = max((l for l in lines if l.kind == "support"), key=lambda l: len(l.touch_indices))
        entry_idx = 38
        ev = {"event_type": "bounce", "direction": "long", "line": support, "bar_idx": 37}
        dist = tls._stop_dist_for_event(ev, bars, entry_idx, {})
        expected = abs(float(bars["open"].iloc[entry_idx]) - support.price_at(entry_idx))
        assert dist == pytest.approx(max(expected, tg.MIN_STOP_DISTANCE_PTS))

    def test_break_with_no_opposing_swing_returns_none(self):
        bars = _build_ascending_support_bars(n_total=45)
        atr = wilder_atr(bars, period=14)
        lines = tg.find_trendlines(bars, window=2, atr=atr)
        support = max((l for l in lines if l.kind == "support"), key=lambda l: len(l.touch_indices))
        ev = {"event_type": "break", "direction": "short", "line": support, "bar_idx": 37}
        # No swing highs registered at all -> no opposing anchor available.
        swings_by_window_kind = {(support.window, "swing_high"): []}
        dist = tls._stop_dist_for_event(ev, bars, 38, swings_by_window_kind)
        assert dist is None


class TestNoLookahead:
    """The load-bearing correctness guarantee (C6 lesson category): a signal at bar k must
    never depend on bars strictly after k. Mirrors test_swing_seeds.py's
    TestStructureSeedNoLookahead pattern -- mutate the tail, verify the head is unchanged."""

    def test_mutating_future_bars_does_not_change_past_signals(self):
        rng = np.random.default_rng(11)
        n = 90
        base = 6000.0 + np.cumsum(rng.normal(0, 1.2, n))
        rows = []
        for i in range(n):
            c = float(base[i])
            o = c + rng.normal(0, 0.3)
            h = max(o, c) + abs(rng.normal(0.5, 0.3))
            l = min(o, c) - abs(rng.normal(0.5, 0.3))
            rows.append((o, h, l, c, 100))
        bars_a = make_h4_bars(rows)
        daily_a = make_daily_bars([(6000, 6020, 5990, 6000 + i * 2, 1000) for i in range(50)])

        sig_a = tls.generate_signals(bars_a, daily_a, apply_bias_filter=False)

        k = 60
        mutated_tail = [(9999.0, 10010.0, 9990.0, 9999.0, 100) for _ in range(n - (k + 1))]
        rows_b = rows[:k + 1] + mutated_tail
        bars_b = make_h4_bars(rows_b)
        sig_b = tls.generate_signals(bars_b, daily_a, apply_bias_filter=False)

        sig_a_upto_k = sig_a[sig_a["signal_bar_idx"] <= k].sort_values(
            ["combo_id", "signal_bar_idx", "direction"]).reset_index(drop=True)
        sig_b_upto_k = sig_b[sig_b["signal_bar_idx"] <= k].sort_values(
            ["combo_id", "signal_bar_idx", "direction"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(
            sig_a_upto_k[["combo_id", "signal_bar_idx", "direction", "action_line_kind"]],
            sig_b_upto_k[["combo_id", "signal_bar_idx", "direction", "action_line_kind"]],
        ), "a signal at/before the mutation boundary changed when FUTURE bars were mutated"

    def test_daily_bias_lookup_only_uses_prior_session(self):
        daily = make_daily_bars([(100 + i, 105 + i, 95 + i, 100 + i, 1000) for i in range(30)])
        lookup = tls._daily_bias_lookup(daily)
        # Mutate only the LAST row's OHLC drastically; every other date's bias entry must
        # be byte-identical (the EMA at index i only ever reads indices <= i).
        daily_mut = daily.copy()
        daily_mut.loc[len(daily_mut) - 1, ["open", "high", "low", "close"]] = [1.0, 1.0, 1.0, 1.0]
        lookup_mut = tls._daily_bias_lookup(daily_mut)
        for d in daily["date"].iloc[:-1]:
            assert lookup[d] == lookup_mut[d]


class TestNoDoubleCounting:
    """Regression for the 2026-08-09 pseudo-replication bug: a first real-MES run found
    one bar counted up to 9x within a single combo (820 raw rows -> 458 distinct events),
    because multiple geometrically-valid-but-overlapping trendlines fire the identical
    (direction, signal_bar_idx) event. `generate_signals` now collapses those to one row.
    This test PROVES the scenario is real (two distinct line objects independently produce
    overlapping raw events) before checking the dedup removes them -- a check that can't
    fail isn't a check."""

    def test_two_overlapping_lines_collapse_to_one_signal_per_bar(self, monkeypatch):
        import dataclasses
        bars = _build_ascending_support_bars(n_total=45)
        atr = wilder_atr(bars, period=14)
        real_lines = tg.find_trendlines(bars, window=2, atr=atr)
        support = max((l for l in real_lines if l.kind == "support"), key=lambda l: len(l.touch_indices))
        # A second "distinct" line object, shifted 0.01pt (well inside the ~6pt/0.10% tolerance)
        # -- stands in for two independently-anchored-but-overlapping valid trendlines.
        support_2 = dataclasses.replace(support, intercept=support.intercept + 0.01)
        # Bar 37 (> confirmed_idx=36): a live touch+reject bar both lines will react to
        # near-identically (their price_at() differs by only 0.01, inside tolerance).
        lp = support.price_at(37)
        bars.loc[37, ["low", "close", "open", "high"]] = [lp - 0.5, lp + 8.0, lp + 7.0, lp + 8.5]

        events_1 = tls._walk_line_events(support, bars, tg.TOUCH_TOLERANCE_PCT)
        events_2 = tls._walk_line_events(support_2, bars, tg.TOUCH_TOLERANCE_PCT)
        overlap_bars = {e["bar_idx"] for e in events_1} & {e["bar_idx"] for e in events_2}
        assert overlap_bars, "test scenario didn't actually create overlapping raw events -- fix the fixture"

        def fake_find_trendlines(bars_arg, window, atr_arg, **kwargs):
            return [support, support_2] if window == 2 else []
        monkeypatch.setattr(tls, "find_trendlines", fake_find_trendlines)

        daily = make_daily_bars([(6000, 6020, 5990, 6000 + i, 1000) for i in range(50)])
        sig = tls.generate_signals(bars, daily,
                                    grid=[{"window": 2, "entry_trigger": "bounce", "stop_shape": "atr"}],
                                    apply_bias_filter=False)
        dup_counts = sig.groupby(["combo_id", "direction", "signal_bar_idx"]).size()
        assert len(dup_counts) > 0
        assert dup_counts.max() == 1, (
            "duplicate (combo,direction,bar) rows survived generate_signals -- the "
            "pseudo-replication guard regressed"
        )


class TestEndToEndSmoke:
    def test_score_trendline_seed_runs_on_synthetic_bars(self):
        rng = np.random.default_rng(3)
        n = 200
        base = 6000.0 + np.cumsum(rng.normal(0, 1.5, n))
        rows = []
        for i in range(n):
            c = float(base[i])
            o = c + rng.normal(0, 0.4)
            h = max(o, c) + abs(rng.normal(0.6, 0.4))
            l = min(o, c) - abs(rng.normal(0.6, 0.4))
            rows.append((o, h, l, c, 500))
        bars = make_h4_bars(rows)
        daily = make_daily_bars([(6000 + i, 6020 + i, 5980 + i, 6000 + i, 5000) for i in range(100)])
        vix_by_date = {d: 15.0 for d in daily["date"]}
        oos_cut = daily["date"].iloc[70]
        horizons = [(2, "1d"), (6, "3d")]
        sc = tls.score_trendline_seed(bars, daily, MES, horizons, oos_cut, vix_by_date,
                                       apply_bias_filter=True)
        assert sc["verdict"] in ("PASS", "KILL")
        assert sc["n_cells_tested"] == 12 * 2 * len(horizons)
        for cell in sc["cells"]:
            assert "clears" in cell and "bh_fdr_survivor" in cell and "beats_buy_and_hold" in cell
            assert cell["stop_basis"] in ("atr", "safety_line")

    @pytest.mark.slow
    def test_real_mes_smoke(self):
        csv = REPO / "backtest" / "data" / "futures" / "MES_1m_continuous.csv"
        if not csv.exists():
            pytest.skip("MES_1m_continuous.csv not found")
        from futures.data import load_continuous_csv, resample_daily, resample_4h_rth
        raw = load_continuous_csv(str(csv))
        daily = resample_daily(raw)
        h4 = resample_4h_rth(raw)
        signals = tls.generate_signals(h4, daily, apply_bias_filter=True)
        assert set(signals["direction"].unique()) <= {"long", "short"}
        assert signals["signal_bar_idx"].between(0, len(h4) - 1).all()
        assert signals["combo_id"].nunique() <= 12
        # Not asserting len(signals) > 0 -- the whole point of this battery is that it might
        # legitimately be zero or near-zero if the validity grammar rarely qualifies on MES.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
