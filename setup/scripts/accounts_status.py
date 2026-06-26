"""accounts_status.py — THE canonical live view of ALL Gamma trading accounts.

Why this exists (2026-06-25): "show me the accounts" was being answered from .mcp.json,
which only wires the 2 heartbeat MCP servers (Safe-2 + Bold-2) — so checks silently showed
2 of 6. The real roster is fleet/accounts.json (arms) + fleet/secrets.json (keys). This
reader is the ONE source of truth: it reads the fleet roster and queries EVERY equity
account live via Alpaca REST. Always use this for an account snapshot — never the MCP config.

Loads keys from fleet/secrets.json at runtime (CLAUDE.md secret rule). READ-ONLY, $0,
no MCP/no pool. Run: python setup/scripts/accounts_status.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1].parent
SECRETS = REPO / "automation" / "state" / "fleet" / "secrets.json"
ACCOUNTS = REPO / "automation" / "state" / "fleet" / "accounts.json"
MCP_JSON = REPO / ".mcp.json"
BASELINE = 2000.0  # every equity account is meant to start here

# Display order + which arms the live engine actually trades through.
ORDER = ["safe-1", "safe-2", "safe-3", "bold-2", "risky-1", "risky-3"]
ENGINE_WIRING = {
    "safe-2": "heartbeat (mcp `alpaca`)",
    "bold-2": "heartbeat (mcp `alpaca_aggressive`)",
    "safe-1": "fleet REST", "safe-3": "fleet REST",
    "risky-1": "fleet REST", "risky-3": "fleet REST",
}


def _query(key: str, sec: str, base: str) -> dict:
    req = urllib.request.Request(base.rstrip("/") + "/v2/account",
                                 headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        return {"ok": True, "acct": d.get("account_number"), "status": d.get("status"),
                "equity": float(d.get("equity", 0)), "last_equity": float(d.get("last_equity", 0))}
    except urllib.error.HTTPError as e:
        return {"ok": False, "err": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__}


def main() -> int:
    secrets = json.loads(SECRETS.read_text(encoding="utf-8")).get("accounts", {})
    print(f"{'ARM':<9} {'ACCOUNT':<15} {'STATUS':<7} {'EQUITY':>10} {'vs $2K':>9}  WIRING")
    print("-" * 78)
    total = 0.0
    flagged = []
    for arm in ORDER:
        a = secrets.get(arm, {})
        key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
        sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
        base = a.get("base_url", "https://paper-api.alpaca.markets")
        if not key:
            print(f"{arm:<9} {'NO_KEY_IN_SECRETS':<15}")
            flagged.append(f"{arm}: no key in secrets.json")
            continue
        r = _query(key, sec, base)
        if not r["ok"]:
            print(f"{arm:<9} {'?':<15} {r['err']}")
            flagged.append(f"{arm}: {r['err']}")
            continue
        delta = r["equity"] - BASELINE
        total += r["equity"]
        dstr = "  even" if abs(delta) < 0.005 else f"{delta:+.2f}"
        print(f"{arm:<9} {r['acct']:<15} {r['status']:<7} ${r['equity']:>9,.2f} {dstr:>9}  {ENGINE_WIRING.get(arm,'')}")
        if abs(delta) >= 0.005:
            flagged.append(f"{arm} ({r['acct']}) = ${r['equity']:,.2f} (not $2,000 — last_equity ${r['last_equity']:,.2f})")
    print("-" * 78)
    print(f"{'TOTAL':<9} {'6 equity accts':<15} {'':<7} ${total:>9,.2f}")
    if flagged:
        print("\nFLAGS:")
        for f in flagged:
            print(f"  - {f}")
    else:
        print("\nAll 6 equity accounts == $2,000.")
    print("\n(source: fleet/secrets.json + live Alpaca REST — NOT .mcp.json, which only wires 2.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
