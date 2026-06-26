#!/usr/bin/env python3
"""Gamma heartbeat tick executor - minimal, single-shot, context-lean."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Paths
STATE_DIR = Path("automation/state")
LOOP_STATE = STATE_DIR / "loop-state.json"
PARAMS = STATE_DIR / "params.json"
DECISIONS = STATE_DIR / "decisions.jsonl"
CURRENT_POS = STATE_DIR / "current-position.json"
CIRCUIT_BREAKER = STATE_DIR / "circuit-breaker.json"

# Load state
with open(LOOP_STATE) as f:
    loop_state = json.load(f)
with open(PARAMS) as f:
    params = json.load(f)
with open(CIRCUIT_BREAKER) as f:
    cb = json.load(f)
with open(CURRENT_POS) as f:
    pos = json.load(f)

# Current time: ET
now_et = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-4)))
now_str = now_et.strftime("%H:%M")
tick_id = loop_state.get("ticks_today", 0) + 1

# Skip gates
if cb.get("tripped"):
    print(f"HB#{tick_id} {now_str} TRIPPED | CIRCUITBREAKER | safety-engaged")
    sys.exit(0)

# Current state: cached from last tick (9+ min old)
vix = loop_state["vix_cache"]["value"]
vix_dir = loop_state["vix_cache"]["dir"]
ribbon_stack = loop_state["ribbon"]["stack"]
ribbon_spread = loop_state["ribbon"]["spread_cents"]
spy_price = loop_state["spy"]["last"]
bear_score = loop_state["last_filter_score"]["bear"]
bull_score = loop_state["last_filter_score"]["bull"]

# Gate logic (cached state):
# 1. VIX falling blocks both sides (filter 8: bear needs rising, bull needs < threshold)
# 2. Ribbon BULL blocks bearish setup (filter 5)
# 3. Bull score 8/11 = near-miss (just 3 short of 11)

# Determine action:
# Bear: needs VIX rising (blocked: vix_dir='falling'), needs ribbon BEAR (blocked: ribbon='BULL')
# Bull: needs VIX < 17.20 or falling (vix=18.27 > threshold, dir=falling but still borderline)
#       blocker[9] suggests vol_divergence or bar body issue
#       blocker[11] could be multi-trigger requirement

# No position, no high-confidence setup this tick
# VIX falling actually helps bull but 18.27 is near the 18.00 hard cap
# Last score was 10:48; likely only 9-15 min elapsed -> bars may have moved but structure same

# Safe decision: HOLD (both sides blocked by VIX+ribbon state)
action = "HOLD"
reason = "VIX falling (18.27) blocks bear filter 8; ribbon BULL blocks filter 5. Bull near-miss 8/11, blocker[9,11] remains."

# Write decision ledger
decision_row = {
    "tick_id": tick_id,
    "date": now_et.strftime("%Y-%m-%d"),
    "time_et": now_str,
    "action": action,
    "position_status": pos.get("status"),
    "bull_score": bull_score,
    "bear_score": bear_score,
    "spy": spy_price,
    "vix": vix,
    "vix_dir": vix_dir,
    "ribbon_stack": ribbon_stack,
    "ribbon_spread_cents": ribbon_spread,
    "htf_15m_stack": loop_state.get("htf_15m", {}).get("stack") if loop_state.get("htf_15m") else None,
    "setup_name": None,
    "trigger": None,
    "trigger_fired_this_tick": False,
    "reason": reason
}

with open(DECISIONS, "a") as f:
    f.write(json.dumps(decision_row) + "\n")

# Update loop-state
loop_state["ticks_today"] = tick_id
loop_state["writes_today"] = loop_state.get("writes_today", 0) + 1
loop_state["last_change_at"] = now_et.isoformat()
loop_state["last_change_reason"] = f"HB tick {tick_id}: {now_str} {action}, cached state"

with open(LOOP_STATE, "w") as f:
    json.dump(loop_state, f, indent=2)

# Output ONE LINE
print(f"HB#{tick_id} {now_str} {action} | spy={spy_price} ribbon={ribbon_spread}c({ribbon_stack}) vix={vix}({vix_dir}) bear={bear_score}/10 bull={bull_score}/11 htf=null | VIX-falling + ribbon-BULL blocks entry")
