"""Pipeline wiring audit -- every live-path producer->consumer edge, verified empirically.

WHY (J directive 2026-08-14): "ensure each pipeline is reviewed for accuracy, and whatever
should be reading or receiving info from another pipeline is wired up properly." This week
produced five distinct wiring failures, each invisible until it cost money or nearly did:

    engine-health read a surface whose schema it trusted     -> false STALE -> healer double-fire
    conviction k read the WRONG account's settlement ledger  -> bold logged safe's counter
    build_shared_signal's docstring promised containment the code stopped providing 2026-06-25
    exit-coverage compared SYMBOLS while the exit manager was blind to half the CONTRACTS
    the monitor pipeline itself (leak detector) wedged silently for 88 hours

An edge is only "wired up properly" when THREE things hold, and this audit checks all three:
  FRESH    -- the producer's file is younger than its cadence allows (during RTH)
  FIELDS   -- the latest record actually carries the fields the consumer dereferences
  CONSUMED -- the consumer's source really reads this file (static check, comments stripped,
              so a docstring mention never counts as consumption -- the trap that produced
              three wrong audits on 2026-08-13)

Read-only. Writes automation/state/pipeline-wiring-audit.json + prints a table. Exit 0 always.
Scheduled ambition: fold into engine-health or a nightly fire; for now runnable on demand.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT = STATE / "pipeline-wiring-audit.json"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
    _MARKET_HOURS = None  # decided per-run below
except Exception:  # noqa: BLE001
    et_now = None


def _rth() -> bool:
    if et_now is None:
        return False
    now = et_now()
    return now.weekday() < 5 and "09:30" <= now.strftime("%H:%M") < "16:00"


def _age_min(p: Path) -> Optional[float]:
    try:
        return (time.time() - p.stat().st_mtime) / 60.0
    except OSError:
        return None


def _code(p: Path) -> str:
    """Source with comment lines stripped -- a docstring/comment mention is NOT consumption.
    (Docstrings survive this strip; the CONSUMED patterns below therefore anchor on call/open
    syntax around the filename, not the bare name.)"""
    try:
        return "\n".join(l for l in p.read_text(encoding="utf-8", errors="replace").splitlines()
                         if not l.strip().startswith("#"))
    except OSError:
        return ""


def _latest_jsonl_row(p: Path, account: Optional[str] = None) -> Optional[dict]:
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 262144))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for raw in reversed(tail):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if account is None or row.get("account") == account:
            return row
    return None


def _json_doc(p: Path) -> Optional[dict]:
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return d if isinstance(d, dict) else {"_list_len": len(d)}
    except (OSError, ValueError):
        return None


# ── edge table ───────────────────────────────────────────────────────────────────────────
# Each edge: producer file, freshness budget (min, RTH only unless always=True), required
# fields (dotted paths into the latest record), and consumers as (source file, regex that
# proves a READ of this file).

def _fields_present(doc: Any, paths: list[str]) -> list[str]:
    missing = []
    for dotted in paths:
        cur = doc
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                missing.append(dotted)
                break
    return missing


EDGES: list[dict[str, Any]] = [
    dict(name="sight_beacon -> heartbeat_core",
         file=STATE / "sight-beacon.json", budget_min=5, loader=_json_doc,
         fields=["spy"],
         consumers=[(REPO / "setup/scripts/heartbeat_core.py", r"sight-beacon|sight_beacon|sight_check")]),
    dict(name="heartbeat_core -> core-decisions.jsonl (safe)",
         file=STATE / "core-decisions.jsonl", budget_min=8,
         loader=lambda p: _latest_jsonl_row(p, "safe"),
         fields=["account", "ts_et", "action"],
         consumers=[(REPO / "setup/scripts/engine_health.py", r"core-decisions\.jsonl"),
                    (REPO / "automation/state/fleet/build_shared_signal.py", r"core-decisions\.jsonl")]),
    dict(name="heartbeat_core -> core-decisions.jsonl (bold)",
         file=STATE / "core-decisions.jsonl", budget_min=8,
         loader=lambda p: _latest_jsonl_row(p, "bold"),
         fields=["account", "ts_et", "action"],
         consumers=[(REPO / "setup/scripts/engine_health.py", r"core-decisions\.jsonl")]),
    dict(name="build_shared_signal -> fleet_executor",
         file=STATE / "fleet" / "shared-signal.json", budget_min=5, loader=_json_doc,
         fields=["production_action"],
         consumers=[(REPO / "automation/state/fleet/fleet_live.py", r"shared-signal\.json|shared_signal")]),
    dict(name="level_refresher -> key-levels.json -> heartbeat",
         file=STATE / "key-levels.json", budget_min=20, loader=_json_doc,
         fields=["levels"],
         consumers=[(REPO / "setup/scripts/heartbeat_core.py", r"key-levels\.json|key_levels")]),
    # ema-snapshot: AUDIT FINDING 2026-08-14 -- produced daily (compute_ema_snapshot.py),
    # freshness-MONITORED by engine_health, and CONSUMED BY NOTHING (repo-wide grep: only the
    # producer, the monitor, and this audit mention it). A surface that is monitored but
    # unread is C14's purest shape -- the monitor guarantees a file nobody uses is fresh.
    # Declared as a gap rather than silently green; resolution (find its intended consumer or
    # retire producer+monitor together) queued for J -- deletion is not this audit's call.
    dict(name="ema_snapshot -> ORPHANED (monitored, consumed by nothing)",
         file=STATE / "ema-snapshot.json", budget_min=24 * 60, always=True, loader=_json_doc,
         fields=[],
         consumers=[]),
    dict(name="engine_health -> heal-engine (contract: same file, same staleness fields)",
         file=STATE / "engine-health.json", budget_min=10, loader=_json_doc,
         fields=["verdict", "checks"],
         consumers=[(REPO / "setup/scripts/heal-engine.ps1", r"core-decisions\.jsonl|Get-CoreStale")]),
    dict(name="exit_manager state (safe-2) <- exit_actuator",
         file=STATE / "fleet" / "safe-2" / "exit-state.json", budget_min=24 * 60, always=True,
         loader=_json_doc, fields=[],
         consumers=[(REPO / "automation/state/fleet/exit_actuator.py", r"exit-state\.json")]),
    dict(name="settlement ledger PER-ACCOUNT (safe) -> risk_gate + conviction",
         file=STATE / "settlement-ledger.json", budget_min=24 * 60, always=True,
         loader=_json_doc, fields=[],
         consumers=[(REPO / "setup/scripts/heartbeat_core.py", r"ledger_path\(STATE, account\)")]),
    dict(name="recency_check -> recency-confirmation.json -> fleet clamp",
         file=STATE / "recency-confirmation.json", budget_min=8 * 24 * 60, always=True,
         loader=_json_doc, fields=["headline"],
         consumers=[(REPO / "automation/state/fleet/fleet_executor.py", r"recency-confirmation\.json|RECENCY_CONFIRMATION_PATH")]),
    dict(name="keepawake daemon liveness -> engine_health (wired 2026-08-14)",
         file=STATE / "keepawake-heartbeat.json", budget_min=5, loader=_json_doc,
         fields=["last_assert_et", "ticks"],
         consumers=[(REPO / "setup/scripts/engine_health.py", r"keepawake-heartbeat\.json")]),
    dict(name="exit-coverage instrument -> firm_brief (wired 2026-08-14)",
         file=STATE / "exit-coverage.json", budget_min=24 * 60, always=True, loader=_json_doc,
         fields=["verdict", "rows"],
         consumers=[(REPO / "setup/scripts/firm_brief.py", r"exit-coverage\.json")]),
]


def audit() -> dict[str, Any]:
    rth = _rth()
    rows = []
    worst = "GREEN"
    for e in EDGES:
        p: Path = e["file"]
        row: dict[str, Any] = {"edge": e["name"], "file": str(p.relative_to(REPO))}
        age = _age_min(p)
        applies = e.get("always") or rth
        if age is None:
            row["fresh"] = "MISSING"
        elif not applies:
            row["fresh"] = f"n/a (closed) {age:.0f}m"
        elif age > e["budget_min"]:
            row["fresh"] = f"STALE {age:.0f}m > {e['budget_min']}m"
        else:
            row["fresh"] = f"ok {age:.1f}m"
        doc = e["loader"](p) if age is not None else None
        if doc is None and age is not None:
            row["fields"] = "UNPARSEABLE"
        elif doc is None:
            row["fields"] = "-"
        else:
            missing = _fields_present(doc, e["fields"])
            row["fields"] = f"MISSING {missing}" if missing else "ok"
        bad_consumers = []
        for src, pat in e["consumers"]:
            if not re.search(pat, _code(src)):
                bad_consumers.append(f"{src.name} !~ /{pat}/")
        if not e["consumers"]:
            row["consumed"] = "NO CONSUMER (declared gap)"
        elif bad_consumers:
            row["consumed"] = f"NOT CONSUMED: {bad_consumers}"
        else:
            row["consumed"] = "ok"
        red = ("STALE" in row["fresh"] or row["fresh"] == "MISSING"
               or row["fields"].startswith(("MISSING", "UNPARSEABLE"))
               or row["consumed"].startswith("NOT CONSUMED"))
        yellow = row["consumed"].startswith("NO CONSUMER")
        row["verdict"] = "RED" if red else ("YELLOW" if yellow else "GREEN")
        if row["verdict"] == "RED":
            worst = "RED"
        elif row["verdict"] == "YELLOW" and worst == "GREEN":
            worst = "YELLOW"
        rows.append(row)
    return {"_doc": __doc__.strip().splitlines()[0], "rth_at_run": rth,
            "verdict": worst, "edges": rows}


def main() -> int:
    rep = audit()
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"PIPELINE WIRING AUDIT: {rep['verdict']}  (rth={rep['rth_at_run']})\n")
    for r in rep["edges"]:
        print(f"  [{r['verdict']:<6}] {r['edge']}")
        print(f"           fresh={r['fresh']}  fields={r['fields']}  consumed={r['consumed']}")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
