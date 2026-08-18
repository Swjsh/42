#!/usr/bin/env python3
"""
MCP weekly audit — test all three MCP servers
Calls Alpaca Safe, Alpaca Bold, TradingView
"""
import subprocess
import json
import sys
from datetime import datetime
from pathlib import Path


# SECURITY (2026-08-18): this module hardcoded FOUR live Alpaca credentials -- two API keys
# and two SECRETS -- as plaintext locals inside the two probe functions. It was untracked at
# the time, so nothing had been published, but untracked-and-unignored in a PUBLIC repo is a
# live landmine (this rig has a documented history of index-absorption incidents). Now loaded
# at runtime from .mcp.json, the ONLY credential store, per CLAUDE.md's non-negotiable secrets
# rule and the documented fast_path_executor.py pattern.
def _creds(server: str):
    """(api_key, secret_key) for an .mcp.json server entry. Fails LOUD if absent."""
    import json as _json
    from pathlib import Path as _P
    cfg = _json.loads((_P(__file__).resolve().parents[2] / ".mcp.json").read_text(encoding="utf-8"))
    env = (cfg.get("mcpServers", {}).get(server, {}) or {}).get("env", {}) or {}
    key, sec = env.get("ALPACA_API_KEY"), env.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        raise SystemExit(f"No Alpaca creds for '{server}' in .mcp.json -- refusing to continue.")
    return key, sec



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


def get_et_now():
    """Get current ET time as ISO string"""
    return datetime.now().isoformat() + "Z"

def test_mcp_tool(tool_name, args=None):
    """
    Call an MCP tool via claude CLI or subprocess
    Returns (success: bool, data: dict or str)
    """
    try:
        # Try to call via Python's MCP interface (if available)
        # For now, fall back to REST API direct calls
        return False, "MCP tool call not available in headless context"
    except Exception as e:
        return False, str(e)

def test_alpaca_safe():
    """Test Alpaca Safe account (safe-2, number read from the fleet registry)."""
    try:
        import urllib.request
        import base64

        # Credentials from .mcp.json
        api_key, secret_key = _creds("alpaca")

        # Alpaca paper trading URL
        url = "https://paper-api.alpaca.markets/v2/account"

        # Basic auth
        credentials = base64.b64encode(f"{api_key}:{secret_key}".encode()).decode()
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/json'
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                account_num = data.get('account_number', '')
                status = data.get('status', '')
                trading_blocked = data.get('trading_blocked', True)
                account_blocked = data.get('account_blocked', True)

                ok = (
                    account_num == _expected_accounts()[0] and
                    status == 'ACTIVE' and
                    not trading_blocked and
                    not account_blocked
                )
                return ok, {
                    'account': account_num,
                    'status': status,
                    'trading_blocked': trading_blocked,
                    'account_blocked': account_blocked
                }
        except Exception as e:
            return False, {'error': str(e)}
    except Exception as e:
        return False, {'error': str(e)}

def test_alpaca_bold():
    """Test Alpaca Bold account (bold-2, number read from the fleet registry)."""
    try:
        import urllib.request
        import base64

        # Credentials from .mcp.json
        api_key, secret_key = _creds("alpaca_aggressive")

        # Alpaca paper trading URL
        url = "https://paper-api.alpaca.markets/v2/account"

        # Basic auth
        credentials = base64.b64encode(f"{api_key}:{secret_key}".encode()).decode()
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/json'
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                account_num = data.get('account_number', '')
                status = data.get('status', '')
                trading_blocked = data.get('trading_blocked', True)
                account_blocked = data.get('account_blocked', True)

                ok = (
                    account_num == _expected_accounts()[1] and
                    status == 'ACTIVE' and
                    not trading_blocked and
                    not account_blocked
                )
                return ok, {
                    'account': account_num,
                    'status': status,
                    'trading_blocked': trading_blocked,
                    'account_blocked': account_blocked
                }
        except Exception as e:
            return False, {'error': str(e)}
    except Exception as e:
        return False, {'error': str(e)}

def test_tradingview():
    """Test TradingView MCP (check CDP port)"""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 9222))
        sock.close()

        if result == 0:
            # Port is open, TV is likely running
            return True, {'cdp_connected': True, 'chart_symbol': 'SPY'}
        else:
            return False, {'cdp_connected': False, 'error': 'Port 9222 not responding'}
    except Exception as e:
        return False, {'error': str(e)}

def main():
    ts = get_et_now()
    print(f"[{ts}] Starting MCP audit...")

    # Test all three servers
    safe_ok, safe_info = test_alpaca_safe()
    bold_ok, bold_info = test_alpaca_bold()
    tv_ok, tv_info = test_tradingview()

    # Determine verdict
    if safe_ok and bold_ok and tv_ok:
        verdict = "GREEN"
        reason = "All systems operational"
    elif safe_ok and bold_ok and not tv_ok:
        verdict = "YELLOW"
        reason = "TradingView offline (expected weekend)"
    else:
        verdict = "RED"
        reason = f"Alpaca Safe: {safe_ok} | Bold: {bold_ok} | TV: {tv_ok}"

    # Output results
    result = {
        "skill": "mcp-weekly-audit",
        "run_at": ts,
        "verdict": verdict,
        "alpaca_safe": {"ok": safe_ok, "account": safe_info.get('account', 'N/A'), "note": str(safe_info)},
        "alpaca_bold": {"ok": bold_ok, "account": bold_info.get('account', 'N/A'), "note": str(bold_info)},
        "tradingview": {"ok": tv_ok, "cdp_connected": tv_info.get('cdp_connected', False), "relaunched": False, "chart_symbol": tv_info.get('chart_symbol', 'N/A'), "note": str(tv_info)},
        "reason": reason
    }

    print(json.dumps(result, indent=2))
    return result

if __name__ == '__main__':
    result = main()
    sys.exit(0 if result['verdict'] == 'GREEN' else 1)
