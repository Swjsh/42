#!/usr/bin/env python3
"""
MCP Weekly Audit — round-trip every broker/chart connection the engine depends on.
READ-ONLY. No trades, no edits.
"""

import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def get_et_now():
    """Get current time in ET (for logging)."""
    utc_now = datetime.now(timezone.utc)
    return utc_now.isoformat()

EXPECTED_ACCOUNTS_DOC = """Read expected account numbers from the FLEET REGISTRY, never hardcode.

SCAR (2026-08-18): this module compared the live API's account_number for equality against
"PA3DHPT7KIQE"/"PA33W2KUAT40". Neither string was ever a real account number -- a documentation
transcription error that got copied into code -- so the equality could NEVER be satisfied and
this audit reported FAIL on every run regardless of real connection health. Its sibling
mcp_audit_direct.py had the identical defect AND fired a Discord alert on every RED, which
manufactured a recurring "engine red" ping with no underlying fault. A monitor that cannot go
green trains the operator to ignore the channel.
"""


def expected_accounts():
    """(safe_acct, bold_acct) from automation/state/fleet/accounts.json. See EXPECTED_ACCOUNTS_DOC."""
    import json as _json
    from pathlib import Path as _Path
    reg_path = _Path(__file__).resolve().parents[2] / "automation" / "state" / "fleet" / "accounts.json"
    reg = _json.loads(reg_path.read_text(encoding="utf-8"))
    by_id = {}
    for arm in reg.get("arms", []):
        aid = arm.get("id") or arm.get("arm_id")
        acct = arm.get("account_number")
        if aid and isinstance(acct, str):
            by_id.setdefault(str(aid), acct)
    return by_id.get("safe-2"), by_id.get("bold-2")


def call_mcp_tool(tool_name: str) -> dict:
    """
    Call an MCP tool via claude command-line.
    Returns {success, data, error}.
    """
    try:
        result = subprocess.run(
            ["claude", "mcp", "call", tool_name],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {"success": True, "data": data}
        else:
            return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}

def audit():
    """Run the audit sequence."""
    ts_iso = get_et_now()
    verdict = "GREEN"
    safe_ok = False
    bold_ok = False
    tv_ok = False
    tv_relaunched = False
    chart_symbol = "UNKNOWN"

    # Step 1: Alpaca Safe
    print("[1] Probing Alpaca Safe (get_clock)...")
    clock_resp = call_mcp_tool("mcp__alpaca__get_clock")
    if not clock_resp["success"]:
        print(f"  FAIL: {clock_resp['error']}")
    else:
        print(f"  OK")

    print("[2] Probing Alpaca Safe (get_account_info)...")
    acct_resp = call_mcp_tool("mcp__alpaca__get_account_info")
    if not acct_resp["success"]:
        print(f"  FAIL: {acct_resp['error']}")
    else:
        data = acct_resp["data"]
        account_num = data.get("account_number", "UNKNOWN")
        status = data.get("status", "UNKNOWN")
        trading_blocked = data.get("trading_blocked", None)
        account_blocked = data.get("account_blocked", None)
        print(f"  OK: acct={account_num}, status={status}")

        _exp_safe, _exp_bold = expected_accounts()
        if (_exp_safe and account_num == _exp_safe and
            status == "ACTIVE" and
            not trading_blocked and
            not account_blocked):
            safe_ok = True
            print("  Safe: PASS")
        else:
            print("  Safe: FAIL")

    # Step 2: Alpaca Bold
    print("[3] Probing Alpaca Bold (get_account_info)...")
    bold_resp = call_mcp_tool("mcp__alpaca_aggressive__get_account_info")
    if not bold_resp["success"]:
        print(f"  FAIL: {bold_resp['error']}")
    else:
        data = bold_resp["data"]
        account_num = data.get("account_number", "UNKNOWN")
        status = data.get("status", "UNKNOWN")
        print(f"  OK: acct={account_num}, status={status}")

        _exp_safe, _exp_bold = expected_accounts()
        if (_exp_bold and account_num == _exp_bold and
            status == "ACTIVE"):
            bold_ok = True
            print("  Bold: PASS")
        else:
            print("  Bold: FAIL")

    # Step 3: TradingView
    print("[4] Probing TradingView (tv_health_check)...")
    tv_resp = call_mcp_tool("mcp__tradingview__tv_health_check")
    if not tv_resp["success"]:
        print(f"  FAIL: {tv_resp['error']}")
    else:
        data = tv_resp["data"]
        success = data.get("success", False)
        cdp_connected = data.get("cdp_connected", False)
        api_available = data.get("api_available", False)
        chart_symbol = data.get("chart_symbol", "UNKNOWN")
        print(f"  OK: success={success}, cdp={cdp_connected}, api={api_available}, chart={chart_symbol}")

        if success and cdp_connected and api_available:
            tv_ok = True
            print("  TradingView: PASS")
        else:
            print("  TradingView: FAIL")

    # Determine verdict
    if safe_ok and bold_ok and tv_ok and not tv_relaunched:
        verdict = "GREEN"
    elif safe_ok and bold_ok and tv_ok:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    reason = f"safe={'ok' if safe_ok else 'FAIL'} bold={'ok' if bold_ok else 'FAIL'} tv={'ok' if tv_ok else 'FAIL'}(relaunch={'y' if tv_relaunched else 'n'})"

    # Step 5: Write outputs
    print(f"\n[5] Writing audit state...")
    output_json = {
        "skill": "mcp-weekly-audit",
        "run_at": ts_iso,
        "verdict": verdict,
        "alpaca_safe": {"ok": safe_ok, "account": expected_accounts()[0], "note": "Clock + Account probed"},
        "alpaca_bold": {"ok": bold_ok, "account": expected_accounts()[1], "note": "Account probed"},
        "tradingview": {"ok": tv_ok, "cdp_connected": tv_ok, "relaunched": tv_relaunched, "chart_symbol": chart_symbol, "note": "Health check"},
        "reason": reason
    }

    output_path = Path(r"C:\Users\jackw\Desktop\42\automation\state\mcp-weekly-audit-latest.json")
    output_path.write_text(json.dumps(output_json, indent=2))
    print(f"  Wrote: {output_path}")

    # Append log
    log_path = Path(r"C:\Users\jackw\Desktop\42\automation\state\mcp-weekly-audit-log.jsonl")
    log_entry = {"run_at": ts_iso, "verdict": verdict, "reason": reason}
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"  Appended: {log_path}")

    # Final output
    print(f"\nMCP-AUDIT {verdict} | safe={'ok' if safe_ok else 'FAIL'} bold={'ok' if bold_ok else 'FAIL'} tv={'ok' if tv_ok else 'FAIL'}(relaunch={'y' if tv_relaunched else 'n'}) | {reason}")
    return verdict

if __name__ == "__main__":
    try:
        verdict = audit()
        sys.exit(0 if verdict == "GREEN" else 1)
    except Exception as e:
        print(f"AUDIT ERROR: {e}", file=sys.stderr)
        sys.exit(2)
