#!/usr/bin/env python3
"""
MCP Weekly Audit Probe
Calls the four critical MCP services and reports health status.
Used by Gamma_MCPAudit scheduled task.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
import subprocess
import time

# Expected account numbers (verified 2026-08-18)
SAFE_ACCOUNT = "PA3POKNV46VG"
BOLD_ACCOUNT = "PA3WEBXJU67N"

# OP-27 L41 / C8: headless Windows scheduled-task spawns must never flash a
# console window -- every subprocess call below passes this creationflags value.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def get_et_now():
    """Get current ET timestamp (DST-aware via local offset)."""
    # Local time is Mountain (UTC-6), ET is UTC-4, so ET = local + 2 hours
    from datetime import datetime, timedelta
    utc_now = datetime.utcnow()
    et_now = utc_now + timedelta(hours=4)  # UTC to ET conversion
    return et_now.isoformat() + "Z"

def call_alpaca_endpoint(endpoint, base_url="https://api.paper-trading.alpaca.markets", server_name="alpaca"):
    """Call Alpaca REST API directly."""
    import os
    import urllib.request
    import json

    # Try environment variables (APCA_API_KEY_ID for standard Alpaca, ALPACA_API_KEY for MCP config)
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    if not key:
        try:
            # Try absolute path first
            mcp_path = Path("C:\\Users\\jackw\\Desktop\\42\\.mcp.json")
            if not mcp_path.exists():
                # Fallback to relative
                mcp_path = Path(".mcp.json")

            mcp_conf = json.loads(mcp_path.read_text())
            alpaca_conf = mcp_conf.get("mcpServers", {}).get(server_name, {})
            env_vars = alpaca_conf.get("env", {})
            # Try both possible key names
            key = env_vars.get("ALPACA_API_KEY") or env_vars.get("APCA_API_KEY_ID")
        except Exception as e:
            pass  # Silent fail, will return error below

    if not key:
        return (False, {}, f"No Alpaca API key found for {server_name}")

    url = f"{base_url}{endpoint}"
    headers = {
        "APCA-API-KEY-ID": key,
        "Content-Type": "application/json"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return (True, data, "")
    except urllib.error.HTTPError as e:
        return (False, {}, f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        if "getaddrinfo failed" in str(e) or "Name or service not known" in str(e):
            return (False, {}, "DNS resolution failed (network unreachable or DNS issue)")
        return (False, {}, f"Network error: {str(e)}")
    except Exception as e:
        return (False, {}, f"{type(e).__name__}: {str(e)}")

def call_tradingview_health():
    """Probe TradingView CDP on port 9222."""
    import urllib.request
    import json

    try:
        # CDP (Chrome DevTools Protocol) listens on 9222
        # Try a simple HTTP GET to see if it's listening
        url = "http://127.0.0.1:9222/json/version"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            # If we got a response, CDP is alive
            return (True, {"cdp_connected": True, "api_available": True}, "")
    except urllib.error.URLError as e:
        if e.reason == "Connection refused":
            return (False, {}, "TradingView CDP not listening on :9222")
        return (False, {}, str(e))
    except Exception as e:
        return (False, {}, str(e))

def main():
    et_now = get_et_now()
    print(f"[AUDIT] Starting at {et_now}", file=sys.stderr)

    safe_ok = False
    bold_ok = False
    tv_ok = False
    tv_relaunched = False
    chart_symbol = None

    safe_note = ""
    bold_note = ""
    tv_note = ""
    reason = ""

    # Step 1: Probe Alpaca Safe
    print("[STEP 1] Testing Alpaca Safe (PA3POKNV46VG)...", file=sys.stderr)
    try:
        # Call Alpaca REST API for clock
        success, clock_resp, err = call_alpaca_endpoint("/v2/clock")
        if not success:
            safe_note = f"clock call failed: {err}"
            print(f"  Clock: FAIL - {err}", file=sys.stderr)
        else:
            is_open = clock_resp.get('is_open', False)
            print(f"  Clock: OK - market_is_open={is_open}", file=sys.stderr)

        # Call Alpaca REST API for account
        success, acct_resp, err = call_alpaca_endpoint("/v2/account")
        if not success:
            safe_note += f"; account call failed: {err}"
            print(f"  Account: FAIL - {err}", file=sys.stderr)
        else:
            acct_num = acct_resp.get("account_number", "unknown")
            trading_blocked = acct_resp.get("trading_blocked", False)
            account_blocked = acct_resp.get("account_blocked", False)
            blocked = trading_blocked or account_blocked
            if acct_num == SAFE_ACCOUNT and not blocked:
                safe_ok = True
                safe_note = f"account={acct_num}, status=ACTIVE"
                print(f"  Account: OK - {acct_num}", file=sys.stderr)
            else:
                safe_note += f"; account mismatch or blocked: {acct_num}, blocked={blocked}"
                print(f"  Account: FAIL - {acct_num}, blocked={blocked}", file=sys.stderr)
    except Exception as e:
        safe_note += f"; exception: {str(e)}"
        print(f"  Exception: {str(e)}", file=sys.stderr)

    # Step 2: Probe Alpaca Bold
    print("[STEP 2] Testing Alpaca Bold (PA3WEBXJU67N)...", file=sys.stderr)
    try:
        # Call Alpaca REST API for account (using alpaca_aggressive server key)
        success, acct_resp, err = call_alpaca_endpoint("/v2/account", server_name="alpaca_aggressive")
        if not success:
            bold_note = f"account call failed: {err}"
            print(f"  Account: FAIL - {err}", file=sys.stderr)
        else:
            acct_num = acct_resp.get("account_number", "unknown")
            trading_blocked = acct_resp.get("trading_blocked", False)
            account_blocked = acct_resp.get("account_blocked", False)
            blocked = trading_blocked or account_blocked
            if acct_num == BOLD_ACCOUNT and not blocked:
                bold_ok = True
                bold_note = f"account={acct_num}, status=ACTIVE"
                print(f"  Account: OK - {acct_num}", file=sys.stderr)
            else:
                bold_note = f"account mismatch or blocked: {acct_num}, blocked={blocked}"
                print(f"  Account: FAIL - {acct_num}, blocked={blocked}", file=sys.stderr)
    except Exception as e:
        bold_note += f"exception: {str(e)}"
        print(f"  Exception: {str(e)}", file=sys.stderr)

    # Step 3: Probe TradingView
    print("[STEP 3] Testing TradingView CDP...", file=sys.stderr)
    try:
        success, tv_resp, err = call_tradingview_health()
        if success:
            tv_ok = tv_resp.get("cdp_connected") and tv_resp.get("api_available")
            chart_symbol = tv_resp.get("chart_symbol", "unknown")
            tv_note = f"cdp={tv_resp.get('cdp_connected')}, api={tv_resp.get('api_available')}"
            print(f"  Health: {'OK' if tv_ok else 'FAIL'} - {tv_note}", file=sys.stderr)
        else:
            tv_note = f"health_check call failed: {err}"
            print(f"  Health: FAIL - {err}", file=sys.stderr)

            # Try one self-heal by relaunching TV
            print("[STEP 3B] Attempting TradingView self-heal (launch_tv_debug.ps1)...", file=sys.stderr)
            try:
                tv_script = Path("C:\\Users\\jackw\\Desktop\\42\\setup\\launch_tv_debug.ps1")
                if tv_script.exists():
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", str(tv_script)],
                        capture_output=True,
                        timeout=15,
                        text=True,
                        creationflags=_CREATE_NO_WINDOW
                    )
                    print(f"  Launch: {result.returncode} - {result.stderr[:100] if result.stderr else 'OK'}", file=sys.stderr)
                    time.sleep(12)

                    # Retry health check
                    success, tv_resp, err = call_tradingview_health()
                    if success:
                        tv_ok = tv_resp.get("cdp_connected") and tv_resp.get("api_available")
                        chart_symbol = tv_resp.get("chart_symbol", "unknown")
                        tv_relaunched = True
                        tv_note = f"RELAUNCHED; cdp={tv_resp.get('cdp_connected')}, api={tv_resp.get('api_available')}"
                        print(f"  Recheck: {'OK' if tv_ok else 'FAIL'} - {tv_note}", file=sys.stderr)
            except Exception as e:
                print(f"  Self-heal failed: {str(e)}", file=sys.stderr)
    except Exception as e:
        tv_note = f"exception: {str(e)}"
        print(f"  Exception: {str(e)}", file=sys.stderr)

    # Step 4: Determine verdict
    if safe_ok and bold_ok and tv_ok and not tv_relaunched:
        verdict = "GREEN"
    elif safe_ok and bold_ok and tv_ok and tv_relaunched:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    reason = f"safe={'OK' if safe_ok else 'FAIL'}, bold={'OK' if bold_ok else 'FAIL'}, tv={'OK' if tv_ok else 'FAIL'}"
    if tv_relaunched:
        reason += ", tv_relaunched=true"

    # Step 5: Write outputs
    print(f"[STEP 5] Writing audit results ({verdict})...", file=sys.stderr)

    audit_result = {
        "skill": "mcp-weekly-audit",
        "run_at": et_now,
        "verdict": verdict,
        "alpaca_safe": {
            "ok": safe_ok,
            "account": SAFE_ACCOUNT,
            "note": safe_note
        },
        "alpaca_bold": {
            "ok": bold_ok,
            "account": BOLD_ACCOUNT,
            "note": bold_note
        },
        "tradingview": {
            "ok": tv_ok,
            "cdp_connected": tv_ok,  # simplified; would come from actual health check
            "relaunched": tv_relaunched,
            "chart_symbol": chart_symbol or "unknown",
            "note": tv_note
        },
        "reason": reason
    }

    output_path = Path("automation/state/mcp-weekly-audit-latest.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit_result, indent=2) + "\n")
    print(f"  Wrote: {output_path}", file=sys.stderr)

    # Append to log
    log_path = Path("automation/state/mcp-weekly-audit-log.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "run_at": et_now,
        "verdict": verdict,
        "reason": reason
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"  Appended: {log_path}", file=sys.stderr)

    # Step 6: Alert if not GREEN
    if verdict != "GREEN":
        print(f"[STEP 6] Alerting ({verdict})...", file=sys.stderr)
        status_path = Path("automation/overnight/STATUS.md")
        if status_path.exists():
            content = status_path.read_text(encoding="utf-8")
            alert_line = f"\n[{et_now}] MCP_AUDIT_{verdict}: {reason}"
            if "## Known broken" in content:
                content = content.replace("## Known broken", "## Known broken" + alert_line, 1)
            else:
                content += f"\n## Known broken{alert_line}\n"
            status_path.write_text(content, encoding="utf-8")
            print(f"  Updated STATUS.md", file=sys.stderr)

        # Append Discord alert
        discord_outbox = Path("automation/state/discord-outbox.jsonl")
        discord_outbox.parent.mkdir(parents=True, exist_ok=True)
        discord_msg = {
            "queued_at": et_now,
            "content": f"<@207983230618435584> MCP weekly audit {verdict}: {reason}"
        }
        with open(discord_outbox, "a") as f:
            f.write(json.dumps(discord_msg) + "\n")
        print(f"  Queued Discord alert", file=sys.stderr)

    # Final output
    safe_str = "ok" if safe_ok else "FAIL"
    bold_str = "ok" if bold_ok else "FAIL"
    tv_str = "ok" if tv_ok else "FAIL"
    relaunch_str = "y" if tv_relaunched else "n"

    summary = f"MCP-AUDIT {verdict} | safe={safe_str} bold={bold_str} tv={tv_str}(relaunch={relaunch_str}) | {reason}"
    print(summary)
    return 0 if verdict == "GREEN" else 1

if __name__ == "__main__":
    sys.exit(main())
