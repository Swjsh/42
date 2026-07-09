"""Guards for the Phase-1 swing-seed detectors (backtest/futures/seeds/).

Covers: grid shapes, the RRW seed's disclosed vol-filter no-op, the E2 context
seed's at-level/VWAP-alignment logic on a hand-built example, and the
structure seed's no-look-ahead property (the load-bearing correctness
guarantee for running find_swing_points/walk_structure over a full historical
array once). A slow, data-dependent smoke test cross-checks the RRW seed
against the real cached MES data (skipped if the CSV is absent).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures.seeds import rrw_seed, e2_context_seed, structure_seed  # noqa: E402


def make_daily_bars(rows: list[tuple], start: dt.date = dt.date(2025, 1, 2)) -> pd.DataFrame:
    """rows: (open, high, low, close, volume). One trading day per row (no
    weekend skipping needed for these unit tests -- only ordering matters)."""
    out = []
    for i, (o, h, l, c, v) in enumerate(rows):
        d = start + dt.timedelta(days=i)
        out.append({"timestamp_et": pd.Timestamp.combine(d, dt.time(9, 30)).tz_localize("America/New_York"),
                     "date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return pd.DataFrame(out)


# ─── RRW seed ───────────────────────────────────────────────────────────────

class TestRRWSeed:
    def test_grid_has_8_combos(self):
        assert len(rrw_seed.build_grid()) == 8

    def test_vol_mult_min_always_disabled(self):
        """The disclosed NOT-PORTABLE contract: every combo's params must have
        vol_mult_min=0.0 regardless of grid values (day-relative volume median
        has no meaning at daily granularity -- see module docstring)."""
        for combo in rrw_seed.build_grid():
            params = rrw_seed._params_for(combo)
            assert params.vol_mult_min == 0.0

    def test_stack_filter_maps_correctly(self):
        p_nf = rrw_seed._params_for({"wick_frac_min": 0.35, "break_lookback_bars": 5,
                                     "stack_filter": "not_flipped"})
        p_any = rrw_seed._params_for({"wick_frac_min": 0.35, "break_lookback_bars": 5,
                                      "stack_filter": "any"})
        assert p_nf.require_stack_not_flipped is True
        assert p_any.require_stack_not_flipped is False

    def test_generate_signals_empty_bars_returns_empty_frame(self):
        out = rrw_seed.generate_signals(make_daily_bars([]))
        assert len(out) == 0
        assert list(out.columns) == ["combo_id", "wick_frac_min", "break_lookback_bars",
                                      "stack_filter", "signal_bar_idx", "direction",
                                      "wick_frac", "bars_since_break", "stack_at_signal"]

    @pytest.mark.slow
    def test_real_mes_daily_smoke(self):
        csv = REPO / "backtest" / "data" / "futures" / "MES_1m_continuous.csv"
        if not csv.exists():
            pytest.skip("MES_1m_continuous.csv not found")
        from futures.data import load_continuous_csv, resample_daily
        daily = resample_daily(load_continuous_csv(str(csv)))
        signals = rrw_seed.generate_signals(daily)
        assert len(signals) > 0, "expected at least some RRW fires over 18mo of MES daily bars"
        assert set(signals["direction"].unique()) <= {"long", "short"}
        assert signals["signal_bar_idx"].between(0, len(daily) - 1).all()
        assert signals["combo_id"].nunique() <= 8


# ─── E2 context seed ────────────────────────────────────────────────────────

class TestE2ContextSeed:
    def test_grid_has_2_combos(self):
        assert len(e2_context_seed.build_grid()) == 2

    def test_long_signal_when_at_pdh_and_above_vwap(self):
        # Day 0: PDH will be 110 (high). Day 1: close = 110.05 (0.045% above PDH,
        # within 0.1% tol) AND close > vwap -> LONG signal.
        bars = make_daily_bars([
            (100, 110, 99, 105, 1000),   # day 0: sets PDH=110
            (105, 111, 104, 110.05, 1000),  # day 1: close near PDH, above vwap
        ])
        vwap_by_date = pd.Series({bars["date"].iloc[1]: 108.0})
        sig = e2_context_seed.generate_signals(bars, vwap_by_date, grid=[{"tol_pct": 0.001}])
        assert len(sig) == 1
        assert sig.iloc[0]["direction"] == "long"
        assert sig.iloc[0]["signal_bar_idx"] == 1
        assert sig.iloc[0]["nearest_level"] == "PDH"

    def test_short_signal_when_at_pdl_and_below_vwap(self):
        bars = make_daily_bars([
            (100, 101, 90, 95, 1000),        # day 0: sets PDL=90
            (95, 96, 89.90, 89.95, 1000),    # day 1: CLOSE near PDL (0.056% away), below vwap
        ])
        vwap_by_date = pd.Series({bars["date"].iloc[1]: 93.0})
        sig = e2_context_seed.generate_signals(bars, vwap_by_date, grid=[{"tol_pct": 0.001}])
        assert len(sig) == 1
        assert sig.iloc[0]["direction"] == "short"
        assert sig.iloc[0]["nearest_level"] == "PDL"

    def test_no_signal_when_far_from_all_levels(self):
        bars = make_daily_bars([
            (100, 110, 99, 105, 1000),
            (105, 111, 104, 108.0, 1000),   # not within 0.1% of PDH(110)/PDL(99)/PDC(105)
        ])
        vwap_by_date = pd.Series({bars["date"].iloc[1]: 106.0})
        sig = e2_context_seed.generate_signals(bars, vwap_by_date, grid=[{"tol_pct": 0.001}])
        assert len(sig) == 0

    def test_no_signal_when_vwap_missing(self):
        bars = make_daily_bars([(100, 110, 99, 105, 1000), (105, 111, 104, 110.0, 1000)])
        sig = e2_context_seed.generate_signals(bars, pd.Series(dtype=float), grid=[{"tol_pct": 0.001}])
        assert len(sig) == 0

    def test_session_vwap_matches_hand_calc(self):
        rth = pd.DataFrame({
            "timestamp_et": [pd.Timestamp("2025-01-02 09:30", tz="America/New_York"),
                             pd.Timestamp("2025-01-02 09:35", tz="America/New_York")],
            "high": [101.0, 103.0], "low": [99.0, 101.0], "close": [100.0, 102.0],
            "volume": [10.0, 20.0],
        })
        vwap = e2_context_seed.compute_session_vwap_by_date(rth)
        tp1, tp2 = (101 + 99 + 100) / 3.0, (103 + 101 + 102) / 3.0
        expected = (tp1 * 10 + tp2 * 20) / 30.0
        assert vwap.iloc[0] == pytest.approx(expected)


# ─── Structure seed ─────────────────────────────────────────────────────────

class TestStructureSeed:
    def test_grid_has_6_combos(self):
        assert len(structure_seed.build_grid()) == 6

    def test_bars_to_bar_objects_are_tz_aware_utc(self):
        bars = make_daily_bars([(100, 105, 95, 100, 10), (100, 106, 96, 101, 10)])
        objs = structure_seed.bars_df_to_bar_objects(bars)
        assert len(objs) == 2
        assert objs[0].open_time.tzinfo is not None
        assert objs[0].open_time.utcoffset().total_seconds() == 0

    def test_bullish_bos_fires_on_clear_uptrend_break(self):
        # Swing-high at bar 2 (100->105->95 pattern needs window bars each side);
        # a clean uptrend break sequence with window=2.
        vals = [100, 95, 105, 96, 94, 108, 97, 95, 112]
        bars = make_daily_bars([(v, v + 3, v - 3, v, 100) for v in vals])
        sig = structure_seed.generate_signals(bars, grid=[{"window": 2, "trade_on": "BOS"},
                                                            {"window": 2, "trade_on": "CHoCH"}])
        assert len(sig) >= 1
        assert set(sig["direction"].unique()) <= {"long", "short"}
        assert sig["signal_bar_idx"].between(0, len(bars) - 1).all()


class TestStructureSeedNoLookahead:
    """The correctness guarantee referenced by structure_seed.py's docstring:
    running find_swing_points/walk_structure over the FULL bar array must
    never let an event at break_index <= k depend on bars strictly after k."""

    def _events_up_to(self, bars: pd.DataFrame, window: int):
        objs = structure_seed.bars_df_to_bar_objects(bars)
        from crypto.lib.trendlines import find_swing_points
        from crypto.lib.market_structure import walk_structure
        swings = find_swing_points(objs, window=window, inclusive_right=True)
        _, events = walk_structure(objs, swings, window)
        return events

    def test_mutating_future_bars_does_not_change_past_events(self):
        vals = [100, 95, 105, 96, 94, 108, 97, 95, 112, 90, 130, 80, 140]
        bars_a = make_daily_bars([(v, v + 3, v - 3, v, 100) for v in vals])
        window = 2
        events_a = self._events_up_to(bars_a, window)

        # Cut at index k: keep bars[0:k+1] identical, WILDLY change everything after.
        k = 6
        mutated_tail = [(999, 1005, 990, 999, 100)] * (len(vals) - (k + 1))
        bars_b = make_daily_bars(
            [(bars_a["open"].iloc[i], bars_a["high"].iloc[i], bars_a["low"].iloc[i],
              bars_a["close"].iloc[i], bars_a["volume"].iloc[i]) for i in range(k + 1)] + mutated_tail
        )
        events_b = self._events_up_to(bars_b, window)

        events_a_upto_k = [e for e in events_a if e.break_index <= k]
        events_b_upto_k = [e for e in events_b if e.break_index <= k]
        assert events_a_upto_k == events_b_upto_k, (
            "an event at/before the mutation boundary changed when FUTURE bars were "
            "mutated -- this would mean the structure seed has a look-ahead leak"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
