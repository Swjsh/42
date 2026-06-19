#!/usr/bin/env python3
"""engine_shadow — read-only Phase-3 ENGINE shadow harness (wired-not-enabled).

Spec: ``docs/SHARED-DECISION-LIBRARY-MIGRATION.md`` §3 "Phase 3 — Shadow-mode the
engine verdict alongside the live prose for N days", and ``docs/ENGINE-SHADOW-HARNESS.md``.

WHAT THIS IS
------------
The decision-library (``engine_cli.decide_payload`` = ``score_bar`` + ``evaluate_gates``)
is built and byte-identical to the orchestrator in backtests (Phases 1-2). Phase 3
is the ONLY validation a synthetic reproducer cannot give: does ``decide()`` agree
with the live PROSE heartbeat *on the exact inputs the LLM produces live*? This
harness is the read-only sidecar that answers it:

  * INPUT  — one tick payload (the ``engine_cli`` ``bar_ctx`` the heartbeat computed
             this tick) + the heartbeat's own PROSE action for the same tick.
  * RUN    — calls ``decide_payload`` (same code the orchestrator/parity-tests use).
  * LOG    — appends ONE paired prod-vs-engine row to
             ``automation/state/engine-shadow-decisions.jsonl`` (a SEPARATE file from
             the Nemotron model shadow's ``shadow-model-decisions.jsonl`` — they are
             different shadows and must not collide).

It is DISTINCT from the existing Nemotron model shadow (``shadow_model_eval.py``):
that one tests a candidate MODEL/params; THIS one tests whether the decision-library
CODE agrees with the prose, to earn the Phase-4 right to let code drive.

THE TWO IRON GUARANTEES (why this is safe to wire into the live heartbeat)
-------------------------------------------------------------------------
1. READ-ONLY: it places no orders, mutates no params/position/loop state. It only
   appends to its own shadow ledger + (optionally) writes a scorecard. The engine
   verdict NEVER drives a real order in this phase.
2. FAIL-OPEN: any error (bad payload, engine exception, unwritable ledger) is
   swallowed into a logged ``SHADOW_ERROR`` row and exit 0 — the shadow can NEVER
   break, slow, or block the live heartbeat tick (the OP-25 / OP-32 invariant: no
   automated process may degrade the live path or lock out the human).

This module REUSES ``decide_payload`` in-process (rather than shelling out to the
``engine_cli`` stdin/stdout boundary) — it is the exact same function ``engine_cli``'s
``main`` calls, so the verdict is identical, while avoiding subprocess/interpreter
fragility on the live Windows path. Requires the backtest venv (pandas) — the
heartbeat invokes it with ``backtest/.venv/Scripts/pythonw.exe`` (venv lesson).

Usage (the heartbeat's Phase-3 shadow block, propose-only — see the harness doc):
  <venv-py> automation/scripts/engine_shadow.py --payload <tick_payload.json> \
            --prose-action ENTER_BEAR --date 2026-06-23 --time 10:05
  <venv-py> automation/scripts/engine_shadow.py --scorecard --date 2026-06-23

Exit code is ALWAYS 0 on the per-tick path (fail-open). --scorecard returns 0/1.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

_REPO = Path(__file__).resolve().parents[2]
# Put backtest/ + repo root on path so decide_payload resolves the SAME lib.* the
# orchestrator imports (identical resolution to engine_cli / pre_order_gate).
for _p in (str(_REPO / "backtest"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SHADOW_LEDGER = _REPO / "automation" / "state" / "engine-shadow-decisions.jsonl"
SCORECARD_DIR = _REPO / "analysis" / "engine-shadow"
TODAY_BIAS = _REPO / "automation" / "state" / "today-bias.json"


# --------------------------------------------------------------------------- #
# Agreement classification — the metric the Phase-4 gate reads.
# --------------------------------------------------------------------------- #

# Prose actions that mean "the heartbeat ENTERED a trade this tick". The heartbeat
# logs many non-entry actions (HOLD/PAUSED/MANAGE/WAIT/...); only an actual entry
# counts as an ENTER for the agreement gate (entries are where disagreement is
# expensive — 100%-on-entries is the strict half of the gate).
_PROSE_ENTER_PREFIXES = ("ENTER", "ENTERED", "BUY", "OPEN", "LONG", "SHORT")
_ENGINE_ENTER = {"ENTER_BEAR", "ENTER_BULL"}


def prose_entered(prose_action: Optional[str]) -> bool:
    """True iff the heartbeat's prose action represents an actual entry this tick."""
    if not prose_action:
        return False
    a = str(prose_action).strip().upper()
    return any(a.startswith(p) for p in _PROSE_ENTER_PREFIXES)


def engine_entered(verdict: Optional[str]) -> bool:
    """True iff the engine verdict is an entry."""
    return str(verdict or "").strip().upper() in _ENGINE_ENTER


def prose_side(prose_action: Optional[str]) -> Optional[str]:
    """Best-effort P/C side from a prose entry action (for side-agreement)."""
    if not prose_entered(prose_action):
        return None
    a = str(prose_action).strip().upper()
    if "BEAR" in a or "PUT" in a or a.endswith("_P") or "SHORT" in a:
        return "P"
    if "BULL" in a or "CALL" in a or a.endswith("_C") or "LONG" in a:
        return "C"
    return None


def classify_agreement(prose_action: Optional[str], verdict: Mapping[str, Any]) -> dict:
    """Bucket one tick into the agreement taxonomy the scorecard aggregates.

    Buckets (mirrors the migration spec's "≥99% agree, 100% on entries" gate):
      * AGREE_ENTER       — both entered, same side
      * AGREE_ENTER_XSIDE — both entered, OPPOSITE side (counts as a disagreement
                            for the entry gate; logged distinctly for forensics)
      * AGREE_NOENTRY     — neither entered (HOLD/SKIP on both)
      * DISAGREE_PROSE_ONLY  — prose entered, engine did not (engine more conservative)
      * DISAGREE_ENGINE_ONLY — engine entered, prose did not (engine more aggressive)
    """
    p_in = prose_entered(prose_action)
    e_in = engine_entered(verdict.get("verdict"))
    if p_in and e_in:
        ps, es = prose_side(prose_action), verdict.get("side")
        if ps is not None and es is not None and ps != es:
            return {"bucket": "AGREE_ENTER_XSIDE", "agree": False, "entry_tick": True}
        return {"bucket": "AGREE_ENTER", "agree": True, "entry_tick": True}
    if not p_in and not e_in:
        return {"bucket": "AGREE_NOENTRY", "agree": True, "entry_tick": False}
    if p_in and not e_in:
        return {"bucket": "DISAGREE_PROSE_ONLY", "agree": False, "entry_tick": True}
    return {"bucket": "DISAGREE_ENGINE_ONLY", "agree": False, "entry_tick": True}


def build_shadow_row(
    *, date: str, time_et: str, prose_action: Optional[str], verdict: Mapping[str, Any]
) -> dict:
    """Assemble the paired prod-vs-engine row (one tick) for the shadow ledger."""
    cls = classify_agreement(prose_action, verdict)
    return {
        "date": date,
        "time_et": time_et,
        "prose_action": prose_action,
        "engine_verdict": verdict.get("verdict"),
        "engine_side": verdict.get("side"),
        "engine_setup": verdict.get("setup_name"),
        "engine_tier": verdict.get("quality_tier"),
        "engine_gate": (verdict.get("gate") or {}).get("gate_id") if verdict.get("gate") else None,
        "bear_score": verdict.get("bear_score"),
        "bull_score": verdict.get("bull_score"),
        "agree": cls["agree"],
        "bucket": cls["bucket"],
        "entry_tick": cls["entry_tick"],
        "engine_reason": verdict.get("reason"),
        "shadow": "engine",  # tag: distinguishes from any other shadow stream
    }


# --------------------------------------------------------------------------- #
# I/O — atomic append (never corrupts the ledger), fail-open everywhere.
# --------------------------------------------------------------------------- #


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    """Append one compact JSON line. Best-effort durable; raises only to caller's
    fail-open wrapper (the per-tick path swallows it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, separators=(",", ":"), default=str) + "\n"
    with io.open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def run_shadow_tick(
    payload: Mapping[str, Any],
    prose_action: Optional[str],
    *,
    date: str,
    time_et: str,
    out_path: Path = SHADOW_LEDGER,
) -> dict:
    """Run ONE shadow tick: decide -> classify -> append paired row. FAIL-OPEN.

    Returns the row written (or a SHADOW_ERROR row). Never raises — the live
    heartbeat calls this and must not break if anything here fails.
    """
    try:
        from lib.engine.engine_cli import decide_payload  # late import: needs pandas
        verdict = decide_payload(payload)
    except Exception as exc:  # fail-open: any engine/import failure -> logged, not raised
        verdict = {
            "verdict": "SHADOW_ERROR",
            "side": None,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    row = build_shadow_row(date=date, time_et=time_et, prose_action=prose_action, verdict=verdict)
    try:
        _append_jsonl(out_path, row)
    except Exception as exc:  # even the ledger write is fail-open
        sys.stderr.write(f"engine_shadow: ledger append failed (non-fatal): {exc}\n")
    return row


# --------------------------------------------------------------------------- #
# Scorecard — aggregate a day's rows into the Phase-4 agreement gate metric.
# --------------------------------------------------------------------------- #


def build_scorecard(rows: list[Mapping[str, Any]], date: str) -> dict:
    """Aggregate one day's shadow rows into the agreement scorecard.

    The migration gate: overall agreement >= 99% AND entry-tick agreement == 100%.
    """
    day = [r for r in rows if r.get("date") == date and r.get("shadow") == "engine"]
    n = len(day)
    errors = sum(1 for r in day if r.get("engine_verdict") == "SHADOW_ERROR")
    scored = [r for r in day if r.get("engine_verdict") != "SHADOW_ERROR"]
    n_scored = len(scored)
    agree = sum(1 for r in scored if r.get("agree"))
    entry_ticks = [r for r in scored if r.get("entry_tick")]
    entry_agree = sum(1 for r in entry_ticks if r.get("agree"))
    buckets: dict[str, int] = {}
    for r in scored:
        b = str(r.get("bucket"))
        buckets[b] = buckets.get(b, 0) + 1
    overall_rate = (agree / n_scored) if n_scored else None
    entry_rate = (entry_agree / len(entry_ticks)) if entry_ticks else None
    gate_pass = (
        n_scored > 0
        and overall_rate is not None and overall_rate >= 0.99
        and (entry_rate is None or entry_rate >= 1.0)
    )
    return {
        "date": date,
        "shadow": "engine",
        "n_ticks": n,
        "n_scored": n_scored,
        "n_shadow_errors": errors,
        "n_agree": agree,
        "overall_agreement_rate": overall_rate,
        "n_entry_ticks": len(entry_ticks),
        "entry_agreement_rate": entry_rate,
        "buckets": buckets,
        "phase4_gate_pass": gate_pass,
        "disagreements": [
            {k: r.get(k) for k in ("time_et", "prose_action", "engine_verdict",
                                   "engine_side", "engine_gate", "bucket", "engine_reason")}
            for r in scored if not r.get("agree")
        ],
        "_gate": "overall>=0.99 AND entry==1.0 over N>=5 trading days (this is ONE day)",
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with io.open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue  # tolerate a partial last line; never crash the scorecard
    return out


# --------------------------------------------------------------------------- #
# Calendar guard (advisory) + CLI.
# --------------------------------------------------------------------------- #


def is_trading_session_today(date: str) -> bool:
    """Best-effort: True if today-bias.json says there's a session for ``date``.

    Data-driven (no hardcoded holiday list to go stale). Fail-open: if today-bias
    is missing/unreadable, returns True (the heartbeat would not have fired on a
    non-trading day anyway; a read-only shadow erring toward 'run' is harmless)."""
    try:
        b = json.loads(io.open(TODAY_BIAS, "r", encoding="utf-8").read())
    except Exception:
        return True
    if str(b.get("date")) != str(date):
        return True  # stale bias -> don't suppress (fail-open)
    sw = b.get("session_window") or {}
    # premarket writes open_et/close_et only on a real session; bias=="no-trade" for holidays
    if str(b.get("bias", "")).lower() in ("closed", "holiday"):
        return False
    return bool(sw.get("open_et")) or b.get("bias") is not None


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="engine_shadow", description=__doc__)
    ap.add_argument("--payload", help="path to the tick bar_ctx payload JSON (engine_cli shape)")
    ap.add_argument("--prose-action", default=None, help="the heartbeat's prose action this tick")
    ap.add_argument("--date", required=True, help="session date YYYY-MM-DD")
    ap.add_argument("--time", default="", help="tick time ET HH:MM")
    ap.add_argument("--out", default=str(SHADOW_LEDGER), help="shadow ledger path")
    ap.add_argument("--scorecard", action="store_true", help="aggregate --date's rows into a scorecard")
    ap.add_argument("--require-trading-day", action="store_true",
                    help="skip (exit 0) if today-bias says no session for --date")
    args = ap.parse_args(argv)

    if args.scorecard:
        rows = _read_jsonl(Path(args.out))
        card = build_scorecard(rows, args.date)
        SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
        out = SCORECARD_DIR / f"scorecard-{args.date}.json"
        io.open(out, "w", encoding="utf-8", newline="\n").write(
            json.dumps(card, indent=2, default=str))
        print(json.dumps({k: card[k] for k in
                          ("date", "n_scored", "overall_agreement_rate",
                           "entry_agreement_rate", "phase4_gate_pass")}, default=str))
        return 0

    # Per-tick path — FAIL-OPEN, always exit 0.
    if args.require_trading_day and not is_trading_session_today(args.date):
        print(json.dumps({"shadow": "engine", "skipped": "non_trading_day", "date": args.date}))
        return 0
    if not args.payload:
        print(json.dumps({"shadow": "engine", "skipped": "no_payload"}))
        return 0
    try:
        payload = json.loads(io.open(args.payload, "r", encoding="utf-8").read())
    except Exception as exc:
        # Even a bad payload file is fail-open: log a row, exit 0.
        row = run_shadow_tick({}, args.prose_action, date=args.date, time_et=args.time,
                              out_path=Path(args.out))
        row["engine_reason"] = f"payload read failed: {exc}"
        print(json.dumps({"shadow": "engine", "verdict": "SHADOW_ERROR", "date": args.date}))
        return 0
    row = run_shadow_tick(payload, args.prose_action, date=args.date, time_et=args.time,
                          out_path=Path(args.out))
    print(json.dumps({"shadow": "engine", "verdict": row.get("engine_verdict"),
                      "agree": row.get("agree"), "bucket": row.get("bucket")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
