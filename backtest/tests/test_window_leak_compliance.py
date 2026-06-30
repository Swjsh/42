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
