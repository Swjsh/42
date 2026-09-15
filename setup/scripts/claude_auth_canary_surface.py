"""claude_auth_canary_surface.py -- route claude_auth_canary.py's verdict onto STATUS.md's
'## Known broken' section via the existing de-duplicating writer.

ROUTING NOTE (2026-09-15 build): MAP.md/dashboard/lib/hq.ts were read first per doctrine.
The HQ "NEEDS J" card (dashboard/lib/hq.ts, ~L259 on) is a READ-ONLY merge of four existing
producers (discord-outbox j_decision rows, conductor_proposals pending rows, overnight
queue.md FABLE-ESCALATION lines, and an active goal's own J-DECISIONS section) -- it has NO
writer API a new producer can call into. Wiring a canary into it would mean either hand-
editing a generated read path or inventing a parallel writer, both against OP-25/doc-
architecture doctrine. So this canary writes to the ONE existing mechanism that DOES have a
sanctioned writer API: setup/scripts/status_known_broken.py's upsert(), the shared, de-
duplicating writer for STATUS.md's '## Known broken' section (used today by roster_liveness,
mcp_audit, guard_runner_full, etc). If NEEDS J ever grows a writer API, wire this module's
`surface()` into it in addition -- the state file this reads from
(automation/state/claude-auth-canary.json) is exactly what such a reader would need.

Marker: 'CLAUDE_AUTH:' (upsert() dedupes/replaces any existing bullet with this prefix, so
repeated fires never spam the section -- same contract every other producer gets for free).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_known_broken as skb  # noqa: E402

MARKER = "CLAUDE_AUTH:"


def surface(state: dict) -> bool:
    """Upsert (or clear) the CLAUDE_AUTH: line in STATUS.md's Known broken section based on
    `state` (the dict returned by claude_auth_canary.run_canary()). Returns whatever
    status_known_broken.upsert() returns (True if the file changed). Never raises --
    status_known_broken.upsert() is itself fail-open, and any exception here is a no-op
    surfacing failure, never a crash of the canary that called it."""
    verdict = state.get("verdict")
    ts_et = state.get("ts_et") or "unknown time"

    if verdict == "OK":
        return skb.upsert(MARKER, None)

    if verdict == "LOGGED_OUT":
        detail = "claude CLI is logged out (loggedIn=false or refresh token expired)"
    elif verdict == "EXPIRING":
        hours = state.get("hours_left")
        expiry = state.get("refresh_expires_at_local") or "unknown"
        detail = f"refresh token expires in {hours}h ({expiry})"
    else:  # UNKNOWN
        errs = state.get("errors") or ["no detail"]
        detail = f"could not determine auth state: {'; '.join(errs)}"

    fix_hint = state.get("fix_hint", "run `claude` then /login in a terminal (J credential step)")
    line = f"- [{ts_et}] {MARKER} {verdict} -- {detail}. Fix: {fix_hint}"
    return skb.upsert(MARKER, line)
