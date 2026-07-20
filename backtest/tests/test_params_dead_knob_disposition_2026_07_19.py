"""Guard for the 2026-07-19 PARAMS-DEAD-KNOB-DISPOSITION slice 1 (resilience-harness
bucket, 4 of 24 KNOWN_DEAD keys, automation/overnight/queue.md Tier 0.1).

Disposition shipped this fire:
  - REMOVE: max_consecutive_failed_mcp_calls / max_consecutive_tv_failures_before_
    kill_switch / wedged_state_alert_hours -- verified zero consumers ANYWHERE in the
    repo (not even the "embedded literal" the params.json doc claimed: the live
    self-heal design in run-tv-watchdog.ps1 relaunches immediately + always alerts on
    every relaunch, it never counted consecutive failures). Deleted from params.json.
  - RESTORE: min_disk_free_mb -- Test-DiskSpaceAvailable in _shared.ps1 now reads it
    live via the new Get-ParamsMinDiskFreeMb helper (fail-open to 100 on any read/parse
    error), instead of hardcoding the literal 100 at the one call site (Invoke-Claude).

BONUS finding while restoring min_disk_free_mb: the reconciliation guard's OWN consumer
corpus (test_params_consumer_reconciliation.py::_CONSUMER_GLOBS) never scanned
setup/scripts/*.ps1 (where _shared.ps1 actually lives -- only the top-level setup/*.ps1
installer directory was scanned) NOR automation/state/fleet/*.py (the live fleet-lane
consumer, whose absence was independently false-flagging recency_min_size_enabled dead
for 4+ days, tracked since 2026-07-15 per STATUS.md history). Both directories added to
the corpus glob in the SAME commit as this file.

Same convention as test_conductor_fire_lock_2026_07_18.py: no Pester harness in this
repo, so PS wrapper guards are text-assertion + a real powershell.exe subprocess
round-trip against the actual shared function.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "setup" / "scripts" / "_shared.ps1"
PARAMS_PATH = REPO / "automation" / "state" / "params.json"

_REMOVED_KEYS = (
    "max_consecutive_failed_mcp_calls",
    "max_consecutive_tv_failures_before_kill_switch",
    "wedged_state_alert_hours",
)


def test_removed_keys_are_gone_from_params():
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    for key in _REMOVED_KEYS:
        assert key not in params, (
            f"{key} was disposed REMOVE (PARAMS-DEAD-KNOB-DISPOSITION slice 1) but is "
            "still present in params.json"
        )


def test_min_disk_free_mb_still_present_and_now_restored():
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    assert "min_disk_free_mb" in params, "min_disk_free_mb was RESTORED, not removed"
    assert params["min_disk_free_mb"] == 100


def test_shared_ps1_defines_the_restore_helper():
    src = SHARED.read_text(encoding="utf-8")
    assert "function Get-ParamsMinDiskFreeMb" in src
    assert "min_disk_free_mb" in src
    # The one live call site must no longer hardcode -MinFreeMB 100 -- it must fall
    # through to the params-driven default, or the RESTORE is cosmetic-only.
    assert "Test-DiskSpaceAvailable -MinFreeMB 100" not in src, (
        "Invoke-Claude still hardcodes -MinFreeMB 100 -- the params-driven default "
        "in Test-DiskSpaceAvailable is dead code if every caller overrides it"
    )


def _run_test_disk_space(params_text: str) -> str:
    """Live powershell.exe round-trip: write params_text to a TEMP params.json copy,
    dot-source _shared.ps1 with $Global:WorkDir repointed at a scratch dir whose
    automation/state/params.json is the temp file, and read back Test-DiskSpaceAvailable's
    MinMB. Never touches the real params.json (unlike a mutate-in-place bite test)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        state_dir = tmp_path / "automation" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "params.json").write_text(params_text, encoding="utf-8")
        ps_cmd = (
            f". '{SHARED}'; "
            f"$Global:WorkDir = '{tmp_path}'; "
            "$d = Test-DiskSpaceAvailable; "
            "Write-Output \"MINMB=$($d.MinMB)\""
        )
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout + out.stderr


def test_bite_live_read_picks_up_a_changed_value():
    """Non-vacuous bite: a scratch params.json with min_disk_free_mb=12345 must make
    Test-DiskSpaceAvailable's default resolve to 12345 -- proves this is a live read,
    not a cached/hardcoded literal masquerading as one."""
    result = _run_test_disk_space('{"min_disk_free_mb": 12345}')
    assert "MINMB=12345" in result, result


def test_bite_fail_open_on_missing_key():
    """Fail-open control: a scratch params.json WITHOUT min_disk_free_mb must fall back
    to the pre-fix literal 100, never crash or block the caller (rail 2 discipline --
    this pre-flight gate must never itself become a reason claude.exe can't be invoked)."""
    result = _run_test_disk_space('{"some_other_key": true}')
    assert "MINMB=100" in result, result


def test_bite_fail_open_on_malformed_json():
    """Fail-open control: a corrupt params.json must not crash Test-DiskSpaceAvailable --
    it must fall back to 100."""
    result = _run_test_disk_space("{ not valid json")
    assert "MINMB=100" in result, result


def test_consumer_corpus_now_scans_setup_scripts_ps1():
    src = (REPO / "backtest" / "tests" / "test_params_consumer_reconciliation.py").read_text(
        encoding="utf-8"
    )
    assert '("setup/scripts", "*.ps1")' in src, (
        "the consumer-corpus glob must scan setup/scripts/*.ps1 (where _shared.ps1 and "
        "every run-*.ps1 live) -- without it, any knob consumed only by a task script "
        "false-flags dead"
    )


def test_consumer_corpus_now_scans_fleet_lane():
    src = (REPO / "backtest" / "tests" / "test_params_consumer_reconciliation.py").read_text(
        encoding="utf-8"
    )
    assert '("automation/state/fleet", "*.py")' in src, (
        "the consumer-corpus glob must scan automation/state/fleet/*.py (the live "
        "fleet-lane consumer) -- without it, fleet-only knobs like "
        "recency_min_size_enabled false-flag dead"
    )
