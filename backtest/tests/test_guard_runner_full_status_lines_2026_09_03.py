"""Guard: FULL-SUITE-RED-LINE-OUTLIVES-GREEN (queue.md 2026-09-02, filed from the
first-live-day box close).

THE BUG: `guard_runner_full.py::_append_status` only ever APPENDED a
'FULL-SUITE RED/timeout/notests' line under '## Known broken', and the function was
never even called on a green verdict -- so a fixed suite kept reading RED to every
consumer (a human skimming STATUS.md, the conductor's own STAGE 0, and
first_live_day_review's conductor heuristic) with nothing left to clear it. Live
evidence: 2026-09-02 carried TWO such lines (10:15 ET '7 failed' and 04:52 ET
'5 failed'), both stale, while a clean 11:09 ET run (11,739 passed / 0 failed) sat
unreferenced anywhere but a paragraph of prose.

THE FIX, tested here: on green, prior FULL-SUITE lines are stripped from the
'## Known broken' section and nothing is written back. On red/timeout/notests, any
prior FULL-SUITE line is stripped first and the newest one is written -- exactly one
survives, never a stack. Only lines inside the pinned section are ever touched; the
same-named runner for `guard_runner_slow.py`'s own GRADUATED-GUARDS-SLOW marker gets
an equivalent fix, tested in the second half of this file.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture()
def grf(tmp_path, monkeypatch):
    mod = _load("guard_runner_full_g", "setup/guard_runner_full.py")
    status_path = tmp_path / "STATUS.md"
    monkeypatch.setattr(mod, "STATUS", status_path)
    return mod, status_path


@pytest.fixture()
def grs(tmp_path, monkeypatch):
    mod = _load("guard_runner_slow_g", "setup/guard_runner_slow.py")
    status_path = tmp_path / "STATUS.md"
    monkeypatch.setattr(mod, "STATUS", status_path)
    return mod, status_path


MARKER = "## Known broken"

REALISTIC_SECTION = (
    f"{MARKER}\n\n"
    "- [2026-09-02T23:50:00-04:00] MCP_AUDIT_YELLOW: All MCP servers healthy.\n"
    "- [2026-09-02 10:15 ET] FULL-SUITE RED :: 11732 passed, 7 failed, 11 skipped :: "
    "tests/test_x.py::test_y :: re-run: cd backtest && python -m pytest tests/ -q -m \"not slow\"\n"
    "- [2026-09-02T14:14+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD.\n"
    "- [2026-09-02 04:52 ET] FULL-SUITE RED :: 11461 passed, 5 failed, 11 skipped :: "
    "tests/test_a.py::test_b :: re-run: cd backtest && python -m pytest tests/ -q -m \"not slow\"\n"
    "- [2026-09-02T06:23:50.560122-04:00] MCP_AUDIT_YELLOW: session start.\n\n"
    "## [2026-09-02T16:15:03 ET] NOT_EXERCISED -- monday_verify\n"
    "some body text, unrelated to guards\n"
)


# ============================================================================
# guard_runner_full._append_status
# ============================================================================

def test_green_clears_prior_full_suite_lines(grf):
    mod, status_path = grf
    status_path.write_text(REALISTIC_SECTION, encoding="utf-8")
    mod._append_status("green", "11739 passed, 0 failed, 11 skipped", [])
    after = status_path.read_text(encoding="utf-8")
    assert "FULL-SUITE" not in after, (
        "a green run left a stale FULL-SUITE line behind -- the exact "
        "FULL-SUITE-RED-LINE-OUTLIVES-GREEN bug"
    )
    assert "MCP_AUDIT_YELLOW" in after and "ROSTER-LIVENESS" in after, (
        "clearing FULL-SUITE lines destroyed unrelated Known-broken content"
    )
    assert "## [2026-09-02T16:15:03 ET] NOT_EXERCISED" in after, (
        "content outside the Known-broken section was touched"
    )


def test_red_keeps_exactly_one_line_newest(grf):
    mod, status_path = grf
    status_path.write_text(REALISTIC_SECTION, encoding="utf-8")
    mod._append_status("red", "11097 passed, 4 failed, 11 skipped", ["tests/test_new.py::test_z"])
    after = status_path.read_text(encoding="utf-8")
    assert after.count("FULL-SUITE") == 1, (
        f"expected exactly one FULL-SUITE line, found {after.count('FULL-SUITE')}"
    )
    assert "test_new.py::test_z" in after
    assert "FULL-SUITE RED :: 11732 passed, 7 failed" not in after
    assert "FULL-SUITE RED :: 11461 passed, 5 failed" not in after
    assert "MCP_AUDIT_YELLOW" in after and "ROSTER-LIVENESS" in after


def test_full_suite_line_outside_the_section_is_untouched(grf):
    mod, status_path = grf
    outside = (
        f"{MARKER}\n\n- some other finding\n\n"
        "## [2026-08-01T09:00 ET] an older dated entry\n"
        "- [2026-08-01 09:00 ET] FULL-SUITE RED :: 100 passed, 1 failed, 0 skipped :: "
        "re-run: cd backtest && python -m pytest tests/ -q -m \"not slow\"\n"
    )
    status_path.write_text(outside, encoding="utf-8")
    mod._append_status("green", "200 passed, 0 failed, 0 skipped", [])
    after = status_path.read_text(encoding="utf-8")
    assert "FULL-SUITE RED :: 100 passed, 1 failed, 0 skipped" in after, (
        "a FULL-SUITE line living in an OLDER dated entry (outside '## Known broken') "
        "was wrongly touched -- history must be left alone"
    )
    assert "some other finding" in after


def test_heading_survives_byte_identical(grf):
    mod, status_path = grf
    status_path.write_text(REALISTIC_SECTION, encoding="utf-8")
    mod._append_status("green", "11739 passed, 0 failed, 11 skipped", [])
    after = status_path.read_text(encoding="utf-8")
    assert MARKER in after
    assert after.count(MARKER) == 1


def test_notests_and_timeout_also_keep_exactly_one_line(grf):
    mod, status_path = grf
    status_path.write_text(REALISTIC_SECTION, encoding="utf-8")
    mod._append_status("notests", "collected nothing", [])
    after = status_path.read_text(encoding="utf-8")
    assert after.count("FULL-SUITE") == 1
    assert "FULL-SUITE NOTESTS" in after


def test_green_on_a_file_with_no_full_suite_line_is_a_noop_shape(grf):
    """Green must never crash or corrupt a section that never had a FULL-SUITE line."""
    mod, status_path = grf
    status_path.write_text(f"{MARKER}\n\n- some other finding\n\n", encoding="utf-8")
    mod._append_status("green", "1 passed, 0 failed, 0 skipped", [])
    after = status_path.read_text(encoding="utf-8")
    assert "some other finding" in after
    assert "FULL-SUITE" not in after


# ============================================================================
# guard_runner_slow: same shape for GRADUATED-GUARDS-SLOW
# ============================================================================

SLOW_SECTION = (
    f"{MARKER}\n\n"
    "- [2026-09-01T10:00:00] GRADUATED-GUARDS-SLOW FAIL :: 30 passed, 2 failed :: "
    "re-run: cd backtest && python -m pytest tests/ -m slow -q\n"
    "- [2026-09-02T06:23:50] MCP_AUDIT_YELLOW: session start.\n\n"
    "## [2026-09-02T16:15:03 ET] some other entry\nbody\n"
)


def test_slow_recovery_clears_the_marker(grs):
    mod, status_path = grs
    status_path.write_text(SLOW_SECTION, encoding="utf-8")
    mod._clear_marker_on_recovery()
    after = status_path.read_text(encoding="utf-8")
    assert "GRADUATED-GUARDS-SLOW" not in after
    assert "MCP_AUDIT_YELLOW" in after


def test_slow_reflag_keeps_exactly_one_line(grs):
    mod, status_path = grs
    status_path.write_text(SLOW_SECTION, encoding="utf-8")
    mod._flag_status_md("fail", "28 passed, 4 failed")
    after = status_path.read_text(encoding="utf-8")
    assert after.count("GRADUATED-GUARDS-SLOW") == 1
    assert "28 passed, 4 failed" in after
    assert "30 passed, 2 failed" not in after


def test_slow_clear_is_idempotent_noop_when_nothing_to_clear(grs):
    mod, status_path = grs
    clean = f"{MARKER}\n\n- some other finding\n\n"
    status_path.write_text(clean, encoding="utf-8")
    mod._clear_marker_on_recovery()
    assert status_path.read_text(encoding="utf-8") == clean
