"""Guard for self_check.check_run_ps1_hidden_masked_exit -- the SECOND half of the
2026-08-04 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT self-audit gap (check_run_cmd_hidden_masked_exit
was the first half, shipped 2026-08-05, and only covers ~24 of the 108 Gamma_* tasks that
route through run_exe_hidden.vbs).

Motivation: the MAJORITY of Gamma_* scheduled tasks (including safety-relevant ones like
Gamma_EodFlatten / Gamma_EodFlatten_Aggressive / Gamma_SightBeacon) route through
wscript -> run_exe_hidden.vbs -> system-pythonw -> run_ps1_hidden.py -> powershell.exe -File
<task>.ps1. The outer wscript hop is fire-and-forget (shell.Run cmd, 0, False), so Task
Scheduler's LastTaskResult can never see these tasks' real outcome -- but run_ps1_hidden.py's
own process runs the child .ps1 SYNCHRONOUSLY and has already been writing the true exit
code to automation/state/logs/run-ps1-hidden-<date>.log on every fire since its own '5/17
evening foot-gun fix'. Nothing consumed that file before this guard (verified live via grep,
zero hits). This closes the gap using evidence that already exists on disk -- no vbs edits,
no scheduled-task edits, no live-trading-path touch at all (purely additive read of an
existing log; the vbs synchronous-exit-code fix itself stays deliberately deferred behind
its own /fable-blast-radius pass, unchanged by this fire).

Live-verified this fire (2026-08-06): the real run-ps1-hidden-2026-08-0{3,4,5}.log files
show run-eod-flatten-aggressive.ps1 exit=1 on all 3 days, run-eod-flatten.ps1 and
run-sight-beacon.ps1 exit=1 once each on 08-05 -- a genuine, previously-invisible finding
this check now surfaces (backstopped by the deterministic Gamma_EodFlattenCore, confirmed
no position was left open on any of those dates via engine-health.json).

Mirrors test_self_check_run_cmd_hidden_masked_exit.py's import + structure convention, with
one deliberate difference: _parse_run_ps1_hidden_log does NOT need launching/exit line-order
pairing (unlike its run_cmd_hidden sibling) because run_ps1_hidden.py's own exit line embeds
the script name directly. This guard specifically proves that a concurrent-launch
interleaving (which the real log routinely exhibits) does not confuse the parser -- the
exact class of bug a naive line-order-pairing copy-paste would have introduced.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


# ---- _parse_run_ps1_hidden_log (pure parser) ----

def test_parse_extracts_name_and_exit_from_single_line():
    text = "[2026-08-05 13:55:42]   run-eod-flatten.ps1 exit=1\n"
    assert sc._parse_run_ps1_hidden_log(text) == [{"name": "run-eod-flatten.ps1", "exit": 1}]


def test_parse_ignores_launching_lines():
    text = (
        "[2026-08-05 13:55:01] launching: run-eod-flatten.ps1 args=[]\n"
        "[2026-08-05 13:55:42]   run-eod-flatten.ps1 exit=0\n"
    )
    assert sc._parse_run_ps1_hidden_log(text) == [{"name": "run-eod-flatten.ps1", "exit": 0}]


def test_parse_handles_concurrent_interleaved_launches_without_misattribution():
    """The real log routinely shows N 'launching:' lines queued before their exits land --
    a sequential launching/exit PAIRING parser (like run_cmd_hidden's) would misattribute
    these. This parser must read exit lines standalone and get every name right regardless
    of interleaving order."""
    text = (
        "[t] launching: run-a.ps1 args=[]\n"
        "[t] launching: run-b.ps1 args=[]\n"
        "[t] launching: run-c.ps1 args=[]\n"
        "[t]   run-b.ps1 exit=1\n"
        "[t]   run-a.ps1 exit=0\n"
        "[t]   run-c.ps1 exit=2\n"
    )
    records = sc._parse_run_ps1_hidden_log(text)
    by_name = {r["name"]: r["exit"] for r in records}
    assert by_name == {"run-a.ps1": 0, "run-b.ps1": 1, "run-c.ps1": 2}


def test_parse_drops_unpaired_trailing_launching_line():
    text = "[t] launching: run-still-running.ps1 args=[]\n"
    assert sc._parse_run_ps1_hidden_log(text) == []


def test_parse_ignores_non_exit_lines():
    text = "[t]   STDOUT[:500]: some noise exit=NOTREAL without a .ps1 name\n"
    assert sc._parse_run_ps1_hidden_log(text) == []


# ---- check_run_ps1_hidden_masked_exit (the wired check) ----

def test_missing_log_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 5, 12, 0)
    missing = tmp_path / "run-ps1-hidden-2026-08-05.log"
    assert sc.check_run_ps1_hidden_masked_exit(now, log_path=missing) == []


def test_all_clean_exits_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 5, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] launching: run-a.ps1 args=[]\n[t]   run-a.ps1 exit=0\n"
        "[t] launching: run-b.ps1 args=[]\n[t]   run-b.ps1 exit=0\n",
        encoding="utf-8",
    )
    assert sc.check_run_ps1_hidden_masked_exit(now, log_path=p) == []


def test_single_nonzero_exit_flags_degraded_with_script_name(tmp_path):
    now = dt.datetime(2026, 8, 5, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] launching: run-eod-flatten-aggressive.ps1 args=[]\n"
        "[t]   run-eod-flatten-aggressive.ps1 exit=1\n",
        encoding="utf-8",
    )
    problems = sc.check_run_ps1_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1
    assert "RUN-PS1-HIDDEN MASKED EXIT" in problems[0]
    assert "run-eod-flatten-aggressive.ps1" in problems[0]
    assert "exit=[1]" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "backstopped R&D/telemetry relay -- must be DEGRADED, never BROKEN"


def test_repeated_failures_of_same_script_collapse_to_one_line(tmp_path):
    now = dt.datetime(2026, 8, 5, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        ("[t]   run-kitchen-seeder.ps1 exit=1\n" * 5),
        encoding="utf-8",
    )
    problems = sc.check_run_ps1_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1, "5 fires of the SAME failing script must collapse to ONE finding, not spam"
    assert "5x" in problems[0]


def test_two_distinct_failing_scripts_named_separately(tmp_path):
    now = dt.datetime(2026, 8, 5, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t]   run-a.ps1 exit=1\n"
        "[t]   run-b.ps1 exit=2\n",
        encoding="utf-8",
    )
    problems = sc.check_run_ps1_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1
    assert "run-a.ps1" in problems[0] and "run-b.ps1" in problems[0]


def test_wired_into_run_verdict():
    """The check must actually be reachable from run()'s aggregate problems list -- not
    just defined and orphaned (C7: being-defined != being-run)."""
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_run_ps1_hidden_masked_exit" in src


def test_live_log_2026_08_05_surfaces_the_real_eod_flatten_finding():
    """OP-33 verify-not-claim: run the check against the ACTUAL on-disk log from today's
    (2026-08-05) session, not just a synthetic fixture. Proves the fix does what the
    STATUS/queue writeup claims against cold reality."""
    real_log = REPO / "automation" / "state" / "logs" / "run-ps1-hidden-2026-08-05.log"
    if not real_log.exists():
        import pytest
        pytest.skip("real 2026-08-05 log not present on this machine")
    now = dt.datetime(2026, 8, 5, 23, 59)
    problems = sc.check_run_ps1_hidden_masked_exit(now, log_path=real_log)
    assert len(problems) == 1
    assert "run-eod-flatten.ps1" in problems[0]
    assert "run-eod-flatten-aggressive.ps1" in problems[0]
    assert "run-sight-beacon.ps1" in problems[0]
