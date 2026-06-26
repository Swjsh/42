"""Tests for setup/scripts/conductor_outcome.py — the conductor net-improvement metric.

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_conductor_outcome.py -q

The module lives under setup/scripts/ (not on the package path), so we load it by
file path via importlib. Every test redirects the module's path constants to a
tmp_path so the real automation/state/ files are never touched.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# --- Load the module by file path -------------------------------------------
_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "setup" / "scripts" / "conductor_outcome.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("conductor_outcome", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def co(tmp_path, monkeypatch):
    """conductor_outcome module with its path constants redirected to tmp_path."""
    mod = _load_module()
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUTCOMES_FILE", tmp_path / "conductor-outcomes.jsonl")
    monkeypatch.setattr(mod, "METRIC_FILE", tmp_path / "autonomy-metric.json")
    return mod


# --- record() ----------------------------------------------------------------
def test_record_appends_and_returns_full_schema(co):
    row = co.record(
        task_id="T1",
        cost_usd=1.5,
        items_drained=1,
        items_added=0,
        lessons_shipped=1,
        tests_delta=7,
        regressions=0,
        note="hello",
    )
    assert row is not None
    # full schema present
    for key in (
        "fired_at",
        "task_id",
        "cost_usd",
        "items_drained",
        "items_added",
        "lessons_shipped",
        "tests_delta",
        "regressions",
        "note",
    ):
        assert key in row
    assert row["task_id"] == "T1"
    assert row["cost_usd"] == 1.5
    assert row["tests_delta"] == 7
    assert row["fired_at"]  # defaulted to now

    # actually appended one JSON line
    lines = co.OUTCOMES_FILE.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["task_id"] == "T1"


def test_record_is_append_only(co):
    co.record(task_id="A", items_drained=1)
    co.record(task_id="B", items_drained=1)
    co.record(task_id="C", items_drained=1)
    lines = co.OUTCOMES_FILE.read_text(encoding="utf-8").splitlines()
    assert [json.loads(ln)["task_id"] for ln in lines] == ["A", "B", "C"]


def test_record_defaults(co):
    row = co.record()  # no args at all
    assert row is not None
    assert row["task_id"] == ""
    assert row["cost_usd"] == 0.0
    assert row["items_drained"] == 0
    assert row["note"] == ""


def test_record_never_throws_on_unwritable_path(co, monkeypatch):
    # Point the outcomes file at a path whose parent cannot be created (a file).
    bad_parent = co.STATE_DIR / "iamafile"
    bad_parent.write_text("x", encoding="utf-8")
    bad_target = bad_parent / "nested" / "outcomes.jsonl"
    # Must return None, not raise.
    result = co.record(task_id="X", outcomes_file=bad_target)
    assert result is None


# --- compute_metric(): empty / torn ------------------------------------------
def test_metric_empty_file_is_all_zeros_flat(co):
    metric = co.compute_metric(window=20)
    assert metric["net_improvement"] == 0
    assert metric["total_drained"] == 0
    assert metric["total_regressions"] == 0
    assert metric["total_cost_usd"] == 0.0
    assert metric["fires_counted"] == 0
    assert metric["cost_per_drained_usd"] == 0.0
    assert metric["trend"] == "flat"
    # and it wrote the file
    written = json.loads(co.METRIC_FILE.read_text(encoding="utf-8"))
    assert written["net_improvement"] == 0


def test_metric_robust_to_torn_line(co):
    # one good row + one torn (truncated) line that is NOT valid JSON
    co.record(task_id="A", items_drained=2, cost_usd=1.0)
    with co.OUTCOMES_FILE.open("a", encoding="utf-8") as fh:
        fh.write('{"task_id": "B", "items_drai')  # torn, no newline
    metric = co.compute_metric(window=20)
    # torn line skipped -> only the good row counts
    assert metric["fires_counted"] == 1
    assert metric["total_drained"] == 2
    assert metric["net_improvement"] == 2


# --- compute_metric(): math --------------------------------------------------
def test_metric_net_improvement_and_cost_per_drained(co):
    # 3 clean drains, total cost 3.0, no regressions, no re-adds.
    co.record(task_id="A", items_drained=1, cost_usd=1.0)
    co.record(task_id="B", items_drained=2, cost_usd=2.0)
    co.record(task_id="C", items_drained=1, cost_usd=0.0)
    metric = co.compute_metric(window=20)
    assert metric["total_drained"] == 4
    assert metric["total_regressions"] == 0
    assert metric["total_cost_usd"] == 3.0
    # net = 4 drained - 0 regressions - 0 thrash
    assert metric["net_improvement"] == 4
    # cost_per_drained = 3.0 / 4
    assert metric["cost_per_drained_usd"] == 0.75
    assert metric["fires_counted"] == 3


def test_metric_regression_subtracts_and_thrash_penalizes(co):
    co.record(task_id="A", items_drained=2)  # +2
    co.record(task_id="B", items_drained=1, regressions=1)  # +1 drained, -1 reg, -1 thrash(reg>0)
    metric = co.compute_metric(window=20)
    assert metric["total_drained"] == 3
    assert metric["total_regressions"] == 1
    # net = 3 - 1(regressions) - 1(thrash from the regression fire) = 1
    assert metric["net_improvement"] == 1


def test_metric_readd_of_drained_task_is_thrash(co):
    co.record(task_id="A", items_drained=1)  # drain A  -> +1
    co.record(task_id="A", items_added=1)    # re-add A -> thrash +1, drained 0
    metric = co.compute_metric(window=20)
    assert metric["total_drained"] == 1
    assert metric["total_regressions"] == 0
    # net = 1 - 0 - 1(thrash: A re-added after being drained) = 0
    assert metric["net_improvement"] == 0


def test_metric_window_limits_rows(co):
    # 5 fires, window=3 -> only last 3 counted
    for i in range(5):
        co.record(task_id=f"T{i}", items_drained=1, cost_usd=1.0)
    metric = co.compute_metric(window=3)
    assert metric["window"] == 3
    assert metric["fires_counted"] == 3
    assert metric["total_drained"] == 3


# --- compute_metric(): trend -------------------------------------------------
def test_trend_improving(co):
    # older half drains little, recent half drains a lot
    co.record(task_id="o1", items_drained=0)
    co.record(task_id="o2", items_drained=0)
    co.record(task_id="r1", items_drained=3)
    co.record(task_id="r2", items_drained=3)
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "improving"


def test_trend_regressing(co):
    # older half drains a lot, recent half drains little
    co.record(task_id="o1", items_drained=3)
    co.record(task_id="o2", items_drained=3)
    co.record(task_id="r1", items_drained=0)
    co.record(task_id="r2", items_drained=0)
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "regressing"


def test_trend_flat_equal_halves(co):
    co.record(task_id="o1", items_drained=1)
    co.record(task_id="o2", items_drained=1)
    co.record(task_id="r1", items_drained=1)
    co.record(task_id="r2", items_drained=1)
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "flat"


def test_trend_flat_single_row(co):
    co.record(task_id="only", items_drained=5)
    metric = co.compute_metric(window=20)
    assert metric["trend"] == "flat"
    assert metric["net_improvement"] == 5
