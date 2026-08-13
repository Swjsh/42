"""Gate x ARM coverage matrix -- which named entry gate is armed on which of the five arms.

WHY THIS EXISTS (2026-08-13, the #1 finding of the 36-agent deep review):

    Five arms run five different entry-gate sets and NO INVENTORY EXISTED of which gate is armed
    where. That moved $942 on 2026-08-13 alone -- 29% of the day's gross -- in two opposite
    directions, neither intended:

      block_bull_1100_1200        armed on safe-2 ONLY. Fired 11:41 ET. The four arms lacking it
                                  took the signal: -$410, 53% of the day's losses.
      block_conf_lvl_rec_afternoon armed on bold-2 ONLY. Fired 14:36 ET. Blocked bold-2 out of
                                  the day's +$532 winning event. Its own provenance doc reads
                                  "KEPT but DEAD (0 impact in all contexts)". It was not dead.

    Running BOTH already-ratified gates across all five arms would have made the day $122 WORSE
    than what actually happened. So the deliverable is the INVENTORY, not a promotion -- picking
    the gate that landed on today's loser and ignoring the one that landed on today's winner is
    post-hoc gate selection.

WHAT THIS IS NOT. It does not decide anything, propose anything, or rank gates. It answers one
question that took seven analysts and 4.9M tokens to notice nobody could answer: *which gate is
armed on which arm, and when was it last retested?*

Read-only. Never writes params, never arms anything. Exit code always 0.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT = STATE / "gate-arm-matrix.json"

# The five arms and the params file each one resolves its gates from.
ARM_PARAMS = {
    "safe-2": "automation/state/params.json",
    "bold-2": "automation/state/aggressive/params.json",
    "safe-3": "automation/state/params.json",
    "risky-1": "automation/state/aggressive/params.json",
    "risky-3": "automation/state/aggressive/params.json",
}
ACCOUNTS = STATE / "fleet" / "accounts.json"
HEARTBEAT = REPO / "setup" / "scripts" / "heartbeat_core.py"


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def known_gate_keys() -> list[str]:
    """The gate names heartbeat_core itself enumerates -- the authority on what a 'gate' IS.
    Derived from the source, never a hand-kept list that would rot (C14)."""
    try:
        src = HEARTBEAT.read_text(encoding="utf-8")
    except OSError:
        return []
    # heartbeat_core keeps its gate ids in a literal tuple/set of quoted names
    names: set[str] = set()
    for m in re.finditer(r'"(block_[a-z0-9_]+|[a-z0-9_]*_gate)"', src):
        names.add(m.group(1))
    return sorted(names)


def arm_patches() -> dict[str, dict]:
    """Per-arm params_patch from accounts.json -- an arm can override its file's value."""
    d = _load(ACCOUNTS)
    arms = d.get("arms") or d.get("accounts") or []
    if isinstance(arms, dict):
        arms = list(arms.values())
    out: dict[str, dict] = {}
    for a in arms:
        if not isinstance(a, dict):
            continue
        aid = a.get("id") or a.get("name")
        if not aid:
            continue
        patch = dict(a.get("params_patch") or {})
        patch.update(a.get("gate_override") or {})
        out[str(aid)] = patch
    return out


def build() -> dict[str, Any]:
    gates = known_gate_keys()
    files = {f: _load(REPO / f) for f in set(ARM_PARAMS.values())}
    patches = arm_patches()
    rows = []
    for g in gates:
        row: dict[str, Any] = {"gate": g, "armed_on": [], "absent_on": [], "per_arm": {}}
        for arm, pf in ARM_PARAMS.items():
            base = files.get(pf, {})
            if g in patches.get(arm, {}):
                val, src = patches[arm][g], f"accounts.json:{arm}.params_patch"
            elif g in base:
                val, src = base[g], pf
            else:
                val, src = None, "ABSENT"
            row["per_arm"][arm] = {"value": val, "source": src}
            (row["armed_on"] if val is True else row["absent_on"]).append(arm)
        row["uniform"] = len(row["armed_on"]) in (0, len(ARM_PARAMS))
        rows.append(row)
    split = [r for r in rows if not r["uniform"]]
    return {
        "_doc": __doc__.strip().splitlines()[0],
        "why": ("2026-08-13: $942 moved by gates armed on some arms and not others, in two "
                "opposite directions. See analysis/deep-research/DEEP-REVIEW-2026-08-13-MULTIAGENT.md"),
        "arms": list(ARM_PARAMS),
        "n_gate_keys_found": len(gates),
        "n_split_coverage": len(split),
        "split_coverage": [
            {"gate": r["gate"], "armed_on": r["armed_on"], "absent_on": r["absent_on"],
             "per_arm": r["per_arm"]} for r in split
        ],
        "all_gates": rows,
        "SCOPE_WARNING": {
            "what_this_measures": (
                "PARAMS-FILE MEMBERSHIP ONLY: is the key present and true in the params file "
                "this arm resolves to (fleet_executor._base_params_for: bold*/risky* -> "
                "aggressive/params.json, everything else -> params.json), after its "
                "accounts.json params_patch."),
            "what_this_does_NOT_measure": (
                "whether the arm's CODE PATH actually evaluates that gate. The core path "
                "(heartbeat_core GATE_KEYS -> engine_cli) and the fleet path (fleet_executor) "
                "are different consumers, and membership in a params file does not prove "
                "consumption."),
            "measured_contradiction_2026_08_13": (
                "fleet_executor.py:789-790 asserts the shared-signal gates 'apply UNIFORMLY to "
                "every arm'. The ledgers disagree: at 11:41-11:43 ET safe-2 logged "
                "SKIP_BULL_1100_1200 and took nothing, while safe-3 ENTERED at 11:42:05 on the "
                "same 775.73 trigger -- and both resolve to params.json, where the gate is "
                "present. Either the comment is stale or the gate is not applied on the fleet "
                "path. This is the THIRD stale-guarantee comment found on 2026-08-13 (the "
                "others: build_shared_signal's 'an arm can only filter further, never enter "
                "when production held', and run_cmd_hidden's 'regardless of launcher "
                "mechanism').  UNRESOLVED -- do not act on this matrix as if it were a "
                "consumption map."),
            "to_resolve": (
                "instrument the actual evaluation: log the gate id on every SKIP verdict and "
                "diff per arm over a week. Until then this file answers 'is the key present', "
                "which is necessary but not sufficient."),
        },
    }


def render(rep: dict[str, Any]) -> str:
    out = [f"GATE x ARM MATRIX -- {rep['n_gate_keys_found']} gate keys, "
           f"{rep['n_split_coverage']} with SPLIT coverage across arms", ""]
    if not rep["split_coverage"]:
        out.append("  (no gate differs across arms -- coverage is uniform)")
    for r in rep["split_coverage"]:
        out.append(f"  {r['gate']}")
        out.append(f"     ARMED  : {', '.join(r['armed_on']) or '(none)'}")
        out.append(f"     ABSENT : {', '.join(r['absent_on']) or '(none)'}")
    return "\n".join(out)


def main() -> int:
    rep = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(render(rep))
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0  # read-only reporting instrument; never breaks a caller


if __name__ == "__main__":
    sys.exit(main())
