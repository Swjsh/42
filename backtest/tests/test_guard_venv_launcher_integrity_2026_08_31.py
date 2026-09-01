"""Venv launcher integrity guard — permanent regression test.

Scar (2026-08-31): ``backtest/.venv/Scripts/pythonw.exe`` had been overwritten
with a byte-identical copy of the BASE CPython ``pythonw.exe`` (the real
``venvwlauncher.exe`` was set aside as ``pythonw.exe.redirector-backup``).

Mechanism: a bare CPython launcher outside its own install directory cannot
locate ``python313.dll``.  The Windows loader searches only the exe's own
directory, System32, and PATH — the DLL is in none of those for a venv's
``Scripts`` dir.  Every launch therefore died on a MODAL "python313.dll was not
found" dialog before the interpreter ever started.

Blast radius when it broke: 80 wedged ``pythonw.exe`` processes and a silently
dead ``automation/scripts/engine_shadow.py`` (the heartbeat invokes the shadow
harness through this exact interpreter path).

Guard class: HARD.  These assertions test the FAILURE MECHANISM, not a
cosmetic property:
  (a) A venv launcher must never be byte-identical to the base interpreter —
      that identity IS the bug.
  (b) A venv launcher must actually start with the base install absent from
      PATH, which is what Task Scheduler hands it.

Deliberately NOT asserted: an exact hash match against
``Lib/venv/scripts/nt/venvlauncher.exe``.  That would flip RED on every routine
CPython patch upgrade and train the reader to ignore this file.

2026-08-31 (author: python313.dll incident).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import sysconfig
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_SCRIPTS = REPO_ROOT / "backtest" / ".venv" / "Scripts"
LAUNCHERS = ("python.exe", "pythonw.exe")

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Windows-only failure mode (DLL loader search order)"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_install_dir() -> Path:
    """Directory of the venv's BASE interpreter (where python313.dll lives)."""
    cfg = REPO_ROOT / "backtest" / ".venv" / "pyvenv.cfg"
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "home" and value.strip():
                return Path(value.strip())
    return Path(sysconfig.get_config_var("BINDIR") or sys.base_prefix)


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"not present on this machine: {path}")
    return path


@pytest.mark.parametrize("name", LAUNCHERS)
def test_venv_launcher_is_not_a_bare_interpreter_copy(name: str) -> None:
    """(a) The exact 2026-08-31 breakage: launcher == base interpreter copy."""
    launcher = _require(VENV_SCRIPTS / name)
    base = _base_install_dir() / name
    if not base.exists():
        pytest.skip(f"base interpreter missing: {base}")

    assert _sha256(launcher) != _sha256(base), (
        f"{launcher} is a byte-identical copy of the base interpreter {base}.\n"
        "A bare CPython launcher in a venv Scripts dir cannot load its "
        "pythonXY.dll and will hang on a modal loader dialog.\n"
        "Fix: restore the venv redirector, e.g.\n"
        f"  copy /Y \"{_base_install_dir() / 'Lib' / 'venv' / 'scripts' / 'nt' / ('venvwlauncher.exe' if name == 'pythonw.exe' else 'venvlauncher.exe')}\" \"{launcher}\""
    )


@pytest.mark.parametrize("name", LAUNCHERS)
def test_venv_launcher_starts_without_base_python_on_path(
    name: str, tmp_path: Path
) -> None:
    """(b) Functional truth under a Task-Scheduler-shaped minimal PATH."""
    launcher = _require(VENV_SCRIPTS / name)

    marker = tmp_path / "ok.txt"
    script = tmp_path / "probe.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys
            with open(sys.argv[1], "w", encoding="utf-8") as fh:
                fh.write(sys.prefix)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    windir = os.environ.get("SystemRoot", r"C:\Windows")
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(windir) / "system32"), windir])

    try:
        proc = subprocess.run(
            [str(launcher), str(script), str(marker)],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:  # modal dialog blocks forever
        pytest.fail(
            f"{launcher} HUNG with the base install off PATH — almost certainly "
            "the modal 'pythonXY.dll was not found' loader dialog. "
            "See this file's docstring."
        )

    assert proc.returncode == 0, (
        f"{launcher} exited {proc.returncode} with the base install off PATH.\n"
        f"stderr: {proc.stderr[-2000:]}"
    )
    assert marker.exists(), (
        f"{launcher} produced no output — it never reached Python.\n"
        f"stderr: {proc.stderr[-2000:]}"
    )
    assert marker.read_text(encoding="utf-8").strip().lower() == str(
        VENV_SCRIPTS.parent
    ).lower(), "launcher started the wrong interpreter (sys.prefix is not the venv)"


def test_no_stray_launcher_backups_shadowing_scripts_dir() -> None:
    """A stashed copy of the BROKEN binary next to the good one is a landmine.

    Backups are fine; a backup that is itself a bare interpreter copy is the
    thing that gets restored over the good launcher next time someone tidies up.
    """
    if not VENV_SCRIPTS.exists():
        pytest.skip(f"venv not present: {VENV_SCRIPTS}")

    base_dir = _base_install_dir()
    base_hashes = {
        _sha256(base_dir / n) for n in LAUNCHERS if (base_dir / n).exists()
    }
    if not base_hashes:
        pytest.skip(f"base interpreter missing: {base_dir}")

    offenders = [
        stray
        for stray in VENV_SCRIPTS.glob("python*.exe.*")
        if _sha256(stray) in base_hashes
    ]
    assert not offenders, (
        "Stray bare-interpreter copies parked in the venv Scripts dir: "
        f"{[str(p) for p in offenders]}. Delete them — restoring one over "
        "python.exe/pythonw.exe reintroduces the python313.dll dialog."
    )
