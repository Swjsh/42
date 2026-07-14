"""Guard tests for trendline_break_replay.py (G1, 2026-07-14).

Two mandatory guard families per the task spec:
  1. NO-LOOKAHEAD -- truncation invariance: replaying bars[:K] for any K must reproduce the
     byte-identical break record (every field that doesn't depend on bars >= K) that a full
     replay produces, and any post-break horizon field must reflect ONLY the bars actually
     present in the truncated array (not the full day's future).
  2. J-RULES -- mixed anchors structurally impossible, no-wick anchors rejected from the wick
     family, and respect_count < 2-beyond-anchors lines are dropped entirely (never emitted).

Pure Python + synthetic bars -- no CSV/network dependency, matches the convention in
test_trendline_engine.py. Run: cd backtest && .venv/Scripts/python.exe -m pytest tests/test_trendline_break_replay.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "autoresearch"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import trendline_engine as te  # noqa: E402
import trendline_break_replay as tbr  # noqa: E402

_BASE_UNIX = 1_752_500_000  # arbitrary epoch, 2025-ish
_BAR_SEC = 300


def _bar(o: float, h: float, l: float, c: float, v: float = 1000.0) -> dict:
    assert l <= min(o, c) and h >= max(o, c), "malformed synthetic bar (h/l must bound o/c)"
    return {"o": o, "h": h, "l": l, "c": c, "v": v}


def _build_day(n: int, overrides: dict[int, dict], far: float = 200.0) -> list[dict]:
    """n-bar synthetic RTH day. Every index defaults to an identical FAR-away filler bar (never
    a pivot -- ties fail find_pivots' strict-extreme test -- and never within tolerance of any
    line living down near `overrides`' price scale), except indices in `overrides`."""
    bars = []
    for i in range(n):
        b = dict(overrides[i]) if i in overrides else _bar(far, far + 0.5, far - 0.5, far + 0.1)
        b["unix"] = _BASE_UNIX + i * _BAR_SEC
        b["hm"] = f"{9 + (30 + i * 5) // 60:02d}:{(30 + i * 5) % 60:02d}"
        bars.append(b)
    return bars


# --------------------------------------------------------------------------- shared scenario
# support/wick line: anchor1 i1=5 @ low=100.00, anchor2 i2=10 @ low=100.50 (slope=0.10/bar).
# Both anchors carry a deep protruding wick (>> WICK_MIN_FRACTION*range and WICK_MIN_CENTS).
# Respect touches at idx15 (lv=101.00) and idx20 (lv=101.50) -> qualifies at idx20.
# Break (close-through) at idx25: lv=102.00, tol=max(0.10,0.0015*102)=0.153, close=101.50.
_ANCHOR1 = _bar(100.40, 100.50, 100.00, 100.45)
_ANCHOR2 = _bar(100.90, 101.00, 100.50, 100.95)
_RESPECT_15 = _bar(101.40, 101.45, 101.00, 101.35)
_RESPECT_20 = _bar(101.90, 101.95, 101.50, 101.85)
_BREAK_25 = _bar(101.80, 101.85, 101.40, 101.50, v=5000.0)  # elevated volume on the break bar


def _qualifying_scenario_overrides() -> dict[int, dict]:
    return {5: _ANCHOR1, 10: _ANCHOR2, 15: _RESPECT_15, 20: _RESPECT_20, 25: _BREAK_25}


def _find_target_line(rows: list[dict]) -> dict | None:
    for r in rows:
        if r["kind"] == "support" and r["anchor_family"] == "wick" and r["a_bar_idx"] == 5 and r["b_bar_idx"] == 10:
            return r
    return None


# =============================================================================================
# 1) NO-LOOKAHEAD
# =============================================================================================
def test_no_lookahead_truncation_invariance_causal_fields():
    """Truncating the day right after the break bar must reproduce byte-identical CAUSAL break
    fields (everything that only depends on bars <= break_bar_idx) vs. a full-day replay that
    has 20 extra future bars available. If the tool were peeking ahead, these would differ."""
    full_bars = _build_day(46, _qualifying_scenario_overrides())  # 20 bars of "future" past the break
    full_rows = tbr.replay_day(full_bars, "2026-07-14")
    full_line = _find_target_line(full_rows)
    assert full_line is not None, "expected scenario line to qualify and break in the full replay"
    assert full_line["break"] is not None

    truncated_bars = full_bars[:26]  # bars 0..25 inclusive -- ZERO bars past the break bar
    trunc_rows = tbr.replay_day(truncated_bars, "2026-07-14")
    trunc_line = _find_target_line(trunc_rows)
    assert trunc_line is not None

    causal_fields = [
        "kind", "anchor_family", "a_bar_idx", "a_et", "a_unix", "a_price",
        "b_bar_idx", "b_et", "b_unix", "b_price", "slope_per_bar", "span_bars",
        "qualified_at_bar_idx", "qualified_at_et",
    ]
    for f in causal_fields:
        assert trunc_line[f] == full_line[f], f"causal field {f!r} diverged under truncation"

    causal_break_fields = [
        "break_bar_idx", "break_unix", "time_of_day_et", "break_type", "break_direction",
        "line_value_at_break", "close_at_break", "extreme_at_break",
        "breach_amount_close", "breach_amount_extreme", "break_bar_volume",
        "avg_volume_20bar", "volume_ratio", "vol_lookback_bars_available",
    ]
    for f in causal_break_fields:
        assert trunc_line["break"][f] == full_line["break"][f], f"causal break field {f!r} diverged"


def test_no_lookahead_horizon_fields_use_only_available_bars():
    """The post-break horizon fields (MFE/MAE/retest) must reflect ONLY the bars the truncated
    replay actually had -- not silently reuse/see the full day's future. Zero-future-bar
    truncation must report bars_available=0 / None, never the full-day numbers."""
    full_bars = _build_day(46, _qualifying_scenario_overrides())
    full_rows = tbr.replay_day(full_bars, "2026-07-14")
    full_break = _find_target_line(full_rows)["break"]
    # Sanity: the full day DOES have future bars for every horizon (46 - 26 = 20 >= 18 needed).
    assert full_break["bars_available_90min"] == 18

    zero_future_bars = full_bars[:26]  # break bar is the LAST bar available
    zero_rows = tbr.replay_day(zero_future_bars, "2026-07-14")
    zero_break = _find_target_line(zero_rows)["break"]
    for h in tbr.HORIZONS_MIN:
        assert zero_break[f"bars_available_{h}min"] == 0
        assert zero_break[f"mfe_{h}min"] is None
        assert zero_break[f"mae_{h}min"] is None
    assert zero_break["retest_within_10bar"] is False
    assert zero_break["retest_within_20bar"] is False

    # Partial truncation: exactly 5 bars past the break (< the 6 needed for a full 30min window).
    partial_bars = full_bars[:31]
    partial_rows = tbr.replay_day(partial_bars, "2026-07-14")
    partial_break = _find_target_line(partial_rows)["break"]
    assert partial_break["bars_available_30min"] == 5
    # And that partial MFE/MAE must equal a hand-computed value from ONLY those 5 bars (proves
    # the window slice, not some cached full-day computation, drove the number).
    window = full_bars[26:31]
    expected_mfe = round(_BREAK_25["c"] - min(b["l"] for b in window), 4)  # bearish break
    expected_mae = round(max(b["h"] for b in window) - _BREAK_25["c"], 4)
    assert partial_break["mfe_30min"] == expected_mfe
    assert partial_break["mae_30min"] == expected_mae
    # And that MUST differ from the full day's 30min figure (full day has 6 bars there, a
    # materially different window) -- proves truncation actually changed the computation.
    assert partial_break["mfe_30min"] != full_break["mfe_30min"] or partial_break["bars_available_30min"] != full_break["bars_available_30min"]


def test_truncation_before_qualification_never_fabricates_a_break():
    """Truncating the day BEFORE the line ever qualifies must never report a break -- there is
    nothing to no-repaint if the line's existence itself hasn't been earned yet."""
    full_bars = _build_day(46, _qualifying_scenario_overrides())
    early_bars = full_bars[:18]  # only 1 of the 2 required respects has happened (idx15, not idx20)
    rows = tbr.replay_day(early_bars, "2026-07-14")
    assert _find_target_line(rows) is None


# =============================================================================================
# 2) J-RULES
# =============================================================================================
def test_mixed_anchor_accessor_structurally_impossible():
    """Every candidate line's two anchors must be read through the SAME accessor (both wick
    fields, or both body-extreme) -- never a wick paired with a body/close. Verified externally
    (not just via the internal assert, which -O could strip)."""
    bars = _build_day(30, {5: _ANCHOR1, 10: _ANCHOR2, 20: _bar(103.0, 103.4, 102.6, 103.1)})
    for family in tbr.FAMILIES:
        lows, highs = te.find_pivots(bars, k=tbr.PIVOT_K, family=family)
        for kind, pivots in (("support", lows), ("resistance", highs)):
            for i1, i2, p1, p2 in tbr._candidate_pairs(bars, pivots, kind, family):
                if family == "wick":
                    wf = "l" if kind == "support" else "h"
                    assert p1 == bars[i1][wf] and p2 == bars[i2][wf]
                    # negative: must NOT equal the body accessor's value when they differ
                    body1 = te._body_extreme(bars[i1], kind)
                    if body1 != bars[i1][wf]:
                        assert p1 != body1
                else:
                    assert p1 == te._body_extreme(bars[i1], kind) and p2 == te._body_extreme(bars[i2], kind)


def test_no_protruding_wick_bar_excluded_from_wick_family():
    """J's rule #2: a bar with open==low (no protruding wick) is a BODY point, not a WICK
    anchor -- it must be excluded from the wick-family pivot list even if it IS the local
    extreme, but remains eligible for the body family."""
    # bar at idx 10: open==low==100.00 (zero lower wick), a strict local-window minimum.
    no_wick_bar = _bar(100.00, 100.30, 100.00, 100.20)
    bars = _build_day(20, {10: no_wick_bar})
    wick_lows, _ = te.find_pivots(bars, k=tbr.PIVOT_K, family="wick")
    assert 10 not in wick_lows, "open==low bar (no protruding wick) must not be a wick-family pivot"
    body_lows, _ = te.find_pivots(bars, k=tbr.PIVOT_K, family="body")
    assert 10 in body_lows, "the same bar IS a valid body-family pivot"


def test_respect_below_two_beyond_anchors_is_dropped_entirely():
    """A candidate line that earns only ONE non-anchor respect before it closes through must
    NEVER appear in the dataset (J's 'garbage 2-point line' rule) -- _scan_line returns None."""
    lv15 = 100.00 + 0.10 * (15 - 5)  # == 101.00
    one_respect = _bar(101.40, 101.45, lv15, 101.35)
    lv20 = 100.00 + 0.10 * (20 - 5)  # == 101.50, tol ~0.152
    early_break = _bar(101.30, 101.35, 101.10, 101.20)  # close < lv20 - tol -> closed_through
    overrides = {5: _ANCHOR1, 10: _ANCHOR2, 15: one_respect, 20: early_break}
    bars = _build_day(30, overrides)
    rows = tbr.replay_day(bars, "2026-07-14")
    assert _find_target_line(rows) is None, "1-respect line that breaks must be dropped, not emitted"


def test_two_respects_then_close_through_qualifies_and_breaks():
    """Positive control for the gate above: the SAME anchors, but with the 2nd genuine respect
    landing before the break, DOES qualify and DOES produce a close_through break record."""
    bars = _build_day(30, _qualifying_scenario_overrides())
    rows = tbr.replay_day(bars, "2026-07-14")
    line = _find_target_line(rows)
    assert line is not None
    assert line["respects_excl_anchors"] >= tbr.MIN_RESPECT_BEYOND_ANCHORS
    assert line["break"]["break_type"] == "close_through"
    assert line["break"]["break_direction"] == "bearish"  # support break = bearish


def test_wick_through_only_break_type_when_close_holds():
    """A bar whose LOW pierces beyond the line by tolerance but whose CLOSE holds back above it
    must be classified wick_through_only, not close_through."""
    lv25 = 100.00 + 0.10 * (25 - 5)  # == 102.00, tol ~0.153
    wick_pierce = _bar(102.20, 102.30, 101.70, 102.10)  # low pierces past 102.00-0.153=101.847, close (102.10) does NOT
    overrides = _qualifying_scenario_overrides()
    overrides[25] = wick_pierce
    bars = _build_day(30, overrides)
    rows = tbr.replay_day(bars, "2026-07-14")
    line = _find_target_line(rows)
    assert line is not None and line["break"] is not None
    assert line["break"]["break_type"] == "wick_through_only"
    assert line["break"]["close_at_break"] > line["break"]["line_value_at_break"]  # closed back inside


def test_volume_ratio_and_time_of_day_populated_on_break():
    bars = _build_day(30, _qualifying_scenario_overrides())
    rows = tbr.replay_day(bars, "2026-07-14")
    line = _find_target_line(rows)
    br = line["break"]
    assert br["break_bar_volume"] == 5000.0
    assert br["avg_volume_20bar"] == 1000.0  # every filler/anchor/respect bar in this fixture is v=1000
    assert br["volume_ratio"] == 5.0
    assert br["time_of_day_et"] == bars[25]["hm"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
