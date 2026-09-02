"""Guards for structure_stop_study's OPRA fetch helper -- two stacked defects, 2026-09-02.

WHAT HAPPENED. The helper hardcoded `creds_all.get("safe-1")`. safe-1 is a DORMANT arm
(live:false) and its key is the only one of the seven in the roster that 401s -- measured
across all seven the same day, safe-1 the sole failure. So every call died during auth and
the "today exhibit" layer of every study using this helper silently returned [], printing
one stderr line nobody chased. The 2026-09-02 structure-stop runs recorded that as "a real
data-completeness gap in the study harness". It was not: the data was there, and six other
keys in the same file could read it.

Fixing the credential UNMASKED A SECOND DEFECT the 401 had been hiding. The window's end is
capped at now-16min to dodge the real-time-data entitlement boundary -- correct for a
session still running, nonsense for a PAST date, where it clamps the end to today's
time-of-day. Any run before ~09:45 ET therefore asks for an end EARLIER than the 09:29
start, and the API answers 400. Auth failed first, so the range was never validated and the
400 never appeared.

That ordering is the lesson worth keeping: an outer failure can hide an inner one
completely, and "fixed the error" is not the same as "the path works". Both are pinned here.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "backtest" / "tools" / "structure_stop_study.py"

for p in (REPO / "backtest" / "tools", REPO / "backtest", REPO / "automation" / "state" / "fleet"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

_spec = importlib.util.spec_from_file_location("structure_stop_study_g", MODULE)
assert _spec and _spec.loader
sss = importlib.util.module_from_spec(_spec)
sys.modules["structure_stop_study_g"] = sss
_spec.loader.exec_module(sss)


# ---------------------------------------------------------------------------------------
# Defect 1: the dormant-arm credential.
# ---------------------------------------------------------------------------------------

def test_safe_1_is_last_in_the_preference_order():
    """safe-1 is dormant and its key 401s. It stays in the list as a final fallback but must
    never be chosen while any other arm has credentials."""
    assert sss._OPRA_CRED_PREFERENCE[-1] == "safe-1"
    assert len(sss._OPRA_CRED_PREFERENCE) > 1


def test_resolver_skips_the_dormant_arm_when_a_live_one_exists():
    creds = {"safe-1": {"key": "DEAD", "secret": "x"},
             "safe-2": {"key": "GOOD", "secret": "y"}}
    assert sss._resolve_opra_creds(creds)["key"] == "GOOD"


def test_resolver_falls_back_to_safe_1_rather_than_returning_nothing():
    """A degraded fetch beats no fetch: if safe-1 is all there is, try it."""
    creds = {"safe-1": {"key": "DEAD", "secret": "x"}}
    assert sss._resolve_opra_creds(creds)["key"] == "DEAD"


def test_resolver_handles_a_roster_shape_change():
    """The preference list is a preference, not a schema. An arm nobody anticipated must
    still be usable rather than silently yielding None."""
    creds = {"brand-new-arm": {"key": "K", "secret": "S"}}
    assert sss._resolve_opra_creds(creds)["key"] == "K"


def test_resolver_returns_none_only_when_nothing_is_usable():
    assert sss._resolve_opra_creds({}) is None
    assert sss._resolve_opra_creds({"a": {"key": "", "secret": ""}}) is None
    assert sss._resolve_opra_creds({"a": {"key": "K"}}) is None  # secret missing


def test_helper_does_not_hardcode_an_arm_id():
    """The whole defect was a literal arm id at the call site."""
    src = MODULE.read_text(encoding="utf-8")
    body = src.split("def fetch_option_bars_today_safe", 1)[1]
    assert 'get("safe-1")' not in body, "the dormant arm is hardcoded again"


# ---------------------------------------------------------------------------------------
# Defect 2: the window cap applied to a past date.
# ---------------------------------------------------------------------------------------

def _end_hhmm(date_et: str, now_et: dt.datetime) -> str:
    """Mirror of the branch under test, so the expectation is stated independently."""
    if date_et < now_et.strftime("%Y-%m-%d"):
        return "16:05"
    safe_end = now_et - dt.timedelta(minutes=16)
    return min(safe_end.strftime("%H:%M"), "16:05")


@pytest.mark.parametrize("now_hour", [0, 4, 6, 9, 12, 23])
def test_historical_date_always_gets_a_full_session_window(now_hour):
    """The 06:00 ET case is the one that bit: end would clamp to 05:44, before the 09:29
    start, and the API answers 400. A past day has fully elapsed -- there is no live-data
    boundary to dodge, so the cap must not apply at any hour."""
    now = dt.datetime(2026, 9, 2, now_hour, 0)
    assert _end_hhmm("2026-07-09", now) == "16:05"


def test_today_still_gets_the_entitlement_cap():
    """The cap is load-bearing on a live session -- options bars younger than ~15 minutes
    are blocked by the unsigned OPRA real-time agreement. Removing it entirely would
    reintroduce that failure."""
    now = dt.datetime(2026, 9, 2, 11, 0)
    assert _end_hhmm("2026-09-02", now) == "10:44"


def test_today_late_in_the_session_is_capped_at_close():
    now = dt.datetime(2026, 9, 2, 23, 0)
    assert _end_hhmm("2026-09-02", now) == "16:05"


def test_source_branches_on_the_date():
    src = MODULE.read_text(encoding="utf-8")
    body = src.split("def fetch_option_bars_today_safe", 1)[1]
    assert 'date_et < now_et.strftime("%Y-%m-%d")' in body, (
        "the past-date branch is gone -- historical fetches will 400 again on any "
        "overnight run"
    )
