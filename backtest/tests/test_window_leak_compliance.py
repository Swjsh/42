"""Ratchet guard for the window-leak compliance audit (OP-27 L41, C8).

The audit `setup/scripts/audit_window_leak_compliance.py` runs daily and writes a
RED/GREEN verdict to `automation/state/window-leak-compliance-audit.json`, but
NOTHING made the build fail on a regression — so 13 `subprocess.run` calls without
`creationflags=CREATE_NO_WINDOW` accumulated undetected (drained to 0 on 2026-06-30).
A bare subprocess spawn from a headless (pythonw) scheduled task allocates a fresh
conhost window on Win11 — the documented window-flash foot-gun, and one of these
(heartbeat_core engine_cli) fires EVERY RTH tick while J is at his machine.

This guard graduates the daily audit into a hard, build-time ratchet:
  - the py-subprocess-missing-creationflags scan must stay EMPTY (the win state)
  - the ps1-bare-python scan must stay EMPTY
  - a non-vacuous BITE proves the detector actually fires on a fresh offender
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "setup" / "scripts" / "audit_window_leak_compliance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_window_leak_compliance", AUDIT)
    assert spec and spec.loader, f"cannot load audit at {AUDIT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = _load_module()


def test_no_py_subprocess_missing_creationflags():
    """The win state: every audited subprocess.run carries creationflags. A new
    bare call (e.g. a future script forgetting the flag) re-REDs this immediately."""
    flags = AUD._audit_py_missing_creationflags()
    detail = "\n".join(f"  {f['file']}:{f['line']}  {f['detail']}" for f in flags)
    assert flags == [], (
        f"{len(flags)} subprocess.run call(s) missing creationflags=CREATE_NO_WINDOW "
        f"(OP-27 L41 — would flash a conhost window on win32):\n{detail}\n"
        "Fix: add `creationflags=_CREATE_NO_WINDOW` (define "
        "`_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0` at module top)."
    )


def test_no_ps1_bare_python():
    """No scheduled-task .ps1 invokes a bare `python` (must use Invoke-PythonHidden)."""
    flags = AUD._audit_ps1_bare_python()
    detail = "\n".join(f"  {f['file']}:{f['line']}  {f['detail']}" for f in flags)
    assert flags == [], f"{len(flags)} bare `python` invocation(s) in run-*.ps1:\n{detail}"


def test_bite_detector_flags_bare_subprocess(tmp_path, monkeypatch):
    """NON-VACUOUS BITE: point the audit at a tmp dir with one bad + one good file,
    and prove the real detector flags the bare call and clears the wrapped one.
    If this stops flagging, the ratchet above is hollow."""
    bad = tmp_path / "leaker.py"
    bad.write_text(
        "import subprocess\n"
        "def go():\n"
        "    return subprocess.run(['git', 'status'], capture_output=True)\n",
        encoding="utf-8",
    )
    good = tmp_path / "clean.py"
    good.write_text(
        "import subprocess, sys\n"
        "_CNW = 0x08000000 if sys.platform == 'win32' else 0\n"
        "def go():\n"
        "    return subprocess.run(['git', 'status'], capture_output=True, creationflags=_CNW)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(AUD, "PY_AUDIT_ROOTS", [tmp_path])
    monkeypatch.setattr(AUD, "REPO", tmp_path)  # so flag's py.relative_to(REPO) resolves
    flags = AUD._audit_py_missing_creationflags()
    flagged = {Path(f["file"]).name for f in flags}
    assert "leaker.py" in flagged, "detector failed to flag a bare subprocess.run — guard is hollow"
    assert "clean.py" not in flagged, "detector wrongly flagged a wrapped subprocess.run"


def test_comment_mentioning_subprocess_run_is_not_flagged(tmp_path, monkeypatch):
    """Regression guard (2026-08-20): a doc comment that merely PROSE-mentions
    `subprocess.run() call` (e.g. explaining why creationflags is defined) was
    matched by the bare-text regex and false-flagged as a real, uncovered call
    site — it re-REDded `mcp_audit_probe.py` right after the fix landed. A
    full-line `#` comment must never count as a call site."""
    commented = tmp_path / "commented.py"
    commented.write_text(
        "import subprocess, sys\n"
        "# Every subprocess.run() call in this module carries creationflags.\n"
        "_CNW = 0x08000000 if sys.platform == 'win32' else 0\n"
        "def go():\n"
        "    return subprocess.run(['git', 'status'], capture_output=True, creationflags=_CNW)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(AUD, "PY_AUDIT_ROOTS", [tmp_path])
    monkeypatch.setattr(AUD, "REPO", tmp_path)
    flags = AUD._audit_py_missing_creationflags()
    assert flags == [], f"a comment-only mention was wrongly flagged as a call site: {flags}"


def test_ps1_comment_mentioning_python_is_not_flagged(tmp_path, monkeypatch):
    """Regression guard (mirrors the py-side fix, commit 6c9bb2a4, queue item
    PS1-BARE-PYTHON-COMMENT-SKIP): a PowerShell `#` doc comment that merely
    prose-mentions a bare `python.exe` invocation must not be flagged as a real
    call site -- only an actual uncommented bare-python line should flag."""
    ps1 = tmp_path / "run-example.ps1"
    ps1.write_text(
        "# python.exe used to be called bare here -- now routed through the hidden shim.\n"
        "Invoke-PythonHidden -ScriptPath 'C:/repo/script.py'\n"
        "python.exe C:/repo/other_script.py\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(AUD, "SCRIPTS_DIR", tmp_path)
    monkeypatch.setattr(AUD, "REPO", tmp_path)
    monkeypatch.setattr(AUD, "PS1_BARE_PYTHON_EXEMPT", set())
    flags = AUD._audit_ps1_bare_python()
    lines = {f["line"] for f in flags}
    assert 1 not in lines, f"commented python.exe mention was wrongly flagged: {flags}"
    assert 3 in lines, f"real uncommented bare-python call site was NOT flagged: {flags}"


# --- hook launcher rule (corrected 2026-08-29) -----------------------------------------
# The rule used to demand a hidden wrapper around EVERY python-ish hook launcher,
# including pythonw. That flagged 7 compliant hooks, and its prescribed "fix" would have
# added an extra process spawn to every PreToolUse -- i.e. every tool call -- to prevent
# a window that a GUI-subsystem binary cannot open. These two tests pin the corrected
# rule from both sides: pythonw is clean, a real console launcher is still caught.

def _hook_flags(tmp_path, monkeypatch, command: str):
    import json
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(
        {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": command}]}]}}),
        encoding="utf-8")
    monkeypatch.setattr(AUD, "HOOK_CONFIG_SOURCES", [settings])
    flags, scanned = AUD._audit_hook_commands()
    assert scanned == 1, f"fixture not scanned in isolation (scanned={scanned})"
    return flags


def test_bare_pythonw_hook_is_compliant(tmp_path, monkeypatch):
    """pythonw.exe is PE subsystem 2 -- the loader gives it no console to flash."""
    flags = _hook_flags(tmp_path, monkeypatch,
                        'C:/Python313/pythonw.exe "${CLAUDE_PROJECT_DIR}/setup/hooks/x.py"')
    assert flags == [], f"bare pythonw wrongly flagged: {flags}"


def test_console_launcher_hook_is_still_flagged(tmp_path, monkeypatch):
    """The BITE: python.exe/npx/cmd genuinely do allocate a console. Still caught."""
    for launcher in ("C:/Python313/python.exe script.py", "npx -y some-pkg", "cmd /c foo"):
        flags = _hook_flags(tmp_path, monkeypatch, launcher)
        assert flags, f"console launcher slipped through: {launcher!r}"
        assert flags[0]["flag"] == "HOOK_BARE_CONSOLE_LAUNCHER"
