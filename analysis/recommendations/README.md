# analysis/recommendations/

> A/B scorecard ledger for proposed rule changes. **Karpathy method principle 3 — propose/eval/ratify lifecycle.** No HIGH+ urgency rule change is ratified without a content-addressed comparison logged here.

## Workflow

```
PROPOSAL                                EVALUATION                              RATIFICATION
─────────                               ──────────                              ────────────
Sunday weekly-review                    weekly-review computes                  premarket Step 1c
emits R-NNNN with             ─────►    A/B scorecard:                ─────►    reads scorecard
hypothesis + trigger                    - both runs share data_hash             auto-ratifies if:
observation                             - new run with proposed                 dominates AND
                                          params_overrides                      sub-window stable AND
                                        - written to                            thresholds 4/4 AND
                                          {rule_id}.json here                   evidence n ≥ 20
```

## File format

See [`SCORECARD_TEMPLATE.json`](SCORECARD_TEMPLATE.json) for the complete schema. Required fields:

| Field | Why |
|---|---|
| `rule_id` | Monotonic R-NNNN, matches `recommendations-log.jsonl` |
| `old_run.run_id`, `new_run.run_id` | Both must be content-addressed via `backtest/lib/repro.py` |
| `data_hash_match` | True iff both runs used identical SPY+VIX bars (apples-to-apples). False = scorecard rejected |
| `metrics` | Side-by-side delta on n_trades, hit_rate, expectancy, total_pnl, wl_ratio, max_drawdown, worst_trade, thresholds_passed |
| `dominates` | Computed: new beats or ties on ALL metrics AND strictly better on ≥1 |
| `sub_window_stability` | Split window in half; both halves must pass 4-of-4 independently |
| `auto_ratify_eligible` | Computed gate — only true if all auto-ratify conditions met |
| `verdict` | `auto_ratify` / `needs_review` / `reject` |

## Why side-by-side and not just "v15 is better"

Karpathy: "you can't claim improvement without measuring against an unchanged baseline on the same data." Three failure modes the A/B catches:

1. **Data drift.** v15 backtest uses today's data; v14 was last run last week. v15 looks better but it's just easier bars. → `data_hash_match: false` blocks ratification.
2. **Code drift.** Someone refactored `simulator_real.py` between runs and inadvertently changed exit logic. → `code_hash` differs across runs; metrics compared are not apples-to-apples.
3. **Cherry-picked window.** v15 was tuned on 2026-04-15..2026-05-08 and "wins" but on the prior 30 days it loses. → `sub_window_stability` blocks if either half fails 4-of-4.

## Index of scorecards

This directory will accumulate one `R-NNNN.json` per ratified or declined recommendation. Audit history lives in `analysis/recommendations-log.jsonl` (the lifecycle log) — this folder holds the evidence each recommendation rests on.

## Lifecycle states

```
pending  ──auto_ratify──► ratified  (premarket consumes)
   │
   ├──verdict=needs_review──►  awaiting_J  (J's Sunday review)
   │
   └──verdict=reject──► rejected_auto  (data_hash mismatch, sub-window failure, etc.)
```

J's Sunday role is reduced to:
- **Revoke** an auto-ratified change (override silence-is-consent)
- **Ratify** a `needs_review` recommendation (when scorecard is borderline)
- **Re-issue** a previously declined recommendation if evidence has grown ≥50%

## What this is NOT

- This is **not** a place to write narrative analysis. Findings go in `analysis/backtests/{label}_findings.md`.
- This is **not** the recommendations log. That's `analysis/recommendations-log.jsonl` — the append-only lifecycle ledger.
- This is **not** a run registry. That's `analysis/backtests/REGISTRY.jsonl` — the content-addressed run index.

The three live together: registry says "this run existed with this hash"; recommendations log says "this proposal moved through these states"; this folder says "and here's the evidence the proposal rests on."
