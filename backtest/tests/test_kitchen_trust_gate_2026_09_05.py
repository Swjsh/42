"""Guard: free_model_audit.py's Kitchen OP-32 trust gate (I4, GOAL-KITCHEN-INTEGRITY-
2026-09-05) -- DEGRADED at 30d fabricated_artifact_rate >= 0.05, HEALTHY below,
UNKNOWN when the metric is unavailable (fail-open, never fabricate a verdict). Also
guards that update_kitchen_status_known_broken upserts on DEGRADED and clears on
HEALTHY/UNKNOWN via status_known_broken.upsert, never writing STATUS.md directly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _load_module(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, _REPO / rel_path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = m
    try:
        spec.loader.exec_module(m)
    finally:
        sys.modules.pop(mod_name, None)
    return m


fma = _load_module("free_model_audit_under_test", "setup/scripts/free_model_audit.py")


def test_degraded_at_or_above_threshold():
    assert fma.kitchen_trust_gate({"fabricated_artifact_rate": 0.05}) == "DEGRADED"
    assert fma.kitchen_trust_gate({"fabricated_artifact_rate": 0.1049}) == "DEGRADED"


def test_healthy_below_threshold():
    assert fma.kitchen_trust_gate({"fabricated_artifact_rate": 0.0499}) == "HEALTHY"
    assert fma.kitchen_trust_gate({"fabricated_artifact_rate": 0.0}) == "HEALTHY"


def test_unknown_when_metric_unavailable():
    assert fma.kitchen_trust_gate(None) == "UNKNOWN"
    assert fma.kitchen_trust_gate({"fabricated_artifact_rate": None}) == "UNKNOWN"


def test_status_upsert_called_on_degraded(monkeypatch):
    calls = []
    monkeypatch.setattr(fma, "_status_upsert", lambda marker, line: calls.append((marker, line)))
    metric = {
        "fabricated_artifact_rate": 0.1049, "provenance_missing": 440,
        "files_scored": 4193, "window_days": 30, "computed_at": "2026-09-05T02:00:00-06:00",
    }
    fma.update_kitchen_status_known_broken(metric, "DEGRADED")
    assert len(calls) == 1
    marker, line = calls[0]
    assert marker == fma._STATUS_MARKER
    assert line is not None and "DEGRADED" in line and "0.1049" in line


def test_status_cleared_on_healthy(monkeypatch):
    calls = []
    monkeypatch.setattr(fma, "_status_upsert", lambda marker, line: calls.append((marker, line)))
    fma.update_kitchen_status_known_broken({"fabricated_artifact_rate": 0.0}, "HEALTHY")
    assert calls == [(fma._STATUS_MARKER, None)]
