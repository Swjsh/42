"""Guard for firm_brief.autopsy_staleness_note -- the instrument that makes a dark
Gamma_TradeAutopsy clock-trigger LOUD on the brief (OP-33b: registered != firing). Pure."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "firm_brief", REPO / "setup" / "scripts" / "firm_brief.py")
fb = importlib.util.module_from_spec(_SPEC)
sys.modules["firm_brief"] = fb
_SPEC.loader.exec_module(fb)


def _et(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm)


def test_fresh_same_day_after_fire_is_silent():
    # Thu 2026-07-09 17:00 ET, autopsy dated 07-09 -> fresh
    assert fb.autopsy_staleness_note("2026-07-09", _et(2026, 7, 9, 17, 0)) is None


def test_missed_todays_fire_is_loud():
    # Thu 17:00 ET but the last autopsy is Wednesday's -> the 16:15 fire went dark
    note = fb.autopsy_staleness_note("2026-07-08", _et(2026, 7, 9, 17, 0))
    assert note and "STALE" in note and "Gamma_TradeAutopsy" in note


def test_before_todays_fire_yesterdays_autopsy_is_fine():
    # Thu 08:35 ET premarket brief: Wednesday's autopsy is the expected latest
    assert fb.autopsy_staleness_note("2026-07-08", _et(2026, 7, 9, 8, 35)) is None


def test_weekend_expects_friday():
    assert fb.autopsy_staleness_note("2026-07-10", _et(2026, 7, 12, 12, 0)) is None   # Fri ok on Sun
    note = fb.autopsy_staleness_note("2026-07-09", _et(2026, 7, 12, 12, 0))           # Thu = stale
    assert note and "STALE" in note


def test_monday_premarket_expects_friday_not_sunday():
    assert fb.autopsy_staleness_note("2026-07-10", _et(2026, 7, 13, 8, 35)) is None
