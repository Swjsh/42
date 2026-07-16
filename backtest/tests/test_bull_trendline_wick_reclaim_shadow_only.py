"""Guard: THE zero-behavior-change proof for the two SHADOW-LOGGED bull triggers
(trendline_reclaim, wick_reclaim; 2026-07-15 fix-ship-repeat root-cause task).

WHAT THIS PINS: `evaluate_bullish_setup` (backtest/lib/filters.py) computes
`detect_trendline_reclaim_bullish` / `detect_wick_reclaim_bullish` and records them on
`BullishSetupResult.shadow_triggers_fired` -- LOGGED ONLY. Nothing on the decision path
(`triggers`/`triggers_fired`, `blockers`, `bull_score`, `passed`, `reclaim_level`,
`ribbon_just_flipped_bullish`, `confluence_match`) may be affected by whether either
shadow trigger fires. Mirrors the `context_bundle` precedent
(test_context_bundle_tag_no_behavior_change.py): same "present vs absent -> all
behavior keys byte-identical, only the tag itself differs" methodology.

FIXTURE: a single synthetic bar (O=96.00 H=96.60 L=95.90 C=96.45) with a 62-bar
descending-pivot `prior_bars` (see test_trendline_reclaim_trigger.py for the same
construction) and `levels_active=[96.50]` makes BOTH shadow detectors fire
simultaneously, while `detect_level_reclaim` (the REGULAR, live-scoring mirror)
deliberately does NOT fire on the same bar+level (close 96.45 < level 96.50, so the
strict `close > level` reclaim check fails -- only the wick-tolerant shadow check
passes) -- so `triggers`/`triggers_fired` stays empty in BOTH the shadow-firing and
shadow-silent variants, giving the strongest possible proof: 2 shadow triggers can
fire while the officially-scored trigger list stays completely empty.

RED-PROOF (performed during authorship, documented here per the context_bundle
precedent's own methodology -- not left as a live hack in this file): the shadow
block in `evaluate_bullish_setup` was temporarily edited to also
`triggers.extend(shadow_triggers)`, this file was re-run, and
`test_shadow_triggers_do_not_affect_bull_scoring_or_routing_fields` FAILED on the
`triggers_fired` equality assertion (res_a became `['trendline_reclaim',
'wick_reclaim']` while res_b stayed `[]`) -- proving this guard actually exercises
the wiring it claims to. The edit was then reverted and this file confirmed green
again.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bull_trendline_wick_reclaim_shadow_only.py -q
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Every non-shadow field BullishSetupResult carries -- must be byte-identical
# regardless of whether the shadow triggers fired.
_BEHAVIOR_FIELDS = (
    "passed", "bull_score", "blockers", "triggers_fired",
    "reclaim_level", "ribbon_just_flipped_bullish", "confluence_match",
)

# Isolate filter 11 (the trigger-count / level-tied gate) so the expected outcome is
# unambiguous and doesn't depend on constructing a fully realistic ribbon/VIX/spread
# context -- filters 1-10 are irrelevant to what this guard is proving.
_DISABLE_ALL_BUT_FILTER_11 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def _build_descending_pivot_window(pivots: dict[int, float], n: int = 62,
                                    baseline_high: float = 95.20) -> pd.DataFrame:
    """Identical construction to test_trendline_reclaim_trigger.py's fixture."""
    rows = []
    for i in range(n):
        if i < 2:
            rows.append({"open": 90.0, "high": 90.3, "low": 89.8, "close": 90.1, "volume": 100000})
            continue
        wpos = i - 2
        if wpos in pivots:
            hv = pivots[wpos]
            rows.append({"open": hv - 0.5, "high": hv, "low": hv - 0.7, "close": hv - 0.3, "volume": 100000})
        else:
            rows.append({"open": 94.9, "high": baseline_high, "low": 94.7, "close": 94.9, "volume": 100000})
    return pd.DataFrame(rows)


def _make_ctx(bar: pd.Series, levels_active: list[float], prior_bars: pd.DataFrame, bar_idx: int):
    from lib.filters import BarContext
    return BarContext(
        bar_idx=bar_idx, timestamp_et=dt.datetime(2026, 5, 1, 13, 35),
        bar=bar, prior_bars=prior_bars,
        ribbon_now=None, ribbon_history=[],
        vix_now=15.0, vix_prior=15.0,
        vol_baseline_20=100_000.0, range_baseline_20=0.5,
        levels_active=levels_active, multi_day_levels=[],
        htf_15m_stack="BULL", level_states={},
    )


def test_shadow_triggers_do_not_affect_bull_scoring_or_routing_fields():
    """THE zero-behavior-change proof: a bar+level combo that fires BOTH shadow
    triggers (trendline_reclaim, wick_reclaim) yields byte-identical `_BEHAVIOR_FIELDS`
    to a bar+level combo where neither fires -- only `shadow_triggers_fired` differs."""
    from lib.filters import evaluate_bullish_setup

    prior_bars = _build_descending_pivot_window({5: 100.00, 20: 99.00, 35: 98.00})
    bar_idx = 62

    # Variant A: BOTH shadow triggers fire. trendline_reclaim via the descending-pivot
    # breakout (see test_trendline_reclaim_trigger.py); wick_reclaim via level=96.50
    # (low 95.90 <= 96.50 reached, close 96.45 within $0.10 tolerance below 96.50,
    # lower wick 0.55 >= threshold). detect_level_reclaim does NOT fire on this same
    # level (close 96.45 is NOT > 96.50 -- the strict reclaim check fails), so
    # `triggers` stays empty despite two shadow detections.
    bar_a = pd.Series({"open": 96.00, "high": 96.60, "low": 95.90, "close": 96.45, "volume": 500_000})
    ctx_a = _make_ctx(bar_a, [96.50], prior_bars, bar_idx)

    # Variant B: neither shadow trigger fires. Flat bar never reaches the ~$96.33
    # trendline, and levels_active=[] trivially prevents any wick/level reclaim.
    bar_b = pd.Series({"open": 96.00, "high": 96.05, "low": 95.95, "close": 96.00, "volume": 500_000})
    ctx_b = _make_ctx(bar_b, [], prior_bars, bar_idx)

    res_a = evaluate_bullish_setup(ctx_a, disable_filters=_DISABLE_ALL_BUT_FILTER_11)
    res_b = evaluate_bullish_setup(ctx_b, disable_filters=_DISABLE_ALL_BUT_FILTER_11)

    # Non-vacuous: the shadow tag itself must actually differ.
    assert res_a.shadow_triggers_fired == ["trendline_reclaim", "wick_reclaim"], (
        f"fixture must fire BOTH shadow triggers in variant A; got {res_a.shadow_triggers_fired}"
    )
    assert res_b.shadow_triggers_fired == [], (
        f"fixture must fire NEITHER shadow trigger in variant B; got {res_b.shadow_triggers_fired}"
    )

    # THE proof: every scored/routed field is byte-identical despite the shadow delta.
    for field_name in _BEHAVIOR_FIELDS:
        val_a = getattr(res_a, field_name)
        val_b = getattr(res_b, field_name)
        assert val_a == val_b, (
            f"{field_name!r} must be byte-identical regardless of shadow-trigger "
            f"presence (purity rule -- shadow detection must never reach scoring): "
            f"A={val_a!r} vs B={val_b!r}"
        )

    # Sharpest form of the proof: triggers_fired is EMPTY in both, even though 2
    # shadow triggers fired in A -- shadow detections cannot leak into the scored list.
    assert res_a.triggers_fired == [], (
        f"triggers_fired must stay empty even though shadow triggers fired; "
        f"got {res_a.triggers_fired!r} (contamination)"
    )
    assert res_a.passed is False and res_b.passed is False
    assert res_a.bull_score == res_b.bull_score == 10
    assert res_a.blockers == res_b.blockers == [11]


def test_shadow_triggers_fired_field_exists_and_defaults_empty():
    """BullishSetupResult.shadow_triggers_fired is additive: constructing a result
    without it defaults to an empty list (no existing caller can break on this field)."""
    from lib.filters import BullishSetupResult

    res = BullishSetupResult(passed=True, bull_score=8)
    assert res.shadow_triggers_fired == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
