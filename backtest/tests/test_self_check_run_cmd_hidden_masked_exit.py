"""Guard for self_check.check_run_cmd_hidden_masked_exit -- the fleet-wide generalization
of the 2026-08-04 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT self-audit gap (self-flagged 2026-08-02
AND 2026-08-04 -- an OP-25/C7 two-batch recurrence, the graduation signal).

Motivation: ~18 Gamma_* tasks already route through wscript -> run_exe_hidden.vbs ->
system-pythonw -> run_cmd_hidden.py (see fix-venv-pythonw-console-leak.ps1). The outer
wscript hop is fire-and-forget (shell.Run cmd, 0, False), so Task Scheduler's
LastTaskResult can never see these tasks' real outcome -- but run_cmd_hidden.py's own
process runs the child SYNCHRONOUSLY and already writes the true exit code to
automation/state/logs/run-cmd-hidden-<date>.log on every fire. Nothing consumed that file
before this guard (verified live via grep, zero hits). This closes the gap using evidence
that already exists on disk -- no vbs edits, no live-trading-path blast radius (that
change stays deliberately deferred behind its own /fable-blast-radius pass).

Mirrors test_self_check_regime_stamp_drift.py's import + structure convention.
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


# ---- _parse_run_cmd_hidden_log (pure parser) ----

def test_parse_pairs_launching_with_next_exit_line():
    text = (
        "[2026-08-04 15:44:59] launching: C:\\v\\pythonw.exe C:\\s\\twin_sentinel.py\n"
        "[2026-08-04 15:44:59]   cwd=C:\\42  env_overrides=[]  log=None\n"
        "[2026-08-04 15:45:00]   exit=0 (off-desktop)\n"
    )
    records = sc._parse_run_cmd_hidden_log(text)
    assert records == [{"cmd": "C:\\v\\pythonw.exe C:\\s\\twin_sentinel.py", "exit": 0}]


def test_parse_captures_nonzero_exit():
    text = (
        "[2026-08-04 08:22:00] launching: C:\\v\\pythonw.exe C:\\s\\regime_stamp.py\n"
        "[2026-08-04 08:22:03]   exit=1\n"
    )
    records = sc._parse_run_cmd_hidden_log(text)
    assert records == [{"cmd": "C:\\v\\pythonw.exe C:\\s\\regime_stamp.py", "exit": 1}]


def test_parse_drops_unpaired_trailing_launching_line():
    text = "[2026-08-04 15:44:59] launching: C:\\v\\pythonw.exe C:\\s\\still_running.py\n"
    assert sc._parse_run_cmd_hidden_log(text) == []


def test_parse_handles_multiple_fires_in_one_file():
    text = (
        "[2026-08-04 08:22:00] launching: a.py\n"
        "[2026-08-04 08:22:03]   exit=0\n"
        "[2026-08-04 08:37:00] launching: b.py\n"
        "[2026-08-04 08:37:03]   exit=2\n"
    )
    records = sc._parse_run_cmd_hidden_log(text)
    assert records == [{"cmd": "a.py", "exit": 0}, {"cmd": "b.py", "exit": 2}]


def test_parse_ignores_malformed_exit_token():
    text = "[t] launching: a.py\n[t]   exit=notanumber\n"
    assert sc._parse_run_cmd_hidden_log(text) == []


# ---- _run_cmd_hidden_script_label ----

def test_label_picks_py_token_not_trailing_args():
    cmd = "C:\\v\\pythonw.exe C:\\s\\free_model_audit.py --subject all"
    assert sc._run_cmd_hidden_script_label(cmd) == "free_model_audit.py"


def test_label_handles_flag_style_trailing_arg():
    cmd = "C:\\v\\pythonw.exe C:\\s\\crypto_twin_health.py --live"
    assert sc._run_cmd_hidden_script_label(cmd) == "crypto_twin_health.py"


def test_label_falls_back_to_last_token_when_no_py():
    assert sc._run_cmd_hidden_script_label("C:\\v\\pythonw.exe") == "pythonw.exe"


# ---- check_run_cmd_hidden_masked_exit (the wired check) ----

def test_missing_log_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 4, 12, 0)
    missing = tmp_path / "run-cmd-hidden-2026-08-04.log"
    assert sc.check_run_cmd_hidden_masked_exit(now, log_path=missing) == []


def test_all_clean_exits_never_flags(tmp_path):
    now = dt.datetime(2026, 8, 4, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] launching: a.py\n[t]   exit=0\n"
        "[t] launching: b.py\n[t]   exit=0 (off-desktop)\n",
        encoding="utf-8",
    )
    assert sc.check_run_cmd_hidden_masked_exit(now, log_path=p) == []


def test_single_nonzero_exit_flags_degraded_with_script_name(tmp_path):
    now = dt.datetime(2026, 8, 4, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] launching: C:\\v\\pythonw.exe C:\\s\\broker_fills.py\n[t]   exit=1\n",
        encoding="utf-8",
    )
    problems = sc.check_run_cmd_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1
    assert "RUN-CMD-HIDDEN MASKED EXIT" in problems[0]
    assert "broker_fills.py" in problems[0]
    assert "exit=[1]" in problems[0]
    assert not sc._problem_is_broken(problems[0]), "R&D-only relay tasks -- must be DEGRADED, never BROKEN"


def test_repeated_failures_of_same_script_collapse_to_one_line(tmp_path):
    now = dt.datetime(2026, 8, 4, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        ("[t] launching: C:\\v\\pythonw.exe C:\\s\\twin_sentinel.py\n[t]   exit=1\n" * 5),
        encoding="utf-8",
    )
    problems = sc.check_run_cmd_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1, "5 fires of the SAME failing script must collapse to ONE finding, not spam"
    assert "5x" in problems[0]


def test_two_distinct_failing_scripts_named_separately(tmp_path):
    now = dt.datetime(2026, 8, 4, 12, 0)
    p = tmp_path / "log.log"
    p.write_text(
        "[t] launching: C:\\v\\pythonw.exe C:\\s\\a.py\n[t]   exit=1\n"
        "[t] launching: C:\\v\\pythonw.exe C:\\s\\b.py\n[t]   exit=2\n",
        encoding="utf-8",
    )
    problems = sc.check_run_cmd_hidden_masked_exit(now, log_path=p)
    assert len(problems) == 1
    assert "a.py" in problems[0] and "b.py" in problems[0]


def test_wired_into_run_verdict(tmp_path, monkeypatch):
    """The check must actually be reachable from run()'s aggregate problems list --
    not just defined and orphaned (the exact registry/wiring class this codebase
    graduated a guard for elsewhere, C7: being-defined != being-run)."""
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_run_cmd_hidden_masked_exit" in src
