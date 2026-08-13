"""Convert every scheduled task off the console-allocating venv pythonw.

Evidence (2026-08-13, controlled A/B, detector-measured):
    venv pythonw + import pandas      -> 9 leaks / 10 launches (90%)
    system pythonw + PYTHONPATH + same -> 0 leaks / 10 launches (0%)
    ambient over a quiet 30s           -> 0

Two task shapes:
  A) direct     : wscript vbs "<venv-pythonw>" "<script.py>" [args]
                  -> "<sys-pythonw>" "run_py_venv_hidden.py" "<script.py>" [args]
  B) run_cmd_hidden: ... run_cmd_hidden.py --env.. --log.. --cwd.. -- "<venv-pythonw>" <rest>
                  -> same, but terminal interpreter swapped to <sys-pythonw> and a
                     --env PYTHONPATH=<venv site-packages> added so imports still resolve.
"""
import csv
import io
import os
import re
import subprocess
import sys
from pathlib import Path

CNW = 0x08000000
SCRATCH = Path(os.environ.get("TEMP", ".")) / "gamma_task_backup"
SCRATCH.mkdir(parents=True, exist_ok=True)

VENV_PYW = r"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"
VENV_PY = r"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe"
SYS_PYW = r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
SHIM = r"C:\Users\jackw\Desktop\42\setup\scripts\run_py_venv_hidden.py"
SITE = r"C:\Users\jackw\Desktop\42\backtest\.venv\Lib\site-packages"


def run(a):
    return subprocess.run(a, capture_output=True, text=True, errors="replace",
                          creationflags=CNW)


def convert(args: str) -> "tuple[str, str] | None":
    """Return (new_args, shape) or None when nothing to do."""
    for venv in (VENV_PYW, VENV_PY):
        if venv not in args:
            continue
        if "run_cmd_hidden.py" in args:
            # SHAPE B: swap the terminal interpreter, add PYTHONPATH so imports resolve.
            new = args.replace(venv, SYS_PYW, 1)
            if "PYTHONPATH" not in new:
                new = new.replace("run_cmd_hidden.py\"",
                                  f'run_cmd_hidden.py" "--env" "PYTHONPATH={SITE}"', 1)
            return new, "B:run_cmd_hidden"
        # SHAPE A: interpreter -> system pythonw, insert the hidden shim before the target.
        return args.replace(venv, f'{SYS_PYW}" "{SHIM}', 1), "A:direct"
    return None


def main() -> int:
    apply = "--apply" in sys.argv
    out = run(["schtasks", "/query", "/fo", "csv", "/v"]).stdout
    names = sorted({r["TaskName"] for r in csv.DictReader(io.StringIO(out))
                    if "gamma" in r["TaskName"].lower()})
    todo, ok, fail, skip = [], [], [], 0
    for tn in names:
        short = tn.lstrip("\\")
        x = run(["schtasks", "/query", "/tn", short, "/xml"])
        if x.returncode != 0:
            continue
        xml = x.stdout
        m = re.search(r"<Arguments>(.*?)</Arguments>", xml, re.S)
        if not m:
            continue
        args = m.group(1)
        conv = convert(args)
        if conv is None:
            skip += 1
            continue
        new_args, shape = conv
        todo.append((short, shape))
        if not apply:
            continue
        (SCRATCH / f"{short}.pre_venvfix.xml").write_text(xml, encoding="utf-16")
        new_xml = xml.replace(f"<Arguments>{args}</Arguments>",
                              f"<Arguments>{new_args}</Arguments>", 1)
        tmp = SCRATCH / f"{short}.venvfix.xml"
        tmp.write_text(new_xml, encoding="utf-16")
        r = run(["schtasks", "/create", "/tn", short, "/xml", str(tmp), "/f"])
        if r.returncode != 0:
            fail.append((short, (r.stderr or r.stdout).strip()[:70]))
            continue
        v = run(["schtasks", "/query", "/tn", short, "/xml"]).stdout
        m2 = re.search(r"<Arguments>(.*?)</Arguments>", v, re.S)
        clean = m2 and VENV_PYW not in m2.group(1) and VENV_PY not in m2.group(1)
        ok.append((short, shape, bool(clean)))
    print(f"mode={'APPLY' if apply else 'DRY-RUN'}  candidates={len(todo)}  untouched={skip}\n")
    if not apply:
        for n, s in todo:
            print(f"   would convert  {n:<32} [{s}]")
        return 0
    good = [x for x in ok if x[2]]
    bad = [x for x in ok if not x[2]]
    print(f"CONVERTED CLEAN: {len(good)}")
    for n, s, _ in good:
        print(f"   OK  {n:<32} [{s}]")
    if bad:
        print(f"\nSTILL DIRTY: {len(bad)}")
        for n, s, _ in bad:
            print(f"   !!  {n:<32} [{s}]")
    if fail:
        print(f"\nFAILED: {len(fail)}")
        for n, w in fail:
            print(f"   {n}: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ---------------------------------------------------------------------------------------
# RUN RECORD 2026-08-13 (J directive: "no more cmd popups")
#
#   full-XML audit BEFORE : 47 of 140 Gamma tasks referenced the venv python
#   full-XML audit AFTER  : 0
#
# The 47 was itself a correction: schtasks' CSV `Task To Run` column TRUNCATES long actions,
# so three earlier audits in the same session under-counted (20, then 7). Only the per-task
# XML shows the whole action. Any future audit of task actions must use /xml, never /fo csv.
#
# Two shapes handled:
#   A:direct          12 tasks  -> system pythonw + run_py_venv_hidden.py
#   B:run_cmd_hidden  35 tasks  -> terminal interpreter swapped + --env PYTHONPATH=<site-packages>
#
# The 7 Funnel/Grind tasks carried the venv path TWICE (outer interpreter and terminal
# command); a replace-first-occurrence pass fixed only the outer one and left them leaking.
# Replacing ALL occurrences is required -- that near-miss is why this file exists rather than
# a one-off inline snippet.
