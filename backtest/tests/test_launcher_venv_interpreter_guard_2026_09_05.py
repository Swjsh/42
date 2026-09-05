"""Guard for GOAL-SILENT-RIG-2026-09-05 R6b: no *.ps1 / *.cmd / *.vbs anywhere under
setup/ (not just install-*.ps1, not just the live Task Scheduler registry) may
reference the venv pythonw.exe STUB (backtest\\.venv\\Scripts\\pythonw.exe) as a live
launch target.

Root cause this guard closes (R6a, same date): (7a) test_task_venv_interpreter_guard
only checks the LIVE task registry; (7b) only checks setup/scripts/install-*.ps1. Neither
would have caught the actual 2026-09-05 incident -- 12 non-install LAUNCHER scripts
(setup/scripts/run-*.ps1, launch-*.ps1, setup/run-j-strategy.cmd) that build their OWN
interpreter path at runtime (`$exe = if (Test-Path $venvPythonW) { $venvPythonW } else
{ $venvPython }`) rather than going through a task-registration script at all. A task's
registered action can point at a perfectly clean wrapper while the wrapper's own body
still picks the broken stub -- that stub's basename looks GUI-subsystem (same name as the
compliant system pythonw) but its base executable is the CONSOLE python.exe, so it opens a
terminal window per fire from a windowless parent.

Style follows test_task_venv_interpreter_guard_2026_09_05.py: import the audit module by
path, RED-proof the new detector against a fixture (bad launcher + good launcher +
comment-only + allowlisted file), then assert the real repo scan is clean.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "setup" / "scripts" / "audit_window_leak_compliance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_window_leak_compliance_r6b", AUDIT)
    assert spec and spec.loader, f"cannot load audit at {AUDIT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = _load_module()


def _write_fixture_tree(tmp_path: Path) -> Path:
    """Builds a fake repo root with a setup/ tree exercising every shape the new check
    must tell apart: a live-offending launcher, a fixed one, a comment-only mention, and
    a file the allowlist names explicitly."""
    setup_dir = tmp_path / "setup"
    scripts_dir = setup_dir / "scripts"
    scripts_dir.mkdir(parents=True)

    # 1. BAD: a non-install launcher script building the venv stub at runtime (the exact
    #    2026-09-05 incident shape -- ternary picking $venvPythonW).
    (scripts_dir / "run-fake-bad-launcher.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\n"
        "$venvPython = Join-Path $repoRoot 'backtest\\.venv\\Scripts\\python.exe'\n"
        "$venvPythonW = Join-Path $repoRoot 'backtest\\.venv\\Scripts\\pythonw.exe'\n"
        "$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }\n"
        "$startInfo = New-Object System.Diagnostics.ProcessStartInfo\n"
        "$startInfo.FileName = $exe\n",
        encoding="utf-8",
    )

    # 2. GOOD: the fixed shape (system pythonw + PYTHONPATH env).
    (scripts_dir / "run-fake-good-launcher.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\n"
        "$sysPythonW = 'C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe'\n"
        "if (-not (Test-Path $sysPythonW)) { throw 'system pythonw.exe not found' }\n"
        "$exe = $sysPythonW\n"
        "$env:PYTHONPATH = Join-Path $repoRoot 'backtest\\.venv\\Lib\\site-packages'\n",
        encoding="utf-8",
    )

    # 3. Comment-only mention, NOT allowlisted by name -- must still be flagged (an
    #    unrecognized comment-only file is not proof of safety; only the maintained
    #    allowlist is).
    (setup_dir / "install-fake-unlisted-comment.ps1").write_text(
        "# 2026-09-05 fix note: was backtest\\.venv\\Scripts\\pythonw.exe, now $sysPythonw\n"
        "$sysPythonw = 'C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe'\n",
        encoding="utf-8",
    )

    # 4. Explicitly allowlisted file -- must NOT be flagged even though it contains the
    #    literal stub string (mirrors run_exe_hidden_exec.vbs's docstring-only mention).
    (scripts_dir / "run_exe_hidden_exec.vbs").write_text(
        "' docstring: backtest\\.venv\\Scripts\\pythonw.exe is a stub that re-execs CONSOLE python.exe\n"
        "Set args = WScript.Arguments\n",
        encoding="utf-8",
    )

    # 5. A .cmd launcher with the live stub -- confirms the sweep covers .cmd, not just .ps1.
    (setup_dir / "run-fake-bad.cmd").write_text(
        "@echo off\r\n"
        "set REPO=C:\\Users\\jackw\\Desktop\\42\r\n"
        "set PYTHONW=%REPO%\\backtest\\.venv\\Scripts\\pythonw.exe\r\n"
        "start \"\" /B \"%PYTHONW%\" -m some.module\r\n",
        encoding="utf-8",
    )

    return tmp_path


def test_bite_launcher_venv_interpreter_flags_non_install_launcher(tmp_path, monkeypatch):
    """NON-VACUOUS BITE: the new (7c) check must catch a non-install launcher script
    building the venv stub at runtime -- the exact shape (7a)/(7b) cannot see, since it is
    neither a live scheduled-task action nor an install-*.ps1 registration script."""
    fake_repo = _write_fixture_tree(tmp_path)
    # LAUNCHER_VENV_INTERPRETER_ALLOWLIST is keyed by paths relative to the real REPO;
    # temporarily swap in one keyed to this fixture's own allowlisted file so allowlist
    # behavior is exercised too.
    fake_allowlist = {"setup/scripts/run_exe_hidden_exec.vbs": "fixture: docstring-only mention"}
    monkeypatch.setattr(AUD, "REPO", fake_repo)
    monkeypatch.setattr(AUD, "LAUNCHER_VENV_INTERPRETER_ALLOWLIST", fake_allowlist)

    flags = AUD._audit_launcher_venv_interpreter()
    flagged_files = {f["file"] for f in flags}

    assert "setup/scripts/run-fake-bad-launcher.ps1" in flagged_files, (
        "guard failed to flag a non-install launcher script that builds the venv pythonw "
        "stub into $exe at runtime -- this is the exact 2026-09-05 incident shape"
    )
    assert "setup/run-fake-bad.cmd" in flagged_files, (
        "guard failed to flag a .cmd launcher referencing the venv stub -- sweep must "
        "cover .cmd files, not just .ps1"
    )
    assert "setup/install-fake-unlisted-comment.ps1" in flagged_files, (
        "guard wrongly cleared a comment-only mention that is NOT in the allowlist -- "
        "only an explicit, maintained allowlist entry may suppress a match"
    )
    assert "setup/scripts/run-fake-good-launcher.ps1" not in flagged_files, (
        "guard wrongly flagged the fixed system-pythonw + PYTHONPATH shape"
    )
    assert "setup/scripts/run_exe_hidden_exec.vbs" not in flagged_files, (
        "guard wrongly flagged a file explicitly named in the allowlist"
    )


def test_launcher_venv_interpreter_scan_is_clean_over_the_real_repo():
    """The win state on THIS repo, right now: every *.ps1/*.cmd/*.vbs under setup/ either
    has no venv-pythonw-stub reference at all, or is a maintained allowlist entry whose
    reason is stated in LAUNCHER_VENV_INTERPRETER_ALLOWLIST (R6a fixed all live offenders
    2026-09-05: 22 direct launcher scripts + ~40 installer dead-variable/inner-hop cases)."""
    flags = AUD._audit_launcher_venv_interpreter()
    detail = "\n".join(f"  {f['file']}:{f['line']}  {f['detail']}" for f in flags)
    assert flags == [], (
        f"{len(flags)} launcher/registration script(s) under setup/ still reference the "
        f"venv pythonw.exe stub as a live target:\n{detail}\n"
        "Fix per GOAL-SILENT-RIG-2026-09-05.md R6a: repoint to the system pythonw "
        "(C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe) with "
        "PYTHONPATH=<repo>\\backtest\\.venv\\Lib\\site-packages, or add a named allowlist "
        "entry with a stated reason if the remaining match is genuinely comment-only."
    )


def test_run_ps1_hidden_and_run_cmd_hidden_never_hardcode_the_stub():
    """run_ps1_hidden.py and run_cmd_hidden.py are the two relay hops nearly every fixed
    launcher/installer in this repo routes through -- if either ever grew a fallback to
    the venv pythonw stub, it would silently reintroduce the leak into every caller at
    once. Both currently take the interpreter path as a CLI argument and never hardcode
    one; this guard keeps that true."""
    for name in ("run_ps1_hidden.py", "run_cmd_hidden.py"):
        path = REPO / "setup" / "scripts" / name
        assert path.exists(), f"{name} not found at {path}"
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "backtest" not in line or "pythonw.exe" not in line or ".venv" not in line, (
                f"{name}:{lineno} appears to hardcode the venv pythonw stub as a fallback "
                f"interpreter -- both relay scripts must only ever launch whatever "
                f"interpreter path is passed to them as an argument: {stripped[:160]!r}"
            )
