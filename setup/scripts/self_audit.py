"""self_audit.py -- the proactive GAP-FINDER organ Gamma was missing.

Why (2026-06-26, J: "WHY IS GAMMA NOT SMART YET? WHY DID GAMMA NOT KNOW THIS"): all day the
operator had to point out gaps Gamma should have caught itself (validation-not-direction,
draw-your-own-trendlines, dormant-setups-are-theater, test-in-the-24/7-gym). Root cause the
swarm itself named: the "brainstorm second-order effects" directive (OP / feedback_proactive_
engine_brainstorm) was NEVER run autonomously -- Gamma reacts instead of interrogating its own
work. This script turns the existing free swarm-decision-engine into a SCHEDULED self-audit:
every run it asks the free swarm "what is Gamma obviously missing right now?", logs the ranked
gaps, and FLAGS the ones it hasn't seen before -- so Gamma surfaces its own gaps before J does.

$0 (free OpenRouter models via swarm_consult.py). Pure stdlib + subprocess. Flash-free when
scheduled via the wscript->pythonw chain (NEVER a bare powershell/cmd action -- see the popup
lesson). Idempotent: appends to a gap-log, dedupes by normalized gap text.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
from et_clock import et_now as _et_clock_now  # DST-aware ET (TZ-SYSTEMIC fix)
SWARM = REPO / "setup" / "scripts" / "swarm_consult.py"
PY = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
LOG = REPO / "analysis" / "self-audit" / "gap-log.jsonl"
FLAGS = REPO / "analysis" / "self-audit" / "new-gaps-flagged.md"
CONSULT_DIR = REPO / "analysis" / "swarm-consult"

STANDING_QUESTION = (
    "Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engine) for "
    "what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 "
    "concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it "
    "isn't using, existing infrastructure not connected, next-order implications, and what the "
    "operator will point at NEXT. Be specific; avoid generic advice."
)


def _et_now() -> datetime:
    """ET from UTC via DST-aware et_clock (replaces hardcoded -4)."""
    return _et_clock_now()


def _recent_context() -> str:
    """Feed the swarm what changed lately so the audit is grounded, not generic."""
    bits = []
    try:
        status = (REPO / "automation" / "overnight" / "STATUS.md").read_text(encoding="utf-8")
        bits.append("RECENT STATUS (top):\n" + "\n".join(status.splitlines()[:40]))
    except Exception:
        pass
    try:
        log = subprocess.run(["git", "-C", str(REPO), "log", "--oneline", "-12"],
                             capture_output=True, text=True, timeout=20)
        bits.append("RECENT COMMITS:\n" + log.stdout)
    except Exception:
        pass
    return "\n\n".join(bits)[:180_000]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()[:90]


def _known_gap_keys() -> set[str]:
    if not LOG.exists():
        return set()
    keys = set()
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            keys.add(json.loads(line)["key"])
        except Exception:
            continue
    return keys


def _extract_gaps(consult_json: dict) -> list[str]:
    """Pull the ranked gap bullets out of the swarm synthesis + perspectives."""
    text = json.dumps(consult_json)
    # The synthesis + perspective markdown carries numbered/bulleted gaps; grab bold lead-ins
    # and numbered items from the raw perspective text.
    out = []
    for persp in consult_json.get("perspectives", []):
        body = persp.get("content") or persp.get("text") or ""
        for m in re.findall(r"(?m)^\s*\d+\.\s+\*\*(.+?)\*\*", body):
            out.append(m.strip())
        for m in re.findall(r"(?m)^\s*[-*]\s+\*\*(.+?)\*\*", body):
            out.append(m.strip())
    synth = consult_json.get("synthesis", {})
    sbody = synth.get("content") if isinstance(synth, dict) else str(synth)
    for m in re.findall(r"(?m)^\s*[-*]\s+(.+)$", sbody or ""):
        out.append(m.strip()[:120])
    # dedupe preserving order
    seen, ded = set(), []
    for g in out:
        k = _norm(g)
        if k and k not in seen:
            seen.add(k); ded.append(g)
    return ded[:12]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    LOG.parent.mkdir(parents=True, exist_ok=True)
    exe = str(PY) if PY.exists() else sys.executable
    before = {p.name for p in CONSULT_DIR.glob("*.json")} if CONSULT_DIR.exists() else set()
    try:
        subprocess.run([exe, str(SWARM), "audit", "--quiet", "--question", STANDING_QUESTION,
                        "--context", _recent_context()],
                       cwd=str(REPO), timeout=300, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001
        print(f"self_audit: swarm run failed ({type(e).__name__}: {e})")
        return 0
    new_files = sorted((CONSULT_DIR.glob("*.json")), key=lambda p: p.stat().st_mtime)
    new_files = [p for p in new_files if p.name not in before]
    if not new_files:
        print("self_audit: no swarm output produced (roster may be fully stale)")
        return 0
    consult = json.loads(new_files[-1].read_text(encoding="utf-8"))
    gaps = _extract_gaps(consult)
    known = _known_gap_keys()
    ts = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
    fresh = []
    with LOG.open("a", encoding="utf-8") as f:
        for g in gaps:
            key = hashlib.sha1(_norm(g).encode()).hexdigest()[:12]
            is_new = _norm(g) not in {_norm(x) for x in []} and key not in known
            f.write(json.dumps({"ts_et": ts, "key": key, "gap": g, "new": is_new}) + "\n")
            if is_new:
                fresh.append(g)
    print(f"self_audit {ts}: {len(gaps)} gaps audited, {len(fresh)} NEW")
    for g in gaps:
        print(("  NEW  " if g in fresh else "  seen ") + g[:100])
    if fresh:
        with FLAGS.open("a", encoding="utf-8") as f:
            f.write(f"\n## {ts} -- {len(fresh)} new gap(s) Gamma self-identified\n")
            for g in fresh:
                f.write(f"- {g}\n")
        print(f"  -> flagged {len(fresh)} new to {FLAGS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
