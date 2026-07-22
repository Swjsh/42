"""Guard: zero-behavior-change proof for the PULLBACK-HOLD shadow-logged bull
trigger (Lane-A vocabulary build, queue item PULLBACK-HOLD-BULL-TRIGGER, filed
2026-07-22 Fable review). Same methodology as
test_bull_trendline_wick_reclaim_shadow_only.py / test_context_bundle_tag_no_behavior_change.py.

WHAT THIS PINS: `evaluate_bullish_setup` (backtest/lib/filters.py) computes
`detect_pullback_hold_bullish` and records it on `BullishSetupResult.shadow_triggers_fired`
-- LOGGED ONLY. Nothing on the decision path (`triggers_fired`, `blockers`,
`bull_score`, `passed`, `reclaim_level`, `ribbon_just_flipped_bullish`,
`confluence_match`) may be affected by whether this shadow trigger fires. Lane-B
validation (frozen pre-reg -> real-fills replay -> 4-condition gate + BH-FDR) must
clear before this can ever be promoted into `triggers`/scoring.

RED-PROOF (performed during authorship, documented here per precedent -- not left
as a live hack): the shadow block in `evaluate_bullish_setup` was temporarily
edited to also `triggers.append("pullback_hold")` for a fired detection, this file
was re-run, and `test_pullback_hold_shadow_trigger_does_not_affect_scoring` FAILED
on the `triggers_fired` equality assertion (res_a's `triggers_fired` picked up
`pullback_hold` while res_b stayed unaffected) -- proving this guard actually
exercises the wiring it claims to. The edit was then reverted and this file
confirmed green again.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_pullback_hold_shadow_only.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

_BEHAVIOR_FIELDS = (
    "passed", "bull_score", "blockers", "triggers_fired",
    "reclaim_level", "ribbon_just_flipped_bullish", "confluence_match",
)

# Isolate filter 11 (trigger-count / level-tied gate) -- filters 1-10 irrelevant here.
_DISABLE_ALL_BUT_FILTER_11 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def _make_bar(o: float, h: float, l: float, c: float, v: float = 300_000) -> pd.Series:
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": v})


def _prior_bars_variant_a() -> pd.DataFrame:
    """idx 6 (the current/trigger bar) is IDENTICAL in variant A and B (same OHLCV) --
    only bars 1-5 (outside what detect_level_reclaim / detect_wick_reclaim_bullish look
    at -- both read `bar` + `levels_active` only, never `prior_bars`) differ, so this
    is the sharpest possible isolation: level_reclaim/wick_reclaim/trendline_reclaim
    are proven empty in BOTH variants (verified below), and ONLY pullback_hold's own
    approach-window scan (which DOES read prior_bars) differs. Bars 3-5 dip into and
    hold the 100.00 level's zone band [99.70, 100.30]; idx 6 closes at 99.98 -- below
    the level itself (so level_reclaim's close>level check fails) but above the
    hold-window's highest close (99.95) -- confirming ONLY pullback_hold."""
    rows = [
        _make_bar(101.00, 101.10, 100.80, 100.90),
        _make_bar(100.90, 100.95, 100.50, 100.60),
        _make_bar(100.60, 100.65, 100.20, 100.25),
        _make_bar(100.25, 100.30, 99.80, 99.85),   # idx 3: pullback low (dist 0.20 from 100.00)
        _make_bar(99.85, 99.90, 99.80, 99.90),      # idx 4: hold
        _make_bar(99.90, 99.95, 99.85, 99.95),      # idx 5: hold
        _make_bar(99.95, 100.05, 99.93, 99.98),      # idx 6: current bar (IDENTICAL in variant B)
    ]
    return pd.DataFrame(rows)


def _prior_bars_variant_b() -> pd.DataFrame:
    """Same idx-6 current bar as variant A, but bars 1-5 never enter the zone band
    (lows stay >= 100.70, always > 0.30 from the 100.00 level) -- so pullback_hold's
    approach-window scan finds no qualifying touch and returns None."""
    rows = [
        _make_bar(101.00, 101.10, 100.80, 100.90),
        _make_bar(100.90, 100.95, 100.70, 100.80),
        _make_bar(100.80, 100.85, 100.70, 100.75),
        _make_bar(100.75, 100.80, 100.70, 100.75),
        _make_bar(100.75, 100.80, 100.70, 100.75),
        _make_bar(100.75, 100.80, 100.70, 100.75),
        _make_bar(99.95, 100.05, 99.93, 99.98),      # idx 6: byte-identical to variant A's idx 6
    ]
    return pd.DataFrame(rows)


def _make_ctx(bar: pd.Series, levels_active: list[float], prior_bars: pd.DataFrame, bar_idx: int):
    from lib.filters import BarContext
    return BarContext(
        bar_idx=bar_idx, timestamp_et=dt.datetime(2026, 7, 22, 10, 50),
        bar=bar, prior_bars=prior_bars,
        ribbon_now=None, ribbon_history=[],
        vix_now=15.0, vix_prior=15.0,
        vol_baseline_20=300_000.0, range_baseline_20=0.5,
        levels_active=levels_active, multi_day_levels=[],
        htf_15m_stack="BULL", level_states={},
    )


def test_pullback_hold_shadow_trigger_does_not_affect_scoring():
    """THE zero-behavior-change proof: variant A and B share a BYTE-IDENTICAL
    current bar (idx 6) and `levels_active` -- the only difference is bars 1-5 of
    `prior_bars` (which detect_level_reclaim / detect_wick_reclaim_bullish never
    even read). pullback_hold fires in A (bars 3-5 dip into and hold the zone) and
    not in B (bars 1-5 never enter the zone) -- proving the shadow trigger's own
    approach-window scan is the ONLY thing that differs, while every scored/routed
    field on BullishSetupResult stays byte-identical."""
    from lib.filters import evaluate_bullish_setup

    bar_idx = 6
    prior_bars_a = _prior_bars_variant_a()
    prior_bars_b = _prior_bars_variant_b()
    bar_a = prior_bars_a.iloc[bar_idx]
    bar_b = prior_bars_b.iloc[bar_idx]

    # Sharpest possible isolation check: the current bar is IDENTICAL between variants.
    assert bar_a.equals(bar_b), "variant A/B must share a byte-identical current bar"

    ctx_a = _make_ctx(bar_a, [100.00], prior_bars_a, bar_idx)
    ctx_b = _make_ctx(bar_b, [100.00], prior_bars_b, bar_idx)

    res_a = evaluate_bullish_setup(ctx_a, disable_filters=_DISABLE_ALL_BUT_FILTER_11)
    res_b = evaluate_bullish_setup(ctx_b, disable_filters=_DISABLE_ALL_BUT_FILTER_11)

    assert res_a.shadow_triggers_fired == ["pullback_hold"], (
        f"fixture must fire ONLY the pullback_hold shadow trigger in variant A; "
        f"got {res_a.shadow_triggers_fired}"
    )
    assert res_b.shadow_triggers_fired == [], (
        f"fixture must fire NO shadow triggers in variant B; got {res_b.shadow_triggers_fired}"
    )

    # THE proof: every scored/routed field is byte-identical despite the shadow delta.
    for field_name in _BEHAVIOR_FIELDS:
        val_a = getattr(res_a, field_name)
        val_b = getattr(res_b, field_name)
        assert val_a == val_b, (
            f"{field_name!r} must be byte-identical regardless of pullback_hold shadow "
            f"presence (purity rule): A={val_a!r} vs B={val_b!r}"
        )

    # Sharpest form of the proof: triggers_fired is EMPTY in both (level_reclaim itself
    # does not fire on this bar+level -- close 99.98 is below the level, not above it),
    # even though pullback_hold fired in A -- shadow detections cannot leak into the
    # scored list.
    assert res_a.triggers_fired == [], (
        f"triggers_fired must stay empty even though pullback_hold fired; "
        f"got {res_a.triggers_fired!r} (contamination)"
    )


def test_pullback_hold_shadow_field_defaults_empty():
    """BullishSetupResult.shadow_triggers_fired stays additive/backward-compatible."""
    from lib.filters import BullishSetupResult

    res = BullishSetupResult(passed=True, bull_score=8)
    assert res.shadow_triggers_fired == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
