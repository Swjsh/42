"""worker_registry.py - keep the org chart honest.

`automation/state/worker-registry.json` declares Gamma's master/worker topology:
who the master is, which workers exist, which repeated J-intent each one OWNS,
what deterministic gate verifies its output, and where that output reaches J.

A registry nobody validates is a comment. This script is the validation: it
cross-checks every declaration against the actual `.claude/agents/*.md`
frontmatter, `automation/state/SCHEDULED-TASKS.md`, and the paths on disk.
Drift is an ERROR, not a note.

Also enforces the delegation contract Anthropic documents for subagent prompts -
objective / output_format / tools_and_sources / boundaries - so a fan-out that
omits one cannot be written by accident. ("Without detailed task descriptions,
agents duplicate work, leave gaps, or fail to find necessary information.")

USAGE
  python setup/scripts/worker_registry.py --check              # validate, exit 1 on drift
  python setup/scripts/worker_registry.py --show               # human org chart
  python setup/scripts/worker_registry.py --intents            # J-intent ownership + delivery
  python setup/scripts/worker_registry.py --contract spec.json # validate a delegation spec
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "automation" / "state" / "worker-registry.json"
AGENT_DIR = REPO / ".claude" / "agents"
TASKS_MD = REPO / "automation" / "state" / "SCHEDULED-TASKS.md"


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _frontmatter(path: Path) -> dict:
    """Parse the leading --- block of an agent persona file (flat scalars only)."""
    out = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return out
    for line in m.group(1).splitlines():
        km = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line)
        if km:
            val = km.group(2).strip()
            val = re.sub(r"\s+#.*$", "", val).strip().strip('"')
            out[km.group(1)] = val
    return out


def check(reg: dict) -> list:
    errors = []

    def err(msg):
        errors.append(msg)

    tasks_text = TASKS_MD.read_text(encoding="utf-8", errors="replace") if TASKS_MD.exists() else ""
    if not tasks_text:
        err("SCHEDULED-TASKS.md unreadable — cannot validate scheduled_task claims")

    # ---- master -----------------------------------------------------------
    master = reg.get("master", {})
    for key in ("persona", "loop"):
        p = master.get(key)
        if not p or not (REPO / p).exists():
            err("master.%s missing on disk: %s" % (key, p))
    mfm = _frontmatter(REPO / master.get("persona", ""))
    if mfm and mfm.get("model") and mfm["model"] != master.get("model"):
        err("master model drift: registry=%s persona=%s" % (master.get("model"), mfm["model"]))

    caps = master.get("fanout_caps", {})
    for key in ("max_subagent_spawn_depth", "max_concurrent_subagents", "max_budget_usd_per_fire"):
        if not isinstance(caps.get(key), (int, float)):
            err("master.fanout_caps.%s must be numeric" % key)

    # ---- workers ----------------------------------------------------------
    names = set()
    for w in reg.get("workers", []):
        n = w.get("name", "<unnamed>")
        if n in names:
            err("duplicate worker name: %s" % n)
        names.add(n)

        persona = w.get("persona")
        if not persona or not (REPO / persona).exists():
            err("%s: persona missing on disk: %s" % (n, persona))
            continue
        fm = _frontmatter(REPO / persona)
        if fm.get("name") and fm["name"] != n:
            err("%s: persona declares name=%s" % (n, fm["name"]))
        if fm.get("model") and w.get("model") and fm["model"] != w["model"]:
            err("%s: model drift — registry=%s persona=%s" % (n, w["model"], fm["model"]))

        # The context-boundary rule is the whole justification for being a
        # separate agent rather than an inline prompt. Enforce it.
        if not (w.get("context_boundary") or "").strip():
            err("%s: no context_boundary — decompose by context, not by role" % n)
        if not (w.get("verified_by") or "").strip():
            err("%s: no verified_by gate — the master cannot bank an unverified claim" % n)
        if not (w.get("delivers_to") or "").strip():
            err("%s: no delivers_to surface — work that lands nowhere gets redone" % n)

        st = w.get("scheduled_task")
        if st and tasks_text and st not in tasks_text:
            err("%s: scheduled_task %s not found in SCHEDULED-TASKS.md" % (n, st))

    # ---- j-intents --------------------------------------------------------
    valid_delivery = {"PUSH", "PARTIAL", "PULL_ONLY", "NONE"}
    for key, spec in (reg.get("j_intents") or {}).items():
        if key.startswith("_"):
            continue
        owner = spec.get("owner")
        if owner not in names and owner != "UNOWNED":
            err("j_intent %s: owner %r is not a registered worker" % (key, owner))
        if spec.get("delivery_status") not in valid_delivery:
            err("j_intent %s: delivery_status %r not one of %s"
                % (key, spec.get("delivery_status"), sorted(valid_delivery)))
        for m in spec.get("machinery", []):
            if "/" in m and not m.endswith(" skill") and not (REPO / m).exists():
                if tasks_text and m in tasks_text:
                    continue        # a scheduled task named, not a path
                err("j_intent %s: machinery path missing: %s" % (key, m))

    # ---- worker <-> intent consistency ------------------------------------
    for w in reg.get("workers", []):
        ji = w.get("j_intent")
        if ji and ji not in (reg.get("j_intents") or {}):
            err("%s: claims j_intent %r which is not declared" % (w.get("name"), ji))

    return errors


def check_contract(spec: dict) -> list:
    """Validate one delegation spec against the required four-part contract."""
    reg = load()
    required = reg["delegation_contract"]["required_fields"]
    errs = [f"missing required field: {f}" for f in required
            if not str(spec.get(f, "")).strip()]
    if reg["delegation_contract"].get("model_pin_required") and not spec.get("model"):
        errs.append("missing model pin: every fan-out must name its model explicitly "
                    "(subagents cannot switch their own model)")
    return errs


def show(reg: dict) -> None:
    m = reg["master"]
    print("MASTER  %s (%s)  loop=%s" % (m["name"], m["model"], m["loop"]))
    caps = m["fanout_caps"]
    print("        caps: depth<=%s  concurrency<=%s  budget<=$%s/fire" % (
        caps["max_subagent_spawn_depth"], caps["max_concurrent_subagents"],
        caps["max_budget_usd_per_fire"]))
    print()
    print("%-17s %-8s %-7s %-22s %s" % ("WORKER", "TIER", "MODEL", "OWNS J-INTENT", "VERIFIED BY"))
    print("-" * 100)
    for w in reg["workers"]:
        print("%-17s %-8s %-7s %-22s %s" % (
            w["name"], w["tier"], w["model"], w.get("j_intent") or "-",
            (w.get("verified_by") or "")[:44]))


def intents(reg: dict) -> None:
    print("%-22s %-6s %-14s %-13s %s" % ("J-INTENT", "ASKED", "OWNER", "DELIVERY", "GAP"))
    print("-" * 110)
    rows = [(k, v) for k, v in reg["j_intents"].items() if not k.startswith("_")]
    rows.sort(key=lambda kv: -kv[1].get("asked", 0))
    for k, v in rows:
        print("%-22s %-6s %-14s %-13s %s" % (
            k, v.get("asked", "?"), v.get("owner"), v.get("delivery_status"),
            (v.get("gap") or "")[:52]))
    unowned = [k for k, v in rows if v.get("owner") == "UNOWNED"]
    pull = [k for k, v in rows if v.get("delivery_status") in ("PULL_ONLY", "NONE")]
    print()
    print("UNOWNED: %s" % (", ".join(unowned) or "none"))
    print("NOT PUSHED TO J: %d of %d — this is the binding constraint on autonomy."
          % (len(pull), len(rows)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate and display the Gamma worker registry.")
    ap.add_argument("--check", action="store_true", help="validate registry against reality")
    ap.add_argument("--show", action="store_true", help="print the org chart")
    ap.add_argument("--intents", action="store_true", help="print J-intent ownership")
    ap.add_argument("--contract", metavar="SPEC.json",
                    help="validate a delegation spec against the four-part contract")
    a = ap.parse_args()

    if not REGISTRY.exists():
        print("worker_registry: %s missing" % REGISTRY, file=sys.stderr)
        return 1
    reg = load()

    if a.contract:
        spec = json.loads(Path(a.contract).read_text(encoding="utf-8"))
        errs = check_contract(spec)
        for e in errs:
            print("CONTRACT ERROR: %s" % e)
        print("CONTRACT %s" % ("OK" if not errs else "INVALID"))
        return 0 if not errs else 1

    if a.show:
        show(reg)
    if a.intents:
        if a.show:
            print()
        intents(reg)
    if a.check or not (a.show or a.intents):
        errs = check(reg)
        for e in errs:
            print("DRIFT: %s" % e)
        print("worker-registry: %s (%d workers, %d j-intents, %d drift)" % (
            "GREEN" if not errs else "RED",
            len(reg["workers"]),
            len([k for k in reg["j_intents"] if not k.startswith("_")]),
            len(errs)))
        return 0 if not errs else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
