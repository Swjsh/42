"""Guard suite for setup/scripts/trendline_human_anchor_shadow.py -- the shadow instrument
for the FROZEN "human anchor" rising-support rule (queue
TRENDLINE-RISING-SUPPORT-HUMAN-ANCHOR-SHADOW), per
analysis/recommendations/prereg-trendline-rising-support-human-anchor-2026-09-03.md.

These guards pin the mechanics that would matter if broken:
  1. A = running session-minimum low, tracked bar-by-bar, NOT a pivot itself.
  2. B = the first CONFIRMED (window k, no look-ahead) swing-low pivot above A, at least
     MIN_GAP bars after A.
  3. A line is a candidate the instant B confirms -- no third-touch gate.
  4. Re-anchor triggers: a new lower low (A resets, active line dies) OR a break (A stays,
     search restarts from the same A).
  5. TOUCH / BREAK event definitions (tolerance-bounded low vs unconditional close-break).
  6. wick vs body modes never mix within one line.
  7. Bar aggregation convention (open-of-interval, full-bucket-only 15m).
  8. Idempotent, deduped backfill -- a second run against the same cache never duplicates a
     (date_et, bar_set, anchor_mode) session_marker or its rows.

Run: cd backtest && python -m pytest tests/test_trendline_human_anchor_shadow_2026_09_03.py -v
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import trendline_human_anchor_shadow as tha  # noqa: E402


# ---------------------------------------------------------------------------------
# helpers -- build synthetic bar_dicts directly (bypasses to_barset/cache for unit tests)
# ---------------------------------------------------------------------------------
def _mkbars(rows: list[tuple[str, float, float, float, float]]) -> list[dict]:
    """rows: (HH:MM, o, h, l, c) on 2026-09-03, 5-minute spacing implied by caller order."""
    out = []
    for hhmm, o, h, l, c in rows:
        hh, mm = hhmm.split(":")
        out.append({"t_dt": dt.datetime(2026, 9, 3, int(hh), int(mm)),
                    "o": o, "h": h, "l": l, "c": c, "v": 1000.0})
    return out


def _mk_lc(rows: list[tuple[float, float]], base: dt.datetime = dt.datetime(2026, 9, 3, 9, 30),
           step: int = 5) -> list[dict]:
    """rows: (low, close) pairs, `step`-minute spacing from `base`. open=close and
    high=max(low,close)+0.5 (irrelevant to every test below -- only low/close drive the
    anchor/touch/break logic in wick mode)."""
    out = []
    for i, (l, c) in enumerate(rows):
        ts = base + dt.timedelta(minutes=step * i)
        out.append({"t_dt": ts, "o": c, "h": max(l, c) + 0.5, "l": l, "c": c, "v": 1000.0})
    return out


# A verified 5m base template: A anchors at idx1 (low=90), B confirms at idx7 (low=92,
# a genuine swing low -- neighbors idx5/6=98/99 and idx8/9=100/101 are all higher),
# confirm_idx=9 (=7+PIVOT_WINDOW). Satisfies the n>=2*k+MIN_GAP_BARS['5m']+1=11 guard and
# the gap requirement (7-1=6>=6) exactly. slope=(92-90)/(7-1)=0.33333/bar,
# line_value(j) = 90 + 0.33333*(j-1) -- e.g. line_value(11) = 93.33333.
_BASE_TEMPLATE: list[tuple[float, float]] = [
    (110, 110.5), (90, 90.5), (95, 95.5), (96, 96.5), (97, 97.5),
    (98, 98.5), (99, 99.5), (92, 92.5), (100, 100.5), (101, 101.5), (102, 102.5),
]


# ---------------------------------------------------------------------------------
# 1. A = running session minimum, not a pivot
# ---------------------------------------------------------------------------------
def test_a_is_the_running_session_minimum_not_a_pivot():
    """A steadily-declining opening sequence with no fractal pivot at its lowest bar must
    still anchor A there (A is a raw running min, never gated by the pivot test)."""
    # 09:30..09:50 strictly declining lows (no pivot at the bottom bar 09:50 -- its right
    # side never turns back up within this snippet), then a genuine reversal + swing low.
    rows = [
        ("09:30", 100.0, 100.2, 100.0, 100.1),
        ("09:35", 99.8, 100.0, 99.8, 99.9),
        ("09:40", 99.5, 99.8, 99.5, 99.6),
        ("09:45", 99.2, 99.5, 99.2, 99.3),
        ("09:50", 99.0, 99.2, 99.0, 99.1),   # session low, strictly declining into it
        ("09:55", 99.3, 99.6, 99.2, 99.5),
        ("10:00", 99.6, 99.9, 99.4, 99.8),
        ("10:05", 99.9, 100.2, 99.7, 100.1),
        ("10:10", 100.2, 100.5, 100.0, 100.4),
        ("10:15", 100.5, 100.8, 100.3, 100.7),   # B candidate region (swing low @10:20 next)
        ("10:20", 100.1, 100.3, 99.95, 100.2),   # a swing low above A=99.0
        ("10:25", 100.4, 100.7, 100.3, 100.6),
        ("10:30", 100.7, 101.0, 100.6, 100.9),   # confirms 10:20 (k=2 bars after)
        ("10:35", 101.0, 101.3, 100.9, 101.2),
    ]
    bd = _mkbars(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert lines, "expected at least one candidate line"
    assert bd[lines[0]["a_idx"]]["t_dt"].strftime("%H:%M") == "09:50"
    assert lines[0]["a_price"] == pytest.approx(99.0)


# ---------------------------------------------------------------------------------
# 2. B confirmation respects no-look-ahead (confirm_idx = b_idx + k)
# ---------------------------------------------------------------------------------
def test_b_confirm_idx_is_pivot_index_plus_window():
    bd = _mk_lc(_BASE_TEMPLATE)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert lines
    ln = lines[0]
    assert ln["b_idx"] == ln["confirm_idx"] - tha.PIVOT_WINDOW
    assert (ln["a_idx"], ln["a_price"], ln["b_idx"], ln["b_price"]) == (1, 90, 7, 92)


# ---------------------------------------------------------------------------------
# 3. gap requirement (MIN_GAP_BARS) is enforced per timeframe
# ---------------------------------------------------------------------------------
def test_b_rejected_if_too_close_to_a_on_5m():
    """A swing low only 2 bars after A (needs >=6 on 5m) must NOT become B."""
    rows = [
        ("09:30", 100.0, 100.2, 100.0, 100.1),
        ("09:35", 99.0, 99.2, 99.0, 99.1),     # A
        ("09:40", 99.3, 99.6, 99.1, 99.5),     # candidate pivot only 1 bar after A
        ("09:45", 99.6, 99.9, 99.4, 99.8),
        ("09:50", 99.9, 100.2, 99.7, 100.1),
    ]
    bd = _mkbars(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert lines == [], "gap-violating pivot must never become B"


# ---------------------------------------------------------------------------------
# 4. no third-touch gate -- a line is a candidate the instant B confirms
# ---------------------------------------------------------------------------------
def test_line_is_candidate_with_zero_touches_required():
    bd = _mk_lc(_BASE_TEMPLATE)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert len(lines) == 1
    assert len(lines[0]["touches"]) == 0
    assert lines[0]["end_reason"] == "session_end_still_active"


# ---------------------------------------------------------------------------------
# 5. re-anchor trigger 1: a new lower low kills the active line and resets A
# ---------------------------------------------------------------------------------
def test_reanchor_on_new_lower_low_kills_active_line():
    # base template (A=90@idx1, B=92@idx7, confirms idx9, active through idx10) + a bar at
    # idx11 whose low (80) undercuts A -- must kill the active line and reset A there.
    rows = _BASE_TEMPLATE + [(80, 80.5), (81, 81.5), (82, 82.5)]
    bd = _mk_lc(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert len(lines) == 1
    dead = lines[0]
    assert dead["end_reason"] == "reanchor_lower_low"
    assert dead["end_idx"] == 11
    assert dead["a_price"] == pytest.approx(90)


# ---------------------------------------------------------------------------------
# 6. re-anchor trigger 2: a break kills the line but A is NOT reset
# ---------------------------------------------------------------------------------
def test_reanchor_on_break_keeps_the_same_a():
    """After a line breaks (close far below the line), the NEXT line built from the same
    A must reuse that A's price exactly -- A is not reset by a break alone. idx10 replaces
    the base template's filler bar with a close (85) that breaks line1 (line_value(10)=93.0,
    tol=0.2) while its low (91) stays above A=90 -- no reanchor-by-lower-low, break only.
    idx11 (low=90.5, still >A) becomes the new B2, confirmed at idx13."""
    rows = list(_BASE_TEMPLATE)
    rows[10] = (91, 85.0)
    rows = rows + [(90.5, 90.9), (93, 93.3), (95, 95.3)]
    bd = _mk_lc(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert len(lines) == 2
    assert lines[0]["end_reason"] == "break"
    assert lines[0]["break_idx"] == 10
    assert lines[1]["a_price"] == pytest.approx(lines[0]["a_price"]) == pytest.approx(90)
    assert lines[1]["b_idx"] != lines[0]["b_idx"], "B must not be reused"
    assert lines[1]["b_price"] == pytest.approx(90.5)


# ---------------------------------------------------------------------------------
# 7. TOUCH definition: strict two-sided proximity on the low + close above the line
# ---------------------------------------------------------------------------------
def test_touch_requires_low_within_tolerance_and_close_above():
    """A deep wick that pierces far below the line and merely closes back above it must
    NOT count as a touch (tolerance is on the LOW, not open-ended) -- this is the exact
    T2 finding (the 10:56 wick-through at 5m never counted as a touch). line_value(11) on
    the base template = 93.33333; idx11 wicks to low=80 and closes at 95 (above line)."""
    rows = _BASE_TEMPLATE + [(80, 95.0)]
    bd = _mk_lc(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert len(lines[0]["touches"]) == 0, "a deep wick-through-and-reclaim must not count as a touch"
    assert lines[0]["break_idx"] is None


def test_touch_fires_when_low_is_within_tolerance():
    """idx11: low=93.2 (0.1333 from line_value(11)=93.33333, within tol 0.20), close=93.5
    (above the line) -> a genuine touch."""
    rows = _BASE_TEMPLATE + [(93.2, 93.5)]
    bd = _mk_lc(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert lines[0]["touches"] == [11]


# ---------------------------------------------------------------------------------
# 8. BREAK definition: close strictly below line - tol
# ---------------------------------------------------------------------------------
def test_break_requires_close_below_line_minus_tolerance():
    """idx11: close=93.1833, exactly line_value(11)(93.33333) - 0.15 -- within tol(0.20), so
    NOT a break."""
    rows = _BASE_TEMPLATE + [(93.0, 93.1833)]
    bd = _mk_lc(rows)
    lines = tha.detect_session_lines(bd, "5m", "wick")
    assert lines[0]["break_idx"] is None, "a close only within tolerance must not break the line"


# ---------------------------------------------------------------------------------
# 9. wick vs body modes never mix within one line (structural)
# ---------------------------------------------------------------------------------
def test_wick_and_body_modes_produce_independently_consistent_anchors():
    """Body mode must use min(open,close) for BOTH the running-min A and the pivot/B
    search -- never a wick value smuggled in. idx1's wick low (70) is far below its body
    (open=close=90.5) -- the two modes must anchor A at visibly different prices."""
    rows = list(_BASE_TEMPLATE)
    rows[1] = (70, 90.5)   # huge wick to 70, but body (min(open,close)) stays 90.5
    bd = _mk_lc(rows)
    lines_wick = tha.detect_session_lines(bd, "5m", "wick")
    lines_body = tha.detect_session_lines(bd, "5m", "body")
    assert lines_wick, "wick-mode line expected"
    assert lines_body, "body-mode line expected"
    assert lines_wick[0]["a_price"] == pytest.approx(70)
    assert lines_body[0]["a_price"] == pytest.approx(90.5)
    assert lines_body[0]["a_price"] != pytest.approx(lines_wick[0]["a_price"])


# ---------------------------------------------------------------------------------
# 10. aggregation convention: open-of-interval, full-bucket-only 15m
# ---------------------------------------------------------------------------------
def test_to_barset_15m_drops_partial_trailing_bucket():
    bars_1m = []
    for m in range(0, 14):   # only 14 of 15 minutes for the 09:30 bucket -- partial
        bars_1m.append({"t": f"2026-09-03T09:{30+m:02d}:00", "o": 100.0, "h": 100.1,
                        "l": 99.9, "c": 100.0, "v": 10.0})
    out = tha.to_barset(bars_1m, [], "2026-09-03", "15m", rth=False)
    assert out == [], "a partial (14/15) 1m bucket must never be scored"


def test_to_barset_15m_open_of_interval_and_ohlc_aggregation():
    bars_1m = []
    for m in range(0, 15):
        bars_1m.append({"t": f"2026-09-03T09:{30+m:02d}:00", "o": 100.0 + m * 0.01,
                        "h": 100.5 + m * 0.01, "l": 99.5 - m * 0.01, "c": 100.2 + m * 0.01,
                        "v": 10.0})
    out = tha.to_barset(bars_1m, [], "2026-09-03", "15m", rth=False)
    assert len(out) == 1
    b = out[0]
    assert b["t_dt"] == dt.datetime(2026, 9, 3, 9, 30)          # open-of-interval label
    assert b["o"] == pytest.approx(100.0)                        # first 1m open
    assert b["c"] == pytest.approx(100.2 + 14 * 0.01)            # last 1m close
    assert b["h"] == pytest.approx(max(100.5 + m * 0.01 for m in range(15)))
    assert b["l"] == pytest.approx(min(99.5 - m * 0.01 for m in range(15)))


def test_to_barset_5m_rth_filter_drops_premarket():
    bars_5m = [
        {"t": "2026-09-03T08:00:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1},
        {"t": "2026-09-03T09:30:00", "o": 2, "h": 2, "l": 2, "c": 2, "v": 1},
        {"t": "2026-09-03T09:35:00", "o": 3, "h": 3, "l": 3, "c": 3, "v": 1},
    ]
    out_rth = tha.to_barset([], bars_5m, "2026-09-03", "5m", rth=True)
    out_premkt = tha.to_barset([], bars_5m, "2026-09-03", "5m", rth=False)
    assert [b["c"] for b in out_rth] == [2, 3]
    assert [b["c"] for b in out_premkt] == [1, 2, 3]


# ---------------------------------------------------------------------------------
# 11. idempotent backfill -- second run against the same cache never duplicates rows
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"
    ledger = out_dir / "ledger.jsonl"
    summary = out_dir / "summary.json"

    date = "2026-09-01"
    bars_1m = []
    t0 = dt.datetime(2026, 9, 1, 9, 30)
    price = 100.0
    for i in range(40):
        ts = t0 + dt.timedelta(minutes=i)
        low = price - 1.0 if i == 5 else price - 0.1
        bars_1m.append({"t": ts.isoformat(), "o": price, "h": price + 0.2, "l": low,
                        "c": price + 0.05, "v": 100.0})
        price += 0.05
    (cache_dir / f"spy_1m_{date}.json").write_text(json.dumps({"bars": bars_1m}), encoding="utf-8")

    bars_5m = []
    for i in range(0, 40, 5):
        group = bars_1m[i:i + 5]
        ts = dt.datetime.fromisoformat(group[0]["t"])
        bars_5m.append({"t": ts.isoformat(), "o": group[0]["o"],
                        "h": max(g["h"] for g in group), "l": min(g["l"] for g in group),
                        "c": group[-1]["c"], "v": sum(g["v"] for g in group)})
    (cache_dir / f"spy_5m_{date}.json").write_text(json.dumps({"bars": bars_5m}), encoding="utf-8")

    monkeypatch.setattr(tha, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(tha, "OUT_DIR", out_dir)
    monkeypatch.setattr(tha, "LEDGER", ledger)
    monkeypatch.setattr(tha, "SUMMARY", summary)
    return {"ledger": ledger, "summary": summary, "date": date}


def test_run_is_idempotent_on_a_second_fire(_wired_cache):
    out1 = tha.run()
    assert "error" not in out1, out1
    rows1 = tha._read_ledger()
    assert rows1, "expected at least the session_marker rows from the backfill"
    n1 = len(rows1)

    out2 = tha.run()
    assert "error" not in out2, out2
    rows2 = tha._read_ledger()
    assert len(rows2) == n1, "a second run against an unchanged cache must add zero new rows"
    assert out2["new_rows_this_run"] == 0

    markers = tha._processed_session_configs(rows2)
    expected = {(_wired_cache["date"], bs, m) for bs in tha.BAR_SETS for m in tha.ANCHOR_MODES}
    assert markers == expected, "every bar_set x anchor_mode combo must be marked processed exactly once"


def test_run_flags_in_sample_correctly(_wired_cache):
    out = tha.run()
    rows = tha._read_ledger()
    markers = [r for r in rows if r["kind"] == "session_marker"]
    assert markers
    for m in markers:
        assert m["in_sample"] is True, "2026-09-01 <= cutoff 2026-09-03 must be in_sample"


# ---------------------------------------------------------------------------------
# 12. summary shape sanity (decision block present, forward-only gating fields exist)
# ---------------------------------------------------------------------------------
def test_summarize_shape_has_decision_block_and_forward_split():
    rows = [
        {"kind": "session_marker", "date_et": "2026-09-01", "bar_set": "5m_premkt",
         "anchor_mode": "wick", "in_sample": True, "n_bars": 10, "n_lines": 0,
         "n_touches": 0, "n_breaks": 0},
    ]
    for bs in tha.BAR_SETS:
        for m in tha.ANCHOR_MODES:
            if bs == "5m_premkt" and m == "wick":
                continue
            rows.append({"kind": "session_marker", "date_et": "2026-09-01", "bar_set": bs,
                        "anchor_mode": m, "in_sample": True, "n_bars": 10, "n_lines": 0,
                        "n_touches": 0, "n_breaks": 0})
    s = tha._summarize(rows)
    assert "decision" in s
    for bs in tha.PRIMARY_BAR_SETS:
        for etype in ("touch", "break"):
            key = f"{bs}|{etype}"
            assert key in s["decision"], key
            assert s["decision"][key]["status"] in (
                "ACCRUING", "BAR_MET_DATE_GATED", "SUPPORTED_PROCEED_TO_RATIFICATION",
                "FALSIFIED", "BAR_MET_INCONCLUSIVE")
    assert s["decision"][f"{tha.PRIMARY_BAR_SETS[0]}|touch"]["bar_met"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
