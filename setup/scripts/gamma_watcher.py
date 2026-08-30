"""gamma_watcher.py -- the cockpit watches itself.

J, 2026-08-29: "i want a gamma watching the command center for efficiency and maybe even
driving itself. i need autonomy. figure it out."

WHAT THIS IS: the deterministic observe->decide->act loop that connects surfaces which
already exist but did not talk to each other. It is a $0 Python tick, not an LLM -- doctrine
(brain-sovereignty, no-LLM-in-loops) puts models at the EDGES: the watcher decides WHETHER
something needs attention; the card/autofire machinery decides who acts on it.

  OBSERVE   army payload (sessions, context), action cards, cost meter, what-changed,
            autofire ledger, companion liveness, pulse telemetry freshness
  DECIDE    a small, auditable rule table -- every rule names its evidence
  ACT       three tiers, in order of increasing consequence:
              note    -> watcher-report.json only (the cockpit renders it)
              card    -> inject a ranked card via the existing card surface
              fire    -> invoke autofire_cards.py, which owns ALL of its own guards
                         (dry-run default, RTH refusal, halt flag, quiet mode, caps)

WHAT IT NEVER DOES: place orders, edit config, spawn sessions directly, or bypass the
autofire runner's guards by calling the companion itself. The watcher OBSERVES and ROUTES;
consequence stays behind the surfaces that already carry guards. Self-driving here means
the loop no longer needs J to notice things -- not that anything bypasses the gates.

Cadence: designed for a 15-min scheduled tick (registered separately). Also runs bare for
an on-demand pulse. Every tick writes automation/state/watcher-report.json INCLUDING when
everything is fine -- "all quiet, checked at T" and silence are different claims, and only
one of them is evidence the watcher itself is alive.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_STATE = _REPO / "automation" / "state"
_REPORT = _STATE / "watcher-report.json"
_LEDGER = _STATE / "watcher-ledger.jsonl"
_PY = sys.executable

sys.path.insert(0, str(_REPO / "setup" / "scripts"))

# Findings the watcher can raise. Severity decides the tier: note < card. "fire" is never
# chosen by a rule directly -- it is the autofire runner's decision, invoked at most once
# per tick and only outside quiet/RTH, which the runner itself enforces again.
SEV_NOTE, SEV_CARD = "note", "card"


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _age_minutes(path: Path) -> float | None:
    try:
        return (time.time() - path.stat().st_mtime) / 60.0
    except OSError:
        return None


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# OBSERVE + DECIDE. Each check returns a list of findings:
#   {rule, severity, message, evidence}
# The rule table is the contract: a finding with no named evidence is a bug.
# --------------------------------------------------------------------------------------
def check_companion() -> list[dict]:
    """The fire path depends on :4317; a dead companion silently disables every card."""
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:4317/", timeout=5) as resp:
            if resp.status == 200:
                return []
            status = resp.status
    except Exception as exc:
        status = repr(exc)[:80]
    return [{
        "rule": "companion-down",
        "severity": SEV_CARD,
        "message": "Companion on :4317 is not answering -- card fires and the cockpit chat are dead until it restarts.",
        "evidence": f"GET http://127.0.0.1:4317/ -> {status}",
    }]


def check_context_pressure() -> list[dict]:
    """Sessions near the compact threshold. The army builder owns the numbers; the watcher
    only reads them -- and only when the builder says they are real."""
    findings: list[dict] = []
    try:
        from gamma_cockpit_army import build_army

        army = build_army()
    except Exception as exc:
        return [{
            "rule": "army-payload-broken",
            "severity": SEV_CARD,
            "message": "build_army() itself failed -- the Army view and every context number is stale.",
            "evidence": repr(exc)[:120],
        }]
    for s in army.get("sessions", []):
        pct = s.get("context_pct")
        if s.get("context_source") == "unknown" or not isinstance(pct, (int, float)):
            continue  # a fabricated alarm is worse than none
        if pct >= 90 and s.get("activity") in ("active", "idle"):
            findings.append({
                "rule": "context-critical",
                "severity": SEV_CARD,
                "message": f"Session '{(s.get('title') or s.get('name'))}' is at {pct:.0f}% of its "
                           f"compact threshold -- about to lose in-context state.",
                "evidence": f"{s.get('context_tokens')}/{s.get('context_limit')} via {s.get('context_source')}",
            })
    return findings


def check_pulse_freshness() -> list[dict]:
    """Pulse telemetry going quiet while sessions are active means the Army view is lying."""
    pulse = _STATE / "hooks" / "pulse.jsonl"
    age = _age_minutes(pulse)
    if age is None:
        return [{
            "rule": "pulse-missing",
            "severity": SEV_NOTE,
            "message": "pulse.jsonl does not exist -- no session has made a hooked tool call yet, or the hook layer is off.",
            "evidence": str(pulse),
        }]
    if age > 120:
        return [{
            "rule": "pulse-stale",
            "severity": SEV_NOTE,
            "message": f"No pulse row for {age:.0f} min. Fine if nothing is running; a lie if something is.",
            "evidence": f"mtime age {age:.1f}m",
        }]
    return []


def check_cost() -> list[dict]:
    """Reads the cost meter if the (parallel-built) meter has produced output."""
    meter = _load_json(_STATE / "cost-meter.json")
    if not meter:
        return []
    today = meter.get("today_usd")
    if isinstance(today, (int, float)) and today > 25:
        return [{
            "rule": "cost-spike",
            "severity": SEV_CARD,
            "message": f"Estimated spend today ${today:.2f} -- above the $25 watcher line.",
            "evidence": f"cost-meter.json today_usd={today} ({meter.get('provenance', 'estimate')})",
        }]
    return []


def check_autofire_health() -> list[dict]:
    """An autofire ledger whose last rows are all refusals for the SAME reason is a stuck
    runner pretending to be a careful one."""
    ledger = _STATE / "autofire-ledger.jsonl"
    try:
        rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()[-10:] if l.strip()]
    except Exception:
        return []
    if len(rows) >= 5:
        reasons = {r.get("reason") for r in rows if r.get("decision") == "refused"}
        if len(reasons) == 1 and reasons != {None}:
            reason = next(iter(reasons))
            if reason not in ("quiet-mode", "rth"):  # those are refusals working as designed
                return [{
                    "rule": "autofire-stuck",
                    "severity": SEV_NOTE,
                    "message": f"Last {len(rows)} autofire decisions all refused for the same reason: {reason}.",
                    "evidence": f"{ledger.name} tail",
                }]
    return []


def check_goal() -> list[dict]:
    """An active goal whose file has not moved in 24h is drift, not progress."""
    goal = _load_json(_STATE / "active-goal.json")
    if not goal or not goal.get("active"):
        return []
    goal_file = _REPO / str(goal.get("file") or "")
    age = _age_minutes(goal_file)
    if age is not None and age > 24 * 60:
        return [{
            "rule": "goal-drifting",
            "severity": SEV_CARD,
            "message": f"Goal {goal.get('id')} is active but its file has not been touched in {age/60:.0f}h.",
            "evidence": f"{goal_file.name} mtime age {age/60:.1f}h",
        }]
    return []


CHECKS = (
    check_companion,
    check_context_pressure,
    check_pulse_freshness,
    check_cost,
    check_autofire_health,
    check_goal,
)


# --------------------------------------------------------------------------------------
# ACT
# --------------------------------------------------------------------------------------
def act(findings: list[dict], drive: bool) -> dict:
    """Write the report; optionally hand the baton to the autofire runner.

    The watcher NEVER calls the companion itself: consequence stays behind
    autofire_cards.py, which re-checks RTH / halt / quiet / caps on its own. Passing
    --drive here therefore cannot bypass a single guard -- it only means the watcher
    tick is also the tick that gives the runner a chance to act.
    """
    cards = [f for f in findings if f["severity"] == SEV_CARD]
    report = {
        "checked_at": _now_iso(),
        "ok": not findings,
        "findings": findings,
        "card_count": len(cards),
        "drive": drive,
        "autofire": None,
    }

    if drive:
        runner = _REPO / "setup" / "scripts" / "autofire_cards.py"
        if runner.is_file():
            try:
                proc = subprocess.run(
                    [_PY, str(runner), "--live"],
                    capture_output=True, text=True, timeout=120, cwd=str(_REPO),
                )
                report["autofire"] = {
                    "exit": proc.returncode,
                    "tail": (proc.stdout or proc.stderr or "")[-400:],
                }
            except Exception as exc:
                report["autofire"] = {"exit": None, "tail": f"runner failed to start: {exc!r}"}
        else:
            report["autofire"] = {"exit": None, "tail": "autofire_cards.py not built yet"}

    try:
        _REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        with _LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": report["checked_at"], "ok": report["ok"],
                                 "rules": [f["rule"] for f in findings], "drive": drive}) + "\n")
        # ring-cap, same OP-22 contract as every other append-only producer here
        lines = _LEDGER.read_text(encoding="utf-8").splitlines()
        if len(lines) > 2400:
            _LEDGER.write_text("\n".join(lines[-2000:]) + "\n", encoding="utf-8")
    except OSError:
        pass
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="One watcher tick over the command center.")
    parser.add_argument("--drive", action="store_true",
                        help="after observing, also give autofire_cards.py one chance to act "
                             "(all of ITS guards still apply -- this bypasses nothing)")
    args = parser.parse_args()

    findings: list[dict] = []
    for check in CHECKS:
        try:
            findings.extend(check())
        except Exception as exc:  # a broken check must not kill the tick
            findings.append({
                "rule": f"check-crashed:{check.__name__}",
                "severity": SEV_NOTE,
                "message": f"watcher check {check.__name__} crashed -- fix the check.",
                "evidence": repr(exc)[:120],
            })

    report = act(findings, args.drive)
    if report["ok"]:
        print(f"all quiet -- 6 checks, 0 findings, {report['checked_at']}")
    else:
        for f in findings:
            print(f"  [{f['severity']}] {f['rule']}: {f['message']}")
        print(f"{len(findings)} finding(s) -> watcher-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
