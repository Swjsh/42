"""dojo/scorecard.py -- end-of-session arm scoring for DOJO replay sessions.

session.py (frozen -- not edited by this build) calls exactly:

    scorecard.score_session(session_ledger: Path) -> dict

Reads the session's append-only ledger (automation/state/dojo/sessions/<id>.jsonl,
written by session.py's cmd_step/cmd_directive/cmd_close) AND the adjacent positions file
sim_executor.py maintains (<id>-positions.json), and produces a per-arm scorecard:
J-directed realized/unrealized P&L (always reconstructable -- sim_executor already
computed it), plus every DIVERGENCE POINT between what J directed and what the engine's
own per-step decisions (DojoDecision.would_place, logged verbatim on each `step` ledger
row) would have done.

PROSPECTIVE J-EDGE-CAPTURE (OP-16 measured forward, per DOJO-ARCHITECTURE-DECISION.md):
the full metric is `j_directed_pnl - engine_counterfactual_pnl` per divergence, summed.
This module reports the J-directed half honestly and marks engine_counterfactual "pending"
-- turning it into a dollar figure requires shadow-executing each step's would_place=True
engine decision through sim_executor too (a natural Phase-1c extension: arm a second,
parallel SHADOW position per such decision and walk it the same way). That is explicitly
OUT of Phase-1/1b scope per the architecture doc ("Sim P&L scoring (criteria 2) may finish
in 1b"); this module does NOT fabricate a number to fill the gap -- OP-33(a).

HARD FENCE: no alpaca/broker/place_order import anywhere in this module (guard-tested,
backtest/tests/test_dojo_no_broker.py). Read-only over the ledger/positions files it is
given, plus one write of its own scorecard JSON under the SAME directory as the ledger
(never resolves a path outside what the caller handed it) -- never a broker call, never a
git operation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

POSITIONS_SUFFIX = "-positions.json"
SCORECARD_SUFFIX = "-scorecard.json"


# =====================================================================================
# I/O helpers
# =====================================================================================
def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a corrupt line never kills the whole scorecard (C7)
    return rows


def _positions_path_for(session_ledger: Path) -> Path:
    return session_ledger.with_name(f"{session_ledger.stem}{POSITIONS_SUFFIX}")


def _read_positions(session_ledger: Path) -> dict[str, dict]:
    p = _positions_path_for(session_ledger)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw.get("positions", {}) or {}


def _now_et_iso() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).isoformat()
    except Exception:  # noqa: BLE001 -- timestamping the report must never be the failure mode
        return datetime.now().isoformat()


# =====================================================================================
# per-arm J-directed P&L (always reconstructable -- sim_executor already computed it)
# =====================================================================================
def _decision_row_field(row: dict, name: str, default: Any = None) -> Any:
    return row.get(name, default)


def _per_arm_summary(positions: dict[str, dict]) -> dict[str, dict]:
    per_arm: dict[str, dict] = {}
    for pos in positions.values():
        arm = pos.get("arm") or "?"
        a = per_arm.setdefault(arm, {
            "j_directed_realized_pnl": 0.0, "j_directed_unrealized_pnl": 0.0,
            "n_open": 0, "n_closed": 0, "n_no_fill": 0, "n_error": 0, "n_synthetic_fills": 0,
            "positions": [],
        })
        status = pos.get("status")
        a["j_directed_realized_pnl"] += float(pos.get("realized_pnl") or 0.0)
        if status == "OPEN":
            a["n_open"] += 1
            a["j_directed_unrealized_pnl"] += float(pos.get("unrealized_pnl") or 0.0)
        elif status == "CLOSED":
            a["n_closed"] += 1
        elif status == "NO_FILL":
            a["n_no_fill"] += 1
        elif status == "ERROR":
            a["n_error"] += 1
        if pos.get("is_synthetic"):
            a["n_synthetic_fills"] += 1
        a["positions"].append({
            "position_id": pos.get("position_id"), "directive_id": pos.get("directive_id"),
            "symbol": pos.get("symbol"), "side": pos.get("side"), "strike": pos.get("strike"),
            "qty": pos.get("qty"), "status": status,
            "entry_time_et": pos.get("entry_time_et"), "entry_premium": pos.get("entry_premium"),
            "price_source": pos.get("price_source"), "is_synthetic": pos.get("is_synthetic"),
            "exit_reason": pos.get("exit_reason"), "exit_time_et": pos.get("exit_time_et"),
            "realized_pnl": pos.get("realized_pnl"), "unrealized_pnl": pos.get("unrealized_pnl"),
            "legs": pos.get("legs"), "note": pos.get("note"),
        })
    for a in per_arm.values():
        a["j_directed_realized_pnl"] = round(a["j_directed_realized_pnl"], 2)
        a["j_directed_unrealized_pnl"] = round(a["j_directed_unrealized_pnl"], 2)
    return per_arm


# =====================================================================================
# divergence points -- verdict-level (would_place vs a J-directed fill), NEVER a
# fabricated dollar figure. Uses only fields the frozen DojoDecision contract guarantees
# (DOJO-ARCHITECTURE-DECISION.md engine_step.py section): arm, verdict, would_place.
# =====================================================================================
def _open_intervals(positions: dict[str, dict]) -> list[dict]:
    """One row per position with a real fill: (arm, entry_time_et, exit_time_et-or-open)."""
    out = []
    for pos in positions.values():
        if pos.get("status") not in ("OPEN", "CLOSED"):
            continue
        entry = pos.get("entry_time_et")
        if not entry:
            continue
        out.append({
            "arm": pos.get("arm"), "position_id": pos.get("position_id"),
            "entry_time_et": entry, "exit_time_et": pos.get("exit_time_et"),
        })
    return out


def _position_covers(interval: dict, bar_et: Optional[str]) -> bool:
    if not bar_et:
        return False
    try:
        entry = datetime.fromisoformat(interval["entry_time_et"])
        bar = datetime.fromisoformat(bar_et)
    except (ValueError, TypeError):
        return False
    if bar < entry:
        return False
    exit_ts = interval.get("exit_time_et")
    if exit_ts is None:
        return True  # still open at session end -- covers every bar from entry onward
    try:
        return bar <= datetime.fromisoformat(exit_ts)
    except (ValueError, TypeError):
        return True


def _find_divergences(step_rows: list[dict], positions: dict[str, dict]) -> list[dict]:
    intervals = _open_intervals(positions)
    divergences: list[dict] = []
    for row in step_rows:
        bar_et = row.get("bar_et")
        for dec in row.get("decisions") or []:
            arm = _decision_row_field(dec, "arm")
            if arm is None:
                continue
            would_place = bool(_decision_row_field(dec, "would_place", False))
            j_directed = any(iv["arm"] == arm and _position_covers(iv, bar_et) for iv in intervals)
            if would_place == j_directed:
                continue  # agreement -- not a divergence
            divergences.append({
                "bar_et": bar_et, "arm": arm,
                "engine_would_place": would_place,
                "engine_verdict": _decision_row_field(dec, "verdict"),
                "engine_side": _decision_row_field(dec, "side"),
                "engine_setup": _decision_row_field(dec, "setup"),
                "j_directed": j_directed,
                "note": ("engine wanted to enter and J did not direct a matching trade"
                         if would_place and not j_directed else
                         "J directed a trade the engine's own verdict this bar would not have placed"),
            })
    return divergences


# =====================================================================================
# PUBLIC CONTRACT
# =====================================================================================
def score_session(session_ledger: Path) -> dict:
    session_ledger = Path(session_ledger)
    session_id = session_ledger.stem
    sessions_dir = session_ledger.parent

    rows = _read_jsonl(session_ledger)
    positions = _read_positions(session_ledger)

    step_rows = [r for r in rows if r.get("event") == "step"]
    directive_rows = [r for r in rows if r.get("event") == "directive"]
    close_rows = [r for r in rows if r.get("event") == "session_close"]

    per_arm = _per_arm_summary(positions)
    divergences = _find_divergences(step_rows, positions)

    totals = {
        "j_directed_realized_pnl": round(sum(a["j_directed_realized_pnl"] for a in per_arm.values()), 2),
        "j_directed_unrealized_pnl": round(sum(a["j_directed_unrealized_pnl"] for a in per_arm.values()), 2),
        "n_open_positions": sum(a["n_open"] for a in per_arm.values()),
        "n_closed_positions": sum(a["n_closed"] for a in per_arm.values()),
        "n_no_fill_positions": sum(a["n_no_fill"] for a in per_arm.values()),
        "n_error_positions": sum(a["n_error"] for a in per_arm.values()),
        "n_synthetic_fills": sum(a["n_synthetic_fills"] for a in per_arm.values()),
    }

    summary = {
        "session_id": session_id,
        "generated_et": _now_et_iso(),
        "ledger_path": str(session_ledger),
        "positions_path": str(_positions_path_for(session_ledger)),
        "n_ledger_rows": len(rows),
        "n_steps": len(step_rows),
        "n_directives": len(directive_rows),
        "n_positions": len(positions),
        "session_closed": bool(close_rows),
        "per_arm": per_arm,
        "totals": totals,
        "engine_counterfactual": {
            "status": "pending",
            "note": (
                "Engine-actual/counterfactual dollar P&L requires shadow-executing each "
                "step's would_place=True engine decision through sim_executor too (arm a "
                "second, parallel SHADOW position and walk it identically) -- NOT done this "
                "pass, per DOJO-ARCHITECTURE-DECISION.md's own Phase 1 vs 1b scope split. "
                "Reporting J-directed P&L honestly; not fabricating an engine-side dollar "
                "figure (OP-33a)."
            ),
        },
        "divergence_points": divergences,
        "n_divergence_points": len(divergences),
        "j_edge_capture_note": (
            "PROSPECTIVE J-edge-capture (OP-16 measured forward): once engine_counterfactual "
            "is closed (Phase 1c), edge_capture = j_directed_pnl - engine_counterfactual_pnl "
            "per divergence, summed. This scorecard reports the J-directed half plus every "
            "non-fabricated (bar, arm, would_place vs j_directed) divergence point; it does "
            "not compute a final edge_capture number yet."
        ),
    }

    out_path = sessions_dir / f"{session_id}{SCORECARD_SUFFIX}"
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    summary["scorecard_path"] = str(out_path)
    return summary
