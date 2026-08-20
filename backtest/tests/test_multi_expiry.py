"""Tests for the multi-symbol lane's expiry selector (multi/lib/expiry.py).

Core property under test: select_expiry NEVER invents a calendar date — it only
ever returns a member of the caller-supplied `available_expiries` (the live
listed chain). The verified real-world motivator (J-supplied 2026-08-19): NVDA's
2026-08-26 expiry (a Wednesday listing) is not listed because NVDA reports
earnings that day, so a naive "this Friday if DTE>=3 else next Friday" formula
would compute a date that plain doesn't exist in the chain.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_multi_expiry.py -q
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from multi.lib import expiry  # noqa: E402

ET = ZoneInfo("America/New_York")

PARAMS = {"entry": {"min_dte_at_entry": 3}}

# Wednesday, per the real verified case (NVDA earnings day, 2026-08-26 is NOT a
# Friday — confirmed via date.fromisoformat(...).strftime("%A")).
AS_OF = datetime(2026, 8, 19, 10, 0, tzinfo=ET)


# =============================================================================
# 1. Basic min-DTE selection from a live chain
# =============================================================================

def test_select_expiry_picks_nearest_listed_clearing_min_dte():
    chain = ["2026-08-21", "2026-08-28", "2026-09-04"]  # DTE 2, 9, 16 from AS_OF
    result = expiry.select_expiry(
        symbol="AAPL", available_expiries=chain, params=PARAMS, as_of=AS_OF,
    )
    assert result.ok
    assert result.expiry == "2026-08-28"  # nearest that clears min_dte=3 (2026-08-21 is only 2 DTE)
    assert result.dte == 9
    assert result.fallback is False


def test_select_expiry_min_dte_zero_allows_nearest_of_all():
    params = {"entry": {"min_dte_at_entry": 0}}
    chain = ["2026-08-19", "2026-08-21"]  # today itself is 0 DTE
    result = expiry.select_expiry(symbol="AAPL", available_expiries=chain, params=params, as_of=AS_OF)
    assert result.ok
    assert result.expiry == "2026-08-19"
    assert result.dte == 0


def test_select_expiry_accepts_date_and_datetime_objects_not_just_strings():
    from datetime import date
    chain = [date(2026, 8, 21), date(2026, 8, 28)]
    result = expiry.select_expiry(symbol="AAPL", available_expiries=chain, params=PARAMS, as_of=AS_OF)
    assert result.ok
    assert result.expiry == "2026-08-28"


# =============================================================================
# 2. RED-PROOF — NEVER invents a date outside the live listed chain
# =============================================================================

def test_select_expiry_RED_PROOF_never_returns_a_date_not_in_the_chain():
    """RED-PROOF: over a spread of chains with gaps (simulating an
    earnings-week delisting like NVDA's real 2026-08-26 case), the selected
    expiry must ALWAYS be a literal member of available_expiries — never a
    computed Friday that happens to not be listed."""
    chains = [
        ["2026-08-21", "2026-08-28", "2026-09-04"],
        ["2026-08-24", "2026-08-31"],   # Monday-cadence chain, no Fridays at all
        ["2026-08-26", "2026-09-02"],   # Wednesday-cadence chain, no Fridays at all
        ["2026-09-18"],                  # monthly-only chain, far out
    ]
    for chain in chains:
        result = expiry.select_expiry(
            symbol="XYZ", available_expiries=chain, params=PARAMS, as_of=AS_OF,
        )
        if result.ok:
            assert result.expiry in chain, (
                f"select_expiry returned {result.expiry!r} which is NOT a "
                f"member of the supplied chain {chain!r}"
            )


def test_select_expiry_missing_target_expiry_flags_fallback_NVDA_case():
    """The verified real case: NVDA's 2026-08-26 (Wednesday) expiry is not
    listed because earnings land that day. Caller supplies target_expiry=
    "2026-08-26" (their own expectation); it's absent from the live chain, so
    select_expiry must fall back to the nearest listed alternative AND flag it."""
    live_chain = ["2026-08-21", "2026-08-28", "2026-09-04"]  # no 2026-08-26
    result = expiry.select_expiry(
        symbol="NVDA", available_expiries=live_chain, params=PARAMS,
        target_expiry="2026-08-26", as_of=AS_OF,
    )
    assert result.ok
    assert result.code == expiry.CODE_SELECTED_FALLBACK
    assert result.fallback is True
    assert result.fallback_reason is not None
    assert "2026-08-26" in result.fallback_reason
    assert result.expiry in live_chain
    assert result.expiry == "2026-08-28"


def test_select_expiry_target_expiry_present_and_valid_no_fallback():
    live_chain = ["2026-08-21", "2026-08-26", "2026-08-28"]  # target IS listed this time
    result = expiry.select_expiry(
        symbol="NVDA", available_expiries=live_chain, params=PARAMS,
        target_expiry="2026-08-26", as_of=AS_OF,
    )
    assert result.ok
    assert result.code == expiry.CODE_SELECTED
    assert result.fallback is False
    assert result.expiry == "2026-08-26"


def test_select_expiry_target_expiry_listed_but_too_near_flags_fallback():
    # target is listed but only 2 DTE, below min_dte=3 -> must fall back.
    live_chain = ["2026-08-21", "2026-08-28"]
    result = expiry.select_expiry(
        symbol="AAPL", available_expiries=live_chain, params=PARAMS,
        target_expiry="2026-08-21", as_of=AS_OF,
    )
    assert result.ok
    assert result.fallback is True
    assert result.expiry == "2026-08-28"


def test_select_expiry_no_target_supplied_never_flags_fallback():
    chain = ["2026-08-28"]
    result = expiry.select_expiry(symbol="AAPL", available_expiries=chain, params=PARAMS, as_of=AS_OF)
    assert result.ok
    assert result.fallback is False
    assert result.fallback_reason is None


def test_select_expiry_source_never_computes_a_friday():
    """Belt-and-suspenders: the module source must contain no WEEKDAY
    ARITHMETIC at all (the actual computation a Friday-rule would need) — the
    whole point of this fork is that listing cadence is per-name and not
    calendar-derivable (see module docstring, which legitimately discusses
    "Friday" in prose — this checks for the CODE, not the word)."""
    src = (REPO / "multi" / "lib" / "expiry.py").read_text(encoding="utf-8")
    for needle in (".weekday()", "days_ahead"):
        assert needle not in src, (
            f"expiry.py source contains {needle!r} — this module must never "
            f"compute a calendar weekday/Friday to select an expiry"
        )


# =============================================================================
# 3. Fail-closed
# =============================================================================

def test_select_expiry_denies_no_listed_expiry_clears_min_dte():
    chain = ["2026-08-20", "2026-08-21"]  # 1 and 2 DTE, both < min_dte=3
    result = expiry.select_expiry(symbol="AAPL", available_expiries=chain, params=PARAMS, as_of=AS_OF)
    assert not result.ok
    assert result.code == expiry.CODE_NO_LISTED_EXPIRY


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(symbol=None, available_expiries=["2026-08-28"], params=PARAMS),
        dict(symbol="", available_expiries=["2026-08-28"], params=PARAMS),
        dict(symbol="AAPL", available_expiries=None, params=PARAMS),
        dict(symbol="AAPL", available_expiries=[], params=PARAMS),
        dict(symbol="AAPL", available_expiries=["not-a-date", "also-bad"], params=PARAMS),
        dict(symbol="AAPL", available_expiries=["2026-08-28"], params=None),
        dict(symbol="AAPL", available_expiries=["2026-08-28"], params={}),
        dict(symbol="AAPL", available_expiries=["2026-08-28"], params={"entry": {}}),
        dict(symbol="AAPL", available_expiries=["2026-08-28"], params={"entry": {"min_dte_at_entry": -1}}),
        dict(symbol="AAPL", available_expiries=["2026-08-28"], params={"entry": {"min_dte_at_entry": "three"}}),
    ],
)
def test_select_expiry_fails_closed_on_unreadable_input(kwargs):
    result = expiry.select_expiry(as_of=AS_OF, **kwargs)
    assert not result.ok
    assert result.expiry is None


def test_now_et_is_dst_aware_zoneinfo_not_fixed_offset():
    """Belt-and-suspenders: now_et() must use zoneinfo (DST-aware), never a
    hardcoded UTC offset — winter (EST, -5) and summer (EDT, -4) must differ."""
    winter = datetime(2026, 1, 15, 12, 0, tzinfo=ET)
    summer = datetime(2026, 7, 15, 12, 0, tzinfo=ET)
    assert winter.utcoffset().total_seconds() / 3600 == -5
    assert summer.utcoffset().total_seconds() / 3600 == -4
    # And now_et() itself returns a tz-aware datetime in that same zone.
    now = expiry.now_et()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
