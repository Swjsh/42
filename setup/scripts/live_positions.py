"""live_positions.py -- single shared reader for LIVE per-account open-position truth.

HQ-POSITION-TRUTH (root cause fixed 2026-09-15): automation/state/current-position*.json
(current-position.json, current-position-safe.json, current-position-bold.json,
aggressive/current-position-bold.json) stopped being written when the LLM heartbeat
pipeline (run-heartbeat.ps1 -> heartbeat.md, Gamma_Heartbeat/_Aggressive) was retired
2026-06-25 in favor of the deterministic Gamma_HeartbeatCore -- but the old files kept
parsing cleanly as `{"status": null}` / missing entirely, so every reader of them
rendered a confident WRONG "flat" answer instead of an honest "unknown". Live incident
2026-09-15: safe-2 held 3x SPY260915P00757000 10:38-11:46 ET and bold-2 held 5x P755
10:38-10:55 ET (broker-verified fills in automation/state/fills-ledger.jsonl) while
current-position-safe.json / current-position-bold.json stayed all-null the entire day.

The LIVE truth is automation/state/fleet/<arm>/exit-state.json -- a dict keyed by
OPEN option symbol, written by heartbeat_core.py's exit_manager. `{}` == flat. This
is the SAME source dashboard/lib/hq-positions-pure.ts (/api/hq) and
setup/scripts/hq_market_correlate.py already read (both repointed 2026-09-15).

This module is READ-ONLY and touches no trading-path file. It is for display/health
/notification readers ONLY (discord-watcher, engine_health, gamma_glance, gamma_glass,
gamma_lanes, eod_fallback, and similar) -- never import it into anything that places
or closes orders; the live engine (heartbeat_core.py) owns exit-state.json itself and
must never be made to depend on this module.

FAIL-LOUD (judgment-guards failure-honesty): a missing directory or corrupt JSON
raises LivePositionsError rather than silently degrading to "flat". Callers that
render a health/status line must catch it and show an explicit "unknown" state, never
assume flat on a read failure -- an unreadable file is not evidence of no position.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"

# Canonical arm ids (fleet/accounts.json) plus the short aliases callers already
# use elsewhere in the codebase ("safe"/"bold") -- both resolve to the same file.
ARM_EXIT_STATE = {
    "safe": STATE / "fleet" / "safe-2" / "exit-state.json",
    "safe-2": STATE / "fleet" / "safe-2" / "exit-state.json",
    "bold": STATE / "fleet" / "bold-2" / "exit-state.json",
    "bold-2": STATE / "fleet" / "bold-2" / "exit-state.json",
}

_STRIKE_RE = re.compile(r"[CP](\d{8})$")


class LivePositionsError(RuntimeError):
    """Raised when an arm's exit-state.json is missing, unreadable, or malformed.
    Callers MUST NOT catch-and-treat this as "flat" -- render an explicit unknown
    state instead (failure-honesty: unknown != flat)."""


def _strike_from_symbol(symbol: str) -> float | None:
    """OCC-style option symbol -> strike, e.g. SPY260915P00757000 -> 757.0.
    Returns None (never raises) if the symbol doesn't match -- a bad strike parse
    is not a reason to fail the whole read."""
    m = _STRIKE_RE.search(symbol or "")
    if not m:
        return None
    try:
        return int(m.group(1)) / 1000.0
    except ValueError:
        return None


def read_open_positions(arm: str) -> list[dict[str, Any]]:
    """Return the list of OPEN legs for `arm` (accepts "safe"/"safe-2"/"bold"/"bold-2"),
    read live from automation/state/fleet/<arm>/exit-state.json.

    Each row: symbol, side ("C"|"P"|None), strike (derived, may be None), qty,
    entry_premium, hwm_premium, strategy, runner_stop_premium, profit_lock_armed.
    Empty list == confirmed flat (file read successfully and was `{}`).

    Raises LivePositionsError on a missing/corrupt/malformed file or an unknown
    arm id -- this is intentional; see module docstring.
    """
    path = ARM_EXIT_STATE.get(arm)
    if path is None:
        raise LivePositionsError(
            f"unknown arm {arm!r}; known arms: {sorted(set(ARM_EXIT_STATE))}"
        )
    if not path.exists():
        raise LivePositionsError(f"exit-state file missing for arm {arm!r}: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
        data: Any = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError) as e:
        raise LivePositionsError(
            f"exit-state file for arm {arm!r} unreadable/corrupt: {path} ({e})"
        ) from e
    if not isinstance(data, dict):
        raise LivePositionsError(
            f"exit-state file for arm {arm!r} is not a JSON object: {path}"
        )

    out: list[dict[str, Any]] = []
    for symbol, rec in data.items():
        if not isinstance(rec, dict):
            continue  # malformed entry: skip it, don't fail the whole read
        out.append({
            "symbol": symbol,
            "side": rec.get("side"),
            "strike": _strike_from_symbol(symbol),
            "qty": rec.get("total_qty"),
            "entry_premium": rec.get("entry_premium"),
            "hwm_premium": rec.get("hwm_premium"),
            "strategy": rec.get("strategy"),
            "runner_stop_premium": rec.get("runner_stop_premium"),
            "profit_lock_armed": rec.get("profit_lock_armed"),
        })
    return out


def is_flat(arm: str) -> bool:
    """True iff `arm` currently has zero open legs. Raises LivePositionsError on
    a bad read -- a caller that needs a boolean under a read failure must catch
    the exception itself and decide how to render "unknown", never coerce it to
    True here (that would silently reintroduce the exact bug this module fixes)."""
    return len(read_open_positions(arm)) == 0


def position_status_label(arm: str) -> str:
    """Best-effort single-word status for display-only callers that just want a
    string: "flat", "open", or "unknown" (on any read error). This is the ONLY
    function in this module that swallows LivePositionsError -- by design, for
    callers that render one status word and cannot branch on an exception type;
    it still never returns "flat" for a read failure."""
    try:
        return "flat" if is_flat(arm) else "open"
    except LivePositionsError:
        return "unknown"
