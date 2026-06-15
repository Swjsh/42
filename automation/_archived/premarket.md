# [ARCHIVED 2026-05-08] Premarket — original spec — SUPERSEDED

> **STATUS: SUPERSEDED.** This was the 2026-05-04 design doc for the premarket routine. The live implementation is now [`automation/prompts/premarket.md`](../prompts/premarket.md), which is what Task Scheduler invokes at 08:30 ET daily.
>
> **Why superseded:**
> - Original spec was a high-level outline. The live prompt has detailed step-by-step structure (5 reads → 7 numbered steps + sub-steps 5b/5c/8a/8b for trendlines/levels/macro-calendar/dark-pool).
> - Original spec did not include the 2026-05-07 catalyst layer (macro-calendar.json reading), the 2026-05-08 trendline awareness layer (chart_drawings.json + compute_trendlines.py), or the 2026-05-08 key-levels v3 schema (strength scoring + pivot/ORH/VWAP/VP/AVWAP).
> - Original spec referenced the 3-min ribbon timeframe — superseded by 5-min throughout.
> - Original `today-bias.json` shape is missing falsifiable_predictions[] (added 2026-05-05), iv_regime/iv_source/iv_value (added 2026-05-07), prior_day_review_hint (added 2026-05-05).
>
> **Read instead:** [`automation/prompts/premarket.md`](../prompts/premarket.md) for the live routine. Key levels protocol: [`strategy/key-levels-protocol.md`](../../strategy/key-levels-protocol.md). Numeric values: [`automation/state/params.json`](../state/params.json).

---

# Premarket routine — runs once per trading day at 08:30 ET

> Sets up the day. Without this, the heartbeat doesn't know what levels to trade against.

---

## Trigger

Cron entry fires at 08:30 ET, weekdays only (Mon–Fri), with a market-holiday calendar check baked into the prompt.

## Cycle steps

### 1. Market-day check
- Is today a US equities trading day? (No FOMC closure, no holiday, etc.)
- If not: write "NO_TRADE_DAY" to `state/today-bias.json` with reason. Exit.

### 2. Read overnight context
Pull from TradingView MCP:
- ES (S&P futures) overnight session: high, low, current.
- SPY ETH session (extended hours): high, low, current.
- Yesterday's SPY close, yesterday's high, yesterday's low.

### 3. Identify today's key levels — read carry-over, then add fresh

> **HARD PREREQUISITE: every level created/modified in this section must pass `strategy/key-levels-protocol.md`. Five mandatory fields per level (source, tier, verification, reasoning, type), three tier classifications, and a drawing checklist that must clear before any `draw_shape` call. No level enters the system without passing the protocol.**

**Step 3a — Read yesterday's `automation/state/key-levels.json`.** This is the carry-over from yesterday's EOD. It contains:
- Yesterday's session high/low/close
- Levels that were drawn on the chart at EOD (with entity_ids)
- "Tomorrow watch zones" — yesterday's call on what mattered today

**Step 3b — Run protocol audit on carry-over levels:**
- For every level in `key-levels.json#levels[]`: confirm all 5 mandatory fields present (source, tier, verification, reasoning, type). Drop levels missing any field — log to `audit_log.drops[]`.
- For each remaining level: check `verified_at` against tier window (Active: 24h, Carry: 5 sessions, Reference: 30 sessions). Levels past their window go to `pending_reverification[]`.
- Re-verify each pending level against the chart at the appropriate timeframe.
- Then check overnight action: did ES/SPY blow through any verified level? If yes → mark as `broken` and demote to `transition` type.
- Did price gap above/below the highest/lowest verified level? → write a "gap context" note.

**Step 3c — Add today's fresh levels:**
- Premarket high (PMH) — *always relevant for level-rejection setup*.
- Premarket low (PML).
- Multi-day descending trendline value at today's expected open time (if present on chart).
- Multi-day ascending trendline value (for future bullish setup).
- **For multi-day swing levels: switch chart to 1D temporarily, read the actual swing high/low values, then switch back to 5-min.** Do NOT trust inherited swing-low values from old state files — verify against the daily chart every premarket.

**Step 3d — Draw the levels on the chart.** Use `mcp__tradingview__draw_shape` with horizontal_line for each level. Color convention from `workflow/daily-review.md`:
- Red solid → fresh resistance
- Green solid → confirmed support
- Yellow dashed → transition (broken yesterday, weak today)
- Blue solid → secondary support tier
- Blue dashed → multi-day reference

**Step 3e — Capture entity_ids back into `today-bias.json`.** Each `mcp__tradingview__draw_shape` call returns an entity_id. Write these into `today-bias.json#key_levels[].entity_id` so the heartbeat can reference exactly which lines are in play (and EOD can update them).

**Carry-over deletion rule:** if yesterday's levels are no longer relevant (e.g., session opened 5+ points away from the deepest carry-over level, or two consecutive sessions have closed beyond it), the premarket routine **does not redraw them** and adds the entity_id to `today-bias.json#deprecated_entity_ids[]`. The lines stay on the chart from yesterday until J manually removes them — premarket doesn't auto-delete on his chart.

### 4. Read economic calendar
- Is FOMC, CPI, NFP, PPI, retail sales, or Powell-speaking on today's calendar?
- Are there mega-cap earnings before/after the bell that historically move SPY (AAPL, MSFT, NVDA, GOOG, AMZN, TSLA, META)?
- If a release is in the next 30 min after the open: bias = NO_TRADE until 30 min after release.

### 5. Compute today's bias
Decision tree:
- Bearish: price below ribbon, ribbon bearish-stacked, lower-highs visible on prior 1-2 sessions, OR PMH being respected as resistance.
- Bullish: price above ribbon, ribbon bullish-stacked, higher-lows visible, OR PML being respected as support.
- No-trade: post-news whipsaw, range-bound chop with no defined level, FOMC/CPI day before release.

Write `state/today-bias.json`:
```json
{
  "date": "YYYY-MM-DD",
  "bias": "bearish" | "bullish" | "no-trade",
  "rationale": "short string",
  "key_levels": {
    "premarket_high": 721.58,
    "premarket_low": 719.40,
    "prior_day_high": 723.08,
    "prior_day_low": 717.50,
    "trendline_at_open": 723.20,
    "user_drawn": [711.40, 709.40]
  },
  "news_calendar": {
    "events_today": ["CPI 8:30 ET (already released)", "Fed minutes 14:00 ET"],
    "no_trade_window": "13:45-14:30 ET"
  },
  "daily_loss_budget_dollars": 500,
  "day_trades_remaining": 3
}
```

### 6. Write the day's journal seed
Create `journal/{today}.md` if it doesn't exist, populated with:
- Pre-market context summary.
- Today's bias + rationale.
- Key levels as a table.
- News calendar with no-trade windows.
- Sections seeded for "Trades", "Setups skipped", "End-of-day reflection" — heartbeat fills these in as the day runs.

### 7. Sanity check + chat-summary mode
If `state/notify-on-premarket = true`: post a one-message chat summary so J can read it on his phone before the open. (Tier 1 default: false. Tier 2: true.)

---

## Safety: what premarket WON'T do
- Won't place any orders.
- Won't take any side bets.
- Won't override yesterday's open positions (there shouldn't be any — EOD flattens — but if state shows one, log a discrepancy and create kill-switch).

---

## Edge cases

| Edge case | Handling |
|---|---|
| Half-day market (early close) | Pull half-day calendar from TradingView; adjust EOD time to 12:55 ET. |
| Market closed unexpectedly | TradingView MCP returns no data → write `NO_TRADE_DAY` to state. |
| TradingView desktop not running | Premarket fails. Write error to journal. Heartbeat will inherit the failed state and stay in no-trade until premarket succeeds (manually re-runnable). |
