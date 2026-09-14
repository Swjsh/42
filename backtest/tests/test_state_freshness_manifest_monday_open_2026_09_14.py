"""STATE-FRESHNESS false YELLOW at the 09:30 gate (J, Monday 2026-09-14 10:00 ET: "this is months
old and stale fix it NOW").

MEASURED: premarket-readiness.json at 09:30:01 ET carried `engine_health YELLOW -- state_freshness:
4/21 live-path state files STALE -- heartbeat.json, data-freshness.json, eod-summary.json,
heartbeat.json`. All four are the FUTURES lane's files. The futures trader's first tick of the day
landed at 09:30:08 ET (futures-trader-2026-09-14.log) -- seven seconds AFTER the gate -- so the
three 5-minute files still carried Friday's stamp while their `window_et` had already opened at
09:30:00, and the AGE axis called a 65-hour-old file stale. `futures/eod-summary.json` (weekday
16:12 ET writer) was 65 hours old on a Monday morning against a 1500-minute budget: stale every
Monday until 16:12 by construction, on a 24/7 window.

FIX (automation/state/state-freshness-manifest.json): the three 09:30 lanes open their age window
at 09:36 (first fire 09:30:00 + up to ~40 s, second 09:35; the DATE axis still asserts today's
stamp after 09:35, so a lane that never starts is still caught); eod-summary's age budget is 5900
min (a 3-day weekend + 16 h) -- its real contract is the DATE axis (today's date after 16:15).

These tests evaluate the REAL manifest entries with synthetic payloads, so a future edit that
re-opens the race or shrinks the budget fails here, and a genuinely dead lane still reds.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import state_freshness_audit as sfa  # noqa: E402

NO_HOLIDAYS: set = set()
MON_0930_GATE = datetime(2026, 9, 14, 9, 30, 1)   # the readiness gate's real fire time
MON_0941 = datetime(2026, 9, 14, 9, 41, 0)        # window open, lane should have written twice
TUE_0930 = datetime(2026, 9, 15, 9, 30, 1)
FRIDAY_STAMP = "2026-09-11T16:05:00"

FIVE_MIN_LANES = {
    "automation/state/futures/trader/heartbeat.json": "last_tick_et",
    "automation/state/futures/data-freshness.json": "written_at_et",
    "automation/state/futures/trader-broker/heartbeat.json": "last_tick_et",
}
EOD = "automation/state/futures/eod-summary.json"


def _entries() -> dict[str, dict]:
    entries, err = sfa.load_manifest(sfa.DEFAULT_MANIFEST)
    assert err is None, err
    return {e["path"]: e for e in entries}


def _write(tmp: Path, rel: str, payload: dict) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


class TestThe0930GateNoLongerRaces:
    def test_manifest_opens_the_five_minute_lanes_after_their_first_fire(self):
        ents = _entries()
        for rel in FIVE_MIN_LANES:
            start = ents[rel]["window_et"][0]
            assert start >= "09:36", f"{rel} age window opens {start}: the 09:30:01 gate races the 09:30:08 first tick"
            assert ents[rel]["date_expected_after_et"] <= "09:36"

    def test_friday_stamp_is_green_at_the_monday_gate(self, tmp_path):
        ents = _entries()
        for rel, field in FIVE_MIN_LANES.items():
            _write(tmp_path, rel, {field: FRIDAY_STAMP})
            r = sfa.evaluate_entry(ents[rel], MON_0930_GATE, NO_HOLIDAYS, repo=tmp_path)
            assert r["status"] == "GREEN", (rel, r["reasons"])

    def test_friday_stamp_still_reds_once_the_window_is_open(self, tmp_path):
        """The fix must not disable the check: a lane that never started today reds by 09:41."""
        ents = _entries()
        for rel, field in FIVE_MIN_LANES.items():
            _write(tmp_path, rel, {field: FRIDAY_STAMP})
            r = sfa.evaluate_entry(ents[rel], MON_0941, NO_HOLIDAYS, repo=tmp_path)
            assert r["status"] != "GREEN", (rel, r["reasons"])


class TestWeekdayEodWriterSurvivesTheWeekend:
    def test_budget_covers_a_long_weekend(self):
        e = _entries()[EOD]
        assert e["max_age_min"] is None or e["max_age_min"] >= 4400, e["max_age_min"]
        assert e["date_field"] == "date" and e["date_expected_after_et"] == "16:15"

    def test_friday_report_is_green_monday_morning(self, tmp_path):
        _write(tmp_path, EOD, {"date": "2026-09-11", "written_at_et": FRIDAY_STAMP})
        r = sfa.evaluate_entry(_entries()[EOD], MON_0930_GATE, NO_HOLIDAYS, repo=tmp_path)
        assert r["status"] == "GREEN", r["reasons"]

    def test_friday_report_is_stale_by_tuesday_morning(self, tmp_path):
        """Monday's 16:12 run never happened -> Tuesday morning expects Monday's date."""
        _write(tmp_path, EOD, {"date": "2026-09-11", "written_at_et": FRIDAY_STAMP})
        r = sfa.evaluate_entry(_entries()[EOD], TUE_0930, NO_HOLIDAYS, repo=tmp_path)
        assert r["status"] != "GREEN", r["reasons"]
        assert "SESSION" in " ".join(r["reasons"]).upper()
