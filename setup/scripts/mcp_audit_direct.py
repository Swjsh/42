#!/usr/bin/env python3
"""MCP Weekly Audit — round-trip probes of live connections."""
import json, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def get_et_now():
    return datetime.now(timezone.utc).isoformat()

def expected_accounts():
    """(safe_acct, bold_acct) read from the FLEET REGISTRY -- never hardcoded.

    SCAR (2026-08-18): this module hardcoded "PA3DHPT7KIQE"/"PA33W2KUAT40" and compared the
    live API's account_number against them for equality. Those two strings were never real
    account numbers -- a documentation transcription error copied into code -- so the equality
    could NEVER be satisfied. Result: this audit returned RED on every single run regardless of
    real connection health, and (because RED fires a Discord alert and a STATUS.md write) it
    manufactured a recurring "engine red" notification with no underlying fault. Proven fired:
    automation/state/mcp-weekly-audit-log.jsonl:21 (2026-08-17).

    A monitor that cannot ever go green is worse than no monitor: it trains the operator to
    ignore the channel. Reading the expected value from the same registry the executors use
    means this check can only ever fail for a REAL mismatch.
    """
    reg = json.loads(REPO_ROOT.joinpath("automation", "state", "fleet", "accounts.json").read_text(encoding="utf-8"))
    by_id = {}
    for arm in reg.get("arms", []):
        aid = arm.get("id") or arm.get("arm_id")
        acct = arm.get("account_number")
        if aid and isinstance(acct, str):
            by_id.setdefault(str(aid), acct)
    return by_id.get("safe-2"), by_id.get("bold-2")


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
    """(ok, note). SCAR (2026-08-18): the success branch read

        return True, "CDP ok" if <cond> else False, "no Browser"

    which Python parses as a THREE-tuple -- (True, ("CDP ok" if cond else False), "no Browser")
    -- so the two-value unpack at the call site raised ValueError and killed the whole audit
    process. It therefore crashed on EVERY run where CDP was actually reachable, and only
    "worked" when TradingView was down (the except branch's genuine 2-tuple). Combined with the
    phantom-account equality above, this audit could not produce a GREEN verdict under any
    condition. Parenthesised and given an explicit branch.
    """
    try:
        req = urllib.request.Request("http://localhost:9222/json/version")
        with urllib.request.urlopen(req, timeout=3) as r:
            if json.loads(r.read()).get("Browser"):
                return True, "CDP ok"
            return False, "no Browser"
    except Exception as e:  # noqa: BLE001 -- a monitor must report, never raise
        return False, f"port 9222: {str(e)[:40]}"

def audit():
    ts = get_et_now()
    safe_env, bold_env = load_creds()
    safe_acct, bold_acct = expected_accounts()
    # Fail LOUD, not silently-green, if the registry itself can't answer.
    if not safe_acct or not bold_acct:
        safe_ok = bold_ok = False
        safe_n = bold_n = "registry missing safe-2/bold-2 account_number"
    else:
        safe_ok, safe_n = check_alpaca(safe_env, safe_acct)
        bold_ok, bold_n = check_alpaca(bold_env, bold_acct)
    tv_ok, tv_n = check_tv()
    verdict = "GREEN" if (safe_ok and bold_ok and tv_ok) else "RED"
    reason = f"safe={'ok' if safe_ok else 'FAIL'} bold={'ok' if bold_ok else 'FAIL'} tv={'ok' if tv_ok else 'FAIL'}"
    
    output = {
        "skill": "mcp-weekly-audit",
        "run_at": ts,
        "verdict": verdict,
        "alpaca_safe": {"ok": safe_ok, "account": safe_acct, "note": safe_n},
        "alpaca_bold": {"ok": bold_ok, "account": bold_acct, "note": bold_n},
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
