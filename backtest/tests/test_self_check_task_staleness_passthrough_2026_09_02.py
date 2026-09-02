"""Guards for self_check's TASK-STALENESS passthrough (item 22, 2026-09-02).

This one line of output has to satisfy two constraints that pull against each other, and
both were violated in turn before this test existed:

  1. `_problem_is_broken` matches the SUBSTRING "RED". So a finding's own verdict can never
     be interpolated into the message -- the first cut wrote "Gamma_GuardsNightly(RED)" and
     every YELLOW and UNKNOWN line consequently classified BROKEN, contradicting the
     function's own DEGRADED-only contract. Found by probing all four verdicts rather than
     just the RED path.
  2. But naming the top findings REGARDLESS of severity, under a headline that states the
     OVERALL verdict, reads as though every task listed is at that severity. The live case
     the same morning: Gamma_DeadMansSwitch was UNKNOWN ("never run, next fire 09:32 ET,
     expected for a freshly registered task") and was being listed inside a
     "TASK-STALENESS RED" line. Mislabelling a healthy task as RED is precisely the
     cry-wolf pattern the staleness instrument exists to avoid.

The shape that satisfies both: filter findings by severity, interpolate no verdict strings.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location("self_check_g", SCRIPTS / "self_check.py")
assert _spec and _spec.loader
sc = importlib.util.module_from_spec(_spec)
sys.modules["self_check_g"] = sc
_spec.loader.exec_module(sc)


def _artifact(tmp_path: Path, verdict: str, findings: list[dict]) -> Path:
    p = tmp_path / "scheduled-task-staleness.json"
    p.write_text(json.dumps({"verdict": verdict, "findings": findings}), encoding="utf-8")
    return p


def test_red_headline_names_only_red_tasks(tmp_path):
    """The live 2026-09-02 case: an UNKNOWN task must not appear under a RED headline."""
    p = _artifact(tmp_path, "RED", [
        {"name": "Gamma_ActuallyRed", "verdict": "RED"},
        {"name": "Gamma_NeverRanYet", "verdict": "UNKNOWN"},
        {"name": "Gamma_MildlyLate", "verdict": "YELLOW"},
    ])
    out = sc.check_task_staleness(None, p)
    assert len(out) == 1
    assert "Gamma_ActuallyRed" in out[0]
    assert "Gamma_NeverRanYet" not in out[0], "an UNKNOWN task named under a RED headline"
    assert "Gamma_MildlyLate" not in out[0], "a YELLOW task named under a RED headline"


def test_degraded_headline_names_yellow_and_unknown(tmp_path):
    p = _artifact(tmp_path, "UNKNOWN", [
        {"name": "Gamma_NeverRanYet", "verdict": "UNKNOWN"},
        {"name": "Gamma_MildlyLate", "verdict": "YELLOW"},
    ])
    out = sc.check_task_staleness(None, p)
    assert "Gamma_NeverRanYet" in out[0] and "Gamma_MildlyLate" in out[0]


def test_no_verdict_string_leaks_into_a_degraded_message(tmp_path):
    """Constraint 1. A DEGRADED line containing the substring RED classifies BROKEN."""
    p = _artifact(tmp_path, "YELLOW", [
        {"name": "Gamma_MildlyLate", "verdict": "YELLOW"},
        {"name": "Gamma_ActuallyRed", "verdict": "RED"},
    ])
    out = sc.check_task_staleness(None, p)
    assert out
    assert not any(sc._problem_is_broken(x) for x in out), (
        "the DEGRADED line classifies BROKEN -- a verdict string has leaked into it again"
    )


def test_red_verdict_still_classifies_broken(tmp_path):
    """The severity filter must not accidentally stop a real RED from breaking the check."""
    p = _artifact(tmp_path, "RED", [{"name": "Gamma_ActuallyRed", "verdict": "RED"}])
    out = sc.check_task_staleness(None, p)
    assert any(sc._problem_is_broken(x) for x in out)


def test_green_is_silent(tmp_path):
    assert sc.check_task_staleness(None, _artifact(tmp_path, "GREEN", [])) == []


@pytest.mark.parametrize("body", ["{{{ not json", "[]", '"a string"'])
def test_unreadable_artifact_is_a_silent_noop(tmp_path, body):
    """Fail-open: a malformed artifact must not break the whole self-check."""
    p = tmp_path / "scheduled-task-staleness.json"
    p.write_text(body, encoding="utf-8")
    assert sc.check_task_staleness(None, p) == []


def test_missing_artifact_is_silent(tmp_path):
    """SILENT UNTIL DEPLOYED -- absence means the task has not fired yet, not a fault."""
    assert sc.check_task_staleness(None, tmp_path / "nope.json") == []


def test_headline_verdict_with_no_matching_findings_still_renders(tmp_path):
    """Defensive: a RED verdict whose findings list carries no RED rows must not produce an
    empty, meaningless message."""
    p = _artifact(tmp_path, "RED", [{"name": "Gamma_Odd", "verdict": "YELLOW"}])
    out = sc.check_task_staleness(None, p)
    assert out and "(no tasks named)" in out[0]
