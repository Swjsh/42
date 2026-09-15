"""Unit tests for hq_probe_lib.py's pure verdict logic -- synthetic sample
arrays only, no browser, no network. Run: python -m pytest setup/scripts/test_hq_probe_lib.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hq_probe_lib import (  # noqa: E402
    build_verdicts,
    check_bubbles,
    check_page_api_parity,
    check_perf,
    check_spawn_latency,
    check_stand_slots,
    check_walk_out,
    check_walk_speed,
)


def _s(t_ms, page=None, api=None, calls=None):
    return {"t_ms": t_ms, "page_agents": page or [], "api_agents": api or [], "calls": calls}


def _agent(id_, state, pos, target="zone-a", bubble="working · x", raw="working · x", onWalkable=True):
    return {"id": id_, "label": id_, "state": state, "pos": pos, "target": target,
            "bubble": bubble, "rawDetail": raw, "onWalkable": onWalkable, "bubbleOpacity": 1}


# 1. spawn latency ------------------------------------------------------------

def test_spawn_latency_pass_within_one_interval():
    samples = [
        _s(0, page=[], api=[]),
        _s(500, page=[], api=[{"id": "a1"}]),
        _s(1000, page=[_agent("a1", "spawning", [0, 0])], api=[{"id": "a1"}]),
    ]
    v = check_spawn_latency(samples)
    assert v["verdict"] == "PASS", v
    assert v["detail"]["spawn_count"] == 1


def test_spawn_latency_fail_when_late():
    samples = [
        _s(0, page=[], api=[]),
        _s(500, page=[], api=[{"id": "a1"}]),
        _s(1000, page=[], api=[{"id": "a1"}]),
        _s(1500, page=[], api=[{"id": "a1"}]),
        _s(2000, page=[_agent("a1", "spawning", [0, 0])], api=[{"id": "a1"}]),
    ]
    v = check_spawn_latency(samples)
    assert v["verdict"] == "FAIL", v


def test_spawn_latency_no_data_when_nobody_spawns():
    samples = [_s(0), _s(500), _s(1000)]
    v = check_spawn_latency(samples)
    assert v["verdict"] == "NO-DATA", v


# 2. walk speed ----------------------------------------------------------------

def test_walk_speed_pass_in_band():
    # 0.5 units in 1s = 0.5 u/s, within [0.3, 1.0]
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [0.5, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "PASS", v


def test_walk_speed_fail_too_fast():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0])]),
        _s(1000, page=[_agent("a1", "walking", [5, 0])]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v


def test_walk_speed_fail_unwalkable():
    samples = [
        _s(0, page=[_agent("a1", "walking", [0, 0], onWalkable=False)]),
        _s(1000, page=[_agent("a1", "walking", [0.5, 0], onWalkable=False)]),
    ]
    v = check_walk_speed(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["unwalkable_hits"] > 0


def test_walk_speed_no_data():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0])])]
    v = check_walk_speed(samples)
    assert v["verdict"] == "NO-DATA", v


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


# 4. walk-out ---------------------------------------------------------------------

def test_walk_out_pass():
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [3, 0])]),
        _s(2000, page=[]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "PASS", v


def test_walk_out_fail_never_gone():
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [3, 0])]),
        _s(20000, page=[_agent("a1", "leaving", [3, 0])]),
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "FAIL", v


def test_walk_out_no_data():
    samples = [_s(0, page=[_agent("a1", "working", [0, 0])])]
    v = check_walk_out(samples)
    assert v["verdict"] == "NO-DATA", v


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
    samples = [_s(0, page=[_agent(
        "a1", "working", [0, 0],
        bubble="working · x", raw="Ran: cd /c/Users/jackw && ls",
    )])]
    v = check_bubbles(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["leak_count"] == 1


def test_bubbles_no_data():
    samples = [_s(0, page=[])]
    v = check_bubbles(samples)
    assert v["verdict"] == "NO-DATA", v


# 7. perf -----------------------------------------------------------------------------

def test_perf_pass_computes_fps():
    # 60fps steady -> 16.67ms deltas
    frames = [i * 16.667 for i in range(120)]
    v = check_perf(frames, [100, 110, 105])
    assert v["verdict"] == "PASS", v
    assert 55 <= v["detail"]["fps_p50"] <= 65
    assert v["detail"]["headless"] is True


def test_perf_no_data_too_few_frames():
    v = check_perf([1.0], [10])
    assert v["verdict"] == "NO-DATA", v


# build_verdicts smoke ------------------------------------------------------------------

def test_build_verdicts_shape():
    samples = [_s(0), _s(500)]
    out = build_verdicts(samples, [0.0, 16.0, 32.0])
    assert set(out.keys()) == {
        "spawn_latency", "walk_speed", "stand_slots", "walk_out",
        "page_api_parity", "bubbles", "perf",
    }
    for v in out.values():
        assert v["verdict"] in ("PASS", "FAIL", "NO-DATA")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
