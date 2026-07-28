"""premarket_readiness.py -- ONE deterministic morning readiness gate. Pure Python, $0, no LLM.

WHY THIS EXISTS (WS2, filed 2026-07-27): J had to ask "are we ready to trade?" this morning
and the review missed 3 of 6 accounts -- the SECOND time this exact class of miss happened
(first: 2026-06-25; queue.md's FLEET-LIVENESS-IN-ENGINE-HEALTH item, filed 2026-07-27 ~10:00
ET, is the same-mistake-twice trigger). Later the same day the TV/CDP port was found dead and
nobody had flagged it. Every existing readiness surface (`engine_health.py`'s every-minute
beacon, `preopen_readiness.py`'s 08:25 ET task-chain+broker gate) checks PART of this picture
but none of them enumerate every ENABLED fleet arm, sanity-check the level feed's structure, or
fuse it all into ONE verdict a human can read in one line. This script is that fusion.

SEVEN CHECKS, each GREEN/YELLOW/RED + a one-line detail:
  1. fleet:<arm>      -- every ENABLED arm (accounts.json status=="active"; this naturally
                          skips disabled arms AND the frozen safe-1, whose status is "retired")
                          has a REST-reachable broker account. After 09:35 ET on a weekday, it
                          must ALSO have >=1 decision row dated today in its own ledger
                          (core-decisions.jsonl for the two mcp_heartbeat arms, fleet/<arm>/
                          decisions.jsonl for the fleet_rest arms) -- a dark ledger on a live
                          trading morning names the silent arm, never a vague "some account".
  2. core_mcp:<server> -- the exact two .mcp.json-wired servers (`alpaca` -> safe-2, `alpaca_
                          aggressive` -> bold-2 -- the ONLY two accounts the live heartbeat_core
                          engine itself trades) reachable via direct REST, same creds file
                          (fleet/secrets.json) heartbeat_core reads for order placement. Reuses
                          check 1's already-fetched snapshots -- no duplicate REST calls.
  3. levels_sanity     -- key-levels.json dated today, >=4 non-expired valid levels, at least
                          one level on EACH side of spot (an all-resistance or all-support file
                          is a structural failure, not a quiet day), file age < 90 min.
  4. bias_freshness     -- today-bias.json dated today. NON-CRITICAL (advisory context, not a
                          trading-critical gate).
  5. tv_cdp             -- port 9222 answers /json/version within 3s. NON-CRITICAL: the engine
                          trades headless via sight_beacon's direct REST even with TV/CDP down
                          (that IS today's second incident -- TV died and nothing said so; this
                          check exists specifically to close that gap, but stays YELLOW-only so
                          a dead visual surface never fake-blocks a functioning engine).
  6. engine_health      -- reuses `engine_health.py`'s OWN `build_report()` verdict verbatim
                          (heartbeats, watcher feed, kill-switches, positions, etc.) -- per spec,
                          this check REUSES that module's functions rather than re-deriving any
                          of that logic here.
  7. heartbeat_task     -- Gamma_HeartbeatCore is registered and Ready/Running in Task Scheduler
                          (queried via a windowless PowerShell Get-ScheduledTask call, CREATE_NO_
                          WINDOW -- same precedent as preopen_readiness.fetch_task_states).

RED = any CRITICAL check (1, 2, 3, 6, 7) is RED. Checks 4/5 are advisory-only -- they can push
the overall verdict to YELLOW but never RED (TV down with everything else GREEN reads YELLOW,
never RED -- exactly the guard this build is proofed against).

FAIL-OPEN EVERYWHERE (rail-2 + OP-25): every fetcher degrades to an empty/None default on any
IO error; every assessor is wrapped by `_safe_checks()` so a checker that raises internally
degrades to a single UNKNOWN row (never crashes the whole gate, never blocks the morning). This
script ALWAYS exits 0 -- it is read-only/notify-only and must never trade-halt or block J.

Output: automation/state/premarket-readiness.json {verdict, checks[], ts_et, reds[], ...} +
one Discord outbox ping on a transition into a NEW red check (idempotent, same convention as
engine_health.py/preopen_readiness.py's maybe_alert). Consumed additively by daily_brief.py's
morning brief (see `_premarket_readiness_line` there) and is safe to read even when this file
has never been written (missing -> "not yet run today", never a crash).

CREDENTIAL DISCIPLINE: creds are loaded from the gitignored fleet/secrets.json at runtime
(via fleet_broker.load_creds()) and NEVER printed/logged/written -- only derived facts
(reachable?, status, equity) ever leave this module.

Run: python setup/scripts/premarket_readiness.py
Task: Gamma_PremarketReadiness, 09:00 ET daily weekdays -- see SCHEDULED-TASKS.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE = REPO_ROOT / "automation" / "state"
FLEET_DIR = STATE / "fleet"
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
KEY_LEVELS_PATH = STATE / "key-levels.json"
TODAY_BIAS_PATH = STATE / "today-bias.json"
CORE_DECISIONS_PATH = STATE / "core-decisions.jsonl"
MCP_JSON_PATH = REPO_ROOT / ".mcp.json"
OUT_PATH = STATE / "premarket-readiness.json"
OUTBOX = STATE / "discord-outbox.jsonl"
J_MENTION = "<@207983230618435584> "

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash (OP-27 L41)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402 -- canonical DST-aware ET clock, never Bash TZ

# pythonw stdio redirect (OP-27 L41 layer 3, mirrors engine_health.py) -- a scheduled pythonw
# spawn has no console; printing without this redirect either raises or silently vanishes.
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _logs = STATE / "logs"
    _logs.mkdir(parents=True, exist_ok=True)
    _stamp = et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_logs / f"premarket-readiness-{_stamp}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_logs / f"premarket-readiness-{_stamp}.stderr.log", "a", buffering=1, encoding="utf-8")

# Two mcp_heartbeat arm ids -> the account "alias" core-decisions.jsonl rows carry, AND the
# .mcp.json server name that wires them into the live engine. This mapping is the entire
# "core_mcp" check surface -- deliberately narrow (2 accounts), distinct from check 1's
# broader "every enabled arm" sweep.
CORE_MCP_MAP = {"alpaca": "safe-2", "alpaca_aggressive": "bold-2"}
MCP_HEARTBEAT_ALIAS = {"safe-2": "safe", "bold-2": "bold"}

READY_STATES = ("Ready", "Running")
LEVELS_MIN_COUNT = 4
LEVELS_MAX_AGE_MIN = 90
AFTER_OPEN_HHMM = 935  # 09:35 ET -- before this, creds-reachable alone satisfies check 1


def _chk(name: str, status: str, detail: str, critical: bool) -> dict:
    return {"name": name, "status": status, "detail": detail, "critical": critical}


def _safe_checks(name: str, critical: bool, fn, *args) -> list:
    """Run one assessor; a raised exception degrades to ONE UNKNOWN row, never a crash.
    UNKNOWN is treated like YELLOW by fuse() -- "can't verify" is never silently GREEN, and
    never forces RED on a genuinely-innocent internal bug either (rail-2 fail-open)."""
    try:
        result = fn(*args)
    except Exception as e:  # noqa: BLE001 -- a broken checker must never block the morning
        return [_chk(name, "UNKNOWN", f"checker crashed: {type(e).__name__}: {e}", critical)]
    return result if isinstance(result, list) else [result]


def _read_json_or_none(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 -- fail-open: missing/garbled -> None, never raise
        return None


def _parse_naive_et(s: Any) -> Optional[datetime]:
    """First 19 chars as naive ET wall-clock (matches engine_health.check_level_feed's
    convention -- key-levels.json's literal -04:00 suffix is unreliable on this MT-hosted
    rig, so we deliberately ignore it and compare naive-to-naive against et_now())."""
    if not isinstance(s, str) or len(s) < 19:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Fetchers (IO, fail-open -> a safe default; never raise)
# ---------------------------------------------------------------------------

def fetch_active_arms() -> list:
    """Every accounts.json arm with status=="active" -- this is the ENTIRE "enabled" filter:
    it naturally excludes disabled/pending_build/dormant arms AND the frozen safe-1 (whose
    status is "retired", not "active", since the 2026-07-11 repoint). Fail-open -> []."""
    try:
        data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for a in data.get("arms") or []:
        if not isinstance(a, dict) or str(a.get("status")) != "active":
            continue
        if a.get("broker") not in ("alpaca", "alpaca_aggressive", "custom_rest"):
            continue  # defensive: never expect a decision ledger from a non-equity broker
        out.append({"id": a.get("id"), "execution": a.get("execution")})
    return [a for a in out if a["id"]]


def fetch_snapshots(arms: list) -> dict:
    """{arm_id: account_dict_or_{'_error':...}} via fleet_broker (same creds file + REST
    client heartbeat_core itself uses for order placement). Fail-open -> {} on any error;
    per-arm failures degrade to an _error entry rather than dropping the arm silently."""
    if not arms:
        return {}
    try:
        sys.path.insert(0, str(FLEET_DIR))
        import fleet_broker  # type: ignore
        creds = fleet_broker.load_creds()
    except Exception:  # noqa: BLE001
        return {a["id"]: {"_error": "fleet_broker/secrets.json load failed"} for a in arms}
    out = {}
    for a in arms:
        arm_id = a["id"]
        c = creds.get(arm_id)
        if not c:
            out[arm_id] = {"_error": "no creds in secrets.json"}
            continue
        try:
            out[arm_id] = fleet_broker.get_account(c)
        except Exception as e:  # noqa: BLE001
            out[arm_id] = {"_error": f"{type(e).__name__}: {e}"}
    return out


def _count_today_rows(path: Path, today: str, account_filter: Optional[str] = None,
                       tail_bytes: int = 262144) -> "tuple[int, Optional[str]]":
    """(n_rows_dated_today, newest_date_seen_in_tail). Bounded tail-read (mirrors engine_
    health.check_engine_core) so a large ledger never turns this into a slow scan. Fail-open
    -> (0, None) on any read/parse error -- the caller's assessor treats that as "no evidence
    of life today", which is the conservative (RED-leaning) direction for a critical check."""
    if not path.exists():
        return 0, None
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return 0, None
    n = 0
    newest: Optional[str] = None
    for raw in tail:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        if account_filter is not None and row.get("account") != account_filter:
            continue
        ts = str(row.get("ts_et", ""))
        if len(ts) < 10:
            continue
        d = ts[:10]
        if newest is None or d > newest:
            newest = d
        if d == today:
            n += 1
    return n, newest


def fetch_decision_counts(arms: list, et: datetime) -> dict:
    """{arm_id: (n_today, newest_date_seen)}. mcp_heartbeat arms read core-decisions.jsonl
    filtered by account alias; fleet_rest arms read their own fleet/<arm>/decisions.jsonl.
    Fail-open per-arm via _count_today_rows."""
    today = et.strftime("%Y-%m-%d")
    out = {}
    for a in arms:
        arm_id = a["id"]
        if a.get("execution") == "mcp_heartbeat":
            alias = MCP_HEARTBEAT_ALIAS.get(arm_id)
            out[arm_id] = _count_today_rows(CORE_DECISIONS_PATH, today, account_filter=alias)
        else:
            out[arm_id] = _count_today_rows(FLEET_DIR / arm_id / "decisions.jsonl", today)
    return out


def fetch_key_levels() -> Optional[dict]:
    return _read_json_or_none(KEY_LEVELS_PATH)


def fetch_today_bias() -> Optional[dict]:
    return _read_json_or_none(TODAY_BIAS_PATH)


def fetch_mcp_servers_present() -> dict:
    """{"alpaca": bool, "alpaca_aggressive": bool} -- server KEY present in .mcp.json.
    Structural only -- never reads/returns the env credential block. Fail-open -> all False
    (the assessor turns that into RED, same as a genuinely-removed server would)."""
    try:
        data = json.loads(MCP_JSON_PATH.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or {}
        return {name: name in servers for name in CORE_MCP_MAP}
    except Exception:  # noqa: BLE001
        return {name: False for name in CORE_MCP_MAP}


def fetch_tv_cdp() -> dict:
    """Live check: does TradingView's CDP endpoint answer on :9222 within 3s? Fail-open ->
    {"reachable": False, ...} -- this is a notify-only observer, never raises."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:9222/json/version", timeout=3) as r:
            if r.status == 200:
                return {"reachable": True, "detail": "CDP responding on :9222"}
            return {"reachable": False, "detail": f"CDP returned HTTP {r.status}"}
    except Exception as e:  # noqa: BLE001 -- fail-open
        return {"reachable": False, "detail": f"CDP unreachable on :9222: {type(e).__name__}: {e}"}


def fetch_engine_health() -> Optional[dict]:
    """Imports engine_health.py fresh and calls its OWN build_report() -- reuse, not
    reimplementation, per spec. Saves/restores sys.stdout/sys.stderr around the import: that
    module redirects stdio for pythonw spawns AT IMPORT TIME, which would otherwise hijack
    THIS script's own (possibly already-redirected) stdout into engine_health's log file.
    Fail-open -> None on any import/build error."""
    _orig_out, _orig_err = sys.stdout, sys.stderr
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import engine_health as eh  # type: ignore
        return eh.build_report()
    except Exception:  # noqa: BLE001
        return None
    finally:
        sys.stdout, sys.stderr = _orig_out, _orig_err


def fetch_heartbeat_task_state() -> Optional[dict]:
    """{"state": str, "last_result": int|None} for Gamma_HeartbeatCore, or None if unregistered
    / query failed. Windowless PowerShell (CREATE_NO_WINDOW), same precedent as preopen_
    readiness.fetch_task_states. Fail-open -> None."""
    ps = (
        "$t=Get-ScheduledTask -TaskName 'Gamma_HeartbeatCore' -ErrorAction SilentlyContinue;"
        "if($t){ $i=Get-ScheduledTaskInfo -TaskName 'Gamma_HeartbeatCore';"
        " Write-Output ($t.State.ToString()+'|'+$i.LastTaskResult) }"
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        line = out.stdout.strip()
        if not line or "|" not in line:
            return None
        state_s, last_s = line.split("|", 1)
        try:
            last = int(last_s)
        except (TypeError, ValueError):
            last = None
        return {"state": state_s, "last_result": last}
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Assessors (pure-ish over already-fetched data; safe to unit-test with fixtures)
# ---------------------------------------------------------------------------

def assess_fleet_liveness(arms: list, snapshots: dict, decision_counts: dict,
                           et: datetime, after_open: bool) -> list:
    """Check 1. One row PER active arm -- deliberately granular (the exact bug this build
    fixes was a REVIEW that silently missed 3 of 6 accounts; a single aggregate row could
    repeat that same class of miss)."""
    checks = []
    today = et.strftime("%Y-%m-%d")
    for arm in arms:
        arm_id = arm["id"]
        cname = f"fleet:{arm_id}"
        snap = snapshots.get(arm_id)
        if not isinstance(snap, dict) or snap.get("_error") or "status" not in snap:
            err = snap.get("_error", "malformed/unauthenticated") if isinstance(snap, dict) else "no snapshot"
            checks.append(_chk(cname, "RED", f"{arm_id}: broker REST unreachable ({err})", True))
            continue
        status = str(snap.get("status"))
        blocked = bool(snap.get("trading_blocked")) or bool(snap.get("account_blocked"))
        if status != "ACTIVE" or blocked:
            checks.append(_chk(cname, "RED", f"{arm_id}: broker status={status} blocked={blocked}", True))
            continue
        equity = snap.get("equity")
        if not after_open:
            checks.append(_chk(cname, "GREEN",
                                f"{arm_id}: reachable (equity=${equity}) -- pre-open, ledger check pending", True))
            continue
        n_today, newest = decision_counts.get(arm_id, (0, None))
        if n_today < 1:
            checks.append(_chk(
                cname, "RED",
                f"{arm_id}: NO decision rows dated today ({today}) -- ledger DARK on a live "
                f"trading morning (newest row seen: {newest or 'never'})", True,
            ))
        else:
            checks.append(_chk(cname, "GREEN",
                                f"{arm_id}: reachable (equity=${equity}), {n_today} decision row(s) today", True))
    return checks


def assess_core_mcp(snapshots: dict, servers_present: dict) -> list:
    """Check 2. Belt-and-suspenders on the exact two accounts the live heartbeat_core engine
    itself places orders through -- reuses check 1's snapshots, no duplicate REST calls."""
    checks = []
    for server, arm_id in CORE_MCP_MAP.items():
        cname = f"core_mcp:{server}"
        if not servers_present.get(server):
            checks.append(_chk(cname, "RED", f".mcp.json server '{server}' not found (expected arm {arm_id})", True))
            continue
        snap = snapshots.get(arm_id)
        if not isinstance(snap, dict) or snap.get("_error") or "status" not in snap:
            err = snap.get("_error", "malformed/unauthenticated") if isinstance(snap, dict) else "no snapshot"
            checks.append(_chk(cname, "RED", f".mcp.json '{server}' account ({arm_id}) unreachable: {err}", True))
            continue
        status = str(snap.get("status"))
        if status != "ACTIVE":
            checks.append(_chk(cname, "RED", f".mcp.json '{server}' account ({arm_id}) status={status}", True))
        else:
            equity = snap.get("equity")
            checks.append(_chk(cname, "GREEN",
                                f".mcp.json '{server}' account ({arm_id}) reachable (equity=${equity}), status=ACTIVE", True))
    return checks


def assess_levels_sanity(data: Optional[dict], et: datetime) -> dict:
    """Check 3. RED-proofed against: missing file, wrong session date, too few valid levels,
    an all-one-sided level file (the "engine sees only resistance" foot-gun), and staleness."""
    name = "levels_sanity"
    if not data:
        return _chk(name, "RED", "key-levels.json missing/unreadable", True)

    today = et.strftime("%Y-%m-%d")
    for_session = str(data.get("for_session") or "")
    if for_session != today:
        return _chk(name, "RED", f"key-levels.json for_session={for_session!r} != today {today}", True)

    levels = data.get("levels")
    if not isinstance(levels, list):
        return _chk(name, "RED", "key-levels.json has no levels[] array", True)

    valid, degenerate = [], 0
    for lv in levels:
        if not isinstance(lv, dict):
            degenerate += 1
            continue
        price = lv.get("price")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            degenerate += 1
            continue
        exp = _parse_naive_et(lv.get("expires_at"))
        if exp is not None and exp <= et:
            continue  # expired -- silently excluded, not counted as degenerate
        valid.append(lv)

    if len(valid) < LEVELS_MIN_COUNT:
        return _chk(name, "RED",
                    f"only {len(valid)} non-expired valid level(s) (< {LEVELS_MIN_COUNT} required); "
                    f"{degenerate} degenerate entr{'y' if degenerate == 1 else 'ies'} dropped", True)

    spot = data.get("spot_at_compute")
    if not isinstance(spot, (int, float)) or isinstance(spot, bool):
        return _chk(name, "RED", "no numeric spot_at_compute to test above/below structure", True)

    above = [lv for lv in valid if lv["price"] > spot]
    below = [lv for lv in valid if lv["price"] < spot]
    if not above or not below:
        if not above and not below:
            side = "no level straddles spot at all"
        elif not below:
            side = "resistance-only -- NO support below spot"
        else:
            side = "support-only -- NO resistance above spot"
        return _chk(name, "RED",
                    f"{len(valid)} valid level(s), all one-sided vs spot ${spot:.2f} ({side})", True)

    as_of_dt = _parse_naive_et(data.get("as_of"))
    if as_of_dt is None:
        return _chk(name, "RED", "key-levels.json has no parseable as_of timestamp", True)
    age_min = max(0.0, (et - as_of_dt).total_seconds() / 60.0)
    if age_min > LEVELS_MAX_AGE_MIN:
        return _chk(name, "RED",
                    f"key-levels.json stale: age {age_min:.0f}m (> {LEVELS_MAX_AGE_MIN}m), as_of={data.get('as_of')}", True)

    return _chk(name, "GREEN",
                f"{len(valid)} valid levels ({len(above)} above / {len(below)} below spot ${spot:.2f}), "
                f"age {age_min:.0f}m, dated {for_session}", True)


def assess_bias_freshness(data: Optional[dict], et: datetime) -> dict:
    """Check 4. NON-CRITICAL: a stale premarket bias read degrades context, never trade-halts."""
    name = "bias_freshness"
    if not data:
        return _chk(name, "YELLOW", "today-bias.json missing/unreadable", False)
    today = et.strftime("%Y-%m-%d")
    date = str(data.get("date") or "")
    if date != today:
        return _chk(name, "YELLOW", f"today-bias.json dated {date!r} != today {today} -- stale premarket read", False)
    return _chk(name, "GREEN", f"today-bias.json dated today, bias={data.get('bias', 'unknown')}", False)


def assess_tv_cdp(info: dict) -> dict:
    """Check 5. NON-CRITICAL by design: the engine trades headless via sight_beacon even with
    TV/CDP down -- YELLOW, never RED, so a dead visual surface can never fake-block a live
    engine (the exact guard this build is proofed against)."""
    name = "tv_cdp"
    if info.get("reachable"):
        return _chk(name, "GREEN", info.get("detail", "CDP responding on :9222"), False)
    return _chk(name, "YELLOW",
                (info.get("detail", "CDP not responding on :9222")
                 + " -- visual surface degraded; engine still trades headless via sight_beacon"), False)


def assess_engine_health(report: Optional[dict]) -> dict:
    """Check 6. Verbatim reuse of engine_health.build_report()'s own fused verdict."""
    name = "engine_health"
    if not report:
        return _chk(name, "UNKNOWN", "engine_health.build_report() unavailable/failed", True)
    verdict = str(report.get("verdict", "")).upper()
    reds = report.get("reds") or []
    detail = f"engine-health verdict={verdict}"
    if reds:
        detail += f"; top red: {reds[0]}"
    if verdict in ("RED", "YELLOW", "GREEN"):
        return _chk(name, verdict, detail, True)
    return _chk(name, "UNKNOWN", f"unrecognized engine-health verdict {verdict!r}", True)


def assess_heartbeat_task(state: Optional[dict]) -> dict:
    """Check 7. The live engine's own scheduled-task registration -- an unregistered or
    Disabled Gamma_HeartbeatCore means nothing will trade today no matter how green
    everything else reads."""
    name = "heartbeat_task"
    if not state:
        return _chk(name, "RED", "Gamma_HeartbeatCore NOT REGISTERED in Task Scheduler", True)
    st = str(state.get("state", "")).strip()
    last = state.get("last_result")
    if st in READY_STATES:
        return _chk(name, "GREEN", f"Gamma_HeartbeatCore state={st} (last_result={last})", True)
    return _chk(name, "RED", f"Gamma_HeartbeatCore state={st!r} -- not Ready/Running", True)


# ---------------------------------------------------------------------------
# Verdict fusion
# ---------------------------------------------------------------------------

def fuse(checks: list) -> str:
    """RED iff any CRITICAL check is RED. Else YELLOW if any check is RED/YELLOW/UNKNOWN
    (a non-critical RED, e.g. tv_cdp, only ever reaches YELLOW). Else GREEN."""
    if any(c["status"] == "RED" and c["critical"] for c in checks):
        return "RED"
    if any(c["status"] in ("RED", "YELLOW", "UNKNOWN") for c in checks):
        return "YELLOW"
    return "GREEN"


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def build_report() -> dict:
    et = et_now()
    weekday = et.weekday() < 5
    after_open = weekday and (et.hour * 100 + et.minute) >= AFTER_OPEN_HHMM

    # Every fetch is individually fail-open (each function already degrades internally);
    # wrapped again here so a genuinely unexpected exception can never abort the whole gate.
    def _f(fn, default, *args):
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001
            return default

    arms = _f(fetch_active_arms, [])
    snapshots = _f(fetch_snapshots, {}, arms)
    decision_counts = _f(fetch_decision_counts, {}, arms, et) if after_open else {}
    key_levels = _f(fetch_key_levels, None)
    today_bias = _f(fetch_today_bias, None)
    servers_present = _f(fetch_mcp_servers_present, {n: False for n in CORE_MCP_MAP})
    cdp_info = _f(fetch_tv_cdp, {"reachable": False, "detail": "fetch_tv_cdp crashed"})
    eh_report = _f(fetch_engine_health, None)
    hb_state = _f(fetch_heartbeat_task_state, None)

    checks: list = []
    checks += _safe_checks("fleet_liveness", True, assess_fleet_liveness,
                            arms, snapshots, decision_counts, et, after_open)
    checks += _safe_checks("core_mcp", True, assess_core_mcp, snapshots, servers_present)
    checks += _safe_checks("levels_sanity", True, assess_levels_sanity, key_levels, et)
    checks += _safe_checks("bias_freshness", False, assess_bias_freshness, today_bias, et)
    checks += _safe_checks("tv_cdp", False, assess_tv_cdp, cdp_info)
    checks += _safe_checks("engine_health", True, assess_engine_health, eh_report)
    checks += _safe_checks("heartbeat_task", True, assess_heartbeat_task, hb_state)

    verdict = fuse(checks)
    reds = [c["name"] for c in checks if c["status"] == "RED"]
    return {
        "ts_et": et.strftime("%Y-%m-%d %H:%M:%S"),
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "weekday": weekday,
        "after_open": after_open,
        "checks": checks,
        "reds": reds,
        "red_checks": reds,  # idempotency key for maybe_alert (transition-only)
        "note": "read-only/notify-only morning readiness gate; NEVER trade-halts. Critical "
                "checks (RED-capable): fleet_liveness, core_mcp, levels_sanity, engine_health, "
                "heartbeat_task. Advisory-only (YELLOW ceiling): bias_freshness, tv_cdp.",
    }


# ---------------------------------------------------------------------------
# Transition-only Discord ping (reuses the existing outbox; no new delivery path)
# ---------------------------------------------------------------------------

def _prior_reds() -> set:
    data = _read_json_or_none(OUT_PATH)
    if not data:
        return set()
    return set(data.get("red_checks") or [])


def maybe_alert(report: dict, prior_reds: set) -> bool:
    """ONE ping on a NEW red check appearing (idempotent, same convention as engine_health.py
    / preopen_readiness.py). Fail-open: any error returns False, never raises."""
    now_reds = set(report.get("red_checks") or [])
    new_reds = now_reds - prior_reds
    if not new_reds:
        return False
    triggered = sorted(new_reds)
    head = next((r["detail"] for r in report["checks"] if r["name"] == triggered[0]), triggered[0])
    extra = f" (+{len(triggered) - 1} more)" if len(triggered) > 1 else ""
    content = f"{J_MENTION}\U0001f534 PREMARKET NOT READY: {head}{extra}. Verify before 09:30 ET."
    if len(content) > 1900:
        content = content[:1880] + "...[truncated]"
    row = {"queued_at": report["checked_at_utc"], "content": content}
    try:
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as e:  # noqa: BLE001 -- never let alerting crash the gate
        print(f"[premarket_readiness] outbox append failed: {e}", file=sys.stderr)
        return False


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    try:
        prior_reds = _prior_reds()  # read BEFORE we overwrite OUT_PATH
        report = build_report()
        report["alerted"] = maybe_alert(report, prior_reds)
    except Exception as e:  # noqa: BLE001 -- top-level fail-open: never block the morning
        report = {
            "ts_et": "unknown", "verdict": "UNKNOWN", "checks": [], "reds": [], "red_checks": [],
            "error": f"{type(e).__name__}: {e}", "alerted": False,
            "note": "premarket_readiness crashed internally -- fail-open, wrote UNKNOWN",
        }
    _atomic_write(OUT_PATH, report)

    print(f"PREMARKET READINESS [{report.get('ts_et')}] -> {report['verdict']}"
          + (" (J PINGED)" if report.get("alerted") else ""))
    for c in report.get("checks", []):
        flag = "*" if c.get("critical") else " "
        print(f"  {flag} {c['status']:7} {c['name']:24} {c['detail']}")
    if report.get("reds"):
        print(f"  REDS: {', '.join(report['reds'])}")
    return 0  # always 0 -- notify-only, never blocks a scheduled chain


if __name__ == "__main__":
    raise SystemExit(main())
