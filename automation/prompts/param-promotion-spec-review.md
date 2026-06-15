# Param Promotion — Stage 1: Spec Compliance Review

> **Multi-Agent Gamma 2.0 — Big Win #10 (Stage 1 of 2).** Source pattern:
> obra/superpowers `subagent-driven-development` two-stage review (spec compliance → code quality)
> with model-tier selection (cheap for mechanical, top-tier for arch).
>
> This stage answers: **does the candidate satisfy every gate in SCORECARD_TEMPLATE.json?**
> Pure mechanical check. No judgment. If any gate is missing or fails: REJECT.
>
> Stage 2 (`param-promotion-quality-review.md`) answers: **is the gate the right gate?**

---

## Inputs (provided in context)

- `analysis/recommendations/{rule_id}.json` (the candidate scorecard)
- `analysis/recommendations/SCORECARD_TEMPLATE.json` (the gate template)
- `analysis/recommendations/v15-adversarial.json` (Big Win #2 adversarial review verdict)
- `automation/state/params.json` (current production)

---

## The 7 mandatory gates

For the candidate to pass spec compliance, ALL 7 must hold.

### Gate 1 — `data_hash_match`
The `data_hash` field in the scorecard MUST equal the data_hash of the most recent SPY/VIX
master CSVs. Re-compute via `repro.compute_run_id` and compare. If different: candidate was
evaluated on stale data. REJECT.

### Gate 2 — `evidence_n_validate >= 20`
The candidate must have produced ≥ 20 trades on the validate window. Below 20 = noise.
Read from scorecard `metrics.validate.n_trades`.

### Gate 3 — `dominates`
Candidate's val_sharpe AND val_pnl AND val_expectancy MUST each be > production's. ALL three.
Read from scorecard `comparison.dominates: true`.

### Gate 4 — `thresholds_4_of_4`
The candidate must clear 4-of-4 mandatory thresholds:
- `validate_pnl >= 0`
- `train_sharpe >= 0` (no validate-window-only artifacts)
- `validate_win_rate >= 0.10` (avoid degenerate near-zero WR)
- `validate_max_drawdown_pct <= 0.30` (no catastrophic-DD candidates)
Read from scorecard `metrics.thresholds_passed: 4`.

### Gate 5 — `sub_window_stable`
The `sub_window_test.py` results for this candidate must show ROBUST verdict:
≥ 3 of 5 sub-windows positive on PnL AND ≥ 3 of 5 positive on Sharpe.
Read from `_state/random_search/sub_window_seed{N}.json#stability.is_robust: true`.

### Gate 6 — `adversarial_no_critical`
The `v15-adversarial.json#bear_objections` array must contain ZERO objections with
`severity == "critical"`. Critical = REJECT. Non-critical bear objections still allow promotion
but route to Stage 2.

### Gate 7 — `live_evidence_consistent`
If we have ≥ 5 live trades since v14 ratification, replay the candidate against `journal/trades.csv`
and verify it would have improved live P&L on the same fills (or at least not regressed > 5%).
If < 5 live trades: SKIP this gate (annotate "INSUFFICIENT_LIVE_DATA" but don't block).

---

## Output JSON shape

Write to `analysis/recommendations/{rule_id}-spec-review.json`:

```json
{
  "candidate_rule_id": "v15-...",
  "reviewed_at_et": "ISO",
  "stage": "spec_compliance",
  "gates": [
    {"gate": 1, "name": "data_hash_match", "passed": true,  "evidence": "data_hash match: abc123 == abc123"},
    {"gate": 2, "name": "evidence_n_validate", "passed": true, "evidence": "n_trades=99 >= 20"},
    {"gate": 3, "name": "dominates", "passed": true, "evidence": "val_sharpe +2.55 > +1.20; val_pnl +$2295 > +$845; val_exp +$23 > +$15"},
    {"gate": 4, "name": "thresholds_4_of_4", "passed": true, "evidence": "val_pnl=+$2295 >=0; train_sh=+1.46 >=0; val_wr=8.1% >=10%? NO -> CHECK"},
    {"gate": 5, "name": "sub_window_stable", "passed": true, "evidence": "is_robust=true (4/5 pnl, 3/5 sharpe)"},
    {"gate": 6, "name": "adversarial_no_critical", "passed": true, "evidence": "0 critical objections"},
    {"gate": 7, "name": "live_evidence_consistent", "passed": "skipped", "evidence": "INSUFFICIENT_LIVE_DATA (3 live trades < 5 threshold)"}
  ],
  "n_passed": 6,
  "n_failed": 0,
  "n_skipped": 1,
  "verdict": "APPROVE_FOR_QUALITY_REVIEW | REJECT_FAILED_GATES",
  "failed_gate_names": [],
  "next_stage": "param-promotion-quality-review.md"
}
```

---

## Single-line emit

```
PROMOTION_SPEC v15-... gates_passed=6/7 verdict=APPROVE_FOR_QUALITY_REVIEW
```

Append to log + dashboard.

---

## What to do on each verdict

- **APPROVE_FOR_QUALITY_REVIEW**: Stage 2 fires next (called by weekly-review Section 7)
- **REJECT_FAILED_GATES**: weekly-review writes a NOTE explaining which gates failed; J reviews; no auto-ratification

---

## Cost (operating principle 3)

This is a mechanical check. Use Sonnet (medium effort). ~$0.03 per promotion. ~$0.10/mo cap.
