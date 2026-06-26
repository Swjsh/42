#!/usr/bin/env python3
import sys
from datetime import datetime

# CONFIG
TICK_ID = 5
NOW_ET_UNIX = 1755948842
ACCOUNT = "Safe"
EQUITY = 2000
VIX_CURRENT = 17.53
RIBBON_STACK = "BEAR"
RIBBON_SPREAD = 96
TICKS_TODAY = 4

# MCP STUB DATA
bars = [
    {"time": 1755948000, "open": 591.50, "high": 592.10, "low": 591.40, "close": 591.85},
    {"time": 1755947700, "open": 591.60, "high": 591.95, "low": 591.50, "close": 591.75},
    {"time": 1755947400, "open": 591.75, "high": 592.00, "low": 591.60, "close": 591.70},
]

# R1 FILTER: Discard in-progress bar
def filter_closed_bars(bars, now_unix):
    closed_bars = []
    for bar in bars:
        bar_close_time = bar["time"] + (5 * 60)
        if bar_close_time <= now_unix:
            closed_bars.append(bar)
    return closed_bars

# SCORING
def score_bearish(bar_close, bar_open, ribbon_stack, ribbon_spread, vix_value):
    score = 0
    if ribbon_stack == "BEAR":
        score += 1
    if ribbon_spread > 90:
        score += 1
    if vix_value > 17.0:
        score += 1
    if bar_close < bar_open:
        score += 7
    return score

def score_bullish(bar_close, bar_open, ribbon_stack, ribbon_spread, vix_value):
    score = 0
    if ribbon_stack == "BULL":
        score += 1
    if ribbon_spread < 50:
        score += 1
    return score

# DECISION
def decide(bar_close, bar_open, ribbon_stack, ribbon_spread, vix_value):
    bear_score = score_bearish(bar_close, bar_open, ribbon_stack, ribbon_spread, vix_value)
    bull_score = score_bullish(bar_close, bar_open, ribbon_stack, ribbon_spread, vix_value)

    if bear_score > bull_score:
        action = "BEARISH"
        reason = f"Bear setup scored {bear_score}/10 vs Bull {bull_score}/11"
    elif bull_score > bear_score:
        action = "BULLISH"
        reason = f"Bull setup scored {bull_score}/11 vs Bear {bear_score}/10"
    else:
        action = "HOLD"
        reason = "Scores tied, no signal"

    return action, reason, bear_score, bull_score

# MAIN
closed_bars = filter_closed_bars(bars, NOW_ET_UNIX)
if not closed_bars:
    now_hm = datetime.fromtimestamp(NOW_ET_UNIX).strftime("%H:%M")
    print(f"HB#{TICK_ID} {now_hm} HOLD | spy=NA ribbon={RIBBON_SPREAD}c({RIBBON_STACK}) vix={VIX_CURRENT}(flat) bear=0/10 bull=0/11 | No closed bars")
    sys.exit(0)

last_bar = closed_bars[-1]
bar_close = last_bar["close"]
bar_open = last_bar["open"]

positions = []
if positions:
    now_hm = datetime.fromtimestamp(NOW_ET_UNIX).strftime("%H:%M")
    print(f"HB#{TICK_ID} {now_hm} HOLD | spy={bar_close} ribbon={RIBBON_SPREAD}c({RIBBON_STACK}) vix={VIX_CURRENT}(rising) bear=0/10 bull=0/11 | Position open")
    sys.exit(0)

action, reason, bear_score, bull_score = decide(bar_close, bar_open, RIBBON_STACK, RIBBON_SPREAD, VIX_CURRENT)

now_hm = datetime.fromtimestamp(NOW_ET_UNIX).strftime("%H:%M")
vix_dir = "rising" if VIX_CURRENT > 17.0 else "falling"

output = (
    f"HB#{TICK_ID} {now_hm} {action} | "
    f"spy={bar_close} ribbon={RIBBON_SPREAD}c({RIBBON_STACK}) vix={VIX_CURRENT}({vix_dir}) "
    f"bear={bear_score}/10 bull={bull_score}/11 | {reason}"
)
print(output)
