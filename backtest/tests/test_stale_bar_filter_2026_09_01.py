"""Guard: analysis consumers of core-decisions.jsonl must drop stale-bar rows.

SCAR (2026-09-01, found by the give-back review). Every session opens with ~6 ticks per arm
scored against the PRIOR session's closing bar -- `bar_freshness.stale=true`, age 1056-1060
minutes -- before the first fresh print at 09:36. Present in each of the last 7 sessions.

The engine was never fooled: all 12 stale rows on 2026-09-01 were HOLD. The ANALYSIS was.
Those rows carry spy=767.40 (the prior 15:50 bar) while SPY actually opened 761.91, so the
apparent session range was $7.54 against a real $4.71 -- $2.83 of phantom range. Session
high/low, range_position and any entry-location study computed over unfiltered rows inherit
that error, and it was reported to J twice as fact before anyone checked the flag.

The flag was logged on all 766 rows/day the whole time. A repo-wide grep for `bar_freshness`
returned only its writer (heartbeat_core.py) and two guard tests: ZERO analysis consumers
filtered on it. A field that every producer writes and no consumer reads is not a safeguard.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

rsl = importlib.import_module("refused_setup_ledger")

FRESH = {"checked": True, "stale": False, "age_min": 4.0}
STALE = {"checked": True, "stale": True, "age_min": 1060.08,
         "bar_et": "2026-08-31T15:50:00-04:00"}


def _row(ts: str, spy: float, freshness: dict, account: str = "safe") -> str:
    return json.dumps({
        "ts_et": ts, "account": account, "spy": spy, "verdict": "HOLD",
        "bar_freshness": freshness, "bear_score": 7,
        "bear_triggers_raw": ["trendline_rejection"], "bear_blockers": [8],
    })


def test_stale_opening_rows_are_dropped(tmp_path, monkeypatch):
    """The real 2026-09-01 shape: prior-session bars at 767.40, real open 761.91."""
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("\n".join([
        _row("2026-09-01T09:30:04", 767.40, STALE),     # yesterday's 15:50 bar
        _row("2026-09-01T09:31:03", 766.87, STALE),     # yesterday's 15:55 bar
        _row("2026-09-01T09:36:03", 761.91, FRESH),     # first REAL print
        _row("2026-09-01T14:46:03", 759.86, FRESH),     # session low
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(rsl, "DECISIONS", p)

    rows = rsl.load_rows("2026-09-01")
    assert len(rows) == 2, f"stale rows survived the filter: {[r['spy'] for r in rows]}"
    prices = [r["spy"] for r in rows]
    assert 767.40 not in prices and 766.87 not in prices

    # The property that actually matters: the derived range is the REAL one.
    assert max(prices) - min(prices) == 761.91 - 759.86
    assert max(prices) == 761.91, "phantom session high leaked through"


def test_phantom_range_matches_the_measured_2_83(tmp_path, monkeypatch):
    """Pins the magnitude actually measured on 2026-09-01 so a regression is obvious.

    Live figures from the full session: all-ticks span $7.54 (high 767.40, low 759.86);
    fresh-only span $4.71 (high 764.57, low 759.86). Phantom inflation = $2.83.
    """
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("\n".join([
        _row("2026-09-01T09:30:04", 767.40, STALE),    # prior-session high, phantom
        _row("2026-09-01T09:36:03", 761.91, FRESH),    # first real print
        _row("2026-09-01T10:15:00", 764.57, FRESH),    # true RTH high
        _row("2026-09-01T14:46:03", 759.86, FRESH),    # true RTH low
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(rsl, "DECISIONS", p)

    filtered = [r["spy"] for r in rsl.load_rows("2026-09-01")]
    unfiltered = [767.40, 761.91, 764.57, 759.86]

    real_span = max(filtered) - min(filtered)
    fake_span = max(unfiltered) - min(unfiltered)
    assert round(real_span, 2) == 4.71, "filtered range is not the real session range"
    assert round(fake_span, 2) == 7.54
    assert round(fake_span - real_span, 2) == 2.83, "phantom inflation drifted from measured"


def test_rows_without_the_field_are_kept(tmp_path, monkeypatch):
    """Fail OPEN: older rows predate bar_freshness and must not silently vanish."""
    p = tmp_path / "core-decisions.jsonl"
    p.write_text("\n".join([
        json.dumps({"ts_et": "2026-09-01T10:00:00", "account": "safe", "spy": 761.0,
                    "verdict": "HOLD", "bear_score": 7,
                    "bear_triggers_raw": ["x"], "bear_blockers": [8]}),
        _row("2026-09-01T10:01:00", 760.9, FRESH),
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(rsl, "DECISIONS", p)
    assert len(rsl.load_rows("2026-09-01")) == 2


def test_checked_false_is_not_treated_as_stale(tmp_path, monkeypatch):
    """`checked:false` means unknown, not stale -- dropping it would lose real ticks."""
    p = tmp_path / "core-decisions.jsonl"
    p.write_text(_row("2026-09-01T10:00:00", 761.0,
                      {"checked": False, "stale": False}) + "\n", encoding="utf-8")
    monkeypatch.setattr(rsl, "DECISIONS", p)
    assert len(rsl.load_rows("2026-09-01")) == 1
