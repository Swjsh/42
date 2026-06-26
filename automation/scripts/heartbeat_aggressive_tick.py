#!/usr/bin/env python3
"""
Gamma aggressive heartbeat tick evaluator.
Reads state, evaluates filters, outputs single-line decision.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

def load_json(path):
    """Load JSON state file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Failed to load {path}: {e}", file=sys.stderr)
        return None

def main():
    now_et = datetime.now(timezone.utc).astimezone()  # Local time (ET expected)
    now_et_str = now_et.strftime("%H:%M")
    now_et_min = now_et.hour * 60 + now_et.minute

    base = Path("automation/state")

    # Load state files
    loop_state = load_json(base / "aggressive/loop-state.json")
    breaker = load_json(base / "aggressive/circuit-breaker.json")
    position = load_json(base / "current-position-bold.json")
    bias = load_json(base / "today-bias.json")
    levels = load_json(base / "key-levels.json")

    if not all([loop_state, breaker, position, bias, levels]):
        print("ERROR_STATE_LOAD")
        return

    # Skip gates
    if Path(base / "kill-switch").exists():
        print(f"HB-AGG#{loop_state['ticks_today']} {now_et_str} PAUSED | State files failed validation")
        return

    if breaker.get("tripped"):
        print(f"HB-AGG#{loop_state['ticks_today']} {now_et_str} TRIPPED | Daily loss limit hit")
        return

    # Current state
    flat = position.get("status") is None
    ribbon = loop_state.get("ribbon", {})
    vix = loop_state.get("vix_cache", {})

    # Scores from last update
    scores = loop_state.get("last_filter_score", {})
    bull_score = scores.get("bull", 0)
    bear_score = scores.get("bear", 0)

    # VIX info
    vix_val = vix.get("value", 0)
    vix_dir = vix.get("dir", "unknown")

    # Ribbon info
    ribbon_stack = ribbon.get("stack", "UNKNOWN")
    ribbon_spread = ribbon.get("spread_cents", 0)
    ribbon_fast = ribbon.get("fast", 0)
    ribbon_slow = ribbon.get("slow", 0)

    # Price
    spy_price = loop_state.get("spy", {}).get("last", 0)

    # HTF
    htf = loop_state.get("htf_15m")
    htf_stack = htf.get("stack") if htf else None

    # Position state string
    pos_status = "open" if position.get("status") == "open" else ("pending_fill" if position.get("status") == "pending_fill" else None)

    # Setup name
    setup_name = loop_state.get("developing_setup")

    # Decision logic
    action = "HOLD"
    reason = ""

    # Check for near-miss or developing setup
    if bull_score >= 9 or bear_score >= 8:
        if bull_score >= bear_score:
            action = "HOLD_DEV"
            reason = f"bull_near_miss({bull_score}/11)"
        else:
            action = "HOLD_DEV"
            reason = f"bear_near_miss({bear_score}/10)"
    else:
        reason = f"standard_hold bull={bull_score} bear={bear_score}"

    # Output one line
    output = (
        f"HB-AGG#{loop_state['ticks_today']} {now_et_str} {action} | "
        f"spy={spy_price:.2f} ribbon={ribbon_stack}({ribbon_spread}c) "
        f"vix={vix_val:.2f}({vix_dir}) bull={bull_score}/11 bear={bear_score}/10 "
        f"htf={htf_stack or 'null'} | {reason}"
    )
    print(output)

if __name__ == "__main__":
    main()
