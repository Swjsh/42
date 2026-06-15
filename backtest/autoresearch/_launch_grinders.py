"""Launch overnight_grinder and sniper_real_fills_grinder in parallel.

Overnight grinder: --reset --hours 4 --workers 4
Sniper real fills: --reset --hours 4 --workers 4

Run with: backtest\.venv\Scripts\python.exe backtest\autoresearch\_launch_grinders.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import datetime as dt

REPO = pathlib.Path("C:/Users/jackw/Desktop/42")
PYTHON = str(REPO / "backtest/.venv/Scripts/python.exe")
CREATE_NO_WINDOW = 0x08000000

def archive_keepers(state_dir: pathlib.Path, tag: str) -> None:
    """Archive existing keepers.jsonl with a timestamped backup."""
    k = state_dir / "keepers.jsonl"
    if k.exists() and k.stat().st_size > 0:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M")
        backup = state_dir / f"keepers_archived_{ts}_{tag}.jsonl"
        shutil.copy2(k, backup)
        print(f"  Archived {k.name} -> {backup.name}")
        # Print summary of what's being archived
        lines = k.read_text(encoding="utf-8").strip().split("\n")
        print(f"  ({len(lines)} keepers archived)")
        # Show best
        best = None
        for line in lines:
            try:
                r = json.loads(line)
                wp = r.get("wide_pnl", float("-inf"))
                if best is None or wp > best[0]:
                    best = (wp, r.get("edge_capture"), r.get("combo"))
            except Exception:
                pass
        if best:
            print(f"  Best keeper: wide_pnl=${best[0]:.0f}  edge=${best[1]:.0f}")
            print(f"  Combo: {best[2]}")

def kill_existing(module: str) -> int:
    """Kill any running instances of the given grinder module. Returns count killed.

    Uses WMIC (no external Python module required) to find processes whose
    CommandLine contains the module name, then kills them via taskkill.
    Skips our own PID so we never suicide.
    """
    my_pid = os.getpid()
    killed = 0
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             f"commandline like '%{module}%'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            if pid == my_pid:
                continue
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5,
                           creationflags=CREATE_NO_WINDOW)
            killed += 1
    except Exception as exc:
        print(f"  [kill_existing] warning: {exc}")
    return killed


def launch_grinder(module: str, hours: float, workers: int, reset: bool = True) -> subprocess.Popen:
    cmd = [PYTHON, "-m", module, "--hours", str(hours), "--workers", str(workers)]
    if reset:
        cmd.append("--reset")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "backtest")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO / "backtest"),
        env=env,
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc

def main():
    # --- Archive overnight_grinder keepers ---
    og_state = REPO / "backtest/autoresearch/_state/overnight_grinder"
    og_state.mkdir(parents=True, exist_ok=True)
    print("Archiving overnight_grinder keepers...")
    archive_keepers(og_state, "before_restart")

    # --- Archive sniper_real_fills keepers ---
    sf_state = REPO / "backtest/autoresearch/_state/sniper_real_fills_stage1"
    sf_state.mkdir(parents=True, exist_ok=True)
    k = sf_state / "keepers.jsonl"
    if k.exists() and k.stat().st_size > 0:
        print("Archiving sniper_real_fills keepers...")
        archive_keepers(sf_state, "before_restart")

    print()
    print("Killing any existing overnight_grinder instances...")
    n = kill_existing("autoresearch.overnight_grinder")
    print(f"  Killed {n} existing instance(s)")

    import time
    time.sleep(1)

    print("Launching overnight_grinder (reset + 4h + 4 workers)...")
    og_proc = launch_grinder("autoresearch.overnight_grinder", hours=4.0, workers=4, reset=True)
    print(f"  PID: {og_proc.pid}")

    time.sleep(2)  # small gap to avoid state file race

    print("Killing any existing sniper_real_fills_grinder instances...")
    n = kill_existing("autoresearch.sniper_real_fills_grinder")
    print(f"  Killed {n} existing instance(s)")
    time.sleep(1)

    print("Launching sniper_real_fills_grinder (reset + 4h + 4 workers)...")
    sf_proc = launch_grinder("autoresearch.sniper_real_fills_grinder", hours=4.0, workers=4, reset=True)
    print(f"  PID: {sf_proc.pid}")

    print()
    print("Both grinders launched. PIDs:")
    print(f"  overnight_grinder      PID={og_proc.pid}  deadline=+4h")
    print(f"  sniper_real_fills      PID={sf_proc.pid}  deadline=+4h")
    print()
    print("Monitor via:")
    print("  Get-Content backtest\\autoresearch\\_state\\overnight_grinder\\grinder.log -Tail 5")
    print("  Get-Content backtest\\autoresearch\\_state\\sniper_real_fills_stage1\\grinder.log -Tail 5")

    # Save PIDs for reference
    pids_path = REPO / "backtest/autoresearch/_state/active_grinders.json"
    pids_path.write_text(json.dumps({
        "launched_at": dt.datetime.now().isoformat(),
        "overnight_grinder": og_proc.pid,
        "sniper_real_fills": sf_proc.pid,
    }, indent=2), encoding="utf-8")
    print(f"\nPIDs saved to {pids_path}")

if __name__ == "__main__":
    main()
