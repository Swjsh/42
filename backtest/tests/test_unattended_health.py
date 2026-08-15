"""Guard tests for setup/scripts/unattended_health.py -- the ONE-traffic-light-per-
unattended-unit collector built 2026-08-09 on J's ask ("find, consolidate and document
all running processes, audits, pipelines ... i want to know if things break when they
go down now days after the facts").

Every test below RED-proofs a defect that the first working build actually produced, or
a false-alarm class that would get the tile ignored -- which is how monitors die.

Coverage:
  * an OFF (retired-by-design) member must NOT drag its healthy unit out of GREEN
    <- the live trading engine rendered as "off" on the first run, because OFF outranks
       GREEN in STATUS_RANK and the fold used a plain max()
  * a unit whose members are ALL off-by-design is OFF, never GREEN
  * a Mon-Fri task quiet since Friday is GREEN on a Sunday (weekend slack)
  * ... and the SAME task quiet for three weeks is RED (slack must not become amnesty)
  * a WeeklyTrigger carrying a DaysOfWeek mask is scored DAILY, not weekly
    <- scoring it at 10080m gave every Mon-Fri task a 3-week licence to be dead
  * NEVER RUN inside its start-boundary budget is YELLOW (not RED, not GREEN)
    <- the 2026-08-07 task-rebuild wave reset 12 LastRunTimes and read as 12 outages
  * NEVER RUN long past that budget is RED at critical/high, YELLOW at medium/low
  * a nonzero last exit code is flagged
  * a task documented in the registry but absent from Task Scheduler is flagged
  * the coverage diff surfaces live tasks that no unit claims (anti-rot, L292)
  * daemon liveness: dead pid -> fail, unreadable pid -> UNKNOWN (never a false RED)
  * MEMORY: a status change emits a transition; an unchanged status preserves `since`
  * audit() fails OPEN (UNKNOWN, no raise) on an unreadable or malformed registry

Pure functions + a frozen clock + tmp_path. No network, no PowerShell, no LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import unattended_health as uh  # noqa: E402

# Sunday 2026-08-09 15:00 ET -- the clock this instrument was built under, and the one
# that makes every weekend-slack assertion below meaningful.
SUNDAY = datetime(2026, 8, 9, 15, 0, 0)
MON_FRI = 62  # Windows DaysOfWeek bitmask: Mon|Tue|Wed|Thu|Fri


def _task(name="Gamma_X", state="Ready", last_run=None, last_result=0, triggers=None,
          next_run=None):
    return {"name": name, "state": state, "last_run": last_run, "last_result": last_result,
            "next_run": next_run, "triggers": triggers if triggers is not None else [
                {"type": "MSFT_TaskDailyTrigger", "start_boundary": "2026-01-01T06:00:00-06:00",
                 "repetition_interval": None, "repetition_duration": None,
                 "days_of_week": None, "enabled": True}]}


def _weekday_trigger(start="2026-08-07T06:35:00-06:00", interval=None, duration=None):
    return {"type": "MSFT_TaskWeeklyTrigger", "start_boundary": start,
            "repetition_interval": interval, "repetition_duration": duration,
            "days_of_week": MON_FRI, "enabled": True}


# ---------------------------------------------------------------------------
# Duration + cadence parsing
# ---------------------------------------------------------------------------

def test_iso_duration_parsing():
    assert uh.parse_iso_duration_minutes("PT5M") == 5
    assert uh.parse_iso_duration_minutes("PT1H30M") == 90
    assert uh.parse_iso_duration_minutes("P1D") == 1440
    assert uh.parse_iso_duration_minutes("P3650D") == 3650 * 1440
    assert uh.parse_iso_duration_minutes(None) is None
    assert uh.parse_iso_duration_minutes("garbage") is None


def test_weekly_trigger_with_dow_mask_is_scored_daily():
    """RED-PROOF: a WeeklyTrigger with a Mon-Fri mask is a DAILY task that skips
    weekends, not a 7-day task. Scoring it at 10080m (as the first build did) gave
    every one of this rig's Mon-Fri tasks a three-week licence to be dead."""
    cadence, _ = uh.expected_gap_minutes([_weekday_trigger()])
    assert cadence == 1440


def test_intraday_repetition_window_is_scored_at_the_daily_rearm():
    """A PT1M repetition that only runs for PT6H30M each day may legitimately be
    quiet all night. Scoring it on the 1-minute interval makes it a nightly false
    alarm -- the honest budget is the daily re-arm."""
    cadence, why = uh.expected_gap_minutes(
        [_weekday_trigger(interval="PT1M", duration="PT6H30M")])
    assert cadence == 1440
    assert "daily window" in why


def test_no_cadence_contract_for_oneshot_triggers():
    cadence, _ = uh.expected_gap_minutes(
        [{"type": "MSFT_TaskBootTrigger", "start_boundary": None, "repetition_interval": None,
          "repetition_duration": None, "days_of_week": None, "enabled": True}])
    assert cadence is None


# ---------------------------------------------------------------------------
# Axis A -- task liveness
# ---------------------------------------------------------------------------

def test_weekday_task_quiet_since_friday_is_green_on_sunday():
    """RED-PROOF (false-alarm class): a Mon-Fri task last run Friday afternoon has
    done nothing wrong by Sunday. Without unscheduled-day slack the tile would be a
    wall of red every weekend, and a wall of red is a tile nobody reads."""
    t = _task(last_run="2026-08-07T14:00:00-06:00", triggers=[_weekday_trigger()])
    res = uh.evaluate_task(t, "critical", SUNDAY, {})
    assert res["status"] == "GREEN", res["detail"]


def test_weekday_task_quiet_for_three_weeks_is_red():
    """The complement: slack must absorb weekends, NOT excuse a genuine outage."""
    t = _task(last_run="2026-07-17T14:00:00-06:00", triggers=[_weekday_trigger()])
    res = uh.evaluate_task(t, "critical", SUNDAY, {})
    assert res["status"] == "RED"
    assert "HAS NOT FIRED" in res["detail"]


def test_stale_task_severity_follows_unit_criticality():
    t = _task(last_run="2026-07-17T14:00:00-06:00", triggers=[_weekday_trigger()])
    assert uh.evaluate_task(t, "low", SUNDAY, {})["status"] == "YELLOW"
    assert uh.evaluate_task(t, "high", SUNDAY, {})["status"] == "RED"


def test_never_run_inside_start_boundary_budget_is_yellow():
    """RED-PROOF: on 2026-08-07 a task-rebuild wave reset 12 LastRunTimes to the
    'never' sentinel. Scored from epoch they read as 12 chronic outages; scored from
    the trigger's own start boundary they are 12 tasks waiting for Monday. YELLOW,
    not GREEN -- 'not yet proven broken' must not render as 'proven working'."""
    t = _task(last_run=None, last_result=uh._RESULT_NEVER_RUN,
              triggers=[_weekday_trigger(start="2026-08-07T06:35:00-06:00")],
              next_run="2026-08-10T06:35:00-06:00")
    res = uh.evaluate_task(t, "critical", SUNDAY, {})
    assert res["status"] == "YELLOW", res["detail"]
    assert "no fire yet" in res["detail"]


def test_never_run_long_past_budget_is_red():
    t = _task(last_run=None, last_result=uh._RESULT_NEVER_RUN,
              triggers=[_weekday_trigger(start="2026-06-01T06:35:00-06:00")])
    res = uh.evaluate_task(t, "high", SUNDAY, {})
    assert res["status"] == "RED"
    assert "HAS NEVER RUN" in res["detail"]


def test_nonzero_exit_code_is_flagged():
    t = _task(last_run="2026-08-09T12:55:00-06:00", last_result=1)
    res = uh.evaluate_task(t, "medium", SUNDAY, {})
    assert res["status"] == "YELLOW"
    assert "EXITED 1" in res["detail"]


def test_running_and_not_yet_run_result_codes_are_benign():
    for code in (uh._RESULT_RUNNING, uh._RESULT_NEVER_RUN, 0, None):
        t = _task(last_run="2026-08-09T12:55:00-06:00", last_result=code)
        assert uh.evaluate_task(t, "critical", SUNDAY, {})["status"] == "GREEN"


def test_undocumented_disabled_task_fails_but_documented_one_is_off():
    t = _task(state="Disabled")
    assert uh.evaluate_task(t, "critical", SUNDAY, {})["status"] == "RED"
    off = uh.evaluate_task(t, "critical", SUNDAY, {"Gamma_X": "retired 2026-06-25"})
    assert off["status"] == "OFF"
    assert "retired 2026-06-25" in off["detail"]


def test_all_triggers_disabled_is_a_failure():
    trig = _weekday_trigger()
    trig["enabled"] = False
    t = _task(last_run="2026-08-09T12:55:00-06:00", triggers=[trig])
    res = uh.evaluate_task(t, "high", SUNDAY, {})
    assert res["status"] == "RED"
    assert "never fire again" in res["detail"]


# ---------------------------------------------------------------------------
# Unit fold
# ---------------------------------------------------------------------------

def test_off_member_does_not_drag_a_healthy_unit_out_of_green():
    """RED-PROOF (the first build's worst bug): STATUS_RANK puts OFF above GREEN, so a
    plain max() over members rendered the LIVE TRADING ENGINE as 'off' purely because
    the retired Gamma_Heartbeat sits in its expect_disabled list."""
    unit = {"id": "u", "name": "U", "group": "TRADING", "criticality": "critical",
            "tasks": ["Gamma_Live"], "expect_disabled": {"Gamma_Old": "retired"}}
    tasks = {"Gamma_Live": _task(name="Gamma_Live", last_run="2026-08-09T12:55:00-06:00"),
             "Gamma_Old": _task(name="Gamma_Old", state="Disabled")}
    res = uh.evaluate_unit(unit, tasks, {}, SUNDAY, set())
    assert res["status"] == "GREEN", res["problems"]


def test_unit_with_only_retired_members_is_off_not_green():
    unit = {"id": "u", "name": "U", "group": "RESEARCH", "criticality": "low",
            "tasks": [], "expect_disabled": {"Gamma_Old": "on-demand only"}}
    tasks = {"Gamma_Old": _task(name="Gamma_Old", state="Disabled")}
    assert uh.evaluate_unit(unit, tasks, {}, SUNDAY, set())["status"] == "OFF"


def test_registry_task_missing_from_task_scheduler_is_flagged():
    unit = {"id": "u", "name": "U", "group": "TRADING", "criticality": "high",
            "tasks": ["Gamma_Vanished"]}
    res = uh.evaluate_unit(unit, {}, {}, SUNDAY, set())
    assert res["status"] == "RED"
    assert res["tasks"][0]["state"] == "MISSING"


def test_artifact_absent_from_manifest_is_unknown_not_green():
    """A unit referencing a contract that does not exist must not read as healthy --
    that is the silent-scope-rot shape (L292) one level down."""
    unit = {"id": "u", "name": "U", "group": "DATA", "criticality": "high",
            "tasks": [], "artifacts": ["automation/state/nope.json"]}
    res = uh.evaluate_unit(unit, {}, {}, SUNDAY, set())
    assert res["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Axis C -- daemons
# ---------------------------------------------------------------------------

def test_missing_pid_file_fails(tmp_path):
    res = uh.evaluate_daemon({"name": "d", "pid_file": "nope.pid"}, "high", tmp_path)
    assert res["status"] == "RED"


def test_unreadable_pid_is_unknown_never_a_false_red(tmp_path):
    """'I could not look' must never be reported as 'it is dead'."""
    (tmp_path / "d.pid").write_text("not-a-pid", encoding="utf-8")
    res = uh.evaluate_daemon({"name": "d", "pid_file": "d.pid"}, "critical", tmp_path)
    assert res["status"] == "UNKNOWN"


def test_pid_file_shapes(tmp_path):
    """This repo writes three pid-file shapes; all three must parse or a live daemon
    reads as dead."""
    (tmp_path / "a.pid").write_text("1234", encoding="utf-8")
    (tmp_path / "b.pid").write_text("1234|2026-08-09T16:22:01Z", encoding="utf-8")
    (tmp_path / "c.pid").write_text(json.dumps({"pid": 1234, "started_at_utc": "x"}),
                                    encoding="utf-8")
    for f in ("a.pid", "b.pid", "c.pid"):
        assert uh._read_pid(tmp_path / f) == 1234, f


def test_dead_pid_fails(tmp_path, monkeypatch):
    (tmp_path / "d.pid").write_text("999999", encoding="utf-8")
    monkeypatch.setattr(uh, "_pid_alive", lambda pid: False)
    res = uh.evaluate_daemon({"name": "d", "pid_file": "d.pid"}, "medium", tmp_path)
    assert res["status"] == "YELLOW"
    assert "DEAD" in res["detail"]


# ---------------------------------------------------------------------------
# Memory -- the "days after the fact" contract
# ---------------------------------------------------------------------------

def test_status_change_emits_a_transition_and_resets_since():
    units = [{"id": "u", "name": "U", "group": "DATA", "criticality": "high",
              "status": "RED", "problems": ["boom"], "breaks": "x"}]
    prev = {"u": {"id": "u", "status": "GREEN", "since": "2026-08-01 09:00:00"}}
    trans = uh.apply_memory(units, SUNDAY, prev)
    assert len(trans) == 1 and trans[0]["from"] == "GREEN" and trans[0]["to"] == "RED"
    assert units[0]["since"] == "2026-08-09 15:00:00"


def test_unchanged_status_preserves_since_so_downtime_accumulates():
    """THE ASK. A unit that went down on Tuesday must still read 'down for 5d' on
    Sunday -- if `since` reset every run, every outage would look brand new."""
    units = [{"id": "u", "name": "U", "group": "DATA", "criticality": "high",
              "status": "RED", "problems": [], "breaks": "x"}]
    prev = {"u": {"id": "u", "status": "RED", "since": "2026-08-04 09:00:00"}}
    trans = uh.apply_memory(units, SUNDAY, prev)
    assert trans == []
    assert units[0]["since"] == "2026-08-04 09:00:00"
    assert units[0]["down_minutes"] > 7000  # ~5.25 days
    assert units[0]["down_for"].endswith("d")


def test_first_sighting_logs_an_event_only_when_unhealthy():
    units = [{"id": "ok", "name": "OK", "group": "DATA", "criticality": "low",
              "status": "GREEN", "problems": [], "breaks": ""},
             {"id": "bad", "name": "BAD", "group": "DATA", "criticality": "low",
              "status": "RED", "problems": ["x"], "breaks": ""}]
    trans = uh.apply_memory(units, SUNDAY, {})
    assert [t["id"] for t in trans] == ["bad"]
    assert trans[0]["from"] == "(first seen)"


def test_events_ledger_is_capped(tmp_path):
    """OP-22: every append-only producer carries a retention cap."""
    ledger = tmp_path / "events.jsonl"
    ledger.write_text("\n".join(json.dumps({"id": f"x{i}"}) for i in range(60)) + "\n",
                      encoding="utf-8")
    uh.append_events([{"id": "new", "ts_et": "2026-08-09 15:00:00"}], ledger, cap=10)
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 10
    assert json.loads(lines[-1])["id"] == "new"


# ---------------------------------------------------------------------------
# Fail-open contract -- a broken monitor must never look like a broken rig
# ---------------------------------------------------------------------------

def test_audit_fails_open_on_missing_registry(tmp_path):
    rep = uh.audit(registry_path=tmp_path / "nope.json", write=False)
    assert rep["verdict"] == "UNKNOWN"
    assert "unreadable" in rep["reason"]


def test_audit_fails_open_on_malformed_registry(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rep = uh.audit(registry_path=bad, write=False)
    assert rep["verdict"] == "UNKNOWN"
    assert rep["units"] == []


def test_shipped_registry_is_valid_and_every_unit_names_a_consequence():
    """A traffic light with no consequence attached is decoration. `breaks` is the
    field that turns a red bubble into a decision, so it is mandatory."""
    reg = json.loads(uh.REGISTRY.read_text(encoding="utf-8"))
    units = list(reg["units"]) + list(reg.get("external_units") or [])
    assert units
    ids = [u["id"] for u in units]
    assert len(ids) == len(set(ids)), "unit ids must be unique -- they key the ledger"
    for u in units:
        for field in ("id", "name", "group", "criticality", "what", "breaks"):
            assert u.get(field), f"{u.get('id')} missing {field}"
        assert u["criticality"] in uh._BY_CRIT
        assert u["group"] in ("TRADING", "DATA", "AUDIT", "RESEARCH", "REPORTING", "INFRA")


def test_nightly_fold_subproducts_are_covered_not_just_their_parent():
    """RED-PROOF (2026-08-15): the winner-autopsy fold contract is "fail-open, never fatal",
    so every folded shadow producer can fail -- or never be wired at all -- forever, while the
    PARENT artifact (winner-autopsy-last.json) stays perfectly fresh. Covering only the parent
    is what let entry-quality-ledger.json sit frozen at 2026-08-06 for five trading days,
    which in turn pinned an ARMED prereg's forward clock at n_trades=0 / ARMED_AWAITING_FILLS
    -- a state indistinguishable from a genuine absence of fills.

    Each sub-product must be covered by its OWN BUILD STAMP, never a data-derived date: on a
    legitimate no-trade session a data date parks on the last day with fills, and keying
    freshness off that would alarm every time the engine correctly sat out."""
    reg = json.loads(uh.REGISTRY.read_text(encoding="utf-8"))
    unit = next(u for u in reg["units"] if u["id"] == "eod-pipeline")
    covered = {a["path"] if isinstance(a, dict) else a for a in unit.get("artifacts") or []}
    for required in ("analysis/entry-quality/entry-quality-ledger.json",
                     "analysis/recommendations/stop-mode-shadow-summary.json"):
        assert required in covered, (
            f"{required} is produced by the 16:25 fold and read by a forward clock, but no "
            "unit watches it -- a dead clock would again be invisible for weeks")
    for art in unit.get("artifacts") or []:
        if not isinstance(art, dict) or art["path"] not in covered:
            continue
        if art["path"].startswith("analysis/"):
            assert art.get("date_field"), f"{art['path']} needs a build-stamp date_field"
            assert art.get("criticality") == "medium", (
                f"{art['path']}: research artifacts stay YELLOW -- a RED on the trading tile "
                "for a research clock is how a tile gets ignored")


def test_shipped_registry_manifest_refs_all_resolve():
    """Every string artifact ref must resolve in state-freshness-manifest.json --
    otherwise the unit silently degrades to UNKNOWN forever and nobody notices."""
    reg = json.loads(uh.REGISTRY.read_text(encoding="utf-8"))
    manifest = uh._manifest_index()
    missing = [(u["id"], a) for u in reg["units"] for a in (u.get("artifacts") or [])
               if isinstance(a, str) and a not in manifest]
    assert not missing, f"unresolved manifest refs: {missing}"


# ---------------------------------------------------------------------------
# Clock purity -- RED-PROOF for the 2026-08-15 wall-clock coupling defect
# ---------------------------------------------------------------------------

def test_et_offset_does_not_drift_with_the_wall_clock():
    """RED-PROOF: `_et_offset_hours` derived ET-minus-local by differencing its
    argument against `datetime.now()`. That is only correct when the argument IS
    now. Driven with a frozen fixture clock it returned the DISTANCE from today
    (-140 "hours" for SUNDAY), shifting every converted stamp by ~6 days and
    manufacturing 5 fake outages. A timezone offset is a property of a DATE, so
    it must stay bounded no matter how stale the caller's clock is."""
    for clock in (SUNDAY, datetime(2020, 1, 2, 3, 4), datetime(2026, 12, 25, 9, 0)):
        off = uh._et_offset_hours(clock)
        assert -12 <= off <= 12, f"{clock} -> {off}h is a clock difference, not an offset"


def test_task_verdict_depends_only_on_its_frozen_clock():
    """The contract `evaluate_task` advertises ("pure apart from its inputs, so the
    guard can drive it with synthetic task dicts and a frozen clock"). A task that
    ran 2h before the frozen clock is GREEN -- and stays GREEN however far in the
    past that frozen clock sits. Under the old code the same fixture read
    'HAS NOT FIRED in 5.9d' purely because the suite ran 6 days later."""
    for clock in (SUNDAY, datetime(2026, 3, 11, 15, 0), datetime(2025, 11, 5, 15, 0)):
        last = (clock - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        res = uh.evaluate_task(_task(last_run=last), "critical", clock, {})
        assert res["status"] == "GREEN", f"{clock}: {res['detail']}"


# ---------------------------------------------------------------------------
# DaysOfWeek normalisation -- crash hardening on the live evaluation path
# ---------------------------------------------------------------------------

def test_days_of_week_accepts_every_shape_without_raising():
    """RED-PROOF: `_scheduled_days_mask` did a bare `int(dow)`, which raises
    TypeError on a list. The live enumerator casts `[int]$tr.DaysOfWeek` so this
    is latent today, but an unhandled raise here kills the monitor whose only job
    is noticing that things are dead (C7)."""
    assert uh._dow_mask_value(MON_FRI) == MON_FRI
    assert uh._dow_mask_value("62") == MON_FRI
    assert uh._dow_mask_value(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]) == MON_FRI
    assert uh._dow_mask_value([2, 4, 8, 16, 32]) == MON_FRI
    assert uh._dow_mask_value("Monday") == 2
    assert uh._dow_mask_value(None) == 0
    assert uh._dow_mask_value("garbage") == 0
    assert uh._dow_mask_value(["garbage", "Monday"]) == 2


def test_list_shaped_days_of_week_survives_the_whole_evaluator():
    """The exact repro from the 2026-08-15 handoff, driven end-to-end rather than
    at the helper -- a fix that only satisfies the unit is a half-fix."""
    trig = dict(_weekday_trigger(), days_of_week=["Monday", "Tuesday", "Wednesday",
                                                  "Thursday", "Friday"])
    assert uh._scheduled_days_mask([trig]) == MON_FRI
    assert uh.expected_gap_minutes([trig])[0] == 1440
    res = uh.evaluate_task(_task(last_run="2026-08-07T14:00:00-06:00", triggers=[trig]),
                           "critical", SUNDAY, {})
    assert res["status"] == "GREEN", res["detail"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
