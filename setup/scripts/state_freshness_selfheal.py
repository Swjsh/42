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

EFFECT VERIFICATION (2026-09-03, SELFHEAL-VERIFY-EFFECT-AUDIT)
----------------------------------------------------------------
Before this fix, ``start_task``'s ``ok = proc.returncode == 0`` was the ONLY signal of
success -- identical in shape to the pre-c941567c ``Invoke-TvLaunchSafe`` blind spot
(lesson ``tv-selfheal-silent-failure-2026-07-31.md``): a self-heal that reports success on
"the repair action was invoked without throwing" rather than "the repair actually worked".
``Start-ScheduledTask`` returns almost immediately while the real producer can take minutes
to run and write, so the effect can't be checked synchronously the way
``state_freshness_remediate.py`` (direct in-process invocation) does. Instead, every
force-started task is recorded in ``automation/state/state-freshness-selfheal-pending.json``
with its target path and start time; the NEXT ``run()`` call (this module fires every 5 min
via ``Gamma_TvWatchdog``, so the next check is <=5 min later) re-audits that path first --
if it left RED, ``effect_verified: true`` and it drops off the pending list; if it is still
RED after ``EFFECT_VERIFY_GRACE_MIN`` minutes, ``effect_verified: false`` is logged loudly
(``run-tv-watchdog.ps1`` greps for ``"effect_verified": false`` in this module's ``--json``
output) and the entry is dropped (the normal cooldown/RED-entry loop will naturally retry it
on the next pass if it's still RED).

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
PENDING_PATH = REPO / "automation" / "state" / "state-freshness-selfheal-pending.json"
LOG_PATH = REPO / "automation" / "state" / "state-freshness-selfheal-log.jsonl"
DEFAULT_COOLDOWN_MIN = 20
# How long to wait after a force-start before judging the target file still-RED as a
# genuine self-heal failure rather than "the producer just hasn't finished yet". This
# module runs on a 5-min cadence (Gamma_TvWatchdog), so 10 min = 2 ticks of slack.
EFFECT_VERIFY_GRACE_MIN = 10

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


def _load_pending() -> dict:
    try:
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt pending state = nothing to verify, fail open
        return {}


def _save_pending(d: dict) -> None:
    try:
        PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        PENDING_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- best-effort persistence, never fatal
        pass


def _verify_pending(pending: dict, entries_by_path: dict, now: datetime,
                     grace_min: int) -> tuple[dict, list]:
    """Re-check every previously force-started task's target path against the CURRENT
    audit. A path that left RED = the self-heal's effect is confirmed. A path still RED
    after ``grace_min`` minutes = the force-start ran (returncode 0) but did NOT actually
    heal the producer -- exactly the C7 shape this audit item was filed to close. Entries
    still within their grace window are kept for the next pass. Never raises."""
    remaining: dict = {}
    results: list = []
    for path, info in pending.items():
        try:
            started_dt = datetime.strptime(str(info.get("started_at"))[:19], "%Y-%m-%dT%H:%M:%S")
        except (TypeError, ValueError):
            continue  # corrupt pending entry -- drop it rather than get stuck forever
        age_min = (now - started_dt).total_seconds() / 60.0
        cur = entries_by_path.get(path)
        cur_status = cur.get("status") if cur else None
        if cur_status is not None and cur_status != "RED":
            results.append({"path": path, "task": info.get("task"),
                             "effect_verified": True, "age_min": round(age_min, 1)})
            continue
        if age_min >= grace_min:
            results.append({"path": path, "task": info.get("task"),
                             "effect_verified": False, "age_min": round(age_min, 1),
                             "reason": "still_red_after_grace"})
            continue
        remaining[path] = info  # still within grace window -- keep watching
    return remaining, results


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
        now: Optional[datetime] = None, starter=start_task,
        grace_min: int = EFFECT_VERIFY_GRACE_MIN) -> dict:
    """Audit + self-heal in one pass. NEVER raises -- any failure degrades to a
    reported ``UNKNOWN``/empty-actions result, matching ``state_freshness_audit``'s
    own fail-open contract."""
    try:
        rep = sfa.audit()
    except Exception as e:  # noqa: BLE001
        return {"verdict": "UNKNOWN", "reason": f"audit failed: {type(e).__name__}",
                "n_red": 0, "actions": [], "verify_results": []}

    now = now or datetime.now()
    cooldown = _load_cooldown()
    entries_by_path = {e.get("path"): e for e in rep.get("entries", [])}

    # --- effect verification: judge outcomes of self-heals started on a PRIOR pass -----
    pending = _load_pending()
    verify_results: list = []
    if not dry_run:
        pending, verify_results = _verify_pending(pending, entries_by_path, now, grace_min)
        if verify_results:
            _save_pending(pending)

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
            if result.get("started"):
                # Register for effect verification on a LATER pass -- Start-ScheduledTask
                # returns almost immediately, long before the producer has actually run and
                # written, so the effect cannot be judged in THIS pass (see module docstring).
                pending[e.get("path")] = {
                    "task": task_name, "started_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
                }

    if actions and not dry_run:
        _save_cooldown(cooldown)
    if not dry_run:
        _save_pending(pending)

    out = {
        "verdict": rep.get("verdict"),
        "checked_at_et": rep.get("checked_at_et"),
        "n_red": len(red_entries),
        "actions": actions,
        "verify_results": verify_results,
    }

    if actions or verify_results:
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
              f"actions={len(out.get('actions', []))} "
              f"verify_results={len(out.get('verify_results', []))}")
        for a in out.get("actions", []):
            print(f"  {a.get('path')}: {a.get('outcome')} -> {a.get('resolved_task')}")
        for v in out.get("verify_results", []):
            print(f"  VERIFY {v.get('path')}: effect_verified={v.get('effect_verified')} "
                  f"task={v.get('task')} age_min={v.get('age_min')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
