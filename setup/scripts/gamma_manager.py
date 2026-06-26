"""gamma_manager.py — the FREE autonomous driver (the Manager tier).

Replaces the opus Gamma_Conductor's recon+dispatch on $0 free models. ONE bounded
cycle per fire:
  gather context -> the COORDINATOR (fast free lane: Groq, falls to local) picks the
  single highest-value ready R&D action + the Employee role to do it -> dispatch via
  swarm_client.call_role -> write the output -> log. On a guard/blocker it ESCALATES
  (enqueue a signal, NEVER halt).

Rails (mirror the conductor, on free models):
  * FAIL-OPEN — never blocks J / the heartbeat / the dev server (OP-25/OP-32).
  * MARKET-HOURS — no heavy work 09:30-15:55 ET (heartbeat shares the pool + GPU).
  * PROPOSE-NOT-APPLY — never touches the LIVE_DOCTRINE_DENYLIST; only writes to
    analysis/ + strategy/candidates/ + the queue/outbox. No orders, ever.
  * $0 — free lane pool + local Ollama floor only.

CEO (Claude) is invoked ONLY when the coordinator flags escalate=true (a genuine
design fork, a denylist surface, or the SHIP/REVOKE call) — via an enqueued signal.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import swarm_client as sc  # noqa: E402

STATE = REPO / "automation" / "state"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
QUEUE_MD = REPO / "automation" / "overnight" / "queue.md"
OUT_DIR = REPO / "analysis" / "manager"
LOG = STATE / "manager-log.jsonl"
OUTBOX = STATE / "discord-outbox.jsonl"
FEEDBACK = STATE / "manager-feedback.md"   # the Sonnet overseer writes corrective guidance here


def _looks_like_garbage(text: str) -> bool:
    """Detect token-salad / degenerate-loop output (the Nemotron failure mode)."""
    t = (text or "").strip()
    if len(t) < 300:
        return False
    words = t.split()
    if len(words) >= 120:
        uniq = len(set(words)) / len(words)
        if uniq < 0.28:                 # <28% unique words = repetitive salad
            return True
    # a single token repeated many times in a row
    longest = cur = 1
    for a, b in zip(words, words[1:]):
        cur = cur + 1 if a == b else 1
        longest = max(longest, cur)
    return longest >= 8

PICK_SCHEMA = {
    "type": "object",
    "required": ["role", "prompt"],
    "properties": {
        "action": {"type": "string", "description": "short label of the action (optional)"},
        "role": {"type": "string", "description": "employee role: strategist|coder|critic|validator|forager|chef"},
        "prompt": {"type": "string", "description": "the concrete instruction for that employee"},
        "reason": {"type": "string", "description": "why this is the highest-value next thing right now"},
        "escalate": {"type": "boolean", "description": "true ONLY if this needs the CEO (Claude): a design fork, a doctrine/params/order change, or the SHIP/REVOKE call"},
        "python_tool": {"type": "string", "description": "OPTIONAL: instead of an LLM role, run a compute tool an LLM cannot do. Available: rank_contenders (rank the grind/sweep contenders vs the J-edge floor). Use when the best action is backtest/ranking work, not writing."},
    },
}

VALID_ROLES = {"strategist", "coder", "critic", "validator", "forager", "chef"}
ROLE_ALIAS = {
    "ideator": "strategist", "ideate": "strategist", "ideation": "strategist",
    "ranker": "critic", "rank": "critic", "analyst": "critic", "reviewer": "critic",
    "tester": "validator", "validate": "validator", "researcher": "forager",
    "harvester": "forager", "forage": "forager", "cook": "chef", "coding": "coder",
}

# Compute-shaped work the Manager dispatches to PYTHON, not an LLM (an LLM can't run a
# backtest). Bounded, read-only/analysis only — never touches orders/params/heartbeat.
PYTHON_TOOLS = {
    "rank_contenders": ["setup/scripts/rank_contenders.py"],
}


def _et_now() -> datetime:
    now = datetime.now(timezone.utc)
    y = now.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = (march + timedelta(days=(6 - march.weekday()) % 7 + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = (nov + timedelta(days=(6 - nov.weekday()) % 7)).replace(hour=6)
    off = -4 if (dst_start <= now < dst_end) else -5
    return (now + timedelta(hours=off)).replace(tzinfo=None)


def _is_market_hours() -> bool:
    et = _et_now()
    if et.weekday() >= 5:
        return False
    h = et.hour + et.minute / 60
    return 9.5 <= h <= 15.917


def _tail(path: Path, n: int) -> str:
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def gather_context() -> str:
    """Lean context for the coordinator: status, kitchen queue, recent candidates."""
    parts = [f"## TODAY: {_et_now():%Y-%m-%d %H:%M} ET — trust this system clock over your training cutoff; it really is 2026."]
    # Corrective guidance from the Sonnet overseer (training wheels until the free Manager gets it right).
    if FEEDBACK.exists():
        fb = _tail(FEEDBACK, 30).strip()
        if fb:
            parts.append("## OVERSEER FEEDBACK (follow this — it corrects your recent mistakes):\n" + fb)
    parts.append("## STATUS (tail)\n" + _tail(STATUS_MD, 20))
    ks = STATE / "kitchen-status.json"
    if ks.exists():
        try:
            s = json.loads(ks.read_text(encoding="utf-8"))
            qs = s.get("queue_summary", {})
            parts.append(f"## Kitchen: {qs.get('by_status')} pending-by-prio={qs.get('by_priority_pending')}")
        except (json.JSONDecodeError, OSError):
            pass
    cand_dir = REPO / "strategy" / "candidates"
    recent = sorted(cand_dir.glob("2026-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
    if recent:
        parts.append("## Recent candidates (newest first):\n" + "\n".join(f"- {p.name}" for p in recent))
    parts.append("## Pending queue.md tail\n" + _tail(QUEUE_MD, 15))
    # The premarket review sweep (the big contender tournament) streams here. When it
    # completes, validating/testing its top contenders is the highest-value loop-closing work.
    sweep = REPO / "analysis" / "recommendations" / "mass-grind-progress.jsonl"
    if sweep.exists():
        try:
            lines = sweep.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            last = lines[-1][:300] if lines else ""
            parts.append(f"## CONTENDER SWEEP (mass-grind): {len(lines)} rows so far. Last: {last}\n"
                         "If this sweep looks COMPLETE, PRIORITIZE validating/critiquing its top contenders "
                         "(dispatch role=critic or validator) over generating new drafts.")
        except OSError:
            pass
    # Short-term memory: what I just did, so I pick something DIFFERENT (anti-repeat).
    if LOG.exists():
        try:
            done = []
            for line in LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-12:]:
                try:
                    e = json.loads(line)
                    if e.get("phase") == "dispatch" and e.get("action"):
                        done.append(f"{e.get('role')}: {e['action']}")
                except json.JSONDecodeError:
                    continue
            if done:
                parts.append("## You RECENTLY did these (do NOT repeat — pick something DIFFERENT / the next thing):\n"
                             + "\n".join(f"- {a}" for a in done[-8:]))
        except OSError:
            pass
    return "\n\n".join(p for p in parts if p.strip())


SYSTEM = (
    "You are Gamma's MANAGER — the autonomous free-model driver of a 0DTE SPY options "
    "research firm. Each cycle, pick the SINGLE highest-value, ready, BOUNDED R&D action "
    "and the employee role to do it.\n"
    "EMPLOYEES: strategist (ideate ONE concrete variant), coder (write a backtest "
    "config/JSON), critic (adversarially review ONE specific candidate), validator "
    "(check decision-agreement on ONE item), forager (harvest free data/strategies), "
    "chef (cook ONE strategy candidate).\n"
    "ROTATE across DIFFERENT work each cycle — do NOT repeat the same action you did "
    "recently (see 'You RECENTLY did'). Vary the TARGET and the ROLE. Pick from: rank/triage "
    "the contender sweep, critique a SPECIFIC named candidate, ideate ONE new variant of a "
    "known edge, forage a specific free data source, improve a doc, or find a concrete bug.\n"
    "Make the `prompt` CONCRETE and NARROW (name the exact file/candidate/contender + the "
    "exact question). Vague prompts produce garbage. For COMPUTE work an LLM CANNOT do (ranking/backtesting the contender sweep), set python_tool=\"rank_contenders\" instead of a role — it runs the real ranker, not a guess. Set escalate=true ONLY for a genuine "
    "design fork, a doctrine/params/order change, or a SHIP/REVOKE call — never for normal R&D. "
    "Output ONLY the JSON object."
)


def escalate(reason: str, detail: str = "") -> None:
    """Enqueue a signal for the CEO — never halts."""
    line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "gamma_manager", "reason": reason, "detail": detail[:500]}
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass
    try:
        with open(QUEUE_MD, "a", encoding="utf-8") as f:
            f.write(f"\n- [ ] ESCALATION ({reason}) — {detail[:200]} _(gamma_manager {_et_now():%Y-%m-%d %H:%M} ET)_\n")
    except OSError:
        pass


def _log(entry: dict) -> None:
    entry["ts_et"] = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def run_cycle(*, allow_heavy: bool = True) -> dict:
    """One bounded Manager cycle: pick the highest-value action, dispatch, log."""
    ctx = gather_context()
    pick_prompt = (
        "Given the current firm state below, output the JSON for the single "
        "highest-value, bounded, ready R&D action to run RIGHT NOW.\n\n" + ctx
    )
    env, pick = sc.call_role_json("coordinator", pick_prompt, PICK_SCHEMA,
                                  system=SYSTEM, max_tokens=700, task_id="manager.pick")
    if not pick:
        _log({"phase": "pick", "ok": False, "lane": env.get("lane"), "error": env.get("error")})
        return {"ok": False, "stage": "pick", "error": env.get("error")}

    role = (pick.get("role") or "").strip().lower()
    action = pick.get("action") or (pick.get("prompt", "")[:40].strip() or "task")
    if pick.get("escalate"):
        escalate("manager_flagged", f"{action}: {pick.get('reason','')}")
        _log({"phase": "escalate", "action": action, "reason": pick.get("reason")})
        return {"ok": True, "stage": "escalate", "action": action, "reason": pick.get("reason")}

    # PYTHON DISPATCH: compute-shaped work an LLM can't do (ranking/backtesting).
    ptool = (pick.get("python_tool") or "").strip().lower()
    if ptool in PYTHON_TOOLS:
        cmd = [sys.executable] + [str(REPO / p) for p in PYTHON_TOOLS[ptool]]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240,
                                  cwd=str(REPO), encoding="utf-8", errors="replace")
            out = (proc.stdout or proc.stderr or "")[:4000]
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            op = OUT_DIR / f"{_et_now():%Y-%m-%d-%H%M}-python-{ptool}.md"
            op.write_text(f"<!-- gamma_manager PYTHON tool={ptool} rc={proc.returncode} | {action} -->\n\n```\n{out}\n```\n",
                          encoding="utf-8")
            _log({"phase": "python", "ok": proc.returncode == 0, "tool": ptool,
                  "out": str(op.relative_to(REPO))})
            return {"ok": proc.returncode == 0, "stage": "python", "tool": ptool,
                    "out": str(op.relative_to(REPO))}
        except Exception as exc:  # noqa: BLE001
            _log({"phase": "python", "ok": False, "tool": ptool, "error": str(exc)[:200]})
            return {"ok": False, "stage": "python", "tool": ptool, "error": str(exc)[:200]}

    role = ROLE_ALIAS.get(role, role)
    if role not in VALID_ROLES:
        role = "strategist"   # safe default — never waste a cycle on a role-name typo

    # Dispatch to the employee (free). Chef cooks are big; others are bounded.
    work_prompt = (f"(Today is {_et_now():%Y-%m-%d} — trust the system clock, it is 2026, "
                   "not your training-cutoff year.)\n\n" + pick.get("prompt", ""))
    denv = sc.call_role(role, work_prompt, max_tokens=1800, temperature=0.4,
                        timeout=110, remote_timeout=80, task_id=f"manager.dispatch.{role}")
    content = (denv.get("content") or "").strip()
    # Garbage guard: free reasoning models sometimes degenerate into token-salad
    # (the overnight Nemotron failure). Reject + retry ONCE tighter; never write junk.
    if denv.get("ok") and _looks_like_garbage(content):
        _log({"phase": "dispatch", "ok": False, "role": role, "action": action,
              "error": "garbage_retry", "lane": denv.get("lane")})
        denv = sc.call_role(role, work_prompt + "\n\nBe concise + structured, max ~400 words, NO repetition.",
                            max_tokens=900, temperature=0.2, timeout=80, remote_timeout=60,
                            task_id=f"manager.dispatch.{role}.retry")
        content = (denv.get("content") or "").strip()
    if not (denv.get("ok") and content) or _looks_like_garbage(content):
        _log({"phase": "dispatch", "ok": False, "role": role, "action": action,
              "lane": denv.get("lane"), "error": denv.get("error") or "garbage_output"})
        return {"ok": False, "stage": "dispatch", "role": role, "action": action,
                "error": denv.get("error") or "garbage_output"}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in action.lower())[:50]
    out_path = OUT_DIR / f"{_et_now():%Y-%m-%d-%H%M}-{role}-{slug}.md"
    header = (f"<!-- gamma_manager (FREE) | role={role} lane={denv.get('lane')} "
              f"elapsed={denv.get('elapsed_s')}s | action={action} -->\n"
              f"<!-- reason: {pick.get('reason','')} -->\n\n")
    out_path.write_text(header + content, encoding="utf-8")
    _log({"phase": "dispatch", "ok": True, "role": role, "lane": denv.get("lane"),
          "action": action, "out": str(out_path.relative_to(REPO)),
          "elapsed_s": denv.get("elapsed_s")})
    return {"ok": True, "stage": "dispatch", "role": role, "lane": denv.get("lane"),
            "action": action, "out": str(out_path.relative_to(REPO))}


def main() -> int:
    # RTH guard (fail-open): never fan out during market hours — the heartbeat shares
    # the pool + the GPU. The free Manager drives the firm after-hours only.
    if _is_market_hours():
        out = {"ok": True, "stage": "skipped_market_hours", "et": _et_now().strftime("%H:%M")}
        _log(out)
        print(json.dumps(out))
        return 0
    res = run_cycle()
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
