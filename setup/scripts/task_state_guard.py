"""task_state_guard.py -- closes self-healing blind spot (a) from the 2026-08-08 Lane B
audit: NOTHING verified a scheduled task's Enabled state. If a trading-critical task
(Gamma_HeartbeatCore, Gamma_SightBeacon, ...) were ever flipped Disabled, heal-engine.ps1's
Start-ScheduledTask recovery throws and is swallowed by its own try/catch; the one script
that DOES list task state, task_health_et.ps1, explicitly filters
`Where-Object { $_.State -ne 'Disabled' }` -- i.e. it excludes the exact failure mode this
guard exists to catch. Verified live this session (schtasks/Get-ScheduledTask, 2026-08-08):
Gamma_DashboardKeepalive is MISSING from the live scheduler right now, a real positive for
this guard's (b) branch, not a hypothetical.

WHAT THIS DOES (pure Python, deterministic, $0 -- shells out to schtasks/PowerShell only for
the actual query/enable, never an LLM):
  1. Queries the live state (Ready/Disabled/Running/MISSING + LastTaskResult) of a pinned
     list of TRADING-CRITICAL + AUTONOMY-CRITICAL tasks (see CRITICAL_TASKS below).
  2. DISABLED  -> re-enables it (Enable-ScheduledTask) and logs loudly. Skipped under
     --dry-run (reports what WOULD happen, changes nothing).
  3. MISSING   -> logs CRITICAL. Never silently passes -- there is nothing to "enable" for a
     task that doesn't exist; a human/conductor has to re-register it.
  4. LastTaskResult != 0 -> recorded (not acted on -- self_check.py's MASKED EXIT checks and
     the EOD-flatten reality check already own "is the real outcome bad"; LastTaskResult
     itself is frequently masked-to-0 by the hidden-spawn wscript hop per C8/C34, so this
     guard treats it as a WARNING-tier data point, never a verdict driver on its own).
  5. Writes automation/state/task-state-guard.json every fire (always, for the pulse/status
     surface to read).
  6. Appends ONE automation/state/discord-outbox.jsonl row ONLY when something was actually
     broken or repaired this fire, AND the problem signature changed since the last fire
     (mirrors self_check.py's own _alert() dedup idiom) -- never spams on a clean pass or an
     unchanged problem set.

PINNED LIST -- justification per task (cross-checked against automation/state/
SCHEDULED-TASKS.md + preopen_readiness.py's own LIVE_CHAIN, both live-verified 2026-08-08):
  TRADING-CRITICAL (directly gates the live 0DTE path):
    Gamma_HeartbeatCore       -- THE live trading engine, both accounts, deterministic, 1min RTH.
    Gamma_SightBeacon         -- the never-blind price/ribbon eye every other read falls back to.
    Gamma_EodFlatten          -- force-close Safe 0DTE (LLM defense-in-depth layer).
    Gamma_EodFlatten_Aggressive -- force-close Bold 0DTE (LLM defense-in-depth layer).
    Gamma_EodFlattenCore      -- the PRIMARY deterministic no-LLM EOD-flatten backstop for
                                  BOTH accounts (preopen_readiness.py already flags this
                                  critical=True in its own LIVE_CHAIN; not in the audit's
                                  literal 10-name list but the single most load-bearing
                                  omission if left out -- added here with this note so the
                                  addition is auditable, not silent).
    Gamma_Premarket           -- daily bias/levels/journal-seed/rule-pin check (pre-trade gate).
    Gamma_LaunchTV            -- launches TradingView+CDP, the chart data source; "no TV = no
                                  trades".
    Gamma_TvWatchdog          -- 5-min relaunch-on-death fix for the same TV/CDP dependency.
  AUTONOMY-CRITICAL (per this session's audit: the only unattended rig-change path + its
  wake mechanism + J's visibility surface, OP-33 "visibility is the product"):
    Gamma_Conductor           -- the ONLY scheduled loop that can actually change the rig
                                  unattended (claude --print, 3 fires/day).
    Gamma_ConductorWake       -- wake-on-event for the whole conductor family; without it,
                                  event-driven conductor wakeups go dark between the 3 fires.
    Gamma_DashboardKeepalive  -- keeps J's dashboard (:3000) alive; confirmed MISSING live
                                  this session (see module docstring above).

Fail-open, always: every external call (query, enable, file write, outbox append) is wrapped
so this script can NEVER raise into the scheduler and NEVER lock J out of anything -- worst
case on total failure is a QUERY_FAILED status written to disk and exit 0, never a crash.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001 -- fail-open on the clock import too (self_check.py's own pattern)
    def et_now():
        return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

OUT_PATH = STATE / "task-state-guard.json"
DISCORD_OUTBOX = STATE / "discord-outbox.jsonl"
LAST_PATH = STATE / "task-state-guard-last.json"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash (OP-27 L41)

READY_STATES = ("Ready", "Running")

# name -> (tier, role) -- see module docstring for the full justification of each entry.
CRITICAL_TASKS: list[dict] = [
    {"name": "Gamma_HeartbeatCore", "tier": "trading", "role": "THE live trading engine (both accounts, 1min RTH)"},
    {"name": "Gamma_SightBeacon", "tier": "trading", "role": "never-blind price/ribbon eye (1min RTH)"},
    {"name": "Gamma_EodFlatten", "tier": "trading", "role": "EOD flatten Safe (LLM defense-in-depth)"},
    {"name": "Gamma_EodFlatten_Aggressive", "tier": "trading", "role": "EOD flatten Bold (LLM defense-in-depth)"},
    {"name": "Gamma_EodFlattenCore", "tier": "trading", "role": "EOD flatten PRIMARY backstop (deterministic, no LLM, both accounts)"},
    {"name": "Gamma_Premarket", "tier": "trading", "role": "daily bias/levels/journal-seed/rule-pin check"},
    {"name": "Gamma_LaunchTV", "tier": "trading", "role": "launches TradingView+CDP (chart data source)"},
    {"name": "Gamma_TvWatchdog", "tier": "trading", "role": "'no TV = no trades' 5-min relaunch-on-death fix"},
    {"name": "Gamma_Conductor", "tier": "autonomy", "role": "the ONLY scheduled loop that can change the rig unattended"},
    {"name": "Gamma_ConductorWake", "tier": "autonomy", "role": "wake-on-event for the whole conductor family"},
    {"name": "Gamma_DashboardKeepalive", "tier": "autonomy", "role": "keeps J's visibility dashboard (:3000) alive"},
]
CRITICAL_NAMES = [t["name"] for t in CRITICAL_TASKS]


# --------------------------------------------------------------------------------------
# Impure I/O boundary -- the ONLY functions that touch subprocess/schtasks. Both take an
# explicit `names` list and are the two things a test mocks (per the task's own directive:
# "mock the query/enable layer").
# --------------------------------------------------------------------------------------

def query_task_states(names: list[str]) -> Optional[dict[str, dict]]:
    """Query live state for every name in ONE PowerShell round-trip. Returns
    {name: {"found": bool, "state": str, "last_result": Optional[int]}} for every name in
    `names` (always -- a name with no Get-ScheduledTask hit gets found=False/state=MISSING,
    never just absent from the dict, so callers can't misread "no data" as "no problem").

    Returns None (not {}) on a TOTAL query failure (powershell unavailable, timeout, etc.)
    so the caller can distinguish "the query itself broke" from "every task is missing" --
    conflating those would either mass-flag CRITICAL on a transient PS hiccup or silently
    skip real missing-task detection. Fail-open: never raises.
    """
    if not names:
        return {}
    ps_names = ",".join("'" + n.replace("'", "''") + "'" for n in names)
    script = (
        "$ns=@(" + ps_names + ");"
        "foreach($n in $ns){"
        " $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"
        " if ($t) {"
        "   $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue;"
        "   $lr = if ($i) { $i.LastTaskResult } else { 'NA' };"
        "   Write-Output ($n + '|FOUND|' + $t.State + '|' + $lr)"
        " } else {"
        "   Write-Output ($n + '|MISSING|NA|NA')"
        " }"
        "}"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001 -- total query failure, fail-open
        return None

    states: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 4:
            continue
        name, found_flag, state, last_result_raw = parts
        last_result: Optional[int] = None
        if last_result_raw not in ("NA", ""):
            try:
                last_result = int(last_result_raw)
            except (TypeError, ValueError):
                last_result = None
        states[name] = {
            "found": found_flag == "FOUND",
            "state": state if found_flag == "FOUND" else "MISSING",
            "last_result": last_result,
        }
    # Any pinned name PowerShell never echoed back (parse issue, truncated output) still
    # gets an explicit entry -- never silently absent.
    for n in names:
        states.setdefault(n, {"found": False, "state": "MISSING", "last_result": None})
    return states


def enable_tasks(names: list[str]) -> dict[str, bool]:
    """Re-enable each name via Enable-ScheduledTask, ONE PowerShell round-trip. Returns
    {name: bool} -- True only if the cmdlet reported no error for that name. Fail-open:
    total subprocess failure returns {name: False for name in names}, never raises."""
    if not names:
        return {}
    ps_names = ",".join("'" + n.replace("'", "''") + "'" for n in names)
    script = (
        "$ns=@(" + ps_names + ");"
        "foreach($n in $ns){"
        " try { Enable-ScheduledTask -TaskName $n -ErrorAction Stop | Out-Null;"
        "   Write-Output ($n + '|OK') }"
        " catch { Write-Output ($n + '|FAIL') }"
        "}"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:  # noqa: BLE001 -- fail-open
        return {n: False for n in names}

    results: dict[str, bool] = {}
    for line in proc.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 2:
            continue
        results[parts[0]] = parts[1] == "OK"
    for n in names:
        results.setdefault(n, False)
    return results


# --------------------------------------------------------------------------------------
# PURE classification -- given already-fetched states (+ already-attempted repairs, if
# any), decide per-task severity/action. No I/O, fully unit-testable.
# --------------------------------------------------------------------------------------

def classify_tasks(pinned: list[dict], states: dict[str, dict],
                    repair_results: Optional[dict[str, bool]] = None,
                    dry_run: bool = False) -> list[dict]:
    """PURE. `repair_results` is the output of enable_tasks() for whichever DISABLED names
    were attempted (empty/None if nothing needed repair, or if dry_run)."""
    repair_results = repair_results or {}
    rows: list[dict] = []
    for spec in pinned:
        name, tier, role = spec["name"], spec["tier"], spec["role"]
        info = states.get(name, {"found": False, "state": "MISSING", "last_result": None})
        row = {
            "name": name, "tier": tier, "role": role,
            "found": info["found"], "state": info["state"],
            "last_result": info["last_result"],
            "action": "none", "severity": "ok", "note": "",
        }
        if not info["found"]:
            row["severity"] = "critical"
            row["note"] = "MISSING from the live scheduler -- nothing to re-enable; needs re-registration"
        elif info["state"] == "Disabled":
            if dry_run:
                row["action"] = "would-re-enable(dry-run)"
                row["severity"] = "critical"
                row["note"] = "DISABLED -- dry-run, no change made"
            elif repair_results.get(name):
                row["action"] = "re-enabled"
                row["severity"] = "warning"
                row["note"] = "was DISABLED, re-enabled this fire"
            else:
                row["action"] = "re-enable-failed"
                row["severity"] = "critical"
                row["note"] = "was DISABLED, Enable-ScheduledTask FAILED -- still disabled"
        elif info["state"] not in READY_STATES:
            # Anything other than Ready/Running/Disabled (e.g. Queued) -- record, don't act.
            row["severity"] = "warning"
            row["note"] = f"unexpected state '{info['state']}'"

        if info["last_result"] not in (None, 0) and row["severity"] == "ok":
            row["severity"] = "warning"
        if info["last_result"] not in (None, 0):
            suffix = f"LastTaskResult={info['last_result']}"
            row["note"] = (row["note"] + "; " + suffix) if row["note"] else suffix

        rows.append(row)
    return rows


def _verdict(rows: list[dict]) -> str:
    if any(r["severity"] == "critical" for r in rows):
        return "RED"
    if any(r["severity"] == "warning" for r in rows):
        return "YELLOW"
    return "GREEN"


def _problems(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if r["severity"] == "ok":
            continue
        out.append(f"TASK-STATE[{r['tier']}] {r['name']}: {r['note']} (action={r['action']})")
    return out


# --------------------------------------------------------------------------------------
# Orchestration -- injectable query_fn/enable_fn for tests; real callers get the real
# subprocess-backed functions by default.
# --------------------------------------------------------------------------------------

def run(dry_run: bool = False,
        query_fn: Optional[Callable[[list[str]], Optional[dict[str, dict]]]] = None,
        enable_fn: Optional[Callable[[list[str]], dict[str, bool]]] = None,
        now: Optional[dt.datetime] = None,
        out_path: Path = OUT_PATH,
        outbox_path: Path = DISCORD_OUTBOX,
        last_path: Path = LAST_PATH,
        pinned: Optional[list[dict]] = None) -> dict:
    """Fail-open orchestrator. NEVER raises -- any unexpected exception is caught at the
    very top and turned into a QUERY_FAILED result so this guard can never become the next
    masked-exit entry in the very log it exists to help surface.

    query_fn/enable_fn default to None and resolve to the module-level
    query_task_states/enable_tasks INSIDE the function body (not as bound default-argument
    values) so a test's `monkeypatch.setattr(module, "query_task_states", ...)` is actually
    honored by main()'s no-args call path -- a bound default would freeze the reference at
    function-definition time and silently ignore the monkeypatch."""
    query_fn = query_fn or query_task_states
    enable_fn = enable_fn or enable_tasks
    now = now or et_now()
    pinned = pinned if pinned is not None else CRITICAL_TASKS
    names = [t["name"] for t in pinned]

    try:
        states = query_fn(names)
        if states is None:
            result = {
                "ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "dry_run": dry_run,
                "verdict": "QUERY_FAILED", "tasks": [], "problems": [],
                "note": "task query itself failed (powershell unavailable/timeout) -- fail-open, no action taken",
            }
            _write(result, out_path)
            return result

        disabled_names = [n for n in names if states.get(n, {}).get("state") == "Disabled"]
        # `states` stays exactly as first queried (pre-repair) so classify_tasks can still
        # see "this one WAS Disabled" -- overwriting it with the post-repair re-query here
        # would erase that signal and make a successful repair misclassify as a no-op
        # (caught live in this session's own self-test: action stayed "none" instead of
        # "re-enabled" until this was fixed). `post_repair_state` carries the verified
        # NOW-current state separately, applied to the displayed row after classification.
        repair_results: dict[str, bool] = {}
        post_repair_state: dict[str, str] = {}
        if disabled_names and not dry_run:
            try:
                enable_fn(disabled_names)
            except Exception:  # noqa: BLE001 -- a broken repair layer must not break detection
                pass
            # Re-query once to verify the ACTUAL post-repair state (never trust the
            # enable call's own claimed success without checking).
            try:
                verify = query_fn(disabled_names) or {}
            except Exception:  # noqa: BLE001
                verify = {}
            for n in disabled_names:
                v = verify.get(n)
                now_state = v.get("state") if v else None
                post_repair_state[n] = now_state or "Disabled"
                repair_results[n] = bool(now_state and now_state != "Disabled" and now_state != "MISSING")

        rows = classify_tasks(pinned, states, repair_results, dry_run=dry_run)
        for row in rows:
            if row["name"] in post_repair_state:
                row["state"] = post_repair_state[row["name"]]
        verdict = _verdict(rows)
        problems = _problems(rows)
        repairs = [r["name"] for r in rows if r["action"] == "re-enabled"]

        result = {
            "ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "dry_run": dry_run,
            "verdict": verdict, "tasks": rows, "problems": problems, "repairs": repairs,
        }
        _write(result, out_path)
        if problems or repairs:
            _maybe_alert(result, outbox_path, last_path)
        return result
    except Exception as e:  # noqa: BLE001 -- outermost fail-open net, see docstring
        result = {
            "ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "dry_run": dry_run,
            "verdict": "GUARD_ERROR", "tasks": [], "problems": [],
            "note": f"{type(e).__name__}: {e}",
        }
        try:
            _write(result, out_path)
        except Exception:  # noqa: BLE001
            pass
        return result


def _write(result: dict, out_path: Path) -> None:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass


def _maybe_alert(result: dict, outbox_path: Path, last_path: Path) -> None:
    """Discord row ONLY when something is actually broken or was repaired THIS fire, AND
    the problem signature changed since the last fire (mirrors self_check.py's own
    _alert() dedup idiom) -- never spams an unchanged, already-known problem every 30 min."""
    sig = " | ".join(result["problems"])
    prev = ""
    if last_path.exists():
        try:
            prev = (json.loads(last_path.read_text(encoding="utf-8")) or {}).get("_alerted_sig", "")
        except Exception:  # noqa: BLE001
            pass
    if sig != prev:
        try:
            outbox_path.parent.mkdir(parents=True, exist_ok=True)
            with outbox_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": result["ts_et"], "channel": "gamma-ops", "source": "task_state_guard",
                    "message": f"TASK-STATE-GUARD {result['verdict']}: " + "; ".join(result["problems"])[:500],
                }) + "\n")
        except OSError:
            pass
    try:
        result = dict(result)
        result["_alerted_sig"] = sig
        last_path.parent.mkdir(parents=True, exist_ok=True)
        last_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Task-state guard -- detect+repair disabled/missing critical scheduled tasks")
    parser.add_argument("--dry-run", action="store_true", help="detect and report only, never call Enable-ScheduledTask")
    args = parser.parse_args(argv)

    r = run(dry_run=args.dry_run)
    print(f"[task-state-guard] {r['verdict']}" + (" (dry-run)" if args.dry_run else ""))
    for p in r.get("problems", []):
        print(f"  - {p}")
    if r.get("repairs"):
        print(f"  repaired: {', '.join(r['repairs'])}")
    if r["verdict"] == "GREEN":
        print("  (all pinned tasks Ready/Running -- nothing to surface)")
    return 0  # always fail-open -- this script must never itself become a masked exit


if __name__ == "__main__":
    raise SystemExit(main())
