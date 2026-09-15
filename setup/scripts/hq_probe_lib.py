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

Every check returns a dict: {"verdict": "PASS"|"FAIL"|"NO-DATA"|"INFO", "detail": {...}}
Never PASS without evidence -- a check with zero qualifying events is
NO-DATA, not PASS. INFO is perf-only: headless/SwiftShader numbers with no
PASS/FAIL threshold (see check_perf).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

RAW_SHELL_LEAK_RE = re.compile(r"Ran:|\\\\|/c/Users|&&")

# dashboard/components/hq/KitAgent.tsx:85 sets WALK_SPEED = 0.7 u/s -- this
# is the design speed check_walk_speed judges the STEADY walking/leaving
# pace against (not a fixed band). +/-15% default tolerance.
WALK_SPEED_DEFAULT = 0.7
WALK_SPEED_TOL_DEFAULT = 0.15
STAND_SLOT_MIN_DIST = 0.7
WALK_OUT_MAX_S = 15.0

# Below this measured fps, position samples update in jumps rather than
# smooth motion (headless SwiftShader fps_p50 0.71 was the observed
# 2026-09-14/09-15 case: 143/150 walk_speed samples read as out-of-band, a
# measurement artifact of the renderer, not a real speed bug). Any motion
# check (walk_speed, stand_slots, walk_out) is unjudgeable below this rate
# and must report NO-DATA rather than PASS/FAIL.
MOTION_MIN_FPS_P50 = 20.0

# check_spawn_latency must judge against the PAGE's real data-refresh
# cadence, not the probe's own sample tick. dashboard/app/hq/page.tsx:34
# sets `refreshMs = kiosk ? 60_000 : 15_000` for its SWR poll of /api/hq --
# that is when a spawned agent can actually first appear on the page. The
# probe's own --interval-ms sample tick (reported separately as
# sample_tick_ms) is unrelated and must never be used as the PASS/FAIL bar
# (2026-09-15 bug: a 499.8ms sample tick judged 7.5-12.5s spawn latencies as
# FAIL against a 15s page that was working correctly).
PAGE_REFRESH_MS_DEFAULT = 15_000
PAGE_REFRESH_MS_KIOSK = 60_000
# Render/observation slack added on top of the page's refresh interval
# before a spawn is judged late.
SPAWN_LATENCY_RENDER_SLACK_MS = 2_000

_KIOSK_QS_RE = re.compile(r"[?&]kiosk=1(?:&|$)")


def page_refresh_ms_from_url(url: Optional[str]) -> int:
    """Derives the page's real SWR refresh interval from the probe URL --
    kiosk=1 in the query string means dashboard/app/hq/page.tsx:34 used the
    60s branch, otherwise the 15s branch. Callers may still override this
    explicitly (see --page-refresh-ms in hq_live_probe.py) for a page whose
    refreshMs has changed since this comment was written."""
    if url and _KIOSK_QS_RE.search(url):
        return PAGE_REFRESH_MS_KIOSK
    return PAGE_REFRESH_MS_DEFAULT


def _page_ids(sample: Dict[str, Any]) -> set:
    return {a["id"] for a in sample.get("page_agents", [])}


def _api_ids(sample: Dict[str, Any]) -> set:
    return {a["id"] for a in sample.get("api_agents", [])}


def _dist(p1: Sequence[float], p2: Sequence[float]) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


# 1. spawn latency ------------------------------------------------------------

def check_spawn_latency(
    samples: List[Dict[str, Any]],
    page_refresh_ms: int = PAGE_REFRESH_MS_DEFAULT,
) -> Dict[str, Any]:
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

    sample_tick_ms = _median_sample_tick(samples)
    max_lat = max(latencies_ms)
    threshold_ms = page_refresh_ms + SPAWN_LATENCY_RENDER_SLACK_MS
    verdict = "PASS" if max_lat <= threshold_ms else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "spawn_count": len(latencies_ms),
            "latencies_ms": latencies_ms,
            "max_latency_ms": max_lat,
            "page_refresh_ms": page_refresh_ms,
            "slack_ms": SPAWN_LATENCY_RENDER_SLACK_MS,
            # The probe's own --interval-ms sample tick -- NOT the judging
            # threshold. Reported for diagnostics only.
            "sample_tick_ms": sample_tick_ms,
        },
    }


def _median_sample_tick(samples: List[Dict[str, Any]]) -> float:
    deltas = [samples[i]["t_ms"] - samples[i - 1]["t_ms"] for i in range(1, len(samples))]
    if not deltas:
        return 500.0
    deltas.sort()
    return deltas[len(deltas) // 2]


# 2. walk speed ---------------------------------------------------------------

# States in which an agent is actually in transit. A tick where either side
# of a pair is NOT one of these (arrival into 'working', departure out of
# it) captures a partial in-tick move, not the steady walking pace, and must
# be excluded from speed measurement -- the 2026-09-14/09-15 case's 6 LOW
# anomalies (0.047-0.258 u/s) were every one of them exactly such a
# transition tick, not a real speed bug.
WALKING_STATES = {"walking", "leaving"}

# WALK-SPEED-DIAG (coordinator, 2026-09-15 ~04:05 ET): dashboard/components/
# hq/LiveAgents.tsx:136-139 publishes window.__hqLiveAgents on a 250ms
# setInterval while the probe samples every ~500ms -- each RAW tick-to-tick
# displacement is therefore quantized to 1/2/3 diag updates (0.35/0.70/1.05
# u/s at the true 0.7 u/s design speed), a false FAIL on tick-level speed
# alone (run 20260915T074839Z-gZsuTUlH: min 0.337, max 1.021, out_of_band_frac
# 0.2293 -- a measurement artifact, not a real speed bug). Measuring over
# windows >= SPEED_WINDOW_S_DEFAULT averages the 250ms quantization out
# while still catching a genuinely wrong pace (a true 1.02 u/s walk still
# fails the windowed median) -- teleports are caught separately, per-tick,
# below, since a window would just average a real teleport away too.
SPEED_WINDOW_S_DEFAULT = 2.0

# Teleport detection is independent of windowing -- any single tick-to-tick
# displacement beyond what the maximum 250ms-quantization error could
# explain is a real placement bug (the 2cb12e5c-era bug shape: an 8.75u jump
# in 0.48s), not an aliasing artifact. threshold = design_speed * dt_s *
# slack + pos_slack -- the *slack term covers normal jitter around the
# nominal dt, the +pos_slack term covers the up-to-one-diag-tick quantization
# error a window smooths but a single tick-pair can't.
TELEPORT_DT_SLACK = 1.05
TELEPORT_POS_SLACK_U = 0.3

# A gap between consecutive resolved timestamps this much larger than the
# run's own median tick interval means the probe missed ticks (browser
# hiccup, GC pause, CDP round-trip stall) -- a window must not bridge across
# it, same as it must not bridge across a state transition.
GAP_MULTIPLIER = 3.0
GAP_MIN_S = 1.0

# Regression sanity check alongside the windowed medians: the WHOLE-RUN
# average speed per agent (total path / total time, across all continuous
# walking/leaving ticks) must also sit within this fraction of design_speed.
# Reported in the detail dict; does not independently gate PASS/FAIL (the
# windowed median + out-of-band-frac + teleport_count do that) but flags a
# run where windowing alone looks fine yet the whole-path number disagrees.
AVG_SPEED_REGRESSION_TOL = 0.05


def _resolved_t_ms(s: Dict[str, Any]) -> Tuple[float, bool]:
    """Resolves a sample tick's timestamp for speed/teleport measurement.
    Prefers the in-page `performance.now()` captured in the SAME
    page.evaluate() call as window.__hqLiveAgents (sample field
    'page_t_ms') over the Python wall-clock time the CDP round-trip
    finished ('t_ms'/'host_t_ms'): the round-trip itself has 0.198-0.808s
    jitter that has nothing to do with true agent speed (WALK-SPEED-DIAG,
    coordinator 2026-09-15 -- a full reconstructed walk measured 22.52u in
    32.02s = 0.703 u/s once page-side timing replaced host timing). Falls
    back to 't_ms' (host) for samples files captured before page_t_ms
    existed -- second return value is True when that fallback was used."""
    page_t = s.get("page_t_ms")
    if page_t is not None:
        return float(page_t), False
    return float(s["t_ms"]), True


def _median_dt_s(samples: List[Dict[str, Any]]) -> float:
    """Median tick-to-tick interval across the whole run (resolved
    timestamps), used as the reference interval for gap detection. Falls
    back to the nominal 0.5s probe tick when there's nothing to measure."""
    deltas: List[float] = []
    prev: Optional[float] = None
    for s in samples:
        t, _ = _resolved_t_ms(s)
        if prev is not None and t > prev:
            deltas.append((t - prev) / 1000.0)
        prev = t
    if not deltas:
        return 0.5
    deltas.sort()
    return deltas[len(deltas) // 2]


def check_walk_speed(
    samples: List[Dict[str, Any]],
    design_speed: float = WALK_SPEED_DEFAULT,
    tol: float = WALK_SPEED_TOL_DEFAULT,
    speed_window_s: float = SPEED_WINDOW_S_DEFAULT,
) -> Dict[str, Any]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    used_host_fallback = False
    for s in samples:
        t_ms, is_host = _resolved_t_ms(s)
        used_host_fallback = used_host_fallback or is_host
        for a in s.get("page_agents", []):
            by_id.setdefault(a["id"], []).append({"t_ms": t_ms, **a})

    median_dt_s = _median_dt_s(samples)
    gap_threshold_s = max(GAP_MULTIPLIER * median_dt_s, GAP_MIN_S)

    window_speeds_by_agent: Dict[str, List[float]] = {}
    avg_speed_by_agent: Dict[str, float] = {}
    unwalkable_hits = 0
    walking_samples = 0
    teleport_events: List[Dict[str, Any]] = []

    for agent_id, seq in by_id.items():
        # Unwalkable hits are a real placement bug regardless of transition
        # state -- counted on every tick the agent is in transit, not just
        # ticks that also qualify for a speed sample.
        for a in seq:
            if a.get("state") in WALKING_STATES:
                walking_samples += 1
                if not a.get("onWalkable", False):
                    unwalkable_hits += 1

        # Accumulate displacement/time into windows of >= speed_window_s,
        # only across pairs of ticks that are BOTH walking/leaving (no state
        # transition) and not separated by a sampling gap. This is what
        # averages the 250ms-publish/500ms-sample quantization out: a tick
        # that hasn't visually moved yet (0 dist) or one that jumped 2-3
        # diag updates at once both just contribute their real
        # distance/time to the running window sum instead of being scored
        # individually.
        cum_dist = 0.0
        cum_time = 0.0
        total_dist = 0.0
        total_time = 0.0

        for i in range(1, len(seq)):
            cur, prev = seq[i], seq[i - 1]
            dt_s = (cur["t_ms"] - prev["t_ms"]) / 1000.0
            both_walking = cur.get("state") in WALKING_STATES and prev.get("state") in WALKING_STATES
            if not both_walking or dt_s <= 0 or dt_s > gap_threshold_s:
                # transition tick or sampling gap -- flush whatever window
                # was accumulating (discarded if still short of
                # speed_window_s) and start clean on the other side.
                cum_dist = 0.0
                cum_time = 0.0
                continue

            d = _dist(cur["pos"], prev["pos"])

            # Teleport detection -- strict, per-tick, independent of
            # windowing. A displacement beyond the max quantization error
            # is a real placement bug and always FAILs the run.
            threshold = design_speed * dt_s * TELEPORT_DT_SLACK + TELEPORT_POS_SLACK_U
            if d > threshold:
                teleport_events.append({
                    "agent_id": agent_id,
                    "t_ms": cur["t_ms"],
                    "distance": round(d, 4),
                    "dt_s": round(dt_s, 4),
                    "threshold": round(threshold, 4),
                })
                # A teleport corrupts whatever window it landed in -- don't
                # blend it into a speed reading, just drop the window.
                cum_dist = 0.0
                cum_time = 0.0
                continue

            cum_dist += d
            cum_time += dt_s
            total_dist += d
            total_time += dt_s
            if cum_time >= speed_window_s:
                window_speeds_by_agent.setdefault(agent_id, []).append(cum_dist / cum_time)
                cum_dist = 0.0
                cum_time = 0.0
            # else: keep accumulating -- a trailing partial window shorter
            # than speed_window_s at the end of a run is simply discarded
            # (never flushed, since it never reaches the >= check above).

        if total_time > 0:
            avg_speed_by_agent[agent_id] = total_dist / total_time

    teleport_count = len(teleport_events)
    all_window_speeds = [v for vs in window_speeds_by_agent.values() for v in vs]

    if not all_window_speeds and teleport_count == 0 and unwalkable_hits == 0:
        return {
            "verdict": "NO-DATA",
            "detail": {"reason": f"no walking/leaving window >= {speed_window_s:.1f}s observed"},
        }

    # Judge the steady pace against the CONFIGURED design speed, not a fixed
    # band: median windowed speed per agent must sit within design +/- tol;
    # a window is "out of band" (diagnostic, capped at 5% of windows) at
    # double that tolerance so normal window-to-window jitter doesn't itself
    # fail the run.
    band_lo, band_hi = design_speed * (1 - tol * 2), design_speed * (1 + tol * 2)
    out_of_band = [v for v in all_window_speeds if v < band_lo or v > band_hi]
    out_of_band_frac = (len(out_of_band) / len(all_window_speeds)) if all_window_speeds else 0.0

    median_lo, median_hi = design_speed * (1 - tol), design_speed * (1 + tol)
    median_speed_by_agent = {aid: _percentile(vs, 50) for aid, vs in window_speeds_by_agent.items()}
    medians_in_band = bool(median_speed_by_agent) and all(
        median_lo <= m <= median_hi for m in median_speed_by_agent.values()
    )

    regression_lo = design_speed * (1 - AVG_SPEED_REGRESSION_TOL)
    regression_hi = design_speed * (1 + AVG_SPEED_REGRESSION_TOL)
    avg_speed_regression_ok = bool(avg_speed_by_agent) and all(
        regression_lo <= v <= regression_hi for v in avg_speed_by_agent.values()
    )

    verdict = "PASS" if (
        medians_in_band
        and unwalkable_hits == 0
        and out_of_band_frac <= 0.05
        and teleport_count == 0
    ) else "FAIL"
    return {
        "verdict": verdict,
        "detail": {
            "window_count": len(all_window_speeds),
            "speed_window_s": speed_window_s,
            "min_speed": min(all_window_speeds) if all_window_speeds else None,
            "max_speed": max(all_window_speeds) if all_window_speeds else None,
            "out_of_band_count": len(out_of_band),
            "out_of_band_frac": round(out_of_band_frac, 4),
            "unwalkable_hits": unwalkable_hits,
            "walking_samples": walking_samples,
            "design_speed": design_speed,
            "tol": tol,
            "median_speed_by_agent": {k: round(v, 4) for k, v in median_speed_by_agent.items()},
            "avg_speed_by_agent": {k: round(v, 4) for k, v in avg_speed_by_agent.items()},
            "avg_speed_regression_ok": avg_speed_regression_ok,
            "teleport_count": teleport_count,
            "teleport_events": teleport_events,
            "timestamp_source": "host" if used_host_fallback else "page",
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
            # Only agents actually settled at a slot ("working") are judged
            # for slot spacing -- a walking/leaving agent mid-step toward or
            # away from the same target is not a slot-collision, it's transit
            # (the 2026-09-14/09-15 stand_slots FAIL at min pairwise 0.28u was
            # unjudgeable for exactly this reason: walking agents mid-step
            # were being counted alongside settled ones).
            if a.get("state") != "working":
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

# An agent still "leaving" when the sampling window ends is ambiguous, not
# broken -- the window may simply have closed on it mid-walk. Only call it
# a FAIL once it has been leaving for at least this long without despawning;
# below that it's NO-DATA (the window just didn't run long enough to judge
# this particular agent).
WALK_OUT_WINDOW_END_GRACE_S = 20.0


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

    window_end_ms = samples[-1]["t_ms"] if samples else 0.0

    per_agent: Dict[str, Dict[str, Any]] = {}
    for aid, start_t in leaving_start.items():
        moved = moved_while_leaving.get(aid, False)
        # Offset of this agent's leave-start relative to the END of the
        # sampling window -- how much window was left to observe it in.
        leave_started_offset_s = (window_end_ms - start_t) / 1000.0
        if aid in despawn_ms:
            dur_ms = despawn_ms[aid]
            status = "PASS" if (dur_ms <= WALK_OUT_MAX_S * 1000 and moved) else "FAIL"
        elif leave_started_offset_s < WALK_OUT_WINDOW_END_GRACE_S:
            # Started leaving too close to the window's end to judge --
            # this is a probe-window artifact, not evidence of a stuck agent.
            status = "NO-DATA"
        else:
            status = "FAIL"
        per_agent[aid] = {
            "status": status,
            "despawn_ms": despawn_ms.get(aid),
            "moved_while_leaving": moved,
            "leave_started_offset_s": leave_started_offset_s,
        }

    statuses = [v["status"] for v in per_agent.values()]
    if any(v == "FAIL" for v in statuses):
        verdict = "FAIL"
    elif all(v == "NO-DATA" for v in statuses):
        verdict = "NO-DATA"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "detail": {
            "leaving_agents": len(ever_leaving),
            "despawned_agents": len(despawn_ms),
            "despawn_ms": despawn_ms,
            "moved_while_leaving": moved_while_leaving,
            "per_agent": per_agent,
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

# Matches the target of a "reading <target>" / "editing <target>" bubble so
# we can sanity-check it. rawDetail is deliberately RAW (kept for debugging
# only) -- it must never feed the leak scan or the junk-target scan; only
# `bubble` (what's actually rendered on screen) is judged.
BUBBLE_TARGET_RE = re.compile(r"\b(?:reading|editing)\s+(\S+)", re.IGNORECASE)
JUNK_TARGET_CHARS_RE = re.compile(r'[|<>"]')
ANY_ALNUM_RE = re.compile(r"[A-Za-z0-9]")


def _is_junk_target(target: str) -> bool:
    """A target is junk if it has no alphanumeric content at all, or
    contains characters that can never legitimately appear in a filename
    ('working · reading |<Htm' was the observed 2026-09-14 artifact)."""
    if not ANY_ALNUM_RE.search(target):
        return True
    if JUNK_TARGET_CHARS_RE.search(target):
        return True
    return False


def check_bubbles(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    distinct_bubbles: set = set()
    raw_detail_samples: set = set()
    leaks: List[str] = []
    junk_targets: List[Dict[str, str]] = []

    for s in samples:
        for a in s.get("page_agents", []):
            b = a.get("bubble", "")
            raw = a.get("rawDetail", "")
            if raw:
                raw_detail_samples.add(raw)
            if not b:
                continue
            distinct_bubbles.add(b)
            if RAW_SHELL_LEAK_RE.search(b):
                leaks.append(b)
            m = BUBBLE_TARGET_RE.search(b)
            if m and _is_junk_target(m.group(1)):
                junk_targets.append({"bubble": b, "target": m.group(1)})

    if not distinct_bubbles:
        return {
            "verdict": "NO-DATA",
            "detail": {
                "reason": "no bubble text observed",
                "raw_detail_samples": sorted(raw_detail_samples),
            },
        }

    verdict = "FAIL" if (leaks or junk_targets) else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "distinct_bubbles": sorted(distinct_bubbles),
            "leak_count": len(leaks),
            "leaked_strings": leaks,
            "junk_target_count": len(junk_targets),
            "junk_targets": junk_targets,
            # informational only -- rawDetail is deliberately raw (debug
            # field) and never judged for leaks/junk.
            "raw_detail_samples": sorted(raw_detail_samples),
        },
    }


# 7. perf -------------------------------------------------------------------------

def perf_headless_flag(environment: Dict[str, Any]) -> "tuple[Optional[bool], Optional[str]]":
    """The SINGLE source of truth for whether perf numbers came from software
    GL (SwiftShader) or real hardware GL. Driven ONLY by the recorded
    gl_is_hardware field -- never by environment's own 'headless' key (that
    key is always literal True: Playwright always launches headless=True: a
    "no visible window" fact, unrelated to which GL backend rendered the
    frames). Both hq_live_probe.py's live path and its --rescore path must
    call this exact function so they can never compute two different
    verdicts from the same recorded environment (2026-09-15 bug: live used
    `not gl_is_hardware`, rescore used the meaningless `headless` literal --
    rescore reported perf INFO/SwiftShader on a run that was live-verified
    PASS on real NVIDIA hardware).

    Returns (is_software_gl, no_data_reason):
      - gl_is_hardware recorded -> (not gl_is_hardware, None)
      - gl_is_hardware missing (samples file predates this field) ->
        (None, "gl backend not recorded") -- caller must NEVER default this
        to True/False; check_perf treats None as NO-DATA.
    """
    if "gl_is_hardware" not in environment or environment.get("gl_is_hardware") is None:
        return None, "gl backend not recorded"
    return (not bool(environment["gl_is_hardware"])), None


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[idx]


# Real-GPU (non-headless) perf thresholds. There is NO threshold in headless/
# SwiftShader mode -- software rasterizer numbers (fps_p50 0.71 was one
# observed 2026-09-14 sample) don't mean anything relative to a real GPU, so
# headless perf is reported as INFO with the numbers attached, never PASS/FAIL.
PERF_FPS_P50_MIN = 58.0
PERF_P95_FRAME_MS_MAX = 17.0


def check_perf(
    frame_timestamps_ms: List[float],
    calls_samples: List[Optional[int]],
    scene_ready: bool = True,
    headless: Optional[bool] = True,
) -> Dict[str, Any]:
    """Verdict shape depends on environment:
      - headless/SwiftShader (software GL -- see perf_headless_flag): verdict
        is NO-DATA while there's genuinely no data (scene not ready, too few
        frames, no draw-call samples), otherwise INFO -- headless numbers
        carry no PASS/FAIL threshold, they're for trend-watching only.
      - real GPU (headless=False): NO-DATA for the same missing-data cases,
        otherwise PASS only if fps_p50 >= 58, p95 frame time <= 17ms, AND
        draw calls were sampled; FAIL otherwise.
      - headless=None (the gl backend was never recorded -- an older
        samples.json.gz predating gl_is_hardware): always NO-DATA, never
        INFO or PASS -- there is no basis to label the numbers either way.
    Never PASS in headless mode -- that was the 2026-09-14 false-PASS bug
    (fps_p50 0.71 on SwiftShader read as a passing perf number). Callers
    (both the live path and --rescore) must derive `headless` from
    perf_headless_flag(environment), never from environment's own literal
    'headless' key -- see that function's docstring for why."""
    if headless is None:
        return {
            "verdict": "NO-DATA",
            "detail": {"reason": "gl backend not recorded", "headless": None, "label": "UNKNOWN"},
        }
    label = "HEADLESS" if headless else "GPU"
    if not scene_ready:
        return {
            "verdict": "NO-DATA",
            "detail": {"reason": "scene_ready is false -- no real render loop to measure", "headless": headless, "label": label},
        }
    if len(frame_timestamps_ms) < 2:
        return {"verdict": "NO-DATA", "detail": {"reason": "fewer than 2 recorded frames", "headless": headless, "label": label}}

    frame_deltas = [
        frame_timestamps_ms[i] - frame_timestamps_ms[i - 1]
        for i in range(1, len(frame_timestamps_ms))
        if frame_timestamps_ms[i] > frame_timestamps_ms[i - 1]
    ]
    if not frame_deltas:
        return {"verdict": "NO-DATA", "detail": {"reason": "no positive frame deltas", "headless": headless, "label": label}}

    fps_samples = [1000.0 / d for d in frame_deltas if d > 0]
    calls_present = [c for c in calls_samples if c is not None]
    fps_p50 = round(_percentile(fps_samples, 50), 2)
    fps_p95 = round(_percentile(fps_samples, 95), 2)
    p95_frame_time_ms = round(_percentile(frame_deltas, 95), 2)

    if not calls_present:
        return {
            "verdict": "NO-DATA",
            "detail": {
                "reason": "frames were measured but zero draw-call samples were taken (window.__hqGl never populated)",
                "headless": headless,
                "label": label,
                "fps_p50": fps_p50,
                "fps_p95": fps_p95,
                "p95_frame_time_ms": p95_frame_time_ms,
                "frame_count": len(frame_timestamps_ms),
            },
        }

    detail: Dict[str, Any] = {
        "headless": headless,
        "label": label,
        "fps_p50": fps_p50,
        "fps_p95": fps_p95,
        "p95_frame_time_ms": p95_frame_time_ms,
        "frame_count": len(frame_timestamps_ms),
        "mean_draw_calls": round(sum(calls_present) / len(calls_present), 1),
        "draw_call_samples": len(calls_present),
    }

    if headless:
        detail["note"] = (
            "SwiftShader/software-GL numbers -- NOT representative of real-GPU perf; "
            "no PASS/FAIL threshold applies in headless mode, numbers are informational only"
        )
        return {"verdict": "INFO", "detail": detail}

    meets_threshold = (
        fps_p50 >= PERF_FPS_P50_MIN
        and p95_frame_time_ms <= PERF_P95_FRAME_MS_MAX
        and len(calls_present) > 0
    )
    return {"verdict": "PASS" if meets_threshold else "FAIL", "detail": detail}


# 8. run validity ---------------------------------------------------------------

def check_run_validity(build_ids: Sequence[Optional[str]], scene_ready: bool) -> Dict[str, Any]:
    """A run is INVALID (not FAIL -- there is no data to fail on) when the
    dashboard build changed out from under it (another builder's deploy
    rewrote dashboard/.next/BUILD_ID mid-run: deleted chunks, a restarting
    server, net::ERR_CONNECTION_REFUSED) or the scene never actually
    rendered. build_ids should carry the /api/hq build_id sampled at start,
    every ~30s, and at the end -- ANY drift among the non-null values means
    the page was talking to two different deploys during one run."""
    distinct = sorted({b for b in build_ids if b})
    build_changed = len(distinct) > 1
    reasons: List[str] = []
    if build_changed:
        reasons.append(f"build_id changed during run: {distinct}")
    if not scene_ready:
        reasons.append("scene_ready is false -- window.__hqLiveAgents/canvas/Standby-clear never satisfied within the wait window")
    return {"valid": not reasons, "reasons": reasons, "distinct_build_ids": distinct}


def _fps_p50_from_frames(frame_timestamps_ms: List[float]) -> Optional[float]:
    """Same fps_p50 math check_perf uses, exposed standalone so build_verdicts
    can gate the motion checks on it without duplicating check_perf's
    scene_ready/draw-call NO-DATA branches (which don't apply here -- this
    is purely "was the renderer fast enough to trust position deltas")."""
    if len(frame_timestamps_ms) < 2:
        return None
    frame_deltas = [
        frame_timestamps_ms[i] - frame_timestamps_ms[i - 1]
        for i in range(1, len(frame_timestamps_ms))
        if frame_timestamps_ms[i] > frame_timestamps_ms[i - 1]
    ]
    if not frame_deltas:
        return None
    fps_samples = [1000.0 / d for d in frame_deltas if d > 0]
    if not fps_samples:
        return None
    return round(_percentile(fps_samples, 50), 2)


def build_verdicts(
    samples: List[Dict[str, Any]],
    frame_timestamps_ms: List[float],
    calls_samples: Optional[List[Optional[int]]] = None,
    scene_ready: bool = True,
    build_ids: Optional[Sequence[Optional[str]]] = None,
    headless: Optional[bool] = True,
    url: Optional[str] = None,
    page_refresh_ms: Optional[int] = None,
    walk_speed: float = WALK_SPEED_DEFAULT,
    walk_speed_tol: float = WALK_SPEED_TOL_DEFAULT,
    speed_window_s: float = SPEED_WINDOW_S_DEFAULT,
) -> Dict[str, Any]:
    if calls_samples is None:
        calls_samples = [s.get("calls") for s in samples]
    build_ids = build_ids or []
    label = "UNKNOWN" if headless is None else ("HEADLESS" if headless else "GPU")
    # Explicit --page-refresh-ms wins; otherwise derive from the probe URL's
    # kiosk=1 query param (see page_refresh_ms_from_url docstring).
    effective_page_refresh_ms = (
        page_refresh_ms if page_refresh_ms is not None else page_refresh_ms_from_url(url)
    )

    run_check = check_run_validity(build_ids, scene_ready)
    if not run_check["valid"]:
        reason_str = "; ".join(run_check["reasons"])

        def _no_data() -> Dict[str, Any]:
            return {"verdict": "NO-DATA", "detail": {"reason": reason_str}}

        return {
            "run_valid": False,
            "invalid_reasons": run_check["reasons"],
            "spawn_latency": _no_data(),
            "walk_speed": _no_data(),
            "stand_slots": _no_data(),
            "walk_out": _no_data(),
            "page_api_parity": _no_data(),
            "bubbles": _no_data(),
            "perf": {
                "verdict": "NO-DATA",
                "detail": {"reason": reason_str, "headless": headless, "label": label},
            },
        }

    fps_p50 = _fps_p50_from_frames(frame_timestamps_ms)
    motion_gated = fps_p50 is not None and fps_p50 < MOTION_MIN_FPS_P50

    def _motion_no_data() -> Dict[str, Any]:
        return {
            "verdict": "NO-DATA",
            "detail": {
                "reason": f"fps too low for motion checks (<{MOTION_MIN_FPS_P50:.0f})",
                "fps_p50": fps_p50,
            },
        }

    return {
        "run_valid": True,
        "invalid_reasons": [],
        "spawn_latency": check_spawn_latency(samples, page_refresh_ms=effective_page_refresh_ms),
        "walk_speed": _motion_no_data() if motion_gated else check_walk_speed(
            samples, design_speed=walk_speed, tol=walk_speed_tol, speed_window_s=speed_window_s
        ),
        "stand_slots": _motion_no_data() if motion_gated else check_stand_slots(samples),
        "walk_out": _motion_no_data() if motion_gated else check_walk_out(samples),
        "page_api_parity": check_page_api_parity(samples),
        "bubbles": check_bubbles(samples),
        "perf": check_perf(frame_timestamps_ms, calls_samples, scene_ready=scene_ready, headless=headless),
    }
