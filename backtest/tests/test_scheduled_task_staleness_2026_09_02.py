"""Guards for setup/scripts/scheduled_task_staleness.py.

The instrument exists because Gamma_GuardsFull went dark for 48h while State=Ready and
LastTaskResult=0 kept every dashboard green. These tests pin the properties that make the
report trustworthy -- above all that "we could not tell" never renders as "fine".
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "setup" / "scripts" / "scheduled_task_staleness.py"


def _load():
    spec = importlib.util.spec_from_file_location("scheduled_task_staleness", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scheduled_task_staleness"] = mod
    spec.loader.exec_module(mod)
    return mod


sts = _load()
ET = sts.ET
NOW = dt.datetime(2026, 9, 2, 4, 30, tzinfo=ET)


def _row(**kw):
    base = {
        "name": "Gamma_Thing", "state": "Ready", "lastRun": None, "nextRun": None,
        "lastResult": 0, "missedRuns": 0, "triggerKind": "MSFT_TaskDailyTrigger",
        "startBound": "2026-08-20T21:15:00-06:00", "repeat": None,
    }
    base.update(kw)
    return base


def _ago(minutes: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------------------
# The severity rule. This is the defect that shipped in first_live_day_review.py the same
# night: ranking "no data" better than GREEN grades an empty box as a clean pass.
# ---------------------------------------------------------------------------------------

def test_unknown_is_never_better_than_green():
    assert sts.SEVERITY["UNKNOWN"] > sts.SEVERITY["GREEN"]


def test_worst_prefers_unknown_over_green():
    assert sts.worst(["GREEN", "UNKNOWN", "GREEN"]) == "UNKNOWN"


def test_worst_prefers_red_over_everything():
    assert sts.worst(["GREEN", "UNKNOWN", "YELLOW", "RED", "DISABLED"]) == "RED"


def test_worst_on_empty_is_unknown_not_green():
    """A run that classified nothing has verified nothing."""
    assert sts.worst([]) == "UNKNOWN"


def test_disabled_never_escalates():
    assert sts.SEVERITY["DISABLED"] <= sts.SEVERITY["GREEN"]


# ---------------------------------------------------------------------------------------
# Query failure must not look healthy.
# ---------------------------------------------------------------------------------------

def test_none_rows_is_unknown_not_green():
    rep = sts.build_report(None, now=NOW)
    assert rep["verdict"] == "UNKNOWN"
    assert "query itself failed" in rep["reason"]
    assert rep["tasks"] == []


def test_empty_task_list_is_unknown_not_green():
    rep = sts.build_report([], now=NOW)
    assert rep["verdict"] == "UNKNOWN"


def test_all_disabled_is_unknown_not_green():
    """Every task disabled means nothing was actually verified -- must not read as GREEN."""
    rows = [_row(name=f"Gamma_A{i}", state="Disabled") for i in range(3)]
    rep = sts.build_report(rows, now=NOW)
    assert rep["verdict"] == "UNKNOWN"
    assert rep["counts"]["DISABLED"] == 3


# ---------------------------------------------------------------------------------------
# missed-run detection -- the field nothing in the rig read before this.
# ---------------------------------------------------------------------------------------

def test_two_missed_runs_is_red():
    out = sts.classify_task(_row(missedRuns=2, lastRun=_ago(60)), now=NOW)
    assert out["verdict"] == "RED"
    assert "2 missed scheduled start" in out["reason"]


def test_one_missed_run_is_yellow():
    out = sts.classify_task(_row(missedRuns=1, lastRun=_ago(60)), now=NOW)
    assert out["verdict"] == "YELLOW"


def test_missed_runs_beats_a_fresh_last_run():
    """The exact GuardsFull shape: a recent manual run must not mask missed triggers."""
    out = sts.classify_task(_row(missedRuns=2, lastRun=_ago(5)), now=NOW)
    assert out["verdict"] == "RED"


def test_zero_missed_and_recent_is_green():
    out = sts.classify_task(_row(missedRuns=0, lastRun=_ago(60)), now=NOW)
    assert out["verdict"] == "GREEN"


def test_disabled_task_is_bucketed_not_alarmed():
    out = sts.classify_task(_row(state="Disabled", missedRuns=9), now=NOW)
    assert out["verdict"] == "DISABLED"
    assert "quiet mode" in out["reason"]


def test_never_ran_is_unknown_not_green():
    out = sts.classify_task(_row(lastRun=None, missedRuns=0), now=NOW)
    assert out["verdict"] == "UNKNOWN"
    assert "EVER" in out["reason"]


def test_task_with_no_trigger_is_unknown():
    out = sts.classify_task(_row(triggerKind="NONE", lastRun=_ago(10)), now=NOW)
    assert out["verdict"] == "UNKNOWN"


# ---------------------------------------------------------------------------------------
# Tolerance is derived per task, never global.
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("PT5M", 5.0), ("PT30M", 30.0), ("PT1H", 60.0), ("PT1H15M", 75.0),
    ("P1D", 1440.0), ("PT2H30M", 150.0),
])
def test_parse_iso_duration(value, expected):
    assert sts.parse_iso_duration_minutes(value) == expected


@pytest.mark.parametrize("bad", [None, "", "garbage", "5 minutes", "PT"])
def test_parse_iso_duration_rejects_garbage(bad):
    assert sts.parse_iso_duration_minutes(bad) is None


def test_repeating_tolerance_is_four_intervals():
    tol, basis = sts.tolerance_minutes(_row(repeat="PT15M"))
    assert tol == 60.0
    assert "repeating" in basis


def test_repeating_tolerance_has_a_floor():
    """A 1-minute repeater must not get a 4-minute bar -- one slow tick is not an outage."""
    tol, _ = sts.tolerance_minutes(_row(repeat="PT1M"))
    assert tol == 30.0


def test_daily_tolerance_catches_one_missed_night():
    tol, basis = sts.tolerance_minutes(_row(triggerKind="MSFT_TaskDailyTrigger"))
    assert tol == 36 * 60
    assert "daily" in basis
    # A 48h bar would have stayed silent through the real 2026-08-31 -> 09-02 outage.
    assert tol < 48 * 60


def test_weekly_tolerance_tolerates_a_late_sunday():
    tol, _ = sts.tolerance_minutes(_row(triggerKind="MSFT_TaskWeeklyTrigger"))
    assert 7 * 1440 < tol <= 10 * 1440


def test_bounded_repeater_is_judged_daily_not_per_interval():
    """The live Gamma_RosterLiveness shape: every 20m but only FOR 40m, then idle by design.

    Under a bare 4-interval bar this was RED for the 23 hours a day it is correctly idle --
    the first run of this script flagged 37 tasks, most of them this false positive.
    """
    tol, basis = sts.tolerance_minutes(_row(repeat="PT20M", repeatFor="PT40M"))
    assert tol == 1440 + 40 + 80
    assert "idle by design" in basis
    # 21.2h idle -- the real observed value -- must be GREEN...
    out = sts.classify_task(
        _row(repeat="PT20M", repeatFor="PT40M", missedRuns=0, lastRun=_ago(21.2 * 60)), now=NOW)
    assert out["verdict"] == "GREEN"


def test_bounded_repeater_still_catches_a_real_outage():
    """The fix must not blind the bar: two days dark is still RED."""
    out = sts.classify_task(
        _row(repeat="PT20M", repeatFor="PT40M", missedRuns=0, lastRun=_ago(60 * 60)), now=NOW)
    assert out["verdict"] in ("YELLOW", "RED")


def test_unbounded_repeater_keeps_the_tight_bar():
    tol, basis = sts.tolerance_minutes(_row(repeat="PT20M", repeatFor=None))
    assert tol == 80.0
    assert "idle by design" not in basis


def test_never_ran_sentinel_is_unknown_not_a_26_year_staleness():
    """Windows stamps 1999-11-30 for 'never ran'. Read literally that is 234,553 hours, and
    the first cut of this script reported exactly that for two tasks registered the day
    before -- a precise, confident, wrong number."""
    out = sts.classify_task(
        _row(lastRun="1999-11-30T00:00:00-07:00", missedRuns=0,
             nextRun="2026-09-02T07:32:00-06:00"), now=NOW)
    assert out["verdict"] == "UNKNOWN"
    assert "NEVER run" in out["reason"]
    assert "234" not in out["reason"]
    assert out["stale_minutes"] is None
    assert out["last_run"] is None


def test_never_ran_names_the_next_scheduled_fire():
    """A never-ran task with a next fire is expected; without one it is stranded. The
    reader needs that distinction in the reason, not in a separate lookup."""
    out = sts.classify_task(
        _row(lastRun="1999-11-30T00:00:00-07:00", nextRun="2026-09-02T07:32:00-06:00"), now=NOW)
    assert "09-02 09:32 ET" in out["reason"]


def test_is_never_ran_predicate():
    assert sts.is_never_ran(dt.datetime(1999, 11, 30, tzinfo=ET))
    assert not sts.is_never_ran(dt.datetime(2026, 9, 1, tzinfo=ET))
    assert not sts.is_never_ran(None)


def test_repeating_wins_over_trigger_kind():
    """A daily trigger that repeats every 5 min is a repeater, not a daily task."""
    tol, basis = sts.tolerance_minutes(
        _row(triggerKind="MSFT_TaskDailyTrigger", repeat="PT5M"))
    assert tol == 30.0
    assert "repeating" in basis


def test_staleness_past_bar_is_yellow_and_double_is_red():
    daily = _row(triggerKind="MSFT_TaskDailyTrigger", missedRuns=0)
    assert sts.classify_task({**daily, "lastRun": _ago(40 * 60)}, now=NOW)["verdict"] == "YELLOW"
    assert sts.classify_task({**daily, "lastRun": _ago(80 * 60)}, now=NOW)["verdict"] == "RED"


# ---------------------------------------------------------------------------------------
# Quiet-hold attribution.
# ---------------------------------------------------------------------------------------

REAL_LOG = """
2026-09-01T22:57:02.845541-04:00 QUIET ON: disabled=0/0 killed=0
2026-09-01T23:02:01.658314-04:00 QUIET HELD past the clock: fullscreen app in foreground (SparkingZERO-Win64-Shipping.exe)
2026-09-01T23:07:01.636476-04:00 QUIET HELD past the clock: linger: SparkingZERO-Win64-Shipping.exe was foreground 5m ago (<15m)
2026-09-01T23:17:01.636389-04:00 QUIET HELD past the clock: linger: SparkingZERO-Win64-Shipping.exe was foreground 15m ago (<15m)
2026-09-01T23:22:04.927077-04:00 QUIET OFF: re-enabled=120/120
2026-09-02T00:07:01.784348-04:00 QUIET HELD past the clock: fullscreen app in foreground (r5apex_dx12.exe)
2026-09-02T00:42:04.805063-04:00 QUIET OFF: re-enabled=117/117
""".strip()


def test_parses_two_holds_from_the_real_log():
    holds = sts.parse_quiet_holds(REAL_LOG, now=NOW)
    assert len(holds) == 2
    assert holds[0][0].astimezone(ET).strftime("%H:%M") == "23:02"
    assert holds[0][1].astimezone(ET).strftime("%H:%M") == "23:22"
    assert holds[1][1].astimezone(ET).strftime("%H:%M") == "00:42"


def test_unterminated_hold_is_closed_at_now():
    text = "2026-09-02T04:00:00.000000-04:00 QUIET HELD past the clock: fullscreen app"
    holds = sts.parse_quiet_holds(text, now=NOW)
    assert len(holds) == 1
    assert holds[0][1] == NOW


def test_no_log_yields_no_holds():
    assert sts.parse_quiet_holds(None, now=NOW) == []
    assert sts.parse_quiet_holds("", now=NOW) == []


def test_guards_full_23_15_et_is_attributed_to_the_hold():
    """The real case: trigger 21:15 -06:00 == 23:15 ET, inside the 23:02-23:22 hold."""
    holds = sts.parse_quiet_holds(REAL_LOG, now=NOW)
    reason = sts.attribute_quiet_hold(
        _row(name="Gamma_GuardsFull", startBound="2026-08-20T21:15:00-06:00"), holds, now=NOW)
    assert reason is not None
    assert "quiet-mode hold" in reason
    assert "StartWhenAvailable" in reason


def test_spend_summary_23_30_et_is_not_attributed():
    """Fired at 23:30 ET, eight minutes after the hold lifted -- and it really did run."""
    holds = sts.parse_quiet_holds(REAL_LOG, now=NOW)
    reason = sts.attribute_quiet_hold(
        _row(name="Gamma_SpendSummary", startBound="2026-08-20T21:30:00-06:00"), holds, now=NOW)
    assert reason is None


def test_guards_nightly_00_30_et_is_attributed_to_the_second_hold():
    holds = sts.parse_quiet_holds(REAL_LOG, now=NOW)
    reason = sts.attribute_quiet_hold(
        _row(name="Gamma_GuardsNightly", startBound="2026-08-20T22:30:00-06:00"), holds, now=NOW)
    assert reason is not None


def test_attribution_refuses_to_claim_innocence_without_evidence():
    """No parsed holds must yield None (unknown), never a 'quiet mode was not involved'."""
    assert sts.attribute_quiet_hold(_row(), [], now=NOW) is None


def test_attribution_skips_non_daily_triggers():
    """Projecting a weekly recurrence from one boundary would manufacture false causes."""
    holds = sts.parse_quiet_holds(REAL_LOG, now=NOW)
    assert sts.attribute_quiet_hold(
        _row(triggerKind="MSFT_TaskWeeklyTrigger"), holds, now=NOW) is None


def test_cause_is_carried_into_the_finding():
    rows = [_row(name="Gamma_GuardsFull", missedRuns=2, lastRun=_ago(3000),
                 startBound="2026-08-20T21:15:00-06:00")]
    rep = sts.build_report(rows, now=NOW, quiet_log_text=REAL_LOG)
    assert rep["verdict"] == "RED"
    assert rep["findings"][0]["cause"] == "quiet_mode_hold"
    assert "LIKELY CAUSE" in rep["findings"][0]["reason"]


# ---------------------------------------------------------------------------------------
# Report shape + robustness.
# ---------------------------------------------------------------------------------------

def test_findings_are_worst_first():
    rows = [
        _row(name="Gamma_Green", missedRuns=0, lastRun=_ago(30)),
        _row(name="Gamma_Yellow", missedRuns=1, lastRun=_ago(30)),
        _row(name="Gamma_Red", missedRuns=5, lastRun=_ago(30)),
    ]
    rep = sts.build_report(rows, now=NOW)
    assert [f["name"] for f in rep["findings"]][0] == "Gamma_Red"
    assert rep["verdict"] == "RED"


def test_disabled_tasks_do_not_gate_the_overall_verdict():
    rows = [
        _row(name="Gamma_Ok", missedRuns=0, lastRun=_ago(30)),
        _row(name="Gamma_Off", state="Disabled", missedRuns=99),
    ]
    rep = sts.build_report(rows, now=NOW)
    assert rep["verdict"] == "GREEN"
    assert rep["counts"]["DISABLED"] == 1


def test_classify_never_raises_on_garbage_rows():
    for bad in [{}, {"name": None}, {"name": "x", "missedRuns": "two"},
                {"name": "x", "lastRun": "not-a-date", "repeat": "???"}]:
        out = sts.classify_task(bad, now=NOW)
        assert out["verdict"] in sts.SEVERITY


def test_write_report_is_atomic_and_leaves_no_temp(tmp_path):
    out = tmp_path / "sub" / "report.json"
    sts.write_report({"verdict": "GREEN"}, out)
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "GREEN"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_main_exits_zero_when_the_query_fails(monkeypatch, tmp_path):
    """Fail-open: a monitor that can break its caller is worse than no monitor."""
    monkeypatch.setattr(sts, "query_tasks", lambda *a, **k: None)
    monkeypatch.setattr(sts, "OUT_FILE", tmp_path / "out.json")
    assert sts.main(["--no-write"]) == 0


def test_module_has_no_write_side_effects_on_import():
    """Report-only: the module must not enable, disable, or start anything."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ("Start-ScheduledTask", "Enable-ScheduledTask",
                      "Disable-ScheduledTask", "Unregister-ScheduledTask"):
        assert forbidden not in src, f"report-only instrument must never call {forbidden}"
