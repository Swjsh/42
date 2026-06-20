# 2-min Cadence Architecture — brainstorm for J

> Question: J wants chart reads every 2 min instead of every 6 min. Can we hit that without busting the $100/mo Max 5x plan?
>
> Date: 2026-05-18 evening
> Author: Gamma autonomous (per OP-25 engine-benefit autonomy)

## What J literally asked for

> "I need chart reads ever 2 minutes not every 6 minutes. if we need to increase the plan we can. if we cant utilize pthon > webhook for free? idk brainstorm this. need gamma watching like a human trader"

## What's running today

| Layer | Cadence | Cost/day | Cost/mo | LLM? |
|---|---|---:|---:|:-:|
| L1 — heartbeat (production trader, places orders) | every 3 min, 09:30-15:55 ET | ~$5.50 (110 ticks × $0.05) | ~$118 | Yes — Haiku 4.5 |
| L2 — watcher fleet (Python only) | every 5 min | $0 | $0 | No |
| L3 — vision observer (chart screenshot + 6Q framework) | every 6 min, 09:30-15:55 ET | ~$3.20 (64 ticks × $0.05) | ~$67 | Yes — Haiku 4.5 |
| **Total LLM in market hours** | — | **~$8.70** | **~$185** | — |

Note the budget today is already ~$185/mo just for live-tick LLM work — almost 2× the $100/mo Max 5x cap. We're surviving on rate-limit headroom + the assumption not every fire spends $0.05.

## Three categories of 2-min "chart reads"

The user's request collapses three different things into one phrase. Each has a different cost profile:

### A) **Numeric chart reads** — pure-Python detectors on OHLCV
- 6 pattern detectors today (double_bottom, double_top, failed_breakdown_wick, rejection_at_level, momentum_acceleration, inside_bar_consolidation) plus the v15 heartbeat numeric rubric (RSI, MACD, EMA stack, VWAP, regime, levels).
- Cost: **$0/fire** (no LLM). 
- Latency: ~50-300ms per detector pass.
- Can fire every minute, every 30 seconds, every 5 seconds — bounded only by SPY bar granularity (we get 1m and 5m bars from yfinance/Alpaca for free).

### B) **Vision chart reads** — LLM looks at the rendered chart image (TV MCP screenshot + 6Q framework)
- L3 Vision Observer today, calling `Haiku 4.5` per fire.
- Cost: **~$0.05/fire** (image input + ~400 output tokens).
- Latency: ~3-10s per fire including screenshot capture.

### C) **Decision-engine ticks** — LLM scoring + decision + (potentially) order placement
- L1 Heartbeat today, calling `Haiku 4.5` (escalates to Sonnet on edge cases).
- Cost: **~$0.05-0.15/fire** depending on Sonnet escalation rate.
- Latency: ~30-60s per fire including TV MCP + Alpaca MCP roundtrips.

## Options ranked by cost-effectiveness

### Option 1: HYBRID 1m+6m — recommended

Add a **1-minute numeric tick** (free, every 60s) that runs ALL pattern detectors + contra-trend filter + level-proximity check + momentum-acceleration. Keep vision observer at 6-min (no change to budget). Keep heartbeat at 3-min (no change).

**What it gets us:**
- Every minute Gamma evaluates ~12 numeric signals against latest closed 5m bar (and intra-minute 1m bar context).
- When ≥ 2 high-confidence signals fire at the same minute, write to `automation/state/numeric-alert.jsonl`.
- Heartbeat's next 3-min tick reads any unconsumed alerts from `numeric-alert.jsonl` — gives it 2 vs 6-min freshness on signal recognition without spending an extra LLM tick.
- Vision observer's next 6-min tick can also consume this alert ledger (giving the LLM a hint "numeric just saw failed_breakdown_wick at 14:32" so it knows where to look).

**Cost: $0 incremental.** Just a new scheduled task `Gamma_NumericPulse1m` firing every 1 min during market hours, running pattern_backtest in "single-bar" mode against the latest closed bar.

**Coverage of "watching like a human trader":**
- 1m numeric detection of pattern completion: ✅ every minute
- Vision-level qualitative read: ❌ still 6 min cadence
- Decision-engine ticks: ❌ still 3 min cadence
- **Net: 3x improvement on signal *recognition*, no improvement on signal *interpretation*.**

### Option 2: Push vision observer to 3-min (match heartbeat cadence)

Drop vision interval 6m → 3m: 64 fires/day → 128 fires/day = ~$6.40/day = ~$140/mo on vision alone. Total LLM in market hours: ~$310/mo. Over budget by 3×.

**Mitigation:** drop vision to **Haiku 3.5** (cheaper) and shorter prompts (200 tokens output instead of 400). Estimate ~$0.025/fire. 128 fires × $0.025 = $3.20/day = $67/mo on vision. Total: ~$185/mo (same as today). No budget hit, 2× cadence.

**Coverage:**
- Vision-level qualitative read: ✅ every 3 min
- Numeric detection: ❌ still 6-min (lazy, unless we also add Option 1)
- Decision-engine ticks: ❌ still 3 min cadence
- **Net: Marginal improvement on *interpretation* freshness, none on numeric detection.**

### Option 3: TradingView webhook → local Python endpoint

J has TradingView. If J has **TV Pro** (or higher), Pine alerts can webhook to any URL. We'd run a Flask/FastAPI on `localhost:8765`, register a Pine alert per pattern (`alert("DOUBLE_BOTTOM", ...)`), and consume webhook payloads at TradingView's native cadence (which can be down to 1 fire per second on Premium, 1 per minute on Pro).

**Cost: $0 incremental** (local server, free).
**Latency: ~50ms from TV alert → local DB row.**
**Coverage: depends on what we encode in Pine** — we can do all 6 detectors in Pine v6 (already proven via existing TV indicators).

**Pros:**
- Authoritative TV bar boundaries (no yfinance lookahead bugs).
- Sub-second latency vs cron-based 1-min poll.
- Can trigger heartbeat ALERT BAR via cross-process signal — heartbeat reads the alert ledger on every tick.

**Cons:**
- Requires Pine porting of all 6 detectors (1-2 hours each — already largely written in `chart_patterns.py`, needs Pine translation).
- Pine compiles slowly; pinescript-mcp is in repo but heavy.
- TV Premium ($60/mo) is the standard tier that opens webhook + sub-second alerts. TV Pro ($15/mo) only does 1-per-minute alerts.

**Verdict: Option 3 is a STRATEGIC upgrade once we know which signals matter most. Today the bottleneck is signal-recognition latency at minute scale, not sub-second. Defer until Option 1 + Option 2 are proven.**

### Option 4: Anthropic plan upgrade

Max 5x = $100/mo. Max 20x = $250/mo, gives ~5× the message volume.

| Upgrade | Cost | Headroom for new ticks |
|---|---|---|
| Max 5x → Max 20x ($250/mo) | +$150/mo | ~$165/mo new LLM budget = 3300 extra Haiku ticks = ~50 extra ticks/day during market |

**Verdict: makes sense ONLY if Option 1 and Option 3 don't close the gap.**

## Recommendation (single proposal, ratification needed)

**Ship Option 1 today (free). Hold Options 2-4 in reserve.**

### Concrete plan
1. **Build `Gamma_NumericPulse1m`** — fires every 1 min during 09:30-15:55 ET. Calls a new script `backtest/autoresearch/numeric_pulse.py` that:
   - Fetches latest closed 5m bar via yfinance (or Alpaca crypto MCP for crypto, this is just SPY).
   - Runs all 6 pattern detectors + contra-trend filter on the trailing 78 bars.
   - Writes to `automation/state/numeric-alert.jsonl` if ≥ 1 high-confidence (≥ 0.65) hit AND contra-trend AND key-level proximate.
   - Writes ALL hits (even low-conf) to `automation/state/numeric-pulse.jsonl` for forensics + grader.
2. **Update heartbeat doctrine** — `heartbeat.md` Step 2.5 reads `numeric-alert.jsonl`, surfaces unconsumed alerts to the LLM as "FYI numeric saw X at HH:MM" inline context.
3. **Update vision-observer doctrine** — vision-observer prompt reads `numeric-pulse.jsonl` (last 6 min) and includes "numeric ledger" in the LLM context so vision LLM can confirm/deny what numeric saw.
4. **Cost gate** — re-measure $/day after 5 trading days. If still under $200/mo total, advance to Option 2 (push vision to 3-min on Haiku 3.5).

### What "watching like a human trader" means after Option 1 ships
- **Every minute**: numeric detector pass — pattern completion logged within 60s of bar close.
- **Every 3 minutes**: heartbeat decision tick — reads numeric alerts + makes orders.
- **Every 6 minutes**: vision observer — qualitative chart read, with numeric ledger as evidence.

Human traders typically scan-and-decide on a ~30s-2min cadence. This gets us to ~1-min numeric coverage and 3-min decision coverage with no budget hit. That's the lowest-risk, highest-leverage answer.

### Open questions for J
1. **Do you have TV Pro or Premium?** If Premium, Option 3 unlocks sub-second alerts and we can rethink.
2. **Are you OK with `numeric-alert.jsonl` being a one-way feed into the heartbeat?** (Heartbeat reads, doesn't write back.)
3. **What about overnight?** SPY closes — should `Gamma_NumericPulse1m` skip outside RTH (saves nothing, just less log noise)? Default: skip non-RTH.

---

## UPDATE 2026-05-18 (~21:00 ET) — J reframed: "watching vs vision" + "act within minute"

J's points:
1. **L2 is free → ping every 30s** (already shipped via `--cycles 2 --interval-sec 30` in wrapper, total 2 pulses per 1-min fire = effective 30s cadence)
2. **L3 6-min vision is too slow IF the goal is action.** Vision isn't the actor — heartbeat is.
3. **Sub-minute action requires event-driven heartbeat**, not faster vision.

### The three layers, restated for clarity

| Layer | Role | What it does | Latency to bar | Cost |
|---|---|---|---|---|
| **L2 Watching** (`numeric_pulse`) | Eyes — pattern recognition | Numeric pattern detectors on closed bar OHLCV; writes `numeric-alert.jsonl` when 3-of-3 (confidence ≥ 0.65 + contra-trend + level-proximate) | bar-close + 30s | **$0** |
| **L3 Vision** (`chart_vision_observer`) | Brain — context + judgment | Haiku reads chart screenshot; answers 6Q ("is this REAL or chop?"); grades L2 alerts | bar-close + 60s + LLM time | $3.20/day |
| **L1 Pilot** (`heartbeat`) | Hands — actually places orders | Reads chart numbers + Alpaca + 11-filter rubric; places bracket orders | Currently tick-bound (every 3 min) | $5.50/day |

**Vision being 6 min is fine** because vision's job is to grade/confirm, NOT to act. The actor is L1.

### To "act within the minute" — event-driven heartbeat

Today's flow:
```
bar closes -> L2 (every 1 min, now 30s) -> alert.jsonl
                                                |
                                                v
                                    L1 polls alert.jsonl on its next tick (~3 min)
```

Worst-case latency: 3 minutes from bar close to order. With 30s L2 cadence: still 3 min because L1 is the bottleneck.

Proposed flow:
```
bar closes -> L2 (30s) -> writes alert.jsonl
                              |
                              v  (Windows file-watcher OR cron-on-event)
                  L1 ad-hoc heartbeat tick (immediate, < 30s)
                              |
                              v
                       order placed
```

**Latency budget:** bar-close (T+0) → L2 pulse (T+30s) → alert.jsonl write (T+31s) → file-watcher trigger (T+32s) → L1 heartbeat (T+62s) → order. **Total ~60s.**

### Build plan for event-driven L1 (queued for next /loop cycle)

**Option A — Long-running Python file watcher** (recommended)
- New script `setup/scripts/heartbeat_alert_listener.py` — daemon that polls `automation/state/numeric-alert.jsonl` every 5s
- On new high-conviction alert row, fires `setup/scripts/run-heartbeat.ps1` (or aggressive) directly via subprocess.Popen (CREATE_NO_WINDOW)
- Keepalive task `Gamma_HeartbeatAlertListenerKeepalive` every 5 min restarts it if dead
- Cost: $0 baseline (just polling). When alert fires, costs ~$0.05 (one extra heartbeat tick).
- Expected: 2-5 alerts/day = ~$0.25/day incremental.

**Option B — Windows ETW file-change events**
- `Register-WMIEvent` watching the JSONL file
- More native but more fragile across Windows versions

**Option A wins on simplicity + observability.**

### Heartbeat doctrine change required (Rule 9)

Because the alert-triggered heartbeat runs OUTSIDE the normal 3-min cron, `heartbeat.md` needs a new section:

> **Step 0 (alert-driven tick):** If `automation/state/numeric-alert.jsonl` last row has `consumed=false` AND was written within the last 60s, treat this as an ALERT-DRIVEN TICK. Mark `consumed=true` after read. Same filters apply (10:00 ET gate, VIX, ribbon, etc.) — alert is *attention*, not *override*.

This is the **single doctrine change needing J ratification**. Everything else (L2 30s, file watcher, keepalive) is infrastructure and ships under OP-25.

### What's safe to ship NOW vs what needs J approval

| Change | Type | Status |
|---|---|---|
| L2 → 30s cadence (shipped tonight) | Infrastructure | SHIPPED (OP-25) |
| `atomic_bracket_guard.py` (shipped this evening) | Safety primitive | SHIPPED (OP-25) |
| `heartbeat_alert_listener.py` daemon | Infrastructure | OK to ship under OP-25 (just spawns existing heartbeat) |
| `Gamma_HeartbeatAlertListenerKeepalive` task | Infrastructure | OK to ship under OP-25 |
| Adding "Step 0 alert-driven tick" to `heartbeat.md` | **Trading doctrine** | **BLOCKED — needs J ratification (rule 9)** |
| Adding L2 alerts as bonus context (NOT a trigger) in existing tick | **Trading doctrine** | **BLOCKED — needs J ratification (rule 9)** |

Translation: I can build the plumbing tonight. The actual "alert triggers immediate trade" decision is J's call.
