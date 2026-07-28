"""Guards for backtest/tests/run_safety_gate.py itself (SAFETY-GATE-MISSES-PARITY-SUITE,
filed 2026-07-27, queue.md).

Two independent holes were found the same night: commit 3ced7457 touched the LIVE
engine_cli.decide_payload output contract, passed the curated pre-commit gate, and was
pushed -- while breaking 16 cases in test_engine_cli_parity.py.

  1. test_engine_cli_parity.py was not in the curated GATE_TESTS list at all, despite
     being the single most important guard on the engine_cli decision-path contract.
  2. A backgrounded `pytest -k ...` run reported exit code 0 while pytest had actually
     failed 17 cases -- the exit code was trusted instead of the output (C7: audit
     outputs, not exit codes -- same class as L241/L244).

This suite RED-proofs both fixes so neither can silently regress:
  - test_engine_cli_parity.py must be present in GATE_TESTS.
  - _parse_pytest_counts must correctly extract failed/error counts from captured
    pytest output.
  - run() must FAIL (return non-zero) when the subprocess reports exit 0 but the
    parsed summary shows failures -- i.e. the output is trusted over the exit code.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO / "backtest" / "tests" / "run_safety_gate.py"


def _load_gate_module():
    """run_safety_gate.py is a script (no `test_` prefix), so pytest never collects it
    as a module on its own -- import it explicitly via its file path."""
    spec = importlib.util.spec_from_file_location("run_safety_gate", GATE_SCRIPT)
    assert spec and spec.loader, f"could not build an import spec for {GATE_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gate_mod():
    return _load_gate_module()


class TestEngineCliParityInCuratedGate:
    def test_engine_cli_parity_is_in_gate_tests(self, gate_mod):
        """The exact regression: this suite must be a named member of GATE_TESTS, not
        just present on disk. Presence-on-disk alone did not stop the 2026-07-27 miss --
        the file existed the whole time and simply wasn't wired into the list."""
        assert "test_engine_cli_parity.py" in gate_mod.GATE_TESTS

    def test_engine_cli_parity_file_actually_exists(self):
        """A named-but-deleted test would print a loud WARNING (existing missing-test
        handling) rather than silently vanish -- but confirm the target itself is real."""
        assert (REPO / "backtest" / "tests" / "test_engine_cli_parity.py").exists()


class TestParsePytestCounts:
    def test_all_passed_summary(self, gate_mod):
        counts = gate_mod._parse_pytest_counts("...\n59 passed in 4.95s\n")
        assert counts == {"passed": 59}

    def test_failed_summary_is_counted(self, gate_mod):
        counts = gate_mod._parse_pytest_counts(
            "...\n3 failed, 12 passed in 1.02s\n"
        )
        assert counts["failed"] == 3
        assert counts["passed"] == 12

    def test_error_word_and_errors_word_both_map_to_error_key(self, gate_mod):
        assert gate_mod._parse_pytest_counts("1 error in 0.1s")["error"] == 1
        assert gate_mod._parse_pytest_counts("2 errors in 0.1s")["error"] == 2

    def test_no_summary_line_returns_empty(self, gate_mod):
        """A collection crash (bad import, syntax error) prints no '<n> passed/failed'
        line at all -- callers must fall back to the raw exit code in that case."""
        assert gate_mod._parse_pytest_counts("ERROR: file not found\n") == {}


class TestRunTrustsOutputNotExitCode:
    """The RED-proof: feed run() a fake subprocess result where returncode==0 but the
    captured output claims failures, and confirm it does NOT pass the gate open."""

    def test_exit_zero_with_failed_summary_is_a_gate_failure(self, gate_mod, monkeypatch):
        fake = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=0,  # <-- lying exit code, exactly the 2026-07-27 incident shape
            stdout="F.\n1 failed, 1 passed in 0.3s\n",
            stderr="",
        )
        monkeypatch.setattr(gate_mod.subprocess, "run", lambda *a, **k: fake)
        result = gate_mod.run(full=False)
        assert result != 0, (
            "run() returned 0 (PASS) even though the parsed summary showed 1 failed -- "
            "the exit-code-lying defense regressed."
        )

    def test_exit_zero_with_clean_summary_still_passes(self, gate_mod, monkeypatch):
        fake = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=0,
            stdout="....\n4 passed in 0.1s\n",
            stderr="",
        )
        monkeypatch.setattr(gate_mod.subprocess, "run", lambda *a, **k: fake)
        result = gate_mod.run(full=False)
        assert result == 0, "a genuinely green run must still pass -- no false positives introduced"

    def test_nonzero_exit_still_fails_even_with_no_parseable_summary(self, gate_mod, monkeypatch):
        fake = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=2,
            stdout="",
            stderr="ERROR: collection failure, bad import\n",
        )
        monkeypatch.setattr(gate_mod.subprocess, "run", lambda *a, **k: fake)
        result = gate_mod.run(full=False)
        assert result != 0


class TestGateStillGreenLive:
    """A live end-to-end sanity check (not mocked): the real curated gate, as now
    configured with test_engine_cli_parity.py included, must actually pass."""

    @pytest.mark.slow
    def test_curated_gate_passes_for_real(self):
        py = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            pytest.skip("backtest/.venv not present in this environment")
        proc = subprocess.run(
            [str(py), str(GATE_SCRIPT)], cwd=str(REPO), capture_output=True, text=True, timeout=120
        )
        assert proc.returncode == 0, f"curated gate failed:\n{proc.stdout}\n{proc.stderr}"
