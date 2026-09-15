"""Unit tests for hq_probe_lib.py's pure verdict logic -- synthetic sample
arrays only, no browser, no network. Run: python -m pytest setup/scripts/test_hq_probe_lib.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hq_probe_lib import (  # noqa: E402
    LABEL_OVERLAP_MIN_INTERSECTION_FRAC,
    PAGE_REFRESH_MS_DEFAULT,
    PAGE_REFRESH_MS_KIOSK,
    SPAWN_LATENCY_RENDER_SLACK_MS,
    WALK_OUT_MAX_S,
    WALKER_MIN_DIST,
    build_verdicts,
    check_bubbles,
    check_label_overlap,
    check_page_api_parity,
    check_perf,
    check_run_validity,
    check_spawn_latency,
    check_stand_slots,
    check_waiting_separation,
    check_walk_out,
    check_walk_speed,
    check_walker_separation,
    page_refresh_ms_from_url,
    perf_headless_flag,
)


def _s(t_ms, page=None, api=None, calls=None, label_rects=None):
    return {
        "t_ms": t_ms, "page_agents": page or [], "api_agents": api or [], "calls": calls,
        "label_rects": label_rects if label_rects is not None else [],
    }


def _label(text, x, y, w, h, opacity=1.0, id_=None):
    return {"id": id_, "text": text, "x": x, "y": y, "w": w, "h": h, "opacity": opacity, "visible": opacity > 0.01}


def _agent(id_, state, pos, target="zone-a", bubble="working · x", raw="working · x", onWalkable=True):
    return {"id": id_, "label": id_, "state": state, "pos": pos, "target": target,
            "bubble": bubble, "rawDetail": raw, "onWalkable": onWalkable, "bubbleOpacity": 1}


# 1. spawn latency ------------------------------------------------------------
# check_spawn_latency judges against the PAGE's real SWR refresh interval
# (dashboard/app/hq/page.tsx:34 -- 15s normally, 60s for kiosk=1), not the
# probe's own sample tick. See hq_probe_lib.py's PAGE_REFRESH_MS_* comments.

def test_spawn_latency_pass_within_page_refresh():
    # 3 spawns at 7.5s / 11.7s / 12.5s -- all comfortably inside the 15s
    # default page refresh + 2s render slack (17s threshold).
    samples = [
        _s(0, page=[], api=[]),
        _s(0, page=[], api=[{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]),
        _s(7500, page=[_agent("a1", "spawning", [0, 0])],
           api=[{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]),
        _s(11700, page=[_agent("a1", "spawning", [0, 0]), _agent("a2", "spawning", [0, 0])],
           api=[{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]),
        _s(12500, page=[_agent("a1", "spawning", [0, 0]), _agent("a2", "spawning", [0, 0]),
                         _agent("a3", "spawning", [0, 0])],
           api=[{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]),
    ]
    v = check_spawn_latency(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["spawn_count"] == 3
    assert v["detail"]["latencies_ms"] == [7500, 11700, 12500]
    assert v["detail"]["page_refresh_ms"] == PAGE_REFRESH_MS_DEFAULT
    assert v["detail"]["slack_ms"] == SPAWN_LATENCY_RENDER_SLACK_MS
    # sample_tick_ms is reported for diagnostics but must never drive the verdict.
    assert "sample_tick_ms" in v["detail"]
    assert "poll_interval_ms" not in v["detail"]


def test_spawn_latency_fail_when_past_page_refresh_plus_slack():
    # 17.1s exceeds the 15s default page refresh + 2s slack (17s threshold).
    samples = [
        _s(0, page=[], api=[]),
        _s(0, page=[], api=[{"id": "a1"}]),
        _s(17100, page=[_agent("a1", "spawning", [0, 0])], api=[{"id": "a1"}]),
    ]
    v = check_spawn_latency(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["max_latency_ms"] == 17100


def test_spawn_latency_kiosk_uses_60s_refresh():
    assert page_refresh_ms_from_url("http://127.0.0.1:3000/hq?diag=1&kiosk=1") == PAGE_REFRESH_MS_KIOSK
    assert page_refresh_ms_from_url("http://127.0.0.1:3000/hq?diag=1&tier=ultra") == PAGE_REFRESH_MS_DEFAULT

    # The same 17.1s latency that FAILs against the 15s default page refresh
    # PASSes against the 60s kiosk refresh.
    samples = [
        _s(0, page=[], api=[]),
        _s(0, page=[], api=[{"id": "a1"}]),
        _s(17100, page=[_agent("a1", "spawning", [0, 0])], api=[{"id": "a1"}]),
    ]
    v = check_spawn_latency(samples, page_refresh_ms=PAGE_REFRESH_MS_KIOSK)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["page_refresh_ms"] == PAGE_REFRESH_MS_KIOSK


def test_spawn_latency_no_data_when_nobody_spawns():
    samples = [_s(0), _s(500), _s(1000)]
    v = check_spawn_latency(samples)
    assert v["verdict"] == "NO-DATA", v


# 2. walk speed ----------------------------------------------------------------
# 2026-09-15 PROBE-8: check_walk_speed now measures over WINDOWS of
# >= speed_window_s (default 2.0s) instead of per-tick, so the 250ms
# LiveAgents.tsx diag-publish vs ~500ms probe-sample quantization (a false
# FAIL on run 20260915T074839Z-gZsuTUlH: out_of_band_frac 0.2293) averages
# out. Teleport detection stays strict and per-tick (teleport_count).

def test_walk_speed_pass_in_band():
    # 1.4 units over 2.0s (two 1.0s/0.7u ticks) = 0.7 u/s -- exactly the
    # configured design speed (dashboard/components/hq/KitAgent.tsx:85
    # WALK_SPEED = 0.7). Total run time meets the 2.0s window minimum.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["design_speed"] == 0.7
    assert v["detail"]["window_count"] == 1
    assert abs(v["detail"]["median_speed_by_agent"]["a1"] - 0.7) < 1e-9
    assert v["detail"]["teleport_count"] == 0


def test_walk_speed_fail_too_fast():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [5, 0])]),
        _s(2000, page=[_agent("a1", "walking", [10, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v


def test_walk_speed_fail_real_bug_median_1_02_vs_design_0_7():
    # (b) The actual dashboard bug shape (2026-09-15 coordinator analysis):
    # agents walk a real steady ~1.02 u/s against a 0.7 u/s design speed
    # (dashboard/components/hq/KitAgent.tsx:85). Every tick is 'walking' --
    # this is a true wrong pace, not a transition or quantization artifact,
    # and windowing must still catch it (median stays 1.02, not smoothed
    # toward 0.7).
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(500, page=[_agent("a1", "walking", [0.51, 0])]),
        _s(1000, page=[_agent("a1", "walking", [1.02, 0])]),
        _s(1500, page=[_agent("a1", "walking", [1.53, 0])]),
        _s(2000, page=[_agent("a1", "walking", [2.04, 0])]),  # 4 ticks = 2.0s window
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["window_count"] == 1
    assert abs(v["detail"]["median_speed_by_agent"]["a1"] - 1.02) < 1e-9
    assert v["detail"]["teleport_count"] == 0  # a true wrong pace is not a teleport


def test_walk_speed_fail_unwalkable():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0], onWalkable=False)]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0], onWalkable=False)]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0], onWalkable=False)]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["unwalkable_hits"] > 0


def test_walk_speed_fail_unwalkable_even_with_no_window():
    # unwalkable_hits is a real placement bug regardless of whether a full
    # speed_window_s window ever forms -- must not be swallowed by the
    # "no window observed" NO-DATA short-circuit.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0], onWalkable=False)]),
        _s(500, page=[_agent("a1", "walking", [0.35, 0], onWalkable=False)]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["unwalkable_hits"] > 0


def test_walk_speed_no_data():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0])])]
    v = check_walk_speed(samples)
    assert v["verdict"] == "NO-DATA", v


def test_walk_speed_no_data_when_run_shorter_than_window():
    # Steady 0.7 u/s, but the whole run is only 1.0s -- shorter than the
    # 2.0s window minimum, so no window can form. NO-DATA, not PASS/FAIL on
    # an unjudgeable partial window.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "NO-DATA", v


def test_walk_speed_excludes_state_transition_ticks():
    # (d) a1 goes working -> walking (partial in-tick move at the
    # transition, 0.2 u/s -- would itself be out-of-band if counted) ->
    # steady 0.7 u/s walking for a full 2.0s window. The transition tick
    # must be excluded from the window (not bridged across), and the run
    # must PASS on the steady pace alone.
    samples = [
        _s(0, page=[_agent("a1", "working", [0.0, 0])]),
        _s(500, page=[_agent("a1", "walking", [0.1, 0])]),    # transition tick -- excluded
        _s(1000, page=[_agent("a1", "walking", [0.45, 0])]),  # 0.35/0.5 = 0.7 u/s
        _s(1500, page=[_agent("a1", "walking", [0.8, 0])]),   # 0.35/0.5 = 0.7 u/s
        _s(2000, page=[_agent("a1", "walking", [1.15, 0])]),  # 0.35/0.5 = 0.7 u/s
        _s(2500, page=[_agent("a1", "walking", [1.5, 0])]),   # 0.35/0.5 = 0.7 u/s -- 4 walking ticks = 2.0s window
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["window_count"] == 1
    assert abs(v["detail"]["median_speed_by_agent"]["a1"] - 0.7) < 1e-9


def test_walk_speed_excludes_leaving_to_despawn_transition():
    # working -> leaving transition tick, then steady leaving at 0.7 u/s --
    # 'leaving' is a walking state in its own right (departure), and its
    # own entry transition must be excluded from the window the same way
    # 'walking' is.
    samples = [
        _s(0, page=[_agent("a1", "working", [0.0, 0])]),
        _s(500, page=[_agent("a1", "leaving", [0.05, 0])]),  # transition tick -- excluded
        _s(1000, page=[_agent("a1", "leaving", [0.4, 0])]),  # 0.35/0.5 = 0.7 u/s
        _s(1500, page=[_agent("a1", "leaving", [0.75, 0])]),  # 0.35/0.5 = 0.7 u/s
        _s(2000, page=[_agent("a1", "leaving", [1.1, 0])]),   # 0.35/0.5 = 0.7 u/s -- 3 leaving ticks = 1.5s, not enough yet
        _s(2500, page=[_agent("a1", "leaving", [1.45, 0])]),  # 4th leaving tick -> 2.0s window
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["window_count"] == 1


# (a) sampling-aliasing regression: the actual 20260915T074839Z-gZsuTUlH
# shape -- LiveAgents.tsx publishes every 250ms, the probe samples every
# ~500ms, so raw tick-to-tick displacement quantizes to 1/2/3 diag updates
# (0.175/0.35/0.525u at the true 0.7 u/s design speed). Windowing must
# average this out to PASS; the un-windowed (per-tick) reading would FAIL.

def test_walk_speed_pass_despite_250ms_publish_500ms_sample_aliasing():
    deltas = [0.175, 0.35, 0.525] * 8  # repeating quantization pattern, 24 ticks
    pos = 0.0
    samples = [_s(0, page=[_agent("a1", "walking", [0.0, 0])])]
    t = 0
    for d in deltas:
        t += 500
        pos += d
        samples.append(_s(t, page=[_agent("a1", "walking", [round(pos, 6), 0])]))
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["teleport_count"] == 0
    assert v["detail"]["window_count"] >= 1
    for m in v["detail"]["median_speed_by_agent"].values():
        assert abs(m - 0.7) < 0.1, v["detail"]["median_speed_by_agent"]
    assert v["detail"]["out_of_band_frac"] <= 0.05, v["detail"]


# (c) teleport detection: independent of windowing, strict, per-tick -- the
# real 2cb12e5c-era bug shape (an 8.75u jump in 0.48s) must FAIL via
# teleport_count even though a window average alone might otherwise dilute
# a single bad tick into an in-band median.

def test_walk_speed_fail_teleport_jump():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(480, page=[_agent("a1", "walking", [8.75, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["teleport_count"] == 1
    assert v["detail"]["teleport_events"][0]["distance"] == 8.75


def test_walk_speed_teleport_fails_even_inside_an_otherwise_steady_walk():
    # Steady 0.7 u/s for a full window, then one teleport tick -- the
    # window average alone would still look fine, but teleport_count must
    # independently FAIL the run.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(500, page=[_agent("a1", "walking", [0.35, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])]),
        _s(1500, page=[_agent("a1", "walking", [1.05, 0])]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0])]),
        _s(2480, page=[_agent("a1", "walking", [10.15, 0])]),  # +8.75u in 0.48s -- teleport
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["teleport_count"] == 1


# page_t_ms vs host t_ms (WALK-SPEED-DIAG addendum, 2026-09-15) -------------------
# hq_live_probe.py's sample loop timestamps AFTER the CDP round-trip
# (page.evaluate) returns -- that round-trip itself jitters 0.198-0.808s,
# unrelated to true agent speed. check_walk_speed must prefer the in-page
# performance.now() timestamp (page_t_ms, captured in the SAME evaluate()
# call as window.__hqLiveAgents) when present.

def _s_with_page_t(t_ms, page_t_ms, page=None):
    d = _s(t_ms, page=page)
    d["page_t_ms"] = page_t_ms
    return d


def test_walk_speed_uses_page_timestamp_over_jittered_host_timestamp():
    # True cadence (page_t_ms) is a clean 500ms/0.35u steady 0.7 u/s walk;
    # host t_ms is jittered (198-808ms) around that same nominal cadence,
    # as observed in production CDP round-trips. The windowed median must
    # come out 0.7 (from page_t_ms), not skewed by the host jitter.
    host_ts = [0, 198, 1006, 1210, 2014]
    page_ts = [0, 500, 1000, 1500, 2000]
    positions = [0.0, 0.35, 0.7, 1.05, 1.4]
    samples = [
        _s_with_page_t(host_ts[i], page_ts[i], page=[_agent("a1", "walking", [positions[i], 0])])
        for i in range(len(host_ts))
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["timestamp_source"] == "page"
    assert abs(v["detail"]["median_speed_by_agent"]["a1"] - 0.7) < 1e-9


def test_walk_speed_falls_back_to_host_timestamp_when_page_t_ms_absent():
    # Old samples files predate page_t_ms -- must still work, off host t_ms,
    # and must label the source so a rescore report can say so.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["timestamp_source"] == "host"


# whole-run average-speed regression check -----------------------------------------

def test_walk_speed_avg_speed_by_agent_regression_ok_when_steady():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v
    assert abs(v["detail"]["avg_speed_by_agent"]["a1"] - 0.7) < 1e-9
    assert v["detail"]["avg_speed_regression_ok"] is True


def test_walk_speed_avg_speed_by_agent_regression_flags_wrong_pace():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(500, page=[_agent("a1", "walking", [0.51, 0])]),
        _s(1000, page=[_agent("a1", "walking", [1.02, 0])]),
        _s(1500, page=[_agent("a1", "walking", [1.53, 0])]),
        _s(2000, page=[_agent("a1", "walking", [2.04, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["avg_speed_regression_ok"] is False


# --speed-window-s parameter ---------------------------------------------------------

def test_walk_speed_window_s_param_overrides_default():
    # With a 1.0s window, the same 1.0s run that was NO-DATA against the
    # 2.0s default now forms exactly one window and PASSes.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])]),
    ]
    v = check_walk_speed(samples, speed_window_s=1.0)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["window_count"] == 1
    assert v["detail"]["speed_window_s"] == 1.0


# 3. stand slots -----------------------------------------------------------------

def test_stand_slots_pass_spread_out():
    samples = [_s(0, page=[
        _agent("a1", "working", [0, 0], target="zone-a"),
        _agent("a2", "working", [1.0, 0], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "PASS", v


def test_stand_slots_fail_duplicate_position():
    samples = [_s(0, page=[
        _agent("a1", "working", [0, 0], target="zone-a"),
        _agent("a2", "working", [0, 0], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["duplicate_position_count"] == 1


def test_stand_slots_fail_too_close():
    samples = [_s(0, page=[
        _agent("a1", "working", [0, 0], target="zone-a"),
        _agent("a2", "working", [0.2, 0], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "FAIL", v


def test_stand_slots_no_data_single_agent():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0], target="zone-a")])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "NO-DATA", v


def test_stand_slots_duplicate_epsilon_catches_float_noise():
    # PROBE-12 (coordinator, 2026-09-15, run
    # 20260915T085943Z-Da6D81TEcI6kH8JvM85Db): two agents at 1.159e-15u
    # apart -- float noise from position math, not bit-exact 0 -- must still
    # count as a duplicate. The old `d == 0` check missed this.
    samples = [_s(0, page=[
        _agent("a7195e62a4dda3d05", "working", [-0.2999999999999996, -1.599999999999999], target="zone-a"),
        _agent("a1b95546df7c4703f", "working", [-0.3, -1.6], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["duplicate_position_count"] == 1
    assert v["detail"]["violating_groups"] == 1
    assert v["detail"]["violating_frac"] == 1.0
    assert len(v["detail"]["worst_pairs"]) == 1
    wp = v["detail"]["worst_pairs"][0]
    assert {wp["a_id"], wp["b_id"]} == {"a7195e62a4dda3d05", "a1b95546df7c4703f"}
    assert wp["target"] == "zone-a"


def test_stand_slots_worst_pairs_reports_self_explaining_detail():
    samples = [_s(1234, page=[
        _agent("a1", "working", [0, 0], target="zone-a"),
        _agent("a2", "working", [0.1, 0], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "FAIL", v
    wp = v["detail"]["worst_pairs"][0]
    assert wp["t_ms"] == 1234
    assert wp["a_pos"] == [0, 0]
    assert wp["b_pos"] == [0.1, 0]
    assert wp["target"] == "zone-a"


# 3b. walker separation -------------------------------------------------------------
# Companion to stand_slots: catches two agents overlapping WHILE IN TRANSIT
# (walking/leaving), which stand_slots can't see since neither is "working".

def test_walker_separation_fail_lockstep_pair():
    # PROBE-10 shape: two agents walking 0.01u apart for many ticks.
    samples = [
        _s(t, page=[
            _agent("a1", "walking", [float(t) / 1000.0, 0]),
            _agent("a2", "walking", [float(t) / 1000.0 + 0.01, 0]),
        ])
        for t in range(0, 11000, 1000)
    ]
    v = check_walker_separation(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["violating_frac"] == 1.0
    assert v["detail"]["min_pairwise_dist"] == 0.01
    assert len(v["detail"]["worst_pairs"]) <= 5


def test_walker_separation_pass_well_separated():
    samples = [
        _s(t, page=[
            _agent("a1", "walking", [float(t) / 1000.0, 0]),
            _agent("a2", "walking", [float(t) / 1000.0 + 1.0, 0]),
        ])
        for t in range(0, 11000, 1000)
    ]
    v = check_walker_separation(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["violating_frac"] == 0.0


def test_walker_separation_no_data_single_walker():
    samples = [_s(0, page=[_agent("a1", "walking", [0, 0])])]
    v = check_walker_separation(samples)
    assert v["verdict"] == "NO-DATA", v


# 3c. waiting separation -------------------------------------------------------------
# Companion to stand_slots ("working") and walker_separation (walking/
# leaving): PROBE-12's 3rd coverage gap, agents in a non-walking,
# non-working state (e.g. "spawning", waiting at the campus-gate for their
# CONVOY-STACK stagger slot). A SEPARATE check from walker_separation
# (decision stated in hq_probe_lib.py's own header comment): stationary
# wait-point coincidence is a deterministic placement bug, so it FAILs on
# ANY violating tick, not walker_separation's >10%-of-ticks allowance.

def test_waiting_separation_fail_coincident_wait_points():
    # PROBE-12 live shape: two agents at the IDENTICAL wait point
    # [21.65, 0.45] while both "spawning".
    samples = [
        _s(7505, page=[
            _agent("session:abc", "spawning", [21.65, 0.45]),
            _agent("ae892a7f7e3cf5a51", "spawning", [21.65, 0.45]),
        ]),
    ]
    v = check_waiting_separation(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["violating_ticks"] == 1
    assert v["detail"]["min_pairwise_dist"] == 0.0
    wp = v["detail"]["worst_pairs"][0]
    assert {wp["a_id"], wp["b_id"]} == {"session:abc", "ae892a7f7e3cf5a51"}
    assert wp["t_ms"] == 7505


def test_waiting_separation_pass_well_separated():
    samples = [
        _s(0, page=[
            _agent("a1", "spawning", [0, 0]),
            _agent("a2", "spawning", [5, 0]),
        ]),
    ]
    v = check_waiting_separation(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["violating_ticks"] == 0


def test_waiting_separation_no_data_single_waiting_agent():
    samples = [_s(0, page=[_agent("a1", "spawning", [0, 0])])]
    v = check_waiting_separation(samples)
    assert v["verdict"] == "NO-DATA", v


def test_waiting_separation_ignores_walking_and_working_agents():
    # A walking agent and a working agent standing at the SAME point as
    # each other must never be judged by this check (that's
    # walker_separation's and stand_slots's own job respectively) -- only
    # >=2 simultaneously WAITING agents count.
    samples = [_s(0, page=[
        _agent("a1", "walking", [0, 0]),
        _agent("a2", "working", [0, 0], target="zone-a"),
    ])]
    v = check_waiting_separation(samples)
    assert v["verdict"] == "NO-DATA", v


def test_waiting_separation_covers_future_non_literal_states():
    # Built to catch ANY non-walking, non-working state -- not just the
    # literal string "spawning" -- so a future "waiting" state (the
    # coordinator's own example) is covered without another edit here.
    samples = [_s(0, page=[
        _agent("a1", "waiting", [0, 0]),
        _agent("a2", "waiting", [0.01, 0]),
    ])]
    v = check_waiting_separation(samples)
    assert v["verdict"] == "FAIL", v


# 4. walk-out ---------------------------------------------------------------------

def test_walk_out_pass():
    # Despawns near campus-gate (GATE_POS = (21.6, 0.0)) after a real
    # ~2s walk -- correct on both duration and despawn location.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [19.6, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [21.3, 0])]),
        _s(2000, page=[]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "PASS", v


def test_walk_out_pass_30s_ending_at_gate():
    # Live-evidence shape (2026-09-15 run 20260915T081521Z-BJcLqAlox0n-8xa5n5Kns,
    # agent ac4b025b7106368d5): a correct 30.85s walk-out ending 0.30u from
    # the gate. Must PASS under the derived ~51.14s ceiling -- the old fixed
    # 15.0s limit wrongly FAILed exactly this shape.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5.0, 0])]),
        _s(15000, page=[_agent("a1", "leaving", [13.0, 0])]),
        _s(30850, page=[_agent("a1", "leaving", [21.30, 0])]),
        _s(31000, page=[]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["per_agent"]["a1"]["despawned_at_gate"] is True


def test_walk_out_fail_60s_exceeds_derived_ceiling():
    # A walk-out that reaches the gate but takes far longer than the app's
    # own derived ceiling (~51.14s = 27.4u/0.7 + 10s margin + 2s slack) is a
    # genuine FAIL, not a correct-but-slow walk.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5.0, 0])]),
        _s(30000, page=[_agent("a1", "leaving", [13.0, 0])]),
        _s(60000, page=[_agent("a1", "leaving", [21.6, 0])]),
        _s(60100, page=[]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["per_agent"]["a1"]["status"] == "FAIL"


def test_walk_out_fail_despawn_far_from_gate():
    # Despawns well within the time ceiling but 8u from campus-gate --
    # the teleport/ghost-despawn bug shape (vanishing mid-hallway), not a
    # correct walk-out. Must FAIL even though duration alone would PASS.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5.0, 0])]),
        _s(3000, page=[_agent("a1", "leaving", [13.6, 0])]),  # 8u from gate
        _s(4000, page=[]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "FAIL", v
    detail = v["detail"]["per_agent"]["a1"]
    assert detail["status"] == "FAIL"
    assert detail["despawned_at_gate"] is False
    assert detail["dist_to_gate"] == 8.0


def test_walk_out_fail_never_gone():
    # Never despawns, well past the derived grace (WALK_OUT_MAX_S) -- a
    # genuine FAIL, not a probe-window artifact.
    past_grace_ms = (WALK_OUT_MAX_S + 5.0) * 1000
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [3, 0])]),
        _s(past_grace_ms, page=[_agent("a1", "leaving", [3, 0])]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "FAIL", v


def test_walk_out_no_data():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0])])]
    v = check_walk_out(samples)
    assert v["verdict"] == "NO-DATA", v


def test_walk_out_no_data_when_leave_started_near_window_end():
    # 2026-09-14 false-FAIL artifact: 1 agent started leaving 10s before the
    # probe window closed and simply hadn't despawned yet -- that's a probe
    # cutoff, not a stuck agent. Must be NO-DATA, not FAIL.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [3, 0])]),
        _s(10000, page=[_agent("a1", "leaving", [3, 0])]),  # window ends here
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "NO-DATA", v
    assert v["detail"]["per_agent"]["a1"]["status"] == "NO-DATA"
    assert v["detail"]["per_agent"]["a1"]["leave_started_offset_s"] == 10.0


def test_walk_out_fail_when_leaving_past_derived_grace_without_despawn():
    # Same shape as the window-end case but past the derived grace
    # (WALK_OUT_WINDOW_END_GRACE_S == WALK_OUT_MAX_S, ~51.14s) -- now a
    # genuine FAIL, not an artifact.
    past_grace_ms = (WALK_OUT_MAX_S + 1.0) * 1000
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [3, 0])]),
        _s(past_grace_ms, page=[_agent("a1", "leaving", [3, 0])]),  # window ends here
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["per_agent"]["a1"]["status"] == "FAIL"
    assert v["detail"]["per_agent"]["a1"]["leave_started_offset_s"] == past_grace_ms / 1000


def test_walk_out_no_data_when_still_walking_within_max_s_at_window_end():
    # PROBE-10 (coordinator, 2026-09-15, run
    # 20260915T084211Z-5rAPWKjf6d_SvYCYmRL3o): agent a93582c12e2fad9ca
    # started leaving 28.02s before the window ended, moved, and was still
    # walking at window close -- a correct in-progress hub->gate walk
    # (~31s), well inside WALK_OUT_MAX_S (~51.14s). The old fixed 20.0s
    # grace wrongly FAILed this. Must be NO-DATA -- the walk simply hasn't
    # had its full budget to finish yet.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5.0, 0])]),
        _s(14000, page=[_agent("a1", "leaving", [13.0, 0])]),
        _s(28020, page=[_agent("a1", "leaving", [20.02, -0.02])]),  # window ends here
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "NO-DATA", v
    assert v["detail"]["per_agent"]["a1"]["status"] == "NO-DATA"
    assert v["detail"]["per_agent"]["a1"]["leave_started_offset_s"] == 28.02


def test_walk_out_mixed_no_data_and_pass():
    # One agent despawns cleanly at the gate (PASS), another starts leaving
    # only 5s before the window ends (NO-DATA for that agent) -- overall
    # verdict is PASS since nothing actually FAILed.
    samples = [
        _s(0, page=[
            _agent("a1", "leaving", [19.6, 0]),
        ]),
        _s(1000, page=[
            _agent("a1", "leaving", [21.3, 0]),
        ]),
        _s(2000, page=[
            _agent("a2", "leaving", [5, 0]),
        ]),
        _s(7000, page=[
            _agent("a2", "leaving", [5, 0]),
        ]),  # window ends here: a1 despawned by t=2000, a2 started at t=2000 (5s offset)
    ]
    v = check_walk_out(samples)
    assert v["detail"]["per_agent"]["a1"]["status"] == "PASS"
    assert v["detail"]["per_agent"]["a2"]["status"] == "NO-DATA"
    assert v["verdict"] == "PASS", v


# 4b. speech-bubble overlap ----------------------------------------------------------
# PROBE-11: check_label_overlap works off '.hq-beam' rects captured by
# SAMPLE_SCRIPT (hq_live_probe.py) -- no id is recoverable from the DOM, so
# a live-agent bubble is identified by matching its captured text against
# page_agents' own bubble string (same tick), per _live_agent_state_for_label.

def test_label_overlap_fail_overlapping_live_agent_pair():
    # Two live-agent bubbles fully coincident (worst case, matches the
    # PROBE-11 screenshot shape) -- text matches each agent's own bubble
    # field so the pair is correctly identified as involving live agents.
    samples = [
        _s(0,
            page=[
                _agent("a1", "working", [0, 0], bubble="reviewing PR", raw="reviewing PR"),
                _agent("a2", "working", [1, 0], bubble="writing tests", raw="writing tests"),
            ],
            label_rects=[
                _label("Coach · reviewing PR", 100, 100, 80, 20),
                _label("Chef · writing tests", 100, 100, 80, 20),
            ],
        ),
    ]
    v = check_label_overlap(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["violating_frac"] == 1.0
    assert v["detail"]["worst_pairs"][0]["involves_live_agent"] is True
    assert v["detail"]["worst_pairs"][0]["overlap_frac"] == 1.0


def test_label_overlap_pass_disjoint_pair():
    samples = [
        _s(0,
            page=[
                _agent("a1", "working", [0, 0], bubble="reviewing PR", raw="reviewing PR"),
                _agent("a2", "working", [1, 0], bubble="writing tests", raw="writing tests"),
            ],
            label_rects=[
                _label("Coach · reviewing PR", 0, 0, 80, 20),
                _label("Chef · writing tests", 500, 500, 80, 20),
            ],
        ),
    ]
    v = check_label_overlap(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["violating_frac"] == 0.0


def test_label_overlap_no_data_when_no_rects_captured():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0])])]  # label_rects defaults to []
    v = check_label_overlap(samples)
    assert v["verdict"] == "NO-DATA", v


def test_label_overlap_ignores_low_opacity_pair():
    # Two fully-overlapping labels BOTH below LABEL_OVERLAP_MIN_OPACITY
    # (0.5) must be excluded entirely -- a faded-out pair mid-declutter-fade
    # is not what a screenshot reader would call "bubbles on top of each
    # other". A second, disjoint, fully-visible pair in the SAME tick
    # proves the low-opacity pair didn't silently starve the tick of data
    # (verdict is PASS on the visible pair, not NO-DATA).
    samples = [
        _s(0,
            page=[],
            label_rects=[
                _label("fading A", 0, 0, 10, 10, opacity=0.2),
                _label("fading B", 0, 0, 10, 10, opacity=0.2),
                _label("visible C", 100, 100, 10, 10, opacity=1.0),
                _label("visible D", 200, 200, 10, 10, opacity=1.0),
            ],
        ),
    ]
    v = check_label_overlap(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["ticks"] == 1
    assert v["detail"]["violating_ticks"] == 0


def test_label_overlap_below_intersection_threshold_not_a_violation():
    # Two visible labels that touch but overlap by less than
    # LABEL_OVERLAP_MIN_INTERSECTION_FRAC of the smaller rect's area --
    # "close together", not "on top of each other".
    samples = [
        _s(0,
            page=[],
            label_rects=[
                _label("A", 0, 0, 100, 20),
                _label("B", 95, 0, 100, 20),  # 5/100 = 5% overlap of either rect's area
            ],
        ),
    ]
    v = check_label_overlap(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["violating_ticks"] == 0
    assert LABEL_OVERLAP_MIN_INTERSECTION_FRAC > 0.05  # sanity: threshold is above this pair's overlap


# 5. page == API parity -------------------------------------------------------------

def test_parity_pass_ten_consecutive():
    samples = [_s(i * 500, page=[{"id": "a1"}], api=[{"id": "a1"}]) for i in range(10)]
    v = check_page_api_parity(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["best_consecutive_match_run"] == 10


def test_parity_pass_across_replacement():
    samples = [_s(i * 500, page=[{"id": "a1"}], api=[{"id": "a1"}]) for i in range(6)]
    samples += [_s((6 + i) * 500, page=[{"id": "a2"}], api=[{"id": "a2"}]) for i in range(6)]
    v = check_page_api_parity(samples)
    assert v["verdict"] == "PASS", v


def test_parity_fail_short_run():
    samples = [_s(i * 500, page=[{"id": "a1"}], api=[{"id": "a1"}]) for i in range(3)]
    samples.append(_s(1500, page=[{"id": "a1"}], api=[]))
    v = check_page_api_parity(samples)
    assert v["verdict"] == "FAIL", v


# 6. bubbles --------------------------------------------------------------------------

def test_bubbles_pass_clean_text():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0], bubble="working · editing foo.ts", raw="working · editing foo.ts")])]
    v = check_bubbles(samples)
    assert v["verdict"] == "PASS", v


def test_bubbles_fail_shell_leak():
    # Corrected 2026-09-14: the leak must be in `bubble` (what's actually
    # rendered) to FAIL -- a leak confined to rawDetail alone must NOT fail
    # the check (see test_bubbles_pass_when_only_rawdetail_leaks below).
    # This test previously put the leak only in rawDetail and asserted
    # FAIL, which was itself the probe artifact the coordinator flagged
    # (rawDetail is deliberately raw/debug-only and was never meant to be
    # judged for leaks).
    samples = [_s(0, page=[_agent(
        "a1", "working", [0, 0],
        bubble="Ran: cd /c/Users/jackw && ls", raw="Ran: cd /c/Users/jackw && ls",
    )])]
    v = check_bubbles(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["leak_count"] == 1


def test_bubbles_no_data():
    samples = [_s(0, page=[])]
    v = check_bubbles(samples)
    assert v["verdict"] == "NO-DATA", v


def test_bubbles_pass_when_only_rawdetail_leaks():
    # 2026-09-14 false-FAIL artifact: rawDetail is a deliberate debug field
    # and must never feed the leak scan. The on-screen bubble here is clean
    # ("working · editing Agent.tsx") even though rawDetail is messy --
    # verdict must be PASS, with the raw text reported separately.
    samples = [_s(0, page=[_agent(
        "a1", "working", [0, 0],
        bubble="working · editing Agent.tsx",
        raw="Ran: cd /c/Users/jackw && ls",
    )])]
    v = check_bubbles(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["leak_count"] == 0
    assert "Ran: cd /c/Users/jackw && ls" in v["detail"]["raw_detail_samples"]


def test_bubbles_fail_on_junk_target():
    # Observed 2026-09-14 artifact: "working · reading |<Htm" -- a
    # target string containing shell/markup-only characters is junk even
    # though it also contains letters.
    samples = [_s(0, page=[_agent(
        "a1", "working", [0, 0],
        bubble="working · reading |<Htm",
        raw="working · reading |<Htm",
    )])]
    v = check_bubbles(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["junk_target_count"] == 1
    assert v["detail"]["junk_targets"][0]["target"] == "|<Htm"


def test_bubbles_pass_on_clean_target():
    samples = [_s(0, page=[_agent(
        "a1", "working", [0, 0],
        bubble="working · reading Agent.tsx",
        raw="working · reading Agent.tsx",
    )])]
    v = check_bubbles(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["junk_target_count"] == 0


# 7. perf -----------------------------------------------------------------------------

def test_perf_headless_is_info_not_pass():
    # 2026-09-14 false-PASS bug: headless/SwiftShader numbers (fps_p50 0.71
    # in the real run) were read as a passing perf verdict. There is no
    # threshold in headless mode -- verdict must be INFO, never PASS, even
    # with a clean steady-60fps sample like this one.
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [100, 110, 105])  # headless=True default
    assert v["verdict"] == "INFO", v
    assert v["verdict"] != "PASS"
    assert 55 <= v["detail"]["fps_p50"] <= 65
    assert v["detail"]["headless"] is True
    assert v["detail"]["label"] == "HEADLESS"


def test_perf_no_data_too_few_frames():
    v = check_perf([1.0], [10])
    assert v["verdict"] == "NO-DATA", v


def test_perf_no_data_scene_not_ready():
    # Hardening case: even with plenty of frame timestamps and draw calls,
    # scene_ready=False must short-circuit straight to NO-DATA/HEADLESS --
    # this is exactly the 2026-09-14 INVALID-run shape (frames kept ticking
    # while the page never actually mounted the real scene).
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [100, 110, 105], scene_ready=False)
    assert v["verdict"] == "NO-DATA", v
    assert v["detail"]["label"] == "HEADLESS"


def test_perf_no_data_without_draw_calls():
    # Hardening case: frames measured fine, but window.__hqGl never got
    # populated (all calls samples None) -- this is the UltraCanvasRoot.tsx
    # bug this same pass fixes in the app; the probe must never call this
    # PASS just because frames existed.
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [None, None, None])
    assert v["verdict"] == "NO-DATA", v
    assert v["detail"]["label"] == "HEADLESS"
    assert "draw-call" in v["detail"]["reason"]


def test_perf_headless_info_requires_draw_calls_present():
    # Sanity companion to the above: with scene_ready + frames + at least
    # one real draw-call sample, verdict advances past NO-DATA to INFO
    # (headless default) -- draw-call reason above isn't just permanently
    # disabling the check.
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [None, 100, None])
    assert v["verdict"] == "INFO", v
    assert v["detail"]["draw_call_samples"] == 1


def test_perf_real_gpu_pass_meets_thresholds():
    # Non-headless run: fps_p50 >= 58, p95 frame time <= 17ms, draw calls
    # sampled -> PASS. 60fps steady (16.667ms deltas) clears both bars.
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [100, 110, 105], headless=False)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["headless"] is False
    assert v["detail"]["label"] == "GPU"
    assert v["detail"]["fps_p50"] >= 58
    assert v["detail"]["p95_frame_time_ms"] <= 17


def test_perf_real_gpu_fail_below_thresholds():
    # Non-headless run well below the fps/frame-time bar -> FAIL, not the
    # old unconditional PASS.
    frames = [i * 100.0 for i in range(60)]  # 10fps steady, 100ms deltas
    v = check_perf(frames, [100, 110, 105], headless=False)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["fps_p50"] < 58


def test_perf_real_gpu_no_data_still_no_data():
    # Missing-data short-circuits (scene not ready / too few frames / no
    # draw calls) apply regardless of environment -- never FAIL on absence
    # of data, and never PASS either.
    v = check_perf([1.0], [10], headless=False)
    assert v["verdict"] == "NO-DATA", v
    v2 = check_perf([i * 16.667 for i in range(120)], [None, None, None], headless=False)
    assert v2["verdict"] == "NO-DATA", v2


# perf_headless_flag -- single source of truth for live vs rescore ------------------
# 2026-09-15 bug: hq_live_probe.py's live path derived headless from
# `not diag.get("gl_is_hardware", False)`, its --rescore path derived it from
# `diag.get("headless", True)` (a literal always-True field unrelated to GL
# backend) -- two different rules for the same parameter. A real hardware-GL
# run (gl_is_hardware True, live-verified perf PASS) rescored as perf
# INFO/"SwiftShader numbers", which was false. perf_headless_flag is now the
# ONE function both paths call.

def test_perf_headless_flag_hardware_true_means_not_headless():
    is_headless, reason = perf_headless_flag({"gl_is_hardware": True})
    assert is_headless is False, (is_headless, reason)
    assert reason is None


def test_perf_headless_flag_software_gl_means_headless():
    is_headless, reason = perf_headless_flag({"gl_is_hardware": False})
    assert is_headless is True, (is_headless, reason)
    assert reason is None


def test_perf_headless_flag_missing_field_is_unknown_not_defaulted():
    # Must NEVER default to True or False -- an older samples file that
    # predates gl_is_hardware being recorded has no basis for either.
    is_headless, reason = perf_headless_flag({})
    assert is_headless is None, is_headless
    assert reason == "gl backend not recorded"
    is_headless2, reason2 = perf_headless_flag({"gl_is_hardware": None})
    assert is_headless2 is None, is_headless2
    assert reason2 == "gl backend not recorded"


def test_check_perf_headless_none_is_no_data_never_info_or_pass():
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [100, 110, 105], headless=None)
    assert v["verdict"] == "NO-DATA", v
    assert v["detail"]["reason"] == "gl backend not recorded"
    assert v["verdict"] not in ("INFO", "PASS")


def test_rescore_matches_live_verdicts_for_hardware_gl_run(tmp_path, capsys):
    """The exact 2026-09-15 bug this pass fixes: a live hardware-GL run
    (gl_is_hardware True) rescored from its own samples.json.gz must
    reproduce the SAME full build_verdicts dict the live path would compute
    from the same diag -- perf included, PASS/FAIL on real-GPU thresholds,
    never INFO/SwiftShader."""
    import importlib
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")
    importlib.reload(hq_live_probe)

    samples = [
        _s(0, page=[], api=[], calls=100),
        _s(500, page=[], api=[{"id": "a1"}], calls=100),
        _s(1000, page=[_agent("a1", "walking", [0, 0])], api=[{"id": "a1"}], calls=100),
        _s(1500, page=[_agent("a1", "walking", [0.5, 0])], api=[{"id": "a1"}], calls=100),
    ]
    frame_ts = [i * 16.667 for i in range(120)]  # steady 60fps
    build_ids = ["build-hw"] * 5
    diag = {
        "scene_ready": True,
        "gl_is_hardware": True,
        "gl_renderer": "NVIDIA GeForce RTX 5080/PCIe/SSE2",
        "gl_backend": "hardware (ANGLE/D3D11, NVIDIA)",
        "build_id_start": "build-hw",
    }

    # "Live" verdict: exactly the call shape write_partial/main() use.
    live_headless, live_reason = perf_headless_flag(diag)
    assert live_reason is None
    live_verdicts = build_verdicts(
        samples, frame_ts, calls_samples=[s.get("calls") for s in samples],
        scene_ready=True, build_ids=build_ids, headless=live_headless,
    )
    assert live_verdicts["perf"]["verdict"] in ("PASS", "FAIL"), live_verdicts["perf"]

    gz_path = tmp_path / "20260915T070024Z-build_hw.samples.json.gz"
    hq_live_probe.write_samples_gz(
        gz_path, "2026-09-15T07:00:24Z", "http://x/hq?diag=1&tier=ultra",
        diag, samples, frame_ts, build_ids,
    )

    exit_code = hq_live_probe.rescore(gz_path)
    report = _json.loads(capsys.readouterr().out)

    assert report["environment"]["gl_is_hardware"] is True
    assert report["gl_backend_recorded"] is True
    assert report["verdicts"] == live_verdicts, (report["verdicts"], live_verdicts)
    assert report["verdicts"]["perf"]["verdict"] == live_verdicts["perf"]["verdict"]
    assert "SwiftShader" not in _json.dumps(report["verdicts"]["perf"]["detail"])
    assert exit_code in (0, 2)


def test_rescore_no_data_when_gl_fields_missing(tmp_path, capsys):
    """Older samples file predating gl_is_hardware -- rescore must never
    silently report perf INFO or PASS; it's NO-DATA with an explicit reason."""
    import importlib
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")
    importlib.reload(hq_live_probe)

    samples = [_s(0, calls=100), _s(500, calls=100)]
    frame_ts = [i * 16.667 for i in range(120)]
    diag = {"scene_ready": True, "build_id_start": "build-old"}  # no gl_is_hardware
    gz_path = tmp_path / "old.samples.json.gz"
    hq_live_probe.write_samples_gz(
        gz_path, "2026-09-01T00:00:00Z", "http://x/hq", diag, samples, frame_ts,
        ["build-old", "build-old"],
    )

    hq_live_probe.rescore(gz_path)
    report = _json.loads(capsys.readouterr().out)
    assert report["gl_backend_recorded"] is False
    assert report["verdicts"]["perf"]["verdict"] == "NO-DATA"
    assert report["verdicts"]["perf"]["detail"]["reason"] == "gl backend not recorded"


# motion-check fps gating -----------------------------------------------------------
# 2026-09-15: fps_p50 0.71 (headless SwiftShader) produced walk_speed FAIL
# (143/150 out-of-band), stand_slots FAIL (walking agents counted as slot
# occupants), and an unjudgeable walk_out FAIL -- all measurement artifacts
# of a too-slow renderer, not real bugs. Below MOTION_MIN_FPS_P50 these three
# checks must report NO-DATA instead of PASS/FAIL/whatever they'd otherwise
# compute. spawn_latency, page_api_parity, and bubbles are NOT position-based
# and must NOT be gated.

def _low_fps_frames():
    # ~0.7 fps: 1400ms between frames.
    return [i * 1400.0 for i in range(10)]


def _high_fps_frames():
    return [i * 16.667 for i in range(120)]  # steady 60fps


def test_motion_checks_no_data_below_fps_gate():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])], api=[{"id": "a1"}]),
        _s(500, page=[_agent("a1", "walking", [5, 0])], api=[{"id": "a1"}]),  # 10 u/s -- would FAIL walk_speed ungated
    ]
    out = build_verdicts(samples, _low_fps_frames(), calls_samples=[100, 100], scene_ready=True, build_ids=["b", "b"])
    assert out["run_valid"] is True, out
    for key in ("walk_speed", "stand_slots", "walker_separation", "waiting_separation", "walk_out", "label_overlap"):
        assert out[key]["verdict"] == "NO-DATA", (key, out[key])
        assert "fps too low" in out[key]["detail"]["reason"]
    # not gated -- these have nothing to do with position/motion sampling
    assert out["page_api_parity"]["verdict"] in ("PASS", "FAIL", "NO-DATA")


def test_motion_checks_run_normally_above_fps_gate():
    # 0.35u / 0.5s = 0.7 u/s -- matches the 0.7 u/s design speed. Extended
    # to 2.0s total so a full speed_window_s window can form.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])], api=[{"id": "a1"}]),
        _s(500, page=[_agent("a1", "walking", [0.35, 0])], api=[{"id": "a1"}]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])], api=[{"id": "a1"}]),
        _s(1500, page=[_agent("a1", "walking", [1.05, 0])], api=[{"id": "a1"}]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0])], api=[{"id": "a1"}]),
    ]
    out = build_verdicts(samples, _high_fps_frames(), calls_samples=[100] * 5, scene_ready=True, build_ids=["b"] * 5)
    assert out["walk_speed"]["verdict"] == "PASS", out["walk_speed"]
    assert "reason" not in out["walk_speed"]["detail"] or "fps too low" not in out["walk_speed"]["detail"].get("reason", "")


def test_motion_checks_ungated_when_no_frame_data():
    # No frame_timestamps_ms at all -- fps_p50 is unknown (None), not "low".
    # Must NOT gate (an unknown fps is not evidence it was too low); the
    # individual checks run on their own NO-DATA/PASS/FAIL logic. Extended
    # to 2.0s total so a full speed_window_s window can form.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])], api=[{"id": "a1"}]),
        _s(500, page=[_agent("a1", "walking", [0.35, 0])], api=[{"id": "a1"}]),
        _s(1000, page=[_agent("a1", "walking", [0.7, 0])], api=[{"id": "a1"}]),
        _s(1500, page=[_agent("a1", "walking", [1.05, 0])], api=[{"id": "a1"}]),
        _s(2000, page=[_agent("a1", "walking", [1.4, 0])], api=[{"id": "a1"}]),
    ]
    out = build_verdicts(samples, [], calls_samples=[None] * 5, scene_ready=True, build_ids=["b"] * 5)
    assert out["walk_speed"]["verdict"] == "PASS", out["walk_speed"]


# walk_speed: windowing naturally absorbs repeated/flat positions -----------------
# The old per-tick "bridge across repeated positions" special case is gone --
# windowing supersedes it FOR REALISTIC quantization magnitudes (a same-
# position tick just contributes 0 distance to a window's cumulative sum,
# which the window's other ticks average out -- see the 250ms/500ms
# aliasing test above). A single-tick catch-up jump LARGE enough to imply
# several skipped render frames is, correctly, still caught as a teleport
# below -- that scenario belongs to the separate MOTION_MIN_FPS_P50 gate
# one layer up in build_verdicts, not to windowed averaging here.

def test_walk_speed_fails_when_position_never_changes_across_a_full_window():
    # A walking/leaving agent that never actually moves for a whole
    # speed_window_s window is a real stuck-agent bug (or a render rate so
    # slow it should have been caught by the MOTION_MIN_FPS_P50 gate one
    # layer up in build_verdicts) -- must FAIL on 0 u/s, not be silently
    # swallowed as NO-DATA.
    samples = [
        _s(0, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(500, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(1500, page=[_agent("a1", "walking", [0.0, 0])]),
        _s(2000, page=[_agent("a1", "walking", [0.0, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["window_count"] == 1
    assert v["detail"]["median_speed_by_agent"]["a1"] == 0.0


# stand_slots: only 'working' agents count, walking/leaving are transit -----------

def test_stand_slots_ignores_walking_agent_mid_step():
    # a1 settled at zone-a ("working"); a2 is still walking toward zone-a
    # and happens to be very close to a1 mid-step -- this must NOT count as
    # a slot collision, it's transit.
    samples = [_s(0, page=[
        _agent("a1", "working", [0, 0], target="zone-a"),
        _agent("a2", "walking", [0.05, 0], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "NO-DATA", v  # only 1 'working' agent at this target


def test_stand_slots_still_fails_two_working_agents_too_close():
    samples = [_s(0, page=[
        _agent("a1", "working", [0, 0], target="zone-a"),
        _agent("a2", "working", [0.05, 0], target="zone-a"),
    ])]
    v = check_stand_slots(samples)
    assert v["verdict"] == "FAIL", v


# run validity ----------------------------------------------------------------------

def test_run_validity_pass_stable_build():
    v = check_run_validity(["abc123", "abc123", "abc123"], scene_ready=True)
    assert v["valid"] is True, v
    assert v["reasons"] == []


def test_run_invalid_on_build_change():
    # The actual 2026-09-14 failure signature: another builder's deploy
    # rewrote BUILD_ID mid-run.
    v = check_run_validity(["old-build", "old-build", "new-build"], scene_ready=True)
    assert v["valid"] is False, v
    assert any("build_id changed" in r for r in v["reasons"])


def test_run_invalid_on_scene_not_ready():
    v = check_run_validity(["abc123", "abc123"], scene_ready=False)
    assert v["valid"] is False, v
    assert any("scene_ready" in r for r in v["reasons"])


def test_build_verdicts_invalid_on_build_change_never_passes_perf():
    samples = [_s(0), _s(500)]
    frames = [i * 16.667 for i in range(120)]
    out = build_verdicts(
        samples, frames, calls_samples=[100, 110], scene_ready=True,
        build_ids=["build-a", "build-a", "build-b"],
    )
    assert out["run_valid"] is False, out
    assert out["perf"]["verdict"] == "NO-DATA", out["perf"]
    for key in (
        "spawn_latency", "walk_speed", "stand_slots", "walker_separation",
        "waiting_separation", "walk_out", "label_overlap", "page_api_parity", "bubbles",
    ):
        assert out[key]["verdict"] == "NO-DATA", (key, out[key])


def test_build_verdicts_invalid_on_scene_not_ready_never_passes_perf():
    samples = [_s(0), _s(500)]
    frames = [i * 16.667 for i in range(120)]
    out = build_verdicts(
        samples, frames, calls_samples=[100, 110], scene_ready=False,
        build_ids=["build-a", "build-a"],
    )
    assert out["run_valid"] is False, out
    assert out["perf"]["verdict"] == "NO-DATA", out["perf"]


# build_verdicts smoke ------------------------------------------------------------------

def test_build_verdicts_shape():
    samples = [_s(0), _s(500)]
    out = build_verdicts(samples, [0.0, 16.0, 32.0])
    expected_keys = {
        "spawn_latency", "walk_speed", "stand_slots", "walk_out",
        "page_api_parity", "bubbles", "perf",
    }
    assert expected_keys <= set(out.keys())
    assert "run_valid" in out and "invalid_reasons" in out
    for key in expected_keys:
        assert out[key]["verdict"] in ("PASS", "FAIL", "NO-DATA", "INFO")


# raw-sample round-trip + retention (hq_live_probe.py, not hq_probe_lib.py) --------

def test_rescore_roundtrip_matches_original_verdicts(tmp_path):
    """write_samples_gz -> rescore() on the same data must reproduce
    build_verdicts' output exactly (same logic, same inputs)."""
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")

    samples = [
        _s(0, page=[], api=[]),
        _s(500, page=[], api=[{"id": "a1"}]),
        _s(1000, page=[_agent("a1", "walking", [0, 0])], api=[{"id": "a1"}]),
        _s(1500, page=[_agent("a1", "walking", [0.5, 0])], api=[{"id": "a1"}]),
    ]
    frame_ts = [i * 16.667 for i in range(120)]
    build_ids = ["build-x", "build-x", "build-x", "build-x", "build-x"]
    diag = {"scene_ready": True, "headless": True, "build_id_start": "build-x"}

    expected = build_verdicts(
        samples, frame_ts, calls_samples=[s.get("calls") for s in samples],
        scene_ready=True, build_ids=build_ids, headless=True,
    )

    gz_path = tmp_path / "20260914T000000Z-build_x.samples.json.gz"
    hq_live_probe.write_samples_gz(
        gz_path, "2026-09-14T00:00:00Z", "http://x/hq", diag, samples, frame_ts, build_ids,
    )
    assert gz_path.exists()

    payload = hq_live_probe.load_samples_gz(gz_path)
    got = build_verdicts(
        payload["samples"], payload["frame_timestamps_ms"],
        calls_samples=[s.get("calls") for s in payload["samples"]],
        scene_ready=payload["environment"].get("scene_ready", False),
        build_ids=payload["build_ids"],
        headless=payload["environment"].get("headless", True),
    )
    assert got == expected, (got, expected)


def test_rescore_cli_path_prints_verdicts(tmp_path, capsys):
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")

    samples = [_s(0), _s(500)]
    diag = {"scene_ready": True, "headless": True, "build_id_start": "build-y"}
    gz_path = tmp_path / "run.samples.json.gz"
    hq_live_probe.write_samples_gz(
        gz_path, "2026-09-14T00:00:00Z", "http://x/hq", diag, samples, [0.0, 16.0], ["build-y", "build-y"],
    )

    exit_code = hq_live_probe.rescore(gz_path)
    out = capsys.readouterr().out
    report = __import__("json").loads(out)
    assert report["rescored"] is True
    assert report["source_file"] == str(gz_path)
    assert "verdicts" in report
    assert exit_code in (0, 2)


def test_rescore_never_imports_playwright(tmp_path, monkeypatch):
    """rescore() must not touch playwright at all -- guard against a future
    change accidentally launching a browser on the rescore path."""
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")

    # Poison playwright.sync_api so any attempt to import/use it blows up
    # loudly instead of silently launching a real browser.
    class _PoisonedModule:
        def __getattr__(self, name):
            raise AssertionError(f"rescore() must never touch playwright (accessed {name!r})")

    monkeypatch.setitem(_sys.modules, "playwright", _PoisonedModule())
    monkeypatch.setitem(_sys.modules, "playwright.sync_api", _PoisonedModule())

    samples = [_s(0), _s(500)]
    diag = {"scene_ready": True, "headless": True, "build_id_start": "build-z"}
    gz_path = tmp_path / "run.samples.json.gz"
    hq_live_probe.write_samples_gz(
        gz_path, "2026-09-14T00:00:00Z", "http://x/hq", diag, samples, [0.0, 16.0], ["build-z", "build-z"],
    )

    # Must not raise -- proves rescore() never imported the poisoned modules.
    hq_live_probe.rescore(gz_path)


def test_retention_keeps_newest_20(tmp_path):
    import importlib
    import sys as _sys
    import time as _time
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")

    for i in range(25):
        p = tmp_path / f"file-{i:02d}.samples.json.gz"
        p.write_bytes(b"x")
        # force distinct, increasing mtimes regardless of filesystem clock granularity
        mtime = _time.time() + i
        import os
        os.utime(p, (mtime, mtime))

    deleted = hq_live_probe.enforce_samples_retention(tmp_path, keep=20)
    remaining = sorted(tmp_path.glob("*.samples.json.gz"))
    assert len(remaining) == 20, remaining
    assert len(deleted) == 5
    # the 5 oldest (file-00..file-04) must be the ones removed
    remaining_names = {p.name for p in remaining}
    for i in range(5):
        assert f"file-{i:02d}.samples.json.gz" not in remaining_names
    for i in range(5, 25):
        assert f"file-{i:02d}.samples.json.gz" in remaining_names


# run_started_utc bookkeeping: filename stamp must equal the JSON's value ----------

def test_launch_and_probe_run_started_utc_matches_samples_filename(tmp_path, monkeypatch):
    """2026-09-15 bug: the samples.json.gz filename stamp (20260915T064629Z)
    and the final report's run_started_utc (2026-09-15T06:50:37Z) were 4+
    minutes apart for the SAME run, because main() re-captured its own
    timestamp AFTER the run finished instead of reusing the one
    launch_and_probe captured at the start (and used for the filename).
    Fakes out playwright entirely -- no real browser -- to exercise
    launch_and_probe's actual timestamp plumbing end to end."""
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")
    importlib.reload(hq_live_probe)

    class _FakePage:
        def evaluate(self, script, *a, **kw):
            if "pageAgents" in script:  # SAMPLE_SCRIPT
                return {"pageAgents": [], "apiAgents": [], "apiError": None, "calls": 100, "buildId": "fake-build-id", "documentHidden": False}
            if "UNMASKED_RENDERER" in script:
                return "NVIDIA GeForce RTX 5080/PCIe/SSE2"
            if "build_id" in script:  # FETCH_BUILD_ID_SCRIPT
                return "fake-build-id"
            if "webgl2" in script:
                return True
            if "__hqGl" in script:
                return True
            if "document.hidden" in script:
                return False
            if "mode" in script:
                return "diag"
            if "__probeRaf" in script:
                return [i * 16.667 for i in range(30)]
            return None

        def add_init_script(self, *a, **kw):
            pass

        def on(self, *a, **kw):
            pass

        def goto(self, *a, **kw):
            pass

        def wait_for_function(self, *a, **kw):
            pass

        def wait_for_timeout(self, *a, **kw):
            pass

    class _FakeContext:
        def new_page(self):
            return _FakePage()

        def close(self):
            pass

    class _FakeBrowser:
        def new_context(self, *a, **kw):
            return _FakeContext()

        def close(self):
            pass

    class _FakeChromium:
        def launch(self, *a, **kw):
            return _FakeBrowser()

    class _FakePlaywrightCtx:
        chromium = _FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hq_live_probe, "SAMPLE_RUNS_DIR", tmp_path)
    _orig_gz_path = hq_live_probe.samples_gz_path_for_run
    monkeypatch.setattr(
        hq_live_probe, "samples_gz_path_for_run",
        lambda fs_safe, build_id, runs_dir=tmp_path: _orig_gz_path(fs_safe, build_id, runs_dir=tmp_path),
    )

    import types as _types
    fake_sync_api = _types.SimpleNamespace(sync_playwright=lambda: _FakePlaywrightCtx())
    monkeypatch.setitem(_sys.modules, "playwright.sync_api", fake_sync_api)

    out_path = tmp_path / "hq-probe-latest.json"
    run = hq_live_probe.launch_and_probe(
        "http://127.0.0.1:3000/hq?diag=1&tier=ultra", seconds=1, interval_ms=500,
        out_path=out_path, scene_wait_ms=1000,
    )

    assert "run_started_utc" in run
    gz_files = list(tmp_path.glob("*.samples.json.gz"))
    assert len(gz_files) == 1, gz_files
    fs_safe_from_filename = gz_files[0].name.split("-")[0]
    fs_safe_from_run = __import__("time").strftime(
        "%Y%m%dT%H%M%SZ",
        __import__("time").strptime(run["run_started_utc"], "%Y-%m-%dT%H:%M:%SZ"),
    )
    assert fs_safe_from_filename == fs_safe_from_run, (fs_safe_from_filename, fs_safe_from_run, run["run_started_utc"])
    assert run["diag"]["gl_is_hardware"] is True
    assert "NVIDIA" in run["diag"]["gl_renderer"]


def test_retention_noop_when_under_cap(tmp_path):
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    hq_live_probe = importlib.import_module("hq_live_probe")

    for i in range(5):
        (tmp_path / f"file-{i}.samples.json.gz").write_bytes(b"x")

    deleted = hq_live_probe.enforce_samples_retention(tmp_path, keep=20)
    assert deleted == []
    assert len(list(tmp_path.glob("*.samples.json.gz"))) == 5


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
