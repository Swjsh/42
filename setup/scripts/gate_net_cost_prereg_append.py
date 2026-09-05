"""gate_net_cost_prereg_append.py -- GOAL-GATE-NET-COST-2026-09-05 N4 (append step).

Appends an `evidence_2026_09_05_net_of_losers` block (append-only -- adds ONE new top-level
key, never edits any existing key) to the 3 named preregs, sourced from
`analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json` (N3's net table). Idempotent: re-running
overwrites only that one key with the same content, never touches the frozen prereg fields.

CLI: python setup/scripts/gate_net_cost_prereg_append.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REC = REPO / "analysis" / "recommendations"
TABLE_PATH = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.json"

CAVEATS = [
    "5-min OPRA resolution bias: the walk (setup/scripts/gate_net_cost_walk.py) prices most "
    "refused ticks off 5-min-cached OPRA bars (a 1-min hand-check subset is within 10% of "
    "real fills, see backtest/tests/test_gate_net_cost_walk_2026_09_05.py); exact stage "
    "timing/price for any single row can be off by up to one 5-min bar.",
    "50 of 355 refused rows are walk_error (fail-open, not fabricated): 36 have no usable "
    "side on the source decision row (side=None, a real data gap) and 14 have no cached OPRA "
    "contract near the target strike -- excluded from every $ figure below, not zero-filled.",
    "Winner/loser $ uses realized_if_taken_dollars (the walked exit price), NOT the "
    "peak_multiple >= 1.3x ceiling N1/right-tail work used -- a wave can peak above 1.3x and "
    "still reverse before the walked exit stage fires; n_waves_peak_ge_1p3x is reported "
    "alongside as the alternate/ceiling metric so the two are never conflated.",
    "Net figures are PROXY, not a ratifying replay: the same class of proxy caveat "
    "gate_expiry_check.py's own sole-blocker checks (filter-8/filter-10) carry -- this is a "
    "counterfactual walk through the arm's real exit shape, not a full gate-stack re-simulation.",
]


def _gate_row(table: dict, gate: str) -> dict | None:
    for g in table["gate_rows_deduped_to_waves"]:
        if g["gate"] == gate:
            return g
    return None


def _arm_row(table: dict, gate: str, arm: str) -> dict | None:
    for r in table["gate_arm_rows"]:
        if r["gate"] == gate and r["arm"] == arm:
            return r
    return None


def _block(**kwargs) -> dict:
    return {
        "_doc": "Appended by setup/scripts/gate_net_cost_prereg_append.py, GOAL-GATE-NET-COST-2026-09-05 N4. Append-only -- does not alter any field above this key.",
        "source": "analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json (N3 net table, walked from analysis/gate-net-cost/walk-2026-09-05.json N2, 305/355 walk_ok)",
        "definition": "winner := realized_if_taken_dollars > 0; loser := realized_if_taken_dollars <= 0; net := sum(realized_if_taken_dollars) over walk_ok rows == winners + losers.",
        "caveats": CAVEATS,
        **kwargs,
    }


def append_mechanism1(table: dict) -> dict:
    mt = _gate_row(table, "min_triggers")
    rcs = _gate_row(table, "require_confluence_or_sequence")
    combined_full = round(mt["full_window"]["net_dollars"] + rcs["full_window"]["net_dollars"], 2)
    combined_frozen = round(mt["frozen_window"]["net_dollars"] + rcs["frozen_window"]["net_dollars"], 2)
    return _block(
        gates_covered=["min_triggers (risky-1, safe-3)", "require_confluence_or_sequence (risky-1, safe-3)"],
        full_window={
            "min_triggers": mt["full_window"], "require_confluence_or_sequence": rcs["full_window"],
            "combined_net_dollars": combined_full,
            "combined_verdict": "EARNING" if combined_full < 0 else ("COSTING" if combined_full > 0 else "EARNING"),
        },
        frozen_window={
            "min_triggers": mt["frozen_window"], "require_confluence_or_sequence": rcs["frozen_window"],
            "combined_net_dollars": combined_frozen,
            "combined_verdict": "UNDERPOWERED (both gates n<10 waves in the frozen window)",
        },
        reading=(
            "The $4,354.92 refused-WINNER ceiling this prereg was filed on (safe-3+risky-1 "
            "gate_override slice) nets to " + f"${combined_full:,.2f}" + " full-window once the "
            "gate's refused LOSERS are walked through the real exit shape: min_triggers alone "
            "is COSTING (+$516, 20 waves) but require_confluence_or_sequence alone is EARNING "
            "(-$1,806, 13 waves) -- the two knobs this prereg proposes loosening TOGETHER point "
            "in opposite directions net-of-losers. The frozen window (08-31 onward) is "
            "UNDERPOWERED for both (n=3, n=2 waves) -- too few waves since the config freeze to "
            "read a verdict; the full-window combined net is negative (EARNING/saved money) "
            "mainly because require_confluence_or_sequence's losers outweigh its winners. This "
            "does not kill the prereg (kill/extend criteria are unchanged, frozen text above) -- "
            "it is new evidence for the 2026-10-30 checkpoint read, appended per this goal's "
            "DONE-WHEN."
        ),
    )


def append_mechanism6(table: dict) -> dict:
    row = _arm_row(table, "SKIP_MIN_PREMIUM_FLOOR", "bold-2")
    return _block(
        gate_covered="SKIP_MIN_PREMIUM_FLOOR (bold-2 only, per this prereg's own arm scope)",
        full_window=row["full_window"],
        frozen_window=row["frozen_window"],
        reading=(
            f"The $1,664.00 refused-WINNER ceiling this prereg was filed on nets to "
            f"${row['full_window']['net_dollars']:,.2f} full-window (14 waves, verdict "
            f"{row['verdict_full_window']}) once bold-2's refused SKIP_MIN_PREMIUM_FLOOR "
            "losers are walked through the real exit shape -- the gate is EARNING its keep "
            "net-of-losers over the full window: 12 of 14 refused waves would have lost money, "
            "dominated by 2 large premium_stop losses ($-220, $-200). The frozen window (6 "
            f"waves, all losers, net ${row['frozen_window']['net_dollars']:,.2f}) is "
            "UNDERPOWERED by the n>=10 floor but every single frozen-window wave is a loser -- "
            "directionally consistent with, not contradicting, the full-window EARNING read. "
            "This is new evidence against loosening the floor, appended per this goal's "
            "DONE-WHEN; kill/extend criteria above are unchanged."
        ),
    )


def append_structure_veto_ab(table: dict) -> dict:
    row = _gate_row(table, "SKIP_STRUCTURE_VETO")
    return _block(
        gate_covered="SKIP_STRUCTURE_VETO (core, safe-2 only)",
        full_window=row["full_window"],
        frozen_window=row["frozen_window"],
        reading=(
            f"SKIP_STRUCTURE_VETO's refused-wave net is ${row['full_window']['net_dollars']:,.2f} "
            f"full-window (7 waves, verdict {row['verdict_full_window']} -- UNDERPOWERED by the "
            "n>=10 floor) and " + f"${row['frozen_window']['net_dollars']:,.2f}" + " frozen-window "
            "(3 waves, also UNDERPOWERED). Both windows read slightly net-negative (refusing the "
            "veto's blocked ticks would have cost slightly more in losers than it gave up in "
            "winners), consistent with this prereg's own frozen_hypothesis that the veto is a "
            "net-neutral-to-positive robustness gate rather than a forward alpha source -- but n "
            "is too small in both windows to move the kill_criterion's n>=20 forward-accrual "
            "bar on its own; Gamma_FleetGateLeakShadow (the standing instrument this prereg "
            "names) remains the authority for that n>=20 read. Appended per this goal's "
            "DONE-WHEN; decision/kill/extend criteria above are unchanged."
        ),
    )


def main() -> int:
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))

    targets = [
        (REC / "prereg-fleet-capture-mechanism1-gate-override-10-30-2026-09-05.json", append_mechanism1),
        (REC / "prereg-fleet-capture-mechanism6-sizing-floor-10-30-2026-09-05.json", append_mechanism6),
        (REC / "prereg-structure-veto-standing-ab-2026-09-05.json", append_structure_veto_ab),
    ]
    for path, builder in targets:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["evidence_2026_09_05_net_of_losers"] = builder(table)
        path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
        print(f"[prereg-append] appended evidence_2026_09_05_net_of_losers to {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
