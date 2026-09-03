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


_FULL_SUITE_LINE_RE = re.compile(r"^- \[[^\]\n]*\] FULL-SUITE \S+ :: .*\n?", re.MULTILINE)


def _known_broken_body_bounds(text: str, marker: str) -> "tuple[int, int]":
    """(body_start, body_end): body_start sits right after the marker heading's own
    newline; body_end is the offset of the next top-level '## ' heading, or EOF.
    Bounds every clear/replace to ONLY the pinned '## Known broken' section -- a
    FULL-SUITE line that has already rolled into an older dated '## [' entry
    elsewhere in the file is history and must be left alone (FULL-SUITE-RED-LINE-
    OUTLIVES-GREEN, queue.md 2026-09-02)."""
    idx = text.index(marker)
    nl = text.find("\n", idx)
    body_start = nl + 1 if nl != -1 else len(text)
    m = re.search(r"^## ", text[body_start:], re.MULTILINE)
    body_end = body_start + m.start() if m else len(text)
    return body_start, body_end


def _append_status(status: str, summary: str, names: list) -> None:
    """Keep AT MOST ONE 'FULL-SUITE <STATUS>' line inside '## Known broken', written
    only while status != green.

    FULL-SUITE-RED-LINE-OUTLIVES-GREEN (queue.md 2026-09-02, filed from the
    first-live-day box close): this used to only ever APPEND a RED/timeout/notests
    line and this function was never even called on green -- so a fixed suite kept
    reading RED to every consumer (humans, the conductor, first_live_day_review's
    conductor heuristic) with nothing to clear it. Now: prior FULL-SUITE lines are
    ALWAYS stripped from the section body first (bounded to '## Known broken' only,
    see _known_broken_body_bounds), then, if status != green, the newest verdict is
    written back as the section's only FULL-SUITE line -- so red never stacks and
    green never lingers."""
    try:
        text = STATUS.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        # DO NOT return here. Until 2026-08-20 this silently DISCARDED the report.
        # The section had rolled into STATUS-archive-2026-06.md -- status_retention.py
        # rebuilds STATUS.md as `preamble + newest entries`, and the heading sat inside
        # a dated entry that eventually aged out -- so from June onward every failure
        # raised here vanished without a trace while this runner still exited cleanly.
        # Position cannot be relied on either: the conductor PREPENDS new entries above
        # the preamble. So recreate the section instead of trusting it to be there.
        # A failure report that goes nowhere is worse than no report -- it manufactures
        # the belief that something is watching.
        text = marker + "\n\n" + text

    body_start, body_end = _known_broken_body_bounds(text, marker)
    body = _FULL_SUITE_LINE_RE.sub("", text[body_start:body_end])

    if status == "green":
        new_body = body
    else:
        detail = (" :: " + ", ".join(names)) if names else ""
        line = (f"- [{_now()}] FULL-SUITE {status.upper()} :: {summary}{detail} :: "
                "re-run: cd backtest && python -m pytest tests/ -q -m \"not slow\"\n")
        new_body = "\n" + line + body.lstrip("\n")

    STATUS.write_text(text[:body_start] + new_body + text[body_end:], encoding="utf-8")


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
    # The JSON carries EVERY failed nodeid (2026-09-03: the 01:28 ET run reported 24 failed but
    # listed 12, so half the failures were unidentifiable from the artifact); only the one-line
    # STATUS.md summary keeps the 12-name cap for readability.
    names_all = _failed_names(out, cap=10**9)
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
         "failed_names": names_all, "returncode": rc}, indent=1), encoding="utf-8")

    # Always call, never gated on status != green: green now CLEARS any stale
    # FULL-SUITE line from a prior run instead of leaving it to rot (see
    # _append_status's docstring / FULL-SUITE-RED-LINE-OUTLIVES-GREEN).
    _append_status(status, summary, names)
    print(f"[guards-full] {status.upper()} :: {summary}"
          + (f" :: {', '.join(names)}" if names else ""))
    return 0 if status == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
