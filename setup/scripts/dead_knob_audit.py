"""dead_knob_audit.py -- which params.json keys does NOTHING actually read?

WHY (2026-08-17). Two dead knobs surfaced in a single session, both on live exit/entry paths:

  * `tp1_premium_pct: 0.75` in aggressive/params.json. The engine fired TP1 at +100%, not
    +75% -- proven arithmetically on the day's winner (entry 0.72; best hit 1.40 at 13:24,
    which clears +75%=1.26 and did NOT fire; it fired at 13:26 when best hit 1.55, clearing
    +100%=1.44). The real value is hardcoded at strategies.py:131 (`tp1_premium_pct=1.0`).
  * `ribbon_min_spread_cents: 30`. The live gate reads the module constant
    RIBBON_SPREAD_MIN_CENTS (filters.py:40); the orchestrator's key is
    `ribbon_spread_min_cents` WITHOUT the `min_` prefix. Already known and written down in
    fleet_gate_sweetspot.py:505 -- and left in params.json anyway.

Both were found by hand, days or weeks after they started lying. This makes the question
answerable in one command.

WHAT "DEAD" MEANS HERE -- and what it does NOT. This is a STATIC REFERENCE audit: a key is
flagged when its literal name appears in no .py under the searched roots. That is a strong
signal but not proof of deadness, because a key can be reached dynamically
(`params[k] for k in ...`), and a key CAN be referenced yet still be overridden downstream --
which is exactly what `tp1_premium_pct` does (it IS referenced, and the strategy's hardcoded
value wins anyway). So this audit reports two DIFFERENT classes and never conflates them:

  UNREFERENCED  -- the name appears nowhere in code. Almost certainly dead.
  SHADOWED      -- the name IS referenced, but a hardcoded literal for the same concept
                   exists in a strategy/constant. Needs a human read; this is the class that
                   bit us today, and a pure grep would have called it healthy.

Pure static analysis. Reads nothing but source, writes one JSON, arms nothing. $0.

Run:  backtest/.venv/Scripts/python.exe setup/scripts/dead_knob_audit.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "recommendations" / "dead-knob-audit.json"

PARAM_FILES = [
    REPO / "automation" / "state" / "params.json",
    REPO / "automation" / "state" / "aggressive" / "params.json",
]
CODE_ROOTS = [REPO / "setup" / "scripts", REPO / "backtest" / "lib",
              REPO / "backtest" / "autoresearch", REPO / "automation" / "state" / "fleet",
              REPO / "automation" / "scripts", REPO / "crypto" / "lib"]

# Keys whose VALUE is documentation, not configuration.
DOC_PREFIXES = ("_", "note", "doc")

# Concepts that are known to be hardcoded in a strategy cell. A params key naming one of
# these is SHADOWED even if it is referenced somewhere.
SHADOWED_CONCEPTS = {
    "tp1_premium_pct": "automation/state/fleet/strategies.py ExitShape (ribbon_ride=1.0)",
    "tp1_qty_fraction": "automation/state/fleet/strategies.py ExitShape",
    "premium_stop_pct": "automation/state/fleet/strategies.py ExitShape",
    "profit_lock_mode": "automation/state/fleet/strategies.py ExitShape",
}


def source_blob() -> str:
    parts = []
    for root in CODE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if ".venv" in p.parts or "__pycache__" in p.parts:
                continue
            try:
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(parts)


def audit() -> dict:
    blob = source_blob()
    unreferenced, shadowed, live = [], [], []
    for pf in PARAM_FILES:
        if not pf.exists():
            continue
        try:
            doc = json.loads(pf.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        rel = str(pf.relative_to(REPO)).replace("\\", "/")
        for key, val in doc.items():
            k = str(key)
            if k.lower().startswith(DOC_PREFIXES):
                continue
            referenced = bool(re.search(r"[\"']" + re.escape(k) + r"[\"']", blob))
            row = {"file": rel, "key": k, "value": val if not isinstance(val, str)
                   else val[:60]}
            if not referenced:
                unreferenced.append(row)
            elif k in SHADOWED_CONCEPTS:
                shadowed.append({**row, "shadowed_by": SHADOWED_CONCEPTS[k]})
            else:
                live.append(row)
    return {"unreferenced": unreferenced, "shadowed": shadowed, "live_count": len(live)}


def main() -> int:
    res = audit()
    print(f"live (referenced) keys      : {res['live_count']}")
    print(f"SHADOWED by a hardcoded cell: {len(res['shadowed'])}")
    for r in res["shadowed"]:
        print(f"   {r['file']:<40} {r['key']:<28} = {r['value']}   <- {r['shadowed_by']}")
    print(f"UNREFERENCED anywhere in code: {len(res['unreferenced'])}")
    for r in res["unreferenced"]:
        print(f"   {r['file']:<40} {r['key']:<28} = {r['value']}")
    payload = {
        "_meta": {
            "audit": "DEAD-KNOB-AUDIT",
            "generated_for": "2026-08-17 -- two dead knobs found by hand in one session",
            "method": "static reference scan; see module docstring for what this does NOT prove",
            "classes": {
                "unreferenced": "name appears in no .py -- almost certainly dead",
                "shadowed": ("name IS referenced but a hardcoded literal for the same concept "
                             "wins downstream -- a pure grep calls these healthy. This is the "
                             "class that produced the +75%-vs-+100% TP1 lie."),
            },
            "propose_only": True,
        },
        **res,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
