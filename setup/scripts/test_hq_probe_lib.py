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
    check_run_validity,
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


def test_walk_out_fail_when_leaving_at_least_20s_without_despawn():
    # Same shape as the window-end case but past the 20s grace -- now a
    # genuine FAIL, not an artifact.
    samples = [
        _s(0, page=[_agent("a1", "leaving", [5, 0])]),
        _s(1000, page=[_agent("a1", "leaving", [3, 0])]),
        _s(20000, page=[_agent("a1", "leaving", [3, 0])]),  # window ends here
    ]
    v = check_walk_out(samples)
    assert v["verdict"] == "FAIL", v
    assert v["detail"]["per_agent"]["a1"]["status"] == "FAIL"
    assert v["detail"]["per_agent"]["a1"]["leave_started_offset_s"] == 20.0


def test_walk_out_mixed_no_data_and_pass():
    # One agent despawns cleanly (PASS), another starts leaving only 5s
    # before the window ends (NO-DATA for that agent) -- overall verdict is
    # PASS since nothing actually FAILed.
    samples = [
        _s(0, page=[
            _agent("a1", "leaving", [5, 0]),
        ]),
        _s(1000, page=[
            _agent("a1", "leaving", [3, 0]),
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
    for key in ("spawn_latency", "walk_speed", "stand_slots", "walk_out", "page_api_parity", "bubbles"):
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
