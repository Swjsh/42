#!/usr/bin/env python3
"""
Swarm data fetcher - gathers market data from TradingView and Alpaca MCPs
Writes to automation/swarm/state/raw_data.json for swarm agents to consume
"""
import json
import sys
from datetime import datetime, timezone, timedelta
import subprocess

# OP-27 L41 / C8: never let a headless (pythonw) scheduled task flash a conhost window.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def run_mcp_command(tool_name, params):
    """Execute an MCP tool via claude-cli"""
    try:
        cmd = ["claude", "mcp", tool_name]
        if params:
            cmd.extend([json.dumps(params)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                 creationflags=NO_WINDOW)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Error calling {tool_name}: {result.stderr}")
            return None
    except Exception as e:
        print(f"Exception calling {tool_name}: {e}")
        return None

def fetch_spy_data():
    """Fetch SPY OHLCV and ribbon data from TradingView"""
    data = {"tv_data_available": False, "spy_bars": None, "ribbon": None}

    try:
        # Set chart to BATS:SPY
        run_mcp_command("mcp__tradingview__chart_set_symbol", {"symbol": "BATS:SPY"})

        # Set timeframe to 5m
        run_mcp_command("mcp__tradingview__chart_set_timeframe", {"timeframe": "5"})

        # Get OHLCV bars (30 bars, individual bars not summary)
        bars_result = run_mcp_command("mcp__tradingview__data_get_ohlcv", {
            "count": 30,
            "summary": False
        })

        if bars_result and "bars" in bars_result:
            # Filter to last 20 closed bars
            bars = bars_result["bars"][-20:] if len(bars_result["bars"]) > 20 else bars_result["bars"]
            data["spy_bars"] = bars

            # Get current price from first bar (or latest quote)
            if bars:
                current_price = bars[-1].get("close", 0)
                data["spy_context"] = {
                    "current_price": current_price,
                    "prior_session_close": None,
                    "overnight_gap_dollars": None,
                    "overnight_gap_dir": "flat",
                    "premarket_high": None,
                    "premarket_low": None
                }

        # Get ribbon values (Fast EMA, Pivot EMA, Slow EMA)
        ribbon_result = run_mcp_command("mcp__tradingview__data_get_study_values", {})

        if ribbon_result:
            # Extract EMA values if available
            # Look for "Fast EMA", "Pivot EMA", "Slow EMA" or similar
            ribbon = {
                "fast": None,
                "pivot": None,
                "slow": None,
                "stack": "MIXED",
                "spread_cents": 0
            }

            # Parse study values
            if isinstance(ribbon_result, dict):
                for key, val in ribbon_result.items():
                    if "fast" in key.lower():
                        ribbon["fast"] = val
                    elif "pivot" in key.lower():
                        ribbon["pivot"] = val
                    elif "slow" in key.lower():
                        ribbon["slow"] = val

            # Compute stack
            if ribbon["fast"] is not None and ribbon["pivot"] is not None and ribbon["slow"] is not None:
                if ribbon["fast"] > ribbon["pivot"] > ribbon["slow"]:
                    ribbon["stack"] = "BULL"
                    ribbon["spread_cents"] = round((ribbon["fast"] - ribbon["slow"]) * 100)
                elif ribbon["fast"] < ribbon["pivot"] < ribbon["slow"]:
                    ribbon["stack"] = "BEAR"
                    ribbon["spread_cents"] = round((ribbon["slow"] - ribbon["fast"]) * 100)

            data["ribbon"] = ribbon

        data["tv_data_available"] = True
    except Exception as e:
        print(f"Error fetching SPY data: {e}")

    return data

def fetch_vix_data():
    """Fetch VIX quote from TradingView"""
    vix_data = {"current": None, "direction": "flat", "iv_regime": "MID"}

    try:
        # Switch to VIX
        run_mcp_command("mcp__tradingview__chart_set_symbol", {"symbol": "TVC:VIX"})

        # Get VIX quote
        vix_result = run_mcp_command("mcp__tradingview__quote_get", {"symbol": "TVC:VIX"})

        if vix_result:
            current = vix_result.get("last", None)
            change_pct = vix_result.get("change_pct", 0)

            if current:
                vix_data["current"] = current

                # Determine direction
                if change_pct > 0.5:
                    vix_data["direction"] = "rising"
                elif change_pct < -0.5:
                    vix_data["direction"] = "falling"

                # Determine regime
                if current < 15:
                    vix_data["iv_regime"] = "LOW"
                elif current > 22:
                    vix_data["iv_regime"] = "HIGH"

        # Switch back to SPY
        run_mcp_command("mcp__tradingview__chart_set_symbol", {"symbol": "BATS:SPY"})

    except Exception as e:
        print(f"Error fetching VIX data: {e}")

    return vix_data

def fetch_sector_data():
    """Fetch sector ETF data from Alpaca"""
    sectors_data = {
        "XLK": None,
        "XLF": None,
        "XLE": None,
        "SPY": None
    }
    rotation = "mixed"
    alpaca_available = False

    try:
        # Get 3 days of 1Day bars for sectors
        bars_result = run_mcp_command("mcp__alpaca__get_stock_bars", {
            "symbols": "XLK,XLF,XLE,SPY",
            "timeframe": "1Day",
            "limit": 12,
            "days": 3
        })

        if bars_result:
            alpaca_available = True

            # Extract most recent bar for each symbol
            for symbol in ["XLK", "XLF", "XLE", "SPY"]:
                if symbol in bars_result:
                    bars = bars_result[symbol]
                    if bars:
                        latest = bars[-1]
                        open_price = latest.get("open", 0)
                        close_price = latest.get("close", 0)

                        if open_price > 0:
                            change_pct = ((close_price - open_price) / open_price) * 100
                        else:
                            change_pct = 0

                        direction = "up" if change_pct > 0.3 else ("down" if change_pct < -0.3 else "flat")

                        sectors_data[symbol] = {
                            "close": close_price,
                            "change_pct": round(change_pct, 2),
                            "direction": direction
                        }

            # Determine rotation signal
            if (sectors_data["XLK"] and sectors_data["XLK"]["direction"] == "up" and
                sectors_data["SPY"] and sectors_data["SPY"]["direction"] == "up"):
                rotation = "risk_on"
            elif (sectors_data["XLF"] and sectors_data["XLF"]["direction"] == "up" and
                  sectors_data["SPY"] and sectors_data["SPY"]["direction"] == "down"):
                rotation = "risk_off"

    except Exception as e:
        print(f"Error fetching sector data: {e}")

    return sectors_data, rotation, alpaca_available

def main():
    """Main fetcher routine"""
    print(f"Starting data fetch at {datetime.now(timezone.utc).isoformat()}")

    # Fetch all data
    spy_data = fetch_spy_data()
    vix_data = fetch_vix_data()
    sectors_data, rotation, alpaca_available = fetch_sector_data()

    # Assemble raw_data.json
    raw_data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "spy_bars": spy_data.get("spy_bars"),
        "ribbon": spy_data.get("ribbon"),
        "vix": vix_data,
        "spy_context": spy_data.get("spy_context"),
        "sectors": sectors_data,
        "rotation_signal": rotation,
        "tv_data_available": spy_data.get("tv_data_available", False),
        "alpaca_data_available": alpaca_available
    }

    # Ensure output directory exists
    import os
    output_dir = "automation/swarm/state"
    os.makedirs(output_dir, exist_ok=True)

    # Write JSON
    output_file = os.path.join(output_dir, "raw_data.json")
    with open(output_file, "w") as f:
        json.dump(raw_data, f, indent=2)

    print(f"Data written to {output_file}")
    print(f"TV available: {raw_data['tv_data_available']}, Alpaca available: {raw_data['alpaca_available']}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
