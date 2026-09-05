"""Guard: conductor_budget's max_fires counts SPAWNED conductor fires only.

Incident (2026-09-05, Saturday): every row in conductor-outcomes.jsonl counted as a fire.
An interactive Fable session closing 17 goals overnight wrote 29 `record` rows at $0, and
each rail-0 PRECHECK rejection wrote another row, so by 08:00 ET the governor read
"37 fires >= max_fires 8" at $0.76 of the $30 cap and Gamma_ConductorWeekend never spawned
all day. The rejection rows fed the count that caused them.

Mechanism pinned here:
  * PRECHECK-* rows never count.
  * rows stamped `source` count iff source == "conductor" (conductor_outcome.record stamps
    it from GAMMA_CONDUCTOR_FIRE=1, exported by run-conductor*.ps1 at the spawn point).
  * legacy rows (no `source`) count iff cost_usd > 0.
  * cost_usd is summed over EVERY row regardless -- the dollar cap is untouched.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import conductor_budget as cb  # noqa: E402
import conductor_outcome as co  # noqa: E402

DAY = "2026-09-05"


def _ledger(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "conductor-outcomes.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"fired_at": f"{DAY}T16:00:00+00:00", **r}) + "\n")
    return p


def _cfg(fires=8):
    return {"daily_cap_usd": 30.0, "max_fires": fires, "enabled": True}


def test_replay_of_the_2026_09_05_lockout_now_proceeds(tmp_path):
    rows = [{"task_id": f"GOAL-X-{i}", "cost_usd": 0.0} for i in range(29)]
    rows += [{"task_id": f"PRECHECK-BUDGET-EXHAUSTED-{i}", "cost_usd": 0.0} for i in range(9)]
    led = _ledger(tmp_path, rows)
    s = cb.spend_today(DAY, led)
    assert s["fires"] == 0
    assert cb.check(DAY, _cfg(), led)["verdict"] == "PROCEED"


def test_old_counting_would_have_exhausted_same_data(tmp_path):
    # Discriminating half: the same ledger read the old way (every row = fire) is EXHAUSTED.
    rows = [{"task_id": f"GOAL-X-{i}", "cost_usd": 0.0} for i in range(29)]
    led = _ledger(tmp_path, rows)
    n_rows = sum(1 for _ in open(led, encoding="utf-8"))
    assert n_rows >= _cfg()["max_fires"]  # the old reading
    assert cb.spend_today(DAY, led)["fires"] < _cfg()["max_fires"]  # the new one


def test_precheck_rows_never_count_even_with_source_conductor(tmp_path):
    led = _ledger(tmp_path, [{"task_id": "PRECHECK-BUDGET-EXHAUSTED-1", "cost_usd": 0.0,
                              "source": "conductor"}])
    assert cb.spend_today(DAY, led)["fires"] == 0


def test_source_conductor_counts_even_at_zero_cost(tmp_path):
    led = _ledger(tmp_path, [{"task_id": "GOAL-A", "cost_usd": 0.0, "source": "conductor"}] * 8)
    assert cb.spend_today(DAY, led)["fires"] == 8
    assert cb.check(DAY, _cfg(), led)["verdict"] == "EXHAUSTED"


def test_source_interactive_never_counts_but_cost_is_summed(tmp_path):
    led = _ledger(tmp_path, [{"task_id": "GOAL-A", "cost_usd": 4.0, "source": "interactive"}] * 3)
    s = cb.spend_today(DAY, led)
    assert s["fires"] == 0
    assert s["raw_usd"] == pytest.approx(12.0)


def test_legacy_rows_count_iff_positive_cost(tmp_path):
    led = _ledger(tmp_path, [{"task_id": "T", "cost_usd": 5.5}, {"task_id": "T", "cost_usd": 0.0},
                             {"task_id": "T", "cost_usd": 0.3}, {"task_id": "T"}])
    s = cb.spend_today(DAY, led)
    assert s["fires"] == 2
    assert s["raw_usd"] == pytest.approx(5.8)


def test_record_stamps_source_from_env(tmp_path, monkeypatch):
    out = tmp_path / "o.jsonl"
    monkeypatch.delenv("GAMMA_CONDUCTOR_FIRE", raising=False)
    row = co.record("GOAL-T", outcomes_file=out, function_snapshot={})
    assert row["source"] == "interactive"
    monkeypatch.setenv("GAMMA_CONDUCTOR_FIRE", "1")
    row = co.record("GOAL-T", outcomes_file=out, function_snapshot={})
    assert row["source"] == "conductor"
    row = co.record("GOAL-T", outcomes_file=out, function_snapshot={}, source="interactive")
    assert row["source"] == "interactive"
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3


@pytest.mark.parametrize("ps1", ["run-conductor.ps1", "run-conductor-weekend.ps1"])
def test_launch_scripts_export_the_marker_before_the_spawn(ps1):
    text = (REPO / "setup" / "scripts" / ps1).read_text(encoding="utf-8")
    m_env = re.search(r'\$env:GAMMA_CONDUCTOR_FIRE\s*=\s*"1"', text)
    m_spawn = re.search(r"Invoke-ClaudeWithRetry", text)
    assert m_env and m_spawn and m_env.start() < m_spawn.start(), ps1
