"""Guard for the 2026-07-06 TV-launch serialization + ErrorActionPreference fix.

Regression found in tonight's full-day audit: run-tv-watchdog.ps1 had 3 call sites
invoking launch_tv_debug.ps1 via a raw `& powershell.exe ... 2>&1 | Out-File` pattern
that never got the 2026-06-15 fix (ErrorActionPreference='Continue' around the
child-process call). PS 5.1 wraps a native command's stderr as a TERMINATING
NativeCommandError under the inherited 'Stop' preference -- that is the exact
mechanism behind the original "TV came up but CDP was never verified -> heartbeat ran
all morning on ERROR_TV" incident, and run-tv-watchdog.ps1 was still exposed to it via
3 unfixed call sites. Separately: Gamma_LaunchTV and Gamma_TvWatchdog can both decide to
kill+relaunch on the same tick (confirmed 2026-07-06: both fired the identical -Kill
command at the identical second, 09:43:32 ET) -- Invoke-TvLaunchSafe in _shared.ps1
serializes them via a lock file so only one kill+relaunch runs at a time.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
SHARED = SCRIPTS / "_shared.ps1"
WATCHDOG = SCRIPTS / "run-tv-watchdog.ps1"
LAUNCH = SCRIPTS / "run-launch-tv.ps1"
LOCK_FILE = REPO / "automation" / "state" / "tv-launch.lock"


def test_shared_defines_invoke_tv_launch_safe():
    src = SHARED.read_text(encoding="utf-8")
    assert "function Invoke-TvLaunchSafe" in src
    assert "$ErrorActionPreference = 'Continue'" in src
    assert "tv-launch.lock" in src


def test_watchdog_all_three_sites_use_shared_wrapper():
    src = WATCHDOG.read_text(encoding="utf-8")
    assert "powershell.exe -NoProfile" not in src, (
        "run-tv-watchdog.ps1 still has a raw powershell.exe invocation -- "
        "must route through Invoke-TvLaunchSafe"
    )
    # Count actual invocations ("$r = Invoke-TvLaunchSafe ..."), not bare substring
    # hits -- a comment mentioning the function name would inflate a naive count.
    n = len(re.findall(r"\$\w+\s*=\s*Invoke-TvLaunchSafe\b", src))
    assert n == 3, (
        f"expected exactly 3 Invoke-TvLaunchSafe call sites (relaunch_kill, "
        f"relaunch_fresh, relaunch_hung_bridge), found {n}"
    )


def test_launch_tv_uses_shared_wrapper():
    src = LAUNCH.read_text(encoding="utf-8")
    assert "powershell.exe -NoProfile" not in src
    assert "Invoke-TvLaunchSafe" in src


def _run_invoke_tv_launch_safe(dummy_launch: Path, log_file: Path, port: int = 9) -> str:
    # port=9 (TCP "discard" service, never listens on Windows) makes Test-CdpReady fail
    # fast and deterministically without touching the real CDP port 9222 or the real TV app.
    # CdpTimeoutSec=2 keeps the test fast (production default stays 12s).
    ps_cmd = (
        f". '{SHARED}'; "
        f"$r = Invoke-TvLaunchSafe -LaunchScript '{dummy_launch}' -LogFile '{log_file}' "
        f"-Port {port} -CdpTimeoutSec 2; "
        f"Write-Output \"SKIPPED=$($r.skipped)\"; "
        f"Write-Output \"HEALED=$($r.healed)\""
    )
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout + out.stderr


def test_shared_defines_test_cdp_ready():
    """2026-07-31 fix: Invoke-TvLaunchSafe used to return only {skipped}, giving callers
    no way to tell a relaunch ATTEMPT from a relaunch that actually restored CDP. Live
    incident: Gamma_TvWatchdog logged RELAUNCH_KILL at 09:05 and 09:10 ET while CDP stayed
    down the whole time -- self_check.py was the only thing that eventually caught it."""
    src = SHARED.read_text(encoding="utf-8")
    assert "function Test-CdpReady" in src
    assert "$healed = Test-CdpReady" in src
    assert re.search(r"return\s+@\{\s*skipped\s*=\s*\$false;\s*healed\s*=\s*\$healed\s*\}", src)


def test_lock_blocks_a_concurrent_launch(tmp_path):
    """Non-vacuous bite: a FRESH lock file must make the function skip WITHOUT
    invoking the launch script at all. Uses a harmless dummy .ps1, never the real
    TradingView launcher."""
    dummy_launch = tmp_path / "dummy_launch.ps1"
    dummy_launch.write_text("Write-Output 'dummy-ran'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text("held", encoding="utf-8")
    try:
        result = _run_invoke_tv_launch_safe(dummy_launch, log_file)
        assert "SKIPPED=True" in result, result
        assert not log_file.exists(), "dummy launch must NOT run while the lock is fresh"
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def test_no_lock_allows_launch_and_cleans_up(tmp_path):
    """Non-vacuous bite: with no lock present, the function must proceed, actually
    invoke the launch script, and clean up the lock file afterward."""
    dummy_launch = tmp_path / "dummy_launch.ps1"
    dummy_launch.write_text("Write-Output 'dummy-ran'\n", encoding="utf-8")
    log_file = tmp_path / "dummy.log"

    LOCK_FILE.unlink(missing_ok=True)
    try:
        result = _run_invoke_tv_launch_safe(dummy_launch, log_file)
        assert "SKIPPED=False" in result, result
        assert log_file.exists()
        assert "dummy-ran" in log_file.read_text(encoding="utf-8")
        assert not LOCK_FILE.exists(), "lock file must be cleaned up after a completed call"
        # 2026-07-31: dummy launch never opens port 9 -> Test-CdpReady must correctly
        # report healed=False rather than assuming "ran the script" == "it worked".
        assert "HEALED=False" in result, result
    finally:
        LOCK_FILE.unlink(missing_ok=True)
        log_file.unlink(missing_ok=True)


def test_watchdog_escalates_on_failed_selfheal():
    """2026-07-31: a relaunch that RAN but did not restore CDP must be visibly distinct
    from a routine relaunch line in STATUS.md (append-only BROKEN block), not silently
    re-logged as the same "relaunch_kill" shape every 5min while an outage continues."""
    src = WATCHDOG.read_text(encoding="utf-8")
    for suffix in ["relaunch_kill_FAILED", "relaunch_fresh_FAILED", "relaunch_hung_bridge_FAILED"]:
        assert suffix in src, f"missing FAILED escalation path: {suffix}"
    for suffix in ["relaunch_kill_healed", "relaunch_fresh_healed", "relaunch_hung_bridge_healed"]:
        assert suffix in src, f"missing healed confirmation path: {suffix}"
    assert '$tvAction -like "*_FAILED"' in src
    assert "### BROKEN: TV-CDP self-heal failed" in src
