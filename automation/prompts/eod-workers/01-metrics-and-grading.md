# EOD Worker A — Metrics + Trade Grading

> **Scope:** EOD steps 1, 6, 7, 7a, 7c, 7d, 7f from the legacy eod-summary.md.
> Trade grading rubric, archetype-match, tape-assistance, entry-timing precision.
> Excludes chart-heavy steps (those are Worker C).
>
> **Output:** Single JSON file at `automation/state/eod-workers/{date}-metrics.json`.
> NO markdown emit, NO journal writes, NO console output beyond the file path.

---

## Inputs (provided in your context by orchestrator)

- Today's date (ET)
- `automation/state/circuit-breaker.json` summary (start_equity, current_equity)
- `journal/trades.csv` (today's trades only)
- `automation/state/decisions.jsonl` (today's last 200 decisions)
- `strategy/playbook.md` (for archetype matching)

---

## Tasks

### 1. Compute session metrics

```
n_trades_today
n_wins_today
n_losses_today
win_rate (decimal)
total_pnl_dollars
total_pnl_pct (vs start_equity)
day_trades_used_today
day_trades_remaining (5-day rolling)
biggest_win_dollars
biggest_loss_dollars
avg_winner_dollars
avg_loser_dollars
expectancy = (win_rate * avg_winner) + ((1-win_rate) * avg_loser)
```

### 2. Per-trade grade (rubric A-F)

For each trade in today's trades.csv, score 0-5 points:
- (+1) Setup matched a named playbook entry
- (+1) Trigger fired on a closed bar (not anticipated)
- (+1) Stop placed at entry (premium OR chart)
- (+1) Sized within tier table (no overage)
- (+1) Exit followed plan (TP1 / runner doctrine OR mechanical stop, not panic)

Grade map: 5→A, 4→B, 3→C, 2→D, 0-1→F.

### 3. Archetype similarity (per trade)

For each trade, find the closest playbook archetype (top-1 + top-2 similarity score 0-1):
- Use the playbook setup name as the archetype label
- Similarity factors: trigger type match, ribbon stack at entry, level-tier proximity, vol regime

### 4. Tape-assistance flag (per trade)

Did SPY's daily-tape (last 30d) help OR hurt this trade?
- BULL TAPE = SPY 5d > SMA20 AND VIX < 17 → helped longs, hurt shorts
- BEAR TAPE = SPY 5d < SMA20 AND VIX > 18 → helped shorts, hurt longs
- CHOP = neither → neutral
Tag each trade: `tape_assist_score` ∈ {-1 hurt, 0 neutral, +1 helped}.

### 5. Entry-timing precision (per trade)

From decisions.jsonl, find the FIRST tick where this setup's score crossed entry threshold.
Compare to actual entry tick. Compute `entry_lag_ticks` (0 = perfect, +N = late).

---

## Output JSON shape

Write to `automation/state/eod-workers/{date}-metrics.json`:

```json
{
  "worker": "metrics-and-grading",
  "date": "YYYY-MM-DD",
  "generated_at_et": "ISO",
  "session_metrics": {
    "n_trades_today": 0,
    "n_wins_today": 0,
    "n_losses_today": 0,
    "win_rate": 0.0,
    "total_pnl_dollars": 0.0,
    "total_pnl_pct": 0.0,
    "day_trades_used_today": 0,
    "day_trades_remaining_5d": 3,
    "biggest_win_dollars": 0.0,
    "biggest_loss_dollars": 0.0,
    "avg_winner_dollars": 0.0,
    "avg_loser_dollars": 0.0,
    "expectancy_dollars": 0.0
  },
  "trade_grades": [
    {
      "trade_id": "...",
      "setup_name": "...",
      "grade": "A|B|C|D|F",
      "grade_points": 0,
      "rubric": {
        "playbook_match": true,
        "trigger_on_closed_bar": true,
        "stop_at_entry": true,
        "sized_within_tier": true,
        "exit_followed_plan": true
      },
      "archetype_top1": {"name": "...", "similarity": 0.0},
      "archetype_top2": {"name": "...", "similarity": 0.0},
      "tape_assist_score": 0,
      "entry_lag_ticks": 0
    }
  ],
  "csv_updates": [
    {"trade_id": "...", "column": "grade", "new_value": "A"},
    {"trade_id": "...", "column": "tape_assist_score", "new_value": 1}
  ]
}
```

The `csv_updates[]` array is consumed by the orchestrator's Step 4 — it applies the column
updates back to `journal/trades.csv` to enrich the canonical record.

---

## Time budget

Aim for completion in <60 seconds. Use Bash + Python one-liners aggressively. Do NOT call
TradingView (Worker C does charts).
