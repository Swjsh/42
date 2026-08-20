"""Tests for multi/lib/filters.py -- the symbol-parameterized fork of backtest/lib/filters.py's
ribbon_ride 0-11 bull/bear scoring engine (J directive 2026-08-19).

THE MOST IMPORTANT TEST HERE is test_scale_invariance_bear_score_identical_across_price_scales
(and its bull mirror): it constructs the SAME chart pattern at two price scales and asserts the
score is IDENTICAL. This is the test that proves the source engine's dollar-denominated
tolerances were actually converted to symbol-relative ones -- it is designed to RED the moment
any raw dollar constant survives anywhere in the scoring path (see the RED-proof note on each
test for exactly how to break it).

Everything else here is either a structural guard (no import of the source engine, no literal
"SPY" in code) or a vary-and-assert test proving one specific converted tunable actually changes
behavior when varied (not a dead/ignored parameter).
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi.lib import filters as mf  # noqa: E402
from multi.lib.filters import (  # noqa: E402
    BarContext,
    LevelState,
    RibbonState,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)

FILTERS_PATH = REPO_ROOT / "multi" / "lib" / "filters.py"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL GUARDS
# ─────────────────────────────────────────────────────────────────────────────

def test_filters_file_exists_and_is_a_fork_not_a_stub():
    assert FILTERS_PATH.is_file()
    assert FILTERS_PATH.stat().st_size > 10_000, "suspiciously small for a full scoring-engine fork"


def test_no_import_of_the_source_spy_lane_engine():
    """No import of backtest/lib/filters.py, backtest/lib/ribbon.py,
    backtest/lib/structure_shift.py, or automation/state/fleet/* -- this is a FORK, not an
    import, by explicit task requirement.

    RED-PROOF: add `from backtest.lib import filters as _spy_filters` (or `from lib import
    ribbon`) anywhere in multi/lib/filters.py and this test fails immediately.
    """
    tree = ast.parse(FILTERS_PATH.read_text(encoding="utf-8"))
    banned_module_fragments = ("backtest", "fleet")
    banned_bare_modules = {"lib", "ribbon", "structure_shift"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(frag in mod for frag in banned_module_fragments) or mod in banned_bare_modules \
                    or mod.startswith("lib."):
                offenders.append(("from", mod, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(frag in alias.name for frag in banned_module_fragments) \
                        or alias.name in banned_bare_modules or alias.name.startswith("lib."):
                    offenders.append(("import", alias.name, node.lineno))
    assert not offenders, f"multi/lib/filters.py imports the source engine: {offenders}"


def _docstring_constant_ids(tree: ast.Module) -> set[int]:
    """id()s of ast.Constant nodes that are module/class/function DOCSTRINGS -- these are
    documentation (explaining the SPY->symbol-relative conversion, which the task itself
    requires: "DOCUMENT the conversion in a comment naming the original SPY value"), not
    code. Comments (# ...) are not AST nodes at all and are excluded automatically."""
    doc_ids: set[int] = set()
    candidates = [tree] + [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for node in candidates:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr):
            val = body[0].value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                doc_ids.add(id(val))
    return doc_ids


def test_no_literal_spy_in_code():
    """No literal "SPY" anywhere in multi/lib/filters.py's actual CODE -- string literals used
    by logic, and identifier names, must not spell out the source symbol (J: "nothing should
    say hard coded for spy"). Comments and docstrings are explicitly exempt: the task requires
    documenting each conversion "naming the original SPY value," which cannot be done without
    the word appearing in prose -- see multi/lib/filters.py's module docstring for exactly
    that documentation.

    RED-PROOF: rename `REFERENCE_PRICE_ANCHOR_USD` back to `SPY_REFERENCE_PRICE` (or add
    `if ctx.symbol == "SPY": ...` anywhere) and this test fails.
    """
    src = FILTERS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc_ids = _docstring_constant_ids(tree)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in doc_ids:
                continue
            if "SPY" in node.value:
                offenders.append(("string", node.lineno, node.value))
        elif isinstance(node, ast.Name) and "SPY" in node.id:
            offenders.append(("name", node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and "SPY" in node.attr:
            offenders.append(("attr", node.lineno, node.attr))
    assert not offenders, f"literal 'SPY' found in non-docstring code: {offenders}"


# ─────────────────────────────────────────────────────────────────────────────
# SCALE-INVARIANCE — the single most important test in this file.
# ─────────────────────────────────────────────────────────────────────────────

def _build_scaled_bear_bars(scale: float, n_warmup: int = 49) -> tuple[pd.DataFrame, float]:
    """A bear-drift warmup (49 bars) + a level-rejection trigger bar (1 bar), expressed as
    MULTIPLIERS of `scale` so two calls with different `scale` produce PROPORTIONALLY
    IDENTICAL bars -- same relative move sizes, same relative wick size, same relative
    distance-to-level -- differing only by the overall price level. Volume is NOT scaled
    (share counts are real-world price-independent quantities)."""
    rows = []
    mult = 1.05
    step = 0.0012
    for _ in range(n_warmup):
        o, c = mult, mult - step
        h, l = max(o, c) + 0.00015, min(o, c) - 0.00015
        rows.append({"open": o * scale, "high": h * scale, "low": l * scale,
                     "close": c * scale, "volume": 1_000_000.0})
        mult = c
    prior_close_mult = mult
    level_mult = prior_close_mult + 0.006
    o = prior_close_mult
    close_mult = prior_close_mult - 0.0030
    high_mult = level_mult + 0.0020
    low_mult = min(o, close_mult) - 0.0006
    rows.append({"open": o * scale, "high": high_mult * scale, "low": low_mult * scale,
                 "close": close_mult * scale, "volume": 2_000_000.0})
    return pd.DataFrame(rows), level_mult * scale


def _build_scaled_bull_bars(scale: float, n_warmup: int = 49) -> tuple[pd.DataFrame, float]:
    """Bull mirror of _build_scaled_bear_bars: a rising drift + a level-reclaim trigger bar."""
    rows = []
    mult = 0.95
    step = 0.0012
    for _ in range(n_warmup):
        o, c = mult, mult + step
        h, l = max(o, c) + 0.00015, min(o, c) - 0.00015
        rows.append({"open": o * scale, "high": h * scale, "low": l * scale,
                     "close": c * scale, "volume": 1_000_000.0})
        mult = c
    prior_close_mult = mult
    level_mult = prior_close_mult - 0.006
    o = prior_close_mult
    close_mult = prior_close_mult + 0.0030
    low_mult = level_mult - 0.0020
    high_mult = max(o, close_mult) + 0.0006
    rows.append({"open": o * scale, "high": high_mult * scale, "low": low_mult * scale,
                 "close": close_mult * scale, "volume": 2_000_000.0})
    return pd.DataFrame(rows), level_mult * scale


def _scaled_ctx(bars: pd.DataFrame, level: float, scale: float) -> BarContext:
    idx = len(bars) - 1
    ribbon_df = mf.compute_ribbon(bars["close"])
    ribbon_now = mf.ribbon_at(ribbon_df, idx)
    assert ribbon_now is not None, f"ribbon failed to warm up at scale={scale}"
    lookback = mf.RIBBON_FLIP_LOOKBACK_BARS + 1
    ribbon_history = [mf.ribbon_at(ribbon_df, i) for i in range(idx - lookback + 1, idx + 1)]
    atr_series = mf.atr_wilder(bars, mf.ATR_LENGTH_DEFAULT)
    atr_14 = float(atr_series[idx])
    assert atr_14 == atr_14 and atr_14 > 0, f"ATR failed to warm up at scale={scale}"
    return BarContext(
        bar_idx=idx, timestamp_et=dt.datetime(2026, 8, 19, 11, 0),
        bar=bars.iloc[idx], prior_bars=bars, ribbon_now=ribbon_now, ribbon_history=ribbon_history,
        vix_now=None, vix_prior=None,
        vol_baseline_20=mf.vol_baseline_20bar(bars, idx),
        range_baseline_20=mf.range_baseline_20bar(bars, idx),
        atr_14=atr_14, symbol=f"SCALE_{scale}",
        levels_active=[level], multi_day_levels=[], htf_15m_stack=None,
    )


def test_scale_invariance_bear_score_identical_across_price_scales():
    """THE critical test: a $40-stock-scale chart and a $700-ETF-scale chart, proportionally
    identical, must score IDENTICALLY -- proving the SPY-dollar coupling is gone.

    RED-PROOF (performed and captured in the task report): temporarily hardcode
    `confluence_tolerance`/`wick_min_dollars`/`wick_close_tolerance` to ignore `atr_14` and
    return a fixed dollar value (e.g. 0.30/0.15/0.10, the ORIGINAL SPY constants) and this
    test fails -- the $40-scale run's tolerances become enormous relative to its own prices
    while the $700-scale run's stay tiny, changing which triggers fire and therefore the score.
    """
    bars_low, level_low = _build_scaled_bear_bars(40.0)
    bars_high, level_high = _build_scaled_bear_bars(700.0)
    ctx_low = _scaled_ctx(bars_low, level_low, 40.0)
    ctx_high = _scaled_ctx(bars_high, level_high, 700.0)

    res_low = evaluate_bearish_setup(ctx_low)
    res_high = evaluate_bearish_setup(ctx_high)

    assert res_low.bear_score == res_high.bear_score, (res_low.bear_score, res_high.bear_score)
    assert res_low.passed == res_high.passed
    assert res_low.blockers == res_high.blockers
    assert set(res_low.triggers_fired) == set(res_high.triggers_fired)
    # sanity: the pattern must actually PRODUCE a signal, not trivially agree on "nothing fired"
    assert "level_rejection" in res_low.triggers_fired
    assert res_low.passed is True


def test_scale_invariance_bull_score_identical_across_price_scales():
    """Bull mirror of the critical scale-invariance test."""
    bars_low, level_low = _build_scaled_bull_bars(40.0)
    bars_high, level_high = _build_scaled_bull_bars(700.0)
    ctx_low = _scaled_ctx(bars_low, level_low, 40.0)
    ctx_high = _scaled_ctx(bars_high, level_high, 700.0)

    res_low = evaluate_bullish_setup(ctx_low)
    res_high = evaluate_bullish_setup(ctx_high)

    assert res_low.bull_score == res_high.bull_score, (res_low.bull_score, res_high.bull_score)
    assert res_low.passed == res_high.passed
    assert res_low.blockers == res_high.blockers
    assert set(res_low.triggers_fired) == set(res_high.triggers_fired)
    assert "level_reclaim" in res_low.triggers_fired
    assert res_low.passed is True


# ─────────────────────────────────────────────────────────────────────────────
# _ctx HELPER for isolated filter-logic tests (bypasses ribbon/ATR computation so each test
# varies exactly one thing).
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(
    *, symbol: str = "TEST", price: float = 100.0, atr: float = 1.0, stack: str = "BEAR",
    spread_pct: float = 0.002, vix_now=None, vix_prior=None,
    levels_active=None, multi_day_levels=None, htf_15m_stack=None, level_states=None,
    bar_overrides: dict | None = None, bar_idx: int = 30, n_bars: int = 40,
) -> BarContext:
    rows = [{"open": price, "high": price + 0.01, "low": price - 0.01, "close": price,
             "volume": 1_000_000.0} for _ in range(n_bars)]
    df = pd.DataFrame(rows)
    if bar_overrides:
        for k, v in bar_overrides.items():
            df.loc[bar_idx, k] = v
    ribbon = RibbonState(
        fast=price, pivot=price, slow=price,
        spread_cents=spread_pct * price * 100.0, spread_pct=spread_pct, stack=stack,
    )
    return BarContext(
        bar_idx=bar_idx, timestamp_et=dt.datetime(2026, 8, 19, 11, 0),
        bar=df.iloc[bar_idx], prior_bars=df, ribbon_now=ribbon, ribbon_history=[ribbon] * 4,
        vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=1_000_000.0, range_baseline_20=price * 0.002,
        atr_14=atr, symbol=symbol,
        levels_active=levels_active or [], multi_day_levels=multi_day_levels or [],
        htf_15m_stack=htf_15m_stack, level_states=level_states or {},
    )


_TRIGGER_BAR_BEAR = {"open": 100.0, "high": 100.05, "low": 99.90, "close": 99.95, "volume": 2_000_000.0}
_TRIGGER_BAR_BULL = {"open": 100.0, "high": 100.10, "low": 99.95, "close": 100.05, "volume": 2_000_000.0}


# ─────────────────────────────────────────────────────────────────────────────
# VARY-AND-ASSERT — one test per converted tunable, proving it is load-bearing.
# ─────────────────────────────────────────────────────────────────────────────

def test_confluence_tolerance_varies_with_atr():
    """CONFLUENCE_TOLERANCE_ATR_MULT (was CONFLUENCE_TOLERANCE_DOLLARS=$0.30).
    RED-PROOF: set CONFLUENCE_TOLERANCE_ATR_MULT to 0 (or hardcode confluence_tolerance to
    always return 0.30) and the tight/wide cases stop differing (both None)."""
    tight = mf.detect_confluence(100.0, [100.5], atr_14=0.5)   # tol=0.275 < 0.5 -> no match
    wide = mf.detect_confluence(100.0, [100.5], atr_14=2.0)    # tol=1.10  >= 0.5 -> match
    assert tight is None
    assert wide == 100.5


def test_wick_rejection_bearish_varies_with_atr():
    """WICK_MIN_ATR_MULT (was WICK_MIN_DOLLARS=$0.15). Bar geometry chosen so the
    pct-of-range wick-significance component (0.10) stays BELOW the target wick (0.15),
    isolating the ATR-relative component as the sole thing that flips the outcome.
    RED-PROOF: hardcode wick_min_dollars() to always return 0.15 and both cases fire."""
    bar = pd.Series({"open": 100.02, "high": 100.20, "low": 100.00, "close": 100.05})
    tight_atr = mf.detect_wick_rejection_bearish(bar, [100.10], atr_14=0.05)  # min$=0.0135 -> fires
    wide_atr = mf.detect_wick_rejection_bearish(bar, [100.10], atr_14=2.0)    # min$=0.54   -> blocked
    assert tight_atr == 100.10
    assert wide_atr is None


def test_ribbon_spread_threshold_scales_with_price():
    """RIBBON_SPREAD_MIN_PCT_OF_PRICE (was RIBBON_SPREAD_MIN_CENTS=30, i.e. $0.30 flat).
    RED-PROOF: hardcode ribbon_spread_min_dollars() to always return 0.30 and lo/hi collapse
    to the same value regardless of price."""
    lo = mf.ribbon_spread_min_dollars(42.0)
    hi = mf.ribbon_spread_min_dollars(700.0)
    assert hi > lo
    assert hi == pytest.approx(0.30, rel=1e-9)
    assert lo == pytest.approx(0.30 * 42.0 / 700.0, rel=1e-9)


def test_level_state_match_tolerance_varies_with_atr():
    """LEVEL_STATE_MATCH_ATR_MULT (was the inline `<= 0.05` LevelState price-match tolerance).
    Same rejection_level fires in both cases (level_rejection trigger identical); only
    whether `sequence_rejection` ALSO fires depends on atr_14 -- isolates this one tunable's
    effect on the triggers_fired list.
    RED-PROOF: hardcode level_state_match_tolerance() to always return 0.05 and both cases
    agree (sequence_rejection fires in neither, since 0.05 <= 0.05 is a boundary that a
    literal port would need >= vs > care for -- this test uses 0.1 vs 1.0 to stay well clear
    of that boundary either way)."""
    level_states = {
        "L": LevelState(
            price=100.05, role="broken_to_resistance",
            bounce_history=[{"high_reached": 3.0}, {"high_reached": 2.0}, {"high_reached": 1.0}],
        )
    }
    ctx_tight = _ctx(atr=0.1, levels_active=[100.0], level_states=level_states,
                      bar_overrides=_TRIGGER_BAR_BEAR)
    ctx_wide = _ctx(atr=1.0, levels_active=[100.0], level_states=level_states,
                     bar_overrides=_TRIGGER_BAR_BEAR)
    res_tight = evaluate_bearish_setup(ctx_tight)
    res_wide = evaluate_bearish_setup(ctx_wide)
    assert "level_rejection" in res_tight.triggers_fired
    assert "level_rejection" in res_wide.triggers_fired
    assert "sequence_rejection" not in res_tight.triggers_fired
    assert "sequence_rejection" in res_wide.triggers_fired


# ─────────────────────────────────────────────────────────────────────────────
# VIX — logged, never a per-symbol blocker.
# ─────────────────────────────────────────────────────────────────────────────

def test_vix_never_blocks_bear_even_when_unfavorable():
    """VIX at a level/direction that would have hard-blocked the SPY original's filter 8
    must NOT block here -- it must only populate `vix_regime`.
    RED-PROOF: re-add `if not vix_pass: blockers.append(8)` to evaluate_bearish_setup and
    this test fails (8 appears in blockers, passed flips False)."""
    ctx = _ctx(stack="BEAR", vix_now=10.0, vix_prior=10.0,  # low+flat: bear_favorable=False
               levels_active=[100.0], bar_overrides=_TRIGGER_BAR_BEAR)
    res = evaluate_bearish_setup(ctx)
    assert 8 not in res.blockers
    assert res.vix_regime["bear_favorable"] is False
    assert res.passed is True


def test_vix_never_blocks_bull_even_when_unfavorable():
    ctx = _ctx(stack="BULL", vix_now=25.0, vix_prior=25.0,  # high+flat: bull_favorable=False
               levels_active=[100.0], bar_overrides=_TRIGGER_BAR_BULL)
    res = evaluate_bullish_setup(ctx)
    assert 8 not in res.blockers
    assert 9 not in res.blockers
    assert res.vix_regime["bull_favorable"] is False
    assert res.passed is True


def test_vix_regime_unknown_when_vix_missing():
    """None vix_now must yield an explicit 'unknown' regime, never a fabricated favorable
    or unfavorable default (judgment-guards: no silent fallback to a fake value)."""
    ctx = _ctx(stack="BEAR", vix_now=None, vix_prior=None,
               levels_active=[100.0], bar_overrides=_TRIGGER_BAR_BEAR)
    res = evaluate_bearish_setup(ctx)
    assert res.vix_regime["direction"] == "unknown"
    assert res.vix_regime["bear_favorable"] is None


# ─────────────────────────────────────────────────────────────────────────────
# FAIL LOUD — missing/short bar data raises, never a default score.
# ─────────────────────────────────────────────────────────────────────────────

def test_evaluate_bearish_setup_raises_on_empty_prior_bars():
    ctx = _ctx()
    ctx = dataclasses.replace(ctx, prior_bars=pd.DataFrame(), bar_idx=0)
    with pytest.raises(ValueError):
        evaluate_bearish_setup(ctx)


def test_evaluate_bullish_setup_raises_on_bar_idx_out_of_range():
    ctx = _ctx()
    ctx = dataclasses.replace(ctx, bar_idx=99_999)
    with pytest.raises(ValueError):
        evaluate_bullish_setup(ctx)


# ─────────────────────────────────────────────────────────────────────────────
# GREEN-PATH SANITY — a fully-passing setup scores the full denominator.
# ─────────────────────────────────────────────────────────────────────────────

def test_evaluate_bearish_setup_green_path_passes():
    ctx = _ctx(stack="BEAR", spread_pct=0.002, levels_active=[100.0], htf_15m_stack="BEAR",
               bar_overrides=_TRIGGER_BAR_BEAR)
    res = evaluate_bearish_setup(ctx)
    assert res.passed is True
    assert res.bear_score == 10
    assert res.blockers == []
    assert "level_rejection" in res.triggers_fired


def test_evaluate_bullish_setup_green_path_passes():
    ctx = _ctx(stack="BULL", spread_pct=0.002, levels_active=[100.0], htf_15m_stack="BULL",
               bar_overrides=_TRIGGER_BAR_BULL)
    res = evaluate_bullish_setup(ctx)
    assert res.passed is True
    assert res.bull_score == 11
    assert res.blockers == []
    assert "level_reclaim" in res.triggers_fired
