# D1 VIX-Gated Entry Filter — Implementation Spec

**Scorecard:** `analysis/recommendations/d1_vix_gated.json`  
**Status:** AUTO-RATIFY (all 5 OP-22 gates pass). READY TO SHIP — requires heartbeat state machine implementation.  
**Filed:** 2026-06-17

---

## What it is

When `VIX > 18.0` at 09:35 ET, instead of entering immediately when the engine fires an entry signal (current V0), the heartbeat waits up to 6 bars (30 minutes) for price to pull back to the trigger level and **bounce** (close > level AND green bar for calls; close < level AND red bar for puts). If the bounce happens within the window, enter. If the window expires, discard the signal — the move ran away or was a false signal.

When `VIX <= 18.0` (trending/calm regime): use V0 (immediate entry as today).

---

## Validation results

| Metric | Value | Gate | Status |
|--------|-------|------|--------|
| IS delta (high-VIX only) | +457.2/c | >0 | PASS |
| OOS delta (high-VIX only) | +393.1/c | >0 | PASS |
| WF_norm | 1.146 | ≥0.70 | PASS |
| SW_hurt | 1 (SW2 2025H2, -26.1/c) | ≤1 | PASS |
| Anchor no-regression | 0 D1 entries on anchor days, flat | required | PASS |

**Verdict: AUTO-RATIFY per OP-22.**

High-VIX regime context:
- IS high-VIX (119 days): V0=-453.2/c, D1=+4.0/c → +457.2/c improvement
- OOS high-VIX (48 days): V0=-113.8/c, D1=+279.3/c → +393.1/c improvement
- Low-VIX IS: V0 wins (+496.3/c) — correctly keep V0 there

---

## Best D1 parameters

```
window:    6 bars (30 minutes at 5-min bars)
prox_mult: 0.05 × ATR5  (min $0.05)
stop:      -20% premium stop
pl:        PLoff (trailing profit lock OFF)
```

ATR5 = average true range of prior 5 bars at the signal bar. Typical ATR5 = $0.30-0.60 for SPY 5min bars, so tolerance = $0.015-0.030 from the level. Very tight — requires a clean bounce at the level.

---

## Implementation design

### State machine (loop-state.json)

Add field `pending_d1_signal` to loop-state.json:

```json
{
  "pending_d1_signal": {
    "level": 525.40,
    "side": "C",
    "deadline_bar_count": 6,
    "bars_elapsed": 2,
    "signal_bar_time": "2026-06-17T10:15:00-04:00",
    "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "qty": 5,
    "account": "safe"
  }
}
```

`pending_d1_signal = null` means no pending signal.

### Heartbeat tick logic (pseudocode)

```python
vix_now = get_vix_reading_at_935()  # read once per session at 09:35

# --- On new engine signal ---
if new_signal and vix_now > 18.0:
    # VIX regime: queue D1 instead of entering immediately
    loop_state["pending_d1_signal"] = {
        "level": signal.level,
        "side": signal.side,
        "deadline_bar_count": 6,
        "bars_elapsed": 0,
        ...
    }
    log("D1 MODE: VIX=%.1f > 18. Queued signal at level %.2f. Waiting for pullback+bounce." % vix_now, signal.level)
elif new_signal and vix_now <= 18.0:
    # Trending regime: V0 — enter immediately (current production behavior)
    enter_trade(signal)

# --- On each tick: check pending D1 condition ---
if loop_state.get("pending_d1_signal") and not in_position():
    pending = loop_state["pending_d1_signal"]
    pending["bars_elapsed"] += 1
    
    if pending["bars_elapsed"] > pending["deadline_bar_count"]:
        # Expired — signal ran away or was false
        log("D1 signal expired after %d bars. Discarding." % pending["bars_elapsed"])
        loop_state["pending_d1_signal"] = None
    else:
        # Check D1 condition
        level = pending["level"]
        side = pending["side"]
        tol = max(0.05 * atr5(current_bar), 0.05)
        
        bounce_for_call = (bar.low <= level + tol and bar.close > level and bar.close > bar.open)
        bounce_for_put = (bar.high >= level - tol and bar.close < level and bar.close < bar.open)
        
        if (side == "C" and bounce_for_call) or (side == "P" and bounce_for_put):
            log("D1 condition MET. Entering at pullback bar.")
            enter_trade(pending)
            loop_state["pending_d1_signal"] = None
```

### Key implementation details

1. **VIX reading**: Read VIX at 09:35 ET on session start. Store in loop-state.json as `d1_vix_regime_today`. Do NOT re-read VIX intra-session (VIX changes during day but regime is set at open).

2. **Bar counting**: Each heartbeat tick = 1 bar (3-minute heartbeat but 5-minute SPY bars — reconcile: count heartbeat ticks as proxy for bars, OR wait until 5-minute bar close).

3. **Position guard**: If already in position from another account or if daily kill-switch is hit, cancel pending D1 signal.

4. **Signal expiry**: 6 bars = 30 minutes. If VIX signal fires at 09:40, deadline is 10:10 ET.

5. **Double-signal risk**: If engine fires a NEW signal while D1 is pending, overwrite the pending signal (newer signal is more current).

6. **Idempotency**: loop-state.json persists across heartbeat restarts. On cold start, if `pending_d1_signal` exists and deadline not expired, resume monitoring.

---

## Production params change

No params.json change needed. This is a heartbeat.md logic change only.

---

## Implementation checklist

- [ ] J reviews state machine design
- [ ] Add `pending_d1_signal` schema to loop-state.json
- [ ] Add VIX-regime read at session start (09:35 ET)
- [ ] Add D1 tick-monitoring logic in heartbeat.md
- [ ] Add D1 signal in aggressive heartbeat.md
- [ ] Test: simulate 3 ticks with VIX > 18, verify D1 state transitions
- [ ] Test: simulate expiry (6 bars, no bounce), verify signal discarded
- [ ] Test: VIX ≤ 18 path, verify V0 behavior unchanged
- [ ] Add gym validator: d1_entry_state_machine.py

---

## Risk of NOT implementing

Current production (V0 on all days):
- High-VIX IS: -453.2/c average
- High-VIX OOS: -113.8/c average (real money: ~-$340 on 37 OOS trades)

With D1 gate:
- High-VIX IS: +4.0/c average (+$457/c improvement)
- High-VIX OOS: +279.3/c average (+$393/c improvement)

Every VIX>18 day where the engine takes a signal is currently losing money with V0. D1 fixes this.
