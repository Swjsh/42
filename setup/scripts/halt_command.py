"""halt_command.py -- phone-reachable emergency HALT/RESUME (TASK B5-phone-halt, 2026-09-01).

Parses and executes J's "HALT <arm>" / "HALT ALL" / "HALT <arm> FLATTEN" / "RESUME <arm>"
Discord commands. Imported by discord-responder.py (kept out of that file so the parsing +
broker-touching logic has its own focused test file, per the "many small files" rule).

WHY A SEPARATE HALT PATH FROM THE EXISTING ship/shelve/revert BUS (discord-responder.py):
those three all require a PENDING/APPLIED conductor-proposals.jsonl row to act on. HALT must
work with ZERO preconditions -- it is the off-switch for "the day is going wrong, stop trading
NOW", not a proposal-approval flow.

TWO DIFFERENT ENFORCEMENT MECHANISMS, both handled here (arm-specific, not uniform):
  * CORE arms (safe-2, bold-2) trade via mcp_heartbeat/heartbeat_core.py, which reads
    `tripped` off the account's OWN root/aggressive circuit-breaker.json every tick
    (setup/scripts/heartbeat_core.py ~L2604). Writing tripped=true there halts entries on
    the VERY NEXT heartbeat tick (<=1 min during RTH).
  * FLEET arms (safe-3, risky-1) trade via fleet_live.py (Gamma_FleetExecutor, 1-min
    cadence), NOT heartbeat_core.py. Its OWN per-arm breaker --
    automation/state/fleet/<arm>/circuit-breaker.json -- IS read every tick
    (`_load_or_arm_breaker` -> `killed = bool(breaker.get("tripped"))` -> gates
    `arm_live` at fleet_live.py's arm-live computation). THIS IS THE CORRECTION of the
    task brief's working assumption: it named `kill-switch-<arm>.json` (written by
    eod_flatten.py's escalation path) as the only fleet halt file and expected it to be
    unenforced -- true for THAT file (confirmed: fleet_executor.py grep shows no reader),
    but there IS a second, live-enforced breaker file per fleet arm that fleet_live.py
    (not frozen -- only fleet_executor.py is on FROZEN_TRADING_PATH) reads every tick.
    Both files are written here: the enforced one for real effect, kill-switch-<arm>.json
    for audit-trail parity with eod_flatten.py's own escalation precedent.

CAVEAT (disclosed, not hidden): the fleet per-arm breaker has NO escalation_unresolved
check in fleet_live.py's `_load_or_arm_breaker` -- it unconditionally re-arms (tripped=False)
the first tick a NEW day's date doesn't match `last_reset`. So a fleet-arm HALT holds for the
REST OF TODAY (same-day ticks all see last_reset==today, tripped stays true) but does NOT
survive to a new trading day the way a core-arm halt's escalation_unresolved does via
daily_loss_guard.rearm(). RESUME's docstring says this explicitly per arm kind.

FAIL-CLOSED ON ACTION, FAIL-OPEN ON EVERYTHING ELSE: FLATTEN only ever fires on a broker read
that came back OK (fleet_broker.open_spy_option_positions_checked's own contract) -- an
unreadable broker is refused, never treated as "must be flat". Parsing/logging/allowlist
failures degrade to a refusal message, never to a silent no-op AND never to "just do it".
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
REPO = _SCRIPTS_DIR.parents[1]
STATE_DIR = REPO / "automation" / "state"
FLEET_DIR = STATE_DIR / "fleet"
LOG_DIR = STATE_DIR / "logs"
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
CFG_PATH = STATE_DIR / ".discord-config.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"

for _p in (str(_SCRIPTS_DIR), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from et_clock import et_now  # noqa: E402
import fleet_broker  # noqa: E402

# ---------------------------------------------------------------------------------
# Per-arm breaker schema mapping for the two CORE arms (mirrors daily_loss_guard.py's
# ACCOUNTS dict, duplicated as constants rather than imported -- this module must not
# depend on daily_loss_guard's CLI/argparse surface just to read two field names).
# ---------------------------------------------------------------------------------
CORE_BREAKERS: dict[str, dict[str, Any]] = {
    "safe-2": {
        "path": STATE_DIR / "circuit-breaker.json",
        "reason_field": "tripped_reason",
        "at_field": "tripped_at",
    },
    "bold-2": {
        "path": STATE_DIR / "aggressive" / "circuit-breaker.json",
        "reason_field": "trip_reason",
        "at_field": "tripped_at_et",
    },
}


def is_core_arm(arm: str) -> bool:
    return arm in CORE_BREAKERS


def _active_spy_arms() -> list[str]:
    """Every active, real-broker (paper) SPY option arm id -- core + fleet. Mirrors
    eod_flatten.py's `_active_arms()` derivation exactly (same registry, same filters)
    so the HALT roster can never silently drift from what actually trades. accounts.json
    is READ ONLY here -- never written (frozen trading-path file, per CLAUDE.md)."""
    try:
        reg = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return list(CORE_BREAKERS) + ["safe-3", "risky-1"]
    out: list[str] = []
    for arm in reg.get("arms", []):
        acct = arm.get("account_number")
        if not isinstance(acct, str) or not acct.startswith("PA"):
            continue  # skip futures/sim arms -- not SPY options
        if str(arm.get("status") or "").lower() != "active":
            continue  # skip retired arms (e.g. risky-3 as of 2026-09-01)
        aid = arm.get("id") or arm.get("arm_id")
        if aid:
            out.append(str(aid))
    return out or (list(CORE_BREAKERS) + ["safe-3", "risky-1"])


def _fleet_breaker_path(arm: str) -> Path:
    return FLEET_DIR / arm / "circuit-breaker.json"


def _kill_switch_path(arm: str) -> Path:
    return STATE_DIR / f"kill-switch-{arm}.json"


def _write_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(path)


def _et_ts() -> str:
    return et_now().strftime("%Y-%m-%d %H:%M:%S ET")


# ---------------------------------------------------------------------------------
# Logging: automation/state/logs/halt-<date>.log (every HALT/RESUME/FLATTEN + every
# refusal, per TASK B5's "log every HALT" requirement) + a STATUS.md "## Live watch"
# line (mirrors theta_clock.py's `_flag_live_watch` insertion idiom exactly: newest
# line inserted right after the marker, section auto-created if absent).
# ---------------------------------------------------------------------------------

def _log_halt(line: str, *, log_dir: Path = LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    p = log_dir / f"halt-{et_now().strftime('%Y-%m-%d')}.log"
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{_et_ts()}] {line}\n")
    except OSError:
        pass
    logging.info("HALT-LOG %s", line)


def _flag_live_watch(line: str, *, status_md_path: Path = STATUS_MD) -> None:
    """Append ONE line to STATUS.md's '## Live watch' section. Fail-open: a STATUS.md
    write failure must never break the HALT/RESUME action it is merely narrating."""
    try:
        text = status_md_path.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Live watch"
    if marker not in text:
        block = (
            f"{marker}\n\n"
            "_Standing visibility-only flag surface (THETA COCKPIT, 2026-08-01 J directive) -- "
            "NOT a breakage list, no auto-exit ever. Producers append ONE loud line here on a "
            "NEW stalled-position threshold crossing; never re-fired for the same position. "
            "Producer: setup/scripts/theta_clock.py._\n\n---\n\n"
        )
        kb = "## Known broken"
        text = text.replace(kb, block + kb, 1) if kb in text else block + text
    head, _, tail = text.partition(marker + "\n")
    try:
        status_md_path.write_text(
            f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8"
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------------
_HALT_RE = re.compile(r"^\s*HALT\s+(ALL|[A-Za-z][A-Za-z0-9\-]*)(\s+FLATTEN)?\s*$", re.IGNORECASE)
_RESUME_RE = re.compile(r"^\s*RESUME\s+(ALL|[A-Za-z][A-Za-z0-9\-]*)\s*$", re.IGNORECASE)


def parse_command(text: str) -> dict | None:
    """Parse 'HALT <arm>' / 'HALT ALL' / 'HALT <arm|ALL> FLATTEN' / 'RESUME <arm|ALL>'.

    Returns {'verb': 'HALT'|'RESUME', 'target': 'ALL'|<lowercase arm id>, 'flatten': bool}
    or None if `text` does not match one of these shapes at all -- callers MUST fall
    through to their normal pipeline (approve/revoke/Q&A) unchanged on None, exactly like
    `_classify_command` does for ship/shelve. An unrecognized ARM inside a recognized
    HALT/RESUME shape is NOT None here (still returns a dict) -- that is a resolvable-arm
    problem, refused later with the active roster, not a parse failure."""
    if not text:
        return None
    stripped = text.strip()
    m = _HALT_RE.match(stripped)
    if m:
        raw = m.group(1)
        target = "ALL" if raw.upper() == "ALL" else raw.lower()
        return {"verb": "HALT", "target": target, "flatten": bool(m.group(2))}
    m = _RESUME_RE.match(stripped)
    if m:
        raw = m.group(1)
        target = "ALL" if raw.upper() == "ALL" else raw.lower()
        return {"verb": "RESUME", "target": target, "flatten": False}
    return None


# ---------------------------------------------------------------------------------
# Breaker writers -- one pair per arm kind. Each PRESERVES every other field already in
# the file (read -> mutate 3 keys -> atomic write), never truncates to a fresh object.
# ---------------------------------------------------------------------------------

def halt_core_arm(arm: str, *, reason: str, by: str) -> dict:
    cfg = CORE_BREAKERS[arm]
    path: Path = cfg["path"]
    if not path.exists():
        return {"arm": arm, "kind": "core", "ok": False, "action": "ERROR",
                "error": "breaker_file_missing"}
    try:
        breaker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"arm": arm, "kind": "core", "ok": False, "action": "ERROR",
                "error": f"unreadable: {e}"}
    breaker["tripped"] = True
    breaker[cfg["reason_field"]] = reason
    breaker[cfg["at_field"]] = _et_ts()
    breaker["escalation_unresolved"] = True
    _write_atomic(path, breaker)
    _log_halt(f"HALT core arm={arm} by={by} reason={reason}")
    return {"arm": arm, "kind": "core", "ok": True, "action": "TRIPPED"}


def halt_fleet_arm(arm: str, *, reason: str, by: str) -> dict:
    """See module docstring for WHY two files are written and which one is enforced."""
    fb_path = _fleet_breaker_path(arm)
    if fb_path.exists():
        try:
            breaker = json.loads(fb_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            breaker = {}
    else:
        breaker = {}
    breaker["tripped"] = True
    breaker["tripped_at"] = _et_ts()
    breaker["tripped_reason"] = reason
    # Informational only today -- fleet_live.py's _load_or_arm_breaker has no
    # escalation_unresolved check (see module docstring CAVEAT). Set anyway so a future
    # wiring of that check (or a human reading the file) sees clear intent.
    breaker["escalation_unresolved"] = True
    _write_atomic(fb_path, breaker)

    ks_path = _kill_switch_path(arm)
    _write_atomic(ks_path, {
        "armed": True, "arm": arm, "reason": reason,
        "set_by": by, "set_at_et": _et_ts(),
        "clear_by": "RESUME <arm> from Discord, or delete this file",
        "_note": "Audit-trail parity with eod_flatten.py's escalation path. NOT read by any "
                 "live gate today (confirmed: no reader in fleet_executor.py) -- the file that "
                 "actually blocks entries is automation/state/fleet/<arm>/circuit-breaker.json, "
                 "written alongside this one.",
    })
    _log_halt(f"HALT fleet arm={arm} by={by} reason={reason}")
    return {"arm": arm, "kind": "fleet", "ok": True, "action": "TRIPPED"}


def resume_core_arm(arm: str, *, by: str) -> dict:
    cfg = CORE_BREAKERS[arm]
    path: Path = cfg["path"]
    if not path.exists():
        return {"arm": arm, "kind": "core", "ok": False, "action": "ERROR",
                "error": "breaker_file_missing"}
    try:
        breaker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"arm": arm, "kind": "core", "ok": False, "action": "ERROR",
                "error": f"unreadable: {e}"}
    was_tripped = bool(breaker.get("tripped"))
    breaker["escalation_unresolved"] = False
    _write_atomic(path, breaker)
    _log_halt(f"RESUME core arm={arm} by={by} tripped_left_as_is={was_tripped}")
    return {"arm": arm, "kind": "core", "ok": True, "action": "ESCALATION_CLEARED",
            "tripped_still": was_tripped}


def resume_fleet_arm(arm: str, *, by: str) -> dict:
    path = _fleet_breaker_path(arm)
    if not path.exists():
        return {"arm": arm, "kind": "fleet", "ok": False, "action": "ERROR",
                "error": "breaker_file_missing"}
    try:
        breaker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"arm": arm, "kind": "fleet", "ok": False, "action": "ERROR",
                "error": f"unreadable: {e}"}
    was_tripped = bool(breaker.get("tripped"))
    breaker["escalation_unresolved"] = False
    _write_atomic(path, breaker)
    ks_path = _kill_switch_path(arm)
    try:
        if ks_path.exists():
            ks_path.unlink()
    except OSError:
        pass
    _log_halt(f"RESUME fleet arm={arm} by={by} tripped_left_as_is={was_tripped}")
    return {"arm": arm, "kind": "fleet", "ok": True, "action": "ESCALATION_CLEARED",
            "tripped_still": was_tripped}


# ---------------------------------------------------------------------------------
# FLATTEN -- fail-closed on an unverified broker read (task's explicit requirement).
# ---------------------------------------------------------------------------------

def flatten_arm(arm: str, *, by: str) -> dict:
    """Read positions via the CHECKED broker read; only ever submits a market-sell on a
    CONFIRMED-OK read with confirmed-open positions. `live=True` is the flag that
    actually submits orders to the (paper) broker -- fleet_broker.close_all_spy_options's
    `live` kwarg; `live=False` only returns the would-close list, no order hits the wire.
    """
    try:
        creds_all = fleet_broker.load_creds()
    except Exception as e:  # noqa: BLE001 -- creds must never crash the responder
        _log_halt(f"FLATTEN arm={arm} by={by} ABORT_NO_CREDS err={e}")
        return {"arm": arm, "ok": False, "action": "ABORT_NO_CREDS", "error": str(e)}
    creds = creds_all.get(arm)
    if not creds:
        _log_halt(f"FLATTEN arm={arm} by={by} ABORT_NO_CREDS -- no creds entry for {arm}")
        return {"arm": arm, "ok": False, "action": "ABORT_NO_CREDS",
                "error": f"no creds entry for {arm}"}

    before, ok = fleet_broker.open_spy_option_positions_checked(creds)
    if not ok:
        _log_halt(f"FLATTEN arm={arm} by={by} ABORTED -- broker read failed")
        return {"arm": arm, "ok": False, "action": "ABORT_READ_FAILED",
                "message": "broker read failed -- NOT flattening, check the app"}
    before_syms = [p.get("symbol") for p in before]
    if not before_syms:
        _log_halt(f"FLATTEN arm={arm} by={by} NOOP -- already flat")
        return {"arm": arm, "ok": True, "action": "NOOP_ALREADY_FLAT",
                "before": [], "after": []}

    result = fleet_broker.close_all_spy_options(
        creds, live=True, arm=arm,
        reason=f"J_HALT_DISCORD_FLATTEN by={by} at {_et_ts()}",
    )
    after, ok_after = fleet_broker.open_spy_option_positions_checked(creds)
    after_syms = [p.get("symbol") for p in after] if ok_after else None
    _log_halt(
        f"FLATTEN arm={arm} by={by} live=True before={before_syms} "
        f"closed={result.get('closed')} errors={result.get('errors')} "
        f"after={after_syms if ok_after else 'READ_FAILED_POST_FLATTEN'}"
    )
    return {"arm": arm, "ok": True, "action": "FLATTENED", "live_flag_used": True,
            "before": before_syms, "closed": result.get("closed"),
            "errors": result.get("errors"), "after": after_syms,
            "after_read_ok": ok_after}


# ---------------------------------------------------------------------------------
# Allowlist + top-level dispatch -- the function discord-responder.py calls.
# ---------------------------------------------------------------------------------

def _load_allowlist() -> set[str]:
    """Authors allowed to issue HALT/RESUME. Today this is exactly J's Discord user_id
    from .discord-config.json -- the SAME identity discord-responder.py's main() already
    filters the inbox to (any message whose author_id != user_id is dropped before this
    module ever sees it). This is defense-in-depth: if halt_command is ever called from a
    path that does NOT pre-filter (a future multi-operator inbox, direct CLI invocation),
    an unrecognized author is refused HERE too, rather than assumed safe by omission."""
    if not CFG_PATH.exists():
        return set()
    try:
        uid = json.loads(CFG_PATH.read_text(encoding="utf-8-sig")).get("user_id", "")
    except Exception:
        return set()
    return {uid} if uid else set()


def _resolve_targets(target: str) -> list[str] | None:
    active = _active_spy_arms()
    if target == "ALL":
        return active
    return [target] if target in active else None


def _execute(cmd: dict, *, by: str) -> str:
    targets = _resolve_targets(cmd["target"])
    if targets is None:
        active = _active_spy_arms()
        return (f"Unknown arm '{cmd['target']}'. Active arms: {', '.join(active)} (or ALL).")

    lines: list[str] = []
    for arm in targets:
        if cmd["verb"] == "HALT":
            reason = f"J_HALT_DISCORD {_et_ts()}"
            if is_core_arm(arm):
                res = halt_core_arm(arm, reason=reason, by=by)
                if res["ok"]:
                    lines.append(
                        f"{arm}: HALTED. Core arm -- heartbeat_core's entry gate reads "
                        f"this breaker every tick, so this is enforced within the next "
                        f"heartbeat tick (<=1 min during RTH)."
                    )
                else:
                    lines.append(f"{arm}: HALT FAILED -- {res.get('error')}")
            else:
                res = halt_fleet_arm(arm, reason=reason, by=by)
                if res["ok"]:
                    lines.append(
                        f"{arm}: HALTED. Fleet arm -- fleet_live.py reads "
                        f"automation/state/fleet/{arm}/circuit-breaker.json every "
                        f"Gamma_FleetExecutor tick (1 min), so entries are blocked within "
                        f"1 min. kill-switch-{arm}.json also written for audit parity "
                        f"(that file alone is NOT read by any live path)."
                    )
                else:
                    lines.append(f"{arm}: HALT FAILED -- {res.get('error')}")
            if cmd.get("flatten") and res.get("ok"):
                fres = flatten_arm(arm, by=by)
                action = fres.get("action")
                if action == "ABORT_READ_FAILED":
                    lines.append(f"{arm} FLATTEN: broker read failed -- NOT flattening, "
                                 f"check the app.")
                elif action == "ABORT_NO_CREDS":
                    lines.append(f"{arm} FLATTEN: no creds -- NOT flattening "
                                 f"({fres.get('error')}).")
                elif action == "NOOP_ALREADY_FLAT":
                    lines.append(f"{arm} FLATTEN: already flat, nothing to close.")
                elif action == "FLATTENED":
                    lines.append(
                        f"{arm} FLATTEN: before={fres['before']} "
                        f"closed={fres.get('closed')} errors={fres.get('errors')} "
                        f"after={fres.get('after')} (live=True order submitted)."
                    )
        else:  # RESUME
            if is_core_arm(arm):
                res = resume_core_arm(arm, by=by)
                note = ("tripped left AS-IS (rule 9: no mid-session doctrine change) -- "
                        "daily_loss_guard.rearm() clears tripped at the next premarket "
                        "since escalation_unresolved is now false.")
            else:
                res = resume_fleet_arm(arm, by=by)
                note = ("tripped left AS-IS. fleet_live.py's breaker has NO "
                        "escalation_unresolved check -- it auto-clears tripped on its own "
                        "the next time last_reset's date rolls to a new trading day, "
                        "REGARDLESS of this flag. To stay halted past today, HALT again "
                        "tomorrow.")
            if res.get("ok"):
                lines.append(f"{arm}: RESUME -- escalation_unresolved cleared. {note}")
            else:
                lines.append(f"{arm}: RESUME FAILED -- {res.get('error')}")

    _flag_live_watch(
        f"- [{_et_ts()}] PHONE HALT :: {cmd['verb']} {cmd['target']}"
        f"{' FLATTEN' if cmd.get('flatten') else ''} by={by} :: "
        f"{'; '.join(lines)[:400]} :: detail: automation/state/logs/"
        f"halt-{et_now().strftime('%Y-%m-%d')}.log"
    )
    return "\n".join(lines)


def handle_message(content: str, author_id: str, *,
                    allowlist: set[str] | None = None) -> str | None:
    """Entry point for discord-responder.py. Returns the ack/refusal TEXT to queue to the
    outbox if `content` is a HALT/RESUME command (recognized -- whether ALLOWED or
    REFUSED), or None if `content` is not a HALT/RESUME command at all, in which case the
    caller MUST fall through to its normal approve/revoke/Q&A pipeline unchanged."""
    cmd = parse_command(content)
    if cmd is None:
        return None
    allow = _load_allowlist() if allowlist is None else allowlist
    if not allow or author_id not in allow:
        _log_halt(
            f"REFUSED verb={cmd['verb']} target={cmd['target']} author={author_id} "
            f"-- not on the HALT/RESUME allowlist"
        )
        return (f"Refused: {cmd['verb']} {cmd['target']} -- author {author_id} is not on "
                f"the HALT/RESUME allowlist. Only J's Discord account can issue this.")
    return _execute(cmd, by=author_id)
