"""preopen_readiness -- pure-Python pre-open readiness verifier for the LIVE trading chain.

Graduates the W26 *manual* human ritual ("BEFORE Monday open: verify the heartbeat
task + Alpaca key + TV CDP") into an automated, machine-readable GREEN/YELLOW/RED
verdict that pings J once on a genuine RED.

WHY THIS EXISTS (the foot-gun it kills): the old `preflight-readiness-audit.ps1`
verified `Gamma_Heartbeat` -- the LLM heartbeat RETIRED 2026-06-25 -- as "the
heartbeat", omitted the actual live engine `Gamma_HeartbeatCore` + the never-blind
eye `Gamma_SightBeacon`, hardcoded a stale "5/14" date, and had ZERO broker-auth
check. A readiness audit that verifies a DEAD task reports a false-GREEN while the
real engine is unverified (C7: a stale audit masks live state -- same class as the
2026-06-27 16-orphan incident). This verifier checks the LIVE chain + broker auth.

DESIGN (so it is pytest-guardable):
  * The two assessors (`assess_task_chain`, `assess_broker`) are PURE -- they take
    plain dicts and return Checks, no network / no clock / no subprocess.
  * The fetchers (`fetch_task_states`, `fetch_broker_snapshots`) are isolated and
    fail-open (any error -> empty dict, never raises).
  * FAIL-OPEN ALWAYS (OP-25 / rail-2): this is a read-only, notify-only observer.
    It places NO order, arms NOTHING, touches NO params/doctrine, and can NEVER
    block J or trade-halt. Any internal error degrades to a benign verdict.

No side effects on import.
"""
from __future__ import annotations

import json
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash on win32 (OP-27 L41)
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO_ROOT / "automation" / "state" / "fleet"
LOG_DIR = REPO_ROOT / "automation" / "state" / "logs"
OUT_PATH = REPO_ROOT / "automation" / "state" / "preopen-readiness.json"
# Reuse the EXISTING Discord outbox + mention convention (engine_health.py pattern,
# L17/L36 reuse-don't-rebuild). NO new path.
OUTBOX = REPO_ROOT / "automation" / "state" / "discord-outbox.jsonl"
J_MENTION = "<@207983230618435584> "

# --- The canonical LIVE trading chain (reconciled to the deterministic engine,
#     NOT the retired LLM heartbeats). `critical` => a missing/dead one REDs the
#     fused verdict (the engine genuinely cannot trade/flatten without it). ---
LIVE_CHAIN = [
    {"name": "Gamma_HeartbeatCore", "critical": True, "et": "09:30", "role": "live trading engine"},
    {"name": "Gamma_SightBeacon", "critical": True, "et": "session/1min", "role": "never-blind eye"},
    {"name": "Gamma_EodFlatten", "critical": True, "et": "15:55", "role": "EOD flatten (Safe, LLM defense-in-depth)"},
    {"name": "Gamma_EodFlatten_Aggressive", "critical": True, "et": "15:55", "role": "EOD flatten (Bold, LLM defense-in-depth)"},
    {"name": "Gamma_EodFlattenCore", "critical": True, "et": "15:52", "role": "EOD flatten backstop (pure-Python, safe-2+bold-2, no LLM)"},
    {"name": "Gamma_LaunchTV", "critical": False, "et": "08:00", "role": "TV+CDP up"},
    {"name": "Gamma_Premarket", "critical": False, "et": "08:30", "role": "bias/level audit"},
    {"name": "Gamma_TvWatchdog", "critical": False, "et": "08:05/5min", "role": "keeps TV+CDP alive"},
]
# Tasks that MUST NOT be relied on as the live heartbeat (retired 2026-06-25).
RETIRED_HEARTBEATS = ("Gamma_Heartbeat", "Gamma_Heartbeat_Aggressive")
READY_STATES = ("Ready", "Running")
MIN_OPTIONS_LEVEL = 2  # level 2 = long options (required to BUY 0DTE calls/puts)

# --- EOD-flatten "reality" check (2026-07-09 fix, Overnight Read D2 finding #4) ---
# Task Scheduler's LastTaskResult is UNTRUSTED for the wscript/vbs fire-and-forget launch
# chain used across this rig: `Shell.Run cmd, 0, False` (WaitOnReturn=False) means wscript
# itself exits 0 the instant it LAUNCHES the child process -- it never observes the child's
# real exit code. Confirmed 2026-07-09: Gamma_EodFlatten/_Aggressive both genuinely failed
# ("Error: Exceeded USD budget (1)", real log `=== END tick exit=1 ===`) while
# `Get-ScheduledTaskInfo` reported `LastTaskResult: 0` for both. assess_task_chain() above
# (registration/Ready-state) is still useful -- it catches an unregistered/disabled task --
# but it CANNOT catch "registered, fired, and silently failed". This assessor reads the
# task's own log/jsonl tail instead -- the one place the real outcome survives the mask.
EOD_FLATTEN_REALITY_TASKS = ("Gamma_EodFlatten", "Gamma_EodFlatten_Aggressive", "Gamma_EodFlattenCore")
EOD_FLATTEN_MAX_AGE_DAYS = 6  # tolerate a long weekend/holiday gap before flagging "no fire"
GOOD_EOD_OUTCOMES = {"NOOP", "SUCCESS", "DRY_RUN"}  # eod_flatten.py's per-arm outcome vocabulary

# --- broker canary (2026-07-11, markdown/planning/TWIN-PROGRAM.md) -----------------------
# The 24/7 crypto twin observes Alpaca API health (latency/auth/error-rate) hours before
# the SPY 09:30 open would discover a problem -- see setup/scripts/broker_canary.py. This
# is the ONE genuinely NEW piece of information the pre-open gate gains from it: a broker
# outage surfaces at 08:25 ET instead of at the open. CANARY_MAX_AGE_MIN is generous
# relative to the canary's ~5min piggyback cadence (once wired into a scheduled tick --
# see queue.md) so a single missed fire, or the hookup simply not being wired yet, never
# produces a false alarm -- see assess_broker_canary()'s fail-open design below.
CANARY_PATH = REPO_ROOT / "automation" / "state" / "broker-canary.json"
CANARY_MAX_AGE_MIN = 60


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # GREEN | YELLOW | RED
    detail: str
    critical: bool


def assess_task_chain(task_states: dict) -> list[Check]:
    """PURE. task_states = {task_name: {"state": str, "last_result": int|None}}.

    A live-chain task is GREEN when registered AND in a Ready/Running state.
    Missing -> RED. Registered-but-disabled/other -> YELLOW.
    """
    checks: list[Check] = []
    for spec in LIVE_CHAIN:
        name = spec["name"]
        crit = spec["critical"]
        st = task_states.get(name)
        if not st:
            checks.append(Check(name, "RED", f"NOT REGISTERED ({spec['role']})", crit))
            continue
        state = str(st.get("state", "")).strip()
        last = st.get("last_result")
        if state in READY_STATES:
            checks.append(
                Check(name, "GREEN", f"{state} ({spec['role']}, fires ~{spec['et']} ET, last_result={last})", crit)
            )
        else:
            checks.append(Check(name, "YELLOW", f"state={state!r} ({spec['role']})", crit))
    return checks


def assess_tv_cdp(cdp_info: dict) -> list[Check]:
    """PURE. cdp_info = {"reachable": bool, "detail": str}.

    FIX (2026-07-06): preopen_readiness previously verified ONLY Task Scheduler
    registration state for Gamma_LaunchTV/Gamma_TvWatchdog -- which reads "Ready"
    even when the PC was off overnight and CDP is genuinely down (a task's
    registration doesn't change just because the machine was asleep). This is the
    missing LIVE-liveness check that would have caught this morning's TV/CDP gap
    at 08:25 ET instead of it surfacing via Discord alerts at 09:43-09:52 ET.
    """
    if cdp_info.get("reachable"):
        return [Check("tv_cdp", "GREEN", cdp_info.get("detail", "CDP responding"), True)]
    return [Check("tv_cdp", "RED", cdp_info.get("detail", "CDP not responding on :9222"), True)]


def assess_eod_flatten_reality(sources: dict) -> list[Check]:
    """PURE. sources = {task_name: {"date": str|None, "text": str|None, "rows": list|None}}.

    Reads the REAL per-fire evidence for each EOD-flatten task, not Task Scheduler state:
      * Gamma_EodFlatten / Gamma_EodFlatten_Aggressive (LLM): last '=== END tick exit=N ==='
        line in the day's .log tail. N != 0 -> RED, regardless of what LastTaskResult says.
      * Gamma_EodFlattenCore (pure-Python): last per-arm outcome row from the day's .jsonl
        (structured, so no regex needed). Any arm outcome outside GOOD_EOD_OUTCOMES -> RED.
    Missing/stale evidence -> RED "no fire found" (fail toward RED, same convention as
    assess_tv_cdp/assess_broker -- absence of positive evidence is never silently GREEN).
    """
    checks: list[Check] = []
    for name in EOD_FLATTEN_REALITY_TASKS:
        src = sources.get(name)
        cname = f"eod_reality:{name}"
        if not src or not src.get("date"):
            checks.append(Check(
                cname, "RED",
                f"no fire found in the last {EOD_FLATTEN_MAX_AGE_DAYS}d "
                "(safety net unverified -- Task Scheduler state alone is not proof)",
                True,
            ))
            continue

        date = src["date"]
        if name == "Gamma_EodFlattenCore":
            rows = src.get("rows") or []
            if not rows:
                checks.append(Check(cname, "RED", f"log dated {date} but no per-arm rows parsed", True))
                continue
            bad = [r for r in rows if r.get("outcome") not in GOOD_EOD_OUTCOMES]
            if bad:
                checks.append(Check(
                    cname, "RED",
                    f"{date}: real outcome(s) {[r.get('outcome') for r in bad]} "
                    f"for arm(s) {[r.get('arm') for r in bad]}",
                    True,
                ))
            else:
                outs = {r.get("arm"): r.get("outcome") for r in rows}
                checks.append(Check(cname, "GREEN", f"{date}: {outs}", True))
        else:
            import re as _re
            text = src.get("text") or ""
            matches = _re.findall(r"=== END tick exit=(\d+) ===", text)
            if not matches:
                checks.append(Check(cname, "RED", f"log dated {date} has no END-tick marker (incomplete/no run)", True))
                continue
            real_exit = int(matches[-1])
            if real_exit == 0:
                checks.append(Check(cname, "GREEN", f"{date}: real exit=0", True))
            else:
                checks.append(Check(
                    cname, "RED",
                    f"{date}: REAL exit={real_exit} (Task Scheduler LastTaskResult does NOT "
                    "reflect this for wscript-launched tasks -- read from the log tail)",
                    True,
                ))
    return checks


def assess_broker_canary(canary_info: Optional[dict]) -> list[Check]:
    """PURE. canary_info = the parsed broker-canary.json dict (broker_canary.assess()'s
    output), or None when missing/stale -- fetch_broker_canary() already applies the
    staleness gate, so by the time this function sees None it genuinely means "no fresh
    canary data" (not yet wired, or the twin/canary machinery has stopped firing).

    DELIBERATELY FAIL-OPEN on absence -- the opposite convention from assess_tv_cdp /
    assess_eod_flatten_reality (which fail TOWARD red on missing evidence, because those
    ARE the live trading chain). The canary is a piggybacked ENHANCER riding on the 24/7
    crypto twin (TWIN-PROGRAM.md) -- an optional, additive signal -- so a missing/stale
    canary must NEVER be able to gate the live chain on its own: it degrades to
    non-critical "INFO", which fuse() treats as neutral (matches neither its RED nor
    YELLOW branch, so it can never move the fused verdict). A canary-reported RED (the
    twin's own overnight observations show the broker/API genuinely degraded) DOES
    propagate as a critical RED -- that IS the entire point of building this: surface an
    Alpaca outage hours before the 09:30 open would otherwise discover it.
    """
    if not canary_info:
        return [Check("broker_canary", "INFO",
                      "no fresh canary data (not yet wired into a scheduled tick, or quiet) "
                      "-- fail-open, never blocks pre-open", False)]
    verdict = str(canary_info.get("verdict", "")).upper()
    detail = canary_info.get("detail", "")
    last_ok = canary_info.get("last_ok_et") or "unknown"
    if verdict == "RED":
        return [Check("broker_canary", "RED",
                      f"Alpaca API degraded overnight per twin canary: {detail} (last_ok_et={last_ok})",
                      True)]
    if verdict == "YELLOW":
        return [Check("broker_canary", "YELLOW",
                      f"twin canary degraded: {detail} (last_ok_et={last_ok})", False)]
    if verdict == "GREEN":
        return [Check("broker_canary", "GREEN", f"twin canary nominal: {detail}", False)]
    return [Check("broker_canary", "INFO",
                  f"unrecognized canary verdict {verdict!r} -- fail-open, never blocks pre-open", False)]


def assess_broker(snapshots: dict) -> list[Check]:
    """PURE. snapshots = {alias: account_dict}. Verifies each account can place
    0DTE option orders at open: ACTIVE, not blocked, options level >= 2, PDT headroom.
    """
    checks: list[Check] = []
    if not snapshots:
        return [Check("broker", "RED", "no account snapshots (creds load / auth failed)", True)]
    for alias, acct in snapshots.items():
        if not isinstance(acct, dict) or acct.get("_error") or "status" not in acct:
            err = (acct or {}).get("_error", "malformed/unauthenticated") if isinstance(acct, dict) else "malformed"
            checks.append(Check(f"broker:{alias}", "RED", f"auth/read failed: {err}", True))
            continue
        status = str(acct.get("status"))
        blocked = bool(acct.get("trading_blocked")) or bool(acct.get("account_blocked"))
        try:
            level = int(acct.get("options_trading_level", 0))
        except (TypeError, ValueError):
            level = 0
        try:
            dtc = int(acct.get("daytrade_count", 0))
        except (TypeError, ValueError):
            dtc = 0
        pdt = bool(acct.get("pattern_day_trader"))
        try:
            equity = float(acct.get("equity", 0) or 0)
        except (TypeError, ValueError):
            equity = 0.0

        if status != "ACTIVE" or blocked:
            checks.append(
                Check(f"broker:{alias}", "RED", f"status={status} trading/account_blocked={blocked}", True)
            )
        elif level < MIN_OPTIONS_LEVEL:
            checks.append(
                Check(f"broker:{alias}", "RED", f"options_trading_level={level} < {MIN_OPTIONS_LEVEL} (cannot buy options)", True)
            )
        elif pdt and equity < 25000 and dtc >= 3:
            # PDT under $25k with no day-trade headroom -- informational warning, the
            # live risk_gate enforces PDT; never RED the readiness on it.
            checks.append(
                Check(f"broker:{alias}", "YELLOW", f"PDT no headroom: dtc={dtc}, equity=${equity:.0f}", False)
            )
        else:
            checks.append(
                Check(
                    f"broker:{alias}", "GREEN",
                    f"ACTIVE, optsL{level}, equity=${equity:.0f}, dtc={dtc}, pdt={pdt}", True,
                )
            )
    return checks


def fuse(checks: list[Check]) -> str:
    """PURE. Any critical RED -> RED; any non-critical RED or any YELLOW -> YELLOW; else GREEN."""
    if any(c.status == "RED" and c.critical for c in checks):
        return "RED"
    if any(c.status == "RED" or c.status == "YELLOW" for c in checks):
        return "YELLOW"
    return "GREEN"


# ----------------------------- isolated, fail-open fetchers -----------------------------

def fetch_task_states() -> dict:
    """Query the live scheduler for the live-chain tasks. Fail-open -> {} on any error."""
    states: dict = {}
    names = [s["name"] for s in LIVE_CHAIN]
    ps = (
        "$ns=@(" + ",".join(f"'{n}'" for n in names) + ");"
        "foreach($n in $ns){"
        " $t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"
        " if($t){ $i=Get-ScheduledTaskInfo -TaskName $n;"
        " Write-Output ($n+'|'+$t.State+'|'+$i.LastTaskResult) } }"
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=60,
            creationflags=_CREATE_NO_WINDOW,
        )
        for line in out.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3:
                try:
                    last = int(parts[2])
                except (TypeError, ValueError):
                    last = None
                states[parts[0]] = {"state": parts[1], "last_result": last}
    except Exception:
        return {}
    return states


def fetch_broker_snapshots() -> dict:
    """Pull read-only account info per fleet arm. Fail-open -> {} on any error."""
    try:
        sys.path.insert(0, str(FLEET_DIR))
        import fleet_broker  # type: ignore

        creds = fleet_broker.load_creds()
        return {alias: fleet_broker.get_account(c) for alias, c in creds.items()}
    except Exception:
        return {}


def fetch_tv_cdp() -> dict:
    """Live check: is TradingView's CDP endpoint actually responding on :9222?
    Fail-open -> {"reachable": False, ...} on any error, never raises (rail-2)."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:9222/json/version", timeout=5) as r:
            if r.status == 200:
                return {"reachable": True, "detail": "CDP responding on :9222"}
            return {"reachable": False, "detail": f"CDP returned HTTP {r.status}"}
    except Exception as e:  # noqa: BLE001 -- fail-open, this is a notify-only observer
        return {"reachable": False, "detail": f"CDP unreachable on :9222: {type(e).__name__}: {e}"}


def _latest_dated_file(log_dir: Path, glob_pat: str, date_re: str):
    """Return (Path, 'YYYY-MM-DD') for the newest file matching glob_pat, or None.

    Picks the max date STRING (works fine for zero-padded YYYY-MM-DD names); does not
    require the file to exist beyond what glob() already confirms.
    """
    import re as _re
    best = None
    for p in log_dir.glob(glob_pat):
        m = _re.search(date_re, p.name)
        if m:
            d = m.group(1)
            if best is None or d > best[1]:
                best = (p, d)
    return best


def fetch_eod_flatten_reality() -> dict:
    """Read the newest dated log/jsonl per EOD-flatten task. Fail-open -> {} (or a partial
    dict) on any error -- a read failure degrades each missing task to RED via the assessor,
    it never raises and never blocks the pre-open window (rail-2).
    """
    out: dict = {}
    try:
        found = _latest_dated_file(LOG_DIR, "eod-flatten-[0-9]*.log", r"eod-flatten-(\d{4}-\d{2}-\d{2})\.log")
        if found:
            p, d = found
            out["Gamma_EodFlatten"] = {"date": d, "text": p.read_text(encoding="utf-8", errors="replace")[-4000:]}

        found = _latest_dated_file(LOG_DIR, "eod-flatten-aggressive-[0-9]*.log",
                                    r"eod-flatten-aggressive-(\d{4}-\d{2}-\d{2})\.log")
        if found:
            p, d = found
            out["Gamma_EodFlatten_Aggressive"] = {"date": d, "text": p.read_text(encoding="utf-8", errors="replace")[-4000:]}

        found = _latest_dated_file(LOG_DIR, "eod-flatten-[0-9]*.jsonl", r"eod-flatten-(\d{4}-\d{2}-\d{2})\.jsonl")
        if found:
            p, d = found
            last_by_arm: dict = {}
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                arm = row.get("arm")
                if arm:
                    last_by_arm[arm] = row  # keep the LAST row per arm (most recent attempt)
            out["Gamma_EodFlattenCore"] = {"date": d, "rows": list(last_by_arm.values())}
    except Exception:
        return out  # partial is fine -- missing keys degrade to RED per-task in the assessor

    # Staleness gate: a file that exists but is too old is the same signal as "no fire" --
    # drop it so the assessor treats it as missing rather than crediting a stale success.
    try:
        sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))
        from et_clock import et_now  # type: ignore
        from datetime import date as _date

        today = et_now().date()
        for name in list(out.keys()):
            try:
                yy, mm, dd = (int(x) for x in out[name]["date"].split("-"))
                if (today - _date(yy, mm, dd)).days > EOD_FLATTEN_MAX_AGE_DAYS:
                    out.pop(name, None)
            except Exception:
                out.pop(name, None)
    except Exception:
        pass
    return out


def fetch_broker_canary() -> Optional[dict]:
    """Read automation/state/broker-canary.json (broker_canary.assess()'s glance output).
    Fail-open -> None on ANY error (missing file, malformed JSON) AND when the file is
    older than CANARY_MAX_AGE_MIN (assessed_at_et too stale -> treated the same as
    "never written" so assess_broker_canary() degrades to non-critical INFO, never RED --
    see that function's docstring for why absence must never gate the live chain). Never
    raises (rail-2)."""
    try:
        if not CANARY_PATH.exists():
            return None
        data = json.loads(CANARY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- fail-open, this is a notify-only observer
        return None
    assessed_at = data.get("assessed_at_et")
    if not assessed_at:
        return None
    try:
        sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))
        from et_clock import et_now  # type: ignore

        age_min = (et_now() - datetime.fromisoformat(str(assessed_at))).total_seconds() / 60.0
        if age_min > CANARY_MAX_AGE_MIN:
            return None
    except Exception:  # noqa: BLE001 -- an unparsable timestamp is treated as stale, not fatal
        return None
    return data


def build_report(et_iso: str, task_states: dict, snapshots: dict,
                  cdp_info: Optional[dict] = None,
                  eod_flatten_sources: Optional[dict] = None,
                  canary_info: Optional[dict] = None) -> dict:
    checks = (
        assess_task_chain(task_states)
        + assess_broker(snapshots)
        + assess_tv_cdp(cdp_info or {})
        + assess_eod_flatten_reality(eod_flatten_sources or {})
        + assess_broker_canary(canary_info)
    )
    verdict = fuse(checks)
    return {
        "checked_at_et": et_iso,
        "verdict": verdict,
        "checks": [
            {"name": c.name, "status": c.status, "detail": c.detail, "critical": c.critical}
            for c in checks
        ],
        "reds": [c.name for c in checks if c.status == "RED"],
        # `red_checks` is the idempotency key for the transition-only alert (same as
        # `reds` here -- check names are already canonical). Kept distinct for parity
        # with engine_health.py's outbox convention.
        "red_checks": [c.name for c in checks if c.status == "RED"],
        "note": "read-only/notify-only; verifies the LIVE chain (HeartbeatCore + SightBeacon"
                " + EodFlatten) + broker auth + TV/CDP liveness + EOD-flatten REAL log-tail"
                " outcome (not Task Scheduler exit code, which wscript-launch tasks mask)"
                " + the 24/7 twin's broker-canary signal (fail-open enhancer, never a new"
                " single point of failure). NEVER trade-halts.",
    }


# ----------------------------- transition-only J-ping (rail-2 fail-open) -----------------------------

def _prior_reds() -> set:
    """Prior set-of-red-check-names from the last written report (the idempotency key
    for the transition alert). Fail-open -> empty set on any read error."""
    try:
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        return set(data.get("red_checks") or [])
    except Exception:
        return set()


def maybe_alert(report: dict, prior_reds: set, queued_at_utc: str) -> bool:
    """Append ONE SOUL-voice line to the EXISTING Discord outbox on a *transition into
    RED* -- a RED check that was NOT red on the previous run. Idempotent (keyed on the
    SET of red check-names) so it pings ONCE per transition and never re-spams while the
    same red persists (avoids the alert-fatigue foot-gun). FAIL-OPEN (rail-2): any error
    returns False and never raises -- a notify-only observer can never crash the pre-open
    window nor block J.

    NOTE the conservative direction: we alert on a NEWLY-red check regardless of whether
    the fused verdict is RED (critical) or YELLOW (non-critical degraded) -- a broker that
    can't authenticate at open is worth one ping even if a non-critical task carried it to
    YELLOW. But we do NOT ping on GREEN, and never on a red that already pinged."""
    now_reds = set(report.get("red_checks") or [])
    new_reds = now_reds - prior_reds
    if not new_reds:
        return False
    triggered = sorted(new_reds)
    head = triggered[0]
    extra = f" (+{len(triggered) - 1} more)" if len(triggered) > 1 else ""
    content = (
        f"{J_MENTION}\U0001f534 Pre-open NOT READY: {head}{extra}. "
        "Live chain / broker auth failed before open. Verify before 09:30 ET."
    )
    if len(content) > 1900:
        content = content[:1880] + "...[truncated]"
    row = {"queued_at": queued_at_utc, "content": content}
    try:
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as e:  # noqa: BLE001 -- never let alerting crash the verifier
        print(f"[preopen_readiness] outbox append failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    try:
        sys.path.insert(0, str(REPO_ROOT / "setup" / "scripts"))
        from et_clock import et_now  # type: ignore

        et_iso = et_now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        et_iso = "unknown"
    utc_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        prior_reds = _prior_reds()  # read BEFORE we overwrite OUT_PATH
        report = build_report(
            et_iso, fetch_task_states(), fetch_broker_snapshots(), fetch_tv_cdp(),
            fetch_eod_flatten_reality(), fetch_broker_canary(),
        )
        report["alerted"] = maybe_alert(report, prior_reds, utc_iso)
        OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"PRE-OPEN READINESS [{et_iso}] -> {report['verdict']}"
              + (" (J PINGED)" if report["alerted"] else ""))
        for c in report["checks"]:
            flag = "*" if c["critical"] else " "
            print(f"  {flag} {c['status']:6} {c['name']:32} {c['detail']}")
        if report["reds"]:
            print(f"  REDS: {', '.join(report['reds'])}")
    except Exception as e:  # fail-open: never crash the pre-open window
        print(f"PRE-OPEN READINESS: benign-skip ({e})")
    return 0  # always 0 -- a verifier must never break a scheduled chain


if __name__ == "__main__":
    raise SystemExit(main())
