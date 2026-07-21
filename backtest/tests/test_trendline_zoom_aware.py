"""Guard for T16 (2026-07-21, TRENDLINE-FIXES-2026-07-17 item 3): zoom-aware drawing.

J's complaint (queue.md, filed 2026-07-17): "multi-day rails at intraday zoom read as noise...
a blind person drew them." Proposed rule: "only render lines whose anchor span overlaps the
visible ~2-day window, or label-offset placement." This implements the label-offset branch as a
pure, testable CLASSIFICATION (`zoom_classify` + `Trendline.zoom_class`) -- the actual on-chart
rendering decision (does the label render at the anchor or near the current end of the line)
still lives in the trendline-draw skill's live TV session, which is the only thing with a real
`chart_get_state` view of the chart's true visible range. This mechanism-level guard proves the
classification is correct and no-look-ahead; full on-chart visual validation via a real
screenshot is explicitly DEFERRED to the next live TV session (same shipping pattern as T15's
same-day tier: SHADOW-only, `write_live_state`'s own docstring says "the engine does NOT trade
off these yet", so no P&L A/B applies -- a mechanism-correctness guard is the right bar).

Run: cd backtest && python -m pytest tests/test_trendline_zoom_aware.py -v
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))

import trendline_engine as te  # noqa: E402


def _mkbar(t: _dt.datetime, lo: float) -> dict:
    """A bar whose low is exactly `lo`, with a real protruding wick (clears
    _has_protruding_wick: min(o,c)-l = 0.20 >= max(WICK_MIN_CENTS, 0.10*range))."""
    o, c = lo + 0.20, lo + 0.25
    h = max(o, c) + 0.05
    return {"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": round(o, 2), "h": round(h, 2),
            "l": round(lo, 2), "c": round(c, 2), "v": 1000.0}


def _day_bars(start: _dt.datetime, n: int, touches: dict[int, float], flat: float) -> list[dict]:
    out, t = [], start
    for i in range(n):
        out.append(_mkbar(t, touches.get(i, flat)))
        t += _dt.timedelta(minutes=5)
    return out


def _two_day_fixture() -> tuple[list[dict], list[dict], list[dict]]:
    """DAY1 (2026-07-14) is an old 4-touch line -- 6 CALENDAR days before DAY2, well outside any
    ~2-day zoom window ending on DAY2 (deliberately more than a bare single-day gap, so the
    zoom_class assertions below aren't sensitive to exact intraday minute placement). DAY2
    (2026-07-20, "today") has its own fresh 2-touch line in a disjoint price range (anchor is
    same-day, well inside any zoom window)."""
    day1_start = _dt.datetime(2026, 7, 14, 13, 30, tzinfo=_dt.timezone.utc)
    day1_touches = {2: 700.00, 6: 700.40, 10: 700.80, 14: 701.20}
    day1 = _day_bars(day1_start, 16, day1_touches, flat=705.00)

    day2_start = _dt.datetime(2026, 7, 20, 13, 30, tzinfo=_dt.timezone.utc)
    day2_touches = {3: 750.00, 9: 750.60}
    day2 = _day_bars(day2_start, 16, day2_touches, flat=755.00)

    return day1, day2, day1 + day2


# ---------------------------------------------------------------------------
# zoom_classify() -- the pure classification function
# ---------------------------------------------------------------------------

def test_zoom_classify_in_window_at_exact_boundary() -> None:
    """Anchor exactly `window_days` back is INCLUSIVE (>= window_start) -- matches the file's
    established >= convention (mirrors _bar_date_et's == grouping direction of "recent wins")."""
    now_unix = 1_000_000
    window_start = now_unix - int(2.0 * 86400)
    assert te.zoom_classify(window_start, now_unix) == "in_window"


def test_zoom_classify_one_second_inside_window() -> None:
    now_unix = 1_000_000
    a_unix = now_unix - int(2.0 * 86400) + 1
    assert te.zoom_classify(a_unix, now_unix) == "in_window"


def test_zoom_classify_one_second_outside_window() -> None:
    now_unix = 1_000_000
    a_unix = now_unix - int(2.0 * 86400) - 1
    assert te.zoom_classify(a_unix, now_unix) == "anchor_offscreen"


def test_zoom_classify_anchor_in_the_future_is_in_window() -> None:
    """Degenerate/defensive case: an anchor at or after "now" is trivially in-window."""
    now_unix = 1_000_000
    assert te.zoom_classify(now_unix, now_unix) == "in_window"
    assert te.zoom_classify(now_unix + 500, now_unix) == "in_window"


def test_zoom_classify_custom_window_days() -> None:
    now_unix = 1_000_000
    a_unix = now_unix - int(5.0 * 86400) + 10
    assert te.zoom_classify(a_unix, now_unix, window_days=5.0) == "in_window"
    assert te.zoom_classify(a_unix, now_unix, window_days=1.0) == "anchor_offscreen"


# ---------------------------------------------------------------------------
# detect(include_zoom_class=...) wiring
# ---------------------------------------------------------------------------

def test_default_behavior_unchanged_no_zoom_class_opt_in() -> None:
    """Byte-identical to pre-T16 behavior when the caller does not opt in -- every line keeps
    the dataclass default 'in_window', regardless of how stale its real anchor is."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",))  # no include_zoom_class kwarg at all
    for ln in lines:
        assert ln.zoom_class == "in_window"


def test_include_zoom_class_false_explicit_matches_default() -> None:
    _, _, bars = _two_day_fixture()
    lines_default = te.detect(bars, families=("wick",))
    lines_explicit_false = te.detect(bars, families=("wick",), include_zoom_class=False)
    assert lines_default == lines_explicit_false


def test_old_anchor_classified_anchor_offscreen() -> None:
    """DAY1's line anchors on 07-14; using DAY2 (07-20) as 'now' (the last bar in the combined
    store), a 2-day zoom window ending 07-20 EOD does not reach back to 07-14's anchor bar ->
    anchor_offscreen. This is the exact "multi-day rail at intraday zoom" case J flagged."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",), include_zoom_class=True)
    day1_line = next(ln for ln in lines if ln.a_et.startswith("07-14"))
    assert day1_line.zoom_class == "anchor_offscreen", day1_line


def test_fresh_same_day_anchor_classified_in_window() -> None:
    """A line whose own anchor IS within the zoom window (same trading day as 'now') stays
    in_window -- day2-only fixture, so its own primary line anchors on 07-20."""
    _, day2, _ = _two_day_fixture()
    lines = te.detect(day2, families=("wick",), include_zoom_class=True)
    line = next(ln for ln in lines if ln.kind == "support")
    assert line.a_et.startswith("07-20")
    assert line.zoom_class == "in_window", line


def test_zoom_class_does_not_change_line_selection_or_count() -> None:
    """Purely additive classification -- opting in must not change which lines are returned,
    their order, or their count vs. the same call without the opt-in (beyond the zoom_class
    field itself)."""
    _, _, bars = _two_day_fixture()
    lines_off = te.detect(bars, families=("wick",), include_zoom_class=False)
    lines_on = te.detect(bars, families=("wick",), include_zoom_class=True)
    assert len(lines_off) == len(lines_on)
    for off, on in zip(lines_off, lines_on):
        # every field except zoom_class must be identical
        from dataclasses import replace as _replace
        assert _replace(on, zoom_class=off.zoom_class) == off


def test_zoom_class_composes_with_same_day_tier() -> None:
    """Both T15 (same_day tier) and T16 (zoom_class) opt-ins together must not crash and must
    each behave per their own contract simultaneously -- this is the live main() combination."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",), include_same_day_tier=True, include_zoom_class=True)
    primary = next(ln for ln in lines if ln.kind == "support" and ln.tier == "primary")
    same_day = next(ln for ln in lines if ln.kind == "support" and ln.tier == "same_day")
    assert primary.zoom_class == "anchor_offscreen", primary  # anchors 07-14, stale vs 07-20 "now"
    assert same_day.zoom_class == "in_window", same_day       # anchors 07-20, fresh


def test_zoom_class_no_lookahead() -> None:
    """C6 invariant, same pattern as test_same_day_tier_no_lookahead: truncating the bar list to
    a point PARTWAY through today must give the SAME zoom_class result as truncating at that
    exact same point in a longer store that has more bars appended strictly AFTER it -- 'now' is
    always the last bar the caller passed in, never wall-clock time or a future bar."""
    day1, day2, bars = _two_day_fixture()
    idx = len(day1) + 9
    short_store = bars[: idx + 1]
    future_start = _dt.datetime.fromisoformat(day2[-1]["t"].replace("Z", "+00:00")) + _dt.timedelta(minutes=5)
    future_bars = _day_bars(future_start, 10, {}, flat=756.00)
    long_store = bars[: idx + 1] + future_bars + bars[idx + 1:]

    lines_short = te.detect(short_store, families=("wick",), include_zoom_class=True)
    lines_long_truncated = te.detect(long_store[: idx + 1], families=("wick",), include_zoom_class=True)
    assert lines_short == lines_long_truncated, (
        "zoom_class result at truncation point T changed when more bars existed after T in the "
        "underlying store -- this is a look-ahead leak"
    )


def test_write_live_state_carries_zoom_class_field(tmp_path, monkeypatch) -> None:
    """The shadow-state JSON (consumed by the trendline-draw skill / self_check / dashboard)
    must carry `zoom_class` per line -- additive field, non-breaking for readers that ignore
    unknown keys."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",), include_same_day_tier=True, include_zoom_class=True)
    live_state_path = tmp_path / "trendlines-live.json"
    monkeypatch.setattr(te, "LIVE_STATE", live_state_path)
    te.write_live_state(lines, "2026-07-20")
    import json
    payload = json.loads(live_state_path.read_text(encoding="utf-8"))
    zoom_classes = {t["zoom_class"] for t in payload["trendlines"]}
    assert zoom_classes == {"in_window", "anchor_offscreen"}, zoom_classes
