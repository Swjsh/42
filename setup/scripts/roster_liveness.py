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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
