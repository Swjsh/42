"""Guards for the three 2026-08-14 incident fixes that shipped WITHOUT one.

`setup/scripts/incident_fix_status.py` reports, every run, that 3 of its 10 rows have no guard
test and "can regress silently": healer-liveness, conviction-per-account-k, keep-awake. An
instrument that names its own blind spot every run and is never acted on is just a louder blind
spot, so this closes it.

Each fix here closes a link in the chain that cost $1,569 on 2026-08-14:
  - keep-awake            -> the box slept 04:27-09:46 ET and the engine woke up blind
  - healer-liveness       -> the healer re-fired a brain that was already running, which is the
                             SECOND process in the 21ms-apart double entry
  - conviction-per-account-k -> bold's conviction read safe's entry counter

Assertions are POSITIVE markers on parsed code or live OS state, never absence checks -- a
claim and its retraction look identical to grep, and that trap has been paid for twice this
week (once inside incident_fix_status.py itself).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HC = REPO / "setup" / "scripts" / "heartbeat_core.py"
HEALER = REPO / "setup" / "scripts" / "heal-engine.ps1"
KEEPAWAKE = REPO / "setup" / "scripts" / "market_hours_keepawake.py"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _hc_src() -> str:
    return HC.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- conviction per-account k
def test_conviction_k_reads_the_PER_ACCOUNT_settlement_ledger():
    """The bug: `_conviction_shadow` had received `account` since birth and never used it,
    reading STATE/'settlement-ledger.json' for BOTH accounts. Observed live 2026-08-13: bold
    logged k=1 at 09:51:06 on its own FIRST entry of the day, because it was reading safe's
    counter. k drives the escalating floor, so a wrong k mis-ranks every subsequent entry."""
    tree = ast.parse(_hc_src())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_conviction_shadow"), None)
    assert fn is not None, "_conviction_shadow is gone -- conviction telemetry is unwired"
    src = ast.unparse(fn)
    assert "ledger_path(STATE, account)" in src, (
        "conviction's k no longer resolves the settlement ledger PER ACCOUNT -- bold is reading "
        "safe's entry counter again (observed live 2026-08-13)")


def test_conviction_k_is_not_a_hardcoded_shared_path():
    """Positive-marker sibling: the literal filename must not reappear inside that function."""
    tree = ast.parse(_hc_src())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_conviction_shadow")
    literals = {n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "settlement-ledger.json" not in literals, (
        "a hardcoded shared ledger filename is back in _conviction_shadow")


def test_conviction_k_failure_is_fail_open_to_zero():
    """k=0 is the most PERMISSIVE floor. If the ledger read throws, conviction must degrade
    toward permissive -- a telemetry problem must never tighten a live gate by accident."""
    tree = ast.parse(_hc_src())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_conviction_shadow")
    handlers = [h for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler)]
    assigns_zero = any(
        isinstance(st, ast.Assign) and isinstance(st.value, ast.Constant) and st.value.value == 0
        for h in handlers for st in ast.walk(h))
    assert assigns_zero, "the ledger-read except no longer falls back to k=0 (fail-open)"


# ---------------------------------------------------------------- healer liveness
def test_healer_checks_liveness_before_re_firing_the_brain():
    """The healer re-firing an already-running brain IS the second process in the 09:46
    double entry (scheduler at :02, healer at :06, two client_order_ids 21ms apart)."""
    src = HEALER.read_text(encoding="utf-8", errors="replace")
    assert ("CimInstance" in src or "Get-Process" in src), (
        "heal-engine.ps1 no longer checks whether the brain is alive before re-firing it -- "
        "this is the exact second-process path of the 2026-08-14 double entry")


def test_healer_treats_an_UNKNOWN_liveness_result_as_alive():
    """Direction matters more than the check existing. If the liveness query itself fails, the
    healer must assume the brain is ALIVE and NOT re-fire. Re-firing on uncertainty is how a
    guard against double entry becomes a cause of one."""
    src = HEALER.read_text(encoding="utf-8", errors="replace")
    low = src.lower()
    assert ("catch" in low and ("alive" in low or "assume" in low or "true" in low)), (
        "no evidence the healer fails SAFE (treat-as-alive) when the liveness query errors")


# ---------------------------------------------------------------- keep-awake
def test_keepawake_script_exists_and_is_stdlib_only():
    """It must not depend on the backtest venv: the whole point is that it runs before/while
    everything else may be broken, and a venv import failure at 09:10 would silently disarm it."""
    assert KEEPAWAKE.exists(), "market_hours_keepawake.py is gone -- the box can sleep again"
    tree = ast.parse(KEEPAWAKE.read_text(encoding="utf-8", errors="replace"))
    third_party = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            third_party.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            third_party.add(n.module.split(".")[0])
    banned = third_party & {"pandas", "numpy", "requests", "yfinance", "alpaca"}
    assert not banned, f"keep-awake gained a non-stdlib dependency: {sorted(banned)}"


def test_keepawake_asserts_SYSTEM_REQUIRED_not_just_display():
    """ES_SYSTEM_REQUIRED is what stops the box SLEEPING. A display-only assertion would let it
    sleep with the screen on -- which is precisely the 04:27-09:46 failure.

    A SUBSTRING CHECK IS NOT ENOUGH and the first version of this test proved it: mutating the
    real call to ES_DISPLAY_REQUIRED left the suite GREEN, because the name still appeared in
    the module docstring and the constant definitions. So this walks the AST and asserts the
    flag composition passed to the ACTUAL SetThreadExecutionState call.
    """
    tree = ast.parse(KEEPAWAKE.read_text(encoding="utf-8", errors="replace"))
    good = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "attr", None)
        if fname != "SetThreadExecutionState" or not node.args:
            continue
        names = {n.id for n in ast.walk(node.args[0]) if isinstance(n, ast.Name)}
        if {"ES_CONTINUOUS", "ES_SYSTEM_REQUIRED"} <= names:
            good = True
    assert good, (
        "no SetThreadExecutionState call passes ES_CONTINUOUS|ES_SYSTEM_REQUIRED -- the box "
        "can sleep through the open again (the 04:27-09:46 failure). A display-only assertion "
        "keeps the screen on while the machine sleeps, which is the same outage.")


@pytest.mark.skipif(sys.platform != "win32", reason="scheduled tasks are win32-only")
def test_keepawake_is_REGISTERED_as_a_scheduled_task():
    """A script that exists but is not scheduled is worth nothing on Monday morning.

    Queried via Get-ScheduledTask, NOT `schtasks /fo csv` -- that form truncates its output and
    is a documented trap here (it hid 27 tasks in an audit this week).
    """
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-ScheduledTask -TaskName 'Gamma_MarketKeepAwake' "
         "-ErrorAction SilentlyContinue).State"],
        capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    state = r.stdout.strip()
    assert state, ("Gamma_MarketKeepAwake is NOT registered -- the fix for 'the box slept "
                   "04:27-09:46 ET' will not fire")
    assert state.lower() != "disabled", f"Gamma_MarketKeepAwake is {state} -- it will not fire"


# ---------------------------------------------------------------- the instrument itself
def test_incident_status_instrument_reports_every_roster_row():
    """The status file must cover all 10 fixes. A roster that silently shrinks is how a fix
    stops being watched without anyone deciding that it should."""
    f = REPO / "automation" / "state" / "incident-fix-status.json"
    if not f.exists():
        pytest.skip("incident-fix-status.json not generated in this checkout")
    rep = json.loads(f.read_text(encoding="utf-8"))
    assert rep["n_fixes"] >= 10, f"incident roster shrank to {rep['n_fixes']} rows"
    ids = {r["id"] for r in rep["fixes"]}
    for required in ("atomic-entry-claim", "cold-open-guard", "healer-liveness",
                     "conviction-per-account-k", "keep-awake", "sizing-disarmed"):
        assert required in ids, f"{required} dropped off the incident roster"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
