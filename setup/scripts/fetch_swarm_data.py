#!/usr/bin/env python3
"""
Swarm data fetcher - fires at 06:00 ET to gather raw market data for swarm agents.
Calls TradingView MCP (port 9222) and Alpaca MCP to fetch all necessary data.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import time

# CREATE_NO_WINDOW: sys.executable is console-subsystem, which flashes a console on J's
# desktop without the flag when this script is spawned headlessly (OP-27 L41).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def run_tv_command(cmd_dict):
    """Execute a TradingView MCP command via CDP."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "json.tool"],
            input=json.dumps(cmd_dict),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        return json.loads(result.stdout) if result.returncode == 0 else None
    except Exception as e:
        print(f"TV command error: {e}", file=sys.stderr)
        return None


def fetch_tv_spy_data():
    """Fetch SPY OHLCV bars from TradingView MCP."""
    try:
        # This would normally use mcp client; for now return template
        return {
            "bars": None,
            "ribbon": None,
            "available": False
        }
    except Exception as e:
        print(f"TV data fetch error: {e}", file=sys.stderr)
        return {"bars": None, "ribbon": None, "available": False, "error": str(e)}


def fetch_alpaca_sector_data():
    """Fetch sector ETF data from Alpaca MCP."""
    try:
        # Template for Alpaca data
        return {
            "sectors": None,
            "available": False
        }
    except Exception as e:
        print(f"Alpaca data fetch error: {e}", file=sys.stderr)
        return {"sectors": None, "available": False, "error": str(e)}


def assemble_raw_data():
    """Assemble all raw market data into structured format."""

    utc_now = datetime.now(timezone.utc)
    et_tz = timezone(timedelta(hours=-4))  # EDT
    et_now = utc_now.astimezone(et_tz)

    raw_data = {
        "fetched_at": utc_now.isoformat(),
        "fetched_at_et": et_now.isoformat(),
        "spy_bars": None,
        "ribbon": {
            "fast": None,
            "pivot": None,
            "slow": None,
            "stack": None,
            "spread_cents": None
        },
        "vix": {
            "current": None,
            "direction": None,
            "iv_regime": None
        },
        "spy_context": {
            "current_price": None,
            "prior_session_close": None,
            "overnight_gap_dollars": None,
            "overnight_gap_dir": None,
            "premarket_high": None,
            "premarket_low": None
        },
        "sectors": {
            "XLK": {"close": None, "change_pct": None, "direction": None},
            "XLF": {"close": None, "change_pct": None, "direction": None},
            "XLE": {"close": None, "change_pct": None, "direction": None},
            "SPY": {"close": None, "change_pct": None, "direction": None}
        },
        "rotation_signal": None,
        "tv_data_available": False,
        "alpaca_data_available": False,
        "data_issues": []
    }

    # Attempt to fetch TradingView data
    tv_spy = fetch_tv_spy_data()
    if tv_spy.get("bars"):
        raw_data["spy_bars"] = tv_spy["bars"]
        raw_data["tv_data_available"] = True
    else:
        raw_data["data_issues"].append("TradingView SPY data unavailable")

    if tv_spy.get("ribbon"):
        raw_data["ribbon"] = tv_spy["ribbon"]

    # Attempt to fetch Alpaca data
    alpaca_data = fetch_alpaca_sector_data()
    if alpaca_data.get("sectors"):
        raw_data["sectors"] = alpaca_data["sectors"]
        raw_data["alpaca_data_available"] = True
    else:
        raw_data["data_issues"].append("Alpaca sector data unavailable")

    return raw_data


def main():
    """Main entry point - fetch all data and write to JSON."""

    output_dir = Path("automation/swarm/state")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "raw_data.json"

    # Assemble raw data
    raw_data = assemble_raw_data()

    # Write to file
    with open(output_file, "w") as f:
        json.dump(raw_data, f, indent=2)

    print(f"Raw data written to {output_file}")
    print(json.dumps(raw_data, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
