"""agent_pulse.py -- "is anything still running?" answered without asking Claude.

WHY (2026-08-29): J asked "still working in background?" -- a STATE question, which
OP-33(e) classes as a missing instrument rather than a query. Background workflows and
subagents write rich JSONL as they run; nothing read it back. This does.

It is also the first brick of the orchestrator-cockpit data layer: the same rows this
prints are what the pulse UI renders as boxes and in-flight messages.

Reads only. Never writes, never spawns, never blocks. $0.

Usage:
    python setup/scripts/agent_pulse.py            # human table
    python setup/scripts/agent_pulse.py --json     # machine (the cockpit feed)
    python setup/scripts/agent_pulse.py --stale 60 # mark idle after 60s of silence
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
DEFAULT_STALE_SECONDS = 120


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _read_journal(journal: Path) -> tuple[list[str], dict[str, int]]:
    """(started agent ids, {finished agent id: result size})."""
    started: list[str] = []
    finished: dict[str, int] = {}
    try:
        text = journal.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return started, finished
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        agent_id = record.get("label") or record.get("agentId") or ""
        kind = record.get("type")
        if kind == "started":
            started.append(agent_id)
        elif kind == "result":
            finished[agent_id] = len(str(record.get("result") or ""))
    return started, finished


def scan(stale_seconds: int = DEFAULT_STALE_SECONDS) -> dict:
    """Every workflow run this machine has on disk, newest first."""
    now = dt.datetime.now().timestamp()
    runs: list[dict] = []

    for wf_dir in PROJECTS.glob("*/*/subagents/workflows/wf_*"):
        if not wf_dir.is_dir():
            continue
        agent_files = sorted(wf_dir.glob("agent-*.jsonl"), key=_mtime, reverse=True)
        if not agent_files:
            continue
        newest = _mtime(agent_files[0])
        started, finished = _read_journal(wf_dir / "journal.jsonl")
        in_flight = [a for a in started if a not in finished]
        quiet_for = round(now - newest, 1)
        # "running" needs BOTH an unfinished agent AND recent disk activity: an unfinished
        # agent with a cold directory is a dead run, not a working one.
        if in_flight and quiet_for < stale_seconds:
            status = "RUNNING"
        elif in_flight:
            status = "STALLED"
        else:
            status = "DONE"
        runs.append(
            {
                "run_id": wf_dir.name,
                "status": status,
                "agents_started": len(started),
                "agents_finished": len(finished),
                "in_flight": len(in_flight),
                "quiet_for_s": quiet_for,
                "last_write": dt.datetime.fromtimestamp(newest).isoformat(timespec="seconds"),
                "result_chars": sum(finished.values()),
                "dir": str(wf_dir),
            }
        )

    runs.sort(key=lambda r: r["last_write"], reverse=True)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "stale_seconds": stale_seconds,
        "runs": runs,
        "any_running": any(r["status"] == "RUNNING" for r in runs),
    }


def render(report: dict) -> str:
    runs = report["runs"]
    if not runs:
        return "no workflow runs on disk"
    icon = {"RUNNING": "[>]", "STALLED": "[!]", "DONE": "[x]"}
    lines = [
        f"{'run':26} {'state':9} {'agents':>9}  {'quiet':>8}  last write",
        "-" * 74,
    ]
    for r in runs[:12]:
        lines.append(
            f"{r['run_id'][:26]:26} {icon[r['status']]+r['status'][:5]:9} "
            f"{r['agents_finished']}/{r['agents_started']:<7} "
            f"{r['quiet_for_s']:>7.0f}s  {r['last_write'][11:]}"
        )
    running = [r for r in runs if r["status"] == "RUNNING"]
    lines.append("")
    if running:
        r = running[0]
        lines.append(
            f"ANSWER: YES -- {len(running)} run(s) active. "
            f"{r['in_flight']} agent(s) in flight, last write {r['quiet_for_s']:.0f}s ago."
        )
    else:
        stalled = [r for r in runs if r["status"] == "STALLED"]
        lines.append(
            f"ANSWER: NO -- nothing running."
            + (f" {len(stalled)} STALLED run(s) need a look." if stalled else "")
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report background workflow/agent activity.")
    parser.add_argument("--json", action="store_true", help="machine-readable (cockpit feed)")
    parser.add_argument("--stale", type=int, default=DEFAULT_STALE_SECONDS)
    args = parser.parse_args()
    report = scan(args.stale)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
