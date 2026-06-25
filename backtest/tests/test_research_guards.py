"""Unit + RED tests for backtest/lib/research_guards.py.

Two graduated session lessons turned into reusable assertions:

  beats_random_filter_null (L172) — RED-tested against the REAL W1 IV-skew failure
    (analysis/recommendations/web-vwap_cont_iv_skew_confirmer.json): the kept subset must
    NOT beat the random-filter null (reproduce ~p=0.76, passed=False). Also a positive
    discrimination test: a trivially-good filter (keep only the top quartile of P&L) MUST
    pass — proving the guard is not always-False.

  strike_band_covers_range (L177/L182) — RED-tested against the REAL event-day caches:
    backtest/data/options (the +-$5 narrow cache) MUST report covered=False on the
    2025-04-04 big-move day; backtest/data/options_event_wide (the +-$18 wide cache) MUST
    cover the same move's call-side excursion (covered=True).

Pure Python, $0. No OPRA round-trips: the L172 RED-test reconstructs the artifact's own
published null moments (n=149, kept=129, null_mean~48.3, null_p95~54.3, kept_mean=45.66)
deterministically; the band RED-test reads the REAL on-disk strike caches.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np
import pytest

from lib.research_guards import (
    beats_random_filter_null,
    dropped_day_fraction,
    strike_band_covers_range,
)

_REPO = Path(__file__).resolve().parent.parent.parent  # repo root (…/42)
_ARTIFACT = _REPO / "analysis" / "recommendations" / "web-vwap_cont_iv_skew_confirmer.json"
_NARROW_CACHE = _REPO / "backtest" / "data" / "options"
_WIDE_CACHE = _REPO / "backtest" / "data" / "options_event_wide"


# ─────────────────────────────────────────────────────────────────────────────
# GUARD 1 — beats_random_filter_null
# ─────────────────────────────────────────────────────────────────────────────
def _reconstruct_w1_base_pnl(n: int, target_mean: float, seed: int = 7) -> np.ndarray:
    """A deterministic base P&L vector matching the artifact's unfiltered moments.

    The artifact stores summary stats, not the raw 149-trade vector. We rebuild a vector
    with the SAME n and ~same mean so the random-filter null distribution reproduces the
    artifact's published null_mean/null_p95 to within a couple dollars. The kept_mask is then
    chosen so the kept-mean equals the artifact's filtered exp (45.66 < null mean) — which is
    the WHOLE POINT: a filter whose kept subset is BELOW the random distribution.
    """
    rng = np.random.default_rng(seed)
    # 0DTE per-trade with a tight stop: capped left tail, fat right tail (matches the real
    # exit histogram — mostly premium-stops + a few runners). Lognormal-ish, recentered.
    raw = rng.lognormal(mean=4.4, sigma=0.9, size=n) - 60.0
    raw = raw - raw.mean() + target_mean
    return raw


def test_beats_random_filter_null_RED_w1_iv_skew_fails():
    """RED: the REAL W1 IV-skew confirmer kept subset must FAIL the null (~p=0.76)."""
    art = json.loads(_ARTIFACT.read_text())
    v = art["variants"]["W1b_put_side_first_strict25d"]
    nullblk = v["random_filter_null_L172"]
    n_total = nullblk["n_total"]      # 149
    n_keep = nullblk["n_keep"]        # 129
    filtered_exp = v["filtered"]["exp"]  # 45.66 — the published kept-subset mean

    # Reconstruct a base vector with the artifact's unfiltered mean so the null distribution
    # lands on the published null_mean (~48.3) / null_p95 (~54.3).
    base_pnl = _reconstruct_w1_base_pnl(n_total, target_mean=art["unfiltered_baseline"]["exp"])

    # Build a kept_mask of size n_keep reproducing the filtered exp (45.66 < null mean ~48.3).
    # The real W1 confirmer dropped 20 trades that averaged ~$65.5 — only MODESTLY above the
    # $48.3 unfiltered mean (i.e. it shed mildly-good trades, dragging the kept mean down ~$2.6
    # below centre). That is the W1 signature: a subset just BELOW the random-drop centre ->
    # high p (~0.76), FAIL. We reproduce it by dropping the 20 trades nearest that $65.5 target.
    n_drop = n_total - n_keep  # 20
    drop_target = (base_pnl.mean() * n_total - filtered_exp * n_keep) / n_drop
    drop_idx = np.argsort(np.abs(base_pnl - drop_target))[:n_drop]
    kept_mask = np.ones(n_total, dtype=bool)
    kept_mask[drop_idx] = False

    res = beats_random_filter_null(base_pnl, kept_mask)

    assert res.applicable is True
    assert res.n_total == n_total and res.n_keep == n_keep
    # Kept-mean reproduces the artifact's filtered exp (within $3): a subset BELOW the centre.
    assert res.filt_mean < res.null_mean, res.reason
    assert abs(res.filt_mean - filtered_exp) < 3.0, (res.filt_mean, filtered_exp)
    # The kept subset is NOT in the right tail -> does NOT clear p95 -> FAILS (L172).
    assert res.passed is False, res.reason
    # Reproduce the published failure regime: p well above 0.05, near the artifact's 0.763.
    assert res.p_value is not None and 0.6 < res.p_value < 0.95, res.reason
    # Null distribution moments land near the artifact's published numbers (within $4).
    assert abs(res.null_mean - nullblk["null_mean"]) < 4.0, res.reason
    assert abs(res.null_p95 - nullblk["null_p95"]) < 4.0, res.reason
    print("RED W1 IV-skew:", res.reason)


def test_beats_random_filter_null_GREEN_top_quartile_passes():
    """Discrimination: a trivially-good filter (keep only top-quartile P&L) MUST pass."""
    rng = np.random.default_rng(11)
    base_pnl = rng.normal(40.0, 100.0, size=160)
    thresh = np.percentile(base_pnl, 75)
    kept_mask = base_pnl >= thresh  # keep the genuinely-best quarter
    res = beats_random_filter_null(base_pnl, kept_mask)
    assert res.applicable is True
    assert res.passed is True, res.reason
    assert res.p_value is not None and res.p_value < 0.05, res.reason
    assert res.filt_mean > res.null_p95, res.reason
    print("GREEN top-quartile:", res.reason)


def test_beats_random_filter_null_degenerate_keep_all_not_applicable():
    """Degenerate point-null (keep all) is flagged NOT applicable, not blessed."""
    base_pnl = [10.0, 20.0, 30.0, 40.0]
    res = beats_random_filter_null(base_pnl, [True, True, True, True])
    assert res.applicable is False
    assert res.passed is False
    assert "DEGENERATE" in res.reason


def test_beats_random_filter_null_degenerate_keep_none_not_applicable():
    base_pnl = [10.0, 20.0, 30.0, 40.0]
    res = beats_random_filter_null(base_pnl, [False, False, False, False])
    assert res.applicable is False
    assert res.passed is False


def test_beats_random_filter_null_deterministic():
    rng = np.random.default_rng(3)
    base_pnl = rng.normal(0, 50, size=80)
    mask = base_pnl >= np.median(base_pnl)
    a = beats_random_filter_null(base_pnl, mask, n_seeds=500)
    b = beats_random_filter_null(base_pnl, mask, n_seeds=500)
    assert a == b  # frozen dataclass equality — bit-reproducible


def test_beats_random_filter_null_length_mismatch_raises():
    with pytest.raises(ValueError):
        beats_random_filter_null([1.0, 2.0, 3.0], [True, False])


def test_beats_random_filter_null_empty_raises():
    with pytest.raises(ValueError):
        beats_random_filter_null([], [])


# ─────────────────────────────────────────────────────────────────────────────
# GUARD 2 — strike_band_covers_range
# ─────────────────────────────────────────────────────────────────────────────
def _cache_band(cache_dir: Path, yymmdd: str) -> tuple[float, float]:
    """Min/max strike (across both C and P) present in a cache dir for a given day."""
    pat = re.compile(r"SPY" + yymmdd + r"[CP](\d{8})\.csv$")
    strikes = []
    for f in os.listdir(cache_dir):
        m = pat.match(f)
        if m:
            strikes.append(int(m.group(1)) / 1000.0)
    if not strikes:
        raise FileNotFoundError(f"no {yymmdd} contracts in {cache_dir}")
    return min(strikes), max(strikes)


# 2025-04-04 (NFP / tariff crash): SPY realized intraday [502.5, 525.86], open ~523.64.
# The narrow +-$5 cache's PRICEABLE band is [497, 505] (strikes 506/507 exist only as
# *.csv.empty — no bars — which IS the missing_cache truncation in action); the call-side
# excursion to 525.86 blows ~$20 past it (the short-call loser leg the narrow cache silently
# drops). The wide +-$18 cache [505, 540] reaches it.
_EVENT_DAY = "250404"
_DAY_HIGH = 525.86      # realized intraday high — the call-wing tail
_ATM = 513.0            # approx ATM mid for the day


def test_strike_band_covers_range_RED_narrow_cache_fails():
    """RED: the REAL +-$5 narrow cache must NOT cover the 2025-04-04 call-side move."""
    cmin, cmax = _cache_band(_NARROW_CACHE, _EVENT_DAY)
    assert (cmin, cmax) == (497.0, 505.0), (cmin, cmax)
    # Day low INSIDE the band (so we isolate the high-side truncation the cache caused).
    res = strike_band_covers_range(
        day_low=cmin, day_high=_DAY_HIGH, atm=_ATM,
        cache_min_strike=cmin, cache_max_strike=cmax,
    )
    assert res.covered is False, res.reason
    assert res.dropped_side == "high", res.reason
    assert res.slack < 0, res.reason  # exited by ~$18.86
    print("RED narrow cache:", res.reason)


def test_strike_band_covers_range_GREEN_wide_cache_covers():
    """GREEN: the REAL +-$18 wide cache must reach the same 2025-04-04 call-side move."""
    cmin, cmax = _cache_band(_WIDE_CACHE, _EVENT_DAY)
    assert (cmin, cmax) == (505.0, 540.0), (cmin, cmax)
    # Same call-side excursion; low pinned at the wide band's floor to isolate the high side.
    res = strike_band_covers_range(
        day_low=cmin, day_high=_DAY_HIGH, atm=_ATM,
        cache_min_strike=cmin, cache_max_strike=cmax,
    )
    assert res.covered is True, res.reason
    assert res.dropped_side is None, res.reason
    assert res.slack >= 0, res.reason  # ~$14.14 of headroom above the high
    print("GREEN wide cache:", res.reason)


def test_strike_band_covers_range_both_sides_exit():
    res = strike_band_covers_range(
        day_low=490.0, day_high=560.0, atm=513.0,
        cache_min_strike=505.0, cache_max_strike=540.0,
    )
    assert res.covered is False
    assert res.dropped_side == "both"


def test_strike_band_covers_range_low_side_exit():
    res = strike_band_covers_range(
        day_low=500.0, day_high=520.0, atm=513.0,
        cache_min_strike=505.0, cache_max_strike=540.0,
    )
    assert res.covered is False
    assert res.dropped_side == "low"
    assert res.slack == pytest.approx(-5.0)


def test_strike_band_covers_range_exact_edges_covered():
    res = strike_band_covers_range(
        day_low=505.0, day_high=540.0, atm=520.0,
        cache_min_strike=505.0, cache_max_strike=540.0,
    )
    assert res.covered is True
    assert res.slack == pytest.approx(0.0)


def test_strike_band_covers_range_bad_inputs_raise():
    with pytest.raises(ValueError):
        strike_band_covers_range(530.0, 500.0, 513.0, 505.0, 540.0)  # low > high
    with pytest.raises(ValueError):
        strike_band_covers_range(500.0, 530.0, 513.0, 540.0, 505.0)  # cmin > cmax


def test_dropped_day_fraction_aggregates():
    days = [
        strike_band_covers_range(505, 540, 520, 505, 540),   # covered
        strike_band_covers_range(497, 526, 513, 497, 507),   # high drop
        strike_band_covers_range(490, 520, 513, 505, 540),   # low drop
        strike_band_covers_range(490, 560, 513, 505, 540),   # both
    ]
    agg = dropped_day_fraction(days)
    assert agg["n_days"] == 4
    assert agg["n_dropped"] == 3
    assert agg["dropped_fraction"] == pytest.approx(0.75)
    assert agg["dropped_sides"] == {"low": 1, "high": 1, "both": 1}
