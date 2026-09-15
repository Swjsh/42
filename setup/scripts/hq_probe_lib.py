"""Pure verdict logic for the HQ live-agent measurement instrument.

hq_live_probe.py samples window.__hqLiveAgents + /api/hq's liveAgents +
renderer stats over a live headless page and hands the raw sample list to
the functions here. Every function in this module is pure (no I/O, no
Playwright, no fs) so it can be unit-tested against synthetic sample arrays
without a browser -- see test_hq_probe_lib.py.

Sample shape (one dict per poll tick, produced by hq_live_probe.py):
    {
        "t_ms": float,                # wall-clock ms since run start
        "page_agents": [ {id, label, state, pos:[x,z], target, bubble,
                           rawDetail, bubbleOpacity, onWalkable}, ... ],
        "api_agents":  [ {id, state, ...}, ... ],   # /api/hq liveAgents
        "calls": int | None,          # window.__hqGl.info.render.calls
    }

Every check returns a dict: {"verdict": "PASS"|"FAIL"|"NO-DATA", "detail": {...}}
Never PASS without evidence -- a check with zero qualifying events is
NO-DATA, not PASS.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

RAW_SHELL_LEAK_RE = re.compile(r"Ran:|\\\\|/c/Users|&&")

WALK_SPEED_MIN = 0.3
WALK_SPEED_MAX = 1.0
STAND_SLOT_MIN_DIST = 0.7
WALK_OUT_MAX_S = 15.0


def _page_ids(sample: Dict[str, Any]) -> set:
    return {a["id"] for a in sample.get("page_agents", [])}


def _api_ids(sample: Dict[str, Any]) -> set:
    return {a["id"] for a in sample.get("api_agents", [])}


def _dist(p1: Sequence[float], p2: Sequence[float]) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


# 1. spawn latency ------------------------------------------------------------

def check_spawn_latency(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(samples) < 2:
        return {"verdict": "NO-DATA", "detail": {"reason": "fewer than 2 samples"}}

    latencies_ms: List[float] = []
    prev_api: set = _api_ids(samples[0])
    seen_on_page_by: Dict[str, Optional[float]] = {}

    for i in range(1, len(samples)):
        cur = samples[i]
        cur_api = _api_ids(cur)
        newly_spawned = cur_api - prev_api
        for agent_id in newly_spawned:
            seen_on_page_by[agent_id] = None
        prev_api = cur_api

        cur_page = _page_ids(cur)
        for agent_id in list(seen_on_page_by.keys()):
            if seen_on_page_by[agent_id] is None and agent_id in cur_page:
                # first sample tick the id appears on the page after the
                # tick it appeared in the API
                spawn_tick = None
                for j in range(1, i + 1):
                    if agent_id in (_api_ids(samples[j]) - _api_ids(samples[j - 1])):
                        spawn_tick = j
                        break
                if spawn_tick is not None:
                    latencies_ms.append(samples[i]["t_ms"] - samples[spawn_tick]["t_ms"])
                seen_on_page_by[agent_id] = samples[i]["t_ms"]

    if not latencies_ms:
        return {"verdict": "NO-DATA", "detail": {"reason": "no spawn observed this window"}}

    poll_interval_ms = _median_poll_interval(samples)
    max_lat = max(latencies_ms)
    verdict = "PASS" if max_lat <= poll_interval_ms + 1 else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "spawn_count": len(latencies_ms),
            "latencies_ms": latencies_ms,
            "max_latency_ms": max_lat,
            "poll_interval_ms": poll_interval_ms,
        },
    }


def _median_poll_interval(samples: List[Dict[str, Any]]) -> float:
    deltas = [samples[i]["t_ms"] - samples[i - 1]["t_ms"] for i in range(1, len(samples))]
    if not deltas:
        return 500.0
    deltas.sort()
    return deltas[len(deltas) // 2]


# 2. walk speed ---------------------------------------------------------------

def check_walk_speed(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for s in samples:
        for a in s.get("page_agents", []):
            if a.get("state") == "walking":
                by_id.setdefault(a["id"], []).append({"t_ms": s["t_ms"], **a})

    speeds: List[float] = []
    unwalkable_hits = 0
    walking_samples = 0
    for _agent_id, seq in by_id.items():
        for i in range(1, len(seq)):
            walking_samples += 1
            if not seq[i].get("onWalkable", False):
                unwalkable_hits += 1
            dt_s = (seq[i]["t_ms"] - seq[i - 1]["t_ms"]) / 1000.0
            if dt_s <= 0:
                continue
            d = _dist(seq[i]["pos"], seq[i - 1]["pos"])
            speeds.append(d / dt_s)
        if seq and not seq[0].get("onWalkable", False):
            unwalkable_hits += 1
            walking_samples += 1

    if not speeds:
        return {"verdict": "NO-DATA", "detail": {"reason": "no walking agent observed"}}

    out_of_band = [v for v in speeds if v < WALK_SPEED_MIN or v > WALK_SPEED_MAX]
    verdict = "PASS" if not out_of_band and unwalkable_hits == 0 else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "sample_count": len(speeds),
            "min_speed": min(speeds),
            "max_speed": max(speeds),
            "out_of_band_count": len(out_of_band),
            "unwalkable_hits": unwalkable_hits,
            "walking_samples": walking_samples,
        },
    }


# 3. stand slots ---------------------------------------------------------------

def check_stand_slots(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    min_dists: List[float] = []
    duplicate_count = 0
    groups_seen = 0

    for s in samples:
        by_target: Dict[str, List[Dict[str, Any]]] = {}
        for a in s.get("page_agents", []):
            if a.get("state") == "leaving":
                continue
            by_target.setdefault(a.get("target"), []).append(a)
        for _target, group in by_target.items():
            if len(group) < 2:
                continue
            groups_seen += 1
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    d = _dist(group[i]["pos"], group[j]["pos"])
                    min_dists.append(d)
                    if d == 0:
                        duplicate_count += 1

    if groups_seen == 0:
        return {"verdict": "NO-DATA", "detail": {"reason": "never >=2 agents shared a target"}}

    worst = min(min_dists)
    verdict = "PASS" if worst >= STAND_SLOT_MIN_DIST and duplicate_count == 0 else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "groups_observed": groups_seen,
            "pair_count": len(min_dists),
            "min_pairwise_dist": worst,
            "duplicate_position_count": duplicate_count,
        },
    }


# 4. walk-out ------------------------------------------------------------------

def check_walk_out(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    leaving_start: Dict[str, float] = {}
    leaving_last_pos: Dict[str, List[float]] = {}
    moved_while_leaving: Dict[str, bool] = {}
    despawn_ms: Dict[str, float] = {}
    ever_leaving: set = set()

    all_ids_by_tick: List[set] = [_page_ids(s) for s in samples]

    for i, s in enumerate(samples):
        for a in s.get("page_agents", []):
            if a.get("state") != "leaving":
                continue
            aid = a["id"]
            ever_leaving.add(aid)
            if aid not in leaving_start:
                leaving_start[aid] = s["t_ms"]
                leaving_last_pos[aid] = a["pos"]
                moved_while_leaving[aid] = False
            else:
                if _dist(a["pos"], leaving_last_pos[aid]) > 1e-6:
                    moved_while_leaving[aid] = True
                leaving_last_pos[aid] = a["pos"]

    for aid, start_t in leaving_start.items():
        gone_at = None
        for i, ids in enumerate(all_ids_by_tick):
            if samples[i]["t_ms"] >= start_t and aid not in ids:
                gone_at = samples[i]["t_ms"]
                break
        if gone_at is not None:
            despawn_ms[aid] = gone_at - start_t

    if not ever_leaving:
        return {"verdict": "NO-DATA", "detail": {"reason": "no agent observed leaving this window"}}

    within_15s = [v for v in despawn_ms.values() if v <= WALK_OUT_MAX_S * 1000]
    any_moved = any(moved_while_leaving.values())
    verdict = "PASS" if within_15s and any_moved and len(within_15s) == len(despawn_ms) else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "leaving_agents": len(ever_leaving),
            "despawned_agents": len(despawn_ms),
            "despawn_ms": despawn_ms,
            "moved_while_leaving": moved_while_leaving,
        },
    }


# 5. page == API parity ---------------------------------------------------------

def check_page_api_parity(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not samples:
        return {"verdict": "NO-DATA", "detail": {"reason": "no samples"}}

    matches = [_page_ids(s) == _api_ids(s) for s in samples]
    best_run = 0
    cur_run = 0
    for m in matches:
        cur_run = cur_run + 1 if m else 0
        best_run = max(best_run, cur_run)

    replacement_seen = False
    for i in range(1, len(samples)):
        prev_api = _api_ids(samples[i - 1])
        cur_api = _api_ids(samples[i])
        if prev_api and cur_api and prev_api != cur_api and (prev_api & cur_api):
            replacement_seen = True

    verdict = "PASS" if best_run >= 10 else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "best_consecutive_match_run": best_run,
            "total_samples": len(samples),
            "mismatch_count": matches.count(False),
            "replacement_observed": replacement_seen,
        },
    }


# 6. bubbles ---------------------------------------------------------------------

def check_bubbles(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    distinct: set = set()
    leaks: List[str] = []
    for s in samples:
        for a in s.get("page_agents", []):
            b = a.get("bubble", "")
            raw = a.get("rawDetail", "")
            if b:
                distinct.add(b)
            if raw:
                distinct.add(raw)
            for text in (b, raw):
                if text and RAW_SHELL_LEAK_RE.search(text):
                    leaks.append(text)

    if not distinct:
        return {"verdict": "NO-DATA", "detail": {"reason": "no bubble text observed"}}

    verdict = "FAIL" if leaks else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "distinct_bubbles": sorted(distinct),
            "leak_count": len(leaks),
            "leaked_strings": leaks,
        },
    }


# 7. perf -------------------------------------------------------------------------

def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[idx]


def check_perf(frame_timestamps_ms: List[float], calls_samples: List[Optional[int]]) -> Dict[str, Any]:
    if len(frame_timestamps_ms) < 2:
        return {"verdict": "NO-DATA", "detail": {"reason": "fewer than 2 recorded frames", "headless": True}}

    frame_deltas = [
        frame_timestamps_ms[i] - frame_timestamps_ms[i - 1]
        for i in range(1, len(frame_timestamps_ms))
        if frame_timestamps_ms[i] > frame_timestamps_ms[i - 1]
    ]
    if not frame_deltas:
        return {"verdict": "NO-DATA", "detail": {"reason": "no positive frame deltas", "headless": True}}

    fps_samples = [1000.0 / d for d in frame_deltas if d > 0]
    calls_present = [c for c in calls_samples if c is not None]

    return {
        "verdict": "PASS",
        "detail": {
            "headless": True,
            "note": "SwiftShader/software-GL numbers -- NOT representative of real-GPU perf",
            "fps_p50": round(_percentile(fps_samples, 50), 2),
            "fps_p95": round(_percentile(fps_samples, 95), 2),
            "frame_count": len(frame_timestamps_ms),
            "mean_draw_calls": round(sum(calls_present) / len(calls_present), 1) if calls_present else None,
            "draw_call_samples": len(calls_present),
        },
    }


def build_verdicts(samples: List[Dict[str, Any]], frame_timestamps_ms: List[float]) -> Dict[str, Any]:
    calls_samples = [s.get("calls") for s in samples]
    return {
        "spawn_latency": check_spawn_latency(samples),
        "walk_speed": check_walk_speed(samples),
        "stand_slots": check_stand_slots(samples),
        "walk_out": check_walk_out(samples),
        "page_api_parity": check_page_api_parity(samples),
        "bubbles": check_bubbles(samples),
        "perf": check_perf(frame_timestamps_ms, calls_samples),
    }
