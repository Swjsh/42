#!/usr/bin/env python3
"""
MCP Weekly Connection Audit — test Alpaca Safe/Bold and TradingView.
Headless, read-only. Writes results to automation/state/*.json
"""
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# Target accounts
SAFE_ACCT = "PA3POKNV46VG"
BOLD_ACCT = "PA3WEBXJU67N"

def get_et_iso():
    """Get current ET time in ISO format."""
    import pytz
    et = pytz.timezone('US/Eastern')
    return datetime.now(et).isoformat().replace('+00:00', 'Z').replace('+05:00', 'Z').replace('+04:00', 'Z')

def test_alpaca_safe():
    """Test Alpaca Safe via REST."""
    try:
        # Load env from .mcp.json
        mcp_config = json.load(open('.mcp.json'))
        alpaca_cfg = mcp_config['mcpServers']['alpaca']['env']

        import requests
        headers = {
            'APCA-API-KEY-ID': alpaca_cfg['ALPACA_API_KEY'],
            'APCA-API-SECRET-KEY': alpaca_cfg['ALPACA_SECRET_KEY'],
        }
        base_url = alpaca_cfg['ALPACA_BASE_URL']

        # Test clock
        clock_resp = requests.get(f"{base_url}/v1/clock", headers=headers, timeout=5)
        if clock_resp.status_code != 200:
            return {'ok': False, 'account': SAFE_ACCT, 'note': f'clock: {clock_resp.status_code}'}

        # Test account
        acct_resp = requests.get(f"{base_url}/v2/accounts", headers=headers, timeout=5)
        if acct_resp.status_code != 200:
            return {'ok': False, 'account': SAFE_ACCT, 'note': f'account: {acct_resp.status_code}'}

        acct_data = acct_resp.json()
        actual_acct = acct_data.get('account_number', 'UNKNOWN')

        if actual_acct != SAFE_ACCT:
            return {'ok': False, 'account': actual_acct, 'note': f'mismatch: expected {SAFE_ACCT}'}

        if acct_data.get('trading_blocked') or acct_data.get('account_blocked'):
            return {'ok': False, 'account': SAFE_ACCT, 'note': 'trading/account blocked'}

        return {'ok': True, 'account': SAFE_ACCT, 'note': 'healthy'}
    except Exception as e:
        return {'ok': False, 'account': SAFE_ACCT, 'note': str(e)[:50]}

def test_alpaca_bold():
    """Test Alpaca Bold via REST."""
    try:
        # Load env from .mcp.json
        mcp_config = json.load(open('.mcp.json'))
        bold_cfg = mcp_config['mcpServers']['alpaca_aggressive']['env']

        import requests
        headers = {
            'APCA-API-KEY-ID': bold_cfg['ALPACA_API_KEY'],
            'APCA-API-SECRET-KEY': bold_cfg['ALPACA_SECRET_KEY'],
        }
        base_url = bold_cfg['ALPACA_BASE_URL']

        # Test account
        acct_resp = requests.get(f"{base_url}/v2/accounts", headers=headers, timeout=5)
        if acct_resp.status_code != 200:
            return {'ok': False, 'account': BOLD_ACCT, 'note': f'account: {acct_resp.status_code}'}

        acct_data = acct_resp.json()
        actual_acct = acct_data.get('account_number', 'UNKNOWN')

        if actual_acct != BOLD_ACCT:
            return {'ok': False, 'account': actual_acct, 'note': f'mismatch: expected {BOLD_ACCT}'}

        if acct_data.get('trading_blocked') or acct_data.get('account_blocked'):
            return {'ok': False, 'account': BOLD_ACCT, 'note': 'trading/account blocked'}

        return {'ok': True, 'account': BOLD_ACCT, 'note': 'healthy'}
    except Exception as e:
        return {'ok': False, 'account': BOLD_ACCT, 'note': str(e)[:50]}

def test_tradingview():
    """Test TradingView via CDP."""
    try:
        import requests
        # Try to connect to CDP on 9222
        resp = requests.get('http://127.0.0.1:9222/json', timeout=5)
        if resp.status_code == 200:
            cdp_ok = True
        else:
            cdp_ok = False

        return {
            'ok': cdp_ok,
            'cdp_connected': cdp_ok,
            'relaunched': False,
            'chart_symbol': 'UNKNOWN',
            'note': 'CDP port reachable' if cdp_ok else 'CDP unreachable'
        }
    except Exception as e:
        return {
            'ok': False,
            'cdp_connected': False,
            'relaunched': False,
            'chart_symbol': 'UNKNOWN',
            'note': str(e)[:50]
        }

def main():
    iso_ts = get_et_iso()

    safe = test_alpaca_safe()
    bold = test_alpaca_bold()
    tv = test_tradingview()

    # Determine verdict
    safe_ok = safe.get('ok', False)
    bold_ok = bold.get('ok', False)
    tv_ok = tv.get('ok', False)

    if safe_ok and bold_ok and tv_ok:
        verdict = 'GREEN'
    elif (safe_ok and bold_ok) or tv_ok:
        verdict = 'YELLOW'
    else:
        verdict = 'RED'

    reason = ''
    if not safe_ok:
        reason += f"Safe:{safe['note']} "
    if not bold_ok:
        reason += f"Bold:{bold['note']} "
    if not tv_ok:
        reason += f"TV:{tv['note']} "

    reason = reason.strip() if reason else "all healthy"

    # Build output
    output = {
        "skill": "mcp-weekly-audit",
        "run_at": iso_ts,
        "verdict": verdict,
        "alpaca_safe": safe,
        "alpaca_bold": bold,
        "tradingview": tv,
        "reason": reason
    }

    # Write latest.json
    Path('automation/state').mkdir(parents=True, exist_ok=True)
    with open('automation/state/mcp-weekly-audit-latest.json', 'w') as f:
        json.dump(output, f, indent=2)

    # Append to log
    with open('automation/state/mcp-weekly-audit-log.jsonl', 'a') as f:
        log_line = json.dumps({
            "run_at": iso_ts,
            "verdict": verdict,
            "reason": reason
        })
        f.write(log_line + '\n')

    # Print result
    print(f"MCP-AUDIT {verdict} | safe={('ok' if safe_ok else 'FAIL')} bold={('ok' if bold_ok else 'FAIL')} tv={('ok' if tv_ok else 'FAIL')} | {reason}")

if __name__ == '__main__':
    main()
