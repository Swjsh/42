"""Tests for the additive `package`/`package_ready` fields on reduction rows
(GOAL-CHECKPOINT-REDUCTION-PACKAGES-2026-09-05 K3).

Deliberately a SEPARATE file from test_checkpoint_packet_2026_09_05.py -- that file is
being hand-checked concurrently under GOAL-CHECKPOINT-PACKET-2026-09-29 C6 in this same
session window; keeping this additive change in its own file avoids any edit collision
with that parallel worker.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
for _p in (str(SCRIPTS_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import checkpoint_packet as cp  # noqa: E402


def test_reduction_rows_carry_package_and_package_ready():
    packet = cp.build_packet()
    reduction_rows = [r for r in packet["rows"] if r["classification"] == "reduction"]
    assert len(reduction_rows) >= 2
    for r in reduction_rows:
        assert "package" in r
        assert "package_ready" in r
        assert isinstance(r["package_ready"], bool)


def test_non_reduction_rows_never_get_the_package_field():
    packet = cp.build_packet()
    for r in packet["rows"]:
        if r["classification"] != "reduction":
            assert "package" not in r
            assert "package_ready" not in r


def test_score_ladder_v2_row_reads_package_ready_true():
    """K1 shipped analysis/recommendations/packages/score-ladder-v2-shadow-retirement/
    with a non-empty change.patch -- this row must read package_ready True."""
    packet = cp.build_packet()
    row = next(r for r in packet["rows"] if r["row_id"] == "score-ladder-v2-shadow-retirement")
    assert row["package"] == "analysis/recommendations/packages/score-ladder-v2-shadow-retirement"
    assert row["package_ready"] is True


def test_package_status_none_when_directory_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "PACKAGES_DIR", tmp_path / "no-such-dir")
    path, ready = cp._package_status("some-row-with-no-package")
    assert path is None
    assert ready is False


def test_package_status_scaffold_only_when_patch_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "PACKAGES_DIR", tmp_path)
    pkg_dir = tmp_path / "fixture-row"
    pkg_dir.mkdir()
    (pkg_dir / "README.md").write_text("x", encoding="utf-8")
    (pkg_dir / "apply.ps1").write_text("x", encoding="utf-8")
    (pkg_dir / "change.patch").write_text("", encoding="utf-8")  # empty = scaffold only
    path, ready = cp._package_status("fixture-row")
    assert path == "analysis/recommendations/packages/fixture-row"
    assert ready is False


def test_package_status_ready_when_patch_non_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "PACKAGES_DIR", tmp_path)
    pkg_dir = tmp_path / "fixture-row-ready"
    pkg_dir.mkdir()
    (pkg_dir / "README.md").write_text("x", encoding="utf-8")
    (pkg_dir / "apply.ps1").write_text("x", encoding="utf-8")
    (pkg_dir / "change.patch").write_text("diff --git a/x b/x\n", encoding="utf-8")
    path, ready = cp._package_status("fixture-row-ready")
    assert ready is True
