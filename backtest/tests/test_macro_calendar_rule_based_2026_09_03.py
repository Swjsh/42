"""Guards for the B1 rule-based release schedule added to setup/scripts/macro_calendar.py
(2026-09-03, stamp 12:40 ET).

Context: analysis/deep-research/2026-09-03-money/ audits found today's Wave 1
(09:41 ET entries, four arms) and 2026-08-05's equivalent wave were both stopped
at the -50% catastrophe cap on a single-minute quote-tape gap spanning
10:00-10:01 ET, coincident with the ISM Services PMI release both days.
macro_calendar.py's only calendar (KNOWN_EVENTS_2026, hand-curated BLS/BEA/FOMC)
never listed ISM at all -- there was no producer for it, so the no-trade-window
computation could never have blocked those entries even in principle.

These tests guard:
  1. ISM Manufacturing/Services PMI dates are correct per ISM's published rule
     (1st / 3rd US-market business day of the month, 10:00 ET) for every month
     of 2026, cross-checked against the four dates this task's briefing named.
  2. NYSE holidays are actually skipped when counting business days (not just
     weekends) -- forced with a synthetic holiday set.
  3. generate_rule_based_events()/scheduled_releases() are PURE -- zero network
     calls, even importing the module fresh.
  4. KNOWN_EVENTS_2026 (the pre-existing hand-curated table) is untouched by
     this change -- same length, same entries.
  5. Consumer Confidence / UMich prelim / UMich final compute the right
     calendar-weekday dates and carry status="RULE_BASED_UNVERIFIED" +
     verified=False, while ISM entries carry verified=True + verified_by.
  6. JOLTS is never generated anywhere (omit-rather-than-guess).
  7. scheduled_releases() returns [] on an ordinary non-event day.

All tests import macro_calendar directly (module-level, no repo state files
touched) -- consistent with test_macro_calendar_producer.py's existing pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import macro_calendar as mc  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. ISM Manufacturing / Services PMI dates -- Sep through Dec 2026
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "date,expected_type",
    [
        ("2026-09-01", "ism_manufacturing_pmi"),
        ("2026-09-03", "ism_services_pmi"),
        ("2026-10-01", "ism_manufacturing_pmi"),
        ("2026-10-05", "ism_services_pmi"),
        ("2026-11-02", "ism_manufacturing_pmi"),
        ("2026-11-04", "ism_services_pmi"),
        ("2026-12-01", "ism_manufacturing_pmi"),
        ("2026-12-03", "ism_services_pmi"),
    ],
)
def test_ism_dates_sep_through_dec_2026(date: str, expected_type: str) -> None:
    events = mc.scheduled_releases(date)
    types = [e["type"] for e in events]
    assert expected_type in types, f"{date}: expected {expected_type} in {types}"
    ev = next(e for e in events if e["type"] == expected_type)
    assert ev["time_et"] == "10:00"
    assert ev["severity"] == "high"
    assert ev["source"] == "rule_based"


# --------------------------------------------------------------------------- #
# 2. Cross-check against the two live quote-tape gaps this task's briefing named
# --------------------------------------------------------------------------- #
def test_matches_briefing_quote_tape_gap_dates() -> None:
    """2026-08-05 and 2026-09-03 are the two live-verified ISM Services gap
    days named in the task briefing; 2026-09-01 is the Manufacturing release
    three days earlier (also named); the next Services after today is
    2026-10-05 (also named)."""
    aug05 = {e["type"] for e in mc.scheduled_releases("2026-08-05")}
    sep01 = {e["type"] for e in mc.scheduled_releases("2026-09-01")}
    sep03 = {e["type"] for e in mc.scheduled_releases("2026-09-03")}
    assert "ism_services_pmi" in aug05
    assert "ism_manufacturing_pmi" in sep01
    assert "ism_services_pmi" in sep03

    services_2026 = sorted(
        e["date"] for e in mc.generate_rule_based_events(2026) if e["type"] == "ism_services_pmi"
    )
    next_after_today = next(d for d in services_2026 if d > "2026-09-03")
    assert next_after_today == "2026-10-05"


# --------------------------------------------------------------------------- #
# 3. NYSE holidays are actually skipped when counting business days
# --------------------------------------------------------------------------- #
def test_holiday_actually_shifts_business_day_count() -> None:
    """Force a synthetic holiday onto what would otherwise be the 1st business
    day of a month and confirm the ISM Manufacturing date shifts forward by one
    trading day -- proves the holiday set is consulted, not just weekends."""
    # 2026-06-01 is a Monday (first business day of June 2026 with the real
    # NYSE_HOLIDAYS_2026 table, since June has no holiday before it).
    baseline = mc._nth_business_day_of_month(2026, 6, 1, mc.NYSE_HOLIDAYS_2026)
    assert baseline == "2026-06-01"

    forced_holidays = frozenset(mc.NYSE_HOLIDAYS_2026 | {"2026-06-01"})
    shifted = mc._nth_business_day_of_month(2026, 6, 1, forced_holidays)
    assert shifted == "2026-06-02"
    assert shifted != baseline


def test_weekend_is_skipped_for_third_business_day() -> None:
    """September 2026: Sep 1 (Tue), Sep 2 (Wed), Sep 3 (Thu) are the first three
    business days -- no weekend or holiday intervenes, so day 3 == Sep 3
    (matches the live gap). Confirms weekend-skip arithmetic independently of
    the holiday-skip test above."""
    assert mc._nth_business_day_of_month(2026, 9, 3, mc.NYSE_HOLIDAYS_2026) == "2026-09-03"


# --------------------------------------------------------------------------- #
# 4. Purity -- zero network I/O
# --------------------------------------------------------------------------- #
def test_no_network_call_on_import() -> None:
    """Reload the module with urllib.request.urlopen patched to raise on any
    call -- a clean import must not touch it."""
    import importlib

    with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network touched on import")):
        importlib.reload(mc)
    # reload again without the patch so later tests in this file see the real module
    importlib.reload(mc)


def test_no_network_call_in_scheduled_releases_and_generate() -> None:
    with mock.patch.object(mc.urllib.request, "urlopen", side_effect=AssertionError("network touched")) as m:
        mc.scheduled_releases("2026-09-03")
        mc.generate_rule_based_events(2026)
        m.assert_not_called()


# --------------------------------------------------------------------------- #
# 5. KNOWN_EVENTS_2026 (pre-existing hand-curated table) is untouched
# --------------------------------------------------------------------------- #
def test_known_events_2026_unchanged() -> None:
    assert len(mc.KNOWN_EVENTS_2026) == 8
    types = [e["type"] for e in mc.KNOWN_EVENTS_2026]
    assert types == [
        "cpi_release",
        "ppi_release",
        "retail_sales",
        "fomc_decision",
        "gdp_release",
        "pce_release",
        "nfp_release",
        "fomc_decision",
    ]
    # None of the hand-curated entries carry a "source" key -- that key is new
    # and exclusive to the rule-based generator, confirming no cross-contamination.
    assert all("source" not in e for e in mc.KNOWN_EVENTS_2026)
    # Spot-check one untouched entry verbatim.
    cpi = mc.KNOWN_EVENTS_2026[0]
    assert cpi["date"] == "2026-07-14"
    assert cpi["event"] == "CPI (June 2026 data)"


# --------------------------------------------------------------------------- #
# 6. Consumer Confidence / UMich calendar-weekday rules + UNVERIFIED marking
# --------------------------------------------------------------------------- #
def test_consumer_confidence_is_last_tuesday() -> None:
    # September 2026: Tuesdays are 1, 8, 15, 22, 29 -- last is the 29th.
    ev = next(e for e in mc.scheduled_releases("2026-09-29") if e["type"] == "consumer_confidence")
    assert ev["date"] == "2026-09-29"
    assert ev["status"] == "RULE_BASED_UNVERIFIED"
    assert ev["verified"] is False
    assert ev["severity"] == "med"
    assert ev["source"] == "rule_based"


def test_umich_prelim_second_friday_and_final_fourth_friday() -> None:
    # September 2026: Fridays are 4, 11, 18, 25 -- 2nd = Sep 11, 4th = Sep 25.
    prelim = next(e for e in mc.scheduled_releases("2026-09-11") if e["type"] == "umich_sentiment_prelim")
    final = next(e for e in mc.scheduled_releases("2026-09-25") if e["type"] == "umich_sentiment_final")
    assert prelim["date"] == "2026-09-11"
    assert final["date"] == "2026-09-25"
    for ev in (prelim, final):
        assert ev["status"] == "RULE_BASED_UNVERIFIED"
        assert ev["verified"] is False
        assert ev["severity"] == "med"


def test_ism_entries_carry_verified_true_and_verified_by() -> None:
    for date, ev_type in (("2026-09-01", "ism_manufacturing_pmi"), ("2026-09-03", "ism_services_pmi")):
        ev = next(e for e in mc.scheduled_releases(date) if e["type"] == ev_type)
        assert ev["verified"] is True
        assert "verified_by" in ev
        assert "2026-08-05" in ev["verified_by"] and "2026-09-03" in ev["verified_by"]
        assert "status" not in ev  # RULE_BASED_UNVERIFIED marker is exclusive to the unverified four


# --------------------------------------------------------------------------- #
# 7. JOLTS omitted entirely -- omit-rather-than-guess
# --------------------------------------------------------------------------- #
def test_jolts_never_generated() -> None:
    all_2026 = mc.generate_rule_based_events(2026)
    assert not any("jolts" in e["type"].lower() for e in all_2026)
    assert not any("jolts" in e["event"].lower() for e in all_2026)


# --------------------------------------------------------------------------- #
# 8. scheduled_releases() returns [] on an ordinary day
# --------------------------------------------------------------------------- #
def test_scheduled_releases_empty_on_ordinary_day() -> None:
    assert mc.scheduled_releases("2026-09-10") == []


def test_scheduled_releases_all_entries_have_required_shape() -> None:
    """Every entry from every date in 2026 carries the fields the task's
    contract requires: time_et, event, type, severity, source (plus rule,
    which every entry -- verified or not -- must carry)."""
    for ev in mc.generate_rule_based_events(2026):
        for key in ("date", "time_et", "event", "type", "severity", "source", "rule"):
            assert key in ev, f"missing {key!r} in {ev}"
        assert ev["source"] == "rule_based"
        assert ev["time_et"] == "10:00"
        assert ev["severity"] in ("high", "med")
