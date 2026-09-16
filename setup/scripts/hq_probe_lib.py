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

# PROBE-16 addendum (coordinator, 2026-09-15): missed a real leak -- a
# live-agent hover tooltip (LiveAgents.tsx's `taskDetail`, NOT captured by
# this probe today -- see check_bubbles's own comment) showed
# `python "C:/Users/jackw/AppData/Local/Temp/claude/..."`, a drive-letter
# absolute path with FORWARD slashes and the username, neither of which
# the old pattern (backslash-only "/c/Users" mount-style path) caught.
# Widened with: [A-Za-z]:[\\/] (a drive letter followed by EITHER slash
# form -- "C:\" or "C:/"), /Users/ (mac/WSL-style absolute home, no drive
# letter), ~/ (shell home-shorthand), and the literal username "jackw" as
# a whole word in a path (case-insensitive -- scoped inline so it doesn't
# loosen the other alternatives). Kept narrow: a plain filename like
# "editing test_hq_probe_lib.py" or "editing hq-agents.ts" has no
# colon-slash, no /Users/, no ~/, and no "jackw" substring, so it still
# never matches.
RAW_SHELL_LEAK_RE = re.compile(r"Ran:|\\\\|/c/Users|&&|[A-Za-z]:[\\/]|/Users/|~/|(?i:\bjackw\b)")

# dashboard/components/hq/KitAgent.tsx:85 sets WALK_SPEED = 0.7 u/s -- this
# is the design speed check_walk_speed judges the STEADY walking/leaving
# pace against (not a fixed band). +/-15% default tolerance.
WALK_SPEED_DEFAULT = 0.7
WALK_SPEED_TOL_DEFAULT = 0.15
STAND_SLOT_MIN_DIST = 0.7
# PROBE-12 (coordinator, 2026-09-15, run
# 20260915T085943Z-Da6D81TEcI6kH8JvM85Db): `d == 0` missed a pair at
# 1.159e-15u apart -- float noise from position math, not a real distinct
# placement, but not bit-exact 0 either. Anything under this epsilon reads
# as the same point.
STAND_SLOT_DUPLICATE_EPS = 1e-3

# check_walker_separation's collision bar -- same 0.7u bar STAND_SLOT_MIN_DIST
# already uses for settled agents, applied to agents still in transit
# (walking/leaving) instead (PROBE-10, coordinator, 2026-09-15).
WALKER_MIN_DIST = 0.7
WALKER_SEPARATION_FAIL_FRAC = 0.10

# check_walk_out's PASS ceiling and despawn-location gate, derived from
# where commit 6249eaf3 (2026-09-15) actually moved live-agent spawn/despawn
# to -- a real "campus-gate" node, not the hub centre. The old fixed
# WALK_OUT_MAX_S = 15.0 predates that move and was never re-derived, so a
# correct 17-39s gate-to-desk walk (the graph's own worst-case is longer
# than 15s even before any margin) was scored as a FAIL (2026-09-15 live
# probe run 20260915T081521Z-BJcLqAlox0n-8xa5n5Kns: agent ac4b025b7106368d5
# despawned 0.30u from the gate after a correct 30.85s walk-out, FAILed only
# because 30.85 > 15).
#
# GATE_POS mirrors dashboard/components/hq/layout.ts:501
#   addNode("campus-gate", [ARM_LEN + PLAZA_APRON, 0, 0])
# at today's raw-kit dimensions ([21.6, 0, 0]); sample `pos` fields are
# [x, z] (see module docstring), so this is (x, z).
GATE_POS: Tuple[float, float] = (21.6, 0.0)

# The app's OWN hard despawn ceiling is derived per-graph, not a literal:
# dashboard/components/hq/liveAgentWalk.ts#computeMaxPathDurationS walks
# every graph node and returns the longest real walk-graph distance back to
# ENTRY_NODE_ID ("campus-gate"). That longest path is
# ambient-ideas-wall -> hub-center (5.8u, hypot(4.10, 4.10)) -> hub-door-0
# -> t-0 -> campus-gate (21.6u, ARM_LEN + PLAZA_APRON) = 27.4u total
# (dashboard/components/hq/Scene.tsx:396 "ideas-wall": [4.10, 0, 4.10]).
# LiveAgents.tsx then adds its own fixed LEAVE_TIMEOUT_MARGIN_S = 10
# (liveAgentWalk.ts:172) on top before force-despawning a stuck avatar.
_WALK_OUT_MAX_PATH_U = 27.4
_WALK_OUT_LEAVE_TIMEOUT_MARGIN_S = 10.0
# Probe-side slack on top of the app's own ceiling, for sample/poll
# granularity (the probe's own tick interval + CDP round-trip jitter --
# see _resolved_t_ms below), not a re-guess of the app's timeout.
_WALK_OUT_PROBE_SLACK_S = 2.0
WALK_OUT_MAX_S = (
    _WALK_OUT_MAX_PATH_U / WALK_SPEED_DEFAULT
    + _WALK_OUT_LEAVE_TIMEOUT_MARGIN_S
    + _WALK_OUT_PROBE_SLACK_S
)  # ~51.14s

# Despawn must also happen AT the gate, not mid-hallway -- an agent
# vanishing far from campus-gate is the teleport/ghost-despawn bug shape,
# not a slow-but-correct walk-out.
WALK_OUT_GATE_RADIUS = 1.0

# Diag-publish lag budget for per_agent's max_walk_between_last_seen_and_gone_u
# (coordinator note, 2nd 2026-09-15 GPU probe comparison across
# 20260915T081521Z and 20260915T082114Z runs -- despawn positions scatter
# around the gate: 0.94u short, 0.30u short, 0.79u PAST it). Diagnostic-only,
# does not gate PASS/FAIL -- see per_agent's own comment above.
WALK_OUT_DIAG_LAG_SLACK_U = 0.175

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
    # prev_api seeds from samples[0]'s own api_agents -- so any agent ALREADY
    # present when the page/probe first loaded is never in a later tick's
    # `newly_spawned` set below (coordinator note, 2026-09-15 2nd GPU probe:
    # every agent on both runs already existed at page-load, all appearing
    # together at [18.25, 0] mid-walk -- a page-load reconcile, not a live
    # spawn, and must not be judged as one here or in spawn_gate_by_agent).
    prev_api: set = _api_ids(samples[0])
    seen_on_page_by: Dict[str, Optional[float]] = {}
    # Detail-only, per commit 6249eaf3 (campus-gate spawn/despawn): first
    # observed page position + distance to GATE_POS for each spawned agent.
    # NOT folded into the PASS/FAIL verdict above -- doing that cleanly
    # needs the per-agent first-observation delay (WALK_SPEED * delay + a
    # position tolerance) budgeted against the SAME page_refresh_ms/slack
    # the latency check already uses, and that budget hasn't been derived
    #/verified against a live sample yet. Reported as diagnostic detail so
    # a spawn-at-the-wrong-place bug is still visible without risking a
    # false FAIL on a correct-but-conservative tolerance guess.
    spawn_gate_by_agent: Dict[str, Dict[str, Any]] = {}

    for i in range(1, len(samples)):
        cur = samples[i]
        cur_api = _api_ids(cur)
        newly_spawned = cur_api - prev_api
        for agent_id in newly_spawned:
            seen_on_page_by[agent_id] = None
        prev_api = cur_api

        cur_page = _page_ids(cur)
        cur_page_agents = {a["id"]: a for a in cur.get("page_agents", [])}
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
                first_pos = cur_page_agents.get(agent_id, {}).get("pos")
                spawn_gate_by_agent[agent_id] = {
                    "first_pos": first_pos,
                    "dist_to_gate": round(_dist(first_pos, GATE_POS), 4) if first_pos is not None else None,
                }

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
            # Detail-only gate-position report -- see comment above.
            "spawn_gate_by_agent": spawn_gate_by_agent,
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

# PROBE-16 (coordinator, 2026-09-15): check_walk_speed counted intentional
# stillness as slow walking. Run 20260915T130317Z had 521 "frozen"
# walking/leaving samples (pos unchanged tick-to-tick) that drove
# out_of_band_frac to 0.37 -- none of them a real motion bug
# (teleport_count 0, pose_jump 0 jumps): 308 during an actual HQ render
# PAUSE (the orchestrator's own Ollama burst made UltraCanvasRoot.tsx's
# `paused = gaming || hidden || brainBusy` true, commit 79ace8d4 --
# frameloop="never" while paused, so NOTHING moved, correctly), 152 are
# 'leaving' agents holding their CONVOY v4/v9 stagger wait (by design), the
# rest 1-tick diag-publish-cadence duplicates. "Not walking at all, on
# purpose or because rendering itself stopped" is not "walking too slowly".
#
# PAUSE signal (two, layered): frame_timestamps_ms (this run's own
# window.__probeRaf capture, RAF_HOOK_SCRIPT -- ALREADY recorded, no new
# field needed) is the PRIMARY signal -- it works retroactively on samples
# files captured before this fix existed (20260915T130317Z included). A
# gap > PAUSE_FRAME_GAP_MAX_S between consecutive GLOBAL
# requestAnimationFrame callbacks means nothing on the page called rAF for
# that long -- exactly what frameloop="never" produces, since r3f's Canvas
# is this page's only rAF scheduler. A more precise, forward-only
# per-sample signal is ALSO now captured when present (SAMPLE_SCRIPT's own
# 'paused' field, hq_live_probe.py) -- the exact boolean
# UltraCanvasRoot.tsx computes (mode==='gaming' || document.hidden ||
# runtime.brain.busy===true), read from the SAME /api/hq JSON SAMPLE_SCRIPT
# already fetches every tick (zero extra network cost). Used together --
# neither alone is authoritative on every samples file this function might
# see (a pre-fix file has no 'paused' field; a hypothetical page with some
# OTHER rAF consumer would blind the frame-gap signal alone).
PAUSE_FRAME_GAP_MAX_S = 1.0

# HOLD: a window/run of consecutive same-agent ticks with (near) zero
# displacement is intentional stillness (a CONVOY stagger wait, a
# follow-cap yield), not "walking at 0 u/s" -- excluded from the speed
# band entirely (counted as held_windows), never treated as a teleport.
# Epsilon, not bit-exact 0.0, for the same float-noise reason
# STAND_SLOT_DUPLICATE_EPS exists.
HOLD_ZERO_DISPLACEMENT_EPS = 1e-6
# A SINGLE continuous hold this long, while walking/leaving and NOT
# paused, has no known legitimate cause (the CONVOY stagger wait itself is
# only 1-1.5s) -- flagged as a POTENTIAL stuck agent, not auto-failed
# (unconfirmed cause), so a human/future check can investigate.
LONG_HOLD_THRESHOLD_S = 10.0


def _paused_frame_gaps(frame_timestamps_ms: Optional[Sequence[float]], gap_s: float = PAUSE_FRAME_GAP_MAX_S) -> List[Tuple[float, float]]:
    """Returns [(gap_start_ms, gap_end_ms), ...] for every >gap_s gap
    between consecutive (sorted) global requestAnimationFrame timestamps --
    see PAUSE_FRAME_GAP_MAX_S's own header for why a gap this large means
    the renderer was paused. Empty/None input (a samples file with no
    frame_timestamps_ms at all, or an in-process caller that never passed
    one) returns no gaps -- NOT the same as "never paused"; callers must
    treat that as "no pause signal available", not "no pause happened"."""
    if not frame_timestamps_ms or len(frame_timestamps_ms) < 2:
        return []
    ts = sorted(frame_timestamps_ms)
    gaps: List[Tuple[float, float]] = []
    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] > gap_s * 1000.0:
            gaps.append((ts[i - 1], ts[i]))
    return gaps


def _overlaps_any(t_start: float, t_end: float, intervals: List[Tuple[float, float]]) -> bool:
    for a, b in intervals:
        if t_start < b and t_end > a:
            return True
    return False


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
    frame_timestamps_ms: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    used_host_fallback = False
    for s in samples:
        t_ms, is_host = _resolved_t_ms(s)
        used_host_fallback = used_host_fallback or is_host
        for a in s.get("page_agents", []):
            # 'paused' is a SAMPLE-level field (SAMPLE_SCRIPT's own
            # runtime.brain.busy/gaming/document.hidden read) -- merged onto
            # every agent-tick record here purely for this function's own
            # per-pair convenience below. Absent (None) on samples files
            # captured before PROBE-16 -- _paused_frame_gaps is the signal
            # that still works there.
            by_id.setdefault(a["id"], []).append({"t_ms": t_ms, "paused": s.get("paused"), **a})

    median_dt_s = _median_dt_s(samples)
    gap_threshold_s = max(GAP_MULTIPLIER * median_dt_s, GAP_MIN_S)
    paused_intervals = _paused_frame_gaps(frame_timestamps_ms)

    window_speeds_by_agent: Dict[str, List[float]] = {}
    avg_speed_by_agent: Dict[str, float] = {}
    unwalkable_hits = 0
    walking_samples = 0
    teleport_events: List[Dict[str, Any]] = []
    paused_windows = 0
    held_windows = 0
    long_holds: List[Dict[str, Any]] = []

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
        window_paused = False
        total_dist = 0.0
        total_time = 0.0
        # PROBE-16 HOLD tracking -- a CONTINUOUS run of near-zero
        # displacement, independent of speed_window_s's own boundaries (a
        # 10s hold split across 5 two-second windows must still be caught
        # as one long hold, not five separately-innocuous ones).
        hold_start_t: Optional[float] = None
        hold_start_pos: Optional[List[float]] = None

        def _close_hold(end_t: float) -> None:
            nonlocal hold_start_t, hold_start_pos
            if hold_start_t is not None:
                duration = (end_t - hold_start_t) / 1000.0
                if duration >= LONG_HOLD_THRESHOLD_S:
                    long_holds.append({
                        "id": agent_id, "t": hold_start_t,
                        "duration": round(duration, 4), "pos": hold_start_pos,
                    })
            hold_start_t = None
            hold_start_pos = None

        for i in range(1, len(seq)):
            cur, prev = seq[i], seq[i - 1]
            dt_s = (cur["t_ms"] - prev["t_ms"]) / 1000.0
            both_walking = cur.get("state") in WALKING_STATES and prev.get("state") in WALKING_STATES
            pair_paused = bool(cur.get("paused")) or bool(prev.get("paused")) or _overlaps_any(prev["t_ms"], cur["t_ms"], paused_intervals)

            if not both_walking or dt_s <= 0 or dt_s > gap_threshold_s:
                # transition tick or sampling gap -- flush whatever window
                # was accumulating (discarded if still short of
                # speed_window_s) and start clean on the other side. Also
                # ends any open hold run -- a state change or sampling gap
                # is itself evidence the "hold" wasn't a stuck agent.
                _close_hold(prev["t_ms"])
                cum_dist = 0.0
                cum_time = 0.0
                window_paused = False
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
                # blend it into a speed reading, just drop the window. Also
                # ends any hold run WITHOUT flagging it long -- a jump away
                # from a hold is a placement bug already caught above, not
                # a separately-reportable stuck agent.
                hold_start_t, hold_start_pos = None, None
                cum_dist = 0.0
                cum_time = 0.0
                window_paused = False
                continue

            # HOLD: near-zero displacement while NOT paused is intentional
            # stillness (stagger wait / follow-cap yield) -- track the
            # continuous run for long_holds regardless of window boundaries.
            if d < HOLD_ZERO_DISPLACEMENT_EPS and not pair_paused:
                if hold_start_t is None:
                    hold_start_t, hold_start_pos = prev["t_ms"], prev["pos"]
            else:
                _close_hold(prev["t_ms"])

            if pair_paused:
                window_paused = True
            cum_dist += d
            cum_time += dt_s
            total_dist += d
            total_time += dt_s
            if cum_time >= speed_window_s:
                if window_paused:
                    # Render itself was stopped for some/all of this window
                    # -- not evidence of slow walking either way, excluded
                    # entirely (see PAUSE_FRAME_GAP_MAX_S's own header).
                    paused_windows += 1
                elif cum_dist < HOLD_ZERO_DISPLACEMENT_EPS:
                    # The WHOLE window never moved -- intentional stillness,
                    # not a "0 u/s" walking sample.
                    held_windows += 1
                else:
                    window_speeds_by_agent.setdefault(agent_id, []).append(cum_dist / cum_time)
                cum_dist = 0.0
                cum_time = 0.0
                window_paused = False
            # else: keep accumulating -- a trailing partial window shorter
            # than speed_window_s at the end of a run is simply discarded
            # (never flushed, since it never reaches the >= check above).

        if len(seq) > 0:
            _close_hold(seq[-1]["t_ms"])

        if total_time > 0:
            avg_speed_by_agent[agent_id] = total_dist / total_time

    teleport_count = len(teleport_events)
    all_window_speeds = [v for vs in window_speeds_by_agent.values() for v in vs]

    if not all_window_speeds and teleport_count == 0 and unwalkable_hits == 0:
        long_holds.sort(key=lambda h: -h["duration"])
        return {
            "verdict": "NO-DATA",
            "detail": {
                "reason": f"no walking/leaving window >= {speed_window_s:.1f}s observed",
                # PROBE-16: still reported here even though the run is
                # otherwise unjudged -- a NO-DATA verdict must never hide a
                # long_holds entry (a potential stuck agent) just because
                # nothing else was measurable this window.
                "measured_windows": 0,
                "paused_windows": paused_windows,
                "held_windows": held_windows,
                "long_holds": long_holds,
            },
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
    long_holds.sort(key=lambda h: -h["duration"])
    return {
        "verdict": verdict,
        "detail": {
            # PROBE-16: window_count/out_of_band_frac are already MEASURED-
            # windows-only (paused_windows/held_windows are excluded before
            # a window is ever appended to window_speeds_by_agent) --
            # measured_windows is the same number under the coordinator's
            # own requested name, so a reader never has to infer that from
            # window_count's own (unrenamed, for backward compat) meaning.
            "window_count": len(all_window_speeds),
            "measured_windows": len(all_window_speeds),
            "paused_windows": paused_windows,
            "held_windows": held_windows,
            "long_holds": long_holds,
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
    violating_groups = 0
    worst_pairs: List[Dict[str, Any]] = []

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
        for target, group in by_target.items():
            if len(group) < 2:
                continue
            groups_seen += 1
            group_violated = False
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    d = _dist(group[i]["pos"], group[j]["pos"])
                    min_dists.append(d)
                    # PROBE-12: epsilon, not bit-exact 0 -- see
                    # STAND_SLOT_DUPLICATE_EPS's own comment.
                    if d < STAND_SLOT_DUPLICATE_EPS:
                        duplicate_count += 1
                    if d < STAND_SLOT_MIN_DIST:
                        group_violated = True
                        worst_pairs.append({
                            "a_id": group[i]["id"],
                            "b_id": group[j]["id"],
                            "t_ms": s.get("t_ms"),
                            "a_pos": group[i]["pos"],
                            "b_pos": group[j]["pos"],
                            "target": target,
                            "dist": round(d, 6),
                        })
            if group_violated:
                violating_groups += 1

    if groups_seen == 0:
        return {"verdict": "NO-DATA", "detail": {"reason": "never >=2 agents shared a target"}}

    worst = min(min_dists)
    verdict = "PASS" if worst >= STAND_SLOT_MIN_DIST and duplicate_count == 0 else "FAIL"
    worst_pairs.sort(key=lambda p: p["dist"])
    return {
        "verdict": verdict,
        "detail": {
            "groups_observed": groups_seen,
            "pair_count": len(min_dists),
            "min_pairwise_dist": worst,
            "duplicate_position_count": duplicate_count,
            "violating_groups": violating_groups,
            "violating_frac": round(violating_groups / groups_seen, 4),
            "worst_pairs": worst_pairs[:5],
        },
    }


# 3b. walker separation ---------------------------------------------------------

# Companion to check_stand_slots: that check only judges agents SETTLED at a
# shared target ("working"); two agents still in transit (walking/leaving)
# can walk in lockstep, overlapping the whole way, and stand_slots never
# sees it because neither one ever reaches "working" while overlapped
# (PROBE-10, coordinator, 2026-09-15, run
# 20260915T084211Z-5rAPWKjf6d_SvYCYmRL3o: a93582c1 and ab416fc0 walked
# 0.01u apart for ~33s).
def check_walker_separation(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    multi_walker_ticks = 0
    violating_ticks = 0
    tick_min_dists: List[float] = []
    all_pairs: List[Dict[str, Any]] = []

    for s in samples:
        walkers = [a for a in s.get("page_agents", []) if a.get("state") in WALKING_STATES]
        if len(walkers) < 2:
            continue
        multi_walker_ticks += 1
        tick_min = None
        for i in range(len(walkers)):
            for j in range(i + 1, len(walkers)):
                d = _dist(walkers[i]["pos"], walkers[j]["pos"])
                if tick_min is None or d < tick_min:
                    tick_min = d
                all_pairs.append({
                    "a_id": walkers[i]["id"],
                    "b_id": walkers[j]["id"],
                    "t_ms": s.get("t_ms"),
                    "dist": round(d, 4),
                    "a_pos": walkers[i]["pos"],
                    "b_pos": walkers[j]["pos"],
                })
        tick_min_dists.append(tick_min)
        if tick_min < WALKER_MIN_DIST:
            violating_ticks += 1

    if multi_walker_ticks == 0:
        return {"verdict": "NO-DATA", "detail": {"reason": "no tick had >=2 walking/leaving agents"}}

    violating_frac = violating_ticks / multi_walker_ticks
    worst_pairs = sorted(all_pairs, key=lambda p: p["dist"])[:5]
    verdict = "FAIL" if violating_frac > WALKER_SEPARATION_FAIL_FRAC else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "multi_walker_ticks": multi_walker_ticks,
            "violating_ticks": violating_ticks,
            "violating_frac": round(violating_frac, 4),
            "min_pairwise_dist": round(min(tick_min_dists), 4),
            "worst_pairs": worst_pairs,
        },
    }


# 3c. waiting separation ---------------------------------------------------------

# PROBE-12 (coordinator, 2026-09-15, run
# 20260915T085943Z-Da6D81TEcI6kH8JvM85Db): a 3rd coverage gap alongside
# stand_slots ("working") and walker_separation (walking/leaving) --
# page_agents' own "spawning" state (CONVOY-STACK v2's lane-offset wait
# point, LiveAgents.tsx: an agent waiting for its stagger slot before it
# starts walking) was judged by NOTHING. Two agents sat at the identical
# point [21.65,0.45] for 4+ ticks around t=7.5s and no check flagged it. A
# SEPARATE check rather than folding into walker_separation (decision,
# per the coordinator's own "whichever is cleaner; state which"): a waiting
# agent is STATIONARY at a fixed wait point, not in transit -- coinciding
# there is a deterministic placement bug (same wait-point math handed to two
# agents), not walker_separation's own motion-sampling jitter case, so it
# gets its own strict zero-tolerance verdict instead of walker_separation's
# >10%-of-ticks allowance. Built to cover ANY state that is neither a
# walking state nor "working" (not just the literal string "spawning") so a
# future third non-transit, non-settled state -- "waiting" was the
# coordinator's own example -- is covered without another edit here.
WAITING_MIN_DIST = WALKER_MIN_DIST  # same 0.7u bar stand_slots/walker_separation already use


def _is_waiting_state(state: Optional[str]) -> bool:
    return state is not None and state not in WALKING_STATES and state != "working"


def check_waiting_separation(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    multi_waiting_ticks = 0
    violating_ticks = 0
    tick_min_dists: List[float] = []
    all_pairs: List[Dict[str, Any]] = []

    for s in samples:
        waiting = [a for a in s.get("page_agents", []) if _is_waiting_state(a.get("state"))]
        if len(waiting) < 2:
            continue
        multi_waiting_ticks += 1
        tick_min = None
        tick_violated = False
        for i in range(len(waiting)):
            for j in range(i + 1, len(waiting)):
                d = _dist(waiting[i]["pos"], waiting[j]["pos"])
                if tick_min is None or d < tick_min:
                    tick_min = d
                if d < WAITING_MIN_DIST:
                    tick_violated = True
                    all_pairs.append({
                        "a_id": waiting[i]["id"],
                        "b_id": waiting[j]["id"],
                        "t_ms": s.get("t_ms"),
                        "dist": round(d, 4),
                        "a_pos": waiting[i]["pos"],
                        "b_pos": waiting[j]["pos"],
                        "state": waiting[i].get("state"),
                    })
        tick_min_dists.append(tick_min)
        if tick_violated:
            violating_ticks += 1

    if multi_waiting_ticks == 0:
        return {"verdict": "NO-DATA", "detail": {"reason": "no tick had >=2 non-walking, non-working agents"}}

    violating_frac = violating_ticks / multi_waiting_ticks
    worst_pairs = sorted(all_pairs, key=lambda p: p["dist"])[:5]
    # Zero-tolerance: unlike walker_separation, ANY violating tick FAILs --
    # see this section's own header for why (stationary wait points, not
    # motion-sampling jitter).
    verdict = "FAIL" if violating_ticks > 0 else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "multi_waiting_ticks": multi_waiting_ticks,
            "violating_ticks": violating_ticks,
            "violating_frac": round(violating_frac, 4),
            "min_pairwise_dist": round(min(tick_min_dists), 4),
            "worst_pairs": worst_pairs,
        },
    }


# 3d. pose jump -------------------------------------------------------------------

# PROBE-15 (coordinator, 2026-09-15): check_walk_speed's own teleport
# detection (TELEPORT_DT_SLACK/TELEPORT_POS_SLACK_U) only looks at ticks
# where BOTH sides are a walking state (WALKING_STATES) -- by design, so a
# genuine state-transition tick's partial in-tick move never reads as a
# false teleport (see WALKING_STATES's own comment). That design choice
# has a real coverage gap, though: a RESTING ("working") agent snapping
# 0.9-1.1u between two slots -- never walking at all, so never even
# entering check_walk_speed's own windows -- goes completely unflagged.
# This check covers EVERY state (including transitions) for exactly that
# gap: same teleport-threshold shape check_walk_speed's own per-tick
# teleport detection uses (design_speed * dt * slack + pos_slack), applied
# to every consecutive same-agent pair regardless of state.
POSE_JUMP_DT_SLACK = 1.05
POSE_JUMP_POS_SLACK_U = 0.3
# A gap this large between consecutive resolved timestamps means the probe
# missed ticks (browser hiccup, GC pause, CDP stall) -- the agent may have
# legitimately walked across that gap, so it's excluded from judgment, not
# flagged as a jump (same "don't bridge a gap" discipline check_walk_speed's
# own GAP_MULTIPLIER/GAP_MIN_S already use, but pose_jump's gap threshold is
# a flat cap per the coordinator's own spec, not derived from the run's
# median tick interval -- this check has no windowing to protect).
POSE_JUMP_MAX_GAP_S = 2.0
POSE_JUMP_JUMPS_CAP = 10


def check_pose_jump(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    # last[(agent_id)] = (t_ms, pos, state) for the previous tick this
    # agent was observed on, in resolved-timestamp order.
    last: Dict[str, Tuple[float, List[float], Optional[str]]] = {}
    jumps: List[Dict[str, Any]] = []
    jumps_by_state: Dict[str, int] = {}
    comparisons = 0

    for s in samples:
        t_ms, _is_host = _resolved_t_ms(s)
        for a in s.get("page_agents", []):
            aid = a.get("id")
            pos = a.get("pos")
            state = a.get("state")
            if aid is None or pos is None:
                continue
            prev = last.get(aid)
            if prev is None:
                # First sample for this agent -- creation, not a jump (see
                # this check's own header: "exclude only an agent's FIRST
                # sample").
                last[aid] = (t_ms, pos, state)
                continue
            prev_t, prev_pos, prev_state = prev
            dt_s = (t_ms - prev_t) / 1000.0
            last[aid] = (t_ms, pos, state)
            if dt_s <= 0 or dt_s > POSE_JUMP_MAX_GAP_S:
                continue
            comparisons += 1
            d = _dist(pos, prev_pos)
            threshold = WALK_SPEED_DEFAULT * dt_s * POSE_JUMP_DT_SLACK + POSE_JUMP_POS_SLACK_U
            if d <= threshold:
                continue
            jumps_by_state[state] = jumps_by_state.get(state, 0) + 1
            jumps.append({
                "id": aid,
                "t": t_ms,
                "from_state": prev_state,
                "to_state": state,
                "from_pos": prev_pos,
                "to_pos": pos,
                "d": round(d, 4),
                "dt": round(dt_s, 4),
            })

    if comparisons == 0:
        return {"verdict": "NO-DATA", "detail": {"reason": "no agent had 2+ consecutive judgable samples this window"}}

    jump_count = len(jumps)
    jumps_sorted = sorted(jumps, key=lambda j: -j["d"])
    verdict = "FAIL" if jump_count > 0 else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "comparisons": comparisons,
            "jump_count": jump_count,
            "jumps": jumps_sorted[:POSE_JUMP_JUMPS_CAP],
            "jumps_by_state": jumps_by_state,
        },
    }


# 4. walk-out ------------------------------------------------------------------

# An agent still "leaving" when the sampling window ends is ambiguous, not
# broken -- the window may simply have closed on it mid-walk. Only call it
# a FAIL once it has been leaving for at least this long without despawning;
# below that it's NO-DATA (the window just didn't run long enough to judge
# this particular agent).
#
# Derived from WALK_OUT_MAX_S itself (coordinator, PROBE-10, 2026-09-15,
# run 20260915T084211Z-5rAPWKjf6d_SvYCYmRL3o): a fixed 20.0s grace was a
# stale literal from before the campus-gate move -- it FAILed agent
# a93582c12e2fad9ca, which started leaving 28.02s before the window ended,
# was moving, and was still correctly mid-walk (a hub->gate walk is ~31s,
# well inside the ~51.1s WALK_OUT_MAX_S ceiling). An agent that hasn't had
# the full WALK_OUT_MAX_S budget to complete its walk yet is unjudged, not
# broken -- NO-DATA, not FAIL.
WALK_OUT_WINDOW_END_GRACE_S = WALK_OUT_MAX_S


def check_walk_out(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    leaving_start: Dict[str, float] = {}
    leaving_last_pos: Dict[str, List[float]] = {}
    leaving_last_seen_t: Dict[str, float] = {}
    moved_while_leaving: Dict[str, bool] = {}
    despawn_ms: Dict[str, float] = {}
    gone_at_by_agent: Dict[str, float] = {}
    ever_leaving: set = set()

    # Resolve timestamps the same way check_walk_speed does -- prefer the
    # in-page page_t_ms over host t_ms (see _resolved_t_ms), so a walk-out
    # duration isn't inflated/deflated by CDP round-trip jitter that has
    # nothing to do with the agent's real walk time.
    resolved_t_ms = [_resolved_t_ms(s)[0] for s in samples]

    all_ids_by_tick: List[set] = [_page_ids(s) for s in samples]

    for i, s in enumerate(samples):
        for a in s.get("page_agents", []):
            if a.get("state") != "leaving":
                continue
            aid = a["id"]
            ever_leaving.add(aid)
            if aid not in leaving_start:
                leaving_start[aid] = resolved_t_ms[i]
                leaving_last_pos[aid] = a["pos"]
                moved_while_leaving[aid] = False
            else:
                if _dist(a["pos"], leaving_last_pos[aid]) > 1e-6:
                    moved_while_leaving[aid] = True
                leaving_last_pos[aid] = a["pos"]
            leaving_last_seen_t[aid] = resolved_t_ms[i]

    for aid, start_t in leaving_start.items():
        gone_at = None
        for i, ids in enumerate(all_ids_by_tick):
            if resolved_t_ms[i] >= start_t and aid not in ids:
                gone_at = resolved_t_ms[i]
                break
        if gone_at is not None:
            despawn_ms[aid] = gone_at - start_t
            gone_at_by_agent[aid] = gone_at

    if not ever_leaving:
        return {"verdict": "NO-DATA", "detail": {"reason": "no agent observed leaving this window"}}

    window_end_ms = resolved_t_ms[-1] if resolved_t_ms else 0.0

    per_agent: Dict[str, Dict[str, Any]] = {}
    for aid, start_t in leaving_start.items():
        moved = moved_while_leaving.get(aid, False)
        last_pos = leaving_last_pos.get(aid)
        dist_to_gate = _dist(last_pos, GATE_POS) if last_pos is not None else None
        despawned_at_gate = dist_to_gate is not None and dist_to_gate <= WALK_OUT_GATE_RADIUS
        # Offset of this agent's leave-start relative to the END of the
        # sampling window -- how much window was left to observe it in.
        leave_started_offset_s = (window_end_ms - start_t) / 1000.0
        if aid in despawn_ms:
            dur_ms = despawn_ms[aid]
            status = "PASS" if (
                dur_ms <= WALK_OUT_MAX_S * 1000 and moved and despawned_at_gate
            ) else "FAIL"
        elif leave_started_offset_s < WALK_OUT_WINDOW_END_GRACE_S:
            # Started leaving too close to the window's end to judge --
            # this is a probe-window artifact, not evidence of a stuck agent.
            status = "NO-DATA"
        else:
            status = "FAIL"
        # How far a correct walk COULD have moved in the gap between the
        # last observed "leaving" position and the tick it was confirmed
        # gone -- design_speed * gap_s + WALK_OUT_DIAG_LAG_SLACK_U (the
        # 250ms diag-publish lag a coordinator probe-run comparison flagged
        # 2026-09-15: LiveAgents.tsx publishes window.__hqLiveAgents on a
        # 250ms cadence, see WALK-SPEED-DIAG above, so the true despawn
        # position can sit up to one publish tick beyond the last SAMPLED
        # position even on a correct walk). Lets a reader judge whether a
        # last-seen-to-gate gap is normal sampling slack or a real jump,
        # without itself gating PASS/FAIL.
        gone_t = gone_at_by_agent.get(aid)
        last_seen_t = leaving_last_seen_t.get(aid)
        max_walk_u = None
        if gone_t is not None and last_seen_t is not None:
            gap_s = max(0.0, (gone_t - last_seen_t) / 1000.0)
            max_walk_u = round(WALK_SPEED_DEFAULT * gap_s + WALK_OUT_DIAG_LAG_SLACK_U, 4)
        per_agent[aid] = {
            "status": status,
            "despawn_ms": despawn_ms.get(aid),
            "moved_while_leaving": moved,
            "leave_started_offset_s": leave_started_offset_s,
            "last_pos": last_pos,
            "dist_to_gate": round(dist_to_gate, 4) if dist_to_gate is not None else None,
            "despawned_at_gate": despawned_at_gate,
            "max_walk_between_last_seen_and_gone_u": max_walk_u,
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
            "walk_out_max_s": round(WALK_OUT_MAX_S, 4),
            "gate_pos": GATE_POS,
            "gate_radius": WALK_OUT_GATE_RADIUS,
        },
    }


# 4b. speech-bubble overlap ------------------------------------------------------

# PROBE-11 (coordinator, 2026-09-15): a real-screen capture showed two
# live-agent bubbles drawn on top of each other and on the BRAIN/Gamma
# plaques at the hub, 35s after page load. A read-only diagnosis proved the
# pure resolver (dashboard/components/hq/labelDeclutter.ts#resolveLabelOffsets)
# already separates even exactly-coincident rects (its own test passes) --
# the fault is upstream (suspected: LabelDeclutterManager.tsx:139-142's
# natural-position back-calculation for MOVING near-coincident labels), but
# unconfirmed. This check measures first: only visible labels (opacity >=
# LABEL_OVERLAP_MIN_OPACITY, real area) count, and only a REAL geometric
# overlap (intersection area >= LABEL_OVERLAP_MIN_INTERSECTION_FRAC of the
# smaller rect) counts as a collision -- two labels merely close together is
# not what a screenshot reader would call "on top of each other".
LABEL_OVERLAP_MIN_OPACITY = 0.5
LABEL_OVERLAP_MIN_INTERSECTION_FRAC = 0.15
LABEL_OVERLAP_FAIL_FRAC = 0.05
LABEL_OVERLAP_WORST_PAIRS_CAP = 5

# PROBE-13 (coordinator, 2026-09-15): rescore of 20260915T090312Z showed
# label_overlap dominated by a FALSE-POSITIVE source -- HoloChart.tsx's
# LastPriceMarker ("760.78 · last close") also renders a `.hq-beam` box
# (fontSize 16, padding "3px 9px" -- HoloChart.tsx:531) but is NOT a
# declutter-registered label (no useLabelDeclutter call anywhere in that
# file); it measured 21.9x4.6px on screen. `.hq-beam` is confirmed NOT
# exclusive to labels (SAMPLE_SCRIPT's own comment), so a structural size
# rule is the fix: every REAL bubble/plaque this check has captured so far
# (LiveAgents.tsx fontSize 24 padding "3px 10px", Agent.tsx/
# GammaCharacter.tsx same, BrainCore.tsx's plaque) renders at >=21px tall
# once padding/line-height are included -- 20260915T090312Z's own captured
# rects: "Gamma · Nothing new." 130.1x21.2, "SPY 0DTE core..." 248.7x22.0,
# "general-purpose · wrapping up..." 300.8x22.1, "BRAIN · wrote brief..."
# 217.3x49.2 (2-line). The ticker plaque's 4.6px height is a full order of
# magnitude below the SHORTEST real label captured -- height is the
# discriminating dimension (the ticker plaque is comparably WIDE to a short
# real label, so a width-only cutoff would not separate them). Width stays
# a secondary floor only to reject degenerate/zero-ish rects, set well
# under the shortest real label's own width (130px) so it never excludes a
# real one. No ancestor-selector alternative exists: HoloChart's Html tree
# has no distinguishing class/attribute either (same `.hq-beam` convention
# every other file uses), so this is a size rule, not a container rule --
# stated per the coordinator's own "prefer a structural rule you can
# justify" instruction. KNOWN RESIDUAL: Scene.tsx's Pilot trade-action
# strip and StationModule.tsx's bay labels are also non-declutter-registered
# `.hq-beam` boxes at REAL-label-scale font sizes (16px+) -- this size rule
# does not exclude them, since no evidence yet shows them causing a false
# positive the way the ticker plaque did; revisit if a future rescore shows
# them dominating pair_counts the way the ticker plaque did here.
LABEL_MIN_HEIGHT_PX = 12.0
LABEL_MIN_WIDTH_PX = 40.0

# LEGIBILITY-FLOOR fix (2026-09-15): pinned to the SAME value as
# dashboard/components/hq/labelDeclutter.ts's own MIN_LEGIBLE_PX -- the
# runtime declutter resolver now fades any registered label below this
# height to CSS opacity 0 (never unmounted -- getBoundingClientRect() still
# reports its real, still-too-small height). A properly-faded label is
# INTENTIONALLY invisible; check_label_legibility below must not count it as
# a violation just because its DOM rect is still measurable -- that's
# exactly what LABEL_LEGIBILITY_MIN_OPACITY gates on.
LABEL_LEGIBILITY_MIN_OPACITY = 0.05


def _rect_area(r: Dict[str, Any]) -> float:
    return max(0.0, r.get("w", 0.0)) * max(0.0, r.get("h", 0.0))


def _rect_intersection_frac(r1: Dict[str, Any], r2: Dict[str, Any]) -> float:
    """Intersection area as a fraction of the SMALLER rect's own area (0 if
    disjoint or either rect has zero area) -- a small badge fully covered by
    a big plaque and a big plaque mostly covering a small badge should both
    read as a real collision, which a fraction-of-UNION metric would understate
    for the badge's own case."""
    x_left = max(r1.get("x", 0.0), r2.get("x", 0.0))
    y_top = max(r1.get("y", 0.0), r2.get("y", 0.0))
    x_right = min(r1.get("x", 0.0) + r1.get("w", 0.0), r2.get("x", 0.0) + r2.get("w", 0.0))
    y_bottom = min(r1.get("y", 0.0) + r1.get("h", 0.0), r2.get("y", 0.0) + r2.get("h", 0.0))
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
    inter_area = (x_right - x_left) * (y_bottom - y_top)
    smaller = min(_rect_area(r1), _rect_area(r2))
    if smaller <= 0:
        return 0.0
    return inter_area / smaller


def _live_agent_state_for_label(label: Dict[str, Any], page_agents: List[Dict[str, Any]]) -> Optional[str]:
    """Identifies whether a captured label rect IS a live-agent bubble, and
    if so that agent's current state -- by id prefix 'live:<agentId>' (the
    declutter id useLabelDeclutter.ts's LiveAgents.tsx call site uses) when
    the label's `id` field is populated, else by substring-matching the
    label's captured text against each live agent's own bubble string
    (SAMPLE_SCRIPT's own comment: no stable DOM hook exposes the id, so
    `id` is None from the live probe today -- this text-match path is the
    one actually exercised against real samples). Returns None when the
    label doesn't match any agent this tick (it's a persona/Gamma/plaque
    label, or a live agent that already despawned)."""
    label_id = label.get("id")
    text = label.get("text") or ""
    if label_id:
        for a in page_agents:
            if label_id == f"live:{a.get('id')}":
                return a.get("state")
        return None
    for a in page_agents:
        bubble = a.get("bubble") or a.get("rawDetail") or ""
        if bubble and text and bubble in text:
            return a.get("state")
    return None


def _is_label_sized(r: Dict[str, Any]) -> bool:
    """PROBE-13's size gate -- see LABEL_MIN_HEIGHT_PX's own header for the
    measured evidence behind the thresholds."""
    return r.get("h", 0.0) >= LABEL_MIN_HEIGHT_PX and r.get("w", 0.0) >= LABEL_MIN_WIDTH_PX


def _pair_key(text_a: Optional[str], text_b: Optional[str]) -> str:
    """Stable, order-independent key for detail.pair_counts -- collapses
    "A ~ B" and "B ~ A" ticks into one bucket so the dominant offending
    pair is visible without reprocessing. Newlines collapsed to spaces
    (captured `innerText` from a multi-line label carries them raw) so the
    key reads as one line in a JSON report."""
    a = (text_a or "").replace("\n", " ").strip()
    b = (text_b or "").replace("\n", " ").strip()
    return " ~ ".join(sorted([a, b]))


# PROBE-14 (coordinator, 2026-09-15): the >5%-of-ticks rule alone can't
# distinguish a genuinely persistent overlap (a viewer would definitely
# notice it) from scattered 1-tick blips (a single unlucky sample mid-
# declutter-resolve, well under the 5% bar). A run of >=3 CONSECUTIVE
# ticks that ALSO spans >=1.5s of wall-clock time is the "a viewer would
# see this" bar -- consecutive-tick count alone isn't enough on its own
# (a burst of very-fast ticks could hit 3 ticks in well under a second),
# so both conditions are required together.
LABEL_OVERLAP_PERSISTENT_MIN_TICKS = 3
LABEL_OVERLAP_PERSISTENT_MIN_S = 1.5


def _pair_runs_from_events(events: List[Tuple[int, float]]) -> List[Dict[str, Any]]:
    """`events` is (sample_index, t_ms) tuples for ONE pair, in the same
    order they occurred in `samples` (samples are already time-ordered).
    Splits into runs of CONSECUTIVE sample indices (a gap in sample_index
    -- the pair stopped overlapping for at least one tick -- ends a run,
    the same "don't bridge a gap" discipline check_walk_speed's own
    windowing already uses)."""
    runs: List[Dict[str, Any]] = []
    run_start_idx: Optional[int] = None
    run_start_t: Optional[float] = None
    prev_idx: Optional[int] = None
    prev_t: Optional[float] = None
    for idx, t in events:
        if prev_idx is not None and idx == prev_idx + 1:
            prev_idx, prev_t = idx, t
            continue
        if run_start_idx is not None:
            runs.append({
                "ticks": prev_idx - run_start_idx + 1,
                "start_t": run_start_t,
                "end_t": prev_t,
                "duration_s": round((prev_t - run_start_t) / 1000.0, 4),
            })
        run_start_idx, run_start_t = idx, t
        prev_idx, prev_t = idx, t
    if run_start_idx is not None:
        runs.append({
            "ticks": prev_idx - run_start_idx + 1,
            "start_t": run_start_t,
            "end_t": prev_t,
            "duration_s": round((prev_t - run_start_t) / 1000.0, 4),
        })
    return runs


def check_label_overlap(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    any_rects_captured = False
    ticks_with_2plus_visible = 0
    violating_ticks = 0
    excluded_count = 0
    all_pairs: List[Dict[str, Any]] = []
    pair_counts: Dict[str, int] = {}
    pair_events: Dict[str, List[Tuple[int, float]]] = {}
    pair_texts: Dict[str, List[Optional[str]]] = {}

    for sample_idx, s in enumerate(samples):
        rects = s.get("label_rects") or []
        if rects:
            any_rects_captured = True
        opacity_visible = [r for r in rects if (r.get("opacity") or 0) >= LABEL_OVERLAP_MIN_OPACITY and _rect_area(r) > 0]
        visible = [r for r in opacity_visible if _is_label_sized(r)]
        excluded_count += len(opacity_visible) - len(visible)
        if len(visible) < 2:
            continue
        ticks_with_2plus_visible += 1
        page_agents = s.get("page_agents", [])
        t_ms = s.get("t_ms")
        tick_has_live_violation = False
        for i in range(len(visible)):
            for j in range(i + 1, len(visible)):
                frac = _rect_intersection_frac(visible[i], visible[j])
                if frac < LABEL_OVERLAP_MIN_INTERSECTION_FRAC:
                    continue
                text_a, text_b = visible[i].get("text"), visible[j].get("text")
                key = _pair_key(text_a, text_b)
                pair_counts[key] = pair_counts.get(key, 0) + 1
                pair_events.setdefault(key, []).append((sample_idx, t_ms))
                pair_texts.setdefault(key, [text_a, text_b])
                state_a = _live_agent_state_for_label(visible[i], page_agents)
                state_b = _live_agent_state_for_label(visible[j], page_agents)
                involves_live_agent = state_a is not None or state_b is not None
                if involves_live_agent:
                    tick_has_live_violation = True
                all_pairs.append({
                    "t": t_ms,
                    "texts": [text_a, text_b],
                    "rects": [
                        {k: visible[i].get(k) for k in ("x", "y", "w", "h")},
                        {k: visible[j].get(k) for k in ("x", "y", "w", "h")},
                    ],
                    "overlap_frac": round(frac, 4),
                    "involves_live_agent": involves_live_agent,
                    # "walking" covers WALKING_STATES (walking/leaving);
                    # any other page_agents state (working/spawning) reads
                    # as settled. None means that side of the pair didn't
                    # match a live agent at all (persona/Gamma/plaque).
                    "live_agent_states": [state_a, state_b],
                })
        if tick_has_live_violation:
            violating_ticks += 1

    if not any_rects_captured:
        return {
            "verdict": "NO-DATA",
            "detail": {"reason": "no label rects captured this run (older samples file, or the '.hq-beam' DOM hook found nothing)"},
        }
    if ticks_with_2plus_visible == 0:
        return {
            "verdict": "NO-DATA",
            "detail": {
                "reason": "never >=2 visible (opacity >= {:.1f}, label-sized) labels captured in the same tick".format(LABEL_OVERLAP_MIN_OPACITY),
                "excluded_count": excluded_count,
            },
        }

    violating_frac = violating_ticks / ticks_with_2plus_visible
    live_pairs = [p for p in all_pairs if p["involves_live_agent"]]
    worst_pairs = sorted(live_pairs or all_pairs, key=lambda p: -p["overlap_frac"])[:LABEL_OVERLAP_WORST_PAIRS_CAP]

    # PROBE-14: per-pair run analysis -- ticks (== pair_counts' own value),
    # segments (how many separate consecutive-tick runs), and the LONGEST
    # run by both tick-count and wall-clock duration.
    pair_runs: Dict[str, Dict[str, Any]] = {}
    persistent_pairs: List[Dict[str, Any]] = []
    overall_max_run_s = 0.0
    for key, events in pair_events.items():
        runs = _pair_runs_from_events(events)
        max_run_ticks = max((r["ticks"] for r in runs), default=0)
        max_run_s = max((r["duration_s"] for r in runs), default=0.0)
        overall_max_run_s = max(overall_max_run_s, max_run_s)
        pair_runs[key] = {
            "ticks": pair_counts[key],
            "segments": len(runs),
            "max_run_ticks": max_run_ticks,
            "max_run_s": round(max_run_s, 4),
        }
        for r in runs:
            if r["ticks"] >= LABEL_OVERLAP_PERSISTENT_MIN_TICKS and r["duration_s"] >= LABEL_OVERLAP_PERSISTENT_MIN_S:
                persistent_pairs.append({
                    "pair": key,
                    "texts": pair_texts.get(key),
                    "ticks": r["ticks"],
                    "duration_s": r["duration_s"],
                    "start_t": r["start_t"],
                    "end_t": r["end_t"],
                })

    # Sorted descending so the dominant offending pair is first without the
    # reader re-sorting a JSON dict themselves.
    sorted_pair_counts = dict(sorted(pair_counts.items(), key=lambda kv: -kv[1]))
    sorted_pair_runs = dict(sorted(pair_runs.items(), key=lambda kv: -kv[1]["max_run_s"]))
    persistent_pairs.sort(key=lambda p: -p["duration_s"])

    # Existing >5%-of-ticks rule OR a persistent (>=3 consecutive ticks AND
    # >=1.5s) overlap on ANY pair -- either alone is a real FAIL, not just
    # additive noise (see this section's own PROBE-14 header).
    verdict = "FAIL" if (violating_frac > LABEL_OVERLAP_FAIL_FRAC or persistent_pairs) else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "ticks": ticks_with_2plus_visible,
            "violating_ticks": violating_ticks,
            "violating_frac": round(violating_frac, 4),
            "worst_pairs": worst_pairs,
            # PROBE-13: text-pair -> tick count, across ALL intersecting
            # pairs (not only ones involving a live agent) -- surfaces the
            # dominant offender (e.g. a persona/persona pair) without
            # reprocessing raw samples.
            "pair_counts": sorted_pair_counts,
            # Rects that passed the opacity/area gate but were dropped by
            # the LABEL_MIN_HEIGHT_PX/LABEL_MIN_WIDTH_PX size gate (e.g.
            # HoloChart's ticker plaque) -- see that constant's own header.
            "excluded_count": excluded_count,
            # PROBE-14: per-pair run shape -- distinguishes a persistent
            # stuck overlap from scattered 1-tick blips.
            "pair_runs": sorted_pair_runs,
            "max_run_s": round(overall_max_run_s, 4),
            "persistent_pairs": persistent_pairs,
        },
    }


# 4b. label legibility (SCENE-AUDIT pass, 2026-09-15) ---------------------------
# "would a human accept this room" rubric item 4 (markdown/doctrine/
# FRONTEND-OPS.md's "HQ scene acceptance" section, appended 2026-09-15):
# unreadable text at the viewing distance is a FAIL, not merely "present".
# Reuses the SAME `.hq-beam` DOM rects SAMPLE_SCRIPT already captures for
# check_label_overlap above -- zero new capture cost, and the SAME
# LABEL_MIN_HEIGHT_PX (12px) that function already uses to gate "is this
# rect big enough to be a real label" (never introduces a second, slightly
# different magic number for what is functionally the same "too small to
# read" judgment).


def check_label_legibility(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """FAILs any visible `.hq-beam` label/plaque rendered under
    LABEL_MIN_HEIGHT_PX tall AND not already faded below
    LABEL_LEGIBILITY_MIN_OPACITY by the runtime declutter resolver (a label
    the resolver already hid for being too small is a handled case, not an
    unaddressed one -- see LABEL_LEGIBILITY_MIN_OPACITY's own header).
    NO-DATA if the run never captured a single visible label (camera too
    far, no agents/labels this run) -- never a false PASS on zero evidence,
    same discipline every other check_* in this module already follows.
    Screen-face/label overlap (a label's rect intersecting a screen's own
    projected rect) is now its own separate check -- see
    check_label_screen_overlap below / hq-scene-audit.ts#checkLabelScreenOverlap."""
    visible_heights: List[float] = []
    violations: List[Dict[str, Any]] = []
    faded_count = 0
    for s in samples:
        rects = s.get("label_rects") or []
        for r in rects:
            if not r.get("visible", True):
                continue
            h = r.get("h") or 0.0
            if h <= 0:
                continue
            # LEGIBILITY-FLOOR fix: a label the runtime declutter resolver
            # already faded to ~0 opacity (labelDeclutter.ts's own
            # MIN_LEGIBLE_PX floor, same threshold as LABEL_MIN_HEIGHT_PX
            # below) is INTENTIONALLY hidden, not an unaddressed violation --
            # opacity defaults to 1.0 for elements this capture never read a
            # computed style from (older samples / non-declutter labels),
            # so this can only ever EXCLUDE a rect, never manufacture a
            # false PASS for one that was never faded.
            opacity = r.get("opacity")
            if opacity is not None and opacity < LABEL_LEGIBILITY_MIN_OPACITY:
                faded_count += 1
                continue
            visible_heights.append(h)
            if h < LABEL_MIN_HEIGHT_PX:
                violations.append({"text": r.get("text"), "height_px": round(h, 2)})
    if not visible_heights:
        return {"verdict": "NO-DATA", "detail": {"reason": "no visible labels sampled this run"}}
    verdict = "FAIL" if violations else "PASS"
    return {
        "verdict": verdict,
        "detail": {
            "sampled": len(visible_heights),
            "min_height_px": LABEL_MIN_HEIGHT_PX,
            "violation_count": len(violations),
            "violations": violations[:20],
            "faded_excluded_count": faded_count,
            "note": "label-vs-screen-face overlap is now a separate check (label_vs_screen_overlap) -- see hq-scene-audit.ts#checkLabelScreenOverlap",
        },
    }


# LABEL_VS_SCREEN_OVERLAP_MAX_FRAC pinned to the SAME 10% default
# dashboard/lib/hq-scene-audit.ts#checkLabelScreenOverlap uses -- one
# threshold, two enforcement points (mirrors LABEL_MIN_HEIGHT_PX's own
# already-established "same number on both sides" discipline for
# label_legibility above).
LABEL_VS_SCREEN_OVERLAP_MAX_FRAC = 0.1


def _rect_overlap_fraction_of_screen(label: Dict[str, Any], screen: Dict[str, Any]) -> float:
    """Fraction of `screen`'s own area covered by its intersection with
    `label` -- mirrors hq-scene-audit.ts#rectOverlapFractionOfScreen exactly
    (same "tiny local duplication over a cross-file/cross-language
    dependency" convention this codebase already uses -- see e.g.
    TwinMonitors.tsx/DeskScreen.tsx's own duplicated etStamp()). Both rects
    share the SAME 2D viewport-pixel space (top-left x/y), label as
    {x,y,w,h} (this probe's own `.hq-beam` capture convention) and screen as
    {x,y,width,height} (hq-scene-audit.ts's own ScreenViewportRect field
    names, passed through verbatim from window.__hqSceneAudit())."""
    screen_area = screen.get("width", 0.0) * screen.get("height", 0.0)
    if screen_area <= 0:
        return 0.0
    lx, ly, lw, lh = label.get("x", 0.0), label.get("y", 0.0), label.get("w", 0.0), label.get("h", 0.0)
    sx, sy, sw, sh = screen["x"], screen["y"], screen["width"], screen["height"]
    ix0, iy0 = max(lx, sx), max(ly, sy)
    ix1, iy1 = min(lx + lw, sx + sw), min(ly + lh, sy + sh)
    iw, ih = ix1 - ix0, iy1 - iy0
    if iw <= 0 or ih <= 0:
        return 0.0
    return (iw * ih) / screen_area


# 4c. label-vs-screen-face overlap (SCREEN-KEEP-OUT pass, 2026-09-15) -----------
# The sub-check check_label_legibility's own earlier docstring named as a
# stated follow-up ("no cheap 3D->DOM projection this pass"). Now possible
# because hq-scene-audit.ts's own computeSceneAuditReport projects every
# tagged screen face's world AABB through the LIVE camera into the SAME
# viewport-pixel space this probe's `.hq-beam` DOM capture already uses
# (window.__hqSceneAudit()'s own `screenViewportRects` field) -- this
# function just combines the two, over every sampled tick, the same
# "accumulate over the run" shape check_label_overlap above already uses.


def check_label_screen_overlap(samples: List[Dict[str, Any]], screen_rects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """FAILs any tick where a visible, opacity>=LABEL_LEGIBILITY_MIN_OPACITY
    label's rect covers more than LABEL_VS_SCREEN_OVERLAP_MAX_FRAC of a
    READABLE screen's own projected rect (informational screens -- desk
    monitors, bay signs -- are reported but never gate this verdict, same
    convention screen_facing already uses). NO-DATA if no screens were
    captured this run (e.g. TwinMonitors not yet mounted / ?diag=1 missing)
    or no labels were ever sampled -- never a false PASS on zero evidence.

    PER-TICK SCREEN FIX (2026-09-16, root cause: under a MOVING camera --
    the real full-probe run, which does not pass `?tour=0` -- a screen's
    PROJECTED viewport rect moves every tick right along with the camera,
    even though its world geometry is static. `screen_rects` used to be one
    snapshot taken before the whole label-sampling loop ran, so a label
    captured many ticks later was being checked against a screen position
    from a different, earlier camera pose -- comparing two ticks that were
    never simultaneous. Each `samples[i]` may now carry its OWN
    `screen_rects` (hq_live_probe.py's own per-tick
    `window.__hqSceneAuditScreens()` call, same tick as that sample's
    `label_rects`) -- when present and non-empty, THAT tick's own screens
    are used instead of the caller-supplied global `screen_rects`, so every
    comparison is same-tick. Falls back to the global list for a sample
    with no `screen_rects` key (older *.samples.json.gz captured before
    this fix, or a per-tick eval that failed) -- never a false NO-DATA/PASS
    from a single dropped tick when the rest of the run has real per-tick
    data."""
    if not screen_rects and not any(s.get("screen_rects") for s in samples):
        return {"verdict": "NO-DATA", "detail": {"reason": "no screens captured this run (window.__hqSceneAudit()/__hqSceneAuditScreens() returned none)"}}

    fallback_readable_screens = [s for s in screen_rects if s.get("readable")]

    worst_by_screen: Dict[str, float] = {}
    worst_label_by_screen: Dict[str, Optional[str]] = {}
    seen_screen_ids: set = set()
    seen_readable_screen_ids: set = set()
    any_label_sampled = False
    for s in samples:
        tick_screens = s.get("screen_rects")
        readable_screens = [sc for sc in tick_screens if sc.get("readable")] if tick_screens else fallback_readable_screens
        for sc in (tick_screens if tick_screens else screen_rects):
            seen_screen_ids.add(sc.get("id"))
            if sc.get("readable"):
                seen_readable_screen_ids.add(sc.get("id"))
        for r in s.get("label_rects") or []:
            if not r.get("visible", True):
                continue
            opacity = r.get("opacity")
            if opacity is not None and opacity < LABEL_LEGIBILITY_MIN_OPACITY:
                continue
            any_label_sampled = True
            for screen in readable_screens:
                frac = _rect_overlap_fraction_of_screen(r, screen)
                sid = screen["id"]
                if frac > worst_by_screen.get(sid, 0.0):
                    worst_by_screen[sid] = frac
                    worst_label_by_screen[sid] = r.get("text")

    if not any_label_sampled:
        return {"verdict": "NO-DATA", "detail": {"reason": "no visible labels sampled this run"}}

    violations = [
        {"screenId": sid, "overlapFrac": round(frac, 4), "worstLabel": worst_label_by_screen.get(sid)}
        for sid, frac in worst_by_screen.items()
        if frac > LABEL_VS_SCREEN_OVERLAP_MAX_FRAC
    ]
    return {
        "verdict": "FAIL" if violations else "PASS",
        "detail": {
            "maxFrac": LABEL_VS_SCREEN_OVERLAP_MAX_FRAC,
            "readableScreenCount": len(seen_readable_screen_ids),
            "screenCount": len(seen_screen_ids),
            "violations": violations,
            "note": "informational screens (readable:false) are counted in screenCount but never gate this verdict",
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

    # PROBE-16 addendum: informational-only widened-pattern scan over
    # rawDetail -- does NOT gate the verdict (the 2026-09-14 fix that made
    # rawDetail leak-scan-but-not-verdict-gating is preserved deliberately;
    # see test_bubbles_pass_when_only_rawdetail_leaks). The tooltip text
    # that actually leaked (LiveAgents.tsx's `taskDetail`) isn't captured
    # by this probe at all -- it's never written to window.__hqLiveAgents
    # (diagStore.set only carries `rawDetail`, see LiveAgents.tsx:1027-1034)
    # -- so rawDetail is the closest available signal, reported here so a
    # human reviewing a run can see it without it silently reappearing as
    # a false-FAIL regression the way the 2026-09-14 fix was written to
    # prevent.
    raw_detail_leak_matches = sorted(r for r in raw_detail_samples if RAW_SHELL_LEAK_RE.search(r))

    if not distinct_bubbles:
        return {
            "verdict": "NO-DATA",
            "detail": {
                "reason": "no bubble text observed",
                "raw_detail_samples": sorted(raw_detail_samples),
                "raw_detail_leak_matches": raw_detail_leak_matches,
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
            # field) and never judged for leaks/junk (verdict-gating,
            # 2026-09-14 fix). raw_detail_leak_matches is likewise
            # informational -- see this function's own PROBE-16 addendum
            # comment above.
            "raw_detail_samples": sorted(raw_detail_samples),
            "raw_detail_leak_count": len(raw_detail_leak_matches),
            "raw_detail_leak_matches": raw_detail_leak_matches,
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
            "walker_separation": _no_data(),
            "waiting_separation": _no_data(),
            "pose_jump": _no_data(),
            "walk_out": _no_data(),
            "label_overlap": _no_data(),
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
            samples, design_speed=walk_speed, tol=walk_speed_tol, speed_window_s=speed_window_s,
            frame_timestamps_ms=frame_timestamps_ms,
        ),
        "stand_slots": _motion_no_data() if motion_gated else check_stand_slots(samples),
        "walker_separation": _motion_no_data() if motion_gated else check_walker_separation(samples),
        "waiting_separation": _motion_no_data() if motion_gated else check_waiting_separation(samples),
        "pose_jump": _motion_no_data() if motion_gated else check_pose_jump(samples),
        "walk_out": _motion_no_data() if motion_gated else check_walk_out(samples),
        "label_overlap": _motion_no_data() if motion_gated else check_label_overlap(samples),
        "page_api_parity": check_page_api_parity(samples),
        "bubbles": check_bubbles(samples),
        "perf": check_perf(frame_timestamps_ms, calls_samples, scene_ready=scene_ready, headless=headless),
    }
