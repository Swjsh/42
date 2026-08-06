"""D3 guard -- no pytest may append rows to the PRODUCTION core-decisions.jsonl.

THE INCIDENT (2026-08-06, EOD-2026-08-06-FULL-REVIEW "Still owed" #3): an unidentified
writer had injected 322 synthetic rows (armed=false, core_tick_id=null, spy=751.0,
vix=16.0, spread 10, premarket timestamps) into the LIVE decision ledger
automation/state/core-decisions.jsonl. Write-pattern forensics this session identified it:
`backtest/tests/test_g4_extra_setup_routing.py` section 6 (test_structure_veto_blocks_
extra_setup_route + test_non_veto_hold_still_routes_extra_setup) drives the REAL
heartbeat_core.run_account() with the data fetch monkeypatched but `_log` NOT patched, so
every suite run appended the exact blocked/placed pair straight into production via
heartbeat_core._log() -> LEDGER (heartbeat_core.py:813-815). 322 rows = 161 suite runs;
the 751.0/16.0/spread-10 fingerprint is that file's _payload_stub() verbatim. Every OTHER
run_account-driving test file already captured _log (test_blind_no_levels_2026_07_30.py:98,
test_gate_provenance_ordering_2026_07_10.py:92, test_context_bundle_tag_no_behavior_
change.py:270, test_core_entry_idempotency_guard_2026_08_02.py:329) -- the g4 file was the
one leaker.

THE GUARD (graduated, OP-25 / C7): a STATIC source scan -- every test file under
backtest/tests/ whose source calls `run_account(` must also monkeypatch/capture `"_log"`.
A future test that drives the real engine loop without neutralizing its ledger writer REDs
here before it can ever poison production. (A runtime conftest redirect alone cannot close
this: heartbeat_core may be first-imported MID-test, after any autouse fixture ran.)

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_no_ledger_leak_from_tests_2026_08_06.py
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

# Files allowed to reference run_account( without a "_log" patch:
#   - this guard itself (the strings appear in its docstring/source scan)
_EXEMPT = {Path(__file__).name}


def _test_files() -> list[Path]:
    return sorted(p for p in HERE.glob("test_*.py") if p.name not in _EXEMPT)


def test_every_run_account_driving_test_file_patches_log():
    """Any test file that calls run_account( must reference a "_log" patch in its source."""
    offenders = []
    for p in _test_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        # Only files that DRIVE the engine loop (call it), not ones that merely mention it.
        if "run_account(" not in src:
            continue
        if '"_log"' not in src and "'_log'" not in src:
            offenders.append(p.name)
    assert not offenders, (
        "These test files drive heartbeat_core.run_account() without patching _log -- "
        f"every suite run appends REAL rows to production core-decisions.jsonl (D3): {offenders}"
    )


def test_g4_file_specifically_patches_log():
    """Pin the named 2026-08-06 offender directly (non-vacuous even if the scan above is
    ever weakened): test_g4_extra_setup_routing.py must patch _log."""
    src = (HERE / "test_g4_extra_setup_routing.py").read_text(encoding="utf-8", errors="replace")
    assert '"_log"' in src, (
        "test_g4_extra_setup_routing.py no longer patches heartbeat_core._log -- the D3 "
        "synthetic-row ledger leak (322 rows, spy=751.0/vix=16.0 fingerprint) is back."
    )


def test_scan_is_non_vacuous():
    """The scan must actually be looking at files that call run_account( -- if the glob or
    the call-pattern ever silently stops matching, this REDs instead of green-by-vacuity."""
    driving = [p.name for p in _test_files()
               if "run_account(" in p.read_text(encoding="utf-8", errors="replace")]
    assert len(driving) >= 4, (
        f"expected >=4 run_account-driving test files (blind_no_levels, g4, context_bundle, "
        f"idempotency, gate_provenance...), found {driving} -- the leak scan went vacuous."
    )
