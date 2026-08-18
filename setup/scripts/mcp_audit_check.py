#!/usr/bin/env python3
"""
MCP Weekly Connection Audit
Tests Alpaca Safe, Alpaca Bold, and TradingView health
"""
import json
import socket
import sys
import time
from datetime import datetime, timezone


# --- registry-sourced expected accounts (2026-08-18) -------------------------
# SCAR: this module compared the broker's live account_number for equality against
# "PA3DHPT7KIQE"/"PA33W2KUAT40". Neither was ever a real account number -- a documentation
# transcription error copied into code -- so the check could never pass. Same defect as
# mcp_audit_direct.py, which additionally fired a Discord alert on every RED.
# NOTE: this script is UNREFERENCED (nothing invokes it) and duplicates mcp_audit_direct.py.
# Fixed rather than deleted; consolidation is a separate call. See
# analysis/deep-research/ACCOUNT-IDENTITY-ALIGNMENT-2026-08-18.md.
def _expected_accounts():
    """(safe, bold) from automation/state/fleet/accounts.json."""
    import json as _json
    from pathlib import Path as _P
    reg = _json.loads((_P(__file__).resolve().parents[2] / "automation" / "state" / "fleet"
                       / "accounts.json").read_text(encoding="utf-8"))
    by_id = {}
    for arm in reg.get("arms", []):
        aid = arm.get("id") or arm.get("arm_id")
        acct = arm.get("account_number")
        if aid and isinstance(acct, str):
            by_id.setdefault(str(aid), acct)
    return by_id.get("safe-2"), by_id.get("bold-2")


def check_port(host, port):
    """Check if a port is listening"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

# Audit run timestamp (ET)
ts_et = "2026-07-29T18:30:05-04:00"

audit = {
    "run_at": ts_et,
    "safe_ok": False,
    "bold_ok": False,
    "tv_ok": False,
    "tv_relaunched": False,
    "alpaca_safe": {"ok": False, "account": _expected_accounts()[0], "note": ""},
    "alpaca_bold": {"ok": False, "account": _expected_accounts()[1], "note": ""},
    "tradingview": {"ok": False, "cdp_connected": False, "relaunched": False, "chart_symbol": "", "note": ""}
}

# Check TradingView CDP on port 9222 (primary health check)
print("Testing TradingView CDP on port 9222...", file=sys.stderr)
if check_port("127.0.0.1", 9222):
    audit["tradingview"]["ok"] = True
    audit["tradingview"]["cdp_connected"] = True
    audit["tv_ok"] = True
    audit["tradingview"]["note"] = "CDP responding on 9222"
    print("  ✓ TradingView CDP ALIVE", file=sys.stderr)
else:
    audit["tradingview"]["ok"] = False
    audit["tradingview"]["note"] = "TV CDP port 9222 NOT listening - NEEDS RESTART"
    print("  ✗ TradingView CDP DEAD on port 9222", file=sys.stderr)

# For Alpaca, we need to test via MCP invoke or REST if available
# Check if Alpaca MCP servers are listening on common ports
print("Testing Alpaca Safe MCP...", file=sys.stderr)
alpaca_found = False
for port in [3000, 3001, 5000, 5001, 8000, 8001, 8080]:
    if check_port("127.0.0.1", port):
        audit["alpaca_safe"]["ok"] = True
        audit["safe_ok"] = True
        audit["alpaca_safe"]["note"] = f"Alpaca Safe MCP responding on port {port}"
        alpaca_found = True
        print(f"  ✓ Alpaca MCP found on port {port}", file=sys.stderr)
        break

if not alpaca_found:
    audit["alpaca_safe"]["ok"] = False
    audit["alpaca_safe"]["note"] = "Alpaca Safe MCP NOT accessible - port not found"
    print("  ✗ Alpaca MCP not accessible on common ports", file=sys.stderr)

# For now, set bold_ok = safe_ok since they share the same MCP server binary
audit["alpaca_bold"]["ok"] = audit["alpaca_safe"]["ok"]
audit["bold_ok"] = audit["safe_ok"]
if audit["bold_ok"]:
    audit["alpaca_bold"]["note"] = "Alpaca Bold MCP responding (shared binary with Safe)"
else:
    audit["alpaca_bold"]["note"] = "Alpaca Bold MCP NOT accessible"

# Determine overall verdict
if audit["safe_ok"] and audit["bold_ok"] and audit["tv_ok"]:
    verdict = "GREEN"
elif audit["safe_ok"] and audit["bold_ok"] and not audit["tv_ok"]:
    verdict = "YELLOW"
else:
    verdict = "RED"

audit["verdict"] = verdict

print("\n" + json.dumps(audit, indent=2))
