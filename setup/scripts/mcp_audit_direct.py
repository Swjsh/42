#!/usr/bin/env python3
"""MCP Weekly Audit — round-trip probes of live connections."""
import json, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

def get_et_now():
    return datetime.now(timezone.utc).isoformat()

def load_creds():
    data = json.loads(Path(r"C:\Users\jackw\Desktop\42\.mcp.json").read_text())
    safe = data.get("mcpServers", {}).get("alpaca", {}).get("env", {})
    bold = data.get("mcpServers", {}).get("alpaca_aggressive", {}).get("env", {})
    return safe, bold

def check_alpaca(creds, expected_acct):
    try:
        headers = {
            "APCA-API-KEY-ID": creds.get("ALPACA_API_KEY"),
            "APCA-API-SECRET-KEY": creds.get("ALPACA_SECRET_KEY"),
            "Content-Type": "application/json"
        }
        url = creds.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets") + "/v2/account"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5) as r:
            d = json.loads(r.read())
            acct = d.get("account_number", "")
            status = d.get("status", "")
            if acct == expected_acct and status == "ACTIVE":
                return True, f"{acct}"
            return False, f"acct={acct[:8]} status={status[:4]}"
    except Exception as e:
        return False, str(e)[:30]

def check_tv():
    try:
        with urllib.request.urlopen(urllib.request.Request("http://localhost:9222/json/version"), timeout=3) as r:
            return True, "CDP ok" if json.loads(r.read()).get("Browser") else False, "no Browser"
    except:
        return False, "port 9222"

def audit():
    ts = get_et_now()
    safe_env, bold_env = load_creds()
    safe_ok, safe_n = check_alpaca(safe_env, "PA3DHPT7KIQE")
    bold_ok, bold_n = check_alpaca(bold_env, "PA33W2KUAT40")
    tv_ok, tv_n = check_tv()
    verdict = "GREEN" if (safe_ok and bold_ok and tv_ok) else "RED"
    reason = f"safe={'ok' if safe_ok else 'FAIL'} bold={'ok' if bold_ok else 'FAIL'} tv={'ok' if tv_ok else 'FAIL'}"
    
    output = {
        "skill": "mcp-weekly-audit",
        "run_at": ts,
        "verdict": verdict,
        "alpaca_safe": {"ok": safe_ok, "account": "PA3DHPT7KIQE", "note": safe_n},
        "alpaca_bold": {"ok": bold_ok, "account": "PA33W2KUAT40", "note": bold_n},
        "tradingview": {"ok": tv_ok, "note": tv_n},
        "reason": reason
    }
    
    Path(r"C:\Users\jackw\Desktop\42\automation\state\mcp-weekly-audit-latest.json").write_text(json.dumps(output, indent=2))
    with open(r"C:\Users\jackw\Desktop\42\automation\state\mcp-weekly-audit-log.jsonl", "a") as f:
        f.write(json.dumps({"run_at": ts, "verdict": verdict, "reason": reason}) + "\n")
    
    if verdict == "RED":
        sp = Path(r"C:\Users\jackw\Desktop\42\automation\overnight\STATUS.md")
        if sp.exists():
            s = sp.read_text(encoding="utf-8")
            s = s.replace("## Known broken", f"## Known broken\n[{ts}] MCP_AUDIT_{verdict}: {reason}", 1)
            sp.write_text(s, encoding="utf-8")
        dp = Path(r"C:\Users\jackw\Desktop\42\automation\state\discord-outbox.jsonl")
        with open(dp, "a") as f:
            f.write(json.dumps({"queued_at": ts, "content": f"<@207983230618435584> MCP {verdict}: {reason}"}) + "\n")
    
    print(f"MCP-AUDIT {verdict} | safe={'ok' if safe_ok else 'FAIL'} bold={'ok' if bold_ok else 'FAIL'} tv={'ok' if tv_ok else 'FAIL'} | {reason}")
    return 0 if verdict == "GREEN" else 1

if __name__ == "__main__":
    sys.exit(audit())
