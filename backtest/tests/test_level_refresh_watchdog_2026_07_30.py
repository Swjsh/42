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
    # WATCHDOG-TEST-LOCK-RACE de-flake (2026-08-01, chip task_a85b1cb3): the function must
    # accept a -LockFile override so tests (and any other future caller) can point it at an
    # isolated path instead of racing the shared production lock file. Default must still
    # resolve to the unchanged production path -- see the two asserts below.
    fn_body = src.split("function Invoke-LevelRefreshSafe", 1)[1]
    assert re.search(r"\[string\]\$LockFile\s*=", fn_body), (
        "Invoke-LevelRefreshSafe must accept an optional -LockFile override "
        "(else every caller -- including tests -- shares one repo-wide lock file)")
    assert '$LockFile = (Join-Path $WorkDir "automation\\state\\level-refresh-watchdog.lock")' in fn_body, (
        "the -LockFile default must still resolve to the original production path -- "
        "production callers that omit -LockFile must be byte-identical to before this fix")


def test_watchdog_wires_the_self_heal():
    src = WATCHDOG.read_text(encoding="utf-8")
    assert "Invoke-LevelRefreshSafe" in src
    assert "key-levels.json" in src
    # $mins in run-tv-watchdog.ps1 is Hour*60+Minute (minutes-since-midnight -- see the
    # hbFlag window a few lines above, which correctly uses 575/955 for 09:35/15:55). The
    # window boundary for 09:42 ET is therefore 582 (9*60+42), NOT the literal clock digits
    # "942" -- 942 minutes since midnight is 15:42 ET, which would shrink the intended
    # ~373-minute RTH self-heal window down to 13 minutes (942-955). Regression-pinned
    # 2026-07-30 (conductor AFTERHOURS re-audit): the ORIGINAL version of this test asserted
    # the literal substring "942" and passed even though the shipped code carried this exact
    # bug -- a substring check can't tell "09:42 as clock digits" from "942 as minutes", so
    # this now extracts the real $mins bound out of the source and asserts on the computed
    # ET wall-clock time instead.
    m = re.search(r"if\s*\(\$mins\s+-ge\s+(\d+)\s+-and\s+\$mins\s+-le\s+(\d+)\)\s*\{\s*\n\s*\$keyLevelsPath",
                  src)
    assert m, "could not find the levels-refresh self-heal window guard in run-tv-watchdog.ps1"
    lo, hi = int(m.group(1)), int(m.group(2))
    assert (lo // 60, lo % 60) == (9, 42), (
        f"self-heal window must start at 09:42 ET (582 minutes-since-midnight), got "
        f"{lo} minutes = {lo // 60:02d}:{lo % 60:02d} ET")
    assert (hi // 60, hi % 60) == (15, 55), (
        f"self-heal window must end at 15:55 ET (955 minutes-since-midnight), got "
        f"{hi} minutes = {hi // 60:02d}:{hi % 60:02d} ET")
    assert hi - lo > 300, (
        f"self-heal window is only {hi - lo} minutes wide -- should cover most of the RTH "
        "session (09:42-15:55 = 373min), not a narrow tail near the close"
    )
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


# --- WATCHDOG-TEST-LOCK-RACE de-flake (2026-08-01, chip task_a85b1cb3) -----------------
# DIAGNOSIS (fable-differential, evidence not guess): the two live-subprocess tests below
# used to point Invoke-LevelRefreshSafe at LOCK_FILE -- the REAL production lock path
# (automation/state/level-refresh-watchdog.lock), the SAME file real Gamma_TvWatchdog fires
# AND any other concurrent pytest invocation of THIS test module use. Signature matched the
# textbook shared-mutable-resource race, not a fetch/logic bug: "passes standalone
# repeatedly, fails ~50% in paired runs, identical on unmodified code" (STATUS-archive-
# 2026-08-01 log) -- works alone, breaks under concurrency = contention on shared state, per
# this repo's own debugging doctrine. One process's New-Item/Remove-Item on the shared lock
# stomps the other's in-flight subprocess, so the captured stdout/stderr comes back empty --
# no exception to catch, just silence, exactly matching the observed symptom.
# FIX: isolate the resource instead of retrying/sleeping around the contention (a sleep or
# retry would still race, just less often -- banned fake-fix per this repo's doctrine).
# Invoke-LevelRefreshSafe gained an optional -LockFile override (_shared.ps1, default
# unchanged -- zero behavior change for the one real production caller, run-tv-watchdog.ps1,
# which never passes it). Every test below now uses a tmp_path-scoped lock file, which is
# inherently unique per test invocation AND per concurrent pytest process (pytest's own
# tmp_path allocator is itself safe under concurrent sessions) -- so two unrelated callers
# can never again collide on this file, matching how test_lock_blocks_a_concurrent_refresh
# already proves in-process contention is handled CORRECTLY (that's the lock's actual job);
# the bug was an out-of-process caller stepping on an unrelated test's lock.

def _run_invoke_level_refresh_safe(dummy_script: Path, log_file: Path, lock_file: Path):
    """Launch (don't wait). Callers either .communicate() one at a time (serial use) or
    start two of these back-to-back before communicating either, to genuinely overlap them
    in wall-clock time (the concurrency proof below)."""
    ps_cmd = (
        f". '{SHARED}'; "
        f"$r = Invoke-LevelRefreshSafe -Script '{dummy_script}' -LogFile '{log_file}' "
        f"-LockFile '{lock_file}'; "
        f"Write-Output \"SKIPPED=$($r.skipped)\""
    )
    return subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _run_and_wait(dummy_script: Path, log_file: Path, lock_file: Path, timeout: int = 30) -> str:
    proc = _run_invoke_level_refresh_safe(dummy_script, log_file, lock_file)
    out, err = proc.communicate(timeout=timeout)
    return out + err


def test_lock_blocks_a_concurrent_refresh(tmp_path):
    """Non-vacuous bite: a FRESH lock file must make the function skip WITHOUT invoking the
    refresh script at all. Uses a harmless dummy .ps1, never the real level refresher. Lock
    file lives under tmp_path -- isolated, no longer the shared production path."""
    dummy_script = tmp_path / "dummy_refresh.ps1"
    dummy_script.write_text("Write-Output 'dummy-refresh-ran'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"
    lock_file = tmp_path / "level-refresh-watchdog.lock"

    lock_file.write_text("held", encoding="utf-8")
    result = _run_and_wait(dummy_script, log_file, lock_file)
    assert "SKIPPED=True" in result, result
    assert not log_file.exists(), "dummy refresh must NOT run while the lock is fresh"


def test_no_lock_allows_refresh_and_cleans_up(tmp_path):
    """Non-vacuous bite: with no lock present, the function must proceed, actually invoke
    the refresh script, and clean up the lock file afterward. tmp_path is fresh per test
    invocation, so the lock is guaranteed absent going in -- no manual unlink needed."""
    dummy_script = tmp_path / "dummy_refresh.ps1"
    dummy_script.write_text("Write-Output 'dummy-refresh-ran'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"
    lock_file = tmp_path / "level-refresh-watchdog.lock"

    assert not lock_file.exists()
    result = _run_and_wait(dummy_script, log_file, lock_file)
    assert "SKIPPED=False" in result, result
    assert log_file.exists()
    assert "dummy-refresh-ran" in log_file.read_text(encoding="utf-8")
    assert not lock_file.exists(), "lock file must be cleaned up after a completed call"


def test_bite_concurrent_unrelated_callers_do_not_race_on_isolated_locks(tmp_path):
    """The actual de-flake proof: TWO calls launched genuinely concurrently (Popen started
    back-to-back, waited on afterward -- both processes overlap in wall-clock time, the
    exact 'paired runs' shape that flaked before), each with its OWN isolated lock file
    (simulating two unrelated concurrent test/watchdog invocations). Both must succeed
    independently -- neither may see the other's lock or clobber the other's output. Before
    the fix (both pointed at one shared LOCK_FILE) this is precisely the scenario that
    produced empty captured subprocess output ~50% of the time."""
    scripts = []
    for i in range(2):
        d = tmp_path / f"lane{i}"
        d.mkdir()
        dummy_script = d / "dummy_refresh.ps1"
        dummy_script.write_text(f"Write-Output 'dummy-refresh-ran-{i}'\n", encoding="utf-8")
        scripts.append((dummy_script, d / "dummy.log", d / "level-refresh-watchdog.lock"))

    procs = [_run_invoke_level_refresh_safe(s, log, lock) for s, log, lock in scripts]
    results = [proc.communicate(timeout=30) for proc in procs]

    for i, ((out, err), (dummy_script, log_file, lock_file)) in enumerate(zip(results, scripts)):
        combined = out + err
        assert "SKIPPED=False" in combined, f"lane {i}: {combined!r}"
        assert log_file.exists(), f"lane {i} dummy refresh never ran: {combined!r}"
        assert f"dummy-refresh-ran-{i}" in log_file.read_text(encoding="utf-8")
        assert not lock_file.exists(), f"lane {i} lock not cleaned up"


# --- SELFHEAL-VERIFY-EFFECT-AUDIT (2026-09-03) -----------------------------------------
# Before this fix, `skipped=$false` meant only "the relaunch call ran and exited" --
# identical shape to the pre-c941567c Invoke-TvLaunchSafe blind spot (lesson
# tv-selfheal-silent-failure-2026-07-31.md): nothing checked whether key-levels.json's
# mtime actually advanced. These tests prove the new -TargetFile effect check both ways:
# a dummy script that touches the target -> effect_verified=True; one that does NOT ->
# effect_verified=False. Same tmp_path-isolated -LockFile precedent as above, plus a new
# -TargetFile override so this never touches the real production key-levels.json.

def test_shared_effect_verification_present():
    """Text-assertion companion to the behavioral tests below -- pins the shape of the
    fix so a future edit can't silently drop the effect check while leaving the -TargetFile
    param (which would make the text tests below misleadingly still pass)."""
    src = SHARED.read_text(encoding="utf-8")
    fn_body = src.split("function Invoke-LevelRefreshSafe", 1)[1]
    assert re.search(r"\[string\]\$TargetFile\s*=", fn_body), (
        "Invoke-LevelRefreshSafe must accept an optional -TargetFile override for effect "
        "verification (same precedent as -LockFile)")
    assert '$TargetFile = (Join-Path $WorkDir "automation\\state\\key-levels.json")' in fn_body, (
        "the -TargetFile default must resolve to the real production key-levels.json path")
    assert "effect_verified" in fn_body, (
        "Invoke-LevelRefreshSafe must return an effect_verified field -- returning only "
        "skipped/killed_pids is the exact silent-success-is-failure shape this audit closed")
    assert "LastWriteTimeUtc" in fn_body, (
        "effect check must compare the target file's mtime before vs after the relaunch call")


def _run_invoke_level_refresh_safe_with_target(dummy_script: Path, log_file: Path,
                                                 lock_file: Path, target_file: Path):
    ps_cmd = (
        f". '{SHARED}'; "
        f"$r = Invoke-LevelRefreshSafe -Script '{dummy_script}' -LogFile '{log_file}' "
        f"-LockFile '{lock_file}' -TargetFile '{target_file}'; "
        f"Write-Output \"SKIPPED=$($r.skipped)\"; "
        f"Write-Output \"EFFECT_VERIFIED=$($r.effect_verified)\"; "
        f"Write-Output \"DELTA=$($r.mtime_delta_sec)\""
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    )
    return proc.stdout + proc.stderr


def test_effect_verified_true_when_target_file_actually_refreshed(tmp_path):
    """MUTATION-1 target: a dummy refresh script that WRITES the target file (the healthy
    case -- the self-heal actually worked) must report effect_verified=True. If the
    before/after mtime comparison were deleted or inverted, this would go False instead."""
    target_file = tmp_path / "key-levels.json"
    target_file.write_text('{"as_of": "stale"}', encoding="utf-8")
    import time as _time
    _time.sleep(0.05)  # ensure the dummy script's write lands at a strictly later mtime

    dummy_script = tmp_path / "dummy_refresh_touches.ps1"
    dummy_script.write_text(
        f"Set-Content -Path '{target_file}' -Value '{{\"as_of\": \"fresh\"}}' -Encoding utf8\n"
        "Write-Output 'dummy-refresh-touched-target'\n",
        encoding="utf-8",
    )
    log_file = tmp_path / "dummy.log"
    lock_file = tmp_path / "level-refresh-watchdog.lock"

    result = _run_invoke_level_refresh_safe_with_target(dummy_script, log_file, lock_file, target_file)
    assert "SKIPPED=False" in result, result
    assert "EFFECT_VERIFIED=True" in result, (
        f"target file WAS refreshed by the dummy script but effect_verified came back "
        f"non-True: {result!r}")


def test_effect_verified_false_when_target_file_not_touched(tmp_path):
    """MUTATION-2 target: the C7 case this audit item exists to catch -- the relaunch
    script runs and exits cleanly (no exception, so the OLD code would have reported
    success) but never actually refreshes the target file. Must report
    effect_verified=False, not True/silently-missing."""
    target_file = tmp_path / "key-levels.json"
    target_file.write_text('{"as_of": "stale"}', encoding="utf-8")
    stale_mtime_before = target_file.stat().st_mtime

    dummy_script = tmp_path / "dummy_refresh_noop.ps1"
    dummy_script.write_text("Write-Output 'dummy-refresh-ran-but-touched-nothing'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"
    lock_file = tmp_path / "level-refresh-watchdog.lock"

    result = _run_invoke_level_refresh_safe_with_target(dummy_script, log_file, lock_file, target_file)
    assert "SKIPPED=False" in result, result
    assert "EFFECT_VERIFIED=False" in result, (
        f"target file was NOT touched by the dummy script (silent no-op relaunch, the "
        f"exact incident shape) but effect_verified did not come back False: {result!r}")
    assert target_file.stat().st_mtime == stale_mtime_before, "sanity: target truly untouched"
