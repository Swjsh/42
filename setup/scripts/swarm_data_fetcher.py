#!/usr/bin/env python3
"""
Swarm data fetcher — fires at 06:00 ET to gather all raw market data
that the swarm specialist agents will need.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# CREATE_NO_WINDOW: sys.executable is console-subsystem, which flashes a console on J's
# desktop without the flag when this script is spawned headlessly (OP-27 L41).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Try TradingView and Alpaca API calls
def fetch_data():
    """Fetch all market data and return structured JSON."""

    utc_now = datetime.now(timezone.utc)
    et_tz = timezone(timedelta(hours=-4))  # EDT
    et_now = utc_now.astimezone(et_tz)

    result = {
        "fetched_at": utc_now.isoformat(),
        "fetched_at_et": et_now.isoformat(),
        "spy_bars": None,
        "ribbon": None,
        "vix": None,
        "spy_context": None,
        "sectors": None,
        "rotation_signal": None,
        "tv_data_available": False,
        "alpaca_data_available": False,
        "errors": []
    }

    # Try to fetch SPY 5m bars from TradingView
    try:
        import subprocess
        tv_result = subprocess.run(
            [
                sys.executable, "-m", "json.tool"
            ],
            input=json.dumps({"action": "tv_fetch_spy_5m"}),
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        # This is a placeholder - in production, would use the MCP client
        result["errors"].append("TradingView MCP not directly callable from script context")
    except Exception as e:
        result["errors"].append(f"TV fetch error: {str(e)}")

    # Try to fetch Alpaca sector data
    try:
        # This would call Alpaca MCP
        result["errors"].append("Alpaca MCP not directly callable from script context")
    except Exception as e:
        result["errors"].append(f"Alpaca fetch error: {str(e)}")

    # For now, return a template so the file exists
    return result


if __name__ == "__main__":
    data = fetch_data()

    output_path = Path("automation/swarm/state/raw_data.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Data written to {output_path}")
    print(json.dumps(data, indent=2))
