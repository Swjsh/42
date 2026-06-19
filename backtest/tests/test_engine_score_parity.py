"""Parity: engine.score == filters.evaluate_* (Phase 1 of the shared library).

Spec: ``docs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 1 ... Parity gate".

The shared decision library's first phase relocates scoring behind a stable
``backtest/lib/engine/score.py`` interface that THINLY WRAPS the existing
``filters.evaluate_bearish_setup`` / ``filters.evaluate_bullish_setup``. This is
the "assert-agree before replace" discipline from the ``risk_gate`` precedent:
before the orchestrator's call site is allowed to depend on ``engine.score``, we
prove field-for-field that the wrapper returns byte-identical results to calling
``filters`` directly — on a corpus of representative + boundary ``BarContext``
fixtures (the same builders ``crypto/validators/v25_filter_gates.py`` uses to
construct passing + each-filter-broken contexts).

If any of these fail, the extraction is NOT faithful and Phase 1 is not shipped.

Run:  cd backtest && python -m pytest tests/test_engine_score_parity.py -q
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import engine  # noqa: E402  (the package under test)
from lib.engine import ScoreResult, score_bar, score_bear, score_bull  # noqa: E402
from lib.filters import (  # noqa: E402
    BarContext,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)
from lib.ribbon import RibbonState  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures — mirror crypto/validators/v25_filter_gates.py builders so the parity
# corpus covers a clean PASS plus each cascade-breaking variation, with NO
# dependency on the master CSV (these tests always run).
# --------------------------------------------------------------------------- #


def _bear_ribbon(spread_cents: float = 50.0) -> RibbonState:
    return RibbonState(fast=539.0, pivot=540.0, slow=541.0, spread_cents=spread_cents, stack="BEAR")


def _bull_ribbon(spread_cents: float = 50.0) -> RibbonState:
    return RibbonState(fast=541.0, pivot=540.0, slow=539.0, spread_cents=spread_cents, stack="BULL")


def _make_bar(open_=540.5, high=541.5, low=539.5, close=540.3, volume=900_000) -> pd.Series:
    return pd.Series({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


def _prior_bars() -> pd.DataFrame:
    # 30 calm bars: no volume-divergence, modest range. bar_idx=4 used below.
    return pd.DataFrame(
        [{"open": 540.0, "high": 540.4, "low": 539.6, "close": 540.0, "volume": 800_000}
         for _ in range(30)]
    )


def _bear_ctx(
    time_str: str = "10:00",
    vix_now: float = 17.5,
    vix_prior: float = 17.3,
    ribbon: RibbonState | None = None,
    bar: pd.Series | None = None,
    vol_baseline: float = 1_000_000.0,
    levels_active: list | None = None,
) -> BarContext:
    ts = dt.datetime.fromisoformat(f"2026-05-20 {time_str}:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-4))
    )
    return BarContext(
        bar_idx=4,
        timestamp_et=ts,
        bar=_make_bar() if bar is None else bar,
        prior_bars=_prior_bars(),
        ribbon_now=_bear_ribbon() if ribbon is None else ribbon,
        ribbon_history=[_bear_ribbon() if ribbon is None else ribbon],
        vix_now=vix_now,
        vix_prior=vix_prior,
        vol_baseline_20=vol_baseline,
        range_baseline_20=1.0,
        levels_active=[540.8] if levels_active is None else levels_active,
        multi_day_levels=[],
        htf_15m_stack="BEAR",
        level_states={},
    )


def _bull_ctx(
    time_str: str = "10:00",
    vix_now: float = 17.1,
    vix_prior: float = 17.3,
    ribbon: RibbonState | None = None,
    bar: pd.Series | None = None,
    vol_baseline: float = 1_000_000.0,
    levels_active: list | None = None,
) -> BarContext:
    ts = dt.datetime.fromisoformat(f"2026-05-20 {time_str}:00").replace(
        tzinfo=dt.timezone(dt.timedelta(hours=-4))
    )
    green = _make_bar(open_=540.0, high=541.5, low=539.8, close=541.2, volume=750_000)
    return BarContext(
        bar_idx=4,
        timestamp_et=ts,
        bar=green if bar is None else bar,
        prior_bars=_prior_bars(),
        ribbon_now=_bull_ribbon() if ribbon is None else ribbon,
        ribbon_history=[_bull_ribbon() if ribbon is None else ribbon],
        vix_now=vix_now,
        vix_prior=vix_prior,
        vol_baseline_20=vol_baseline,
        range_baseline_20=1.0,
        levels_active=[540.5] if levels_active is None else levels_active,
        multi_day_levels=[],
        htf_15m_stack="BULL",
        level_states={},
    )


# A representative corpus: clean pass + each notable cascade variation + the
# afternoon/boundary contexts. Each entry is (label, ctx, kwargs-for-evaluate).
_BEAR_CASES = [
    ("clean_pass", _bear_ctx(), {}),
    ("before_0935", _bear_ctx(time_str="09:30"), {}),
    ("ribbon_bull_not_bear", _bear_ctx(ribbon=_bull_ribbon()), {}),
    ("spread_too_tight", _bear_ctx(ribbon=_bear_ribbon(29)), {}),
    ("vix_falling", _bear_ctx(vix_now=17.25, vix_prior=17.50), {}),
    ("vix_at_boundary_1730", _bear_ctx(vix_now=17.30, vix_prior=16.90), {}),
    ("vix_just_above_1731", _bear_ctx(vix_now=17.31, vix_prior=16.90), {}),
    ("volume_not_elevated", _bear_ctx(vol_baseline=100_000_000.0), {}),
    ("no_level_tied_trigger", _bear_ctx(levels_active=[200.0]), {}),
    ("disable_f7_f8", _bear_ctx(), {"disable_filters": [7, 8]}),
    ("min_triggers_2", _bear_ctx(), {"min_triggers": 2}),
    ("vix_soft_mode", _bear_ctx(vix_now=17.25, vix_prior=17.50), {"vix_soft_mode": True}),
    ("no_trade_before_1000", _bear_ctx(time_str="09:45"), {"no_trade_before": dt.time(10, 0)}),
]

_BULL_CASES = [
    ("clean_pass", _bull_ctx(), {}),
    ("before_0935", _bull_ctx(time_str="09:30"), {}),
    ("ribbon_bear_not_bull", _bull_ctx(ribbon=_bear_ribbon()), {}),
    ("spread_too_tight", _bull_ctx(ribbon=_bull_ribbon(29)), {}),
    ("vix_rising_above", _bull_ctx(vix_now=17.40, vix_prior=17.10), {}),
    ("vix_hard_cap", _bull_ctx(vix_now=18.0, vix_prior=18.3), {}),
    ("no_level_tied_trigger", _bull_ctx(levels_active=[200.0]), {}),
    ("disable_f7", _bull_ctx(), {"disable_filters": [7]}),
    ("min_triggers_2", _bull_ctx(), {"min_triggers": 2}),
    ("no_trade_window_afternoon",
     _bull_ctx(time_str="14:30"),
     {"no_trade_window": (dt.time(14, 0), dt.time(15, 0))}),
]


def _assert_setup_equal(a, b, label: str) -> None:
    """Field-for-field equality of two SetupResult / BullishSetupResult."""
    assert a.passed == b.passed, f"[{label}] passed differs: {a.passed} != {b.passed}"
    assert a.blockers == b.blockers, f"[{label}] blockers differ: {a.blockers} != {b.blockers}"
    assert a.triggers_fired == b.triggers_fired, (
        f"[{label}] triggers_fired differ: {a.triggers_fired} != {b.triggers_fired}"
    )
    # bear vs bull use different score / level field names; compare whichever exist.
    if hasattr(a, "bear_score"):
        assert a.bear_score == b.bear_score, f"[{label}] bear_score differs"
        assert a.rejection_level == b.rejection_level, f"[{label}] rejection_level differs"
    if hasattr(a, "bull_score"):
        assert a.bull_score == b.bull_score, f"[{label}] bull_score differs"
        assert a.reclaim_level == b.reclaim_level, f"[{label}] reclaim_level differs"


# --------------------------------------------------------------------------- #
# 1. score_bear / score_bull are byte-identical pass-throughs
# --------------------------------------------------------------------------- #


def test_score_bear_matches_filters_across_corpus() -> None:
    for label, ctx, kw in _BEAR_CASES:
        via_engine = score_bear(ctx, **kw)
        via_filters = evaluate_bearish_setup(ctx, **kw)
        _assert_setup_equal(via_engine, via_filters, f"bear/{label}")


def test_score_bull_matches_filters_across_corpus() -> None:
    for label, ctx, kw in _BULL_CASES:
        via_engine = score_bull(ctx, **kw)
        via_filters = evaluate_bullish_setup(ctx, **kw)
        _assert_setup_equal(via_engine, via_filters, f"bull/{label}")


# --------------------------------------------------------------------------- #
# 2. score_bar bundles both sides and agrees with direct calls
# --------------------------------------------------------------------------- #


def test_score_bar_bundles_both_sides() -> None:
    """score_bar(ctx) must carry the SAME bear+bull results as direct evaluate_*,
    and expose matching headline scalars."""
    for label, ctx, _ in _BEAR_CASES:
        sr = score_bar(ctx)
        assert isinstance(sr, ScoreResult)
        _assert_setup_equal(sr.bear, evaluate_bearish_setup(ctx), f"score_bar.bear/{label}")
        assert sr.bull is not None, "bullish enabled by default"
        _assert_setup_equal(sr.bull, evaluate_bullish_setup(ctx), f"score_bar.bull/{label}")
        # headline scalars mirror the underlying results
        assert sr.bear_score == sr.bear.bear_score == evaluate_bearish_setup(ctx).bear_score
        assert sr.bull_score == sr.bull.bull_score
        assert sr.bear_blockers == sr.bear.blockers
        assert sr.bull_blockers == sr.bull.blockers


def test_score_bar_forwards_kwargs_to_each_side() -> None:
    """bear_kwargs / bull_kwargs must reach the underlying evaluators unchanged."""
    ctx = _bear_ctx(vix_now=17.25, vix_prior=17.50)  # bear would block on F8...
    sr = score_bar(
        ctx,
        bear_kwargs={"vix_soft_mode": True},     # ...unless soft-mode is forwarded
        bull_kwargs={"disable_filters": [7]},
    )
    _assert_setup_equal(
        sr.bear, evaluate_bearish_setup(ctx, vix_soft_mode=True), "fwd.bear"
    )
    _assert_setup_equal(
        sr.bull, evaluate_bullish_setup(ctx, disable_filters=[7]), "fwd.bull"
    )


def test_score_bar_enable_bullish_false_skips_bull() -> None:
    """enable_bullish=False mirrors the orchestrator skipping evaluate_bullish_setup."""
    sr = score_bar(_bear_ctx(), enable_bullish=False)
    assert sr.bull is None
    assert sr.bull_score is None
    assert sr.bull_blockers is None
    # bear side still scored identically
    _assert_setup_equal(sr.bear, evaluate_bearish_setup(_bear_ctx()), "no_bull.bear")


# --------------------------------------------------------------------------- #
# 3. package surface + immutability
# --------------------------------------------------------------------------- #


def test_package_reexports_match_module() -> None:
    """The engine package re-exports the same callables score.py defines."""
    assert engine.score_bar is score_bar
    assert engine.score_bear is score_bear
    assert engine.score_bull is score_bull
    assert engine.ScoreResult is ScoreResult


def test_score_result_is_frozen() -> None:
    """ScoreResult is immutable (frozen dataclass), like RiskDecision."""
    sr = score_bar(_bear_ctx())
    try:
        sr.bear_score = 999  # type: ignore[misc]
    except Exception as exc:  # FrozenInstanceError is a dataclasses subclass
        assert "frozen" in type(exc).__name__.lower() or "frozen" in str(exc).lower()
    else:
        raise AssertionError("ScoreResult must be frozen (mutation should raise)")
