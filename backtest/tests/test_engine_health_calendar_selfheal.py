"""Guard: calendar.json must self-heal, never silently return {} forever.

Incident (2026-07-03): calendar.json had two documented consumers
(engine_health._load_holidays, _shared.ps1 Test-HolidayFromAlpaca) but NO
producer ever existed. Both consumers' documented contract on a missing file
was "no holidays" -- so the file's permanent absence was silently correct
per spec while being wrong in practice: market_is_open() called a real NYSE
holiday (July 4th observed) a live trading day, the heartbeat ticked all
morning scoring a frozen tape, and engine-health/self-check false-RED'd on
watcher_feed staleness. Fixed by making _load_holidays() self-heal via
_refresh_calendar_from_alpaca() instead of just accepting the absence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import engine_health as eh  # noqa: E402


def _fake_calendar_response(year: int) -> list[dict]:
    """One real 2026 holiday (July 3rd observed for July 4th) + a couple of
    ordinary trading days, shaped like Alpaca's /v2/calendar payload."""
    return [
        {"date": f"{year}-07-01"}, {"date": f"{year}-07-02"},
        # 07-03 deliberately ABSENT = the holiday
        {"date": f"{year}-07-06"},
    ]


def test_absent_file_self_heals_via_refresh(tmp_path, monkeypatch):
    cal = tmp_path / "calendar.json"
    monkeypatch.setattr(eh, "STATE", tmp_path)
    assert not cal.exists()

    with mock.patch.object(eh, "_refresh_calendar_from_alpaca") as m_refresh:
        def _write(path, year):
            path.write_text(json.dumps({
                "source": "alpaca_v2_calendar", "year_range": [f"{year}-01-01", f"{year}-12-31"],
                "holidays": [f"{year}-07-03"],
            }))
            return True
        m_refresh.side_effect = _write
        holidays = eh._load_holidays()

    m_refresh.assert_called_once()
    assert any(h.endswith("-07-03") for h in holidays)


def test_stale_year_triggers_refresh_not_silent_acceptance(tmp_path, monkeypatch):
    """A calendar.json built for a PRIOR year must not be trusted silently --
    the exact shape of the original bug (a file that once existed but rolled
    stale) must still trigger a refresh, not a quiet 'no holidays this year'."""
    cal = tmp_path / "calendar.json"
    cal.write_text(json.dumps({"year_range": ["2025-01-01", "2025-12-31"], "holidays": ["2025-07-04"]}))
    monkeypatch.setattr(eh, "STATE", tmp_path)

    with mock.patch.object(eh, "_refresh_calendar_from_alpaca") as m_refresh:
        m_refresh.return_value = False  # simulate network failure -> fail-open
        holidays = eh._load_holidays()

    m_refresh.assert_called_once()
    assert holidays == set()  # fail-open, never crashes


def test_refresh_network_failure_fails_open_no_crash(tmp_path, monkeypatch):
    """If Alpaca is unreachable, market_is_open() must still return a boolean,
    never raise -- this is a health-check path, it cannot be the thing that's down."""
    monkeypatch.setattr(eh, "STATE", tmp_path)
    monkeypatch.setattr(eh, "_refresh_calendar_from_alpaca", lambda *_: False)
    holidays = eh._load_holidays()
    assert holidays == set()


def test_market_is_open_honors_self_healed_holiday(tmp_path, monkeypatch):
    """The non-vacuous bite: a self-healed holiday must actually flip
    market_is_open() False on that date (proving the wiring, not just the fetch)."""
    from datetime import datetime

    monkeypatch.setattr(eh, "STATE", tmp_path)

    def _fake_refresh(path, year):
        path.write_text(json.dumps({
            "year_range": [f"{year}-01-01", f"{year}-12-31"], "holidays": ["2026-07-03"],
        }))
        return True

    monkeypatch.setattr(eh, "_refresh_calendar_from_alpaca", _fake_refresh)
    holiday_et = datetime(2026, 7, 3, 10, 0)  # Friday, 10am -- inside the naive weekday+clock window
    assert holiday_et.weekday() < 5
    assert eh.market_is_open(holiday_et) is False


def test_fresh_current_year_file_skips_refresh(tmp_path, monkeypatch):
    """Non-vacuous control: a genuinely fresh file must NOT trigger a refresh
    (else every health check would hit the network for no reason)."""
    monkeypatch.setattr(eh, "STATE", tmp_path)
    cal = tmp_path / "calendar.json"
    year = eh._et_now().year
    cal.write_text(json.dumps({"year_range": [f"{year}-01-01", f"{year}-12-31"], "holidays": []}))

    with mock.patch.object(eh, "_refresh_calendar_from_alpaca") as m_refresh:
        eh._load_holidays()

    m_refresh.assert_not_called()
