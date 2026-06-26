"""fleet_eod -- EOD flatten for the champion/challenger fleet_rest arms.

Mirrors Gamma_EodFlatten (heartbeat accounts) for the fleet. Market-sells every open
SPY option position on each active fleet_rest arm so no 0DTE long rides to expiry /
auto-exercise (an ITM 0DTE exercise on a $2K paper acct = assignment blowup = corrupted
experiment data). Idempotent: a flat/WATCH arm is a no-op. Pure stdlib via fleet_broker.

Wired into run-fleet-executor.ps1 (fires on the >=15:50 ET fleet ticks); also runnable
standalone:  python automation/state/fleet/fleet_eod.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FLEET_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FLEET_DIR))
import fleet_broker as fb  # noqa: E402
import fleet_live as fl  # noqa: E402  (share the _arm_is_processable unification gate)


def main() -> int:
    try:
        creds_all = fb.load_creds()
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        return 0
    accounts = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))
    for arm in accounts.get("arms", []):
        # Same unification gate as fleet_live: the 4 fleet_rest arms always; the 2
        # mcp_heartbeat controls only when FLEET_OWNS_ALL_6 (else Gamma_EodFlatten owns them).
        if not fl._arm_is_processable(arm):
            continue
        arm_id = arm["id"]
        creds = creds_all.get(arm_id)
        if not creds:
            print(f"{arm_id}: no creds")
            continue
        # live=True so it actually sells; flat arms (WATCH / never placed) return no-op.
        res = fb.close_all_spy_options(creds, live=True)
        print(f"{arm_id}: {json.dumps(res)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
