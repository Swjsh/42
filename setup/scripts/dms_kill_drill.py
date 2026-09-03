"""dms_kill_drill.py -- tooling for the DEAD-MAN'S-SWITCH KILL DRILL named in the work order
(markdown/planning/OPUS-WORK-ORDER-2026-09.md section 2c) and LIVE-FLIP-RUNBOOK.md section 2
item 2: "the live-drill bar, distinct from the built bar" -- kill Gamma_HeartbeatCore mid-session
with an open PAPER position on safe-2, >=5 times across different times of day, and confirm the
dead-man's switch (setup/scripts/dead_mans_switch.py) flattens each within 12 minutes
(broker-verified, not state-file-verified).

THIS SCRIPT DOES NOT RUN THE DRILL TONIGHT. It is PREPARATION so J can run the drill as ONE
command on an afternoon he names (STATUS announces it the day before -- see --announce). Built
off-hours per this session's own tasking; --arm refuses outside RTH and without an explicit
same-day confirm token, so it cannot fire itself by accident during a build/test session.

WHY A SEPARATE SCRIPT, NOT A MANUAL PROCEDURE:
  The drill needs an ACCURATE kill (the exact heartbeat_core.py process tree, never a sibling
  interactive claude.exe or an unrelated python.exe), an ACCURATE clock (kill_ts to the second),
  and an ACCURATE observation (the DMS's own JSONL log + a broker-verified flat read, not a
  state file that could itself be stale). Doing this by hand five times risks exactly the kind
  of "it worked this time" the debugging doctrine warns against -- this script makes every kill
  identically instrumented so the 5 rows are comparable.

HOW THE KILL IS IDENTIFIED (reuses the WMI command-line probe pattern from
setup/scripts/_shared.ps1#Stop-StaleClaudeProcesses / #Stop-ProcessTree, and the identical
"CommandLine -like '*heartbeat_core*'" check heal-engine.ps1 already uses to decide whether the
brain process is alive): a Win32_Process WMI query for Name IN (python.exe, pythonw.exe) whose
CommandLine contains "heartbeat_core.py", walked to include descendants, each Stop-Process -Force.
This can ONLY match the Gamma_HeartbeatCore process tree -- it does not touch the user's
interactive claude.exe, TradingView, or any other python.exe on the box (verified narrow: no
other production script's CommandLine contains this literal substring -- grepped 2026-09-03).

WHAT THIS SCRIPT NEVER DOES: it never places, closes, replaces, or cancels a broker order. Every
broker call it makes is a READ (fleet_broker.get_account / open_spy_option_positions_checked /
is_flat_spy_options, plus a raw GET /v2/clock). The dead-man's switch (a separate, already-armed,
already-tested process) is the only thing that flattens anything in this drill -- this script only
KILLS THE ENGINE PROCESS and WATCHES. Guarded by an AST test (test_dms_kill_drill_2026_09_03.py)
that fails if any order-placing call is ever added to this module.

REFUSAL MATRIX (--arm; all must clear before a single kill happens):
  1. GAMMA_DRILL_CONFIRM env var must equal TODAY's ET date (YYYY-MM-DD) -- a stale or absent
     token refuses. This is the "announced in STATUS the day before, J names the afternoon"
     control: J (or a session acting on his stated go-ahead) sets it fresh, same day.
  2. Must be RTH on a weekday, confirmed against the broker's own /v2/clock (never a local
     guess -- L-lessons on TZ: this box runs Mountain time, ET is local+2).
  3. bold-2 must be flat UNLESS --accept-bold-flatten is passed (heartbeat_core drives both
     accounts in one process; killing it risks a bold-2 position too, and the DMS will flatten
     it exactly like safe-2's).
  4. safe-2 must have >=1 open SPY option position -- there is nothing to time-to-flat without
     one.
  5. (--plan and --announce never touch the refusal gate -- they are read-only / text-only.)

OUTPUTS:
  analysis/drills/dms-kill-drill-YYYY-MM-DD.jsonl  -- one row per kill (append-only)
  analysis/drills/dms-kill-drill-YYYY-MM-DD.md     -- same day's rows as a human table
  --report renders ALL rows found under analysis/drills/dms-kill-drill-*.jsonl against the
  >=5-kill target from the runbook, independent of which day(s) they were drilled on.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---- path setup (mirrors dead_mans_switch.py / eod_flatten.py pattern) -------------------
_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parents[1]
for _p in ("setup/scripts", "automation/state/fleet", "backtest/lib"):
    _pp = str(_REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

import fleet_broker  # noqa: E402 (from automation/state/fleet) -- READS ONLY, see docstring
from et_clock import et_now  # noqa: E402 (from setup/scripts)

import importlib.util as _ilu  # noqa: E402

# OP-27 L41: never flash a conhost window on win32
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

# Reuse dead_mans_switch's OWN liveness math (never re-derive it) so this drill measures the
# exact signal the DMS itself acts on.
_dms_spec = _ilu.spec_from_file_location("dead_mans_switch_drill", _SCRIPTS / "dead_mans_switch.py")
_dms = _ilu.module_from_spec(_dms_spec)
_dms_spec.loader.exec_module(_dms)  # type: ignore[union-attr]

# ---- config --------------------------------------------------------------------------- #
CONFIRM_ENV = "GAMMA_DRILL_CONFIRM"
TARGET_ARM = "safe-2"
OTHER_ARM = "bold-2"
HEARTBEAT_MARKER = "heartbeat_core.py"
TARGET_KILLS = 5
TARGET_TIME_TO_FLAT_S = 12 * 60  # runbook: 8-min heal window + 2-min DMS cadence + fill
MAX_OBSERVE_S = 15 * 60  # give up recording (not give up healing) at 15 min
POLL_INTERVAL_S = 5

DRILL_DIR = _REPO / "analysis" / "drills"
DMS_LOG_DIR = _REPO / "automation" / "state" / "logs"
HEARTBEAT_TASK = "Gamma_HeartbeatCore"
DMS_TASK = "Gamma_DeadMansSwitch"


# ---- small helpers ---------------------------------------------------------------------- #

def _et_ts() -> str:
    return et_now().strftime("%Y-%m-%d %H:%M:%S ET")


def _today_et_date() -> str:
    return et_now().strftime("%Y-%m-%d")


def _log_paths_for(date_str: str) -> "tuple[Path, Path]":
    return (
        DMS_LOG_DIR / f"dead-mans-switch-{date_str}.log",
        DMS_LOG_DIR / f"dead-mans-switch-{date_str}.jsonl",
    )


def _drill_paths_for(date_str: str) -> "tuple[Path, Path]":
    DRILL_DIR.mkdir(parents=True, exist_ok=True)
    return (
        DRILL_DIR / f"dms-kill-drill-{date_str}.jsonl",
        DRILL_DIR / f"dms-kill-drill-{date_str}.md",
    )


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Read-only TCP connect probe. Mirrors mcp_audit_check.py#check_port verbatim."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_broker_clock(creds: dict) -> dict:
    """Read-only GET /v2/clock via fleet_broker's internal request helper (no new HTTP
    client duplicated -- reuses the one already used by every arm's real broker calls)."""
    try:
        return fleet_broker._request(creds, "clock")  # noqa: SLF001 -- deliberate reuse, read-only endpoint
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}


# ---- state gathering (read-only) --------------------------------------------------------- #

def read_state() -> dict:
    """Everything --plan reports and --arm's refusal gate checks. Never raises -- every
    sub-read is wrapped so a broken piece degrades to an UNKNOWN field rather than crashing
    the whole report (OP-25 fail-open on observation, never on the action)."""
    et = et_now()
    state: dict = {"ts_et": _et_ts(), "weekday": et.weekday() < 5}

    try:
        creds_all = fleet_broker.load_creds()
    except Exception as exc:  # noqa: BLE001
        creds_all = {}
        state["creds_error"] = str(exc)

    for arm in (TARGET_ARM, OTHER_ARM):
        entry: dict = {}
        creds = creds_all.get(arm)
        if not creds:
            entry["error"] = "no creds for this arm"
            state[arm] = entry
            continue
        positions, read_ok = fleet_broker.open_spy_option_positions_checked(creds)
        entry["read_ok"] = read_ok
        entry["open_positions"] = positions if read_ok else None
        entry["qty_open"] = (
            sum(abs(int(float(p.get("qty", 0)))) for p in positions) if read_ok else None
        )
        state[arm] = entry

    # broker clock -- the only source of truth for "is RTH open right now" (never a local
    # weekday+hour guess -- this box runs Mountain time, per CLAUDE.md's standing TZ lesson).
    clock_creds = creds_all.get(TARGET_ARM) or next(iter(creds_all.values()), None)
    if clock_creds:
        clk = get_broker_clock(clock_creds)
        state["broker_clock"] = clk
        state["market_open"] = bool(clk.get("is_open")) if isinstance(clk, dict) else None
    else:
        state["broker_clock"] = {"_error": "no creds available to read clock"}
        state["market_open"] = None

    # engine liveness -- the exact signal the DMS itself uses (STALE_MIN threshold).
    try:
        et_naive = et.replace(tzinfo=None)
        now_utc = _dms._utc_now()  # noqa: SLF001
        state["heartbeat_liveness_min"] = {
            "safe": _dms.core_liveness_minutes("safe", et_naive),
            "bold": _dms.core_liveness_minutes("bold", et_naive),
        }
    except Exception as exc:  # noqa: BLE001
        state["heartbeat_liveness_min"] = {"error": str(exc)}

    # DMS task state -- read-only Task Scheduler query, never a start/stop action.
    state["dms_task"] = _query_task_state(DMS_TASK)
    state["heartbeat_task"] = _query_task_state(HEARTBEAT_TASK)

    # freeze / Rule-9 permission for today (informational -- doctrine.py owns the real gate;
    # this only surfaces whether the drill window makes sense to run, never bypasses it).
    state["is_rth_by_dms_clock"] = _dms.is_rth(et)

    return state


def _query_task_state(task_name: str) -> dict:
    """Read-only `Get-ScheduledTask` query. Never Start/Stop/Enable/Disable -- purely
    diagnostic. Returns {'state': ..., 'last_result': ...} or {'error': ...}."""
    try:
        ps_cmd = (
            f"$t = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction Stop; "
            f"$i = Get-ScheduledTaskInfo -TaskName '{task_name}' -ErrorAction Stop; "
            "[PSCustomObject]@{State=$t.State.ToString(); "
            "LastRunTime=$i.LastRunTime.ToString('o'); "
            "LastTaskResult=$i.LastTaskResult} | ConvertTo-Json -Compress"
        )
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=20, creationflags=_CREATE_NO_WINDOW
        )
        if out.returncode != 0:
            return {"error": (out.stderr or "non-zero exit").strip()[:300]}
        return json.loads(out.stdout.strip())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---- refusal gate (pure function -- no I/O, fully unit-testable) ------------------------- #

def preflight_check(*, confirm_env: "str | None", today_date: str, accept_bold_flatten: bool,
                     state: dict) -> "tuple[bool, list[str]]":
    """Returns (ok, reasons). ALL reasons are collected (not short-circuited) so a single
    --plan/--arm run shows every blocker at once, not one-at-a-time whack-a-mole."""
    reasons: list[str] = []

    if not confirm_env:
        reasons.append(f"{CONFIRM_ENV} is not set -- refuse (no same-day drill authorization)")
    elif confirm_env != today_date:
        reasons.append(
            f"{CONFIRM_ENV}='{confirm_env}' does not match today's ET date '{today_date}' "
            "-- a stale confirm token from a prior day cannot authorize today's drill"
        )

    if not state.get("weekday", False):
        reasons.append("today is not a weekday")

    if state.get("market_open") is not True:
        reasons.append(
            f"broker clock does not report market open (is_open={state.get('market_open')!r}) "
            "-- refuse outside RTH"
        )

    bold = state.get(OTHER_ARM, {})
    bold_qty = bold.get("qty_open")
    if bold.get("read_ok") is not True:
        reasons.append(f"{OTHER_ARM} position read failed -- cannot confirm it is flat")
    elif bold_qty and bold_qty > 0 and not accept_bold_flatten:
        reasons.append(
            f"{OTHER_ARM} has {bold_qty} open contracts and --accept-bold-flatten was not "
            "passed -- killing heartbeat_core would risk a DMS flatten on bold-2 too"
        )

    safe = state.get(TARGET_ARM, {})
    safe_qty = safe.get("qty_open")
    if safe.get("read_ok") is not True:
        reasons.append(f"{TARGET_ARM} position read failed -- cannot confirm an open position exists")
    elif not safe_qty:
        reasons.append(f"{TARGET_ARM} has no open position -- nothing to time-to-flat")

    return (len(reasons) == 0, reasons)


# ---- the kill itself ---------------------------------------------------------------------- #

def find_heartbeat_core_pids() -> list[int]:
    """Read-only WMI query returning every python.exe/pythonw.exe PID whose CommandLine
    contains the heartbeat_core.py marker, PLUS all descendants (mirrors
    _shared.ps1#Stop-ProcessTree's recursive descent -- an MCP or subprocess child of the
    engine must die too, or the drill would leave a dangling process the kill didn't cover)."""
    ps_cmd = (
        "$root = Get-CimInstance Win32_Process -Filter \"(Name='python.exe' OR "
        f"Name='pythonw.exe') AND CommandLine LIKE '%{HEARTBEAT_MARKER}%'\" "
        "-ErrorAction SilentlyContinue; "
        "$all = @(); "
        "function Get-Desc($pid_) { "
        "  $c = @(Get-CimInstance Win32_Process -Filter \"ParentProcessId=$pid_\" -ErrorAction SilentlyContinue); "
        "  $out = @(); foreach ($k in $c) { $out += [int]$k.ProcessId; $out += Get-Desc([int]$k.ProcessId) }; "
        "  return ,$out "
        "}; "
        "foreach ($r in $root) { $all += [int]$r.ProcessId; $all += Get-Desc([int]$r.ProcessId) }; "
        "$all | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=20, creationflags=_CREATE_NO_WINDOW
        )
        if out.returncode != 0 or not out.stdout.strip():
            return []
        parsed = json.loads(out.stdout.strip())
        if isinstance(parsed, int):
            return [parsed]
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
        return []
    except Exception:  # noqa: BLE001
        return []


def kill_heartbeat_core_tree() -> dict:
    """THE ONE MUTATING ACTION IN THIS MODULE -- everything else is a read. Kills the
    heartbeat_core.py process tree via Stop-Process -Force (never touches an order, a broker
    call, or any other process). Returns {'killed_pids': [...], 'found': bool}."""
    pids = find_heartbeat_core_pids()
    if not pids:
        return {"killed_pids": [], "found": False}
    killed = []
    for pid in pids:
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                capture_output=True, text=True, timeout=10, creationflags=_CREATE_NO_WINDOW
            )
            killed.append(pid)
        except Exception:  # noqa: BLE001
            pass
    return {"killed_pids": killed, "found": True}


# ---- observation (read-only) -------------------------------------------------------------- #

def _tail_new_dms_rows(jsonl_path: Path, since_byte: int) -> "tuple[list[dict], int]":
    """Returns (new rows appended since `since_byte`, new file size). Never raises."""
    try:
        if not jsonl_path.exists():
            return ([], since_byte)
        size = jsonl_path.stat().st_size
        if size <= since_byte:
            return ([], size)
        with jsonl_path.open("rb") as f:
            f.seek(since_byte)
            data = f.read().decode("utf-8", errors="replace")
        rows = []
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        return (rows, size)
    except Exception:  # noqa: BLE001
        return ([], since_byte)


def compute_time_to_flat_s(kill_ts: float, flat_ts: "float | None") -> "float | None":
    if flat_ts is None:
        return None
    return max(0.0, flat_ts - kill_ts)


def classify_outcome(time_to_flat_s: "float | None", target_s: int = TARGET_TIME_TO_FLAT_S) -> str:
    if time_to_flat_s is None:
        return "FAIL"
    return "PASS" if time_to_flat_s <= target_s else "FAIL"


def observe_one_kill(*, creds: dict, kill_ts: float, position_before: list,
                      poll_interval_s: int = POLL_INTERVAL_S,
                      max_observe_s: int = MAX_OBSERVE_S,
                      sleep_fn=time.sleep, time_fn=time.time,
                      broker=fleet_broker) -> dict:
    """Read-only observation loop starting right after a kill. Polls the broker (flat check)
    and the DMS's own JSONL log (first FLATTENED/DRY_RUN_WOULD_FLATTEN row for safe-2) until
    the position is confirmed flat or max_observe_s elapses. Returns the per-kill record."""
    date_str = et_now().strftime("%Y-%m-%d")
    _, dms_jsonl = _log_paths_for(date_str)
    since_byte = dms_jsonl.stat().st_size if dms_jsonl.exists() else 0

    first_dms_action_ts = None
    first_dms_action = None
    flat_ts = None
    dms_rows_seen: list[dict] = []

    deadline = time_fn() + max_observe_s
    while time_fn() < deadline:
        rows, since_byte = _tail_new_dms_rows(dms_jsonl, since_byte)
        for row in rows:
            if row.get("arm") == TARGET_ARM:
                dms_rows_seen.append(row)
                if first_dms_action_ts is None and row.get("action") not in (
                    "LIVE_NO_ACTION", None,
                ):
                    first_dms_action_ts = time_fn()
                    first_dms_action = row.get("action")

        positions, read_ok = broker.open_spy_option_positions_checked(creds)
        if read_ok:
            qty = sum(abs(int(float(p.get("qty", 0)))) for p in positions)
            if qty == 0:
                flat_ts = time_fn()
                break

        sleep_fn(poll_interval_s)

    time_to_flat_s = compute_time_to_flat_s(kill_ts, flat_ts)
    return {
        "kill_ts_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "position_before": position_before,
        "first_dms_action": first_dms_action,
        "first_dms_action_ts_offset_s": (
            None if first_dms_action_ts is None else round(first_dms_action_ts - kill_ts, 1)
        ),
        "flat_ts_offset_s": None if flat_ts is None else round(flat_ts - kill_ts, 1),
        "time_to_flat_s": None if time_to_flat_s is None else round(time_to_flat_s, 1),
        "outcome": classify_outcome(time_to_flat_s),
        "target_s": TARGET_TIME_TO_FLAT_S,
        "dms_rows_observed": dms_rows_seen,
        "observed_up_to_s": min(max_observe_s, round(time_fn() - (deadline - max_observe_s), 1)),
    }


# ---- the drill loop ------------------------------------------------------------------------ #

def run_arm(*, kills: int, min_gap_min: float, accept_bold_flatten: bool,
            sleep_fn=time.sleep, time_fn=time.time,
            kill_fn=kill_heartbeat_core_tree, broker=fleet_broker) -> dict:
    """Runs `kills` kill/observe cycles, gated by preflight_check() EVERY time (state can
    change between kills -- e.g. bold-2 could pick up a position mid-drill)."""
    today_date = _today_et_date()
    confirm = os.environ.get(CONFIRM_ENV)
    rows = []
    for i in range(kills):
        state = read_state()
        ok, reasons = preflight_check(
            confirm_env=confirm, today_date=today_date,
            accept_bold_flatten=accept_bold_flatten, state=state,
        )
        if not ok:
            return {"aborted_at_kill": i + 1, "reasons": reasons, "rows": rows}

        creds_all = broker.load_creds()
        creds = creds_all[TARGET_ARM]
        position_before = state[TARGET_ARM]["open_positions"]
        kill_ts = time_fn()
        kill_res = kill_fn()
        row = observe_one_kill(
            creds=creds, kill_ts=kill_ts, position_before=position_before,
            sleep_fn=sleep_fn, time_fn=time_fn, broker=broker,
        )
        row["kill_result"] = kill_res
        row["kill_index"] = i + 1
        rows.append(row)
        _append_drill_row(today_date, row)

        if i < kills - 1:
            sleep_fn(min_gap_min * 60)

    return {"aborted_at_kill": None, "reasons": [], "rows": rows}


def _append_drill_row(date_str: str, row: dict) -> None:
    jsonl_path, md_path = _drill_paths_for(date_str)
    try:
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass
    _rewrite_md_summary(date_str)


def _rewrite_md_summary(date_str: str) -> None:
    jsonl_path, md_path = _drill_paths_for(date_str)
    rows = []
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    lines = [
        f"# DMS kill drill -- {date_str}", "",
        f"Target: {TARGET_ARM} | time-to-flat bar: {TARGET_TIME_TO_FLAT_S}s "
        f"({TARGET_TIME_TO_FLAT_S // 60} min)", "",
        "| kill # | kill_ts (ET) | first DMS action | +offset (s) | flat +offset (s) | "
        "time-to-flat (s) | outcome |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('kill_index', '?')} | {r.get('kill_ts_et', '?')} | "
            f"{r.get('first_dms_action', '-')} | {r.get('first_dms_action_ts_offset_s', '-')} | "
            f"{r.get('flat_ts_offset_s', '-')} | {r.get('time_to_flat_s', '-')} | "
            f"{r.get('outcome', '-')} |"
        )
    passed = sum(1 for r in rows if r.get("outcome") == "PASS")
    lines += ["", f"**{passed}/{len(rows)} PASS** against a >={TARGET_KILLS}-kill target."]
    try:
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ---- CLI surfaces --------------------------------------------------------------------------- #

def cmd_plan() -> int:
    state = read_state()
    today_date = _today_et_date()
    confirm = os.environ.get(CONFIRM_ENV)
    ok, reasons = preflight_check(
        confirm_env=confirm, today_date=today_date, accept_bold_flatten=False, state=state,
    )
    print("=" * 78)
    print("DMS KILL DRILL -- PLAN (read-only, no process will be touched)")
    print("=" * 78)
    print(f"Target arm         : {TARGET_ARM}  (kills Gamma_HeartbeatCore's process tree)")
    print(f"Time-to-flat target: <= {TARGET_TIME_TO_FLAT_S}s ({TARGET_TIME_TO_FLAT_S // 60} min "
          "= 8-min heal window + 2-min DMS cadence + fill)")
    print(f"Kill count target  : >= {TARGET_KILLS}, across different times of day")
    print(f"Confirm token      : ${CONFIRM_ENV}='{confirm}'  (today={today_date})")
    print()
    print("CURRENT STATE (fresh, as of this call):")
    print(f"  {TARGET_ARM}: read_ok={state[TARGET_ARM].get('read_ok')} "
          f"qty_open={state[TARGET_ARM].get('qty_open')}")
    print(f"  {OTHER_ARM}: read_ok={state[OTHER_ARM].get('read_ok')} "
          f"qty_open={state[OTHER_ARM].get('qty_open')}")
    print(f"  market_open (broker /v2/clock): {state.get('market_open')}")
    print(f"  heartbeat liveness (min): {state.get('heartbeat_liveness_min')}")
    print(f"  {HEARTBEAT_TASK} task state: {state.get('heartbeat_task')}")
    print(f"  {DMS_TASK} task state: {state.get('dms_task')}")
    print()
    if ok:
        print("PERMITS A DRILL RIGHT NOW: yes -- --arm would proceed if invoked this instant.")
    else:
        print("PERMITS A DRILL RIGHT NOW: no. Blockers:")
        for r in reasons:
            print(f"  - {r}")
    print()
    print("To run: set the confirm token then arm --")
    print(f'  $env:{CONFIRM_ENV} = "{today_date}"')
    print(f"  .venv...python.exe setup\\scripts\\dms_kill_drill.py --arm --kills 5 --min-gap-min 20")
    return 0


def cmd_announce() -> int:
    today_date = _today_et_date()
    text = (
        f"## DMS kill drill -- scheduled for tomorrow ({today_date} +1 trading day)\n"
        f"- **What:** J-scheduled kill of `Gamma_HeartbeatCore` mid-session, {TARGET_KILLS}x "
        f"across different times of day, on **{TARGET_ARM}** (retiring arm, never the "
        f"prod-shadow candidate).\n"
        f"- **Why:** LIVE-FLIP-RUNBOOK.md section 2 item 2 -- the dead-man's switch is "
        f"built+unit-tested but not field-drilled; this closes that gap.\n"
        f"- **Safety:** paper only. Refuses without a same-day `{CONFIRM_ENV}` token, outside "
        f"RTH, with bold-2 not flat (unless accepted), or with safe-2 flat.\n"
        f"- **Target:** each kill flattened within {TARGET_TIME_TO_FLAT_S // 60} min "
        f"(broker-verified).\n"
        f"- **Command:** `$env:{CONFIRM_ENV} = \"<the day's ET date>\"; "
        f".venv...python.exe setup\\scripts\\dms_kill_drill.py --arm --kills 5 --min-gap-min 20`\n"
        f"- **Log:** `analysis/drills/dms-kill-drill-<date>.jsonl` + `.md`.\n"
    )
    print(text)
    print("(This text is printed only. Paste it into STATUS.md yourself -- this script never "
          "writes STATUS.md.)")
    return 0


def cmd_arm(kills: int, min_gap_min: float, accept_bold_flatten: bool) -> int:
    result = run_arm(kills=kills, min_gap_min=min_gap_min, accept_bold_flatten=accept_bold_flatten)
    if result["aborted_at_kill"] is not None:
        print(f"REFUSED before kill #{result['aborted_at_kill']}:")
        for r in result["reasons"]:
            print(f"  - {r}")
        return 2
    for row in result["rows"]:
        print(json.dumps(row, indent=2))
    passed = sum(1 for r in result["rows"] if r.get("outcome") == "PASS")
    print(f"\n{passed}/{len(result['rows'])} PASS this run.")
    return 0


def cmd_report() -> int:
    rows = []
    if DRILL_DIR.exists():
        for p in sorted(DRILL_DIR.glob("dms-kill-drill-*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    passed = [r for r in rows if r.get("outcome") == "PASS"]
    print(f"DMS kill drill report -- {len(rows)} kill(s) recorded across all drill days.")
    print(f"Target: >= {TARGET_KILLS} kills, each <= {TARGET_TIME_TO_FLAT_S}s time-to-flat.")
    print(f"PASS: {len(passed)}/{len(rows)}")
    for r in rows:
        print(f"  kill#{r.get('kill_index')} {r.get('kill_ts_et')} "
              f"time_to_flat_s={r.get('time_to_flat_s')} outcome={r.get('outcome')}")
    if len(passed) >= TARGET_KILLS:
        print(f"\nDRILL COMPLETE: {len(passed)} >= {TARGET_KILLS} PASS kills. Runbook §2 box "
              "can be checked.")
    else:
        print(f"\nDRILL INCOMPLETE: {len(passed)}/{TARGET_KILLS} PASS kills so far.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--announce", action="store_true")
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--kills", type=int, default=5)
    ap.add_argument("--min-gap-min", type=float, default=20.0)
    ap.add_argument("--accept-bold-flatten", action="store_true")
    args = ap.parse_args()

    if args.arm:
        return cmd_arm(args.kills, args.min_gap_min, args.accept_bold_flatten)
    if args.report:
        return cmd_report()
    if args.announce:
        return cmd_announce()
    return cmd_plan()  # default


if __name__ == "__main__":
    raise SystemExit(main())
