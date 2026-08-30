"""The lane rail must report each lane's OWN pulse, never its task state.

J, 2026-08-30: "wheres the kitchen? ... wheres the futures, wheres the tech analyiss on
tickets non spy". Two separate failures produced that question -- the lanes were switched
off (quiet mode, fixed in 590b39dc) AND the desk had nowhere to show them.

The trap this file exists to pin: it is very tempting to derive a lane's state from
whether its scheduled tasks are Enabled, because that data is right there and it makes a
tidy green rail. It is also wrong. On the day this shipped the multi-symbol lane's tasks
were all Ready and its newest artefact was ten days old -- a task-derived roster would
have drawn it green and answered the exact question J was asking with a lie.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup" / "scripts"))
import gamma_lanes as gl  # noqa: E402


class TestStateComesFromArtefacts:
    def test_fresh_artefact_is_working(self):
        assert gl._state_for("kitchen", 5) == "WORKING"

    def test_old_artefact_is_stale_however_healthy_the_tasks_look(self):
        """The multi-symbol case: tasks Ready, last output ten days ago."""
        assert gl._state_for("multi", 10 * 24 * 60) == "STALE"

    def test_missing_artefact_is_not_silently_working(self):
        assert gl._state_for("kitchen", None) == "NO DATA"

    def test_broken_beats_freshness(self):
        """A lane writing files while failing every entry is broken, not working."""
        assert gl._state_for("futures", 1, broken=True) == "BROKEN"

    def test_thresholds_are_per_lane(self):
        """One global threshold would cry wolf on the slow lane or go quiet on the fast.

        90 minutes is stale for the kitchen (it turns a task over in minutes) and
        perfectly healthy for the prospector (multi-hour beat).
        """
        assert gl._state_for("kitchen", 120) == "STALE"
        assert gl._state_for("prospector", 120) == "WORKING"


class TestHeldIsNotBroken:
    """Quiet mode holding a lane down and a lane failing are opposite situations."""

    def test_all_disabled_reads_as_held(self):
        assert gl._held({"Gamma_KitchenSeeder": "Disabled",
                         "Gamma_KitchenReviewer": "Disabled"}) is True

    def test_any_enabled_is_not_held(self):
        assert gl._held({"Gamma_KitchenSeeder": "Ready",
                         "Gamma_KitchenReviewer": "Disabled"}) is False

    def test_no_known_tasks_is_not_held(self):
        """Absence of task data must never be reported as a deliberate hold."""
        assert gl._held({}) is False


class TestBuild:
    def test_build_returns_every_lane_j_asked_about(self):
        out = gl.build()
        ids = {l["id"] for l in out["lanes"]}
        for want in ("kitchen", "futures", "multi", "prospector", "spy"):
            assert want in ids, "{} missing from the rail".format(want)

    def test_every_row_carries_what_the_rail_renders(self):
        for lane in gl.build()["lanes"]:
            for key in ("id", "label", "state", "detail", "metric", "metric_label"):
                assert key in lane, "{} lacks {}".format(lane.get("id"), key)
            assert lane["state"] in {"WORKING", "STALE", "HELD", "BROKEN",
                                     "NO DATA", "ERROR"}, lane["state"]

    def test_a_failing_lane_still_produces_a_row(self, monkeypatch):
        """Dropping the row would read as 'this lane does not exist' -- the exact
        invisibility that prompted the whole feature."""
        monkeypatch.setattr(gl, "lane_kitchen",
                            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        out = gl.build()
        bad = [l for l in out["lanes"] if l["state"] == "ERROR"]
        assert len(bad) == 1
        assert "boom" in bad[0]["detail"]

    def test_output_is_json_serialisable(self):
        """It is served over HTTP; a stray Path or datetime would 500 the endpoint."""
        json.dumps(gl.build(), default=str)

    def test_build_is_read_only(self, monkeypatch):
        """A status reader that writes is a status reader that can corrupt state."""
        def boom(*a, **k):
            raise AssertionError("gamma_lanes must never write")
        monkeypatch.setattr(Path, "write_text", boom)
        monkeypatch.setattr(Path, "write_bytes", boom)
        gl.build()


class TestTaskTableIsFetchedOnce:
    """Five lanes each spawning PowerShell made desk_live take 7.35s, served to a
    client polling every 30s. One call, cached for the process."""

    def test_all_tasks_is_cached(self, monkeypatch):
        calls = []
        gl._TASK_CACHE.clear()

        class FakeRun:
            stdout = json.dumps([{"TaskName": "Gamma_KitchenSeeder", "State": 3}])

        def fake(*a, **k):
            calls.append(1)
            return FakeRun()

        monkeypatch.setattr(gl.subprocess, "run", fake)
        gl._all_tasks(); gl._all_tasks(); gl._all_tasks()
        assert len(calls) == 1, "the task table must be fetched once per process"
        gl._TASK_CACHE.clear()

    def test_powershell_failure_degrades_to_empty_not_crash(self, monkeypatch):
        gl._TASK_CACHE.clear()
        monkeypatch.setattr(gl.subprocess, "run",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("no shell")))
        assert gl._all_tasks() == {}
        gl._TASK_CACHE.clear()
