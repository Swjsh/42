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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO_ROOT / "automation" / "state" / "fleet"
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
    {"name": "Gamma_EodFlatten", "critical": True, "et": "15:55", "role": "EOD flatten (Safe)"},
    {"name": "Gamma_EodFlatten_Aggressive", "critical": True, "et": "15:55", "role": "EOD flatten (Bold)"},
    {"name": "Gamma_LaunchTV", "critical": False, "et": "08:00", "role": "TV+CDP up"},
    {"name": "Gamma_Premarket", "critical": False, "et": "08:30", "role": "bias/level audit"},
    {"name": "Gamma_TvWatchdog", "critical": False, "et": "08:05/5min", "role": "keeps TV+CDP alive"},
]
# Tasks that MUST NOT be relied on as the live heartbeat (retired 2026-06-25).
RETIRED_HEARTBEATS = ("Gamma_Heartbeat", "Gamma_Heartbeat_Aggressive")
READY_STATES = ("Ready", "Running")
MIN_OPTIONS_LEVEL = 2  # level 2 = long options (required to BUY 0DTE calls/puts)


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


def build_report(et_iso: str, task_states: dict, snapshots: dict) -> dict:
    checks = assess_task_chain(task_states) + assess_broker(snapshots)
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
                " + EodFlatten) + broker auth. NEVER trade-halts.",
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
        report = build_report(et_iso, fetch_task_states(), fetch_broker_snapshots())
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
