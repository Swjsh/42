"""Guards for setup/scripts/live_watch_trendlines_brief.py -- the WS8->WS7 READ-SIDE
MERGE compact text renderer (2026-08-01, WEEKEND-TWELVE Next-Twelve #11).

Pins the two load-bearing invariants:
  1. ADDITIVE-ONLY: merging trendlines must never mutate the input snapshot, and the base
     render_brief() text must be byte-for-byte unchanged when trendlines are absent --
     this is a pure ADD, never a rewrite of the WS7 surface.
  2. NEVER TOUCHES live_watch.py: this module only IMPORTS live_watch.render_brief (a
     pure function) -- it must never import anything that writes live-watch.json, and
     live_watch.py's own mtime must be untouched by running this module (mirrors the
     existing theta-clock read-only-link-in guard convention in test_live_watch.py).

Pure-logic + tmp_path only where filesystem is involved -- no network, no live state
mutated (this module has no write mode at all).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
for _p in (str(SCRIPTS),):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _mod():
    return importlib.import_module("live_watch_trendlines_brief")


def _live_watch():
    return importlib.import_module("live_watch")


CLOSED_SNAP = {
    "schema_version": 1, "written_at_et": "2026-08-01T12:53:46",
    "market_state": "CLOSED", "in_trade_count": 0, "arms": {}, "errors": [],
}

RTH_SNAP = {
    "schema_version": 1, "written_at_et": "2026-08-03T10:15:00",
    "market_state": "RTH", "spy": {"last": 746.79}, "in_trade_count": 0,
    "arms": {
        "safe-2": {
            "display_name": "CORE-SAFE (KIQE)", "in_trade": False,
            "position": None,
            "last_decision": {"verdict": "HOLD", "reason": "no trigger", "age_min": 2.0},
            "kill_switch": {"tripped": False}, "status": "ok",
        },
    },
    "errors": [],
}

TL_TWO_ACTIVE = {
    "schema_version": 1, "ts_et": "2026-08-01T12:52:04", "n_total": 4, "n_active": 2,
    "last_close": 746.79,
    "nearest_active": {
        "kind": "support", "flavor": "body", "status": "TESTING",
        "current_value": 746.79, "distance_dollars": 0.0, "side": "below",
    },
    "last_break": {
        "kind": "resistance", "flavor": "body", "level": 746.34,
        "ts_et": "2026-07-31T15:20:03",
    },
}

TL_ZERO_ACTIVE = {
    "schema_version": 1, "ts_et": "2026-08-01T12:52:04", "n_total": 4, "n_active": 0,
}


# --------------------------------------------------------------------------- #
# 1. merge_trendlines -- pure, additive, non-mutating
# --------------------------------------------------------------------------- #
def test_merge_adds_additive_key():
    m = _mod()
    merged = m.merge_trendlines(RTH_SNAP, TL_TWO_ACTIVE)
    assert merged["trendlines"] == TL_TWO_ACTIVE
    # everything else carried through unchanged
    for k, v in RTH_SNAP.items():
        assert merged[k] == v


def test_merge_never_mutates_the_input_snapshot():
    """RED-PROOF: the original dict object must be untouched -- immutable update, not an
    in-place mutation (this repo's own coding-style rule)."""
    m = _mod()
    original = dict(RTH_SNAP)  # shallow copy to compare against post-call
    m.merge_trendlines(RTH_SNAP, TL_TWO_ACTIVE)
    assert RTH_SNAP == original, "merge_trendlines must not mutate its snap argument"
    assert "trendlines" not in RTH_SNAP, "the additive key must land on the COPY, not the original"


def test_merge_none_snap_passes_through_none():
    m = _mod()
    assert m.merge_trendlines(None, TL_TWO_ACTIVE) is None


def test_merge_returns_a_new_object_not_the_same_reference():
    m = _mod()
    merged = m.merge_trendlines(RTH_SNAP, TL_TWO_ACTIVE)
    assert merged is not RTH_SNAP


# --------------------------------------------------------------------------- #
# 2. render_trendline_summary -- terse, fail-open
# --------------------------------------------------------------------------- #
def test_summary_none_when_trendlines_missing():
    m = _mod()
    assert m.render_trendline_summary(None) is None


def test_summary_none_when_not_a_dict():
    m = _mod()
    assert m.render_trendline_summary("garbled") is None


def test_summary_none_when_zero_active():
    m = _mod()
    assert m.render_trendline_summary(TL_ZERO_ACTIVE) is None


def test_summary_formats_nearest_and_last_break():
    m = _mod()
    s = m.render_trendline_summary(TL_TWO_ACTIVE)
    assert s is not None
    assert "trendlines: 2/4 active" in s
    assert "nearest support[body] 746.79" in s
    assert "0.00 below" in s
    assert "TESTING" in s
    assert "last break resistance[body] 746.34" in s
    assert "@ 15:20" in s


def test_summary_tolerates_missing_nearest_and_break():
    m = _mod()
    s = m.render_trendline_summary({"n_active": 1, "n_total": 3})
    assert s == "trendlines: 1/3 active"


# --------------------------------------------------------------------------- #
# 3. render_brief_with_trendlines -- the compact text renderer, additive-only
# --------------------------------------------------------------------------- #
def test_bite_no_trendlines_output_byte_identical_to_base_render_brief():
    """RED-PROOF / non-vacuous: with trendlines=None, the merged renderer's output must
    be EXACTLY live_watch.render_brief(snap) -- zero bytes added. Proves the merge is
    purely additive, never a rewrite of the base WS7 surface."""
    m = _mod()
    lw = _live_watch()
    assert m.render_brief_with_trendlines(RTH_SNAP, None) == lw.render_brief(RTH_SNAP)
    assert m.render_brief_with_trendlines(CLOSED_SNAP, None) == lw.render_brief(CLOSED_SNAP)


def test_bite_zero_active_trendlines_also_byte_identical_to_base():
    """Same non-vacuous proof, but with a real (non-None) trendlines payload that simply
    has nothing active -- must still add nothing."""
    m = _mod()
    lw = _live_watch()
    assert m.render_brief_with_trendlines(RTH_SNAP, TL_ZERO_ACTIVE) == lw.render_brief(RTH_SNAP)


def test_with_active_trendlines_appends_exactly_one_line():
    m = _mod()
    lw = _live_watch()
    base = lw.render_brief(CLOSED_SNAP)
    merged_text = m.render_brief_with_trendlines(CLOSED_SNAP, TL_TWO_ACTIVE)
    assert merged_text.startswith(base + "\n")
    assert merged_text.count("\n") == base.count("\n") + 1


def test_with_active_trendlines_on_rth_snap_with_arms():
    m = _mod()
    lw = _live_watch()
    base = lw.render_brief(RTH_SNAP)
    merged_text = m.render_brief_with_trendlines(RTH_SNAP, TL_TWO_ACTIVE)
    assert merged_text.startswith(base + "\n")
    assert "trendlines: 2/4 active" in merged_text


def test_no_snapshot_still_renders_gracefully():
    """Independent reads, independent failure modes (matches the API route's contract):
    a missing live-watch.json must not suppress trendline context that WAS read fine --
    the merged renderer appends the trendline line onto the base 'no snapshot' message."""
    m = _mod()
    lw = _live_watch()
    base = lw.render_brief(None)
    merged_text = m.render_brief_with_trendlines(None, TL_TWO_ACTIVE)
    assert merged_text.startswith(base + "\n")
    assert "trendlines: 2/4 active" in merged_text


def test_no_snapshot_and_no_trendlines_is_byte_identical_to_base():
    m = _mod()
    lw = _live_watch()
    assert m.render_brief_with_trendlines(None, None) == lw.render_brief(None)


# --------------------------------------------------------------------------- #
# 4. never touches live_watch.py (the lane boundary)
# --------------------------------------------------------------------------- #
def test_never_imports_a_write_path_from_live_watch():
    """This module's only live_watch dependency is the pure render_brief function --
    grep-level pin so a future edit can't silently start calling run_once/main from
    live_watch (which would blur the 'never touches the writer' boundary)."""
    src = (SCRIPTS / "live_watch_trendlines_brief.py").read_text(encoding="utf-8")
    assert "live_watch.render_brief" in src
    assert "live_watch.run_once" not in src
    assert "live_watch.main(" not in src


def test_running_this_module_does_not_modify_live_watch_py_mtime(tmp_path, monkeypatch):
    """RED-PROOF: running the merged renderer must leave setup/scripts/live_watch.py
    byte-for-byte and mtime-for-mtime untouched -- the lane-boundary invariant, mirrored
    from test_live_watch.py's existing theta-clock read-only-link-in guard."""
    lw_path = SCRIPTS / "live_watch.py"
    before_mtime = lw_path.stat().st_mtime_ns
    before_bytes = lw_path.read_bytes()

    live_path = tmp_path / "live-watch.json"
    tl_path = tmp_path / "trendline-watch.json"
    live_path.write_text(json.dumps(CLOSED_SNAP), encoding="utf-8")
    tl_path.write_text(json.dumps(TL_TWO_ACTIVE), encoding="utf-8")

    m = _mod()
    monkeypatch.setattr(m, "LIVE_WATCH_PATH", live_path)
    monkeypatch.setattr(m, "TRENDLINE_WATCH_PATH", tl_path)
    rc = m.main([])
    assert rc == 0

    assert lw_path.stat().st_mtime_ns == before_mtime
    assert lw_path.read_bytes() == before_bytes


# --------------------------------------------------------------------------- #
# 5. live smoke -- against the real repo state files, never raises
# --------------------------------------------------------------------------- #
def test_live_repo_state_renders_without_raising():
    m = _mod()
    snap = m._read_json(m.LIVE_WATCH_PATH)
    trendlines = m._read_json(m.TRENDLINE_WATCH_PATH)
    text = m.render_brief_with_trendlines(snap, trendlines)
    assert isinstance(text, str) and len(text) > 0


def test_read_json_fail_open_on_missing_file(tmp_path):
    m = _mod()
    assert m._read_json(tmp_path / "does-not-exist.json") is None


def test_read_json_fail_open_on_garbled_file(tmp_path):
    m = _mod()
    p = tmp_path / "garbled.json"
    p.write_text("{not json", encoding="utf-8")
    assert m._read_json(p) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
