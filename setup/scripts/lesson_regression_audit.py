#!/usr/bin/env python
"""Lesson-regression audit (Phase 4 of the autonomy plan).

The system graduates anti-patterns into code assertions (backtest/tests/test_graduated_guards.py,
test_lNNN_*.py). They run in CI, but a FAILURE there is only an aggregate red -- there is no
loop that says "lesson L173 re-violated, here's a fresh work item." This audit closes that:

  1. Run the graduated guard suite (slow -- backtests -- so this is a periodic audit, not a
     per-commit gate).
  2. Parse PER-LESSON failures from the pytest output.
  3. Record each to automation/state/lesson-regressions.jsonl (idempotent per lesson+day).
  4. File a `LESSON-REGRESSION` queue item per NEW regression so it resurfaces as drainable
     work in the conductor backlog -- a regressed lesson can never silently rot.

Exit 0 if all graduated guards pass, 1 if any regressed. Pure stdlib.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "backtest" / "tests"
STATE = REPO / "automation" / "state"
REG_LOG = STATE / "lesson-regressions.jsonl"
QUEUE = REPO / "automation" / "overnight" / "queue.md"

_LESSON_RE = re.compile(r"l(\d{1,4})", re.IGNORECASE)
_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)


def _guard_targets() -> list[str]:
    targets = [TESTS / "test_graduated_guards.py"]
    targets += sorted(TESTS.glob("test_l[0-9]*.py"))  # per-lesson graduated tests
    return [str(p) for p in targets if p.exists()]


def run_guards() -> tuple[int, str]:
    """Run the graduated guard suite; return (returncode, combined_output).
    Seam: tests monkeypatch this so the parser is verifiable without the slow run."""
    py = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
    py = str(py) if py.exists() else sys.executable
    targets = _guard_targets()
    if not targets:
        return 0, "no graduated guard tests found"
    proc = subprocess.run([py, "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider", *targets],
                          cwd=str(REPO), capture_output=True, text=True)
    return proc.returncode, proc.stdout + "\n" + proc.stderr


def parse_failures(output: str) -> list[dict]:
    """From pytest output, return [{test, lesson}] for each FAILED line. The lesson id is the
    first lNNN token in the test node id (e.g. ...::test_l173_supersede -> 'L173'); falls back
    to the bare test name when no lesson token is present."""
    out = []
    for node in _FAILED_RE.findall(output):
        # the lesson token may live in the FILE (test_l173_*.py) or the test name
        # (test_l99_*) -- search the whole node id; fall back to the bare test name.
        m = _LESSON_RE.search(node)
        if m:
            lesson = "L" + m.group(1)
        else:
            lesson = node.split("::")[-1] if "::" in node else node
        out.append({"test": node, "lesson": lesson})
    return out


def _today() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def _already_logged(lesson: str, day: str) -> bool:
    if not REG_LOG.exists():
        return False
    for line in REG_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("lesson") == lesson and str(r.get("detected_at", "")).startswith(day):
            return True
    return False


def _record(fail: dict) -> bool:
    """Append a regression row (idempotent per lesson+day). Return True if newly recorded."""
    day = _today()
    if _already_logged(fail["lesson"], day):
        return False
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with REG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"detected_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                                "lesson": fail["lesson"], "test": fail["test"]}) + "\n")
        return True
    except Exception:
        return False


def _file_queue_item(fail: dict) -> bool:
    """Append a LESSON-REGRESSION item to the Active backlog (idempotent by lesson). True if added."""
    if not QUEUE.exists():
        return False
    marker = f"LESSON-REGRESSION-{fail['lesson']}"
    text = QUEUE.read_text(encoding="utf-8")
    if marker in text:
        return False
    item = (f"- [ ] {marker} (HIGH) :: Graduated lesson {fail['lesson']} RE-VIOLATED -- its guard "
            f"`{fail['test']}` is failing. A graduated lesson regressed; fix the code that broke it "
            f"(do NOT weaken the test). :: depends:none :: status:pending\n")
    # insert right under the "## Active backlog" header so it's seen first
    anchor = "## Active backlog\n"
    idx = text.find(anchor)
    if idx < 0:
        with QUEUE.open("a", encoding="utf-8") as f:
            f.write("\n" + item)
    else:
        cut = idx + len(anchor)
        text = text[:cut] + "\n" + item + text[cut:]
        QUEUE.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit graduated lessons for regression.")
    ap.add_argument("--dry-run", action="store_true", help="report only; do not write log/queue")
    args = ap.parse_args()

    rc, output = run_guards()
    fails = parse_failures(output)
    if not fails:
        print(f"[lesson-audit] all graduated guards green (rc={rc}). No regressions.")
        return 0

    new_logged = new_queued = 0
    for f in fails:
        print(f"[lesson-audit] REGRESSION: {f['lesson']} ({f['test']})")
        if not args.dry_run:
            if _record(f):
                new_logged += 1
            if _file_queue_item(f):
                new_queued += 1
    print(f"[lesson-audit] {len(fails)} regression(s); {new_logged} newly logged, {new_queued} queue item(s) filed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
