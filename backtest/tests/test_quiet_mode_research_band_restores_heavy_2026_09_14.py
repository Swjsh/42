"""RESEARCH-BAND-STRANDS-HEAVY-TASKS (found 2026-09-14 00:5x ET by the company audit).

MEASURED: `Get-ScheduledTask Gamma_* | ? State -eq Disabled` listed Gamma_GuardsFull,
Gamma_EodDeepDive, Gamma_EodFullAudit, Gamma_GymSession and Gamma_DressRehearsal, every one
with LastRunTime on 2026-09-11 -- Friday's and the weekend's fires never happened -- plus
Gamma_CryptoGrinderKeepalive and Gamma_EngineStressSwarm dark since 2026-09-05. quiet-mode.log
told the story: `2026-09-12T08:02 RESEARCH BAND: light_up=0/0 heavy_held=5`, then
`2026-09-13T23:02 QUIET OFF: re-enabled=136/136` (the evening's LIGHT set only), then
`WARN heavy catch-up start failed for Gamma_GuardsFull: The task is disabled` every 15 min
all night, and quiet-mode.json said "nothing to restore".

MECHANISM: go_research() Disable-ScheduledTask'd the heavy set but never wrote it to the
restore file. Only go_quiet() writes that file, from a READY-only snapshot taken at 18:00 --
by then the heavy tasks are already Disabled, so they are never recorded, so go_loud() at
23:00 never re-enables them, so the next weekend fire finds them Disabled (heavy_held=0) and
the outage is permanent. The comment above the hold even said the heavy set "must stay on
the restore list"; the code did not do it.

FIX: go_research() persists `wanted + heavy_up` to the restore file the moment it holds
something. go_quiet() already merges on top of the file; go_loud() restores the union.
These tests pin the four things that must all remain true:
  1. a research-band hold is recorded on the restore file,
  2. the full weekend sequence research -> quiet -> loud ends with everything READY,
  3. repeated research-band fires are idempotent (no duplicates, no re-holds),
  4. a heavy task that was ALREADY Disabled (parked on purpose) is left alone -- the fix
     revives only what quiet mode itself took down.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup" / "scripts"))
import quiet_mode as qm  # noqa: E402

HEAVY_A = "Gamma_GuardsFull"
HEAVY_B = "Gamma_EodDeepDive"
LIGHT = "Gamma_FakeLightProducer"  # not in ESSENTIAL, not in HEAVY_TASKS


@pytest.fixture
def rig(monkeypatch, tmp_path):
    assert HEAVY_A in qm.HEAVY_TASKS and HEAVY_B in qm.HEAVY_TASKS
    assert LIGHT not in qm.HEAVY_TASKS and LIGHT not in qm.ESSENTIAL
    restore = tmp_path / "restore.json"
    monkeypatch.setattr(qm, "RESTORE_FILE", restore)
    monkeypatch.setattr(qm, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(qm, "LOG_FILE", tmp_path / "quiet.log")
    monkeypatch.setattr(qm, "_never_restore", lambda: set())
    monkeypatch.setattr(qm, "_catchup_sweep", lambda now: [])
    monkeypatch.setattr(qm, "_stop_heavy_processes", lambda: [])

    states = {HEAVY_A: qm.STATE_READY, HEAVY_B: qm.STATE_READY,
              LIGHT: qm.STATE_READY, "Gamma_QuietMode": qm.STATE_READY}
    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_set(names, enable):
        for n in names:
            states[n] = qm.STATE_READY if enable else "1"
        calls.append((tuple(names), enable))
        return len(names)

    monkeypatch.setattr(qm, "_gamma_tasks", lambda: dict(states))
    monkeypatch.setattr(qm, "_set_tasks", fake_set)
    return states, calls, restore


def _restore_names(restore: Path) -> list[str]:
    if not restore.exists():
        return []
    return list(json.loads(restore.read_text(encoding="utf-8"))["restore_to_ready"])


class TestResearchBandRecordsItsHold:
    def test_held_heavy_tasks_land_on_the_restore_file(self, rig):
        states, _calls, restore = rig
        assert qm.go_research() == 0
        assert states[HEAVY_A] == "1" and states[HEAVY_B] == "1", "the hold itself is unchanged"
        assert set(_restore_names(restore)) == {HEAVY_A, HEAVY_B}, (
            "2026-09-12 bug: the hold was never recorded, so 23:00 never restored it")

    def test_light_tasks_are_not_held_and_not_recorded(self, rig):
        states, _calls, restore = rig
        qm.go_research()
        assert states[LIGHT] == qm.STATE_READY
        assert LIGHT not in _restore_names(restore)


class TestWeekendSequenceEndsReady:
    def test_research_then_quiet_then_loud_restores_everything(self, rig):
        states, _calls, restore = rig
        assert qm.go_research() == 0          # 08:00 ET: heavy held
        assert qm.go_quiet() == 0             # 18:00 ET: light held too, list merged
        assert states[LIGHT] == "1" and states[HEAVY_A] == "1"
        assert set(_restore_names(restore)) == {HEAVY_A, HEAVY_B, LIGHT}
        assert qm.go_loud() == 0              # 23:00 ET: the union comes back
        assert states[HEAVY_A] == qm.STATE_READY, "GuardsFull dark since 09-12 was this line"
        assert states[HEAVY_B] == qm.STATE_READY
        assert states[LIGHT] == qm.STATE_READY
        assert not restore.exists(), "a full restore clears the file"


class TestResearchBandIsIdempotent:
    def test_second_fire_holds_nothing_new_and_keeps_the_record(self, rig):
        _states, calls, restore = rig
        qm.go_research()
        first = _restore_names(restore)
        calls.clear()
        qm.go_research()  # 08:15 ET: same band, nothing READY among the heavy set
        held_again = [n for names, enable in calls if not enable for n in names]
        assert held_again == []
        assert _restore_names(restore) == first, "no duplicates, nothing dropped"


class TestParkedHeavyTaskIsLeftAlone:
    def test_already_disabled_heavy_task_is_not_revived_at_23(self, rig):
        states, _calls, restore = rig
        states[HEAVY_B] = "1"  # parked on purpose before the weekend
        qm.go_research()
        assert HEAVY_A in _restore_names(restore)
        assert HEAVY_B not in _restore_names(restore), (
            "the fix revives only what quiet mode took down, never a deliberate park")
        qm.go_loud()
        assert states[HEAVY_B] == "1"
