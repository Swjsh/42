"""Guard: roster_liveness must SPEAK, not just write JSON.

Scar (2026-08-29 audit): the probe existed since Phase 0 but was mute -- it wrote
roster-health.json and always returned 0. It last ran 2026-07-01; in the gap three
lanes 404'd, coordinator's and coder's PRIMARY lanes were dead ~2 months, and
gamma_manager's pick phase failed on every fire while Task Scheduler saw exit 0.
These tests RED if the alerting or the non-zero exit is ever removed again.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup" / "scripts"))
import roster_liveness as rl  # noqa: E402

DEAD = [{"lane": "openrouter::fake/dead-model:free"}]


def test_dead_lane_is_flagged_and_prior_content_preserved(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n- [old] prior entry\n\n## Other\n", encoding="utf-8")
    assert rl.flag_known_broken(DEAD, status_md=status) is True
    out = status.read_text(encoding="utf-8")
    assert "ROSTER-LIVENESS" in out and "fake/dead-model" in out
    assert "- [old] prior entry" in out, "must not clobber existing Known-broken entries"
    assert "## Other" in out, "must not clobber the rest of STATUS.md"


def test_missing_marker_is_recreated_not_dropped(tmp_path):
    """The 2026-08-20 scar: the section had been deleted, so positional writes vanished."""
    status = tmp_path / "STATUS.md"
    status.write_text("## Something\n\ncontent\n", encoding="utf-8")
    assert rl.flag_known_broken(DEAD, status_md=status) is True
    out = status.read_text(encoding="utf-8")
    assert out.startswith("## Known broken"), "marker must be recreated when absent"
    assert "## Something" in out and "content" in out


def test_no_dead_lanes_is_a_silent_no_op(tmp_path):
    status = tmp_path / "STATUS.md"
    status.write_text("## Known broken\n\n- [old] prior\n", encoding="utf-8")
    before = status.read_text(encoding="utf-8")
    assert rl.flag_known_broken([], status_md=status) is False
    assert status.read_text(encoding="utf-8") == before, "no dead lanes => no write, no noise"


def test_missing_status_file_fails_soft(tmp_path):
    """Never crash the probe because STATUS.md moved -- report, don't explode."""
    assert rl.flag_known_broken(DEAD, status_md=tmp_path / "nope.md") is False


def test_main_returns_nonzero_only_when_a_lane_is_dead(monkeypatch, tmp_path):
    """Task Scheduler's LastTaskResult must carry the signal (exit 0 == indistinguishable
    from 'never ran' -- exactly how this rotted for two months)."""
    monkeypatch.setattr(rl.sc, "REPO", tmp_path)  # main() prints a repo-relative path
    monkeypatch.setattr(rl, "HEALTH_FILE", tmp_path / "roster-health.json")
    monkeypatch.setattr(rl, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(rl, "unique_lanes", lambda roster: [{"provider": "p", "model": "m"}])
    monkeypatch.setattr(rl.sc, "load_roster", lambda: {"roles": {}})

    for klass, expected in (("dead_id", 1), ("throttled", 0), ("live", 0)):
        monkeypatch.setattr(rl, "probe", lambda ln, roster, _k=klass: {
            "lane": "p::m", "ok": _k == "live", "class": _k, "elapsed_s": 0.1, "error": ""})
        assert rl.main() == expected, f"class={klass} should exit {expected}"
