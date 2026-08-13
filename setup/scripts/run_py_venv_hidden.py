"""Launch a backtest-venv Python script with GUARANTEED no console window.

WHY THIS EXISTS (2026-08-13). J: "STOP THESE FUCKING CMD POPUS BEFORE I KILL MYSELF".
With the leak detector unwedged, 63 leaks were caught in ~10 minutes -- every one a
`WindowsTerminal.exe -Embedding` console host, and 26 of them titled:

    C:\\Users\\jackw\\Desktop\\42\\backtest\\.venv\\Scripts\\pythonw.exe

That is the VENV's pythonw, not the system one. The 2026-07-14 root-cause note in
window-leak-detector.py records that `import pandas`/numpy on a headless venv-pythonw launch
allocates a WindowsTerminal -Embedding host, and that script-level fixes (sys.stdout redirect,
os.dup2, warnings filter) and launcher-level fixes (Shell.Run, WshExec, Popen+CREATE_NO_WINDOW)
were all tested live and all still leaked. The detector's mitigation HIDES those windows, but
hiding happens up to one poll interval (100ms) later -- which is exactly the flash J sees.

THE PATTERN THAT DOES WORK is already proven in this repo by
window_leak_detector_keepalive.py: run the SYSTEM pythonw (GUI subsystem, allocates no console)
and put the venv's site-packages on PYTHONPATH, rather than invoking the venv's own pythonw.
That is L41's shape and it has run for months without leaking.

    task action:  wscript //nologo run_exe_hidden.vbs <system-pythonw> run_py_venv_hidden.py <script.py> [args...]

SCOPE / HONESTY: PYTHONPATH is not a full venv activation. A package needing an entry-point
script, a .pth side effect, or a DLL directory beyond site-packages may behave differently.
This launcher therefore FAILS LOUDLY (non-zero exit + a log line) rather than silently degrading,
and each task must be verified individually after conversion -- not converted in bulk on faith.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG_DIR = REPO / "automation" / "state" / "logs"
SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
VENV_SITE = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
VENV_ROOT = REPO / "backtest" / ".venv"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with (LOG_DIR / f"run-py-venv-hidden-{dt.date.today().isoformat()}.log").open(
            "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        _log("FATAL: no target script given")
        return 2
    target = Path(argv[1])
    args = argv[2:]
    if not target.exists():
        _log(f"FATAL: target missing: {target}")
        return 2
    if not SYS_PYTHONW.exists():
        # Fail LOUD. Silently falling back to the venv pythonw would reintroduce the exact
        # leak this launcher exists to remove.
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW} -- refusing to fall back to the "
             f"venv pythonw, which is the console-allocating binary")
        return 2

    env = os.environ.copy()
    if VENV_SITE.exists():
        prior = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(VENV_SITE) + (os.pathsep + prior if prior else "")
        env["VIRTUAL_ENV"] = str(VENV_ROOT)
    else:
        _log(f"WARN: venv site-packages not found at {VENV_SITE}; running with ambient imports")

    try:
        proc = subprocess.run(
            [str(SYS_PYTHONW), str(target), *args],
            cwd=str(REPO), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
        _log(f"{target.name} exit={proc.returncode}" + (f" args={args}" if args else ""))
        return int(proc.returncode)
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL: launch failed for {target.name}: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
