"""Guard for GOAL-SILENT-RIG-2026-09-05 S2: neither the LIVE Task Scheduler registry nor
any install-*.ps1 / task-registration script may reference the venv pythonw/python STUB
(backtest\\.venv\\Scripts\\pythonw.exe) as a launch target.

Root cause this guard locks in (S1, same date): that stub's basename looks GUI-subsystem
(same name as the compliant system pythonw) but its base executable is the CONSOLE
python.exe -- GetConsoleWindow() != 0 under the stub, proven live 2026-09-05. 23-24 Gamma_*
tasks and ~19 install-*.ps1 registration scripts carried this for weeks before today; this
guard turns "stayed fixed" into a build-time assertion instead of tribal memory.

Style follows backtest/tests/test_window_leak_compliance.py: import the audit module by
path, RED-proof each detector against a fixture (bad + good), then assert the real live/
repo scan is clean. The live-registry test SKIPS (not errors, not silently passes) if Task
Scheduler is unreachable from this process -- distinguishing "clean" from "couldn't look"
per C7 (silent success is failure).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "setup" / "scripts" / "audit_window_leak_compliance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_window_leak_compliance_s2", AUDIT)
    assert spec and spec.loader, f"cannot load audit at {AUDIT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = _load_module()


def _fake_ast_module(tasks):
    """Build a stand-in for audit_scheduled_tasks with a canned _registered_tasks()."""
    fake = types.ModuleType("audit_scheduled_tasks")
    fake._registered_tasks = lambda: tasks
    fake._is_hidden = lambda execute, arguments: True
    fake._is_bare_console_launcher = lambda execute: False
    return fake


# --- 7a: live task-registry stub detector ------------------------------------------------

def test_bite_task_venv_interpreter_flags_stub_task(monkeypatch):
    """NON-VACUOUS BITE: a fixture task whose action still names the venv stub must be
    flagged, whether it is Enabled OR Disabled -- GOAL-SILENT-RIG's whole point is these
    tasks stay Disabled while their actions get fixed, so a Disabled-skipping scan would
    report false-GREEN on exactly what this guard exists to catch."""
    bad_disabled = {
        "name": "Gamma_FakeStubDisabled",
        "state": "Disabled",
        "execute": "wscript.exe",
        "arguments": (
            '//nologo "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_exe_hidden.vbs" '
            '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
            '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_cmd_hidden.py" --cwd '
            '"C:\\Users\\jackw\\Desktop\\42" -- '
            '"C:\\Users\\jackw\\Desktop\\42\\backtest\\.venv\\Scripts\\pythonw.exe" '
            '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\some_script.py"'
        ),
    }
    bad_enabled_outer = {
        "name": "Gamma_FakeStubOuter",
        "state": "Ready",
        "execute": "wscript.exe",
        "arguments": (
            '//nologo "C:\\...\\run_exe_hidden.vbs" '
            '"C:\\Users\\jackw\\Desktop\\42\\backtest\\.venv\\Scripts\\pythonw.exe" '
            '"C:\\...\\run_cmd_hidden.py" --cwd "C:\\Users\\jackw\\Desktop\\42" -- '
            '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
            '"C:\\...\\some_script.py"'
        ),
    }
    good = {
        "name": "Gamma_FakeClean",
        "state": "Disabled",
        "execute": "wscript.exe",
        "arguments": (
            '//nologo "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_exe_hidden.vbs" '
            '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
            '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_cmd_hidden.py" --env '
            '"PYTHONPATH=C:\\Users\\jackw\\Desktop\\42\\backtest\\.venv\\Lib\\site-packages" '
            '--cwd "C:\\Users\\jackw\\Desktop\\42" -- '
            '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
            '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\some_script.py"'
        ),
    }
    fake_mod = _fake_ast_module([bad_disabled, bad_enabled_outer, good])
    monkeypatch.setitem(sys.modules, "audit_scheduled_tasks", fake_mod)

    flags = AUD._audit_task_venv_interpreter()
    flagged_names = {f["detail"] for f in flags}
    names = {f["file"] for f in flags}
    assert "scheduled-task:Gamma_FakeStubDisabled" in names, (
        "guard failed to flag a DISABLED task whose action still names the venv stub -- "
        "this is the exact false-GREEN this guard exists to prevent"
    )
    assert "scheduled-task:Gamma_FakeStubOuter" in names, (
        "guard failed to flag a task using the stub as the OUTER wscript hop"
    )
    assert "scheduled-task:Gamma_FakeClean" not in names, (
        "guard wrongly flagged a fully-compliant system-pythonw + PYTHONPATH action"
    )
    assert len(flags) == 2


def test_task_venv_interpreter_scan_empty_is_a_failure(monkeypatch):
    """A 0-task result must be reported as a FAILED scan, never as '0 violations found' --
    same C7 structural guard as _audit_live_task_registry's own EMPTY check."""
    fake_mod = _fake_ast_module([])
    monkeypatch.setitem(sys.modules, "audit_scheduled_tasks", fake_mod)
    flags = AUD._audit_task_venv_interpreter()
    assert len(flags) == 1
    assert flags[0]["flag"] == "TASK_VENV_INTERPRETER_SCAN_EMPTY"


def test_live_task_venv_interpreter_registry_is_clean():
    """The win state on THIS box, right now: live Task Scheduler has 0 tasks whose action
    names the venv stub (S1 fixed all 24; installers fixed so a re-install can't bring it
    back). SKIPS -- does not silently pass -- if Task Scheduler is unreachable from this
    test process, so a broken scan can never be mistaken for a clean box."""
    flags = AUD._audit_task_venv_interpreter()
    scan_failed_flags = {
        "TASK_VENV_INTERPRETER_SCAN_IMPORT_FAILED",
        "TASK_VENV_INTERPRETER_SCAN_FAILED",
        "TASK_VENV_INTERPRETER_SCAN_EMPTY",
    }
    if any(f["flag"] in scan_failed_flags for f in flags):
        pytest.skip(
            f"live Task Scheduler registry unreachable from this test process: {flags}"
        )
    detail = "\n".join(f"  {f['file']}  {f['detail']}" for f in flags)
    assert flags == [], (
        f"{len(flags)} LIVE scheduled task(s) still reference the venv pythonw/python "
        f"stub as a launch target:\n{detail}\n"
        "Fix: Set-ScheduledTask -Action <system pythonw + --env PYTHONPATH, both hops> "
        "per GOAL-SILENT-RIG-2026-09-05.md S1."
    )


# --- 7b: installer/registration-script stub detector --------------------------------------

def test_bite_installer_venv_interpreter_flags_stub_action_line(tmp_path, monkeypatch):
    """NON-VACUOUS BITE: an install-*.ps1 whose New-ScheduledTaskAction/-Argument line still
    builds the venv stub into the action must be flagged; a Test-Path guard mentioning the
    same path (not an action-building line) must NOT be flagged; a comment must NOT be
    flagged; a fully system-pythonw + PYTHONPATH installer must NOT be flagged."""
    bad = tmp_path / "install-fake-leaker.ps1"
    bad.write_text(
        '$root = "C:\\Users\\jackw\\Desktop\\42"\n'
        '$pythonwVenv = Join-Path $root "backtest\\.venv\\Scripts\\pythonw.exe"\n'
        'if (-not (Test-Path $pythonwVenv)) { throw "missing" }\n'
        '$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd '
        '`"$root`" -- `"$pythonwVenv`" `"$script`""\n'
        '$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs\n',
        encoding="utf-8",
    )
    good = tmp_path / "install-fake-clean.ps1"
    good.write_text(
        '$root = "C:\\Users\\jackw\\Desktop\\42"\n'
        '$sysPythonw = "C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe"\n'
        '$pythonPath = Join-Path $root "backtest\\.venv\\Lib\\site-packages"\n'
        '# old shape used to run backtest\\.venv\\Scripts\\pythonw.exe here (comment only)\n'
        '$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env '
        '`"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""\n'
        '$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(AUD, "SCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(AUD, "REPO", tmp_path)

    flags = AUD._audit_installer_venv_interpreter()
    flagged_files = {Path(f["file"]).name for f in flags}
    assert "install-fake-leaker.ps1" in flagged_files, (
        "guard failed to flag an installer whose action-building line still names the venv stub"
    )
    assert "install-fake-clean.ps1" not in flagged_files, (
        "guard wrongly flagged a compliant installer (false positive on its Test-Path-free, "
        "system-pythonw + PYTHONPATH action line, or on its own explanatory comment)"
    )
    # Exactly the one action-building line in the leaker should be flagged, not its
    # Test-Path guard line (line 3) which merely references the stub path, not a launch.
    leaker_flags = [f for f in flags if Path(f["file"]).name == "install-fake-leaker.ps1"]
    assert len(leaker_flags) == 1
    assert leaker_flags[0]["line"] == 4


def test_installer_venv_interpreter_scan_is_clean_over_the_real_repo():
    """The win state on THIS repo, right now: every install-*.ps1 and
    fix-venv-pythonw-console-leak.ps1 builds its action from the system pythonw, never the
    venv stub (S1 fixed 20 registration scripts on 2026-09-05)."""
    flags = AUD._audit_installer_venv_interpreter()
    detail = "\n".join(f"  {f['file']}:{f['line']}  {f['detail']}" for f in flags)
    assert flags == [], (
        f"{len(flags)} installer/registration script line(s) still build the venv "
        f"pythonw/python stub into a scheduled-task action:\n{detail}\n"
        "Fix per GOAL-SILENT-RIG-2026-09-05.md S1: swap to system pythonw + "
        "--env PYTHONPATH=<repo>\\backtest\\.venv\\Lib\\site-packages."
    )
