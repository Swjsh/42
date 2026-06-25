"""Reusable research-integrity guards — graduated session lessons (L172 + L177/L182).

This is the SINGLE SOURCE OF TRUTH for two cross-checks that recurred often enough to
graduate from inline copies into a library every sim/validator imports:

  beats_random_filter_null  (L172)  — a CONDITIONING FILTER that keeps a subset of a base
        P&L sample must beat a random filter dropping the SAME fraction. This is the bar the
        W1 IV-skew confirmer FAILED (kept $45.66 vs null mean $48.30, one-sided p=0.76), the
        VIX-level gate FAILED (p=0.355), and touch-and-go was selective-only. The decisive
        question for any "keep X, drop Y" rule: does the kept subset sit in the RIGHT TAIL of
        what a coin-flip drop of the same size yields, or does the filter just shrink n?

  strike_band_covers_range  (L177/L182) — a SHORT-PREMIUM / defined-risk / credit sim must
        verify the cached strike band reaches the day's realized [low, high]. A fixed narrow
        band silently TRUNCATES the loss tail on big-move days (drops the loser strikes as
        ``missing_cache``), manufacturing a phantom edge. This is the cache-tail-bias that
        made the event condor look +$32/tr on a +-$5 cache when the real tail (+-$18 wide
        cache) was -$751 on the same day. A fill-rate-SYMMETRIC drop protects the SELECTION
        signal but NOT the absolute magnitude — and the cap + the null both judge magnitude.

CONSOLIDATION (don't duplicate). The L172 null logic previously lived inline in
``backtest/autoresearch/_iv_skew_confirmer.py`` (``random_filter_null`` + ``null_p_for``)
and is sibling to the random-ENTRY null in ``backtest/autoresearch/null_baseline.py``
(distinct: that one re-runs entries at random BARS; this one drops trades at random from a
FIXED sample). New filters should import :func:`beats_random_filter_null` from HERE so the
benchmark is one implementation. ``cap_admission`` is a separate concern and is NOT touched.

Pure functions, no side effects, no I/O, no third-party deps beyond numpy. Deterministic
(fixed-seed private RNG). Guarded by ``backtest/tests/test_research_guards.py``.

Doctrine cross-refs: CLAUDE.md C3/L58 (a structural-gate pass a null reproduces is an
artifact — beat the null MAX), C1/L182 (real fills only; a narrow band truncates the tail),
C4 (a positive average is NOT automatically a per-trade edge), C30/L148/L176 (audit what the
cache actually prices/reaches before trusting a tail).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

# Matches the L172 reference (``_iv_skew_confirmer.NULL_SEEDS``). 2000 random draws give a
# stable p-value at the 0.05 bar without being expensive.
DEFAULT_SEEDS = 2000
DEFAULT_SEED_BASE = 1234
SIG_LEVEL = 0.05


# ─────────────────────────────────────────────────────────────────────────────
# GUARD 1 — beats_random_filter_null  (L172)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FilterNullResult:
    """Immutable verdict of the L172 random-filter null.

    ``passed`` is True iff the kept subset's mean sits in the right tail of the random-drop
    distribution at one-sided p < ``sig_level`` — equivalently ``filt_mean > null_p95``.
    ``applicable`` is False (and ``passed`` False) for a DEGENERATE point-null where the
    random pool size equals the kept size (drops 0 or all): there is no distribution to
    beat, so the guard refuses to bless it (the event-long-vega harness hit this).
    """

    passed: bool
    applicable: bool
    p_value: Optional[float]
    filt_mean: Optional[float]
    null_mean: Optional[float]
    null_p95: Optional[float]
    n_total: int
    n_keep: int
    drop_fraction: float
    seeds: int
    reason: str


def beats_random_filter_null(
    base_pnl: Sequence[float],
    kept_mask: Sequence[bool],
    *,
    n_seeds: int = DEFAULT_SEEDS,
    seed_base: int = DEFAULT_SEED_BASE,
    sig_level: float = SIG_LEVEL,
) -> FilterNullResult:
    """Does a CONDITIONING FILTER select better than a coin-flip drop of the same size?

    The filter keeps ``kept_mask`` of ``base_pnl`` (the realized per-trade P&L of the
    UNFILTERED signal set). A real filter's kept-subset mean must sit in the right tail of
    the distribution of means from random subsets of the SAME size (``passed`` iff
    ``filt_mean > null_p95``, i.e. one-sided p < ``sig_level``). If it does not, the filter
    is just shrinking n without real selection (C3/L58, L172).

    Args:
        base_pnl: per-trade P&L of the UNFILTERED signal universe (the random pool).
        kept_mask: boolean mask, same length as ``base_pnl``; True = the filter KEPT it.
        n_seeds: number of random subsets drawn (default 2000, matches the L172 reference).
        seed_base: seed for the private RNG so the null is reproducible across runs/processes.
        sig_level: one-sided significance bar (default 0.05).

    Returns:
        :class:`FilterNullResult`. ``applicable`` is False for the degenerate point-null
        (kept count == 0 or == N): no random distribution exists, so the guard does not
        bless it (``passed`` False).

    Raises:
        ValueError: if ``base_pnl`` and ``kept_mask`` differ in length, or ``base_pnl`` empty.
    """
    pnl = np.asarray(list(base_pnl), dtype=float)
    mask = np.asarray(list(kept_mask), dtype=bool)
    if pnl.shape[0] != mask.shape[0]:
        raise ValueError(
            f"base_pnl ({pnl.shape[0]}) and kept_mask ({mask.shape[0]}) length mismatch"
        )
    n_total = int(pnl.shape[0])
    if n_total == 0:
        raise ValueError("base_pnl is empty — no sample to filter")

    n_keep = int(mask.sum())
    drop_fraction = round(1.0 - n_keep / n_total, 4) if n_total else 0.0

    # DEGENERATE point-null: keeping 0 or all gives no distribution of alternatives to beat.
    # Flag (don't bless) — this is the event-long-vega trap where pool == sample size.
    if n_keep <= 0 or n_keep >= n_total:
        return FilterNullResult(
            passed=False,
            applicable=False,
            p_value=None,
            filt_mean=(round(float(pnl[mask].mean()), 4) if n_keep > 0 else None),
            null_mean=None,
            null_p95=None,
            n_total=n_total,
            n_keep=n_keep,
            drop_fraction=drop_fraction,
            seeds=n_seeds,
            reason=(
                "DEGENERATE point-null: filter kept 0 or all trades "
                f"(n_keep={n_keep}, n_total={n_total}) — no random-drop distribution to "
                "beat; guard NOT applicable (does not bless)"
            ),
        )

    filt_mean = float(pnl[mask].mean())

    rng = random.Random(seed_base)
    idx_all = list(range(n_total))
    means = np.empty(n_seeds, dtype=float)
    for s in range(n_seeds):
        pick = rng.sample(idx_all, n_keep)
        means[s] = pnl[pick].mean()

    null_mean = float(means.mean())
    null_p95 = float(np.percentile(means, 95))
    # One-sided p: fraction of random subsets matching or beating the observed kept mean.
    p_value = float((means >= filt_mean).mean())
    passed = bool(p_value < sig_level)

    reason = (
        f"filt_mean=${round(filt_mean, 2)} vs null_mean=${round(null_mean, 2)} / "
        f"null_p95=${round(null_p95, 2)} -> one-sided p={round(p_value, 4)} "
        f"({'BEATS' if passed else 'FAILS'} random-filter null @ p<{sig_level}; "
        f"kept {n_keep}/{n_total}, drop {round(drop_fraction * 100, 1)}%)"
    )

    return FilterNullResult(
        passed=passed,
        applicable=True,
        p_value=round(p_value, 4),
        filt_mean=round(filt_mean, 4),
        null_mean=round(null_mean, 4),
        null_p95=round(null_p95, 4),
        n_total=n_total,
        n_keep=n_keep,
        drop_fraction=drop_fraction,
        seeds=n_seeds,
        reason=reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GUARD 2 — strike_band_covers_range  (L177 / L182, cache-tail-bias)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class StrikeBandResult:
    """Immutable verdict of the cache-tail-bias band-coverage check.

    ``covered`` is True iff the cached strike band spans the day's realized [low, high]
    (so the loss tail of a short-premium / defined-risk structure is priceable, not
    truncated). ``dropped_side`` names which side(s) the realized move exited the band on
    (``"low"`` / ``"high"`` / ``"both"`` / ``None``). ``slack`` is the worst-side margin:
    >= 0 = covered with that much room; < 0 = the move exited by that distance.
    """

    covered: bool
    dropped_side: Optional[str]
    slack: float
    day_low: float
    day_high: float
    atm: float
    cache_min_strike: float
    cache_max_strike: float
    reason: str


def strike_band_covers_range(
    day_low: float,
    day_high: float,
    atm: float,
    cache_min_strike: float,
    cache_max_strike: float,
) -> StrikeBandResult:
    """Does the cached strike band reach the day's realized [low, high]?

    A short-premium / credit / defined-risk sim that prices off a FIXED strike-band cache
    must verify the band covers the realized intraday extreme. If the underlying travelled
    PAST the cached band, the adverse strikes have no CSV and the day is silently dropped
    as ``missing_cache`` — truncating the loss tail and biasing magnitude upward (L177/L182,
    the event condor +-$5-cache phantom +$32/tr). Return ``covered=False`` so the caller
    SKIPS+counts the day rather than pricing a truncated tail.

    Args:
        day_low: realized intraday low of the underlying (over the relevant hold window).
        day_high: realized intraday high of the underlying.
        atm: at-the-money reference (entry spot / ATM strike) — disclosure only.
        cache_min_strike: lowest strike present in the day's cache.
        cache_max_strike: highest strike present in the day's cache.

    Returns:
        :class:`StrikeBandResult`. ``covered`` True iff
        ``cache_min_strike <= day_low and day_high <= cache_max_strike``.

    Raises:
        ValueError: if ``day_low > day_high`` or ``cache_min_strike > cache_max_strike``.
    """
    if day_low > day_high:
        raise ValueError(f"day_low ({day_low}) > day_high ({day_high})")
    if cache_min_strike > cache_max_strike:
        raise ValueError(
            f"cache_min_strike ({cache_min_strike}) > cache_max_strike ({cache_max_strike})"
        )

    low_margin = float(day_low - cache_min_strike)   # >=0 = low is inside the band
    high_margin = float(cache_max_strike - day_high)  # >=0 = high is inside the band
    low_ok = low_margin >= 0
    high_ok = high_margin >= 0
    covered = bool(low_ok and high_ok)

    if covered:
        dropped_side: Optional[str] = None
    elif not low_ok and not high_ok:
        dropped_side = "both"
    elif not low_ok:
        dropped_side = "low"
    else:
        dropped_side = "high"

    slack = round(min(low_margin, high_margin), 4)

    if covered:
        reason = (
            f"band [{cache_min_strike}, {cache_max_strike}] covers realized "
            f"[{day_low}, {day_high}] (atm={atm}); slack=${slack} — loss tail priceable"
        )
    else:
        reason = (
            f"CACHE-TAIL-BIAS: realized [{day_low}, {day_high}] exits band "
            f"[{cache_min_strike}, {cache_max_strike}] on the {dropped_side} side "
            f"(slack=${slack}); the loss tail would be TRUNCATED (missing_cache) — "
            f"SKIP this day, do not price a truncated tail (L177/L182)"
        )

    return StrikeBandResult(
        covered=covered,
        dropped_side=dropped_side,
        slack=slack,
        day_low=float(day_low),
        day_high=float(day_high),
        atm=float(atm),
        cache_min_strike=float(cache_min_strike),
        cache_max_strike=float(cache_max_strike),
        reason=reason,
    )


def dropped_day_fraction(day_results: Sequence[StrikeBandResult]) -> dict:
    """Aggregate a sim's day set: what fraction of days had their loss tail truncated?

    A non-trivial dropped fraction means the sim's expectancy/worst-day is magnitude-biased
    (the violent-move days — the loser days for a short-premium structure — are exactly the
    ones the narrow band drops). Use this to disclose how much of the day set was priceable
    before trusting an aggregate (L177/L182).

    Args:
        day_results: per-day :class:`StrikeBandResult` objects.

    Returns:
        dict with ``n_days``, ``n_dropped``, ``dropped_fraction`` and ``dropped_sides``
        (count of low/high/both drops).
    """
    n_days = len(day_results)
    dropped = [r for r in day_results if not r.covered]
    sides = {"low": 0, "high": 0, "both": 0}
    for r in dropped:
        if r.dropped_side in sides:
            sides[r.dropped_side] += 1
    return {
        "n_days": n_days,
        "n_dropped": len(dropped),
        "dropped_fraction": round(len(dropped) / n_days, 4) if n_days else 0.0,
        "dropped_sides": sides,
    }
