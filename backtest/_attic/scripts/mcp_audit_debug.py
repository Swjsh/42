#!/usr/bin/env python3
"""MCP audit with detailed debugging."""
import json
import sys
from datetime import datetime, timezone
import requests
import subprocess

# ET now
et_now = datetime.now(timezone.utc).astimezone()
iso_ts = et_now.strftime('%Y-%m-%dT%H:%M:%S')

results = {
    "run_at": iso_ts,
    "safe_ok": False,
    "bold_ok": False,
    "tv_ok": False,
    "tv_relaunched": False,
    "chart_symbol": None,
    "process_check": {},
    "alpaca_safe_raw": None,
    "alpaca_bold_raw": None,
}

# Check processes
try:
    proc = subprocess.run(
        ["powershell", "-Command", "Get-Process alpaca-mcp* -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
        capture_output=True, text=True, timeout=2
    )
    results["process_check"]["alpaca_processes"] = proc.stdout.strip()
except:
    results["process_check"]["alpaca_check_error"] = "Could not check processes"

# === ALPACA SAFE ===
try:
    headers_safe = {
        "Authorization": "Bearer PKWEWC7NFCNLWI45M35ZBID46O",
    }
    resp = requests.get(
        "https://paper-api.alpaca.markets/v2/account",
        headers=headers_safe,
        timeout=5
    )
    results["alpaca_safe_raw"] = {
        "status_code": resp.status_code,
        "text_len": len(resp.text),
        "text_first_100": resp.text[:100],
        "headers": dict(resp.headers)
    }

    if resp.status_code == 200 and resp.text:
        try:
            acct_data = resp.json()
            expected_acct = "PA3POKNV46VG"
            actual_acct = acct_data.get("account_number", "UNKNOWN")

            if actual_acct == expected_acct:
                if not (acct_data.get("trading_blocked") or acct_data.get("account_blocked")):
                    results["safe_ok"] = True
                    results["safe_note"] = f"OK ({actual_acct})"
                else:
                    results["safe_note"] = "Account blocked"
            else:
                results["safe_note"] = f"Account mismatch: got {actual_acct}"
        except json.JSONDecodeError as e:
            results["safe_note"] = f"JSON parse error: {e}"
    else:
        results["safe_note"] = f"HTTP {resp.status_code}"
except Exception as e:
    results["safe_error"] = str(e)

# === ALPACA BOLD ===
try:
    headers_bold = {
        "Authorization": "Bearer PKEZ6OKPFVYBQC4YYGFF2A7EBN",
    }
    resp = requests.get(
        "https://paper-api.alpaca.markets/v2/account",
        headers=headers_bold,
        timeout=5
    )
    results["alpaca_bold_raw"] = {
        "status_code": resp.status_code,
        "text_len": len(resp.text),
        "text_first_100": resp.text[:100],
    }

    if resp.status_code == 200 and resp.text:
        try:
            acct_data = resp.json()
            expected_acct = "PA3WEBXJU67N"
            actual_acct = acct_data.get("account_number", "UNKNOWN")

            if actual_acct == expected_acct:
                if not (acct_data.get("trading_blocked") or acct_data.get("account_blocked")):
                    results["bold_ok"] = True
                    results["bold_note"] = f"OK ({actual_acct})"
                else:
                    results["bold_note"] = "Account blocked"
            else:
                results["bold_note"] = f"Account mismatch: got {actual_acct}"
        except json.JSONDecodeError as e:
            results["bold_note"] = f"JSON parse error: {e}"
    else:
        results["bold_note"] = f"HTTP {resp.status_code}"
except Exception as e:
    results["bold_error"] = str(e)

# === TRADINGVIEW ===
try:
    resp = requests.post(
        "http://localhost:9222/json/protocol",
        timeout=3
    )
    if resp.status_code == 200:
        results["tv_ok"] = True
        results["tv_note"] = "CDP responding"
except Exception as e:
    results["tv_error"] = str(e)

# Verdict
if results["safe_ok"] and results["bold_ok"] and results["tv_ok"]:
    verdict = "GREEN"
elif results["safe_ok"] and results["bold_ok"]:
    verdict = "YELLOW"
else:
    verdict = "RED"

results["verdict"] = verdict

print(json.dumps(results, indent=2))
sys.exit(0 if verdict == "GREEN" else 1)
