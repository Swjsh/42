"""Tests for setup/scripts/checkpoint_package.py (GOAL-CHECKPOINT-REDUCTION-PACKAGES-2026-09-05 K2).

Scaffolds into tmp_path (via monkeypatching PACKAGES_DIR) so the test never writes
into the real analysis/recommendations/packages/ tree.
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

import checkpoint_package as cpkg  # noqa: E402


@pytest.fixture()
def packages_dir(tmp_path: Path, monkeypatch) -> Path:
    d = tmp_path / "packages"
    monkeypatch.setattr(cpkg, "PACKAGES_DIR", d)
    return d


def test_new_creates_all_four_files(packages_dir):
    pkg_dir = cpkg.new_package("fixture-row-id")
    assert pkg_dir == packages_dir / "fixture-row-id"
    for name in ("README.md", "apply.ps1", "guard_test.py", "change.patch"):
        assert (pkg_dir / name).exists(), f"missing {name}"
    assert (pkg_dir / "change.patch").stat().st_size == 0


def test_readme_names_the_row_id_and_required_sections(packages_dir):
    pkg_dir = cpkg.new_package("fixture-row-id")
    text = (pkg_dir / "README.md").read_text(encoding="utf-8")
    assert "fixture-row-id" in text
    for required in ("Packet row", "Revert", "RED-proof", "Nothing applied"):
        assert required in text


def test_apply_ps1_refuses_without_freeze_override(packages_dir, monkeypatch):
    pkg_dir = cpkg.new_package("fixture-row-id")
    text = (pkg_dir / "apply.ps1").read_text(encoding="utf-8")
    assert "GAMMA_FREEZE_OVERRIDE" in text
    assert "-DryRun" in text
    assert "run_safety_gate.py" in text


def test_guard_test_scaffold_is_red_by_default(packages_dir):
    """A freshly scaffolded guard_test.py must exit non-zero -- an unfinished package
    can never be mistaken for a passing guard."""
    pkg_dir = cpkg.new_package("fixture-row-id")
    import importlib.util

    spec = importlib.util.spec_from_file_location("fixture_guard_test", pkg_dir / "guard_test.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main() == 1


def test_new_refuses_to_overwrite_without_force(packages_dir):
    cpkg.new_package("fixture-row-id")
    with pytest.raises(FileExistsError):
        cpkg.new_package("fixture-row-id")
    # --force succeeds
    cpkg.new_package("fixture-row-id", force=True)


def test_invalid_row_id_rejected(packages_dir):
    with pytest.raises(ValueError):
        cpkg.new_package("Not_A_Valid_Row_Id!")


def test_scaffold_for_real_tickers_theta_budget_cadence_row(packages_dir):
    """Sanity-check against the actual pending reduction row named in the goal text
    (currently INSUFFICIENT N, no package yet) -- the scaffold must accept it."""
    pkg_dir = cpkg.new_package("tickers-theta-budget-cadence")
    assert pkg_dir.exists()
    assert "tickers-theta-budget-cadence" in (pkg_dir / "README.md").read_text(encoding="utf-8")
