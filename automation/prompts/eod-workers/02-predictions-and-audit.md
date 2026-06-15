# EOD Worker B — Predictions + Rule Audit

> **Scope:** EOD steps 2 + 3 from legacy eod-summary.md.
> Grade today-bias predictions; audit rule breaks.
>
> **Output:** Single JSON file at `automation/state/eod-workers/{date}-predictions.json`.

---

## Inputs

- `automation/state/today-bias.json` (predictions to grade)
- `automation/state/circuit-breaker.json` (final state)
- SPY closing data via TradingView MCP `quote_get` for actual outcomes
- `journal/trades.csv` (today's trades for rule-break audit)
- `automation/state/heartbeat-{today}.log` (decision audit trail)
- `journal/{today}.md` (any manual notes)

---

## Tasks

### 1. Grade falsifiable predictions

For each entry in `today-bias.falsifiable_predictions[]`:

```json
{
  "claim": "SPY will hold above 720 by 11:30 ET",
  "actual": "<observed outcome via SPY 1m chart>",
  "verdict": "TRUE | FALSE | UNRESOLVED | PARTIAL",
  "confidence_at_morning": "high | medium | low",
  "lesson": "<1 sentence what to update if wrong>"
}
```

Append each grade to `automation/state/hypothesis-grades.jsonl` (one JSON per line, append-only).

### 2. Rule-break audit

For each of Gamma's 10 rules + the operating principles, scan today's trades and decisions:

| Rule | Audit query |
|---|---|
| 1. No setup, no trade | Any trade with setup_name not in playbook? |
| 2. Wait for the trigger | Any entry where developing_setup.score < score_max at entry tick? |
| 3. Defined stop on entry | Any trade with null premium_stop AND null chart_stop? |
| 4. No adding without trigger | Any add-on with no fresh trigger fire between adds? |
| 5. Daily kill-switch | Did we trade after circuit-breaker.tripped flipped true? |
| 6. Per-trade risk cap | Any trade where premium × qty / start_equity > 0.50? |
| 7. PDT awareness | Did day_trades_used exceed 3 with equity < 25k? |
| 8. Journal real-time | Any trade missing pre-trade thesis or post-trade lesson? |
| 9. No mid-session changes | Any modification to params.json or heartbeat.md timestamps within market hours? |
| 10. Heed Gamma flags | Any trade after a "BLOCKED" log line? |

Each break: append to `automation/state/rule-breaks.jsonl` with `{rule, trade_id, severity, cost_dollars, summary}`.

### 3. Process compliance flag

Compute boolean `clean_session = no rule breaks of severity >= "high"`.
Append to `automation/state/process-compliance.jsonl`: `{date, clean, n_breaks, n_high_severity}`.

---

## Output JSON shape

Write to `automation/state/eod-workers/{date}-predictions.json`:

```json
{
  "worker": "predictions-and-audit",
  "date": "YYYY-MM-DD",
  "generated_at_et": "ISO",
  "predictions_graded": [
    {
      "claim": "...",
      "actual": "...",
      "verdict": "TRUE",
      "confidence_at_morning": "high",
      "lesson": "..."
    }
  ],
  "predictions_summary": {
    "n_total": 0,
    "n_true": 0,
    "n_false": 0,
    "n_unresolved": 0,
    "hit_rate": 0.0
  },
  "rule_breaks": [
    {
      "rule_number": 5,
      "rule_name": "Daily kill-switch",
      "trade_id": "...",
      "severity": "high",
      "cost_dollars": 0,
      "summary": "..."
    }
  ],
  "rule_break_summary": {
    "n_total": 0,
    "n_high": 0,
    "n_medium": 0,
    "n_low": 0,
    "clean_session": true
  }
}
```

---

## Time budget

<60 seconds. Heavy use of Read on small JSONs, no chart replays.
