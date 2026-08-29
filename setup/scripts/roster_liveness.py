"""roster_liveness.py — ping every lane in model-roster.json, write a health map.

Phase 0 deliverable (Plan B sec 3.2): the liveness probe that surfaces dead /
throttled / unkeyed lanes so the future auto-rotation (and J) know which lanes
are actually usable right now. REPORTS ONLY — does not mutate model-roster.json
(auto-demote of a 404'd id is a later, careful step).

    python setup/scripts/roster_liveness.py
Writes automation/state/roster-health.json + prints a one-line-per-lane summary.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm_client as sc  # noqa: E402

HEALTH_FILE = sc.REPO / "automation" / "state" / "roster-health.json"
STATUS_MD = sc.REPO / "automation" / "overnight" / "STATUS.md"
KNOWN_BROKEN_MARKER = "## Known broken"
PROBE_TIMEOUT_S = 8   # a 5-token "reply ok" ping answers in 1-3s; 8s = generous ceiling


def unique_lanes(roster: dict) -> list[dict]:
    seen: set = set()
    out: list[dict] = []
    for role in roster.get("roles", {}).values():
        for ln in role.get("lanes", []):
            k = (ln.get("provider"), ln.get("model"))
            if k not in seen:
                seen.add(k)
                out.append(ln)
    floor = roster.get("local_floor")
    if floor and (floor.get("provider"), floor.get("model")) not in seen:
        out.append({"provider": floor["provider"], "model": floor["model"]})
    return out


def probe(lane: dict, roster: dict) -> dict:
    env = sc._call_lane(lane, "ping", system="Reply with: ok",
                        max_tokens=5, temperature=0.0, timeout=PROBE_TIMEOUT_S,
                        task_id="liveness", roster=roster)
    err = (env.get("error") or "")
    klass = "live"
    if not env.get("ok"):
        if "401" in err or "Invalid API Key" in err or "no-key" in err.lower():
            klass = "no_key"
        elif "429" in err or "rate" in err.lower():
            klass = "throttled"
        elif "404" in err or "no endpoints" in err.lower():
            klass = "dead_id"
        else:
            klass = "error"
    return {"lane": sc._lane_key(lane), "ok": bool(env.get("ok")),
            "class": klass, "elapsed_s": env.get("elapsed_s"), "error": err[:140]}


NL = chr(10)


def flag_known_broken(dead: list[dict], status_md: Path = STATUS_MD) -> bool:
    """Surface permanently-dead lane ids on the STATUS Known-broken channel.

    WHY (2026-08-29 audit): this probe existed since Phase 0 but was MUTE -- it wrote
    roster-health.json and always exited 0. Its last run before tonight was 2026-07-01,
    and in that gap THREE lanes 404'd (llama-3.3-70b, qwen3-coder, cerebras zai-glm-4.7).
    coordinator's and coder's PRIMARY lanes were dead for ~2 months: gamma_manager's pick
    phase failed on every fire (content_head='', lanes_rejected=[]) and the free swarm's
    artifact output collapsed from 13 artifacts in Jun25-Jul08 to ~1/month. Nobody noticed
    because nothing read the JSON. A report nothing reads is not an instrument.

    Only class=dead_id is flagged: a 429 throttle self-heals, and crying wolf on transient
    throttles is how a Known-broken channel goes back to being ignored.
    """
    if not dead:
        return False
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return False
    ids = ", ".join(d["lane"] for d in dead)
    line = ("- [" + datetime.now(timezone.utc).isoformat(timespec="minutes") + "] "
            "ROSTER-LIVENESS: " + str(len(dead)) + " lane(s) permanently DEAD "
            "(404/archived): " + ids + ". Roles are falling through to their next lane or "
            "the local floor. Repoint in automation/state/model-roster.json, then re-run "
            "setup/scripts/roster_liveness.py. See automation/state/roster-health.json.")
    if KNOWN_BROKEN_MARKER not in text:
        text = KNOWN_BROKEN_MARKER + NL + NL + text
    head, _, tail = text.partition(KNOWN_BROKEN_MARKER + NL)
    status_md.write_text(
        head + KNOWN_BROKEN_MARKER + NL + NL + line + NL + tail.lstrip(NL),
        encoding="utf-8")
    return True


def main() -> int:
    roster = sc.load_roster()
    lanes = unique_lanes(roster)
    # Probe lanes concurrently — a hung/throttled lane no longer holds up the rest.
    with ThreadPoolExecutor(max_workers=min(len(lanes), 8)) as ex:
        results = list(ex.map(lambda ln: probe(ln, roster), lanes))
    live = [r for r in results if r["ok"]]
    health = {
        "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_lanes": len(lanes), "n_live": len(live), "lanes": results,
    }
    HEALTH_FILE.write_text(json.dumps(health, indent=2), encoding="utf-8")
    for r in results:
        tag = "LIVE" if r["ok"] else f"DOWN/{r['class']}"
        print(f"{tag:14} {r['lane']:48} {r.get('elapsed_s')}s  {r['error']}")
    print(f"\n{len(live)}/{len(lanes)} lanes live  ->  {HEALTH_FILE.relative_to(sc.REPO)}")
    dead = [r for r in results if r["class"] == "dead_id"]
    if flag_known_broken(dead):
        print(f"FLAGGED {len(dead)} dead lane(s) to STATUS.md Known broken")
    # Non-zero so Task Scheduler's LastTaskResult carries the signal too: a scheduled
    # probe that always exits 0 is indistinguishable from one that never ran.
    return 1 if dead else 0


if __name__ == "__main__":
    raise SystemExit(main())
