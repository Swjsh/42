"""Guard for setup/scripts/tail_frequency_tracker.py (PREREG-TAIL-FREQUENCY-2026-09-10).

WHAT THIS PROTECTS
------------------
The tracker scores a pre-registered hypothesis whose H0 branch ("<= 1 tail day")
recommends a KILL conversation on the engine's signal. That makes two failure modes
expensive and ASYMMETRIC:

  1. A silent zero. If the source file goes missing/unparseable and the tracker
     returns 0 tail days instead of raising, the output reads as strong evidence
     for H0 -- i.e. a data outage would argue for killing a working strategy.
     This is the rig's signature C7 failure (silent success is failure).
  2. A verdict on thin data. Calling H0_SUPPORTED off 2 trading days is exactly
     the undersampling error the whole prereg exists to avoid.

It also pins the decision rule itself, because a threshold that drifts after the
data arrives is no longer a pre-registration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import tail_frequency_tracker as tft  # noqa: E402


# --- 1. the frozen decision rule -------------------------------------------------

@pytest.mark.parametrize(
    "n_tail,n_days,expected",
    [
        (7, 20, "H1_SUPPORTED"),     # August's real shape
        (4, 30, "H1_SUPPORTED"),     # exactly at the H1 boundary
        (3, 30, "AMBIGUOUS"),
        (2, 30, "AMBIGUOUS"),
        (1, 30, "H0_SUPPORTED"),     # exactly at the H0 boundary
        (0, 30, "H0_SUPPORTED"),
    ],
)
def test_decision_rule_matches_the_frozen_prereg(n_tail, n_days, expected):
    got, _ = tft.verdict(n_tail, n_days)
    assert got == expected, (
        f"decision rule drifted: {n_tail} tail days over {n_days} days -> {got}, "
        f"prereg says {expected}. A threshold that moves after the data arrives "
        f"is not a pre-registration."
    )


def test_thresholds_match_the_prereg_file_verbatim():
    """The prereg JSON is the contract; the code must not quietly diverge from it."""
    prereg = json.loads(tft.PREREG.read_text(encoding="utf-8"))
    rule = prereg["decision_rule"]
    assert ">= 4" in rule["H1_SUPPORTED"]
    assert "<= 1" in rule["H0_SUPPORTED"]
    assert prereg["observation_window"]["starts"] == tft.WINDOW_START
    assert prereg["observation_window"]["ends"] == tft.WINDOW_END
    assert prereg["status"] == "armed_paper_collecting_evidence"
    assert rule["committed_before_data"] is True


# --- 2. underpowered must never become a verdict ---------------------------------

@pytest.mark.parametrize("n_days", [0, 1, 5, 9])
def test_thin_windows_return_underpowered_not_a_verdict(n_days):
    """Calling H0 off a handful of days is the undersampling error the prereg exists
    to prevent -- and H0 recommends a kill conversation."""
    got, why = tft.verdict(0, n_days)
    assert got == "UNDERPOWERED", f"{n_days} days produced {got}; must be UNDERPOWERED"
    assert "no verdict" in why


def test_ten_days_is_the_boundary_where_verdicts_begin():
    assert tft.verdict(0, 9)[0] == "UNDERPOWERED"
    assert tft.verdict(0, 10)[0] == "H0_SUPPORTED"


# --- 3. FAIL LOUD: never return a silent zero ------------------------------------

def test_missing_source_raises_rather_than_reporting_zero(tmp_path):
    """A data outage must not read as 'no tail days' (= evidence for H0)."""
    with pytest.raises(FileNotFoundError):
        tft.load_engine_trips(tmp_path / "does-not-exist.jsonl")


def test_unparseable_source_raises_rather_than_reporting_zero(tmp_path):
    p = tmp_path / "garbage.jsonl"
    p.write_text("not json\n{also not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="silent zero"):
        tft.load_engine_trips(p)


def test_source_with_no_engine_rows_raises(tmp_path):
    """Manual/mixed-attribution rows only must NOT silently score as zero tail days."""
    p = tmp_path / "manual-only.jsonl"
    p.write_text(
        json.dumps({"attribution": "manual", "date": "2026-08-04", "pnl_dollars": 3624.0}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        tft.load_engine_trips(p)


# --- 4. population discipline ----------------------------------------------------

def test_only_engine_attributed_rows_are_counted(tmp_path):
    """journal/trades.csv-style manual rows inflate any engine claim (lesson 2026-09-10);
    a manual monster day must not create a phantom tail day."""
    p = tmp_path / "mixed.jsonl"
    p.write_text("\n".join([
        json.dumps({"attribution": "engine", "arm": "safe-2", "date": "2026-09-15", "pnl_dollars": 100.0}),
        json.dumps({"attribution": "manual", "arm": "safe-2", "date": "2026-09-15", "pnl_dollars": 9999.0}),
    ]) + "\n", encoding="utf-8")
    trips = tft.load_engine_trips(p)
    assert len(trips) == 1
    day = tft.daily_totals(trips)
    assert day["2026-09-15"] == 100.0
    assert tail_count(day) == 0, "a MANUAL +$9,999 day leaked into the engine tail count"


def tail_count(day):
    return len(tft.tail_days(day, "2026-09-11", "2026-10-30"))


def test_active_4_scope_excludes_retired_arms(tmp_path):
    p = tmp_path / "arms.jsonl"
    p.write_text("\n".join([
        json.dumps({"attribution": "engine", "arm": "safe-2", "date": "2026-09-15", "pnl_dollars": 100.0}),
        json.dumps({"attribution": "engine", "arm": "risky-3", "date": "2026-09-15", "pnl_dollars": 700.0}),
        json.dumps({"attribution": "engine", "arm": "safe-1", "date": "2026-09-15", "pnl_dollars": 700.0}),
    ]) + "\n", encoding="utf-8")
    trips = tft.load_engine_trips(p)
    assert tft.daily_totals(trips, tft.ACTIVE_ARMS)["2026-09-15"] == 100.0
    assert tft.daily_totals(trips, None)["2026-09-15"] == 1500.0


def test_tail_threshold_is_strictly_greater_than_500():
    day = {"2026-09-15": 500.0, "2026-09-16": 500.01}
    got = [d for d, _ in tft.tail_days(day, "2026-09-11", "2026-10-30")]
    assert got == ["2026-09-16"], "exactly +$500 must not count as a tail day"


def test_window_bounds_are_inclusive_and_exclude_outside_days():
    day = {"2026-09-10": 5000.0, "2026-09-11": 600.0, "2026-10-30": 600.0, "2026-10-31": 5000.0}
    got = [d for d, _ in tft.tail_days(day, "2026-09-11", "2026-10-30")]
    assert got == ["2026-09-11", "2026-10-30"], (
        "pre-window days (incl. the 08-04-style monster that motivated the prereg) "
        "must not count toward the forward test"
    )
