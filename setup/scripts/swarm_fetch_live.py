#!/usr/bin/env python3
"""
Live market data fetcher for swarm agents.
This runs in the Claude session context where MCP tools are available.
Fires at 06:00 ET, writes raw_data.json for all swarm agents.
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Output path
OUTPUT = Path(__file__).parent.parent.parent / "automation" / "swarm" / "state" / "raw_data.json"


def build_raw_data_stub():
    """Build minimal raw_data.json structure when MCP is unavailable."""
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat() + "Z",
        "spy_bars": None,
        "ribbon": None,
        "vix": None,
        "spy_context": None,
        "sectors": None,
        "rotation_signal": "mixed",
        "tv_data_available": False,
        "alpaca_data_available": False,
        "note": "This is a stub. In live environment with MCP connected, data would be populated here."
    }


def main():
    """Write raw_data.json stub."""
    try:
        # Ensure directory
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)

        # Build data
        data = build_raw_data_stub()

        # Write to file
        with open(OUTPUT, "w") as f:
            json.dump(data, f, indent=2)

        print(f"✓ raw_data.json written to {OUTPUT}")
        print(f"  Timestamp: {data['fetched_at']}")
        print(f"  TV: {data['tv_data_available']}, Alpaca: {data['alpaca_data_available']}")

        return 0

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
