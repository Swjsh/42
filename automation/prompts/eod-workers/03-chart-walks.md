# EOD Worker C — Chart-Walks (Counterfactuals + Loss Audits + Hold Quality)

> **Scope:** EOD steps 7b, 7e, 7g, 7h, 7i from legacy eod-summary.md.
> The TradingView-heavy work — counterfactual exits, hold-quality scoring, skip-cost retro,
> decision grading, per-loss chart-walk markdown.
>
> **Output:** Single JSON file at `automation/state/eod-workers/{date}-chart-walks.json`.
> Plus per-loss markdown files in `journal/losses/{date}-{HHMM}-{setup}.md`.
>
> **Heaviest worker — budget cap $1.** Use TradingView MCP efficiently: batch chart reads,
> reuse the same SPY 5m + 1m fetches across all sub-tasks.

---

## Inputs

- `journal/trades.csv` (today's trades for chart context)
- `automation/state/decisions.jsonl` (today's tick decisions)
- `automation/state/skipped-setups.csv` (setups that scored ≥7 but didn't fire)
- TradingView MCP (chart_set_symbol, data_get_ohlcv, capture_screenshot)

---

## Tasks

### 1. Counterfactual exit P&L (per trade)

For each trade today, compute alternative exit P&Ls:

| Exit rule | Premium target | Computed P&L |
|---|---|---|
| Entered + held to TP1 only | actual_exit | (already in CSV) |
| Held to runner_target | runner stop or 15:50 ET | counterfactual |
| Held to ribbon flip | ribbon stack opposite + 30c spread | counterfactual |
| Held to chart-stop only (no TP1 partial) | chart_stop | counterfactual |
| Time-stop only (15:50 ET no TP) | last 5m close before 15:50 | counterfactual |

Record each `cf_*` value back to trades.csv via the `csv_updates[]` array in output JSON.

### 2. Hold-quality score (per trade)

Walk the bars during the trade. Score 0-10:
- (+2) entry within 1 bar of trigger
- (+2) stop never moved against the trade
- (+2) at least one TP fired (or runner survived to time-stop with green close)
- (+2) no panic exit (max drawdown during hold < 50% of max favorable excursion)
- (+2) exit reason matched plan (not "felt wrong")

Tag each trade `hold_quality_score` 0-10.

### 3. Skip-cost retro (per skipped setup)

For each row in `skipped-setups.csv` from today (setup score ≥7 but didn't fire):
- Walk SPY 30 min forward from skip time
- Compute "would-have-been P&L" assuming default entry rules
- Tag as `skip_cost_dollars` (positive = we missed a winner; negative = correct skip)

### 4. Decision grading (per significant tick)

For each `decisions.jsonl` row today where action ≠ "HOLD":
- Walk SPY 30 min forward from decision tick
- Grade A-F based on whether decision aligned with subsequent move
- Append grade back to that decisions.jsonl row (use jq + temp file pattern, atomic write)

### 5. Per-loss chart-walk (per losing trade — Karpathy method)

For each trade with `pnl_dollars < 0`, generate `journal/losses/{date}-{HHMM}-{setup}.md`:

```markdown
# Loss walk: {date} {HHMM} {setup}

## Trade
- Entry: ${entry_premium} qty={qty}
- Exit: ${exit_premium} ({exit_reason}) → ${pnl_dollars:+.0f}
- Hold time: {minutes} min

## Pre-entry context
- SPY: ${spy_at_entry} | VIX: {vix_at_entry} ({vix_dir})
- Ribbon: {stack} (spread {spread_cents}c)
- Filter score: {score}/{score_max}, triggers: {triggers}
- Pattern fingerprint: {fingerprint}  ← for clustering in weekly-review 3.5

## What went wrong (3 sentences max)
{your analysis}

## Candidate blocking filter
{specific filter that would have blocked this; if no good candidate, say "none — this is acceptable variance"}

## Screenshot
![entry](../replays/{date}-{HHMM}-ENTRY-{setup}.png)
![exit](../replays/{date}-{HHMM}-EXIT-{setup}.png)
```

The pattern fingerprint format (4-tuple): `{vix_regime}|{ribbon_stack_at_entry}|{trigger_type}|{outcome_minutes}`.
Example: `vix_low|BEAR|sequence_rejection|stopped_in_15min`.

---

## Output JSON shape

Write to `automation/state/eod-workers/{date}-chart-walks.json`:

```json
{
  "worker": "chart-walks",
  "date": "YYYY-MM-DD",
  "generated_at_et": "ISO",
  "trade_chart_data": [
    {
      "trade_id": "...",
      "cf_runner_target_pnl": 0.0,
      "cf_ribbon_flip_pnl": 0.0,
      "cf_chart_stop_only_pnl": 0.0,
      "cf_time_stop_only_pnl": 0.0,
      "hold_quality_score": 0
    }
  ],
  "skip_costs": [
    {
      "skip_id": "...",
      "setup": "...",
      "skipped_at_et": "HH:MM",
      "skip_cost_dollars": 0.0
    }
  ],
  "decisions_graded_count": 0,
  "loss_walks_generated": ["journal/losses/...md"],
  "csv_updates": [
    {"trade_id": "...", "column": "cf_runner_target_pnl", "new_value": 0.0},
    {"trade_id": "...", "column": "hold_quality_score", "new_value": 8}
  ]
}
```

---

## Time budget

<3 minutes. Heaviest worker — chart replays + screenshot capture + markdown generation.
If running long, SKIP non-loss chart walks first (per-loss is highest value Karpathy artifact).
