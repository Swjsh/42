"""guard_runner_full.py -- run the WHOLE test suite nightly and fail LOUD.

THE GAP THIS CLOSES (found 2026-08-20)
--------------------------------------
Three tiers of guard existed, and between them ~9,900 tests ran nowhere:

  * PRE-COMMIT  `run_safety_gate.py` -- 6 curated fast suites (59 tests). Its
    scope is deliberate and documented: protect autonomous self-modification,
    stay under ~2s, run on EVERY commit. Correct as designed. Not a regression net.
  * NIGHTLY     `guard_runner_slow.py` -- exactly ONE file,
    `test_graduated_guards.py -m slow`. Correct as designed. Also not a net.
  * EVERYTHING ELSE -- never ran unattended.

Consequence, observed: the 2026-08-20 ATM-tier revert left THREE pins in
`test_bold_core_strike_tier_2026_07_15.py` asserting the pre-revert wiring. That
file is in neither tier, so it sat RED for a full day while every commit passed
and the nightly reported success. A guard that pins LIVE PRODUCTION WIRING can
rot silently -- which is the same C7 silent-success class the gate itself exists
to prevent, one level up.

WHAT THIS DOES
  Runs `pytest -m "not slow"` over the entire suite, then appends ONE loud,
  timestamped line to STATUS.md "## Known broken" on any failure -- reusing
  guard_runner_slow.py's exact reporting shape so J has one place to look and one
  format to read. Writes a machine-readable verdict for the cockpit.

WHY `not slow`: the slow marker is already covered by guard_runner_slow.py, and
those tests each load the 16-month master CSV. Running them twice a night buys
nothing and risks the reaper.

FAIL LOUD, NEVER SILENT: a pytest that cannot even collect ("notests") is
reported as a WIRING problem, not as success. Exit code 0 from this script never
means "all green" by itself -- read the STATUS line.

USAGE
    python setup/guard_runner_full.py [--timeout-sec N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "automation" / "state"
STATUS = ROOT / "automation" / "overnight" / "STATUS.md"
WATCH = STATE / "guard-watch-full.json"

# MEASURED 2026-08-20, not guessed: the suite reached 26% in ~10 minutes on this
# box, implying ~40 min end to end. The first draft shipped 1500s (25 min), which
# would have TIMED OUT every single night and reported a false alarm forever.
# 3600s gives ~50% headroom; the task's ExecutionTimeLimit is set wider (60 min)
# so pytest's own timeout fires first and produces a clean, reportable result.
DEFAULT_TIMEOUT_SEC = 3600
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # OP-27 L41 / C8
_SUMMARY_RE = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")


def _now() -> str:
    try:
        sys.path.insert(0, str(ROOT / "setup" / "scripts"))
        from et_clock import et_now          # DST-aware; never bash TZ (box is Mountain)
        return et_now().strftime("%Y-%m-%d %H:%M ET")
    except Exception:                        # noqa: BLE001 - a clock miss must not lose the report
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M (local)")


def _parse(out: str) -> dict:
    counts = {k: int(n) for n, k in _SUMMARY_RE.findall(out or "")}
    return {
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0),
        "skipped": counts.get("skipped", 0),
    }


def _failed_names(out: str, cap: int = 12) -> list:
    names = re.findall(r"^FAILED (\S+)", out or "", re.MULTILINE)
    return names[:cap]


def _append_status(status: str, summary: str, names: list) -> None:
    """One loud line under '## Known broken' -- same shape guard_runner_slow uses."""
    try:
        text = STATUS.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        return
    detail = (" :: " + ", ".join(names)) if names else ""
    line = (f"- [{_now()}] FULL-SUITE {status.upper()} :: {summary}{detail} :: "
            "re-run: cd backtest && python -m pytest tests/ -q -m \"not slow\"")
    head, _, tail = text.partition(marker + "\n")
    STATUS.write_text(f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    a = ap.parse_args()

    cmd = [sys.executable.replace("pythonw", "python"), "-m", "pytest", "tests/",
           "-q", "-m", "not slow", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT / "backtest"), capture_output=True, text=True,
                           timeout=a.timeout_sec, errors="replace", creationflags=NO_WINDOW)
        out = (r.stdout or "") + (r.stderr or "")
        rc = r.returncode
    except subprocess.TimeoutExpired:
        out, rc = "", -1
        _append_status("timeout", f"suite exceeded {a.timeout_sec}s", [])
        WATCH.write_text(json.dumps({"status": "timeout", "at": _now()}, indent=1), encoding="utf-8")
        print(f"[guards-full] TIMEOUT after {a.timeout_sec}s")
        return 1

    counts = _parse(out)
    names = _failed_names(out)
    if counts["passed"] == 0 and counts["failed"] == 0:
        # Collected nothing -> a WIRING problem, not a pass. Never report success.
        status = "notests"
    elif counts["failed"] or rc != 0:
        status = "red"
    else:
        status = "green"

    summary = (f"{counts['passed']} passed, {counts['failed']} failed, "
               f"{counts['skipped']} skipped")
    WATCH.write_text(json.dumps(
        {"status": status, "at": _now(), "counts": counts,
         "failed_names": names, "returncode": rc}, indent=1), encoding="utf-8")

    if status != "green":
        _append_status(status, summary, names)
    print(f"[guards-full] {status.upper()} :: {summary}"
          + (f" :: {', '.join(names)}" if names else ""))
    return 0 if status == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
