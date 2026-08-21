"""Guard: the trigger-bar freshness check must actually EVALUATE.

THE DEFECT (found 2026-08-21 by reading a live tick, not by reading the code)
----------------------------------------------------------------------------
`heartbeat_core._trigger_bar_stale` shipped 2026-08-20 to close queue item
T-OPEN-TICK-STALE-QUOTE-2026-08-20: on 2026-08-20 the first six core ticks served the
**06:35 premarket bar** as the live quote (a ~3-hour-old price, +$2.80-3.15 adrift from
the last closed 5m bar) and `blind` was False on every one of them.

The fix looked wired. It was inert. It searched `bar_ctx` for `"trigger_bar_et"` -- the
name the LOGGED ROW uses (written at heartbeat_core.py:1665 from `bc["timestamp_et"]`) --
and for a nested `bar` dict that does not exist. `bar_ctx` carries **`timestamp_et`**.
Neither key was ever present, so `raw` was always None, the function returned early, and
every one of 2026-08-21's 772 live ticks logged `bar_freshness.checked: False`.

CONFUSING A FIELD'S LOG NAME FOR ITS PAYLOAD NAME IS HOW A GUARD SHIPS INERT AND STILL
LOOKS WIRED. It fails open by design, so nothing ever complains -- no error, no alert,
no test failure. The only way to catch it was to read a real logged row and notice a
field that was False when it should have been True.

WHAT IS PINNED
  1. The function reads the key bar_ctx ACTUALLY carries (`timestamp_et`).
  2. `checked` is True for any parseable stamp -- the inertness itself is the regression.
  3. Prior-session bars are FLAGGED but do NOT blind -- freshness is measured,
     never enforced. Enforcing it broke 10 tests the moment the key was fixed,
     because historical bars always read 'prior session' against the real clock.
  4. Same-day-but-old bars are LOGGED stale but do NOT set blind. That asymmetry is
     deliberate (docstring: "a merely-old bar is logged but left to the existing
     age/entry gates so this cannot mass-block on a slow feed"). Arming a same-day
     block is a live behaviour change and needs OP-11 evidence, not a code tweak --
     this test exists partly to make that boundary explicit.
  5. It still FAILS OPEN on garbage, and a missing symbol still re-raises (an
     AttributeError is a BUG, not a data problem -- an earlier cut swallowed one into a
     permanent silent no-op).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import heartbeat_core as hc  # noqa: E402

NOW = dt.datetime(2026, 8, 21, 9, 51, 0)


def _ctx(stamp, levels=(765.0,)):
    return {"timestamp_et": stamp, "levels_active": list(levels)}


# ---------------------------------------------------------------- the regression
def test_it_reads_the_key_bar_ctx_actually_carries():
    """THE bug. bar_ctx has `timestamp_et`; the logged row renames it `trigger_bar_et`."""
    r = hc._trigger_bar_stale(_ctx("2026-08-21T09:45:00-04:00"), now_et=NOW)
    assert r["checked"] is True, (
        "the freshness guard did not evaluate a payload carrying `timestamp_et` -- it is "
        "inert again. bar_ctx does NOT carry `trigger_bar_et`; that is the LOG field name."
    )
    assert r["age_min"] == 6.0


def test_the_log_field_name_still_works_as_a_fallback():
    """Belt and braces: if a caller ever passes the log-shaped key, still evaluate."""
    r = hc._trigger_bar_stale({"trigger_bar_et": "2026-08-21T09:45:00-04:00"}, now_et=NOW)
    assert r["checked"] is True and r["age_min"] == 6.0


def test_a_live_shaped_payload_is_never_unchecked():
    """Mirrors what heartbeat_core logs on EVERY row. `checked: False` here means the
    ledger is recording a freshness verdict it never actually computed."""
    for stamp in ("2026-08-21T09:45:00-04:00", "2026-08-21T09:06:00-04:00",
                  "2026-08-20T15:55:00-04:00"):
        assert hc._trigger_bar_stale(_ctx(stamp), now_et=NOW)["checked"] is True, stamp


# ---------------------------------------------------------------- semantics
def test_fresh_bar_is_not_stale():
    r = hc._trigger_bar_stale(_ctx("2026-08-21T09:45:00-04:00"), now_et=NOW)
    assert r["stale"] is False and r["prior_session"] is False


def test_same_day_old_bar_is_stale_but_not_prior_session():
    """The real 2026-08-20 scar shape: 06:35 premarket bar served at 09:30 the same day."""
    r = hc._trigger_bar_stale(_ctx("2026-08-20T06:35:00-04:00"),
                              now_et=dt.datetime(2026, 8, 20, 9, 30, 0))
    assert r["checked"] is True
    assert r["age_min"] == 175.0
    assert r["stale"] is True, "a 3-hour-old quote must at minimum be LOGGED stale"
    assert r["prior_session"] is False


def test_prior_session_bar_is_flagged_but_does_NOT_blind():
    """Freshness is MEASURED, not enforced -- and that separation is load-bearing.

    An earlier cut ORed prior_session into `_is_blind`. The clause was unreachable while
    the payload-key bug made _trigger_bar_stale always return early; the moment the key was
    fixed it came alive and broke 10 tests, because _trigger_bar_stale compares against the
    REAL clock -- so in any replay/backtest built on historical bars EVERY tick reads
    "prior session", blinds, and blocks every entry. Turning this measurement into a block
    needs OP-11 evidence and an injected clock, not a boolean in the blindness check."""
    ctx = _ctx("2026-08-20T15:55:00-04:00")
    r = hc._trigger_bar_stale(ctx, now_et=NOW)
    assert r["prior_session"] is True and r["stale"] is True, "must still be MEASURED"
    assert hc._is_blind(ctx) is False, (
        "_is_blind must depend on levels_active ONLY. Gating it on wall-clock freshness "
        "silently disables the entire replay/backtest lane."
    )


def test_is_blind_never_consults_the_wall_clock():
    """The structural guarantee behind the test above."""
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    fn = src[src.index("def _is_blind"):]
    fn = fn[:fn.index(chr(10) + "def ")]
    body = chr(10).join(l for l in fn.splitlines() if not l.strip().startswith("#"))
    assert "_trigger_bar_stale" not in body, (
        "_is_blind consults the freshness check again -- that re-breaks every replay, "
        "because historical bars are always 'prior session' against the real clock."
    )


def test_no_levels_still_blinds_regardless_of_freshness():
    """The primary blindness check must be untouched by this fix."""
    assert hc._is_blind({"timestamp_et": "2026-08-21T09:45:00-04:00", "levels_active": []}) is True
    assert hc._is_blind({}) is True


def test_the_age_threshold_is_a_named_constant():
    assert hc.TRIGGER_BAR_MAX_AGE_MIN == 20.0


# ---------------------------------------------------------------- fail-open contract
@pytest.mark.parametrize("ctx", [
    {}, None, {"timestamp_et": None}, {"timestamp_et": ""},
    {"timestamp_et": "not-a-timestamp"}, {"timestamp_et": 12345},
])
def test_garbage_fails_open_and_never_raises(ctx):
    """An auxiliary check must never become a new single point of failure (NEVER-BLIND)."""
    r = hc._trigger_bar_stale(ctx, now_et=NOW)
    assert r["stale"] is False and r["prior_session"] is False


def test_unparseable_stamp_is_not_reported_as_checked():
    r = hc._trigger_bar_stale({"timestamp_et": "not-a-timestamp"}, now_et=NOW)
    assert r["checked"] is False, "must not claim to have checked something it could not parse"


def test_a_missing_symbol_still_raises_rather_than_failing_silently():
    """The first cut called a clock helper that does not exist in this module, and its own
    broad `except Exception` swallowed the AttributeError into a permanent silent no-op.
    A missing symbol is a BUG, not a data problem."""
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    fn = src[src.index("def _trigger_bar_stale"):]
    fn = fn[:fn.index("\ndef ")]
    assert "except AttributeError" in fn and "raise" in fn, (
        "the AttributeError re-raise is gone -- a typo'd symbol would again fail open forever"
    )
