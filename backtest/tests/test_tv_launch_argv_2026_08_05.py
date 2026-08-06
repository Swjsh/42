"""Guards for Invoke-TvLaunchSafe's 2026-08-05 argv fix + 2026-08-06 non-blocking fix.

CONTEXT (two stacked defects, one function):

1. ARGV FIX (2026-08-05, live incident): `@killArg` array-SPLAT into a NATIVE command
   (powershell.exe) does not splat -- it emitted a malformed token the child bound
   positionally to launch_tv_debug.ps1's [int]$Port, throwing BEFORE the script body ran.
   Invoke-TvLaunchSafe -Kill therefore NEVER launched anything, silently (healed was
   computed from Test-CdpReady, which is True whenever TV happens to already be alive).
   Fix: build ONE explicit $psArgs array, no splat. This guard was CITED in _shared.ps1
   the morning it shipped but never written (L249 class) -- authored 2026-08-06 evening
   by the Monday-readiness lane, which RED-proved the fix through the real watchdog path.

2. NON-BLOCKING FIX (2026-08-06 evening, exposed BY the argv fix): the
   `& powershell.exe $psArgs 2>&1 | Out-File` pipeline BLOCKED until TradingView itself
   exited -- launch_tv_debug.ps1 starts TV via [Diagnostics.Process]::Start with
   UseShellExecute=$false and no redirection, so TV INHERITS the child's stdout handle
   and the pipeline can never complete while TV runs. Masked pre-argv-fix because the
   child died instantly. Live repro 2026-08-06 18:48 ET: watchdog tick healed TV+CDP,
   then hung 12+ min; production Gamma_TvWatchdog (ExecutionTimeLimit=PT4M) would have
   been KILLED before logging healed/*_FAILED -- the 2026-07-31 escalation machinery was
   unreachable in exactly the scenario it exists for. Fix: Start-Process with sidecar
   file redirection + Wait-Process on the CHILD ONLY (file handles block nobody).

Text assertions (no Pester harness, per test_tv_launch_safe_2026_07_06.py convention)
plus one functional hang-repro bite.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "setup" / "scripts" / "_shared.ps1"
LOCK_FILE = REPO / "automation" / "state" / "tv-launch.lock"


def _invoke_block() -> str:
    """The Invoke-TvLaunchSafe function body only (don't let sibling functions
    satisfy an assertion by accident)."""
    src = SHARED.read_text(encoding="utf-8")
    m = re.search(r"function Invoke-TvLaunchSafe \{.*?\nfunction ", src, re.DOTALL)
    assert m, "could not isolate Invoke-TvLaunchSafe block"
    return m.group(0)


def _code_only(block: str) -> str:
    """Strip full-line comments: the function's own incident comments legitimately QUOTE
    the banned patterns (`@killArg`, the blocking pipeline) while documenting them --
    negative assertions must only see executable lines."""
    return "\n".join(
        line for line in block.splitlines() if not line.lstrip().startswith("#")
    )


def test_argv_is_one_explicit_array_no_splat():
    block = _invoke_block()
    assert re.search(r"\$psArgs\s*=\s*@\(", block), "explicit $psArgs array missing"
    assert re.search(r"if \(\$Kill\) \{ \$psArgs \+= '-Kill' \}", block), (
        "-Kill must be appended to the SAME argv array, never splatted separately"
    )
    assert "@killArg" not in _code_only(block), "the broken @killArg splat pattern is back"
    assert "'-File', $LaunchScript" in block, "argv must pass -File <LaunchScript>"


def test_no_blocking_pipeline_on_the_native_child():
    """The exact pattern that hung the tick: piping the native child's output. Any
    `& powershell.exe ... |` pipeline in this function re-introduces the TV-inherited-
    handle hang, no matter what it pipes into."""
    block = _code_only(_invoke_block())
    assert not re.search(r"&\s+powershell\.exe[^\n]*\|", block), (
        "Invoke-TvLaunchSafe pipes the native child's output again -- TradingView "
        "inherits the stdout handle and the pipeline blocks until TV exits (2026-08-06)"
    )


def test_start_process_wait_process_with_timeout():
    block = _invoke_block()
    assert "Start-Process -FilePath 'powershell.exe' -ArgumentList $psArgs" in block
    assert "-RedirectStandardOutput" in block and "-RedirectStandardError" in block, (
        "child stdio must go to sidecar FILES (TV inherits file handles harmlessly)"
    )
    assert re.search(r"Wait-Process -Id \$proc\.Id -Timeout \d+", block), (
        "must wait on the CHILD process only, with a bounded timeout"
    )


def test_cdp_timeout_default_covers_cold_boot():
    """12s structurally cannot see a genuine heal (cold TV boot-to-CDP measured >29s on
    2026-08-06) -- every real relaunch would log *_FAILED + STATUS.md BROKEN spam."""
    block = _invoke_block()
    m = re.search(r"\[int\]\$CdpTimeoutSec\s*=\s*(\d+)", block)
    assert m, "CdpTimeoutSec param missing"
    assert int(m.group(1)) >= 60, (
        f"CdpTimeoutSec default {m.group(1)}s cannot cover a measured >29s cold boot "
        "with margin -- the *_FAILED escalation would cry wolf on every real relaunch"
    )


def test_function_returns_while_longlived_child_grandchild_still_runs(tmp_path):
    """FUNCTIONAL hang repro (the 2026-08-06 live incident in miniature): the dummy
    launch script spawns a detached 120s sleeper via the SAME Process.Start/
    UseShellExecute=$false mechanism launch_tv_debug.ps1 uses for TradingView, so the
    sleeper inherits the child's stdout handle exactly like TV does. OLD code: the
    pipeline stays open until the sleeper dies -> this test times out. NEW code:
    Wait-Process returns when the CHILD powershell exits (~2s) and the function
    completes. Port 9 (never listens) + CdpTimeoutSec 2 keep Test-CdpReady fast and
    away from the real CDP port; the real TV app is never touched."""
    dummy = tmp_path / "dummy_launch_longlived.ps1"
    dummy.write_text(
        "param([int]$Port = 9222, [switch]$Kill)\n"
        "$psi = New-Object System.Diagnostics.ProcessStartInfo("
        "'powershell.exe', '-NoProfile -NonInteractive -Command Start-Sleep -Seconds 120')\n"
        "$psi.UseShellExecute = $false\n"
        "[System.Diagnostics.Process]::Start($psi) | Out-Null\n"
        "Write-Output 'dummy-launched-longlived'\n",
        encoding="utf-8",
    )
    log_file = tmp_path / "dummy.log"
    LOCK_FILE.unlink(missing_ok=True)
    ps_cmd = (
        f". '{SHARED}'; "
        f"$r = Invoke-TvLaunchSafe -LaunchScript '{dummy}' -LogFile '{log_file}' "
        f"-Port 9 -CdpTimeoutSec 2; "
        f"Write-Output \"SKIPPED=$($r.skipped) HEALED=$($r.healed)\""
    )
    # stdout/stderr go to FILES, not capture_output pipes: the detached sleeper inherits
    # every inheritable handle down the chain (Windows bInheritHandles=TRUE), so a python
    # pipe would never see EOF until the sleeper dies even though the function returned --
    # that would re-create the hang at the TEST layer and mask the fix under test.
    out_f = tmp_path / "outer.out"
    err_f = tmp_path / "outer.err"
    t0 = time.monotonic()
    try:
        with out_f.open("w") as fo, err_f.open("w") as fe:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                stdout=fo, stderr=fe, text=True, timeout=90,
            )
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "Invoke-TvLaunchSafe hung past 90s with a long-lived grandchild holding "
            "the inherited stdout handle -- the 2026-08-06 TV-pipeline hang is back"
        )
    finally:
        LOCK_FILE.unlink(missing_ok=True)
    elapsed = time.monotonic() - t0
    text = out_f.read_text(encoding="utf-8", errors="replace") + err_f.read_text(
        encoding="utf-8", errors="replace")
    assert "SKIPPED=False" in text, text
    assert elapsed < 60, f"took {elapsed:.1f}s -- should return seconds after the child exits"
    assert log_file.exists() and "dummy-launched-longlived" in log_file.read_text(encoding="utf-8"), (
        "child output must still be copied into the caller's LogFile"
    )
