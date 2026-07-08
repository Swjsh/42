"""j_call_capture.py -- capture J's live trade CALLS as anchor data (G5 capture leg).

OP-16: J's real trades are the source of truth; the engine is measured by how well it
captures J's edge. Today those calls arrive in chat/Discord ("if we reject 750 enter puts")
and evaporate -- they are never captured as structured anchors the way the 7 immutable
source-of-truth trades are. This module is the standing capture surface: a validated append
to analysis/j-calls/anchors.jsonl so every J call becomes labelled anchor data (entry thesis
now; outcome/pnl filled in later), feeding the edge-capture score + future validation.

Pure stdlib, no trading path. Schema documented in analysis/j-calls/README.md.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1].parent
ANCHORS = REPO / "analysis" / "j-calls" / "anchors.jsonl"

REQUIRED = ("ts_et", "source", "symbol", "side", "thesis")
_SIDES = {"call", "put", "long", "short"}


def _call_id(call: dict) -> str:
    seed = f"{call.get('ts_et')}|{call.get('symbol')}|{call.get('side')}|{call.get('level')}"
    return "jc_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def validate(call: dict) -> dict:
    """Return a normalized anchor row, or raise ValueError on a malformed call. Fills defaults
    for the outcome fields (filled in after the trade resolves)."""
    if not isinstance(call, dict):
        raise ValueError("call must be a dict")
    missing = [k for k in REQUIRED if not str(call.get(k) or "").strip()]
    if missing:
        raise ValueError(f"j-call missing required field(s): {missing}")
    side = str(call["side"]).lower().strip()
    if side not in _SIDES:
        raise ValueError(f"side must be one of {_SIDES}, got {side!r}")
    row = {
        "call_id": call.get("call_id") or _call_id(call),
        "ts_et": str(call["ts_et"]),
        "source": str(call["source"]),          # discord | chat | manual
        "symbol": str(call["symbol"]).upper(),
        "side": side,
        "level": _num_or_none(call.get("level")),
        "thesis": str(call["thesis"]),
        "strike": _num_or_none(call.get("strike")),
        "expiry": call.get("expiry"),            # 0DTE / ISO date / null
        "outcome": call.get("outcome"),          # win | loss | flat | open | null (filled later)
        "pnl": _num_or_none(call.get("pnl")),
        "tags": list(call.get("tags") or []),
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return row


def _num_or_none(x) -> Optional[float]:
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def capture(call: dict, *, path: Path = ANCHORS) -> dict:
    """Validate + append one J-call anchor row. Returns the written row. Raises ValueError on
    a malformed call (a bad anchor must fail loudly, not silently corrupt the corpus)."""
    row = validate(call)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row
