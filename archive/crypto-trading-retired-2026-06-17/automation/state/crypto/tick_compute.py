#!/usr/bin/env python3
"""Crypto heartbeat tick computation. Single-fire, no state persistence."""

import json
import sys
from datetime import datetime
from collections import deque

def ema(values, period):
    """Compute EMA over values (oldest first)."""
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = sum(values[:period]) / period
    for i in range(period, len(values)):
        ema_val = values[i] * k + ema_val * (1 - k)
    return ema_val

def atr(bars, period):
    """Compute ATR over bar dicts with 'h','l','c' keys. Bars oldest-first."""
    if len(bars) < period:
        return None
    trs = []
    for i in range(len(bars)):
        h = bars[i]['h']
        l = bars[i]['l']
        c = bars[i-1]['c'] if i > 0 else bars[i]['c']
        tr = max(h - l, abs(h - c), abs(l - c))
        trs.append(tr)
    k = 2.0 / (period + 1)
    atr_val = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr_val = trs[i] * k + atr_val * (1 - k)
    return atr_val

def rsi(values, period):
    """Compute RSI. Values oldest-first."""
    if len(values) < period + 1:
        return None
    deltas = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (gains[i] + avg_gain * (period - 1)) / period
        avg_loss = (losses[i] + avg_loss * (period - 1)) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

# Load bar data (passed as JSON)
bars_15m_data = json.loads(sys.stdin.read())
bars_15m_raw = bars_15m_data['bars_15m']
bars_1h_raw = bars_15m_data['bars_1h']

# Reverse to oldest-first
bars_15m = list(reversed(bars_15m_raw))
bars_1h = list(reversed(bars_1h_raw))

# Extract closes
closes_15m = [b['c'] for b in bars_15m]
closes_1h = [b['c'] for b in bars_1h]

# Compute 15m EMAs
ema_fast_15 = ema(closes_15m, 9)
ema_pivot_15 = ema(closes_15m, 21)
ema_slow_15 = ema(closes_15m, 50)

# Compute 1h EMAs
ema_fast_1h = ema(closes_1h, 9)
ema_slow_1h = ema(closes_1h, 50)

# Current prices
price_15m = closes_15m[-1]
price_1h = closes_1h[-1]

# Compute RSI and ATR on 15m
rsi_14 = rsi(closes_15m, 14)
atr_14 = atr(bars_15m, 14)

# Ribbon state
if ema_fast_15 > ema_pivot_15 > ema_slow_15:
    ribbon_15 = "BULL"
    stack_direction = "bull"
elif ema_fast_15 < ema_pivot_15 < ema_slow_15:
    ribbon_15 = "BEAR"
    stack_direction = "bear"
else:
    ribbon_15 = "CHOP"
    stack_direction = "chop"

# Count consecutive bars in current stack
stack_duration = 0
if ribbon_15 == "BULL":
    for i in range(len(closes_15m) - 1, -1, -1):
        idx = i
        if closes_15m[idx] > ema_pivot_15 and ema_fast_15 > ema_pivot_15 > ema_slow_15:
            # Check point estimate for this bar
            ema_fast_bar = ema(closes_15m[:idx+1], 9)
            ema_pivot_bar = ema(closes_15m[:idx+1], 21)
            ema_slow_bar = ema(closes_15m[:idx+1], 50)
            if ema_fast_bar and ema_pivot_bar and ema_slow_bar and ema_fast_bar > ema_pivot_bar > ema_slow_bar:
                stack_duration += 1
            else:
                break
        else:
            break
elif ribbon_15 == "BEAR":
    for i in range(len(closes_15m) - 1, -1, -1):
        idx = i
        if closes_15m[idx] < ema_pivot_15 and ema_fast_15 < ema_pivot_15 < ema_slow_15:
            ema_fast_bar = ema(closes_15m[:idx+1], 9)
            ema_pivot_bar = ema(closes_15m[:idx+1], 21)
            ema_slow_bar = ema(closes_15m[:idx+1], 50)
            if ema_fast_bar and ema_pivot_bar and ema_slow_bar and ema_fast_bar < ema_pivot_bar < ema_slow_bar:
                stack_duration += 1
            else:
                break
        else:
            break

# H1 trend
h1_bull = ema_fast_1h > ema_slow_1h if (ema_fast_1h and ema_slow_1h) else False
h1_bear = ema_fast_1h < ema_slow_1h if (ema_fast_1h and ema_slow_1h) else False

# Ribbon spread
spread_pct = 0
if ema_slow_15:
    spread_pct = abs(ema_fast_15 - ema_slow_15) / ema_slow_15 * 100 if ema_fast_15 and ema_slow_15 else 0

# Signal logic
signal = None
if ribbon_15 == "BULL" and stack_duration >= 2 and rsi_14 < 80 and spread_pct >= 0.05:
    signal = "LONG"
elif ribbon_15 == "BEAR" and stack_duration >= 2 and rsi_14 > 20 and spread_pct >= 0.05:
    signal = "SHORT"

# H1 filter gate
blocked_by = None
if signal == "LONG" and not h1_bull:
    blocked_by = "h1_trend_filter"
    signal = None
elif signal == "SHORT" and not h1_bear:
    blocked_by = "h1_trend_filter"
    signal = None

# Output
output = {
    "tick_time": bars_15m[-1]['t'],
    "price_15m": price_15m,
    "ema_fast_15": ema_fast_15,
    "ema_pivot_15": ema_pivot_15,
    "ema_slow_15": ema_slow_15,
    "ribbon_15": ribbon_15,
    "stack_duration": stack_duration,
    "stack_direction": stack_direction,
    "spread_pct": spread_pct,
    "rsi_14": rsi_14,
    "atr_14": atr_14,
    "ema_fast_1h": ema_fast_1h,
    "ema_slow_1h": ema_slow_1h,
    "h1_bull": h1_bull,
    "h1_bear": h1_bear,
    "signal": signal,
    "blocked_by": blocked_by
}

print(json.dumps(output, indent=2))
