"""Guard: the engine must never decide today's tape on a PRIOR SESSION's bar.

THE SCAR (2026-08-20 open)
  The first six core ticks of the session carried
  trigger_bar_et = 2026-08-19T15:50 / 15:55 -- YESTERDAY's closing bars --
  reporting spy 768.74 / 769.09 against a real last-closed-bar of 765.94. A
  +$3.15 drift, and `blind` was False on every one of them. Bull score read 9/6
  through the stale window and dropped to 8/6 the tick it corrected.

WHY EVERY EXISTING GUARD MISSED IT
  * `_sight_staleness_check` compares against a LIVE quote, but only runs once an
    ENTER verdict is already on the table. Those six ticks were HOLD, so it never
    ran and the drift never reached a decision row.
  * The 09:35 entry floor covered 09:30-09:34 by accident of timing, leaving the
    09:35 tick itself both entry-legal AND reading a yesterday bar.
  * Neither guard looks at the bar's TIMESTAMP. A stale bar whose price happens
    to land within $1.00 of the tape passes both.

WHY THIS CHECK IS FREE
  `trigger_bar_et` is already on every payload. No REST call, no quote spend.

THE SECOND SCAR, IN THIS FILE'S OWN FIX
  The first cut called `et_now()` -- a symbol that does not exist in
  heartbeat_core -- and a broad `except Exception` swallowed the AttributeError
  into a silent fail-open. The guard would have been PERMANENTLY INERT in
  production with nothing to say so: the exact C7 class it was written to close.
  Caught only by RED-proofing. AttributeError is now re-raised.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import heartbeat_core as hc                      # noqa: E402

MID_SESSION = dt.datetime(2026, 8, 20, 9, 36, 3)     # a normal in-session clock


def ctx(bar_et, levels=(768.10, 769.00)):
    return {"trigger_bar_et": bar_et, "levels_active": list(levels)}


# ------------------------------------------------------------- the scar

@pytest.mark.parametrize("bar_et", ["2026-08-19T15:50:00-04:00",
                                    "2026-08-19T15:55:00-04:00"])
def test_the_actual_stale_bars_from_the_open_are_caught(bar_et):
    """The exact timestamps that ran undetected on 2026-08-20."""
    r = hc._trigger_bar_stale(ctx(bar_et), now_et=MID_SESSION)
    assert r["checked"] is True
    assert r["prior_session"] is True, r
    assert r["stale"] is True, r
    assert r["age_min"] > 1000, r


def test_a_prior_session_bar_makes_the_tick_blind():
    """blind must mean DO NOT TRADE. A yesterday bar is blind about today however
    many levels the tick can name."""
    stale = ctx("2026-08-19T15:50:00-04:00")
    assert hc._trigger_bar_stale(stale)["prior_session"] is True
    assert hc._is_blind(stale) is True


# ------------------------------------------------- no false positives

@pytest.mark.parametrize("bar_et,age_lo,age_hi", [
    ("2026-08-20T09:30:00-04:00", 0, 10),
    ("2026-08-20T09:25:00-04:00", 10, 15),
    ("2026-08-20T09:10:00-04:00", 25, 30),
])
def test_same_session_bars_are_never_prior_session(bar_et, age_lo, age_hi):
    """A slow feed must not mass-block. Only the unambiguous prior-session case
    feeds blindness; merely-old is logged, not blinding."""
    r = hc._trigger_bar_stale(ctx(bar_et), now_et=MID_SESSION)
    assert r["prior_session"] is False, r
    assert age_lo <= r["age_min"] <= age_hi, r


def test_merely_old_is_flagged_stale_but_does_not_blind():
    """26 minutes old exceeds the age bound and IS reported, but blindness is
    reserved for the prior-session case so a laggy feed cannot halt the book."""
    old = ctx("2026-08-20T09:10:00-04:00")
    r = hc._trigger_bar_stale(old, now_et=MID_SESSION)
    assert r["stale"] is True and r["prior_session"] is False
    # blind is driven by prior_session only
    assert hc._trigger_bar_stale(old, now_et=MID_SESSION)["prior_session"] is False


# ------------------------------------------------- fail-open / fail-loud

@pytest.mark.parametrize("bad", ["not-a-date", "", None])
def test_unparseable_timestamp_fails_open(bad):
    """An auxiliary check must never become a new single point of failure."""
    r = hc._trigger_bar_stale({"trigger_bar_et": bad, "levels_active": [1]})
    assert r["checked"] is False and r["stale"] is False


def test_missing_levels_still_blinds_independently():
    """The original blindness condition must survive the addition."""
    assert hc._is_blind({"trigger_bar_et": "2026-08-20T09:30:00-04:00", "levels_active": []}) is True


def test_a_missing_clock_symbol_raises_instead_of_failing_open():
    """THE META-GUARD. The first cut of this fix called a nonexistent et_now() and
    the broad except swallowed it — the check would have been inert forever."""
    src = Path(hc.__file__).read_text(encoding="utf-8")
    body = src.split("def _trigger_bar_stale(", 1)[1].split("\ndef ", 1)[0]
    assert "except AttributeError:" in body and "raise" in body, \
        "AttributeError must re-raise; a missing symbol is a bug, not a data problem"
    assert "_et_clock_now()" in body, "must use the module's real DST-aware ET clock"


def test_freshness_is_logged_on_every_row_not_just_entries():
    """The drift was invisible because the existing guard only ran on ENTER
    verdicts. This must be recorded on HOLD rows too."""
    src = Path(hc.__file__).read_text(encoding="utf-8")
    assert '"bar_freshness": _trigger_bar_stale(bc)' in src
