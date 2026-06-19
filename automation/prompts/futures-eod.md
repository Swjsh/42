# Futures EOD Review — Gamma Futures Edition

NON-INTERACTIVE. Fires 16:05 ET weekdays (after EOD flatten at 15:55).
Runtime target: < 120 seconds.

DO NOT use ScheduleWakeup, AskUserQuestion, or any prompting tool.

---

## Step 0 — pre-flight

1. Read `automation/state/futures/position.json` — must show `"side": "flat"` (EOD flatten already ran).
2. Read `automation/state/futures/account.json` — end-of-day equity, daily_pnl field.
3. Read `automation/state/futures/risk.json` — kill switch status.
4. Get today's date in ET (`YYYY-MM-DD`).

---

## Step 1 — gather today's activity

**Would-be trades (simulation log):**
- Read `automation/state/futures/would-be-trades.jsonl`
- Filter rows where `"time"` starts with today's date
- These are the entries/exits the engine logged, whether WATCH_ONLY or live

**Actual fills (live paper mode):**
- Connect to Tastytrade via `TastytradeBroker` from `backtest.futures.tastytrade_paper`
- Call `broker.connect()` then pull account balances for final equity
- TT sandbox resets fills at EOD — so today's fill data lives in would-be-trades.jsonl + local state

**Tick log:**
- Read `journal/futures/{today}-heartbeat.jsonl` if it exists — gives a tick-by-tick record of what the heartbeat saw and decided each fire

---

## Step 2 — parse each trade

For each entry in today's would-be trades:
```
instrument | side | qty | entry_price | stop | tp1 | exit_price | exit_reason | watcher | confidence | vix
```

Compute:
- `pnl_pts = (exit_price - entry_price) * (1 if side=="BUY" else -1)` — if exit known
- `pnl_usd = pnl_pts * POINT_VALUE[instrument]` (MNQ=2, MES=5)
- Outcome: WIN / LOSS / OPEN (still running) / WATCH_ONLY (no fill yet)

If no exits recorded: note trades that fired but outcome is UNKNOWN (need tomorrow's data or manual review).

---

## Step 3 — daily backtest replay (in-prompt)

From TradingView MCP:
```
chart_set_symbol("CME_MINI:MNQ1!")
data_get_ohlcv(count=80, summary=false)   # full 5m bar history for today
data_get_study_values                      # EMA ribbon
chart_set_symbol("TVC:VIX") + quote_get
```

Walk today's bars (09:35 ET onward, closed bars only) and identify:
- Each bar where the v3 config would have signaled an entry (ribbon state + watcher + VIX gate)
- Estimated entry price (next bar open after signal)
- Natural TP1 (nearest key level above/below) and stop (chart stop)
- Estimated P&L if taken

Compare to what the heartbeat actually logged in would-be-trades.jsonl:
- Entries the engine took that the replay also shows: CONFIRMED
- Entries the engine took that the replay doesn't: PHANTOM (possible look-ahead or state error)
- Entries the replay shows that the engine missed: MISSED

Document each MISSED or PHANTOM in the EOD reflection section.

**MNQ v3 expected baseline** (from backtest analysis/recommendations/futures-edition-summary.md):
- OOS WR: 67.4%, avg ~$15,027 over test period
- Per-trade expectancy: ~$37 (erl_irl long, dominant signal)
- Entry requires: ribbon aligned, VIX >= 16, watcher in approved set

---

## Step 4 — update trades.csv

Append one row per completed trade to `journal/futures/trades.csv`:
```
date,instrument,direction,entry,stop,tp1,runner,qty,tp1_qty,setup,watcher,confidence,vix,entry_time,tp1_time,exit_time,exit_price,exit_reason,pnl_pts,pnl_usd,hold_bars,thesis,rule_break
```

For WATCH_ONLY trades: fill what's known, leave exit fields blank if no outcome yet.
For open trades at EOD: exit_reason=EOD_FLATTEN, use last known price.

---

## Step 5 — running statistics

Read all rows in `journal/futures/trades.csv` (all days).
Compute:
- `total_trades`, `wins`, `losses`
- `win_rate = wins / total_trades`
- `avg_win_usd`, `avg_loss_usd`
- `expectancy = (win_rate * avg_win) - ((1-win_rate) * avg_loss)`
- `total_pnl_usd`

**Live thresholds (from CLAUDE.md):** >= 20 trades, WR >= 45%, positive expectancy before going live with real money.

Progress toward threshold: `{total_trades}/20 trades, WR={win_rate:.0%}`

---

## Step 6 — write EOD section to journal

Append to `journal/futures/{today}.md`:
```markdown
## EOD Review (16:05 ET)

**Account equity:** ${equity:.2f} (start: ${day_start:.2f}, P&L: ${pnl:+.2f})
**Trades today:** {count}
**Today's WR:** {today_wr}%

### Trade log
| Time | Instrument | Direction | Entry | Exit | P&L pts | P&L $ | Signal |
|---|---|---|---|---|---|---|---|
| 10:15 | MNQ | LONG | 21,340 | 21,390 | +50 | +$100 | erl_irl LONG high |
...

### Replay vs Engine comparison
- CONFIRMED: {n}  MISSED: {n}  PHANTOM: {n}
- {bullet per missed/phantom with bar time + price + reason}

### Running stats ({total_trades} total trades)
- WR: {win_rate:.0%} | Expectancy: ${expectancy:.2f}/trade | Total: ${total_pnl:+.2f}
- Live threshold progress: {total_trades}/20 trades minimum

### Reflection
{1-3 sentences: what worked, what didn't, what to watch for tomorrow}
```

---

## Step 7 — VIX gate audit

- Did VIX gate fire correctly today? (gate: VIX >= 16 for most signals)
- If VIX was < 18 all day: note `VIX_GATE_LOW_DAY — engine correctly blocked or should have`
- If trades fired below VIX threshold: rule break flag in trades.csv

---

## Step 8 — write decisions.jsonl

Append one entry to `automation/state/futures/decisions.jsonl`:
```json
{
  "date": "YYYY-MM-DD",
  "trades_today": N,
  "pnl_today": X,
  "win_rate_running": X,
  "total_trades_running": N,
  "vix_gate_fired": bool,
  "missed_signals": N,
  "phantom_signals": N,
  "live_threshold_pct": N/20,
  "review_complete_at": "ISO"
}
```

---

## Constraints
- No order placement
- No ScheduleWakeup or CronCreate
- Always write the EOD section even on zero-trade days
- If TV unreachable for replay: note "TV_UNAVAILABLE — replay skipped" and complete Steps 4-8 from local state
- Total runtime: < 120 seconds
