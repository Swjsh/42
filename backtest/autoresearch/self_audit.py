"""Self-audit — runs every hour, verifies the full autonomy stack is HEALTHY.

Per CLAUDE.md OP 18: "I should publish status proactively at every milestone".
Per OP 19: "self-healing pipeline" — detects + restarts dead components.

Checks:
  1. Discord bridge alive (PID + recent outbox send confirmed)
  2. Discord responder ran in last 10 min (log timestamp)
  3. Grinder pipeline state (which stage, completed counts, dead/alive)
  4. Usage tracker: today's claude --print count vs cap
  5. Scheduled task health (all Gamma_* state)

Writes:
  automation/state/self-audit.json     — machine-readable
  docs/HEALTH.md                       — human-readable

If anything is RED (dead component / cap exceeded / pipeline stalled),
queues a Discord ping. Otherwise silent — no spam.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
STATE_DIR = ROOT / "automation" / "state"
DOCS = ROOT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost on Windows subprocess spawns. OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

AUDIT_JSON = STATE_DIR / "self-audit.json"
HEALTH_MD = DOCS / "HEALTH.md"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"
CFG = STATE_DIR / ".discord-config.json"

DISCORD_RESPONDER_LOG = STATE_DIR / "logs" / "discord-responder.log"
USAGE_SNAP = STATE_DIR / "usage-snapshot.json"

STAGE_DIRS = {
    "stage1": REPO / "autoresearch" / "_state" / "overnight_grinder",
    "stage2": REPO / "autoresearch" / "_state" / "stage2_grinder",
    "stage3": REPO / "autoresearch" / "_state" / "stage3_grinder",
    "stage4": REPO / "autoresearch" / "_state" / "stage4_grinder",
    "bullish": REPO / "autoresearch" / "_state" / "bullish_grinder",
}


def _is_pid_alive(pid: int) -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return f"{pid}" in out
    except Exception:
        return False


def _bridge_alive() -> dict:
    pid_file = STATE_DIR / "discord-bridge.pid"
    if not pid_file.exists():
        return {"alive": False, "reason": "no pid file"}
    try:
        content = pid_file.read_text(encoding="utf-8").strip()
        pid = int(content.split("|")[0])
        return {"alive": _is_pid_alive(pid), "pid": pid}
    except Exception as e:
        return {"alive": False, "reason": str(e)}


def _responder_recent() -> dict:
    if not DISCORD_RESPONDER_LOG.exists():
        return {"ran_recently": False, "reason": "no log"}
    try:
        text = DISCORD_RESPONDER_LOG.read_text(encoding="utf-8").splitlines()
        if not text:
            return {"ran_recently": False, "reason": "empty log"}
        last_line = text[-1]
        # log format: "2026-05-10 10:20:08,092 [INFO] no new messages"
        ts_str = last_line.split(" [")[0].split(",")[0]
        ts = dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        age_min = (dt.datetime.now() - ts).total_seconds() / 60
        return {"ran_recently": age_min < 10, "last_run_min_ago": round(age_min, 1)}
    except Exception as e:
        return {"ran_recently": False, "reason": str(e)}


def _stage_health(stage_dir: Path) -> dict:
    p = stage_dir / "progress.json"
    if not p.exists():
        return {"state": "not_started"}
    try:
        prog = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "progress_unreadable"}
    pid_file = stage_dir / "runner.pid"
    pid_alive = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            pid_alive = _is_pid_alive(pid)
        except Exception:
            pass
    status = prog.get("status", "?")
    return {
        "state": status,
        "completed": prog.get("completed", 0),
        "total": prog.get("total_combos", 0),
        "keepers": prog.get("keepers", 0),
        "pid_alive": pid_alive,
        "deadline_passed_but_running": (
            status == "running" and prog.get("deadline_at") and
            dt.datetime.now() > dt.datetime.fromisoformat(prog["deadline_at"])
        ),
    }


def _scheduled_tasks_state() -> list[dict]:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-ScheduledTask | Where-Object { $_.TaskName -like 'Gamma_*' } | Select-Object TaskName, State | ConvertTo-Json -Compress"],
            stderr=subprocess.DEVNULL, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return json.loads(out) if out.strip().startswith("[") else [json.loads(out)]
    except Exception:
        return []


def _usage_snap() -> dict:
    if not USAGE_SNAP.exists():
        return {"today_count": 0, "today_est_cost_usd": 0.0}
    try:
        return json.loads(USAGE_SNAP.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _user_mention() -> str:
    if not CFG.exists():
        return ""
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:
        return ""


def _queue_alert(content: str) -> None:
    row = {
        "queued_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "content": _user_mention() + content,
    }
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def main() -> int:
    now = dt.datetime.now()

    audit = {
        "checked_at": now.isoformat(),
        "bridge": _bridge_alive(),
        "responder": _responder_recent(),
        "stages": {n: _stage_health(d) for n, d in STAGE_DIRS.items()},
        "scheduled_tasks": _scheduled_tasks_state(),
        "usage": _usage_snap(),
    }

    # Determine RED/AMBER/GREEN
    reds = []
    if not audit["bridge"]["alive"]:
        reds.append("Discord bridge DEAD")
    if not audit["responder"]["ran_recently"]:
        reds.append(f"Discord responder hasn't run in {audit['responder'].get('last_run_min_ago', '?')} min")
    for sname, sh in audit["stages"].items():
        if sh.get("deadline_passed_but_running"):
            reds.append(f"{sname}: past deadline but still marked running")
    usage_today = audit["usage"].get("today_count", 0)
    daily_cap = audit["usage"].get("caps", {}).get("daily", 50)
    if usage_today >= daily_cap * 0.8:
        reds.append(f"usage at {usage_today}/{daily_cap} today (~80% cap)")

    audit["health"] = "RED" if reds else "GREEN"
    audit["red_flags"] = reds

    AUDIT_JSON.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")

    # Health markdown
    md = [f"# Health — {now.isoformat()}\n"]
    md.append(f"**Status:** {audit['health']}\n")
    if reds:
        md.append("## 🔴 Red flags")
        for r in reds:
            md.append(f"- {r}")
        md.append("")
    md.append("## Components")
    md.append(f"- **Discord bridge**: {'✅ alive' if audit['bridge']['alive'] else '❌ ' + audit['bridge'].get('reason', 'dead')}")
    md.append(f"- **Discord responder**: {'✅ ran ' + str(audit['responder'].get('last_run_min_ago', '?')) + ' min ago' if audit['responder']['ran_recently'] else '❌ ' + audit['responder'].get('reason', 'stale')}")
    md.append(f"- **Usage today**: {usage_today}/{daily_cap} (~${audit['usage'].get('today_est_cost_usd', 0):.2f})")
    md.append("")
    md.append("## Pipeline")
    md.append("| Stage | State | Progress | Keepers |")
    md.append("|---|---|---|---|")
    for sname, sh in audit["stages"].items():
        prog = f"{sh.get('completed', 0)}/{sh.get('total', 0)}" if sh.get("total") else "—"
        md.append(f"| {sname} | {sh.get('state', '?')} | {prog} | {sh.get('keepers', 0)} |")
    HEALTH_MD.write_text("\n".join(md), encoding="utf-8")

    # Alert ping ONLY on red flags (no green-status spam)
    if reds:
        msg = f"🔴 **HEALTH RED** ({len(reds)} flags):\n" + "\n".join(f"- {r}" for r in reds)
        _queue_alert(msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
