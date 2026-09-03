"""Diagnostic regression guard for PANDAS-CONSOLE-LEAK-ROOT-CAUSE (queue.md, LOW,
discovered 2026-07-14, root-cause corrected 2026-09-03).

BACKGROUND
----------
The 2026-07-14 investigation attributed a leaked ``WindowsTerminal.exe -Embedding``
console-host window to ``import pandas``/numpy under
``backtest\\.venv\\Scripts\\pythonw.exe``, and shipped a MITIGATION (auto-hide via
``window-leak-detector.py``) without finding the mechanism.

BISECTION DONE 2026-09-03 (this fire)
--------------------------------------
Ran three variants of a script under the venv's ``pythonw.exe`` with
CREATE_NO_WINDOW deliberately ABSENT (matching the item's own instruction), using
``automation/state/window-leaks.jsonl`` (the live detector's log) as the oracle:
zero-import control, ``import numpy`` alone, and ``import pandas``. ALL THREE
produced the byte-identical leak signature: a child process image ``python.exe``
(the BASE INSTALL's CONSOLE-subsystem interpreter, confirmed via
``Win32_Process.ExecutablePath``) spawned by the venv's ``pythonw.exe``, which
itself immediately spawns a ``conhost.exe`` grandchild — the actual console host.
Running the BASE INSTALL's own ``pythonw.exe`` DIRECTLY (bypassing the venv
redirector) with the identical control script never leaked anything.

ROOT CAUSE: pandas/numpy is NOT the trigger. ``backtest\\.venv\\Scripts\\pythonw.exe``
is a legitimate, byte-identical copy of CPython's ``venvwlauncher.exe`` redirector
(see ``test_guard_venv_launcher_integrity_2026_08_31.py`` — this is NOT the
2026-08-31 "corrupted launcher" scar; that one is already fixed and guarded
separately). ``pyvenv.cfg`` stores only ONE ``executable=...\\python.exe`` key (no
GUI-variant path), so the redirector's target resolution reaches the
CONSOLE-subsystem base interpreter on every launch, regardless of which Scripts-dir
stub (``python.exe`` or ``pythonw.exe``) was invoked or what the script imports.

NOT a one-liner: the real fix is either upgrading the base CPython install (if a
later 3.13.x patch corrects the launcher's GUI-variant target resolution) or
rerouting every headless launch to call the BASE INSTALL's ``pythonw.exe`` directly,
bypassing the venv redirector — both out of scope for this LOW hygiene pass (the
second touches the scheduler launch chain). Reported, not patched. See the
corrected root-cause comment in ``setup/scripts/window-leak-detector.py`` (search
"ROOT CAUSE CORRECTED 2026-09-03").

WHAT THIS TEST GUARDS
----------------------
Not "the bug exists" (an upstream CPython/Windows quirk this repo doesn't control
and shouldn't pin as required) but the CLAIM that actually matters for future
investigators: whether pandas/numpy participates in the leak at all. It launches a
zero-import control script and an ``import pandas`` script through the identical
venv ``pythonw.exe`` path and asserts their child-process behavior is IDENTICAL.
That assertion holds whether the underlying CPython launcher quirk is still present
(both leak) or has since been fixed upstream (neither leaks) — the only way it
FAILS is the scenario this test exists to catch: pandas participating where a
plain script does not, i.e. the original (now-refuted) 2026-07-14 theory turning
out to be right after all.

Windows-only, best-effort: skips cleanly (never fails) when the venv, the base
install, or WMIC process introspection is unavailable — this documents a live
environment finding, it is not a portable application-code contract.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_SCRIPTS = REPO_ROOT / "backtest" / ".venv" / "Scripts"
VENV_PYTHONW = VENV_SCRIPTS / "pythonw.exe"

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Windows-only investigation (venv launcher / conhost behavior)"
)


def _base_install_pythonw() -> "Path | None":
    cfg = REPO_ROOT / "backtest" / ".venv" / "pyvenv.cfg"
    if not cfg.exists():
        return None
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "home" and value.strip():
            candidate = Path(value.strip()) / "pythonw.exe"
            return candidate if candidate.exists() else None
    return None


def _child_image_names(parent_pid: int, timeout_s: float = 4.0) -> set[str]:
    """Poll (best-effort, WMIC) for the set of direct child process image names of
    `parent_pid` while it's alive. Never raises -- WMIC/parsing failure yields an
    empty set (treated as "no leaked child observed" by callers, the conservative
    direction for a diagnostic test)."""
    deadline = time.monotonic() + timeout_s
    names: set[str] = set()
    while time.monotonic() < deadline:
        try:
            out = subprocess.check_output(
                ["wmic", "process", "where", f"ParentProcessId={parent_pid}",
                 "get", "Name", "/FORMAT:LIST"],
                stderr=subprocess.DEVNULL, timeout=5,
                creationflags=0x08000000,  # CREATE_NO_WINDOW -- this is OUR polling
                # call, not the thing under test (which launches with the flag
                # deliberately absent, per the item's own instruction).
            ).decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(0.2)
            continue
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Name="):
                val = line[len("Name="):].strip()
                if val:
                    names.add(val)
        if names:
            break
        time.sleep(0.2)
    return names


def _run_and_observe_children(pythonw: Path, script: Path) -> set[str]:
    """Launch `script` under `pythonw` with CREATE_NO_WINDOW deliberately absent
    (matching the item's own bisection instruction), observe direct child image
    names, then clean up. Never raises."""
    proc = None
    try:
        proc = subprocess.Popen([str(pythonw), str(script)])
        names = _child_image_names(proc.pid)
        return names
    except Exception:
        return set()
    finally:
        if proc is not None:
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


@pytest.fixture()
def _control_script(tmp_path: Path) -> Path:
    p = tmp_path / "control.py"
    p.write_text("import time\ntime.sleep(3)\n", encoding="utf-8")
    return p


@pytest.fixture()
def _pandas_script(tmp_path: Path) -> Path:
    p = tmp_path / "pandas_import.py"
    p.write_text(
        textwrap.dedent(
            """
            import pandas  # noqa: F401
            import time
            time.sleep(3)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return p


def test_pandas_import_does_not_change_venv_pythonw_child_spawn_behavior(
    _control_script, _pandas_script
):
    """THE core claim: pandas participates in the leak no more than a bare script.
    Asserts identical child-process outcomes for both -- see module docstring."""
    if not VENV_PYTHONW.exists():
        pytest.skip(f"venv pythonw.exe not present: {VENV_PYTHONW}")

    control_children = _run_and_observe_children(VENV_PYTHONW, _control_script)
    pandas_children = _run_and_observe_children(VENV_PYTHONW, _pandas_script)

    if not control_children and not pandas_children:
        pytest.skip(
            "neither run produced an observable child within the timeout -- "
            "either WMIC introspection is unavailable on this box, or the "
            "2026-09-03 finding's underlying CPython launcher behavior has "
            "since been fixed upstream. Either way, non-reproduction here."
        )

    assert control_children == pandas_children, (
        "pandas import changed the venv pythonw.exe child-spawn signature -- "
        "this WOULD mean pandas/numpy genuinely IS implicated (the ORIGINAL "
        "2026-07-14 theory), contradicting the 2026-09-03 bisection finding "
        f"that it is not. control={control_children!r} pandas={pandas_children!r}"
    )


def test_base_install_pythonw_does_not_leak_a_console_child(_control_script):
    """Confirms the DIFFERENTIAL half of the finding: the BASE INSTALL's own
    pythonw.exe (bypassing the venv redirector entirely) launches the control
    script WITHOUT spawning any console-subsystem child -- isolating the defect
    to the venv launcher indirection, not the interpreter itself."""
    base_pythonw = _base_install_pythonw()
    if base_pythonw is None:
        pytest.skip("base install pythonw.exe not resolvable from pyvenv.cfg")

    children = _run_and_observe_children(base_pythonw, _control_script)
    assert "python.exe" not in children, (
        f"base install pythonw.exe unexpectedly spawned a python.exe child: {children!r} "
        "-- if this now reproduces, the defect has moved into the base interpreter "
        "itself, not just the venv redirector; re-open PANDAS-CONSOLE-LEAK-ROOT-CAUSE."
    )
