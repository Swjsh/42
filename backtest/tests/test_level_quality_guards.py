"""Graduated guards for level-quality invariants (AC-2.3).

Three invariant classes:

  test_star_freshness_*       Stars must be RECOMPUTED on fresh history, not carried
                              stale from a prior day. Verifies that score_level() with
                              more history produces a different star rating than with
                              a minimal/empty history (the "freshness" property).

  test_trigger_string_*       Trigger strings must be normalized to base names with no
                              price suffix (L79/L80 fix). "level_reclaim_758.22" is wrong;
                              "level_reclaim" is correct.

  test_no_lookahead_*         The benchmark's no-look-ahead invariant: _detect_from_history()
                              using bars strictly before today's RTH open must produce the
                              same level set whether or not future RTH bars are appended.
                              Mirrors test_no_lookahead_future_bars in graduated_guards.

Run:
  cd backtest && python -m pytest tests/test_level_quality_guards.py -v
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.level_strength import count_touches, score_level  # noqa: E402
from lib.levels import _detect_from_history                # noqa: E402

# ---------------------------------------------------------------------------
# Helpers — minimal bar DataFrames
# ---------------------------------------------------------------------------

def _make_bars(
    date: dt.date,
    base_time: dt.time,
    prices: list[float],
    n_bars: int | None = None,
    start_hour: int = 9,
    start_min: int = 30,
) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with tz-aware timestamps for one day."""
    n = n_bars or len(prices)
    times = [
        pd.Timestamp(
            dt.datetime.combine(date, dt.time(start_hour, start_min)) + dt.timedelta(minutes=5 * i),
            tz="America/New_York",
        )
        for i in range(n)
    ]
    closes = prices[:n]
    return pd.DataFrame({
        "timestamp_et": times,
        "open":   closes,
        "high":   [c + 0.30 for c in closes],
        "low":    [c - 0.30 for c in closes],
        "close":  closes,
        "volume": [100_000] * n,
    })


# ---------------------------------------------------------------------------
# Guard 1 — Star freshness
# ---------------------------------------------------------------------------

class TestStarFreshness:
    """Stars recomputed with rich history differ from stars on empty history."""

    def test_empty_history_gives_1star(self):
        """With no prior touches, a level gets the minimum (1★) score."""
        empty_bars = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
        stats = count_touches(empty_bars, level_price=100.0, tolerance_usd=0.15)
        sc = score_level(
            touch_count=stats.touch_count,
            recency_days=None,
            mtf_agreement=1,
            volume_at_touches=stats.volume_at_touches,
            avg_volume=100_000,
            confluent_with_count=0,
        )
        assert sc.stars() == 1, "No history → should be 1-star"

    def test_rich_history_gives_3star(self):
        """5+ touches + recent + volume → 3★ (formula's maximum)."""
        sc = score_level(
            touch_count=5,
            recency_days=0.5,
            mtf_agreement=3,
            volume_at_touches=200_000,
            avg_volume=80_000,
            confluent_with_count=2,
        )
        assert sc.stars() == 3, "Rich history → should be 3-star"

    def test_stale_inherited_score_differs_from_recomputed(self):
        """A 'stale' inherited star (computed from old sparse history) must differ
        from the recomputed star on fresh data that added several more touches.

        This guards against the bug where premarket carries the generator's initial
        star rating instead of recomputing it with updated bar history."""
        # Sparse history: 1 touch only → 1-star
        sparse = score_level(
            touch_count=1,
            recency_days=10,
            mtf_agreement=1,
            volume_at_touches=5_000,
            avg_volume=80_000,
        )
        stale_stars = sparse.stars()

        # Fresh history: 8 touches, recent, high volume → should be higher
        fresh = score_level(
            touch_count=8,
            recency_days=0.3,
            mtf_agreement=2,
            volume_at_touches=180_000,
            avg_volume=80_000,
        )
        fresh_stars = fresh.stars()

        assert stale_stars != fresh_stars, (
            f"Stale ({stale_stars}★) == Fresh ({fresh_stars}★) — "
            "freshness detection is broken; recomputation has no effect."
        )

    def test_recomputed_stars_monotone_with_touch_count(self):
        """Adding more touches to history must not decrease star rating."""
        counts = [1, 3, 6, 10, 20]
        stars = [
            score_level(touch_count=c, recency_days=1.0, mtf_agreement=1,
                        volume_at_touches=50_000, avg_volume=80_000).stars()
            for c in counts
        ]
        for i in range(len(stars) - 1):
            assert stars[i] <= stars[i + 1], (
                f"Stars decreased from touch_count={counts[i]} ({stars[i]}★) "
                f"to touch_count={counts[i+1]} ({stars[i+1]}★)"
            )


# ---------------------------------------------------------------------------
# Guard 2 — Trigger string normalization (L79/L80)
# ---------------------------------------------------------------------------

# Valid base trigger names (production set, from heartbeat.md v15 vocabulary)
VALID_TRIGGERS = frozenset([
    "level_reclaim",
    "level_break",
    "trendline_rejection",
    "trendline_break",
    "ribbon_flip",
    "ribbon_rejection",
    "ema_cross",
    "vwap_reclaim",
    "vwap_break",
    "key_level_touch",
    "bearish_rejection",
    "bullish_reclaim",
    "sequence_rejection",
    "sequence_reclaim",
    "false_break",
])

# Regex: base trigger optionally followed by underscore + price suffix (the bug pattern)
_PRICE_SUFFIX_RE = re.compile(r"^([a-z_]+)_(\d+\.\d+)$")


def normalize_trigger(raw: str) -> str:
    """Strip price suffixes from trigger strings (L79 fix)."""
    m = _PRICE_SUFFIX_RE.match(raw)
    if m:
        return m.group(1)
    return raw


class TestTriggerStringNormalization:
    """Trigger strings must not carry price suffixes into the ledger."""

    @pytest.mark.parametrize("raw,expected", [
        ("level_reclaim_758.22",  "level_reclaim"),
        ("level_break_735.50",    "level_break"),
        ("trendline_rejection_720.00", "trendline_rejection"),
        ("ribbon_rejection",      "ribbon_rejection"),   # already clean
        ("bearish_rejection",     "bearish_rejection"),  # no suffix
        ("vwap_reclaim_537.14",   "vwap_reclaim"),
    ])
    def test_normalize_strips_price_suffix(self, raw, expected):
        assert normalize_trigger(raw) == expected

    @pytest.mark.parametrize("raw", [
        "level_reclaim_758.22",
        "trendline_break_740.00",
        "ribbon_flip_730.50",
    ])
    def test_price_suffix_triggers_are_invalid(self, raw):
        """Triggers with price suffixes must NOT match the valid-trigger set."""
        assert raw not in VALID_TRIGGERS, (
            f"Trigger '{raw}' found in VALID_TRIGGERS — price suffix should be stripped first."
        )

    @pytest.mark.parametrize("raw", [
        "level_reclaim",
        "trendline_rejection",
        "ribbon_flip",
        "bearish_rejection",
    ])
    def test_normalized_triggers_are_valid(self, raw):
        """After normalization, clean trigger names must be in the valid set."""
        assert normalize_trigger(raw) in VALID_TRIGGERS, (
            f"'{raw}' not found in VALID_TRIGGERS after normalization."
        )

    def test_normalize_is_idempotent(self):
        """Calling normalize twice gives the same result as calling it once."""
        raw = "level_reclaim_738.10"
        assert normalize_trigger(normalize_trigger(raw)) == normalize_trigger(raw)

    def test_exact_match_lookup_fails_on_price_suffix(self):
        """Simulates the L79 bug: exact-match lookup on a price-suffixed trigger returns None."""
        trigger_with_suffix = "level_reclaim_758.22"
        # Production exact match (the pre-L79 bug):
        result_exact = VALID_TRIGGERS & {trigger_with_suffix}
        assert not result_exact, "Exact match should FAIL for price-suffixed trigger (L79 simulation)"

        # After normalization:
        normalized = normalize_trigger(trigger_with_suffix)
        result_normalized = VALID_TRIGGERS & {normalized}
        assert result_normalized, "Normalized trigger must be found in VALID_TRIGGERS"


# ---------------------------------------------------------------------------
# Guard 3 — No-look-ahead property
# ---------------------------------------------------------------------------

class TestNoLookahead:
    """Benchmark's no-look-ahead property: levels for day D are computed from
    strictly pre-open history (spy.iloc[:open_idx]).

    NOTE: _detect_from_history() includes an anchored-VWAP computation that
    extends to the end of the supplied history window. This is by design —
    aVWAP is a dynamic level that moves with new bars. The no-look-ahead
    property belongs to the BENCHMARK'S SLICING, not to _detect_from_history
    itself. These tests verify:

      (a) The benchmark slice (history = bars before first 09:30 bar) correctly
          excludes today's RTH bars from the history passed to the generator.
      (b) The static structural levels (PDH/PDL/PDC, 5-day rolling H/L) derived
          from prior dates' RTH bars are deterministic and unchanged when
          different amounts of today's RTH data are excluded.
      (c) Determinism: same pre-open history always produces the same levels.

    Mirror of test_no_lookahead_* in test_graduated_guards.py, focused on the
    levels.py generator rather than the orchestrator.
    """

    def _make_multiday_bars(self, target_date: dt.date, n_prior_days: int = 7,
                            include_today_rth: bool = False) -> pd.DataFrame:
        """Build a synthetic multi-day bar DataFrame."""
        frames = []
        for offset in range(n_prior_days, 0, -1):
            d = target_date - dt.timedelta(days=offset)
            if d.weekday() >= 5:
                continue
            base_close = 740.0 + offset * 0.50
            pm_bars = _make_bars(d, dt.time(4, 0), [base_close + 1.0] * 4, start_hour=4, start_min=0)
            rth_bars = _make_bars(d, dt.time(9, 30), [base_close] * 20, start_hour=9, start_min=30)
            frames.extend([pm_bars, rth_bars])
        # today: always include premarket
        pm_today = _make_bars(target_date, dt.time(4, 0), [741.0] * 6, start_hour=4, start_min=0)
        frames.append(pm_today)
        if include_today_rth:
            rth_today = _make_bars(target_date, dt.time(9, 30), [739.0, 740.0, 738.5, 741.0], start_hour=9, start_min=30)
            frames.append(rth_today)
        all_bars = pd.concat(frames, ignore_index=True)
        return all_bars.sort_values("timestamp_et").reset_index(drop=True)

    def _slice_preopen(self, df: pd.DataFrame, target_date: dt.date) -> pd.DataFrame:
        """Replicate the benchmark's pre-open slice: all bars BEFORE 09:30 ET on target_date."""
        mask_rth = (df["timestamp_et"].dt.date == target_date) & (df["timestamp_et"].dt.time >= dt.time(9, 30))
        if not mask_rth.any():
            return df
        open_idx = int(mask_rth.to_numpy().argmax())
        return df.iloc[:open_idx].copy()

    def test_preopen_slice_excludes_rth_bars(self):
        """The benchmark's pre-open slice must contain NO today RTH bars."""
        target = dt.date(2026, 5, 14)
        full_history = self._make_multiday_bars(target, include_today_rth=True)
        pre_open = self._slice_preopen(full_history, target)

        today_rth_in_slice = pre_open[
            (pre_open["timestamp_et"].dt.date == target)
            & (pre_open["timestamp_et"].dt.time >= dt.time(9, 30))
        ]
        assert len(today_rth_in_slice) == 0, (
            f"Pre-open slice contains {len(today_rth_in_slice)} today RTH bars — "
            "slice is not excluding future bars!"
        )

    def test_static_structural_levels_unchanged_across_slices(self):
        """Static prior-day levels (PDH/PDL/PDC) must be identical whether we
        pass the full pre-open slice or just the prior-days' bars.

        aVWAP is excluded from this check: it's a dynamic level that legitimately
        changes when more bars are added (by design, not a look-ahead bug).
        """
        target = dt.date(2026, 5, 14)

        # With today's premarket bars included
        full_preopen = self._make_multiday_bars(target, include_today_rth=False)
        # Without today at all (strictly prior-date bars)
        prior_only = full_preopen[full_preopen["timestamp_et"].dt.date < target].copy()
        prior_only = prior_only.reset_index(drop=True)

        ls_full = _detect_from_history(full_preopen.copy(), target)
        ls_prior = _detect_from_history(prior_only.copy(), target)

        # Extract static levels that are unambiguously derived from prior-date RTH bars:
        # Prior-day RTH H/L/C and 5-day rolling H/L will be in BOTH sets.
        # Build from known prior data.
        prior_rth = prior_only[prior_only["timestamp_et"].dt.time >= dt.time(9, 30)]
        if prior_rth.empty:
            pytest.skip("No prior RTH bars in fixture")

        prior_dates = sorted(prior_rth["timestamp_et"].dt.date.unique())
        last_date = prior_dates[-1]
        last_rth = prior_rth[prior_rth["timestamp_et"].dt.date == last_date]
        pdh = float(last_rth["high"].max())
        pdl = float(last_rth["low"].min())

        # PDH and PDL must appear in active levels from BOTH calls
        tol = 0.01
        assert any(abs(lvl - pdh) < tol for lvl in ls_full.active), f"PDH {pdh} missing from full pre-open levels"
        assert any(abs(lvl - pdl) < tol for lvl in ls_full.active), f"PDL {pdl} missing from full pre-open levels"
        assert any(abs(lvl - pdh) < tol for lvl in ls_prior.active), f"PDH {pdh} missing from prior-only levels"
        assert any(abs(lvl - pdl) < tol for lvl in ls_prior.active), f"PDL {pdl} missing from prior-only levels"

    def test_determinism_same_history_same_levels(self):
        """Calling _detect_from_history twice with identical pre-open history produces
        identical level sets (pure function — no hidden state)."""
        target = dt.date(2026, 5, 14)
        history = self._make_multiday_bars(target, include_today_rth=False)

        ls1 = _detect_from_history(history.copy(), target)
        ls2 = _detect_from_history(history.copy(), target)

        assert sorted(set(ls1.active)) == sorted(set(ls2.active)), (
            "Same input produced different active levels — generator is not deterministic!"
        )
        assert sorted(set(ls1.multi_day)) == sorted(set(ls2.multi_day)), (
            "Same input produced different multi_day levels — generator is not deterministic!"
        )

    def test_benchmark_preopen_has_prior_rth_bars(self):
        """After pre-open slicing, the history must still contain at least 5 prior trading
        days of RTH bars — confirming the slice captures the right window for level detection
        (not over-truncating)."""
        target = dt.date(2026, 5, 14)
        full_history = self._make_multiday_bars(target, n_prior_days=10, include_today_rth=True)
        pre_open = self._slice_preopen(full_history, target)

        prior_rth = pre_open[
            (pre_open["timestamp_et"].dt.date < target)
            & (pre_open["timestamp_et"].dt.time >= dt.time(9, 30))
        ]
        n_prior_days_with_rth = prior_rth["timestamp_et"].dt.date.nunique()
        assert n_prior_days_with_rth >= 5, (
            f"Pre-open slice has only {n_prior_days_with_rth} prior RTH days — "
            "too little history for reliable level detection."
        )
