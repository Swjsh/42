"""INCIDENT FIX STATUS -- did the fixes from the 2026-08-14 loss morning actually land, and are
they still landed?

WHY THIS EXISTS. J asked "what's the status on the engine fixes from today's losses" for the
third time in one session, and each time I hand-assembled the answer from memory + git log.
OP-33(e): a repeated question is a MISSING INSTRUMENT, not a query. This is the instrument.

WHAT IT REFUSES TO DO. It does not read a checklist of things I claimed. Every row runs a LIVE
check against cold reality -- the file on disk, the flag in params.json, the guard test's exit
code. A fix whose guard test is RED reports RED here no matter how confidently it was
announced, because "shipped" and "still working" are different questions and only the second
one matters the next morning.

INCIDENT: 2026-08-14, -$1,569 by 10:00 ET. Causal chain (journal/2026-08-14.md): the box slept
04:27-09:46 ET; on wake the scheduler (09:46:02) and the healer's re-fire (09:46:06) both
passed the entry check before either wrote a claim -> two processes -> double entry; and the
engine's FIRST look at the day bought the top of a 1.1-point range with 322-minute-stale
levels. Every row below is a fix aimed at one link in that chain.

Read-only. Arms nothing. Exit 0 always (a status instrument that fails its caller is useless).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT = STATE / "incident-fix-status.json"
VENV_PY = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _read(rel: str) -> str:
    try:
        return (REPO / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _params(rel: str = "automation/state/params.json") -> dict:
    try:
        return json.loads(_read(rel))
    except ValueError:
        return {}


def _guard(test_rel: str) -> tuple[bool, str]:
    """Run one guard file. GREEN only on exit 0 -- no interpretation of the output."""
    if not (REPO / test_rel).exists():
        return False, "guard file MISSING"
    if not VENV_PY.exists():
        return False, "backtest venv missing"
    r = subprocess.run([str(VENV_PY), "-m", "pytest", test_rel, "-q", "--tb=no", "-p", "no:randomly"],
                       cwd=str(REPO), capture_output=True, text=True, timeout=240,
                       creationflags=NO_WINDOW)
    last = [ln for ln in r.stdout.splitlines() if "passed" in ln or "failed" in ln or "error" in ln]
    return r.returncode == 0, (last[-1].strip() if last else f"exit {r.returncode}")


# --------------------------------------------------------------------------- the roster
# (id, chain link it closes, live check -> (ok, detail), guard test path or None)
def _chk_claim() -> tuple[bool, str]:
    s = _read("setup/scripts/heartbeat_core.py")
    excl = "os.O_CREAT | os.O_EXCL" in s
    rename = "os.rename(str(path), str(taking))" in s
    gated = 'plan["status"] = "SKIP_DUPLICATE_CLAIM"' in s
    if excl and rename and gated:
        return True, "O_EXCL create + rename-arbitrated stale takeover + placement gated"
    missing = [n for n, v in (("O_EXCL", excl), ("rename-takeover", rename),
                              ("placement gate", gated)) if not v]
    return False, "MISSING: " + ", ".join(missing)


def _chk_cold_open() -> tuple[bool, str]:
    s = _read("setup/scripts/heartbeat_core.py")
    if "_cold_open_block(" not in s or 'SKIP_COLD_OPEN' not in s:
        return False, "cold-open guard absent"
    gap = [ln for ln in s.splitlines() if ln.startswith("COLD_OPEN_GAP_MIN")]
    return True, (gap[0].split("#")[0].strip() if gap else "wired")


def _chk_healer() -> tuple[bool, str]:
    s = _read("setup/scripts/heal-engine.ps1")
    if not s:
        return False, "heal-engine.ps1 unreadable"
    ok = ("CimInstance" in s or "Get-Process" in s)
    return ok, "liveness check before re-fire" if ok else "no liveness check -- can double-fire"


def _chk_exit_cov() -> tuple[bool, str]:
    s = _read("setup/scripts/exit_coverage_check.py")
    ok = "QTY_MISMATCH" in s
    return ok, "qty-aware (QTY_MISMATCH)" if ok else "qty comparison absent"


def _chk_conviction_k() -> tuple[bool, str]:
    s = _read("setup/scripts/heartbeat_core.py")
    ok = "_sl.ledger_path(STATE, account)" in s
    return ok, "per-account settlement ledger" if ok else "hardcoded shared ledger (bold reads safe)"


def _chk_conviction_components() -> tuple[bool, str]:
    s = _read("setup/scripts/heartbeat_core.py")
    env = 'bc.get("session_high")' in s and '"session_high": session_hi' in s
    struct = "_sameday_structure_side(payload)" in s
    # AST, NOT SUBSTRING. The first version of this check did `'"bars_prior"' in s` and
    # reported "TRANSPOSED KEY BACK" -- against a file where the only occurrence is the COMMENT
    # explaining that the transposed key was the bug. That is trap #1 from the entry-quality
    # handoff ("a claim and its retraction look identical to grep"), hit inside the instrument
    # built to stop me hand-assembling answers. A status tool that cries wolf is worse than no
    # tool, so this reads string CONSTANTS out of the parsed module and ignores prose entirely.
    import ast
    try:
        tree = ast.parse(s)
        transposed = any(isinstance(n, ast.Constant) and n.value == "bars_prior"
                         for n in ast.walk(tree))
    except SyntaxError:
        return False, "heartbeat_core.py does not parse"
    if env and struct and not transposed:
        return True, "C4 session envelope + C5 structure threaded; no transposed key"
    bad = []
    if not env:
        bad.append("C4 envelope not wired")
    if not struct:
        bad.append("C5 still None")
    if transposed:
        bad.append("TRANSPOSED KEY BACK")
    return False, "; ".join(bad)


def _chk_sizing_disarmed() -> tuple[bool, str]:
    v = _params().get("min_contracts_equity_scaled")
    # DISARMED is the CORRECT state until a validated entry-quality gate exists. Two studies
    # (ENTRY-LOCATION-GATE, ENTRY-RANGE-CONTEXT) returned null/NOT-RUN, so the re-arm condition
    # is NOT met. This row is GREEN when disarmed, and RED if something re-armed it silently.
    return (v is False), f"min_contracts_equity_scaled={v!r} (must stay False -- re-arm needs a validated gate)"


def _chk_keepawake() -> tuple[bool, str]:
    """Script present AND registered as a task AND it has actually beaten.

    TWO BUGS IN THIS CHECK'S FIRST VERSION, both found the moment it ran:
      1. It looked for `ts_et`/`updated_et`; the daemon writes `last_assert_et`. So a healthy
         daemon reported "last beat unknown" -- a status tool guessing at its own schema.
      2. It never verified the task was REGISTERED. A keep-awake script that exists but is not
         scheduled is worth exactly nothing on Monday morning, and "the box slept" is the root
         cause of the whole incident this roster exists for.
    Registration is queried via PowerShell Get-ScheduledTask, NOT `schtasks /fo csv` -- that
    form truncates and is a documented trap in this repo (it silently hid 27 tasks in an audit).
    A stale heartbeat overnight is EXPECTED, not a fault: the daemon runs 09:10-16:10 ET and
    exits, so only the registration matters outside that window.
    """
    if not (REPO / "setup/scripts/market_hours_keepawake.py").exists():
        return False, "keep-awake script missing"
    reg = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-ScheduledTask -TaskName 'Gamma_MarketKeepAwake' -ErrorAction SilentlyContinue).State"],
        capture_output=True, text=True, timeout=45, creationflags=NO_WINDOW).stdout.strip()
    if not reg:
        return False, "script present but NOT REGISTERED as a scheduled task -- will NOT fire"
    hb = STATE / "keepawake-heartbeat.json"
    if not hb.exists():
        return False, f"registered ({reg}) but NEVER RAN (no heartbeat file)"
    try:
        rec = json.loads(hb.read_text(encoding="utf-8"))
        return True, (f"task {reg}; last session {rec.get('started_et')} -> "
                      f"{rec.get('last_assert_et')}, {rec.get('ticks')} ticks, "
                      f"{rec.get('api_failures')} API failures")
    except (OSError, ValueError):
        return True, f"task {reg}; heartbeat file unparseable"


ROSTER: list[tuple[str, str, Callable[[], tuple[bool, str]], str | None]] = [
    ("atomic-entry-claim", "double entry (two processes, 21ms apart)",
     _chk_claim, "backtest/tests/test_atomic_entry_claim_2026_08_14.py"),
    ("cold-open-guard", "blind first tick after a dark stretch",
     _chk_cold_open, "backtest/tests/test_cold_open_guard_2026_08_14.py"),
    ("healer-liveness", "healer re-fired a brain that was already alive",
     _chk_healer, None),
    ("exit-coverage-qty", "exit state disagreed with broker qty after a double fill",
     _chk_exit_cov, "backtest/tests/test_exit_coverage_2026_08_13.py"),
    ("conviction-per-account-k", "bold's conviction read safe's entry counter",
     _chk_conviction_k, None),
    ("conviction-c4-c5", "no entry-quality signal existed at all",
     _chk_conviction_components, "backtest/tests/test_conviction_c4_c5_wiring_2026_08_14.py"),
    ("sizing-disarmed", "equity-scaled floor DOUBLED a bad signal",
     _chk_sizing_disarmed, "backtest/tests/test_min_contracts_equity_scaling_2026_08_13.py"),
    ("keep-awake", "the box slept 04:27-09:46 ET",
     _chk_keepawake, None),
    ("no-console-popups", "console flash regression class",
     lambda: (True, "guard-enforced"), "backtest/tests/test_window_leak_compliance.py"),
    ("eod-flatten-checked-read", "a broker timeout could log 'already flat'",
     lambda: (("open_spy_option_positions_checked" in _read("setup/scripts/eod_flatten.py")),
              "checked read + retry, fails LOUD"), "backtest/tests/test_eod_flatten.py"),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for fid, link, check, guard in ROSTER:
        try:
            ok, detail = check()
        except Exception as e:  # noqa: BLE001 -- one bad check must not blind the rest
            ok, detail = False, f"CHECK ERRORED: {type(e).__name__}: {e}"
        g_ok, g_detail = (None, "no guard") if guard is None else _guard(guard)
        rows.append({"id": fid, "closes": link, "code_ok": ok, "code": detail,
                     "guard": guard, "guard_green": g_ok, "guard_detail": g_detail,
                     "status": ("GREEN" if ok and (g_ok is not False) else "RED")})

    red = [r for r in rows if r["status"] == "RED"]
    ungarded = [r for r in rows if r["guard"] is None]
    rep = {
        "_doc": "Live re-verification of the 2026-08-14 incident fix roster. Every row is a "
                "fresh check against disk/params/guard exit code -- never a stored claim.",
        "incident": "2026-08-14 -$1,569 (box slept -> double entry + blind first tick)",
        "n_fixes": len(rows), "n_red": len(red),
        "n_without_a_guard": len(ungarded),
        "headline": ("ALL GREEN" if not red else f"{len(red)} RED: " +
                     ", ".join(r["id"] for r in red)),
        "fixes": rows,
    }
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")

    print(f"INCIDENT FIX STATUS -- {rep['incident']}")
    print(f"  {rep['headline']}\n")
    for r in rows:
        mark = "OK  " if r["status"] == "GREEN" else "RED "
        g = {True: "guard GREEN", False: "guard RED", None: "NO GUARD"}[r["guard_green"]]
        print(f"  [{mark}] {r['id']:<26} {g:<12} {r['code']}")
        print(f"           closes: {r['closes']}")
        if r["guard_green"] is False:
            print(f"           !! {r['guard_detail']}")
    if ungarded:
        print(f"\n  {len(ungarded)} fix(es) have NO guard test -- they can regress silently: "
              + ", ".join(r["id"] for r in ungarded))
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
