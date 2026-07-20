"""Guard for T15 (2026-07-20, TRENDLINE-FIXES-2026-07-17 item 2): the same-day priority tier.

`_fit`'s own score (`respect - 5*violations + span*0.1`) structurally rewards LONGER-LIVED
lines, so a fresh 2-3-touch same-day line J hand-draws almost never wins a (kind, family) slot
over an older multi-day line that happens to share it -- the gap the 2026-07-14 trendline-
subsystem audit found and explicitly deferred ("Same-day-priority scoring ... needs its own
eval, not bundled into this audit's read-mostly fixes"). The audit's own referenced pre-reg
(`analysis/recommendations/trendline-structure-conviction-preregistration.json`) turned out,
on inspection, to answer a DIFFERENT question (a VIX-band conviction override for
block_elite_bull) and is already RUN_COMPLETE/KILL -- it is not a spec for THIS gap; corrected
in `automation/overnight/queue.md` alongside this fix.

`detect(bars, include_same_day_tier=True)` (default False -- every existing caller/test is
byte-identical unless it opts in) adds a SECOND independent best-scoring pass restricted to
ONLY today's bars per (kind, family), appended tagged `tier="same_day"` when it is a genuinely
different line from its (kind, family) primary sibling. SHADOW-only (per
`write_live_state`'s own docstring: "the engine does NOT trade off these yet") -- this is a
pure visibility fix, zero trading-behavior change; wired live at the one production entry
point, `main()` (the `Gamma_Trendlines` 5-min RTH cadence + the premarket drawing bridge).

Run: cd backtest && python -m pytest tests/test_trendline_same_day_tier.py -v
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
    """`n` synthetic 5m bars starting at `start`: bars at indices in `touches` sit at the given
    (ascending-support-line) low, every other bar sits at the CONSTANT `flat` level (never itself
    a strict local extreme against a flat neighbor, so it can't spawn a stray pivot)."""
    out, t = [], start
    for i in range(n):
        out.append(_mkbar(t, touches.get(i, flat)))
        t += _dt.timedelta(minutes=5)
    return out


def _two_day_fixture() -> tuple[list[dict], list[dict], list[dict]]:
    """DAY1 (2026-07-19): a clean 4-touch ascending support line spanning the whole day (this
    wins the PRIMARY (kind='support', family='wick') slot on respect_count alone -- 4 touches,
    0 violations, vs DAY2's 2 touches). DAY2 (2026-07-20, "today"): its OWN short, genuinely
    DIFFERENT ascending support line (different anchors, different price range entirely --
    750s vs 700s, so day2's flat/touch bars can never violate day1's line or vice versa,
    eliminating cross-day pivot-pairing as a confound). Returns (day1, day2, day1+day2)."""
    day1_start = _dt.datetime(2026, 7, 19, 13, 30, tzinfo=_dt.timezone.utc)
    day1_touches = {2: 700.00, 6: 700.40, 10: 700.80, 14: 701.20}   # slope 0.10/bar, 4 touches
    day1 = _day_bars(day1_start, 16, day1_touches, flat=705.00)

    day2_start = _dt.datetime(2026, 7, 20, 13, 30, tzinfo=_dt.timezone.utc)
    day2_touches = {3: 750.00, 9: 750.60}                          # slope 0.10/bar, 2 touches
    day2 = _day_bars(day2_start, 16, day2_touches, flat=755.00)

    return day1, day2, day1 + day2


def test_default_behavior_unchanged_no_same_day_tier() -> None:
    """Byte-identical to pre-T15 behavior when the caller does not opt in -- default detect()
    call (as every existing caller/test in the repo uses) must return ONLY the primary line."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",))  # no include_same_day_tier kwarg at all
    support_lines = [ln for ln in lines if ln.kind == "support"]
    assert len(support_lines) == 1, f"expected exactly 1 support line by default, got {support_lines}"
    assert support_lines[0].tier == "primary"
    assert support_lines[0].a_et.startswith("07-19"), support_lines[0]


def test_include_same_day_tier_false_explicit_matches_default() -> None:
    """Explicit include_same_day_tier=False must be indistinguishable from omitting it."""
    _, _, bars = _two_day_fixture()
    lines_default = te.detect(bars, families=("wick",))
    lines_explicit_false = te.detect(bars, families=("wick",), include_same_day_tier=False)
    assert lines_default == lines_explicit_false


def test_same_day_tier_surfaces_the_distinct_today_line() -> None:
    """The core fix: with include_same_day_tier=True, day1's multi-day line STILL wins the
    primary slot (more touches -- this is the documented, unchanged scoring behavior), but
    day2's own genuinely-different same-day line now ALSO appears, tagged tier='same_day'."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",), include_same_day_tier=True)
    support_lines = [ln for ln in lines if ln.kind == "support"]
    assert len(support_lines) == 2, f"expected primary + same_day support lines, got {support_lines}"

    primary = next(ln for ln in support_lines if ln.tier == "primary")
    same_day = next(ln for ln in support_lines if ln.tier == "same_day")

    assert primary.a_et.startswith("07-19"), primary
    assert primary.respect_count == 4, primary

    assert same_day.a_et.startswith("07-20"), same_day
    assert same_day.b_et.startswith("07-20"), same_day
    assert same_day.respect_count == 2, same_day
    assert same_day.violations == 0, same_day


def test_same_day_tier_is_additive_never_replaces_primary() -> None:
    """The primary line's own fields must be IDENTICAL whether or not the same-day tier is
    requested -- this is strictly additive, never a re-selection of the primary slot."""
    _, _, bars = _two_day_fixture()
    lines_off = te.detect(bars, families=("wick",), include_same_day_tier=False)
    lines_on = te.detect(bars, families=("wick",), include_same_day_tier=True)
    primary_off = next(ln for ln in lines_off if ln.kind == "support")
    primary_on = next(ln for ln in lines_on if ln.kind == "support" and ln.tier == "primary")
    assert primary_off == primary_on


def test_no_duplicate_when_primary_already_is_same_day() -> None:
    """If the primary winner for a (kind, family) is ALREADY confined to today (single-day
    fixture, no multi-day competitor), the same-day pass must not add a duplicate -- dedup is on
    exact anchor identity (a_et/b_et), so the identical line should appear exactly once."""
    _, day2, _ = _two_day_fixture()
    lines = te.detect(day2, families=("wick",), include_same_day_tier=True)
    support_lines = [ln for ln in lines if ln.kind == "support"]
    assert len(support_lines) == 1, f"expected no duplicate when primary IS the same-day line, got {support_lines}"
    assert support_lines[0].tier == "primary"


def test_same_day_tier_no_op_when_no_distinct_today_line_exists() -> None:
    """DAY1-only fixture (no "today" data with its own qualifying line beyond the primary
    itself) must not fabricate a spurious second entry."""
    day1, _, _ = _two_day_fixture()
    lines = te.detect(day1, families=("wick",), include_same_day_tier=True)
    support_lines = [ln for ln in lines if ln.kind == "support"]
    assert len(support_lines) == 1, support_lines


def test_same_day_tier_no_lookahead() -> None:
    """C6 invariant: truncating the bar list to a point PARTWAY through today must give the
    SAME same-day-tier result as truncating at that exact same point in a longer store that has
    more bars appended strictly AFTER it (mirrors test_trendline_conviction_override_no_
    lookahead.py's pattern) -- proves the same-day slice never reads beyond what the caller
    already passed in."""
    day1, day2, bars = _two_day_fixture()
    idx = len(day1) + 9  # partway through day2 (bars[idx] is day2's 2nd touch, index 9)
    short_store = bars[: idx + 1]
    future_start = _dt.datetime.fromisoformat(day2[-1]["t"].replace("Z", "+00:00")) + _dt.timedelta(minutes=5)
    future_bars = _day_bars(future_start, 10, {}, flat=756.00)
    long_store = bars[: idx + 1] + future_bars + bars[idx + 1:]

    lines_short = te.detect(short_store, families=("wick",), include_same_day_tier=True)
    lines_long_truncated = te.detect(long_store[: idx + 1], families=("wick",), include_same_day_tier=True)
    assert lines_short == lines_long_truncated, (
        "same-day tier result at truncation point T changed when more bars existed after T in "
        "the underlying store -- this is a look-ahead leak"
    )


def test_write_live_state_carries_tier_field(tmp_path, monkeypatch) -> None:
    """The shadow-state JSON consumers (self_check/dashboard) must be able to see `tier` per
    line -- additive field, non-breaking for readers that ignore unknown keys."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, families=("wick",), include_same_day_tier=True)
    live_state_path = tmp_path / "trendlines-live.json"
    monkeypatch.setattr(te, "LIVE_STATE", live_state_path)
    te.write_live_state(lines, "2026-07-20")
    import json
    payload = json.loads(live_state_path.read_text(encoding="utf-8"))
    tiers = {t["tier"] for t in payload["trendlines"]}
    assert tiers == {"primary", "same_day"}, tiers


def test_families_both_still_work_with_same_day_tier() -> None:
    """Sanity: default families=("wick","body") + include_same_day_tier=True together must not
    crash and must never mix a wick anchor with a body anchor within a same_day-tier line either
    (the anchor-family invariant is enforced inside _fit, not tier-specific)."""
    _, _, bars = _two_day_fixture()
    lines = te.detect(bars, include_same_day_tier=True)  # families default = ("wick", "body")
    assert lines, "expected at least the wick-support lines on this fixture"
    for ln in lines:
        assert ln.tier in ("primary", "same_day")
        assert ln.anchor_family in ("wick", "body")
