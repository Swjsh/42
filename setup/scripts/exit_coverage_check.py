"""Alarm when a HELD position is not covered by a fresh exit-state.

THE INCIDENT THIS EXISTS FOR (2026-08-13, measured, journal/2026-08-13.md):

    bold-2 held 5x SPY260813P00776000 @0.64 with a -50% stop at 0.32. From ~12:55 to 13:12 ET
    its /v2/positions and /v2/account hung at 15s while /v2/clock and /v2/orders answered in
    0.2s -- that arm only. The exit loop's position read timed out, the arm was skipped, and
    EVERY tick still logged `exit=0` with nothing in any error log. exit-state went 14 minutes
    without refreshing while the bid (0.28) sat through the 0.32 stop. The engine recovered and
    stopped out at 13:12 once the endpoint came back: -$200 realized, of which -$40 is
    attributable to the delay (filled 0.24 against a 0.32 stop level).

    `exit=0` does not mean the arm was managed. It means nothing raised.

WHAT THIS CHECKS -- one question, per arm:

    Is there a position the exit manager is not currently tracking, or tracking staleley?

WHY STALENESS ALONE IS THE WRONG ALARM: measured 2026-08-13 13:46 ET, four FLAT arms carried
exit-state ages of 34-121 minutes, all correct -- there is nothing to write when flat. Alarming
on age alone would have fired four false positives at that instant. The alarm is the CONJUNCTION
of (position exists) AND (coverage missing or stale). That conjunction is what was true for
bold-2 and false for everyone else during the incident.

BROKER BLINDNESS IS ITSELF AN ALARM. If the position read fails after retries, this reports
BLIND for that arm -- never "flat". Treating an unreadable arm as empty is the exact defect
being detected; it must not be reproduced inside the detector (C7, no silent fallback).

Read-only. Places no orders, writes no params, changes no exit state. Exit code is always 0 --
a monitor must never break its caller or block a tick (OP-25 guards fail open).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
SECRETS = FLEET / "secrets.json"
OUT = REPO / "automation" / "state" / "exit-coverage.json"

sys.path.insert(0, str(FLEET))
from arm_roster import active_arms  # noqa: E402 -- ONE roster def; queue.md THREE-MODULES-...


def __getattr__(name: str):  # PEP 562 -- module.ARMS always reflects the CURRENT roster
    if name == "ARMS":
        return tuple(active_arms())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# The exit loop ticks every 60s. Three missed ticks is a real stall, not jitter.
STALE_MIN = 3.0
READ_TIMEOUT_S = 25      # above the 24.0s recovery latency measured during the incident;
                         # fleet_broker's own 15s is BELOW it and fails a recovering endpoint
READ_ATTEMPTS = 3


def _load(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_positions(arm: str, creds: dict) -> tuple[Optional[list], str]:
    """Returns (positions, detail). positions is None ONLY when every attempt failed --
    which is BLIND, never an empty list. Conflating those two is the bug this file detects."""
    base = str(creds.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
    hdr = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    errs = []
    for attempt in range(READ_ATTEMPTS):
        t0 = time.time()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(base + "/v2/positions", headers=hdr),
                timeout=READ_TIMEOUT_S,
            ) as r:
                return json.loads(r.read()), f"ok in {time.time() - t0:.1f}s (attempt {attempt + 1})"
        except Exception as e:  # noqa: BLE001 -- fail-open by contract
            errs.append(f"{type(e).__name__} {time.time() - t0:.1f}s")
            time.sleep(1.0)
    return None, "; ".join(errs)


def assess_arm(arm: str, creds: dict, now: float) -> dict[str, Any]:
    pos, detail = read_positions(arm, creds)
    st_path = FLEET / arm / "exit-state.json"
    state = _load(st_path)
    age_min = ((now - st_path.stat().st_mtime) / 60.0) if st_path.exists() else None
    row: dict[str, Any] = {
        "arm": arm, "read_detail": detail,
        "exit_state_age_min": None if age_min is None else round(age_min, 1),
        "tracked": sorted(state.keys()) if isinstance(state, dict) else None,
    }
    if pos is None:
        row["status"] = "BLIND"
        row["held"] = None
        row["why"] = ("position read failed every attempt -- this arm's coverage is UNKNOWN, "
                      "not empty. The exit loop treats this case as nothing-to-do.")
        return row

    held = [p["symbol"] for p in pos]
    row["held"] = held
    if not held:
        # Flat: exit-state age is meaningless. Do not alarm on it.
        row["status"] = "FLAT"
        return row

    tracked = set(row["tracked"] or ())
    uncovered = [s for s in held if s not in tracked]
    if uncovered:
        row["status"] = "UNCOVERED"
        row["why"] = f"held but absent from exit-state: {uncovered}"
        return row
    # QTY MISMATCH (2026-08-14): symbol membership is NOT coverage. On 2026-08-14 a wake-storm
    # double entry left safe-2 holding 6 contracts with exit-state tracking 3, bold-2 10 vs 5 --
    # this detector reported OK because the SYMBOL was tracked, while half of each position had
    # no stop, no TP1, and nothing that would ever exit it. Coverage = the exit manager knows
    # about every CONTRACT, not every symbol.
    qty_gaps = []
    for p in (pos or []):
        sym = str(p.get("symbol"))
        if sym not in tracked or not isinstance(state, dict):
            continue
        try:
            held_q = abs(int(float(p.get("qty", 0))))
            trk_q = int(state[sym].get("total_qty") or 0)
        except (TypeError, ValueError, KeyError):
            continue        # unparseable -> fall through to the stale/OK checks, never crash
        if held_q != trk_q:
            qty_gaps.append(f"{sym}: broker={held_q} tracked={trk_q}")
    if qty_gaps:
        row["status"] = "QTY_MISMATCH"
        row["why"] = ("exit manager tracks the symbol but NOT the full size -- the surplus "
                      f"contracts have no stop and nothing will exit them: {qty_gaps}")
        return row
    if age_min is not None and age_min > STALE_MIN:
        row["status"] = "STALE"
        row["why"] = (f"holding {held} but exit-state has not refreshed in {age_min:.1f} min "
                      f"(> {STALE_MIN} min = 3 missed ticks)")
        return row
    row["status"] = "OK"
    return row


def assess() -> dict[str, Any]:
    secrets = _load(SECRETS) or {}
    accounts = secrets.get("accounts") or {}
    now = time.time()
    rows = [assess_arm(a, accounts[a], now) for a in active_arms() if a in accounts]
    order = {"UNCOVERED": 3, "QTY_MISMATCH": 3, "BLIND": 2, "STALE": 2, "OK": 0, "FLAT": 0}
    worst = max((order.get(r["status"], 0) for r in rows), default=0)
    verdict = "RED" if worst >= 3 else ("YELLOW" if worst == 2 else "GREEN")
    return {
        "_doc": "Alarms only on (position held) AND (uncovered or stale). Flat arms never alarm.",
        "verdict": verdict,
        "stale_threshold_min": STALE_MIN,
        "read_timeout_s": READ_TIMEOUT_S,
        "rows": rows,
        "incident": "journal/2026-08-13.md -- broker read hang silently skipped bold-2's exit loop",
    }


def render(rep: dict[str, Any]) -> str:
    out = [f"EXIT COVERAGE: {rep['verdict']}"]
    for r in rep["rows"]:
        line = f"  [{r['status']:<9}] {r['arm']:<8}"
        if r["status"] == "FLAT":
            line += " flat"
        elif r["status"] == "BLIND":
            line += f" read FAILED -- {r['read_detail']}"
        else:
            line += f" held={r['held']} age={r['exit_state_age_min']}m"
        out.append(line)
        if r.get("why"):
            out.append(f"                {r['why']}")
    return "\n".join(out)


def main() -> int:
    rep = assess()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(render(rep))
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0  # fail-open by contract


if __name__ == "__main__":
    sys.exit(main())
