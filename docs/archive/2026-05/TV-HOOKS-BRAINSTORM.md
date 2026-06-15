# TradingView Hooks — Brainstorm & Implementation Plan

> Authored 2026-05-15 evening per J directive: "maybe we need more TV hooks, brainstorm on this all and build it out effectively and cost efficient."

## The problem

The current MCP `alert_create` tool returns `success=false, source=dom_fallback` whenever TV desktop is idle/closed. That means our heartbeat can't push real-time alerts into TV from Claude, AND TV can't push alerts back to us without manual configuration. We've been polling TV at 3-minute intervals via the MCP server, which:

1. Costs tokens every poll (a chart-state call is ~2K tokens of input/output)
2. Misses level interactions that happen between polls (today's chart had ~8 interactions, engine traded once)
3. Cannot react in real-time to fast moves

## What "TV hooks" actually means

Three separate channels, each with different cost/latency/reliability:

| Channel | Direction | Latency | Token cost | Reliability |
|---|---|---|---|---|
| **A. MCP alert_create** | Claude → TV | seconds | low | broken when TV idle |
| **B. yfinance polling** | local → SPY price | 5–30 s | $0 | high (free) |
| **C. TV Pro webhook alerts** | TV → local server | seconds | $0 in pipe | requires TV Pro + local server |
| **D. TV Pine script alerts** | TV → notification | seconds | $0 | requires Pro for webhook delivery |
| **E. Polling via MCP** | Claude → TV (read) | tick-cadence | high | working |

## Recommendation: Three-layer stack

### L1 (shipped tonight) — yfinance level-cross daemon

**File:** `automation/scripts/level_alert_daemon.py`

Pure local Python. Polls `yf.Ticker("SPY").fast_info.last_price` every 30s during RTH. Compares to ★★+ levels in `key-levels.json`. Writes to `automation/state/live-alerts.jsonl` on:
- **Cross:** price moves from above→below or below→above a named level
- **Touch:** price enters the $0.15 proximity band of a level

**Token cost:** $0/day (no API calls).
**Latency:** 30s.
**Status:** Built tonight, single-tick test passed.
**Schedule:** Add to Windows Task Scheduler as `Gamma_LevelAlertDaemon` running 09:25 ET weekdays, max 6.75 hours.

### L2 (medium priority) — TV Pine script that fires alerts on chart events

**File to create:** `automation/scripts/tv_pine_alerts.pine`

Use TV's `alert()` function inside a Pine script to fire alerts when:
- Saty Pivot Ribbon flips BULL ↔ BEAR
- Spread crosses 30¢ threshold
- Bar wicks ≥ 33% of range (SHOTGUN T1 rejection signal)
- Volume spikes ≥ 1.5× 20-bar avg

Pine `alert()` can push to TV's notification system (sound, popup, email) or to a webhook URL (requires Pro+). For local-server route, the alert pushes JSON to `http://localhost:8089/tv_alert` which is consumed by a small Flask listener that appends to `live-alerts.jsonl`.

**Token cost:** $0 in the alert pipeline.
**Latency:** seconds.
**Status:** NOT BUILT TONIGHT (deferred — Pine + webhook server is ~3 hours of work).
**Dependency:** J needs TV Pro+ subscription for webhook delivery.

### L3 (low priority for now) — MCP alert_create reliability

The current `mcp__tradingview__alert_create` tool depends on TV desktop being **open and focused** for DOM automation. When TV is closed or in another tab, the tool silently fails with `source=dom_fallback`.

**Two paths to fix:**

1. **Auto-launch TV before alert_create.** The `Gamma_LaunchTV` scheduled task already opens TV at 08:00 ET. Add a hook before any `alert_create` call to verify TV is actually responsive — if not, send a desktop notification asking J to launch it.

2. **Replace DOM automation with TV's native alert API.** TradingView has a private API for alert management (used by the web app). Reverse-engineering it would be fragile. **Not recommended.**

**Recommendation:** Document the failure mode (already done in `MORNING-SUMMARY-2026-05-16.md`), set TV alerts manually for now, build L1 (shipped) and L2 (deferred).

## L1 daemon — wiring into heartbeat awareness

The heartbeat (`automation/prompts/heartbeat.md`) currently reads `automation/state/*.json` at the start of each tick. To make it aware of L1 alerts, add:

```
4a. read_last_alerts:
    Read last 5 entries of automation/state/live-alerts.jsonl.
    For each entry within the last 3 minutes:
      - If type=cross AND level_stars >= 3: include in alert digest
      - If type=touch AND level_stars >= 3: include for awareness
    Append to bias_note as "RECENT LEVEL ACTIVITY: <bullet list>"
```

This gives the heartbeat real-time level awareness without polling TV every tick. Cost: ~30 extra tokens per tick to read 5 JSON lines.

**Implementation deferred to Sunday** so today's overnight Stage 1 grinder gets clean run. Heartbeat prompt edit is small (~10 lines of new instruction) and reversible.

## Phase 2 — TV Pine script template

Below is the SKELETON of the Pine script L2 will use. Saving here for J review; J can paste into TV's Pine editor and tune the inputs.

```pinescript
//@version=5
indicator("Gamma SHOTGUN Alerts", overlay=true)

// === Inputs ===
fast_len   = input.int(8,  "Fast EMA")
pivot_len  = input.int(21, "Pivot EMA")
slow_len   = input.int(34, "Slow EMA")
spread_min = input.float(0.30, "Min ribbon spread $")
wick_frac  = input.float(0.33, "Min upper-wick fraction")
vol_mult   = input.float(1.5,  "Min volume ratio")

// === Ribbon ===
f = ta.ema(close, fast_len)
p = ta.ema(close, pivot_len)
s = ta.ema(close, slow_len)
spread = s - f
bear_stack = f < p and p < s and spread >= spread_min
bull_stack = f > p and p > s and -spread >= spread_min

// === Rejection candle detection ===
upper_wick = high - math.max(open, close)
rng = high - low
strong_reject = (upper_wick / rng) >= wick_frac and close < open

// === Volume spike ===
vol_baseline = ta.sma(volume, 20)
vol_spike = volume >= vol_baseline * vol_mult

// === Alerts ===
alertcondition(bear_stack and not bear_stack[1],
    title="Ribbon Flip BEAR",
    message='{"strategy":"shotgun","event":"ribbon_flip_bear","price":' + str.tostring(close) + ',"spread":' + str.tostring(spread) + '}')

alertcondition(strong_reject and vol_spike,
    title="SHOTGUN T1 Open Rejection",
    message='{"strategy":"shotgun","event":"open_rejection","price":' + str.tostring(close) + ',"open":' + str.tostring(open) + ',"wick":' + str.tostring(upper_wick) + ',"vol_ratio":' + str.tostring(volume/vol_baseline) + '}')

plot(f, "Fast", color=color.blue)
plot(p, "Pivot", color=color.orange)
plot(s, "Slow", color=color.red)
```

When J pastes this in and creates webhook alerts on each `alertcondition`, the events flow to whatever URL J configures. Local Flask listener would catch them at `POST http://localhost:8089/tv_alert` and append to `live-alerts.jsonl`.

## Cost-efficiency summary

| Component | Build time | Run-time token cost | Maintenance |
|---|---|---|---|
| L1 yfinance daemon | DONE | $0/day | Low — yfinance is stable |
| L2 Pine + Flask server | ~3 hours | $0/day | Medium — TV Pine changes occasionally |
| L3 MCP alert_create fix | Deferred | low ($0.01/alert) | High — DOM automation fragile |

**Recommendation:** ship L1 to scheduled task before Monday. Defer L2 to next weekend when J can confirm TV Pro+ status and pick a Flask hosting approach.

## Open questions for J

1. **TV subscription tier?** Webhook alerts (L2) need TV Pro+ ($14.95/mo) or above. If on basic TV, L2 is blocked and we rely on L1.
2. **Discord / phone push?** Currently alerts only go to `live-alerts.jsonl`. Want them also pinged to Discord (already integrated via the discord plugin) or via SMS/email?
3. **Level granularity?** L1 currently alerts on ★★+ levels. Want ★ (single-star) levels too, or is the noise floor too high?
4. **Frequency?** L1 polls every 30s. Want faster (10s — costs ~3× more yfinance calls) or slower (60s)?
