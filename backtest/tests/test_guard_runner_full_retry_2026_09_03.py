"""Guard: GUARD-RUNNER-FLAKE-RETRY (2026-09-03).

THE INCIDENT: the 02:13-02:45 ET full-suite run (`guard-watch-full.json`) reported
4 UNRELATED tests red -- test_queue_md_retention_cap, test_quiet_mode_starvation,
test_shadow_board_nonterminal_2026_09_03, test_walker_fidelity_2026_09_03 -- each
of which passed individually seconds later. Root cause: system-load / shared
mutable state (queue.md byte count, a live PowerShell Task Scheduler enumeration
subprocess, etc) during a 12,000+ test run with several other concurrent Claude
sessions writing to the same files. A near-identical incident (bec56cd9) burned a
full investigation cycle the same night to re-derive "not reproducible" by hand.

THE FIX pinned here: `guard_runner_full.py` retries a SMALL red (<= 20 failures)
scoped to just the failing node ids, once, after first-pass contention has
cleared. Anything still red on the scoped retry is a real regression and stays
RED. Anything that clears is logged (never silently dropped -- C7) as
'flaked_and_recovered', not folded into a false-green with no trace.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    path = REPO / "setup" / "guard_runner_full.py"
    spec = importlib.util.spec_from_file_location("guard_runner_full_retry_g", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture()
def grf(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "STATUS", tmp_path / "STATUS.md")
    monkeypatch.setattr(mod, "FLAKY_LOG", tmp_path / "guard-flaky-tests.jsonl")
    return mod


# ============================================================================
# _reconcile_after_retry -- pure logic, the load-bearing part
# ============================================================================

def test_all_four_pass_on_retry_reconciles_to_green(grf):
    mod = grf
    counts = {"passed": 12488, "failed": 4, "skipped": 16}
    names_all = [
        "tests/test_queue_md_retention_cap.py::test_queue_md_under_retention_cap",
        "tests/test_quiet_mode_starvation.py::test_no_registered_task_is_starved_by_the_quiet_window",
        "tests/test_shadow_board_nonterminal_2026_09_03.py::test_status_regexes_are_the_same_object_as_prereg_hygiene",
        "tests/test_walker_fidelity_2026_09_03.py::test_pdt_harness_validation_output_carries_magnitude_fidelity_shape",
    ]
    retry_out = "4 passed in 1.47s\n"
    status, final_counts, still_failing, flaked = mod._reconcile_after_retry(counts, names_all, retry_out)
    assert status == "green"
    assert still_failing == []
    assert flaked == names_all
    assert final_counts["failed"] == 0
    assert final_counts["passed"] == 12488 + 4


def test_one_of_four_still_fails_on_retry_stays_red_narrowed(grf):
    mod = grf
    counts = {"passed": 12488, "failed": 4, "skipped": 16}
    names_all = [
        "tests/test_a.py::test_1",
        "tests/test_b.py::test_2",
        "tests/test_c.py::test_3",
        "tests/test_d.py::test_4",
    ]
    retry_out = "FAILED tests/test_c.py::test_3\n1 failed, 3 passed in 2.0s\n"
    status, final_counts, still_failing, flaked = mod._reconcile_after_retry(counts, names_all, retry_out)
    assert status == "red", "a test that fails on the SCOPED retry is a real regression, must stay red"
    assert still_failing == ["tests/test_c.py::test_3"]
    assert flaked == ["tests/test_a.py::test_1", "tests/test_b.py::test_2", "tests/test_d.py::test_4"]
    assert final_counts["failed"] == 1


def test_all_still_fail_on_retry_reports_the_full_original_set(grf):
    mod = grf
    counts = {"passed": 100, "failed": 2, "skipped": 0}
    names_all = ["tests/test_a.py::test_1", "tests/test_b.py::test_2"]
    retry_out = "FAILED tests/test_a.py::test_1\nFAILED tests/test_b.py::test_2\n2 failed in 1.0s\n"
    status, final_counts, still_failing, flaked = mod._reconcile_after_retry(counts, names_all, retry_out)
    assert status == "red"
    assert still_failing == names_all
    assert flaked == []
    assert final_counts["failed"] == 2
    assert final_counts["passed"] == 100  # no flakes recovered, no phantom passed bump


# ============================================================================
# main() wiring -- large first-pass failures must NEVER be retried
# ============================================================================

def test_large_failure_count_exceeds_retry_threshold(grf):
    """A wide break (> RETRY_MAX_FAILURES) must NOT match main()'s retry-eligibility
    guard `0 < len(names_all) <= RETRY_MAX_FAILURES` -- retrying a real wide
    regression just burns another ~40 minutes for nothing. This pins the exact
    boundary main() branches on."""
    mod = grf
    big_names = [f"tests/test_x.py::t{i}" for i in range(mod.RETRY_MAX_FAILURES + 5)]
    assert not (0 < len(big_names) <= mod.RETRY_MAX_FAILURES)
    small_names = [f"tests/test_x.py::t{i}" for i in range(4)]
    assert 0 < len(small_names) <= mod.RETRY_MAX_FAILURES
    # boundary itself is retry-eligible (<=), one past it is not
    boundary_names = [f"tests/test_x.py::t{i}" for i in range(mod.RETRY_MAX_FAILURES)]
    over_names = [f"tests/test_x.py::t{i}" for i in range(mod.RETRY_MAX_FAILURES + 1)]
    assert 0 < len(boundary_names) <= mod.RETRY_MAX_FAILURES
    assert not (0 < len(over_names) <= mod.RETRY_MAX_FAILURES)


# ============================================================================
# retry-timeout must never be read as "nothing failed"
# ============================================================================

def test_retry_timeout_flag_is_distinguishable_from_a_clean_pass(grf):
    """`_retry_failed_out` must signal timeout distinctly from '' + rc handling --
    an empty string alone is indistinguishable from a real 0-failure pytest run,
    which would silently flip a real red to a false green."""
    mod = grf

    def _timeout(*a, **k):
        import subprocess
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch_target = mod.subprocess
    orig_run = monkeypatch_target.run
    monkeypatch_target.run = _timeout
    try:
        out, timed_out = mod._retry_failed_out(["tests/test_a.py::test_1"], timeout_sec=1)
    finally:
        monkeypatch_target.run = orig_run
    assert timed_out is True
    assert out == ""


# ============================================================================
# _log_flaky -- pattern-tracking must never be silent (C7) and never blocking
# ============================================================================

def test_log_flaky_appends_a_row(grf):
    mod = grf
    mod._log_flaky(["tests/test_a.py::test_1"], [])
    rows = [json.loads(l) for l in mod.FLAKY_LOG.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["flaked_and_recovered"] == ["tests/test_a.py::test_1"]
    assert rows[0]["still_failing_after_retry"] == []


def test_log_flaky_noop_when_nothing_to_report(grf):
    mod = grf
    mod._log_flaky([], [])
    assert not mod.FLAKY_LOG.exists()


def test_log_flaky_never_raises_when_parent_uncreatable(grf, monkeypatch):
    mod = grf
    # Point at a path whose parent can't be created (a file standing where a dir
    # should be) -- must degrade silently (best-effort), never crash the real verdict.
    bad_parent = mod.FLAKY_LOG.parent.parent / "not_a_dir_but_used_as_one.txt"
    bad_parent.write_text("x", encoding="utf-8")
    monkeypatch.setattr(mod, "FLAKY_LOG", bad_parent / "guard-flaky-tests.jsonl")
    mod._log_flaky(["tests/test_a.py::test_1"], [])  # must not raise
