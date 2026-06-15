"""One-shot helper for interactive Claude runs: injects Alpaca data fetched via MCP.

Usage from interactive Claude (after fetching Alpaca orders + account via MCP):
    python -m autoresearch.eod_deep.run_with_mcp_data \
      --date 2026-05-14 \
      --alpaca-data-file path/to/mcp_dump.json

Or call run_with_injected() directly with dicts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    REPO = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(REPO / "backtest"))
    from autoresearch.eod_deep import main as main_mod
else:
    from . import main as main_mod


def run_with_injected(date_str: str, mcp_dump: dict) -> dict:
    """Invoke main.run() with injected MCP data."""
    return main_mod.run(
        date_str=date_str,
        alpaca_orders=mcp_dump.get("alpaca_orders"),
        alpaca_account=mcp_dump.get("alpaca_account"),
        tv_chart_state=mcp_dump.get("tv_chart_state"),
        tv_screenshot_path=mcp_dump.get("tv_screenshot_path"),
        tv_ribbon=mcp_dump.get("tv_ribbon"),
    )


def main_cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--alpaca-data-file", required=True,
                   help="Path to JSON dump of MCP-fetched data")
    args = p.parse_args()
    dump = json.loads(Path(args.alpaca_data_file).read_text(encoding="utf-8"))
    result = run_with_injected(args.date, dump)
    print(f"=== EOD DEEP-DIVE for {args.date} (injected MCP data) ===")
    print(f"  Process score: {result['process_score']}/100")
    print(f"  Edge capture: {result['edge_capture_pct']}%")
    print(f"  Day P&L: ${result['day_pnl_dollars']:,.2f} ({result['day_pnl_pct']:+.2f}%)")
    print(f"  Trades: {result['day_trade_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
