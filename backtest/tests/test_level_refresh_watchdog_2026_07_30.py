"""Guard for the 2026-07-30 levels_blind incident fix: Gamma_LevelRefresh self-heal.

ROOT CAUSE (root-caused by Gamma_Conductor, 2026-07-30 evening fire): Gamma_LevelRefresh's
own Task Scheduler config (PT5M repetition / MultipleInstances=IgnoreNew / PT3M
ExecutionTimeLimit) went silently dark for ~20h -- last good run 2026-07-29 22:43 ET (see
automation/state/logs/level-refresh-2026-07-29.log), nothing until a manual repair at
18:57 ET on 2026-07-30 (automation/state/logs/level-refresh-2026-07-30.log's first entry) --
with ZERO errors logged in either day's log and ZERO Task Scheduler recovery of its own.
Every one of the day's 770 RTH decision rows carried levels_active=[] (engine-health.json
`levels_blind` RED; setup/scripts/levels_blind_check.py). Nothing previously force-killed
+relaunched a stuck instance the way Invoke-TvLaunchSafe already does for the analogous
TV/CDP-hang failure mode. This fix adds the identical kill-the-tree-then-relaunch pattern,
gated to RTH with a post-open warmup, wired into the already-proven 5-min Gamma_TvWatchdog
cadence (no new scheduled task needed).

No Pester harness in this repo (see test_tv_launch_safe_2026_07_06.py's identical note) --
these are real subprocess-executed PowerShell assertions against the shipped .ps1 text AND
live behavioral checks against a harmless dummy script, never the real level-refresh script.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"
WATCHDOG = SCRIPTS / "run-tv-watchdog.ps1"
LEVEL_REFRESH = SCRIPTS / "run-level-refresh.ps1"
LOCK_FILE = REPO / "automation" / "state" / "level-refresh-watchdog.lock"


def test_shared_defines_invoke_level_refresh_safe():
    src = SHARED.read_text(encoding="utf-8")
    assert "function Invoke-LevelRefreshSafe" in src
    assert "level-refresh-watchdog.lock" in src
    # Must kill by command-line match, not assume a single wrapper layer hung.
    assert "refresh_levels_intraday.py" in src
    assert "run-level-refresh.ps1" in src
    assert "Stop-ProcessTree" in src.split("function Invoke-LevelRefreshSafe", 1)[1]


def test_watchdog_wires_the_self_heal():
    src = WATCHDOG.read_text(encoding="utf-8")
    assert "Invoke-LevelRefreshSafe" in src
    assert "key-levels.json" in src
    # RTH-scoped (matches levels_blind_check.py's own 12min warmup / 09:30 session start).
    assert "942" in src, "self-heal window must start at 09:42 ET (09:30 + 12min warmup)"
    assert "955" in src, "self-heal window must end at 15:55 ET (session close)"
    # The staleness threshold must be a real number, not accidentally deleted.
    assert re.search(r"\$klAgeMin\s+-gt\s+12", src), "stale threshold must be 12 minutes"
    # levels_refresh must feed the same problem/alert surface as tv_action/heartbeat.
    assert '$levelsRefreshAction -eq "self_heal"' in src


def test_level_refresh_script_unchanged_by_this_fix():
    """The watchdog relaunches the EXISTING run-level-refresh.ps1 verbatim -- this fix must
    not have accidentally forked or duplicated the launch logic."""
    assert LEVEL_REFRESH.exists()
    src = LEVEL_REFRESH.read_text(encoding="utf-8")
    assert "refresh_levels_intraday.py" in src


def _run_invoke_level_refresh_safe(dummy_script: Path, log_file: Path) -> str:
    ps_cmd = (
        f". '{SHARED}'; "
        f"$r = Invoke-LevelRefreshSafe -Script '{dummy_script}' -LogFile '{log_file}'; "
        f"Write-Output \"SKIPPED=$($r.skipped)\""
    )
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout + out.stderr


def test_lock_blocks_a_concurrent_refresh(tmp_path):
    """Non-vacuous bite: a FRESH lock file must make the function skip WITHOUT invoking the
    refresh script at all. Uses a harmless dummy .ps1, never the real level refresher."""
    dummy_script = tmp_path / "dummy_refresh.ps1"
    dummy_script.write_text("Write-Output 'dummy-refresh-ran'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text("held", encoding="utf-8")
    try:
        result = _run_invoke_level_refresh_safe(dummy_script, log_file)
        assert "SKIPPED=True" in result, result
        assert not log_file.exists(), "dummy refresh must NOT run while the lock is fresh"
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def test_no_lock_allows_refresh_and_cleans_up(tmp_path):
    """Non-vacuous bite: with no lock present, the function must proceed, actually invoke
    the refresh script, and clean up the lock file afterward."""
    dummy_script = tmp_path / "dummy_refresh.ps1"
    dummy_script.write_text("Write-Output 'dummy-refresh-ran'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"

    LOCK_FILE.unlink(missing_ok=True)
    try:
        result = _run_invoke_level_refresh_safe(dummy_script, log_file)
        assert "SKIPPED=False" in result, result
        assert log_file.exists()
        assert "dummy-refresh-ran" in log_file.read_text(encoding="utf-8")
        assert not LOCK_FILE.exists(), "lock file must be cleaned up after a completed call"
    finally:
        LOCK_FILE.unlink(missing_ok=True)
        log_file.unlink(missing_ok=True)
