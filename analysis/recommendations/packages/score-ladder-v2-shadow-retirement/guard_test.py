"""guard_test.py -- guard for the score-ladder-v2-shadow-retirement package.

Packet row: score-ladder-v2-shadow-retirement (RULE MET 2026-09-05; prereg
analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json KILLED: extras net
-$13,760 risky-1 / -$13,435 risky-3-era over 28 sessions; ledger
analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl).

Two independent assertions, per the goal's DONE-WHEN ("guard test that fails before and
passes after"):

1. test_retirement_flag_short_circuits_before_any_write
   Mechanism-level: with change.patch applied, `score_ladder_rung_shadow_nightly.RETIRED`
   is True and `run_for_date` returns 0 and appends ZERO lines to the ledger even when
   `lrr.load_core_rows` is monkeypatched to return non-empty fake data (proves the
   retirement guard fires BEFORE the real replay path, not just "happens to have no data
   today"). FAILS before change.patch is applied (RETIRED does not exist / is False and
   the module would proceed into the real replay).

2. test_scheduled_task_absent
   System-level: `Get-ScheduledTask -TaskName Gamma_LadderRungShadow` must find nothing.
   This assertion is EXPECTED TO FAIL until apply.ps1 actually unregisters the task on
   2026-09-29 -- it is the live proof that the organ is gone, not a mechanism check. Read
   only; never mutates scheduler state itself.

Run: backtest/.venv/Scripts/python.exe analysis/recommendations/packages/score-ladder-v2-shadow-retirement/guard_test.py
Exit 0 = both pass. Exit 1 = at least one failed (prints which).
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BACKTEST = REPO / "backtest"
for _p in (str(REPO), str(BACKTEST), str(BACKTEST / "tools"), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LEDGER_PATH = REPO / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl"
TASK_NAME = "Gamma_LadderRungShadow"


def _ledger_line_count() -> int:
    if not LEDGER_PATH.exists():
        return 0
    return sum(1 for ln in LEDGER_PATH.read_text(encoding="utf-8").splitlines() if ln.strip())


def test_retirement_flag_short_circuits_before_any_write() -> None:
    mod = importlib.import_module("score_ladder_rung_shadow_nightly")
    importlib.reload(mod)
    assert getattr(mod, "RETIRED", False) is True, (
        "RETIRED flag missing or False -- change.patch not applied, or reverted"
    )

    before = _ledger_line_count()

    # Force the "there WOULD have been real data" branch so we prove the guard fires
    # ahead of the replay, not merely that today happens to have no core rows.
    original_load = mod.lrr.load_core_rows
    mod.lrr.load_core_rows = lambda *_a, **_kw: [{"fake": "row"}]
    try:
        rc = mod.run_for_date("2099-01-01", retally=True)
    finally:
        mod.lrr.load_core_rows = original_load

    after = _ledger_line_count()
    assert rc == 0, f"run_for_date should fail-open to 0 when RETIRED, got {rc}"
    assert after == before, (
        f"ledger grew ({before} -> {after}) despite RETIRED=True -- retirement guard did not short-circuit"
    )


def _is_task_registered(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue) -ne $null"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AssertionError(f"could not query Task Scheduler: {exc}") from exc
    return proc.stdout.strip().lower() == "true"


def test_scheduled_task_absent() -> None:
    assert not _is_task_registered(TASK_NAME), (
        f"{TASK_NAME} is still registered -- expected only AFTER apply.ps1 runs "
        f"Unregister-ScheduledTask on 2026-09-29 with GAMMA_FREEZE_OVERRIDE=1"
    )


def main() -> int:
    results = []
    for name, fn in (
        ("test_retirement_flag_short_circuits_before_any_write", test_retirement_flag_short_circuits_before_any_write),
        ("test_scheduled_task_absent", test_scheduled_task_absent),
    ):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as exc:
            results.append((name, False, str(exc)))
    ok = True
    for name, passed, msg in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}" + (f" -- {msg}" if msg else ""))
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
