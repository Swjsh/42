#!/usr/bin/env python3
"""bg_status.py -- one-glance "is the background work still running, and is it producing?"

WHY (OP-33(e), J 2026-08-06): J has asked "confirm it's all still running / we're not waiting on
an empty result" more than once, and each time it was answered by hand-rolling a throwaway Python
snippet against the workflow journal. A repeated question is a MISSING INSTRUMENT, not a query.
This is that instrument.

The specific failure it exists to catch: a workflow can report agents as "done" while their
returned payload is null or a stub -- the 2026-08-06 EOD run had 4 agents die on API 529s and
return nothing, and the only way to know was to inspect journal.jsonl by hand. So this does not
merely count completions; it MEASURES EACH PAYLOAD and flags empty ones loudly.

2026-08-12 -- WHY THIS GREW A SECOND HALF. J asked "are we still working on anything in the
background?" for the **37th** time (`automation/state/j-question-ledger.jsonl`, intent
`is_running`) while this very instrument sat on disk built to retire that exact question. Root
cause: it globbed ONLY `subagents/workflows/*/journal.jsonl`, i.e. runs of the Workflow tool.
Agents spawned with the **Agent tool** -- which is how essentially all of this repo's background
work is actually dispatched -- leave no journal.jsonl and were therefore 100% invisible. The
instrument reported "No workflow runs found" while 13 agents were live. A monitor whose coverage
SCOPE is narrower than the thing it monitors reads as "nothing running" instead of "I can't see"
(L292). So: Agent-tool subagents are now first-class here.

Three distinct failure classes are flagged, because they fail differently:
  * EMPTY    -- returned null/stub (the 2026-08-06 API-529 class).
  * HOLDING? -- returned a *long, plausible* payload whose content is "I'm still waiting on my
                sub-agents." Two of 13 agents did exactly this on 2026-08-12: the constants
                auditor ended on "All three sweep agents are still running" and the slippage
                re-baseline on "Holding for the arms to finish." Both look complete and both
                delivered no answer. A character-count check cannot see this, which is precisely
                why it went unnoticed for hours. Heuristic and marked with a "?" -- it reads the
                final text, so it can misfire; treat it as "go look", never as proof.
  * STALE?   -- mid-tool-call and cold for STALE_MINUTES.

COMPLETION ORACLE (self-contained, no 76MB parent-transcript scan): an agent transcript ends in a
bare assistant message exactly when that agent finished its turn. If the last record still carries
a `tool_use` block it is mid-flight. Note that a sub-agent's tool_result lands in its PARENT
AGENT's transcript, never the session's -- scanning the session transcript marks every depth-2
agent permanently "outstanding", which is why that approach was rejected.

Reads only. Writes nothing. No network. $0. Fails open -- never raises into a caller.

Usage:
    python setup/scripts/bg_status.py            # last 24h, agents + workflows
    python setup/scripts/bg_status.py --all      # every run on disk
    python setup/scripts/bg_status.py --json     # machine-readable
    python setup/scripts/bg_status.py --live     # only what is still RUNNING
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# A returned payload smaller than this is almost certainly a stub/null rather than real work.
# Calibrated against the 2026-08-06 runs: real lane payloads ran 17k-24k chars; the 529-killed
# agents returned literally nothing.
EMPTY_PAYLOAD_CHARS = 50

# No journal write in this long, with agents still marked running, means the run is likely wedged
# rather than merely slow. Agents in this repo routinely run 20-40 min, so this is deliberately
# generous -- a false "STALE" is worse than a late one.
STALE_MINUTES = 45

# Phrases that mean "I finished my turn without finishing my job."
#
# Matched against the LEDE ONLY -- the first HOLDING_LEDE_CHARS of the final message.
#
# That window is set by evidence, not taste. All three dud returns observed on 2026-08-12 put the
# tell in their opening sentence:
#     "All three sweep agents are still running."          (constants audit, 336 chars)
#     "Holding for the arms to finish."                    (slippage, 1,422 chars)
#     "77/78 ... Waiting on the completion notifications." (slippage, 3rd notification)
# An agent that stops early leads with why. My first cut also scanned the last 400 chars to catch a
# hypothetical "I'll report back once they finish" sign-off -- but that case was invented, not
# observed, and the false-positive guard immediately caught the cost: on any message shorter than
# ~700 chars, head+tail covers the entire text, so an ordinary report that merely MENTIONS a
# still-running nightly task in its body gets flagged. Designing around an imagined failure mode
# created a real one. Lede-only, until a real sign-off case shows up.
HOLDING_PHRASES = (
    "still running",
    "still in progress",
    "holding for",
    "waiting for",
    "waiting on",
    "have not yet returned",
    "yet to return",
)
HOLDING_LEDE_CHARS = 300


def _ascii(s: str) -> str:
    """Windows consoles here are cp1252; an emoji in an agent's summary raised UnicodeEncodeError
    and killed the whole report mid-print. Status output must never die on its own payload."""
    return s.encode("ascii", "replace").decode("ascii")


def _sessions_root() -> Path:
    return Path(os.path.expanduser("~")) / ".claude" / "projects"


def _find_workflow_dirs(max_age_h: float | None) -> list[Path]:
    root = _sessions_root()
    if not root.exists():
        return []
    out: list[Path] = []
    now = time.time()
    for jf in root.glob("*/*/subagents/workflows/*/journal.jsonl"):
        try:
            age_h = (now - jf.stat().st_mtime) / 3600.0
        except OSError:
            continue
        if max_age_h is not None and age_h > max_age_h:
            continue
        out.append(jf.parent)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def _scan(run_dir: Path) -> dict:
    jf = run_dir / "journal.jsonl"
    started, results, empties = 0, [], []
    try:
        text = jf.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # fail open
        return {"run": run_dir.name, "error": str(exc)}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        kind = rec.get("type")
        if kind == "started":
            started += 1
        elif kind == "result":
            label = rec.get("label") or rec.get("agentId") or "?"
            value = rec.get("value", rec.get("result"))
            try:
                size = 0 if value is None else len(json.dumps(value))
            except (TypeError, ValueError):
                size = 0
            results.append({"label": label, "chars": size})
            if size < EMPTY_PAYLOAD_CHARS:
                empties.append(label)

    try:
        idle_min = (time.time() - jf.stat().st_mtime) / 60.0
    except OSError:
        idle_min = -1.0

    running = max(0, started - len(results))
    if running == 0 and started > 0:
        state = "COMPLETE"
    elif idle_min > STALE_MINUTES:
        state = "STALE?"
    else:
        state = "RUNNING"
    if empties:
        state += " +EMPTY"

    return {
        "run": run_dir.name,
        "state": state,
        "started": started,
        "done": len(results),
        "running": running,
        "idle_min": round(idle_min, 1),
        "empty_payloads": empties,
        "results": results,
    }


def _detached_workers() -> list[dict]:
    """Long-running processes that an AGENT LAUNCHED AND LEFT BEHIND.

    WHY (found the same night this file grew its agent lane, by testing the new lane's own answer):
    `--live` reported "0 RUNNING" while two study arms the slippage agent had spawned -- batch.py,
    gated.py and two slip_runner*.py -- had been grinding for two hours. They survive because
    `backtest/.venv` is reaper-exempt (`_shared.ps1#Stop-StaleClaudeProcesses`). An agent stopping
    is NOT its work stopping, so "no agents running" is not an answer to "is anything still
    running". Same L292 shape as the agent gap itself, one level down.

    Windows-only (CIM); returns [] anywhere else and on any failure. Fails open by construction --
    a status tool must never raise, and an empty list here degrades to the agent+workflow view.
    """
    if not sys.platform.startswith("win"):
        return []
    import subprocess  # noqa: PLC0415 -- optional, Windows-only path
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
        "ForEach-Object { [pscustomobject]@{ pid=$_.ProcessId; "
        "started=$_.CreationDate.ToString('o'); cmd=$_.CommandLine } } | ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=25).stdout
        procs = json.loads(raw) if raw.strip() else []
    except Exception:  # noqa: BLE001 -- fail open; this lane is a bonus, never a dependency
        return []
    if isinstance(procs, dict):
        procs = [procs]

    out: list[dict] = []
    for p in procs:
        cmd = (p or {}).get("cmd") or ""
        # Agent-launched work lives in the per-session scratchpad. Scheduled daemons launch from
        # setup/scripts via run_cmd_hidden and are NOT what "are we still working?" is asking
        # about -- they are always on by design.
        #
        # Slashes are NORMALIZED first: the same session scratchpad shows up with backslashes from
        # some launchers and forward slashes from others. A backslash-only match silently dropped
        # the two longest-running arms (batch.py, gated.py) while listing their short-lived
        # children -- an undercount that reads as "less is running than really is".
        norm = cmd.lower().replace("/", "\\")
        if "\\claude\\" not in norm or "scratchpad" not in norm:
            continue
        started = str((p or {}).get("started") or "")
        age_min = -1.0
        try:
            from datetime import datetime  # noqa: PLC0415
            ts = datetime.fromisoformat(started)
            age_min = (datetime.now(ts.tzinfo) - ts).total_seconds() / 60.0
        except Exception:  # noqa: BLE001
            pass
        # The script name is the only legible part of a 400-char scratchpad command line.
        script = next((tok.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                       for tok in cmd.split() if tok.lower().endswith(".py")), "?")
        out.append({"pid": (p or {}).get("pid"), "script": script,
                    "age_min": round(age_min, 1), "cmd": cmd[:200]})
    return sorted(out, key=lambda r: -r["age_min"])


def _tail_message(transcript: Path) -> tuple[str, bool, int]:
    """Return (final assistant text, last_record_has_tool_use, record_count).

    Reads the whole file rather than seeking the tail: these transcripts are tens-to-hundreds of
    KB, and a byte-offset seek can land mid-line and mis-parse. Cheap enough at this size.
    """
    text, has_tool, n = "", False, 0
    try:
        with transcript.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                n += 1
                last = line
    except OSError:
        return "", False, 0
    if n == 0:
        return "", False, 0
    try:
        rec = json.loads(last)
    except (ValueError, TypeError):
        return "", False, n
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                has_tool = True
            elif block.get("type") == "text":
                parts.append(block.get("text", ""))
        text = "\n".join(parts)
    # A record that is not an assistant turn at all (a tool_result being fed back in) also means
    # the agent is mid-flight, not finished.
    if rec.get("type") != "assistant":
        has_tool = True
    return text, has_tool, n


def _find_agent_metas(max_age_h: float | None) -> list[Path]:
    """Agent-tool subagents. THE COVERAGE GAP this instrument was missing until 2026-08-12."""
    root = _sessions_root()
    if not root.exists():
        return []
    out: list[Path] = []
    now = time.time()
    for mf in root.glob("*/*/subagents/agent-*.meta.json"):
        try:
            age_h = (now - mf.stat().st_mtime) / 3600.0
        except OSError:
            continue
        if max_age_h is not None and age_h > max_age_h:
            continue
        out.append(mf)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def _scan_agent(meta_path: Path) -> dict:
    agent_id = meta_path.name[len("agent-"):-len(".meta.json")]
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, TypeError) as exc:  # fail open
        return {"kind": "agent", "id": agent_id, "error": str(exc)}

    transcript = meta_path.with_name(f"agent-{agent_id}.jsonl")
    final_text, mid_tool, records = _tail_message(transcript)
    try:
        idle_min = (time.time() - transcript.stat().st_mtime) / 60.0
    except OSError:
        idle_min = -1.0

    stripped = final_text.strip()
    chars = len(stripped)
    lede = stripped[:HOLDING_LEDE_CHARS].lower()
    holding = bool(stripped) and any(p in lede for p in HOLDING_PHRASES)

    if mid_tool or records == 0:
        state = "RUNNING" if 0 <= idle_min <= STALE_MINUTES else "STALE?"
    elif chars < EMPTY_PAYLOAD_CHARS:
        state = "EMPTY"
    elif holding:
        state = "HOLDING?"
    else:
        state = "DONE"

    return {
        "kind": "agent",
        "id": agent_id,
        "short": agent_id[:9],
        "desc": meta.get("description", "?"),
        "agent_type": meta.get("agentType", "?"),
        "model": meta.get("model", "?"),
        "depth": meta.get("spawnDepth", 1),
        "state": state,
        "records": records,
        "final_chars": chars,
        "idle_min": round(idle_min, 1),
        # The lede, not the tail: it is where a dud return announces itself.
        "final_lede": stripped[:160],
    }


def _print_agents(agents: list[dict]) -> None:
    print(f"{'STATE':<9} {'D':<2} {'ID':<10} {'MODEL':<7} {'DESC':<34} {'CHARS':>8} {'IDLE':>7}")
    print("-" * 82)
    for a in agents:
        if a.get("error"):
            print(f"{'ERR':<9} {'?':<2} {a['id'][:10]:<10} {_ascii(a['error'])[:40]}")
            continue
        print(
            f"{a['state']:<9} {a['depth']:<2} {a['short']:<10} {str(a['model'])[:7]:<7} "
            f"{_ascii(a['desc'])[:34]:<34} {a['final_chars']:>8,} {a['idle_min']:>6.1f}m"
        )
    bad = [a for a in agents if a.get("state") in ("EMPTY", "HOLDING?", "STALE?")]
    for a in bad:
        why = {
            "EMPTY": "returned nothing",
            "HOLDING?": "returned a WAITING message, not an answer",
            "STALE?": "mid-tool-call and cold",
        }[a["state"]]
        print(f"    !! {a['short']} {a['state']} -- {why}: {_ascii(a['final_lede'])[:90]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Background work status at a glance.")
    ap.add_argument("--all", action="store_true", help="every run on disk, not just last 24h")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--live", action="store_true", help="only what is still RUNNING")
    args = ap.parse_args(argv)

    max_age = None if args.all else 24.0
    scans = [_scan(d) for d in _find_workflow_dirs(max_age)]
    agents = [_scan_agent(m) for m in _find_agent_metas(max_age)]
    workers = _detached_workers()
    if args.live:
        agents = [a for a in agents if a.get("state") in ("RUNNING", "STALE?")]
        scans = [s for s in scans if str(s.get("state", "")).startswith("RUNNING")]

    running = [a for a in agents if a.get("state") == "RUNNING"]
    if args.json:
        print(json.dumps({"agents": agents, "runs": scans, "detached_workers": workers,
                          "n_running": len(running),
                          "n_detached": len(workers)}, indent=2))
        return 0

    # Detached work first: an agent stopping is not its work stopping, and this is the lane that
    # answers "is anything still running" when every agent has already reported.
    print(f"DETACHED WORKERS (agent-launched, still alive) -- {len(workers)}")
    if workers:
        for w in workers:
            print(f"   pid {str(w['pid']):<7} {w['age_min']:>7.1f}m  {_ascii(w['script'])}")
    else:
        print("   none.")

    print()
    window = "" if args.all else " (last 24h; --all for everything)"
    print(f"AGENT-TOOL SUBAGENTS{window} -- {len(running)} RUNNING of {len(agents)}")
    if agents:
        _print_agents(agents)
    else:
        print("  none found.")

    print()
    if scans:
        print(f"{'STATE':<16} {'WORKFLOW RUN':<24} {'DONE':>6} {'RUN':>5} {'IDLE':>7}")
        print("-" * 64)
        for s in scans:
            if s.get("error"):
                print(f"{'ERR':<16} {s['run']:<24} {_ascii(s['error'])[:30]}")
                continue
            print(
                f"{s['state']:<16} {s['run'][:24]:<24} "
                f"{s['done']:>3}/{s['started']:<2} {s['running']:>5} {s['idle_min']:>6.1f}m"
            )
            if s["empty_payloads"]:
                print(f"    !! EMPTY PAYLOADS: {_ascii(', '.join(s['empty_payloads']))}")
    else:
        print("WORKFLOW-TOOL RUNS: none" + ("" if args.all else " in the last 24h."))
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 -- fail open, never raise into a caller
        print(f"bg_status: non-fatal error: {exc}")
        sys.exit(0)
