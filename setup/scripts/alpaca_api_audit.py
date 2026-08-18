#!/usr/bin/env python3
"""
Direct Alpaca REST API audit - bypasses MCP, tests accounts directly
"""
import json
import sys
import requests
from datetime import datetime, timezone

# SECURITY (2026-08-18): this block previously hardcoded FOUR live Alpaca credentials --
# two API keys and two SECRETS -- as plaintext module constants. The file is untracked (so
# they were never published) but it was NOT gitignored either, meaning a single `git add -A`
# in a repo that is PUBLIC would have pushed them. This rig has a documented history of
# index-absorption incidents (the reason setup/scripts/commit_scoped.py exists), so that was
# a live landmine, not a theoretical one. Now loaded at runtime from .mcp.json -- the ONLY
# credential store, per CLAUDE.md's non-negotiable secrets rule and the documented
# fast_path_executor.py pattern. Nothing secret remains in this file.
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[2]


def _load_creds():
    """(safe_key, safe_secret, bold_key, bold_secret) from .mcp.json. Fails LOUD if absent."""
    cfg = json.loads((_REPO / ".mcp.json").read_text(encoding="utf-8"))
    srv = cfg.get("mcpServers", {})
    safe = srv.get("alpaca", {}).get("env", {}) or {}
    bold = srv.get("alpaca_aggressive", {}).get("env", {}) or {}
    vals = (safe.get("ALPACA_API_KEY"), safe.get("ALPACA_SECRET_KEY"),
            bold.get("ALPACA_API_KEY"), bold.get("ALPACA_SECRET_KEY"))
    if not all(vals):
        print("Could not read Alpaca creds from .mcp.json -- refusing to continue.", file=sys.stderr)
        sys.exit(2)
    return vals


def _expected_accounts():
    """(safe, bold) account numbers from the FLEET REGISTRY -- never hardcoded.

    The literals that used to live below ("PA3DHPT7KIQE"/"PA33W2KUAT40") were never real
    account numbers -- a documentation transcription error copied into code -- so the
    equality check they fed could never be satisfied. Same defect class as the weekly MCP
    audit, which reported RED on every run for the same reason.
    """
    reg = json.loads((_REPO / "automation" / "state" / "fleet" / "accounts.json").read_text(encoding="utf-8"))
    by_id = {}
    for arm in reg.get("arms", []):
        aid = arm.get("id") or arm.get("arm_id")
        acct = arm.get("account_number")
        if aid and isinstance(acct, str):
            by_id.setdefault(str(aid), acct)
    return by_id.get("safe-2"), by_id.get("bold-2")


SAFE_KEY, SAFE_SECRET, BOLD_KEY, BOLD_SECRET = _load_creds()

BASE_URL = "https://paper-api.alpaca.markets"

def test_alpaca_account(api_key, secret_key, account_name):
    """Test Alpaca account via direct REST API"""
    result = {
        "name": account_name,
        "ok": False,
        "account_number": None,
        "status": None,
        "trading_blocked": None,
        "account_blocked": None,
        "note": ""
    }

    try:
        # SCAR (2026-08-18): this sent `Authorization: Bearer <api_key>`, which is NOT how
        # Alpaca authenticates -- it wants the APCA-API-KEY-ID / APCA-API-SECRET-KEY header
        # pair. `secret_key` was accepted as a parameter and then never used at all. Every
        # request therefore returned 401 and this audit could never report OK, under any
        # credentials -- the third independent "monitor that cannot go green" defect found in
        # this file today (the others: hardcoded creds, and phantom expected-account literals).
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

        # Test 1: GET /v2/clock
        try:
            r = requests.get(f"{BASE_URL}/v2/clock", headers=headers, timeout=5)
            if r.status_code != 200:
                result["note"] = f"Clock failed: {r.status_code}"
                return result
            clock_data = r.json()
            print(f"{account_name} clock: {clock_data.get('is_open')} | next_open: {clock_data.get('next_open')}", file=sys.stderr)
        except Exception as e:
            result["note"] = f"Clock call failed: {str(e)}"
            return result

        # Test 2: GET /v2/account
        try:
            r = requests.get(f"{BASE_URL}/v2/account", headers=headers, timeout=5)
            if r.status_code != 200:
                result["note"] = f"Account failed: {r.status_code}"
                return result
            acct = r.json()
            result["account_number"] = acct.get("account_number")
            result["status"] = acct.get("status")
            result["trading_blocked"] = acct.get("trading_blocked")
            result["account_blocked"] = acct.get("account_blocked")

            # Check health
            if (acct.get("status") == "ACTIVE" and
                not acct.get("trading_blocked") and
                not acct.get("account_blocked")):
                result["ok"] = True
                result["note"] = f"Account ACTIVE, account_number={acct.get('account_number')}"
                print(f"  ✓ {account_name} ALIVE: {acct.get('account_number')}", file=sys.stderr)
            else:
                result["note"] = f"Account blocked or inactive: status={acct.get('status')}, trading_blocked={acct.get('trading_blocked')}, account_blocked={acct.get('account_blocked')}"
                print(f"  ✗ {account_name} BLOCKED: {result['note']}", file=sys.stderr)
        except Exception as e:
            result["note"] = f"Account call failed: {str(e)}"
            print(f"  ✗ {account_name} error: {str(e)}", file=sys.stderr)
            return result

    except Exception as e:
        result["note"] = f"Exception: {str(e)}"
        print(f"  ✗ {account_name} exception: {str(e)}", file=sys.stderr)

    return result

print("Testing Alpaca Safe and Bold accounts via REST API...", file=sys.stderr)

safe_result = test_alpaca_account(SAFE_KEY, SAFE_SECRET, "Alpaca-Safe-2")
bold_result = test_alpaca_account(BOLD_KEY, BOLD_SECRET, "Alpaca-Bold-2")

# Expected accounts
expected_safe, expected_bold = _expected_accounts()

safe_match = safe_result["ok"] and safe_result["account_number"] == expected_safe
bold_match = bold_result["ok"] and bold_result["account_number"] == expected_bold

output = {
    "safe": safe_result,
    "bold": bold_result,
    "safe_ok": safe_match,
    "bold_ok": bold_match,
    "expected_safe": expected_safe,
    "expected_bold": expected_bold
}

print("\n" + json.dumps(output, indent=2))
