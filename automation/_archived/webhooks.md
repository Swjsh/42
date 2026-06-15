# [ARCHIVED 2026-05-08] Webhook layer (Tier 2) — DEFERRED INDEFINITELY

> **STATUS: NOT BUILT, NOT ON ROADMAP.** This was the original Tier 2 plan from 2026-05-04 (replace 3-min polling lag with sub-30s event-driven entries via TradingView Pro alerts → Cloudflare Worker → file queue → heartbeat). Two weekends of optimization (2026-05-06 token-economy v3, 2026-05-08 doctrine layer optimization) made polling cost-effective enough that the webhook acceleration is no longer the highest-leverage next step.
>
> **Why deferred:**
> - **Cost.** Adds $14.95/month TradingView Plus on top of the $100/mo Max 5x plan. Not worth it for the latency saved unless live trading is fully ratified (which is gated on 20 paper trades + 4-of-4 thresholds — not yet).
> - **Polling cadence is now adaptive.** HOT mode fires every 3 min, BASE every 6, COOL every 9. With 15-min HTF override (`tickIndex % 5 == 1` always-fire) and HOT auto-elevation on score crossings, the worst-case lag is ≤ 6 min in BASE — not the 3-min worst case originally feared.
> - **Real entry latency floor.** Operating principle 11 + chart-level TP1 means the engine waits for bar close anyway. Sub-second alert delivery doesn't help if we wait for the close on a 5-min chart.
> - **Operational complexity.** Adds Cloudflare Worker + KV queue + alert payload validation + secret rotation. Each is a new failure mode in an autonomous system that's already self-healing 23 of 23 smoke tests.
>
> **When to reconsider:** if live deployment passes the 4-of-4 threshold AND J observes that morning entries are still firing 5+ minutes late on his eye-test, revisit Option B (Cloudflare Worker → file queue). Until then, this file is reference for the original architecture only.
>
> **Superseded by:** `automation/prompts/heartbeat.md` (the live polling engine) + `automation/loop-v2.md` (the adaptive cadence design).

---

# Webhook layer (Tier 2)

> Replaces 3-min polling lag with sub-30s event-driven entry triggers. Targeted ship: 1-2 weeks after Tier 1 is stable.

---

## Why webhooks

3-min polling means worst-case 3-min latency on entry. On 0DTE puts, where premium can move 30% in 3 minutes, that's significant. The 5/4 trade entry at 10:27 was already 2 minutes late on a clean signal — the price had moved $0.10 against us before fill.

Webhooks fix this. TradingView Pro+ supports server-side alert webhooks: when an indicator condition fires, TradingView POSTs a JSON payload to a URL we control. Latency: typically <5 seconds end-to-end.

---

## Three architecture options

### Option A — TradingView → Alpaca direct
**The simplest version.** TradingView alert fires → posts directly to Alpaca's webhook order endpoint (or to a service like Alertatron / Pickmytrade that translates).
- Pros: zero infrastructure on our side. Sub-2-second latency.
- Cons: zero visibility / no overrides. The alert IS the trade. Tight alert config required to avoid mis-fires.
- Best for: well-validated setups with low ambiguity.

### Option B — TradingView → Cloudflare Worker → file queue → heartbeat (recommended for Tier 2 launch)
**Most controllable.** TradingView alert → Cloudflare Worker (free tier, 30 LOC of JS) → writes the alert payload to a file in the trading rig's workspace folder via SSH or a webhook listener daemon. Next heartbeat tick (we drop interval to 30s when armed) reads the file, runs the playbook check with the alert as additional confirmation, decides.
- Pros: full visibility. Heartbeat still validates the alert against context filters and sizing math. We can A/B compare alert-driven vs polling-driven entries.
- Cons: ~5–30s latency depending on heartbeat tick alignment. Cloudflare Worker setup (one-time, ~30 min).

### Option C — TradingView → Cloudflare Worker → SSE/long-poll → heartbeat fires immediately
**Lowest-latency.** Worker pushes the event over SSE or long-poll to a daemon on the trading rig that wakes Claude Code immediately. Sub-2-second.
- Pros: speed.
- Cons: extra moving piece (the daemon). More to debug.

**Recommendation:** ship **Option B** for Tier 2. Migrate to A or C only after we trust the strategy.

---

## TradingView alerts to wire up

For the BEARISH_REJECTION_RIDE_THE_RIBBON setup:

1. **PRIMARY ENTRY ALERT:** EMA ribbon flips bullish → bearish on 3-min SPY. (The "Death Cross" indicator print on J's chart, but on the 3-min timeframe specifically.)
2. **SECONDARY ENTRY ALERT:** SPY closes a 3-min candle below a key intraday level (PMH, descending TL). Configurable per-day from premarket.
3. **EXIT ALERT (open position):** EMA ribbon flips bearish → bullish on 3-min SPY. (The "Golden Cross" print, exit-side.)
4. **EXIT ALERT (open position):** SPY closes a 3-min candle above the rejected entry level.

Each alert payload includes:
- timestamp
- symbol (SPY)
- timeframe (3m)
- alert type (e.g., `ribbon_flip_bearish`)
- current price
- additional context the alert can carry (level, candle close, etc.)

---

## Cloudflare Worker — sketch

```js
// Cloudflare Worker (free tier: 100k requests/day, plenty)
export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    
    // Verify TradingView shared secret
    const secret = request.headers.get("X-TV-Secret");
    if (secret !== env.TV_SHARED_SECRET) return new Response("Forbidden", { status: 403 });
    
    const body = await request.json();
    body.received_at = new Date().toISOString();
    
    // Forward to a long-running endpoint on J's rig (via Cloudflare Tunnel or static IP)
    // OR write to KV / R2 for the heartbeat to read on next tick
    await env.ALERT_QUEUE.put(`alert:${Date.now()}`, JSON.stringify(body), { expirationTtl: 600 });
    
    return new Response("OK", { status: 200 });
  },
};
```

Heartbeat reads from the KV queue on each tick:
```python
# pseudocode in the heartbeat
new_alerts = cloudflare_kv.list(prefix="alert:")
for alert in new_alerts:
    process_alert(alert)
    cloudflare_kv.delete(alert.key)
```

---

## Latency budget

| Step | Latency |
|---|---|
| TradingView indicator print → alert fire | 0–1s (real-time) |
| Alert HTTP POST → Cloudflare Worker | 100–500ms |
| Worker → KV write | 50–200ms |
| Heartbeat tick (worst case wait for next tick at 30s interval) | 0–30s |
| Heartbeat reads alert + decides | <2s |
| Alpaca paper order → fill | 100–500ms |
| **Total worst case (Option B)** | **~32 seconds** |
| **Total worst case (Option A)** | **~2 seconds** |
| **Total worst case (Option C)** | **~3 seconds** |

For comparison, Tier 1 polling worst case is **180 seconds (3 min)**.

---

## Cost

- Cloudflare Worker free tier: 100k requests/day. We'll use <1k/day.
- TradingView Pro+ for server-side alerts: $14.95/month (Essential plan does NOT include webhooks; need Plus or Premium).
- Alpaca paper API: free.

**Total Tier 2 ongoing: $14.95/month for TradingView Plus.**

---

## What Tier 2 doesn't change

- Sizing rules (still per `risk-rules.md`).
- Setup logic (still per `playbook.md`).
- Kill switch and circuit breaker (still authoritative).
- Journaling cadence.

The webhook layer is a *trigger source*, not a replacement for the heartbeat's discipline checks. Even an alert-driven entry runs the same context filter validation + sizing math + thesis logging that a polling-driven entry does. Speed without discipline = catastrophe.
