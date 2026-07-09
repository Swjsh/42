"""p5_shape_gate.py -- ground rule 10, HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.

The P5-HARD-GATE (governance fix for the T5 scar). No exit shape ships to any arm --
paper included -- unless it PASSES the P5 robustness rule (qpf==1.0 AND >=3 neighbors with
>=0.5 elite-rate) on the current grind, i.e. it appears in the current
`analysis/recommendations/mass-grind-phase5-summary.json` survivors, OR it carries an
explicit waiver in `automation/state/p5-shape-waivers.json`.

WHY: the live `ribbon_ride` shape (stop -20% / TP1 +150% / sell 80% / fixed) was shipped
06-25 even though it FAILED its own P5 gate that same night (the survivors at stop-20 are
TP+100%, never +150%). This module graduates "check P5 before shipping a shape" into code so
the scar cannot silently repeat.

Pure stdlib. `shape_p5_status()` is the reusable predicate the pytest guard
(test_p5_shape_gate.py) and the `--check` CLI both call.

Usage:
    python setup/scripts/p5_shape_gate.py            # report live-shape P5 status
    python setup/scripts/p5_shape_gate.py --check     # exit 1 if any live shape is neither survivor nor waived
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

REPO = Path(__file__).resolve().parents[2]
STRATEGIES_PY = REPO / "automation" / "state" / "fleet" / "strategies.py"
P5_SUMMARY = REPO / "analysis" / "recommendations" / "mass-grind-phase5-summary.json"
WAIVERS = REPO / "automation" / "state" / "p5-shape-waivers.json"

# Combo layout in the phase5 summary survivors:
#   [strike_label, strike_offset, block_LR, min_trig, stop_label, stop_val, tp1_level, tp1_qty, lock]
# The EXIT-shape-relevant fields (a shape's P5 identity) are the last four numeric/string cells.
_COMBO_STOP, _COMBO_TP1, _COMBO_QTY, _COMBO_LOCK = 5, 6, 7, 8
_TOL = 1e-6


class ShapeSig(NamedTuple):
    """The four fields that define an exit shape's P5 identity (strike/gate are separate axes)."""
    stop: float
    tp1: float
    qty: float
    lock: str


def shape_sig_from_strategy(exit_shape: Any) -> ShapeSig:
    """ShapeSig from a strategies.py ExitShape (or its .to_dict())."""
    d = exit_shape.to_dict() if hasattr(exit_shape, "to_dict") else dict(exit_shape)
    return ShapeSig(round(float(d["premium_stop_pct"]), 6), round(float(d["tp1_premium_pct"]), 6),
                    round(float(d["tp1_qty_fraction"]), 6), str(d["profit_lock_mode"]).lower())


def shape_sig_from_combo(combo: list) -> ShapeSig:
    """ShapeSig from a phase5 survivor combo row."""
    return ShapeSig(round(float(combo[_COMBO_STOP]), 6), round(float(combo[_COMBO_TP1]), 6),
                    round(float(combo[_COMBO_QTY]), 6), str(combo[_COMBO_LOCK]).lower())


def _sig_eq(a: ShapeSig, b: ShapeSig) -> bool:
    return (abs(a.stop - b.stop) < _TOL and abs(a.tp1 - b.tp1) < _TOL
            and abs(a.qty - b.qty) < _TOL and a.lock == b.lock)


def load_survivor_sigs(summary_path: Path = P5_SUMMARY) -> list[ShapeSig]:
    """The exit-shape signatures of the current P5 survivors. Reads the SAME persisted artifact
    ground rule 10 names (the summary's `top_survivors`). Fail-closed: unreadable -> [] (so every
    live shape is treated as un-survived and must be waived -- we never silently pass on a
    missing gate)."""
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    sigs = []
    for s in data.get("top_survivors", []):
        combo = s.get("combo")
        if isinstance(combo, list) and len(combo) > _COMBO_LOCK:
            sigs.append(shape_sig_from_combo(combo))
    return sigs


def load_waivers(waivers_path: Path = WAIVERS) -> list[dict]:
    try:
        data = json.loads(waivers_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    return data.get("waivers", [])


def waiver_sig(w: dict) -> ShapeSig:
    sh = w["shape"]
    return ShapeSig(round(float(sh["premium_stop_pct"]), 6), round(float(sh["tp1_premium_pct"]), 6),
                    round(float(sh["tp1_qty_fraction"]), 6), str(sh["profit_lock_mode"]).lower())


def shape_p5_status(sig: ShapeSig, survivors: list[ShapeSig], waivers: list[dict]) -> dict:
    """The reusable predicate. Returns {ok, reason, is_survivor, waiver}.

    ok is True iff the shape is a P5 survivor OR carries a waiver. A waiver with
    j_signed=false is PROVISIONAL: it still satisfies `ok` (so a pre-existing live shape
    doesn't hard-RED the suite) but is surfaced loudly for J to sign or replace."""
    is_survivor = any(_sig_eq(sig, s) for s in survivors)
    match = next((w for w in waivers if _sig_eq(sig, waiver_sig(w))), None)
    if is_survivor:
        return {"ok": True, "reason": "P5 survivor", "is_survivor": True, "waiver": None}
    if match is not None:
        signed = bool(match.get("j_signed"))
        status = match.get("status", "PROVISIONAL" if not signed else "SIGNED")
        return {"ok": True, "reason": f"waived ({status})", "is_survivor": False, "waiver": match}
    return {"ok": False, "reason": "NOT a P5 survivor and NO waiver -- shape must not ship",
            "is_survivor": False, "waiver": None}


def _load_live_strategies() -> list:
    spec = importlib.util.spec_from_file_location("_p5_strategies", STRATEGIES_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_p5_strategies"] = mod
    spec.loader.exec_module(mod)
    return list(mod.REGISTRY)


def audit_live_shapes() -> list[dict]:
    """Status of every live strategy shape. One row per strategy."""
    survivors = load_survivor_sigs()
    waivers = load_waivers()
    out = []
    for strat in _load_live_strategies():
        sig = shape_sig_from_strategy(strat.exit)
        st = shape_p5_status(sig, survivors, waivers)
        st["strategy"] = strat.name
        st["sig"] = sig._asdict()
        out.append(st)
    return out


def main() -> int:
    check = "--check" in sys.argv
    rows = audit_live_shapes()
    failed, provisional = [], []
    for r in rows:
        sig = r["sig"]
        tag = "SURVIVOR" if r["is_survivor"] else ("WAIVED" if r["ok"] else "**FAIL**")
        print(f"  {r['strategy']:20s} stop{sig['stop']:+.2f}/tp+{sig['tp1']:.2f}/"
              f"sell{sig['qty']:.3f}/{sig['lock']:8s} -> {tag} ({r['reason']})")
        if not r["ok"]:
            failed.append(r["strategy"])
        elif r["waiver"] is not None and not r["waiver"].get("j_signed"):
            provisional.append(r["strategy"])
    if provisional:
        print(f"[p5_shape_gate] PROVISIONAL waivers (unsigned -- J must sign or replace): "
              f"{', '.join(provisional)}", file=sys.stderr)
    if failed:
        print(f"[p5_shape_gate] RED: {len(failed)} live shape(s) neither P5-survivor nor waived: "
              f"{', '.join(failed)}", file=sys.stderr)
        return 1 if check else 0
    print(f"[p5_shape_gate] OK: all {len(rows)} live shapes are P5-survivor or waived.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
