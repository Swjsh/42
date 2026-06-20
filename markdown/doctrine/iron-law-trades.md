# Iron Law — Verification Before Trade Writes

> **Multi-Agent Gamma 2.0 — Big Win #5.** Source pattern: obra/superpowers
> `verification-before-completion` skill: *"NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION
> EVIDENCE."*
>
> This document codifies the rule that **nothing** gets written to `journal/trades.csv`,
> `automation/state/decisions.jsonl`, or `automation/state/current-position.json` until the
> evidence required for that specific claim is in hand and was fetched in the **same tick**
> as the write.
>
> Fresh evidence means the MCP tool call producing it was made within the current heartbeat
> tick — NOT carried over from a prior tick's loop-state, NOT inferred from price action,
> NOT estimated from open marks.
>
> Estimated marks are NOT fills. A position-mark moving below stop level does NOT count as
> a stop-out. Only a confirmed Alpaca order with `status="filled"` proves a fill.

---

## The Claim → Required Evidence Table

Every row is enforceable. The "Required Evidence" column is the literal MCP tool call that
must execute and return the specified result before the claim is allowed.

### Claim 1: "Order was filled" → trades.csv ENTRY row

| | |
|---|---|
| **Trigger** | Heartbeat just placed an order via `mcp__alpaca__place_option_order` |
| **Required evidence** | `mcp__alpaca__get_order_by_id(order_id)` returns `status == "filled"` AND `filled_qty > 0` AND `filled_avg_price IS NOT NULL` |
| **What gets written** | New row in `journal/trades.csv` with `entry_time, entry_premium, qty, side, setup_name, ...` |
| **Block on failure** | Order in PENDING_NEW or NEW → wait, do NOT write entry row. Order in REJECTED/CANCELED → write SKIPPED row in `skipped-setups.csv`, log "fill_failed:{reason}" |
| **Recovery** | Re-poll `get_order_by_id` after 2-3 seconds. Max 3 retries. If still not filled after retries: log INCIDENT, alert dashboard |

---

### Claim 2: "Position closed" → trades.csv EXIT row + decisions.jsonl EXIT_*

| | |
|---|---|
| **Trigger** | Heartbeat confirms position fully closed: `get_open_position(symbol)` returns 404 or qty=0 |
| **Required evidence (step 1 — gate)** | `mcp__alpaca__get_order_by_id(exit_order_id)` confirms `status == "filled"` AND `mcp__alpaca__get_open_position(symbol)` returns 404 or qty=0 |
| **Required evidence (step 2 — fill reconciliation)** | `mcp__alpaca__get_account_activities(activity_types=["FILL"], date=today)` filtered to current contract symbol. Group BUY fills (entry) and SELL fills (all exit legs). Compute: `weighted_entry_px`, `weighted_exit_px`, `total_qty`, `dollar_pnl = sum((sell_price - weighted_entry_px) × sell_qty × 100)`. This is the ONLY source for trades.csv numbers — captures J manual exits, partial fills, and any leg missed between ticks. |
| **What gets written** | ONE row in `journal/trades.csv` (one row per trade, not per exit event) using fill-reconciled values. EXIT_* row in `decisions.jsonl`. `current-position.json` set to `{"status": null}`. Screenshot captured. |
| **Partial exit (TP1 only — position still open)** | Do NOT write to trades.csv. Log EXIT_TP1 to decisions.jsonl. Update current-position.json with tp1_exit_price, tp1_qty, tp1_pnl. trades.csv row waits until final close. |
| **Block on failure** | Exit order pending → wait, retry. Position qty > 0 → DO NOT mark closed; log "phantom_exit_alpaca_disagrees". `get_account_activities` fails → fall back to per-order filled_avg_price, log "FILL_RECON_FALLBACK" to decisions.jsonl. |
| **Recovery** | Critical mismatch (Alpaca says open, we say closed) → kill-switch. |

---

### Claim 3: "Stop triggered" → decisions.jsonl EXIT_STOP

| | |
|---|---|
| **Trigger** | Premium-stop, chart-stop, or ribbon-flip-back exit logic identified |
| **Required evidence** | After placing exit order: `mcp__alpaca__get_order_by_id(exit_order_id).status == "filled"` AND `exit_order.side` is OPPOSITE of `entry.side` AND `filled_qty == position.qty` |
| **What gets written** | Row in `decisions.jsonl` with `action: "EXIT_STOP", stop_type: "premium|chart|ribbon_flip_back", filled_at_premium: ...` |
| **Block on failure** | Exit order rejected → escalate to MARKET order at next tick. Order still pending after 30s → cancel + replace at adjusted limit. Both fail → kill-switch + alert |
| **Recovery** | Stop didn't fill at intended price → log "stop_slippage:{intended,actual}". Critical: if exit doesn't fill at all and price still adverse, J is at risk. PROC alarm: page if not closed within 90 sec of stop trigger |

---

### Claim 4: "TP1 hit" → decisions.jsonl EXIT_TP1 (partial close)

| | |
|---|---|
| **Trigger** | Premium reached `entry × tp1_premium_multiplier` (1.30 in v14) or chart-level target |
| **Required evidence** | `mcp__alpaca__get_order_by_id(tp1_order_id).status == "filled"` AND `filled_qty == tp1_qty` (NOT entry_qty — TP1 is partial). AND `mcp__alpaca__get_open_position(symbol).qty == entry_qty - tp1_qty` (runner survives) |
| **What gets written** | Row in `decisions.jsonl` with `action: "EXIT_TP1", tp1_qty: ..., remaining_runner_qty: ...`. Update `current-position.json#runner_qty`. Update `current-position.json#stop` to break-even per runner doctrine. |
| **Block on failure** | TP1 order partial-filled (less than tp1_qty) → log "tp1_partial:{filled,intended}", continue with whatever filled. Runner positions unchanged but stop NOT moved to break-even (ensure both happen atomically or neither). |
| **Recovery** | Runner stop move + TP1 record write must be atomic — see operating principle 4 (no code drift). Use the .lastgood/ pattern: write tentative state, verify both succeed, then atomic rename. |

---

### Claim 5: "Daily kill-switch tripped" → circuit-breaker.tripped = true

| | |
|---|---|
| **Trigger** | Any heartbeat tick where realized P&L crosses threshold |
| **Required evidence** | `sum(today's filled exits realized_pnl_dollars from decisions.jsonl) <= -0.50 * circuit-breaker.start_equity_today`. NEVER use estimated marks (open positions don't count). Only filled exits. |
| **What gets written** | `automation/state/circuit-breaker.json` updated with `tripped: true, tripped_at_et: ISO, trigger_pnl: ..., start_equity: ...` |
| **Block on failure** | If realized P&L computation requires unfilled exit (position still open) → DO NOT trip the kill-switch on estimated value. Compute only from filled exits. |
| **Recovery** | If kill-switch trips mid-tick while a position is open: complete the position-management logic FIRST (don't skip exit logic), then enforce no-new-entry rule. Trips disable all NEW entries for the rest of the session. |

---

### Claim 6: "Margin available" / "Buying power sufficient" → entry sizing decision

| | |
|---|---|
| **Trigger** | Entry branch sizing computation |
| **Required evidence** | `mcp__alpaca__get_account_info().non_marginable_buying_power` (cash account) OR `.options_buying_power` (margin account), fetched WITHIN last 5 minutes (5-min freshness gate). If older: re-fetch. |
| **What gets written** | Sizing decision recorded in `decisions.jsonl#sizing_evidence`: `{buying_power_dollars, fetched_at_et, method: "from_alpaca"}`. Order placement proceeds. |
| **Block on failure** | Stale buying-power read (>5 min old) and re-fetch fails → BLOCK entry, log "stale_buying_power_skip" |

---

### Claim 7: "Setup score = X/Y" → loop-state filter scores

| | |
|---|---|
| **Trigger** | Heartbeat tick computing filter scores |
| **Required evidence** | All 10 (bear) / 11 (bull) filter checks were just executed against current bar values. NO partial — if any filter check raised an exception, score is invalid. |
| **What gets written** | `loop-state.last_filter_score = {bear: N, bear_blockers: [...], bull: M, bull_blockers: [...]}` |
| **Block on failure** | One or more filter functions threw → set `last_filter_score: null` and log "filter_compute_error". DO NOT write a partial score (would leak into next tick's scoring decisions). |

---

## How Iron Law manifests in heartbeat.md

In the Position Branch's exit logic, EVERY exit decision must produce a code path like:

```
1. Identify exit reason (e.g., "premium stop hit")
2. Place exit order via mcp__alpaca__place_option_order
3. Wait for fill: poll mcp__alpaca__get_order_by_id until status == "filled" (max 3 retries, 2s apart)
4. ONLY AFTER fill confirmed:
   a. Append EXIT row to journal/trades.csv  (now writing FACTS, not predictions)
   b. Append EXIT_* row to decisions.jsonl
   c. Set current-position.json#status = null
   d. Capture exit screenshot
5. If fill NOT confirmed after retries:
   - Log INCIDENT to incidents.jsonl
   - Alert dashboard
   - DO NOT mark position closed (state diverges from broker = catastrophic)
```

Order of writes matters: trades.csv first (durable record of fact), then state files. If we
crash between writes, the next tick's `Repair-StateFiles` reads the trade row from CSV and can
reconstruct that the position is closed even if state files lag.

---

## Cross-cutting: the verification log

Each tick, append to `automation/state/verification-evidence.jsonl`:

```json
{
  "tick_id": "2026-05-09T12:34:56Z",
  "claim": "EXIT_TP1",
  "evidence_tool_calls": ["get_order_by_id:abc123", "get_open_position:SPY"],
  "evidence_results": [{"status": "filled", "filled_qty": 3}, {"qty": 2}],
  "claim_passed": true
}
```

This log is the audit trail for the Iron Law itself — proof that we checked, not just that we
claimed.

---

## Anti-patterns (DO NOT do these)

| Anti-pattern | Why it's banned |
|---|---|
| "Position is probably closed because price moved through stop" | Probably ≠ filled. Mark moves don't equal exits. |
| "I'll write the exit row now and confirm the fill on the next tick" | Optimistic write = state divergence if fill fails. ALWAYS confirm before writing. |
| "Fill confirmation is slow, let me skip it just this once" | Skipping IS the failure mode this gate exists to prevent. |
| "The order was 'accepted' so it counts as filled" | Accepted ≠ filled. Specifically `status == "filled"` (not "accepted", "new", "pending_new"). |
| Writing to trades.csv with `pnl_dollars` computed from `current_quote` instead of `filled_avg_price` | P&L must come from actual fills. |
| Trusting `current-position.json` over `mcp__alpaca__get_open_position` | Alpaca is source of truth for broker state. State file is a cache. On disagreement: kill-switch. |
| Writing one trades.csv row per exit event (TP1 row, then runner row) | One row per trade. Partial exits log to decisions.jsonl only. Final row uses fill-reconciled totals across all legs. |
| Using per-order `filled_avg_price` for the final trades.csv row without calling `get_account_activities` | A single order's fill doesn't capture J manual exits or legs placed outside the bracket. Only `get_account_activities` sees all fills. |

---

## Cost note (operating principle 3)

Iron Law adds ~2 extra MCP calls per final close: `get_order_by_id` (fill gate) + `get_account_activities` (reconciliation). At 1-3 trades/day × $0.0001/call = **~$0.01/mo**. Negligible.

The real cost is the SAVING — every silent state corruption that the Iron Law prevents costs
hours of debugging + a potentially wrong trade. Cheapest insurance in the system.
