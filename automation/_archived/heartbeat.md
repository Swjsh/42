# [ARCHIVED 2026-05-08] Heartbeat — original spec — SUPERSEDED

> **STATUS: SUPERSEDED.** This was the 2026-05-04 design doc for the heartbeat loop. The live implementation is now [`automation/prompts/heartbeat.md`](../prompts/heartbeat.md), which is what Task Scheduler actually invokes.
>
> **Why superseded:**
> - Original spec described the heartbeat as a 3-min tick reading 15+ files of doctrine on every cycle (CLAUDE.md + risk-rules.md + playbook.md + state). 2026-05-06 token-economy v3 rewrote it as a lean ~89-line prompt that reads only 5 state files and embeds doctrine directly.
> - Original spec described `-50%` premium stop and ATM strike — both superseded by v14 (-8% premium stop, ITM-2 strike).
> - Original spec described "≥ 2 of 3 triggers" — superseded by v11/v12 asymmetric (bear ≥1, bull ≥2 of 4 triggers including sequence_rejection/reclaim).
> - Original spec did not include the Sonnet escalation rules (added 2026-05-06), the change-only state writes (added 2026-05-06), the HOT/BASE/COOL adaptive cadence (added 2026-05-06), or the macro bias inheritance (added 2026-05-07).
>
> **Read instead:** [`automation/prompts/heartbeat.md`](../prompts/heartbeat.md) for the live tick logic. Numeric values: [`automation/state/params.json`](../state/params.json).

---

# Heartbeat — the agent loop

> Runs every 3 min during market hours (09:30–15:50 ET). Each invocation is a complete read → decide → act → log cycle.

---

## Invocation contract

Cron invokes `claude --print` (Claude Code's non-interactive mode) with the heartbeat prompt. The prompt is fixed; Gamma reads state from disk, never from arguments. This makes invocations idempotent and debuggable.

**The fixed prompt:**

```
You are Gamma. Read CLAUDE.md, strategy/risk-rules.md, strategy/playbook.md.
Then read automation/state/. Run one heartbeat cycle per automation/heartbeat.md.
Take exactly one action (or no action). Update state files. Append to journal/{today}.md.
Exit.
```

That's it. The decision tree lives in `automation/decision-log.md`.

---

## The cycle (run order)

### 1. Read kill switch
- If `automation/state/kill-switch` exists → log "PAUSED" to heartbeat log, exit.
- If `automation/state/circuit-breaker.json` shows daily-loss tripped → log, exit.

### 2. Read time window
- If outside 09:30–15:50 ET → exit silently.
- Special handling: `09:30–09:35` is no-trade (open chop); first scan that takes a trade is at the bar closing 09:36.

### 3. Read open position
- `automation/state/current-position.json` is the source of truth.
- Cross-check against Alpaca `get_positions` — if mismatch, log discrepancy and **do nothing else** until reconciled (manual override required).

### 4a. NO POSITION → look for entry

Pull from TradingView MCP:
- SPY current price
- EMA ribbon state (color/orientation on 3-min): bullish-stack | bearish-stack | transitioning
- Recent N candles (last 10 × 3-min): OHLC, volume
- Indicator triangles printed (sell/buy signals from your indicator)
- Distance to the day's key levels (loaded from `state/today-bias.json`)

Pull from Alpaca paper MCP:
- Account equity
- Day-trade count remaining
- Buying power

Run the playbook trigger check (decision tree in `decision-log.md`):
1. Is `BEARISH_REJECTION_RIDE_THE_RIBBON` setup eligible right now? (Context filters in `playbook.md` all true.)
2. Did the trigger fire on the last closed candle? (≥ 2 of 3 trigger events.)
3. If yes: compute size, place order, write pre-trade thesis. If no: log "no signal" + relevant chart conditions, exit.

If trigger fires AND sizing math passes:
- Compute strike (ATM or 1st OTM put), premium estimate, qty = 3.
- Compute $-risk = (premium × qty × 100) × 0.5 (assuming -50% premium stop).
- Verify $-risk ≤ 50% of equity AND ≤ daily-loss budget remaining.
- Write pre-trade thesis to `journal/{today}.md` (BEFORE order placement).
- Place limit order via Alpaca paper MCP at mid.
- Update `state/current-position.json` with order details.
- Set timer/flag to confirm fill on next heartbeat (in 3 min).

### 4b. POSITION OPEN → manage

Pull current chart state + position state.

**Stop checks (any → exit immediately):**
1. Premium ≤ entry × 0.5 → premium stop hit → market-sell all → log "STOP_HIT premium".
2. SPY closed a 3-min candle above the rejected level → chart stop hit → market-sell all → log "STOP_HIT chart".
3. EMA ribbon flipped back bullish (cyan/blue stack, confirmed close) → invalidation → market-sell all → log "STOP_HIT ribbon-flip".
4. Time ≥ 15:50 ET → time stop → market-sell all → log "STOP_HIT time".

**Take-profit checks (in order):**
1. **TP1 not yet taken AND** premium ≥ entry × 1.5 (i.e., +50% gain) **AND** at first major support level (from `state/today-bias.json`):
   - Sell ⅔ of position (2 of 3 contracts).
   - Update position state: `tp1_taken = true`, `qty_remaining = 1`.
   - Move stop to breakeven on runner.
2. **Runner active:** ride the ribbon. Hold while every closed 3-min candle is on the bearish side of the ribbon. Exit triggers (any):
   - Candle closes back into the ribbon (yellow band).
   - Bounce signature: long lower wick + immediate reversal (next candle closes green).
   - Premium ≥ entry × 2.5 (massive runner — take it).

If no stop, no TP, no exit signal: do nothing this cycle. Log "HOLD". Exit.

### 5. Always do at end of cycle
- Append a one-line entry to `automation/state/heartbeat.log` with timestamp + action taken.
- If action was a trade entry/exit: also append structured row to `journal/trades.csv` (entries get a row at fill confirm; exits update the row).
- If action involved a fill: confirm fill via Alpaca on next cycle, not this one (avoid race conditions).

---

## Modes

The heartbeat supports three modes, set by `state/mode.json`:

| Mode | What runs |
|---|---|
| `live-paper` | Full cycle as above. Paper orders sent to Alpaca. **Default for Tier 1.** |
| `dry-run` | Full cycle EXCEPT `place_order` calls. Logs the order it *would* have placed. Used for end-to-end verification before going live-paper. |
| `paused` | Only kill-switch + state-read steps run. No reads of TradingView, no Alpaca. Used during weekends, off-hours, or manual interventions. |

Switch modes by editing `state/mode.json` — change takes effect on next heartbeat tick.

---

## Failure modes & how the heartbeat handles them

| Failure | Handling |
|---|---|
| TradingView MCP unreachable | Log error, skip this cycle, retry next tick. After 3 consecutive failures: alert via journal entry + create kill-switch file. |
| Alpaca MCP unreachable | Same: log, skip, retry. After 3 consecutive: kill-switch. |
| Position state mismatch (state vs. Alpaca) | Hard stop. Create `state/kill-switch` with reason. Require manual reconciliation. |
| Order placed but fill not confirmed in 2 ticks (6 min) | Cancel the unfilled order, log, no new entry until next clean trigger. |
| Daily loss budget exceeded mid-trade | Allow the open trade to resolve via its existing stops. Block any new entries. |
| Cron didn't fire on a tick | The next tick handles it; the loop is robust to skipped cycles. State doesn't depend on tick contiguity. |

---

## Auditability

Every heartbeat invocation writes:
1. A line to `automation/state/heartbeat.log`.
2. A pre-trade thesis (if entering) to `journal/{today}.md`.
3. A management note (if holding) every Nth tick — by default every 5th tick to avoid clutter.
4. An exit summary (if exiting) to `journal/{today}.md` and `journal/trades.csv`.

End of day: `automation/eod.md` runs and produces a single readable summary in `journal/{today}.md` of every action and decision Gamma made that day. J reads that one file at end of day to audit.
