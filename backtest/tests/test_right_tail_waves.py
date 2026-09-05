"""RED-proofed tests for backtest/lib/right_tail_waves.py (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R1).

Fixtures per the goal's DONE-WHEN:
  - 2026-08-04: SECOND EVIDENCE CORRECTION (2026-09-05, conductor_outcome.py
    `_decisions_for_day` truncation fix): the R1 fixture below originally
    asserted FLEET_FALLBACK mode for this date, on the claim that
    core-decisions.jsonl "has NO rows before 2026-08-26". That claim was
    FALSE -- `_decisions_for_day` filtered strictly on a `date` key that
    heartbeat_core.py only started injecting on 2026-08-25 (DEFECT-A fix);
    every row before that carries `ts_et` only, so the filter silently
    dropped 776 real 2026-08-04 rows. `_decisions_for_day` (setup/scripts/
    conductor_outcome.py) now falls back to `ts_et[:10]` when `date` is
    absent (`_row_day`), so 2026-08-04 correctly resolves to CORE_SCORE mode.
    Re-verified against the real ledger (`python -m backtest.lib.
    right_tail_waves --date 2026-08-04`): 4 waves at 10:00/13:00/13:35/15:40
    ET, peaks 7.0758x / 2.1849x / 1.7091x / 1.1011x (3 of 4 clear 1.3x). This
    does NOT reproduce the old FLEET_FALLBACK-era "09:58 ~5.4x / 12:28 ~3.0x"
    figures the goal text and SUMMARY.md quoted -- CORE_SCORE mode is
    anchored to the `safe` core account's own admission ticks (bull_score>=9,
    zero blockers, deduped to unique 5-min bars via zero_enter_autopsy's
    `_dedup_by_bar`, "last occurrence wins" per bar), a genuinely different
    and independent eligibility source from the fleet-arms' own admission
    gates the old FLEET_FALLBACK anchor used -- not a further bug in this
    reader fix, just a different (and now correct-per-goal-spec) source.
    Fixture updated to the real, re-verified numbers per the anti-sycophancy
    rule (say so when evidence disagrees, don't force the fixture to match a
    stale guess).
  - 2026-09-02: 13 bull fills, all lost (-$699, edge-master-doctrine.md).
    EVIDENCE CORRECTION (2026-09-05): the goal text guessed "expect waves
    present but peak < 1.3x, or none" -- the actual computed peaks are
    1.46x and 1.35x (2 of 4 waves DO clear 1.3x) alongside 1.25x and 1.04x
    (2 do not). The goal's guess was wrong; this is exactly the
    existence-vs-capture gap R2 is built to score (a wave existed on tape,
    the arm's real fills still lost) -- so this test asserts the true
    computed numbers, not the guessed ones, per the anti-sycophancy rule
    (say so when evidence disagrees, don't force the fixture to match a
    guess).
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
        # ts like "2026-08-04T09:58:05" or with a "-04:00" suffix
        t = ts.split("T")[1][:5]
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    target_h, target_m = (int(x) for x in hh_mm.split(":"))
    target = target_h * 60 + target_m
    return min(waves, key=lambda w: abs(minute_of(w["start_tick_et"]) - target))


def test_no_such_date_returns_empty_not_a_crash():
    """A date with no decisions data at all (weekend) fails open to []."""
    waves = find_waves("2026-08-01")  # Saturday
    assert waves == []


def test_2026_08_04_uses_core_score_mode_and_reproduces_real_waves():
    """Post-fix: 2026-08-04 has 776 real core-decisions.jsonl rows (ts_et-only,
    pre-dating the 2026-08-25 `date`-field injection) and must resolve to
    CORE_SCORE mode, not FLEET_FALLBACK. Numbers re-verified directly against
    `find_waves` this session -- see module docstring's evidence correction."""
    waves = find_waves("2026-08-04")
    assert len(waves) == 4, f"expected exactly 4 core_score waves on 08-04, got {waves}"
    assert all(w["source_mode"] == "core_score" for w in waves), (
        f"08-04 has real core-decisions.jsonl rows -- must never fall back: {waves}"
    )

    expected = [
        ("10:00", 7.0758, True),
        ("13:00", 2.1849, True),
        ("13:35", 1.7091, True),
        ("15:40", 1.1011, False),
    ]
    for (hh_mm, peak, meets) in expected:
        w = _closest_wave(waves, hh_mm)
        assert w["computed"] is True
        assert abs(_minute_gap(w["start_tick_et"], hh_mm)) <= 2, w
        assert w["peak_multiple"] == peak, (
            f"{hh_mm} wave peak {w['peak_multiple']} != re-verified {peak}: {w}"
        )
        assert w["meets_threshold"] is meets, w

    n_meeting = sum(1 for w in waves if w["meets_threshold"])
    assert n_meeting == 3, f"expected 3 of 4 waves to clear 1.3x, got {n_meeting}: {waves}"


def test_2026_08_04_core_decisions_has_date_is_true_never_fallback():
    """RED-PROOF (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R-followup): a date with
    real core-decisions.jsonl rows must never select FLEET_FALLBACK mode.
    This directly exercises the fixed `_core_decisions_has_date` /
    `_decisions_for_day` path (`co._row_day` ts_et fallback) that a pre-fix
    reader (filtering strictly on the `date` key) would fail -- confirmed by
    running this exact assertion against a copied pre-fix `conductor_outcome.py`
    in the same session (see the goal fire's RED-proof transcript): 0 rows /
    FAIL pre-fix, 776 rows / PASS post-fix."""
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


def test_2026_09_02_all_bull_fills_lost_waves_dont_all_clear_threshold():
    """09-02 real fills (13 bull fills) all lost per edge-master-doctrine.md.
    CORE_SCORE mode applies (09-02 >= 08-26). Evidence correction: at least
    one wave that day does NOT clear 1.3x (the losing-day signature), even
    though not every wave misses it -- see module docstring's correction."""
    waves = find_waves("2026-09-02", account="safe")
    assert len(waves) >= 1
    assert all(w["source_mode"] == "core_score" for w in waves)
    sub_threshold = [w for w in waves if w["computed"] and w["peak_multiple"] < WAVE_THRESHOLD]
    assert sub_threshold, (
        f"expected at least one sub-1.3x wave on the all-losers day, got {waves}"
    )


def test_wave_schema_has_required_fields():
    waves = find_waves("2026-08-04")
    for w in waves:
        for key in ("date", "source_mode", "start_tick_et", "side", "computed"):
            assert key in w, f"wave missing {key}: {w}"
        if w["computed"]:
            for key in ("symbol", "strike", "entry_bar_et", "entry_premium",
                        "peak_high", "peak_time_et", "peak_multiple", "meets_threshold"):
                assert key in w, f"computed wave missing {key}: {w}"


def _minute_gap(ts: str, hh_mm: str) -> int:
    t = ts.split("T")[1][:5]
    h, m = t.split(":")
    minute_of_ts = int(h) * 60 + int(m)
    target_h, target_m = (int(x) for x in hh_mm.split(":"))
    return minute_of_ts - (target_h * 60 + target_m)
