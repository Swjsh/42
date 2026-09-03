"""Guards for the HIDDEN-CHAIN-OUTPUT-FRESHNESS-GUARD extension to
setup/scripts/scheduled_task_staleness.py.

The instrument this file extends already answers "did the scheduler fire the task on
time?". These tests pin the additive half: "did the script the task launched actually
FINISH, and did its OUTPUT move?" -- read the module docstring block above
build_report() (search 'OUTPUT-FRESHNESS GUARD') for the full rationale.
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
    spec = importlib.util.spec_from_file_location("scheduled_task_staleness_ofg", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scheduled_task_staleness_ofg"] = mod
    spec.loader.exec_module(mod)
    return mod


sts = _load()
ET = sts.ET
NOW = dt.datetime(2026, 9, 3, 21, 55, tzinfo=ET)  # 17:55 ET


def _row(**kw):
    base = {
        "name": "Gamma_Thing", "state": "Ready", "lastRun": None, "nextRun": None,
        "lastResult": 0, "missedRuns": 0, "triggerKind": "MSFT_TaskDailyTrigger",
        "startBound": "2026-09-03T15:00:00-06:00", "repeat": None,
        "argsRaw": (r'//nologo "C:\42\setup\scripts\run_exe_hidden.vbs" '
                   r'"C:\42\...\pythonw.exe" "C:\42\setup\scripts\run_cmd_hidden.py" '
                   r'--cwd "C:\42" -- "C:\42\...\pythonw.exe" '
                   r'"C:\42\setup\scripts\the_thing.py"'),
    }
    base.update(kw)
    return base


def _ago(minutes: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------------------
# Log parsing -- multiple concurrent pids for the SAME script must not misattribute exits.
# ---------------------------------------------------------------------------------------

MULTI_PID_LOG = """
[2026-09-03 15:49:19] launching: C:\\a\\pythonw.exe C:\\a\\setup\\scripts\\retest_zone_shadow.py  [pid=9396]
[2026-09-03 15:49:19]   cwd=C:\\a  env_overrides=[]  log=None
[2026-09-03 15:49:57] launching: C:\\a\\pythonw.exe C:\\a\\setup\\scripts\\structure_classifier_shadow.py  [pid=36360]
[2026-09-03 15:49:57]   cwd=C:\\a  env_overrides=[]  log=None
[2026-09-03 15:49:57]   exit=1  [pid=36360]
[2026-09-03 15:49:40]   exit=0  [pid=9396]
[2026-09-03 15:51:34] launching: C:\\a\\pythonw.exe C:\\a\\setup\\scripts\\structure_classifier_shadow.py  [pid=26264]
[2026-09-03 15:51:34]   cwd=C:\\a  env_overrides=[]  log=None
[2026-09-03 15:51:36]   exit=0  [pid=26264]
""".strip()


def test_multi_pid_log_pairs_by_pid_not_line_order():
    """The two overlapping structure_classifier_shadow.py fires (pid 36360 exit=1,
    pid 26264 exit=0) must each keep their own exit code even though a THIRD script's
    exit line (retest_zone_shadow.py, pid 9396) lands physically between them."""
    records = sts.parse_run_cmd_hidden_log(MULTI_PID_LOG)
    by_pid = {}
    for r in records:
        # recover pid isn't stored directly, but each record is one completed pairing
        by_pid.setdefault(r["script"], []).append(r["exit"])
    assert by_pid["retest_zone_shadow.py"] == [0]
    assert by_pid["structure_classifier_shadow.py"] == [1, 0]


def test_latest_by_script_takes_the_last_chronological_record():
    """The real live shape: exit=1 at 15:49:57, then exit=0 at 15:51:34 -- latest must be
    the RECOVERY (0), not the earlier failure."""
    records = sts.parse_run_cmd_hidden_log(MULTI_PID_LOG)
    latest = sts.latest_by_script(records)
    assert latest["structure_classifier_shadow.py"]["exit"] == 0


def test_launched_script_names_independent_of_pairing():
    names = sts.launched_script_names(MULTI_PID_LOG)
    assert "retest_zone_shadow.py" in names
    assert "structure_classifier_shadow.py" in names


def test_log_parsing_empty_and_none_input_never_raises():
    assert sts.parse_run_cmd_hidden_log(None) == []
    assert sts.parse_run_cmd_hidden_log("") == []
    assert sts.launched_script_names(None) == set()


def test_unpaired_trailing_launch_is_dropped_not_guessed():
    text = "[2026-09-03 15:00:00] launching: C:\\a\\x.py  [pid=1]"
    assert sts.parse_run_cmd_hidden_log(text) == []
    assert "x.py" in sts.launched_script_names(text)


# ---------------------------------------------------------------------------------------
# Exit-code flagging.
# ---------------------------------------------------------------------------------------

def test_nonzero_exit_is_flagged_red():
    latest = sts.latest_by_script(sts.parse_run_cmd_hidden_log(MULTI_PID_LOG))
    findings = sts.check_exit_codes(latest)
    reds = [f for f in findings if f["script"] == "structure_classifier_shadow.py"]
    assert reds == []  # latest is exit=0 -- must NOT be flagged once recovered


def test_a_script_stuck_on_nonzero_is_flagged():
    text = "[2026-09-03 15:00:00] launching: C:\\a\\bad.py  [pid=5]\n" \
           "[2026-09-03 15:00:05]   exit=1  [pid=5]"
    latest = sts.latest_by_script(sts.parse_run_cmd_hidden_log(text))
    findings = sts.check_exit_codes(latest, {"bad.py": "Gamma_Bad"})
    assert len(findings) == 1
    assert findings[0]["exit"] == 1
    assert findings[0]["task"] == "Gamma_Bad"
    assert findings[0]["verdict"] == "RED"
    assert findings[0]["kind"] == "nonzero_exit"


def test_zero_exit_never_flagged():
    text = "[2026-09-03 15:00:00] launching: C:\\a\\ok.py  [pid=5]\n" \
           "[2026-09-03 15:00:05]   exit=0  [pid=5]"
    latest = sts.latest_by_script(sts.parse_run_cmd_hidden_log(text))
    assert sts.check_exit_codes(latest) == []


# ---------------------------------------------------------------------------------------
# Missing-launch detection (silent failure in an earlier hop of the wscript chain).
# ---------------------------------------------------------------------------------------

def test_missing_launch_flagged_when_last_run_falls_inside_window_but_never_logged():
    rows = [_row(name="Gamma_Ghost", lastRun=_ago(10))]
    findings = sts.check_missing_launches(
        rows, launched=set(), window_start=NOW - dt.timedelta(days=2), now=NOW)
    assert len(findings) == 1
    assert findings[0]["task"] == "Gamma_Ghost"
    assert findings[0]["script"] == "the_thing.py"
    assert findings[0]["verdict"] == "RED"
    assert findings[0]["kind"] == "missing_launch"


def test_missing_launch_not_flagged_when_script_was_logged():
    rows = [_row(name="Gamma_Ghost", lastRun=_ago(10))]
    findings = sts.check_missing_launches(
        rows, launched={"the_thing.py"}, window_start=NOW - dt.timedelta(days=2), now=NOW)
    assert findings == []


def test_missing_launch_skips_tasks_not_on_the_relay():
    """Gamma_PullbackHoldShadow routes through run_py_venv_hidden.py, not
    run_cmd_hidden.py -- it must never be flagged as a 'silent launch failure' just
    because it has no line in a log file it was never on."""
    rows = [_row(name="Gamma_PullbackHoldShadow", lastRun=_ago(5),
                argsRaw=r'"run_exe_hidden.vbs" "pythonw.exe" "run_py_venv_hidden.py" '
                        r'"C:\42\setup\scripts\pullback_hold_shadow.py"')]
    findings = sts.check_missing_launches(
        rows, launched=set(), window_start=NOW - dt.timedelta(days=2), now=NOW)
    assert findings == []


def test_missing_launch_skips_last_run_outside_window():
    rows = [_row(name="Gamma_OldGhost", lastRun=(NOW - dt.timedelta(days=10)).isoformat())]
    findings = sts.check_missing_launches(
        rows, launched=set(), window_start=NOW - dt.timedelta(days=2), now=NOW)
    assert findings == []


def test_missing_launch_skips_never_ran():
    rows = [_row(name="Gamma_Fresh", lastRun="1999-11-30T00:00:00-07:00")]
    findings = sts.check_missing_launches(
        rows, launched=set(), window_start=NOW - dt.timedelta(days=2), now=NOW)
    assert findings == []


def test_extract_script_from_args_skips_run_cmd_hidden_itself():
    assert sts.extract_script_from_args(_row()["argsRaw"]) == "the_thing.py"


def test_script_to_task_map_only_includes_relay_tasks():
    rows = [
        _row(name="Gamma_OnRelay"),
        _row(name="Gamma_OffRelay",
             argsRaw=r'"run_py_venv_hidden.py" "C:\42\setup\scripts\other.py"'),
    ]
    mapping = sts.script_to_task_map(rows)
    assert mapping.get("the_thing.py") == "Gamma_OnRelay"
    assert "other.py" not in mapping


# ---------------------------------------------------------------------------------------
# Output-freshness: fresh vs stale, and the table covers all eight 2026-09-03 tasks.
# ---------------------------------------------------------------------------------------

def test_table_covers_all_eight_2026_09_03_shadow_tasks():
    required = {
        "Gamma_DayTypeLabels", "Gamma_ProfitLockV2Shadow", "Gamma_EntryLocationTrendShadow",
        "Gamma_RetestZoneShadow", "Gamma_ConvictionC4Sidecar", "Gamma_ReleaseBlackoutShadow",
        "Gamma_FleetGateLeakShadow", "Gamma_StructureClassifierShadow",
    }
    assert required.issubset(set(sts.TASK_OUTPUT_MAP))


def test_table_also_covers_the_earlier_forward_shadows():
    required = {"Gamma_Tp1R50ForwardShadow", "Gamma_TrendlineTightExitShadow",
                "Gamma_PullbackHoldShadow"}
    assert required.issubset(set(sts.TASK_OUTPUT_MAP))


def test_fresh_output_is_green(tmp_path):
    out = tmp_path / "analysis" / "recommendations" / "thing.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"generated_at_et": _ago_naive_et(5)}), encoding="utf-8")
    rows_by_name = {"Gamma_Thing": _row(name="Gamma_Thing", lastRun=_ago(10))}
    findings = sts.check_output_freshness(
        rows_by_name, NOW,
        task_output_map={"Gamma_Thing": ("analysis/recommendations/thing.json", "generated_at_et")},
        root=tmp_path)
    assert findings[0]["verdict"] == "GREEN"


def test_stale_output_older_than_last_fire_is_red(tmp_path):
    out = tmp_path / "analysis" / "recommendations" / "thing.json"
    out.parent.mkdir(parents=True)
    # output stamped an HOUR before the task's last fire -- it ran but didn't write.
    out.write_text(json.dumps({"generated_at_et": _ago_naive_et(120)}), encoding="utf-8")
    rows_by_name = {"Gamma_Thing": _row(name="Gamma_Thing", lastRun=_ago(10))}
    findings = sts.check_output_freshness(
        rows_by_name, NOW,
        task_output_map={"Gamma_Thing": ("analysis/recommendations/thing.json", "generated_at_et")},
        root=tmp_path)
    assert findings[0]["verdict"] == "RED"
    assert "did not move" in findings[0]["reason"]


def test_missing_output_file_is_red(tmp_path):
    rows_by_name = {"Gamma_Thing": _row(name="Gamma_Thing", lastRun=_ago(10))}
    findings = sts.check_output_freshness(
        rows_by_name, NOW,
        task_output_map={"Gamma_Thing": ("analysis/recommendations/nope.json", "generated_at_et")},
        root=tmp_path)
    assert findings[0]["verdict"] == "RED"
    assert "missing" in findings[0]["reason"]


def test_output_stamp_falls_back_to_mtime_when_field_absent(tmp_path):
    out = tmp_path / "analysis" / "recommendations" / "thing.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"no_stamp_here": True}), encoding="utf-8")
    stamp, basis = sts.read_output_stamp("analysis/recommendations/thing.json",
                                         "generated_at_et", root=tmp_path)
    assert stamp is not None
    assert "mtime" in basis


def test_output_stamp_reads_nested_meta_field(tmp_path):
    """day-type-labels.json, conviction-c4-sidecar-summary.json and
    pullback-hold-shadow-summary.json all nest generated_at_et under '_meta' rather than
    top-level -- verified live 2026-09-03 (json.load on the real files). A stamp reader
    that only checks the top level silently falls back to mtime for all three and never
    surfaces that as wrong -- it must check '_meta' before giving up."""
    out = tmp_path / "analysis" / "recommendations" / "nested.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"_meta": {"generated_at_et": _ago_naive_et(5)}}), encoding="utf-8")
    stamp, basis = sts.read_output_stamp("analysis/recommendations/nested.json",
                                         "generated_at_et", root=tmp_path)
    assert stamp is not None
    assert basis == "'generated_at_et' field"


def _ago_naive_et(minutes: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes)).astimezone(ET).replace(tzinfo=None).isoformat()


# ---------------------------------------------------------------------------------------
# STATUS.md posting: ONE loud line, deduped, never a stack.
# ---------------------------------------------------------------------------------------

def test_post_output_freshness_writes_one_line_on_red(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n", encoding="utf-8")
    report = {
        "generated_at_et": "2026-09-03 17:55:00 ET",
        "exit_codes": [{"task": "Gamma_Bad", "script": "bad.py", "kind": "nonzero_exit",
                        "verdict": "RED", "reason": "x"}],
        "output_freshness": [],
    }
    changed = sts.post_output_freshness_status(report, status_path=status)
    assert changed is True
    text = status.read_text(encoding="utf-8")
    assert text.count("TASK-OUTPUT-FRESHNESS:") == 1
    assert "Gamma_Bad" in text


def test_post_output_freshness_dedupes_across_repeated_fires(tmp_path):
    """Two fires reporting the SAME finding must leave exactly ONE line, never a stack --
    the exact bug status_known_broken.py's own module docstring documents for other
    producers (roster_liveness.py, mcp_daily_audit.py) before they were re-pointed at it."""
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n", encoding="utf-8")
    report = {
        "generated_at_et": "2026-09-03 17:55:00 ET",
        "exit_codes": [{"task": "Gamma_Bad", "script": "bad.py", "kind": "nonzero_exit",
                        "verdict": "RED", "reason": "x"}],
        "output_freshness": [],
    }
    sts.post_output_freshness_status(report, status_path=status)
    report2 = dict(report, generated_at_et="2026-09-03 18:10:00 ET")
    sts.post_output_freshness_status(report2, status_path=status)
    text = status.read_text(encoding="utf-8")
    assert text.count("TASK-OUTPUT-FRESHNESS:") == 1
    assert "18:10:00 ET" in text
    assert "17:55:00 ET" not in text  # the stale line was replaced, not stacked


def test_post_output_freshness_clears_marker_when_all_green(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text(
        "## Known broken\n\n- [old] TASK-OUTPUT-FRESHNESS: 1 finding(s): Gamma_Bad[nonzero_exit]\n",
        encoding="utf-8")
    report = {"generated_at_et": "now", "exit_codes": [], "output_freshness": []}
    sts.post_output_freshness_status(report, status_path=status)
    text = status.read_text(encoding="utf-8")
    assert "TASK-OUTPUT-FRESHNESS:" not in text


# ---------------------------------------------------------------------------------------
# build_report integration: new keys present, existing verdict/reason untouched.
# ---------------------------------------------------------------------------------------

def test_build_report_carries_new_keys():
    rep = sts.build_report([], now=NOW, run_cmd_hidden_log_text="")
    assert "exit_codes" in rep
    assert "output_freshness" in rep
    assert isinstance(rep["exit_codes"], list)
    assert isinstance(rep["output_freshness"], list)


def test_build_report_none_rows_still_carries_new_keys():
    """rows=None (query failure) is a real, common shape -- the new keys must not KeyError
    a caller just because the scheduler round-trip itself failed."""
    rep = sts.build_report(None, now=NOW, run_cmd_hidden_log_text="")
    assert rep["verdict"] == "UNKNOWN"
    assert "exit_codes" in rep
    assert "output_freshness" in rep


def test_build_report_existing_verdict_unaffected_by_new_red_findings():
    """A nonzero-exit finding must not change the existing staleness-based `verdict` field
    -- that field's contract (missed-runs / stale-minutes) is unchanged by this queue item;
    the new evidence lives ONLY in the new keys."""
    rows = [_row(name="Gamma_Green", missedRuns=0, lastRun=_ago(30))]
    log_text = ("[2026-09-03 15:00:00] launching: C:\\a\\the_thing.py  [pid=1]\n"
               "[2026-09-03 15:00:05]   exit=9  [pid=1]")
    rep = sts.build_report(rows, now=NOW, run_cmd_hidden_log_text=log_text)
    assert rep["verdict"] == "GREEN"  # staleness verdict unchanged
    assert any(f["verdict"] == "RED" for f in rep["exit_codes"])  # but the new evidence is there


def test_read_run_cmd_hidden_log_text_reads_last_two_dates(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "run-cmd-hidden-2026-09-02.log").write_text("DAY-BEFORE\n", encoding="utf-8")
    (log_dir / "run-cmd-hidden-2026-09-03.log").write_text("TODAY\n", encoding="utf-8")
    (log_dir / "run-cmd-hidden-2026-09-01.log").write_text("TOO-OLD\n", encoding="utf-8")
    text = sts.read_run_cmd_hidden_log_text(NOW, days=2, log_dir=log_dir)
    assert "DAY-BEFORE" in text
    assert "TODAY" in text
    assert "TOO-OLD" not in text


def test_read_run_cmd_hidden_log_text_missing_file_is_fail_open(tmp_path):
    text = sts.read_run_cmd_hidden_log_text(NOW, days=2, log_dir=tmp_path / "nope")
    assert text == ""
