"""manager_overseer.py — Sonnet "training wheels" for the free Ollama Manager.

Periodically (scheduled, after-hours), SONNET (not opus — cheap) reviews the free
Manager's recent outputs + actions, diagnoses quality problems (repetition / garbage
token-salad / vagueness), and writes CONCRETE corrective guidance to
automation/state/manager-feedback.md — which gamma_manager reads at the top of every
cycle. This is temporary supervision until the free Manager produces good work solo;
then disable Gamma_ManagerOverseer.

Cost: a few Sonnet `claude --print` calls/day (Max pool, NOT opus). Self-gates RTH.
Fail-open: any failure just leaves the prior feedback in place.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
OUT_DIR = REPO / "analysis" / "manager"
LOG = STATE / "manager-log.jsonl"
FEEDBACK = STATE / "manager-feedback.md"

SONNET = "claude-sonnet-4-6"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _claude_exe() -> str:
    cands = [
        Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
        Path(r"C:\Users\jackw\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"),
        Path(r"C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.181\claude.exe"),
    ]
    for c in cands:
        if c.exists():
            return str(c)
    return "claude"


def _et_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=-4)


def _is_rth() -> bool:
    et = _et_now()
    h = et.hour + et.minute / 60
    return et.weekday() < 5 and 9.5 <= h <= 16


def _clean(s: str, n: int) -> str:
    s = "".join(ch for ch in s if ch.isprintable() or ch in "\n\t ")
    return s[:n]


def gather() -> str:
    files = sorted(glob.glob(str(OUT_DIR / "2026-*.md")), key=os.path.getmtime, reverse=True)[:4]
    samples = []
    for f in files:
        t = Path(f).read_text(encoding="utf-8", errors="replace")
        words = t.split()
        uniq = len(set(words)) / max(1, len(words))
        tag = " [DEGENERATE token-salad]" if (len(words) > 120 and uniq < 0.3) else ""
        samples.append(f"### {Path(f).name} ({len(t)} chars){tag}\n{_clean(t, 700)}")
    actions = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-14:]:
            try:
                e = json.loads(line)
                if e.get("phase") == "dispatch":
                    actions.append(f"ok={e.get('ok')} {e.get('role')}: {e.get('action')}")
            except json.JSONDecodeError:
                continue
    return ("## Recent Manager actions:\n" + "\n".join(actions) +
            "\n\n## Recent output samples:\n" + "\n\n".join(samples))


PROMPT = """TASK: Review the recent work of an autonomous FREE-model "Manager" (it drives 0DTE SPY options R&D for Project Gamma; each cycle it picks an action and dispatches to a free model) and write corrective guidance for its NEXT cycle. Today is {today} (2026). Do the task now — do not ask questions.

Known problems: it REPEATS "validate the top contender" almost every cycle, and one free-model output degenerated into repetitive token-salad.

Write <=250 words of markdown bullets (the Manager reads this verbatim before its next pick):
- What to STOP (e.g. repeating the same validate action).
- 3-4 SPECIFIC, varied next actions with concrete named targets (e.g. "rank the contender sweep top-5 by edge_capture vs the 771 J-edge floor"; "critique candidate <name>"; "ideate ONE vwap_continuation rvol-floor variant"; "forage one free FRED series").
- One rule: outputs <=400 words, structured, no repetition.

Output ONLY the guidance bullets. No preamble, no questions, no code fences.

=== RECENT MANAGER WORK ===
{context}
"""


def main() -> int:
    if _is_rth():
        print("skipped (RTH)")
        return 0
    prompt = PROMPT.format(today=_et_now().strftime("%Y-%m-%d"), context=gather())
    tf = STATE / ".overseer-prompt.tmp"
    try:
        tf.write_text(prompt, encoding="utf-8")
    except OSError:
        pass
    exe = _claude_exe()
    try:
        # Feed the prompt via stdin redirect (a long multi-line prompt is unreliable
        # as a Windows positional arg). shell=True uses cmd.exe's < redirect.
        proc = subprocess.run(f'"{exe}" --print --model {SONNET} < "{tf}"',
                              shell=True, capture_output=True, text=True,
                              timeout=240, cwd=str(REPO), encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"overseer claude call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    fb = (proc.stdout or "").strip()
    if not fb:
        print(f"empty feedback; rc={proc.returncode} stderr={(proc.stderr or '')[:300]}", file=sys.stderr)
        return 1
    FEEDBACK.write_text(f"<!-- Sonnet overseer {_et_now():%Y-%m-%d %H:%M} ET -->\n{fb}\n", encoding="utf-8")
    print(f"wrote {len(fb)} chars of overseer feedback -> {FEEDBACK.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
