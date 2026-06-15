# [ARCHIVED 2026-05-08] EOD — original spec — SUPERSEDED

> **STATUS: SUPERSEDED.** This was the 2026-05-04 design doc for two end-of-day tasks. The live implementations are now [`automation/prompts/eod-flatten.md`](../prompts/eod-flatten.md) (15:55 ET safety net) and [`automation/prompts/eod-summary.md`](../prompts/eod-summary.md) (16:00 ET reflection) and [`automation/prompts/daily-review.md`](../prompts/daily-review.md) (16:30 ET strategic review).
>
> **Why superseded:**
> - Original spec described the 16:30 task as "daily summary"; live system splits it into 16:00 EOD-summary (metrics + counterfactuals) AND 16:30 daily-review (predictions vs actual + tomorrow's key-levels).
> - Original spec did not include the 2026-05-07 catalyst & liquidity layer additions (dark-pool TRF aggregation, hypothesis grading, decision grading, archetype matching, hold-quality scoring, tape-assistance tagging, process-compliance tracking).
> - Original spec did not include the 2026-05-07 daily backtest sync (Section 8b in the live eod-summary — pure Python, catches engine drift within 24h).
> - Original "weekly EOD" Friday rollup is now `Gamma_WeeklyReview` Sunday 18:00 ET task in [`automation/prompts/weekly-review.md`](../prompts/weekly-review.md), with full recommendations executive block + setup performance aggregation + baselines + threshold check.
>
> **Read instead:** [`automation/prompts/eod-flatten.md`](../prompts/eod-flatten.md) + [`automation/prompts/eod-summary.md`](../prompts/eod-summary.md) + [`automation/prompts/daily-review.md`](../prompts/daily-review.md) + [`automation/prompts/weekly-review.md`](../prompts/weekly-review.md).

---

# End-of-day routine

> Two cron entries: 15:55 ET (flatten) and 16:30 ET (summary).

---

## 15:55 ET — Flatten

### Purpose
0DTE options held past 15:55 ET face brutal theta and vanishing liquidity. Hard rule: flat by 15:50 (heartbeat handles 15:50). The 15:55 cron is the **safety net** in case the heartbeat missed it.

### Cycle steps
1. Read `state/current-position.json`.
2. If position open: market-sell remaining contracts via Alpaca paper MCP.
3. Update position state to `null`.
4. Append exit row to `journal/trades.csv`.
5. Append `EOD_FLATTEN` entry to `journal/{today}.md` with reason ("safety net" or "normal exit").

### What if the heartbeat already exited cleanly?
- State will show `null` position. The 15:55 cron sees nothing to do, logs "no-op".

---

## 16:30 ET — Daily summary

### Purpose
Produce a single, readable end-of-day report J can review on his phone after work.

### Cycle steps

1. **Read all heartbeat log entries from today** (`automation/state/heartbeat.log`).
2. **Read today's journal** (`journal/{today}.md`).
3. **Compute metrics:**
   - Trades placed today (count).
   - Trades won / lost.
   - Total $ P&L (paper).
   - % return on starting equity.
   - Largest winner / largest loser.
   - Setups skipped (and reason).
   - Rule breaks (any).
   - Day-trade count consumed.
4. **Append "End-of-day summary" section** to `journal/{today}.md` with:
   - One-paragraph narrative of how the day went.
   - The metrics table.
   - "What worked" / "What to fix" / "Tomorrow's expected bias" if signals are clear.
5. **Update `journal/trades.csv`** with any rows still pending close-out math.
6. **Update `state/equity-curve.json`** with today's closing equity and a rolling window of recent days.
7. **Optional: post a single chat message** summarizing the day if `state/notify-on-eod = true`. Tier 1 default: true. (You should see a phone notification at 16:30 ET each trading day with the day's results.)

### Sanity checks

- Equity in `current-position.json` matches Alpaca's reported equity → if not, log discrepancy.
- All entries today have a corresponding exit (no leftover positions) → if not, alarm.
- Trades.csv is sorted, no duplicate timestamps, no orphan entries.

---

## Weekly EOD (Friday 16:30 ET)

After daily summary, if it's Friday:
1. Compute the weekly metrics (win rate, avg R, expectancy, max DD over the week).
2. Write `analysis/{YYYY-Www}.md` with the weekly review structure from `journal/README.md`.
3. Highlight any rule breaks from `journal/mistakes.md` from this week.
4. Suggest (don't execute) any rule changes for the next week. **J reviews and decides on Sunday.**

---

## Monthly EOD (last trading day of month, after weekly)

1. Roll up all weekly reviews for the month.
2. Compute monthly P&L, max DD, total trades, expectancy.
3. Write `analysis/{YYYY-MM}.md` with the monthly summary.
4. Flag any setup whose performance has drifted (was confirmed, now losing) for review.
