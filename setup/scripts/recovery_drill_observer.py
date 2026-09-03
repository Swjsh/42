"""recovery_drill_observer.py -- tooling for the RECOVERY DRILL named in the work order
(markdown/planning/OPUS-WORK-ORDER-2026-09.md section 2c): "TV CDP dead + Alpaca REST 5xx +
Windows restart mid-session, each once, read-only observation of what the healers and DMS do.
Done: a table of failure -> first automated action -> time."

THIS SCRIPT NEVER INDUCES A FAILURE. It is a pure OBSERVER -- every read it makes is read-only
(a TCP connect probe, a broker GET, a log tail, a JSON state read, a Task Scheduler query). J
(or a documented manual step) causes the failure; this script watches what the existing
automated healers (heal-engine.ps1, run-tv-watchdog.ps1, dead_mans_switch.py, engine_health.py,
Task Scheduler's own StartWhenAvailable recovery) do about it, and times the first automated
reaction.

HOW EACH FAILURE IS INDUCED SAFELY ON PAPER (J's step, not this script's):
  * tv_cdp_dead   -- kill the TradingView process (Task Manager, or
                     `taskkill /F /IM TradingView.exe`). Check afterward:
                     Gamma_TvWatchdog (every 5 min, 08:05-16:00 ET) should relaunch it via
                     Invoke-TvLaunchSafe; automation/state/logs/tv-watchdog-<date>.log gets a
                     RELAUNCH_* line. The engine itself should NOT stop trading (it reads price
                     via sight_beacon's own REST/yfinance fallback, not the TV chart) -- that is
                     part of what this drill is meant to prove, not assume.
  * alpaca_5xx    -- block the broker host via a hosts-file entry J adds (as Administrator,
                     `C:\\Windows\\System32\\drivers\\etc\\hosts`): a line routing
                     `paper-api.alpaca.markets` to `127.0.0.1` (or another dead IP), then J
                     REMOVES the line to end the drill. This script never edits that file --
                     hosts-file changes require elevation this session does not have and must
                     never silently acquire. Check afterward: dead_mans_switch.py's own
                     fail-CLOSED branch should log READ_FAILED (refuses to flatten on an
                     unverified broker read -- see its own docstring point 5); engine_health.py
                     should show a RED broker-connectivity check.
  * windows_restart -- J runs `shutdown /r /t 0` (or Start > Restart) mid-session on a day with
                     an open paper position. Check afterward: Task Scheduler's own
                     StartWhenAvailable behavior should re-fire Gamma_HeartbeatCore /
                     Gamma_SightBeacon / Gamma_DeadMansSwitch after boot without any of this
                     project's code involved; core-decisions.jsonl should show a resumed ticking
                     cadence; if a position was open at the moment of restart, dead_mans_switch's
                     STALE_MIN=10 gate is what actually protects it during the boot gap.

WHAT THIS SCRIPT NEVER DOES: it never places, closes, replaces, or cancels a broker order, never
edits the hosts file, never kills or restarts a process, and never touches Task Scheduler beyond
a read-only `Get-ScheduledTask`/`Get-ScheduledTaskInfo` query. Guarded by an AST test
(test_recovery_drill_observer_2026_09_03.py) that fails if any mutating call is ever added.

USAGE:
  --watch --scenario {tv_cdp_dead,alpaca_5xx,windows_restart} --minutes M
      Samples every 10s (read-only) until M minutes elapse. Writes
      analysis/drills/recovery-drill-<scenario>-YYYY-MM-DD.jsonl (one row per sample) and
      analysis/drills/recovery-drill-<scenario>-YYYY-MM-DD.md (that scenario's own recap).
  --report
      Reads the most recent run of each of the 3 scenarios under analysis/drills/ and renders
      ONE combined failure -> first automated action -> time table to
      analysis/drills/recovery-drill-summary.md (and stdout).
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---- path setup (mirrors dead_mans_switch.py / dms_kill_drill.py pattern) ----------------
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

_dms_spec = _ilu.spec_from_file_location("dead_mans_switch_recovery", _SCRIPTS / "dead_mans_switch.py")
_dms = _ilu.module_from_spec(_dms_spec)
_dms_spec.loader.exec_module(_dms)  # type: ignore[union-attr]

# ---- config --------------------------------------------------------------------------- #
SCENARIOS = ("tv_cdp_dead", "alpaca_5xx", "windows_restart")
SAMPLE_INTERVAL_S = 10
DEFAULT_MINUTES = 20

REPO_STATE = _REPO / "automation" / "state"
LOG_DIR = REPO_STATE / "logs"
ENGINE_HEALTH_PATH = REPO_STATE / "engine-health.json"
DRILL_DIR = _REPO / "analysis" / "drills"
HEARTBEAT_TASK = "Gamma_HeartbeatCore"
TV_CDP_HOST = "127.0.0.1"
TV_CDP_PORT = 9222


# ---- small read-only helpers -------------------------------------------------------------- #

def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Read-only TCP connect probe. Mirrors mcp_audit_check.py#check_port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _query_task_state(task_name: str) -> dict:
    """Read-only Get-ScheduledTask(Info) query. Never Start/Stop/Enable/Disable."""
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
            capture_output=True, text=True, timeout=20,
        )
        if out.returncode != 0:
            return {"error": (out.stderr or "non-zero exit").strip()[:300]}
        return json.loads(out.stdout.strip())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _read_json(path: Path) -> "dict | None":
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _tail_new_lines(path: Path, since_byte: int) -> "tuple[list[str], int]":
    """Returns (new lines appended since `since_byte`, new file size). Never raises."""
    try:
        if not path.exists():
            return ([], since_byte)
        size = path.stat().st_size
        if size <= since_byte:
            return ([], size)
        with path.open("rb") as f:
            f.seek(since_byte)
            data = f.read().decode("utf-8", errors="replace")
        lines = [ln for ln in data.splitlines() if ln.strip()]
        return (lines, size)
    except Exception:  # noqa: BLE001
        return ([], since_byte)


def _tail_new_jsonl_rows(path: Path, since_byte: int) -> "tuple[list[dict], int]":
    lines, size = _tail_new_lines(path, since_byte)
    rows = []
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except (json.JSONDecodeError, ValueError):
            continue
    return (rows, size)


def get_broker_account_probe(creds: dict) -> dict:
    """Read-only GET /v2/account -- used ONLY to observe whether the broker is reachable
    (for the alpaca_5xx scenario). Never places or modifies anything."""
    try:
        return fleet_broker._request(creds, "account")  # noqa: SLF001 -- deliberate reuse, read-only endpoint
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}


# ---- sampling --------------------------------------------------------------------------- #

class _TailCursors:
    """Byte offsets into each log/jsonl this observer tails, so every sample only carries
    NEW lines since the previous sample (never re-reports the same line twice)."""

    def __init__(self, date_str: str):
        self.date_str = date_str
        self.tv_watchdog_log = LOG_DIR / f"tv-watchdog-{date_str}.log"
        self.engine_heal_log = LOG_DIR / f"engine-heal-{date_str}.log"
        self.dms_jsonl = LOG_DIR / f"dead-mans-switch-{date_str}.jsonl"
        self.tv_off = self.tv_watchdog_log.stat().st_size if self.tv_watchdog_log.exists() else 0
        self.heal_off = self.engine_heal_log.stat().st_size if self.engine_heal_log.exists() else 0
        self.dms_off = self.dms_jsonl.stat().st_size if self.dms_jsonl.exists() else 0
        self._last_engine_health_mtime: "float | None" = None


def sample_once(cursors: _TailCursors, *, ts_offset_s: float, creds_all: dict) -> dict:
    """ONE read-only sample. Never raises -- every sub-read is independently guarded."""
    et = et_now()
    sample: dict = {"ts_offset_s": round(ts_offset_s, 1), "ts_et": et.strftime("%Y-%m-%d %H:%M:%S ET")}

    sample["tv_cdp_port_open"] = check_port(TV_CDP_HOST, TV_CDP_PORT)

    try:
        et_naive = et.replace(tzinfo=None)
        sample["heartbeat_liveness_min"] = {
            "safe": _dms.core_liveness_minutes("safe", et_naive),
            "bold": _dms.core_liveness_minutes("bold", et_naive),
        }
    except Exception as exc:  # noqa: BLE001
        sample["heartbeat_liveness_min"] = {"error": str(exc)}

    eh = _read_json(ENGINE_HEALTH_PATH)
    sample["engine_health"] = (
        {"verdict": eh.get("verdict"), "red_checks": eh.get("red_checks")} if eh else None
    )

    sample["heartbeat_task"] = _query_task_state(HEARTBEAT_TASK)

    tv_lines, cursors.tv_off = _tail_new_lines(cursors.tv_watchdog_log, cursors.tv_off)
    sample["tv_watchdog_new_lines"] = tv_lines

    heal_lines, cursors.heal_off = _tail_new_lines(cursors.engine_heal_log, cursors.heal_off)
    sample["engine_heal_new_lines"] = heal_lines

    dms_rows, cursors.dms_off = _tail_new_jsonl_rows(cursors.dms_jsonl, cursors.dms_off)
    sample["dms_new_rows"] = dms_rows

    creds = creds_all.get("safe-2") or next(iter(creds_all.values()), None)
    if creds:
        probe = get_broker_account_probe(creds)
        sample["broker_probe_ok"] = not bool(isinstance(probe, dict) and probe.get("_error"))
        sample["broker_probe_status"] = probe.get("_status") if isinstance(probe, dict) else None
    else:
        sample["broker_probe_ok"] = None
        sample["broker_probe_status"] = None

    return sample


# ---- first-automated-action detection (pure, testable on fixture samples) ---------------- #

_TV_RELAUNCH_RE = re.compile(r"RELAUNCH_(KILL|FRESH|HUNG_BRIDGE)(?!_FAILED)")
_TV_RELAUNCH_FAILED_RE = re.compile(r"RELAUNCH_\w+_FAILED")
_HEAL_RE = re.compile(r"HEALED")


def detect_first_action(scenario: str, samples: "list[dict]") -> "dict | None":
    """Scans samples IN ORDER for the first sign of an automated reaction matching the
    scenario. Returns {'action': str, 'detail': str, 'ts_offset_s': float} or None if no
    signal has fired yet across the samples given. Pure function -- no I/O, so it can be
    driven entirely by fixture data in tests."""
    if scenario == "tv_cdp_dead":
        for s in samples:
            for line in s.get("tv_watchdog_new_lines", []):
                if _TV_RELAUNCH_RE.search(line):
                    return {"action": "TV_RELAUNCH", "detail": line, "ts_offset_s": s["ts_offset_s"]}
                if _TV_RELAUNCH_FAILED_RE.search(line):
                    return {"action": "TV_RELAUNCH_FAILED", "detail": line, "ts_offset_s": s["ts_offset_s"]}
        return None

    if scenario == "alpaca_5xx":
        for s in samples:
            for row in s.get("dms_new_rows", []):
                if row.get("action") in ("READ_FAILED", "NO_CREDS"):
                    return {
                        "action": f"DMS_{row['action']}", "detail": json.dumps(row),
                        "ts_offset_s": s["ts_offset_s"],
                    }
            eh = s.get("engine_health")
            if eh and eh.get("verdict") == "RED":
                reds = eh.get("red_checks") or []
                broker_reds = [r for r in reds if isinstance(r, str) and
                               ("broker" in r.lower() or "alpaca" in r.lower())]
                if broker_reds:
                    return {
                        "action": "ENGINE_HEALTH_RED_BROKER", "detail": ", ".join(broker_reds),
                        "ts_offset_s": s["ts_offset_s"],
                    }
            if s.get("broker_probe_ok") is False:
                return {
                    "action": "BROKER_PROBE_FAILED_OBSERVED",
                    "detail": f"status={s.get('broker_probe_status')}",
                    "ts_offset_s": s["ts_offset_s"],
                }
        return None

    if scenario == "windows_restart":
        prior_liveness_unknown = True
        for s in samples:
            live = s.get("heartbeat_liveness_min") or {}
            safe = live.get("safe")
            bold = live.get("bold")
            resumed = (safe is not None and safe < 2) or (bold is not None and bold < 2)
            if resumed and prior_liveness_unknown:
                return {
                    "action": "ENGINE_RESUMED_TICKING", "detail": f"safe={safe} bold={bold}",
                    "ts_offset_s": s["ts_offset_s"],
                }
            if safe is None and bold is None:
                prior_liveness_unknown = True
            else:
                prior_liveness_unknown = False
            for line in s.get("engine_heal_new_lines", []):
                if _HEAL_RE.search(line):
                    return {"action": "HEAL_ENGINE_ACTED", "detail": line, "ts_offset_s": s["ts_offset_s"]}
        return None

    return None


# ---- output ------------------------------------------------------------------------------- #

def _paths_for(scenario: str, date_str: str) -> "tuple[Path, Path]":
    DRILL_DIR.mkdir(parents=True, exist_ok=True)
    return (
        DRILL_DIR / f"recovery-drill-{scenario}-{date_str}.jsonl",
        DRILL_DIR / f"recovery-drill-{scenario}-{date_str}.md",
    )


def _write_scenario_md(scenario: str, samples: "list[dict]", md_path: Path) -> None:
    first = detect_first_action(scenario, samples)
    lines = [
        f"# Recovery drill -- {scenario}", "",
        f"Samples: {len(samples)} @ {SAMPLE_INTERVAL_S}s interval "
        f"({(len(samples) * SAMPLE_INTERVAL_S) / 60:.1f} min observed).", "",
    ]
    if first:
        lines += [
            f"**First automated action:** `{first['action']}` at +{first['ts_offset_s']}s",
            f"- detail: {first['detail']}",
        ]
    else:
        lines += ["**First automated action:** none observed in this window."]
    lines += ["", "| +s | tv_cdp_open | heartbeat safe/bold (min) | engine_health verdict |",
              "|---|---|---|---|"]
    for s in samples:
        live = s.get("heartbeat_liveness_min") or {}
        lines.append(
            f"| {s['ts_offset_s']} | {s.get('tv_cdp_port_open')} | "
            f"{live.get('safe')}/{live.get('bold')} | "
            f"{(s.get('engine_health') or {}).get('verdict')} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- CLI surfaces --------------------------------------------------------------------------- #

def run_watch(scenario: str, minutes: float, *, sleep_fn=time.sleep, time_fn=time.time) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}, expected one of {SCENARIOS}")

    date_str = et_now().strftime("%Y-%m-%d")
    jsonl_path, md_path = _paths_for(scenario, date_str)
    cursors = _TailCursors(date_str)
    try:
        creds_all = fleet_broker.load_creds()
    except Exception:  # noqa: BLE001
        creds_all = {}

    start = time_fn()
    deadline = start + minutes * 60
    samples: list[dict] = []
    with jsonl_path.open("a", encoding="utf-8") as f:
        while time_fn() < deadline:
            s = sample_once(cursors, ts_offset_s=time_fn() - start, creds_all=creds_all)
            samples.append(s)
            f.write(json.dumps(s) + "\n")
            f.flush()
            sleep_fn(SAMPLE_INTERVAL_S)

    _write_scenario_md(scenario, samples, md_path)
    return {"scenario": scenario, "n_samples": len(samples), "jsonl": str(jsonl_path), "md": str(md_path)}


def cmd_watch(scenario: str, minutes: float) -> int:
    print(f"Watching scenario={scenario} for {minutes} min, read-only, sampling every "
          f"{SAMPLE_INTERVAL_S}s. Induce the failure yourself now (see module docstring).")
    result = run_watch(scenario, minutes)
    print(json.dumps(result, indent=2))
    return 0


def cmd_report() -> int:
    if not DRILL_DIR.exists():
        print("No analysis/drills/ directory yet -- run --watch for at least one scenario first.")
        return 1
    rows_by_scenario: dict = {}
    for scenario in SCENARIOS:
        files = sorted(DRILL_DIR.glob(f"recovery-drill-{scenario}-*.jsonl"))
        if not files:
            rows_by_scenario[scenario] = None
            continue
        latest = files[-1]
        samples = []
        for line in latest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        rows_by_scenario[scenario] = (latest, detect_first_action(scenario, samples))

    lines = ["# Recovery drill summary", "",
             "| scenario | first automated action | time | source file |",
             "|---|---|---|---|"]
    for scenario, entry in rows_by_scenario.items():
        if entry is None:
            lines.append(f"| {scenario} | not yet drilled | - | - |")
            continue
        latest, first = entry
        if first is None:
            lines.append(f"| {scenario} | none observed | - | `{latest.name}` |")
        else:
            lines.append(f"| {scenario} | {first['action']} | +{first['ts_offset_s']}s | `{latest.name}` |")
    text = "\n".join(lines) + "\n"
    print(text)
    (DRILL_DIR / "recovery-drill-summary.md").write_text(text, encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--scenario", choices=SCENARIOS)
    ap.add_argument("--minutes", type=float, default=DEFAULT_MINUTES)
    args = ap.parse_args()

    if args.watch:
        if not args.scenario:
            print("--watch requires --scenario {tv_cdp_dead,alpaca_5xx,windows_restart}")
            return 2
        return cmd_watch(args.scenario, args.minutes)
    if args.report:
        return cmd_report()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
