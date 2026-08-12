"""Guard: the WINNER autopsy must go loud when its nightly fire goes dark (2026-08-11, P0).

WHY. The loss autopsy has had `autopsy_staleness_note` since it shipped; the winner side had
none. That asymmetry is load-bearing, not cosmetic: the WS9 pain ledger and three shadow
counters (catastrophe-cap, entry, stop-mode) all ride Gamma_WinnerAutopsy's fire as folds. A
dark clock trigger therefore freezes FIVE surfaces at once while the brief keeps printing the
last capture rate as if it were current -- the most plausible explanation for the pain ledger
sitting at 2026-08-01 for nine days unnoticed (C7).

SECOND DEFECT THIS PINS. winner-autopsy-last.json has NO `date` key and never has (its
schema uses `scope` + `generated_at`). A diagnostic doing `.get("date")` returns None on a
perfectly healthy payload -- that false "partial-run signature" is what put this on the work
map in the first place. The note must read `generated_at`, and a payload without `date` must
NOT be treated as stale.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import firm_brief as fb  # noqa: E402


def _et(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm)


def test_fresh_run_is_silent():
    """Tuesday 17:00, generated today -> no note."""
    assert fb.winner_autopsy_staleness_note("2026-08-11T16:25:03", _et(2026, 8, 11, 17, 0)) is None


def test_dark_clock_goes_loud_and_names_the_riders():
    """Nine days stale -- the exact pain-ledger blackout shape."""
    note = fb.winner_autopsy_staleness_note("2026-08-01T16:25:00", _et(2026, 8, 11, 17, 0))
    assert note is not None
    assert "STALE" in note
    assert "Gamma_WinnerAutopsy" in note
    # must name the downstream riders -- a reader has to know 5 surfaces froze, not 1
    assert "pain ledger" in note


def test_never_ran_is_silent_not_stale():
    """None/empty -> the 'no winner autopsy yet' line owns that case, not this one."""
    assert fb.winner_autopsy_staleness_note(None, _et(2026, 8, 11, 17, 0)) is None
    assert fb.winner_autopsy_staleness_note("", _et(2026, 8, 11, 17, 0)) is None


def test_missing_date_key_is_not_stale():
    """THE FALSE SIGNAL THAT CREATED THIS TASK: the real payload has no `date` key. A healthy
    payload read via .get('date') yields None and must NOT produce a staleness warning."""
    healthy = {"scope": "population", "generated_at": "2026-08-11T16:25:03",
               "n_winners_scored": 12}
    assert healthy.get("date") is None          # documents the schema fact
    assert fb.winner_autopsy_staleness_note(healthy.get("generated_at"),
                                            _et(2026, 8, 11, 17, 0)) is None


def test_before_todays_fire_looks_back_to_the_previous_weekday():
    """Tuesday 09:00 -- today's 16:25 has not happened, so Monday is the bar."""
    assert fb.winner_autopsy_staleness_note("2026-08-10T16:25:00", _et(2026, 8, 11, 9, 0)) is None
    assert fb.winner_autopsy_staleness_note("2026-08-07T16:25:00", _et(2026, 8, 11, 9, 0)) is not None


def test_weekend_expects_friday():
    """Sunday -> Friday is the most recent expected fire; a Friday run is fresh."""
    assert fb.winner_autopsy_staleness_note("2026-08-07T16:25:00", _et(2026, 8, 9, 12, 0)) is None


def test_unparseable_timestamp_goes_loud():
    note = fb.winner_autopsy_staleness_note("not-a-date", _et(2026, 8, 11, 17, 0))
    assert note is not None and "unparseable" in note


def test_wired_into_the_brief_body():
    """Source-level: the note must actually be CALLED in the Winner autopsy section --
    a helper nobody invokes is the silent-failure this guard exists to prevent."""
    src = (SCRIPTS / "firm_brief.py").read_text(encoding="utf-8")
    i = src.index('lines.append("## Winner autopsy (capture rate)")')
    section = src[i:i + 600]
    assert "winner_autopsy_staleness_note(" in section, (
        "the winner section no longer calls its staleness note:\n" + section[:300])
    assert 'winner.get("generated_at")' in section, "must read generated_at, never `date`"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
