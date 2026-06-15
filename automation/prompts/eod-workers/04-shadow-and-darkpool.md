# EOD Worker D — Shadow Scorecard + Dark-Pool Aggregation

> **Scope:** EOD steps 8b + 8c from legacy eod-summary.md.
> Karpathy shadow-mode diff. Dark-pool TRF block aggregation for level discovery.
>
> **Output:** Single JSON file at `automation/state/eod-workers/{date}-shadow-darkpool.json`.

---

## Inputs

- `automation/state/shadow-version.json` (is shadow enabled? what overrides?)
- `automation/state/decisions.jsonl` (today's decisions, both v14 + shadow if enabled)
- `analysis/recommendations/` (target dir for shadow scorecards)
- Alpaca MCP `get_stock_trades` for SPY (dark-pool block detection)
- `automation/state/key-levels.json` (current level set, may be appended)

---

## Tasks

### 1. Shadow-mode scorecard (only if shadow-version.enabled == true)

Read all today's decisions.jsonl rows. Each row has a `version` field (e.g., "v14" or "v15-loose-vix").

For each pair of (v14, shadow) decisions on the same tick:
- ENTRY agreement: did both fire? same direction? same setup?
- EXIT agreement: did both stop / TP at the same bar?
- Hypothetical P&L: if shadow had been live, what's the simulated P&L assuming same fills?

Produce per-day scorecard:

```json
{
  "date": "YYYY-MM-DD",
  "rule_id": "v15-loose-vix",
  "v14_pnl": 0.0,
  "v14_n_trades": 0,
  "shadow_pnl": 0.0,
  "shadow_n_trades": 0,
  "agreement_pct": 0.0,
  "shadow_dominates": false,
  "margin_pnl": 0.0,
  "margin_pct": 0.0,
  "verdict": "needs_more_data | shadow_dominates | v14_dominates | inconclusive"
}
```

Append to `analysis/recommendations/{rule_id}.json#daily_scorecards[]`.
If 7 daily scorecards accumulate AND shadow_dominates in 5+: flag for weekly-review auto-ratification.

If shadow-version.enabled == false: SKIP this section, return `{"shadow_enabled": false}`.

### 2. Dark-pool TRF block aggregation

Read SPY trades from Alpaca for today (use `get_stock_trades` with limit=10000, deduplicated).
Filter for blocks where:
- Trade conditions include "TRF" code (or detected via venue absence)
- Volume ≥ 5000 shares
- Within RTH (09:30-16:00 ET)

Aggregate by price level (round to nearest $0.25):
```
$724.50 → 145,000 shares (3 prints)
$725.00 → 89,000 shares (2 prints)
$724.75 → 67,000 shares (1 print)
```

Top 3 dark-pool clusters become CARRY-tier candidates. Append to `key-levels.json`:

```json
{
  "price": 724.50,
  "tier": "Carry",
  "source": "dark_pool_block",
  "size_shares": 145000,
  "n_prints": 3,
  "discovered_at_et": "ISO",
  "expires_after": "next_trading_day_eod"
}
```

Update `automation/state/dashboard-dialogue.json` with a NOTE about new dark-pool levels for J's morning review.

---

## Output JSON shape

Write to `automation/state/eod-workers/{date}-shadow-darkpool.json`:

```json
{
  "worker": "shadow-and-darkpool",
  "date": "YYYY-MM-DD",
  "generated_at_et": "ISO",
  "shadow": {
    "enabled": false,
    "rule_id": null,
    "scorecard": null
  },
  "darkpool": {
    "n_blocks_processed": 0,
    "n_levels_added": 0,
    "top_clusters": [
      {"price": 724.50, "size_shares": 145000, "n_prints": 3}
    ]
  }
}
```

---

## Time budget

<90 seconds. Alpaca call is the long pole — single batched fetch + Python aggregation.
Skip dark-pool entirely if `params.json#enable_dark_pool_aggregation == false`.
