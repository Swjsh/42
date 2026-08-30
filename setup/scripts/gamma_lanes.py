"""gamma_lanes.py -- one row per RESEARCH LANE, for the desk's left rail.

WHY (J, 2026-08-30): "wheres the kitchen? ... wheres the futures, wheres the tech
analyiss on tickets non spy, etc that should be in activity feed and like 1 agent per
or somthing".

He was right twice over. The lanes were genuinely OFF -- 116 tasks held down by the
weekend blackout, fixed in 590b39dc -- but even with them running the desk had nowhere
to SHOW them. It rendered the Claude-session roster (who is typing right now) and the
git/commit feed (what landed), and between those two sits the thing J actually runs a
firm to do: several independent research lanes, each with its own clock, its own state
files and its own way of being broken.

A lane is not a Claude session and not a scheduled task. It is a standing line of work
with a heartbeat, and the question it must answer at a glance is "is this lane alive,
and when did it last produce something". So every row carries a `state` and a `last_at`,
and both are read from the lane's OWN artefacts -- the file it writes when it does work
-- never from whether its scheduled task happens to be enabled. A task can be Ready and
producing nothing for ten days; the multi-symbol lane was exactly that on the day this
was written, and a roster keyed on task state would have drawn it green.

READ-ONLY. Decides nothing, fires nothing, writes nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "automation" / "state"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import ET_TZ as ET  # noqa: E402

NO_WINDOW = 0x08000000

# How stale a lane's newest artefact may be before the row stops claiming it is working.
# Deliberately per-lane: the kitchen turns a task over in minutes, the prospector runs on
# a multi-hour beat, and holding both to one threshold would either cry wolf on the slow
# lane or go quiet on the fast one.
STALE_MIN = {"kitchen": 90, "futures": 1440, "multi": 1440,
             "prospector": 720, "spy": 1440, "weather": 1440}


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _age_min(path: Path):
    try:
        return (dt.datetime.now().timestamp() - path.stat().st_mtime) / 60
    except OSError:
        return None


def _newest(paths):
    """The freshest existing artefact, and its age. This is a lane's real pulse."""
    best, best_age = None, None
    for p in paths:
        a = _age_min(p)
        if a is None:
            continue
        if best_age is None or a < best_age:
            best, best_age = p, a
    return best, best_age


def _iso(path):
    if path is None:
        return None
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, ET).isoformat()
    except OSError:
        return None


def _tail(path: Path, n: int = 1) -> list:
    """Last n JSON objects from a .jsonl, tolerating a torn final line."""
    try:
        lines = [x for x in path.read_text(encoding="utf-8", errors="replace")
                 .splitlines() if x.strip()]
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _state_for(key: str, age_min, broken: bool = False) -> str:
    if broken:
        return "BROKEN"
    if age_min is None:
        return "NO DATA"
    return "WORKING" if age_min <= STALE_MIN.get(key, 1440) else "STALE"


_TASK_CACHE = {}


def _all_tasks() -> dict:
    """The whole Gamma_* task table, fetched ONCE per process.

    Measured 2026-08-30: without this each of the five lanes span up its own PowerShell
    and desk_live took 7.35s -- served to a client that polls every 30s, which is how a
    read-only status endpoint turns into a load problem. One call, 1.4s.
    """
    if "all" not in _TASK_CACHE:
        try:
            raw = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-ScheduledTask | Where-Object {$_.TaskName -like 'Gamma*'} | "
                 "Select-Object TaskName,State | ConvertTo-Json -Depth 3 -Compress"],
                capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW,
            ).stdout.strip()
            rows = json.loads(raw) if raw else []
            if isinstance(rows, dict):
                rows = [rows]
            _TASK_CACHE["all"] = {
                r.get("TaskName", ""): ("Ready" if str(r.get("State")) == "3" else "Disabled")
                for r in rows}
        except Exception:  # noqa: BLE001 -- task state is context, not the verdict
            _TASK_CACHE["all"] = {}
    return _TASK_CACHE["all"]


def _task_states(prefixes) -> dict:
    """Enabled/disabled for this lane's tasks -- context, never the liveness verdict.

    A lane whose tasks are all Disabled is being HELD (quiet mode), which is a different
    thing from a lane that is broken, and J needs to tell those apart at a glance.
    """
    return {n: v for n, v in _all_tasks().items()
            if any(p.lower() in n.lower() for p in prefixes)}


def _held(tasks: dict) -> bool:
    return bool(tasks) and all(v == "Disabled" for v in tasks.values())


# --- lanes -----------------------------------------------------------------------------

def lane_kitchen() -> dict:
    p = STATE / "kitchen-status.json"
    d = _read(p) or {}
    age = _age_min(p)
    q = (d.get("queue_summary") or {}).get("by_status") or {}
    recent = d.get("recent_completed_top_10") or []
    tasks = _task_states(("Kitchen",))
    alive = bool(d.get("daemon_alive"))
    doing = (recent[0].get("task") or "")[:110] if recent else None
    spend = d.get("today_cost_usd_paid_tier")
    cap = d.get("today_cost_cap_usd")
    return {
        "id": "kitchen", "label": "Kitchen", "kind": "R&D",
        "state": "HELD" if _held(tasks) else _state_for("kitchen", age, broken=not alive),
        "detail": "{} pending, {} done all-time".format(
            q.get("pending", 0), q.get("completed", 0)),
        "doing": doing,
        "last_at": _iso(p),
        # Sourced or absent. `.get(key, 0)` printed a confident "$0.00 / $3" from a
        # kitchen-status file that had failed to load -- a fabricated dollar figure
        # sitting next to a BROKEN badge, which is the one thing this project's
        # no-invented-numbers law exists to prevent.
        "metric": ("${:.2f} / ${:.0f}".format(spend, cap)
                   if isinstance(spend, (int, float)) and isinstance(cap, (int, float))
                   else None),
        "metric_label": "spend today",
        "tasks": tasks,
    }


def lane_futures() -> dict:
    h = STATE / "futures" / "health.json"
    d = _read(h) or {}
    dec = STATE / "futures" / "decisions.jsonl"
    newest, age = _newest([h, dec])
    verdict = d.get("verdict")
    reds = [c for c in (d.get("checks") or []) if c.get("status") == "RED"]
    tasks = _task_states(("Futures",))
    return {
        "id": "futures", "label": "Futures", "kind": "MNQ/MES",
        "state": ("HELD" if _held(tasks)
                  else "BROKEN" if verdict == "RED"
                  else _state_for("futures", age)),
        "detail": (reds[0].get("detail", "")[:150] if reds
                   else "health {}".format(verdict or "unknown")),
        "doing": (reds[0].get("name") if reds else None),
        "last_at": _iso(newest),
        "metric": verdict or "?",
        "metric_label": "health",
        "tasks": tasks,
    }


def lane_multi() -> dict:
    d = STATE / "multi"
    casc = d / "participation-cascade.jsonl"
    syms = sorted(p.stem.replace("level-states-", "") for p in d.glob("level-states-*.json"))
    newest, age = _newest([casc] + list(d.glob("level-states-*.json")))
    last = (_tail(casc, 1) or [{}])[0]
    tasks = _task_states(("Multi",))
    uni, tier2 = last.get("funnel_universe"), last.get("tier2_symbols")
    return {
        "id": "multi", "label": "Multi-symbol", "kind": "non-SPY TA",
        "state": "HELD" if _held(tasks) else _state_for("multi", age),
        "detail": ("{} scanned -> {} tier-2".format(uni, tier2) if uni is not None
                   else "no cascade recorded"),
        "doing": (", ".join(syms) if syms else None),
        "last_at": _iso(newest),
        "metric": str(len(syms)),
        "metric_label": "symbols tracked",
        "tasks": tasks,
    }


def lane_prospector() -> dict:
    p = ROOT / "analysis" / "prospector" / "state.json"
    d = _read(p) or {}
    age = _age_min(p)
    tasks = _task_states(("Prospector",))
    return {
        "id": "prospector", "label": "Prospector", "kind": "idea hunt",
        "state": "HELD" if _held(tasks) else _state_for("prospector", age),
        "detail": "{} ideas, {} promoted, {} folded".format(
            d.get("ideas_total", 0), d.get("promoted_total", 0), d.get("folded_total", 0)),
        "doing": d.get("last_beat"),
        "last_at": _iso(p),
        "metric": str(d.get("fires_total", 0)),
        "metric_label": "fires",
        "tasks": tasks,
    }


def lane_spy() -> dict:
    """The live engine. Its pulse is the decision ledger, not a status file."""
    cands = [STATE / "decisions.jsonl", STATE / "current-position.json",
             STATE / "today-bias.json"]
    newest, age = _newest([c for c in cands if c.exists()])
    tasks = _task_states(("HeartbeatCore", "SightBeacon", "EodFlatten"))
    up = sum(1 for v in tasks.values() if v == "Ready")
    return {
        "id": "spy", "label": "SPY 0DTE core", "kind": "live engine",
        "state": _state_for("spy", age),
        "detail": ("market closed -- weekend" if dt.datetime.now(ET).weekday() >= 5
                   else "heartbeat cadence 1min 09:30-15:55 ET"),
        "doing": (newest.name if newest else None),
        "last_at": _iso(newest),
        "metric": "{}/{}".format(up, len(tasks)),
        "metric_label": "engine tasks up",
        "tasks": tasks,
    }


def build() -> dict:
    lanes = []
    for fn in (lane_spy, lane_kitchen, lane_futures, lane_multi, lane_prospector):
        try:
            lanes.append(fn())
        except Exception as exc:  # noqa: BLE001
            # A lane that cannot be read says so IN THE RAIL. Dropping the row would
            # quietly shrink the list and read as "this lane does not exist".
            lanes.append({"id": fn.__name__, "label": fn.__name__.replace("lane_", ""),
                          "state": "ERROR", "detail": str(exc)[:160],
                          "kind": "", "doing": None, "last_at": None,
                          "metric": "!", "metric_label": "read failed", "tasks": {}})
    return {"generated_at": dt.datetime.now(ET).isoformat(), "lanes": lanes}


if __name__ == "__main__":
    json.dump(build(), sys.stdout, indent=2, default=str)
