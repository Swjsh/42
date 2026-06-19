"""Unit tests for lib.engine.regime_book — the Regime-Aware Multi-Setup Book scaffold.

Pure-function tests on SYNTHETIC signals: no network, no data files, no BarContext
construction (the classifier reads a tiny RegimeSignals view). Pins:
  * every classification path (bull / bear / range_pin / high_vol / neutral),
  * the declared precedence (high_vol dominates a BEAR-stacked panic; first-match wins),
  * VIX character (rising/falling deadband) gating bear/bull,
  * range compression gating bull/pin,
  * GEX corroboration is reinforce-ONLY (never flips a clean read; absent => no effect),
  * select_setups is DATA-driven and enforces the propose-only safety property
    (WATCH_ONLY excluded by default; the whole seed map => () for every regime),
  * the signals_from_bar_context adapter (range_ratio math, missing-field tolerance).

Run:  cd backtest && python -m pytest tests/test_regime_book.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine.regime_book import (  # noqa: E402
    REGIME_PRECEDENCE,
    REGIME_SETUP_MAP,
    RANGE_COMPRESSION_RATIO,
    VIX_HIGH_VOL_FLOOR,
    VIX_LOW_CEIL,
    Evidence,
    PromotionStatus,
    Regime,
    RegimeSignals,
    SetupSlot,
    classify_regime,
    select_setups,
    signals_from_bar_context,
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _sig(**kw) -> RegimeSignals:
    """RegimeSignals with sane defaults (calm/neutral) overridden per test."""
    base = dict(
        vix_now=16.0, vix_prior=16.0, ribbon_stack="MIXED",
        htf_stack=None, range_ratio=1.0, gex_hint=None,
    )
    base.update(kw)
    return RegimeSignals(**base)


# ── classification: bear_trend ────────────────────────────────────────────────
def test_bear_trend_down_stack_vix_not_falling():
    # BEAR stack, VIX flat (not falling), mid VIX -> bear_trend.
    assert classify_regime(_sig(ribbon_stack="BEAR", vix_now=17.0, vix_prior=17.0)) is Regime.BEAR_TREND


def test_bear_trend_with_rising_vix_still_bear():
    # Rising fear on a down-stack is still bear_trend (the confirmed edge regime).
    assert classify_regime(_sig(ribbon_stack="BEAR", vix_now=18.0, vix_prior=17.0)) is Regime.BEAR_TREND


def test_bear_stack_but_vix_falling_is_not_bear_trend():
    # VIX-falling relief bounce on a down-stack is NOT the bear regime -> neutral.
    r = classify_regime(_sig(ribbon_stack="BEAR", vix_now=16.5, vix_prior=17.5))
    assert r is not Regime.BEAR_TREND
    assert r is Regime.NEUTRAL  # mid VIX, no other predicate fires


# ── classification: bull_trend ────────────────────────────────────────────────
def test_bull_trend_up_stack_calm():
    assert classify_regime(_sig(ribbon_stack="BULL", vix_now=15.0, vix_prior=15.0)) is Regime.BULL_TREND


def test_bull_stack_but_vix_rising_is_not_bull_trend():
    r = classify_regime(_sig(ribbon_stack="BULL", vix_now=16.5, vix_prior=15.5))
    assert r is not Regime.BULL_TREND


def test_bull_stack_but_compressed_is_not_bull_trend():
    # Compression on an up-stack disqualifies bull_trend (it's a pin-ish tape).
    r = classify_regime(_sig(ribbon_stack="BULL", vix_now=15.0, vix_prior=15.0, range_ratio=0.5))
    assert r is not Regime.BULL_TREND


# ── classification: range_pin ─────────────────────────────────────────────────
def test_range_pin_mixed_compressed_low_vix():
    s = _sig(ribbon_stack="MIXED", vix_now=14.0, vix_prior=14.0, range_ratio=0.5)
    assert classify_regime(s) is Regime.RANGE_PIN


def test_range_pin_requires_compression():
    # MIXED + low VIX but NOT compressed -> not range_pin (falls to neutral).
    s = _sig(ribbon_stack="MIXED", vix_now=14.0, vix_prior=14.0, range_ratio=1.0)
    assert classify_regime(s) is Regime.NEUTRAL


def test_range_pin_requires_low_vix():
    # MIXED + compressed but VIX too high -> not range_pin.
    s = _sig(ribbon_stack="MIXED", vix_now=17.0, vix_prior=17.0, range_ratio=0.5)
    assert classify_regime(s) is not Regime.RANGE_PIN


# ── classification: high_vol + precedence ─────────────────────────────────────
def test_high_vol_floor():
    assert classify_regime(_sig(vix_now=VIX_HIGH_VOL_FLOOR, vix_prior=18.0)) is Regime.HIGH_VOL


def test_high_vol_dominates_bear_stack():
    # A BEAR-stacked PANIC day is high_vol, not ordinary bear_trend (precedence).
    s = _sig(ribbon_stack="BEAR", vix_now=25.0, vix_prior=24.0)
    assert classify_regime(s) is Regime.HIGH_VOL


def test_high_vol_dominates_bull_stack():
    s = _sig(ribbon_stack="BULL", vix_now=22.0, vix_prior=22.0)
    assert classify_regime(s) is Regime.HIGH_VOL


def test_precedence_constant_order():
    # The declared precedence is the spec: high_vol first, neutral last.
    assert REGIME_PRECEDENCE[0] is Regime.HIGH_VOL
    assert REGIME_PRECEDENCE[-1] is Regime.NEUTRAL
    assert set(REGIME_PRECEDENCE) == set(Regime)  # every regime is reachable


# ── classification: neutral fallback ──────────────────────────────────────────
def test_neutral_when_nothing_matches():
    # MIXED stack, mid VIX, no compression -> neutral.
    assert classify_regime(_sig()) is Regime.NEUTRAL


def test_classify_always_returns_a_regime():
    # Even degenerate inputs (None stack) classify (to neutral), never crash.
    assert classify_regime(_sig(ribbon_stack=None)) is Regime.NEUTRAL
    assert classify_regime(_sig(ribbon_stack="WARMUP")) is Regime.NEUTRAL


# ── GEX corroboration: reinforce-only, never override, absent => no effect ─────
def test_gex_absent_no_effect():
    # No hint -> same as base classification.
    s = _sig(ribbon_stack="MIXED", vix_now=14.0, vix_prior=14.0, range_ratio=1.0)
    assert classify_regime(s) is Regime.NEUTRAL


def test_gex_long_gamma_pin_nudges_neutral_to_range_pin():
    # NEUTRAL base + long_gamma_pin + low VIX -> range_pin (reinforce the ambiguous case).
    s = _sig(ribbon_stack="MIXED", vix_now=14.0, vix_prior=14.0, range_ratio=1.0,
             gex_hint="long_gamma_pin")
    assert classify_regime(s) is Regime.RANGE_PIN


def test_gex_short_gamma_trend_nudges_neutral_to_high_vol_only_if_vix_high():
    # NEUTRAL base + short_gamma_trend but VIX low -> stays neutral (no override).
    s_low = _sig(ribbon_stack="MIXED", vix_now=14.0, vix_prior=14.0, range_ratio=1.0,
                 gex_hint="short_gamma_trend")
    assert classify_regime(s_low) is Regime.NEUTRAL


def test_gex_cannot_override_a_clean_read():
    # A clean BULL_TREND read is NOT flipped by a contrary GEX hint (reinforce-only).
    s = _sig(ribbon_stack="BULL", vix_now=15.0, vix_prior=15.0, range_ratio=1.0,
             gex_hint="long_gamma_pin")
    assert classify_regime(s) is Regime.BULL_TREND


# ── select_setups: the propose-only safety property ───────────────────────────
def test_seed_map_is_entirely_watch_only():
    # The whole shipped book must be WATCH_ONLY (nothing live yet).
    for slots in REGIME_SETUP_MAP.values():
        for slot in slots:
            assert slot.status is PromotionStatus.WATCH_ONLY


def test_select_returns_empty_for_every_regime_today():
    # The structural propose-only contract: default selection is inert everywhere.
    for regime in Regime:
        assert select_setups(regime) == ()


def test_include_watch_exposes_watch_slots():
    # Research view sees the candidates; bear_trend has 4 seeded (2 fleet rows +
    # the 2 data-discovered survivors VWAP_TREND_PULLBACK / GAP_AND_GO).
    bear = select_setups(Regime.BEAR_TREND, include_watch=True)
    assert len(bear) == 4
    assert any(s.setup == "BEARISH_REJECTION_RIDE_THE_RIBBON" for s in bear)


def test_data_discovered_survivors_seeded_in_both_trends_watch_only_and_inert():
    # The 2 infinite-ammo survivors must appear in BOTH trend cells, carry
    # DSR=PASS + OOS-stable + the _DISCOVERY provenance, and stay WATCH_ONLY so
    # they are NOT live-eligible (select_setups default still returns ()).
    discovered = {"VWAP_TREND_PULLBACK", "GAP_AND_GO"}
    for regime in (Regime.BULL_TREND, Regime.BEAR_TREND):
        watch = select_setups(regime, include_watch=True)
        present = {s.setup for s in watch} & discovered
        assert present == discovered, f"{regime} missing a discovered survivor: {present}"
        for slot in watch:
            if slot.setup in discovered:
                assert slot.status is PromotionStatus.WATCH_ONLY
                assert slot.is_live_eligible() is False
                assert slot.evidence is not None
                assert slot.evidence.dsr_verdict == "PASS"
                assert slot.evidence.oos_sign_stable is True
                assert slot.evidence.on_real_levels is False  # proxy strikes (L58)
                assert "infinite-ammo-discovery" in slot.evidence.source
                assert slot.evidence.n > 0 and slot.evidence.exp > 0
        # default (live) selection still excludes them — propose-only intact.
        assert select_setups(regime) == ()


def test_range_pin_is_empty_by_design():
    assert select_setups(Regime.RANGE_PIN, include_watch=True) == ()
    assert select_setups(Regime.NEUTRAL, include_watch=True) == ()


def test_select_is_data_driven_with_injected_book():
    # A promoted slot in an injected book IS selected by default; watch/retired are not.
    ev = Evidence(exp=30.0, wr=70.0, n=40, dsr_verdict="PASS", oos_sign_stable=True,
                  on_real_levels=True, source="test")
    book = {
        Regime.BULL_TREND: (
            SetupSlot("ACTIVE_ONE", PromotionStatus.REGIME_ACTIVE, "elite", ev),
            SetupSlot("WATCH_ONE", PromotionStatus.WATCH_ONLY, "base", ev),
            SetupSlot("DEAD_ONE", PromotionStatus.RETIRED, "base", ev),
        ),
    }
    live = select_setups(Regime.BULL_TREND, book=book)
    assert [s.setup for s in live] == ["ACTIVE_ONE"]
    assert live[0].is_live_eligible() is True
    # include_watch adds the watch slot but never the retired one.
    both = select_setups(Regime.BULL_TREND, include_watch=True, book=book)
    assert [s.setup for s in both] == ["ACTIVE_ONE", "WATCH_ONE"]


def test_select_returns_fresh_tuple_not_internal_object():
    # Callers cannot mutate the book through the returned value.
    a = select_setups(Regime.BEAR_TREND, include_watch=True)
    b = select_setups(Regime.BEAR_TREND, include_watch=True)
    assert a == b
    assert a is not b


def test_retired_never_selected_even_with_include_watch():
    ev = Evidence(exp=0.0, wr=0.0, n=0)
    book = {Regime.HIGH_VOL: (SetupSlot("X", PromotionStatus.RETIRED, evidence=ev),)}
    assert select_setups(Regime.HIGH_VOL, include_watch=True, book=book) == ()


# ── SetupSlot / Evidence are immutable data ───────────────────────────────────
def test_records_are_frozen():
    slot = SetupSlot("S", PromotionStatus.WATCH_ONLY)
    with pytest.raises(Exception):
        slot.status = PromotionStatus.REGIME_ACTIVE  # type: ignore[misc]
    ev = Evidence(exp=1.0, wr=2.0, n=3)
    with pytest.raises(Exception):
        ev.exp = 9.0  # type: ignore[misc]


def test_evidence_carries_proxy_provenance():
    # Seed slots must disclose they are on proxy (not real) levels.
    for slots in REGIME_SETUP_MAP.values():
        for slot in slots:
            if slot.evidence is not None:
                assert slot.evidence.on_real_levels is False


# ── signals_from_bar_context adapter ──────────────────────────────────────────
class _StubRibbon:
    def __init__(self, stack):
        self.stack = stack


class _StubBar(dict):
    """A dict bar (BarContext.bar is a pandas Series; dict supports [] the same way)."""


class _StubCtx:
    def __init__(self, vix_now, vix_prior, stack, htf, hi, lo, base):
        self.vix_now = vix_now
        self.vix_prior = vix_prior
        self.ribbon_now = _StubRibbon(stack) if stack is not None else None
        self.htf_15m_stack = htf
        self.bar = _StubBar(high=hi, low=lo)
        self.range_baseline_20 = base


def test_adapter_computes_range_ratio():
    ctx = _StubCtx(17.0, 17.0, "BEAR", "BEAR", hi=601.0, lo=600.0, base=2.0)
    s = signals_from_bar_context(ctx)
    assert s.vix_now == 17.0
    assert s.ribbon_stack == "BEAR"
    assert s.htf_stack == "BEAR"
    assert s.range_ratio == pytest.approx(0.5)  # (601-600)/2.0
    assert s.gex_hint is None


def test_adapter_handles_zero_baseline():
    # Warmup: no baseline -> range_ratio None -> "not compressed" downstream.
    ctx = _StubCtx(17.0, 17.0, "MIXED", None, hi=601.0, lo=600.0, base=0.0)
    s = signals_from_bar_context(ctx)
    assert s.range_ratio is None
    assert s.is_compressed() is False


def test_adapter_passes_gex_hint_through():
    ctx = _StubCtx(20.0, 20.0, "MIXED", None, hi=601.0, lo=600.0, base=2.0)
    s = signals_from_bar_context(ctx, gex_hint="short_gamma_trend")
    assert s.gex_hint == "short_gamma_trend"


def test_adapter_end_to_end_classifies():
    # Adapter -> classifier wires together on a BEAR panic stub -> high_vol (precedence).
    ctx = _StubCtx(25.0, 24.0, "BEAR", "BEAR", hi=605.0, lo=600.0, base=2.0)
    assert classify_regime(signals_from_bar_context(ctx)) is Regime.HIGH_VOL


# ── threshold sanity (pins the cut points the research used) ───────────────────
def test_thresholds_match_research_proxy():
    assert VIX_HIGH_VOL_FLOOR == 19.0
    assert VIX_LOW_CEIL == 16.0
    assert RANGE_COMPRESSION_RATIO == 0.85
