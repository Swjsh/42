"""RED-proofed tests for backtest/lib/right_tail_waves.py (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R1/R4).

R4 ROOT-CAUSE FIX (2026-09-05, R4 reopen): the R1 CORE_SCORE eligibility test
("bull_score/bear_score >= 9, zero blockers, deduped to unique 5-min bars via
zero_enter_autopsy._dedup_by_bar") anchored waves on the WRONG tick and used
the WRONG dedup for this purpose -- see right_tail_waves.py's module
docstring for the full discriminated hypothesis table. The fix anchors waves
directly on core-decisions.jsonl `verdict` in {ENTER_BULL, ENTER_BEAR} rows
whose `setup` is the doctrine two-trigger ribbon shape, unioned across both
core accounts (safe + bold) -- no score threshold, no bar-dedup.

RED-PROOF (this session, quoted): before the fix, `find_waves("2026-08-04")`
returned 4 waves at 10:00/13:00/13:35/15:40 ET (peaks 7.0758x/2.1849x/
1.7091x/1.1011x) -- none of which reproduce edge-master-doctrine.md's
"August 2026 big-day anatomy" anchors (09:56 cores, 12:28 second wave). The
old `test_2026_08_04_uses_core_score_mode_and_reproduces_real_waves` (which
asserted exactly those stale numbers) now FAILS against the fixed code
(confirmed: `pytest -k test_2026_08_04_uses_core_score` on the fixed
right_tail_waves.py raised `assert len(waves) == 4 ... got 5`, i.e. the old
fixture is provably wrong post-fix) -- that test's body is REPLACED below
with the real, re-verified fixed-code numbers, and the divergence from the
old (buggy) fixture IS the RED-proof for this fire's change.

Five-day reproduction (start times within 2 ticks of edge-master-doctrine.md's
"August 2026 big-day anatomy" anchors; peaks quoted from this session's
`find_waves` run, not hand-guessed):
  - 08-04: 09:56 wave (doctrine anchor, exact tick match), peak 5.4421x
    (tape truth -- real fills' best runner reached 3.29-3.34x by 13:51/13:51,
    well before the tape's own 15:45 high; existence/capture gap, not a
    detector bug -- R2's job, not R4's). 12:26 wave (doctrine anchor "12:28",
    2 ticks early), peak 3.0137x -- within 15% of the real runner exits
    (3.29x/3.34x, diff ~8-10%).
  - 08-06: 10:31 BEAR wave (doctrine anchor "10:31-10:32", exact), peak
    1.8543x -- squarely inside the real fills' realized-exit range
    (1.325x-2.117x across risky-1/risky-3/safe).
  - 08-13: 09:51 wave (doctrine anchor, exact), peak 1.875x (doctrine
    "~2.0-2.2x", diff 6-15%). 14:36 wave (doctrine anchor, exact), peak
    1.7045x (doctrine "~2.0x", diff 15% -- borderline-in-tolerance).
  - 08-27: 09:41 wave (doctrine anchor, exact) exists and clears 1.3x (peak
    2.8824x) but the tape kept drifting for hours after every arm's own
    exit (SPY 768.2->772.0 by 13:10, verified via core-decisions.jsonl `spy`
    field) -- the wave's SESSION peak legitimately exceeds what any arm's
    early trailing-stop/time exit captured (real fills capped out at
    1.30x-1.66x); flagged, not forced to match, per the anti-sycophancy rule.
    11:51 wave (doctrine anchor "11:52", 1 tick early), peak 1.9685x --
    doctrine "~2.0x", diff 1.6%, tight match.
  - 08-28: 10:21 wave (doctrine anchor, exact) exists and clears 1.3x (peak
    2.9733x); same tape-continues-past-every-exit pattern as 08-27's first
    wave (flagged, not forced).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.right_tail_waves import find_waves, WAVE_THRESHOLD  # noqa: E402
import conductor_outcome as co  # noqa: E402


def _closest_wave(waves, hh_mm: str):
    """Return the wave whose start_tick_et minute-of-day is closest to hh_mm."""
    def minute_of(ts: str) -> int:
        t = ts.split("T")[1][:5]
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    target_h, target_m = (int(x) for x in hh_mm.split(":"))
    target = target_h * 60 + target_m
    return min(waves, key=lambda w: abs(minute_of(w["start_tick_et"]) - target))


def _minute_gap(ts: str, hh_mm: str) -> int:
    t = ts.split("T")[1][:5]
    h, m = t.split(":")
    minute_of_ts = int(h) * 60 + int(m)
    target_h, target_m = (int(x) for x in hh_mm.split(":"))
    return minute_of_ts - (target_h * 60 + target_m)


def test_no_such_date_returns_empty_not_a_crash():
    """A date with no decisions data at all (weekend) fails open to []."""
    waves = find_waves("2026-08-01")  # Saturday
    assert waves == []


def test_2026_08_04_reproduces_doctrine_anchors():
    """2026-08-04 must resolve to CORE_SCORE mode and reproduce
    edge-master-doctrine.md's two named anchors: 09:56 (cores) and 12:28
    (second wave). See module docstring's RED-proof for why the OLD
    (bar-dedup, score-threshold) fixture's 10:00/13:00/13:35/15:40 numbers
    are provably wrong."""
    waves = find_waves("2026-08-04")
    assert all(w["source_mode"] == "core_score" for w in waves), waves
    assert len(waves) == 5, f"expected 5 core_score waves on 08-04, got {waves}"

    w1 = _closest_wave(waves, "09:56")
    assert abs(_minute_gap(w1["start_tick_et"], "09:56")) <= 2, w1
    assert w1["computed"] and w1["meets_threshold"], w1
    assert w1["peak_multiple"] == 5.4421, w1

    w2 = _closest_wave(waves, "12:28")
    assert abs(_minute_gap(w2["start_tick_et"], "12:28")) <= 2, w2
    assert w2["computed"] and w2["meets_threshold"], w2
    assert w2["peak_multiple"] == 3.0137, w2
    # doctrine's real-fills runner exits that wave hit 3.29x/3.34x
    # (journal/trades.csv risky-1/risky-3, 12:28 entry, 13:51 exit) --
    # the detector's tape peak is within 15% of that realized runner range.
    assert abs(w2["peak_multiple"] - 3.29) / 3.29 <= 0.15


def test_2026_08_04_core_decisions_has_date_is_true_never_fallback():
    """RED-PROOF (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R-followup): a date with
    real core-decisions.jsonl rows must never select FLEET_FALLBACK mode."""
    rows = co._decisions_for_day("2026-08-04", co.DECISIONS_FILE)
    assert len(rows) == 776, f"expected 776 real 2026-08-04 rows, got {len(rows)}"
    assert all(r.get("date") in (None, "", "2026-08-04") for r in rows)

    from lib.right_tail_waves import _core_decisions_has_date
    assert _core_decisions_has_date("2026-08-04") is True

    waves = find_waves("2026-08-04")
    assert waves and all(w["source_mode"] == "core_score" for w in waves), (
        "a date with real core-decisions.jsonl coverage must resolve to "
        f"CORE_SCORE, never fleet_fallback: {waves}"
    )


def test_2026_08_06_bear_wave_reproduces_doctrine_anchor():
    """2026-08-06 is the bear-mirror big day (edge-master-doctrine.md:
    BEARISH_REJECTION_RIDE_THE_RIBBON, 10:31-10:32). The pre-fix detector
    found 0 waves this day (bear_score at the real ENTER_BEAR tick was 8,
    below the old SCORE_THRESHOLD of 9 -- H4 confirmed: the score/blockers
    proxy does not track the engine's own verdict). Anchoring on `verdict`
    directly fixes this."""
    waves = find_waves("2026-08-06")
    assert len(waves) == 1, f"expected exactly 1 wave on 08-06, got {waves}"
    w = waves[0]
    assert w["side"] == "P"  # pricing side_char overwrites the "bull"/"bear" wave side; P = put/bear
    assert abs(_minute_gap(w["start_tick_et"], "10:31")) <= 2, w
    assert w["computed"] and w["meets_threshold"], w
    assert w["peak_multiple"] == 1.8543, w
    # real fills that day (risky-1/risky-3/safe, 770P) realized 1.325x-2.117x
    assert 1.325 <= w["peak_multiple"] <= 2.117


def test_2026_08_13_reproduces_both_doctrine_anchors():
    """2026-08-13: doctrine names 09:51 (~2.0-2.2x) and 14:36 (~2.0x)."""
    waves = find_waves("2026-08-13")
    assert all(w["source_mode"] == "core_score" for w in waves), waves

    w1 = _closest_wave(waves, "09:51")
    assert abs(_minute_gap(w1["start_tick_et"], "09:51")) <= 2, w1
    assert w1["computed"] and w1["meets_threshold"], w1
    assert w1["peak_multiple"] == 1.875, w1

    w2 = _closest_wave(waves, "14:36")
    assert abs(_minute_gap(w2["start_tick_et"], "14:36")) <= 2, w2
    assert w2["computed"] and w2["meets_threshold"], w2
    assert w2["peak_multiple"] == 1.7045, w2


def test_2026_08_27_reproduces_both_doctrine_anchors():
    """2026-08-27: doctrine names 09:41 (1.3-1.6x REALIZED exit) and 11:52
    (~2.0x). The 09:41 wave's tape peak (2.8824x) legitimately exceeds every
    arm's realized 1.30x-1.66x exit -- SPY kept drifting (768.2 -> 772.0,
    verified via core-decisions.jsonl `spy`) for hours after every arm's own
    trailing-stop/time exit. That is an existence-vs-capture gap (R2's job),
    not a detector bug -- flagged here, not forced to match by narrowing the
    pricing window (which the goal explicitly forbids: 'without tuning to
    the fixtures'). Only the 09:41 START TICK and threshold-clearance are
    asserted at doctrine tolerance; the 11:52 wave's peak DOES match
    doctrine's ~2.0x tightly (1.6% off) so its peak is asserted exactly."""
    waves = find_waves("2026-08-27")
    assert all(w["source_mode"] == "core_score" for w in waves), waves

    w1 = _closest_wave(waves, "09:41")
    assert abs(_minute_gap(w1["start_tick_et"], "09:41")) <= 2, w1
    assert w1["computed"] and w1["meets_threshold"], w1
    assert w1["peak_multiple"] == 2.8824, w1  # tape truth; see docstring

    w2 = _closest_wave(waves, "11:52")
    assert abs(_minute_gap(w2["start_tick_et"], "11:52")) <= 2, w2
    assert w2["computed"] and w2["meets_threshold"], w2
    assert w2["peak_multiple"] == 1.9685, w2
    assert abs(w2["peak_multiple"] - 2.0) / 2.0 <= 0.15


def test_2026_08_28_reproduces_doctrine_anchor():
    """2026-08-28: doctrine names 10:21 (~2.0x). Same tape-keeps-drifting
    pattern as 08-27's 09:41 wave (see that test's docstring) -- the
    detected tape peak (2.9733x) exceeds every arm's realized exit; the
    START TICK and threshold-clearance reproduce doctrine, the peak
    magnitude is a flagged existence-vs-capture gap, not forced to match."""
    waves = find_waves("2026-08-28")
    assert all(w["source_mode"] == "core_score" for w in waves), waves
    w1 = _closest_wave(waves, "10:21")
    assert abs(_minute_gap(w1["start_tick_et"], "10:21")) <= 2, w1
    assert w1["computed"] and w1["meets_threshold"], w1
    assert w1["peak_multiple"] == 2.9733, w1


def test_2026_09_02_all_bull_fills_lost_waves_dont_all_clear_threshold():
    """09-02 real fills (13 bull fills) all lost per edge-master-doctrine.md.
    CORE_SCORE mode applies. At least one wave that day does NOT clear
    1.3x (the losing-day signature)."""
    waves = find_waves("2026-09-02", account="safe")
    assert len(waves) >= 1
    assert all(w["source_mode"] == "core_score" for w in waves)
    sub_threshold = [w for w in waves if w["computed"] and w["peak_multiple"] < WAVE_THRESHOLD]
    assert sub_threshold, (
        f"expected at least one sub-1.3x wave on the all-losers day, got {waves}"
    )


def test_2026_09_03_reproduces_wave3_near_noon():
    """09-03: edge-master-doctrine.md's forward-window note says "wave 3 at
    11:07-11:22 paid +$1,597 across safe-3/risky-1/bold" -- a real ~2x wave.
    Unioned across both core accounts, the detector finds it at 11:06
    (1 tick early), peak 2.0513x (~2x)."""
    waves = find_waves("2026-09-03")
    assert all(w["source_mode"] == "core_score" for w in waves)
    w = _closest_wave(waves, "11:07")
    assert abs(_minute_gap(w["start_tick_et"], "11:07")) <= 2, w
    assert w["computed"] and w["meets_threshold"], w
    assert abs(w["peak_multiple"] - 2.0) / 2.0 <= 0.15


def test_wave_schema_has_required_fields():
    waves = find_waves("2026-08-04")
    for w in waves:
        for key in ("date", "source_mode", "start_tick_et", "side", "computed"):
            assert key in w, f"wave missing {key}: {w}"
        if w["computed"]:
            for key in ("symbol", "strike", "entry_bar_et", "entry_premium",
                        "peak_high", "peak_time_et", "peak_multiple", "meets_threshold"):
                assert key in w, f"computed wave missing {key}: {w}"
