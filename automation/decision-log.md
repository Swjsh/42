# Decision tree — plain English

> The decision tree the heartbeat runs every 3 minutes. Plain English so it's auditable and modifiable without reading code. The heartbeat reads this and the playbook on every invocation; any changes to logic happen here, not in code.

---

## Top-level decision

```
On heartbeat tick:
├── Is system paused (kill-switch present)? → exit
├── Is daily loss budget tripped? → exit (manage existing positions only)
├── Outside market hours (09:30–15:50 ET)? → exit
├── Is there an open position?
│   ├── YES → run MANAGEMENT branch
│   └── NO  → run ENTRY branch
└── Always: log heartbeat entry + state snapshot
```

---

## ENTRY branch — looking for a setup

```
ENTRY branch:
├── Read state/today-bias.json
│   ├── bias = "no-trade"? → exit (log "skipped: no-trade day")
│   ├── inside no-trade-window (e.g., FOMC release)? → exit
│   └── any bias → continue (heartbeat scans BOTH bearish and bullish setups
│                           regardless of pre-market bias direction —
│                           bias is context, not a filter on what setups can fire)
│
├── Pull TradingView MCP state:
│   ├── SPY current price + last N candles (5-min default)
│   ├── EMA ribbon stack + spread on each of last 3 closed candles
│   ├── VIX last + trend (3 ticks)
│   ├── Indicator triangles printed in last 3 candles
│   └── Distance from each key level in today's bias
│
├── Pull Alpaca paper MCP:
│   ├── account equity
│   ├── day-trades remaining
│   └── buying power
│
├── Run BEARISH_REJECTION_RIDE_THE_RIBBON trigger check (CONFIRMED — paper-eligible):
│   ├── Context filters (ALL must be true per playbook.md):
│   │   ├── Time ≥ 09:35 ET? (no first-5-min)
│   │   ├── No major news in next 30 min?
│   │   ├── Daily loss budget remaining > planned $-risk?
│   │   ├── Day-trades remaining ≥ 1?
│   │   ├── EMA ribbon currently bearish-stacked (Fast < Pivot < Slow)?
│   │   ├── Ribbon spread ≥ 30 cents?
│   │   ├── No volume divergence on breakdown bar?
│   │   └── VIX > 17.30 baseline AND rising tick-over-tick?
│   │
│   ├── Trigger conditions (need ≥ 2 of 3):
│   │   ├── Level rejection: SPY tested a key resistance level AND printed a
│   │   │   rejection candle (close back below the level) on LAST CLOSED candle?
│   │   ├── Ribbon flip: bullish-stack → bearish-stack on last 1-3 candles?
│   │   └── Confluence with multi-day trendline / prior day high / PMH?
│   │
│   ├── If filters pass + ≥ 2 triggers: PROCEED to sizing → place paper order
│   └── Else: log "no bearish signal" with diagnostic dump, continue to bullish scan
│
├── Run BULLISH_RECLAIM_RIDE_THE_RIBBON trigger check (PAPER-ELIGIBLE — J override 2026-05-06):
│   ├── Context filters (mirror of bearish, ALL must be true):
│   │   ├── Time ≥ 09:35 ET?
│   │   ├── No major news in next 30 min?
│   │   ├── EMA ribbon currently bullish-stacked (Fast > Pivot > Slow)?
│   │   ├── Ribbon spread ≥ 30 cents?
│   │   └── VIX < 17.20 baseline OR falling tick-over-tick? (NEVER call when VIX > 22)
│   │
│   ├── Trigger conditions (need ≥ 2 of 3):
│   │   ├── Level reclaim: SPY tested key support AND printed reversal candle
│   │   │   (open low, close high, range ≥ 1.5× recent avg, vol ≥ 1.5× avg)
│   │   │   on LAST CLOSED candle?
│   │   ├── Ribbon flip: bearish-stack → bullish-stack on last 1-3 candles?
│   │   └── Confluence with multi-day support / prior day low / PML?
│   │
│   ├── If filters pass + ≥ 2 triggers:
│   │   ├── Compute sizing: choose ATM or 1st OTM CALL strike (SPY rounded)
│   │   ├── Pull option chain via Alpaca MCP, filter for 0DTE expiry, find
│   │   │   best mid in the $0.50–$2.00 premium range
│   │   ├── Compute qty: 3 contracts (or 4 if account ≥ $2K)
│   │   ├── Compute deployed: premium × qty × 100
│   │   ├── Compute max-loss: deployed × 0.5 (at -50% premium stop)
│   │   ├── Validate per risk-rules.md (max-loss ≤ 50% equity, ≤ daily-budget)
│   │   ├── Write pre-trade thesis to journal/{today}.md (BEFORE order)
│   │   ├── Place limit order via Alpaca paper MCP at mid
│   │   ├── Update state/current-position.json with: order_id, status,
│   │   │   trade params, side="bullish_call", timestamp
│   │   ├── Increment observation counter in playbook.md sample table
│   │   │   (paper trades still count toward 3-example confirmation gate
│   │   │   for live-money deployment)
│   │   └── Exit cycle, next tick checks fill
│   │
│   └── Else: log "no bullish signal" with diagnostic dump, exit
│
├── Compute sizing:
│   ├── Choose strike: ATM put (SPY rounded to nearest $1) OR 1st OTM
│   │   → Pull option chain via Alpaca MCP, filter for 0DTE expiry, find best mid
│   │     in the $0.50–$2.00 premium range.
│   ├── Compute qty: 3 contracts (or 4 if account ≥ $2K)
│   ├── Compute deployed: premium × qty × 100
│   ├── Compute max-loss: deployed × 0.5 (at -50% premium stop)
│   ├── Validate:
│   │   ├── max-loss ≤ 50% of equity? (per-trade cap)
│   │   ├── max-loss ≤ daily-budget-remaining?
│   │   ├── deployed ≤ buying power?
│   │   └── premium ≤ $3.30 (so 3 contracts fits the cap)
│   └── If all pass: PROCEED to order. Else: log "sizing failed: <reason>", exit.
│
├── Write pre-trade thesis to journal/{today}.md (BEFORE order placement):
│   ├── Setup name + version
│   ├── Trigger events that fired (with chart prices and times)
│   ├── Strike, expiry, qty, entry mid, premium, deployed, $-risk, % equity
│   ├── Stop level (premium and chart)
│   ├── Target plan (TP1 + runner via ribbon)
│   └── Timestamp
│
├── Place limit order via Alpaca paper MCP:
│   ├── BUY {qty} SPY {expiry} {strike}P @ {mid} LIMIT, time-in-force DAY
│   ├── Capture order ID
│   └── Update state/current-position.json with: order_id, status="pending_fill",
│       trade params, timestamp
│
└── Exit. Next tick will check for fill.
```

---

## MANAGEMENT branch — position open

```
MANAGEMENT branch:
├── Pull current TradingView state + Alpaca position state
├── Reconcile: state file says X, Alpaca says Y → if mismatch, kill-switch + alarm
│
├── If position status = "pending_fill":
│   ├── Has the order filled? (check Alpaca order status)
│   │   ├── YES → update state to "open" with fill price, fill time
│   │   ├── NO + age < 6 min → wait, exit cycle
│   │   └── NO + age ≥ 6 min → cancel order, update state to null, exit cycle (no entry)
│
├── If position status = "open":
│   │
│   ├── STOP CHECKS (any → exit immediately):
│   │   ├── Premium ≤ entry × 0.5 (premium stop hit)
│   │   ├── 3-min candle just closed ABOVE the rejected level
│   │   ├── EMA ribbon flipped back bullish (cyan/blue stack confirmed close)
│   │   └── Time ≥ 15:50 ET (time stop)
│   │
│   ├── If any stop hit:
│   │   ├── Place market sell for entire remaining qty via Alpaca MCP
│   │   ├── Capture fill price, log to journal with stop reason
│   │   ├── Update trades.csv with exit row
│   │   ├── Set state to null
│   │   └── Exit cycle
│   │
│   ├── TP1 CHECK (only if not yet taken):
│   │   ├── Premium ≥ entry × 1.30 (i.e., +30% gain)?
│   │   │   → Take TP1: market sell ⅔ of qty (2 of 3, or 2 of 4)
│   │   ├── OR price at first major support level (from today-bias.json)?
│   │   │   → Take TP1
│   │   ├── If TP1 taken:
│   │   │   ├── Update state: tp1_taken=true, qty_remaining = qty - 2
│   │   │   ├── Move stop to breakeven on runner (premium stop now = entry premium)
│   │   │   └── Log to journal
│   │
│   ├── RUNNER / EXIT-ALL CHECK:
│   │   ├── Compute exit signal: ribbon-flip-back OR bounce-signature OR premium ≥ entry × 3.0
│   │   ├── If exit signal fires:
│   │   │   ├── If tp1_taken: market sell qty_remaining (the runner only)
│   │   │   ├── If NOT tp1_taken: market sell ALL qty  ← FALLBACK rule
│   │   │   │   (small-magnitude trade — never reached +30% TP1, exits unified)
│   │   │   ├── Log fill + reason
│   │   │   └── Set state to null
│   │
│   └── No stop, no TP, no runner exit: log "HOLD", exit cycle
│
└── Always: log state at end of cycle
```

---

## What the heartbeat WILL NOT do

- **Will not** add to a losing position. Period. The "averaging down" that worked on 5/1 was retroactively reframed as "the second entry was the actual signal" — Gamma re-treats that as a fresh entry decision under fresh trigger logic, which means the *position* is closed first then re-entered. In automation, simpler: one entry per setup-fire, no re-entry until the position is closed.
- **Will not** widen a stop. Stops only tighten or stay put.
- **Will not** trade outside the named playbook. If a setup not in `playbook.md` looks promising in the chart, log it as an observation only.
- **Will not** override the kill-switch.
- **Will not** trade on a no-trade day or in a no-trade window.

---

## Tunable parameters (live in `state/params.json`)

These are the knobs we adjust as we learn from paper data. Heartbeat reads them on every tick.

```json
{
  "heartbeat_interval_minutes": 3,
  "premium_stop_pct": -0.5,
  "tp1_premium_pct": 0.3,
  "tp1_qty_fraction": 0.667,
  "runner_be_stop_after_tp1": true,
  "exit_all_on_runner_signal_if_tp1_unfired": true,
  "runner_max_premium_pct": 3.0,
  "min_contracts": 3,
  "scale_up_account_threshold": 2000,
  "scale_up_min_contracts": 4,
  "max_premium_per_contract": 3.30,
  "per_trade_risk_cap_pct": 0.5,
  "daily_loss_kill_switch_pct": 0.5,
  "no_trade_first_minutes": 5,
  "time_stop_et": "15:50"
}
```

When we want to test a tighter stop or a different TP1 target, we edit this file. No code changes needed.
