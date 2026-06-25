"""ribbon_cli.py — CLI wrapper for ribbon_fallback.compute_ribbon().

Usage: python automation/scripts/ribbon_cli.py '[544.5, 544.8, ...]'
Input: JSON array of close prices (oldest→newest) as argv[1]
Output: JSON object on stdout; exit 0 on success (BULL/BEAR/MIXED), exit 1 if UNKNOWN or error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backtest" / "lib"))

from ribbon_fallback import compute_ribbon


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python ribbon_cli.py '<json_closes_array>'", file=sys.stderr)
        sys.exit(1)

    try:
        closes = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(f"JSON parse error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(closes, list):
        print("Input must be a JSON array of close prices", file=sys.stderr)
        sys.exit(1)

    if not closes:
        print("Empty closes array — cannot compute ribbon", file=sys.stderr)
        sys.exit(1)

    read = compute_ribbon([float(c) for c in closes])

    result = {
        "stack": read.stack,
        "price": read.price,
        "ema_fast": read.ema_fast,
        "ema_pivot": read.ema_pivot,
        "ema_slow": read.ema_slow,
        "sma_50": read.sma_50,
        "spread_cents": read.spread_cents,
        "bars_used": read.bars_used,
        "source": read.source,
    }
    print(json.dumps(result))

    if read.stack == "UNKNOWN":
        # Not enough bars to seed EMA — heartbeat treats this as fallback failed.
        sys.exit(1)


if __name__ == "__main__":
    main()
