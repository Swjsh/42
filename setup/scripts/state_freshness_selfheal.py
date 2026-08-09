"""state_freshness_selfheal -- turns state_freshness_audit's RED verdicts into ACTION.

WHY THIS EXISTS (2026-07-31, generalizing a live incident)
------------------------------------------------------------
``state_freshness_audit.py`` (built 2026-07-30) DETECTS a stalled producer -- a
manifest-listed file gone stale-by-age or stale-by-session -- but only REPORTS it.
The RED just sits in ``engine-health.json`` until a human notices, which is the
exact same "nothing recovers it" shape as the incident that motivated building the
audit in the first place (``Gamma_LevelRefresh`` silently went dark ~20h, fixed only
by a manual repair at 18:57 ET the next day).

``Invoke-LevelRefreshSafe`` (``_shared.ps1``) closed that gap for ONE file
(``key-levels.json``) with a kill-tree+relaunch, wired into the 5-min
``Gamma_TvWatchdog`` cadence. This module generalizes the REMEDIATION half across
every manifest entry: on a RED whose ``task`` field names a single resolvable
Windows scheduled task, force-start that task NOW via ``Start-ScheduledTask``
instead of waiting for its own next scheduled trigger (which the LIVE 2026-07-31
finding shows can itself silently stop firing for days with zero Task Scheduler
error signal -- ``Gamma_TradeToday``/``Gamma_BrokerFills``/``Gamma_EmaSnapshot`` all
last ran 2026-07-29 despite ``Enabled=True``, ``State=Ready``, no crash, no hung
process, and a MANUAL ``Start-ScheduledTask`` call succeeding immediately).

SCOPE / SAFETY
--------------
- Read-mostly: the only mutation is ``Start-ScheduledTask`` against a task the
  fleet already runs on its own schedule -- this just runs it EARLY. Never touches
  params/heartbeat_core/filters/placement/exit code, never places an order.
- Cooldown-guarded per task (default 20 min, persisted in
  ``automation/state/state-freshness-selfheal-cooldown.json``) so a genuinely-broken
  producer (one that fails even when force-started) is not hammered every 5-min
  TvWatchdog tick.
- Ambiguous ``task`` fields (empty, ``manual``/``n/a``, or anything that does not
  resolve to exactly one ``Gamma_*`` identifier) are SKIPPED, never guessed --
  mirrors the audit's own "never invent evidence" contract.
- Fails OPEN at every boundary: a missing ``powershell`` binary, a permission
  error, a raised exception anywhere in the audit -- all caught and reported, never
  propagated. This is a monitoring+remediation helper; it must never be able to
  break its caller.
- Every self-heal attempt (success or failure) is appended to
  ``automation/state/state-freshness-selfheal-log.jsonl`` for the audit trail.

USAGE
-----
    python setup/scripts/state_freshness_selfheal.py            # human summary
    python setup/scripts/state_freshness_selfheal.py --json     # machine payload
    python setup/scripts/state_freshness_selfheal.py --dry-run  # detect only, never starts a task

Guard: backtest/tests/test_state_freshness_selfheal.py
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import state_freshness_audit as sfa  # noqa: E402

# CREATE_NO_WINDOW: this module shells out to powershell.exe on a schedule, which flashes
# a console on J's desktop without the flag (2026-08-09 popup sweep).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

COOLDOWN_PATH = REPO / "automation" / "state" / "state-freshness-selfheal-cooldown.json"
LOG_PATH = REPO / "automation" / "state" / "state-freshness-selfheal-log.jsonl"
DEFAULT_COOLDOWN_MIN = 20

_LEADING_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+")


def extract_task_name(task_field) -> Optional[str]:
    """Pull a single Windows scheduled task name out of a manifest ``task`` string
    like ``'Gamma_TradeToday (every 2 min, 09:30-16:00 ET wd)'``.

    Returns ``None`` (never a guess) for anything ambiguous or non-actionable:
    empty/missing, ``'manual'``/``'n/a'``/``'none'``, multiple names joined by
    ``'+'`` before the parenthetical, or a leading token that isn't a
    ``Gamma_``-prefixed identifier.
    """
    if not isinstance(task_field, str):
        return None
    s = task_field.strip()
    if not s or s.lower() in ("manual", "n/a", "none"):
        return None
    head = s.split("(", 1)[0]
    if "+" in head:  # multiple writers/tasks named before the paren -- ambiguous, skip
        return None
    m = _LEADING_IDENT_RE.match(s)
    if not m:
        return None
    name = m.group(0)
    if not name.startswith("Gamma_"):
        return None
    return name


def _load_cooldown() -> dict:
    try:
        return json.loads(COOLDOWN_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt cooldown state = no cooldown, fail open
        return {}


def _save_cooldown(d: dict) -> None:
    try:
        COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- best-effort persistence, never fatal
        pass


def _on_cooldown(task_name: str, cooldown: dict, now: datetime, cooldown_min: int) -> bool:
    last = cooldown.get(task_name)
    if not last:
        return False
    try:
        last_dt = datetime.strptime(str(last)[:19], "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return False
    return (now - last_dt) < timedelta(minutes=cooldown_min)


def start_task(task_name: str, dry_run: bool = False) -> dict:
    """Force-start a Windows scheduled task via ``Start-ScheduledTask``.

    Fails open: any error (missing binary, no permission, task not found, timeout)
    is caught and reported in the returned dict, never raised.
    """
    if dry_run:
        return {"started": False, "dry_run": True}
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-Command", f"Start-ScheduledTask -TaskName '{task_name}'"],
            capture_output=True, text=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        ok = proc.returncode == 0
        return {"started": ok, "returncode": proc.returncode,
                "stderr": (proc.stderr or "").strip()[:300]}
    except Exception as e:  # noqa: BLE001 -- self-heal must never raise
        return {"started": False, "error": f"{type(e).__name__}: {e}"}


def run(dry_run: bool = False, cooldown_min: int = DEFAULT_COOLDOWN_MIN,
        now: Optional[datetime] = None, starter=start_task) -> dict:
    """Audit + self-heal in one pass. NEVER raises -- any failure degrades to a
    reported ``UNKNOWN``/empty-actions result, matching ``state_freshness_audit``'s
    own fail-open contract."""
    try:
        rep = sfa.audit()
    except Exception as e:  # noqa: BLE001
        return {"verdict": "UNKNOWN", "reason": f"audit failed: {type(e).__name__}",
                "n_red": 0, "actions": []}

    now = now or datetime.now()
    cooldown = _load_cooldown()
    actions = []
    red_entries = [e for e in rep.get("entries", []) if e.get("status") == "RED"]

    for e in red_entries:
        task_name = extract_task_name(e.get("task"))
        entry_result = {
            "path": e.get("path"),
            "task_field": e.get("task"),
            "resolved_task": task_name,
            "reason": (e.get("reasons") or [None])[0],
        }
        if task_name is None:
            entry_result["outcome"] = "skipped_unresolvable_task"
            actions.append(entry_result)
            continue
        if _on_cooldown(task_name, cooldown, now, cooldown_min):
            entry_result["outcome"] = "skipped_cooldown"
            actions.append(entry_result)
            continue
        result = starter(task_name, dry_run=dry_run)
        entry_result["outcome"] = "start_attempted"
        entry_result.update(result)
        actions.append(entry_result)
        if not dry_run:
            cooldown[task_name] = now.strftime("%Y-%m-%dT%H:%M:%S")

    if actions and not dry_run:
        _save_cooldown(cooldown)

    out = {
        "verdict": rep.get("verdict"),
        "checked_at_et": rep.get("checked_at_et"),
        "n_red": len(red_entries),
        "actions": actions,
    }

    if actions:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now.strftime("%Y-%m-%dT%H:%M:%S"), **out}) + "\n")
        except Exception:  # noqa: BLE001 -- logging must never break the heal
            pass

    return out


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Self-heal state-freshness RED entries by force-starting their producer task.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cooldown-min", type=int, default=DEFAULT_COOLDOWN_MIN)
    args = ap.parse_args(argv)
    out = run(dry_run=args.dry_run, cooldown_min=args.cooldown_min)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"verdict={out.get('verdict')} n_red={out.get('n_red')} "
              f"actions={len(out.get('actions', []))}")
        for a in out.get("actions", []):
            print(f"  {a.get('path')}: {a.get('outcome')} -> {a.get('resolved_task')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
