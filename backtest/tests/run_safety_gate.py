#!/usr/bin/env python
"""Safety gate -- the curated guard suite that MUST pass before any commit touches
the trading/doctrine surface.

Wired three ways:
  1. git pre-commit hook (setup/install-git-hooks.ps1) -- blocks a local commit.
  2. CI on push (.github/workflows/safety-gate.yml) -- the bypass-proof backstop.
  3. the autonomy actuator (setup/scripts/autonomy_actuator.py) -- gates an
     autonomous J-approved apply BEFORE it commits; a red gate => snapshot restore.

Curated for SPEED (a slow pre-commit hook just gets bypassed). These are the
self-modification-critical guards only -- each encodes a graduated lesson or a
params<->code contract whose violation would let a bad change ship. Use --full to
run the entire backtest/tests suite (CI does this on top of the curated gate).

Exit 0 = all green (safe to commit). Exit 1 = a gate failed (do NOT commit).
Anchored to the repo root; runs under backtest/.venv if present.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO / "backtest" / "tests"

# The curated gate. Each line is a guard that protects autonomous self-modification.
# Keep this list FAST (each <2s, no backtests / no live-state / no network) -- it runs
# on EVERY commit and before every autonomous apply. Measured: ~2s total.
GATE_TESTS = [
    "test_verify_committed.py",        # new files are git-tracked (L62: --only drops untracked)
    "test_op25_index_reconciliation.py",    # LESSONS-LEARNED <-> CLAUDE.md index ratchet (guards doc-fold applies)
    "test_killswitch_threshold_parity.py",  # risk kill-switch parity (Rule 5) -- guards params applies
    "test_params_filters_drift.py",    # params.json <-> filters.py stay in sync (C14) -- guards params applies
    "test_scheduled_tasks_doc.py",     # SCHEDULED-TASKS.md registry matches reality
    "test_engine_cli_parity.py",       # engine_cli.decide_payload output contract (SAFETY-GATE-MISSES-PARITY-SUITE,
                                        # 2026-07-27: commit 3ced7457 broke 16 parity cases and PASSED this gate
                                        # because this suite wasn't in it -- ~3.3s, no reason to keep it out)
]
# Heavy guards that are too slow (backtests) or validate mutable LIVE runtime state --
# NOT suitable for a per-commit gate. They run in CI / `--full` and in the scheduled
# lesson-regression audit instead, where minutes are acceptable.
#   test_graduated_guards.py   (>180s -- runs backtests)
#   test_state_contracts.py    (validates live loop-state.json -- transient runtime state)
#   test_commit_scoped.py      (2026-08-01: EVALUATED for this list, deliberately left out.
#                               Same shape as test_verify_committed.py (real throwaway-repo
#                               git subprocesses) but 9 tests vs 4 -- measured +4.5-5s on
#                               this box (2 back-to-back A/B runs: baseline 6 suites 7.3-8.5s
#                               -> 7 suites 12.6-13.1s with it added), which breaks this
#                               gate's own "keep FAST, runs on EVERY commit" contract. Still
#                               runs in `--full` / CI. Re-measure before adding -- don't
#                               assume the test_verify_committed.py precedent transfers.


_SUMMARY_COUNT_RE = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")


def _parse_pytest_counts(output: str) -> dict[str, int]:
    """Parse pytest's short-summary counts (passed/failed/error/...) out of captured
    stdout+stderr. Defends against a trusted-but-wrong exit code (C7: audit outputs, not
    exit codes -- SAFETY-GATE-MISSES-PARITY-SUITE, 2026-07-27: a backgrounded `pytest -k`
    run once reported exit 0 while 17 cases had actually failed, and the exit code was
    trusted instead of the output). Returns {} if no recognizable summary line exists
    (e.g. a collection crash) -- callers must still honor the raw exit code in that case."""
    counts: dict[str, int] = {}
    for m in _SUMMARY_COUNT_RE.finditer(output):
        n, word = int(m.group(1)), m.group(2)
        key = "error" if word in ("error", "errors") else word
        counts[key] = counts.get(key, 0) + n
    return counts


def _venv_python() -> str:
    """Prefer backtest/.venv (where pandas/pytest live -- system Python lacks them).
    Falls back to the current interpreter so the gate still runs in CI containers."""
    for cand in (
        REPO / "backtest" / ".venv" / "Scripts" / "python.exe",  # Windows
        REPO / "backtest" / ".venv" / "bin" / "python",          # POSIX / CI
    ):
        if cand.exists():
            return str(cand)
    return sys.executable


def run(full: bool = False) -> int:
    py = _venv_python()
    if full:
        targets = [str(TESTS_DIR)]
        label = "FULL backtest suite"
    else:
        # Only include gate tests that actually exist (a renamed/removed test must
        # not silently skip the gate -- we report it loudly instead).
        targets, missing = [], []
        for t in GATE_TESTS:
            p = TESTS_DIR / t
            (targets if p.exists() else missing).append(str(p if p.exists() else t))
        if missing:
            print("[safety-gate] WARNING: curated gate test(s) not found: " + ", ".join(missing))
        if not targets:
            print("[safety-gate] FAIL: no curated gate tests found at all -- refusing to pass open.")
            return 1
        label = f"curated safety gate ({len(targets)} suites)"

    print(f"[safety-gate] running {label} via {Path(py).name} ...")
    cmd = [py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *targets]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output, end="" if output.endswith("\n") else "\n")

    # Never trust the exit code alone (C7 / SAFETY-GATE-MISSES-PARITY-SUITE): parse the
    # pytest summary counts out of the captured output and cross-check.
    counts = _parse_pytest_counts(output)
    failed_or_errored = counts.get("failed", 0) + counts.get("error", 0)

    if proc.returncode == 0 and failed_or_errored > 0:
        print(
            f"[safety-gate] FAIL -- exit code was 0 but the parsed summary shows "
            f"{failed_or_errored} failed/errored ({counts}) -- trusting the output, "
            f"not the exit status. Do NOT commit."
        )
        return 1

    if proc.returncode == 0:
        print(f"[safety-gate] PASS -- {label} green ({counts or 'no summary line found'}). Safe to commit.")
        return 0

    print(f"[safety-gate] FAIL -- a guard tripped (exit {proc.returncode}, parsed {counts}). Do NOT commit.")
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the autonomous self-modification safety gate.")
    ap.add_argument("--full", action="store_true", help="run the entire backtest/tests suite, not just the curated gate")
    args = ap.parse_args()
    return run(full=args.full)


if __name__ == "__main__":
    raise SystemExit(main())
